"""scripts/decision_stats.py reads the real local journal and counts what it says, with no model call."""
from collections import Counter
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import play
import reference_policy
from harness import PLAN_KEEP_QUESTION, PLAN_STEP_QUESTIONS, plan_answer, plan_questions
from kitchen import load_config
from levels import level_config
from scripts.decision_stats import main, report
from spatial_kitchen import SpatialKitchen
from web_server import GameSession
from whitebox_server import SpatialJevClient


class Inline:
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


class Scripted(SpatialJevClient):
    """Heads for the fridge, changes its mind to the serving window and back, then plays the reference policy.

    The first three answers are close calls (margin .02); later ones are clear (.7).
    """

    def __init__(self, config, game):
        super().__init__(config, key='unit-test-not-a-real-key')
        self.game, self.script = game, ['fetch', 'go serve', 'fetch']

    def ask(self, payload):
        criteria = payload['questions']['next_action']['criteria']
        k = self.game().k
        scripted = self.script.pop(0) if self.script else None
        move = reference_policy.choose(k, 'jeff', 'cook')
        choice = (scripted if scripted in criteria else move.key if move and move.key in criteria
                  else next(key for key in ('wait', 'continue', *criteria) if key in criteria))
        other = next(key for key in criteria if key != choice)
        close = scripted is not None
        answer = {'choice': choice, 'sprint': False, 'confidence': None, 'model': 'test-model', 'usage': {}, 'latency': 0.0,
                  'probabilities': {choice: .5, other: .48} if close else {choice: .8, other: .1}}
        if PLAN_STEP_QUESTIONS[0] in plan_questions(payload):
            answer.update(plan_answer({'plan_step_1': 'fetch:beef', 'plan_step_2': 'chop:beef'}, payload))
        elif PLAN_KEEP_QUESTION in plan_questions(payload):
            answer.update(plan_answer({PLAN_KEEP_QUESTION: 'keep'}, payload))
        return answer


def play_round(folder, seconds=20.0, plan=True, ask_on_step_end=False):
    with patch('play.ROOT', Path(folder)):
        # The scripted timeline (the round's end stops Jeff mid-action) was written for the request timing
        # without ai_ask_on_step_end; only the step gap tests turn it on.
        config = {**level_config(load_config(), 'level-2'), 'ai_ask_on_step_end': ask_on_step_end}
        # The scripted timeline was written without the one-press options (released since); rounds with them are
        # counted apart and tested in test_one_press.StatsTests.
        import features
        off = features.check({**json.loads(features.PATH.read_text(encoding='utf-8')),
                              'one_press': {'stage': 'release', 'on': False, 'version': features.VERSIONS['one_press']}})
        with patch.object(features, 'current', lambda: off):
            game = GameSession(config, client_factory=lambda c: Scripted(c, lambda: game),
                               journal_factory=play.Journal, kitchen_factory=SpatialKitchen, log_prefix='whitebox')
        if plan:
            game._command('/api/plan', {'mode': 'choice'})
        clock = [1000.0]
        with patch('jev.time.monotonic', lambda: clock[0]), patch('jev.threading.Thread', Inline):
            game.last_tick = game.last_seen = clock[0]
            assert game._command('/api/start', {'speed': 1})[0] == 200
            game.last_tick = game.last_seen = clock[0]
            while game.k.time < seconds:
                clock[0] += .05
                game.last_seen = clock[0]
                game.tick(clock[0])
            game._command('/api/end', {})
        game.close()
    return next(Path(folder, 'logs').glob('*.jsonl'))


class RealJournalTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = play_round(self.folder.name)
        self.rows = [json.loads(line) for line in self.path.read_text().splitlines()]
        self.model = report([self.path.parent])['models']['test-model']

    def test_decisions_and_close_calls_match_the_answers(self):
        answers = [r for r in self.rows if r['kind'] == 'ai_response']
        self.assertEqual(self.model['decisions']['answered'], len(answers))
        unsure = self.model['unsure']
        self.assertEqual(unsure['with_probabilities'], len(answers))
        self.assertEqual(unsure['below']['0.05']['count'], 3)        # the three scripted close calls
        self.assertEqual(unsure['chose_the_top_option'], 1.0)
        close = [sorted(key.split(' ')[0] for key in r['probabilities']) for r in answers[:3]]
        self.assertEqual(sum(unsure['closest_pairs'].values()), 3)
        self.assertEqual(unsure['closest_pairs'], dict(Counter('/'.join(pair) for pair in close)))

    def test_its_own_changes_of_mind_are_replacements_and_one_back_and_forth(self):
        starts = [r for r in self.rows if r['kind'] == 'action_start' and r['actor'] == 'jeff']
        self.assertEqual([r['action'] for r in starts[:3]], ['fetch', 'go serve', 'fetch'])
        actions = self.model['actions']
        self.assertEqual(actions['started'], len(starts))
        self.assertEqual(actions['replaced_by_own_next_choice'], 2)
        self.assertEqual(actions['back_and_forth'], 1)
        self.assertEqual((actions['knocked_off'], actions['other_interruptions']), (0, 1))   # the round's end stops Jeff

    def test_the_plan_counts_follow_the_requests(self):
        plan = self.model['plan']
        requests = {r['request_id']: r for r in self.rows if r['kind'] == 'ai_request'}
        current = lambda r: r['jeff_plan']['current']
        set_at = [current(r)['set_at'] for r in requests.values() if current(r)]
        self.assertEqual((plan['rounds'], plan['older_rules_rounds'], plan['set']), (1, 0, len(set(set_at))))
        self.assertGreater(plan['set'], 0)
        self.assertEqual(plan['ended'], dict(Counter(r['plan_ended'] for r in requests.values() if r['plan_ended'])))
        answers = [r for r in self.rows if r['kind'] == 'ai_response']
        held = [r for r in answers if current(requests[r['request_id']])]
        self.assertEqual(plan['decisions_with_plan'], len(held))
        self.assertEqual(plan['decisions_without_plan'], len(answers) - len(held))
        self.assertEqual(plan['wait_share_with_plan'], round(sum(r['choice'] == 'wait' for r in held) / len(held), 4))

    def test_the_command_line_writes_the_same_report(self):
        out = Path(self.folder.name, 'report.json')
        self.assertEqual(main([str(self.path), '--out', str(out)]), 0)
        self.assertEqual(json.loads(out.read_text()), report([self.path]))


def row(kind, t, **data):
    return {'kind': kind, 'game_time_ms': round(t * 1000), **data}


