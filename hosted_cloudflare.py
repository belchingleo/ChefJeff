"""Opt-in Cloudflare Workers AI forwarding: its API refuses browser (CORS) requests.
The player's key and account ID belong to a single HTTP request, never a game or a log."""
import json
import re
import urllib.error
import urllib.request

from hosted_free_models import MODELS, chat_answer
from hosted_jev import ForwardError, JevForwarder, NoRedirect
from model_output import chat_body

CONSENT_VERSION = 'cloudflare-relay-2026-11-v1'
# Only the probed models, each with the request fields that passed the synthetic probe.
RELAYED = {MODELS[p]['model']: p for p in ('cloudflare-gemma', 'cloudflare-llama')}


class CloudflareForwarder(JevForwarder):
    name, consent = 'Cloudflare', CONSENT_VERSION

    def check(self, body):
        account = body.get('account_id')
        if not isinstance(account, str) or not re.fullmatch(r'[0-9a-f]{32}', account):
            return '请填写 32 位的 Account ID（在服务商控制台里可以找到）。'
        if body.get('model') not in RELAYED:
            return '在线转发只支持 Gemma 4 26B 和 Llama 3.1 8B。'
        return None

    def forward(self, body, payload):
        """Fixed host and path, verified TLS, no redirects or retries; the account ID is checked above."""
        provider = RELAYED[body['model']]
        model = MODELS[provider]
        request = urllib.request.Request(
            'https://api.cloudflare.com/client/v4/accounts/' + body['account_id'] + '/ai/v1/chat/completions',
            data=json.dumps(chat_body(payload, model['model'], model['extra']), ensure_ascii=False).encode(),
            headers={'Authorization': 'Bearer ' + body['api_key'], 'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=18) as response:
                raw = response.read(262145)
            if len(raw) > 262144:
                raise ForwardError(502, 'Cloudflare 回复过大。')
            return chat_answer(raw, payload, provider)
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            raise ForwardError(503 if status in (429, 529) else 502,
                               'Cloudflare 接口返回 HTTP ' + str(status) + '，请检查账号和模型。') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ForwardError(502, '试玩服务器无法连接 Cloudflare，请稍后重试。') from None
