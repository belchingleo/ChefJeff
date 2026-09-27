#!/usr/bin/env python3
"""Start or reuse the local kitchen, then open its stable web address."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
PORT = 8775
LOCAL_HTTP = build_opener(ProxyHandler({}))


def kitchen_ready(port):
    try:
        with LOCAL_HTTP.open(f'http://127.0.0.1:{port}/api/state', timeout=2) as response:
            state = json.load(response)
        return isinstance(state, dict) and all(k in state for k in ('game_id', 'phase', 'connection', 'memory'))
    except (OSError, ValueError):
        return False


def ensure_server(port=PORT):
    if kitchen_ready(port):
        return None
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError(f'端口 {port} 已被占用，但厨房没有正常响应。请保留当前窗口，把提示发给我。')
    if not (ROOT / 'cocos-kitchen/build/web/index.html').is_file():
        raise RuntimeError('缺少网页构建，请先运行 python3 scripts/build_cocos.py web。')
    log = ROOT / 'logs/web-startup.log'
    log.parent.mkdir(exist_ok=True)
    options = {'start_new_session': True} if os.name != 'nt' else {
        'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    with log.open('ab') as output:
        process = subprocess.Popen(
            [sys.executable, '-u', str(ROOT / 'cocos_server.py'), '--port', str(port)],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=output, **options)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if kitchen_ready(port):
            return process
        if process.poll() is not None:
            break
        time.sleep(.2)
    raise RuntimeError(f'厨房启动未成功，请检查启动日志：{log}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-open', action='store_true', help='仅检查或启动，不打开浏览器')
    args = parser.parse_args()
    try:
        process = ensure_server()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    url = f'http://127.0.0.1:{PORT}/'
    print(f'{"厨房已启动" if process else "厨房已在运行"}：{url}')
    if not args.no_open:
        if sys.platform == 'darwin':
            subprocess.run(['/usr/bin/open', url], check=True)
        else:
            webbrowser.open(url)
    print('服务在后台运行，可以关闭这个终端窗口。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
