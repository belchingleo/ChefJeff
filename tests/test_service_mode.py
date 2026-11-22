"""Service rules of the listed levels: money goal, continuous orders, burnt tiers.

Confirmed rules (2026-09-27): 180 game seconds; level menus steak / burger /
steak + burger; prices 50 / 80; the goal is net revenue at closing; no bad
reviews; wrong dish -20; expired order -10; a dish burnt up to 5 s is accepted
at price -10, longer is refused (no money, the order keeps waiting), the burnt
time running while it stays on a stove, burning or not (2026-11-22); serving at
the deadline counts; orders keep arriving until closing and orders still open
at closing carry no penalty; countdowns are per dish; at most 5 tickets.
"""
import unittest

import config_contract as cc
from kitchen import Food, Kitchen
from levels import available_levels
from model_language import english_text
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient


def level(n, **edits):
    bundle = cc.level_bundle(f'level-{n}', embed=True)
    bundle['level']['seeds'] = {'orders': 3, 'spawn': 0}
    for kind, edit in edits.items():
        edit(bundle[kind])
    return cc.freeze_bundle(bundle)


# The order policy without Overcooked 2's flow: the plan's fixed times, an expired order leaves.
FIXED_TIMES = lambda o: [o.pop(key, None) for key in ('keep_open', 'max_open', 'on_expire')]


class OrderFlowTests(unittest.TestCase):
    """Overcooked 2's order flow (ServerOrderControllerBase.Update) on the shipped levels."""

    def test_two_wait_from_the_start_and_a_served_one_is_replaced_at_once(self):
        k = Kitchen(level(1))
        pending = lambda: [o for o in k.orders if o['status'] == 'pending']
        self.assertEqual(len(pending()), 2)
        first = pending()[0];first['status'] = 'served';k.advance(.05)
        self.assertEqual(len(pending()), 2)
        self.assertAlmostEqual(pending()[-1]['arrival'], k.time, places=6)

    def test_one_more_every_interval_and_never_more_than_five(self):
        k = Kitchen(level(1))
        interval = k.order_flow['interval']
        k.advance(interval + .01)
        self.assertEqual(sum(o['status'] == 'pending' for o in k.orders), 3)
        k.advance(10 * interval)
        self.assertLessEqual(sum(o['status'] == 'pending' for o in k.orders), 5)