class HandBuiltTests(unittest.TestCase):
    def write(self, rows, extra=''):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name, 'round.jsonl')
        path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n' + extra)
        return path

    def test_a_dash_or_a_closing_is_not_a_change_of_mind(self):
        rows = [row('start', 0, jeff_plan=None),
                row('ai_request', 0, request_id=1, candidates=['chop', 'wait']),
                row('ai_response', 0, request_id=1, choice='chop', model='m', applied=True, fresh=True, action_id=1,
                    probabilities={'chop': .6, 'wait': .4, 'not offered': .9}, current_state={'chefs': {'jeff': {'target': 'b1', 'action_kind': 'chop'}}}),
                row('action_start', 0, actor='jeff', action='chop', action_id=1),
                row('interrupted', 4, actor='jeff', action_id=1), row('knocked', 4, actor='jeff'),
                row('action_start', 6, actor='human', action='fetch', action_id=2),
                row('interrupted', 9, actor='human', action_id=2), row('action_start', 9, actor='human', action='go', action_id=3),
                row('end', 60)]
        result = report([self.write(rows, 'not json\n')])
        self.assertEqual(result['unreadable_lines'], 1)
        m = result['models']['m']
        self.assertEqual(m['game_minutes'], 1.0)
        self.assertEqual(m['unsure']['median_top_probability'], .6)     # an option that was not offered is left out
        self.assertEqual(m['actions'], {'started': 1, 'replaced_by_own_next_choice': 0, 'replaced_share': 0.0,
                                        'replaced_per_game_minute': 0.0, 'back_and_forth': 0, 'back_and_forth_per_game_minute': 0.0,
                                        'knocked_off': 1, 'other_interruptions': 0})
        self.assertNotIn('plan', m)

    def test_steps_undone_by_the_next_ones(self):
        done = lambda t, action, n: row('action_done', t, actor='jeff', action=action, action_id=n)
        rows = [row('start', 0, jeff_plan=None),
                row('ai_request', 0, request_id=1, candidates=['wait']),
                row('ai_response', 0, request_id=1, choice='wait', model='m', applied=True, fresh=True),
                done(1, 'put counter3', 1), done(3, 'take counter3', 2),        # put down and taken straight back
                done(4, 'drop', 3), done(5, 'pickup G1', 4),                    # dropped and picked up again
                done(6, 'go lettuce', 5), done(8, 'go serve', 6), done(10, 'go lettuce', 7),   # A -> B -> A
                done(11, 'put counter5', 8), done(30, 'take counter5', 9),      # taken back, but much later
                done(31, 'put b1', 10), done(32, 'chop b1', 11),
                row('action_done', 33, actor='human', action='take b1', action_id=12),
                row('end', 60)]
        undone = report([self.write(rows)])['models']['m']['undone']
        self.assertEqual(undone, {'finished_steps': 11, 'walks_share': round(3 / 11, 4), 'put_then_taken_back': 2,
                                  'put_then_taken_back_per_game_minute': 2.0, 'walk_round_trips': 1,
                                  'walk_round_trips_per_game_minute': 1.0,
                                  'round_trip_routes': {'lettuce/serve': 1}, 'walked_to': {'lettuce': 2, 'serve': 1}})
        self.assertEqual(report([self.write(rows)], put_back=30)['models']['m']['undone']['put_then_taken_back'], 3)

    def test_unsure_with_a_plan_counts_only_after_the_plan_age(self):
        plan = {'steps': 4, 'current': {'steps': [{'work': 'fetch:beef', 'done': True}, {'work': 'chop:beef', 'done': False}],
                                        'set_at': 1.0}, 'options': None}
        rows = [row('start', 0, jeff_plan={'mode': 'choice', 'steps': 4, 'rules_version': 'plan-v2'})]
        for n, t in enumerate((3.0, 7.0), 1):
            rows += [row('ai_request', t, request_id=n, candidates=['go x', 'go y'], jeff_plan=plan),
                     row('ai_response', t, request_id=n, choice='go x', model='m', applied=True, fresh=True,
                         probabilities={'go x': .51, 'go y': .49})]
        rows += [row('ai_request', 9.0, request_id=3, candidates=['wait'], plan_ended='new_preference',
                     jeff_plan={'steps': 4, 'current': None, 'options': {'fetch:beef': 'f', 'serve': 's'}}),
                 row('ai_response', 9.0, request_id=3, choice='wait', model='m', applied=True, fresh=True)]
        m = report([self.write(rows)])['models']['m']
        self.assertEqual(m['unsure']['below']['0.05']['count'], 2)
        self.assertEqual(m['unsure']['closest_pairs'], {'go/go': 2})
        plan = m['plan']
        self.assertEqual(plan['unsure_with_plan'], 1)          # at 7 s the plan had held 6 s; at 3 s only 2 s
        self.assertEqual((plan['set'], plan['median_steps'], plan['ended'], plan['median_hold_seconds']),
                         (1, 2, {'new_preference': 1}, 8.0))
        self.assertEqual((plan['decisions_with_plan'], plan['wait_share_with_plan']), (2, 0.0))
        self.assertEqual((plan['decisions_without_plan'], plan['wait_share_without_plan']), (1, 1.0))

    def test_a_round_under_the_earlier_plan_rules_is_only_counted(self):
        plan = {'seconds': 12, 'current': {'role': 'prep', 'set_at': 1.0, 'expires_at': 13.0}, 'options': None}
        rows = [row('start', 0, jeff_plan={'mode': 'choice', 'seconds': 12, 'rules_version': 'plan-v1'}),
                row('ai_request', 2.0, request_id=1, candidates=['wait'], jeff_plan=plan),
                row('ai_response', 2.0, request_id=1, choice='wait', model='m', applied=True, fresh=True)]
        plan = report([self.write(rows)])['models']['m']['plan']
        self.assertEqual((plan['rounds'], plan['older_rules_rounds'], plan['set'], plan['decisions_with_plan']), (0, 1, 0, 0))

    def test_a_round_without_model_answers_is_skipped(self):
        result = report([self.write([row('start', 0), row('action_start', 1, actor='human', action='fetch', action_id=1)])])
        self.assertEqual((result['rounds'], result['rounds_without_model_answers'], result['models']), (0, 1, {}))


