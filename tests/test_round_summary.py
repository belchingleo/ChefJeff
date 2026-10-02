"""The end-of-round record is generated from the round and the level data."""
import json
import re
import sys
import time
import unittest
from collections import Counter
from pathlib import Path

import config_contract as cc
from kitchen import ROOT
from levels import level_config
from kitchen import load_config
from round_summary import round_summary
from spatial_kitchen import SpatialKitchen
from web_server import GameSession
from test_web import Client, FakeJournal

sys.path.insert(0, str(ROOT / 'scripts'))
import reference_sweep as rs  # noqa: E402


def reference_round(level, pair):
    policy = cc.load_level(f'level-{level}')['order_policy']
    return rs.play(level, policy['interval_game_ms'], policy['patience_by_recipe'], None, 'fast', pair, False)


def row(summary, category):
    return next((r for r in summary['rows'] if r['category'] == category), None)


class RoundSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rounds = {1: reference_round(1, 'classic'), 2: reference_round(2, 'zoned'), 3: reference_round(3, 'classic')}

    def test_counts_match_the_engine_event_stream(self):
        # Independent path: count completions straight from the engine events.
        for level, k in self.rounds.items():
            with self.subTest(level=level):
                s = round_summary(k)
                done = Counter((e['actor'], e['action'].split(' ')[0]) for e in k.events
                               if e.get('kind') == 'action_done' and e.get('action'))
                for category, kind in (('fetch', 'fetch'), ('chop', 'chop'), ('wash', 'wash'), ('pass', 'throw')):
                    r = row(s, category)
                    for who in ('human', 'jeff'):
                        self.assertEqual(r['counts'][who] if r else 0, done[(who, kind)], (category, who))
                served = row(s, 'serve')
                accepted = sum(d['counts'][w] for d in served['details'] if d['outcome'] == 'served' for w in d['counts'])
                self.assertEqual(accepted, k.served)
                washed = Counter(e['actor'] for e in k.events if e.get('kind') == 'washed')
                self.assertEqual(row(s, 'wash')['counts'], {w: washed[w] for w in ('human', 'jeff')})

    def test_details_add_up_and_come_from_the_level_data(self):
        k = self.rounds[2]
        s = round_summary(k)
        names = k.rules.item_names
        for category in ('fetch', 'chop', 'heat'):
            r = row(s, category)
            for who in ('human', 'jeff'):
                self.assertEqual(sum(d['counts'][who] for d in r['details']), r['counts'][who], category)
            for d in r['details']:
                self.assertEqual(d['name'], names[d['id']])
        self.assertEqual({d['dish'] for d in row(s, 'serve')['details']}, {'burger'})
        self.assertEqual({d['id'] for d in row(s, 'fetch')['details']}, {'beef', 'bread', 'lettuce', 'tomato'})
        heat = row(s, 'heat')['details'][0]
        self.assertEqual(sum(heat.get('cooked', {}).values()) + sum(heat.get('burnt', {}).values()),
                         sum(heat['counts'].values()) - self.unfinished_beef(k))

    @staticmethod
    def unfinished_beef(k):
        cooked = {e.get('item') for e in k.events if e.get('kind') in ('ready', 'burn')}
        return sum(1 for m in k.provenance.containers if m.dish not in cooked)

    def test_renamed_ingredient_needs_no_code_change(self):
        bundle = cc.level_bundle('level-2', embed=True)
        bundle['recipe_catalog']['items']['lettuce']['name'] = 'Kale'
        k = SpatialKitchen(cc.freeze_bundle(bundle))
        fetch = next(a for a in k.actions('human') if a.key == 'fetch lettuce')
        k.positions['human'] = k.path('human', fetch.target)[-1]
        self.assertTrue(k.start('human', fetch)[0])
        k.advance(.5)
        details = row(round_summary(k), 'fetch')['details']
        self.assertEqual([(d['id'], d['name']) for d in details], [('lettuce', 'Kale')])

    def test_the_module_names_no_level_dish_or_ingredient(self):
        source = (ROOT / 'round_summary.py').read_text()
        code = re.sub(r'""".*?"""|#.*', '', source, flags=re.S)
        for word in ('steak', 'burger', 'beef', 'lettuce', 'tomato', 'bread', 'level-', '牛', '汉堡'):
            self.assertNotIn(word, code)

    def test_empty_categories_are_omitted_and_hidden_fields_exist(self):
        s = round_summary(self.rounds[1])
        self.assertIsNone(row(s, 'pass'))
        self.assertTrue(all(any(r['counts'].values()) or r['details'] for r in s['rows']))
        self.assertEqual(set(s['not_displayed']), {'wasted', 'harmful', 'action_share', 'critical_path', 'effort'})
        self.assertEqual(set(s['contribution']), {'standard', 'delay_seconds', 'idle_seconds'})
        for block in (s['contribution']['standard'], s['not_displayed']['effort'], s['not_displayed']['critical_path']):
            self.assertAlmostEqual(sum(block['share'].values()), 1, places=2)
        self.assertIn('action_share', s['not_displayed'])
        json.dumps(s)


class SessionStateTests(unittest.TestCase):
    def test_record_appears_only_after_the_round_and_reaches_the_end_journal(self):
        g = GameSession(config=level_config(load_config(), 1), client_factory=Client, journal_factory=FakeJournal)
        self.addCleanup(g.close)

        def command(path):
            return g.command('/api/' + path, {'game_id': g.game_id, 'request_id': str(time.monotonic_ns())})
        self.assertIsNone(g.public_state()['round_summary'])
        self.assertEqual(command('start')[0], 200)
        self.assertIsNone(g.public_state()['round_summary'])
        log = g.journal
        self.assertEqual(command('end')[0], 200)
        state = g.public_state()
        self.assertEqual(state['round_summary']['level_id'], 'level-1')
        ends = [v for key, v in log.rows if key == 'end']
        self.assertEqual(ends[0]['round_summary'], state['round_summary'])


if __name__ == '__main__':
    unittest.main()