class BurntTimeTests(unittest.TestCase):
    """Owner decision 2026-11-22: burnt food's burnt time runs while it stays on a stove, whether the stove is
    burning, put out or neither, and stops when it leaves the stove; its stove catches fire once, as it burns.
    Level 1 accepts a steak burnt up to 5 s at the price -10 and refuses one burnt longer."""

    def setUp(self):
        self.k = k = Kitchen(level(1))
        self.burn = k.rules.heat_thresholds('beef')[1]
        self.stove = s = k.stations['p1']
        # Beef cooked in its own pan, 0.5 s from burning; both chefs stand at the stove (Jeff starts there).
        s.food = Food('B', 'ready', 6, self.burn - .5, ingredient='beef')
        k.heat_stove(s)
        k.chefs['human'].location = 'p1'
        k.advance(.5)
        self.assertEqual((s.food.stage, s.fire, k.burns, k.fires), ('burnt', True, 1, 1))

    def burnt(self, food=None):
        return (food or self.stove.food).heated - self.burn

    def do(self, who, key):
        ok, reason = self.k.command(who, key)
        self.assertTrue(ok, (key, reason))
        job = self.k.chefs[who].job
        self.k.advance(job.travel + job.work + 1e-6)
        self.assertIsNone(self.k.chefs[who].job)

    def put_out(self):
        """Jeff, at the stove, takes the extinguisher and sprays the fire out (0.5 s)."""
        k = self.k
        k.chefs['jeff'].hand, k.stations['extinguisher'].food = k.stations['extinguisher'].food, None
        label = next(a.label for a in k.actions('jeff') if a.key == 'extinguish p1')
        self.assertIn(f'随后糊菜可以装盘上菜（扣 10 元，还剩 {5 - self.burnt():.1f} 秒），也可以端锅到垃圾桶倒掉', label)
        self.do('jeff', 'extinguish p1')
        self.assertFalse(self.stove.fire)

    def lift(self):
        self.do('human', 'take pot p1')
        return self.k.chefs['human'].hand

    def serve(self):
        """Plate the held pan's food on the plate counter, put the pan back and serve: (order, money gained)."""
        k = self.k
        order = min((o for o in k.orders if o['status'] == 'pending'), key=lambda o: o['deadline'])
        money = k.money
        for key in ('plate plates', 'put pot p1', 'take plates', 'serve'):
            self.do('human', key)
        return order, k.money - money

    def test_put_out_at_three_seconds_and_lifted_at_four_is_accepted_at_minus_ten(self):
        k = self.k
        k.advance(2.5);self.put_out()
        self.assertAlmostEqual(self.burnt(), 3, places=3)
        self.assertTrue(self.stove.heating)  # the burnt time runs on once the fire is out
        k.advance(1);pan = self.lift()
        self.assertAlmostEqual(self.burnt(pan.contents), 4, places=3)
        order, gained = self.serve()
        self.assertEqual((order['status'], gained), ('served', k.rules.prices['steak'] - 10))
        self.assertEqual(k.fires, 1)

    def test_left_on_the_stove_past_the_limit_after_the_fire_is_out_is_refused(self):
        k = self.k
        k.advance(2.5);self.put_out();k.advance(2.5)
        pan = self.lift()
        self.assertAlmostEqual(self.burnt(pan.contents), 5.5, places=3)
        order, gained = self.serve()
        self.assertEqual((order['status'], gained), ('pending', 0))
        self.assertIn('dish_rejected', [e['kind'] for e in k.events])

    def test_lifted_off_a_stove_that_burnt_the_whole_time_past_the_limit_is_refused(self):
        k = self.k
        k.advance(5.5);self.assertTrue(self.stove.fire)
        pan = self.lift()
        self.assertAlmostEqual(self.burnt(pan.contents), 5.5, places=3)
        order, gained = self.serve()
        self.assertEqual((order['status'], gained), ('pending', 0))

    def test_the_burnt_time_stops_when_the_pan_leaves_the_stove(self):
        k = self.k
        k.advance(2.5);self.put_out();k.advance(1)
        pan = self.lift();k.advance(30)  # carried for 30 s
        self.assertAlmostEqual(self.burnt(pan.contents), 4, places=3)
        order, gained = self.serve()
        self.assertEqual((order['status'], gained), ('served', k.rules.prices['steak'] - 10))

    def test_burnt_food_on_a_stove_never_sets_it_alight_again(self):
        # As in Overcooked 2: neither left on the stove after the fire is out nor lifted and put back on it.
        k = self.k
        k.advance(1);self.put_out();k.advance(30)
        self.assertFalse(self.stove.fire);self.assertAlmostEqual(self.burnt(), 31.5, places=2)
        pan = self.lift();k.advance(10);self.assertAlmostEqual(self.burnt(pan.contents), 31.5, places=2)
        self.do('human', 'put pot p1');k.advance(2)
        self.assertAlmostEqual(self.burnt(), 33.5, places=2)  # back on a stove its burnt time runs again
        self.assertFalse(self.stove.fire);self.assertEqual((k.burns, k.fires), (1, 1))


