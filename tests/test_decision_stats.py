"""scripts/decision_stats.py reads the real local journal and counts what it says, with no model call."""
from collections import Counter
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import play
import reference_policy
from harness import action_part
from kitchen import Action, load_config
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
        if 'plan_role' in payload['questions']:
            answer['plan_role'] = 'prep'
        return answer


def play_round(folder, seconds=20.0, plan=True):
    with patch('play.ROOT', Path(folder)):
        game = GameSession(level_config(load_config(), 'level-2'), client_factory=lambda c: Scripted(c, lambda: game),
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

    def test_the_plan_parts_follow_the_started_actions(self):
        plan = self.model['plan']
        self.assertEqual(plan['rounds'], 1)
        self.assertEqual(set(plan['set']), {'prep'})
        held = plan['actions_while_held']['prep']
        expected = {'in_part': 0, 'other_part': 0, 'no_part': 0}
        requests = {r['request_id']: r for r in self.rows if r['kind'] == 'ai_request'}
        for r in self.rows:
            current = (requests.get(r.get('request_id'), {}).get('jeff_plan') or {}).get('current') if r['kind'] == 'ai_response' else None
            if current and r['applied'] and r['action_id'] is not None and r['choice'] not in ('wait', 'continue'):
                chef = r['current_state']['chefs']['jeff']
                part = action_part(Action(r['choice'], '', chef['action_kind'], chef['target']), r['current_state'])
                expected['no_part' if part is None else 'in_part' if part == 'prep' else 'other_part'] += 1
        self.assertEqual({k: held[k] for k in expected}, expected)
        self.assertGreater(held['in_part'], 0)

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

    def test_unsure_with_a_plan_counts_only_after_the_plan_age(self):
        plan = {'seconds': 12, 'current': {'role': 'prep', 'set_at': 1.0, 'expires_at': 13.0}, 'options': None}
        rows = [row('start', 0, jeff_plan={'mode': 'choice', 'seconds': 12, 'rules_version': 'plan-v1'})]
        for n, t in enumerate((3.0, 7.0), 1):
            rows += [row('ai_request', t, request_id=n, candidates=['go x', 'go y'], jeff_plan=plan),
                     row('ai_response', t, request_id=n, choice='go x', model='m', applied=True, fresh=True,
                         probabilities={'go x': .51, 'go y': .49})]
        rows += [row('ai_request', 9.0, request_id=3, candidates=['wait'], plan_ended='new_preference',
                     jeff_plan={'seconds': 12, 'current': None, 'options': {'prep': 'p', 'flexible': 'f'}}),
                 row('ai_response', 9.0, request_id=3, choice='wait', model='m', applied=True, fresh=True)]
        m = report([self.write(rows)])['models']['m']
        self.assertEqual(m['unsure']['below']['0.05']['count'], 2)
        self.assertEqual(m['unsure']['closest_pairs'], {'go/go': 2})
        self.assertEqual(m['plan']['unsure_with_plan'], 1)          # at 7 s the plan had held 6 s; at 3 s only 2 s
        self.assertEqual(m['plan']['ended'], {'new_preference': 1})
        self.assertEqual(m['plan']['median_hold_seconds'], 8.0)

    def test_a_round_without_model_answers_is_skipped(self):
        result = report([self.write([row('start', 0), row('action_start', 1, actor='human', action='fetch', action_id=1)])])
        self.assertEqual((result['rounds'], result['rounds_without_model_answers'], result['models']), (0, 1, {}))


if __name__ == '__main__':
    unittest.main()
