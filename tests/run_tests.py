#!/usr/bin/env python3
"""Run the Python test modules in tests/ in parallel worker processes.

`python3 -m unittest discover -s tests` stays the reference command; CI runs it. This runner finds
the same modules (tests/test*.py) and runs each module whole inside one of several worker
processes. Like discover, each worker first imports every test module in sorted order, with the
same sys.path (tests/ first, then the repository root) and the repository root as working
directory, so what a module changes at import time is in place for the others as in the reference
run. The workers are started with the spawn method and are not daemonic, so a test may start its
own pool of processes. Each worker gets its own TMPDIR folder under the current one; the folders
are removed at the end. What the tests print is kept per worker and shown only for modules with
problems.

  python3 tests/run_tests.py                 every module, one worker per physical core
  python3 tests/run_tests.py -j 4            four workers ('auto', the default, is one per core)
  python3 tests/run_tests.py --fast          only the quick modules in tests/fast_modules.txt
  python3 tests/run_tests.py test_kitchen test_jev -k throw

The exit status is 0 when every test passed, 1 on any failure, error, unexpected success, module
that failed to import or worker that exited in the middle of a module, and 5 when no test ran.
"""

import argparse
import faulthandler
import fnmatch
import gc
import importlib
import io
import multiprocessing
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
from multiprocessing.connection import wait

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
FAST_LIST = os.path.join(TESTS, 'fast_modules.txt')
PATTERN = 'test*.py'  # the default pattern of unittest discover
VALID_NAME = re.compile(r'[_a-z]\w*\.py$', re.IGNORECASE)  # unittest.loader.VALID_MODULE_NAME
FAST_LIMIT_S = 1.5
FAST_FACTOR_FLOOR_S = 0.1  # quicker modules are mostly fixed start-up time, too short to scale by
FAST_OUT_OF_LINE = 2  # a fast module slowed down this many times more than its neighbours is named
OUTPUT_LINES = 60
OUTPUT_BYTES = 64 * 1024
RULE = '=' * 70
THIN_RULE = '-' * 70

# The slowest modules, longest first (serial and four-worker timings of 2026-11-21). They are
# queued first so that no long module starts near the end of a run. Modules from the fast list
# go last. Update the list when the timings change a lot; -v prints the time of every module.
SLOWEST = (
    'test_ask_ahead',
    'test_payload_fingerprint',
    'test_admin_v2',
    'test_model_rounds',
    'test_research_replay',
    'test_fingerprint',
    'test_engine_english',
    'test_walk_and_pickup',
    'test_release',
    'test_admin_v7',
    'test_admin_export_token',
    'test_visual_geometry',
)


def physical_cores():
    """Physical CPU cores available to this process; the logical count where that is unknown."""
    logical = os.cpu_count() or 1
    if hasattr(os, 'sched_getaffinity'):
        logical = len(os.sched_getaffinity(0)) or logical
    count = None
    try:
        if sys.platform == 'darwin':
            out = subprocess.run(['sysctl', '-n', 'hw.physicalcpu'], capture_output=True,
                                 text=True, timeout=5, check=True).stdout
            count = int(out.strip())
        elif sys.platform.startswith('linux'):
            cores, physical, core = set(), None, None
            with open('/proc/cpuinfo', encoding='utf-8', errors='replace') as handle:
                for line in list(handle) + ['']:
                    key, _, value = line.partition(':')
                    key = key.strip()
                    if key == 'physical id':
                        physical = value.strip()
                    elif key == 'core id':
                        core = value.strip()
                    elif not line.strip():
                        if core is not None:
                            cores.add((physical, core))
                        physical = core = None
            count = len(cores) or None
    except (OSError, ValueError, subprocess.SubprocessError):
        count = None
    return max(1, min(count or logical, logical))


def discover_modules():
    """The module names `python3 -m unittest discover -s tests` loads, in its order."""
    names = []
    for entry in sorted(os.listdir(TESTS)):
        path = os.path.join(TESTS, entry)
        if os.path.isdir(path):
            if os.path.isfile(os.path.join(path, '__init__.py')):
                raise SystemExit(f'tests/{entry} is a package. unittest discover searches packages; '
                                 'this runner only runs the modules directly in tests/.')
            continue
        if os.path.isfile(path) and VALID_NAME.match(entry) and fnmatch.fnmatch(entry, PATTERN):
            names.append(entry[:-3])
    return names


