"""servability-v1 (released, no switch): burnt food says whether a dish with it is still accepted, at the tier's price
change and, while its burnt time runs on a stove, for how many seconds more, or refused, in the engine's labels (both
chefs, Chinese for the player and English for Jeff) and in the kitchen state Jeff reads. A step that takes the food off
a stove says the tier the step leaves it in, and serving says the wrong-dish cost when no order waits for the dish. The
shipped tier accepts a dish burnt up to 5 s at the price -10 and refuses one burnt longer; every case is checked on
both sides of that limit, and the steps are carried out to check that the engine does what the label said. The seconds
are rounded down to the tenth, so a step started when they are up still holds and one started a substep past the real
margin does not. No model is called."""
import re
import unittest
from unittest.mock import patch

import config_contract as cc
import features
import one_press
import servability
import work_notes
from jev import DecisionLoop, compose_payload
from kitchen import SERVE_LABEL, SUBSTEP, Food, GroundItem
from model_language import english_text
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient

CJK = re.compile(r'[　-〿㐀-鿿＀-￯]')
LIMIT = 5.0                 # the shipped tier: accepted at -10 up to 5 s burnt, refused after
JUST_OVER = LIMIT + .01
LIFT = '端起灶台 1的平底锅（离开灶台停止加热，占手持位）'
LIFT_EN = 'Lift the frying pan from Stove 1 (stops heating off the stove; occupies your hands)'
PLATE = '用手中的干净盘盛出灶台 1的菜'
PLATE_EN = 'Plate food from Stove 1'
SERVE_EN = 'Serve the plated dish (serving a dish no order is waiting for costs money; '
NO_ORDER = '拿已装盘的菜出餐（现在没有订单在等这道菜，出餐扣 20 元）'
NO_ORDER_EN = 'Serve the plated dish (no order is waiting for this dish now, so serving it costs 20 yuan)'


def level(name, **edits):
    bundle = cc.level_bundle(name, embed=True)
    bundle['level']['seeds'] = {'orders': 3, 'spawn': 0}
    for kind, edit in edits.items():
        edit(bundle[kind])
    return SpatialKitchen(cc.freeze_bundle(bundle))


def burnt(k, seconds, item='beef', **extra):
    """Burnt food that has been burnt for `seconds` by the engine's own measure (Rules.overcook)."""
    return Food(extra.pop('id', 'B1'), 'burnt', 6, k.rules.heat_thresholds(item)[1] + seconds, ingredient=item, **extra)


def on_stove(k, seconds, stove='p1'):
    s = k.stations[stove]
    s.food = burnt(k, seconds)
    k.heat_stove(s)
    return s


def pan_of(k, seconds, stove='p1'):
    """Stove 1's pan (the level's only one), taken off it, with food burnt for `seconds` in it."""
    s = k.stations[stove]
    pan, s.pot_id, s.food = s.pot_id, None, None
    return Food(pan, 'pot', contents=burnt(k, seconds))


def plated(k, seconds, plate='D1'):
    """A steak on a plate, its beef burnt for `seconds`."""
    return Food('B2', 'burnt', 6, k.rules.heat_thresholds('beef')[1] + seconds, plate_id=plate, ingredient='dish',
                components=('beef',))


def label(k, key, who='jeff'):
    """The listed action with this key (its label and English)."""
    return next(a for a in k.actions(who) if a.key == key)


def english(chinese):
    text = english_text(chinese)
    assert not CJK.search(text), text
    return text


def run(k, who, key):
    ok, reason = k.command(who, key)
    assert ok, (key, reason)
    while k.chefs[who].job is not None:
        k.advance(.05)


def holding_plate(k, who):
    """`who` holds level 1's clean plate, taken off Counter 1."""
    k.chefs[who].hand, k.stations['plates'].food = k.stations['plates'].food, None


def started(k, who, key, wait):
    """The tier a step leaves its food in when it starts `wait` s from now (the engine's own outcome)."""
    k.advance(wait)
    run(k, who, key)
    held = k.chefs[who].hand
    return k.burnt_service(held.contents if held.stage == 'pot' else held)['outcome']


def request(k, **switches):
    # The full kitchen (no request parts): these tests read the state's own keys (kitchen_view, released in 0.11.0,
    # writes it out another way).
    options = {**features.compose_options(features.current()), 'parts': None, **switches}
    return compose_payload(SpatialJevClient(k.c, key='test-no-credential'), k, k.snapshot(), k.actions('jeff'), [],
                           None, **options)


class TierTests(unittest.TestCase):
    """Kitchen.burnt_service: the tier the serving step reads, with the seconds left while the burnt time runs."""

    def test_at_the_limit_accepted_with_no_time_left_and_just_over_refused(self):
        k = level('level-1')
        tier = k.burnt_service(on_stove(k, 2.9).food, running=True)
        self.assertEqual((tier['outcome'], tier['adjustment']), ('accepted', -10))
        self.assertAlmostEqual(tier['left'], LIMIT - 2.9)
        self.assertEqual(k.burnt_service(on_stove(k, LIMIT).food, running=True),
                         {'outcome': 'accepted', 'adjustment': -10, 'left': 0.0})
        self.assertEqual(k.burnt_service(on_stove(k, JUST_OVER).food, running=True),
                         {'outcome': 'rejected', 'adjustment': 0, 'left': None})
        # Off a stove the burnt time stands still: no seconds.
        self.assertEqual(k.burnt_service(burnt(k, LIMIT)), {'outcome': 'accepted', 'adjustment': -10, 'left': None})
        self.assertIsNone(k.burnt_service(Food('B1', 'ready', 6, 12, ingredient='beef')))

    def test_serving_takes_the_tier_the_label_said(self):
        for seconds, served, money in ((LIMIT, 'served', 50 - 10), (JUST_OVER, 'pending', 0)):
            with self.subTest(seconds=seconds):
                k = level('level-1')
                order = k.waiting_order(plated(k, seconds))
                k.stations['plates'].food = None
                k.chefs['jeff'].hand = plated(k, seconds)
                said = k.burnt_service(k.chefs['jeff'].hand)
                run(k, 'jeff', 'serve')
                self.assertEqual((order['status'], k.money), (served, money))
                self.assertEqual(said['outcome'], 'accepted' if served == 'served' else 'rejected')

    def test_a_step_off_the_stove_gains_its_walk_in_whole_substeps(self):
        """Jeff stands 0.51 s from Stove 1 on level 1: the stove heats through 11 substeps before the step ends."""
        k = level('level-1')
        on_stove(k, 1)
        self.assertAlmostEqual(k.travel_time(k.chefs['jeff'], 'p1', 'lift_pot'), .5125)
        self.assertAlmostEqual(k.step_gain('jeff', 'p1', 'lift_pot'), 11 * SUBSTEP)
        k.chefs['jeff'].location, k.positions['jeff'] = 'p1', k.path('jeff', 'p1', kind='lift_pot')[-1]
        self.assertAlmostEqual(k.step_gain('jeff', 'p1', 'lift_pot'), SUBSTEP)     # standing there: one substep


