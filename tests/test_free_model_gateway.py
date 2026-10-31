"""Synthetic two-region coordination, durable aggregate budgets and loopback RPC only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from free_model_budget import CallBudget, BudgetError
from free_model_gateway import FreeCoordinator, GatewayError, GatewayServer, PREFIX
from free_model_client import FreeGatewayClient, RegionalFreeModels
from hosted_free_models import FreeModels, FreeCallError
from hosted_jev import TEST_PAYLOAD
from hosted_server import HostedSession, BrowserRelay, make_server
from shared_client import SharedClient

KEYS = {'zhipu': 'synthetic-zhipu-key-not-real', 'startlux': 'synthetic-bamboo-key-not-real'}
SITES = {'cn': 'c'*43, 'global': 'g'*43}
ANSWER = {'choice': 'wait', 'sprint': False, 'usage': {'input_tokens': 3, 'output_tokens': 0}}


class BudgetTests(unittest.TestCase):
    def test_attempt_is_durable_and_crash_blocks_reuse_without_resetting_budget(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'private'
            budget = CallBudget(path, clock=lambda: 1000)
            budget.begin('zhipu'); budget.close()
            second = CallBudget(path, clock=lambda: 1001)
            self.addCleanup(second.close)
            with self.assertRaises(BudgetError) as result:
                second.begin('zhipu')
            self.assertEqual(result.exception.code, 'upstream_blocked')
            self.assertEqual(len(second.value['attempts']), 1)
            second.acknowledge_idle('zhipu')
            self.assertEqual(second.available('zhipu'), 'upstream_cooldown')
            self.assertEqual(len(second.value['attempts']), 1)
            self.assertEqual((path/'budget.json').stat().st_mode & 0o777, 0o600)
            self.assertFalse(any(secret in (path/'budget.json').read_text() for secret in KEYS.values()))

    def test_one_owner_and_corrupt_or_public_state_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            budget = CallBudget(d)
            with self.assertRaises(ValueError): CallBudget(d)
            budget.close()
            path = Path(d)/'budget.json'
            path.chmod(0o644)
            with self.assertRaises(ValueError): CallBudget(d)
            path.chmod(0o600); path.write_text('{"bad":true}')
            with self.assertRaises(ValueError): CallBudget(d)

    def test_both_regions_share_minute_hour_day_budgets_and_restarts_preserve_counts(self):
        clock = [10000.0]
        with tempfile.TemporaryDirectory() as d:
            b = CallBudget(d, clock=lambda: clock[0], minute=1, hour=2, day=3)
            b.begin('zhipu'); b.finish('zhipu')
            self.assertEqual(b.available('zhipu'), 'call_budget')
            b.begin('startlux'); b.finish('startlux')
            self.assertEqual(b.available('startlux'), 'call_budget')
            b.close(); clock[0] += 3601
            b = CallBudget(d, clock=lambda: clock[0], minute=1, hour=2, day=3)
            self.addCleanup(b.close)
            b.begin('zhipu'); b.finish('zhipu')
            self.assertEqual(b.available('startlux'), 'call_budget')
            clock[0] += 86401
            self.assertIsNone(b.available('zhipu'))

    def test_timeout_stays_blocked_across_restart(self):
        with tempfile.TemporaryDirectory() as d:
            b = CallBudget(d); b.begin('startlux'); b.finish('startlux', 'transport_uncertain'); b.close()
            b = CallBudget(d); self.addCleanup(b.close)
            self.assertEqual(b.available('startlux'), 'upstream_blocked')


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.clock = [1000.0]
        self.sender = FreeModels(KEYS, verified=True)
        self.calls = []
        def send(provider, payload):
            self.calls.append((provider, deepcopy(payload))); return deepcopy(ANSWER)
        self.sender.send = send
        self.coordinator = FreeCoordinator(self.sender, clock=lambda: self.clock[0])

    def reserve(self, site='cn', provider='zhipu', owner='o'*24, round_ref='r'*24, **extra):
        return self.coordinator.reserve(site, {'provider': provider, 'owner': owner, 'round': round_ref, **extra})

    def decide(self, lease, site='cn', ident='synthetic-task'):
        return self.coordinator.decide(site, {'lease': lease['lease'], 'id': ident, 'payload': deepcopy(TEST_PAYLOAD)})

    def test_two_regions_race_for_the_same_one_global_seat(self):
        def reserve(site):
            try: return self.reserve(site=site, owner=site*16)
            except GatewayError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, ('cn', 'global')))
        self.assertEqual(sum(isinstance(x, dict) for x in results), 1)
        self.assertEqual(results.count('seat_busy'), 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.coordinator.catalog()['global_capacity']['zhipu']['used'], 1)
        self.assertEqual(self.reserve(provider='startlux', owner='s'*24)['ttl'], 45)

    def test_reservation_deduplication_site_ownership_and_secret_free_catalog(self):
        one = self.reserve()
        self.assertEqual(self.reserve(), one)
        with self.assertRaises(GatewayError): self.decide(one, site='global')
        with self.assertRaises(GatewayError): self.coordinator.release('global', {'lease': one['lease']})
        catalog = json.dumps(self.coordinator.catalog())
        for secret in (*KEYS.values(), one['lease'], 'o'*24, 'r'*24): self.assertNotIn(secret, catalog)
        first = self.decide(one)
        self.assertEqual(self.decide(one), first)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.coordinator.budget.value['attempts']), 1)

    def test_expired_or_released_inflight_seat_cannot_be_reassigned(self):
        one = self.reserve(); entered = threading.Event(); release = threading.Event()
        def slow(*_args): entered.set(); release.wait(2); return deepcopy(ANSWER)
        self.sender.send = slow
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.decide, one)
            try:
                self.assertTrue(entered.wait(1)); self.clock[0] += 46
                self.coordinator.release('cn', {'lease': one['lease']})
                with self.assertRaises(GatewayError): self.reserve(site='global', owner='g'*24)
                self.assertEqual(self.coordinator.catalog()['global_capacity']['zhipu']['used'], 1)
            finally: release.set()
            with self.assertRaises(GatewayError): future.result(timeout=1)
        self.assertTrue(self.reserve(site='global', owner='g'*24)['lease'])

    def test_released_round_resume_keeps_its_attempt_budget(self):
        one = self.reserve(); self.decide(one)
        self.coordinator.release('cn', {'lease': one['lease']})
        two = self.reserve()
        self.assertNotEqual(one['lease'], two['lease'])
        self.decide(two, ident='second-task')
        self.assertEqual(list(self.coordinator.round_calls.values()), [2])
        self.coordinator.round_calls[('cn', 'o'*24, 'r'*24)] = 200
        with self.assertRaises(GatewayError) as error: self.decide(two, ident='third-task')
        self.assertEqual(error.exception.code, 'round_budget')
        self.assertEqual(len(self.calls), 2)

    def test_wrong_epoch_bad_payload_and_provider_never_call_model(self):
        with self.assertRaises(GatewayError): self.reserve(epoch='wrong-epoch')
        one = self.reserve()
        for body in ({'lease': one['lease'], 'id': 'task', 'payload': {}},
                     {'lease': one['lease'], 'id': 'task', 'payload': TEST_PAYLOAD, 'model': 'paid'},
                     {'lease': one['lease'], 'id': ['task'], 'payload': TEST_PAYLOAD}):
            with self.assertRaises(GatewayError): self.coordinator.decide('cn', body)
        self.assertEqual(self.calls, [])

    def test_uncertain_transport_blocks_model_instead_of_retrying(self):
        one = self.reserve()
        def fail(*_args): raise FreeCallError(503, 'safe message', 'transport_uncertain')
        self.sender.send = fail
        with self.assertRaises(GatewayError): self.decide(one)
        self.assertEqual(self.coordinator.budget.available('zhipu'), 'upstream_blocked')
        self.coordinator.release('cn', {'lease': one['lease']})
        with self.assertRaises(GatewayError) as result: self.reserve(site='global', owner='g'*24)
        self.assertEqual(result.exception.code, 'upstream_blocked')


class GatewayHTTPTests(unittest.TestCase):
    def setUp(self):
        self.sender = FreeModels(KEYS, verified=True)
        self.calls = []
        self.sender.send = lambda provider, payload: self.calls.append((provider, deepcopy(payload))) or deepcopy(ANSWER)
        self.coordinator = FreeCoordinator(self.sender)
        self.server = GatewayServer(0, self.coordinator, SITES)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.cleanup)
        url = f'http://127.0.0.1:{self.server.server_port}'
        self.clients = {site: FreeGatewayClient(SharedClient({'url': url, 'site': site, 'token': token}), gateway_url=url) for site, token in SITES.items()}

    def cleanup(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)

    def test_private_rpc_reserves_global_seat_and_sends_server_snapshot(self):
        one = self.clients['cn'].request('reserve', {'provider': 'zhipu', 'owner': 'c'*24, 'round': 'r'*24})
        with self.assertRaises(GatewayError):
            self.clients['global'].request('reserve', {'provider': 'zhipu', 'owner': 'g'*24, 'round': 'r'*24})
        result = self.clients['cn'].request('decide', {'lease': one['lease'], 'id': 'task', 'payload': TEST_PAYLOAD})
        self.assertEqual(result, {'answer': ANSWER})
        self.assertEqual(self.calls, [('zhipu', TEST_PAYLOAD)])

    def test_browser_origin_cookie_or_wrong_credentials_are_rejected(self):
        for extra in ({'Origin': 'https://game.example'}, {'Cookie': 'browser=1'}, {'Authorization': 'Bearer bad'}):
            c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=2)
            headers = {'Authorization': 'Bearer '+SITES['cn'], 'X-ChefJeff-Site': 'cn', 'Content-Type': 'application/json', **extra}
            try:
                c.request('POST', PREFIX+'catalog', '{}', headers)
                response = c.getresponse(); self.assertEqual(response.status, 401); response.read()
            finally: c.close()
        self.assertEqual(self.calls, [])


class RegionalTests(unittest.TestCase):
    def setUp(self):
        self.clock = [1000.0]
        self.sender = FreeModels(KEYS, verified=True)
        self.calls = []
        self.sender.send = lambda provider, payload: self.calls.append((provider, deepcopy(payload))) or deepcopy(ANSWER)
        self.coordinator = FreeCoordinator(self.sender, clock=lambda: self.clock[0])
        class Direct:
            def __init__(self, coordinator, site): self.coordinator, self.site = coordinator, site
            def request(self, operation, body): return self.coordinator.operation(self.site, operation, body)
        self.regions = {site: RegionalFreeModels(Direct(self.coordinator, site), clock=lambda: self.clock[0]) for site in SITES}
        self.games = {site: HostedSession() for site in SITES}
        for game in self.games.values(): self.addCleanup(game.close)

    def prepare(self, site, provider='zhipu', path='/api/start', ident='start-request'):
        game, region = self.games[site], self.regions[site]
        status, _ = region.select(game, {'game_id': game.game_id, 'provider': provider})
        self.assertEqual(status, 200)
        return region.prepare_start(game, path, {'game_id': game.game_id, 'request_id': ident})

    def task(self, game):
        game.relay = BrowserRelay(game.c)
        game.relay.pending = {'id': 'synthetic-task', 'payload': deepcopy(TEST_PAYLOAD),
            'event': threading.Event(), 'result': None, 'sent': time.monotonic()}

    def test_second_region_cannot_start_before_a_global_seat_is_available(self):
        one = self.prepare('cn')
        with self.assertRaises(GatewayError): self.prepare('global')
        self.assertEqual(self.games['global'].phase, 'ready')
        self.assertIsNone(self.games['global'].journal)
        self.assertEqual(self.calls, [])
        self.regions['cn'].finish_start(one, False)
        two = self.prepare('global'); self.regions['global'].finish_start(two, False)

    def test_play_routes_only_to_gateway_and_ended_game_releases_seat(self):
        permit = self.prepare('cn'); game = self.games['cn']; game.phase = 'running'
        self.regions['cn'].finish_start(permit, True); self.task(game)
        status, result = self.regions['cn'].handle(game, {'game_id': game.game_id, 'id': 'synthetic-task', 'provider': 'zhipu'})
        self.assertEqual((status, result), (200, {'answer': ANSWER}))
        game.phase = 'ended'; self.regions['cn'].tick(game)
        self.assertIsNone(game.free_model_lease)
        two = self.prepare('global'); self.regions['global'].finish_start(two, False)
        self.assertEqual(len(self.calls), 1)

    def test_paused_lease_expires_and_resume_reuses_round_budget(self):
        permit = self.prepare('cn'); game = self.games['cn']; game.phase = 'running'
        self.regions['cn'].finish_start(permit, True)
        old_round = game.free_round_ref
        game.phase = 'paused'; self.clock[0] += 46; self.regions['cn'].tick(game)
        resume = self.regions['cn'].prepare_start(game, '/api/resume', {'game_id': game.game_id, 'request_id': 'resume-request'})
        self.assertEqual(game.free_round_ref, old_round)
        game.phase = 'running'; self.regions['cn'].finish_start(resume, True)
        game.phase = 'ended'; self.regions['cn'].tick(game)

    def test_gateway_loss_fails_closed_and_never_falls_back_to_local_model_calls(self):
        permit = self.prepare('cn'); game = self.games['cn']; game.phase = 'running'
        self.regions['cn'].finish_start(permit, True); self.task(game)
        with patch.object(self.regions['cn'].client, 'request', side_effect=GatewayError(503, 'gateway_unavailable')):
            status, _ = self.regions['cn'].handle(game, {'game_id': game.game_id, 'id': 'synthetic-task', 'provider': 'zhipu'})
        self.assertEqual(status, 503); self.assertEqual(self.calls, [])

    def test_gateway_restart_prevents_resuming_an_old_round_with_reset_budgets(self):
        permit = self.prepare('cn'); game = self.games['cn']; game.phase = 'running'
        self.regions['cn'].finish_start(permit, True); game.phase = 'paused'
        self.coordinator.epoch = 'new-generation-with-no-old-leases'
        with self.assertRaises(GatewayError):
            self.regions['cn'].prepare_start(game, '/api/resume', {'game_id': game.game_id, 'request_id': 'resume-request'})
        self.assertFalse(game.free_admission_gate.locked())


class TwoRegionAdmissionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.sender = FreeModels(KEYS, verified=True)
        self.calls = []
        def send(provider, payload):
            self.calls.append(provider)
            return {'choice': next(iter(payload['questions']['next_action']['criteria'])),
                    'sprint': False, 'usage': {'input_tokens': 1, 'output_tokens': 0}}
        self.sender.send = send
        self.coordinator = FreeCoordinator(self.sender)
        self.gateway = GatewayServer(0, self.coordinator, SITES)
        self.gateway_thread = threading.Thread(target=self.gateway.serve_forever, daemon=True)
        self.gateway_thread.start()
        self.servers, self.threads = {}, []
        for site in SITES:
            server = make_server(0, 'http://127.0.0.1', capacity=2)
            server.public_origin = f'http://127.0.0.1:{server.server_port}'
            client = SharedClient({'url':f'http://127.0.0.1:{self.gateway.server_port}', 'site':site, 'token':SITES[site]})
            server.free_models = RegionalFreeModels(FreeGatewayClient(client, gateway_url=f'http://127.0.0.1:{self.gateway.server_port}'))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            self.servers[site] = server; self.threads.append(thread)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for server in self.servers.values():
            server.shutdown(); server.sessions.close(); server.server_close()
        for thread in self.threads: thread.join(2)
        self.gateway.shutdown(); self.gateway.server_close(); self.gateway_thread.join(2)

    def request(self, site, path, body=None, token=None):
        server = self.servers[site]
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=4)
        headers = {'Origin':server.public_origin}
        if token: headers['X-ChefJeff-Session'] = token
        if body is not None: headers['Content-Type'] = 'application/json'
        try:
            connection.request('GET' if body is None else 'POST', path, None if body is None else json.dumps(body), headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally: connection.close()

    def page(self, site, provider='zhipu'):
        status, value = self.request(site, '/api/session', {})
        self.assertEqual(status, 201)
        token = value['session']; game = self.servers[site].sessions.get(token)
        self.assertEqual(self.request(site, '/api/model/free/select', {'game_id':game.game_id, 'provider':provider}, token)[0], 200)
        return token, game

    def command(self, site, token, game, path, ident, **body):
        return self.request(site, path, {'game_id':game.game_id, 'request_id':ident, **body}, token)

    def test_full_http_admission_rejects_second_region_without_starting_its_clock(self):
        cn, one = self.page('cn'); de, two = self.page('global')
        self.assertEqual(self.command('cn', cn, one, '/api/start', 'start-cn')[0], 200)
        status, value = self.command('global', de, two, '/api/start', 'start-global')
        self.assertEqual(status, 503)
        self.assertIn('名额', value['error']); self.assertEqual(two.phase, 'ready'); self.assertIsNone(two.journal)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.command('cn', cn, one, '/api/end', 'end-cn')[0], 200)
        self.assertEqual(self.command('global', de, two, '/api/start', 'start-global')[0], 200)
        self.assertEqual(two.phase, 'running')
        # Same start replay doesn't reserve a second seat or reset round budgets.
        self.assertEqual(self.command('global', de, two, '/api/start', 'start-global')[0], 200)
        self.assertEqual(len(self.coordinator.leases), 1)

    def test_complete_synthetic_round_keeps_identity_and_releases_its_seat(self):
        token, game = self.page('cn', 'startlux')
        self.assertEqual(self.command('cn', token, game, '/api/start', 'start')[0], 200)
        deadline = time.monotonic()+2
        task = None
        while time.monotonic()<deadline:
            task = self.request('cn', '/api/model/request', token=token)[1]['request']
            if task: break
            time.sleep(.01)
        self.assertIsNotNone(task)
        status, value = self.request('cn', '/api/model/free', {'game_id':game.game_id,'provider':'startlux','id':task['id']}, token)
        self.assertEqual(status, 200)
        self.assertEqual(self.request('cn', '/api/model/result', {'id':task['id'], **value['answer']}, token)[0], 200)
        with game.lock:
            game.k.advance(181)
            game.tick()
        self.assertEqual(game.phase, 'ended')
        self.assertTrue(game.k.ended); self.assertFalse(game.faulted)
        self.servers['cn'].free_models.tick(game)
        self.assertEqual(self.coordinator.catalog()['global_capacity']['startlux']['used'], 0)
        self.assertEqual(self.calls, ['startlux'])
        self.assertIsNone(game.store); self.assertFalse(game.research_active)


if __name__ == '__main__': unittest.main()
