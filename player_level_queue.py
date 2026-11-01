"""Calibrate players' levels one at a time, away from the kitchens being played.

Calibration plays dozens of scripted rounds. In the server process it would hold the interpreter
lock and slow every live kitchen, so each job runs in its own spawned process at a lower priority,
one job after another. An owner (a hosted session, or the local page) may have one job waiting or
running; at most ``max_waiting`` jobs wait; a job running past ``timeout`` seconds is stopped. A
design's report is kept by its content id, so the same level submitted again is answered at once.
"""
from collections import OrderedDict
import multiprocessing
import os
import secrets
import threading

import config_contract as cc
import level_calibration

KEEP_JOBS = 256


def _calibrate(pipe, bundle, seeds, workers, nice, calibrate):
    """Child process: one calibration, its report sent back through ``pipe``."""
    try:
        if nice:
            os.nice(nice)
        pipe.send(('done', calibrate(bundle, seeds=seeds, workers=workers)))
    except Exception as error:  # the job fails alone; the server keeps running
        pipe.send(('failed', type(error).__name__))
    finally:
        pipe.close()


def summary(report):
    """What the page needs from a report, without the per-run detail."""
    out = {key: report[key] for key in ('playable', 'target', 'pacing', 'pair_median', 'solo_median',
                                        'solo_reaches_target', 'seeds') if key in report}
    out['diagnostics'] = [{key: d[key] for key in ('code', 'severity', 'field_path', 'message') if key in d}
                          for d in report.get('diagnostics', [])]
    return out


class CalibrationQueue:
    def __init__(self, workers=1, max_waiting=8, timeout=300, keep=64, nice=10,
                 seeds=level_calibration.SEEDS, calibrate=level_calibration.calibrate):
        self.workers, self.max_waiting, self.timeout, self.keep, self.nice = workers, max_waiting, timeout, keep, nice
        self.seeds, self.calibrate = tuple(seeds), calibrate
        self.lock = threading.Condition()
        self.jobs = OrderedDict()     # job id -> job, the most recent KEEP_JOBS
        self.waiting = []             # queued job ids, first in first out
        self.reports = OrderedDict()  # content id -> (normalized level, report), the most recent ``keep``
        self.process = None
        self.closed = False
        self.thread = threading.Thread(target=self._work, daemon=True)
        self.thread.start()

    def submit(self, owner, design):
        """Check a design and queue its calibration: (status, reply)."""
        level, problems = level_calibration.normalize(design)
        if level is None:
            return 400, {'state': 'refused', **summary({'diagnostics': problems})}
        draft, diagnostics = cc.resolve_config(level_calibration.paced(level))
        if draft is None:
            return 400, {'state': 'refused', **summary({'diagnostics': cc.errors(diagnostics)})}
        content_id = level['level']['id']
        with self.lock:
            if self.closed:
                return 503, {'error': '校准服务已停止。'}
            job = {'id': secrets.token_urlsafe(12), 'owner': owner, 'content_id': content_id, 'state': 'queued'}
            if content_id in self.reports:
                self.reports.move_to_end(content_id)
                job['state'] = 'done'
                self._remember(job)
                return 200, self._view(job)
            if any(j['owner'] == owner and j['state'] in ('queued', 'running') for j in self.jobs.values()):
                return 409, {'error': '上一张关卡还在计算，请等它算完。'}
            if len(self.waiting) >= self.max_waiting:
                return 503, {'error': '校准排队已满，请稍后再试。'}
            job['level'] = level
            self._remember(job)
            self.waiting.append(job['id'])
            self.lock.notify_all()
            return 202, self._view(job)

    def status(self, owner, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job['owner'] != owner:
                return 404, {'error': '没有这项校准。'}
            return 200, self._view(job)

    def result(self, owner, job_id):
        """(normalized level, report) of a finished job of this owner, else None."""
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job['owner'] != owner or job['state'] != 'done' or job['content_id'] not in self.reports:
                return None
            return self.reports[job['content_id']]

    def close(self):
        with self.lock:
            self.closed = True
            self.lock.notify_all()
            process = self.process
        if process is not None and process.is_alive():
            process.terminate()

    def _remember(self, job):
        self.jobs[job['id']] = job
        for job_id in list(self.jobs):
            if len(self.jobs) <= KEEP_JOBS:
                break
            if self.jobs[job_id]['state'] in ('done', 'failed'):
                del self.jobs[job_id]

    def _view(self, job):
        view = {'job': job['id'], 'state': job['state'], 'content_id': job['content_id']}
        if job['state'] == 'queued':
            view['position'] = self.waiting.index(job['id']) + 1 + any(j['state'] == 'running' for j in self.jobs.values())
        elif job['state'] == 'done':
            view['report'] = summary(self.reports[job['content_id']][1]) if job['content_id'] in self.reports else None
        elif job['state'] == 'failed':
            view['error'] = job.get('error')
        return view

    def _work(self):
        while True:
            with self.lock:
                while not self.waiting and not self.closed:
                    self.lock.wait()
                if self.closed:
                    return
                job = self.jobs.get(self.waiting.pop(0))
                if job is None:
                    continue
                job['state'] = 'running'
                level = job.pop('level')
            outcome, value = self._run(level)
            with self.lock:
                if outcome == 'done':
                    self.reports[job['content_id']] = (level, value)
                    while len(self.reports) > self.keep:
                        self.reports.popitem(last=False)
                    job['state'] = 'done'
                else:
                    job.update(state='failed', error=value)
                self.lock.notify_all()

    def _run(self, level):
        context = multiprocessing.get_context('spawn')
        receive, send = context.Pipe(duplex=False)
        # Not a daemon: a calibration on several processes starts its own pool. close() stops it.
        process = context.Process(target=_calibrate, args=(send, level, self.seeds, self.workers, self.nice, self.calibrate))
        with self.lock:
            if self.closed:
                return 'failed', '校准服务已停止。'
            self.process = process
        process.start()
        send.close()
        try:
            if not receive.poll(self.timeout):
                return 'failed', '校准超时，请简化关卡后再试。'
            outcome, value = receive.recv()
            return (outcome, value) if outcome == 'done' else ('failed', '校准出错，请稍后再试。')
        except (EOFError, OSError):
            return 'failed', '校准出错，请稍后再试。'
        finally:
            if process.is_alive():
                process.terminate()
            process.join(5)
            receive.close()
            with self.lock:
                self.process = None
