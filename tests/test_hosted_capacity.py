"""Active-slot admission, leases, isolated budgets and real concurrent HTTP starts."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from types import SimpleNamespace
import threading
import time
import unittest

from hosted_capacity import ActiveKitchens, RequestBudget
from hosted_server import make_server, Sessions, HostedSession


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.slots = ActiveKitchens(1, clock=lambda:self.now)
        self.entries = {key:(SimpleNamespace(phase='ready'),0) for key in ('a','b')}

    def begin(self, token):
        allocation = self.slots.reserve(token, self.entries)
        self.assertIsNotNone(allocation)
        self.entries[token][0].phase = 'running'
        self.slots.settle(token, self.entries, allocation, True)

    def test_browsing_does_not_hold_an_active_slot_and_pending_admission_does(self):
        self.assertTrue(self.slots.describe('a',self.entries)['can_start'])
        allocated = self.slots.reserve('a',self.entries)
        self.assertIs(allocated,True)
        self.assertIsNone(self.slots.reserve('b',self.entries))
        self.assertFalse(self.slots.describe('b',self.entries)['can_start'])
        self.slots.settle('a',self.entries,allocated,False)
        self.assertTrue(self.slots.describe('b',self.entries)['can_start'])

    def test_polling_does_not_extend_pause_or_result_leases(self):
        self.begin('a')
        self.entries['a'][0].phase = 'paused'
        self.slots.refresh(self.entries)
        for self.now in (10,30,59):
            self.assertFalse(self.slots.describe('b',self.entries)['can_start'])
        self.now = 60
        self.assertTrue(self.slots.describe('b',self.entries)['can_start'])
        self.begin('b')
        self.entries['b'][0].phase = 'ended'
        self.slots.refresh(self.entries)
        self.now = 89
        self.assertFalse(self.slots.describe('a',self.entries)['can_start'])
        self.now = 90
        self.assertTrue(self.slots.describe('a',self.entries)['can_start'])

    def test_resume_and_next_round_keep_the_existing_slot_and_failure_keeps_its_deadline(self):
        self.begin('a')
        self.entries['a'][0].phase='ended'
        self.slots.refresh(self.entries)
        self.now=20
        self.assertIs(self.slots.reserve('a',self.entries),False)
        self.slots.settle('a',self.entries,False,False)
        self.assertEqual(self.slots.leases['a']['until'],30)
        self.assertIs(self.slots.reserve('a',self.entries),False)
        self.entries['a'][0].phase='running'
        self.slots.settle('a',self.entries,False,True)
        self.now=1000
        self.assertFalse(self.slots.describe('b',self.entries)['can_start'])
        del self.entries['a']
        self.assertTrue(self.slots.describe('b',self.entries)['can_start'])

    def test_independent_request_budgets_refill_and_bound_bursts(self):
        a=RequestBudget(rate=40,burst=40,clock=lambda:self.now)
        b=RequestBudget(rate=40,burst=40,clock=lambda:self.now)
        self.assertTrue(all(a.take() for _ in range(40)))
        self.assertFalse(a.take())
        self.assertTrue(b.take())
        self.now=.025
        self.assertTrue(a.take())
        self.assertFalse(a.take())
        self.now=100
        self.assertTrue(all(a.take() for _ in range(40)))
        self.assertFalse(a.take())


class AdmissionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server=make_server(0,'http://127.0.0.1',capacity=2,max_waiting=10)
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        self.server.public_origin=self.origin
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown();self.server.sessions.close();self.server.server_close();self.thread.join(2)

    def request(self,path,body=None,token=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            headers={'Origin':self.origin}
            if token:headers['X-ChefJeff-Session']=token
            if body is not None:headers['Content-Type']='application/json'
            c.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),headers)
            r=c.getresponse()
            return r.status,json.loads(r.read())
        finally:c.close()

    def page(self):
        status,d=self.request('/api/session',{})
        self.assertEqual(status,201)
        token=d['session']
        status,s=self.request('/api/state',token=token)
        self.assertEqual(status,200)
        body={'game_id':s['game_id'],'request_id':'connect','connected':True}
        self.assertEqual(self.request('/api/browser-ready',body,token)[0],200)
        return token,s['game_id']

    def test_ten_waiting_pages_do_not_fill_two_kitchens_and_concurrent_starts_never_overbook(self):
        pages=[self.page() for _ in range(10)]
        barrier=threading.Barrier(10)
        def start(page):
            token,gid=page;barrier.wait(3)
            return self.request('/api/start',{'game_id':gid,'request_id':'start'},token)[0]
        with ThreadPoolExecutor(max_workers=10) as pool:
            statuses=list(pool.map(start,pages))
        self.assertEqual(statuses.count(200),2)
        self.assertEqual(statuses.count(503),8)
        for (token,_),status in zip(pages,statuses):
            _,s=self.request('/api/state',token=token)
            self.assertEqual(s['capacity']['used'],2)
            self.assertEqual(s['capacity']['can_start'],status==200)
        active=next(page for page,status in zip(pages,statuses) if status==200)
        self.assertEqual(self.request('/api/session/close',{},active[0])[0],200)
        waiting=next(page for page,status in zip(pages,statuses) if status==503)
        self.assertEqual(self.request('/api/start',{'game_id':waiting[1],'request_id':'retry'},waiting[0])[0],200)

    def test_rate_rejection_is_per_valid_session_and_close_still_works(self):
        a,gid=self.page();b,_=self.page()
        self.assertEqual(self.request('/api/start',{'game_id':gid,'request_id':'start'},a)[0],200)
        with self.server.sessions.lock:
            self.server.sessions.budgets[a].tokens=0
            self.server.sessions.budgets[a].rate=0
        self.assertEqual(self.request('/api/state',token=a)[0],429)
        self.assertEqual(self.request('/api/state',token=b)[0],200)
        self.assertEqual(self.request('/api/state',token='made-up-token')[0],401)
        self.assertEqual(self.request('/api/pause',{'game_id':gid,'request_id':'pause'},a)[0],200)
        self.assertEqual(self.server.sessions.get(a).phase,'paused')
        self.assertEqual(self.request('/api/session/close',{},a)[0],200)

    def test_invalid_start_does_not_keep_a_slot_and_operator_metrics_are_aggregate(self):
        a,gid=self.page()
        self.assertEqual(self.request('/api/start',{'game_id':gid,'request_id':'bad','speed':99},a)[0],400)
        status,d=self.request('/ops/capacity')
        self.assertEqual(status,200)
        self.assertEqual(d['capacity']['used'],0)
        text=json.dumps(d)
        self.assertNotIn(a,text);self.assertNotIn(gid,text)
        self.assertIn('python_cpu_percent_one_core',d['runtime'])
        self.assertEqual(self.server.request_queue_size,128)


class PagePoolTests(unittest.TestCase):
    def game(self):
        stopped=threading.Event()
        return SimpleNamespace(phase='ready',run=lambda:stopped.wait(2),close=stopped.set)

    def test_slow_page_creation_does_not_block_existing_pages_and_pool_reservations_are_bounded(self):
        sessions=Sessions(capacity=1,max_waiting=1,factory=self.game)
        self.addCleanup(sessions.close)
        token=sessions.create()
        entered=threading.Event();release=threading.Event()
        def slow():
            entered.set();release.wait(2);return self.game()
        sessions.factory=slow
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending=pool.submit(sessions.create)
            try:
                self.assertTrue(entered.wait(1))
                self.assertIsNotNone(pool.submit(sessions.get,token).result(timeout=.5))
                self.assertIsNone(sessions.create())
            finally:release.set()
            self.assertIsNotNone(pending.result(timeout=1))

    def test_expired_page_close_does_not_hold_the_global_lock(self):
        sessions=Sessions(capacity=1,max_waiting=1,factory=self.game)
        self.addCleanup(sessions.close)
        first=sessions.create();second=sessions.create()
        entered=threading.Event();release=threading.Event()
        def slow_close():entered.set();release.wait(2)
        game=sessions.get(first);game.close=slow_close
        sessions.entries[first]=(game,time.monotonic()-601)
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending=pool.submit(sessions.reap)
            try:
                self.assertTrue(entered.wait(1))
                self.assertIsNotNone(pool.submit(sessions.get,second).result(timeout=.5))
            finally:release.set()
            pending.result(timeout=1)

    def test_idle_ready_paused_and_ended_pages_do_not_accumulate_noop_inputs(self):
        game=HostedSession()
        self.addCleanup(game.close)
        for phase in ('ready','paused','ended'):
            game.phase=phase
            before=len(game.k.inputs)
            for _ in range(1000):game.tick()
            self.assertEqual(len(game.k.inputs),before)
        game.phase='paused'
        game.k.set_manual('human',1,0)
        before=len(game.k.inputs)
        game.tick()
        self.assertEqual(game.k.manual['human'],(0,0))
        self.assertEqual(len(game.k.inputs),before+1)
        for _ in range(100):game.tick()
        self.assertEqual(len(game.k.inputs),before+1)


if __name__=='__main__':unittest.main()
