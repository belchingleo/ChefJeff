"""Backend clients. Aggregate delivery stays outside gameplay request threads."""
from contextlib import closing
import http.client
import json
from pathlib import Path
import re
import secrets
import ssl
import sqlite3
import threading
import time
from urllib.parse import urlsplit

from hosted_usage import UsageStats
from shared_data import usage_payload, encode


class SharedClient:
    def __init__(self, config):
        if set(config) != {'url', 'site', 'token'}:
            raise ValueError('Invalid shared client configuration')
        self.url = urlsplit(config['url'])
        if (self.url.scheme not in ('http', 'https') or not self.url.hostname
                or self.url.username or self.url.password or self.url.query or self.url.fragment
                or self.url.path not in ('', '/')
                or (self.url.scheme == 'http' and self.url.hostname not in ('127.0.0.1', 'localhost'))):
            raise ValueError('Use HTTPS, or HTTP on loopback only')
        if (not isinstance(config['site'], str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', config['site'])
                or not isinstance(config['token'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', config['token'])):
            raise ValueError('Invalid site credentials')
        self.site, self.token = config['site'], config['token']

    def request(self, operation, body, timeout=3):
        # The timeout bounds the whole send (Python's sendall) and then each read of the reply.
        connection_class = http.client.HTTPSConnection if self.url.scheme == 'https' else http.client.HTTPConnection
        options = {'timeout': timeout}
        if self.url.scheme == 'https':
            options['context'] = ssl.create_default_context()
        connection = connection_class(self.url.hostname, self.url.port, **options)
        try:
            connection.request('POST', '/v1/'+operation, encode(body).encode(),
                               {'Authorization': 'Bearer '+self.token, 'X-ChefJeff-Site': self.site,
                                'Content-Type': 'application/json'})
            response = connection.getresponse()
            raw = response.read(14_000_001)
            if response.status != 200 or len(raw) > 14_000_000:
                raise OSError('Shared data request failed')
            value = json.loads(raw)
            if not isinstance(value, dict) or set(value) != {'value'}:
                raise OSError('Invalid shared data response')
            return value['value']
        except (ValueError, http.client.HTTPException):
            raise OSError('Shared data connection failed') from None
        finally:
            connection.close()


# Between the sites a whole round's record (about 1-5 MB) takes many seconds: on 2026-11-26 Germany fetched 1.6 MB from
# Shanghai in 6-11 s (about 150-280 KB/s), so every full overseas round ran out of the 3 s that small requests get and
# was never stored. Records get their own time; a finished round's record goes out in the background, retried.
SAVE_SECONDS = 8                # a round's opening record (a few KB), sent while the round starts
RECORD_SECONDS = 300            # a whole record either way (update, a receipt's download); the largest is 13 MB,
                                # which needs 300 s at about 45 KB/s (0.11.1: 120 s left no room for a slow hour)
RETRY_SECONDS = (10, 30, 60, 120, 300)
CLOSE_SECONDS = 45              # how long a stopping server waits for records still to be sent


class RemoteRecords:
    def __init__(self, client, retry_seconds=RETRY_SECONDS, record_seconds=RECORD_SECONDS):
        self.client = client
        self.retry_seconds, self.record_seconds = tuple(retry_seconds), record_seconds
        # record id -> {'create': the create request still to send or None, 'record': the newest update still to send
        # or None, 'tries': failed sends so far, 'due': monotonic time it may go}
        self.queue = {}
        self.queue_changed = threading.Condition()
        self.sending = None                 # the record id being sent now
        self.closing = False
        self.thread = None
        self.given_up = 0                   # records dropped after every retry failed

    @staticmethod
    def create_body(record):
        return {'request_id': secrets.token_hex(16), 'created_at': time.time(),
                'deletion_token': secrets.token_urlsafe(32), 'record': record}

    def save(self, record):
        body = self.create_body(record)
        # One bounded retry reuses the create ID, token and original timestamp.
        for attempt in range(2):
            try:
                return self.client.request('records/save', body, self.record_seconds)
            except OSError:
                if attempt:
                    raise

    def save_later(self, record):
        """The receipt for this record at once, with the record sent in the background (2026-11-27). A round's start
        and the player's 贡献本局 used to wait for the record to reach Shanghai, and a page gives up after 5 s (start)
        or 10 s (contribution): on the overseas site a whole round's record never got there in time. The service keeps
        the id and deletion token the create request names, and its expiry is the request's creation time plus the
        retention period (shared_data, ContributionStore.create), so the receipt is known before the record is sent.
        A failed create is sent again unchanged (the service takes a repeated create as the same record); updates
        queued meanwhile go after it."""
        from hosted_records import CONSENT_VERSION, RETENTION_SECONDS
        from datetime import datetime, timezone
        body = self.create_body(record)
        with self.queue_changed:
            if self.closing:
                raise OSError('Record delivery has stopped')
            self.queue[body['request_id']] = {'create': body, 'record': None, 'tries': 0, 'due': 0.0}
            self._start_thread()
        return {'id': body['request_id'], 'deletion_token': body['deletion_token'],
                'expires_at': datetime.fromtimestamp(body['created_at'] + RETENTION_SECONDS, timezone.utc).isoformat(),
                'consent_version': CONSENT_VERSION}

    def update(self, identifier, record):
        return self.client.request('records/update', {'id': identifier, 'record': record}, self.record_seconds)

    def update_later(self, identifier, record):
        """Send this record in the background and return at once, so a round never waits on the link between the
        sites. Only the newest snapshot of a record is kept; a failed send is tried again after each of RETRY_SECONDS.
        An update the service refuses because the record was withdrawn or has expired is dropped (it cannot bring the
        record back)."""
        with self.queue_changed:
            if self.closing:
                raise OSError('Record delivery has stopped')
            entry = self.queue.get(identifier)
            if entry and entry['create']:
                entry['record'] = record            # after the create still waiting to go
            else:
                self.queue[identifier] = {'create': None, 'record': record, 'tries': 0, 'due': 0.0}
            self._start_thread()

    def _start_thread(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._deliver, name='shared-records', daemon=True)
            self.thread.start()
        self.queue_changed.notify_all()

    def pending(self):
        with self.queue_changed:
            return len(self.queue) + (self.sending is not None)

    def _deliver(self):
        while True:
            with self.queue_changed:
                while True:
                    if not self.queue:
                        if self.closing:
                            return
                        self.queue_changed.wait()
                        continue
                    identifier, entry = min(self.queue.items(), key=lambda item: item[1]['due'])
                    wait = entry['due'] - time.monotonic()
                    if wait <= 0 or self.closing:
                        break
                    self.queue_changed.wait(wait)
                del self.queue[identifier]
                self.sending = identifier
            create = entry['create']
            try:
                if create:
                    self.client.request('records/save', create, self.record_seconds)
                else:
                    self.update(identifier, entry['record'])
                error = None
            except OSError as failure:
                error = failure
            with self.queue_changed:
                self.sending = None
                self.queue_changed.notify_all()
                newer = self.queue.get(identifier)
                if error is None:
                    if create and entry['record'] is not None and newer is None:
                        self.queue[identifier] = {'create': None, 'record': entry['record'], 'tries': 0, 'due': 0.0}
                    continue                # created or updated; an update queued meanwhile goes next
                if create:
                    # The create must go first, unchanged; a newer snapshot queued meanwhile follows it.
                    record = newer['record'] if newer else entry['record']
                    retry = {'create': create, 'record': record}
                elif newer:
                    continue                # a newer snapshot replaces the one that failed
                else:
                    retry = {'create': None, 'record': entry['record']}
                tries = entry['tries']
                if self.closing or tries >= len(self.retry_seconds):
                    self.queue.pop(identifier, None)
                    self.given_up += 1
                    print(f'shared records: gave up on a record after {tries + 1} tries ({error})', flush=True)
                    continue
                self.queue[identifier] = {**retry, 'tries': tries + 1, 'due': time.monotonic() + self.retry_seconds[tries]}
                print(f'shared records: sending a record failed ({error}); trying again in {self.retry_seconds[tries]} s',
                      flush=True)

    def close(self, wait=CLOSE_SECONDS):
        """Stop taking records and send the ones still queued (each tried once more), waiting up to wait seconds."""
        with self.queue_changed:
            self.closing = True
            self.queue_changed.notify_all()
            thread = self.thread
        if thread:
            thread.join(timeout=wait)

    def delete(self, identifier, token):
        with self.queue_changed:
            self.queue.pop(identifier, None)    # a withdrawn round's queued snapshot is never sent
            # A create already on its way must land before the delete, or it would bring the round back after it.
            deadline = time.monotonic() + self.record_seconds
            while self.sending == identifier and time.monotonic() < deadline:
                self.queue_changed.wait(deadline - time.monotonic())
            self.queue.pop(identifier, None)
        return self.client.request('records/delete', {'id': identifier, 'deletion_token': token}, SAVE_SECONDS)

    def download(self, identifier, token):
        return self.client.request('records/download', {'id': identifier, 'deletion_token': token}, self.record_seconds)

    def accept_terms(self, identifier, token):
        return self.client.request('records/terms', {'id': identifier, 'deletion_token': token}, SAVE_SECONDS)

    def prune(self):
        # The authoritative service owns expiry, independently of game processes.
        pass


class RegionalUsage(UsageStats):
    def __init__(self, directory, client):
        directory = Path(directory) / 'shared-usage-outbox'
        super().__init__(directory)
        if self.path is None:
            raise OSError('Regional usage outbox unavailable')
        # Keep the stream identity in the same durable file as its cumulative totals.
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS shared_identity (id INTEGER PRIMARY KEY CHECK(id=1), stream TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO shared_identity VALUES (1,?)', (secrets.token_hex(16),))
            self.stream = db.execute('SELECT stream FROM shared_identity WHERE id=1').fetchone()[0]
        if not re.fullmatch(r'[0-9a-f]{32}', self.stream):
            raise ValueError('Invalid usage outbox identity')
        self.client = client
        self.stop = threading.Event()
        self.sync_lock = threading.Lock()
        self.status_lock = threading.Lock()
        self.central = None
        self.last_sync = 0
        self.delivery_errors = 0
        self.running = lambda: 0
        self.thread = None

    def sync(self):
        with self.sync_lock:
            local = super().snapshot()
            try:
                if not local['persistent']:
                    raise OSError('Regional outbox is not durable')
                central = self.client.request('usage/push', {'stream': self.stream,
                    'aggregate': usage_payload(local), 'running': self.running()})
                if not isinstance(central, dict) or central.get('shared') is not True:
                    raise OSError('Invalid aggregate response')
            except OSError:
                with self.status_lock:
                    self.delivery_errors += 1
                return False
            with self.status_lock:
                self.central = central
                self.last_sync = time.monotonic()
            return True

    def start(self, running):
        self.running = running
        def deliver():
            while not self.stop.is_set():
                self.sync()
                self.stop.wait(2)
        self.thread = threading.Thread(target=deliver, name='shared-usage', daemon=True)
        self.thread.start()

    def snapshot(self):
        local = super().snapshot()
        with self.status_lock:
            return {**(self.central or local), 'shared': True,
                    'scope': 'global' if self.central else 'regional-until-first-sync',
                    'synchronized': bool(self.last_sync and time.monotonic() - self.last_sync < 15),
                    'delivery_errors': self.delivery_errors, 'regional_persistent': local['persistent'],
                    'regional_storage_errors': local['storage_errors']}

    def close(self):
        if self.stop.is_set():
            return
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=4)
        self.sync()
