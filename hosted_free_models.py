"""Optional, fixed-model free trials. Disabled until the original two models are operator-verified;
each later model is enabled only by its own verified private key.

Only server-created pending kitchen requests can consume the private credentials.
No arbitrary prompts, endpoints, paid fallback, automatic retries or raw replies.
"""
from collections import OrderedDict, deque
from copy import deepcopy
import json
import http.client
import os
from pathlib import Path
import re
import stat
import threading
import time
import urllib.error
import urllib.request

from cooperation_memory import validate_browser_context, PAST_EPISODES_RULE
from hosted_jev import ForwardError, NoRedirect, valid_key, parse_answer as decision_answer
from model_language import english_data
from model_output import chat_body, zhipu_body
from model_status import ObservedAnswer, clean, numeric_provider_code, response_issue

CLOUDFLARE = 'https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions'
MODELS = {
    'zhipu': {'model': 'glm-4.7-flash', 'name': '智谱 GLM-4.7-Flash', 'platform': '智谱开放平台',
              'endpoint': 'https://open.bigmodel.cn/api/paas/v4/chat/completions', 'field': 'zhipu_api_key'},
    'startlux': {'model': 'startlux-decision-27b-autothink', 'name': 'StartLux 决策模型',
                'platform': 'Bamboo Relay', 'endpoint': 'https://api.bamboonode.dev/v1/decisions', 'field': 'bamboo_api_key'},
    # Later models: OpenAI-compatible chat with the request fields that passed the synthetic probe.
    # record: the research-record service name (model-providers.json); the model ID stays exact.
    'gemini': {'model': 'gemini-3.5-flash-lite', 'name': 'Gemini 3.5 Flash-Lite', 'platform': 'Google AI Studio',
               'endpoint': 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
               'field': 'gemini_api_key', 'record': 'gemini',
               'extra': {'reasoning_effort': 'minimal', 'response_format': {'type': 'json_object'}}},
    'cloudflare-gemma': {'model': '@cf/google/gemma-4-26b-a4b-it', 'name': 'Gemma 4 26B', 'platform': 'Cloudflare Workers AI',
                         'endpoint': CLOUDFLARE, 'field': 'cloudflare_api_key', 'record': 'cloudflare',
                         'extra': {'chat_template_kwargs': {'enable_thinking': False}, 'response_format': {'type': 'json_object'}}},
    'cloudflare-llama': {'model': '@cf/meta/llama-3.1-8b-instruct-fp8', 'name': 'Llama 3.1 8B', 'platform': 'Cloudflare Workers AI',
                         'endpoint': CLOUDFLARE, 'field': 'cloudflare_api_key', 'record': 'cloudflare',
                         'extra': {'response_format': {'type': 'json_object'}}},
}
ORIGINAL = ('zhipu', 'startlux')
EXTRA_FIELDS = {'gemini_api_key', 'cloudflare_api_key', 'cloudflare_account_id'}


class FreeCallError(ForwardError):
    def __init__(self, status, message, category, diagnostic=None):
        super().__init__(status, message)
        self.category = category
        self.diagnostic = clean(diagnostic)


def private_json(path, allow_root_import=False):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Trial credentials must be a private regular file')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 20000
                or (info.st_uid not in (0, os.getuid()) and not (allow_root_import and os.getuid() == 0))
                or stat.S_IMODE(info.st_mode) & 0o027):
            raise ValueError('Trial credentials must be owner-only or group-readable')
        with os.fdopen(fd, 'r', encoding='utf-8') as stream:
            fd = None
            value = json.load(stream)
    except (OSError, ValueError):
        raise ValueError('Cannot load private trial credentials') from None
    finally:
        if fd is not None:
            os.close(fd)
    return value


def read_trial_keys(path, *, allow_root_import=False):
    value = private_json(path, allow_root_import)
    if (not isinstance(value, dict) or set(value) != {'format', 'zhipu_api_key', 'bamboo_api_key'}
            or value.get('format') != 'chefjeff-private-api-keys-v1'
            or any(not valid_key(value.get(MODELS[p]['field'])) for p in ORIGINAL)):
        raise ValueError('Both trial services require valid private credentials')
    return {p: value[MODELS[p]['field']] for p in ORIGINAL}


