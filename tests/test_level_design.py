"""The editor's design becomes a level bundle: map, starting inventory and recipes, checked in one place."""
from http.server import ThreadingHTTPServer
import copy
import http.client
import json
import threading
import time
import unittest

import config_contract as cc
import level_calibration as lc
import level_design
from player_level_fakes import quick
from player_level_queue import CalibrationQueue
from spatial_kitchen import SpatialKitchen
from web_server import GameSession, Handler

DESIGN = {
    'format': level_design.FORMAT, 'name': '拌面小馆', 'size': [14, 9], 'walls': [[9, 4]],
    'stations': [
        {'type': 'ingredient_source', 'x': 2, 'y': 1, 'item': 'beef'}, {'type': 'ingredient_source', 'x': 3, 'y': 1, 'item': 'noodles'},
        {'type': 'ingredient_source', 'x': 4, 'y': 1, 'item': 'scallion'}, {'type': 'ingredient_source', 'x': 5, 'y': 1, 'item': 'chicken'},
        {'type': 'counter', 'x': 7, 'y': 1}, {'type': 'counter', 'x': 8, 'y': 1}, {'type': 'counter', 'x': 9, 'y': 1},
        {'type': 'serving_window', 'x': 11, 'y': 0},
        {'type': 'board', 'x': 1, 'y': 3}, {'type': 'board', 'x': 1, 'y': 4}, {'type': 'counter', 'x': 1, 'y': 5},
        {'type': 'stove', 'x': 12, 'y': 3, 'vessel': 'pan'}, {'type': 'stove', 'x': 12, 'y': 4, 'vessel': 'pot'},
        {'type': 'counter', 'x': 12, 'y': 5}, {'type': 'counter', 'x': 6, 'y': 4}, {'type': 'counter', 'x': 7, 'y': 4},
        {'type': 'sink', 'x': 3, 'y': 7}, {'type': 'plate_return', 'x': 4, 'y': 8}, {'type': 'counter', 'x': 6, 'y': 7},
        {'type': 'counter', 'x': 7, 'y': 7}, {'type': 'bin', 'x': 9, 'y': 7}, {'type': 'tool_rack', 'x': 10, 'y': 7}],
    'dishes': [{'name': '红烧牛肉面', 'price': 90, 'items': ['noodles', 'beef', 'scallion']},
               {'name': '鸡丝面', 'price': 90, 'items': ['noodles', 'chicken', 'scallion']}],
}


def design(**change):
    return {**copy.deepcopy(DESIGN), **change}


def codes(found):
    return [d['code'] for d in found]


