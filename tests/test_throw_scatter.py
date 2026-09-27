import unittest

from kitchen import Food, GroundItem, load_config
from spatial_kitchen import SpatialKitchen, neighbors, tile_key


class ThrowScatterTests(unittest.TestCase):
    def make(self, human=(5., 4.), jev=(6., 5.)):
        k = SpatialKitchen(load_config() | {'spawn_seed': 0})
        k.positions.update(human=human, jev=jev)
        k.chefs['human'].location = tile_key(k.anchor('human'))
        k.chefs['jev'].location = tile_key(k.anchor('jev'))
        k.chefs['human'].hand = Food('human-food', 'chopped')
        k.chefs['jev'].hand = Food('jev-food', 'raw')
        return k

    def throw_toward(self, k, who, point):
        action = k.throw_action(who, point)
        self.assertIsNotNone(action)
        self.assertTrue(k.start(who, action)[0])
        return action

    def make_level_corner(self, level, corner, human_has_food=False):
        k = SpatialKitchen(load_config() | {'spawn_seed': 0, 'level': level})
        access = k.equipment[corner]['access']
        k.positions.update(human=tuple(map(float, access)), jev=tuple(map(float, access)))
        k.chefs['human'].location = tile_key(access)
        k.chefs['jev'].location = tile_key(access)
        k.chefs['jev'].hand = Food('jev-food', 'raw')
        k.chefs['human'].hand = Food('human-food', 'chopped') if human_has_food else None
        return k

    @staticmethod
    def take_action(k, who, counter):
        return next(a for a in k.actions(who)
                    if a.kind == 'take_counter' and a.target == counter)

    def test_same_direction_short_interval_reserves_separate_landings_and_both_pick_up(self):
        k = self.make()
        shared = (6, 4)
        human_food = k.chefs['human'].hand
        jev_food = k.chefs['jev'].hand

        first = self.throw_toward(k, 'jev', shared)
        k.advance(.05)  # First throw has reserved its landing during windup.
        self.assertEqual(k.drop_locks.get(first.target), 'jev')
        second = self.throw_toward(k, 'human', shared)
        self.assertNotEqual(first.target, second.target)
        k.advance(1.2)

        locations = {item.food.id: item.location for item in k.ground.values()}
        self.assertEqual(set(locations), {'human-food', 'jev-food'})
        self.assertEqual(len(set(locations.values())), 2)
        self.assertEqual(k.cell(locations['jev-food']), shared)
        self.assertIn(k.cell(locations['human-food']), neighbors(shared))
        self.assertFalse(k.projectiles)
        k.assert_invariants()

        for item_id, food in [('human-food', human_food), ('jev-food', jev_food)]:
            picker = 'human' if item_id == 'human-food' else 'jev'
            self.assertTrue(k.command(picker, f'pickup {item_id}')[0])
            job = k.chefs[picker].job
            k.advance(job.travel + job.work + .01)
            self.assertIs(k.chefs[picker].hand, food)
            k.assert_invariants()

    def test_opposing_short_interval_throws_do_not_share_reserved_tile(self):
        k = self.make(human=(8., 4.), jev=(5., 4.))
        shared = (6, 4)
        first = self.throw_toward(k, 'jev', shared)
        k.advance(.05)
        second = self.throw_toward(k, 'human', shared)
        self.assertNotEqual(first.target, second.target)
        k.advance(1.2)

        self.assertEqual(set(k.ground), {'human-food', 'jev-food'})
        cells = [k.cell(item.location) for item in k.ground.values()]
        self.assertEqual(len(set(cells)), 2)
        self.assertIn(shared, cells)
        self.assertTrue(any(cell in neighbors(shared) for cell in cells))
        k.assert_invariants()

    def test_full_local_area_rejects_later_throw_and_conserves_food(self):
        k = self.make(human=(4., 6.), jev=(6., 5.))
        target = (5, 4)
        # Occupy every legal adjacent landing while leaving the requested tile free.
        for i, cell in enumerate([*neighbors(target)]):
            food = Food(f'blocker-food-{i}')
            k.ground[food.id] = GroundItem(food, tile_key(cell))
        first = self.throw_toward(k, 'jev', target)
        self.assertEqual(first.target, tile_key(target))
        k.advance(.05)
        # Every adjacent cell is occupied (including the first projectile only if
        # its target is among them), so a second throw toward the shared tile fails.
        second = k.throw_action('human', target)
        self.assertIsNone(second)
        self.assertIsNotNone(k.chefs['human'].hand)
        k.advance(1.)
        self.assertEqual(k.chefs['human'].hand.id, 'human-food')
        self.assertIn('jev-food', k.ground)
        self.assertEqual(len(k.ground), len(neighbors(target)) + 1)
        k.assert_invariants()

    def test_throw_clips_at_wall_and_does_not_land_beyond_it(self):
        k = self.make(human=(4., 6.), jev=(6., 2.))
        food = k.chefs['jev'].hand
        action = self.throw_toward(k, 'jev', (9, 2))
        k.advance(1.)
        self.assertIsNone(k.chefs['jev'].hand)
        self.assertEqual(k.ground[food.id].location, action.target)
        landing = k.cell(k.ground[food.id].location)
        self.assertLessEqual(landing[0], 6)
        self.assertFalse(k.clear_throw_line((6., 2.), (8., 2.)))
        k.assert_invariants()

    def test_every_maps_corner_counter_accepts_throw_and_normal_take_uses_corner_access(self):
        for level in (1, 2, 3):
            with self.subTest(level=level):
                k = SpatialKitchen(load_config() | {'spawn_seed': 0, 'level': level})
                corners = [key for key, station in k.equipment.items()
                           if station.get('reach') == 'corner']
                self.assertTrue(corners)
                for corner in corners:
                    with self.subTest(corner=corner):
                        k = self.make_level_corner(level, corner)
                        access = k.equipment[corner]['access']
                        self.assertEqual(k.path('human', corner), [access])
                        food = k.chefs['jev'].hand
                        action = self.throw_toward(k, 'jev', k.equipment[corner]['cell'])
                        self.assertEqual(action.target, corner)
                        k.advance(1.)
                        self.assertIs(k.stations[corner].food, food)
                        self.assertTrue(k.command('human', f'take {corner}')[0])
                        job = k.chefs['human'].job
                        self.assertEqual(k.path('human', corner), [access])
                        k.advance(job.travel + job.work + .01)
                        self.assertIs(k.chefs['human'].hand, food)
                        self.assertIsNone(k.stations[corner].food)
                        k.assert_invariants()

    def test_in_flight_corner_throw_blocks_put_counter(self):
        k = self.make_level_corner(1, 'counter_corner1', human_has_food=True)
        action = self.throw_toward(k, 'jev', k.equipment['counter_corner1']['cell'])
        k.advance(.05)
        self.assertEqual(k.drop_locks.get('counter_corner1'), 'jev')
        self.assertFalse(k.command('human', 'put counter_corner1')[0])
        k.advance(1.)
        self.assertEqual(k.stations['counter_corner1'].food.id, 'jev-food')
        self.assertEqual(k.chefs['human'].hand.id, 'human-food')
        k.assert_invariants()

    def test_competing_corner_counter_throw_keeps_one_item_on_counter_and_spills_one_to_floor(self):
        k = self.make_level_corner(1, 'counter_corner1', human_has_food=True)
        cell = k.equipment['counter_corner1']['cell']
        spare = Food('jev-spare', 'raw')
        k.ground[spare.id] = GroundItem(spare, tile_key((10, 2)))
        first_food = k.chefs['jev'].hand
        first = self.throw_toward(k, 'jev', cell)
        self.assertEqual(first.target, 'counter_corner1')
        k.advance(.4)
        self.assertIs(k.stations['counter_corner1'].food, first_food)
        second = self.throw_toward(k, 'human', cell)
        self.assertIn(second.target, k.floor_places)
        self.assertTrue(k.command('jev', f'pickup {spare.id}')[0])
        k.advance(.5)

        self.assertEqual(k.stations['counter_corner1'].food.id, 'jev-food')
        self.assertEqual(set(k.ground), {'human-food'})
        self.assertIn(k.ground['human-food'].location, k.floor_places)
        self.assertIs(k.chefs['jev'].hand, spare)
        self.assertFalse(k.projectiles)
        k.assert_invariants()


if __name__ == '__main__':
    unittest.main()
