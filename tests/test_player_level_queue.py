"""Players' levels calibrate one at a time in their own process, behind a bounded queue, on both servers."""
import http.client
import json
import tempfile
import threading
import time
import unittest

from hosted_server import make_server
from player_level_fakes import broken, pooled, quick, slow
from player_level_queue import CalibrationQueue
from test_level_calibration import restock


def wait(queue, owner, job, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, view = queue.status(owner, job)
        if view.get('state') in ('done', 'failed'):
            return view
        time.sleep(.05)
    raise AssertionError('the calibration did not finish')


class QueueTests(unittest.TestCase):
    def queue(self, **options):
        queue = CalibrationQueue(**options)
        self.addCleanup(queue.close)
        return queue

    def test_a_design_that_cannot_run_is_refused_without_queueing(self):
        bad = restock({}, ['steak'])
        bad['recipe_catalog']['recipes']['steak']['price'] = 155
        status, reply = self.queue(calibrate=quick).submit('a', bad)
        self.assertEqual((status, reply['state']), (400, 'refused'))
        self.assertEqual([d['code'] for d in reply['diagnostics']], ['PRICE_OUT_OF_RANGE'])

    def test_report_reaches_its_owner_only_and_the_same_design_is_answered_from_memory(self):
        queue = self.queue(calibrate=quick)
        status, reply = queue.submit('a', restock({}, ['steak']))
        self.assertEqual((status, reply['state'], reply['position']), (202, 'queued', 1))
        view = wait(queue, 'a', reply['job'])
        self.assertEqual(view['report'], {'playable': True, 'target': 150, 'pacing': {'interval_game_ms': 30000},
                                          'pair_median': 300, 'solo_median': 100, 'solo_reaches_target': False,
                                          'seeds': [1, 2, 3, 4, 5, 6, 7], 'diagnostics': []})
        self.assertEqual(queue.status('b', reply['job'])[0], 404)
        level, report = queue.result('a', reply['job'])
        self.assertEqual(level['level']['id'], reply['content_id'])
        self.assertIsNone(queue.result('b', reply['job']))
        status, again = queue.submit('b', restock({}, ['steak']))
        self.assertEqual((status, again['state'], again['content_id']), (200, 'done', reply['content_id']))

    def test_a_calibration_may_run_its_own_pool_of_processes(self):
        queue = self.queue(calibrate=pooled, workers=2)
        view = wait(queue, 'a', queue.submit('a', restock({}, ['steak']))[1]['job'])
        self.assertEqual(view['state'], 'done')

    def test_one_job_per_owner_and_a_bounded_queue(self):
        queue = self.queue(calibrate=slow, max_waiting=1)
        self.assertEqual(queue.submit('a', restock({}, ['steak']))[0], 202)
        deadline = time.monotonic() + 10
        while queue.process is None and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertEqual(queue.submit('a', restock({}, ['burger']))[0], 409)
        status, waiting = queue.submit('b', restock({}, ['burger']))
        self.assertEqual((status, waiting['position']), (202, 2))
        self.assertEqual(queue.submit('c', restock({}, ['steak', 'burger']))[0], 503)

    def test_a_job_running_too_long_or_failing_stops_alone(self):
        queue = self.queue(calibrate=slow, timeout=1)
        view = wait(queue, 'a', queue.submit('a', restock({}, ['steak']))[1]['job'])
        self.assertEqual(view, {**view, 'state': 'failed', 'error': '校准超时，请简化关卡后再试。'})
        queue = self.queue(calibrate=broken)
        view = wait(queue, 'a', queue.submit('a', restock({}, ['steak']))[1]['job'])
        self.assertEqual(view['error'], '校准出错，请稍后再试。')


class HostedEndpointTests(unittest.TestCase):
    def serve(self, **options):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        server = make_server(0, 'https://chefjeff.online', data_dir=directory.name, **options)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.sessions.close)
        self.addCleanup(server.shutdown)
        return server

    def request(self, server, path, body=None, token=None):
        headers = {'Host': 'chefjeff.online', **({'X-ChefJeff-Session': token} if token else {})}
        if body is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': 'https://chefjeff.online'})
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            connection.request('GET' if body is None else 'POST', path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_off_unless_the_server_is_started_with_player_levels(self):
        server = self.serve()
        token = self.request(server, '/api/session', {})[1]['session']
        self.assertEqual(self.request(server, '/api/player-level/submit', {'level': restock({}, ['steak'])}, token)[0], 404)
        self.assertEqual(self.request(server, '/api/player-level/status?job=x', token=token)[0], 404)

    def test_submit_a_level_larger_than_any_command_and_poll_its_report(self):
        server = self.serve(player_levels=True)
        server.player_levels.close()
        server.player_levels = CalibrationQueue(calibrate=quick)
        token = self.request(server, '/api/session', {})[1]['session']
        other = self.request(server, '/api/session', {})[1]['session']
        design = restock({}, ['steak'])
        self.assertGreater(len(json.dumps({'level': design})), 8192)
        status, reply = self.request(server, '/api/player-level/submit', {'level': design}, token)
        self.assertEqual(status, 202)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            status, view = self.request(server, '/api/player-level/status?job=' + reply['job'], token=token)
            if view['state'] == 'done':
                break
            time.sleep(.05)
        self.assertEqual((status, view['report']['target']), (200, 150))
        self.assertEqual(self.request(server, '/api/player-level/status?job=' + reply['job'], token=other)[0], 404)
        self.assertEqual(self.request(server, '/api/player-level/submit', {'level': design, 'extra': 1}, token)[0], 400)


if __name__ == '__main__':
    unittest.main()
