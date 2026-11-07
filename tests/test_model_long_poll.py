"""The page's model requests by long poll (GET /api/model/request?wait=1): prompt, lock-free and slot-free waiting."""
import http.client
import json
import tempfile
import threading
import time
import unittest
import uuid

import hosted_server
from hosted_server import BrowserRelay, make_server
from kitchen import load_config


class RelayWaitTests(unittest.TestCase):
    def setUp(self):
        self.relay = BrowserRelay(load_config())

    def ask_later(self, delay=.1):
        def ask():
            time.sleep(delay)
            try:
                self.relay.ask({'state': {'rules': {}}, 'questions': {}})
            except RuntimeError:            # nobody answers: the relay closes at cleanup
                pass
        thread = threading.Thread(target=ask, daemon=True)
        thread.start()
        self.addCleanup(self.relay.close)
        return thread

    def test_a_new_request_answers_a_waiting_poll_within_50_ms(self):
        self.ask_later(.2)
        started = time.monotonic()
        got = self.relay.wait_request(5)
        waited = time.monotonic() - started
        self.assertIsNotNone(got)
        self.assertLess(waited - .2, .05)

    def test_nothing_comes_by_the_timeout(self):
        started = time.monotonic()
        self.assertIsNone(self.relay.wait_request(.3))
        self.assertGreaterEqual(time.monotonic() - started, .29)

    def test_close_cancel_and_a_finished_round_answer_at_once(self):
        for name in ('close', 'cancel'):
            relay = BrowserRelay(load_config())
            threading.Timer(.1, getattr(relay, name)).start()
            started = time.monotonic()
            self.assertIsNone(relay.wait_request(5))
            self.assertLess(time.monotonic() - started, .2)
        running = [True]
        threading.Timer(.1, lambda: running.clear()).start()
        started = time.monotonic()
        self.assertIsNone(BrowserRelay(load_config()).wait_request(5, lambda: bool(running)))
        self.assertLess(time.monotonic() - started, .45)        # checked every quarter second

    def test_a_long_polled_request_carries_the_compact_parts_when_that_trial_is_on(self):
        from unittest.mock import patch
        import features
        on = {key: dict(value) for key, value in features.current().items()}
        on['compact_input']['on'] = True
        self.ask_later(0)
        with patch.object(features, 'current', lambda: {key: dict(value) for key, value in on.items()}):
            got = self.relay.wait_request(2)
        self.assertEqual(got['wire']['version'], 'compact-v1')

    def test_a_request_already_waiting_is_answered_without_waiting(self):
        self.ask_later(0)
        time.sleep(.05)
        started = time.monotonic()
        self.assertIsNotNone(self.relay.wait_request(5))
        self.assertLess(time.monotonic() - started, .05)


class LongPollHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_server(0, 'http://127.0.0.1', data_dir=self.tmp.name)
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        self.server.public_origin = self.origin
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup)
        self.hold = hosted_server.LONG_POLL_SECONDS
        hosted_server.LONG_POLL_SECONDS = 1.5
        self.addCleanup(lambda: setattr(hosted_server, 'LONG_POLL_SECONDS', self.hold))

    def cleanup(self):
        self.server.shutdown()
        self.server.sessions.close()
        self.server.server_close()
        self.thread.join(2)
        self.tmp.cleanup()

    def call(self, method, path, body=None, token=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        headers = {'Origin': self.origin, 'Content-Type': 'application/json'}
        if token:
            headers['X-ChefJeff-Session'] = token
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        raw, status = response.read(), response.status
        conn.close()
        return status, json.loads(raw)

    def running_session(self):
        """A page session with a round running through its browser relay."""
        status, data = self.call('POST', '/api/session', {})
        self.assertEqual(status, 201)
        token = data['session']
        game = self.server.sessions.get(token)
        game.stop_event.set()               # no background ticking: the test drives the kitchen
        game.wake.set()
        command = lambda path, **b: self.call('POST', '/api/' + path, {'game_id': game.game_id, 'request_id': uuid.uuid4().hex, **b}, token)
        self.assertEqual(command('browser-ready', connected=True)[0], 200)
        game.stop_event.clear()
        self.assertEqual(command('start')[0], 200)
        game.stop_event.set()
        game.wake.set()
        game.stop_event.clear()
        with game.lock:
            self.assertEqual(game.phase, 'running')
        return token, game

    def test_a_request_reaches_a_waiting_page_at_once_and_state_answers_meanwhile(self):
        token, game = self.running_session()
        answer = {}
        poll = threading.Thread(target=lambda: answer.update(zip(('status', 'data', 't'),
                                (*self.call('GET', '/api/model/request?wait=1', token=token), time.monotonic()))))
        poll.start()
        time.sleep(.2)
        started = time.monotonic()
        self.assertEqual(self.call('GET', '/api/state', token=token)[0], 200)     # the poll does not hold game.lock
        self.assertLess(time.monotonic() - started, .5)
        asked = time.monotonic()
        def ask():
            try:
                game.relay.ask({'questions': {'next_action': {'criteria': {'wait': 'Wait'}}}})
            except RuntimeError:            # cancelled below, unanswered
                pass
        threading.Thread(target=ask, daemon=True).start()
        poll.join(3)
        self.assertEqual(answer['status'], 200)
        self.assertIsNotNone(answer['data']['request'])
        self.assertLess(answer['t'] - asked, .2)
        self.assertTrue(game.relay_long_poll)
        game.relay.cancel()

    def test_without_wait_the_answer_comes_at_once_as_before(self):
        token, _ = self.running_session()
        started = time.monotonic()
        self.assertEqual(self.call('GET', '/api/model/request', token=token), (200, {'request': None}))
        self.assertLess(time.monotonic() - started, .3)

    def test_one_poll_per_page_and_an_empty_answer_by_the_hold(self):
        token, _ = self.running_session()
        first = threading.Thread(target=lambda: self.call('GET', '/api/model/request?wait=1', token=token))
        first.start()
        time.sleep(.2)
        started = time.monotonic()
        self.assertEqual(self.call('GET', '/api/model/request?wait=1', token=token), (200, {'request': None}))
        self.assertLess(time.monotonic() - started, .3)                     # the second one does not wait
        first.join(3)
        held = self.server.metrics.snapshot()
        self.assertGreaterEqual(held['model_long_polls'].get('empty', 0), 1)
        self.assertLess(held['recent_latency_ms']['p99'] or 0, 1000)        # the held time is not counted as latency

    def test_waiting_polls_leave_the_shared_slots_to_state(self):
        polls = []
        for _ in range(3):
            token, _ = self.running_session()
            polls.append(threading.Thread(target=lambda t=token: self.call('GET', '/api/model/request?wait=1', token=t)))
        for poll in polls:
            poll.start()
        time.sleep(.3)                       # every poll is waiting
        token = self.running_session()[0]
        results = []
        states = [threading.Thread(target=lambda: results.append(self.call('GET', '/api/state', token=token)[0]))
                  for _ in range(32)]
        for thread in states:
            thread.start()
        for thread in states + polls:
            thread.join(5)
        self.assertEqual(results.count(200), 32, results)


if __name__ == '__main__':
    unittest.main()
