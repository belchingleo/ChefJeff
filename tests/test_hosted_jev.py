"""Opt-in forwarding, fixed upstream, no credential retention and live HTTP isolation."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import io
import json
import threading
import time
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from hosted_jev import CONSENT_VERSION, ENDPOINT, ForwardError, JevForwarder, NoRedirect, TEST_PAYLOAD, parse_answer
from hosted_server import BrowserRelay, make_server
from cooperation_memory import memory_context

KEY = 'unit-test-jev-key-not-a-real-secret'
ANSWER = {'choice':'wait','sprint':False,'usage':{'input_tokens':3,'output_tokens':0}}


class UpstreamTests(unittest.TestCase):
    def test_fixed_url_model_headers_tls_defaults_and_filtered_reply(self):
        reply={'answers':{'next_action':{'type':'choice','choice':'wait','probabilities':{'private':KEY}}},
               'model':KEY,'usage':{'input_tokens':3,'output_tokens':0,'private':KEY},'debug':KEY}
        upstream=MagicMock();upstream.open.return_value.__enter__.return_value.read.return_value=json.dumps(reply).encode()
        with patch('hosted_jev.urllib.request.build_opener',return_value=upstream) as build:
            self.assertEqual(JevForwarder().send(KEY,TEST_PAYLOAD),ANSWER)
        self.assertIsInstance(build.call_args.args[0],NoRedirect)
        request=upstream.open.call_args.args[0]
        self.assertEqual(request.full_url,ENDPOINT)
        self.assertEqual(request.get_header('Authorization'),'Bearer '+KEY)
        self.assertIsNone(request.get_header('Origin'))
        self.assertEqual(json.loads(request.data)['model'],'jev-latest')
        self.assertEqual(upstream.open.call_args.kwargs['timeout'],18)
        self.assertEqual(upstream.open.return_value.__enter__.return_value.read.call_args.args,(262145,))

    def test_errors_never_include_provider_body_key_or_redirect_location(self):
        for status in (301,307,401,429,529):
            error=urllib.error.HTTPError(ENDPOINT,status,KEY,{'Location':'https://other.example/'+KEY},io.BytesIO(KEY.encode()))
            with self.subTest(status=status),patch('hosted_jev.urllib.request.build_opener') as build:
                build.return_value.open.side_effect=error
                with self.assertRaises(ForwardError) as result:JevForwarder().send(KEY,TEST_PAYLOAD)
                self.assertNotIn(KEY,str(result.exception))
                self.assertIn(str(status),str(result.exception))
                self.assertEqual(build.return_value.open.call_count,1)
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,KEY,{},'https://other.example'))
        with patch('hosted_jev.urllib.request.build_opener') as build:
            build.return_value.open.side_effect=urllib.error.URLError(KEY)
            with self.assertRaises(ForwardError) as result:JevForwarder().send(KEY,TEST_PAYLOAD)
            self.assertNotIn(KEY,str(result.exception))

    def test_invalid_action_usage_sprint_and_oversized_reply_rejected(self):
        bad=[{}, {'answers':[]}, {'answers':{'next_action':{'type':'choice','choice':'invented'}}},
             {'answers':{'next_action':{'type':'choice','choice':'wait'}},'usage':{'input_tokens':True}},
             {'answers':{'next_action':{'type':'choice','choice':'wait'}},'usage':{'output_tokens':-1}}]
        for d in bad:
            with self.subTest(reply=d),self.assertRaises(ForwardError):parse_answer(json.dumps(d).encode(),TEST_PAYLOAD)
        payload={**TEST_PAYLOAD,'questions':{**TEST_PAYLOAD['questions'],'sprint':{'criteria':{'yes':'Run','no':'Walk'}}}}
        with self.assertRaises(ForwardError):parse_answer(b'{"answers":{"next_action":{"type":"choice","choice":"wait"}}}',payload)
        with patch('hosted_jev.urllib.request.build_opener') as build:
            build.return_value.open.return_value.__enter__.return_value.read.return_value=b'x'*262145
            with self.assertRaises(ForwardError):JevForwarder().send(KEY,TEST_PAYLOAD)


class ForwardHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server=make_server(0,'http://127.0.0.1',capacity=4)
        self.origin='http://127.0.0.1:'+str(self.server.server_port);self.server.public_origin=self.origin
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.cleanup)
        self.calls=[]
        def send(key,payload):self.calls.append((key,payload));return dict(ANSWER)
        self.server.jev_forwarder.send=send

    def cleanup(self):
        self.server.shutdown();self.server.sessions.close();self.server.server_close();self.thread.join(2)

    def request(self,path,body=None,token=None,origin=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        headers={'Origin':origin or self.origin}
        if token:headers['X-ChefJeff-Session']=token
        if body is not None:headers['Content-Type']='application/json'
        try:
            c.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),headers)
            r=c.getresponse();return r.status,json.loads(r.read())
        finally:c.close()

    def page(self):
        status,data=self.request('/api/session',{});self.assertEqual(status,201)
        token=data['session'];game=self.server.sessions.get(token)
        return token,game

    def body(self,game,**extra):
        return {'game_id':game.game_id,'request_id':'connection-test','test':True,
                'consent':True,'consent_version':CONSENT_VERSION,'api_key':KEY,**extra}

    def forward(self,token,game,**extra):return self.request('/api/model/jev',self.body(game,**extra),token)

    def pending_task(self,game):
        game.phase='running';game.relay=BrowserRelay(game.c)
        task={'id':'server-created-task','payload':TEST_PAYLOAD,'event':threading.Event(),'result':None,'sent':time.monotonic()}
        game.relay.pending=task
        return task

    def test_no_consent_invalid_session_origin_fields_and_keys_never_call_upstream(self):
        token,game=self.page()
        cases=[{'consent':False},{'consent_version':'old'},{'api_key':'short'},{'api_key':'x'*2049},
               {'api_key':KEY+'\nheader'},{'api_key':KEY+'\u007f'},{'test':'true'},
               {'payload':{'invented':'state'}},{'base_url':'https://other.example'}]
        for extra in cases:
            with self.subTest(extra=extra):self.assertEqual(self.forward(token,game,**extra)[0],400)
        self.assertEqual(self.forward('invalid',game)[0],401)
        self.assertEqual(self.request('/api/model/jev',self.body(game),token,'https://other.example')[0],403)
        self.assertEqual(self.forward(token,game,game_id='old-round')[0],409)
        self.assertEqual(self.calls,[])
        self.assertNotIn(KEY,json.dumps(game.public_state()))

    def test_connection_test_deduplicates_throttles_and_never_retains_credentials(self):
        token,game=self.page()
        status,d=self.forward(token,game);self.assertEqual(status,200);self.assertEqual(d['answer'],ANSWER)
        self.assertEqual(self.forward(token,game),(status,d));self.assertEqual(len(self.calls),1)
        self.assertEqual(self.forward(token,game,request_id='another-test')[0],429)
        self.assertEqual(self.calls[0][1],TEST_PAYLOAD)
        for value in (game.public_state(),game.receipts,game.jev_receipts,game.k.snapshot(),game.positions):
            self.assertNotIn(KEY,str(value))
        self.assertIsNone(game.setting);self.assertFalse(game.connected)
        # Confirmation still follows the existing browser-ready flow.
        self.assertEqual(self.request('/api/browser-ready',{'game_id':game.game_id,'request_id':'ready','connected':True},token)[0],200)

    def test_live_memory_condition_is_bounded_recorded_and_frozen_for_the_round(self):
        token,game=self.page();task=self.pending_task(game)
        condition={'version':2,'enabled':True,'used_rounds':1,'omitted_rounds':0}
        result={'id':task['id'],'choice':'wait','sprint':False,'usage':{},'memory_condition':condition}
        self.assertEqual(self.request('/api/model/result',result,token)[0],200)
        self.assertEqual(game.round_memory_condition,{**condition,'source':'browser-reported'})
        from hosted_records import pilot_record
        self.assertEqual(pilot_record(game)['conditions']['cross_round_memory'],game.round_memory_condition)
        self.assertNotIn('episodes',json.dumps(pilot_record(game)['conditions']))
        task=self.pending_task(game);result['memory_condition']={**condition,'used_rounds':2}
        self.assertEqual(self.request('/api/model/result',result,token)[0],409)
        self.assertEqual(game.round_memory_condition['used_rounds'],1)
        result['memory_condition']={**condition,'api_key':KEY}
        status,body=self.request('/api/model/result',result,token)
        self.assertEqual(status,400);self.assertNotIn(KEY,str(body))

    def test_task_payload_is_server_created_and_other_kitchens_cannot_borrow_it(self):
        a,one=self.page();b,two=self.page();task=self.pending_task(one)
        two.phase='running'
        self.assertEqual(self.forward(b,two,test=False,id=task['id'])[0],409)
        self.assertEqual(self.calls,[])
        status,d=self.forward(a,one,test=False,id=task['id']);self.assertEqual(status,200)
        self.assertEqual(self.forward(a,one,test=False,id=task['id']),(status,d));self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][1],task['payload'])
        self.assertTrue(one.relay.resolve({'id':task['id'],**d['answer']}))
        task['id']='next-task';task['event']=threading.Event()
        self.assertEqual(self.forward(a,one,test=False,id='invented-task')[0],409)

    def test_slow_upstream_does_not_block_game_pause_and_late_answer_is_discarded(self):
        token,game=self.page();task=self.pending_task(game)
        # No AI object in this fixture: exercise the real cancellation and phase path.
        from types import SimpleNamespace
        game.ai=SimpleNamespace(invalidate=lambda:None)
        game.journal=lambda *_:None
        entered=threading.Event();release=threading.Event()
        def slow(key,payload):entered.set();release.wait(2);return dict(ANSWER)
        self.server.jev_forwarder.send=slow
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending=pool.submit(self.forward,token,game,test=False,id=task['id'])
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.forward(token,game,test=False,id=task['id'])[0],409)
                paused=pool.submit(self.request,'/api/pause',{'game_id':game.game_id,'request_id':'pause'},token)
                self.assertEqual(paused.result(timeout=.5)[0],200)
            finally:release.set()
            self.assertEqual(pending.result(timeout=1)[0],409)
        game.journal=None;game.ai=None

    def test_global_concurrency_bound_releases_after_failure(self):
        token,game=self.page();self.server.jev_forwarder.slots=threading.BoundedSemaphore(1)
        self.server.jev_forwarder.slots.acquire()
        self.assertEqual(self.forward(token,game)[0],503);self.assertEqual(self.calls,[])
        self.server.jev_forwarder.slots.release()
        def fail(*_):raise ForwardError(502,'试玩服务器无法连接 Jev，请稍后重试。')
        self.server.jev_forwarder.send=fail
        self.assertEqual(self.forward(token,game)[0],502)
        self.assertTrue(self.server.jev_forwarder.slots.acquire(blocking=False))
        self.server.jev_forwarder.slots.release()
        self.assertTrue(game.jev_gate.acquire(blocking=False));game.jev_gate.release()


if __name__=='__main__':unittest.main()
