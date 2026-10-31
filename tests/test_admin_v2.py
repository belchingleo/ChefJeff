"""Synthetic-only tests for selection, previews, analysis and authenticated source tagging."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import zipfile

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ops' / 'research_admin'))

import test_admin_console as baseline
import admin_data as data
import source_observer
from source_observer import SourceObserver
from hosted_records import RETENTION_SECONDS, CONSENT_VERSION
from shared_data import SharedUsage, usage_payload
from hosted_usage import UsageStats
from shared_client import SharedClient
import shared_server


class V2Tests(baseline.AdminTests):
    def refs(self):
        return json.loads(self.request('/research-admin/api/records',cookie=self.login())[2])['records']

    def source(self):
        with patch.object(source_observer.time,'time',return_value=time.time()-300):
            observer=SourceObserver(self.db.parent,RETENTION_SECONDS)
        observer.save_receipt('cn',self.full)
        return observer

    def selected(self,refs,cookie):
        return self.request('/research-admin/download/selected.cjresearch.zip','POST',urlencode({'refs':json.dumps(refs)}),cookie=cookie,origin=baseline.ORIGIN,content_type='application/x-www-form-urlencoded')

    def test_single_and_multiple_selected_export_exactly_match_selection(self):
        self.source();cookie=self.login()
        refs=[r['ref'] for r in json.loads(self.request('/research-admin/api/records',cookie=cookie)[2])['records']]
        for selection in (refs[:1],refs):
            status,headers,raw=self.selected(selection,cookie)
            self.assertEqual(status,200)
            target=self.root/'selected.zip';target.write_bytes(raw)
            manifest=baseline.verify_package(target,database=self.db)
            self.assertEqual(manifest['rounds'],len(selection))
            self.assertEqual({s['source_ref'] for s in manifest['sources']},set(selection))
            with zipfile.ZipFile(target) as z:
                origin=json.loads(z.read('source-sites.json'))
                self.assertEqual({r['source_ref'] for r in origin['records']},set(selection))
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),self.before)

    def test_selected_download_validation_auth_and_withdrawal(self):
        refs=[r['ref'] for r in self.refs()];cookie=self.login()
        self.assertEqual(self.selected(refs,None)[0],401)
        for invalid in ([],refs+refs,[refs[0]]*51,['../../anything'],[1]):
            self.assertEqual(self.selected(invalid,cookie)[0],400)
        with sqlite3.connect(self.db) as c:c.execute('DELETE FROM records WHERE id=?',(self.full['id'],))
        self.assertEqual(self.selected([data.reference(self.full['id'])],cookie)[0],410)

    def test_preview_paginates_events_and_preserves_original_record(self):
        self.source();cookie=self.login();ref=data.reference(self.full['id'])
        status,_,raw=self.request('/research-admin/api/preview?'+urlencode({'ref':ref}),cookie=cookie)
        self.assertEqual(status,200);preview=json.loads(raw)
        self.assertEqual(preview['site'],'cn')
        self.assertEqual(preview['metadata']['round_id'],self.sample['round_id'])
        self.assertNotIn('events',preview['metadata'])
        self.assertEqual(preview['event_total'],len(self.sample['events']))
        status,_,raw=self.request('/research-admin/api/preview?'+urlencode({'ref':ref,'type':'start'}),cookie=cookie)
        self.assertEqual(status,200);self.assertTrue(all(e['type']=='start' for e in json.loads(raw)['events']))
        self.assertEqual(self.request('/research-admin/api/preview?ref='+ref)[0],401)
        self.assertEqual(self.request('/research-admin/api/preview?ref=../../bad',cookie=cookie)[0],400)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),self.before)

    def test_analysis_uses_entire_dataset_and_missing_denominators(self):
        self.source();cookie=self.login()
        def analysis(metric,group='site',extra=None):
            query={'metric':metric,'group':group,**(extra or {})}
            status,_,raw=self.request('/research-admin/api/analysis?'+urlencode(query),cookie=cookie)
            self.assertEqual(status,200);return json.loads(raw)
        result=analysis('records')
        self.assertEqual(result['records'],2)
        self.assertEqual({g['label']:g['value'] for g in result['groups']},{'国内站 · 上海':1,'来源未知':1})
        complete=analysis('complete_rate','day')
        self.assertEqual(complete['eligible'],2);self.assertEqual(complete['groups'][0]['value'],50)
        wins=analysis('win_rate','day')
        self.assertEqual(wins['records'],2);self.assertEqual(wins['eligible'],1)
        self.assertEqual(wins['groups'][0]['value'],0)
        selected=analysis('records','day',{'refs':json.dumps([data.reference(self.full['id'])])})
        self.assertEqual(selected['records'],1)
        self.assertEqual(analysis('records','site',{'site':'cn'})['records'],1)
        self.assertEqual(analysis('records','site',{'site':'global'})['records'],0)

    def test_dynamic_levels_and_site_filtered_download(self):
        self.source();cookie=self.login()
        for site,count in [('cn',1),('global',0),('unknown',1)]:
            body=json.loads(self.request('/research-admin/api/records?site='+site,cookie=cookie)[2]);self.assertEqual(body['total'],count)
        status,_,raw=self.request('/research-admin/download/research.cjresearch.zip?site=cn',cookie=cookie)
        self.assertEqual(status,200)
        target=self.root/'region.zip';target.write_bytes(raw);self.assertEqual(baseline.verify_package(target,database=self.db)['rounds'],1)
        with sqlite3.connect(self.db) as c:
            # Metadata selector supports future IDs; old record validation remains strict.
            future=deepcopy(self.sample);future['level']=7
            c.execute('INSERT INTO records VALUES (?,?,?,?)',('synthetic-future-level','unused',time.time()+1000,json.dumps(future)))
        self.assertIn(7,json.loads(self.request('/research-admin/api/options',cookie=cookie)[2])['levels'])

    def test_regional_usage_is_snapshot_consistent_and_keeps_unknown_history(self):
        usage=SharedUsage(self.db.parent)
        for site,views in [('cn',10),('global',20)]:
            stats=UsageStats()
            for _ in range(views):stats.increment('page_views')
            usage.apply(site,secrets.token_hex(16),usage_payload(stats.snapshot()))
        with sqlite3.connect(usage.path) as c:c.execute('UPDATE totals SET page_views=page_views+12 WHERE id=1')
        before=hashlib.sha256(usage.path.read_bytes()).hexdigest()
        result=data.regional_usage(self.db)
        self.assertEqual(result['totals']['page_views'],42)
        self.assertEqual({r['site']:r['page_views'] for r in result['sites']},{'cn':10,'global':20,'unknown':12})
        self.assertEqual(hashlib.sha256(usage.path.read_bytes()).hexdigest(),before)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),self.before)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.tokens={site:secrets.token_urlsafe(32) for site in ('cn','global')}
        Handler,Server=source_observer.observed_classes(shared_server)
        self.handler_patch=patch.object(shared_server,'DataHandler',Handler);self.handler_patch.start()
        self.server=Server(0,self.root/'data',self.tokens)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.record=json.loads((baseline.RELEASE/'tests/fixtures/research-v2-short.json').read_text());self.record['consent_version']=CONSENT_VERSION

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3);self.handler_patch.stop();self.temp.cleanup()

    def client(self,site,token=None):
        return SharedClient({'url':f'http://127.0.0.1:{self.server.server_port}','site':site,'token':token or self.tokens[site]})

    def body(self,created_at=None):
        return {'request_id':secrets.token_hex(16),'created_at':time.time() if created_at is None else created_at,
                'deletion_token':secrets.token_urlsafe(32),'record':deepcopy(self.record)}

    def test_authenticated_origin_creation_is_stable_on_retry_and_cross_site_update(self):
        body=self.body();receipt=self.client('global').request('records/save',body)
        self.assertEqual(data.source_index(self.root/'data/contributions.sqlite3')['sources'][data.reference(receipt['id'])],'global')
        self.assertEqual(self.client('global').request('records/save',body),receipt)
        self.client('cn').request('records/update',{'id':receipt['id'],'record':self.record})
        self.assertEqual(data.source_index(self.root/'data/contributions.sqlite3')['sources'][data.reference(receipt['id'])],'global')
        # Retrying the same create through another trusted site never overwrites first provenance.
        self.client('cn').request('records/save',body)
        self.assertEqual(data.source_index(self.root/'data/contributions.sqlite3')['sources'][data.reference(receipt['id'])],'global')
        downloaded=self.client('cn').request('records/download',{'id':receipt['id'],'deletion_token':receipt['deletion_token']})
        self.assertEqual(downloaded,self.record)

    def test_historical_create_is_not_backfilled_and_withdrawal_removes_index(self):
        old=self.client('global').request('records/save',self.body(time.time()-600))
        self.assertNotIn(data.reference(old['id']),data.source_index(self.root/'data/contributions.sqlite3')['sources'])
        new=self.client('cn').request('records/save',self.body())
        self.assertIn(data.reference(new['id']),data.source_index(self.root/'data/contributions.sqlite3')['sources'])
        self.assertTrue(self.client('global').request('records/delete',{'id':new['id'],'deletion_token':new['deletion_token']}))
        self.assertNotIn(data.reference(new['id']),data.source_index(self.root/'data/contributions.sqlite3')['sources'])

    def test_bad_auth_never_creates_source_metadata(self):
        with self.assertRaises(Exception):self.client('cn',secrets.token_urlsafe(32)).request('records/save',self.body())
        self.assertEqual(data.source_index(self.root/'data/contributions.sqlite3')['sources'],{})

    def test_restart_does_not_backfill_records_from_a_prior_capture_gap(self):
        body=self.body(time.time()-600)
        receipt=self.server.records.create(body['request_id'],body['deletion_token'],body['created_at'],body['record'])
        with sqlite3.connect(self.server.source_observer.path) as db:
            db.execute('UPDATE meta SET tracking_since=? WHERE id=1',(time.time()-1000,))
        restarted=SourceObserver(self.root/'data',RETENTION_SECONDS)
        restarted.save_receipt('global',receipt)
        self.assertNotIn(data.reference(receipt['id']),data.source_index(self.root/'data/contributions.sqlite3')['sources'])

    def test_metadata_failure_keeps_original_save_success(self):
        with patch.object(self.server.source_observer,'save_receipt',side_effect=sqlite3.OperationalError('synthetic failure')):
            receipt=self.client('global').request('records/save',self.body())
        self.assertEqual(self.client('cn').request('records/download',{'id':receipt['id'],'deletion_token':receipt['deletion_token']}),self.record)
        self.assertEqual(self.server.source_observer.failures,1)

    def test_cleanup_snapshot_cannot_erase_a_concurrently_added_tag(self):
        snapshot,created=threading.Event(),threading.Event()
        real_connect=sqlite3.connect
        class Cursor:
            def __init__(self,cursor):self.cursor=cursor
            def __iter__(self):
                old=self.cursor.fetchall();snapshot.set()
                if not created.wait(3):raise AssertionError('fixture insert did not finish')
                return iter(old)
        class Connection:
            def __init__(self,conn):self.conn=conn
            def execute(self,sql,*args):
                cursor=self.conn.execute(sql,*args)
                return Cursor(cursor) if sql.startswith('SELECT id FROM records') else cursor
            def close(self):self.conn.close()
        def connect(path,*args,**kw):
            conn=real_connect(path,*args,**kw)
            return Connection(conn) if isinstance(path,str) and path.endswith('contributions.sqlite3?mode=ro') else conn
        errors=[]
        def sweep():
            try:self.server.source_observer.prune()
            except BaseException as error:errors.append(error)
        with patch.object(source_observer.sqlite3,'connect',side_effect=connect):
            worker=threading.Thread(target=sweep);worker.start();self.assertTrue(snapshot.wait(3))
            body=self.body()
            receipt=self.server.records.create(body['request_id'],body['deletion_token'],body['created_at'],body['record'])
            saving=threading.Thread(target=lambda:self.server.source_observer.save_receipt('cn',receipt));saving.start()
            # Permit an unlocked implementation to insert before the old snapshot is used.
            saving.join(.1);created.set();worker.join(3);saving.join(3)
        self.assertFalse(errors)
        self.assertFalse(worker.is_alive());self.assertFalse(saving.is_alive())
        self.assertEqual(data.source_index(self.root/'data/contributions.sqlite3')['sources'][data.reference(receipt['id'])],'cn')


if __name__=='__main__':unittest.main(verbosity=2)
