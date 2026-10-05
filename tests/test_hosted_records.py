import json
from pathlib import Path
import tempfile
import time
import unittest
from hosted_records import ContributionStore, CONSENT_VERSION
from hosted_server import HostedSession


class ContributionTests(unittest.TestCase):
    def test_opt_in_only_and_idempotent_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            store=ContributionStore(d);s=HostedSession();s.store=store
            try:
                self.assertEqual(s._command('/api/contribution/save',{'consent':True,'consent_version':CONSENT_VERSION})[0],409)
                s._command('/api/browser-ready',{'connected':True});s._command('/api/start',{})
                s.tick();s._command('/api/end',{})
                with store.connect() as db:self.assertEqual(db.execute('select count(*) from records').fetchone()[0],0)
                self.assertEqual(s._command('/api/contribution/save',{'consent':False,'consent_version':CONSENT_VERSION})[0],400)
                body={'consent':True,'consent_version':CONSENT_VERSION}
                code,reply=s._command('/api/contribution/save',body)
                self.assertEqual(code,200)
                self.assertEqual(reply,s._command('/api/contribution/save',body)[1])
                with store.connect() as db:
                    rows=db.execute('select record from records').fetchall()
                    self.assertEqual(len(rows),1)
                    self.assertNotIn('api_key',rows[0][0])
                    self.assertNotIn('payload',rows[0][0])
                    self.assertIn('positions',json.loads(rows[0][0]))
                r=reply['receipt']
                self.assertFalse(store.delete(r['id'],'wrong'))
                self.assertTrue(store.delete(r['id'],r['deletion_token']))
                self.assertFalse(store.delete(r['id'],r['deletion_token']))
            finally:s.close()
    def test_standing_consent_is_recorded_and_other_modes_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            store=ContributionStore(d);s=HostedSession();s.store=store
            try:
                s._command('/api/browser-ready',{'connected':True});s._command('/api/start',{});s.tick();s._command('/api/end',{})
                body={'consent':True,'consent_version':CONSENT_VERSION}
                self.assertEqual(s._command('/api/contribution/save',{**body,'consent_mode':'always'})[0],400)
                self.assertEqual(s._command('/api/contribution/save',{**body,'consent_mode':'standing'})[0],200)
                with store.connect() as db:
                    self.assertEqual(json.loads(db.execute('select record from records').fetchone()[0])['consent_mode'],'standing')
            finally:s.close()
    def test_expiry_capacity_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            store=ContributionStore(d,limit=1)
            receipt=store.save({'schema':'test'})
            self.assertEqual(store.path.stat().st_mode&0o777,0o600)
            with self.assertRaises(ValueError):store.save({})
            self.assertNotIn(receipt['deletion_token'].encode(),store.path.read_bytes())
            store.prune(time.time()+31*86400)
            with store.connect() as db:self.assertEqual(db.execute('select count(*) from records').fetchone()[0],0)
            self.assertNotIn(b'"schema":"test"',store.path.read_bytes())

if __name__=='__main__':unittest.main()
