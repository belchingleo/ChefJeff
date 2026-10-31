"""Authenticated regional gateway client; upstream model keys never leave Shanghai."""
from copy import deepcopy
import http.client
import json
import secrets
import ssl
import threading
import time
import weakref

from cooperation_memory import validate_browser_context, PAST_EPISODES_RULE
from free_model_gateway import GatewayError, CODES, PREFIX
from hosted_free_models import MODELS
from model_language import english_data

ERRORS = {
    'seat_busy': '这个模型的免费厨房名额已满，请稍后开局或使用自己的模型。',
    'request_busy': '所选免费模型仍在处理请求，请稍后再试。',
    'lease_lost': '本局免费名额已释放，请尝试继续；满额时需等待或结束本局。',
    'round_changed': '免费服务已重启，请结束本局后重新开局。',
    'upstream_blocked': '所选免费模型暂不可用，恢复确认后才能继续提供试玩。',
    'upstream_cooldown': '所选免费模型正在冷却，请稍后再试。',
    'call_budget': '免费试玩调用预算已用完，请稍后再来或使用自己的模型。',
    'round_budget': '本局免费模型调用已达 200 次上限。',
    'budget_unavailable': '免费试玩预算服务暂不可用，本次未发起模型请求。',
}


def public_error(error):
    return error.status, {'error': ERRORS.get(error.code, '免费模型协调服务暂不可用，请稍后再试。')}


