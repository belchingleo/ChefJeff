import json
from pathlib import Path
import tempfile
import unittest
from map_definition import build_map, load_map, save_map, validate_map, geometry
from spatial_kitchen import SpatialKitchen
from kitchen import load_config


class MapDocumentTests(unittest.TestCase):
    @staticmethod
    def _footprint_fixture():
        width = height = 7
        walls = [[x, y] for x in range(width) for y in range(height)
                 if x in (0, width - 1) or y in (0, height - 1)]
        return {
            'schema_version': 1, 'id': 'fixture', 'revision': 1,
            'size': [width, height], 'walls': walls,
            'equipment': [
                {'id': 'counter1', 'cell': [3, 3], 'cells': [[3, 3], [3, 4]],
                 'access': [2, 3], 'facing': 'west'}
            ],
            'presentation': {'theme': 'courtyard', 'corner_caps': [], 'decorations': []}
        }

    def test_accepts_contiguous_footprint_including_anchor_cell(self):
        doc = self._footprint_fixture()
        checked = validate_map(doc)
        equipment, _ = geometry(checked)
        self.assertEqual(equipment['counter1']['cells'], ((3, 3), (3, 4)))

    def test_rejects_duplicate_discontinuous_and_overlapping_footprints(self):
        doc = self._footprint_fixture()
        doc['equipment'][0]['cells'] = [[3, 3], [3, 3]]
        with self.assertRaises(ValueError):
            validate_map(doc)

        doc = self._footprint_fixture()
        doc['equipment'][0]['cells'] = [[3, 3], [3, 5]]
        with self.assertRaises(ValueError):
            validate_map(doc)

        doc = self._footprint_fixture()
        doc['equipment'][0]['cells'] = [[3, 3], [3, 4], [4, 4]]
        doc['equipment'].append({'id': 'b2', 'cell': [4, 4], 'access': [4, 3], 'facing': 'south'})
        with self.assertRaises(ValueError):
            validate_map(doc)

    def test_rejects_size_bounds_and_non_integer_dimensions(self):
        for size in ([4, 9], [14, 65], [14.0, 9], [True, 9], [14], [14, 9, 1]):
            with self.subTest(size=size):
                doc = load_map(1)
                doc['size'] = size
                with self.assertRaises(ValueError):
                    validate_map(doc)

    def test_rejects_out_of_bounds_and_non_integer_coordinates(self):
        for cell in ([-1, 2], [14, 2], [2, 9], [2.0, 2], [True, 2], [2]):
            with self.subTest(cell=cell):
                doc = load_map(1)
                doc['equipment'][0]['cell'] = cell
                with self.assertRaises(ValueError):
                    validate_map(doc)

    def test_rejects_disconnected_walkable_regions(self):
        doc = load_map(1)
        width, height = 5, 5
        doc['size'] = [width, height]
        doc['walls'] = [[x, y] for x in range(width) for y in range(height)
                        if x in (0, width - 1) or y in (0, height - 1)]
        # A complete internal wall divides the open floor into two regions.
        doc['walls'].extend([[2, y] for y in range(1, height - 1)])
        doc['equipment'] = []
        doc['presentation'] = {'theme': 'courtyard', 'corner_caps': [], 'decorations': []}
        with self.assertRaises(ValueError):
            validate_map(doc)

    def test_rejects_duplicate_station_ids(self):
        doc = load_map(1)
        doc['equipment'][1]['id'] = doc['equipment'][0]['id']
        with self.assertRaises(ValueError):
            validate_map(doc)

    def test_station_views_are_visual_only_and_legacy_documents_remain_valid(self):
        doc = load_map(1)
        before = geometry(doc)
        equipment_ids = {station['id'] for station in doc['equipment']}
        station_views = doc['presentation']['station_views']
        self.assertEqual(set(station_views), equipment_ids)

        boards = [station for station in doc['equipment'] if station['id'] in ('b1', 'b2', 'b3')]
        self.assertEqual({station_views[station['id']]['run_axis'] for station in boards}, {'vertical'})
        self.assertEqual({station_views[station['id']]['device_axis'] for station in boards}, {'vertical'})
        self.assertGreater(len({station['facing'] for station in boards}), 1)

        # A rendering-axis change must not leak into the simulation geometry.
        doc['presentation']['station_views']['b2']['device_axis'] = 'horizontal'
        self.assertEqual(geometry(validate_map(doc)), before)

        legacy = load_map(1)
        legacy['presentation'].pop('station_views')
        self.assertNotIn('station_views', validate_map(legacy)['presentation'])
        self.assertEqual(geometry(legacy), before)

    def test_station_views_reject_unknown_ids_and_invalid_axes(self):
        doc = load_map(1)
        doc['presentation']['station_views']['not-a-station'] = {
            'run_axis': 'horizontal', 'device_axis': 'vertical'
        }
        with self.assertRaises(ValueError):
            validate_map(doc)

        for axis_name in ('run_axis', 'device_axis'):
            doc = load_map(1)
            doc['presentation']['station_views']['b1'][axis_name] = 'diagonal'
            with self.assertRaises(ValueError):
                validate_map(doc)

    def test_authored_station_views_follow_each_level_axis_layout(self):
        for level in (1, 2, 3):
            doc = load_map(level)
            views = doc['presentation']['station_views']
            self.assertEqual(set(views), {station['id'] for station in doc['equipment']})
            self.assertEqual(doc['revision'], 4)
            for station in doc['equipment']:
                axis = views[station['id']]['run_axis']
                x, y = station['cell']
                if level == 1:
                    if station['id'] in {'b1', 'b2', 'b3'} or (x == 12 and y not in (1, 7)):
                        self.assertEqual(axis, 'vertical', station['id'])
                    if y in (1, 7):
                        self.assertEqual(axis, 'horizontal', station['id'])
                elif level == 2:
                    if y in (1, 7) or (y == 4 and x not in (1, 12)):
                        self.assertEqual(axis, 'horizontal', station['id'])
                    if x in (1, 12) and y not in (1, 7):
                        self.assertEqual(axis, 'vertical', station['id'])
                else:
                    if y in (1, 7):
                        self.assertEqual(axis, 'horizontal', station['id'])
                    if x in (1, 6, 8, 12) and y not in (1, 7):
                        self.assertEqual(axis, 'vertical', station['id'])

    def test_corner_counters_are_operable_without_changing_walkable_floor(self):
        for level in (1, 2, 3):
            doc = load_map(level)
            corners = [station for station in doc['equipment'] if station.get('reach') == 'corner']
            self.assertTrue(corners)
            size = doc['size']

            def walkable(document):
                occupied = {tuple(p) for p in document['walls']}
                occupied.update(tuple(e['cell']) for e in document['equipment'])
                return {(x, y) for x in range(size[0]) for y in range(size[1])} - occupied

            before = walkable(doc)
            without_corner_stations = json.loads(json.dumps(doc))
            without_corner_stations['equipment'] = [
                station for station in without_corner_stations['equipment']
                if station.get('reach') != 'corner'
            ]
            without_corner_stations['walls'].extend(station['cell'] for station in corners)
            self.assertEqual(before, walkable(without_corner_stations))

            kitchen = SpatialKitchen({**load_config(), 'level': level, 'spawn_seed': 0})
            for station in corners:
                route = kitchen.path(next(iter(kitchen.chefs)), station['id'])
                self.assertTrue(route)
                self.assertEqual(tuple(station['access']), route[-1])

    def test_rejects_corner_diagonal_access_through_wall(self):
        doc = load_map(1)
        corner = next(e for e in doc['equipment'] if e.get('reach') == 'corner')
        # This diagonal target is a wall cell, so it cannot serve as a reachable approach.
        corner['access'] = [11, 0]
        with self.assertRaises(ValueError):
            validate_map(doc)

    def test_round_trip_preserves_geometry_and_independent_decor(self):
        for level in (1,2,3):
            doc = load_map(level)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/'map.json'
                save_map(doc,path)
                self.assertEqual(doc,json.loads(path.read_text()))
            k = SpatialKitchen({**load_config(),'level':level,'spawn_seed':0})
            equipment,walls = geometry(doc)
            self.assertEqual(k.equipment,equipment)
            self.assertEqual(k.walls,walls)
            for who in k.chefs:
                for station in equipment:self.assertTrue(k.path(who,station))
            changed = load_map(level)
            changed['presentation']['decorations'] = []
            self.assertEqual(geometry(validate_map(changed)),geometry(doc))

    def test_reject_overlap_invalid_access_and_asset_path(self):
        for mutate in (
            lambda d:d['equipment'][1].update(cell=d['equipment'][0]['cell']),
            lambda d:d['equipment'][0].update(access=[0,0]),
            lambda d:d['presentation']['decorations'][0].update(asset='../../private'),
            lambda d:d.update(schema_version=999),
        ):
            doc=load_map(1);mutate(doc)
            with self.assertRaises(ValueError):validate_map(doc)

    def test_bad_save_does_not_replace_valid_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'map.json';save_map(load_map(1),path)
            before=path.read_bytes();doc=load_map(1);doc['walls']=[]
            with self.assertRaises(ValueError):save_map(doc,path)
            self.assertEqual(before,path.read_bytes())


