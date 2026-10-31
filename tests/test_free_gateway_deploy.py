"""Pure deployment review rendering and bounded mocked probes, without root actions."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from deploy.free_gateway_config import data_candidate, gateway_unit, nginx_location
from deploy.install_free_region import existing_arguments
from deploy import install_free_region as region
from deploy.free_install_common import save, load, digest
from deploy.render_region import data_nginx
from free_model_client import FreeGatewayClient
from shared_client import SharedClient


class DeploymentTests(unittest.TestCase):
    def activation_fixture(self,root):
        previous=root/'old';previous.mkdir();new=root/'new';new.mkdir()
        current=root/'current';current.symlink_to(previous)
        override=root/'override.conf';work=root/'review';work.mkdir()
        command='/usr/bin/python3 /opt/chefjeff/current/hosted_server.py --port 8780 --origin https://chefjeff.belchingleo.online --data-dir /var/lib/chefjeff --shared-config /etc/chefjeff/shared-client.json'
        raw='{ argv[]='+command+' ; ignore_errors=no ; pid=456; }'
        candidate=work/'free-region.conf';candidate.write_text('[Service]\nExecStart=\nExecStart='+command+' --free-model-gateway\n')
        save(work,{'phase':'prepared','previous':str(previous),'release':str(new),
            'manifest_sha':'synthetic','unit_sha':digest(candidate),'startup_snapshot':'old metadata only',
            'startup_arguments':command.split(),'other_pids':{}})
        return previous,new,current,override,work,raw

    def test_failed_region_check_records_stage_rolls_back_and_can_retry_same_review(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);previous,new,current,override,work,raw=self.activation_fixture(root)
            calls=[]
            def fail(site,folder,mark):
                mark('public_fingerprint')
                raise region.InstallError('unexpected_http_status',http_status=502,expected_status=200)
            def props(unit,name):return raw if name=='ExecStart' else 'active'
            with patch.object(region,'CURRENT',current),patch.object(region,'OVERRIDE',override),\
                 patch.object(region,'property_of',side_effect=props),patch.object(region,'run',side_effect=lambda *a:calls.append(a)),\
                 patch.object(region,'wait_local'),patch.object(region,'verify',side_effect=fail) as verify,\
                 patch.object(region,'public_release',return_value=(new,{'release':{'fingerprint':'synthetic'}})),\
                 patch.object(region,'validate_import'):
                with self.assertRaises(region.InstallError):region.activate('cn',work,False)
                self.assertEqual(calls,[])
                output=io.StringIO()
                with contextlib.redirect_stdout(output),self.assertRaises(region.InstallError):region.activate('cn',work,True)
                self.assertEqual(current.resolve(),previous);self.assertFalse(override.exists())
                state=load(work)
                self.assertEqual(state['phase'],'rolled-back')
                self.assertEqual(state['last_failure']['stage'],'public_fingerprint')
                self.assertEqual(state['last_failure']['http_status'],502)
                verify.side_effect=None
                region.activate('cn',work,True)
                self.assertEqual(load(work)['phase'],'active');self.assertEqual(current.resolve(),new)
            self.assertTrue(previous.is_dir());self.assertTrue(new.is_dir())
            self.assertEqual([c for c in calls if c[:2]==('systemctl','restart')],
                [('systemctl','restart','chefjeff.service')]*3)

    def test_changed_arguments_stop_before_switching_or_restarting(self):
        with tempfile.TemporaryDirectory() as d:
            previous,new,current,override,work,raw=self.activation_fixture(Path(d))
            with patch.object(region,'CURRENT',current),patch.object(region,'OVERRIDE',override),\
                 patch.object(region,'property_of',return_value=raw.replace('--port 8780','--port 9999')),patch.object(region,'run') as run:
                with self.assertRaises(ValueError):region.activate('cn',work,True)
                run.assert_not_called()
            self.assertEqual(current.resolve(),previous);self.assertFalse(override.exists())

    def test_service_user_import_failure_stops_before_any_live_change(self):
        with tempfile.TemporaryDirectory() as d:
            previous,new,current,override,work,raw=self.activation_fixture(Path(d))
            with patch.object(region,'CURRENT',current),patch.object(region,'OVERRIDE',override),\
                 patch.object(region,'property_of',return_value=raw),patch.object(region,'run') as run,\
                 patch.object(region,'public_release',return_value=(new,{'release':{'fingerprint':'synthetic'}})),\
                 patch.object(region,'validate_import',side_effect=region.InstallError('service_user_import_failed')):
                with self.assertRaises(region.InstallError):region.activate('cn',work,True)
                run.assert_not_called()
            self.assertEqual(load(work)['phase'],'prepared');self.assertEqual(current.resolve(),previous)

    def test_import_preflight_never_prints_untrusted_stderr_or_exception_text(self):
        from subprocess import CompletedProcess
        secret='synthetic-private-text-not-for-output'
        result=CompletedProcess([],1,stdout='not JSON '+secret,stderr=secret)
        with patch.object(region.subprocess,'run',return_value=result):
            with self.assertRaises(region.InstallError) as error:region.validate_import('/public/release','expected')
        self.assertEqual(error.exception.code,'service_user_import_failed')
        self.assertNotIn(secret,json.dumps(error.exception.details))

    def test_http_failure_keeps_actual_stage_and_is_not_hidden_by_session_cleanup_failure(self):
        with tempfile.TemporaryDirectory() as d:
            previous,new,current,override,work,raw=self.activation_fixture(Path(d))
            current.unlink();current.symlink_to(new)
            state=load(work);state['switched_monotonic_us']=1;save(work,state)
            def props(unit,name):return '2' if name=='ExecMainStartTimestampMonotonic' else 'active'
            calls=[]
            def request(domain,path,*args,**kwargs):
                calls.append(path)
                return {'/healthz':(200,b'{}'),'/':(200,b'<aside id="free-model-picker"></aside><script>inline</script>'),
                    '/api/session':(201,b'{"session":"synthetic-session"}'),'/api/state':(503,b'{}'),
                    '/api/session/close':(500,b'{}')}[path]
            stages=[]
            with patch.object(region,'CURRENT',current),patch.object(region,'property_of',side_effect=props),\
                 patch.object(region,'public_release',return_value=(new,{'release':{'fingerprint':'synthetic'}})),\
                 patch.object(region,'request',side_effect=request):
                with self.assertRaises(region.InstallError) as caught:region.verify('cn',work,stages.append)
            self.assertEqual(caught.exception.details['http_status'],503)
            self.assertEqual(stages[-1],'public_fingerprint')
            self.assertEqual(calls[-1],'/api/session/close')

    def test_existing_data_routes_are_preserved_with_one_scoped_include(self):
        original=data_nginx('data.belchingleo.online','2.31.58.179')
        candidate=data_candidate(original)
        line='    include /etc/chefjeff-free/nginx-location.conf;\n'
        self.assertEqual(candidate.replace(line,''),original)
        with self.assertRaises(ValueError):data_candidate(candidate)
        with self.assertRaises(ValueError):data_candidate(original.replace('data.belchingleo.online','other.example'))
        location=nginx_location()
        self.assertIn('location ^~ /v1/free-models/',location)
        self.assertIn('proxy_read_timeout 25s;',location)
        self.assertIn('allow 2.31.58.179;',location)
        self.assertIn('deny all;',location)
        self.assertIn('proxy_pass http://127.0.0.1:8798;',location)

    def test_gateway_is_a_dedicated_sandboxed_user_without_player_database_access(self):
        unit=gateway_unit('/opt/chefjeff/releases/china-free-reviewed/chefjeff-web-demo')
        self.assertIn('User=chefjeff-free',unit)
        self.assertIn('ReadWritePaths=/var/lib/chefjeff-free',unit)
        self.assertIn('InaccessiblePaths=-/var/lib/chefjeff-data',unit)
        self.assertIn('--models-verified',unit)
        self.assertNotIn('api_key=',unit)

    def test_existing_region_arguments_are_preserved_without_accepting_unknown_secret_flags(self):
        command='/usr/bin/python3 /opt/chefjeff/current/hosted_server.py --port 8780 --origin https://global.belchingleo.online --data-dir /var/lib/chefjeff --shared-config /etc/chefjeff/shared-client.json --max-sessions 6 --max-waiting 20'
        raw='{ path=/usr/bin/python3 ; argv[]='+command+' ; ignore_errors=no ; start_time=[today] ; pid=123; }'
        args=existing_arguments(raw,'global.belchingleo.online')
        self.assertEqual(' '.join(args),command)
        with self.assertRaises(ValueError):existing_arguments(raw.replace('--max-sessions 6','--api-key hidden'),'global.belchingleo.online')
        with self.assertRaises(ValueError):existing_arguments(raw,'chefjeff.belchingleo.online')

    def test_shanghai_loopback_and_overseas_https_route_to_the_one_gateway(self):
        cn=SharedClient({'url':'http://127.0.0.1:8790','site':'cn','token':'c'*43})
        de=SharedClient({'url':'https://data.belchingleo.online','site':'global','token':'g'*43})
        self.assertEqual(FreeGatewayClient(cn).url.port,8798)
        self.assertEqual(FreeGatewayClient(de).url.geturl(),'https://data.belchingleo.online')

    def test_synthetic_operator_probe_is_bounded_to_two_calls_and_never_prints_tokens(self):
        path=Path(__file__).resolve().parents[1]/'scripts/probe_free_gateway.py'
        spec=importlib.util.spec_from_file_location('gateway_probe',path)
        probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
        calls=[]
        class Client:
            site='cn'
            def __init__(self,*args):pass
            def request(self,operation,body):
                calls.append(operation)
                if operation=='reserve':return {'lease':'synthetic-private-lease-not-real'}
                if operation=='decide':return {'answer':{'choice':next(iter(body['payload']['questions']['next_action']['criteria'])),'sprint':False}}
                return {}
        output=io.StringIO()
        with patch('sys.argv',['probe']),patch.object(probe,'read_private_json',return_value={
            'url':'https://data.belchingleo.online','site':'cn','token':'c'*43}),\
             patch.object(probe,'FreeGatewayClient',Client),contextlib.redirect_stdout(output):
            probe.main()
        self.assertEqual(calls.count('decide'),2)
        self.assertEqual(calls.count('reserve'),2)
        self.assertEqual(calls.count('release'),2)
        self.assertNotIn('synthetic-private-lease-not-real',output.getvalue())
        self.assertNotIn('c'*43,output.getvalue())


if __name__=='__main__':unittest.main()
