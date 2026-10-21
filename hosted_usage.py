"""Aggregate hosted counters only: no visitor, session, round or request records."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
import math


COUNTERS = ('page_views', 'started_sessions', 'started_rounds', 'completed_rounds', 'manual_ends',
            'page_full_rejections', 'kitchen_full_rejections', 'network_full_rejections',
            'estimated_visitor_browsers', 'estimated_player_browsers')
OUTCOMES = ('completed', 'manual_end', 'page_close', 'disconnected', 'restart', 'shutdown')
# Effective running seconds (game progress / the round's fixed speed), not page-open time.
DURATION_BUCKETS = ((10, '0–10s'), (30, '10–30s'), (60, '30–60s'), (120, '1–2min'),
                    (180, '2–3min'), (300, '3–5min'), (math.inf, '5min+'))


class UsageStats:
    def __init__(self, directory=None):
        self.lock = threading.Lock()
        self.counts = dict.fromkeys(COUNTERS, 0)
        self.levels = {level: {'started_rounds': 0, 'completed_rounds': 0} for level in (1, 2, 3)}
        self.durations = {}
        self.tracking_since = datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.path = None
        self.storage_errors = 0
        if directory is not None:
            try:
                directory = Path(directory)
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                path = directory / 'usage.sqlite3'
                with closing(sqlite3.connect(path, timeout=.25)) as db, db:
                    db.execute('CREATE TABLE IF NOT EXISTS totals (id INTEGER PRIMARY KEY CHECK (id=1), '
                               'tracking_since TEXT NOT NULL, ' + ', '.join(f'{key} INTEGER NOT NULL' for key in COUNTERS) + ')')
                    db.execute('INSERT OR IGNORE INTO totals VALUES (1, ?, ' + ', '.join('0' for _ in COUNTERS) + ')',
                               (self.tracking_since,))
                    db.execute('CREATE TABLE IF NOT EXISTS levels (level INTEGER PRIMARY KEY, '
                               'started_rounds INTEGER NOT NULL, completed_rounds INTEGER NOT NULL)')
                    db.execute('CREATE TABLE IF NOT EXISTS durations (level INTEGER NOT NULL, outcome TEXT NOT NULL, '
                               'bucket TEXT NOT NULL, rounds INTEGER NOT NULL, game_seconds REAL NOT NULL, '
                               'active_seconds REAL NOT NULL, PRIMARY KEY (level, outcome, bucket))')
                    row = db.execute('SELECT tracking_since, ' + ', '.join(COUNTERS) + ' FROM totals WHERE id=1').fetchone()
                    levels = db.execute('SELECT level, started_rounds, completed_rounds FROM levels').fetchall()
                    durations = db.execute('SELECT level, outcome, bucket, rounds, game_seconds, active_seconds FROM durations').fetchall()
                path.chmod(0o600)
                self.tracking_since = row[0]
                self.counts = dict(zip(COUNTERS, row[1:]))
                for level, started, completed in levels:
                    self.levels[level] = {'started_rounds': started, 'completed_rounds': completed}
                self.durations = {(level, outcome, bucket): {'rounds': rounds, 'game_seconds': game, 'active_seconds': active}
                                  for level, outcome, bucket, rounds, game, active in durations}
                self.path = path
            except (OSError, sqlite3.Error):
                # Analytics must never stop the kitchen. Surface failure to the operator,
                # without including exception text, paths or any request material.
                self.storage_errors += 1

    def increment(self, counter):
        if counter not in COUNTERS:
            raise ValueError('Unknown usage counter')
        self._record({counter: 1})

    def start_round(self, level, first=False):
        self._check_level(level)
        self._record({'started_rounds': 1, **({'started_sessions': 1} if first else {})}, level=level)

    def record_browsers(self, first_visit, first_play):
        updates = {key: 1 for key, first in (('estimated_visitor_browsers', first_visit),
                                           ('estimated_player_browsers', first_play)) if first}
        if updates: self._record(updates)

    def end_round(self, level, outcome, game_seconds, speed):
        self._check_level(level)
        if outcome not in OUTCOMES or not math.isfinite(game_seconds) or game_seconds < 0 or speed not in (.5, .75, 1):
            raise ValueError('Invalid round aggregate')
        game = round(game_seconds, 3)
        active = round(game_seconds / speed, 3)
        bucket = next(label for upper, label in DURATION_BUCKETS if active < upper)
        updates = {'completed_rounds': 1} if outcome == 'completed' else {'manual_ends': 1} if outcome == 'manual_end' else {}
        self._record(updates, level=level, duration=(outcome, bucket, game, active))

    @staticmethod
    def _check_level(level):
        if type(level) is not int or level not in (1, 2, 3):
            raise ValueError('Unknown level')

    def _record(self, updates, level=None, duration=None):
        with self.lock:
            for key, value in updates.items():
                self.counts[key] += value
            if level is not None:
                self.levels[level]['started_rounds'] += updates.get('started_rounds', 0)
                self.levels[level]['completed_rounds'] += updates.get('completed_rounds', 0)
            if duration is not None:
                outcome, bucket, game, active = duration
                aggregate = self.durations.setdefault((level, outcome, bucket),
                                                     {'rounds': 0, 'game_seconds': 0., 'active_seconds': 0.})
                aggregate['rounds'] += 1
                aggregate['game_seconds'] += game
                aggregate['active_seconds'] += active
            if self.path is not None:
                try:
                    with closing(sqlite3.connect(self.path, timeout=.25)) as db, db:
                        if updates:
                            db.execute('UPDATE totals SET ' + ', '.join(f'{key}={key}+?' for key in updates) + ' WHERE id=1',
                                       tuple(updates.values()))
                        if level is not None:
                            db.execute('INSERT INTO levels VALUES (?, ?, ?) ON CONFLICT(level) DO UPDATE SET '
                                       'started_rounds=started_rounds+excluded.started_rounds, '
                                       'completed_rounds=completed_rounds+excluded.completed_rounds',
                                       (level, updates.get('started_rounds', 0), updates.get('completed_rounds', 0)))
                        if duration is not None:
                            db.execute('INSERT INTO durations VALUES (?, ?, ?, 1, ?, ?) '
                                       'ON CONFLICT(level, outcome, bucket) DO UPDATE SET rounds=rounds+1, '
                                       'game_seconds=game_seconds+excluded.game_seconds, '
                                       'active_seconds=active_seconds+excluded.active_seconds',
                                       (level, outcome, bucket, game, active))
                except (OSError, sqlite3.Error):
                    self.storage_errors += 1
                    self.path = None  # Continue in memory; do not stall each later event on disk I/O.

    def snapshot(self):
        with self.lock:
            durations = [{'level': level, 'outcome': outcome, 'bucket': bucket, 'rounds': row['rounds'],
                          'game_seconds': round(row['game_seconds'], 3), 'active_seconds': round(row['active_seconds'], 3),
                          'average_active_seconds': round(row['active_seconds'] / row['rounds'], 1)}
                         for level in (1, 2, 3) for outcome in OUTCOMES for _, bucket in DURATION_BUCKETS
                         if (row := self.durations.get((level, outcome, bucket)))]
            return {'tracking_since': self.tracking_since, **self.counts,
                    'full_rejections': self.counts['page_full_rejections'] + self.counts['kitchen_full_rejections'],
                    'levels': [{'level': level, **counts} for level, counts in self.levels.items()],
                    'round_outcomes': {outcome: sum(row['rounds'] for row in durations if row['outcome'] == outcome)
                                       for outcome in OUTCOMES}, 'durations': durations,
                    'persistent': self.path is not None, 'storage_errors': self.storage_errors}