class ExtinguishLabelTests(unittest.TestCase):
    """What the extinguish option of a burning stove says follows for the food in its pan, from the rules at listing
    time (the burnt_service tiers, the discard cost, the heat thresholds); the language catalog gives Jeff the same."""

    def kitchen(self, **edits):
        k = Kitchen(level(1, **edits))
        k.chefs['jeff'].hand, k.stations['extinguisher'].food = k.stations['extinguisher'].food, None
        return k

    def label(self, k):
        label = next(a.label for a in k.actions('jeff') if a.key == 'extinguish p1')
        self.assertNotRegex(english_text(label), r'[　-〿㐀-鿿＀-￯]')
        return label

    def burnt_for(self, k, seconds):
        """Beef that burns in Stove 1's pan, setting the stove alight, and stays there `seconds` more."""
        s = k.stations['p1']
        s.food = Food('B', 'ready', 6, k.rules.heat_thresholds('beef')[1] - .5, ingredient='beef')
        k.heat_stove(s);k.advance(.5 + seconds)
        self.assertEqual((s.food.stage, s.fire), ('burnt', True))

    def do(self, k, who, key):
        ok, reason = k.command(who, key)
        self.assertTrue(ok, (key, reason))
        job = k.chefs[who].job
        k.advance(job.travel + job.work + 1e-6)

    def test_burnt_food_still_accepted_can_be_served_with_the_seconds_left_or_emptied(self):
        k = self.kitchen();self.burnt_for(k, 2)
        label = self.label(k)
        self.assertEqual(label, '拿灭火器到灶台 1灭火（0.5s；随后糊菜可以装盘上菜（扣 10 元，还剩 3.0 秒），也可以端锅到垃圾桶倒掉）')
        self.assertEqual(english_text(label), 'Use the extinguisher at Stove 1 (0.5s; then the burnt food can be plated and '
                                              'served (10 yuan off, 3.0 s left), or the pan carried to a bin and emptied)')
        k.advance(1)  # the burnt time runs on while the pan is on the stove
        self.assertIn('还剩 2.0 秒', self.label(k))

    def cooking_on_fire(self, k):
        """Beef still cooking in Stove 1's pan when a fire spreads to the stove."""
        s = k.stations['p1']
        s.food = Food('B', 'cooking', 6, 1, ingredient='beef')
        k.heat_stove(s);k.ignite('p1')

    def test_the_task_and_the_events_leave_out_what_follows(self):
        """What follows is true when the option is listed; the task and the events that carry the label outlast it."""
        for setup in (lambda k: self.burnt_for(k, 2), lambda k: self.burnt_for(k, 5.5), self.cooking_on_fire,
                      lambda k: k.ignite('p1')):
            k = self.kitchen();setup(k)
            self.assertTrue(self.label(k).startswith('拿灭火器到灶台 1灭火（0.5s'))
            n = len(k.events)
            self.assertTrue(k.command('jeff', 'extinguish p1')[0])
            self.assertEqual(k.snapshot()['chefs']['jeff']['task'], '拿灭火器到灶台 1灭火（0.5s）')
            job = k.chefs['jeff'].job;k.advance(job.travel + job.work + 1e-6)
            events = [e['message'] for e in k.events[n:] if e['kind'] in ('action_start', 'action_done')]
            self.assertEqual(events, ['Jeff开始：拿灭火器到灶台 1灭火（0.5s）（路程 0s + 操作 0.5s）', 'Jeff完成动作：拿灭火器到灶台 1灭火（0.5s）'])
            self.assertEqual(english_text(events[-1]), 'jeff completed: Use the extinguisher at Stove 1 (0.5s)')

    def test_the_tier_is_the_one_when_the_spray_ends(self):
        """Burnt 4.6 s with 0.5 s of spraying left: accepted now, refused by the time the fire is out."""
        k = self.kitchen();self.burnt_for(k, 4.6)
        self.assertEqual(self.label(k), '拿灭火器到灶台 1灭火（0.5s；随后糊菜上菜会被拒收，只能端锅到垃圾桶倒掉（花 2 元））')
        self.do(k, 'jeff', 'extinguish p1')
        s = k.stations['p1']
        self.assertFalse(s.fire)
        self.assertEqual(k.rules.burnt_tier(k.rules.overcook(s.food, ('beef',)))['outcome'], 'rejected')
        # Half the spray done: 0.25 s left, so burnt 4.6 s still ends the spray inside the tier.
        k = self.kitchen();self.burnt_for(k, 4.6);k.stations['p1'].fire_strength = .5
        self.assertIn('随后糊菜可以装盘上菜（扣 10 元，还剩 0.4 秒）', self.label(k))

    def test_burnt_food_already_refused_can_only_be_emptied_at_the_discard_cost(self):
        k = self.kitchen();self.burnt_for(k, 5.5)
        label = self.label(k)
        self.assertEqual(label, '拿灭火器到灶台 1灭火（0.5s；随后糊菜上菜会被拒收，只能端锅到垃圾桶倒掉（花 2 元））')
        self.assertEqual(english_text(label), 'Use the extinguisher at Stove 1 (0.5s; then the burnt food would be refused if '
                                              'served, so the pan can only be carried to a bin and emptied (costs 2 yuan))')

    def test_the_numbers_are_the_rules(self):
        def rules(tiers):
            def edit(ruleset):
                ruleset['burnt_service'] = tiers
                ruleset['penalties']['discard'] = -4
            return edit
        tiers = [{'max_overcook_game_ms': 3000, 'outcome': 'accepted', 'adjustment': -15},
                 {'max_overcook_game_ms': None, 'outcome': 'rejected', 'adjustment': 0}]
        k = self.kitchen(ruleset=rules(tiers));self.burnt_for(k, 1)
        self.assertIn('随后糊菜可以装盘上菜（扣 15 元，还剩 2.0 秒），也可以端锅到垃圾桶倒掉', self.label(k))
        k.advance(2.5)
        self.assertIn('随后糊菜上菜会被拒收，只能端锅到垃圾桶倒掉（花 4 元）', self.label(k))
        # A last tier that accepts has no seconds left to give.
        k = self.kitchen(ruleset=rules(tiers[:1] + [{**tiers[0], 'max_overcook_game_ms': None, 'adjustment': -30}]))
        self.burnt_for(k, 4)
        label = self.label(k)
        self.assertIn('随后糊菜可以装盘上菜（扣 30 元），也可以端锅到垃圾桶倒掉', label)
        self.assertIn('then the burnt food can be plated and served (30 yuan off), or the pan carried', english_text(label))

    def test_food_a_fire_spread_to_is_not_burnt_and_cooks_on_once_the_fire_is_out(self):
        k = self.kitchen();s = k.stations['p1']
        ready, burn, _ = k.rules.heat_thresholds('beef')
        s.food = Food('B', 'ready', 6, ready + 1, ingredient='beef');k.heat_stove(s);k.ignite('p1')
        label = self.label(k)
        self.assertEqual(label, f'拿灭火器到灶台 1灭火（0.5s；锅里的菜没有糊，灭火后接着加热，再过 {burn - ready - 1:.1f} 秒糊锅）')
        self.assertEqual(english_text(label), 'Use the extinguisher at Stove 1 (0.5s; the food in the pan is not burnt and '
                                              f'cooks on once the fire is out, burning {burn - ready - 1:.1f} s later)')
        k.advance(3);self.assertIn(f'再过 {burn - ready - 1:.1f} 秒糊锅', self.label(k))  # it waits while the fire burns
        self.do(k, 'jeff', 'extinguish p1')
        k.advance(burn - ready - 1 - .05);self.assertEqual(s.food.stage, 'ready')
        k.advance(.1);self.assertEqual(s.food.stage, 'burnt')
        # Food still cooking: no seconds, it may cook on while the fire burns.
        k = self.kitchen();s = k.stations['p1']
        s.food = Food('B', 'cooking', 6, 1, ingredient='beef');k.heat_stove(s);k.ignite('p1')
        label = self.label(k)
        self.assertEqual(label, '拿灭火器到灶台 1灭火（0.5s；锅里的菜没有糊，灭火后接着加热）')
        self.assertEqual(english_text(label), 'Use the extinguisher at Stove 1 (0.5s; the food in the pan is not burnt and '
                                              'cooks on once the fire is out)')

    def test_an_empty_pan_or_no_pan_has_no_follow_up(self):
        k = self.kitchen();k.ignite('p1')
        self.assertEqual(english_text(self.label(k)), 'Use the extinguisher at Stove 1 (0.5s)')
        self.assertEqual(self.label(k), '拿灭火器到灶台 1灭火（0.5s）')
        k = self.kitchen();self.do(k, 'human', 'take pot p1');k.ignite('p1')
        self.assertIsNone(k.stations['p1'].pot_id)
        self.assertEqual(self.label(k), '拿灭火器到灶台 1灭火（0.5s）')


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
        self.assertEqual([e['id'] for e in available_levels()], ['level-1', 'level-2', 'level-3', 'level-4', 'level-5'])
        menus = {1: ['steak'], 2: ['burger'], 3: ['steak', 'burger'], 4: ['steak', 'burger'], 5: ['steak', 'burger']}
        for n in (1, 2, 3, 4, 5):
            resolved = level(n)
            self.assertEqual(resolved['level']['round_limit_game_ms'], 180000)
            self.assertEqual([e['recipe_ref'] for e in resolved['order_policy']['menu']], menus[n])
            prices = {r: v['price'] for r, v in resolved['recipe_catalog']['recipes'].items()}
            self.assertEqual({r: prices[r] for r in ('steak', 'burger')}, {'steak': 50, 'burger': 80})
            self.assertEqual(resolved['level']['goal']['type'], 'minimum_money')
            self.assertEqual(set(resolved['order_policy']['patience_by_recipe']), set(menus[n]))

    def test_good_dish_earns_the_price(self):
        k = self.kitchen(3);o = self.first(k);self.plate(k, o['dish'])
        self.serve(k)
        self.assertEqual(o['status'], 'served');self.assertEqual(k.money, k.rules.prices[o['dish']])

    def test_serving_at_the_deadline_counts_in_full(self):
        k = self.kitchen(2);o = self.first(k);self.plate(k, 'burger')
        self.serve(k, deadline_at_finish=True, order=o)
        self.assertEqual(o['status'], 'served');self.assertEqual(k.money, 80)

    def test_dish_goes_to_the_next_waiting_order_when_the_first_expired(self):
        # Overcooked 2: the expired order stays and starts its countdown again, so the dish goes to the
        # waiting order with the earliest deadline, now the second.
        k = self.kitchen(2)
        first, second = [o for o in k.orders if o['status'] == 'pending'][:2]
        first['deadline'] = k.time + .02;k.advance(.05)
        self.assertEqual(first['status'], 'pending');self.assertEqual(first['expired_times'], 1)
        self.assertAlmostEqual(first['deadline'], k.time + first['patience'], places=1);self.assertEqual(k.money, -10)
        self.plate(k, 'burger');self.serve(k)
        self.assertEqual(second['status'], 'served');self.assertEqual(first['status'], 'pending')
        self.assertEqual(k.money, -10 + 80)

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

    def test_wrong_dish_costs_twenty_and_hidden_future_orders_do_not_match(self):
        k = self.kitchen(1)
        self.plate(k, 'burger');self.serve(k)
        self.assertEqual(k.money, -20)
        # With the plan's fixed times (Overcooked 2's flow always keeps two orders waiting).
        k = self.kitchen(2, order_policy=FIXED_TIMES)
        self.first(k)['status'] = 'served'  # nothing waiting; later burger orders have not arrived
        self.plate(k, 'burger');self.serve(k)
        self.assertEqual(k.money, -20)

    def test_expiry_costs_ten_and_the_order_starts_again(self):
        k = self.kitchen(1);o = self.first(k)
        waiting = sum(x['status'] == 'pending' for x in k.orders)
        k.advance(o['deadline'] - k.time + .1)
        self.assertEqual(o['status'], 'pending');self.assertEqual(o['expired_times'], 1)
        self.assertEqual(k.money, -10 * waiting);self.assertEqual(k.expired_count(), waiting)
        self.assertGreater(o['deadline'], k.time + o['patience'] - .5)

    def test_without_the_flow_an_expired_order_leaves(self):
        k = self.kitchen(1, order_policy=FIXED_TIMES);o = self.first(k)
        k.advance(o['deadline'] - k.time + .1)
        self.assertEqual(o['status'], 'expired');self.assertEqual(k.money, -10)


