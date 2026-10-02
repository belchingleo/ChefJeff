"""Player-owned credentials for the local, single-kitchen web demo."""
import ipaddress
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from kitchen import ROOT
from web_server import GameSession
from whitebox_server import SpatialJevClient
from model_language import english_data
from cooperation_memory import CooperationMemory, round_scope, episode, ROUNDS
from release_info import release_info
from feedback import feedback_report


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'Redirect refused', headers, fp)


def settings_from(body):
    provider=body.get('provider')
    if provider not in ('jev','deepseek','compatible'):
        raise ValueError('请选择 API 服务。')
    key=body.get('api_key')
    if not isinstance(key,str) or not 8<=len(key.strip())<=2048 or any(c.isspace() for c in key.strip()):
        raise ValueError('请填写完整的 API Key，不要包含空格或换行。')
    defaults={'jev':('https://api.typesafe.ai/v1','jev-latest'),'deepseek':('https://api.deepseek.com','deepseek-flash')}
    base,model=defaults.get(provider,(body.get('base_url',''),body.get('model','')))
    if provider=='deepseek':model=body.get('model') or model
    if not isinstance(base,str) or not isinstance(model,str) or not model.strip() or len(model)>120:
        raise ValueError('请填写接口地址和模型名称。')
    base=base.strip().rstrip('/')
    if base.endswith('/chat/completions'):base=base[:-17].rstrip('/')
    u=urllib.parse.urlsplit(base)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError('接口地址需要是 HTTPS Base URL，不能包含密码、查询参数或片段。')
    host=u.hostname.lower()
    if host=='localhost' or host.endswith(('.localhost','.local','.internal')):
        raise ValueError('第一版仅支持公网 HTTPS 模型接口。')
    try:address=ipaddress.ip_address(host)
    except ValueError:address=None
    if address is not None and not address.is_global:raise ValueError('不支持内网接口地址。')
    if type(body.get('remember',False)) is not bool:raise ValueError('保存选项无效。')
    return {'provider':provider,'base_url':base,'model':model.strip(),'api_key':key.strip(),'remember':body.get('remember',False)}


