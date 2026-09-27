import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from cocos_server import CocosHandler


class CocosStaticTests(unittest.TestCase):
    def request(self, root, path, host='127.0.0.1:8769'):
        h=object.__new__(CocosHandler);h.web_root=root;h.path=path
        h.headers={'Host':host};h.server=SimpleNamespace(server_port=8769)
        h.request_version='HTTP/1.1';h.requestline='GET '+path+' HTTP/1.1'
        h.wfile=io.BytesIO();h.do_GET();return h.wfile.getvalue()

    def test_only_built_files_are_served_and_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'build';root.mkdir();(root/'index.html').write_text('demo-only')
            (Path(d)/'private.txt').write_text('private-marker')
            (root/'outside.txt').symlink_to(Path(d)/'private.txt')
            self.assertIn(b'200 OK',self.request(root,'/'))
            for path in ('/../private.txt','/%2e%2e/private.txt','/outside.txt','/.env'):
                response=self.request(root,path)
                self.assertIn(b'404',response);self.assertNotIn(b'private-marker',response)
            self.assertIn(b'403',self.request(root,'/',host='elsewhere.example:8769'))