def read_fast_list():
    """{module: its reference time in seconds, or None} from tests/fast_modules.txt, in file order."""
    modules = {}
    with open(FAST_LIST, encoding='utf-8') as handle:
        for number, line in enumerate(handle, 1):
            fields = line.split('#', 1)[0].split()
            if not fields:
                continue
            try:
                modules[fields[0]] = float(fields[1]) if len(fields) > 1 else None
            except ValueError:
                raise SystemExit(f'tests/fast_modules.txt line {number}: expected a module name '
                                 'and its time in seconds') from None
    return modules


def queue_order(names):
    """The slowest modules first, then the modules on neither list, then the fast list."""
    fast = set(read_fast_list()) if os.path.isfile(FAST_LIST) else set()
    slow = [name for name in SLOWEST if name in names]
    rest = [name for name in names if name not in SLOWEST]
    return slow + [name for name in rest if name not in fast] + [name for name in rest if name in fast]


# Worker process ----------------------------------------------------------------------------------

def _interrupt(signum, frame):
    raise KeyboardInterrupt


def _settle(tmpdir):
    """Working directory and temp folder each module starts with."""
    os.makedirs(tmpdir, exist_ok=True)
    os.chdir(ROOT)
    for key in ('TMPDIR', 'TEMP', 'TMP') if os.name == 'nt' else ('TMPDIR',):
        os.environ[key] = tmpdir
    tempfile.tempdir = None


def _flush():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (AttributeError, OSError, ValueError):
            pass


def _import_all(names):
    """Imports the test modules in discover's order, as discover does before it runs any test,
    so that what one module changes at import time (sys.path, for one) is in place for all of
    them as in the reference run. Returns {module: (kind, text)} for those that did not import."""
    problems = {}
    for name in names:
        try:
            importlib.import_module(name)
        except unittest.SkipTest as skip:
            problems[name] = ('skip', str(skip))
        except KeyboardInterrupt:
            raise
        except BaseException:
            problems[name] = ('error', traceback.format_exc())
    return problems


def _run_module(name, patterns, not_imported):
    record = {'module': name, 'tests': 0, 'failures': [], 'errors': [], 'skipped': 0,
              'expected_failures': 0, 'unexpected_successes': [], 'import_failed': False}
    loader = unittest.TestLoader()
    if patterns:
        loader.testNamePatterns = patterns
    start = time.perf_counter()
    module = None
    if name in not_imported:
        kind, text = not_imported[name]
        if kind == 'skip':
            record.update(tests=1, skipped=1)  # discover counts a module that skips itself as one skip
        else:
            # discover reports a module that fails to import as one test with an error
            record.update(tests=1, import_failed=True)
            record['errors'].append((f'Failed to import test module: {name}', text))
    else:
        module = sys.modules.get(name)
    if module is not None:
        suite = loader.loadTestsFromModule(module, pattern=PATTERN)
        runner = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0,
                                         warnings=None if sys.warnoptions else 'default')
        try:
            result = runner.run(suite)
        except KeyboardInterrupt:
            raise
        except BaseException:
            record['errors'].append((f'{name} (outside any test)', traceback.format_exc()))
        else:
            record.update(tests=result.testsRun, skipped=len(result.skipped),
                          failures=[(str(test), text) for test, text in result.failures],
                          errors=[(str(test), text) for test, text in result.errors],
                          expected_failures=len(result.expectedFailures),
                          unexpected_successes=[str(test) for test in result.unexpectedSuccesses])
        gc.collect()
    record['seconds'] = time.perf_counter() - start
    return record


