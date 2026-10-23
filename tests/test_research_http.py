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

    def begin(self,telemetry=False):
        self.assertEqual(self.command('browser-ready',connected=True)[0],200)
        self.assertEqual(self.command('contribution/consent',consent=True,consent_version=CONSENT_VERSION,decision_telemetry=telemetry)[0],200)
        status,data=self.command('start');self.assertEqual(status,200)
        return data['receipt']

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
