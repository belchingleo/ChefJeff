#!/usr/bin/env python3
"""Gracefully stop only this project's local macOS kitchen, outside a live round."""
import os
import shlex
import signal
import subprocess
import sys
import time
import json
from launch_web import ROOT, PORT, LOCAL_HTTP


def main():
    if sys.platform != 'darwin':
        print('此停止入口用于 macOS。')
        return 1
    result = subprocess.run(['/usr/sbin/lsof', '-nP', f'-iTCP:{PORT}', '-sTCP:LISTEN', '-t'],
                            capture_output=True, text=True)
    pids = set(result.stdout.split())
    if not pids:
        print('厨房已经停止。下次双击“开始网页版”即可。')
        return 0
    if len(pids) != 1:
        raise RuntimeError('发现多个监听进程，未停止任何程序。')
    pid = int(pids.pop())
    command = subprocess.check_output(['/bin/ps', '-p', str(pid), '-o', 'command='], text=True)
    args = shlex.split(command)
    cwd = subprocess.check_output(['/usr/sbin/lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'], text=True)
    if (len(args) < 2 or not any(a == 'cocos_server.py' or a == str(ROOT/'cocos_server.py') for a in args[1:])
            or f'n{ROOT}' not in cwd.splitlines()):
        raise RuntimeError('该端口不是本项目的厨房，未停止任何程序。')
    with LOCAL_HTTP.open(f'http://127.0.0.1:{PORT}/api/state', timeout=3) as response:
        state = json.load(response)
    if state.get('phase') not in ('ready', 'ended'):
        raise RuntimeError('当前还有未结束的对局。请先完成对局，或在游戏中重新开局回到准备页，再停止服务。')
    os.kill(pid, signal.SIGINT)
    deadline = time.monotonic()+8
    while time.monotonic() < deadline:
        status = subprocess.run(['/usr/sbin/lsof', '-a', '-p', str(pid), f'-iTCP:{PORT}',
                                 '-sTCP:LISTEN', '-t'], capture_output=True)
        if not status.stdout:
            print('厨房服务已停止。可以关闭游戏标签页；配置、记忆和对局日志已保留。')
            return 0
        time.sleep(.2)
    raise RuntimeError('厨房尚未退出，未强制结束进程。请稍后重试。')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
