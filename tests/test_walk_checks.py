"""scripts/walk_label_check.py on a small journal, with a stand-in for Jev, and the walk groups of hands_full_check."""
from copy import deepcopy
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import hands_full_check, jev_replay_check, walk_label_check
from test_jev_checks import journal, payloads

SUFFIX = '; no other listed action is at {} now'


class WalkLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty, cls.full = payloads()

    def folder(self, journals):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for name, text in journals.items():
            Path(folder.name, name).write_text(text, encoding='utf-8')
        return folder.name

    def test_only_the_walk_labels_change(self):
        before = self.full['questions']['next_action']['criteria']
        after = walk_label_check.label(self.full)['questions']['next_action']['criteria']
        self.assertEqual(list(after), list(before))
        for key, text in after.items():
            with self.subTest(key):
                if walk_label_check.walk(key):
                    self.assertEqual(text, before[key] + SUFFIX.format(key[3:]))
                else:
                    self.assertEqual(text, before[key])
        self.assertIn('go partner', before)
        self.assertEqual(walk_label_check.label(self.full)['state'], self.full['state'])
        self.assertEqual(self.full['questions']['next_action']['criteria'], before)     # the logged request is untouched

    def test_a_station_another_key_names_keeps_its_label(self):
        payload = deepcopy(self.full)
        criteria = payload['questions']['next_action']['criteria']
        criteria['put serve'] = 'Put it at Serve'
        self.assertEqual(walk_label_check.label(payload)['questions']['next_action']['criteria']['go serve'], criteria['go serve'])

    def test_the_arms_compare_walks_and_steps(self):
        logs = self.folder({'today.jsonl': journal('2026-11-04', [(self.full, 'go serve'), (self.full, 'drop'),
                                                                   (self.empty, 'go p1'), (self.empty, 'go partner')],
                                                   model='jev-1.14.0')})
        items = [i for i in jev_replay_check.journal_requests([logs], '2026-11-04') if walk_label_check.picked(i)]
        self.assertEqual([i['logged_choice'] for i in items], ['go serve', 'go p1'])     # not drop, not go partner

        def ask(payload):
            criteria = payload['questions']['next_action']['criteria']
            labeled = any(text.endswith(' now') for text in criteria.values())
            if not labeled:
                return {'choice': 'go serve' if jev_replay_check.hands_full(payload) else 'go p1', 'model': 'jev-1.14.0'}
            return {'choice': 'assemble plates' if 'assemble plates' in criteria else 'fetch bread', 'model': 'jev-1.14.0'}
        report = walk_label_check.run(items, ask)
        self.assertEqual((report['moments'], report['hands_full']), (2, 1))
        logged, labeled = report['arms']['as_logged'], report['arms']['walks_labeled']
        self.assertEqual((logged['all']['same_as_logged'], logged['all']['chose_walk']), (1.0, 1.0))
        self.assertEqual((labeled['hands_full']['chose_a_step_of_the_dish'], labeled['hands_empty']['chose_take']), (1.0, 1.0))
        self.assertEqual(labeled['all']['chose_walk'], 0.0)

    def test_a_dry_run_sends_nothing(self):
        logs = self.folder({'today.jsonl': journal('2026-11-04', [(self.full, 'go serve')], model='jev-1.14.0')})
        out, err = io.StringIO(), io.StringIO()
        with patch.object(walk_label_check, 'client', side_effect=AssertionError('no client in a dry run')), \
                redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(walk_label_check.main([logs, '--dry-run']), 0)
            self.assertEqual(walk_label_check.main([logs, '--since', '2026-12-01', '--dry-run']), 1)
        self.assertIn('2 requests', err.getvalue())         # one moment, two arms

    def test_explained_walks_state_what_lies_there(self):
        payload = deepcopy(self.full)
        payload['state']['kitchen']['stations']['b1']['food'] = {'id': 'F7', 'stage': 'raw', 'ingredient': 'lettuce', 'meaning': 'Lettuce'}
        criteria = payload['questions']['next_action']['criteria']
        criteria['go b1'] = 'Walk to Board 1 (Prep area)'
        for key in [k for k in criteria if k.endswith(' b1') and k != 'go b1']:
            del criteria[key]
        after = walk_label_check.arm(payload, 'walks_explained')['questions']['next_action']['criteria']
        self.assertEqual(after['go b1'], 'Walk to Board 1 (Prep area); Board 1 holds Lettuce (raw); '
                                         'with what you hold, no other listed action is at b1 now')
        self.assertEqual(after['go serve'], criteria['go serve'] + '; with what you hold, no other listed action is at serve now')
        self.assertEqual([k for k in after if after[k] != criteria[k]], [k for k in criteria if walk_label_check.walk(k)])
        self.assertEqual(walk_label_check.lying_there({'food': {'stage': 'clean_plate', 'meaning': 'Clean plate'}}), 'Clean plate')

    def test_put_then_take_sits_next_to_walks_to_an_item(self):
        payload = deepcopy(self.full)
        payload['state']['kitchen']['stations']['b1']['food'] = {'id': 'F7', 'stage': 'raw', 'ingredient': 'lettuce', 'meaning': 'Lettuce'}
        criteria = payload['questions']['next_action']['criteria']
        for key in [k for k in criteria if k.endswith(' b1')]:
            del criteria[key]
        criteria['go b1'] = 'Walk to Board 1 (Prep area)'
        after = walk_label_check.arm(payload, 'put_then_take')['questions']['next_action']['criteria']
        added = {k: v for k, v in after.items() if k not in criteria}
        self.assertEqual(added, {'put then take b1': 'Put the held Bread (raw) on Counter 14, then take Lettuce (raw) from Board 1'})
        keys = list(after)
        self.assertEqual(keys.index('put then take b1'), keys.index('go b1') + 1)       # right after its walk
        self.assertEqual({k: after[k] for k in criteria}, criteria)                     # the rest unchanged
        self.assertEqual(walk_label_check.arm(self.empty, 'put_then_take'), self.empty)  # empty hands: nothing added
        answers = [({'logged_choice': 'go b1', 'payload': payload}, walk_label_check.arm(payload, 'put_then_take'),
                    {'choice': 'put then take b1'})]
        report = walk_label_check.arm_report(answers)
        self.assertEqual((report['chose_put_then_take'], report['offered_put_then_take'], report['chose_walk']), (1.0, 1, 0.0))

    def kitchen_with(self, held=True):
        payload = deepcopy(self.full if held else self.empty)
        stations = payload['state']['kitchen']['stations']
        stations['b1']['food'] = {'id': 'F7', 'stage': 'raw', 'ingredient': 'lettuce', 'meaning': 'Lettuce'}
        stations['returns']['food'] = {'id': 'D9', 'stage': 'dirty_plate', 'meaning': 'Dirty plate'}
        criteria = payload['questions']['next_action']['criteria']
        for key in [k for k in criteria if k.endswith(' b1')]:
            del criteria[key]
        criteria['go b1'] = 'Walk to Board 1 (Prep area)'
        return payload

    def test_one_press_offers_both_and_lets_him_choose_where(self):
        payload = self.kitchen_with()
        after = walk_label_check.arm(payload, 'one_press')
        criteria = after['questions']['next_action']['criteria']
        self.assertEqual(criteria['put then take b1'], 'Put the held Bread (raw) where you choose in put_where, then take Lettuce (raw) from Board 1')
        self.assertEqual(criteria['wash from returns'], 'Put the held Bread (raw) where you choose in put_where, then take the dirty '
                                                        'plate from Plate return, put it in Sink and wash it')
        places = after['questions']['put_where']['criteria']
        self.assertEqual(places, walk_label_check.put_places(payload))
        self.assertIn('drop', places)
        self.assertTrue(all(k == 'drop' or k.startswith('put ') for k in places))
        empty = walk_label_check.arm(self.kitchen_with(held=False), 'one_press')
        self.assertEqual(empty['questions']['next_action']['criteria']['wash from returns'],
                         'Take the dirty plate from Plate return, put it in Sink and wash it')
        self.assertNotIn('put_where', empty['questions'])                       # nothing to put down
        self.assertNotIn('put then take b1', empty['questions']['next_action']['criteria'])

    def test_the_put_where_answer_is_read_back_and_reported(self):
        import harness
        payload = walk_label_check.arm(self.kitchen_with(), 'one_press')
        place = next(k for k in payload['questions']['put_where']['criteria'] if k.startswith('put counter'))

        def client(sent):     # what jev.JevClient.ask does with the answers it gets
            answers = {'put_where': {'type': 'choice', 'choice': place}}     # the decision API's answer shape
            return {'choice': 'put then take b1', 'model': 'jev-1.14.0',
                    **harness.plan_answer(harness.choices(answers, harness.plan_questions(sent)), sent)}
        answer = walk_label_check.ask_keeping_put_where(client, payload)
        self.assertEqual(answer, {'choice': 'put then take b1', 'model': 'jev-1.14.0', 'put_where': place})
        self.assertEqual(harness.plan_questions(payload), [])                    # the patch is gone afterwards
        report = walk_label_check.arm_report([({'logged_choice': 'go b1', 'payload': payload}, payload, answer),
                                              ({'logged_choice': 'go b1', 'payload': payload}, payload,
                                               {'choice': 'wash from returns', 'put_where': 'nowhere'})])
        self.assertEqual((report['chose_put_then_take'], report['chose_wash_from_returns']), (.5, .5))
        self.assertEqual((report['offered_put_then_take'], report['offered_wash_from_returns']), (2, 2))
        self.assertEqual(report['put_where'], {'counter': 1, 'not_offered': 1})

    def test_hands_full_groups_name_where_walks_went(self):
        moments = [{'payload': self.full, 'logged_choice': key, 'round': 1} for key in ('go serve', 'go p1', 'go partner', 'wait')]
        walks = hands_full_check.groups(moments)['walks']
        self.assertEqual(walks, {'count': 3, 'to': {'serving_window': 1, 'stove': 1, 'partner': 1}, 'by_held': {'ingredient': 3},
                                 'on_station': {'empty': 1, 'empty_pan': 1, 'partner': 1},
                                 'held_and_on_station': {'ingredient -> empty': 1, 'ingredient -> empty_pan': 1,
                                                         'ingredient -> partner': 1}})
        board = deepcopy(self.full)
        board['state']['kitchen']['stations']['b1']['food'] = {'id': 'F7', 'stage': 'chopped', 'ingredient': 'lettuce'}
        moment = [{'payload': board, 'logged_choice': 'go b1', 'round': 1}]
        self.assertEqual(hands_full_check.groups(moment)['walks']['held_and_on_station'], {'ingredient -> ingredient': 1})


if __name__ == '__main__':
    unittest.main()
