"""Exercise the dedicated private Nginx location with mock providers and no databases."""
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest

from deploy.free_gateway_config import nginx_location
from free_model_gateway import FreeCoordinator, GatewayServer
from hosted_free_models import FreeModels

NGINX=os.environ.get('CHEFJEFF_NGINX_BIN') or shutil.which('nginx')


@unittest.skipUnless(NGINX,'Install Nginx for private gateway routing integration checks')
class GatewayProxyTests(unittest.TestCase):
    def test_private_authentication_scoped_routing_and_size_limit(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);directory.chmod(0o755)
            sender=FreeModels({'zhipu':'synthetic-zhipu-key','startlux':'synthetic-startlux-key'},verified=True)
            sender.send=lambda *a:self.fail('Proxy/control checks must not invoke models')
            gateway=GatewayServer(0,FreeCoordinator(sender),{'cn':'c'*43,'global':'g'*43})
            thread=threading.Thread(target=gateway.serve_forever,daemon=True);thread.start()
            with socket.socket() as probe:
                probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            config=directory/'nginx.conf'
            config.write_text(f'pid {directory}/nginx.pid;\nerror_log {directory}/error.log;\nevents {{}}\nhttp {{\n'
                f'access_log off; client_body_temp_path {directory}/body; proxy_temp_path {directory}/proxy;\n'
                f'fastcgi_temp_path {directory}/fastcgi; uwsgi_temp_path {directory}/uwsgi; scgi_temp_path {directory}/scgi;\n'
                f'server {{ listen 127.0.0.1:{port};\n'+nginx_location(port=gateway.server_port)+
                '\nlocation /v1/ { return 200 "old-data-route"; }\n}\n}\n')
            process=None
            try:
                subprocess.run([NGINX,'-t','-p',d+'/', '-c',str(config)],check=True)
                process=subprocess.Popen([NGINX,'-p',d+'/', '-c',str(config),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                def request(path,body='{}',extra=None):
                    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
                    try:
                        connection.request('POST',path,body,{'Content-Type':'application/json',**(extra or {})})
                        response=connection.getresponse();return response.status,response.read()
                    finally:connection.close()
                for _ in range(100):
                    try:
                        if request('/v1/existing')[0]==200:break
                    except OSError:pass
                    time.sleep(.02)
                self.assertEqual(request('/v1/existing'),(200,b'old-data-route'))
                self.assertEqual(request('/v1/free-models/catalog')[0],401)
                auth={'Authorization':'Bearer '+'g'*43,'X-ChefJeff-Site':'global'}
                status,raw=request('/v1/free-models/catalog',extra=auth)
                self.assertEqual(status,200)
                self.assertEqual(json.loads(raw)['value']['global_capacity']['zhipu']['limit'],1)
                self.assertEqual(request('/v1/free-models/catalog',extra={**auth,'Origin':'https://example.com'})[0],401)
                self.assertEqual(request('/v1/free-models/catalog','x'*262145,auth)[0],413)
                self.assertFalse((directory/'proxy').exists() and any((directory/'proxy').rglob('*')))
            finally:
                if process is not None:
                    process.terminate()
                    try:process.wait(3)
                    except subprocess.TimeoutExpired:process.kill();process.wait(3)
                gateway.shutdown();gateway.server_close();thread.join(2)


if __name__=='__main__':unittest.main()
