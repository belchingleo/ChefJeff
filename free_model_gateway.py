#!/usr/bin/env python3
"""One private free-model gateway for both regions; no research/usage database access."""
import argparse
from collections import OrderedDict
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import signal
import threading
import time

from free_model_budget import CallBudget, BudgetError
from free_model_diagnostics import Diagnostics
from model_status import clean
from hosted_free_models import FreeModels, FreeCallError, MODELS, ORIGINAL, read_trial_keys, read_extra_keys
from hosted_jev import ForwardError

PREFIX = '/v1/free-models/'
MAX_BODY = 262144
CODES = frozenset(('invalid_request', 'seat_busy', 'request_busy', 'lease_lost', 'round_changed',
    'upstream_blocked', 'upstream_cooldown', 'call_budget', 'daily_budget', 'call_pacing', 'round_budget',
    'budget_unavailable', 'upstream_failed', 'gateway_unavailable', 'unauthorized'))


def platform_pools(state_dir):
    """The later models' budgets, each in its own directory so the original budget file keeps its format.
    Below each platform's free tier: Gemini 15 requests a minute and 500 a day; Cloudflare 10,000
    Neurons a day for the whole account, about 70 (Gemma) or 100 (Llama) per kitchen request."""
    from pathlib import Path
    return (CallBudget(Path(state_dir)/'gemini', providers=('gemini',), minute=14, hour=450, day=450, spacing=4.3),
            CallBudget(Path(state_dir)/'cloudflare', providers=('cloudflare-gemma', 'cloudflare-llama'),
                       minute=30, hour=9000, day=9000, weights={'cloudflare-gemma': 80, 'cloudflare-llama': 115}))


class GatewayError(Exception):
    def __init__(self, status, code, diagnostic=None):
        self.status = status
        self.code = code if code in CODES else 'gateway_unavailable'
        self.diagnostic=clean(diagnostic)
        super().__init__(self.code)


def identifier(value, minimum=1):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{'+str(minimum)+r',100}', value) is not None


