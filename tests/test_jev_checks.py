"""scripts/jev_replay_check.py and scripts/hands_full_check.py on small journals, with a stand-in for Jev."""
from copy import deepcopy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jev import NO_MEMORY, compose_payload
from kitchen import load_config
from levels import level_config
from scripts import hands_full_check, jev_replay_check
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient


def payloads():
    """Jeff's request at the start of level 2 (hands empty) and after he fetched bread (hands full)."""
    k = SpatialKitchen(level_config(load_config(), 'level-2'))
    client = SpatialJevClient(k.c, key='unit-test-not-a-real-key')
    empty = compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, NO_MEMORY)
    k.start('jeff', next(a for a in k.actions('jeff') if a.key == 'fetch bread'))
    while k.chefs['jeff'].job:
        k.advance(.05)
    recent = [{'t': 1.0, 'choice': 'go lettuce', 'accepted': True, 'result': '开始', 'sprint_applied': False}]
    full = compose_payload(client, k, k.snapshot(), k.actions('jeff'), recent, None, NO_MEMORY)
    return empty, full


def journal(day, pairs, model='jev-1.13.0'):
    """One round: a start row on that day, then each (payload, logged choice) as a request and its answer."""
    rows = [{'kind': 'start', 'wall_time': f'{day}T12:00:00+08:00'}]
    for n, (payload, choice) in enumerate(pairs, 1):
        rows += [{'kind': 'ai_request', 'request_id': n, 'payload': payload},
                 {'kind': 'ai_response', 'request_id': n, 'choice': choice, 'model': model}]
    return '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n'


class JevChecksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty, cls.full = payloads()

    def folder(self, journals):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for name, text in journals.items():
            Path(folder.name, name).write_text(text, encoding='utf-8')
        return folder.name

    def test_the_replay_compares_now_with_then_and_with_itself(self):
        logs = self.folder({'old.jsonl': journal('2026-10-01', [(self.empty, 'fetch lettuce'), (self.full, 'drop')]),
                            'new.jsonl': journal('2026-11-04', [(self.full, 'go lettuce')], model='jev-1.14.0'),
                            'chat.jsonl': journal('2026-10-01', [(self.empty, 'wait')], model='deepseek-flash')})
        items = jev_replay_check.journal_requests([logs], '2026-09-28', '2026-10-02')
        self.assertEqual([(i['logged_choice'], i['logged_model']) for i in items], [('fetch lettuce', 'jev-1.13.0'), ('drop', 'jev-1.13.0')])
        calls = []

        def ask(payload):      # the same answer as then with hands empty; with full hands a walk, then a throw
            calls.append(payload)
            if not jev_replay_check.hands_full(payload):
                return {'choice': 'fetch lettuce', 'model': 'jev-1.14.0'}
            return {'choice': 'go lettuce' if len(calls) % 2 else 'throw partner', 'model': 'jev-1.14.0'}
        report = jev_replay_check.summary(jev_replay_check.replay(items, ask))
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0], items[0]['payload'])                      # sent exactly as logged
        self.assertEqual((report['requests'], report['rounds'], report['answered_twice']), (2, 1, 2))
        self.assertEqual(report['models_now'], {'jev-1.14.0': 4})
        self.assertEqual(report['hands_empty']['same_as_logged'], 1.0)
        self.assertEqual(report['hands_full']['same_as_logged'], 0.0)
        self.assertEqual(report['hands_full']['same_on_resend'], 0.0)
        self.assertEqual(report['hands_full']['logged_kinds'], {'use_or_put_down': 1})
        self.assertEqual(report['hands_full']['kinds_now'], {'supply_walk': 1})
        failing = jev_replay_check.summary(jev_replay_check.replay(items[:1], lambda p: (_ for _ in ()).throw(RuntimeError('TypeSafe HTTP 429'))))
        self.assertEqual((failing['answered'], failing['errors']), (0, {'TypeSafe HTTP 429': 2}))
        self.assertIsNone(failing['all']['same_as_logged'])

    def test_stuck_moments_are_asked_three_ways(self):
        logs = self.folder({'today.jsonl': journal('2026-11-04', [(self.full, 'go lettuce'), (self.full, 'drop'),
                                                                   (self.empty, 'wait')], model='jev-1.14.0')})
        items = [i for i in jev_replay_check.journal_requests([logs], '2026-11-04') if hands_full_check.stuck(i)]
        self.assertEqual([i['logged_choice'] for i in items], ['go lettuce'])     # full hands and a walk; not drop, not empty hands
        no_recent = hands_full_check.arm(self.full, 'no_recent')
        self.assertEqual((no_recent['state']['recent_decisions'], no_recent['state']['recent_events']), ([], []))
        self.assertEqual(no_recent['state']['kitchen'], self.full['state']['kitchen'])
        no_walks = hands_full_check.arm(self.full, 'no_supply_walks')
        removed = set(self.full['questions']['next_action']['criteria']) - set(no_walks['questions']['next_action']['criteria'])
        self.assertEqual(removed, {'go fridge', 'go lettuce', 'go tomato'})       # he stands at the bread supply
        self.assertEqual(hands_full_check.arm(self.full, 'as_logged'), self.full)

        def ask(payload):
            criteria = payload['questions']['next_action']['criteria']
            return {'choice': 'go lettuce' if 'go lettuce' in criteria else 'put b1', 'model': 'jev-1.14.0'}
        report = hands_full_check.run(items, ask)
        self.assertEqual((report['moments'], report['logged_kinds'], report['with_supply_walks_offered']), (1, {'supply_walk': 1}, 1))
        self.assertEqual(report['arms']['as_logged']['chose_supply_walk'], 1.0)
        self.assertEqual(report['arms']['no_recent']['same_as_logged'], 1.0)
        self.assertEqual(report['arms']['no_supply_walks']['chose_use_or_put_down'], 1.0)

    def test_a_dry_run_sends_nothing(self):
        logs = self.folder({'today.jsonl': journal('2026-11-04', [(self.full, 'go lettuce')], model='jev-1.14.0')})
        out, err = io.StringIO(), io.StringIO()
        with patch.object(jev_replay_check, 'client', side_effect=AssertionError('no client in a dry run')), \
                redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(jev_replay_check.main([logs, '--dry-run']), 0)
            self.assertEqual(hands_full_check.main([logs, '--dry-run']), 0)
            self.assertEqual(hands_full_check.main([logs, '--since', '2026-12-01', '--dry-run']), 1)
        self.assertIn('2 requests', err.getvalue())         # one request, sent twice
        self.assertIn('3 requests', err.getvalue())         # one moment, three arms
        self.assertNotIn('Bread', out.getvalue() + err.getvalue())


if __name__ == '__main__':
    unittest.main()
