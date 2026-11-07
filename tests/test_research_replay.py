"""Consented online rounds replay exactly from their own record (v7 terms).

Synthetic loopback rounds through the real HTTP handlers and relay test path; no model is called.
"""
import contextlib
import io
import json
import tempfile
import time
from unittest.mock import patch
from pathlib import Path

import one_press
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
        self.assertEqual(initial['conditions']['jeff_plan'], {'mode': 'rolling', 'steps': 2, 'rules_version': 'rolling-v3'})
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
        self.assertEqual(requests[2]['rebuilt']['state']['plan_rules_version'], 'rolling-v3')

    def test_a_round_keeps_the_released_one_press_and_replays_exactly(self):
        self.assertEqual(self.command('one-press', name='put_then_take', on=False)[0], 400)   # released: no switch
        receipt = self.begin_manual_relay()
        initial = self.game.store.download(receipt['id'], receipt['deletion_token'])
        condition = {'put_then_take': True, 'wash_from_returns': True, 'version': one_press.VERSION}
        self.assertEqual(initial['conditions']['one_press'], condition)
        self.assertEqual(initial['conditions']['features']['one_press'], {'on': True, 'version': one_press.VERSION})
        self.assertEqual({name: value['on'] for name, value in initial['conditions']['features'].items()},
                         {'one_press': True, 'jeff_plan': False, 'rolling_intent': False, 'undo_note': False,
                          'compact_input': False, 'ask_ahead': False})
        with self.game.lock:                                    # the human leaves beef on a board
            k = self.game.k
            for chosen in (lambda a: a.key == 'fetch', lambda a: a.kind == 'put_board'):
                k.start('human', next(a for a in k.actions('human') if chosen(a)))
                while k.chefs['human'].job:
                    k.advance(.05)
            board = next(key for key, station in k.stations.items() if station.food is not None and key.startswith('b'))
        self.assertEqual(self.answer_with(choice=lambda criteria, _: 'fetch')[0], 200)
        with self.game.lock:
            while self.game.k.chefs['jeff'].job:
                self.game.k.advance(.05)
        where = lambda criteria, _: {'put_where': next(key for key in criteria if key.startswith('put counter'))}
        self.assertEqual(self.answer_with(choice=lambda criteria, _: 'put then take ' + board, plan=where)[0], 200)
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['one_press'], condition)
        flags = [e['payload']['one_press'] for e in record['events'] if e['type'] == 'ai_request']
        self.assertEqual(flags[0], {'put_then_take': True, 'wash_from_returns': True})
        started = [e['payload']['one_press_start'] for e in record['events'] if 'one_press_start' in e['payload']]
        self.assertEqual([(s['first']['key'], s['fallback']) for s in started], [(started[0]['first']['key'], False)])
        self.assertTrue(started[0]['first']['key'].startswith('put counter'))
        requests = list(research_replay.rebuild_requests(record))
        self.assertEqual({r['status'] for r in requests}, {'verified'})
        asked = [r for r in requests if 'put_where' in r['rebuilt']['questions']]
        self.assertTrue(asked and 'put then take ' + board in asked[0]['rebuilt']['questions']['next_action']['criteria'])
        self.assertEqual(research_replay.check(record)['replay'], 'verified')

    def test_a_round_with_undo_notes_keeps_the_step_and_replays_exactly(self):
        import undo_note
        with self.game.lock:
            self.game.features = {**self.game.features, 'undo_note': {**self.game.features['undo_note'], 'on': True}}
        receipt = self.begin_manual_relay()
        initial = self.game.store.download(receipt['id'], receipt['deletion_token'])
        self.assertEqual(initial['conditions']['features']['undo_note'], {'on': True, 'version': undo_note.VERSION})
        with self.game.lock:                                    # the human leaves beef on a board
            k = self.game.k
            for chosen in (lambda a: a.key == 'fetch', lambda a: a.kind == 'put_board'):
                k.start('human', next(a for a in k.actions('human') if chosen(a)))
                while k.chefs['human'].job:
                    k.advance(.05)
            board = next(key for key, station in k.stations.items() if station.food is not None and key.startswith('b'))
        self.assertEqual(self.answer_with(choice=lambda criteria, _: 'fetch')[0], 200)
        with self.game.lock:
            while self.game.k.chefs['jeff'].job:
                self.game.k.advance(.05)
        where = lambda criteria, _: {'put_where': next(key for key in criteria if key.startswith('put counter'))}
        self.assertEqual(self.answer_with(choice=lambda criteria, _: 'put then take ' + board, plan=where)[0], 200)
        with self.game.lock:
            for _ in range(200):
                self.game.k.advance(.05)
                self.game.ai.poll()
                if self.game.ai.chain is None and self.game.k.chefs['jeff'].job is None:
                    break
        self.assertEqual(self.answer_with(choice=lambda criteria, _: 'wait')[0], 200)
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        steps = [e['payload']['undo_note']['step'] for e in record['events'] if e['type'] == 'ai_request']
        self.assertIsNone(steps[0])
        self.assertTrue(any(s and s['take'] and s['take']['station'] == board for s in steps))
        requests = list(research_replay.rebuild_requests(record))
        self.assertEqual({r['status'] for r in requests}, {'verified'})
        self.assertTrue(any('(Note: this puts' in label for r in requests
                            for label in r['rebuilt']['questions']['next_action']['criteria'].values()))
        self.assertEqual(research_replay.check(record)['replay'], 'verified')

    def test_a_round_closed_mid_way_replays_with_its_aborted_flag(self):
        # The session marks the round aborted when the page closes; no engine input carries that.
        receipt = self.play()
        self.assertEqual(self.request('/api/session/close', {}, self.token)[0], 200)
        record = self.saved(receipt, aborted=True, reason='page_close_request')
        self.assertTrue(record['aborted'])
        report = research_replay.check(record)
        self.assertEqual(report['replay'], 'verified', report['replay_mismatches'])
        # The flag is taken from the record only when the record says so.
        record['aborted'] = False
        self.assertEqual(research_replay.check(record)['replay'], 'diverged')

    def test_a_round_sent_in_the_compact_format_replays_exactly(self):
        import features
        import wire_format
        on = {key: dict(value) for key, value in features.current().items()}
        on['compact_input']['on'] = True
        with patch.object(features, 'current', lambda: {key: dict(value) for key, value in on.items()}):
            self.game.features = features.current()          # as a session started with the switch on
            receipt = self.begin_manual_relay()
            self.human_action()
            for _ in range(3):
                with self.game.lock:
                    self.game.ai.poll()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and not self.game.relay.request():
                    time.sleep(.005)
                sent = self.game.relay.request()
                self.assertEqual(sent['wire']['version'], wire_format.VERSION)          # the page gets the two parts
                self.assertEqual(self.answer_with()[0], 200)
            self.natural_end()
            self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['features']['compact_input'], {'on': True, 'version': wire_format.VERSION})
        requests = list(research_replay.rebuild_requests(record))
        self.assertGreater(len(requests), 2)
        self.assertEqual({r['status'] for r in requests}, {'verified'})      # the record keeps the payload, not the wire
        self.assertEqual(research_replay.check(record)['replay'], 'verified')

    def test_a_request_asked_ahead_replays_exactly(self):
        import ask_ahead
        receipt = self.begin_manual_relay()
        with self.game.lock:
            self.game.ai.ask_ahead = True
        # Jeff walks somewhere; while he walks, replies are slow enough that his step will end first.
        walk = lambda criteria, _: next(key for key in criteria if key.startswith('go '))
        self.assertEqual(self.answer_with(choice=walk)[0], 200)
        with self.game.lock:
            self.assertIsNotNone(self.game.k.chefs['jeff'].job)
            self.game.ai.reply_times = [60.0]
        self.due()
        with self.game.lock:
            self.game.ai.poll()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not self.game.relay.request():
            time.sleep(.005)
        self.assertEqual(self.answer_with()[0], 200)
        with self.game.lock:                     # the answer waits for the walk to end, then is carried out or dropped
            k, held = self.game.k, self.game.ai.held
            self.assertIsNotNone(held)
            walking = held[0]['ahead']['job_id']
            while k.chefs['jeff'].job is not None and k.chefs['jeff'].job.id == walking:
                k.advance(.05)
            self.game.ai.poll()
            self.assertIsNone(self.game.ai.held)
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertTrue(record['conditions']['request_policy']['ask_ahead'])
        asked = [e for e in record['events'] if e['type'] == 'ai_request' and 'ask_ahead' in e['payload']]
        self.assertGreaterEqual(len(asked), 1)          # the next step, as slow, is asked ahead again
        self.assertEqual(set(asked[0]['payload']['ask_ahead']), {'job_id', 'predicted_end_t'})
        requests = list(research_replay.rebuild_requests(record))
        self.assertEqual({r['status'] for r in requests}, {'verified'})
        ahead = next(r for r in requests if r['request_id'] == asked[0]['request_id'])
        self.assertEqual(ahead['rebuilt']['state']['kitchen']['time'], asked[0]['payload']['ask_ahead']['predicted_end_t'])
        answered = [e for e in record['events'] if e['type'] == 'ai_response' and 'ask_ahead_result' in e['payload']]
        self.assertGreaterEqual(len(answered), 1)
        self.assertIn(answered[0]['payload']['ask_ahead_result']['result'], ('applied', 'discarded'))
        self.assertEqual(research_replay.check(record)['replay'], 'verified')

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
