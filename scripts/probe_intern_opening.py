#!/usr/bin/env python3
"""One experimental Intern-Decision request using the real opening payload.

No game actions, saved credentials, existing player memory, journals, or retries.
The compact input is reversible; it changes presentation, not the evidence.
"""
from collections import Counter
from copy import deepcopy
import argparse
import getpass
import json
from pathlib import Path
import sys
import tempfile
import time
import urllib.error
import urllib.request
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cooperation_memory import CooperationMemory, round_scope
from hosted_jev import ForwardError, NoRedirect, parse_answer, valid_key
from jev import DecisionLoop, http_error_detail
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient

ENDPOINT = 'https://discovery-api.intern-ai.org.cn/v1/systemone'
MODEL = 'intern-decision-4b'
FORMAT = 'chefjeff-opening-sparse-jsonl-v1'
GROUPS = (('kitchen', 'stations'), ('kitchen', 'map', 'equipment'))
HEADER = (FORMAT + '. Each following line is [field_name, JSON_value] for the full state. '
          'The @defaults line gives shared fields for every child object at each named path. '
          'Merge defaults first, then explicit child fields (including null). '
          'All other fields, rules and choices retain their original meaning; no evidence is truncated.')


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def at_path(value, path):
    for part in path:
        value = value[part]
    return value


def compact_payload(payload):
    """Share repeated station/equipment values and send compact JSON lines as text."""
    # Normalize exactly as HTTP JSON does (e.g. Python coordinates tuples become arrays).
    result = json.loads(compact_json(payload))
    state = result['state']
    defaults = {}
    for path in GROUPS:
        rows = at_path(state, path)
        if not rows or not all(isinstance(row, dict) for row in rows.values()):
            continue
        shared = {}
        # A field must exist in every original row: absent and null stay distinct.
        fields = set.intersection(*(set(row) for row in rows.values()))
        for field in sorted(fields):
            values = {name: compact_json(row[field]) for name, row in rows.items()}
            value, count = Counter(values.values()).most_common(1)[0]
            if count < 3 or (count - 1) * (len(compact_json(field)) + len(value) + 2) < 40:
                continue
            shared[field] = json.loads(value)
            for name, row in rows.items():
                if values[name] == value:
                    del row[field]
        if shared:
            defaults['.'.join(path)] = shared
    records = [['@defaults', defaults], *[[name, value] for name, value in state.items()]]
    result['state'] = HEADER + '\n' + '\n'.join(compact_json(row) for row in records)
    # Refuse a transformation that cannot reproduce every original value.
    if restore_state(result['state']) != json.loads(compact_json(payload['state'])):
        raise ValueError('Compact state did not restore the original evidence')
    return result


def restore_state(text):
    lines = text.splitlines()
    if not lines or lines[0] != HEADER:
        raise ValueError('Unknown opening-test input format')
    records = dict(json.loads(line) for line in lines[1:])
    defaults = records.pop('@defaults')
    for path, shared in defaults.items():
        rows = at_path(records, path.split('.'))
        for name, row in rows.items():
            rows[name] = {**deepcopy(shared), **row}
    return records


def opening_payload(level=1):
    """Capture the normal scheduler's first request before its HTTP worker starts."""
    config = level_config(load_config(), level)
    config.update(order_seed=1, spawn_seed=0, model=MODEL)
    kitchen = SpatialKitchen(config)
    client = SpatialJevClient(kitchen.c, key='offline-opening-placeholder')

    class Captured(Exception):
        pass

    def capture(kind, data):
        if kind == 'ai_request':
            raise Captured(deepcopy(data['payload']))

    ai = DecisionLoop(kitchen, client, capture, lambda _message: None)
    # A fresh local player has memory enabled, with no previous episodes.
    setting = {'provider': 'intern-decision', 'base_url': ENDPOINT, 'model': MODEL}
    with tempfile.TemporaryDirectory(prefix='chefjeff-opening-') as folder:
        ai.cooperation_memory = CooperationMemory(Path(folder) / 'memory.json').context(round_scope(setting, kitchen))
        try:
            ai.poll()
        except Captured as captured:
            return captured.args[0]
    raise RuntimeError('The scheduler did not produce an opening request')


def send_once(payload, key, timeout=20):
    """Fixed HTTPS endpoint, no redirects, no retry and no raw response output."""
    request = urllib.request.Request(ENDPOINT, data=compact_json(payload).encode('utf-8'), method='POST',
                                     headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    started = time.monotonic()
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise RuntimeError('模型回复过大。')
        answer = parse_answer(raw, payload)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'Intern-Decision HTTP {error.code}{http_error_detail(error, key)}') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError('Intern-Decision 网络连接失败或超时。') from None
    except ForwardError:
        raise RuntimeError('Intern-Decision 未返回候选集内的有效动作和冲刺选择。') from None
    # Only an allowlisted action and numeric measurements are printed; never provider text.
    return {'choice': answer['choice'], 'sprint': answer['sprint'], **answer['usage'],
            'latency_seconds': round(time.monotonic() - started, 3)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='只测试 Intern-Decision 的一次开局请求，不操作游戏、不保存 Key。')
    parser.add_argument('--level', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--dry-run', action='store_true', help='只生成并校验输入，不读取 Key、不调用接口')
    parser.add_argument('--uncompressed', action='store_true', help='对照测试：发送原始输入而非实验压缩格式')
    args = parser.parse_args(argv)
    original = opening_payload(args.level)
    payload = original if args.uncompressed else compact_payload(original)
    report = {'level': args.level, 'order_seed': 1, 'spawn_seed': 0,
              'format': 'original-object' if args.uncompressed else FORMAT,
              'original_request_bytes': len(compact_json(original).encode('utf-8')),
              'test_request_bytes': len(compact_json(payload).encode('utf-8')),
              'all_evidence_preserved': True, 'request_count': 0}
    print('只测第一条决策；输入 Token 数以接口返回为准，字节数不等于 Token 数。', flush=True)
    print('测试超时为 20 秒；接受请求不代表满足游戏延迟要求，也不代表整局可用。', flush=True)
    if not args.dry_run:
        if not sys.stdin.isatty():
            print('请在交互式终端运行，以隐藏方式输入 Key；不要把 Key 放进命令。', file=sys.stderr)
            return 2
        with warnings.catch_warnings():
            # Do not let getpass fall back to echoing a key on an unusual terminal.
            warnings.simplefilter('error', getpass.GetPassWarning)
            try:
                key = getpass.getpass('请粘贴端砚 API Key（输入不显示，不保存）：').strip()
            except getpass.GetPassWarning:
                print('此终端无法隐藏输入；没有读取 Key，也没有发起请求。', file=sys.stderr)
                return 2
        if not valid_key(key):
            print('Key 格式无效；没有发起请求。', file=sys.stderr)
            return 2
        report['request_count'] = 1
        try:
            report.update(outcome='success', **send_once(payload, key))
        except RuntimeError as error:
            report.update(outcome='error', error=str(error).replace(key, '***'))
        finally:
            key = None
    else:
        report['outcome'] = 'dry_run'
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['outcome'] == 'error' else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        raise SystemExit('\n测试已取消。')