def _worker(index, conn, tmpdir, log_path, patterns, every_module):
    """Imports every test module, then runs the modules the parent sends until it sends None."""
    signal.signal(signal.SIGTERM, _interrupt)  # stop the processes a test started, then exit
    sys.path[:] = [TESTS, ROOT] + [path for path in sys.path
                                   if os.path.abspath(path or os.curdir) not in (TESTS, ROOT)]
    log = open(log_path, 'ab', buffering=0)
    _flush()
    os.dup2(log.fileno(), 1)  # child processes the tests start write here too
    os.dup2(log.fileno(), 2)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)  # keeps the order and survives a crash
        except (AttributeError, ValueError):
            pass
    faulthandler.enable()
    code = 0
    try:
        _settle(tmpdir)
        not_imported = _import_all(every_module)
        _flush()
        conn.send(('ready', index))
        while True:
            try:
                name = conn.recv()
            except EOFError:
                break
            if name is None:
                break
            _settle(tmpdir)
            if name not in sys.modules and name not in not_imported:
                not_imported.update(_import_all([name]))  # a test took it out of sys.modules
            record = _run_module(name, patterns, not_imported)
            _flush()
            conn.send(('done', record))
    except KeyboardInterrupt:
        code = 130
    finally:
        for child in multiprocessing.active_children():
            child.terminate()
            child.join(2)
        _flush()
        conn.close()
    os._exit(code)  # threads a test left running must not keep the worker alive


# Parent process ----------------------------------------------------------------------------------

class _Worker:
    def __init__(self, ctx, index, run_dir, patterns, every_module):
        self.index = index
        self.log_path = os.path.join(run_dir, f'w{index}.log')
        open(self.log_path, 'wb').close()
        self.conn, child_end = ctx.Pipe()
        self.process = ctx.Process(
            target=_worker, name=f'run_tests-w{index}', daemon=False,
            args=(index, child_end, os.path.join(run_dir, f'w{index}'), self.log_path, patterns,
                  every_module))
        self.process.start()
        child_end.close()
        self.ready = False
        self.stopping = False
        self.module = None
        self.offset = 0
        self.started = 0.0


def _output_tail(path, offset):
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as handle:
            handle.seek(max(offset, size - OUTPUT_BYTES))
            text = handle.read().decode('utf-8', 'replace').rstrip()
    except OSError:
        return ''
    return '\n'.join(text.splitlines()[-OUTPUT_LINES:])


def _has_problems(record):
    return bool(record['failures'] or record['errors'] or record['unexpected_successes'])


def _dispatch(worker, pending):
    if not pending:
        worker.stopping = True
        try:
            worker.conn.send(None)
        except OSError:
            pass
        return
    name = pending.pop(0)
    worker.module, worker.started = name, time.perf_counter()
    try:
        worker.offset = os.path.getsize(worker.log_path)
        worker.conn.send(name)
    except OSError:  # the worker has gone; its exit is handled when its sentinel fires
        pending.insert(0, name)
        worker.module = None


def _exit_record(worker):
    code = worker.process.exitcode
    how = f'was stopped by signal {-code}' if code is not None and code < 0 else f'exited with code {code}'
    return {'module': worker.module, 'tests': 0, 'failures': [],
            'errors': [(f'worker {worker.index} {how} while running {worker.module}', '')],
            'skipped': 0, 'expected_failures': 0, 'unexpected_successes': [], 'import_failed': False,
            'worker_exited': True, 'seconds': time.perf_counter() - worker.started,
            'output': _output_tail(worker.log_path, worker.offset)}


