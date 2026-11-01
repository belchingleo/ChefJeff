#!/usr/bin/env python3
"""Pull private research packages with the read-only export token. Never prints or logs the token."""
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
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.research_export import verify_package

HOST = 'chefjeff.belchingleo.online'  # Fixed: the token is never sent to any other host.
PREFIX = '/research-admin/'
TOKEN_FILE = Path.home()/'.config/chefjeff/research-export.token'
TOKEN_PATTERN = re.compile(r'cjx1\.[a-f0-9]{8}\.[A-Za-z0-9_-]{43}')
MAX_PACKAGE = 280_000_000
FILTERS = ('since', 'until', 'level', 'schema', 'site')


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


def request(token, method, path, body=None):
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
    if response.status != 200:
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


def pull(token, out, filters=None, refs=None):
    out = Path(out).expanduser()
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    if refs:
        c, response = request(token, 'POST', 'download/selected.cjresearch.zip', {'refs': json.dumps(refs)})
    else:
        c, response = request(token, 'GET', 'download/research.cjresearch.zip?'+query(filters))
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
        destination = out/f'chefjeff-research-{stamp}.cjresearch.zip'
        os.link(temporary, destination)  # Never overwrites an existing package.
        return {'path': str(destination), 'rounds': manifest['rounds'], 'bytes': length, 'sha256': digest.hexdigest(),
                'expires_at': datetime.fromtimestamp(manifest['expires'], timezone.utc).isoformat(timespec='seconds')}
    finally:
        c.close()
        if temporary:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('save-token', 'list', 'pull'))
    parser.add_argument('--token-file', type=Path, default=TOKEN_FILE)
    parser.add_argument('--replace', action='store_true', help='save-token: replace the saved token')
    parser.add_argument('--out', type=Path, help='pull: folder for the research package')
    parser.add_argument('--refs', help='pull: comma-separated record refs (1-50) instead of filters')
    parser.add_argument('--since', help='UTC start date YYYY-MM-DD, inclusive')
    parser.add_argument('--until', help='UTC end date YYYY-MM-DD, inclusive')
    parser.add_argument('--level')
    parser.add_argument('--schema')
    parser.add_argument('--site', choices=('cn', 'global', 'unknown'))
    args = parser.parse_args(argv)
    filters = {key: getattr(args, key) for key in FILTERS}
    try:
        if args.command == 'save-token':
            path = save_token(args.token_file, args.replace)
            return print('已保存导出令牌：'+str(path)+'（权限600）。')
        token = read_token(args.token_file)
        if args.command == 'list':
            return print(json.dumps(list_records(token, filters), ensure_ascii=False, indent=2))
        if not args.out:
            parser.error('pull 需要 --out 指定保存目录')
        refs = [ref.strip() for ref in args.refs.split(',') if ref.strip()] if args.refs else None
        if refs and any(filters.values()):
            parser.error('--refs 不能和日期、关卡等筛选同时使用')
        print(json.dumps(pull(token, args.out, filters, refs), ensure_ascii=False, indent=2))
    except (PullError, OSError, http.client.HTTPException) as error:
        raise SystemExit('拉取已停止：'+str(error)) from None


if __name__ == '__main__':
    main()
