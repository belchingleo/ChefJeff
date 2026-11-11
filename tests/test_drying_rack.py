"""The sink and its drying rack, as Overcooked 2's washing station: dirty plates stack in the sink and stay there until
washed (first in, washed first); each washed plate goes onto the rack beside it, the newest on top; taking from the
rack takes the top plate; Space at the sink with empty hands takes a clean plate from the rack (HandlePickupReferral).
Every official level has one rack, beside its sink."""
import unittest

from kitchen import Food, load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen


def dirty(i):
    f = Food(f'X{i}')
    f.stage = 'dirty_plate'
    return f


class DryingRackTests(unittest.TestCase):
    def kitchen(self, level=2):
        k = SpatialKitchen(level_config(load_config(), level))
        # Take every plate out of play but two dirty ones the test hands around (the plate count must hold).
        return k

    def plates(self, k):
        """The kitchen's own plate objects, made dirty and moved into the human's reach one at a time."""
        ids = [f'D{i}' for i in range(1, k.plate_count + 1)]
        found = {}
        for key, s in k.stations.items():
            if s.food and s.food.id in ids:
                found[s.food.id] = (key, s.food)
        return [found[i] for i in ids if i in found]

    def finish(self, k, who, action):
        k.positions[who] = k.path(who, action.target)[-1]
        self.assertTrue(k.start(who, action)[0], action.key)
        for _ in range(80):
            k.advance(.05)
            if not k.chefs[who].job:
                break
        k.assert_invariants()

    def test_every_level_has_one_rack_beside_its_sink(self):
        for level in (1, 2, 3, 4):
            k = SpatialKitchen(level_config(load_config(), level))
            sx, sy = k.equipment['sink']['cell']
            rx, ry = k.equipment[k.dryer]['cell']
            self.assertEqual(abs(sx - rx) + abs(sy - ry), 1, level)

    def test_dirty_plates_stack_wash_in_order_and_dry_on_the_rack(self):
        k = self.kitchen()
        (k1, p1), (k2, p2) = self.plates(k)[:2]
        for key, plate in ((k1, p1), (k2, p2)):
            plate.stage = 'dirty_plate'
            k.stations[key].food = None
            k.chefs['human'].hand = plate
            put = next(a for a in k.actions('human') if a.kind == 'put_sink')
            self.finish(k, 'human', put)
        sink = k.stations[k.sink]
        self.assertEqual((sink.food.id, [f.id for f in sink.stack]), (p1.id, [p2.id]))
        # No way back out for a dirty plate.
        self.assertFalse([a for a in k.actions('human') if a.target == k.sink and a.kind.startswith('take')])
        for expected_rack in ([p1.id], [p2.id, p1.id]):
            wash = next(a for a in k.actions('human') if a.kind == 'wash')
            self.finish(k, 'human', wash)
            rack = k.stations[k.dryer]
            self.assertEqual([rack.food.id] + [f.id for f in reversed(rack.stack)], expected_rack)
        self.assertIsNone(sink.food)
        take = next(a for a in k.actions('human') if a.kind == 'take_plate' and a.target == k.dryer)
        self.finish(k, 'human', take)
        self.assertEqual(k.chefs['human'].hand.id, p2.id)
        self.assertEqual(k.stations[k.dryer].food.id, p1.id)

    def test_space_at_the_sink_with_empty_hands_takes_from_the_rack(self):
        k = self.kitchen()
        (key, plate), = self.plates(k)[:1]
        k.stations[key].food = None
        k.stations[k.dryer].food = plate
        k.chefs['human'].hand = None
        sx, sy = k.equipment['sink']['cell']
        ax, ay = k.equipment['sink']['access']
        k.positions['human'] = (float(ax), float(ay))
        k.facing['human'] = {(1, 0): 'right', (-1, 0): 'left', (0, 1): 'down', (0, -1): 'up'}[(sx - ax, sy - ay)]
        target, action = k.facing_interaction('human')
        self.assertEqual((action.kind, action.target), ('take_plate', k.dryer))

    def test_jeff_has_the_same_rack_actions(self):
        k = self.kitchen()
        (key, plate), = self.plates(k)[:1]
        k.stations[key].food = None
        k.stations[k.dryer].food = plate
        k.chefs['jeff'].hand = None
        self.assertTrue([a for a in k.actions('jeff') if a.kind == 'take_plate' and a.target == k.dryer])


if __name__ == '__main__':
    unittest.main()