def timed(kind, wall, **data):
    return {'kind': kind, 'game_time_ms': round(wall * 1000), 'elapsed_wall_ms': round(wall * 1000), **data}


def event(seq, kind, wall, **data):
    return {'seq': seq, 'type': kind, 'game_time_ms': round(wall * 1000), 'elapsed_wall_ms': round(wall * 1000), **data}


def chop(n, wall, applied=True, fresh=True):
    return event(n, 'ai_response', wall, request_id=n, action_id=n if applied else None,
                 payload={'choice': {'key': 'chop', 'kind': 'chop', 'target': 'b1'}, 'applied': applied, 'fresh': fresh})


class StepGapTests(unittest.TestCase):
    write = HandBuiltTests.write

    def test_a_journal_gap_is_split_at_the_first_request_and_the_answer_that_started_the_step(self):
        # Journal order: the answer is written before the step it started.
        rows = [timed('start', 0, config={'ai_ask_on_step_end': True}),
                timed('ai_request', 0, request_id=1, candidates=['chop', 'wait']),
                timed('ai_response', .1, request_id=1, choice='chop', model='m', applied=True, fresh=True, action_id=1),
                timed('action_start', .1, actor='jeff', action='chop', action_id=1),
                timed('action_done', 3, actor='jeff', action='chop', action_id=1),
                timed('ai_request', 3.5, request_id=2, candidates=['fetch', 'wait']),
                timed('ai_response', 3.8, request_id=2, choice='wait', model='m', applied=True, fresh=True, action_id=None),
                timed('ai_request', 4, request_id=3, candidates=['fetch', 'wait']),
                timed('ai_response', 4.4, request_id=3, choice='fetch', model='m', applied=True, fresh=True, action_id=2),
                timed('action_start', 4.4, actor='jeff', action='fetch', action_id=2),
                timed('pause', 8), timed('end', 10)]       # closed while paused: 8 wall seconds of play
        gaps = report([self.write(rows)])['models']['m']['step_gaps']
        self.assertEqual(set(gaps), {'ask_on_step_end'})
        g = gaps['ask_on_step_end']
        self.assertEqual((g['rounds'], g['gaps'], g['split_unknown']), (1, 1, 0))
        self.assertEqual([g[part]['median'] for part in ('total', 'waiting_to_ask', 'answers_before_the_step', 'reply')],
                         [1.4, .5, .5, .4])
        self.assertEqual((g['with_discarded_reply_share'], g['seconds_per_round'], g['share_of_round_wall_time']), (0.0, 1.4, .175))

    def test_a_record_gap_finds_its_answer_after_the_step_and_leaves_out_a_pause(self):
        # Record order: the step's start is logged before the answer that started it.
        events = [event(1, 'ai_request', 0, request_id=1),
                  event(2, 'action_start', .1, actor_id='jeff', action_id=1, payload={'action': {'key': 'chop'}}), chop(1, .1),
                  event(3, 'ai_request', 2, request_id=2),
                  event(4, 'action_done', 3, actor_id='jeff', action_id=1, payload={'action': {'key': 'chop'}}),
                  chop(2, 3.2, applied=False, fresh=False),       # asked mid-step, came back after it: discarded
                  event(5, 'ai_request', 3.5, request_id=3),
                  event(6, 'action_start', 4.1, actor_id='jeff', action_id=3, payload={'action': {'key': 'chop'}}), chop(3, 4.1),
                  event(7, 'action_done', 6, actor_id='jeff', action_id=3, payload={'action': {'key': 'chop'}}),
                  event(8, 'pause', 6.5), event(9, 'resume', 9.5),
                  event(10, 'ai_request', 9.6, request_id=4),
                  event(11, 'action_start', 9.8, actor_id='jeff', action_id=4, payload={'action': {'key': 'chop'}}), chop(4, 9.8),
                  event(12, 'action_done', 12, actor_id='jeff', action_id=4, payload={'action': {'key': 'chop'}})]
        record = {'schema': 'chefjeff-pilot-session-v2', 'duration': 12.0,
                  'conditions': {'model_identity': {'model_id': 'm'}, 'request_policy': {'ai_min_interval': 2}}, 'events': events}
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name, 'round.json')
        path.write_text(json.dumps(record))
        gaps = report([path])['models']['m']['step_gaps']
        self.assertEqual(set(gaps), {'min_interval_only'})     # a record from before the switch
        g = gaps['min_interval_only']
        self.assertEqual((g['gaps'], g['split_unknown']), (1, 0))    # the gap with the pause is left out
        self.assertEqual([g[part]['median'] for part in ('total', 'waiting_to_ask', 'answers_before_the_step', 'reply')],
                         [1.1, .5, 0.0, .6])
        self.assertEqual(g['with_discarded_reply_share'], 1.0)
        self.assertEqual(g['share_of_round_wall_time'], round(1.1 / 9, 4))      # 12 wall seconds less the 3 paused

    def test_a_request_written_above_the_step_end_of_its_tick_is_asked_after_it(self):
        # A local journal writes a tick's engine events after that tick's request: the request sent as the
        # step ended comes first, a millisecond earlier, at a game time no earlier than the step's end.
        def at(kind, wall, game, **data):
            return {'kind': kind, 'game_time_ms': round(game * 1000), 'elapsed_wall_ms': round(wall * 1000), **data}
        rows = [at('start', 0, 0, config={'ai_ask_on_step_end': True}),
                at('ai_request', 0, 0, request_id=1, candidates=['chop']),
                at('ai_response', .1, .1, request_id=1, choice='chop', model='m', applied=True, fresh=True, action_id=1),
                at('action_start', .1, .1, actor='jeff', action='chop', action_id=1),
                at('ai_request', 2.999, 3.0, request_id=2, candidates=['fetch']),          # sent as the step ended
                at('action_done', 3.0, 2.98, actor='jeff', action='chop', action_id=1),
                at('ai_response', 4.0, 4.0, request_id=2, choice='fetch', model='m', applied=True, fresh=True, action_id=2),
                at('action_start', 4.0, 4.0, actor='jeff', action='fetch', action_id=2),
                # A request sent in the middle of a step, whose answer starts the next one: not split.
                at('ai_request', 5.0, 5.0, request_id=3, candidates=['go x']),
                at('action_done', 6.0, 6.0, actor='jeff', action='fetch', action_id=2),
                at('ai_response', 6.5, 6.5, request_id=3, choice='go x', model='m', applied=True, fresh=True, action_id=3),
                at('action_start', 6.5, 6.5, actor='jeff', action='go x', action_id=3),
                at('end', 8, 8)]
        g = report([self.write(rows)])['models']['m']['step_gaps']['ask_on_step_end']
        self.assertEqual((g['gaps'], g['split_unknown']), (2, 1))
        self.assertEqual([g[part]['median'] for part in ('waiting_to_ask', 'answers_before_the_step', 'reply')], [0.0, 0.0, 1.0])

    def test_a_step_without_its_answer_counts_but_is_not_split(self):
        rows = [timed('start', 0),
                timed('ai_request', 0, request_id=1, candidates=['chop']),
                timed('ai_response', .1, request_id=1, choice='chop', model='m', applied=True, fresh=True, action_id=1),
                timed('action_start', .1, actor='jeff', action='chop', action_id=1),
                timed('action_done', 2, actor='jeff', action='chop', action_id=1),
                timed('action_start', 2.5, actor='jeff', action='chop', action_id=9),
                timed('end', 5)]
        g = report([self.write(rows)])['models']['m']['step_gaps']['min_interval_only']
        self.assertEqual((g['gaps'], g['split_unknown'], g['total']['median'], g['waiting_to_ask']), (1, 1, .5, None))

    def test_rows_without_wall_times_give_no_step_gaps(self):
        rows = [row('start', 0), row('ai_request', 0, request_id=1, candidates=['chop']),
                row('ai_response', 0, request_id=1, choice='chop', model='m', applied=True, fresh=True, action_id=1),
                row('action_start', 0, actor='jeff', action='chop', action_id=1),
                row('action_done', 2, actor='jeff', action='chop', action_id=1)]
        self.assertNotIn('step_gaps', report([self.write(rows)])['models']['m'])


