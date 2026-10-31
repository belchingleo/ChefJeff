"""Authenticated site provenance in a separate expiring index, never inside research records."""
from contextlib import closing
from datetime import datetime
import hashlib
from pathlib import Path
import sqlite3
import threading
import time


class SourceObserver:
    def __init__(self, directory, retention_seconds):
        self.directory = Path(directory)
        self.path = self.directory/'record-sources.sqlite3'
        self.retention_seconds = retention_seconds
        self.lock = threading.Lock()
        self.failures = 0
        self.capture_since = time.time()
        with closing(sqlite3.connect(self.path, timeout=1)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), tracking_since REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sources (ref TEXT PRIMARY KEY, site TEXT NOT NULL, expires REAL NOT NULL)')
            db.execute('INSERT OR IGNORE INTO meta VALUES (1,?)', (time.time(),))
            self.tracking_since = db.execute('SELECT tracking_since FROM meta WHERE id=1').fetchone()[0]
        self.path.chmod(0o600)

    def save_receipt(self, site, receipt):
        if site not in ('cn','global') or not isinstance(receipt,dict):
            return
        expiry = datetime.fromisoformat(receipt['expires_at'].replace('Z','+00:00')).timestamp()
        # Do not backfill historical records when an old create is retried after installation.
        if expiry-self.retention_seconds+0.000001 < self.capture_since:
            return
        ref = hashlib.sha256(receipt['id'].encode()).hexdigest()[:24]
        with self.lock, closing(sqlite3.connect(self.path, timeout=1)) as db, db:
            db.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?)', (ref,site,expiry))

    def prune(self):
        # Remove withdrawn/expired provenance as well. Read IDs only, never deletion hashes.
        original = (self.directory/'contributions.sqlite3').resolve().as_uri()+'?mode=ro'
        # Hold the same lock as insertion across the source snapshot and deletion.
        # A contribution may commit meanwhile, but its new provenance is inserted only
        # after this sweep, so an older ID snapshot cannot erase a newly inserted tag.
        with self.lock:
            with closing(sqlite3.connect(original,uri=True,timeout=1)) as source:
                source.execute('PRAGMA query_only=ON')
                active = {hashlib.sha256(row[0].encode()).hexdigest()[:24] for row in
                          source.execute('SELECT id FROM records WHERE expires>?',(time.time(),))}
            with closing(sqlite3.connect(self.path,timeout=1)) as db, db:
                for ref, expiry in db.execute('SELECT ref,expires FROM sources').fetchall():
                    if ref not in active or expiry<=time.time():
                        db.execute('DELETE FROM sources WHERE ref=?',(ref,))


def observed_classes(module):
    """Extend the original handler without changing auth, save, update or HTTP results."""
    from hosted_records import RETENTION_SECONDS
    OriginalHandler, OriginalServer = module.DataHandler, module.DataServer

    class ObservedHandler(OriginalHandler):
        def reply(self, status, value):
            if status == 200:
                try:
                    if self.path == '/v1/records/save':
                        # Original do_POST has already checked this site's private token.
                        self.server.source_observer.save_receipt(self.headers.get('X-ChefJeff-Site',''),value.get('value'))
                    elif self.path == '/v1/records/delete' and value.get('value') is True:
                        self.server.source_observer.prune()
                    elif self.path == '/v1/health':
                        value = {'value': {**value['value'], 'source_tracking': True,
                            'source_tracking_since': self.server.source_observer.tracking_since,
                            'source_metadata_errors': self.server.source_observer.failures}}
                except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):
                    # A metadata problem must never turn a successful contribution into failure.
                    self.server.source_observer.failures += 1
            return super().reply(status,value)

    class ObservedServer(OriginalServer):
        def __init__(self, port, directory, sites):
            super().__init__(port,directory,sites)
            try:
                self.source_observer = SourceObserver(directory,RETENTION_SECONDS)
            except BaseException:
                super().server_close()
                raise
            self._source_stop = threading.Event()
            def sweep():
                while not self._source_stop.wait(30):
                    try:
                        self.source_observer.prune()
                    except (OSError,ValueError,sqlite3.Error):
                        self.source_observer.failures += 1
            self._source_thread = threading.Thread(target=sweep,daemon=True)
            self._source_thread.start()

        def server_close(self):
            if hasattr(self,'_source_stop'):
                self._source_stop.set()
                self._source_thread.join(2)
            super().server_close()

    return ObservedHandler, ObservedServer
