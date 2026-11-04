#!/usr/bin/env python3
"""Pull private research packages with the read-only export token. Never prints or logs the token.

    list                      what the server holds
    pull --out DIR            one package (by filters, or --refs)
    sync --out DIR            only the rounds not yet in DIR, in small packages

A package the server is still building is waited for: the console answers 202 while it builds.
"""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
import tempfile
import time
from urllib.parse import urlencode
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.research_export import verify_package

HOST = 'chefjeff.belchingleo.online'  # Fixed: the token is never sent to any other host.
PREFIX = '/research-admin/'
TOKEN_FILE = Path.home()/'.config/chefjeff/research-export.token'
TOKEN_PATTERN = re.compile(r'cjx1\.[a-f0-9]{8}\.[A-Za-z0-9_-]{43}')
MAX_PACKAGE = 280_000_000
FILTERS = ('since', 'until', 'level', 'schema', 'site')
WAIT = 3600             # seconds pull waits for a package the server is still building
BATCH = 3               # rounds per package when syncing: what a console without background builds manages
SYNC_INDEX = 'sync-index.json'
SYNC_FORMAT = 'chefjeff-research-sync-v1'
# Listed fields that change when a stored round is updated (its final save, a later page close).
SIGNATURE = ('ended_at', 'duration', 'quality.complete', 'termination.session_close.reason', 'expires')


class PullError(Exception):
    pass


def connection():
    # Certificate and hostname are verified; http.client never follows redirects.
    return http.client.HTTPSConnection(HOST, 443, timeout=180, context=ssl.create_default_context())


def check_location(path):
    path = Path(path).expanduser().absolute()
    if path.resolve().is_relative_to(ROOT.resolve()):
        raise PullError('令牌文件不要放在仓库目录里，请使用默认位置 '+str(TOKEN_FILE)+'。')
    return path


def read_token(path=TOKEN_FILE):
    path = check_location(path)
    try:
        info = path.stat()
    except FileNotFoundError:
        raise PullError('还没有保存导出令牌；先运行 python3 scripts/pull_research.py save-token。') from None
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PullError('令牌文件必须属于当前用户且权限为600：chmod 600 '+str(path))
    token = path.read_text().strip()
    if not TOKEN_PATTERN.fullmatch(token):
        raise PullError('令牌文件格式不对，请重新运行 save-token。')
    return token