class BuildTests(unittest.TestCase):
    def test_a_design_becomes_a_level_that_freezes_and_plays(self):
        level, problems = level_design.bundle(design())
        self.assertEqual(problems, [])
        stations = {e['id']: e for e in level['map']['equipment']}
        self.assertLessEqual({'serve', 'sink', 'returns', 'extinguisher', 'bin', 'b1', 'b2', 'p1', 'p2', 'fridge', 'noodles'}, set(stations))
        self.assertEqual(stations['fridge']['params'], {'item': 'beef'})
        self.assertEqual(stations['b1']['facing'], 'east')  # towards the free floor
        self.assertIn([9, 4], level['map']['walls'])
        self.assertEqual(level['level']['initial_inventory'], [
            {'object': 'extinguisher', 'id': 'E1', 'at_type': 'tool_rack'},
            {'object': 'plate', 'id': 'D1', 'state': 'clean', 'at_type': 'counter'},
            {'object': 'plate', 'id': 'D2', 'state': 'clean', 'at_type': 'counter'},
            {'object': 'plate', 'id': 'D3', 'state': 'clean', 'at_type': 'counter'},
            {'object': 'pan', 'id': 'P1', 'at': 'p1'}, {'object': 'pot', 'id': 'P2', 'at': 'p2'}])
        k = SpatialKitchen(lc.finalize(level, {'playable': True, 'target': 100}))
        snapshot = k.snapshot()
        self.assertEqual([d['id'] for d in snapshot['menu']], ['dish_1', 'dish_2'])
        self.assertEqual(snapshot['stations']['p2']['vessel'], 'pot')
        self.assertNotEqual(k.positions['human'][0] < 7, k.positions['jeff'][0] < 7)  # one chef on each side

    def test_the_rules_the_editor_shows_are_enforced_here_too(self):
        stations = DESIGN['stations']
        cases = {
            'WALLS_SPLIT_KITCHEN': design(walls=[[x, 2] for x in range(1, 13)]),
            'UNSUPPORTED_EQUIPMENT_COUNT': design(stations=stations + [{'type': 'sink', 'x': 9, 'y': 5}]),
            'INVENTORY_NO_FREE_STATION': design(stations=[s for s in stations if s['type'] != 'counter'] + [{'type': 'counter', 'x': 7, 'y': 1}]),
            'STATION_UNREACHABLE': design(stations=stations + [{'type': 'counter', 'x': 1, 'y': 2}, {'type': 'counter', 'x': 2, 'y': 3}]),
        }
        for code, case in cases.items():
            with self.subTest(code=code):
                self.assertIn(code, codes(level_design.bundle(case)[1]))
        serving = [{'type': 'serving_window', 'x': 10, 'y': 0}, {'type': 'serving_window', 'x': 12, 'y': 0}]
        self.assertEqual(level_design.bundle(design(stations=stations + serving[:1]))[1], [])
        self.assertIn('UNSUPPORTED_EQUIPMENT_COUNT', codes(level_design.bundle(design(stations=stations + serving))[1]))
        self.assertEqual(codes(level_design.bundle(design(size=[20, 20]))[1]), ['DESIGN_INVALID'])
        self.assertEqual(codes(level_design.bundle({**DESIGN, 'format': 'other'})[1]), ['DESIGN_INVALID'])
        five = [{'name': str(n), 'price': 50, 'items': ['beef']} for n in range(5)]
        self.assertIn('DESIGN_INVALID', codes(level_design.bundle(design(dishes=five))[1]))

    def test_stations_may_be_set_into_the_outer_wall(self):
        stations = DESIGN['stations']
        level, problems = level_design.bundle(design(stations=stations + [{'type': 'counter', 'x': 6, 'y': 0}]))
        self.assertEqual(problems, [])
        e = {s['id']: s for s in level['map']['equipment']}
        self.assertEqual((e['serve']['cell'], e['serve']['facing'], e['serve']['access']), ([11, 0], 'south', [11, 1]))
        self.assertEqual((e['returns']['cell'], e['returns']['facing'], e['returns']['access']), ([4, 8], 'north', [4, 7]))
        self.assertNotIn([6, 0], level['map']['walls'])
        # Food leaves and dirty plates come back through the wall, so those two must be set into it.
        moved = lambda kind, x, y: [dict(s, x=x, y=y) if s['type'] == kind else s for s in stations]
        self.assertIn('STATION_NOT_IN_WALL', codes(level_design.bundle(design(stations=moved('serving_window', 11, 1)))[1]))
        self.assertIn('STATION_NOT_IN_WALL', codes(level_design.bundle(design(stations=moved('plate_return', 4, 7)))[1]))
        # Not in a corner, which faces no floor; walls themselves go inside the room.
        self.assertIn('DESIGN_INVALID', codes(level_design.bundle(design(stations=stations + [{'type': 'counter', 'x': 0, 'y': 0}]))[1]))
        self.assertIn('DESIGN_INVALID', codes(level_design.bundle(design(walls=[[5, 0]]))[1]))
        # A station in the wall is reached only from the cell in front of it.
        self.assertIn('STATION_UNREACHABLE', codes(level_design.bundle(design(stations=stations + [{'type': 'bin', 'x': 0, 'y': 3}]))[1]))


class SubmitTests(unittest.TestCase):
    def test_the_local_page_submits_a_design(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.game = GameSession(kitchen_factory=SpatialKitchen)
        server.player_levels = CalibrationQueue(calibrate=quick)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.player_levels.close)
        self.addCleanup(server.shutdown)

        def call(method, path, body=None):
            port = server.server_port
            headers = {'Host': f'127.0.0.1:{port}', **({'Content-Type': 'application/json'} if body is not None else {})}
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
            try:
                connection.request(method, path, json.dumps(body) if body is not None else None, headers)
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        status, refused = call('POST', '/api/player-level/submit', {'design': design(walls=[[x, 2] for x in range(1, 13)])})
        self.assertEqual((status, refused['state']), (400, 'refused'))
        self.assertIn('WALLS_SPLIT_KITCHEN', [d['code'] for d in refused['diagnostics']])
        status, reply = call('POST', '/api/player-level/submit', {'design': design()})
        self.assertEqual(status, 202)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            view = call('GET', '/api/player-level/status?job=' + reply['job'])[1]
            if view['state'] == 'done':
                break
            time.sleep(.05)
        self.assertEqual(view['report']['target'], 150)
        self.assertEqual(call('POST', '/api/player-level/submit', {'design': design(), 'level': {}})[0], 400)


if __name__ == '__main__':
    unittest.main()
