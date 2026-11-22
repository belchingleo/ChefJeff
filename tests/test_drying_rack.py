"""The sink and its drying rack, as Overcooked 2's washing station: dirty plates stack in the sink and stay there until
washed (first in, washed first); each washed plate goes onto the rack beside it, the newest on top; taking from the
rack takes the top plate; Space at the sink with empty hands takes a clean plate from the rack (HandlePickupReferral),
and a chef at the sink, either chef, takes it where it stands; from anywhere else the take walks to the rack.
Every official level has one rack, beside its sink."""
import math
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

    def rack_plate(self, k):
        """One of the kitchen's own clean plates, not one in the sink, moved onto the empty rack."""
        key, plate = next((key, p) for key, p in self.plates(k) if p.stage == 'clean_plate' and key != k.dryer)
        k.stations[key].food = None
        k.stations[k.dryer].food = plate
        return plate

    def go_rack_walks(self, k, who):
        """On a fork: the walk to the rack listed for a chef at the sink walks there, round the sink or beside it, as
        any walk does (the take alone is done at the sink): travel, a route of more than one point, a new position and
        the rack as the chef's location."""
        k = k.fork()
        go = next((a for a in k.actions(who) if a.key == f'go {k.dryer}'), None)
        self.assertIsNotNone(go)
        self.assertEqual(go.kind, 'go')
        here = k.positions[who]
        self.assertTrue(k.start(who, go)[0])
        self.assertGreater(k.chefs[who].job.travel, 0)
        self.assertGreater(len(k.routes[who]['points']), 1)
        for _ in range(200):
            k.advance(.05)
            if not k.chefs[who].job:
                break
        self.assertIsNone(k.chefs[who].job)
        self.assertGreater(math.dist(k.positions[who], here), .5)
        self.assertEqual(k.chefs[who].location, k.dryer)
        k.assert_invariants()

    def take(self, k, who):
        return next(a for a in k.actions(who) if a.kind == 'take_plate' and a.target == k.dryer)

    def test_space_at_the_sink_takes_the_rack_plate_where_the_chef_stands(self):
        """Level 4's notch west of the sink: Space aiming right at the sink takes the rack's plate there, as the page
        sends it (aim, the highlighted station, then the action), with no walk round the sink and still facing it."""
        for start in ((4.15, 7.0), (4.0, 7.3)):
            with self.subTest(start=start):
                k = self.kitchen(4)
                plate = self.rack_plate(k)
                k.chefs['human'].hand = None
                k.positions['human'] = start
                self.assertTrue(k.face('human', 1., 0.))
                facing, aim = k.facing['human'], k.aim['human']
                target, action = k.facing_interaction('human', 'hands', station=k.sink)
                self.assertEqual((target, action.kind, action.target), (k.sink, 'take_plate', k.dryer))
                self.assertTrue(k.pick_station('human', target))
                self.assertEqual(k.path('human', action.target, kind=action.kind), [start])
                # Only the take: a walk to the rack from here still goes round the sink.
                self.assertGreater(len(k.path('human', action.target)), 1)
                self.assertTrue(k.start('human', action)[0])
                self.assertEqual(k.routes['human']['points'], [start])
                self.assertEqual(k.chefs['human'].job.travel, 0)
                k.advance(.05)
                self.assertEqual(k.positions['human'], start)
                self.assertIsNone(k.chefs['human'].job)
                self.assertEqual(k.chefs['human'].hand.id, plate.id)
                self.assertEqual(k.chefs['human'].hand.stage, 'clean_plate')
                self.assertEqual(k.facing['human'], facing)
                self.assertEqual(k.selected_station('human'), k.sink)
                # The chef is still at the sink, and Jeff's request says so (not at the rack).
                self.assertEqual(k.chefs['human'].location, k.sink)
                self.assertEqual(k.snapshot()['chefs']['human']['location'], k.sink)
                k.assert_invariants()

    def test_jeff_at_the_sink_takes_the_rack_plate_where_he_stands(self):
        """Jeff, walked to the sink by putting a dirty plate in it, takes the rack's plate there: travel 0, still facing
        the sink. Turned away from it first, he stands at its face all the same and turns back to the sink, never to
        the rack. Level 4 puts Jeff on the side away from the sink; level 5 is that kitchen with the chefs swapped.
        Only the take is done at the sink: his walk to the rack walks there, with the rack empty (the dirty plate just
        put in, or the rack's only plate just taken) and with a plate on it."""
        for level, turned in ((1, False), (2, False), (3, False), (5, False), (1, True), (2, True), (3, True), (5, True)):
            with self.subTest(level=level, turned_away=turned):
                k = self.kitchen(level)
                (key, dirty_plate), = self.plates(k)[:1]
                k.stations[key].food = None
                dirty_plate.stage = 'dirty_plate'
                k.chefs['jeff'].hand = dirty_plate
                put = next(a for a in k.actions('jeff') if a.kind == 'put_sink')
                self.assertTrue(k.start('jeff', put)[0])
                for _ in range(200):
                    k.advance(.05)
                    if not k.chefs['jeff'].job:
                        break
                self.assertIsNone(k.chefs['jeff'].hand)
                self.assertIsNone(k.stations[k.dryer].food)
                self.go_rack_walks(k, 'jeff')
                plate = self.rack_plate(k)
                self.go_rack_walks(k, 'jeff')
                here, facing, aim = k.positions['jeff'], k.facing['jeff'], k.aim['jeff']
                self.assertEqual(k.selected_station('jeff'), k.sink)
                if turned:
                    k._face_vector('jeff', -aim[0], -aim[1])
                    self.assertNotEqual(k.facing['jeff'], facing)
                self.assertTrue(k.rack_at_sink('jeff', k.dryer))
                self.assertTrue(k.start('jeff', self.take(k, 'jeff'))[0])
                self.assertEqual(k.chefs['jeff'].job.travel, 0)
                self.assertEqual(k.routes['jeff']['points'], [here])
                k.advance(.05)
                self.assertIsNone(k.chefs['jeff'].job)
                self.assertEqual(k.chefs['jeff'].hand.id, plate.id)
                self.assertEqual(k.chefs['jeff'].hand.stage, 'clean_plate')
                self.assertEqual((k.positions['jeff'], k.facing['jeff'], k.aim['jeff']), (here, facing, aim))
                # He is still at the sink: no walk to the sink he stands at among his actions, and the rack is a walk.
                self.assertEqual(k.chefs['jeff'].location, k.sink)
                self.assertNotIn(f'go {k.sink}', {a.key for a in k.actions('jeff')})
                self.assertIsNone(k.stations[k.dryer].food)
                self.go_rack_walks(k, 'jeff')
                k.assert_invariants()

    def test_jeff_away_from_the_sink_walks_to_the_rack(self):
        for level in (1, 2, 3, 5):
            with self.subTest(level=level):
                k = self.kitchen(level)
                plate = self.rack_plate(k)
                start = k.positions['jeff']
                self.assertFalse(k.rack_at_sink('jeff', k.dryer))
                self.assertTrue(k.start('jeff', self.take(k, 'jeff'))[0])
                route = k.routes['jeff']['points']
                self.assertGreater(k.chefs['jeff'].job.travel, 0)
                self.assertGreater(len(route), 1)
                for _ in range(200):
                    k.advance(.05)
                    if not k.chefs['jeff'].job:
                        break
                self.assertEqual(k.chefs['jeff'].hand.id, plate.id)
                self.assertNotEqual(k.positions['jeff'], start)
                self.assertLess(math.dist(k.positions['jeff'], route[-1]), 1e-6)
                self.assertIn(k.dryer, k.selectable_stations('jeff'))
                k.assert_invariants()


if __name__ == '__main__':
    unittest.main()
