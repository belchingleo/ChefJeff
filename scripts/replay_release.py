#!/usr/bin/env python3
"""Replay research rounds with the code of the release that recorded them. Local and read only; no model is called.

    python3 scripts/replay_release.py check ~/ChefJeff-research [--commit SHA] [--out report.json]
    python3 scripts/replay_release.py record SHA        # note which commit a deployed build came from

A round replays exactly only on the engine that played it, and the engine changes from release to release. Each
research record carries its build's fingerprint (release_info.py). This script finds the commit with that
fingerprint, extracts that commit's code into a private cache (git archive; the working tree is not touched) and
replays the round there: the engine, the state projection and the request composer come from the old commit,
and the replay check itself comes from this checkout (research_replay.py), so a fix to the checker applies to old
rounds too. Requests are rebuilt with the old commit's own research_replay.rebuild_requests when it has one.

Fingerprints already matched to a commit are kept in deploy/release-fingerprints.json. An unknown fingerprint
is looked up by computing the fingerprint of earlier commits (all branches, newest first, from before the round
started), and a match is added to that table. `record` adds a commit directly: run it for every deployed build.

The report holds refs, releases and counts only: no state, request or player text leaves the replay.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config_contract as cc  # noqa: E402
from research_record import validate_record  # noqa: E402
from scripts.research_export import verify_package  # noqa: E402

TABLE = ROOT / 'deploy' / 'release-fingerprints.json'
TABLE_FORMAT = 'chefjeff-release-fingerprints-v1'
CACHE = Path.home() / '.cache' / 'chefjeff' / 'release-code'
SEEN = 'fingerprints-by-commit.json'   # in the cache: commits already fingerprinted while searching
TOOL = ROOT / 'research_replay.py'

FINGERPRINT = '''
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import release_info
print(release_info.release_info()['fingerprint'])
'''

# Runs inside the old commit's code: argv = code root, this checkout's research_replay.py, record files.
DRIVER = '''
import importlib.util, json, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
sys.dont_write_bytecode = True
root, tool_path, files = sys.argv[1], sys.argv[2], sys.argv[3:]
sys.path.insert(0, root)
spec = importlib.util.spec_from_file_location('replay_tool', tool_path)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)        # its imports (engine, projection) resolve to the old commit
try:
    import research_replay as own    # the old commit's request rebuild, matching its composer
    rebuild = own.rebuild_requests
except (ImportError, AttributeError):
    rebuild = None
out = []
for path in files:
    with open(path, encoding='utf-8') as f:
        item = json.load(f)
    record, row = item['record'], {'ref': item['ref']}
    try:
        report = tool.check(record)
        row.update(replay=report['replay'], states_checked=report.get('replay_states_checked', 0),
                   mismatches=len(report.get('replay_mismatches') or []),
                   first_mismatch={k: v for k, v in ((report.get('replay_mismatches') or [{}])[0]).items()
                                   if k in ('engine_input_n', 'game_time_ms')} or None)
    except Exception as exc:
        row.update(replay='error', error=type(exc).__name__)
    if record.get('replay') and rebuild is not None:
        try:
            row['requests'] = dict(Counter(r['status'] for r in rebuild(record)))
        except Exception as exc:
            row['requests'] = {'error': type(exc).__name__}
    elif record.get('replay'):
        row['requests'] = {'not_available': 1}
    out.append(row)
print(json.dumps(out))
'''


class ReleaseError(Exception):
    pass


def git(*args, text=True):
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True, capture_output=True, text=text).stdout


def full_sha(commit):
    try:
        return git('rev-parse', '--verify', commit + '^{commit}').strip()
    except subprocess.CalledProcessError:
        raise ReleaseError(f'未知的提交：{commit}') from None


def extract(commit, dest):
    dest.mkdir(parents=True)
    archive = subprocess.run(['git', '-C', str(ROOT), 'archive', commit], check=True, capture_output=True).stdout
    subprocess.run(['tar', '-x', '-C', str(dest)], input=archive, check=True)


def fingerprint(root):
    result = subprocess.run([sys.executable, '-I', '-c', FINGERPRINT, str(root)], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def code_root(commit, cache=CACHE):
    """The commit's code, extracted once into the cache."""
    sha = full_sha(commit)
    root = Path(cache) / sha
    if (root / '.complete').exists():
        return root
    if root.exists():
        shutil.rmtree(root)
    work = Path(cache) / (sha + '.partial')
    if work.exists():
        shutil.rmtree(work)
    extract(sha, work)
    (work / '.complete').write_text(sha + '\n')
    work.rename(root)
    return root


