"""Opt-in pilot session records, separate from ephemeral kitchen and model transport."""
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time

RETENTION_SECONDS = 30 * 86400
CONSENT_VERSION = 'pilot-session-2026-10-v4'


def pilot_record(session):
    """Safe v2 projection of the only session log; old stored v1 records stay untouched."""
    from research_record import record
    return record(session)


class ContributionStore:
    def __init__(self, directory, limit=1000, byte_limit=256_000_000):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'contributions.sqlite3'
        self.limit = limit
        self.byte_limit = byte_limit
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, deletion_hash TEXT NOT NULL, expires REAL NOT NULL, record TEXT NOT NULL)')
        self.path.chmod(0o600)
        self.prune()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('PRAGMA secure_delete=ON')
            with db:
                yield db
        finally:
            db.close()

    def prune(self, now=None):
        with self.connect() as db:
            db.execute('DELETE FROM records WHERE expires <= ?', (time.time() if now is None else now,))

    def save(self, record):
        self.prune()
        identifier, token = secrets.token_urlsafe(18), secrets.token_urlsafe(32)
        expires = time.time() + RETENTION_SECONDS
        if record.get('schema') == 'chefjeff-pilot-session-v2':
            from research_record import validate_record
            validate_record(record)
        encoded = json.dumps(record, ensure_ascii=False, separators=(',',':'), allow_nan=False)
        if len(encoded.encode()) > 13_000_000: raise ValueError('Session record exceeds storage limit.')
        with self.connect() as db:
            # Transaction serializes capacity check and insertion across sessions.
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM records').fetchone()[0] >= self.limit:
                raise ValueError('Contribution storage is full. Please keep your local export.')
            stored_bytes = db.execute('SELECT coalesce(sum(length(CAST(record AS BLOB))),0) FROM records').fetchone()[0]
            if stored_bytes + len(encoded.encode()) > self.byte_limit:
                raise ValueError('Contribution byte capacity reached.')
            db.execute('INSERT INTO records VALUES (?,?,?,?)',
                (identifier, hashlib.sha256(token.encode()).hexdigest(), expires, encoded))
        return {'id':identifier,'deletion_token':token,
                'expires_at':datetime.fromtimestamp(expires,timezone.utc).isoformat(),
                'consent_version':CONSENT_VERSION}

    def delete(self, identifier, token):
        if not isinstance(identifier,str) or not isinstance(token,str) or len(identifier)>100 or len(token)>100: return False
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as db:
            row = db.execute('SELECT deletion_hash FROM records WHERE id=?',(identifier,)).fetchone()
            if not row or not secrets.compare_digest(row[0],digest): return False
            db.execute('DELETE FROM records WHERE id=?',(identifier,))
        return True

    def update(self, identifier, record):
        """Update an already consented round; deletion/expiry cannot resurrect it."""
        from research_record import validate_record
        validate_record(record)
        encoded = json.dumps(record, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        if len(encoded.encode()) > 13_000_000:
            raise ValueError('Session record exceeds storage limit.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            stored_bytes = db.execute('SELECT coalesce(sum(length(CAST(record AS BLOB))),0) FROM records WHERE id!=?', (identifier,)).fetchone()[0]
            if stored_bytes + len(encoded.encode()) > self.byte_limit:
                raise ValueError('Contribution byte capacity reached.')
            return bool(db.execute('UPDATE records SET record=? WHERE id=? AND expires>?',
                                   (encoded, identifier, time.time())).rowcount)

    def download(self, identifier, token):
        if not isinstance(identifier, str) or not isinstance(token, str) or max(len(identifier), len(token)) > 100:
            return None
        with self.connect() as db:
            row = db.execute('SELECT deletion_hash,record FROM records WHERE id=? AND expires>?',
                             (identifier, time.time())).fetchone()
            if row and secrets.compare_digest(row[0], hashlib.sha256(token.encode()).hexdigest()):
                return json.loads(row[1])
        return None
