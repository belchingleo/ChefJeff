"""Service rules of the listed levels: money goal, continuous orders, burnt tiers.

Confirmed rules (2026-09-27): 180 game seconds; level menus steak / burger /
steak + burger; prices 50 / 80; the goal is net revenue at closing; no bad
reviews; wrong dish -20; expired order -10; a dish burnt up to 5 s is accepted
at price -10, longer is refused (no money, the order keeps waiting); serving at
the deadline counts; orders keep arriving until closing and orders still open
at closing carry no penalty; countdowns are per dish; at most 5 tickets.
"""
import unittest

import config_contract as cc
from kitchen import Food, Kitchen
from levels import available_levels
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient


def level(n, **edits):
    bundle = cc.level_bundle(f'level-{n}', embed=True)
    bundle['level']['seeds'] = {'orders': 3, 'spawn': 0}
    for kind, edit in edits.items():
        edit(bundle[kind])
    return cc.freeze_bundle(bundle)


class ServeTests(unittest.TestCase):
    def kitchen(self, n=3, **edits):
        k = Kitchen(level(n, **edits))
        k.advance(.01)
        return k

    def plate(self, k, dish, stage='ready', heated=12):
        parts = tuple(sorted(k.rules.recipe_parts[dish]))
        k.stations['plates'].food = None
        k.chefs['human'].hand = Food('X1', stage, heated=heated, plate_id='D1', ingredient='dish', components=parts)

    def serve(self, k, deadline_at_finish=False, order=None):
        ok, message = k.command('human', 'serve')
        self.assertTrue(ok, message)
        job = k.chefs['human'].job
        if deadline_at_finish:
            order['deadline'] = k.time + job.travel + job.work
        k.advance(job.travel + job.work + .001)

    def first(self, k):
        return next(o for o in k.orders if o['status'] == 'pending')

    def test_levels_and_prices(self):
        self.assertEqual([e['id'] for e in available_levels()], ['level-1', 'level-2', 'level-3'])
        menus = {1: ['steak'], 2: ['burger'], 3: ['steak', 'burger']}
        for n in (1, 2, 3):
            resolved = level(n)
            self.assertEqual(resolved['level']['round_limit_game_ms'], 180000)
            self.assertEqual([e['recipe_ref'] for e in resolved['order_policy']['menu']], menus[n])
            self.assertEqual({r: v['price'] for r, v in resolved['recipe_catalog']['recipes'].items()}, {'steak': 50, 'burger': 80})
            self.assertEqual(resolved['level']['goal']['type'], 'minimum_money')
            self.assertEqual(set(resolved['order_policy']['patience_by_recipe']), set(menus[n]))

    def test_good_dish_earns_the_price(self):
        k = self.kitchen(3);o = self.first(k);self.plate(k, o['dish'])
        self.serve(k)
        self.assertEqual(o['status'], 'served');self.assertEqual(k.money, k.rules.prices[o['dish']])
        self.assertEqual(k.bad_reviews, 0)

    def test_serving_at_the_deadline_counts_in_full(self):
        k = self.kitchen(2);o = self.first(k);self.plate(k, 'burger')
        self.serve(k, deadline_at_finish=True, order=o)
        self.assertEqual(o['status'], 'served');self.assertEqual(k.money, 80)

    def test_dish_goes_to_the_next_waiting_order_when_the_first_expired(self):
        k = self.kitchen(2)
        k.advance(k.rules.resolved['order_policy']['interval_game_ms'] / 1000)  # second order arrives
        first, second = [o for o in k.orders if o['status'] == 'pending'][:2]
        first['deadline'] = k.time + .02;k.advance(.05)
        self.assertEqual(first['status'], 'expired');self.assertEqual(k.money, -10)
        self.plate(k, 'burger');self.serve(k)
        self.assertEqual(second['status'], 'served');self.assertEqual(k.money, -10 + 80)

    def test_burnt_up_to_five_seconds_is_accepted_at_price_minus_ten(self):
        for dish in ('steak', 'burger'):
            with self.subTest(dish=dish):
                k = self.kitchen(3)
                o = next(o for o in k.orders if o['dish'] == dish and o['status'] in ('pending', 'future'))
                if o['status'] == 'future':
                    k.advance(o['arrival'] - k.time + .01)
                burn = k.rules.heat_thresholds('beef')[1]
                self.plate(k, dish, 'burnt', heated=burn + 4.9)
                self.serve(k)
                self.assertEqual(o['status'], 'served')
                self.assertEqual(k.money, k.rules.prices[dish] - 10)

    def test_burnt_longer_is_refused_and_the_order_keeps_waiting(self):
        k = self.kitchen(1);o = self.first(k)
        burn = k.rules.heat_thresholds('beef')[1]
        self.plate(k, 'steak', 'burnt', heated=burn + 5.5)
        self.serve(k)
        self.assertEqual(o['status'], 'pending');self.assertEqual(k.money, 0);self.assertIsNone(k.chefs['human'].hand)
        self.assertEqual([e['kind'] for e in k.events].count('dish_rejected'), 1)
        self.assertTrue(k.dining)  # the plate still comes back to be washed
        self.plate(k, 'steak');self.serve(k)
        self.assertEqual(o['status'], 'served');self.assertEqual(k.money, 50)

    def test_food_burnt_by_fire_is_refused(self):
        k = self.kitchen(1);o = self.first(k)
        self.plate(k, 'steak', 'burnt', heated=15)  # burnt by a spreading fire before its own burn point
        self.serve(k)
        self.assertEqual(o['status'], 'pending');self.assertEqual(k.money, 0)

    def test_wrong_dish_costs_twenty_and_hidden_future_orders_do_not_match(self):
        k = self.kitchen(1)
        self.plate(k, 'burger');self.serve(k)
        self.assertEqual(k.money, -20)
        k = self.kitchen(2)
        self.first(k)['status'] = 'served'  # nothing waiting; later burger orders have not arrived
        self.plate(k, 'burger');self.serve(k)
        self.assertEqual(k.money, -20)

    def test_expiry_costs_ten_without_bad_reviews(self):
        k = self.kitchen(1);o = self.first(k)
        k.advance(o['deadline'] - k.time + .1)
        self.assertEqual(o['status'], 'expired');self.assertEqual(k.money, -10);self.assertEqual(k.bad_reviews, 0)


