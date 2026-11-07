"""Research packages are built apart from the request, so a slow build never needs one long connection.

Synthetic records only, through the real console handlers on loopback.
"""
from contextlib import closing
import json
import sqlite3
import time
from unittest.mock import patch
from urllib.parse import urlencode

import test_admin_console as baseline
from test_admin_console import app, verify_package


class BuildTests(baseline.AdminTests):
    def slow(self, seconds=.6):
        """Make each build outlast the request's wait (both download paths add the sites), and count builds."""
        calls = []
        real = app.data.add_source_artifact
        def slow_sites(*args):
            calls.append(1)
            time.sleep(seconds)
            return real(*args)
        return calls, patch.object(app.data, 'add_source_artifact', slow_sites)

    def leftovers(self):
        return sorted(p.name for p in self.root.iterdir() if p.name not in ('auth.json', 'data'))

    def poll(self, path, cookie, method='GET', body=None, deadline=10):
        statuses = []
        end = time.monotonic() + deadline
        while time.monotonic() < end:
            status, headers, raw = self.request(path, method, body, cookie=cookie, origin=baseline.ORIGIN if method == 'POST' else None,
                                                content_type='application/x-www-form-urlencoded' if method == 'POST' else None)
            statuses.append(status)
            if status != 202:
                return statuses, headers, raw
            self.assertEqual(headers['Retry-After'], str(app.RETRY_AFTER))
            self.assertEqual(json.loads(raw)['status'], 'building')
            time.sleep(.1)
        self.fail('the package was never built')

    def test_a_slow_build_answers_building_then_serves_the_same_package_once(self):
        cookie = self.login()
        calls, slowed = self.slow()
        with patch.object(app, 'BUILD_WAIT', .1), slowed:
            statuses, headers, raw = self.poll(app.PREFIX + 'download/research.cjresearch.zip', cookie)
        self.assertEqual(statuses[0], 202)
        self.assertEqual(statuses[-1], 200)
        self.assertEqual(len(calls), 1)             # polling did not start the build again
        target = self.root / 'download.zip'
        target.write_bytes(raw)
        self.assertEqual(verify_package(target, database=self.db)['rounds'], 2)
        target.unlink()
        self.assertEqual(self.leftovers(), [])
        self.assertIn('attachment', headers['Content-Disposition'])

    def test_a_different_request_waits_while_one_is_built(self):
        cookie = self.login()
        calls, slowed = self.slow()
        with patch.object(app, 'BUILD_WAIT', .1), slowed:
            self.assertEqual(self.request(app.PREFIX + 'download/research.cjresearch.zip', cookie=cookie)[0], 202)
            status, headers, _ = self.request(app.PREFIX + 'download/research.cjresearch.zip?level=1', cookie=cookie)
            self.assertEqual(status, 429)
            self.assertEqual(headers['Retry-After'], str(app.RETRY_AFTER))
            self.assertEqual(self.poll(app.PREFIX + 'download/research.cjresearch.zip', cookie)[0][-1], 200)
        self.assertEqual(len(calls), 1)

    def test_a_record_withdrawn_after_the_build_is_not_sent(self):
        cookie = self.login()
        with patch.object(app, 'BUILD_WAIT', .1):
            refs = [r['ref'] for r in json.loads(self.request(app.PREFIX + 'api/records', cookie=cookie)[2])['records']]
            body = urlencode({'refs': json.dumps(refs[:1])})
            calls, slowed = self.slow()
            with slowed:
                path = app.PREFIX + 'download/selected.cjresearch.zip'
                status = self.request(path, 'POST', body, cookie=cookie, origin=baseline.ORIGIN,
                                      content_type='application/x-www-form-urlencoded')[0]
                self.assertEqual(status, 202)
                deadline = time.monotonic() + 5
                while self.server.build is not None and self.server.build.finished is None and time.monotonic() < deadline:
                    time.sleep(.05)
            # The record's stored text changes after the package was built and checked.
            with closing(sqlite3.connect(self.db)) as db, db:
                identifier = next(i for (i,) in db.execute('SELECT id FROM records') if app.data.reference(i) == refs[0])
                text = db.execute('SELECT record FROM records WHERE id=?', (identifier,)).fetchone()[0]
                db.execute('UPDATE records SET record=? WHERE id=?', (text + ' ', identifier))
            status, headers, raw = self.request(path, 'POST', body, cookie=cookie, origin=baseline.ORIGIN,
                                                content_type='application/x-www-form-urlencoded')
        self.assertEqual(status, 410)
        self.assertNotIn('Content-Disposition', headers)
        self.assertNotIn(b'PK', raw)
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(len(calls), 1)

    def test_a_package_nobody_fetches_is_removed(self):
        cookie = self.login()
        calls, slowed = self.slow(.3)
        with patch.object(app, 'BUILD_WAIT', .05), patch.object(app, 'BUILD_KEEP', .3), slowed:
            self.assertEqual(self.request(app.PREFIX + 'download/research.cjresearch.zip', cookie=cookie)[0], 202)
            deadline = time.monotonic() + 5
            while (self.server.build is not None or self.leftovers()) and time.monotonic() < deadline:
                time.sleep(.05)
        self.assertIsNone(self.server.build)
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(len(calls), 1)


# Only the cases above; the inherited ones already run in their own module.
for _name in dir(baseline.AdminTests):
    if _name.startswith('test_'):
        setattr(BuildTests, _name, None)
