"""Real two-region HTTP checks, retained receipts and retry-safe shared totals."""
from contextlib import closing
from datetime import datetime
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from hosted_records import ContributionStore, RETENTION_SECONDS, CONSENT_VERSION
from hosted_usage import UsageStats
from hosted_server import make_server
from shared_client import SharedClient, RegionalUsage, RemoteRecords
from shared_data import Gone, SharedRecords, SharedUsage, usage_payload
from shared_server import DataServer


ROOT = Path(__file__).resolve().parents[1]


class SharedDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tokens = {site: secrets.token_urlsafe(32) for site in ('cn', 'global')}
        self.server = DataServer(0, self.root/'central', self.tokens)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 3)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.record = json.loads((ROOT/'tests/fixtures/research-v2-short.json').read_text())
        self.record['consent_version'] = CONSENT_VERSION

    def config(self, site):
        return {'url': f'http://127.0.0.1:{self.server.server_port}', 'site': site, 'token': self.tokens[site]}

    def client(self, site):
        return SharedClient(self.config(site))

    def test_receipt_saved_in_china_works_overseas_and_delete_cannot_be_undone(self):
        cn, global_ = RemoteRecords(self.client('cn')), RemoteRecords(self.client('global'))
        receipt = cn.save(self.record)
        self.assertEqual(global_.download(receipt['id'], receipt['deletion_token']), self.record)
        self.assertTrue(global_.delete(receipt['id'], receipt['deletion_token']))
        self.assertFalse(cn.update(receipt['id'], self.record))
        self.assertIsNone(cn.download(receipt['id'], receipt['deletion_token']))

    def test_retried_create_is_one_record_and_cannot_resurrect_a_deleted_record(self):
        client = self.client('cn')
        body = {'request_id': secrets.token_hex(16), 'created_at': time.time(),
                'deletion_token': secrets.token_urlsafe(32), 'record': self.record}
        first = client.request('records/save', body)
        self.assertEqual(client.request('records/save', body), first)
        with self.server.records.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM records').fetchone()[0], 1)
        self.server.records.delete(first['id'], first['deletion_token'])
        with self.assertRaises(OSError):
            client.request('records/save', body)
        with self.server.records.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM records').fetchone()[0], 0)

    def test_new_contributions_keep_180_days_and_earlier_expiries_never_move(self):
        self.assertEqual(RETENTION_SECONDS, 180 * 86400)
        for store in (ContributionStore(self.root/'local'), RemoteRecords(self.client('cn'))):
            before = time.time()
            receipt = store.save(self.record)
            expires = datetime.fromisoformat(receipt['expires_at']).timestamp()
            self.assertGreaterEqual(expires, before + RETENTION_SECONDS - 1)
            self.assertLessEqual(expires, time.time() + RETENTION_SECONDS + 1)
        # A record saved under the 30-day terms keeps its expiry through the final update.
        local = ContributionStore(self.root/'local')
        receipt = local.save(self.record)
        thirty_days = time.time() + 30 * 86400
        with local.connect() as db:
            db.execute('UPDATE records SET expires=? WHERE id=?', (thirty_days, receipt['id']))
        self.assertTrue(local.update(receipt['id'], self.record))
        with local.connect() as db:
            self.assertEqual(db.execute('SELECT expires FROM records WHERE id=?', (receipt['id'],)).fetchone()[0], thirty_days)
        remote = RemoteRecords(self.client('global'))
        receipt = remote.save(self.record)
        with self.server.records.connect() as db:
            db.execute('UPDATE records SET expires=? WHERE id=?', (thirty_days, receipt['id']))
        self.assertTrue(remote.update(receipt['id'], self.record))
        with self.server.records.connect() as db:
            self.assertEqual(db.execute('SELECT expires FROM records WHERE id=?', (receipt['id'],)).fetchone()[0], thirty_days)

    def test_legacy_receipt_hash_and_original_expiry_survive_service_adoption(self):
        legacy = {'schema': 'chefjeff-pilot-session-v1', 'events': [], 'duration': 12}
        receipt = ContributionStore(self.root/'central').save(legacy)
        original_expiry = time.time()+3600
        with self.server.records.connect() as db:
            db.execute('UPDATE records SET expires=? WHERE id=?', (original_expiry, receipt['id']))
        peer = RemoteRecords(self.client('global'))
        self.assertEqual(peer.download(receipt['id'], receipt['deletion_token']), legacy)
        with self.server.records.connect() as db:
            row = db.execute('SELECT expires,deletion_hash FROM records WHERE id=?', (receipt['id'],)).fetchone()
        self.assertEqual(row, (original_expiry, hashlib.sha256(receipt['deletion_token'].encode()).hexdigest()))
        with self.server.records.connect() as db:
            db.execute('UPDATE records SET expires=? WHERE id=?', (time.time()-1, receipt['id']))
        self.assertIsNone(peer.download(receipt['id'], receipt['deletion_token']))
        with self.assertRaises(Gone):
            self.server.records.create(secrets.token_hex(16), secrets.token_urlsafe(32), time.time()-RETENTION_SECONDS-1, legacy)

    def test_region_outbox_restart_and_repeated_delivery_do_not_duplicate_history(self):
        # Existing production aggregates become the baseline exactly once.
        baseline = UsageStats(self.root/'central')
        for _ in range(7):
            baseline.increment('page_views')
        # Reload after the one-time offline baseline import, before writes begin.
        self.server.usage = SharedUsage(self.root/'central')
        cn = RegionalUsage(self.root/'cn', self.client('cn'))
        overseas = RegionalUsage(self.root/'global', self.client('global'))
        for _ in range(2): cn.increment('page_views')
        for _ in range(3): overseas.increment('page_views')
        cn.start_round(2, first=True)
        cn.end_round(2, 'manual_end', 12, .5)
        self.assertTrue(cn.sync())
        self.assertTrue(overseas.sync())
        self.assertTrue(cn.sync())
        self.assertTrue(overseas.sync())
        data = self.server.usage.snapshot()
        self.assertEqual(data['page_views'], 12)
        self.assertEqual(data['started_rounds'], 1)
        self.assertEqual(data['durations'][0]['rounds'], 1)
        restarted = RegionalUsage(self.root/'cn', self.client('cn'))
        self.assertEqual(restarted.stream, cn.stream)
        self.assertTrue(restarted.sync())
        self.assertEqual(self.server.usage.snapshot()['page_views'], 12)
        restarted.increment('page_views')
        restarted.sync()
        self.assertEqual(self.server.usage.snapshot()['page_views'], 13)

    def test_network_loss_never_enters_gameplay_counting_and_pending_totals_recover(self):
        cn = RegionalUsage(self.root/'cn', self.client('cn'))
        with patch.object(cn.client, 'request', side_effect=AssertionError('network on gameplay path')):
            cn.increment('page_views')
            cn.start_round(1)
            cn.end_round(1, 'completed', 10, 1)
        with patch.object(cn.client, 'request', side_effect=OSError('unavailable')):
            self.assertFalse(cn.sync())
            self.assertFalse(cn.snapshot()['synchronized'])
            self.assertEqual(cn.snapshot()['scope'], 'regional-until-first-sync')
        restarted = RegionalUsage(self.root/'cn', self.client('cn'))
        self.assertTrue(restarted.sync())
        self.assertEqual(self.server.usage.snapshot()['completed_rounds'], 1)
        self.assertEqual(self.server.usage.snapshot()['page_views'], 1)

    def test_invalid_or_stale_aggregate_rolls_back_counters_and_checkpoint_together(self):
        local = UsageStats()
        local.increment('page_views');local.start_round(1)
        aggregate = usage_payload(local.snapshot())
        stream = secrets.token_hex(16)
        self.server.usage.apply('cn', stream, aggregate)
        aggregate['counts']['page_views'] = 10
        aggregate['levels'][0]['started_rounds'] = 0
        with self.assertRaises(ValueError):
            self.server.usage.apply('cn', stream, aggregate)
        reloaded = UsageStats(self.root/'central').snapshot()
        self.assertEqual(reloaded['page_views'], 1)
        with closing(sqlite3.connect(self.root/'central/usage.sqlite3')) as db:
            previous = json.loads(db.execute('SELECT aggregate FROM shared_streams').fetchone()[0])
        self.assertEqual(previous['counts']['page_views'], 1)

    def test_site_authentication_is_required_and_request_material_is_not_echoed(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request('POST', '/v1/usage/read', '{}', {'Content-Type': 'application/json',
            'X-ChefJeff-Site': 'cn', 'Authorization': 'Bearer wrong-credential'})
        response = connection.getresponse()
        self.assertEqual(response.status, 401)
        self.assertNotIn(b'wrong-credential', response.read())
        connection.close()
        with self.assertRaises(ValueError):
            SharedClient({**self.config('cn'), 'url': 'http://public.example'})
        with self.assertRaises(ValueError):
            SharedClient({**self.config('cn'), 'url': 'https://user:pass@public.example'})

    def test_both_real_game_origins_share_receipts_without_loosening_browser_origin_checks(self):
        servers = []
        for site, origin in [('cn', 'https://chefjeff.online'), ('global', 'https://global.chefjeff.online')]:
            server = make_server(0, origin, data_dir=self.root/site, shared_config=self.config(site))
            thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
            self.addCleanup(thread.join, 3)
            self.addCleanup(server.server_close)
            self.addCleanup(server.sessions.close)
            self.addCleanup(server.shutdown)
            servers.append(server)
        receipt = servers[0].sessions.store.save(self.record)
        connection = http.client.HTTPConnection('127.0.0.1', servers[1].server_port)
        credentials = json.dumps({'id': receipt['id'], 'deletion_token': receipt['deletion_token']})
        headers = {'Host': 'global.chefjeff.online', 'Origin': 'https://global.chefjeff.online', 'Content-Type': 'application/json'}
        connection.request('POST', '/api/contribution/download', credentials, headers)
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())['record'], self.record)
        connection.close()
        connection = http.client.HTTPConnection('127.0.0.1', servers[1].server_port)
        connection.request('POST', '/api/contribution/delete', credentials, {**headers, 'Origin': 'https://chefjeff.online'})
        response = connection.getresponse();self.assertEqual(response.status, 403);response.read();connection.close()
        with patch.object(servers[1].sessions.store, 'download', side_effect=OSError('private-detail')):
            connection = http.client.HTTPConnection('127.0.0.1', servers[1].server_port)
            connection.request('POST', '/api/contribution/download', credentials, headers)
            response = connection.getresponse();self.assertEqual(response.status, 503)
            self.assertNotIn(b'private-detail', response.read());connection.close()


if __name__ == '__main__':
    unittest.main()
