"""Provenance tracking and the deterministic collaboration analysis."""
import sys
import unittest
from pathlib import Path

import config_contract as cc
from collaboration_analyzer import analyze_collaboration, _lineage
from kitchen import Food, GroundItem, replay
from spatial_kitchen import SpatialKitchen, tile_key

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reference_sweep as rs  # noqa: E402


def reference_round(level, pair):
    policy = cc.load_level(f'level-{level}')['order_policy']
    return rs.play(level, policy['interval_game_ms'], policy['patience_by_recipe'], None, 'fast', pair, False)


class ProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.l1 = reference_round(1, 'classic')
        cls.l2 = reference_round(2, 'zoned')

    def test_every_action_is_contributing_harmful_or_wasted(self):
        for k in (self.l1, self.l2):
            r = analyze_collaboration(k)
            self.assertEqual(r['contributing'] + r['harmful']['count'] + r['wasted']['count'], r['actions'])
            self.assertEqual(r['actions'], sum(c['actions'] for c in r['chefs'].values()))
            self.assertEqual(len(r['dishes']), k.served)

    def test_each_served_burger_traces_back_to_four_fetched_ingredients(self):
        p = self.l2.provenance
        for serve in p.serves:
            chain = []
            _lineage(p, serve['item'], len(p.history[serve['item']]), chain)
            fetched = {item for item, t in chain if t.kind == 'fetch'}
            # Independent path: the ingredient kinds of those items, from their first touch.
            self.assertEqual(len(fetched), 4, serve)
            plates = {item for item, _ in chain if item.startswith('D')}
            self.assertEqual(plates, {serve['plate']})

    def test_zoned_pair_dishes_cross_both_chefs(self):
        r = analyze_collaboration(self.l2)
        self.assertEqual(r['dishes_with_both_chefs'], len(r['dishes']))
        self.assertGreater(r['cross_chef_handoffs'], 0)

    def test_pot_returned_to_the_stove_counts_for_the_next_beef(self):
        p, r = self.l1.provenance, analyze_collaboration(self.l1)
        last_serve = max(s['t'] for s in p.serves)
        returns = [aid for aid, a in p.actions.items() if a['kind'] == 'return_pot' and a['t'] < last_serve - 20]
        self.assertTrue(returns)
        contributing = set()
        for serve in p.serves:
            chain = []
            _lineage(p, serve['item'], len(p.history[serve['item']]), chain)
            contributing |= {aid for _, t in chain for aid in t.action_ids}
        self.assertTrue(set(returns) <= contributing)
        self.assertEqual(r['wasted']['by_label']['loop'], 0)

    def test_effort_time_matches_the_event_stream(self):
        # Independent path: action_start / action_done times straight from the engine events.
        for k in (self.l1, self.l2):
            r = analyze_collaboration(k)
            starts = {e['action_id']: e['t'] for e in k.events if e.get('kind') == 'action_start'}
            ends = {e['action_id']: (e['t'], e['actor']) for e in k.events if e.get('kind') == 'action_done' and e.get('action_id')}
            contributing = set()
            for serve in k.provenance.serves:
                if serve['outcome'] == 'served':
                    chain = []
                    _lineage(k.provenance, serve['item'], len(k.provenance.history[serve['item']]), chain)
                    contributing |= {a for _, t in chain for a in t.action_ids} | {serve['action_id']}
            kinds = {aid: a['kind'] for aid, a in k.provenance.actions.items()}
            expected = {'human': 0., 'jeff': 0.}
            for aid in contributing:
                if kinds[aid] not in ('go', 'wait', 'stop', 'continue') and aid not in k.provenance.penalties:
                    expected[ends[aid][1]] += ends[aid][0] - starts[aid]
            for who in expected:
                self.assertAlmostEqual(r['effort_seconds'][who], expected[who], places=2)
            self.assertAlmostEqual(sum(v for v in r['effort_share'].values()), 1, places=2)

    def test_critical_path_time_adds_up_to_the_dish_time(self):
        for k in (self.l1, self.l2):
            r = analyze_collaboration(k)
            starts = {e['action_id']: e['t'] for e in k.events if e.get('kind') == 'action_start'}
            for dish in r['dishes']:
                path = dish['critical_path']
                total = sum(path['seconds'].values()) + path['waiting_seconds']
                self.assertGreater(path['steps'], 2)
                # The path starts with some action's start and ends at the serve; nothing is double counted.
                self.assertLessEqual(total, dish['t'] + 1e-6)
                self.assertTrue(any(abs(dish['t'] - total - s) < 1e-6 for s in starts.values()), dish)
            self.assertAlmostEqual(sum(r['critical_path']['seconds'].values()) + r['critical_path']['waiting_seconds'],
                                   sum(sum(d['critical_path']['seconds'].values()) + d['critical_path']['waiting_seconds'] for d in r['dishes']),
                                   places=3)

    def test_replay_rebuilds_the_same_analysis(self):
        k = self.l2
        again = replay(SpatialKitchen, k.resolved, k.inputs)
        self.assertEqual(analyze_collaboration(again), analyze_collaboration(k))


class LoopAndHarmTests(unittest.TestCase):
    def kitchen(self):
        k = SpatialKitchen(cc.load_level('level-2'))
        k.ground.clear()
        return k

    def test_swapping_two_items_back_and_forth_is_a_loop(self):
        k = self.kitchen()
        cell = sorted(k.floor)[len(k.floor) // 2]
        k.positions['jeff'] = cell
        k.chefs['jeff'].location = tile_key(cell)
        k.ground['F90'] = GroundItem(Food('F90', ingredient='bread'), tile_key(cell))
        k.chefs['jeff'].hand = Food('F91', 'chopped', ingredient='lettuce')
        done = []
        for n in range(4):
            target = 'F90' if n % 2 == 0 else 'F91'
            a = next(a for a in k.actions('jeff') if a.key == f'pickup {target}')
            k.positions['jeff'] = k.path('jeff', a.target)[-1]
            self.assertTrue(k.start('jeff', a)[0])
            k.advance(.4)
            done.append(max(k.provenance.actions))
        r = analyze_collaboration(k)
        self.assertEqual(r['wasted']['by_label']['loop'], 2)
        self.assertEqual(r['contributing'], 0)

    def test_serving_a_dish_nobody_waits_for_is_harmful_not_contributing(self):
        k = self.kitchen()
        station = next(s for s in k.stations.values() if s.food and s.food.stage == 'clean_plate')
        plate, station.food = station.food, None
        k.chefs['jeff'].hand = k.merge_plate(plate, Food('F99', 'ready', 6, 12))
        a = next(a for a in k.actions('jeff') if a.kind == 'serve')
        k.positions['jeff'] = k.path('jeff', a.target)[-1]
        self.assertTrue(k.start('jeff', a)[0])
        k.advance(.4)
        r = analyze_collaboration(k)
        self.assertEqual(r['harmful']['by_reason'], {'wrong_dish': 1})
        self.assertEqual(r['contributing'], 0)
        self.assertEqual(r['dishes'], [])


class SingleChefTests(unittest.TestCase):
    def test_one_chef_cannot_reach_the_target(self):
        # Owner decisions: a level must need both chefs (2026-09-28); level 1 is the
        # practice tutorial and is exempt (2026-09-29): one chef can serve every order there.
        for level in (2, 3):
            with self.subTest(level=level):
                row = rs.rung(level, 'solo')
                target = cc.load_level(f'level-{level}')['level']['goal']['min_money']
                self.assertLess(row['money'], target)


if __name__ == '__main__':
    unittest.main()