def read_extra_keys(path, *, allow_root_import=False):
    """A separate private file, so the original key file and an older gateway stay valid on rollback.
    A platform's models are enabled only when its own fields are present and well formed."""
    value = private_json(path, allow_root_import)
    if (not isinstance(value, dict) or value.get('format') != 'chefjeff-private-extra-keys-v1'
            or set(value) - EXTRA_FIELDS - {'format'} or len(value) < 2
            or any(not valid_key(value[f]) for f in ('gemini_api_key', 'cloudflare_api_key') if f in value)
            or ('cloudflare_api_key' in value) != ('cloudflare_account_id' in value)
            or ('cloudflare_account_id' in value and not (isinstance(value['cloudflare_account_id'], str)
                and re.fullmatch(r'[0-9a-f]{32}', value['cloudflare_account_id'])))):
        raise ValueError('Invalid private credentials for the later free models')
    keys = {}
    for provider, model in MODELS.items():
        if provider not in ORIGINAL and model['field'] in value:
            keys[provider] = {'key': value[model['field']],
                              'endpoint': model['endpoint'].format(account=value.get('cloudflare_account_id', ''))}
    return keys


def chat_answer(raw, payload, provider='zhipu'):
    model = MODELS[provider]
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or 'error' in data:
            raise ValueError()
        if data.get('model', model['model']) != model['model']:
            raise ValueError()
        content = data['choices'][0]['message']['content']
        if not isinstance(content, str):
            raise ValueError()
        answer = json.loads(re.sub(r'\s*```$', '', re.sub(r'^```(?:json)?\s*', '', content.strip())))
        if (not isinstance(answer, dict) or set(answer) - {'choice', 'sprint'}
                or not isinstance(answer.get('choice'), str)
                or answer['choice'] not in payload['questions']['next_action']['criteria']
                or ('sprint' in answer and type(answer['sprint']) is not bool)):
            raise ValueError()
        usage = data.get('usage', {})
        counts = {name: usage.get(field, 0) for name, field in (
            ('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens'))}
        if any(type(n) is not int or not 0 <= n <= 10000000 for n in counts.values()):
            raise ValueError()
        return {'choice': answer['choice'], 'sprint': answer.get('sprint') is True, 'usage': counts}
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise ForwardError(502, model['name'] + ' 回复格式或动作无效，本次未执行。') from None