def run_modules(names, every_module, jobs, run_dir, patterns, on_record):
    """Runs the modules in `names` (queue order) on `jobs` workers and returns one record each.
    Each worker first imports `every_module` in that order."""
    ctx = multiprocessing.get_context('spawn')
    pending = list(names)
    records, workers = [], []

    def done(record, worker):
        record.update(worker=worker.index, start=worker.started, end=time.perf_counter())
        worker.module = None
        records.append(record)
        on_record(record)

    started = 0
    for _ in range(jobs):
        started += 1
        workers.append(_Worker(ctx, started, run_dir, patterns, every_module))
    try:
        while workers:
            ready = set(wait([w.conn for w in workers] + [w.process.sentinel for w in workers]))
            for worker in list(workers):
                message = None
                if worker.conn in ready:
                    try:
                        message = worker.conn.recv()
                    except (EOFError, OSError):
                        message = None
                if message is not None:
                    if message[0] == 'done':
                        record = message[1]
                        record['output'] = (_output_tail(worker.log_path, worker.offset)
                                            if _has_problems(record) else '')
                        done(record, worker)
                    worker.ready = True
                    _dispatch(worker, pending)
                    continue
                if worker.process.sentinel not in ready and worker.conn not in ready:
                    continue
                worker.process.join(5)
                if worker.process.exitcode is None:
                    continue
                workers.remove(worker)
                worker.conn.close()
                if worker.module is not None:
                    done(_exit_record(worker), worker)
                elif not worker.ready:
                    output = _output_tail(worker.log_path, 0)
                    raise RuntimeError(f'worker {worker.index} exited while importing the test '
                                       f'modules (exit code {worker.process.exitcode})'
                                       + (f'. Its output:\n{output}' if output else ''))
                if not worker.stopping and pending:
                    started += 1
                    workers.append(_Worker(ctx, started, run_dir, patterns, every_module))
    finally:
        for worker in workers:
            if worker.process.is_alive():
                worker.process.terminate()
        for worker in workers:
            worker.process.join(5)
            if worker.process.is_alive():
                worker.process.kill()
                worker.process.join(5)
    return records


# Report ------------------------------------------------------------------------------------------

def _plural(count, word):
    return f'{count} {word}' + ('' if count == 1 else 's')


def fast_summary(records, check):
    """Prints the fast tier's total and every fast module that took over FAST_LIMIT_S.

    Parallel workers and other work on the machine make modules slower than their reference times
    in tests/fast_modules.txt, and by different amounts as the load changes during a run. So each
    module over the limit is compared with the median slowdown of the other modules that ran
    alongside it (counting only modules whose reference time is long enough to measure one). It is
    named as out of line when either
      - its time divided by that median is still over FAST_LIMIT_S, or
      - its own slowdown is more than FAST_OUT_OF_LINE times that median. Dividing alone would
        hide a module that now waits (a sleep, a timeout, a server that is slow to start) while
        CPU-bound modules around it slow down.
    The other modules over the limit are listed on one line with both slowdowns, so none is hidden.
    """
    reference = read_fast_list()
    module_time = sum(record['seconds'] for record in records)
    listed = sum(reference.get(record['module']) or 0 for record in records)
    print(THIN_RULE)
    print(f'Fast tier: {_plural(len(records), "module")}, {module_time:.1f} s of module time; '
          f'their reference times add up to {listed:.1f} s.')
    if not check:
        return
    timed = [record for record in records
             if (reference.get(record['module']) or 0) >= FAST_FACTOR_FLOOR_S]

    def slowdown(record):
        return record['seconds'] / reference[record['module']]

    overall = max(1.0, statistics.median(map(slowdown, timed))) if timed else 1.0

    def factor(record):
        alongside = [slowdown(other) for other in timed if other is not record
                     and other['start'] < record['end'] and other['end'] > record['start']]
        return max(1.0, statistics.median(alongside)) if len(alongside) >= 3 else overall

    if overall >= 1.05:
        print(f'Modules took {overall:.1f} times their reference time (median). A module over '
              f'{FAST_LIMIT_S} s is out of line when its time divided by that median for the '
              f'modules that ran alongside it is still over {FAST_LIMIT_S} s, or when it slowed '
              f'down more than {FAST_OUT_OF_LINE} times as much as they did.')
    slow, in_line = [], []
    for record in sorted(records, key=lambda record: -record['seconds']):
        if record['seconds'] <= FAST_LIMIT_S:
            continue
        local = factor(record)
        scaled = record['seconds'] / local
        listed_s = reference.get(record['module'])
        own = None  # unknown for a module listed without a time
        if listed_s is not None:
            # A reference under the floor is mostly start-up time; the floor keeps the ratio sane.
            own = record['seconds'] / max(listed_s, FAST_FACTOR_FLOOR_S)
        reasons = []
        if scaled > FAST_LIMIT_S and local >= 1.05:
            reasons.append(f'{scaled:.2f} s after dividing by {local:.1f}, the median slowdown of '
                           'the modules alongside it')
        if own is not None and own > FAST_OUT_OF_LINE * local:
            reasons.append(f'{own:.1f} times its reference {listed_s:.2f} s, against {local:.1f} '
                           'times for the modules alongside it')
        if scaled > FAST_LIMIT_S or reasons:
            slow.append((record, reasons))
        else:
            in_line.append(f"{record['module']} {record['seconds']:.2f} s ("
                           + (f'{own:.1f} times against {local:.1f}' if own is not None
                              else f'no reference time; {local:.1f} times alongside') + ')')
    if in_line:
        print(f'Also over {FAST_LIMIT_S} s in this run, but not out of line (its slowdown against '
              'the median of the modules that ran alongside it): ' + ', '.join(in_line))
    if not slow:
        print('No fast module out of line.' if in_line else f'No fast module over {FAST_LIMIT_S} s.')
        return
    print(f'Fast modules over {FAST_LIMIT_S} s and out of line:')
    for record, reasons in slow:
        print(f"  {record['module']} {record['seconds']:.2f} s in this run"
              + ''.join(f'; {reason}' for reason in reasons))
    print(f'Take out of tests/fast_modules.txt any that stays over {FAST_LIMIT_S} s alone: '
          'python3 tests/run_tests.py -j 1 -v ' + ' '.join(record['module'] for record, _ in slow))


