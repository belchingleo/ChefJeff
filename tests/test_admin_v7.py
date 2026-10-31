"""A synthetic v7 round can be previewed and exported through the private HTTP API."""
import io
import json
from urllib.parse import urlencode
import zipfile

import test_admin_console as baseline
from hosted_server import HostedSession
from hosted_records import CONSENT_VERSION, ContributionStore
from research_record import record
import research_replay


class V7PreviewExportTests(baseline.AdminTests):
    def test_v7_replay_survives_authenticated_preview_and_single_record_export(self):
        session=HostedSession()
        session.store=ContributionStore(self.root/'synthetic-v7-game')
        try:
            with session.lock:
                session.connected=True
                session.stop_event.set();session.wake.set()
                self.assertEqual(session._command('/api/contribution/consent',
                    {'consent':True,'consent_version':CONSENT_VERSION})[0],200)
                self.assertEqual(session._command('/api/start',{})[0],200)
                session.k.advance(.4)
                self.assertEqual(session._command('/api/end',{})[0],200)
                synthetic=record(session)
        finally:session.close()
        self.assertEqual(synthetic['consent_version'],'pilot-session-2026-10-v7')
        self.assertIsNotNone(synthetic['replay'])
        receipt=ContributionStore(self.db.parent).save(synthetic)
        import admin_data
        ref=admin_data.reference(receipt['id']);cookie=self.login()
        status,_,raw=self.request('/research-admin/api/preview?ref='+ref,cookie=cookie)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['metadata']['replay'],synthetic['replay'])
        status,_,raw=self.request('/research-admin/download/selected.cjresearch.zip','POST',
            urlencode({'refs':json.dumps([ref])}),cookie=cookie,origin=baseline.ORIGIN,
            content_type='application/x-www-form-urlencoded')
        self.assertEqual(status,200)
        target=self.root/'v7-synthetic.zip';target.write_bytes(raw)
        self.assertEqual(baseline.verify_package(target,database=self.db)['rounds'],1)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            metadata=json.loads(archive.read(ref+'/metadata.json'))
            self.assertEqual(metadata['consent_version'],'pilot-session-2026-10-v7')
            self.assertEqual(metadata['replay'],synthetic['replay'])
        self.assertEqual(research_replay.check(synthetic)['replay'],'verified')
