"""Allowlisted operational diagnostics, independent of research consent and schemas."""
import math
import time

CODES=frozenset(('ok','upstream_rate_limited','upstream_overloaded','upstream_authentication',
 'upstream_http_error','invalid_response','transport_uncertain','model_mismatch','upstream_failed',
 'upstream_blocked','upstream_cooldown','call_budget','daily_budget','call_pacing','round_budget','budget_unavailable',
 'seat_busy','request_busy','lease_lost','round_changed','gateway_unavailable'))
# The fixed free-model names (hosted_free_models.MODELS); a diagnostic never carries any other text.
FREE_PROVIDERS=frozenset(('zhipu','startlux','gemini','cloudflare-gemma','cloudflare-llama'))
FORMAT_ERRORS=frozenset(('invalid_json','invalid_action','invalid_sprint','invalid_usage','unknown'))


def clean(value):
    if not isinstance(value,dict):return {}
    out={}
    if isinstance(value.get('code'),str) and value['code'] in CODES:out['code']=value['code']
    if isinstance(value.get('provider'),str) and value['provider'] in FREE_PROVIDERS:out['provider']=value['provider']
    for key in ('upstream_called','blocked','diagnostics_saved'):
        if type(value.get(key)) is bool:out[key]=value[key]
    for key,low,high in [('upstream_http_status',100,599),('provider_error_code',0,99999999),
                         ('duration_ms',0,3600000),('retry_after_seconds',0,86400)]:
        n=value.get(key)
        if type(n) in (int,float) and math.isfinite(n) and low<=n<=high:out[key]=round(n) if key!='retry_after_seconds' else round(n,3)
    if isinstance(value.get('format_error'),str) and value['format_error'] in FORMAT_ERRORS:out['format_error']=value['format_error']
    return out


class ObservedAnswer(dict):
    def __init__(self,answer,diagnostic):
        super().__init__(answer);self.diagnostic=clean(diagnostic)


class ModelWait(RuntimeError):
    def __init__(self,diagnostic,message,clock=None):
        self.diagnostic=clean(diagnostic)
        self.retry_deadline=(clock or time.monotonic)()+self.diagnostic.get('retry_after_seconds',2)
        self.blocked=self.diagnostic.get('blocked') is True
        self.deferred=self.diagnostic.get('upstream_called') is False
        super().__init__(message)


def numeric_provider_code(value):
    if not isinstance(value,dict) or not isinstance(value.get('error'),dict):return None
    n=value['error'].get('code')
    if type(n) is int and 0<=n<=99999999:return n
    if isinstance(n,str) and n.isascii() and n.isdigit() and len(n)<=8:return int(n)
    return None


def response_issue(raw,payload,provider):
    import json,re
    try:
        data=json.loads(raw)
        if provider!='startlux':
            content=data['choices'][0]['message']['content']
            if not isinstance(content,str):return 'invalid_json'
            a=json.loads(re.sub(r'\s*```$','',re.sub(r'^```(?:json)?\s*','',content.strip())))
            if not isinstance(a,dict) or set(a)-{'choice','sprint'}:return 'invalid_json'
            if type(a.get('sprint',False)) is not bool:return 'invalid_sprint'
            choice=a.get('choice');usage=data.get('usage',{})
            if not isinstance(usage,dict) or any(type(usage.get(k,0)) is not int for k in ('prompt_tokens','completion_tokens')):return 'invalid_usage'
        else:
            choice=data['answers']['next_action']['choice']
            if 'sprint' in payload['questions'] and data['answers'].get('sprint',{}).get('choice') not in ('yes','no'):return 'invalid_sprint'
        if not isinstance(choice,str) or choice not in payload['questions']['next_action']['criteria']:return 'invalid_action'
    except Exception:return 'invalid_json'
    return 'unknown'