class FixedSeedTests(unittest.TestCase):
    def test_listed_levels_use_fixed_seeds_so_every_round_is_identical(self):
        for n in (1, 2, 3):
            a, b = cc.load_level(f'level-{n}'), cc.load_level(f'level-{n}')
            self.assertEqual(a['seeds']['source'], 'configured')
            self.assertEqual(a['config_hash'], b['config_hash'])
        orders = [o['recipe_ref'] for o in cc.load_level('level-3')['order_plan']['orders']]
        self.assertEqual(orders, ['steak', 'burger', 'burger', 'steak', 'burger', 'steak'])

    def test_targets_are_whole_tens(self):
        for n in (1, 2, 3):
            self.assertEqual(cc.load_level(f'level-{n}')['level']['goal']['min_money'] % 10, 0)

    def test_targets_are_half_the_calibrated_reference_income(self):
        # Targets are 50% of the fast reference pair's net income on the fixed plan
        # (scripts/reference_sweep.py --fixed). Level 2 needs the zoned pair that passes
        # food and dishes across the long counter.
        import importlib.util
        from pathlib import Path
        path = Path(cc.__file__).resolve().parent / 'scripts' / 'reference_sweep.py'
        spec = importlib.util.spec_from_file_location('reference_sweep', path)
        sweep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sweep)
        for n, pair in ((1, 'classic'), (2, 'zoned'), (3, 'classic')):
            with self.subTest(level=n):
                policy = cc.load_level(f'level-{n}')['order_policy']
                k = sweep.play(n, policy['interval_game_ms'], policy['patience_by_recipe'], None, 'fast', pair, False)
                target = cc.load_level(f'level-{n}')['level']['goal']['min_money']
                self.assertEqual(target, int(k.money * .5) // 10 * 10)
                if pair == 'zoned':
                    self.assertTrue(any(e['kind'] == 'thrown' for e in k.events))


class ServiceWordingTests(unittest.TestCase):
    def test_burn_event_and_serve_hint_do_not_mention_bad_reviews(self):
        # Local acceptance found the 0.5.9 wording ("burnt food earns a bad review") in service levels.
        import json as _json
        from pathlib import Path
        english = _json.loads((Path(cc.__file__).resolve().parent / 'model-language-en-v3.json').read_text())
        k = SpatialKitchen(cc.load_level('level-1'))
        pot = k.stations['p1']
        pot.food = Food('fixture', stage='cooking', chopped=k.c['chop_seconds'], heated=0, ingredient='beef')
        pot.heating = True
        k.advance(40)
        burns = [e['message'] for e in k.events if e['kind'] == 'burn']
        self.assertTrue(burns)
        plate = k.stations['plates'].food
        k.stations['plates'].food = None
        plate.stage, plate.plate_id, plate.components = 'ready', 'D9', ['beef']
        k.chefs['human'].hand = plate
        serve = [a.label for a in k.actions('human') if a.kind == 'serve']
        self.assertTrue(serve)
        for text in burns + serve:
            self.assertNotIn('差评', text)
        catalog = _json.dumps(english, ensure_ascii=False)
        self.assertIn('a dish burnt too long is refused', catalog)


    def test_hint_names_an_ingredient_the_plate_already_has(self):
        # Local play: adding lettuce to a finished burger only said "cannot be used now".
        k = SpatialKitchen(cc.load_level('level-2'))
        k.positions['human'], k.facing['human'] = (7., 5.), 'up'
        k.chefs['human'].hand = Food('x', 'chopped', 6, ingredient='lettuce')
        plate = Food('F6', 'burnt', plate_id='D1', ingredient='dish')
        plate.components = ('beef', 'bread', 'lettuce', 'tomato')
        k.stations['counter18'].food = plate
        self.assertIsNone(k.quick_interaction('human', preferred='counter18'))
        self.assertEqual(k.interaction_hint('human', 'counter18'), '盘里已经有切好的生菜了')


class RoundTests(unittest.TestCase):
    def test_orders_arrive_until_closing_and_open_orders_end_without_penalty(self):
        resolved = level(3)
        interval = resolved['order_policy']['interval_game_ms']
        plan = resolved['order_plan']['orders']
        self.assertEqual([o['arrival_game_ms'] for o in plan], list(range(0, 180000, interval)))
        k = Kitchen(resolved)
        k.advance(179.9)
        self.assertFalse(k.ended)
        money = k.money
        k.advance(1.)
        self.assertTrue(k.ended);self.assertAlmostEqual(k.time, 180., places=6)
        self.assertEqual(k.money, money - 10 * sum(o['status'] == 'expired' and o['deadline'] > 179.9 for o in k.orders))
        for o in k.orders:
            if o['deadline'] >= 180 - 1e-9:
                self.assertEqual(o['status'], 'unresolved_at_close')

    def test_money_is_judged_at_closing(self):
        k = Kitchen(level(1, level=lambda d: d['goal'].update(min_money=50)))
        k.money = 60
        self.assertTrue(k.snapshot()['goal_status']['met_now'])
        k.advance(10.);self.assertFalse(k.ended)  # reaching the target does not end the round
        k.money = 40
        k.advance(200.)
        self.assertTrue(k.ended);self.assertFalse(k.won());self.assertIn('未达目标', k.result())
        self.assertEqual(k.time_bonus, 0)

    def test_unreachable_target_is_announced_once(self):
        k = Kitchen(level(1, level=lambda d: d['goal'].update(min_money=300)))
        k.advance(179.)
        self.assertEqual([e['kind'] for e in k.events].count('goal_unreachable'), 1)
        self.assertFalse(k.ended)

    def test_observations_do_not_reveal_future_orders(self):
        k = Kitchen(level(3))
        state = k.snapshot()
        self.assertEqual(set(state['goal_status']), {'type', 'target_money', 'money', 'met_now', 'judged_at'})
        self.assertIn(state['future_orders'], (0, 1))
        self.assertTrue(all(o['status'] != 'future' for o in state['orders']))

    def test_one_large_step_equals_many_small_steps(self):
        a, b = Kitchen(level(3)), Kitchen(level(3))
        a.advance(150.)
        for _ in range(3000):
            b.advance(.05)
        self.assertEqual([(o['id'], o['status']) for o in a.orders], [(o['id'], o['status']) for o in b.orders])

    def test_spatial_levels_run(self):
        for n in (1, 2, 3):
            k = SpatialKitchen(level(n));k.advance(30.);k.assert_invariants()
            self.assertEqual(k.snapshot()['level_id'], f'level-{n}')


class DisplayLimitTests(unittest.TestCase):
    def test_waiting_orders_never_exceed_five_tickets(self):
        for n in (1, 2, 3):
            resolved = level(n)
            for t in range(0, 180000, 250):
                waiting = sum(o['arrival_game_ms'] <= t <= o['deadline_game_ms'] for o in resolved['order_plan']['orders'])
                self.assertLessEqual(waiting, 5, (n, t))

    def test_configurations_that_could_hide_tickets_are_rejected(self):
        bundle = cc.level_bundle('level-3', embed=True)
        bundle['order_policy']['patience_by_recipe']['burger'] = 5 * bundle['order_policy']['interval_game_ms']
        _, diagnostics = cc.resolve_config(bundle)
        self.assertIn('ORDER_BACKLOG_EXCEEDS_DISPLAY', {d['code'] for d in diagnostics})


class AgentRulesTests(unittest.TestCase):
    def test_jeff_receives_the_service_rules(self):
        k = SpatialKitchen(level(3))
        rules = SpatialJevClient(k.c, key='t').payload(k.snapshot(), k.actions('jeff'))['state']['rules']
        self.assertIn(f"at least {k.rules.goal['min_money']} yuan", rules['objective'])
        self.assertIn('only the net revenue at closing counts', rules['objective'])
        for text in ('steak 50 yuan', 'burger 80 yuan', 'up to 5 s: accepted at the price -10 yuan', 'refused with no payment',
                     'order keeps waiting', 'serving exactly at the deadline still counts', '-20 yuan', 'Expired order: -10 yuan',
                     'no bad reviews'):
            self.assertIn(text, rules['score'])


if __name__ == '__main__':
    unittest.main()