class StepGapJournalTests(unittest.TestCase):
    def test_asking_on_step_end_shortens_the_wait_in_a_real_round(self):
        gaps = {}
        for on in (False, True):
            with tempfile.TemporaryDirectory() as folder:
                path = play_round(folder, ask_on_step_end=on)
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                gaps.update(report([path])['models']['test-model']['step_gaps'])
            ends = [i for i, r in enumerate(rows) if r['kind'] == 'action_done' and r['actor'] == 'jeff']
            followed = sum(any(r['kind'] == 'action_start' and r.get('actor') == 'jeff' for r in rows[i + 1:]) for i in ends)
            policy = 'ask_on_step_end' if on else 'min_interval_only'
            self.assertEqual((gaps[policy]['gaps'], gaps[policy]['split_unknown']), (followed, 0))
            self.assertGreater(followed, 0)
        off, on = gaps['min_interval_only'], gaps['ask_on_step_end']
        self.assertGreater(off['waiting_to_ask']['median'], 1.0)            # the 2 s minimum after the last request
        self.assertLess(on['waiting_to_ask']['median'], .1)                 # asked when the step ended
        self.assertLess(on['total']['mean'], off['total']['mean'])


if __name__ == '__main__':
    unittest.main()


import time  # noqa: E402

import test_research_save_paths as paths  # noqa: E402
from scripts.research_export import export_package  # noqa: E402