class FreeCoordinator:
    def __init__(self, sender, budget=None, clock=time.monotonic, lease_seconds=45, seats=None, pools=()):
        self.sender, self.budget, self.clock = sender, budget or CallBudget(), clock
        self.enabled = tuple(p for p in MODELS if p in sender.keys)
        # Each model draws on its platform's pool; the original two share the original budget.
        self.budgets = {p: self.budget for p in self.budget.providers}
        for pool in pools:
            self.budgets.update(dict.fromkeys(pool.providers, pool))
        if any(p not in self.budgets for p in self.enabled):
            raise ValueError('Every enabled free model needs a call budget')
        self.lease_seconds = lease_seconds
        self.seats = seats or dict.fromkeys(self.enabled, 1)
        # Initial rollout always respects the confirmed Zhipu single-concurrency limit.
        if set(self.seats) != set(self.enabled) or any(type(n) is not int or n != 1 for n in self.seats.values()):
            raise ValueError('Initial global trial has one seat per model')
        self.lock = threading.RLock()
        self.epoch = secrets.token_urlsafe(24)
        self.leases = {}
        self.round_calls = OrderedDict()
        self.diagnostics=Diagnostics(self.budget.directory, self.enabled)

    def _reap(self):
        now = self.clock()
        for token, lease in list(self.leases.items()):
            if (lease['released'] or lease['until'] <= now) and not lease['inflight']:
                del self.leases[token]

    def catalog(self):
        with self.lock:
            self._reap()
            result = self.sender.catalog()
            result['epoch'] = self.epoch
            result['diagnostics_version']=1
            result['global_capacity'] = {}
            for provider in self.enabled:
                used = sum(x['provider'] == provider for x in self.leases.values())
                budget = self.budgets[provider]
                reason = budget.available(provider)
                result['global_capacity'][provider] = {'used': used, 'limit': 1,
                    'available': not reason and used < 1, 'reason': reason or ('seat_busy' if used else None),
                    'retry_after_seconds':budget.retry_after(provider)}
            return result

    def _lookup(self, site, token):
        lease = self.leases.get(token) if identifier(token, 16) else None
        if (lease is None or lease['site'] != site or lease['released'] or lease['until'] <= self.clock()):
            raise GatewayError(409, 'lease_lost')
        return lease

    def reserve(self, site, body):
        if (set(body) - {'provider', 'owner', 'round', 'epoch'} or
                not isinstance(body.get('provider'), str) or body.get('provider') not in self.enabled or not identifier(body.get('owner'), 16)
                or not identifier(body.get('round'), 16)):
            raise GatewayError(400, 'invalid_request')
        if body.get('epoch', self.epoch) != self.epoch:
            raise GatewayError(409, 'round_changed')
        provider = body['provider']
        with self.lock:
            self._reap()
            for token, lease in list(self.leases.items()):
                if (lease['site'], lease['owner']) == (site, body['owner']):
                    if lease['round'] == body['round'] and lease['provider'] == provider and not lease['released']:
                        lease['until'] = self.clock()+self.lease_seconds
                        return {'lease': token, 'epoch': self.epoch, 'ttl': self.lease_seconds}
                    if lease['inflight']:
                        raise GatewayError(503, 'request_busy')
                    del self.leases[token]
            reason = self.budgets[provider].available(provider)
            if reason:
                raise GatewayError(429 if reason in ('call_budget', 'daily_budget') else 503, reason)
            if sum(x['provider'] == provider for x in self.leases.values()) >= self.seats[provider]:
                raise GatewayError(503, 'seat_busy')
            token = secrets.token_urlsafe(32)
            self.leases[token] = {'provider': provider, 'site': site, 'owner': body['owner'],
                'round': body['round'], 'until': self.clock()+self.lease_seconds,
                'inflight': False, 'released': False, 'receipts': OrderedDict()}
            return {'lease': token, 'epoch': self.epoch, 'ttl': self.lease_seconds}

    def renew(self, site, body):
        if set(body) != {'lease'}:
            raise GatewayError(400, 'invalid_request')
        with self.lock:
            lease = self._lookup(site, body['lease'])
            lease['until'] = self.clock()+self.lease_seconds
            return {'ttl': self.lease_seconds}

    def release(self, site, body):
        if set(body) != {'lease'} or not identifier(body.get('lease'), 16):
            raise GatewayError(400, 'invalid_request')
        with self.lock:
            lease = self.leases.get(body['lease'])
            if lease and lease['site'] != site:
                raise GatewayError(409, 'lease_lost')
            if lease:
                lease['released'] = True
            self._reap()
            return {'released': True}

    def decide(self, site, body):
        if (set(body) != {'lease', 'id', 'payload'} or not identifier(body.get('lease'), 16)
                or not identifier(body.get('id'))):
            raise GatewayError(400, 'invalid_request')
        payload = body['payload']
        try:
            questions = payload['questions']
            criteria = questions['next_action']['criteria']
            if (not isinstance(payload, dict) or not isinstance(payload['state'], dict)
                    or not isinstance(questions, dict) or not isinstance(criteria, dict)
                    or not 1 <= len(criteria) <= 512 or any(not isinstance(k, str) for k in criteria)
                    or len(json.dumps(payload).encode()) > MAX_BODY-1024):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise GatewayError(400, 'invalid_request') from None
        with self.lock:
            lease = self._lookup(site, body['lease'])
            cached = lease['receipts'].get(body['id'])
            if cached is not None:
                if cached[0] != 200:
                    raise GatewayError(cached[0],cached[1],cached[2])
                return cached[1]
            if lease['inflight']:
                raise GatewayError(503, 'request_busy')
            usage_key = (site, lease['owner'], lease['round'])
            used = self.round_calls.get(usage_key, 0)
            if used >= 200:
                raise GatewayError(429,'round_budget',{'code':'round_budget','provider':lease['provider'],'upstream_called':False,'blocked':True})
            provider = lease['provider']
            budget = self.budgets[provider]
            wait = budget.pace(provider)
            if wait:  # a platform per-minute limit: Jeff waits a few seconds, nothing is spent
                raise GatewayError(503,'call_pacing',{'code':'call_pacing','provider':provider,
                    'upstream_called':False,'retry_after_seconds':wait,'blocked':False})
            try:
                budget.begin(provider)
            except BudgetError as error:
                raise GatewayError(429 if error.code in ('call_budget', 'daily_budget') else 503,error.code,
                    {'code':error.code,'provider':provider,'upstream_called':False,
                     'retry_after_seconds':budget.retry_after(provider),'blocked':budget.retry_after(provider) is None}) from None
            lease['inflight'] = True
            self.round_calls[usage_key] = used+1
            while len(self.round_calls) > 2048:
                self.round_calls.popitem(last=False)
        category, result = None, (503, 'upstream_failed')
        started=time.monotonic();diagnostic={}
        try:
            answer=self.sender.send(provider,payload)
            diagnostic=getattr(answer,'diagnostic',{})
            result=(200,{'answer':dict(answer)})
        except FreeCallError as error:
            category = error.category
            diagnostic=error.diagnostic
        except ForwardError:
            category = 'invalid_response'
        except Exception:
            # Unknown outcomes must never silently open a second upstream request.
            category = 'transport_uncertain'
        with self.lock:
            lease['inflight'] = False
            try:
                budget.finish(provider, category)
            except BudgetError:
                result = (503, 'budget_unavailable')
            if lease['released'] or lease['until'] <= self.clock():
                result = (409, 'lease_lost')
            self._reap()
            diagnostic=clean({'code':'ok' if result[0]==200 else category if category in ('invalid_response','transport_uncertain','model_mismatch') else 'upstream_failed',
                'provider':provider,'upstream_called':True if result[0]==200 else None,'duration_ms':round((time.monotonic()-started)*1000),**diagnostic,
                'retry_after_seconds':budget.retry_after(provider),
                'blocked':budget.available(provider) in ('upstream_blocked','budget_unavailable')})
            if isinstance(result[1],str) and result[1] in ('lease_lost','budget_unavailable'):
                diagnostic.update(code=result[1],blocked=True)
            diagnostic['diagnostics_saved']=self.diagnostics.record(diagnostic)
            if result[0]==200:result[1]['diagnostic']=diagnostic
            lease['receipts'][body['id']]=(result[0],result[1],diagnostic)
            while len(lease['receipts']) > 200:
                lease['receipts'].popitem(last=False)
        if result[0] != 200:
            raise GatewayError(result[0],result[1],diagnostic)
        return result[1]

    def operation(self, site, operation, body):
        if not isinstance(body, dict):
            raise GatewayError(400, 'invalid_request')
        if operation == 'catalog' and not body:
            return self.catalog()
        if operation=='status' and not body:
            with self.lock:return {'catalog':self.catalog(),'diagnostics':self.diagnostics.snapshot()}
        function = {'reserve': self.reserve, 'renew': self.renew, 'release': self.release, 'decide': self.decide}.get(operation)
        if function is None:
            raise GatewayError(400, 'invalid_request')
        return function(site, body)


