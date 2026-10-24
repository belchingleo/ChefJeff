"""Live loopback boundaries; upstream requests stay in BrowserRelay, never a provider."""
import http.client
import json
import tempfile
import threading
import time
import unittest
import uuid
from hosted_records import CONSENT_VERSION
from hosted_server import make_server
from research_record import validate_record


class ResearchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=make_server(0,'http://127.0.0.1',data_dir=self.tmp.name)
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        self.server.public_origin=self.origin
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.cleanup)
        status,data=self.request('/api/session',{})
        self.assertEqual(status,201);self.token=data['session'];self.game=self.server.sessions.get(self.token)

    def cleanup(self):
        self.server.shutdown();self.server.sessions.close();self.server.server_close();self.thread.join(2);self.tmp.cleanup()

    def request(self,path,body,token=None,origin=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        headers={'Origin':origin or self.origin,'Content-Type':'application/json'}
        if token:headers['X-ChefJeff-Session']=token
        conn.request('POST',path,json.dumps(body),headers)
        response=conn.getresponse();raw=response.read();status=response.status;conn.close()
        return status,json.loads(raw)

    def command(self,path,**body):
        return self.request('/api/'+path,{'game_id':self.game.game_id,'request_id':uuid.uuid4().hex,**body},self.token)

    def begin(self,telemetry=False,model_identity=None):
        self.assertEqual(self.command('browser-ready',connected=True)[0],200)
        self.assertEqual(self.command('contribution/consent',consent=True,consent_version=CONSENT_VERSION,decision_telemetry=telemetry,model_identity=model_identity)[0],200)
        status,data=self.command('start');self.assertEqual(status,200)
        return data['receipt']

    def browser_answer(self, choice, stale=False):
        """Exercise the real relay worker and scheduler, with no upstream model call."""
        with self.game.lock:
            self.game.ai.poll()
        deadline=time.monotonic()+2
        pending=None
        while time.monotonic()<deadline:
            pending=self.game.relay.request()
            if pending:break
            time.sleep(.005)
        self.assertIsNotNone(pending)
        self.assertEqual(self.request('/api/model/result',{
            'id':pending['id'],'choice':choice,'sprint':False,
            'usage':{'input_tokens':6500,'output_tokens':1},
            'telemetry':{'duration_ms':100,'error_type':None},
            'memory_condition':{'enabled':True,'version':2,'used_rounds':0,'omitted_rounds':0},
        },self.token)[0],200)
        deadline=time.monotonic()+2
        while self.game.ai.q.empty() and time.monotonic()<deadline:time.sleep(.005)
        self.assertFalse(self.game.ai.q.empty())
        with self.game.lock:
            if stale:self.game.ai.invalidate()
            self.game.ai.poll()
            self.game.k.advance(.2)

    def begin_manual_relay(self):
        with self.game.lock:
            self.game.stop_event.set();self.game.wake.set()
        return self.begin(True)

    def test_custom_model_identity_persists_with_states_and_decisions(self):
        with self.game.lock:
            self.game.stop_event.set();self.game.wake.set()
        identity={'provider':'compatible','model_id':'studio/not-in-presets-v2:fast'}
        receipt=self.begin(True,identity)
        initial=self.game.store.download(receipt['id'],receipt['deletion_token'])
        self.assertEqual(initial['conditions']['model_identity']['model_id'],identity['model_id'])
        self.browser_answer('wait')
        self.assertEqual(self.command('end')[0],200)
        # A newly armed model belongs to the next round, never the finished one.
        other={'provider':'openrouter-chat','model_id':'other/new-model'}
        self.assertEqual(self.command('contribution/consent',consent=True,consent_version=CONSENT_VERSION,model_identity=other)[0],200)
        status,data=self.request('/api/contribution/download',{k:receipt[k] for k in ('id','deletion_token')})
        self.assertEqual(status,200);r=data['record'];validate_record(r)
        self.assertEqual(r['conditions']['model_identity'],{**identity,'interface':'chat_completions','source':'browser-reported','verified':False})
        self.assertTrue(any(e['type']=='state_checkpoint' for e in r['events']))
        self.assertTrue(any(e['type']=='ai_response' and e['payload']['choice']['key']=='wait' for e in r['events']))
        self.assertNotIn('api_key',json.dumps(r))

    def test_manual_model_metadata_requires_current_consent_and_cannot_relabel_saved_round(self):
        self.assertEqual(self.command('browser-ready',connected=True)[0],200)
        self.assertEqual(self.command('start')[0],200)
        self.assertEqual(self.command('end')[0],200)
        identity={'provider':'openrouter-decision','model_id':'lab/custom-decision'}
        self.assertEqual(self.command('contribution/save',consent=True,consent_version='pilot-session-2026-10-v4',model_identity=identity)[0],400)
        status,data=self.command('contribution/save',consent=True,consent_version=CONSENT_VERSION,model_identity=identity)
        self.assertEqual(status,200);receipt=data['receipt']
        self.assertEqual(self.command('contribution/save',consent=True,consent_version=CONSENT_VERSION,model_identity={'provider':'compatible','model_id':'changed-after-round'})[0],200)
        saved=self.game.store.download(receipt['id'],receipt['deletion_token'])
        self.assertEqual(saved['conditions']['model_identity']['model_id'],'lab/custom-decision')
        self.assertEqual(saved['conditions']['model_identity']['interface'],'systemone')

    def test_model_descriptor_rejects_connection_secrets_and_verification_claims(self):
        for identity in [
            {'provider':'compatible','model_id':'model','api_key':'synthetic-secret'},
            {'provider':'compatible','model_id':'model','base_url':'https://private.example'},
            {'provider':'compatible','model_id':'model','verified':True},
            {'provider':'unknown','model_id':'model'},
            {'provider':'compatible','model_id':'https://private.example/model'},
        ]:
            with self.subTest(identity=identity):
                self.assertEqual(self.command('contribution/consent',consent=True,consent_version=CONSENT_VERSION,model_identity=identity)[0],400)
                self.assertIsNone(self.game.research_armed)

    def saved_null_action_response(self, receipt, choice, applied):
        status,data=self.request('/api/contribution/download',{
            key:receipt[key] for key in ('id','deletion_token')})
        self.assertEqual(status,200)
        record=data['record']
        self.assertGreaterEqual(record['duration'],.2)
        self.assertIsNotNone(record['ended_at'])
        self.assertTrue(record['quality']['complete'])
        validate_record(record)
        response=next(e for e in record['events'] if e['type']=='ai_response')
        self.assertEqual(response['payload']['choice']['key'],choice)
        self.assertEqual(response['payload']['applied'],applied)
        self.assertIsNone(response['action_id'])
        self.assertNotIn('action_id',response['payload'])
        self.assertIsNone(self.game.research_error)
        return record

    def test_wait_response_survives_finish_save_and_own_download(self):
        receipt=self.begin_manual_relay()
        self.browser_answer('wait')
        self.assertEqual(self.command('end')[0],200)
        self.saved_null_action_response(receipt,'wait',True)

    def test_continue_response_survives_page_close_save_and_own_download(self):
        receipt=self.begin_manual_relay()
        with self.game.lock:self.assertTrue(self.game.k.command('jeff','fetch')[0])
        self.browser_answer('continue')
        self.assertEqual(self.request('/api/session/close',{},self.token)[0],200)
        record=self.saved_null_action_response(receipt,'continue',True)
        self.assertEqual(record['termination']['session_close']['reason'],'page_close_request')

    def test_stale_choice_with_no_applied_action_still_saves_the_round(self):
        receipt=self.begin_manual_relay()
        self.browser_answer('fetch',stale=True)
        self.assertEqual(self.command('end')[0],200)
        self.saved_null_action_response(receipt,'fetch',False)

    def test_preview_exact_saved_projection_and_own_download_delete(self):
        receipt=self.begin()
        with self.game.lock:self.game.k.command('human','fetch');self.game.k.advance(1.2)
        self.assertEqual(self.command('end')[0],200)
        status,preview=self.command('contribution/preview');self.assertEqual(status,200)
        status,saved=self.request('/api/contribution/download',{'id':receipt['id'],'deletion_token':receipt['deletion_token']})
        self.assertEqual(status,200);self.assertEqual(preview['record'],saved['record']);validate_record(saved['record'])
        self.assertEqual(self.request('/api/contribution/download',{'id':receipt['id'],'deletion_token':'bad'})[0],404)
        self.assertEqual(self.request('/api/contribution/download',receipt)[0],400)
        credentials={key:receipt[key] for key in ('id','deletion_token')}
        self.assertEqual(self.request('/api/contribution/delete',credentials)[0],200)
        self.assertEqual(self.request('/api/contribution/download',credentials)[0],404)
        self.game._persist_research()
        self.assertEqual(self.request('/api/contribution/download',credentials)[0],404)

    def test_other_page_origin_and_arbitrary_metadata_are_rejected(self):
        self.assertEqual(self.command('contribution/preview')[0],409)
        self.assertEqual(self.command('contribution/consent',consent=True,consent_version='old')[0],400)
        self.assertEqual(self.command('contribution/consent',consent=True,consent_version=CONSENT_VERSION,provider_url='private')[0],400)
        self.begin()
        body={'game_id':self.game.game_id,'request_id':'isolated'}
        self.assertEqual(self.request('/api/contribution/preview',body,'invalid')[0],401)
        self.assertEqual(self.request('/api/contribution/preview',body,self.token,'https://other.example')[0],403)
        status,other=self.request('/api/session',{})
        self.assertEqual(self.request('/api/contribution/preview',body,other['session'])[0],409)

    def test_telemetry_requires_current_optional_consent_and_marks_claims(self):
        with self.game.lock:
            self.game.stop_event.set();self.game.wake.set()  # deterministic manual pending-task fixture
        self.begin(False)
        # Construct the server-owned pending task from its real action interface.
        with self.game.lock:
            payload=self.game.relay.payload(self.game.k.snapshot(),self.game.k.actions('jeff'))
            self.game.relay.pending={'id':'controlled-pending','payload':payload,'event':threading.Event(),
                                     'result':None,'sent':time.monotonic()}
        body={'id':'controlled-pending','choice':'wait','sprint':False,'telemetry':{'duration_ms':55,'error_type':None}}
        self.assertEqual(self.request('/api/model/result',body,self.token)[0],400)
        self.command('end');self.command('reset');self.begin(True)
        with self.game.lock:
            payload=self.game.relay.payload(self.game.k.snapshot(),self.game.k.actions('jeff'))
            self.game.relay.pending={'id':'controlled-pending','payload':payload,'event':threading.Event(),
                                     'result':None,'sent':time.monotonic()}
        forged={**body,'telemetry':{**body['telemetry'],'model':'private-name'}}
        self.assertEqual(self.request('/api/model/result',forged,self.token)[0],400)
        self.assertEqual(self.request('/api/model/result',body,self.token)[0],200)
        rows=[r for r in self.game.session_log.records if r['type']=='client_telemetry']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['payload']['source'],'client-reported')
        self.assertFalse(rows[0]['payload']['provider_verified'])

if __name__=='__main__':unittest.main()
