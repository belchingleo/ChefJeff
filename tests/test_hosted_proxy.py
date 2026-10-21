"""Exercise the shipped Nginx forwarding rules against the real hosted handler."""
import http.client
import gzip
import json
import re
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from hosted_server import HostedHandler, make_server
from hosted_jev import CONSENT_VERSION


NGINX = os.environ.get('CHEFJEFF_NGINX_BIN') or shutil.which('nginx')
ROOT = Path(__file__).resolve().parents[1]
DOMAIN = 'chefjeff.online'
ORIGIN = 'https://' + DOMAIN


@unittest.skipUnless(NGINX, 'Install Nginx or set CHEFJEFF_NGINX_BIN for proxy integration tests.')
class HostedProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='chefjeff-proxy-')
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        directory.chmod(0o755)
        cls.observed = []

        class ObservedHandler(HostedHandler):
            def valid_origin(self, post=False):
                cls.observed.append(dict(self.headers))
                return super().valid_origin(post)

        cls.backend = make_server(0, ORIGIN)
        cls.backend.RequestHandlerClass = ObservedHandler
        cls.thread = threading.Thread(target=cls.backend.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.thread.join, 2)
        cls.addClassCleanup(cls.backend.server_close)
        cls.addClassCleanup(cls.backend.sessions.close)
        cls.addClassCleanup(cls.backend.shutdown)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            cls.port = probe.getsockname()[1]
        template = (ROOT / 'deploy/nginx-https.conf').read_text()
        zones = template[:template.index('server {')]
        # Exercise authentication cases without consuming the production
        # session-creation quota; rate limiting is independent of this change.
        zones = zones.replace('rate=15r/m', 'rate=1000r/s')
        site = template[template.index('server {\n    listen 443 ssl http2;'):]
        # TLS is unrelated to forwarding headers; retain the complete HTTPS
        # virtual host's location/header configuration on a loopback HTTP port.
        site = '\n'.join(line for line in site.splitlines()
                         if not line.strip().startswith(('ssl_certificate', 'ssl_protocols')))
        site = site.replace('listen 443 ssl http2;', f'listen 127.0.0.1:{cls.port};')
        site = site.replace('burst=2 ', 'burst=1000 ')
        site = site.replace('127.0.0.1:8780', f'127.0.0.1:{cls.backend.server_port}')
        site = site.replace('/opt/chefjeff/current/cocos-kitchen/build/web',str(cls.backend.web_root))
        config = directory / 'nginx.conf'
        config.write_text(f'worker_processes 1;\npid {directory}/nginx.pid;\n'
                          f'error_log {directory}/error.log;\nevents {{}}\nhttp {{\n'
                          f'client_body_temp_path {directory}/body;\n'
                          f'proxy_temp_path {directory}/proxy;\n'
                          f'fastcgi_temp_path {directory}/fastcgi;\n'
                          f'uwsgi_temp_path {directory}/uwsgi;\n'
                          f'scgi_temp_path {directory}/scgi;\naccess_log off;\n'
                          + zones + site + '\n}\n')
        subprocess.run([NGINX, '-t', '-p', str(directory) + '/', '-c', str(config)], check=True)
        cls.process = subprocess.Popen([NGINX, '-p', str(directory) + '/', '-c', str(config),
                                        '-g', 'daemon off;'])
        cls.addClassCleanup(cls.stop_proxy)
        for _ in range(100):
            if cls.process.poll() is not None:
                raise RuntimeError((directory / 'error.log').read_text())
            try:
                if cls.request('/healthz')[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(.02)
        raise RuntimeError('Nginx did not become ready.')

    @classmethod
    def stop_proxy(cls):
        cls.process.terminate()
        try:
            cls.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=3)

    @classmethod
    def request(cls, path, body=None, headers=None, include_headers=False):
        connection = http.client.HTTPConnection('127.0.0.1', cls.port, timeout=3)
        request_headers = {'Host': DOMAIN, **(headers or {})}
        if body is not None:
            request_headers['Content-Type'] = 'application/json'
        try:
            connection.request('GET' if body is None else 'POST', path,
                               None if body is None else json.dumps(body), request_headers)
            response = connection.getresponse()
            result = response.status, response.read()
            return (*result, dict(response.getheaders())) if include_headers else result
        finally:
            connection.close()

    def test_public_page_opens_from_external_links(self):
        for site in ('cross-site', 'same-site', 'none'):
            with self.subTest(site=site):
                status, page = self.request('/', headers={'Sec-Fetch-Site': site,
                    'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'})
                self.assertEqual(status, 200)
                self.assertIn(b'/hosted-agent.js', page)

    def test_public_route_keeps_host_and_strips_credentials(self):
        status, _ = self.request('/healthz', headers={'Authorization': 'unit-test-placeholder',
                                                     'Cookie': 'unit-test=placeholder'})
        self.assertEqual(status, 200)
        forwarded = self.observed[-1]
        self.assertEqual(forwarded.get('Host'), DOMAIN)
        self.assertNotIn('Authorization', forwarded)
        self.assertNotIn('Cookie', forwarded)

    def test_consented_jev_body_streams_without_proxy_temporary_files(self):
        status,raw=self.request('/api/session',{},headers={'Origin':ORIGIN})
        self.assertEqual(status,201)
        token=json.loads(raw)['session'];game=self.backend.sessions.get(token)
        key='unit-test-'+('x'*2038)
        body={'game_id':game.game_id,'request_id':'test-jev','api_key':key,
              'test':True,'consent':True,'consent_version':CONSENT_VERSION}
        try:
            with patch.object(self.backend.jev_forwarder,'send',return_value={'choice':'wait','sprint':False,'usage':{}}) as send:
                status,raw=self.request('/api/model/jev',body,headers={'Origin':ORIGIN,'X-ChefJeff-Session':token,
                    'Authorization':'must-be-stripped','Cookie':'must-be-stripped'})
                self.assertEqual(status,200)
                self.assertNotIn(key,raw.decode())
                self.assertEqual(send.call_args.args[0],key)
            self.assertNotIn('Authorization',self.observed[-1]);self.assertNotIn('Cookie',self.observed[-1])
            for folder in ('body','proxy'):
                root=Path(self.temp.name)/folder
                self.assertFalse(any(p.is_file() for p in root.rglob('*')))
        finally:self.request('/api/session/close',{},headers={'Origin':ORIGIN,'X-ChefJeff-Session':token})

    def test_public_route_keeps_explicit_origin_validation(self):
        self.assertEqual(self.request('/', headers={'Origin': 'https://bad.example'})[0], 403)

    def test_api_rejects_cross_site_requests_and_navigation(self):
        for site in ('cross-site', 'same-site'):
            with self.subTest(site=site):
                headers = {'Origin': ORIGIN, 'Sec-Fetch-Site': site,
                           'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}
                self.assertEqual(self.request('/api/state', headers=headers)[0], 403)
                self.assertEqual(self.request('/api/session', {}, headers=headers)[0], 403)

    def test_api_keeps_origin_requirement_and_allows_same_origin_session(self):
        self.assertEqual(self.request('/api/session', {}, headers={})[0], 403)
        self.assertEqual(self.request('/api/session', {},
                                     headers={'Origin': 'https://bad.example'})[0], 403)
        status, body = self.request('/api/session', {},
                                   headers={'Origin': ORIGIN, 'Sec-Fetch-Site': 'same-origin'})
        self.assertEqual(status, 201)
        self.assertTrue(json.loads(body)['session'])

    def test_engine_javascript_is_compressed_over_the_proxy(self):
        engine = max((self.backend.web_root / 'cocos-js').glob('*.js'), key=lambda p: p.stat().st_size)
        path = '/' + engine.relative_to(self.backend.web_root).as_posix()
        status, body, headers = self.request(path, headers={'Accept-Encoding': 'gzip'}, include_headers=True)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Content-Encoding'), 'gzip')
        self.assertIn('Accept-Encoding', headers.get('Vary', ''))
        self.assertEqual(gzip.decompress(body), engine.read_bytes())
        self.assertLess(len(body), engine.stat().st_size / 3)

    def test_static_assets_revalidate_without_caching_pages_or_state(self):
        status, body, headers = self.request('/hosted-agent.js', include_headers=True)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Cache-Control'], 'public, max-age=0, must-revalidate')
        etag = headers['ETag']
        status, cached, _ = self.request('/hosted-agent.js', headers={'If-None-Match': 'W/' + etag}, include_headers=True)
        self.assertEqual(status, 304)
        self.assertEqual(cached, b'')
        status, changed, _ = self.request('/hosted-agent.js', headers={'If-None-Match': '"old-release"'}, include_headers=True)
        self.assertEqual(status, 200)
        self.assertEqual(changed, body)
        for path in ('/', '/api/state', '/healthz'):
            with self.subTest(path=path):
                _, _, headers = self.request(path, include_headers=True)
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.assertNotIn('ETag', headers)

    def test_assets_bypass_python_and_keep_mime_cache_and_security_headers(self):
        path='/touch-controls.js'
        before=len(self.observed)
        status,body,headers=self.request(path,include_headers=True)
        self.assertEqual(status,200)
        self.assertEqual(body,(self.backend.web_root/'touch-controls.js').read_bytes())
        self.assertEqual(len(self.observed),before)
        self.assertIn('javascript',headers['Content-Type'])
        self.assertEqual(headers['Cache-Control'],'public, max-age=0, must-revalidate')
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertIn('max-age=',headers['Strict-Transport-Security'])
        self.assertEqual(self.request(path,headers={'If-None-Match':headers['ETag']})[0],304)
        for path in ('/ops/capacity','/../../hosted_records.py','/release-manifest.json','/assets/resources.meta'):
            with self.subTest(path=path):self.assertIn(self.request(path)[0],(400,404))
        status,_,headers=self.request('/assets/absent.js',include_headers=True)
        self.assertEqual(status,404)
        self.assertEqual(headers['Cache-Control'],'no-store')

    def test_content_hashed_build_files_are_cached_for_a_year(self):
        # md5Cache names a file by its content (cc.<5 hex>.js), so a new release never reuses a name.
        root=self.backend.web_root
        hashed=[p for p in root.rglob('*') if p.is_file() and re.search(r'\.[0-9a-f]{5}\.(js|json|css|png)$',p.name)]
        self.assertTrue(hashed,'The release web build should use content-hashed names.')
        for file in (max(hashed,key=lambda p:p.stat().st_size),next(p for p in hashed if p.suffix=='.png')):
            with self.subTest(file=file.name):
                status,body,headers=self.request('/'+file.relative_to(root).as_posix(),include_headers=True)
                self.assertEqual(status,200)
                self.assertEqual(body,file.read_bytes())
                self.assertEqual(headers['Cache-Control'],'public, max-age=31536000, immutable')
                self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        status,_,headers=self.request('/cocos-js/cc.00000.js',include_headers=True)
        self.assertEqual(status,404)
        self.assertEqual(headers['Cache-Control'],'no-store')
        _,_,headers=self.request('/kitchen-i18n.js',include_headers=True)
        self.assertEqual(headers['Cache-Control'],'public, max-age=0, must-revalidate')

    def test_eight_same_ip_kitchens_can_poll_without_the_old_shared_limit(self):
        pages=[]
        try:
            for _ in range(8):
                status,raw=self.request('/api/session',{},headers={'Origin':ORIGIN})
                self.assertEqual(status,201)
                pages.append(json.loads(raw)['session'])
            # One network, eight independent validated sessions. The former
            # 30r/s + 30 burst quota would reject this sustained workload.
            import concurrent.futures
            def poll(token):
                for _ in range(15):
                    self.assertEqual(self.request('/api/state',headers={'X-ChefJeff-Session':token})[0],200)
                    time.sleep(.05)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(poll,pages))
        finally:
            for token in pages:self.request('/api/session/close',{},headers={'Origin':ORIGIN,'X-ChefJeff-Session':token})


if __name__ == '__main__':
    unittest.main()
