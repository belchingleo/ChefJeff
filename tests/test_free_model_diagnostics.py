"""Synthetic provider failures and clock-controlled recovery; no real API calls."""
from copy import deepcopy
import http.client
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import urllib.error

from free_model_budget import CallBudget
from free_model_diagnostics import Diagnostics
from free_model_gateway import FreeCoordinator, GatewayError
from hosted_free_models import FreeModels, FreeCallError
from hosted_jev import TEST_PAYLOAD
from hosted_server import HostedSession
from jev import DecisionLoop, JevClient
from kitchen import Kitchen, load_config
from model_status import ModelWait, clean

KEYS={'zhipu':'synthetic-zhipu-not-real','startlux':'synthetic-startlux-not-real'}

class ProviderDiagnosticsTests(unittest.TestCase):
    def send(self,raw=None,error=None):
        response=Mock();response.status=200;response.read.return_value=raw
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.side_effect=error;opener.open.return_value=response
        with patch('hosted_free_models.urllib.request.build_opener',return_value=opener):
            with self.assertRaises(FreeCallError) as caught:
                FreeModels(KEYS,verified=True).send('zhipu',deepcopy(TEST_PAYLOAD))
        self.assertEqual(opener.open.call_count,1)
        self.assertNotIn(KEYS['zhipu'],str(caught.exception))
        self.assertNotIn(KEYS['zhipu'],json.dumps(caught.exception.diagnostic))
        return caught.exception

    def test_overload_keeps_status_code_without_private_error_message(self):
        body=json.dumps({'error':{'code':'1305','message':KEYS['zhipu']}}).encode()
        error=self.send(error=urllib.error.HTTPError('https://synthetic.invalid',429,'private',{},io.BytesIO(body)))
        self.assertEqual(error.category,'upstream_rejected')
        self.assertEqual(error.diagnostic['code'],'upstream_overloaded')
        self.assertEqual(error.diagnostic['upstream_http_status'],429)
        self.assertEqual(error.diagnostic['provider_error_code'],1305)
        self.assertTrue(error.diagnostic['upstream_called'])

    def test_invalid_boolean_reports_format_issue_without_repairing_model_action(self):
        error=self.send(json.dumps({'choices':[{'message':{'content':'{"choice":"wait","sprint":"false"}'}}]}).encode())
        self.assertEqual(error.category,'invalid_response')
        self.assertEqual(error.diagnostic['format_error'],'invalid_sprint')
        self.assertEqual(error.diagnostic['upstream_http_status'],200)

    def test_truncated_http_response_is_uncertain_not_invalid_action(self):
        error=self.send(error=http.client.IncompleteRead(b'synthetic-private'))
        self.assertEqual(error.category,'transport_uncertain')
        self.assertNotIn('synthetic-private',json.dumps(error.diagnostic))