class BuildMapTests(unittest.TestCase):
    def test_coordinates_and_facing_make_a_valid_map(self):
        # A run along the top wall with a boxed-in corner, a vertical island and a fridge.
        doc = build_map('island', [8, 6], [('ctl', 1, 1, 'south'), ('fridge', 2, 1, 'south'), ('c1', 1, 2, 'east'),
                                           ('c2', 4, 2, 'west'), ('b1', 4, 3, 'east'),
                                           {'id': 'shelf', 'cell': [6, 4], 'facing': 'west', 'type': 'bin', 'name': '回收'}])
        self.assertEqual(validate_map(doc), doc)
        self.assertTrue(all(tuple(p) in map(tuple, doc['walls']) for p in [[0, 0], [7, 5], [3, 0], [0, 3]]))
        e = {s['id']: s for s in doc['equipment']}
        self.assertEqual((e['ctl']['reach'], e['ctl']['access']), ('corner', [2, 2]))
        self.assertEqual([e[k]['access'] for k in ('fridge', 'c1', 'c2', 'b1')], [[2, 2], [2, 2], [3, 2], [5, 3]])
        self.assertEqual({k: v['type'] for k, v in e.items()},
                         {'ctl': 'counter', 'fridge': 'ingredient_source', 'c1': 'counter', 'c2': 'counter', 'b1': 'board', 'shelf': 'bin'})
        self.assertEqual((e['fridge']['params'], e['shelf']['name'], e['c2']['name']), ({'item': 'beef'}, '回收', 'c2'))
        self.assertEqual(doc['floor_areas'], {'axis': 'x', 'split': 4, 'below': 'prep', 'at_or_above': 'cook'})
        self.assertEqual([e[k]['area'] for k in ('fridge', 'c2', 'shelf')], ['prep', 'cook', 'cook'])
        # Areas split across the longer side.
        tall = build_map('tall', [6, 9], [('c1', 1, 1, 'south'), ('c2', 1, 7, 'north')])
        self.assertEqual((tall['floor_areas']['axis'], tall['floor_areas']['split']), ('y', 4))
        self.assertEqual([s['area'] for s in tall['equipment']], ['prep', 'cook'])

    def test_a_station_facing_a_wall_is_named(self):
        with self.assertRaisesRegex(ValueError, 'fridge faces north'):
            build_map('bad', [6, 6], [('fridge', 2, 1, 'north')])
        # Only a counter boxed in by counters may be reached diagonally.
        with self.assertRaisesRegex(ValueError, 'b1 faces'):
            build_map('bad', [6, 6], [('b1', 1, 1, 'south'), ('c1', 1, 2, 'east'), ('c2', 2, 1, 'south')])
