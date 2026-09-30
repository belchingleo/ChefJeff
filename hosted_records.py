"""Opt-in pilot session records, separate from ephemeral kitchen and model transport."""
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
from feedback import EVENTS

RETENTION_SECONDS = 30 * 86400
CONSENT_VERSION = 'pilot-session-2026-09-v1'


def pilot_record(session):
    """All values originate from the engine or finite communication choices, never request/provider text."""
    k = session.k
    events = []
    log = getattr(session, 'session_log', None)
    # Derived from the session's single event stream when one exists.
    source = ([{'t': r['game_time_ms']/1000, 'kind': r['type'], 'actor': r.get('actor_id'), **r['payload']}
               for r in log.engine_events()] if log and log.session.k is k else k.events)
    for e in source:
        if e.get('kind') not in EVENTS: continue
        row = {'t':e['t'], 'kind':e['kind']}
        if e.get('actor') in ('human','jeff'): row['actor'] = e['actor']
        a = e.get('action', '')
        if re.fullmatch(r'[a-zA-Z0-9_ .-]{1,90}', a): row['action'] = a
        events.append(row)
    return {'schema':'chefjeff-pilot-session-v1', 'consent_version':CONSENT_VERSION,
        'purpose':'Improve the cooperative game and develop whole-session evaluation methods; no public raw-data release.',
        'release':session.release, 'level':k.c.get('level',1), 'speed':session.speed,
        'duration':round(k.time,3), 'aborted':bool(k.aborted),
        'result':{'served':k.served,'money':k.money,'won':k.won()},
        'events':events,
        'communication':[{'t':m['game_time'],'code':m['code']} for m in session.player_messages],
        'positions':list(session.positions),
        'coverage':'Engine events and 1-second chef position samples, not a full deterministic replay or finalized benchmark schema.'}


class ContributionStore:
    def __init__(self, directory, limit=1000):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'contributions.sqlite3'
        self.limit = limit
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
        encoded = json.dumps(record, ensure_ascii=False, separators=(',',':'))
        if len(encoded.encode()) > 2_000_000: raise ValueError('Session record exceeds storage limit.')
        with self.connect() as db:
            # Transaction serializes capacity check and insertion across sessions.
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM records').fetchone()[0] >= self.limit:
                raise ValueError('Contribution storage is full. Please keep your local export.')
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