def report(records, order, wall, jobs, fast):
    """Prints problems and totals; returns the exit status. `fast` is '', 'list' or 'check'."""
    by_name = {record['module']: record for record in records}
    problems = [by_name[name] for name in sorted(by_name) if _has_problems(by_name[name])]
    for record in problems:
        module = record['module']
        for kind, entries in (('ERROR', record['errors']), ('FAIL', record['failures'])):
            for test, text in entries:
                print(RULE)
                print(f'{kind} [{module}]: {test}')
                if text:
                    print(THIN_RULE)
                    print(text.rstrip())
        for test in record['unexpected_successes']:
            print(RULE)
            print(f'UNEXPECTED SUCCESS [{module}]: {test}')
        if record.get('output'):
            print(THIN_RULE)
            print(f'Output of {module} (last {OUTPUT_LINES} lines at most):')
            print(record['output'])

    tests = sum(record['tests'] for record in records)
    failures = sum(len(record['failures']) for record in records)
    errors = sum(len(record['errors']) for record in records)
    skipped = sum(record['skipped'] for record in records)
    expected = sum(record['expected_failures'] for record in records)
    unexpected = sum(len(record['unexpected_successes']) for record in records)
    module_time = sum(record['seconds'] for record in records)

    if fast:
        fast_summary(records, check=fast == 'check')
    elif len(records) > 10:
        slowest = sorted(records, key=lambda record: -record['seconds'])[:5]
        print(THIN_RULE)
        print('Slowest modules: ' + ', '.join(f"{record['module']} {record['seconds']:.1f} s"
                                              for record in slowest))

    print(THIN_RULE)
    print(f'Ran {_plural(tests, "test")} from {_plural(len(records), "module")} in {wall:.1f} s '
          f'with {_plural(jobs, "worker")} ({module_time:.1f} s of module time)')
    print()
    details = [f'{label}={count}' for label, count in (
        ('failures', failures), ('errors', errors), ('skipped', skipped),
        ('expected failures', expected), ('unexpected successes', unexpected)) if count]
    status = 0
    if failures or errors or unexpected:
        print(f"FAILED ({', '.join(details)})")
        summary = []
        for record in problems:
            if record['import_failed']:
                summary.append(f"{record['module']} (failed to import)")
            elif record.get('worker_exited'):
                summary.append(f"{record['module']} (worker exited)")
            else:
                parts = [_plural(len(record['failures']), 'failure') if record['failures'] else '',
                         _plural(len(record['errors']), 'error') if record['errors'] else '',
                         _plural(len(record['unexpected_successes']), 'unexpected success')
                         if record['unexpected_successes'] else '']
                summary.append(f"{record['module']} ({', '.join(part for part in parts if part)})")
        print('Modules with problems: ' + ', '.join(summary))
        print('Run them again: python3 tests/run_tests.py '
              + ' '.join(record['module'] for record in problems))
        status = 1
    elif tests == 0:
        print('NO TESTS RAN')
        status = 5
    else:
        print('OK' + (f" ({', '.join(details)})" if details else ''))
    missing = [name for name in order if name not in by_name]
    if missing:
        print('Not run: ' + ', '.join(missing))
        status = 1
    return status


