"""Private aggregate call budgets, never kitchen payloads, credentials or player records."""
import fcntl
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import threading
import time

PROVIDERS = ('zhipu', 'startlux')


class BudgetError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class CallBudget:
    def __init__(self, directory=None, clock=time.time, minute=30, hour=300, day=1000):
        self.clock, self.minute, self.hour, self.day = clock, minute, hour, day
        if any(type(n) is not int or n < 1 for n in (minute, hour, day)) or not minute <= hour <= day <= 10000:
            raise ValueError('Invalid aggregate budget')
        self.lock = threading.RLock()
        self.directory = Path(directory) if directory is not None else None
        self.descriptor = None
        self.value = {'version': 1, 'attempts': [], 'inflight': dict.fromkeys(PROVIDERS, False),
                      'blocked': dict.fromkeys(PROVIDERS, False), 'cooldown': dict.fromkeys(PROVIDERS, 0.0)}
        if self.directory is not None:
            try:
                self._open()
                self._load()
                # A crash with an outstanding HTTP call leaves its upstream outcome uncertain.
                for provider in PROVIDERS:
                    if self.value['inflight'][provider]:
                        self.value['blocked'][provider] = True
                        self.value['inflight'][provider] = False
                self._save()
            except BaseException:
                self.close()
                raise

    def _open(self):
        p = self.directory
        if p.is_symlink():
            raise ValueError('Invalid budget directory')
        p.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = p.stat()
        if not stat.S_ISDIR(info.st_mode) or (os.geteuid() != 0 and info.st_uid != os.getuid()) or info.st_mode & 0o077:
            raise ValueError('Budget directory must be private')
        self.descriptor = os.open(p/'budget.lock', os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        if os.geteuid() == 0:
            os.fchown(self.descriptor, info.st_uid, info.st_gid)
        file = os.fstat(self.descriptor)
        if not stat.S_ISREG(file.st_mode) or file.st_nlink != 1 or file.st_mode & 0o077:
            raise ValueError('Invalid budget lock')
        try:
            fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Only one gateway may own this budget directory') from None

    def _load(self):
        path = self.directory/'budget.json'
        if not path.exists() and not path.is_symlink():
            return
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077 or info.st_size > 1_000_000:
                raise ValueError('Invalid budget state')
            value = json.load(source)
        if (not isinstance(value, dict) or set(value) != set(self.value) or value['version'] != 1
                or not isinstance(value['attempts'], list) or len(value['attempts']) > 10000):
            raise ValueError('Invalid budget state')
        for field in ('inflight', 'blocked', 'cooldown'):
            if not isinstance(value[field], dict) or set(value[field]) != set(PROVIDERS):
                raise ValueError('Invalid budget state')
        for provider in PROVIDERS:
            if type(value['inflight'][provider]) is not bool or type(value['blocked'][provider]) is not bool:
                raise ValueError('Invalid budget state')
            n = value['cooldown'][provider]
            if type(n) not in (int, float) or not math.isfinite(n) or n < 0:
                raise ValueError('Invalid budget state')
        for row in value['attempts']:
            if (not isinstance(row, list) or len(row) != 2 or row[1] not in PROVIDERS
                    or type(row[0]) not in (int, float) or not math.isfinite(row[0]) or row[0] < 0):
                raise ValueError('Invalid budget state')
        self.value = value

    def _save(self):
        if self.directory is None:
            return
        fd, name = tempfile.mkstemp(prefix='.budget-', dir=self.directory)
        temp = Path(name)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                if os.geteuid() == 0:
                    owner = self.directory.stat()
                    os.fchown(output.fileno(), owner.st_uid, owner.st_gid)
                os.fchmod(output.fileno(), 0o600)
                json.dump(self.value, output, separators=(',', ':'), allow_nan=False)
                output.flush(); os.fsync(output.fileno())
            temp.replace(self.directory/'budget.json')
            parent = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        finally:
            temp.unlink(missing_ok=True)

    def available(self, provider):
        with self.lock:
            now = self.clock()
            if self.value['blocked'][provider]:
                return 'upstream_blocked'
            if self.value['inflight'][provider]:
                return 'request_busy'
            if now < self.value['cooldown'][provider]:
                return 'upstream_cooldown'
            rows = self.value['attempts']
            if (sum(p == provider and t > now-60 for t, p in rows) >= self.minute
                    or sum(t > now-3600 for t, _ in rows) >= self.hour
                    or sum(t > now-86400 for t, _ in rows) >= self.day):
                return 'call_budget'
            return None

    def begin(self, provider):
        with self.lock:
            error = self.available(provider)
            if error:
                raise BudgetError(error)
            now = self.clock()
            self.value['attempts'] = [[t, p] for t, p in self.value['attempts'] if t > now-86400]
            self.value['attempts'].append([now, provider])
            self.value['inflight'][provider] = True
            try:
                self._save()  # The attempt marker is durable BEFORE any upstream request.
            except Exception:
                self.value['blocked'][provider] = True
                raise BudgetError('budget_unavailable') from None

    def finish(self, provider, category=None):
        with self.lock:
            self.value['inflight'][provider] = False
            if category in ('transport_uncertain', 'authentication', 'model_mismatch', 'interrupted'):
                self.value['blocked'][provider] = True
            if category is not None:
                self.value['cooldown'][provider] = self.clock()+60
            try:
                self._save()
            except Exception:
                self.value['blocked'][provider] = True
                raise BudgetError('budget_unavailable') from None

    def acknowledge_idle(self, provider):
        """Operator-only recovery, with the gateway stopped and upstream idle confirmed."""
        with self.lock:
            self.value['inflight'][provider] = False
            self.value['blocked'][provider] = False
            self.value['cooldown'][provider] = self.clock()+60
            self._save()

    def close(self):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