class LabelTests(unittest.TestCase):
    """The engine's labels, the same for both chefs; the language catalog gives Jeff the same in English."""

    def test_lifting_a_pan_of_burnt_food_says_the_tier_the_lift_leaves_it_in(self):
        k = level('level-1')
        on_stove(k, 2.95)
        gain = k.step_gain('jeff', 'p1', 'lift_pot')          # 11 substeps (test_a_step_off_the_stove_...)
        lift = label(k, 'take pot p1')
        self.assertEqual(lift.label, LIFT + '（锅里是糊菜：1.5 秒内开始这一步，端起后还能上菜，扣 10 元）')
        self.assertEqual(english(lift.label), LIFT_EN + ' (it holds burnt food: accepted at -10 yuan if this starts '
                                                        'within 1.5 s)')
        self.assertEqual(label(k, 'take pot p1', 'human').label.split('（锅里是糊菜')[0], LIFT)
        on_stove(k, JUST_OVER)
        self.assertEqual(label(k, 'take pot p1').label, LIFT + '（锅里是糊菜：端起时已糊太久，上菜会被拒收）')
        self.assertEqual(english(label(k, 'take pot p1').label),
                         LIFT_EN + ' (it holds burnt food: refused, burnt too long by the time it is lifted)')
        # The walk carries it past the limit: accepted with no time to spare at LIMIT - gain, refused just after.
        for seconds, note in ((LIMIT - gain, '（锅里是糊菜：只有马上开始这一步，端起后才还能上菜，扣 10 元）'),
                              (LIMIT - gain + .01, '（锅里是糊菜：端起时已糊太久，上菜会被拒收）'), (LIMIT, '（锅里是糊菜：端起时已糊太久，上菜会被拒收）')):
            with self.subTest(seconds=seconds):
                k = level('level-1')
                on_stove(k, seconds)
                self.assertEqual(label(k, 'take pot p1').label, LIFT + note)
                run(k, 'jeff', 'take pot p1')
                outcome = k.burnt_service(k.chefs['jeff'].hand.contents)['outcome']
                self.assertEqual(outcome, 'rejected' if '拒收' in note else 'accepted')
        # Food that is not burnt: the label as before.
        k = level('level-1')
        k.stations['p1'].food = Food('B1', 'ready', 6, 12, ingredient='beef')
        self.assertEqual(label(k, 'take pot p1').label, LIFT)

    def test_the_seconds_to_start_are_what_the_engine_gives(self):
        """Burnt 2.95 s: the lift may wait 1.5 s to start and stay accepted; started later the pan is refused."""
        for wait, outcome in ((1.5, 'accepted'), (1.55, 'rejected')):
            with self.subTest(wait=wait):
                k = level('level-1')
                on_stove(k, 2.95)
                k.advance(wait)
                run(k, 'jeff', 'take pot p1')
                self.assertEqual(k.burnt_service(k.chefs['jeff'].hand.contents)['outcome'], outcome)

    def test_swapping_a_held_pan_with_a_pan_of_burnt_food_says_its_tier(self):
        """Level 3, Jeff holds the empty Stove 2 pan. The swap takes Stove 1's pan off the stove as a lift does, so it
        gives the tier as the swap leaves it; a counter's pan, off the stove, its tier now."""
        swap = '与灶台 1的平底锅交换（各自保留里面的食物）'
        swap_en = 'Swap with the frying pan at Stove 1 (contents stay where they are)'

        def kitchen(seconds, who='jeff'):
            k = level('level-3')
            s2 = k.stations['p2']
            pan, s2.pot_id, s2.food = s2.pot_id, None, None
            k.chefs[who].hand = Food(pan, 'pot')
            on_stove(k, seconds)
            return k
        gain = kitchen(1).step_gain('jeff', 'p1', 'swap_pot')
        seconds = LIMIT - gain - 1.22                    # the real margin 1.22 s
        option = label(kitchen(seconds), 'swap pot p1')
        self.assertEqual(option.label, swap + '（锅里是糊菜：1.2 秒内开始这一步，换下后还能上菜，扣 10 元）')
        self.assertEqual(english(option.label), swap_en + ' (it holds burnt food: accepted at -10 yuan if this starts '
                                                          'within 1.2 s)')
        self.assertEqual(started(kitchen(seconds), 'jeff', 'swap pot p1', 1.2), 'accepted')
        self.assertEqual(started(kitchen(seconds), 'jeff', 'swap pot p1', 1.25), 'rejected')
        self.assertEqual(label(kitchen(LIMIT - gain), 'swap pot p1').label,
                         swap + '（锅里是糊菜：只有马上开始这一步，换下后才还能上菜，扣 10 元）')
        self.assertEqual(english(label(kitchen(LIMIT - gain), 'swap pot p1').label),
                         swap_en + ' (it holds burnt food: accepted at -10 yuan only if this starts now)')
        for seconds in (LIMIT - gain + .01, JUST_OVER):
            refused = label(kitchen(seconds), 'swap pot p1')
            self.assertEqual(refused.label, swap + '（锅里是糊菜：换下时已糊太久，上菜会被拒收）')
            self.assertEqual(english(refused.label), swap_en + ' (it holds burnt food: refused, burnt too long by the '
                                                               'time the swap takes it off the stove)')
            self.assertEqual(started(kitchen(seconds), 'jeff', 'swap pot p1', 0), 'rejected')
        self.assertEqual(label(kitchen(JUST_OVER, 'human'), 'swap pot p1', 'human').label, refused.label)
        k = kitchen(2.0)
        self.assertTrue(k.command('jeff', 'swap pot p1')[0])
        self.assertEqual(k.chefs['jeff'].job.action.label, swap)          # the task leaves the tier out
        # A pan of burnt food on a counter: its burnt time stands still there.
        for seconds, note, note_en in ((LIMIT, '（锅里是糊菜：还能上菜，扣 10 元）', ' (it holds burnt food: accepted at -10 yuan)'),
                                       (JUST_OVER, '（锅里是糊菜：糊太久，上菜会被拒收）', ' (it holds burnt food: refused)')):
            k = kitchen(1)
            k.stations['counter3'].food = pan_of(k, seconds)
            option = label(k, 'swap pot counter3')
            self.assertEqual(option.label, '与柜台 3的平底锅交换（各自保留里面的食物）' + note)
            self.assertEqual(english(option.label), 'Swap with the frying pan at Counter 3 (contents stay where they are)'
                             + note_en)
            # The same pan on the floor by Counter 3.
            k = kitchen(1)
            pan = pan_of(k, seconds)
            k.ground[pan.id] = GroundItem(pan, 'counter3')
            option = label(k, f'swap pot ground {pan.id}')
            self.assertEqual(option.label, '与地上的平底锅交换（各自保留里面的食物）' + note)
            self.assertEqual(english(option.label), 'Swap with the frying pan on the floor (contents stay where they are)'
                             + note_en)

    def test_plating_from_a_stove_gives_the_tier_of_the_dish_it_makes_and_off_it_no_seconds(self):
        k = level('level-1')
        k.chefs['jeff'].hand, k.stations['plates'].food = k.stations['plates'].food, None
        on_stove(k, 2.95)
        gain = k.step_gain('jeff', 'p1', 'plate_pot')
        plate = label(k, 'plate p1')
        self.assertEqual(plate.label, PLATE + '（糊菜：1.5 秒内开始这一步，装出的菜还能上菜，扣 10 元）')
        self.assertEqual(english(plate.label), PLATE_EN + ' (burnt food: accepted at -10 yuan if this starts within 1.5 s)')
        on_stove(k, JUST_OVER)
        self.assertEqual(english(label(k, 'plate p1').label),
                         PLATE_EN + ' (burnt food: refused, burnt too long by the time it is plated)')
        # Burnt 4.5 s, 0.51 s away (the reviewed case): the step makes a plate burnt 5.05 s, which is refused.
        for seconds in (LIMIT - gain, LIMIT - gain + .01, 4.5):
            with self.subTest(seconds=seconds):
                k = level('level-1')
                k.chefs['jeff'].hand, k.stations['plates'].food = k.stations['plates'].food, None
                on_stove(k, seconds)
                text = label(k, 'plate p1').label
                refused = seconds > LIMIT - gain + 1e-9
                self.assertEqual(text, PLATE + ('（糊菜：装盘时已糊太久，上菜会被拒收）' if refused
                                                else '（糊菜：只有马上开始这一步，装出的菜才还能上菜，扣 10 元）'))
                run(k, 'jeff', 'plate p1')
                self.assertEqual(k.burnt_service(k.chefs['jeff'].hand)['outcome'], 'rejected' if refused else 'accepted')
                run(k, 'jeff', 'serve')
                self.assertEqual(k.money, 0 if refused else 50 - 10)
        # A held pan onto the plate on a counter: off the stove, no seconds.
        for seconds, note, note_en in ((LIMIT, '（糊菜：还能上菜，扣 10 元）', ' (burnt food: accepted at -10 yuan)'),
                                       (JUST_OVER, '（糊菜：糊太久，上菜会被拒收）', ' (burnt food: refused)')):
            k = level('level-1')
            k.chefs['jeff'].hand = pan_of(k, seconds)
            fill = label(k, 'plate plates')
            self.assertEqual(fill.label, '把手中平底锅里的菜盛到柜台 1的盘里（空平底锅留在手中）' + note)
            self.assertEqual(english(fill.label),
                             'Fill the plate on Counter 1 from your frying pan (keep the empty frying pan)' + note_en)

    def test_plating_from_a_pan_on_a_counter_or_the_floor_in_both_languages(self):
        """The two labels the engine also writes in English itself (engine_english) say the same as the Chinese."""
        k = level('level-1')
        pan = k.stations['p1'].pot_id
        pan_of(k, 0)
        k.chefs['jeff'].hand, k.stations['plates'].food = k.stations['plates'].food, None
        for seconds, tier in ((LIMIT, 'accepted at -10 yuan'), (JUST_OVER, 'refused')):
            k.stations['counter3'].food = Food(pan, 'pot', contents=burnt(k, seconds))
            counter = label(k, 'plate counter3')
            self.assertTrue(counter.label.startswith('用手中的盘盛出柜台 3的平底锅里的菜（糊菜：'), counter.label)
            self.assertEqual(counter.english, f'Plate food from the frying pan on Counter 3 (burnt food: {tier})')
            # The catalog's own reading of this label is garbled before the note (engine_english.py says why).
            self.assertTrue(english_text(counter.label).endswith(f' (burnt food: {tier})'))
            k.stations['counter3'].food = None
            k.ground[pan] = GroundItem(Food(pan, 'pot', contents=burnt(k, seconds)), k.chefs['jeff'].location)
            ground = label(k, f'plate ground {pan}')
            self.assertTrue(ground.label.startswith('用手中的干净盘盛出地上平底锅里的菜（空平底锅留在原地）（糊菜：'), ground.label)
            self.assertEqual(ground.english, 'Plate food from the frying pan on the floor (empty frying pan stays in '
                                             f'place) (burnt food: {tier})')
            del k.ground[pan]

    def test_adding_to_a_plate_with_burnt_food_and_merging_it(self):
        k = level('level-3')
        k.stations['counter3'].food = plated(k, LIMIT)
        k.chefs['jeff'].hand = Food('L1', 'chopped', 2.2, ingredient='lettuce')
        add = label(k, 'assemble counter3')
        self.assertEqual(add.label, '把手中的生菜放进柜台 3的盘里（糊菜：还能上菜，扣 10 元）')
        self.assertEqual(english(add.label), 'Put the held Lettuce onto the plate at Counter 3 (burnt food: accepted at '
                                             '-10 yuan)')
        self.assertNotIn('糊菜', label(k, 'assemble plates').label)      # a clean plate there: nothing said
        k.stations['counter3'].food = plated(k, JUST_OVER)
        self.assertTrue(label(k, 'assemble counter3').label.endswith('（糊菜：糊太久，上菜会被拒收）'))
        # The held plate takes the counter's lettuce; the held plate is the burnt one.
        k.stations['counter3'].food, k.chefs['jeff'].hand = Food('L1', 'chopped', 2.2, ingredient='lettuce'), plated(k, LIMIT)
        self.assertEqual(label(k, 'assemble counter3').label, '把柜台 3的生菜加进手中的盘（糊菜：还能上菜，扣 10 元）')
        # Merging the counter's burnt plate into a held plate with bread.
        k.chefs['jeff'].hand = Food('R1', 'assembled', plate_id='D8', ingredient='dish', components=('bread',))
        k.stations['counter3'].food = plated(k, JUST_OVER)
        merge = label(k, 'merge counter3')
        self.assertEqual(merge.label, '把柜台 3盘中食物合入手中盘（空盘留在原位）（糊菜：糊太久，上菜会被拒收）')
        self.assertEqual(english(merge.label), 'Merge food from the plate at Counter 3 into the held plate (empty plate '
                                               'stays in place) (burnt food: refused)')

    def test_filling_the_other_chefs_plate_from_a_pan_of_burnt_food(self):
        for seconds, note in ((LIMIT, '（糊菜：还能上菜，扣 10 元）'), (JUST_OVER, '（糊菜：糊太久，上菜会被拒收）')):
            k = level('level-1')
            k.chefs['human'].hand, k.stations['plates'].food = k.stations['plates'].food, None
            k.chefs['jeff'].hand = pan_of(k, seconds)
            self.assertEqual(label(k, 'plate partner').label, '走近，把食材加入队友手中的盘（容器留在原持有者手中）' + note)
            english(label(k, 'plate partner').label)

    def test_serving_a_burnt_dish_says_accepted_or_refused_and_what_refusal_costs(self):
        k = level('level-1')
        k.stations['plates'].food = None
        k.chefs['jeff'].hand = plated(k, LIMIT)
        serve = label(k, 'serve')
        self.assertEqual(serve.label, '拿已装盘的菜出餐（没有订单在等这道菜会扣钱；这盘糊菜还能上菜，扣 10 元）')
        self.assertEqual(english(serve.label), SERVE_EN + 'this burnt dish is accepted at -10 yuan)')
        k.chefs['jeff'].hand = plated(k, JUST_OVER)
        serve = label(k, 'serve')
        self.assertEqual(serve.label, '拿已装盘的菜出餐（没有订单在等这道菜会扣钱；这盘糊菜会被拒收，不收钱，菜没了，订单继续等待）')
        self.assertEqual(english(serve.label), SERVE_EN + 'this burnt dish is refused with no payment; the dish is lost '
                                                          'and the order keeps waiting)')
        k.chefs['human'].hand = plated(k, JUST_OVER, 'D2')
        self.assertEqual(label(k, 'serve', 'human').label, serve.label)          # the player reads the same
        k.chefs['jeff'].hand = Food('B2', 'ready', 6, 12, plate_id='D1', ingredient='dish', components=('beef',))
        self.assertEqual(label(k, 'serve').label, SERVE_LABEL)

    def test_with_no_order_waiting_for_the_dish_serving_costs_the_wrong_dish_penalty_whatever_the_tier(self):
        """Level 2 orders only burgers: a burnt steak, accepted or refused by the tier, costs 20 yuan to serve."""
        for seconds in (3, LIMIT, JUST_OVER):
            with self.subTest(seconds=seconds):
                k = level('level-2')
                k.stations['plates'].food = None
                k.chefs['jeff'].hand = plated(k, seconds)
                self.assertIsNone(k.waiting_order(k.chefs['jeff'].hand))
                self.assertEqual(label(k, 'serve').label, NO_ORDER)
                self.assertEqual(english(NO_ORDER), NO_ORDER_EN)
                k.chefs['human'].hand = plated(k, seconds, 'D2')
                self.assertEqual(label(k, 'serve', 'human').label, NO_ORDER)
                n = len(k.events)
                run(k, 'jeff', 'serve')
                self.assertEqual(k.money, -20)
                self.assertEqual([e['kind'] for e in k.events[n:] if e['kind'] in ('wrong_dish', 'dish_rejected', 'served')],
                                 ['wrong_dish'])
        # Level 3 with both waiting orders made burgers: the same for its steak.
        k = level('level-3')
        for order in k.orders:
            if order['status'] == 'pending':
                order['dish'] = 'burger'
        k.stations['plates'].food = None
        k.chefs['jeff'].hand = plated(k, 3)
        self.assertEqual(label(k, 'serve').label, NO_ORDER)

    def test_the_numbers_are_the_rules(self):
        def tiers(ruleset):
            ruleset['burnt_service'] = [{'max_overcook_game_ms': 3000, 'outcome': 'accepted', 'adjustment': -15},
                                        {'max_overcook_game_ms': None, 'outcome': 'rejected', 'adjustment': 0}]
            ruleset['penalties']['wrong_dish'] = -25
        k = level('level-1', ruleset=tiers)
        on_stove(k, .95)
        self.assertTrue(label(k, 'take pot p1').label.endswith('（锅里是糊菜：1.5 秒内开始这一步，端起后还能上菜，扣 15 元）'))
        on_stove(k, 3.01)
        self.assertTrue(label(k, 'take pot p1').label.endswith('（锅里是糊菜：端起时已糊太久，上菜会被拒收）'))
        k = level('level-2', ruleset=tiers)
        k.stations['plates'].food = None
        k.chefs['jeff'].hand = plated(k, 1)
        self.assertEqual(label(k, 'serve').label, '拿已装盘的菜出餐（现在没有订单在等这道菜，出餐扣 25 元）')

    def test_taking_or_picking_up_burnt_food_says_its_tier(self):
        """Off a stove its burnt time stands still: no seconds; the pan says it holds burnt food."""
        for seconds, tier, tier_en in ((LIMIT, '还能上菜，扣 10 元', 'accepted at -10 yuan'),
                                       (JUST_OVER, '糊太久，上菜会被拒收', 'refused')):
            with self.subTest(seconds=seconds):
                k = level('level-1')
                k.stations['counter3'].food = pan_of(k, seconds)
                take = label(k, 'take counter3')
                self.assertEqual(take.label, f'从柜台 3拿起锅（锅里是糊菜：{tier}）')
                self.assertEqual(english(take.label), f'Take Pot from Counter 3 (it holds burnt food: {tier_en})')
                self.assertEqual(label(k, 'take counter3', 'human').label, take.label)
                criteria = request(k)['questions']['next_action']['criteria']
                self.assertEqual(criteria['take counter3'],
                                 f'Take frying pan with beef (burnt) from Counter 3 (it holds burnt food: {tier_en})')
                pan = k.stations['counter3'].food
                k.stations['counter3'].food = None
                k.ground[pan.id] = GroundItem(pan, 'counter3')
                pickup = label(k, f'pickup {pan.id}')
                self.assertEqual(pickup.label, f'去柜台 3捡起 {pan.id}（锅；自动换手）（锅里是糊菜：{tier}）')
                self.assertEqual(request(k)['questions']['next_action']['criteria'][f'pickup {pan.id}'],
                                 f'Pick up frying pan with beef (burnt) {pan.id} at Counter 3 (it holds burnt food: {tier_en})')
                k = level('level-1')
                k.stations['counter3'].food = plated(k, seconds)
                self.assertEqual(label(k, 'take counter3').label, f'从柜台 3拿起糊了（糊菜：{tier}）')
                # Without option_notes' order note (released in 0.11.0), which these labels do not test.
                self.assertEqual(request(k, serve_note=False)['questions']['next_action']['criteria']['take counter3'],
                                 f'Take burnt dish from Counter 3 (burnt food: {tier_en})')
        k = level('level-1')
        k.stations['counter3'].food = Food('B2', 'ready', 6, 12, plate_id='D1', ingredient='dish', components=('beef',))
        self.assertNotIn('糊菜', label(k, 'take counter3').label)

    def test_one_press_put_then_take_says_the_tier_and_put_then_lift_says_it_as_it_is_now(self):
        flags = one_press.flags({name: True for name in one_press.NAMES})
        k = level('level-1')
        k.chefs['jeff'].hand = Food('L1', 'raw', ingredient='beef')
        on_stove(k, 2.9)
        k.stations['counter3'].food = plated(k, JUST_OVER)
        options = {a.key: a.label for a in one_press.options(k, 'jeff', k.actions('jeff'), flags)}
        self.assertTrue(options['put then take p1'].endswith(
            LIFT + '（锅里是糊菜：还能上菜，扣 10 元，留在灶台上还剩 2.1 秒）'), options['put then take p1'])
        self.assertTrue(options['put then take counter3'].endswith('拿起糊了（糊菜：糊太久，上菜会被拒收）'))
        english(options['put then take p1'])

    def test_the_task_and_the_events_leave_the_tier_out(self):
        """The tier is true when the option is listed; the task and the events that carry the label outlast it."""
        k = level('level-1')
        on_stove(k, 2.9)
        n = len(k.events)
        self.assertTrue(k.command('jeff', 'take pot p1')[0])
        self.assertEqual(k.snapshot()['chefs']['jeff']['task'], LIFT)
        self.assertEqual(k.events[n]['message'].split('（路程')[0], 'Jeff开始：' + LIFT)
        while k.chefs['jeff'].job is not None:
            k.advance(.05)
        self.assertEqual(k.events[-1]['message'], 'Jeff完成动作：' + LIFT)
        k.stations['plates'].food = None
        k.chefs['jeff'].hand = plated(k, JUST_OVER)
        self.assertTrue(k.command('jeff', 'serve')[0])
        self.assertEqual(k.snapshot()['chefs']['jeff']['task'], SERVE_LABEL)
        # The engine's own English (engine_english) leaves it out too.
        k = level('level-1')
        k.chefs['jeff'].hand, k.stations['plates'].food = k.stations['plates'].food, None
        k.stations['counter3'].food = pan_of(k, LIMIT)
        self.assertTrue(k.command('jeff', 'plate counter3')[0])
        job = k.chefs['jeff'].job
        self.assertEqual((job.action.label, job.action.english),
                         ('用手中的盘盛出柜台 3的平底锅里的菜', 'Plate food from the frying pan on Counter 3'))
        self.assertTrue(k.english_events[k.events[-1]['seq']].startswith('jeff started: Plate food from the frying pan '
                                                                         'on Counter 3 (travel'))

    def test_the_players_notice_of_jeffs_choice_leaves_it_out(self):
        """The notice stays on the player's status line after the seconds it was listed with go stale."""
        def notice(k, key):
            notices = []
            loop = DecisionLoop(k, SpatialJevClient(k.c, key='test-no-credential'), lambda kind, data: None,
                                notices.append)
            loop.send = lambda *args: None
            decision = label(k, key)
            loop.q.put(({'id': 0, 'sent': 100.0, 'epoch': loop.epoch, 'job_id': None, 'actions': {key: decision},
                         'decision': decision},
                        {'choice': key, 'sprint': False, 'confidence': None, 'probabilities': {}, 'model': 'test-only',
                         'usage': {}, 'latency': 0.1}, None))
            with patch('jev.time.monotonic', lambda: 101.0):
                loop.poll()
            return decision.label, notices[-1]
        k = level('level-1')
        on_stove(k, 2.9)
        listed, shown = notice(k, 'take pot p1')
        self.assertIn('锅里是糊菜', listed)
        self.assertEqual(shown, f'Jeff 选择：{LIFT} | 0.10s')
        k = level('level-1')
        k.stations['plates'].food = None
        k.chefs['jeff'].hand = plated(k, JUST_OVER)
        self.assertEqual(notice(k, 'serve')[1], f'Jeff 选择：{SERVE_LABEL} | 0.10s')
        # The extinguish option's seconds of what follows for the food in the pan.
        k = level('level-1')
        s = on_stove(k, 2.9)
        s.fire, s.fire_strength = True, 1.
        k.chefs['jeff'].hand = Food('E1', 'extinguisher')
        listed, shown = notice(k, 'extinguish p1')
        self.assertIn('随后糊菜可以装盘上菜（扣 10 元，还剩', listed)
        self.assertEqual(shown, f"Jeff 选择：{k.extinguish_label(s, follows=False)} | 0.10s")


