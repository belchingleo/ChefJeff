"""Every way a consented round can close reaches the database complete, or says it did not.

Synthetic loopback rounds only: the model answers come from the real BrowserRelay test path
(test_research_http), never a provider. Each round is read back from SQLite, through the
player's own download and through the private export package.
"""
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest import mock

from research_record import validate_record
import test_research_http as base
from scripts.research_export import export_package, verify_package


class SavePathTests(base.ResearchHTTPTests):
    def human_action(self):
        with self.game.lock:
            action = self.game.k.actions('human')[0]
        status, _ = self.command('action', action=action.key, expected=list(action.expected))
        self.assertEqual(status, 200)

    def due(self):
        # Several answers in one synthetic round: skip the wall-clock spacing between requests.
        with self.game.lock:
            self.game.ai.last_request = float('-inf')
            self.game.ai.last_revision = -1

    def browser_answer(self, choice, stale=False):
        self.due()
        super().browser_answer(choice, stale)

    def legal_choice(self):
        """A real action key from the pending request, so Jeff's choice is applied."""
        self.due()
        with self.game.lock:
            self.game.ai.poll()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not self.game.relay.request():
            time.sleep(.005)
        criteria = self.game.relay.request()['payload']['questions']['next_action']['criteria']
        return next(key for key in criteria if key not in ('wait', 'continue'))

    def play(self):
        """Human input, an applied AI action, wait, continue and a stale answer in one round."""
        receipt = self.begin_manual_relay()
        self.human_action()
        self.browser_answer(self.legal_choice())
        self.browser_answer('continue')  # offered while Jeff's job runs; wait is offered once it is done
        self.human_action()
        with self.game.lock:
            while self.game.k.chefs['jeff'].job:
                self.game.k.advance(.2)
        self.browser_answer('continue')  # asked while the job ran, answered after it ended
        self.browser_answer('wait')
        self.browser_answer('wait', stale=True)
        with self.game.lock:
            self.game.k.advance(1.0)
        return receipt

    def natural_end(self):
        with self.game.lock:
            now = time.monotonic()
            self.game.last_seen = now
            self.game.last_tick = now - 400  # one tick call runs the whole remaining round
        self.game.tick(now)
        self.assertEqual(self.game.phase, 'ended')

    def saved(self, receipt, aborted, reason=None):
        """The finished round as stored, as downloaded and as exported."""
        with sqlite3.connect(self.game.store.path) as db:
            rows = db.execute('SELECT count(*) FROM records').fetchone()[0]
        stored = self.game.store.download(receipt['id'], receipt['deletion_token'])
        status, data = self.request('/api/contribution/download',
                                    {k: receipt[k] for k in ('id', 'deletion_token')})
        self.assertEqual(status, 200)
        record = data['record']
        self.assertEqual(record, stored)
        validate_record(record)
        types = [e['type'] for e in record['events']]
        self.assertTrue(record['quality']['complete'], record['quality'])
        self.assertIsNotNone(record['ended_at'])
        self.assertGreater(record['duration'], 0)
        self.assertEqual(record['aborted'], aborted)
        self.assertIn('end', types)
        for kind in ('browser_input', 'ai_request', 'ai_response', 'state_checkpoint'):
            self.assertIn(kind, types)
        responses = [e['payload']['choice']['key'] for e in record['events'] if e['type'] == 'ai_response']
        self.assertTrue({'wait', 'continue'} <= set(responses), responses)
        for event in record['events']:  # the old failure: a null link left inside a payload
            self.assertFalse({'action_id', 'request_id', 'input_id'} & set(event['payload']), event)
        if reason:
            self.assertEqual(record['termination']['session_close']['reason'], reason)
        self.assertIsNone(self.game.research_error)
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / 'private.cjresearch.zip'
            export_package(self.game.store.path, package)
            self.assertEqual(verify_package(package, database=self.game.store.path)['rounds'], rows)
        return record

    def contribute(self):
        """What the page does at the result screen with automatic contribution on."""
        return self.command('contribution/save', consent=True, consent_version=self.consent_version,
                            consent_mode='standing')

    @property
    def consent_version(self):
        from hosted_records import CONSENT_VERSION
        return CONSENT_VERSION

    def test_natural_end_saves_the_whole_round(self):
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute(), (200, {'receipt': receipt}))
        record = self.saved(receipt, aborted=False)
        self.assertEqual(record['termination']['game_condition'], 'round_limit')
        self.assertGreaterEqual(record['duration'], 179)

    def test_manual_end_saves_the_whole_round(self):
        receipt = self.play()
        self.assertEqual(self.command('end')[0], 200)
        self.saved(receipt, aborted=True)

    def test_restart_saves_the_paused_round_before_the_next_one(self):
        receipt = self.play()
        self.assertEqual(self.command('pause')[0], 200)
        self.assertEqual(self.command('restart')[0], 200)
        self.assertEqual(self.game.phase, 'running')
        self.saved(receipt, aborted=True)

    def test_next_level_keeps_the_finished_round_and_its_close(self):
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        self.assertEqual(self.command('next', level='level-2')[0], 200)
        self.saved(receipt, aborted=False, reason='next_level')

    def test_page_close_mid_round_saves_what_happened(self):
        receipt = self.play()
        self.assertEqual(self.request('/api/session/close', {}, self.token)[0], 200)
        self.saved(receipt, aborted=True, reason='page_close_request')

    def test_page_close_after_the_result_screen_adds_the_close(self):
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.request('/api/session/close', {}, self.token)[0], 200)
        self.saved(receipt, aborted=False, reason='page_close_request')

    def test_a_failed_final_save_is_reported_not_shown_as_contributed(self):
        receipt = self.play()
        with mock.patch.object(self.game.store, 'update', side_effect=sqlite3.OperationalError('disk I/O error')):
            self.assertEqual(self.command('end')[0], 200)
            state = self.game.public_state()
            self.assertEqual(state['hosted']['research_error'], 'storage_failed')
            self.assertFalse(state['hosted']['contributed'])
            status, data = self.contribute()
            self.assertEqual(status, 503)
            self.assertIn('保存失败', data['error'])
        # Only the opening snapshot is on disk; it still says so.
        partial = self.game.store.download(receipt['id'], receipt['deletion_token'])
        self.assertFalse(partial['quality']['complete'])
        self.assertIsNone(partial['ended_at'])
        # Retrying once storage works saves the same finished round in full.
        self.assertEqual(self.contribute(), (200, {'receipt': receipt}))
        state = self.game.public_state()
        self.assertTrue(state['hosted']['contributed'])
        self.saved(receipt, aborted=True)


# Only the paths above; the inherited HTTP tests already run in test_research_http.
for _name in dir(base.ResearchHTTPTests):
    if _name.startswith('test_'):
        setattr(SavePathTests, _name, None)
