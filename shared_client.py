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

    def request(self, operation, body):
        connection_class = http.client.HTTPSConnection if self.url.scheme == 'https' else http.client.HTTPConnection
        options = {'timeout': 3}
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


class RemoteRecords:
    def __init__(self, client):
        self.client = client

    def save(self, record):
        body = {'request_id': secrets.token_hex(16), 'created_at': time.time(),
                'deletion_token': secrets.token_urlsafe(32), 'record': record}
        # One bounded retry reuses the create ID, token and original timestamp.
        for attempt in range(2):
            try:
                return self.client.request('records/save', body)
            except OSError:
                if attempt:
                    raise

    def update(self, identifier, record):
        return self.client.request('records/update', {'id': identifier, 'record': record})

    def delete(self, identifier, token):
        return self.client.request('records/delete', {'id': identifier, 'deletion_token': token})

    def download(self, identifier, token):
        return self.client.request('records/download', {'id': identifier, 'deletion_token': token})

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
