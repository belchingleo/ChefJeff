"""Single-authority records and atomic, retry-safe regional usage aggregation."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

from hosted_records import ContributionStore, CONSENT_VERSION, RETENTION_SECONDS
from hosted_usage import COUNTERS, OUTCOMES, DURATION_BUCKETS, UsageStats


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class Gone(ValueError):
    """An expired/deleted create request must never create its record again."""


class SharedRecords(ContributionStore):
    def __init__(self, directory):
        super().__init__(directory)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS shared_creates ('
                       'id TEXT PRIMARY KEY, deletion_hash TEXT NOT NULL, digest TEXT NOT NULL, expires REAL NOT NULL)')

    def prune(self, now=None):
        super().prune(now)
        with self.connect() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='shared_creates'").fetchone():
                db.execute('DELETE FROM shared_creates WHERE expires<=?', (time.time() if now is None else now,))

    def create(self, identifier, token, created_at, record):
        if not isinstance(identifier, str) or not re.fullmatch(r'[0-9a-f]{32}', identifier):
            raise ValueError('Invalid create identifier')
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{40,100}', token):
            raise ValueError('Invalid deletion token')
        now = time.time()
        if type(created_at) not in (int, float) or not math.isfinite(created_at) or created_at > now + 60:
            raise ValueError('Invalid creation time')
        expires = min(now, created_at) + RETENTION_SECONDS
        if expires <= now:
            raise Gone('Create request expired')
        if (not isinstance(record, dict) or record.get('schema') != 'chefjeff-pilot-session-v2'
                or record.get('consent_version') != CONSENT_VERSION):
            raise ValueError('Invalid record')
        from research_record import validate_record
        validate_record(record)
        raw = encode(record)
        if len(raw.encode()) > 13_000_000:
            raise ValueError('Record too large')
        digest = hashlib.sha256(raw.encode()).hexdigest()
        deletion_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM records WHERE expires <= ?', (now,))
            db.execute('DELETE FROM shared_creates WHERE expires <= ?', (now,))
            previous = db.execute('SELECT deletion_hash,digest,expires FROM shared_creates WHERE id=?', (identifier,)).fetchone()
            if previous:
                if not secrets.compare_digest(previous[0], deletion_hash) or previous[1] != digest:
                    raise ValueError('Create request conflicts')
                if not db.execute('SELECT 1 FROM records WHERE id=? AND expires>?', (identifier, now)).fetchone():
                    raise Gone('Record withdrawn')
                expires = previous[2]
            else:
                count, size = db.execute('SELECT count(*),coalesce(sum(length(CAST(record AS BLOB))),0) FROM records').fetchone()
                if count >= self.limit or size + len(raw.encode()) > self.byte_limit:
                    raise ValueError('Contribution capacity reached')
                # Bound deduplication metadata as well as live records.
                if db.execute('SELECT count(*) FROM shared_creates').fetchone()[0] >= 10000:
                    raise ValueError('Create capacity reached')
                db.execute('INSERT INTO records VALUES (?,?,?,?)', (identifier, deletion_hash, expires, raw))
                db.execute('INSERT INTO shared_creates VALUES (?,?,?,?)', (identifier, deletion_hash, digest, expires))
        return {'id': identifier, 'deletion_token': token,
                'expires_at': datetime.fromtimestamp(expires, timezone.utc).isoformat(),
                'consent_version': CONSENT_VERSION}


def usage_payload(snapshot):
    """Only bounded aggregates cross the connection; never visitor/session data."""
    return {'counts': {key: snapshot[key] for key in COUNTERS},
            'levels': snapshot['levels'],
            'durations': [{key: row[key] for key in ('level', 'outcome', 'bucket', 'rounds', 'game_seconds', 'active_seconds')}
                          for row in snapshot['durations']]}


def validate_usage(value):
    if not isinstance(value, dict) or set(value) != {'counts', 'levels', 'durations'}:
        raise ValueError('Invalid aggregate')
    counts, levels, durations = value['counts'], value['levels'], value['durations']
    def integer(n):
        return type(n) is int and 0 <= n <= 10**15
    def number(n):
        return type(n) in (int, float) and math.isfinite(n) and 0 <= n <= 10**15
    if not isinstance(counts, dict) or set(counts) != set(COUNTERS) or not all(integer(n) for n in counts.values()):
        raise ValueError('Invalid counters')
    if not isinstance(levels, list) or len(levels) != 3:
        raise ValueError('Invalid levels')
    seen = set()
    for row in levels:
        if (not isinstance(row, dict) or set(row) != {'level', 'started_rounds', 'completed_rounds'}
                or type(row['level']) is not int or row['level'] not in (1, 2, 3) or row['level'] in seen
                or not all(integer(row[k]) for k in ('started_rounds', 'completed_rounds'))):
            raise ValueError('Invalid level aggregate')
        seen.add(row['level'])
    if not isinstance(durations, list) or len(durations) > 126:
        raise ValueError('Invalid durations')
    seen = set()
    for row in durations:
        if not isinstance(row, dict) or set(row) != {'level', 'outcome', 'bucket', 'rounds', 'game_seconds', 'active_seconds'}:
            raise ValueError('Invalid duration aggregate')
        key = (row['level'], row['outcome'], row['bucket'])
        if (type(row['level']) is not int or row['level'] not in (1, 2, 3)
                or row['outcome'] not in OUTCOMES or row['bucket'] not in {b for _, b in DURATION_BUCKETS}
                or key in seen or not integer(row['rounds']) or row['rounds'] == 0
                or not number(row['game_seconds']) or not number(row['active_seconds'])):
            raise ValueError('Invalid duration aggregate')
        seen.add(key)
    return value


class SharedUsage:
    """Checkpoint and added totals commit in the same SQLite transaction."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.stats = UsageStats(directory)
        if self.stats.path is None:
            raise OSError('Shared usage storage unavailable')
        self.path = self.stats.path
        self.lock = threading.Lock()
        self.live = {}
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS shared_streams ('
                       'site TEXT NOT NULL, stream TEXT NOT NULL, aggregate TEXT NOT NULL, PRIMARY KEY(site,stream))')

    def apply(self, site, stream, aggregate, running=0):
        if not isinstance(stream, str) or not re.fullmatch(r'[0-9a-f]{32}', stream):
            raise ValueError('Invalid stream')
        if type(running) is not int or not 0 <= running <= 16:
            raise ValueError('Invalid running count')
        validate_usage(aggregate)
        def difference(new, old):
            delta = new - old
            if delta < -0.000001:
                raise ValueError('Stale aggregate')
            return max(0, delta)
        with self.lock:
            with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT aggregate FROM shared_streams WHERE site=? AND stream=?', (site, stream)).fetchone()
                previous = json.loads(row[0]) if row else {'counts': dict.fromkeys(COUNTERS, 0), 'levels': [], 'durations': []}
                if not row and db.execute('SELECT count(*) FROM shared_streams').fetchone()[0] >= 64:
                    raise ValueError('Usage stream capacity reached')
                deltas = [difference(aggregate['counts'][k], previous['counts'][k]) for k in COUNTERS]
                db.execute('UPDATE totals SET ' + ','.join(k+'='+k+'+?' for k in COUNTERS)+' WHERE id=1', deltas)
                old_levels = {r['level']: r for r in previous['levels']}
                for r in aggregate['levels']:
                    old = old_levels.get(r['level'], {})
                    started = difference(r['started_rounds'], old.get('started_rounds', 0))
                    completed = difference(r['completed_rounds'], old.get('completed_rounds', 0))
                    db.execute('INSERT INTO levels VALUES (?,?,?) ON CONFLICT(level) DO UPDATE SET '
                               'started_rounds=started_rounds+excluded.started_rounds,completed_rounds=completed_rounds+excluded.completed_rounds',
                               (r['level'], started, completed))
                old_durations = {(r['level'], r['outcome'], r['bucket']): r for r in previous['durations']}
                new_keys = {(r['level'], r['outcome'], r['bucket']) for r in aggregate['durations']}
                if old_durations.keys() - new_keys:
                    raise ValueError('Stale aggregate')
                for r in aggregate['durations']:
                    key = (r['level'], r['outcome'], r['bucket'])
                    old = old_durations.get(key, {})
                    delta = [difference(r[k], old.get(k, 0)) for k in ('rounds', 'game_seconds', 'active_seconds')]
                    db.execute('INSERT INTO durations VALUES (?,?,?,?,?,?) ON CONFLICT(level,outcome,bucket) DO UPDATE SET '
                               'rounds=rounds+excluded.rounds,game_seconds=game_seconds+excluded.game_seconds,active_seconds=active_seconds+excluded.active_seconds',
                               (*key, *delta))
                db.execute('INSERT INTO shared_streams VALUES (?,?,?) ON CONFLICT(site,stream) DO UPDATE SET aggregate=excluded.aggregate',
                           (site, stream, encode(aggregate)))
            # This process is the only usage writer; refresh its public projection after commit.
            refreshed = UsageStats(self.directory)
            if refreshed.path is None:
                raise OSError('Shared usage storage unavailable')
            self.stats = refreshed
            self.live[site] = (time.monotonic(), running)
            return self._snapshot()

    def _snapshot(self):
        return {**self.stats.snapshot(), 'shared': True,
                'running_sessions': sum(n for at, n in self.live.values() if time.monotonic() - at < 15)}

    def snapshot(self):
        with self.lock:
            return self._snapshot()
