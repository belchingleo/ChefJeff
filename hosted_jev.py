"""Opt-in Jev forwarding. Keys belong to a single HTTP request, never a game."""
import json
import threading
import time
import urllib.error
import urllib.request
from copy import deepcopy
from cooperation_memory import validate_browser_context, PAST_EPISODES_RULE
from model_language import english_data

ENDPOINT = 'https://api.typesafe.ai/v1/systemone'
CONSENT_VERSION = 'jev-relay-2026-10-v1'
TEST_PAYLOAD = {'state':{'connection_test':True}, 'questions':{'next_action':{
    'type':'choice', 'instructions':'Connection test. Choose wait.', 'criteria':{'wait':'Wait'}}}}


class ForwardError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def valid_key(key):
    return isinstance(key,str) and 8 <= len(key) <= 2048 and key.isascii() and not any(c.isspace() or ord(c)<32 or ord(c)==127 for c in key)


def parse_answer(raw, payload):
    try:
        d = json.loads(raw)
        answer = d['answers']['next_action']
        choice = answer['choice']
        if answer['type'] != 'choice' or not isinstance(choice,str) or choice not in payload['questions']['next_action']['criteria']:
            raise ValueError()
        sprint = d['answers'].get('sprint',{})
        if 'sprint' in payload['questions'] and (sprint.get('type')!='choice' or sprint.get('choice') not in ('yes','no')):
            raise ValueError()
        usage = d.get('usage',{})
        if not isinstance(usage,dict): raise ValueError()
        counts = {name:usage.get(name,0) for name in ('input_tokens','output_tokens')}
        if any(type(n) is not int or not 0 <= n <= 10000000 for n in counts.values()): raise ValueError()
        from research_record import probabilities
        # Never return provider model text, headers or raw replies; option probabilities only for offered keys.
        return {'choice':choice, 'sprint':sprint.get('choice')=='yes', 'usage':counts,
                'probabilities':probabilities(answer.get('probabilities'), payload['questions']['next_action']['criteria'])}
    except (ValueError,TypeError,KeyError,AttributeError):
        raise ForwardError(502,'Jev 返回了无效动作，未执行任何操作。') from None


class JevForwarder:
    """One opt-in relay. Subclasses change only the vendor, its consent and what goes upstream."""
    name, consent = 'Jev', CONSENT_VERSION

    def __init__(self, concurrency=8):
        self.slots = threading.BoundedSemaphore(concurrency)

    def check(self, body):
        """An error for vendor fields the request must carry, before any slot or game lock."""
        return None

    def forward(self, body, payload):
        return self.send(body['api_key'], payload)

    def send(self, key, payload):
        """Fixed upstream, verified TLS/default runtime proxy, no redirects/retries."""
        request = urllib.request.Request(ENDPOINT,
            data=json.dumps({**payload,'model':'jev-latest'},ensure_ascii=False).encode(),
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=18) as response:
                raw = response.read(262145)
            if len(raw)>262144: raise ForwardError(502,'Jev 回复过大。')
            return parse_answer(raw,payload)
        except urllib.error.HTTPError as e:
            status = e.code
            e.close()
            raise ForwardError(503 if status in (429,529) else 502,
                'Jev 接口返回 HTTP '+str(status)+'，请检查账号和模型。') from None
        except (urllib.error.URLError,TimeoutError,OSError):
            raise ForwardError(502,'试玩服务器无法连接 Jev，请稍后重试。') from None

    def handle(self, game, body):
        name = self.name
        if body.get('consent_version') != self.consent or body.get('consent') is not True:
            return 400, {'error':f'请先同意通过试玩服务器调用 {name}。'}
        if not valid_key(body.get('api_key')):
            return 400, {'error':'请输入完整的 API Key。'}
        if type(body.get('test')) is not bool:
            return 400, {'error':f'{name} 请求无效。'}
        problem = self.check(body)
        if problem:
            return 400, {'error':problem}
        check = body.get('test') is True
        ident = body.get('request_id') if check else body.get('id')
        if not isinstance(ident,str) or not 1 <= len(ident) <= 100:
            return 400, {'error':f'{name} 请求无效。'}
        # One relayed request per kitchen at a time, whichever vendor it goes to.
        if not game.jev_gate.acquire(blocking=False):
            return 409, {'error':f'此厨房的 {name} 请求仍在处理中。'}
        acquired = False
        try:
            with game.lock:
                if body.get('game_id') != game.game_id or game.stop_event.is_set():
                    return 409, {'error':'这是上一局的操作，请刷新页面。'}
                if (check and game.phase not in ('ready','ended')) or (not check and game.phase!='running'):
                    return 409, {'error':f'当前不能请求 {name}。'}
                cache_id = ('test' if check else 'task', game.game_id, ident)
                if cache_id in game.jev_receipts:
                    return game.jev_receipts[cache_id]
                relay = game.relay
                if check:
                    if time.monotonic()-game.jev_last_check < 10:
                        return 429, {'error':'连接测试过于频繁，请稍后重试。'}
                    payload = TEST_PAYLOAD
                else:
                    task = relay.request() if relay else None
                    if not task or task['id'] != ident:
                        return 409, {'error':f'{name} 决策请求已过期。'}
                    payload = task['payload']
                    if 'memory' in body:
                        try:
                            context = validate_browser_context(body['memory'], game.c['level_id'])
                        except (ValueError, TypeError, KeyError, OverflowError):
                            return 400, {'error':'跨局记忆格式无效；请清空记忆后重试。'}
                        payload = deepcopy(payload)
                        payload['state']['past_episodes'] = english_data(context)
                        payload['state']['rules']['past_episodes'] = PAST_EPISODES_RULE
                acquired = self.slots.acquire(blocking=False)
                if not acquired:
                    return 503, {'error':f'{name} 转发请求较多，请稍后重试。'}
                if check: game.jev_last_check = time.monotonic()
            # No game/global admission lock is held during network I/O.
            try:
                answer = self.forward(body, payload)
                result = (200, {'answer':answer})
            except ForwardError as e:
                result = (e.status, {'error':e.message})
            with game.lock:
                # Pause/end/close/next-round must invalidate late decisions.
                current = relay.request() if relay else None
                if body['game_id'] != game.game_id or game.stop_event.is_set() or (not check and (
                        game.phase!='running' or game.relay is not relay or not current or current['id']!=ident)):
                    result = (409, {'error':f'{name} 决策请求已过期。'})
                game.jev_receipts[cache_id] = result
                while len(game.jev_receipts)>16: game.jev_receipts.popitem(last=False)
            return result
        finally:
            if acquired: self.slots.release()
            game.jev_gate.release()
