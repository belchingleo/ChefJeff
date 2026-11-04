"""Cached routes must not carry another call's number types into a later round."""
import math
import unittest
from kitchen import load_config
from levels import level_config
import spatial_kitchen
from spatial_kitchen import SpatialKitchen


def kitchen():
    return SpatialKitchen(level_config(load_config(), 'level-2'))


class RouteCacheTests(unittest.TestCase):
    def setUp(self):
        spatial_kitchen._map_navigation.cache_clear()
        self.addCleanup(spatial_kitchen._map_navigation.cache_clear)

    def test_a_later_round_routes_from_its_own_spawn_point(self):
        goal = (6.0, 1.95)
        first = kitchen()
        first.nav.shortest_path((6.0, 2.0), goal)       # a chef standing on that spot in an earlier round
        second = kitchen()
        self.assertIs(second.nav, first.nav)            # kitchens on one map share the navigation
        spawn = second.positions['human']
        self.assertEqual(spawn, (6, 2))
        route = second.nav.shortest_path(spawn, goal)
        self.assertEqual([tuple(type(v) for v in p) for p in route], [(int, int), (float, float)])

    def test_both_ends_are_the_callers_points_and_the_route_is_unchanged(self):
        nav = kitchen().nav
        start = (6, 5)
        # The first floor cell whose route from the start has to turn around equipment.
        end = next(c for c in sorted(nav.floor) if nav.walkable_point(c) and len(nav.shortest_path(start, c)) > 2)
        nav._cached_shortest_path.cache_clear()
        floats = nav.shortest_path((6.0, 5.0), tuple(float(v) for v in end))
        ints = nav.shortest_path(start, end)
        self.assertGreater(len(ints), 2)                # a route around equipment, with corners
        self.assertEqual((ints[0], ints[-1]), (start, end))
        self.assertIs(type(ints[0][0]), int)
        self.assertEqual(ints, floats)                  # equal values, corners shared
        self.assertEqual(sum(math.dist(a, b) for a, b in zip(ints, ints[1:])),
                         sum(math.dist(a, b) for a, b in zip(floats, floats[1:])))

    def test_standing_still_returns_the_callers_start(self):
        nav = kitchen().nav
        nav.shortest_path((6.0, 5.0), (6.0, 5.0))
        self.assertEqual([tuple(type(v) for v in p) for p in nav.shortest_path((6, 5), (6, 5))], [(int, int)])


if __name__ == '__main__':
    unittest.main()
