#!/usr/bin/env python3
"""Read aggregate counters from the hosted backend on this server; no database access needed."""
import argparse
import http.client
import json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8780)
    parser.add_argument('--host', default='chefjeff.online', help='The configured regional hostname')
    args = parser.parse_args()
    connection = http.client.HTTPConnection('127.0.0.1', args.port, timeout=5)
    try:
        connection.request('GET', '/ops/usage', headers={'Host': args.host})
        response = connection.getresponse()
        if response.status != 200:
            raise SystemExit(f'无法读取统计（HTTP {response.status}），请确认已部署统计版本。')
        usage = json.loads(response.read())['usage']
    except (OSError, ValueError, KeyError, http.client.HTTPException):
        raise SystemExit('无法读取统计，请确认 ChefJeff 服务正在运行。')
    finally:
        connection.close()
    print('统计开始时间（UTC）：', usage['tracking_since'])
    if usage.get('shared'):
        print('统计范围：', '两站汇总' if usage.get('scope') == 'global' else '暂为本站，尚未完成首次汇总')
        if not usage.get('synchronized'):
            print('共享统计尚未同步或已过期；本地持久化增量将在连接恢复后继续提交。')
        if not usage.get('regional_persistent'):
            print('本站统计持久化失败，重启可能丢失尚未汇总的增量。')
    for label, key in [('页面访问次数', 'page_views'), ('首次开局会话数', 'started_sessions'),
                       ('实际开局局数', 'started_rounds'), ('自然完成对局数', 'completed_rounds'),
                       ('手动结束局数', 'manual_ends'), ('当前游戏中的会话数', 'running_sessions'),
                       ('满员拒绝次数（页面／厨房名额）', 'full_rejections'),
                       ('同网络名额拒绝次数', 'network_full_rejections'),
                       ('估算访问浏览器数', 'estimated_visitor_browsers'), ('估算试玩浏览器数', 'estimated_player_browsers')]:
        print(label + '：', usage[key])
    print('次数包含重复访问和自己的测试；浏览器数是客户端标记估算，不是真实人数。')
    print('\n各关试玩情况：')
    for level in usage['levels']:
        print(f"第 {level['level']} 关：开局 {level['started_rounds']} 局，自然完成 {level['completed_rounds']} 局")
    print('\n已结束对局的时长汇总（有效游玩秒数 = 游戏内进度 / 节奏，不含暂停和排队）：')
    names = {'completed': '自然完成', 'manual_end': '手动结束', 'page_close': '页面关闭（收到通知）',
             'disconnected': '断线清理（延迟确认）', 'restart': '重开／换关', 'shutdown': '服务停止（不作玩家退出）'}
    if not usage['durations']: print('暂无已结束对局。')
    for level in usage['levels']:
        for outcome, label in names.items():
            rows = [row for row in usage['durations'] if row['level'] == level['level'] and row['outcome'] == outcome]
            n = sum(row['rounds'] for row in rows)
            if not n: continue
            active = sum(row['active_seconds'] for row in rows) / n
            game = sum(row['game_seconds'] for row in rows) / n
            print(f"第 {level['level']} 关 · {label}：{n} 局，平均有效游玩 {active:.1f} 秒，游戏内进度 {game:.1f} 秒")
            print('  ' + '；'.join(f"{row['bucket']}: {row['rounds']} 局" for row in rows))
    if not usage['persistent']:
        print('注意：当前仅保存在内存中，重启会丢失本次未持久化的计数。')
    if usage['storage_errors']:
        print('统计存储错误次数：', usage['storage_errors'])


if __name__ == '__main__':
    main()