class FixedSeedTests(unittest.TestCase):
    def test_listed_levels_use_fixed_seeds_so_every_round_is_identical(self):
        for n in (1, 2, 3):
            a, b = cc.load_level(f'level-{n}'), cc.load_level(f'level-{n}')
            self.assertEqual(a['seeds']['source'], 'configured')
            self.assertEqual(a['config_hash'], b['config_hash'])
        orders = [o['recipe_ref'] for o in cc.load_level('level-3')['order_plan']['orders']]
        self.assertEqual(orders[:6], ['steak', 'burger', 'burger', 'steak', 'burger', 'steak'])
        self.assertEqual(len(orders), 180000 // cc.OPEN_ORDER_PLAN_GAP_MS + 2)  # enough for any pace

    def test_targets_are_whole_tens(self):
        for n in (1, 2, 3):
            self.assertEqual(cc.load_level(f'level-{n}')['level']['goal']['min_money'] % 10, 0)

    # Targets the owner set apart from the calibration (level: target). Level 3 was kept at 190 above its
    # calibration (owner decision 2026-10-06); since calibration-v2 (owner decision 2026-11-06) every level
    # uses its calibrated target.
    OWNER_TARGETS = {}

    @staticmethod
    def sweep():
        import importlib.util
        from pathlib import Path
        path = Path(cc.__file__).resolve().parent / 'scripts' / 'reference_sweep.py'
        spec = importlib.util.spec_from_file_location('reference_sweep', path)
        sweep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sweep)
        return sweep

    @staticmethod
    def report():
        import json
        from pathlib import Path
        path = Path(cc.__file__).resolve().parent / 'docs' / 'architecture' / 'reports' / 'calibration.json'
        return json.loads(path.read_text())

    def test_calibration_report_records_the_run_set_and_is_current(self):
        # The report is reproducible from its run set; replaying the first seed of every level must
        # give the recorded incomes (regenerate: python scripts/reference_sweep.py --calibrate
        # --out docs/architecture/reports/calibration.json).
        sweep, report = self.sweep(), self.report()
        self.assertEqual(report['run_set'], sweep.CALIBRATION)
        self.assertEqual([row['level'] for row in report['levels']], [1, 2, 3, 4, 5])
        seed = report['run_set']['seeds'][0]
        for row in report['levels']:
            n = row['level']
            with self.subTest(level=n):
                recorded = next(r for r in row['runs'] if r['seed'] == seed)
                # The recorded best pairing and the solo rung (replaying all four pairings costs too much here).
                pair, swapped = recorded['pair'].split(' ')[0], recorded['pair'].endswith('swapped')
                policy = cc.load_level(f'level-{n}')['order_policy']
                k = sweep.play(n, policy['interval_game_ms'], policy['patience_by_recipe'], seed, report['run_set']['variant'], pair, swapped)
                self.assertEqual(k.money, recorded['money'])
                self.assertEqual(sweep.solo(n, seed).money, recorded['solo'])

    def test_targets_are_half_the_median_reference_income(self):
        # Targets are 50% of the median net income of the scripted reference pair over the calibration
        # run set (owner decisions 2026-09-27 and 2026-10-06), rounded down to a multiple of 10.
        for row in self.report()['levels']:
            n = row['level']
            with self.subTest(level=n):
                target = cc.load_level(f'level-{n}')['level']['goal']['min_money']
                if n in self.OWNER_TARGETS:
                    self.assertEqual(target, self.OWNER_TARGETS[n])
                    self.assertGreaterEqual(target, row['target_50pct'])
                else:
                    self.assertEqual(target, row['target_50pct'])