def save_token(path=TOKEN_FILE, replace=False, prompt=getpass.getpass):
    path = check_location(path)
    token = prompt('粘贴导出令牌（不回显）：').strip()
    if not TOKEN_PATTERN.fullmatch(token):
        raise PullError('令牌格式不对；请从服务器签发输出里完整复制 cjx1. 开头的那一行。')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() and not replace:
        raise PullError('已有令牌文件；确认要换成新令牌时加 --replace。')
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.token-')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as output:
            output.write(token+'\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


def request(token, method, path, body=None, accept=(200,)):
    headers = {'Host': HOST, 'Authorization': 'Bearer '+token, 'Connection': 'close'}
    if body is not None:
        body = urlencode(body).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    c = connection()
    try:
        c.request(method, PREFIX+path, body=body, headers=headers)
        response = c.getresponse()
    except BaseException:
        c.close()
        raise
    if response.status not in accept:
        try:
            message = json.loads(response.read(4096)).get('error', '')
        except ValueError:
            message = ''
        finally:
            c.close()
        raise PullError(f'服务器返回 HTTP {response.status}：{message or "没有说明"}')
    return c, response


def query(filters):
    return urlencode({key: value for key, value in (filters or {}).items() if value not in (None, '')})


def list_records(token, filters=None):
    records, page = [], 1
    while True:
        selected = query({**(filters or {}), 'page': page})
        c, response = request(token, 'GET', 'api/records?'+selected)
        try:
            data = json.loads(response.read(20_000_001))
        finally:
            c.close()
        records += data['records']
        if not data['records'] or len(records) >= data['total']:
            return {'total': data['total'], 'records': records}
        page += 1


def download(token, method, path, body=None, wait=WAIT):
    """Ask again while the server builds the package (202), or builds another one (429 with Retry-After)."""
    end = time.monotonic() + wait
    while True:
        c, response = request(token, method, path, body, accept=(200, 202, 429))
        if response.status == 200:
            return c, response
        retry = response.getheader('Retry-After')
        try:
            message = json.loads(response.read(4096)).get('error', '')
        except ValueError:
            message = ''
        finally:
            c.close()
        if response.status == 429 and retry is None:    # the token throttle, not a busy builder
            raise PullError(f'服务器返回 HTTP 429：{message or "没有说明"}')
        pause = min(30, max(1, int(retry) if (retry or '').isdigit() else 5))
        if time.monotonic() + pause > end:
            raise PullError(f'研究包还在生成，已等待 {wait} 秒；请稍后再运行一次，服务器会接着用已生成的包。')
        print('研究包正在生成，请稍候…' if response.status == 202 else '服务器正在生成另一份研究包，请稍候…',
              file=sys.stderr, flush=True)
        time.sleep(pause)


def pull(token, out, filters=None, refs=None, wait=WAIT):
    out = Path(out).expanduser()
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    if refs:
        c, response = download(token, 'POST', 'download/selected.cjresearch.zip', {'refs': json.dumps(refs)}, wait)
    else:
        c, response = download(token, 'GET', 'download/research.cjresearch.zip?'+query(filters), wait=wait)
    temporary = None
    try:
        length = int(response.getheader('Content-Length') or -1)
        if not 0 < length <= MAX_PACKAGE:
            raise PullError('服务器没有给出有效的研究包大小。')
        fd, temporary = tempfile.mkstemp(dir=out, prefix='.pull-', suffix='.part')
        temporary = Path(temporary)
        digest, received = hashlib.sha256(), 0
        with os.fdopen(fd, 'wb') as output:
            while chunk := response.read(65536):
                received += len(chunk)
                if received > length:
                    break
                digest.update(chunk); output.write(chunk)
        c.close()
        if received != length:
            raise PullError('研究包没有完整收到，请重试。')
        temporary.chmod(0o600)
        try:
            manifest = verify_package(temporary)
        except (ValueError, KeyError, OSError) as error:
            raise PullError('研究包没有通过manifest核对：'+str(error)) from None
        if str(int(manifest['expires'])) != response.getheader('X-Research-Expires'):
            raise PullError('研究包到期时间与服务器响应不一致。')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        for n in range(1, 1000):    # several packages can arrive within one second when syncing
            destination = out/(f'chefjeff-research-{stamp}.cjresearch.zip' if n == 1 else f'chefjeff-research-{stamp}-{n}.cjresearch.zip')
            try:
                os.link(temporary, destination)  # Never overwrites an existing package.
                break
            except FileExistsError:
                continue
        else:
            raise PullError('保存目录里同名的研究包太多，请换一个目录。')
        return {'path': str(destination), 'rounds': manifest['rounds'], 'bytes': length, 'sha256': digest.hexdigest(),
                'expires_at': datetime.fromtimestamp(manifest['expires'], timezone.utc).isoformat(timespec='seconds')}
    finally:
        c.close()
        if temporary:
            temporary.unlink(missing_ok=True)


def signature(row):
    return [row.get(key) for key in SIGNATURE]


def load_index(out):
    path = out/SYNC_INDEX
    if not path.exists():
        return {'format': SYNC_FORMAT, 'packages': {}, 'records': {}}
    index = json.loads(path.read_text())
    if index.get('format') != SYNC_FORMAT:
        raise PullError('同步目录里的清单格式不认识：'+str(path))
    return index


def save_index(out, index):
    fd, temporary = tempfile.mkstemp(dir=out, prefix='.sync-', suffix='.part')
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(index, output, ensure_ascii=False, indent=2)
        os.chmod(temporary, 0o600)
        os.replace(temporary, out/SYNC_INDEX)
    finally:
        Path(temporary).unlink(missing_ok=True)


def sync(token, out, filters=None, batch=BATCH, wait=WAIT):
    """Pull only the rounds DIR does not hold yet, keeping a local list of what came in which package.

    A package goes as a whole when it expires, when one of its rounds is no longer on the server
    (withdrawn or expired) or when one was updated there: each package's own terms say to remove
    the copy on any included withdrawal or the earliest expiry. Its other rounds are pulled again.
    """
    out = Path(out).expanduser()
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    index = load_index(out)
    report = {'removed_expired': [], 'removed_not_on_server': [], 'removed_updated': [], 'pulled': 0, 'packages_pulled': 0}

    def drop(name, reason, refs):
        (out/name).unlink(missing_ok=True)
        info = index['packages'].pop(name)
        for ref in info['refs']:
            index['records'].pop(ref, None)
        report[reason] += refs

    now = time.time()
    for name, info in list(index['packages'].items()):
        if not (out/name).exists() or info['expires'] <= now:
            drop(name, 'removed_expired', info['refs'])
    # All of the server's rounds, so a round outside the filters is not mistaken for a withdrawn one.
    server = {row['ref']: row for row in list_records(token)['records']}
    wanted = server if not any((filters or {}).values()) else {row['ref']: row for row in list_records(token, filters)['records']}
    for name, info in list(index['packages'].items()):
        gone = [ref for ref in info['refs'] if ref not in server]
        updated = [ref for ref in info['refs'] if ref in server and index['records'][ref]['signature'] != signature(server[ref])]
        if gone:
            drop(name, 'removed_not_on_server', gone)
        elif updated:
            drop(name, 'removed_updated', updated)
    save_index(out, index)
    missing = [ref for ref in wanted if ref not in index['records']]
    for start in range(0, len(missing), batch):
        refs = missing[start:start+batch]
        try:
            result = pull(token, out, refs=refs, wait=wait)
        except (PullError, OSError, http.client.HTTPException):
            time.sleep(5)       # one retry: a cut transfer ("没有完整收到") usually goes through again
            result = pull(token, out, refs=refs, wait=wait)
        name = Path(result['path']).name
        with zipfile.ZipFile(result['path']) as archive:   # verified by pull
            manifest = json.loads(archive.read('manifest.json'))
        refs = [source['source_ref'] for source in manifest['sources']]
        index['packages'][name] = {'sha256': result['sha256'], 'expires': manifest['expires'], 'refs': refs,
                                   'pulled_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
        for ref in refs:
            index['records'][ref] = {'package': name, 'signature': signature(server[ref])}
        save_index(out, index)      # an interrupted sync keeps every package it finished
        report['pulled'] += len(refs)
        report['packages_pulled'] += 1
    report.update(server_rounds=len(server), local_rounds=len(index['records']), local_packages=len(index['packages']),
                  index=str(out/SYNC_INDEX))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('save-token', 'list', 'pull', 'sync'))
    parser.add_argument('--token-file', type=Path, default=TOKEN_FILE)
    parser.add_argument('--replace', action='store_true', help='save-token: replace the saved token')
    parser.add_argument('--out', type=Path, help='pull, sync: private folder for the research packages')
    parser.add_argument('--batch', type=int, default=BATCH, help='sync: rounds per package, 1-50')
    parser.add_argument('--wait', type=int, default=WAIT, help='pull, sync: seconds to wait for a package being built')
    parser.add_argument('--refs', help='pull: comma-separated record refs (1-50) instead of filters')
    parser.add_argument('--since', help='UTC start date YYYY-MM-DD (a date, not a time), inclusive')
    parser.add_argument('--until', help='UTC end date YYYY-MM-DD (a date, not a time), inclusive')
    parser.add_argument('--level')
    parser.add_argument('--schema')
    parser.add_argument('--site', choices=('cn', 'global', 'unknown'))
    args = parser.parse_args(argv)
    filters = {key: getattr(args, key) for key in FILTERS}
    for key in ('since', 'until'):
        if filters[key] and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', filters[key]):
            parser.error(f'--{key} 写日期，格式是 YYYY-MM-DD（例如 2026-11-03），不带时间')
    if not 1 <= args.batch <= 50:
        parser.error('--batch 需要在 1 到 50 之间')
    try:
        if args.command == 'save-token':
            path = save_token(args.token_file, args.replace)
            return print('已保存导出令牌：'+str(path)+'（权限600）。')
        token = read_token(args.token_file)
        if args.command == 'list':
            return print(json.dumps(list_records(token, filters), ensure_ascii=False, indent=2))
        if not args.out:
            parser.error(args.command+' 需要 --out 指定保存目录')
        if args.command == 'sync':
            if args.refs:
                parser.error('sync 自己决定拉哪些记录，不能用 --refs')
            return print(json.dumps(sync(token, args.out, filters, args.batch, args.wait), ensure_ascii=False, indent=2))
        refs = [ref.strip() for ref in args.refs.split(',') if ref.strip()] if args.refs else None
        if refs and any(filters.values()):
            parser.error('--refs 不能和日期、关卡等筛选同时使用')
        print(json.dumps(pull(token, args.out, filters, refs, args.wait), ensure_ascii=False, indent=2))
    except (PullError, OSError, ValueError, http.client.HTTPException) as error:
        raise SystemExit('拉取已停止：'+str(error)) from None


if __name__ == '__main__':
    main()