class FreeModels:
    def __init__(self, keys=None, verified=False, default='startlux', clock=time.monotonic, extra=None):
        if default not in ORIGINAL:
            raise ValueError('Unknown default free model')
        if keys is not None and (verified is not True or set(keys) != set(ORIGINAL)
                                 or any(not valid_key(key) for key in keys.values())):
            raise ValueError('Verify both free services before enabling trials')
        if extra and (keys is None or set(extra) - set(MODELS) - set(ORIGINAL) or any(
                not valid_key(v.get('key')) or not str(v.get('endpoint', '')).startswith('https://') for v in extra.values())):
            raise ValueError('Later free models need the original two and their own verified keys')
        self.keys = dict(keys or {})
        self.endpoints = {p: MODELS[p]['endpoint'] for p in self.keys}
        for provider, value in (extra or {}).items():
            self.keys[provider], self.endpoints[provider] = value['key'], value['endpoint']
        self.default, self.clock = default, clock
        self.lock = threading.Lock()
        self.slots = {p: threading.BoundedSemaphore(1) for p in MODELS}
        self.minute = {p: deque() for p in MODELS}
        self.hour = deque()
        self.cooldown = dict.fromkeys(MODELS, 0.0)
        self.blocked = set()

    def catalog(self):
        if not self.keys:
            return {'enabled': False, 'models': []}
        return {'enabled': True, 'default': self.default, 'per_round_limit': 200,
                'reason': ('默认使用 StartLux：它原生返回候选动作及选项概率，便于观察决策；你也可以切换其他免费模型比较。'
                           if self.default == 'startlux' else '默认使用智谱 GLM-4.7-Flash：它通过通用对话接口生成动作；你也可以切换其他免费模型比较不同决策方式。'),
                'note': '免费试玩由服务器提供调用额度，无需填写 Key；每局最多 200 次请求。开局前选择，本局固定。研究数据贡献由你单独选择。',
                'models': [{'provider': p, 'model': m['model'], 'name': m['name'], 'platform': m['platform'],
                            'record': m.get('record', p)} for p, m in MODELS.items() if p in self.keys]}

    def select(self, game, body):
        provider = body.get('provider')
        if not self.keys:
            return 503, {'error': '免费试玩暂未开放，请使用自己的模型配置。'}
        if not isinstance(provider, str) or provider not in self.keys:
            return 400, {'error': '请选择开放的免费模型。'}
        with game.lock:
            if body.get('game_id') != game.game_id or game.stop_event.is_set():
                return 409, {'error': '厨房已更新，请刷新状态。'}
            if game.phase not in ('ready', 'ended'):
                return 409, {'error': '本局模型已固定，请结算后切换。'}
            game.free_model_provider = provider
            game.connected = True
        return 200, {'ok': True, 'provider': provider, 'model': MODELS[provider]['model']}

    def send(self, provider, payload):
        model = MODELS[provider]
        body = (zhipu_body(payload) if provider == 'zhipu' else
                {**payload, 'model': model['model'], 'think_mode': 'never', 'allow_none': False} if provider == 'startlux' else
                chat_body(payload, model['model'], model['extra']))
        request = urllib.request.Request(self.endpoints[provider], data=json.dumps(body, ensure_ascii=False).encode(),
            headers={'Authorization': 'Bearer ' + self.keys[provider], 'Content-Type': 'application/json'}, method='POST')
        started=time.monotonic();http_status=None;raw=b''
        def diagnostic(code,**extra):
            return clean({'code':code,'provider':provider,'upstream_called':True,
                'upstream_http_status':http_status,'duration_ms':round((time.monotonic()-started)*1000),**extra})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=18) as response:
                observed_status=getattr(response,'status',None)
                http_status=observed_status if type(observed_status) is int else None
                raw = response.read(262145)
            if len(raw) > 262144:
                raise ForwardError(502, '免费模型回复过大，本次未执行。')
            try:
                data = json.loads(raw)
                returned = data.get('model') if isinstance(data, dict) else None
                if returned is not None and returned != model['model']:
                    with self.lock:
                        self.blocked.add(provider)
                    raise FreeCallError(502, '免费模型回复不符合预期，本次未执行。', 'model_mismatch',diagnostic('model_mismatch'))
                if isinstance(data, dict) and 'error' in data:
                    with self.lock:
                        self.cooldown[provider] = self.clock() + 60
                    code=numeric_provider_code(data)
                    raise FreeCallError(503,'所选免费模型暂不可用，请稍后再试。','upstream_rejected',
                        diagnostic('upstream_overloaded' if code==1305 else 'upstream_http_error',provider_error_code=code))
            except (ValueError, TypeError):
                raise ForwardError(502, '免费模型回复不符合预期，本次未执行。') from None
            if provider != 'startlux':
                return ObservedAnswer(chat_answer(raw, payload, provider),diagnostic('ok'))
            try:
                return ObservedAnswer(decision_answer(raw, payload),diagnostic('ok'))
            except ForwardError:
                raise ForwardError(502, 'StartLux 回复格式或动作无效，本次未执行。') from None
        except urllib.error.HTTPError as error:
            status = error.code;http_status=status;code=None
            try:
                body=error.read(65537)
                if len(body)<=65536:code=numeric_provider_code(json.loads(body))
            except Exception:pass
            error.close()
            with self.lock:
                self.cooldown[provider] = self.clock() + 60
                if status in (401, 403):
                    self.blocked.add(provider)
            raise FreeCallError(503, '所选免费模型暂不可用，请稍后再试；结算后可切换其他模型。',
                                'authentication' if status in (401, 403) else 'upstream_rejected',
                                diagnostic('upstream_authentication' if status in (401,403) else 'upstream_overloaded' if code==1305 else 'upstream_rate_limited' if status==429 else 'upstream_http_error',provider_error_code=code)) from None
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
            raise FreeCallError(503, '免费模型连接超时或不可用，请稍后再试。', 'transport_uncertain',diagnostic('transport_uncertain')) from None
        except FreeCallError:
            raise
        except ForwardError:
            raise FreeCallError(502,'免费模型返回格式或动作无效，本次未执行。','invalid_response',
                diagnostic('invalid_response',format_error=response_issue(raw,payload,provider))) from None

    def handle(self, game, body):
        if not self.keys:
            return 503, {'error': '免费试玩暂未开放。'}
        provider, ident = body.get('provider'), body.get('id')
        if not isinstance(provider, str) or provider not in self.keys or not isinstance(ident, str) or not 1 <= len(ident) <= 100:
            return 400, {'error': '免费模型请求无效。'}
        if not game.free_model_gate.acquire(blocking=False):
            return 409, {'error': '当前模型请求仍在处理中。'}
        acquired = False
        try:
            with game.lock:
                if (body.get('game_id') != game.game_id or game.phase != 'running'
                        or game.stop_event.is_set() or game.free_model_provider != provider):
                    return 409, {'error': '本局模型或对局状态已经改变。'}
                cache_id = (game.game_id, provider, ident)
                if cache_id in game.free_model_receipts:
                    return game.free_model_receipts[cache_id]
                relay = game.relay
                task = relay.request() if relay else None
                if not task or task['id'] != ident:
                    return 409, {'error': '模型决策请求已过期。'}
                payload = task['payload']
                if 'memory' in body:
                    try:
                        context = validate_browser_context(body['memory'], game.c['level_id'])
                    except (ValueError, TypeError, KeyError, OverflowError):
                        return 400, {'error': '跨局记忆格式无效。'}
                    payload = deepcopy(payload)
                    payload['state']['past_episodes'] = english_data(context)
                    payload['state']['rules']['past_episodes'] = PAST_EPISODES_RULE
                if game.free_model_budget_round != game.game_id:
                    game.free_model_budget_round, game.free_model_calls = game.game_id, 0
                if game.free_model_calls >= 200:
                    return 429, {'error': '本局免费模型调用已达 200 次上限。'}
                with self.lock:
                    now = self.clock()
                    minute = self.minute[provider]
                    while minute and minute[0] <= now - 60:
                        minute.popleft()
                    while self.hour and self.hour[0] <= now - 3600:
                        self.hour.popleft()
                    if provider in self.blocked or now < self.cooldown[provider]:
                        return 503, {'error': '所选免费模型暂不可用，请稍后再试。'}
                    if len(minute) >= 30 or len(self.hour) >= 300:
                        return 429, {'error': '免费试玩请求较多，请稍后再试。'}
                    acquired = self.slots[provider].acquire(blocking=False)
                    if not acquired:
                        return 503, {'error': '所选免费模型正在服务其他厨房，请稍后再试。'}
                    minute.append(now)
                    self.hour.append(now)
                    game.free_model_calls += 1
            try:
                answer = self.send(provider, payload)
                result = (200, {'answer': answer})
            except ForwardError as error:
                result = (error.status, {'error': error.message})
            with game.lock:
                current = relay.request() if relay else None
                if (body['game_id'] != game.game_id or game.phase != 'running' or game.stop_event.is_set()
                        or game.relay is not relay or game.free_model_provider != provider
                        or not current or current['id'] != ident):
                    result = (409, {'error': '模型决策请求已过期。'})
                game.free_model_receipts[cache_id] = result
                while len(game.free_model_receipts) > 32:
                    game.free_model_receipts.popitem(last=False)
            return result
        finally:
            if acquired:
                self.slots[provider].release()
            game.free_model_gate.release()