class RecoveryTests(unittest.TestCase):
    def make(self):
        now=[1000.0];budget=CallBudget(clock=lambda:now[0]);sender=FreeModels(KEYS,verified=True)
        coordinator=FreeCoordinator(sender,budget=budget,clock=lambda:now[0])
        lease=coordinator.reserve('cn',{'provider':'zhipu','owner':'o'*24,'round':'r'*24})
        body={'lease':lease['lease'],'id':'first','payload':deepcopy(TEST_PAYLOAD)}
        return now,budget,sender,coordinator,body

    def test_overload_cached_failure_and_cooldown_do_not_make_extra_calls(self):
        now,budget,sender,c,body=self.make()
        sender.send=Mock(side_effect=FreeCallError(503,'safe','upstream_rejected',{
            'code':'upstream_overloaded','upstream_http_status':429,'provider_error_code':1305,'upstream_called':True}))
        with self.assertRaises(GatewayError) as first:c.decide('cn',body)
        self.assertEqual(first.exception.diagnostic['retry_after_seconds'],60)
        with self.assertRaises(GatewayError) as cached:c.decide('cn',body)
        self.assertEqual(cached.exception.diagnostic,first.exception.diagnostic)
        now[0]+=10
        with self.assertRaises(GatewayError) as cooling:c.decide('cn',{**body,'id':'second'})
        self.assertFalse(cooling.exception.diagnostic['upstream_called'])
        self.assertEqual(cooling.exception.diagnostic['retry_after_seconds'],50)
        self.assertEqual(sender.send.call_count,1)
        self.assertEqual(len(budget.value['attempts']),1)
        self.assertEqual(c.operation('cn','status',{})['diagnostics']['providers']['zhipu']['upstream_attempts'],1)

    def test_invalid_response_short_cooldown_and_uncertain_failure_stays_blocked(self):
        now,budget,sender,c,body=self.make()
        budget.begin('zhipu');budget.finish('zhipu','invalid_response')
        self.assertEqual(budget.retry_after('zhipu'),2)
        now[0]+=2;self.assertIsNone(budget.available('zhipu'))
        budget.begin('zhipu');budget.finish('zhipu','transport_uncertain')
        self.assertIsNone(budget.retry_after('zhipu'))
        now[0]+=3600;self.assertEqual(budget.available('zhipu'),'upstream_blocked')

    def test_rolling_window_retry_uses_latest_applicable_limit(self):
        now=[10000.0];budget=CallBudget(clock=lambda:now[0],minute=1,hour=2,day=3)
        budget.begin('zhipu');budget.finish('zhipu');now[0]+=10
        self.assertEqual(budget.retry_after('zhipu'),50)
        budget.begin('startlux');budget.finish('startlux')
        self.assertEqual(budget.retry_after('zhipu'),3590)

    def test_diagnostic_persistence_is_private_bounded_and_does_not_change_budget(self):
        with tempfile.TemporaryDirectory() as d:
            b=CallBudget(d);before=(Path(d)/'budget.json').read_bytes()
            diagnostics=Diagnostics(d)
            self.assertTrue(diagnostics.record({'provider':'zhipu','code':'invalid_response','upstream_called':True,
                'api_key':'private','prompt':'private','player_id':'private','format_error':'invalid_sprint'}))
            self.assertEqual((Path(d)/'budget.json').read_bytes(),before)
            self.assertEqual((Path(d)/'diagnostics.json').stat().st_mode&0o777,0o600)
            self.assertNotIn('private',(Path(d)/'diagnostics.json').read_text())
            self.assertEqual(Diagnostics(d).snapshot()['providers']['zhipu']['upstream_attempts'],1)
            with patch('free_model_diagnostics.tempfile.mkstemp',side_effect=OSError()):
                self.assertFalse(diagnostics.record({'provider':'zhipu','code':'ok'}))
            self.assertIsNone(b.available('zhipu'));b.close()

    def test_scheduler_waits_until_provider_deadline_without_exponential_backoff(self):
        k=Kitchen(load_config());client=JevClient(k.c,key='synthetic-not-real')
        log=[];ai=DecisionLoop(k,client,lambda kind,data:log.append((kind,data)),lambda text:None)
        ai.failures=5;ai.inflight=True;ai.last_request=100
        error=ModelWait({'code':'upstream_cooldown','upstream_called':False,'retry_after_seconds':60},'safe',clock=lambda:100)
        ai.q.put(({'id':1},None,error))
        with patch('jev.time.monotonic',return_value=101):ai.poll(enabled=False)
        self.assertEqual(ai.next_allowed,160);self.assertEqual(ai.failures,0);self.assertEqual(ai.deferred_count,1)
        with patch('jev.threading.Thread') as thread:
            with patch('jev.time.monotonic',return_value=159.9):ai.poll()
            thread.assert_not_called()
            with patch('jev.time.monotonic',return_value=160):ai.poll()
            self.assertEqual(thread.call_count,1)
        self.assertEqual(log[0][1]['retry_in'],59)

    def test_scheduler_blocked_outcome_never_automatically_retries(self):
        k=Kitchen(load_config());ai=DecisionLoop(k,None,lambda *args:None,lambda text:None)
        ai.q.put(({'id':1},None,ModelWait({'code':'upstream_blocked','blocked':True},'safe')))
        with patch('jev.threading.Thread') as thread:
            ai.poll()
            with patch('jev.time.monotonic',return_value=1e10):ai.poll()
            thread.assert_not_called()
        self.assertEqual(ai.next_allowed,float('inf'))

    def test_allowlist_drops_arbitrary_strings_and_nonfinite_or_nested_values(self):
        self.assertEqual(clean({'code':{},'provider':[], 'retry_after_seconds':float('nan'),'api_key':'secret'}),{})
        self.assertEqual(clean({'code':'upstream_overloaded','provider_error_code':'secret'}),{'code':'upstream_overloaded'})

    def test_round_diagnostics_are_deduplicated_and_reset_between_rounds(self):
        game=HostedSession();self.addCleanup(game.close)
        game.record_free_diagnostic('private-task',{'code':'ok','provider':'zhipu','upstream_called':True,'prompt':'secret'})
        game.record_free_diagnostic('private-task',{'code':'ok'})
        self.assertEqual(len(game.free_diagnostics),1)
        self.assertNotIn('secret',json.dumps(list(game.free_diagnostics.values())))
        game.game_id='different-round'
        game.record_free_diagnostic('different-task',{'code':'upstream_cooldown','upstream_called':False})
        self.assertEqual(len(game.free_diagnostics),1)
        self.assertEqual(game.free_diagnostic_round,'different-round')
