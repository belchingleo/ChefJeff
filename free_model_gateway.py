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
from hosted_free_models import FreeModels, FreeCallError, MODELS, read_trial_keys
from hosted_jev import ForwardError

PREFIX = '/v1/free-models/'
MAX_BODY = 262144
CODES = frozenset(('invalid_request', 'seat_busy', 'request_busy', 'lease_lost', 'round_changed',
    'upstream_blocked', 'upstream_cooldown', 'call_budget', 'round_budget', 'budget_unavailable',
    'upstream_failed', 'gateway_unavailable', 'unauthorized'))


class GatewayError(Exception):
    def __init__(self, status, code):
        self.status = status
        self.code = code if code in CODES else 'gateway_unavailable'
        super().__init__(self.code)


def identifier(value, minimum=1):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{'+str(minimum)+r',100}', value) is not None


class FreeCoordinator:
    def __init__(self, sender, budget=None, clock=time.monotonic, lease_seconds=45, seats=None):
        self.sender, self.budget, self.clock = sender, budget or CallBudget(), clock
        self.lease_seconds = lease_seconds
        self.seats = seats or dict.fromkeys(MODELS, 1)
        # Initial rollout always respects the confirmed Zhipu single-concurrency limit.
        if set(self.seats) != set(MODELS) or any(type(n) is not int or n != 1 for n in self.seats.values()):
            raise ValueError('Initial global trial has one seat per model')
        self.lock = threading.RLock()
        self.epoch = secrets.token_urlsafe(24)
        self.leases = {}
        self.round_calls = OrderedDict()

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
            result['global_capacity'] = {}
            for provider in MODELS:
                used = sum(x['provider'] == provider for x in self.leases.values())
                reason = self.budget.available(provider)
                result['global_capacity'][provider] = {'used': used, 'limit': 1,
                    'available': not reason and used < 1, 'reason': reason or ('seat_busy' if used else None)}
            return result

    def _lookup(self, site, token):
        lease = self.leases.get(token) if identifier(token, 16) else None
        if (lease is None or lease['site'] != site or lease['released'] or lease['until'] <= self.clock()):
            raise GatewayError(409, 'lease_lost')
        return lease

    def reserve(self, site, body):
        if (set(body) - {'provider', 'owner', 'round', 'epoch'} or
                not isinstance(body.get('provider'), str) or body.get('provider') not in MODELS or not identifier(body.get('owner'), 16)
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
            reason = self.budget.available(provider)
            if reason:
                raise GatewayError(429 if reason == 'call_budget' else 503, reason)
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
                    raise GatewayError(*cached)
                return cached[1]
            if lease['inflight']:
                raise GatewayError(503, 'request_busy')
            usage_key = (site, lease['owner'], lease['round'])
            used = self.round_calls.get(usage_key, 0)
            if used >= 200:
                raise GatewayError(429, 'round_budget')
            provider = lease['provider']
            try:
                self.budget.begin(provider)
            except BudgetError as error:
                raise GatewayError(429 if error.code == 'call_budget' else 503, error.code) from None
            lease['inflight'] = True
            self.round_calls[usage_key] = used+1
            while len(self.round_calls) > 2048:
                self.round_calls.popitem(last=False)
        category, result = None, (503, 'upstream_failed')
        try:
            result = (200, {'answer': self.sender.send(provider, payload)})
        except FreeCallError as error:
            category = error.category
        except ForwardError:
            category = 'invalid_response'
        except Exception:
            # Unknown outcomes must never silently open a second upstream request.
            category = 'transport_uncertain'
        with self.lock:
            lease['inflight'] = False
            try:
                self.budget.finish(provider, category)
            except BudgetError:
                result = (503, 'budget_unavailable')
            if lease['released'] or lease['until'] <= self.clock():
                result = (409, 'lease_lost')
            lease['receipts'][body['id']] = result
            while len(lease['receipts']) > 200:
                lease['receipts'].popitem(last=False)
            self._reap()
        if result[0] != 200:
            raise GatewayError(*result)
        return result[1]

    def operation(self, site, operation, body):
        if not isinstance(body, dict):
            raise GatewayError(400, 'invalid_request')
        if operation == 'catalog' and not body:
            return self.catalog()
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
            return self.reply(error.status, {'error': error.code})
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
    parser.add_argument('--default-model', choices=tuple(MODELS), default='startlux')
    parser.add_argument('--provider', choices=tuple(MODELS))
    parser.add_argument('--upstream-idle-confirmed', action='store_true')
    parser.add_argument('--port', type=int, default=8798)
    args = parser.parse_args()
    if args.operation == 'acknowledge-idle':
        if not args.provider or not args.upstream_idle_confirmed:
            parser.error('Confirm upstream idle before acknowledging an interrupted request')
        with_budget = CallBudget(args.state_dir)
        try:
            with_budget.acknowledge_idle(args.provider)
        finally:
            with_budget.close()
        print('Gateway recovery acknowledged; call budgets preserved; 60-second cooldown applied.')
        return
    if not args.models_verified or args.keys_file is None or args.site_credentials is None:
        parser.error('Verify both fixed models and provide private external credentials')
    from shared_server import read_private_json
    config = read_private_json(args.site_credentials)
    if set(config) != {'sites'}:
        parser.error('Invalid private sites configuration')
    budget = CallBudget(args.state_dir)
    try:
        sender = FreeModels(read_trial_keys(args.keys_file), verified=True, default=args.default_model)
        server = GatewayServer(args.port, FreeCoordinator(sender, budget), config['sites'])
        signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown(); server.server_close()
    finally:
        budget.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError):
        raise SystemExit('Gateway stopped: private configuration or budget state is unavailable.') from None