class GatewayServer(ThreadingHTTPServer):
    # A normal restart drains bounded upstream calls before releasing the budget lock.
    daemon_threads = False
    request_queue_size = 16

    def __init__(self, port, coordinator, sites):
        if (not isinstance(sites, dict) or not 1 <= len(sites) <= 4
                or any(not identifier(site) or not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', token) for site, token in sites.items())
                or len(set(sites.values())) != len(sites)):
            raise ValueError('Invalid private gateway site credentials')
        self.coordinator, self.sites = coordinator, dict(sites)
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(('127.0.0.1', port), GatewayHandler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        pass  # No request, credential, provider text or traceback logging.


class GatewayHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def reply(self, status, value):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            self.wfile.write(raw)
        except OSError:
            pass

    def do_GET(self):
        self.reply(404, {'error': 'invalid_request'})

    def do_POST(self):
        site = self.headers.get('X-ChefJeff-Site', '')
        token = self.server.sites.get(site)
        supplied = self.headers.get('Authorization', '')
        if (not token or not hmac.compare_digest(supplied.encode(), ('Bearer '+token).encode())
                or self.headers.get('Origin') or self.headers.get('Cookie')):
            return self.reply(401, {'error': 'unauthorized'})
        if not self.path.startswith(PREFIX):
            return self.reply(404, {'error': 'invalid_request'})
        try:
            if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
                raise ValueError()
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            value = self.server.coordinator.operation(site, self.path[len(PREFIX):], body)
            return self.reply(200, {'value': value})
        except GatewayError as error:
            return self.reply(error.status, {'error': error.code,'diagnostic':error.diagnostic})
        except (ValueError, TypeError, KeyError, OverflowError):
            return self.reply(400, {'error': 'invalid_request'})
        except Exception:
            return self.reply(503, {'error': 'gateway_unavailable'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('serve', 'acknowledge-idle'))
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--keys-file', type=Path)
    parser.add_argument('--site-credentials', type=Path)
    parser.add_argument('--models-verified', action='store_true')
    parser.add_argument('--extra-keys-file', type=Path)
    parser.add_argument('--extra-models-verified', action='store_true')
    parser.add_argument('--default-model', choices=ORIGINAL, default='startlux')
    parser.add_argument('--provider', choices=tuple(MODELS))
    parser.add_argument('--upstream-idle-confirmed', action='store_true')
    parser.add_argument('--port', type=int, default=8798)
    args = parser.parse_args()
    if args.operation == 'acknowledge-idle':
        if not args.provider or not args.upstream_idle_confirmed:
            parser.error('Confirm upstream idle before acknowledging an interrupted request')
        pool = next((b for b in platform_pools(args.state_dir) if args.provider in b.providers), None) \
            if args.provider not in ORIGINAL else CallBudget(args.state_dir)
        try:
            pool.acknowledge_idle(args.provider)
        finally:
            pool.close()
        print('Gateway recovery acknowledged; call budgets preserved; 60-second cooldown applied.')
        return
    if not args.models_verified or args.keys_file is None or args.site_credentials is None:
        parser.error('Verify both fixed models and provide private external credentials')
    if (args.extra_keys_file is None) != (not args.extra_models_verified):
        parser.error('Later free models need their own key file and operator verification')
    from shared_server import read_private_json
    config = read_private_json(args.site_credentials)
    if set(config) != {'sites'}:
        parser.error('Invalid private sites configuration')
    budget = CallBudget(args.state_dir)
    pools = ()
    try:
        extra = read_extra_keys(args.extra_keys_file) if args.extra_keys_file else None
        pools = platform_pools(args.state_dir) if extra else ()
        sender = FreeModels(read_trial_keys(args.keys_file), verified=True, default=args.default_model, extra=extra)
        server = GatewayServer(args.port, FreeCoordinator(sender, budget, pools=pools), config['sites'])
        signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown(); server.server_close()
    finally:
        budget.close()
        for pool in pools:
            pool.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError):
        raise SystemExit('Gateway stopped: private configuration or budget state is unavailable.') from None