def read_table(path=TABLE):
    if not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('format') != TABLE_FORMAT:
        raise ReleaseError('版本指纹表格式不对：' + str(path))
    return data['releases']


def write_table(releases, path=TABLE):
    text = json.dumps({'format': TABLE_FORMAT, 'releases': dict(sorted(releases.items()))},
                      ensure_ascii=False, indent=2)
    Path(path).write_text(text + '\n', encoding='utf-8')


def record_commit(commit, path=TABLE):
    """Add a commit's build fingerprint to the table; returns (fingerprint, entry)."""
    sha = full_sha(commit)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / 'code'
        extract(sha, root)
        fp = fingerprint(root)
        version = subprocess.run([sys.executable, '-I', '-c', FINGERPRINT.replace("['fingerprint']", "['version']"),
                                  str(root)], capture_output=True, text=True).stdout.strip()
    if not fp:
        raise ReleaseError(f'{sha[:7]} 算不出版本指纹（没有 release_info.py？）')
    releases = read_table(path)
    entry = {'commit': sha, 'version': version}
    releases[fp] = entry
    write_table(releases, path)
    return fp, entry


def search_commit(fp, before=None, limit=300, cache=CACHE):
    """The newest commit (any branch, committed before `before`) whose build has this fingerprint."""
    args = ['rev-list', '--all', '--date-order', f'--max-count={limit}']
    if before:
        args.append('--before=' + before)
    seen_file = Path(cache) / SEEN
    try:
        seen = json.loads(seen_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        seen = {}
    found = None
    with tempfile.TemporaryDirectory() as folder:
        for i, sha in enumerate(git(*args).split()):
            if sha not in seen:
                if i and i % 25 == 0:
                    print(f'  查找版本指纹 {fp[:12]}：已试 {i} 个提交', file=sys.stderr)
                root = Path(folder) / str(i)
                extract(sha, root)
                seen[sha] = fingerprint(root)
                shutil.rmtree(root)
            if seen[sha] == fp:
                found = sha
                break
    seen_file.parent.mkdir(parents=True, exist_ok=True)
    seen_file.write_text(json.dumps(seen), encoding='utf-8')
    return found


def records(paths):
    """{ref: record} from local research packages (verified first); legacy-v1 rounds are only counted."""
    files = []
    for p in paths:
        p = Path(p).expanduser()
        files += sorted(p.glob('*.cjresearch.zip')) if p.is_dir() else [p]
    found, legacy = {}, set()
    for path in files:     # sorted by name, so a newer package's copy of a round wins
        manifest = verify_package(path)
        with zipfile.ZipFile(path) as archive:
            for source in manifest['sources']:
                ref, prefix = source['source_ref'], source['source_ref'] + '/'
                if prefix + 'metadata.json' not in archive.namelist():
                    legacy.add(ref)
                    continue
                metadata = json.loads(archive.read(prefix + 'metadata.json'))
                record = {k: v for k, v in metadata.items() if k not in ('artifacts', 'source_expires_at')}
                record['resolved_config'] = json.loads(archive.read(prefix + 'resolved-config.json'))
                record['events'] = [json.loads(line) for line in archive.read(prefix + 'events.jsonl').splitlines() if line]
                validate_record(record)
                if cc.sha256(record) != source['record_sha256']:
                    raise ReleaseError('研究包里的记录校验不通过：' + str(path))
                found[ref] = record
    return found, len(legacy - set(found))


def day_after(started_at):
    if isinstance(started_at, (int, float)):
        moment = datetime.fromtimestamp(started_at, timezone.utc)
    else:
        moment = datetime.fromisoformat(str(started_at).replace('Z', '+00:00'))
    return (moment + timedelta(days=1)).strftime('%Y-%m-%d')


def resolve(found, commit=None, search=300, table=TABLE, cache=CACHE):
    """{fingerprint: sha or None} for the rounds' builds, adding searched matches to the table."""
    releases = read_table(table)
    builds = {}
    for record in found.values():
        fp = (record.get('release') or {}).get('fingerprint')
        if fp:
            builds.setdefault(fp, []).append(record)
    if commit:
        sha = full_sha(commit)
        return {fp: sha for fp in builds}
    out, added = {}, False
    for fp, rounds in builds.items():
        if fp in releases:
            out[fp] = releases[fp]['commit']
            continue
        latest = max((r.get('started_at') for r in rounds if r.get('started_at')), default=None, key=str)
        sha = search_commit(fp, day_after(latest) if latest else None, search, cache)
        out[fp] = sha
        if sha:
            releases[fp] = {'commit': sha, 'version': rounds[0]['release'].get('version')}
            added = True
            print(f'版本指纹 {fp[:12]} 对应提交 {sha[:7]}，已记入 {Path(table).name}', file=sys.stderr)
    if added:
        write_table(releases, table)
    return out


def replay_group(root, items):
    """Replay [(ref, record)] in the code at `root` (a release's extracted code); returns the driver's rows."""
    with tempfile.TemporaryDirectory() as folder:
        os.chmod(folder, 0o700)
        files = []
        for i, (ref, record) in enumerate(items):
            path = Path(folder) / f'{i}.json'
            path.write_text(json.dumps({'ref': ref, 'record': record}), encoding='utf-8')
            files.append(str(path))
        result = subprocess.run([sys.executable, '-I', '-c', DRIVER, str(root), str(TOOL), *files],
                                capture_output=True, text=True)
    if result.returncode != 0:
        last = (result.stderr.strip().splitlines() or ['?'])[-1]
        return [{'ref': ref, 'replay': 'error', 'error': last[:200]} for ref, _ in items]
    return json.loads(result.stdout)


def check(paths, commit=None, search=300, cache=CACHE, table=TABLE):
    found, legacy = records(paths)
    commits = resolve(found, commit, search, table, cache)
    groups, rows = {}, []
    for ref, record in found.items():
        release = record.get('release') or {}
        sha = commits.get(release.get('fingerprint'))
        base = {'ref': ref, 'version': release.get('version'), 'fingerprint': (release.get('fingerprint') or '')[:12],
                'commit': sha[:12] if sha else None, 'started': str(record.get('started_at'))[:10]}
        if not record.get('replay'):
            rows.append({**base, 'replay': 'not_available'})
        elif not sha:
            rows.append({**base, 'replay': 'release_not_found'})
        else:
            groups.setdefault(sha, []).append((ref, record, base))
    # One process per round, several at once: a round replays on one core.
    tasks = [(code_root(sha, cache), ref, record, base) for sha, items in groups.items() for ref, record, base in items]
    with ThreadPoolExecutor(max_workers=max(1, min(len(tasks), os.cpu_count() or 1))) as pool:
        done = pool.map(lambda task: (task[3], replay_group(task[0], [(task[1], task[2])])[0]), tasks)
        rows += [{**base, **row} for base, row in done]
    rows.sort(key=lambda r: (r['started'], r['ref']))
    requests = Counter()
    for row in rows:
        requests.update({k: v for k, v in (row.get('requests') or {}).items() if isinstance(v, int)})
    return {'rounds': len(rows), 'legacy_v1': legacy, 'replay': dict(Counter(r['replay'] for r in rows)),
            'requests': dict(requests), 'releases': {r['fingerprint']: {'version': r['version'], 'commit': r['commit']}
                                                     for r in rows if r['fingerprint']},
            'by_round': rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    c = sub.add_parser('check', help='replay rounds from local research packages with their own release')
    c.add_argument('paths', nargs='+', help='research packages (.cjresearch.zip) or folders of them')
    c.add_argument('--commit', help='replay every round with this commit instead of looking up its fingerprint')
    c.add_argument('--search', type=int, default=300, help='commits to try for an unknown fingerprint')
    c.add_argument('--cache', default=str(CACHE), help='where extracted release code is kept')
    c.add_argument('--out', help='write the JSON report here instead of printing it')
    r = sub.add_parser('record', help="add a commit's build fingerprint to deploy/release-fingerprints.json")
    r.add_argument('commit')
    args = parser.parse_args(argv)
    try:
        if args.command == 'record':
            fp, entry = record_commit(args.commit)
            print(f"{entry['version']} {entry['commit'][:7]} → 指纹 {fp[:12]}")
            return 0
        report = check(args.paths, args.commit, args.search, Path(args.cache))
    except (ReleaseError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'无法回放：{error}', file=sys.stderr)
        return 1
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    summary = ', '.join(f'{k} {v}' for k, v in report['replay'].items())
    print(f"{report['rounds']} rounds ({summary}); requests {report['requests']}; legacy v1 {report['legacy_v1']}",
          file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
