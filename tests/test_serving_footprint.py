from copy import deepcopy
import unittest
from unittest.mock import patch

from kitchen import Food, load_config
from map_definition import load_map
from spatial_kitchen import SpatialKitchen


class ServingFootprintTests(unittest.TestCase):
    def make(self, level):
        config = load_config()
        config.update(level=level, spawn_seed=0, round_seconds=500, order_patience=450)
        return SpatialKitchen(config)

    def serving_sides(self, kitchen):
        serve_cells = kitchen.equipment['serve'].get('cells', (kitchen.equipment['serve']['cell'],))
        return {
            cell: [side for side in kitchen.nav.neighbors(cell)
                   if side not in serve_cells]
            for cell in serve_cells
        }

    def test_authored_serve_footprints_and_snapshot(self):
        for level, facing in ((1, 'west'), (2, 'east'), (3, 'west')):
            with self.subTest(level=level):
                kitchen = self.make(level)
                serve = kitchen.equipment['serve']
                cells = serve.get('cells', (serve['cell'],))
                self.assertEqual(len(cells), 1)
                self.assertIn(tuple(serve['cell']), cells)
                self.assertEqual(serve['facing'], facing)
                self.assertTrue(all(cell in kitchen.nav.blocked for cell in cells))
                self.assertEqual(kitchen.snapshot()['map']['equipment']['serve']['cell'], serve['cell'])
                for route in (kitchen.path('human', 'serve'), kitchen.path('jeff', 'serve')):
                    self.assertTrue(route)
                    self.assertTrue(all(kitchen.nav.clear_walk_line(a, b)
                                        for a, b in zip(route, route[1:])))
                    self.assertTrue(all(tuple(point) not in kitchen.nav.blocked for point in route))

        level_two = self.make(2)
        self.assertEqual(level_two.equipment['returns']['cell'], (1, 5))

    def _assert_serve_from_each_side(self, kitchen, level):
        sides = self.serving_sides(kitchen)
        self.assertTrue(all(sides.values()))
        for serve_cell, cells in sides.items():
            for side in cells:
                for who in ('human', 'jeff'):
                    with self.subTest(level=level, serve_cell=serve_cell, side=side, who=who):
                        kitchen = self.make(level)
                        kitchen.positions[who] = side
                        route = kitchen.path(who, 'serve')
                        self.assertEqual(route[-1], kitchen.operation_point('serve',side))
                        self.assertTrue(all(kitchen.nav.clear_walk_line(a, b)
                                            for a, b in zip(route, route[1:])))

                        dx, dy = serve_cell[0] - side[0], serve_cell[1] - side[1]
                        kitchen.facing[who] = {
                            (0, -1): 'up', (0, 1): 'down', (-1, 0): 'left', (1, 0): 'right'
                        }[(dx, dy)]
                        self.assertEqual(kitchen.interaction_target(who), 'serve')

                        chef = kitchen.chefs[who]
                        chef.location = f'floor_{side[0]}_{side[1]}'
                        chef.hand = Food('test-plate', 'ready', 6, 12,
                                         plate_id='plate', components=('beef',))
                        kitchen.orders[0].update(status='pending', dish='steak', deadline=450)
                        ok, message = kitchen.command(who, 'serve')
                        self.assertTrue(ok, message)
                        job = chef.job
                        kitchen.advance(job.travel + job.work + .001)
                        self.assertEqual(kitchen.served, 1)

    def test_single_cell_authored_serve_is_usable_from_every_side(self):
        for level in (1, 2, 3):
            self._assert_serve_from_each_side(self.make(level), level)

    def test_synthetic_two_cell_serve_uses_removed_counter_footprint(self):
        # Work from a copy: counter5 supplies the extra cell and must be removed
        # before that cell becomes part of the serving station footprint.
        document = deepcopy(load_map(1))
        serve = next(e for e in document['equipment'] if e['id'] == 'serve')
        placeholder = next(e for e in document['equipment'] if e['id'] == 'counter5')
        document['equipment'].remove(placeholder)
        serve['cells'] = [placeholder['cell'], serve['cell']]

        with patch('spatial_kitchen.load_map', return_value=document):
            kitchen = self.make(1)
            serve_geometry = kitchen.equipment['serve']
            self.assertEqual(len(serve_geometry['cells']), 2)
            self.assertIn(serve_geometry['cell'], serve_geometry['cells'])
            self.assertTrue(all(cell in kitchen.nav.blocked for cell in serve_geometry['cells']))
            self.assertEqual(kitchen.snapshot()['map']['equipment']['serve']['cells'],
                             serve_geometry['cells'])
            self._assert_serve_from_each_side(kitchen, 1)


if __name__ == '__main__':
    unittest.main()