class ResearchRecordTests(paths.SavePathTests):
    """A consented online round through the real HTTP handlers and relay, read as a record and as a package."""

    def answer(self, choice, top, second):
        """Answer choice with probability top, and second for the first other option offered."""
        self.due()
        with self.game.lock:
            self.game.ai.poll()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not self.game.relay.request():
            time.sleep(.005)
        pending = self.game.relay.request()
        criteria = pending['payload']['questions']['next_action']['criteria']
        self.assertIn(choice, criteria)
        other = next(key for key in criteria if key != choice)
        body = {'id': pending['id'], 'choice': choice, 'sprint': False, 'usage': {'input_tokens': 1, 'output_tokens': 1},
                'probabilities': {choice: top, other: second}}
        asked = plan_questions(pending['payload'])
        if asked:
            body['plan'] = {'plan_step_1': 'fetch:beef'} if PLAN_STEP_QUESTIONS[0] in asked else {PLAN_KEEP_QUESTION: 'keep'}
        self.assertEqual(self.request('/api/model/result', body, self.token)[0], 200)
        deadline = time.monotonic() + 2
        while self.game.ai.q.empty() and time.monotonic() < deadline:
            time.sleep(.005)
        with self.game.lock:
            self.game.ai.poll()

    def test_a_record_and_its_package_give_the_same_counts(self):
        self.assertEqual(self.command('plan', mode='choice')[0], 200)
        with self.game.lock:
            self.game.stop_event.set()
            self.game.wake.set()
        receipt = self.begin(True, {'provider': 'compatible', 'model_id': 'test/decider'})
        # To the fridge, then the serving window, then the fridge again: two replacements, one back-and-forth.
        self.answer('fetch', .5, .48)
        self.answer('go serve', .7, .2)
        self.answer('fetch', .9, .05)
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        with tempfile.TemporaryDirectory() as folder:
            download = Path(folder, 'round.json')
            download.write_text(json.dumps({'record': record}))
            package = Path(folder, 'private.cjresearch.zip')
            export_package(self.game.store.path, package)
            from_record, from_package = report([download]), report([package])
        self.assertEqual(from_record['models'], from_package['models'])
        m = from_record['models']['test/decider [one-press]']   # one-press is released: every new round has it
        # Replaying the record rebuilds the summary the results page showed for this round.
        shown = self.game.round_record()
        self.assertEqual(m['outcomes']['money_per_round'], [shown['result']['money']])
        self.assertEqual(m['outcomes']['rounds_without_summary'], 0)
        self.assertEqual({c: {w: v for w, v in counts.items() if w != 'jeff_share'} for c, counts in m['work'].items()},
                         {r['category']: r['counts'] for r in shown['rows'] if any(r['counts'].values())})
        self.assertEqual(m['decisions']['answered'], 3)
        self.assertEqual(m['unsure']['below']['0.05']['count'], 1)
        self.assertEqual(m['unsure']['closest_pairs'], {'fetch/wait': 1})
        self.assertEqual((m['actions']['replaced_by_own_next_choice'], m['actions']['back_and_forth']), (2, 1))
        self.assertEqual(record['conditions']['request_policy']['ai_ask_on_step_end'], True)    # config.json
        self.assertEqual(set(m['step_gaps']), {'ask_on_step_end'})
        plan = m['plan']
        self.assertEqual(plan['set'], 1)          # answered with the first request, carried by the second and third
        self.assertEqual((plan['decisions_with_plan'], plan['decisions_without_plan']), (2, 1))
        self.assertEqual(plan['ended'], {})

    def test_an_expired_package_is_refused(self):
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder, 'private.cjresearch.zip')
            export_package(self.game.store.path, package)
            with patch('scripts.research_export.time.time', lambda: 10 ** 12):
                result = report([package])
        self.assertEqual(result['rounds'], 0)
        self.assertIn('expired', result['refused_files']['private.cjresearch.zip'])
        self.assertIsNotNone(receipt)