class SecondsTests(unittest.TestCase):
    """Every seconds figure is rounded down to the tenth (servability.tenths): a step started when the seconds its label
    gives are up still leaves the dish accepted, and burnt food left on a stove for the seconds the state gives is still
    accepted; started one engine substep (0.05 s) later, past the real margin, it is refused. Rounded to the nearest
    tenth, as before, a label could give up to 0.05 s the engine does not."""

    def test_tenths_round_down_past_float_noise(self):
        self.assertEqual([servability.tenths(x) for x in (3.45, 3.49, LIMIT - 2.95 - .55, .05, 0.)],
                         [3.4, 3.4, 1.5, 0., 0.])

    def test_a_lift_started_after_its_seconds_holds_where_rounding_to_the_nearest_tenth_overstated(self):
        """Level 1, beef burnt 1.0 s, Jeff 0.51 s away: the real margin is 3.45 s; the label said 3.5 s before."""
        k = level('level-1')
        on_stove(k, 1.0)
        self.assertTrue(english(label(k, 'take pot p1').label).endswith('if this starts within 3.4 s)'))
        for wait, outcome in ((3.4, 'accepted'), (3.45, 'accepted'), (3.5, 'rejected')):
            with self.subTest(wait=wait):
                k = level('level-1')
                on_stove(k, 1.0)
                self.assertEqual(started(k, 'jeff', 'take pot p1', wait), outcome)

    def test_plating_with_under_a_tenth_left_says_only_if_it_starts_now(self):
        """Jeff holds a plate, the beef burnt 4.4 s: the real margin is 0.05 s; the label said "within 0.1 s" before."""
        def kitchen():
            k = level('level-1')
            holding_plate(k, 'jeff')
            on_stove(k, 4.4)
            return k
        plate = label(kitchen(), 'plate p1')
        self.assertEqual(plate.label, PLATE + '（糊菜：只有马上开始这一步，装出的菜才还能上菜，扣 10 元）')
        self.assertEqual(english(plate.label), PLATE_EN + ' (burnt food: accepted at -10 yuan only if this starts now)')
        self.assertEqual(started(kitchen(), 'jeff', 'plate p1', 0), 'accepted')
        self.assertEqual(started(kitchen(), 'jeff', 'plate p1', .1), 'rejected')

    def test_both_chefs_lift_and_plate_at_the_seconds_given_and_one_substep_later_is_refused(self):
        """The burnt time set so that the real margin is the label's seconds plus 0.02 s, from where each chef stands."""
        for who in ('jeff', 'human'):
            for key, kind in (('take pot p1', 'lift_pot'), ('plate p1', 'plate_pot')):
                with self.subTest(who=who, key=key):
                    def kitchen(seconds=1.):
                        k = level('level-1')
                        if kind == 'plate_pot':
                            holding_plate(k, who)
                        on_stove(k, seconds)
                        return k
                    seconds = LIMIT - kitchen().step_gain(who, 'p1', kind) - 1.22
                    self.assertTrue(english(label(kitchen(seconds), key, who).label).endswith(
                        'accepted at -10 yuan if this starts within 1.2 s)'))
                    self.assertEqual(started(kitchen(seconds), who, key, 1.2), 'accepted')
                    self.assertEqual(started(kitchen(seconds), who, key, 1.25), 'rejected')

    def test_food_left_on_the_stove_for_the_seconds_the_state_gives_is_still_accepted(self):
        """Burnt 1.03 s: 3.97 s left, "3.9 s more" (it said 4.0 s before, and after 4.0 s it is refused)."""
        for seconds, said, past in ((1.03, '3.9 s', 4.0), (1.07, '3.9 s', 3.95), (4.95, 'under 0.1 s', .1)):
            with self.subTest(seconds=seconds):
                for wait, outcome in ((float(said.split()[0]) if said[0].isdigit() else 0., 'accepted'), (past, 'rejected')):
                    k = level('level-1')
                    on_stove(k, seconds)
                    self.assertEqual(request(k)['state']['kitchen']['stations']['p1']['food']['meaning'],
                                     f'beef (burnt; accepted at -10 yuan for {said} more while on the stove)')
                    k.advance(wait)
                    self.assertEqual(k.burnt_service(k.stations['p1'].food)['outcome'], outcome)

    def test_put_then_lift_gives_the_seconds_rounded_down(self):
        flags = one_press.flags({name: True for name in one_press.NAMES})
        for seconds, note in ((1.03, '还剩 3.9 秒）'), (4.95, '还剩不到 0.1 秒）')):
            k = level('level-1')
            k.chefs['jeff'].hand = Food('L1', 'raw', ingredient='beef')
            on_stove(k, seconds)
            lift = next(a.label for a in one_press.options(k, 'jeff', k.actions('jeff'), flags) if a.key == 'put then take p1')
            self.assertTrue(lift.endswith('（锅里是糊菜：还能上菜，扣 10 元，留在灶台上' + note), lift)
            self.assertTrue(english(lift).endswith(
                'accepted at -10 yuan for %s more while on the stove)' % ('3.9 s' if seconds < 2 else 'under 0.1 s')))