# Command line ------------------------------------------------------------------------------------

def _jobs(value):
    if value == 'auto':
        return physical_cores()
    try:
        count = int(value)
    except ValueError:
        count = 0
    if count < 1:
        raise argparse.ArgumentTypeError("expected a positive whole number or 'auto'")
    return count


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog='python3 tests/run_tests.py',
        description='Run the test modules in tests/ in parallel worker processes. '
                    'python3 -m unittest discover -s tests is the reference command.')
    parser.add_argument('modules', nargs='*', metavar='MODULE',
                        help='test modules to run, such as test_kitchen (default: all)')
    parser.add_argument('-j', '--jobs', type=_jobs, default='auto',
                        help="number of worker processes, or 'auto' for one per physical core "
                             '(default: auto)')
    parser.add_argument('--fast', action='store_true',
                        help='run only the quick modules listed in tests/fast_modules.txt')
    parser.add_argument('-k', '--pattern', dest='patterns', action='append', default=[],
                        metavar='PATTERN',
                        help='only run tests whose name matches, as unittest -k does (repeatable)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='print one line with the time of every module')
    args = parser.parse_args(argv)
    if args.fast and args.modules:
        parser.error('--fast runs the modules in tests/fast_modules.txt; leave out module names')
    return parser, args


def main(argv=None):
    parser, args = parse_args(argv)
    known = discover_modules()
    if args.fast:
        names = list(read_fast_list())
        unknown = [name for name in names if name not in known]
        if unknown:
            print('tests/fast_modules.txt names modules that are not in tests/: '
                  + ', '.join(unknown), file=sys.stderr)
            return 2
    elif args.modules:
        names = []
        for given in args.modules:
            name = os.path.basename(given)
            name = name[:-3] if name.endswith('.py') else name
            if name not in known:
                parser.error(f'no test module {given} in tests/')
            if name not in names:
                names.append(name)
    else:
        names = known
    patterns = [pattern if '*' in pattern else f'*{pattern}*' for pattern in args.patterns]
    order = queue_order(names)
    jobs = max(1, min(args.jobs, len(order)))
    if not order:
        print('NO TESTS RAN')
        return 5
    print(f'Running {_plural(len(order), "test module")} with {_plural(jobs, "worker")}', flush=True)

    begin = time.perf_counter()
    marks = 0

    def on_record(record):
        nonlocal marks
        if args.verbose:
            flag = ''
            if record['errors']:
                flag = '  ERROR'
            elif record['failures'] or record['unexpected_successes']:
                flag = '  FAIL'
            print(f"[{time.perf_counter() - begin:7.1f} s] w{record['worker']:<2} "
                  f"{record['module']:<36} {record['seconds']:7.2f} s  "
                  f"{_plural(record['tests'], 'test')}{flag}", flush=True)
        else:
            mark = 'E' if record['errors'] else 'F' if _has_problems(record) else '.'
            marks += 1
            print(mark, end='\n' if marks % 70 == 0 else '', flush=True)

    signal.signal(signal.SIGTERM, _interrupt)  # a stopped run still stops its workers and cleans up
    run_dir = tempfile.mkdtemp(prefix='run_tests-', dir=tempfile.gettempdir())
    try:
        records = run_modules(order, known, jobs, run_dir, patterns, on_record)
    except KeyboardInterrupt:
        print('\nInterrupted.', file=sys.stderr)
        return 130
    except RuntimeError as problem:
        print(f'\n{problem}', file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
    wall = time.perf_counter() - begin
    if not args.verbose and marks % 70:
        print()
    fast = ('list' if patterns else 'check') if args.fast else ''  # -k leaves module times partial
    return report(records, order, wall, jobs, fast)


if __name__ == '__main__':
    sys.exit(main())