class ServiceWordingTests(unittest.TestCase):
    def test_burn_event_and_serve_hint_do_not_mention_bad_reviews(self):
        # There are no bad reviews; no player- or model-facing text may mention them.
        import json as _json
        from pathlib import Path
        english = _json.loads((Path(cc.__file__).resolve().parent / 'model-language-en-v4.json').read_text())
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
        resolved = level(3, order_policy=FIXED_TIMES)
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

    def test_unreachable_target_is_announced_once(self):
        k = Kitchen(level(1, level=lambda d: d['goal'].update(min_money=300), order_policy=FIXED_TIMES))
        k.advance(179.)
        self.assertEqual([e['kind'] for e in k.events].count('goal_unreachable'), 1)
        self.assertFalse(k.ended)

    def test_observations_do_not_reveal_future_orders(self):
        k = Kitchen(level(3))
        state = k.snapshot()
        self.assertEqual(set(state['goal_status']), {'type', 'target_money', 'star_scores', 'money', 'met_now', 'stars_now', 'judged_at'})
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
        self.assertIn(f"{k.rules.goal['min_money']} yuan or more earns one star and reaches the target", rules['objective'])
        self.assertIn('only the net revenue at closing counts', rules['objective'])
        for text in ('steak 50 yuan', 'burger 80 yuan', 'up to 5 s: accepted at the price -10 yuan', 'refused with no payment',
                     'order keeps waiting', 'serving exactly at the deadline still counts', '-20 yuan', 'Expired order: -10 yuan',
                     'no bad reviews'):
            self.assertIn(text, rules['score'])


if __name__ == '__main__':
    unittest.main()