class RequestTests(unittest.TestCase):
    """What Jeff reads: the state's food text, the kitchen view, plate_result, the links table and own_chain."""

    def test_the_state_names_each_burnt_food_with_its_tier(self):
        def state(k, names):
            return request(k, names=names, clear=names, english=names, plate=names)['state']
        for names, stove, pan, floor in (
                (True, 'beef (burnt; accepted at -10 yuan for 2.1 s more while on the stove)',
                 ('frying pan with beef (burnt; accepted at -10 yuan)', 'beef (burnt; accepted at -10 yuan)'),
                 'beef (burnt too long; refused)'),
                (False, 'Burnt (accepted at -10 yuan for 2.1 s more while on the stove)',
                 ('Frying pan - Burnt (accepted at -10 yuan)', 'Burnt (accepted at -10 yuan)'),
                 'Burnt (burnt too long; refused)')):
            with self.subTest(names=names):
                k = level('level-1')
                on_stove(k, 2.9)
                self.assertEqual(state(k, names)['kitchen']['stations']['p1']['food']['meaning'], stove)
                self.assertEqual(state(k, names)['servability_version'], servability.VERSION)
                pan_id, k.stations['p1'].pot_id, k.stations['p1'].food = k.stations['p1'].pot_id, None, None
                k.chefs['jeff'].hand = Food(pan_id, 'pot', contents=burnt(k, LIMIT))
                held = state(k, names)['kitchen']['chefs']['jeff']['holding']
                self.assertEqual((held['meaning'], held['contents']['meaning']), pan)
                k.chefs['jeff'].hand = None
                k.ground[pan_id] = GroundItem(Food(pan_id, 'pot', contents=burnt(k, JUST_OVER)), k.chefs['jeff'].location)
                ground = state(k, names)['kitchen']['ground']
                self.assertEqual(next(g for g in ground if g['food']['id'] == pan_id)['food']['contents']['meaning'], floor)
        k = level('level-1')
        k.chefs['jeff'].hand = plated(k, LIMIT)
        self.assertEqual(request(k)['state']['kitchen']['chefs']['jeff']['holding']['meaning'],
                         'burnt dish (accepted at -10 yuan)')

    def test_the_kitchen_view_shows_the_tier(self):
        k = level('level-1')
        on_stove(k, 2.9)
        view = request(k, parts={'view': True})['state']['kitchen']
        self.assertTrue(view['stations']['Stove 1 (p1)'].startswith(
            'frying pan P1 with beef (burnt; accepted at -10 yuan for 2.1 s more while on the stove) B1: burnt for 2.9 s'),
            view['stations']['Stove 1 (p1)'])
        run(k, 'jeff', 'take pot p1')
        held = request(k, parts={'view': True})['state']['kitchen']['chefs']['you']['holding']
        self.assertTrue(held.startswith('frying pan with beef (burnt; accepted at -10 yuan) P1 (burnt for '), held)
        # Rounded up to the tenth of a second: refused food never reads as burnt for the limit itself.
        for seconds, shown in ((LIMIT, 'beef (burnt; accepted at -10 yuan for under 0.1 s more while on the stove) B1: '
                                        'burnt for 5.0 s'),
                               # The burnt time rounded up and the seconds left rounded down: never past the limit.
                               (2.94, 'beef (burnt; accepted at -10 yuan for 2.0 s more while on the stove) B1: burnt '
                                      'for 3.0 s'),
                               (JUST_OVER, 'beef (burnt too long; refused) B1: burnt for 5.1 s'),
                               (LIMIT + .04, 'beef (burnt too long; refused) B1: burnt for 5.1 s')):
            k = level('level-1')
            on_stove(k, seconds)
            self.assertIn(shown, request(k, parts={'view': True})['state']['kitchen']['stations']['Stove 1 (p1)'])

    def test_the_kitchen_view_gives_burnt_food_in_the_air_its_tier(self):
        for seconds, name in ((LIMIT, 'burnt dish (accepted at -10 yuan)'),
                              (JUST_OVER, 'burnt dish (burnt too long; refused)')):
            k = level('level-1')
            k.stations['plates'].food = None
            k.chefs['jeff'].hand = plated(k, seconds)
            throw = next(a for a in k.actions('jeff') if a.kind == 'throw')
            k.start('jeff', throw)
            k.advance(.2)
            air = request(k, parts={'view': True})['state']['kitchen']['in_the_air']
            self.assertTrue(air[0].startswith(f'B2 {name}, thrown by you'), air)

    def test_plate_result_names_the_burnt_dish_and_its_tier(self):
        work = {'own': False, 'plate': True, 'board': False}
        for seconds, note in ((LIMIT, ' (makes a burnt Steak: order O1 accepts it at -10 yuan)'),
                              (JUST_OVER, ' (makes a burnt Steak: refused)')):
            k = level('level-1')
            k.chefs['jeff'].hand = pan_of(k, seconds)
            criteria = request(k, work=work)['questions']['next_action']['criteria']
            self.assertTrue(criteria['plate plates'].endswith(note), criteria['plate plates'])
        # Level 2 orders only burgers: a burnt steak has no order waiting, so serving it costs the wrong-dish penalty
        # on either side of the limit (and the steak is named by its id there).
        for seconds in (LIMIT, JUST_OVER):
            k = level('level-2')
            k.chefs['jeff'].hand = pan_of(k, seconds)
            self.assertTrue(request(k, work=work)['questions']['next_action']['criteria']['plate plates'].endswith(
                ' (makes a burnt steak; no waiting order asks for a steak, so serving it costs 20 yuan)'))
        # Plating from the stove: the engine's label and plate_result give the same tier, the walk counted.
        k = level('level-1')
        k.chefs['jeff'].hand, k.stations['plates'].food = k.stations['plates'].food, None
        on_stove(k, 4.5)
        self.assertEqual(request(k, work=work)['questions']['next_action']['criteria']['plate p1'],
                         'Plate food from Stove 1 onto the held clean plate (burnt food: refused, burnt too long by the '
                         'time it is plated) (makes a burnt Steak: refused)')
        # A part-made burger with burnt beef on it: the tier with a waiting order for a burger, none without one.
        k = level('level-3')
        k.stations['counter3'].food = plated(k, JUST_OVER)
        k.chefs['jeff'].hand = Food('L1', 'chopped', 2.2, ingredient='lettuce')
        text = request(k, work=work)['questions']['next_action']['criteria']['assemble counter3']
        self.assertRegex(text, r' \(the plate then still needs .* for a Burger; order O\d+ waits .*; burnt food: refused\)$')
        for order in k.orders:
            if order['status'] == 'pending':
                order['dish'] = 'steak'
        text = request(k, work=work)['questions']['next_action']['criteria']['assemble counter3']
        self.assertTrue(text.endswith('; no waiting order asks for a Burger)'), text)

    def test_after_lifting_the_follow_up_lines_say_refused_when_the_lift_ends_past_the_limit(self):
        """Burnt 4.5 s and Jeff 0.51 s from the stove: the lift says the pan is refused once lifted, and so do the links
        table's lines after it; burnt 4.45 s, the lift ends at the limit and every line says accepted."""
        k = level('level-1')
        on_stove(k, 4.5)
        payload = request(k, links=True)
        self.assertTrue(payload['questions']['next_action']['criteria']['take pot p1'].endswith(
            '(it holds burnt food: refused, burnt too long by the time it is lifted)'))
        self.assertEqual(payload['state']['option_links']['take pot p1'],
                         ['Fill the plate on Counter 1 from your frying pan (keep the empty frying pan) (burnt food: refused)',
                          'Fill the plate on Counter 2 from your frying pan (keep the empty frying pan) (burnt food: refused)'])
        k = level('level-1')
        on_stove(k, 1)
        on_stove(k, LIMIT - k.step_gain('jeff', 'p1', 'lift_pot'))
        payload = request(k, links=True)
        self.assertTrue(payload['questions']['next_action']['criteria']['take pot p1'].endswith(
            '(it holds burnt food: accepted at -10 yuan only if this starts now)'))
        self.assertTrue(all(line.endswith('(burnt food: accepted at -10 yuan)')
                            for line in payload['state']['option_links']['take pot p1']))

    def test_a_links_line_that_plates_from_the_stove_counts_the_walk_from_where_the_option_leaves_jeff(self):
        """Level 4, beef burnt 4.5 s: after taking a plate, plating from Stove 1 would end past the limit."""
        k = level('level-4')
        on_stove(k, 4.5)
        links = request(k, links=True)['state']['option_links']
        lines = [line for key, value in links.items() if key.startswith('take counter') for line in value
                 if line.startswith('Plate food from Stove 1')]
        self.assertTrue(lines)
        self.assertTrue(all(line == 'Plate food from Stove 1 (burnt food: refused, burnt too long by the time it is plated)'
                            for line in lines), lines)

    def test_own_chain_after_a_lift_says_the_dish_is_refused(self):
        """Level 4: no clean plate on Jeff's side, one on the other chef's; Jeff could hand the pan over and the other
        chef fill that plate from it. The other chef's take of the pan says its tier too."""
        k = level('level-4')
        for key in k.counters:
            if k.stations[key].food is not None and k.stations[key].food.stage == 'clean_plate':
                k.stations[key].food = None
        theirs = next(c for c in k.counters if k.reaches('human', c) and not k.reaches('jeff', c))
        k.stations[theirs].food = Food('D1', 'clean_plate')
        work = {'own': True, 'plate': False, 'board': False}
        for seconds, tier in ((2.0, 'accepted at -10 yuan'), (LIMIT - .1, 'refused')):
            on_stove(k, seconds)
            text = request(k, work=work)['questions']['next_action']['criteria']['take pot p1']
            self.assertIn(work_notes.OWN, text)
            self.assertRegex(text, r'then the other chef could: Take frying pan with beef \(burnt\) from Counter \d+ '
                                   r'\(it holds burnt food: ' + re.escape(tier) + r'\)')
            self.assertTrue(text.endswith(f'from your frying pan (keep the empty frying pan) (burnt food: {tier})'), text)

    def test_with_no_burnt_food_the_state_is_as_before(self):
        k = level('level-1')
        k.stations['p1'].food = Food('B1', 'ready', 6, 12, ingredient='beef')
        k.heat_stove(k.stations['p1'])
        payload = request(k)
        self.assertEqual(payload['state']['kitchen']['stations']['p1']['food']['meaning'], 'beef (cooked)')
        self.assertNotIn('burnt food', ' '.join(payload['questions']['next_action']['criteria'].values()))