class CompatibleClient(SpatialJevClient):
    def __init__(self,config,setting):
        super().__init__(config,key=setting['api_key'])
        self.setting=setting
    def payload(self,state,actions):
        payload=super().payload(state,actions)
        payload['model']=self.setting['model']
        return payload
    def ask(self,payload):
        payload=english_data(payload)
        started=time.monotonic()
        body={'model':self.setting['model'],'messages':[
            {'role':'system','content':'You control the blue chef in a shared kitchen. Using the supplied state and rules, choose exactly one action key from questions.next_action.criteria. Return only a JSON object, for example {"choice":"wait"}. If questions.sprint is present, also return a boolean sprint (true or false) in the same JSON object. Do not explain or choose an action outside the candidate set.'},
            {'role':'user','content':json.dumps({'state':payload['state'],'questions':payload['questions']},ensure_ascii=False)}],
            'max_tokens':128}
        if self.setting['provider']=='deepseek':
            body['response_format']={'type':'json_object'}
            body['thinking']={'type':'disabled'}
        req=urllib.request.Request(self.setting['base_url']+'/chat/completions',data=json.dumps(body).encode(),
            headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
        try:
            with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as r:data=json.load(r)
        except urllib.error.HTTPError as e:raise RuntimeError(f'模型接口 HTTP {e.code}') from None
        except (OSError,ValueError):raise RuntimeError('模型接口连接失败或返回了无效数据') from None
        try:
            content=data['choices'][0]['message']['content'].strip()
            if content.startswith('```'):
                content=content.split('\n',1)[1].rsplit('```',1)[0].strip()
            parsed=json.loads(content)
            choice=parsed['choice']
            if 'sprint' in payload['questions'] and type(parsed.get('sprint')) is not bool:raise ValueError()
            if not isinstance(choice,str) or choice not in payload['questions']['next_action']['criteria']:raise ValueError()
            usage=data.get('usage') or {}
            return {'sprint':parsed.get('sprint',False),'choice':choice,'confidence':None,'probabilities':{},'model':self.setting['model'],
                    'usage':{'input_tokens':int(usage.get('prompt_tokens',0)),'output_tokens':int(usage.get('completion_tokens',0))},
                    'latency':time.monotonic()-started}
        except (KeyError,IndexError,TypeError,AttributeError,ValueError):
            raise RuntimeError('模型没有返回可执行的合法动作；本次不执行。') from None


def create_client(config,setting):
    if setting['provider']=='jev':return SpatialJevClient(config,key=setting['api_key'])
    return CompatibleClient(config,setting)


class PlayerGameSession(GameSession):
    def __init__(self,*args,credential_path=None,memory_path=None,connector=create_client,**kwargs):
        self.credential_path=Path(credential_path or ROOT/'.player-api.json')
        self.connector=connector
        self.setting=None
        self.connecting=False
        self.connection_checks=0
        if self.credential_path.is_file():
            try:self.setting=settings_from(json.loads(self.credential_path.read_text()))
            except (OSError,ValueError,TypeError):pass
        super().__init__(*args,client_factory=self._player_client,**kwargs)
        self.memory = CooperationMemory(memory_path or self.credential_path.parent/'.player-memory.json')
        self.round_memory = None
        self.release = release_info()
        if self.setting and self.setting['provider']!='jev':self.c['ai_max_response_age']=15
    def _player_client(self,config):
        if not self.setting:raise RuntimeError('需要配置玩家 API')
        return self.connector(config,self.setting.copy())
    def connection_state(self):
        s=self.setting or {}
        return {'configured':bool(s),'provider':s.get('provider','jev'),'base_url':s.get('base_url',''),
                'model':s.get('model',''),'remembered':s.get('remember',False),
                'editable':self.phase in ('ready','ended') and not self.connecting}
    def public_state(self):
        with self.lock:
            state=super().public_state();state['connection']=self.connection_state()
            state['memory']=self.memory_state()
            state['release']=self.release
            state['limits']=self.limit_state()
            return state
    def limit_state(self):
        ai=self.ai
        limit=ai.call_limit if ai else self.c.get('ai_max_calls',200)
        calls=ai.calls if ai else 0
        return {'max_calls':limit,'next_max_calls':self.c.get('ai_max_calls',200),'calls':calls,'remaining':max(0,limit-calls),
                'reached':calls>=limit,'editable':self.phase in ('ready','ended') and not self.connecting,
                'connection_checks':self.connection_checks,
                'usage':dict(ai.tokens) if ai else {'input_tokens':0,'output_tokens':0},
                'usage_scope':'successful_responses_only'}
    def memory_state(self):
        scope=round_scope(self.setting or {},self.k)
        rounds=self.memory.data['scopes'].get(scope,[])
        return {'enabled':self.memory.data['enabled'],'saved_rounds':len(rounds),'limit':ROUNDS,
                'editable':self.phase in ('ready','ended') and not self.connecting,
                'error':self.memory.error,
                'used_rounds':len(self.round_memory['episodes']) if self.round_memory else 0}
    def _finish(self,aborted=False):
        if self.journal and not aborted and self.k.ended and self.round_memory and self.round_memory['enabled']:
            try:
                self.memory.remember(round_scope(self.setting or {},self.k),
                                     episode(self.k,self.game_id,getattr(self.ai,'actual_model',None)))
            except OSError:
                self.memory.error='本局已结束，但跨局记录未能保存；请检查本地文件权限。'
                self.note(self.memory.error)
        super()._finish(aborted)
    def _command(self,path,body):
        if path=='/api/limits':
            if not self.limit_state()['editable']:
                return 409,{'error':'请在开局前或结算后修改下一局调用上限。'}
            limit=body.get('max_calls')
            if type(limit) is not int or not 1<=limit<=2000:
                return 400,{'error':'调用上限须为 1–2000 的整数。'}
            self.c['ai_max_calls']=limit
            # Finished round usage remains tied to its original limit.
            return 200,{'ok':True,'next_max_calls':limit}
        if path in ('/api/feedback','/api/export-run'):
            return 200,{'ok':True,'report':feedback_report(self)}
        if path=='/api/memory':
            if not self.memory_state()['editable']:
                return 409,{'error':'请在开局前或结算后修改记忆设置，保证一局内条件一致。'}
            enabled=body.get('enabled')
            clear=body.get('clear',False)
            if (enabled is not None and type(enabled) is not bool) or type(clear) is not bool:
                return 400,{'error':'记忆设置无效。'}
            if enabled is None and not clear:
                return 400,{'error':'没有指定记忆操作。'}
            try:self.memory.configure(enabled,clear)
            except OSError:return 500,{'error':'无法保存记忆设置，请检查本地文件权限。'}
            return 200,{'ok':True,'memory':self.memory_state()}
        if path in ('/api/start','/api/restart') and self.connecting:
            return 409,{'error':'正在测试连接，请等测试完成后再开局。'}
        if path in ('/api/start','/api/restart') and not self.setting:
            return 428,{'error':'请先打开 API 设置，连接你自己的账号。不会使用开发者的 Key。'}
        result=super()._command(path,body)
        if path=='/api/start' and result[0]==200:
            self.round_memory=self.memory.context(round_scope(self.setting,self.k))
            self.ai.cooperation_memory=self.round_memory
            self.journal('memory_context',self.round_memory)
            self.journal('release',self.release)
        if path=='/api/reset' and result[0]==200:self.round_memory=None
        return result
    def command(self,path,body):
        if path!='/api/connection':return super().command(path,body)
        request_id=body.get('request_id')
        with self.lock:
            if body.get('game_id')!=self.game_id:return 409,{'error':'对局已变化，请重试。'}
            if not isinstance(request_id,str) or not 1<=len(request_id)<=100:return 400,{'error':'请求无效。'}
            if request_id in self.receipts:return self.receipts[request_id]
            if self.phase not in ('ready','ended') or self.connecting:
                return 409,{'error':'请在开局前或结算后修改连接；请完成当前对局后再修改。'}
            if body.get('clear') is True:
                try:self.credential_path.unlink(missing_ok=True)
                except OSError:return 500,{'error':'无法清除保存的连接，请检查文件权限。'}
                self.setting=None
                # Dispose the finished round's client reference too.
                if self.ai and self.ai.closed:self.ai=None
                response=(200,{'ok':True,'connection':self.connection_state()})
                self.receipts[request_id]=response
                while len(self.receipts)>128:self.receipts.popitem(last=False)
                return response
            try:setting=settings_from(body)
            except ValueError as e:return 400,{'error':str(e)}
            self.connecting=True
        try:
            client=self.connector(self.c,setting)
            with self.lock:self.connection_checks+=1
            client.ask({'model':setting['model'],'state':{'purpose':'API connection check'},
                'questions':{'next_action':{'type':'choice','instructions':'Choose ready and return the required format.','criteria':{'ready':'Connection ready'}}}})
            with self.lock:
                if body['game_id']!=self.game_id or self.phase not in ('ready','ended'):
                    return 409,{'error':'对局已变化，连接未保存。'}
                if setting['remember']:
                    fd,name=tempfile.mkstemp(prefix='.player-api-',dir=self.credential_path.parent)
                    try:
                        with os.fdopen(fd,'w') as f:json.dump(setting,f)
                        os.replace(name,self.credential_path)
                    finally:
                        if os.path.exists(name):os.unlink(name)
                else:self.credential_path.unlink(missing_ok=True)
                self.setting=setting
                if self.ai and self.ai.closed:self.ai=None
                self.c['ai_max_response_age']=6 if setting['provider']=='jev' else 15
                response=(200,{'ok':True,'connection':self.connection_state()})
                self.receipts[request_id]=response
                while len(self.receipts)>128:self.receipts.popitem(last=False)
                return response
        except Exception as e:
            # Never echo an upstream body, key, or arbitrary provider exception.
            message='连接失败。请检查地址、模型名、Key、余额及网络。'
            if type(e) is RuntimeError:
                for code in ('401','403','402','429'):
                    if 'HTTP '+code in str(e):message={'401':'Key 无效，请检查后重试。','403':'账号无权访问这个模型。','402':'账号余额不足，请到服务商充值。','429':'请求受限或额度不足，请稍后重试。'}[code]
            return 502,{'error':message}
        finally:
            with self.lock:self.connecting=False
