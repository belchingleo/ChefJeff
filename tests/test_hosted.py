import json
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path
import http.client
from hosted_server import HostedSession, BrowserRelay, Sessions, make_server, hosted_html, SHELL_REPLACEMENTS, CONTRIBUTION_SLOT
from kitchen import Food, load_config


class HostedTests(unittest.TestCase):
    def test_never_loads_machine_credentials_or_journals(self):
        with patch('jev.load_key', side_effect=AssertionError('Must not read keys')), patch('play.Journal', side_effect=AssertionError('No journal')):
            s = HostedSession()
            try:
                self.assertEqual(s._command('/api/start', {})[0], 428)
                self.assertEqual(s._command('/api/browser-ready', {'connected':True})[0], 200)
                self.assertEqual(s._command('/api/start', {})[0], 200)
                self.assertEqual(s.public_state()['hosted']['retention'], 'session-only')
                self.assertEqual(s._command('/api/communicate', {'code':'wash'})[0], 200)
                s.tick()
                self.assertIsNotNone(s.relay)
            finally:s.close()

    def test_kitchens_are_isolated_and_expire(self):
        sessions = Sessions(capacity=2, ttl=600)
        try:
            a, b = sessions.create(), sessions.create()
            self.assertNotEqual(a,b)
            self.assertIsNone(sessions.create())
            one, two = sessions.get(a), sessions.get(b)
            one._command('/api/limits', {'max_calls':7})
            self.assertNotEqual(two.c['ai_max_calls'],7)
            self.assertNotEqual(one.game_id,two.game_id)
            self.assertIsNone(sessions.get('invalid'))
            sessions.entries[a] = (one,time.monotonic()-601)
            sessions.reap()
            self.assertIsNone(sessions.get(a))
            self.assertTrue(one.stop_event.is_set())
        finally:sessions.close()

    def test_relay_validates_and_strips_provider_text(self):
        r = BrowserRelay(load_config());results=[]
        payload={'questions':{'next_action':{'criteria':{'wait':'Wait'}}}}
        thread=threading.Thread(target=lambda:results.append(r.ask(payload)));thread.start()
        for _ in range(100):
            if r.request():break
            time.sleep(.005)
        task=r.request()
        self.assertFalse(r.resolve({'id':'wrong','choice':'wait','sprint':False}))
        self.assertFalse(r.resolve({'id':task['id'],'choice':'bogus','sprint':False}))
        self.assertFalse(r.resolve({'id':task['id'],'choice':'wait','sprint':False,'usage':{'input_tokens':-1}}))
        self.assertTrue(r.resolve({'id':task['id'],'choice':'wait','sprint':False}))
        thread.join(1)
        self.assertEqual(results[0]['model'],'browser-model')
        self.assertIsNone(r.request())
        r.close()

    def test_cancel_unblocks_waiter(self):
        r=BrowserRelay(load_config());errors=[]
        def ask():
            try:r.ask({'questions':{}})
            except RuntimeError as e:errors.append(str(e))
        t=threading.Thread(target=ask);t.start()
        for _ in range(100):
            if r.request():break
            time.sleep(.005)
        r.cancel();t.join(1)
        self.assertFalse(t.is_alive());self.assertEqual(len(errors),1)

    def test_privacy_markup_only_affects_hosted_page(self):
        raw=(Path(__file__).resolve().parents[1]/'cocos-kitchen/build/web/index.html').read_bytes()
        html=hosted_html(raw).decode()
        self.assertIn('<head><script src="/hosted-agent.js">',html)
        self.assertIn('browser localStorage',html)
        self.assertNotIn('记住后以明文保存在这台电脑的本地配置文件',html)
        self.assertIn('<section hidden aria-labelledby="memory-title"',html)
        self.assertNotIn(b'hosted-agent.js',raw)
    def test_web_shell_keeps_every_hosted_anchor(self):
        shell=(Path(__file__).resolve().parents[1]/'cocos-kitchen/web-shell.html').read_text()
        for old,_ in SHELL_REPLACEMENTS:self.assertIn(old,shell)
        self.assertIn(CONTRIBUTION_SLOT,shell)
        html=hosted_html(('<head></head>'+shell).encode()).decode()
        self.assertIn('contribution-save',html);self.assertNotIn(CONTRIBUTION_SLOT,html)


class HostedHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(0,'http://127.0.0.1')
        cls.port=cls.server.server_address[1]
        cls.origin='http://127.0.0.1:'+str(cls.port)
        cls.server.public_origin=cls.origin
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.sessions.close();cls.server.server_close();cls.thread.join(2)
    def request(self,path,body=None,token=None,origin=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        headers={'Origin':origin or self.origin}
        if token:headers['X-ChefJeff-Session']=token
        if body is not None:headers['Content-Type']='application/json'
        c.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),headers)
        r=c.getresponse();raw=r.read();status=r.status;c.close()
        return status,raw
    def test_auth_csrf_secret_rejection_and_two_sessions(self):
        self.assertEqual(self.request('/api/state')[0],401)
        self.assertEqual(self.request('/api/session',{},origin='https://bad.example')[0],403)
        _,raw=self.request('/api/session',{});a=json.loads(raw)['session']
        _,raw=self.request('/api/session',{});b=json.loads(raw)['session']
        _,raw=self.request('/api/state',token=a);s=json.loads(raw)
        _,raw=self.request('/api/state',token=b);other=json.loads(raw)
        self.assertNotEqual(s['game_id'],other['game_id'])
        body={'game_id':s['game_id'],'request_id':'test','connected':True,'api_key':'unit-test-placeholder'}
        status,raw=self.request('/api/browser-ready',body,a)
        self.assertEqual(status,400);self.assertNotIn(b'unit-test-placeholder',raw)
        self.assertEqual(self.request('/api/connection',body,a)[0],400)
        body.pop('api_key')
        self.assertEqual(self.request('/api/browser-ready',body,a)[0],200)
        self.assertEqual(self.request('/api/browser-ready',body,b)[0],409)
    def test_static_paths_and_injection(self):
        self.assertEqual(self.request('/../../config.json')[0],404)
        status,raw=self.request('/')
        self.assertEqual(status,200);self.assertIn(b'/hosted-agent.js',raw)
        self.assertEqual(self.request('/hosted-agent.js')[0],200)

    def test_shipped_audio_is_served_with_audio_mime_type(self):
        files = list((self.server.web_root / 'assets/resources/native').rglob('*.mp3'))
        self.assertTrue(files, 'The web build must include its game audio.')
        for file in files:
            with self.subTest(asset=file.name):
                c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
                try:
                    c.request('GET', '/' + file.relative_to(self.server.web_root).as_posix())
                    response = c.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.getheader('Content-Type'), 'audio/mpeg')
                    self.assertEqual(response.read(), file.read_bytes())
                finally:
                    c.close()

    def test_aimed_throw_crosses_hosted_http_and_keeps_direction_validation(self):
        _, raw = self.request('/api/session', {})
        token = json.loads(raw)['session']
        game = self.server.sessions.get(token)
        try:
            with game.lock:
                game._command('/api/browser-ready', {'connected':True})
                game._command('/api/start', {})
                game.k.positions['human'] = (3., 5.)
                game.k.positions['jeff'] = (10., 2.)
                game.k.chefs['human'].hand = Food('aimed-food', 'raw', ingredient='tomato')
                # Freeze automatic ticks while exercising the HTTP boundary.
                game.stop_event.set()
            base = {'game_id':game.game_id, 'expected_item':'aimed-food'}
            for i, direction in enumerate(([0,0], [True,1], [0], [0,10001])):
                status, _ = self.request('/api/throw', {**base, 'request_id':f'invalid-aim-{i}',
                                                       'direction':direction}, token)
                self.assertEqual(status, 400)
                self.assertEqual(game.k.chefs['human'].hand.id, 'aimed-food')
            status, raw = self.request('/api/throw', {**base, 'request_id':'valid-aim',
                                                     'direction':[0,1]}, token)
            self.assertEqual(status, 200, raw)
            with game.lock:
                game.k.advance(1)
                self.assertIsNone(game.k.chefs['human'].hand)
                item = game.k.ground['aimed-food']
                self.assertEqual(game.k.cell(item.location)[0], 3)
                self.assertGreater(game.k.cell(item.location)[1], 5)
                game.k.assert_invariants()
        finally:
            game.close()


if __name__=='__main__':unittest.main()
