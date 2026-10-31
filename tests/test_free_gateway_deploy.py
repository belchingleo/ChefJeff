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
    def test_failed_region_health_check_restores_old_link_and_only_restarts_game(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);previous=root/'old';previous.mkdir();new=root/'new';new.mkdir()
            current=root/'current';current.symlink_to(previous)
            override=root/'override.conf';work=root/'review';work.mkdir()
            candidate=work/'free-region.conf';candidate.write_text('[Service]\nExecStart=reviewed\n')
            import hashlib
            save(work,{'phase':'prepared','previous':str(previous),'release':str(new),
                'unit_sha':digest(candidate),'startup_snapshot':hashlib.sha256(b'original').hexdigest()})
            calls=[]
            with patch.object(region,'CURRENT',current),patch.object(region,'OVERRIDE',override),\
                 patch.object(region,'property_of',return_value='original'),patch.object(region,'run',side_effect=lambda *a:calls.append(a)),\
                 patch.object(region,'wait_local'),patch.object(region,'verify',side_effect=ValueError('synthetic health failure')):
                with self.assertRaises(ValueError):region.activate('cn',work,False)
                self.assertEqual(calls,[])
                with self.assertRaises(ValueError):region.activate('cn',work,True)
            self.assertEqual(current.resolve(),previous)
            self.assertFalse(override.exists())
            self.assertTrue(new.is_dir())
            self.assertEqual(load(work)['phase'],'rolled-back')
            self.assertEqual([c for c in calls if c[:2]==('systemctl','restart')],
                [('systemctl','restart','chefjeff.service')]*2)

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