def noodle_kitchen():
    """The noodle player level (tests/test_player_level_play.noodle_design): beef or chicken with noodles and
    scallion, two heated parts in each dish."""
    import level_calibration as lc
    from test_player_level_play import noodle_design
    design, _ = lc.normalize(noodle_design())
    return SpatialKitchen(lc.finalize(design, {'playable': True, 'target': 170}))


def part(k, item, burnt_for=None, heat=None, id=None):
    """A loose heated part: burnt for `burnt_for` s by its own burn point, or cooked (at `heat`, else its cook point)."""
    ready, burn, _ = k.rules.heat_thresholds(item)
    id = id or item[0].upper() + '1'
    if burnt_for is None:
        return Food(id, 'ready', 6, ready if heat is None else heat, ingredient=item)
    return Food(id, 'burnt', 6, burn + burnt_for, ingredient=item)


def scallion():
    return Food('S1', 'chopped', 9, 0, ingredient='scallion')


def assembled(k, *foods, plate='D9'):
    plate = Food(plate, 'clean_plate')
    for f in foods:
        plate = k.merge_plate(plate, f)
    return plate


class DishOfTwoHeatedPartsTests(unittest.TestCase):
    """A dish's burnt time is the longest of its heated parts' own burnt times (2026-11-22). Before, a dish with two
    heated parts read its most heated part's heat against the lowest burn point among them, so beef burnt 1 s with
    cooked noodles read as burnt 6 s and was refused. Levels 1-5 have one heated part per dish and are unchanged."""

    # (meat, meat burnt for, noodles burnt for, the dish's burnt time); None: cooked (noodles at heat 26, past their
    # cook point but under their burn point, the case the old formula got wrong).
    CASES = (('beef', 1.0, None, 1.0), ('beef', JUST_OVER, None, JUST_OVER), ('beef', None, .5, .5),
             ('beef', 2.0, 3.0, 3.0), ('beef', 4.0, 1.0, 4.0), ('beef', 1.0, 5.5, 5.5), ('beef', 5.5, 1.0, 5.5),
             ('chicken', 1.0, None, 1.0), ('chicken', JUST_OVER, None, JUST_OVER), ('chicken', None, .5, .5))

    def parts(self, k, meat, meat_s, noodles_s):
        return (part(k, meat, meat_s), part(k, 'noodles', noodles_s, heat=26))

    def test_a_dish_counts_each_heated_parts_own_burnt_time_in_any_order(self):
        for meat, meat_s, noodles_s, want in self.CASES:
            with self.subTest(meat=meat, meat_s=meat_s, noodles_s=noodles_s):
                k = noodle_kitchen()
                m, n = self.parts(k, meat, meat_s, noodles_s)
                for order in ((m, n, scallion()), (n, m, scallion()), (scallion(), n, m)):
                    plate = assembled(k, *order)
                    self.assertAlmostEqual(k.rules.overcook(plate, k.parts(plate)), want, places=6)
                halves = (assembled(k, m, plate='D8'), assembled(k, n, scallion()))
                for a, b in (halves, halves[::-1]):
                    merged, _ = k.merge_plates(a, b)
                    self.assertAlmostEqual(k.rules.overcook(merged, k.parts(merged)), want, places=6)

    def test_serving_takes_the_tier_of_the_longest_burnt_part(self):
        for meat, meat_s, noodles_s, want in self.CASES:
            with self.subTest(meat=meat, meat_s=meat_s, noodles_s=noodles_s):
                k = noodle_kitchen()
                plate = assembled(k, *self.parts(k, meat, meat_s, noodles_s), scallion())
                while k.waiting_order(plate) is None:
                    k.advance(.5)
                order = k.waiting_order(plate)
                k.chefs['jeff'].hand = plate
                refused = want > LIMIT
                self.assertTrue(k.serve_label(plate).endswith(
                    '这盘糊菜会被拒收，不收钱，菜没了，订单继续等待）' if refused else '这盘糊菜还能上菜，扣 10 元）'))
                money = k.money
                run(k, 'jeff', 'serve')
                event = [e for e in k.events if e.get('kind') in ('served', 'dish_rejected')][-1]
                if refused:
                    self.assertEqual((event['kind'], event['overcook_game_ms'], k.money - money, order['status']),
                                     ('dish_rejected', round(want * 1000), 0, 'pending'))
                    self.assertIsNone(k.chefs['jeff'].hand)
                else:
                    self.assertEqual((event['kind'], event['adjustment'], order['status']), ('served', -10, 'served'))
                    self.assertEqual(k.money - money, 80)

    def test_the_state_and_its_readers_agree_with_the_scoring(self):
        import request_parts
        for meat, meat_s, noodles_s, want in self.CASES:
            with self.subTest(meat=meat, meat_s=meat_s, noodles_s=noodles_s):
                k = noodle_kitchen()
                k.chefs['jeff'].hand = plate = assembled(k, *self.parts(k, meat, meat_s, noodles_s), scallion())
                held = k.snapshot()['chefs']['jeff']['holding']
                self.assertAlmostEqual(held['burnt_elapsed'], want, places=2)
                self.assertEqual(held['heat_elapsed'], round(plate.heated, 2))
                self.assertAlmostEqual(request_parts._burnt_for(held, k), k.rules.overcook(plate, k.parts(plate)),
                                       places=2)
                meaning = request(k)['state']['kitchen']['chefs']['jeff']['holding']['meaning']
                self.assertEqual(meaning, 'burnt dish (burnt too long; refused)' if want > LIMIT
                                 else 'burnt dish (accepted at -10 yuan)')

    def test_plating_from_a_stove_counts_the_seconds_from_the_food_on_the_stove(self):
        # (part on the plate, its burnt time or None for cooked, food on the stove, its burnt time)
        for frozen, frozen_s, cooking, stove_s in (('beef', 3.0, 'noodles', .5), ('noodles', 4.9, 'beef', .2),
                                                  ('beef', 5.5, 'noodles', .2), ('beef', 1.0, 'noodles', 4.0),
                                                  ('beef', None, 'noodles', 1.0)):
            for who in ('jeff', 'human'):
                with self.subTest(frozen=frozen, frozen_s=frozen_s, stove_s=stove_s, who=who):
                    def setup():
                        k = noodle_kitchen()
                        stove = next(p for p in k.pots if k.rules.heat[cooking].get('container', 'pot')
                                     == k.rules.vessels.get(k.stations[p].pot_id))
                        k.chefs[who].hand = assembled(k, part(k, frozen, frozen_s), scallion())
                        s = k.stations[stove]
                        s.food = part(k, cooking, stove_s, id='Y1')
                        k.heat_stove(s)
                        return k, stove
                    k, stove = setup()
                    gain = k.step_gain(who, stove, 'plate_pot')
                    left = min(LIMIT - stove_s - gain, LIMIT - (frozen_s or 0) - 0)
                    text = label(k, f'plate {stove}', who).label
                    if frozen_s is not None and frozen_s > LIMIT or left < -1e-9:
                        self.assertTrue(text.endswith('（糊菜：装盘时已糊太久，上菜会被拒收）'), text)
                        run(k, who, f'plate {stove}')
                        self.assertEqual(k.burnt_service(k.chefs[who].hand)['outcome'], 'rejected')
                        continue
                    left = LIMIT - stove_s - gain
                    said = servability.tenths(left)
                    if said > 0:
                        self.assertTrue(text.endswith(f'（糊菜：{said:.1f} 秒内开始这一步，装出的菜还能上菜，扣 10 元）'), text)
                        self.assertTrue(english(text).endswith(
                            f' (burnt food: accepted at -10 yuan if this starts within {said} s)'), english(text))
                    self.assertEqual(started(k, who, f'plate {stove}', said), 'accepted')
                    k, stove = setup()
                    self.assertEqual(started(k, who, f'plate {stove}', left + SUBSTEP), 'rejected')

    def test_only_a_burnt_dish_of_two_heated_parts_carries_the_figure(self):
        k = noodle_kitchen()
        k.chefs['jeff'].hand = cooked = assembled(k, part(k, 'beef'), part(k, 'noodles', heat=26), scallion())
        self.assertEqual(cooked.overcook, 0)
        self.assertNotIn('burnt_elapsed', k.snapshot()['chefs']['jeff']['holding'])
        # Level 1, a pan of beef burnt 2 s plated: one heated part, read from its heat as before.
        k = level('level-1')
        k.chefs['jeff'].hand = pan_of(k, 2.0)
        run(k, 'jeff', 'plate plates')
        k.chefs['jeff'].hand, k.stations['plates'].food = k.stations['plates'].food, None
        dish = k.chefs['jeff'].hand
        self.assertEqual((dish.stage, dish.overcook), ('burnt', 0))
        self.assertNotIn('burnt_elapsed', k.snapshot()['chefs']['jeff']['holding'])
        # Level 3, a burger with burnt beef.
        k = level('level-3')
        burger = assembled(k, burnt(k, 2.0), Food('R1', 'raw', 0, 0, ingredient='bread'),
                           Food('L1', 'chopped', 9, 0, ingredient='lettuce'), Food('T1', 'chopped', 9, 0, ingredient='tomato'))
        k.chefs['jeff'].hand = burger
        self.assertEqual((burger.stage, burger.overcook), ('burnt', 0))
        self.assertNotIn('burnt_elapsed', k.snapshot()['chefs']['jeff']['holding'])
        self.assertAlmostEqual(k.rules.overcook(burger, k.parts(burger)), 2.0, places=6)

    def test_research_records_keep_their_food_fields(self):
        import research_record
        k = noodle_kitchen()
        plate = assembled(k, part(k, 'beef', 1.0), part(k, 'noodles', heat=26), scallion())
        self.assertEqual(set(research_record.food(plate)), {'id', 'stage', 'ingredient', 'components', 'plate_id',
                                                             'chopped', 'heated', 'washed', 'contents'})


if __name__ == '__main__':
    unittest.main()