# Only the cases above; the inherited ones already run in their own modules.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(ResearchRecordTests, _name, None)


class RecordRowsTests(unittest.TestCase):
    def test_a_records_plan_ends_read_not_recorded(self):
        held = {'steps': 4, 'current': {'steps': [{'work': 'fetch:beef', 'done': False}], 'set_at': 1.0}, 'options': None}
        free = {'steps': 4, 'current': None, 'options': {'fetch:beef': 'f'}}
        events = []
        for n, (t, plan, key) in enumerate(((1000, free, 'wait'), (2000, held, 'fetch'), (5000, free, 'wait')), 1):
            events += [{'seq': 2 * n, 'type': 'ai_request', 'game_time_ms': t, 'request_id': n, 'payload': {'candidates': ['wait', 'fetch'], 'jeff_plan': plan}},
                       {'seq': 2 * n + 1, 'type': 'ai_response', 'game_time_ms': t, 'request_id': n,
                        'payload': {'choice': {'key': key, 'kind': key}, 'applied': True, 'fresh': True}}]
        record = {'schema': 'chefjeff-pilot-session-v2', 'duration': 30.0,
                  'conditions': {'model_identity': None, 'jeff_plan': {'mode': 'choice', 'steps': 4, 'rules_version': 'plan-v2'}},
                  'events': events}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'round.json')
            path.write_text(json.dumps(record))
            plan = report([path])['models']['not reported']['plan']
        self.assertEqual((plan['set'], plan['ended'], plan['median_hold_seconds']), (1, {'not_recorded': 1}, 4.0))
        self.assertEqual((plan['decisions_with_plan'], plan['wait_share_with_plan'], plan['wait_share_without_plan']), (1, 0.0, 1.0))

    def test_a_round_in_two_inputs_counts_once_from_its_fuller_copy(self):
        def record(answers):
            events = []
            for n in range(1, answers + 1):
                events += [{'seq': 2 * n, 'type': 'ai_request', 'game_time_ms': n * 1000, 'request_id': n, 'payload': {'candidates': ['wait']}},
                           {'seq': 2 * n + 1, 'type': 'ai_response', 'game_time_ms': n * 1000, 'request_id': n,
                            'payload': {'choice': {'key': 'wait', 'kind': 'wait'}, 'applied': True, 'fresh': True}}]
            return {'schema': 'chefjeff-pilot-session-v2', 'round_id': 'r' * 32, 'duration': 10.0,
                    'conditions': {'model_identity': {'model_id': 'm'}}, 'events': events}
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'early.json').write_text(json.dumps(record(2)))
            Path(folder, 'final.json').write_text(json.dumps({'record': record(3)}))
            result = report([folder])
        self.assertEqual((result['rounds'], result['duplicate_rounds_dropped']), (1, 1))
        self.assertEqual(result['models']['m']['decisions']['answered'], 3)

    def test_a_legacy_record_is_counted_as_unsupported(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'old.json')
            path.write_text(json.dumps({'schema': 'chefjeff-pilot-session-v1'}))
            result = report([folder])
        self.assertEqual((result['files'], result['rounds'], result['unsupported_records']), (1, 0, 1))
