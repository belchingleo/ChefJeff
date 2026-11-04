"""Consented online rounds replay exactly from their own record (v7 terms).

Synthetic loopback rounds through the real HTTP handlers and relay test path; no model is called.
"""
import contextlib
import io
import json
import tempfile
import time
from pathlib import Path

import research_replay
from research_record import validate_record
from scripts.check_research_record import main as check_cli
from scripts.research_export import export_package, verify_package
import test_research_save_paths as paths
from web_server import PLAYER_MESSAGES


class ReplayTests(paths.SavePathTests):
    def browser_inputs(self):
        """Every kind of input the page sends: walk, sprint, position reports, Space, throw, a preset message."""
        seq = 0
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            seq += 1
            self.assertEqual(self.command('move', dx=dx, dy=dy, seq=seq, sprint=seq == 1)[0], 200)
            with self.game.lock:
                self.game.k.advance(.4)
                x, y = self.game.k.positions['human']
            self.assertEqual(self.command('position', seq=seq, at=[x + .05, y], base=0, press=False)[0], 200)
        self.assertEqual(self.command('move', dx=0, dy=0, seq=seq + 1)[0], 200)
        for aim in ([1, 0], [0, 1], [-1, 0], [0, -1]):
            with self.game.lock:
                hand = self.game.k.chefs['human'].hand
                x, y = self.game.k.positions['human']
            self.command('interact', expected_item=hand.id if hand else None, aim=aim, at=[x, y], base=0)
            with self.game.lock:
                self.game.k.advance(.5)
                hand = self.game.k.chefs['human'].hand
            if hand:
                self.command('throw', direction=[0, 1], expected_item=hand.id, at=[x, y], base=0)
                with self.game.lock:
                    self.game.k.advance(1.0)
        self.assertEqual(self.command('communicate', code=next(iter(PLAYER_MESSAGES)))[0], 200)

    def test_a_consented_round_replays_exactly_from_its_record(self):
        receipt = self.play()
        self.browser_inputs()
        self.browser_answer(self.legal_choice())
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.saved(receipt, aborted=False)
        calls = {row['call'] for row in record['replay']['inputs']}
        self.assertTrue({'advance', 'start', 'set_manual', 'sprint', 'report_position'} <= calls, calls)
        self.assertEqual(record['quality']['replay'], 'engine_inputs')
        report = research_replay.check(record)
        self.assertEqual(report['replay'], 'verified', report['replay_mismatches'])
        self.assertGreater(report['replay_states_checked'], 100)
        self.assertEqual(report['seq_gaps'], [])
        self.assertEqual(report['replay_end_time_ms'], record['termination']['last_game_time_ms'])
        requests = list(research_replay.rebuild_requests(record))
        self.assertGreater(len(requests), 3)
        self.assertEqual({r['status'] for r in requests}, {'verified'}, [r['request_id'] for r in requests if r['status'] != 'verified'])
        self.assertTrue(any('player_communication' in r['rebuilt']['state'] for r in requests))
        # The rebuilt kitchen is the recorded one, including what only the engine knows.
        with self.game.lock:
            self.assertEqual(research_replay.rebuild(record).inputs, self.game.k.inputs)

    def test_command_line_reads_downloads_and_the_private_database(self):
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        status, data = self.request('/api/contribution/download', {k: receipt[k] for k in ('id', 'deletion_token')})
        self.assertEqual(status, 200)
        with tempfile.TemporaryDirectory() as folder:
            download = Path(folder) / 'round.json'
            download.write_text(json.dumps(data))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(check_cli([str(download), '--database', str(self.game.store.path)]), 0)
        reports = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([r['replay'] for r in reports], ['verified', 'verified'])

    def answer_with(self, **extra):
        """A browser model result carrying optional probabilities and memory provenance."""
        self.due()
        with self.game.lock:
            self.game.ai.poll()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not self.game.relay.request():
            time.sleep(.005)
        pending = self.game.relay.request()
        criteria = pending['payload']['questions']['next_action']['criteria']
        choice = next(key for key in criteria if key not in ('wait', 'continue'))
        body = {'id': pending['id'], 'choice': choice, 'sprint': False, 'usage': {'input_tokens': 1, 'output_tokens': 1}}
        body.update({key: value(criteria, choice) if callable(value) else value for key, value in extra.items()})
        status, _ = self.request('/api/model/result', body, self.token)
        if status == 200:
            deadline = time.monotonic() + 2
            while self.game.ai.q.empty() and time.monotonic() < deadline:
                time.sleep(.005)
            with self.game.lock:
                self.game.ai.poll()
        return status, choice

    def test_reported_probabilities_and_memory_sources_are_kept_with_the_round(self):
        receipt = self.begin_manual_relay()
        self.human_action()
        source = 'ab' * 16
        provenance = {'version': 2, 'source_round_ids': [source], 'context_sha256': 'cd' * 32}
        condition = {'enabled': True, 'version': 2, 'used_rounds': 1, 'omitted_rounds': 0}
        other_key = {}
        def split(criteria, choice):
            other_key['key'] = next(k for k in criteria if k != choice)
            return {choice: .75, other_key['key']: .25}
        status, choice = self.answer_with(probabilities=split,
                                          memory_provenance=provenance, memory_condition=condition)
        self.assertEqual(status, 200)
        self.assertEqual(self.answer_with(probabilities={'not-offered': 1.0})[0], 409)
        self.assertEqual(self.answer_with(probabilities=lambda c, choice: {choice: 1.5})[0], 409)
        other = {**provenance, 'source_round_ids': ['ef' * 16]}
        self.assertEqual(self.answer_with(memory_provenance=other, memory_condition=condition)[0], 409)
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        reported = [r['payload']['probabilities'] for r in record['events'] if r['type'] == 'ai_response']
        self.assertIn({choice: .75, other_key['key']: .25}, reported)
        kept = record['conditions']['memory_provenance']
        self.assertEqual((kept['source_round_ids'], kept['context_sha256'], kept['source']), ([source], 'cd' * 32, 'browser-reported'))

    def test_a_round_with_jeffs_plan_keeps_the_condition_and_replays_exactly(self):
        self.assertEqual(self.command('plan', mode='choice')[0], 200)
        receipt = self.begin_manual_relay()
        initial = self.game.store.download(receipt['id'], receipt['deletion_token'])
        self.assertEqual(initial['conditions']['jeff_plan'], {'mode': 'choice', 'steps': 4, 'rules_version': 'plan-v2'})
        self.human_action()
        self.assertEqual(self.answer_with(plan={'plan_step_1': 'fetch:beef', 'plan_step_2': 'chop:beef'})[0], 200)
        self.assertEqual(self.answer_with()[0], 200)
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['jeff_plan'], initial['conditions']['jeff_plan'])
        with tempfile.TemporaryDirectory() as folder:     # the private export package keeps and verifies it too
            package = Path(folder) / 'private.cjresearch.zip'
            export_package(self.game.store.path, package)
            self.assertEqual(verify_package(package)['rounds'], 1)
        plans = [e['payload']['jeff_plan'] for e in record['events'] if e['type'] == 'ai_request']
        self.assertIsNone(plans[0]['current'])
        self.assertEqual(plans[1]['current']['steps'], [{'work': 'fetch:beef', 'done': False}, {'work': 'chop:beef', 'done': False}])
        requests = list(research_replay.rebuild_requests(record))
        self.assertEqual({r['status'] for r in requests}, {'verified'})
        self.assertIn('plan_step_1', requests[0]['rebuilt']['questions'])
        self.assertIn('plan_keep', requests[1]['rebuilt']['questions'])
        self.assertEqual(requests[1]['rebuilt']['state']['jeff_plan']['steps'][0]['work'], 'fetch:beef')

    def test_a_round_with_the_rolling_intent_keeps_the_condition_and_replays_exactly(self):
        self.assertEqual(self.command('plan', mode='rolling')[0], 200)
        receipt = self.begin_manual_relay()
        initial = self.game.store.download(receipt['id'], receipt['deletion_token'])
        self.assertEqual(initial['conditions']['jeff_plan'], {'mode': 'rolling', 'steps': 2, 'rules_version': 'rolling-v1'})
        self.human_action()
        self.assertEqual(self.answer_with(plan={'plan_step_1': 'fetch:beef', 'plan_step_2': 'chop:beef'})[0], 200)
        self.assertEqual(self.answer_with(plan={'plan_step_1': 'take_plate'})[0], 200)
        self.assertEqual(self.answer_with()[0], 200)
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['jeff_plan'], initial['conditions']['jeff_plan'])
        plans = [e['payload']['jeff_plan'] for e in record['events'] if e['type'] == 'ai_request']
        self.assertEqual({p['mode'] for p in plans}, {'rolling'})
        self.assertIsNone(plans[0]['current'])
        self.assertEqual([s['work'] for s in plans[1]['current']['steps']], ['fetch:beef', 'chop:beef'])
        self.assertEqual([s['work'] for s in plans[2]['current']['steps']], ['take_plate'])    # each answer replaces the last
        requests = list(research_replay.rebuild_requests(record))
        self.assertEqual({r['status'] for r in requests}, {'verified'})
        for request in requests[:3]:     # asked at every request, never keep or drop
            self.assertIn('plan_step_1', request['rebuilt']['questions'])
            self.assertNotIn('plan_keep', request['rebuilt']['questions'])
        self.assertEqual(requests[2]['rebuilt']['state']['plan_rules_version'], 'rolling-v1')

    def test_a_tampered_record_is_reported_as_diverged(self):
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        first = next(row for row in record['replay']['inputs'] if row['call'] == 'advance')
        first['seconds'] += .5
        self.assertEqual(research_replay.check(record)['replay'], 'diverged')

    def test_without_prestart_consent_no_inputs_are_kept(self):
        self.assertEqual(self.command('browser-ready', connected=True)[0], 200)
        self.assertEqual(self.command('start')[0], 200)
        with self.game.lock:
            self.game.k.advance(2)
        self.assertEqual(self.command('end')[0], 200)
        status, data = self.command('contribution/save', consent=True, consent_version=self.consent_version,
                                    consent_mode='round')
        self.assertEqual(status, 200)
        record = self.game.store.download(data['receipt']['id'], data['receipt']['deletion_token'])
        self.assertIsNone(record['replay'])
        self.assertEqual(record['quality']['replay'], 'not_claimed')
        self.assertIn('engine_inputs_not_collected_without_prestart_consent', record['quality']['missing'])
        self.assertEqual(research_replay.check(record)['replay'], 'not_available')


# Only the cases above; the inherited ones already run in their own modules.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(ReplayTests, _name, None)