class FreeGatewayClient:
    def __init__(self, shared_client, gateway_url=None):
        # shared_client has already validated the private URL/site/token configuration.
        self.url, self.site, self.token = shared_client.url, shared_client.site, shared_client.token
        if gateway_url is not None:
            from shared_client import SharedClient
            self.url = SharedClient({'url': gateway_url, 'site': self.site, 'token': self.token}).url
        elif self.url.scheme == 'http':
            # Shanghai's existing data client uses loopback port 8790. Its model
            # traffic belongs to the independent gateway, never the data service.
            self.url = self.url._replace(netloc=self.url.hostname+':8798')

    def request(self, operation, body):
        if operation not in ('catalog', 'reserve', 'renew', 'release', 'decide'):
            raise GatewayError(400, 'invalid_request')
        kind = http.client.HTTPSConnection if self.url.scheme == 'https' else http.client.HTTPConnection
        options = {'timeout': 22 if operation == 'decide' else 3}
        if self.url.scheme == 'https':
            options['context'] = ssl.create_default_context()
        connection = kind(self.url.hostname, self.url.port, **options)
        try:
            raw = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            if len(raw) > 262144:
                raise GatewayError(400, 'invalid_request')
            connection.request('POST', PREFIX+operation, raw, {'Authorization': 'Bearer '+self.token,
                'X-ChefJeff-Site': self.site, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError()
            value = json.loads(raw)
            if response.status != 200:
                code = value.get('error') if isinstance(value, dict) else None
                raise GatewayError(response.status if response.status in (400, 401, 409, 429, 503) else 503,
                                   code if isinstance(code, str) and code in CODES else 'gateway_unavailable')
            if not isinstance(value, dict) or set(value) != {'value'} or not isinstance(value['value'], dict):
                raise ValueError()
            return value['value']
        except GatewayError:
            raise
        except (OSError, ValueError, http.client.HTTPException):
            raise GatewayError(503, 'gateway_unavailable') from None
        finally:
            connection.close()


class RegionalFreeModels:
    def __init__(self, client, clock=time.monotonic):
        self.client, self.clock = client, clock
        self.guard = threading.Lock()
        self.catalog_time = float('-inf')
        self.cached_catalog = {'enabled': False, 'models': []}
        self.games = weakref.WeakSet()
        self.games_guard = threading.Lock()
        self.stopped = threading.Event()
        self.thread = None

    def catalog(self):
        with self.guard:
            if self.clock()-self.catalog_time < 2:
                return deepcopy(self.cached_catalog)
            try:
                value = self.client.request('catalog', {})
                models = value['models']
                if (value.get('enabled') is not True or not isinstance(models, list) or len(models) != 2
                        or {m.get('provider') for m in models} != set(MODELS)
                        or any(m.get('model') != MODELS[m['provider']]['model'] for m in models)
                        or value.get('default') not in MODELS):
                    raise ValueError()
                value.pop('epoch', None)  # Generation is private control metadata, not player telemetry.
                value['gateway_available'] = True
                self.cached_catalog = value
            except (GatewayError, ValueError, TypeError, KeyError):
                self.cached_catalog = {**self.cached_catalog, 'gateway_available': False}
                if self.cached_catalog.get('enabled'):
                    self.cached_catalog['global_capacity'] = {p: {'used': 0, 'limit': 1, 'available': False,
                        'reason': 'gateway_unavailable'} for p in MODELS}
            self.catalog_time = self.clock()
            return deepcopy(self.cached_catalog)

    def select(self, game, body):
        provider = body.get('provider')
        catalog = self.catalog()
        if not catalog.get('gateway_available'):
            return public_error(GatewayError(503, 'gateway_unavailable'))
        if not isinstance(provider, str) or provider not in MODELS:
            return 400, {'error': '请选择开放的免费模型。'}
        if not game.free_admission_gate.acquire(blocking=False):
            return 409, {'error': '正在申请免费名额，请稍候。'}
        try:
            with game.lock:
                if body.get('game_id') != game.game_id or game.stop_event.is_set():
                    return 409, {'error': '厨房已更新，请刷新状态。'}
                if game.phase not in ('ready', 'ended'):
                    return 409, {'error': '本局模型已固定，请结算后切换。'}
                game.free_model_provider = provider
                game.connected = True
                with self.games_guard:
                    self.games.add(game)
            return 200, {'ok': True, 'provider': provider, 'model': MODELS[provider]['model']}
        finally:
            game.free_admission_gate.release()

    def prepare_start(self, game, path, body):
        """Reserve before game time starts, without holding the game or session lock."""
        if game.free_model_provider is None:
            return None
        if not game.free_admission_gate.acquire(blocking=False):
            raise GatewayError(503, 'request_busy')
        held = True
        lease = None
        try:
            with game.lock:
                if body.get('game_id') != game.game_id or game.stop_event.is_set():
                    raise GatewayError(409, 'round_changed')
                if isinstance(body.get('request_id'), str) and body['request_id'] in game.receipts:
                    return None
                phases = {'/api/start': ('ready',), '/api/restart': ('paused', 'ended'),
                          '/api/next': ('ended',), '/api/resume': ('paused',)}
                if game.phase not in phases.get(path, ()):
                    raise GatewayError(409, 'round_changed')
                old = (game.free_round_ref, game.free_lease_epoch, game.free_round_game)
                resume = path == '/api/resume' and game.free_round_ref is not None
                round_ref = game.free_round_ref if resume else secrets.token_urlsafe(24)
                previous = game.game_id, game.phase, game.free_model_provider
                request = {'provider': game.free_model_provider, 'owner': game.free_owner, 'round': round_ref}
                if resume and game.free_lease_epoch is not None:
                    request['epoch'] = game.free_lease_epoch
            lease = self.client.request('reserve', request)
            from free_model_gateway import identifier
            if not identifier(lease.get('lease'), 16) or not identifier(lease.get('epoch'), 16):
                raise GatewayError(503, 'gateway_unavailable')
            with game.lock:
                if previous != (game.game_id, game.phase, game.free_model_provider) or game.stop_event.is_set():
                    raise GatewayError(409, 'round_changed')
                game.free_model_lease = lease['lease']
                game.free_lease_epoch = lease['epoch']
                game.free_round_ref = round_ref
                game.free_renew_at = self.clock()+5
                with self.games_guard:
                    self.games.add(game)
            held = False
            return {'game': game, 'lease': lease['lease'], 'old': old, 'resume': resume}
        except Exception:
            if lease is not None and isinstance(lease.get('lease'), str):
                self._release(lease['lease'])
            raise
        finally:
            if held:
                game.free_admission_gate.release()

    def finish_start(self, permit, success):
        if permit is None:
            return
        game = permit['game']
        try:
            with game.lock:
                success = success and game.phase == 'running' and not game.stop_event.is_set()
                if success:
                    game.free_round_game = game.game_id
                else:
                    game.free_round_ref, game.free_lease_epoch, game.free_round_game = permit['old']
                    if game.free_model_lease == permit['lease']:
                        game.free_model_lease = None
            if not success:
                self._release(permit['lease'])
        finally:
            game.free_admission_gate.release()

    def _release(self, lease):
        try:
            self.client.request('release', {'lease': lease})
        except GatewayError:
            pass  # TTL reclaims the seat, never a local fallback model call.

    def tick(self, game):
        with game.lock:
            if game.free_admission_gate.locked():
                return
            lease = game.free_model_lease
            if not lease:
                return
            ending = game.stop_event.is_set() or game.phase not in ('running', 'paused') or game.faulted
            if ending:
                game.free_model_lease = None
            elif game.phase == 'paused' or self.clock() < game.free_renew_at:
                return  # Paused kitchens stop renewing and release within the 45-second TTL.
        if ending:
            self._release(lease)
            return
        try:
            self.client.request('renew', {'lease': lease})
            with game.lock:
                if game.free_model_lease == lease:
                    game.free_renew_at = self.clock()+5
        except GatewayError as error:
            if error.code == 'lease_lost':
                with game.lock:
                    if game.free_model_lease == lease:
                        game.free_model_lease = None

    def handle(self, game, body):
        if not game.free_model_gate.acquire(blocking=False):
            return public_error(GatewayError(503, 'request_busy'))
        try:
            with game.lock:
                if (body.get('game_id') != game.game_id or game.phase != 'running' or game.stop_event.is_set()
                        or body.get('provider') != game.free_model_provider):
                    return public_error(GatewayError(409, 'round_changed'))
                lease = game.free_model_lease
                if not lease:
                    return public_error(GatewayError(409, 'lease_lost'))
                relay = game.relay
                task = relay.request() if relay else None
                if not task or body.get('id') != task['id']:
                    return public_error(GatewayError(409, 'round_changed'))
                payload = task['payload']
                if 'memory' in body:
                    try:
                        memory = validate_browser_context(body['memory'], game.c['level_id'])
                    except (ValueError, TypeError, KeyError, OverflowError):
                        return 400, {'error': '跨局记忆格式无效。'}
                    payload = deepcopy(payload)
                    payload['state']['past_episodes'] = english_data(memory)
                    payload['state']['rules']['past_episodes'] = PAST_EPISODES_RULE
                ident = task['id']
            result = self.client.request('decide', {'lease': lease, 'id': ident, 'payload': payload})
            with game.lock:
                current = relay.request() if relay else None
                if (game.free_model_lease != lease or game.relay is not relay or game.phase != 'running'
                        or game.stop_event.is_set() or not current or current['id'] != ident):
                    raise GatewayError(409, 'round_changed')
            return 200, result
        except GatewayError as error:
            return public_error(error)
        finally:
            game.free_model_gate.release()

    def start(self):
        def maintain():
            while not self.stopped.wait(1):
                with self.games_guard:
                    games = list(self.games)
                for game in games:
                    try:
                        self.tick(game)
                    except Exception:
                        pass  # Failed maintenance never causes a local model call or secret logging.
        self.thread = threading.Thread(target=maintain, name='free-model-leases', daemon=True)
        self.thread.start()

    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=4)
        with self.games_guard:
            games = list(self.games)
        for game in games:
            with game.lock:
                lease = game.free_model_lease
                game.free_model_lease = None
            if lease:
                self._release(lease)
