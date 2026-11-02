"""A calibrated player level is played like a listed one; Jeff reads its dishes only as English components."""
from http.server import ThreadingHTTPServer
import http.client
import json
import tempfile
import threading
import time
import unittest

import config_contract as cc
from hosted_server import make_server
from jev import compose_payload
import level_calibration as lc
from level_calibration import DISPLAY_NAMES
from player_level_fakes import quick
from player_level_queue import CalibrationQueue
import reference_policy
from spatial_kitchen import SpatialKitchen
from test_level_calibration import restock
from web_server import GameSession, Handler
from whitebox_server import SpatialJevClient

NAMES = {'beef_noodles': '红烧牛肉面！', 'chicken_noodles': '鸡丝面'}


def noodle_design():
    design = restock({'lettuce': 'noodles', 'tomato': 'scallion', 'bread': 'chicken'},
                     ['beef_noodles', 'chicken_noodles'], {'P2': 'pot'})
    for dish, name in NAMES.items():
        design['recipe_catalog']['recipes'][dish]['name'] = name
    return design


class JeffInputTests(unittest.TestCase):
    def test_jeff_reads_neutral_ids_and_english_components_never_the_players_names(self):
        level, _ = lc.normalize(noodle_design())
        self.assertEqual(level['recipe_catalog']['extensions'][DISPLAY_NAMES], {'dish_1': '红烧牛肉面！', 'dish_2': '鸡丝面'})
        self.assertEqual(level['recipe_catalog']['recipes']['dish_1']['name'], 'cooked noodles + cooked beef + chopped scallion')
        k = SpatialKitchen(lc.finalize(level, {'playable': True, 'target': 170}))
        client = SpatialJevClient(k.c, key='test')
        roles = {'human': 'assembler', 'jeff': 'cook'}
        seen = 0
        for step in range(3600):
            if step % 10 == 0:
                for who, role in roles.items():
                    action = reference_policy.choose(k, who, role)
                    if action:
                        k.start(who, action)
            if step % 300 == 0:
                text = json.dumps(compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None), ensure_ascii=False)
                self.assertTrue(text.isascii(), [ch for ch in text if not ch.isascii()][:10])
                self.assertNotIn('鸡丝面', text)
                self.assertIn('cooked noodles + cooked chicken + chopped scallion', text)
                seen += 1
            k.advance(.05)
        self.assertGreater(k.served, 0)
        self.assertEqual(seen, 12)


def wait(call, job, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, view = call('GET', '/api/player-level/status?job=' + job)
        if view.get('state') in ('done', 'failed'):
            return view
        time.sleep(.05)
    raise AssertionError('the calibration did not finish')


class LocalPlayTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.game = GameSession(kitchen_factory=SpatialKitchen)
        self.server.player_levels = CalibrationQueue(calibrate=quick)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.player_levels.close)
        self.addCleanup(self.server.shutdown)
        self.requests = 0

    def call(self, method, path, body=None):
        port = self.server.server_port
        headers = {'Host': f'127.0.0.1:{port}', **({'Content-Type': 'application/json'} if body is not None else {})}
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        try:
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def command(self, path, body):
        self.requests += 1
        state = self.call('GET', '/api/state')[1]
        return self.call('POST', path, {**body, 'game_id': state['game_id'], 'request_id': f'r{self.requests}'})

    def test_play_a_calibrated_level_then_return_to_a_listed_one(self):
        self.assertEqual(self.command('/api/player-level/play', {'job': 'none'})[0], 404)
        status, reply = self.call('POST', '/api/player-level/submit', {'level': noodle_design()})
        self.assertEqual(status, 202)
        self.assertEqual(wait(self.call, reply['job'])['state'], 'done')
        status, _ = self.command('/api/player-level/play', {'job': reply['job']})
        self.assertEqual(status, 200)
        state = self.call('GET', '/api/state')[1]
        # The page shows the player's names, and the official noodle dishes' pictures for the same components.
        self.assertEqual(state['player_level'], {'id': reply['content_id'], 'names': {'dish_1': '红烧牛肉面！', 'dish_2': '鸡丝面'},
                                                 'looks': {'dish_1': 'beef_noodles', 'dish_2': 'chicken_noodles'},
                                                 'target': 150, 'solo_reaches_target': False})
        self.assertEqual(state['kitchen']['goal_status']['target_money'], 150)
        self.assertEqual(state['kitchen']['level'], None)
        self.assertEqual([d['id'] for d in state['kitchen']['menu']], ['dish_1', 'dish_2'])
        self.assertEqual(self.server.game.k.resolved['level']['id'], reply['content_id'])
        self.command('/api/reset', {})
        self.assertEqual(self.server.game.k.resolved['level']['id'], reply['content_id'])  # a restart keeps the level
        self.assertEqual(self.command('/api/level', {'level': 1})[0], 200)
        state = self.call('GET', '/api/state')[1]
        self.assertIsNone(state['player_level'])
        self.assertEqual(self.server.game.k.resolved['level']['id'], 'level-1')


class HostedPlayTests(unittest.TestCase):
    def test_a_session_plays_only_its_own_calibrated_level(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        server = make_server(0, 'https://chefjeff.online', data_dir=directory.name, player_levels=True)
        server.player_levels.close()
        server.player_levels = CalibrationQueue(calibrate=quick)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.sessions.close)
        self.addCleanup(server.shutdown)

        def call(method, path, body=None, token=None):
            headers = {'Host': 'chefjeff.online', **({'X-ChefJeff-Session': token} if token else {})}
            if body is not None:
                headers.update({'Content-Type': 'application/json', 'Origin': 'https://chefjeff.online'})
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            try:
                connection.request(method, path, json.dumps(body) if body is not None else None, headers)
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        mine, other = (call('POST', '/api/session', {})[1]['session'] for _ in range(2))
        status, reply = call('POST', '/api/player-level/submit', {'level': noodle_design()}, mine)
        self.assertEqual(wait(lambda m, p: call(m, p, token=mine), reply['job'])['state'], 'done')
        game_id = server.sessions.get(other).game_id
        play = {'job': reply['job'], 'game_id': game_id, 'request_id': 'p1'}
        self.assertEqual(call('POST', '/api/player-level/play', play, other)[0], 404)
        play['game_id'] = server.sessions.get(mine).game_id
        self.assertEqual(call('POST', '/api/player-level/play', play, mine)[0], 200)
        state = call('GET', '/api/state', token=mine)[1]
        self.assertEqual(state['player_level']['id'], reply['content_id'])
        self.assertEqual(server.sessions.get(mine).k.resolved['level']['id'], reply['content_id'])


if __name__ == '__main__':
    unittest.main()
