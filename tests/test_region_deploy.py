"""Verify region configuration and private transfer invariants before deployment."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from deploy.init_shared_config import create
from deploy.install_region import preserve_limits, verify_release
from deploy.migrate_data import export_transfer, import_transfer
from deploy.render_region import game_nginx, game_unit, data_nginx, renewal_hook
from deploy import set_kitchen_capacity as capacity
from hosted_records import ContributionStore
from hosted_usage import UsageStats
from shared_server import read_private_json

NGINX = os.environ.get('CHEFJEFF_NGINX_BIN') or shutil.which('nginx')


class RegionDeployTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def source(self):
        source = self.root/'original'
        store = ContributionStore(source)
        receipt = store.save({'schema': 'chefjeff-pilot-session-v1', 'events': []})
        UsageStats(source).increment('page_views')
        return source, receipt

    def test_transfer_keeps_original_receipt_content_expiry_and_historical_totals(self):
        source, receipt = self.source()
        with closing(sqlite3.connect(source/'contributions.sqlite3')) as db:
            original = db.execute('SELECT * FROM records').fetchall()
        archive = self.root/'transfer.zip'
        export_transfer(source, archive)
        target = self.root/'imported'
        import_transfer(archive, target)
        with closing(sqlite3.connect(target/'contributions.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT * FROM records').fetchall(), original)
        self.assertEqual(UsageStats(target).snapshot()['page_views'], 1)
        self.assertTrue(ContributionStore(target).delete(receipt['id'], receipt['deletion_token']))
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        self.assertEqual((target/'contributions.sqlite3').stat().st_mode & 0o777, 0o600)

    def test_import_refuses_existing_data_and_expired_or_modified_transfer(self):
        source, _ = self.source();archive = self.root/'transfer.zip'
        export_transfer(source, archive)
        with self.assertRaises(ValueError):import_transfer(archive, source)
        with patch('deploy.migrate_data.time.time', return_value=time.time()+3700):
            with self.assertRaises(ValueError):import_transfer(archive, self.root/'expired')
        modified = self.root/'modified.zip'
        with zipfile.ZipFile(archive) as incoming, zipfile.ZipFile(modified, 'w') as outgoing:
            for item in incoming.namelist():
                raw = incoming.read(item)
                if item == 'usage.sqlite3':raw = raw[:-1]+bytes([raw[-1] ^ 1])
                outgoing.writestr(item, raw)
        with self.assertRaises(ValueError):import_transfer(modified, self.root/'modified')

    def test_private_credentials_are_distinct_and_point_regions_to_one_service(self):
        directory = self.root/'credentials';create(directory, 'https://data.chefjeff.online')
        central = read_private_json(directory/'data-server.json')
        cn = read_private_json(directory/'cn-client.json')
        overseas = read_private_json(directory/'global-client.json')
        self.assertNotEqual(cn['token'], overseas['token'])
        self.assertEqual(central['sites'], {'cn': cn['token'], 'global': overseas['token']})
        self.assertEqual(cn['url'], 'http://127.0.0.1:8790')
        self.assertEqual(overseas['url'], 'https://data.chefjeff.online')
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        for path in directory.iterdir():self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):create(directory, 'https://data.chefjeff.online')
        (directory/'cn-client.json').chmod(0o644)
        with self.assertRaises(ValueError):read_private_json(directory/'cn-client.json')

    def test_global_host_headers_certificates_and_legacy_redirect_are_consistent(self):
        text = game_nginx('global.chefjeff.online', legacy=['chefjeff.belchingleo.online'])
        self.assertIn('proxy_set_header Host global.chefjeff.online;', text)
        self.assertIn('/live/global.chefjeff.online/fullchain.pem', text)
        self.assertIn('/live/chefjeff.belchingleo.online/fullchain.pem', text)
        self.assertNotIn('https://chefjeff.online$request_uri', text)
        self.assertIn('return 301 https://global.chefjeff.online$request_uri;', text)
        self.assertIn('--origin https://global.chefjeff.online', game_unit('global.chefjeff.online'))
        self.assertIn('--shared-config /etc/chefjeff/shared-client.json', game_unit('global.chefjeff.online'))
        for invalid in ['example.com;return 200;', '*.example.com', 'example.com/path']:
            with self.assertRaises(ValueError):game_nginx(invalid)

    def test_existing_capacity_and_shared_configuration_survive_capacity_change(self):
        command = ('/usr/bin/python3 /opt/chefjeff/current/hosted_server.py --port 8780'
            ' --origin https://global.chefjeff.online --max-sessions 8 --data-dir /var/lib/chefjeff'
            ' --shared-config /etc/chefjeff/shared-client.json --max-per-network 2')
        states = [{'capacity': {'limit': 8, 'session_limit': 40}}, {'capacity': {'limit': 12, 'session_limit': 44}}]
        with patch.object(capacity, 'read_metrics', side_effect=states), patch.object(capacity, 'run'), \
                patch.object(capacity.subprocess, 'check_output', return_value=command):
            path = self.root/'region.conf';capacity.apply(12, path, domain='global.chefjeff.online')
        self.assertIn('--shared-config /etc/chefjeff/shared-client.json', path.read_text())
        self.assertIn('--max-per-network 2', path.read_text())
        unit = preserve_limits(game_unit('global.chefjeff.online'), command.replace('--max-sessions 8', '--max-sessions 12'))
        self.assertIn('--max-sessions 12', unit);self.assertIn('--max-per-network 2', unit)

    def test_manifest_rejects_modified_runtime(self):
        release = self.root/'release';release.mkdir();path = release/'runtime.py';path.write_text('original')
        (release/'release-manifest.json').write_text(json.dumps({'files': {'runtime.py': hashlib.sha256(path.read_bytes()).hexdigest()}}))
        verify_release(release);path.write_text('modified')
        with self.assertRaises(ValueError):verify_release(release)

    @unittest.skipUnless(NGINX and shutil.which('openssl'), 'Nginx and OpenSSL required')
    def test_actual_nginx_accepts_both_region_configs_and_private_data_virtual_host(self):
        self.root.chmod(0o755)
        certificate, key = self.root/'certificate.pem', self.root/'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-subj', '/CN=localhost', '-keyout', str(key), '-out', str(certificate)], check=True, capture_output=True)
        configurations = [game_nginx('chefjeff.online', ['www.chefjeff.online']),
            game_nginx('global.chefjeff.online', legacy=['chefjeff.belchingleo.online']),
            data_nginx('data.chefjeff.online', '2.31.58.179')]
        import re
        for i, body in enumerate(configurations):
            body = re.sub(r'/etc/letsencrypt/live/[^/]+/fullchain.pem', str(certificate), body)
            body = re.sub(r'/etc/letsencrypt/live/[^/]+/privkey.pem', str(key), body)
            config = self.root/f'nginx-{i}.conf'
            temporary_paths = '\n'.join(f'{kind}_temp_path {self.root}/{kind};' for kind in ('client_body', 'proxy', 'fastcgi', 'uwsgi', 'scgi'))
            config.write_text(f'pid {self.root}/nginx.pid;\nerror_log stderr;\nevents {{}}\nhttp {{\n'+temporary_paths+'\n'+body+'\n}\n')
            result = subprocess.run([NGINX, '-t', '-p', str(self.root)+'/', '-c', str(config)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        hook = self.root/'renew';hook.write_text(renewal_hook(['global.chefjeff.online', 'data.chefjeff.online']))
        subprocess.run(['sh', '-n', str(hook)], check=True)


if __name__ == '__main__':unittest.main()
