#!/usr/bin/env python3
"""Realtime text kitchen. Enter a menu number or a stable command."""
from __future__ import annotations
import argparse
import json
import os
import queue
import sys
import time
from datetime import datetime
from pathlib import Path
from kitchen import Kitchen, ROOT, STATES, load_config
from jev import JevClient, DecisionLoop


class Journal:
    def __init__(self, name="game"):
        folder = ROOT / "logs"
        folder.mkdir(exist_ok=True)
        self.path = folder / f"{name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.jsonl"
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.f = os.fdopen(fd, "w", encoding="utf-8")

    def __call__(self, kind, data):
        self.f.write(json.dumps({"wall_time": datetime.now().astimezone().isoformat(), "kind": kind, **data}, ensure_ascii=False) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


class Console:
    """Nonblocking terminal line editor; event output preserves partially typed input."""
    def __init__(self):
        import codecs
        self.q = queue.Queue()
        self.active = False
        self.buffer = ""
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.saved_terminal = None
        self.escape = ""
        self.eof = False

    def write(self, text):
        if sys.stdin.isatty() and self.active:
            print("\r\033[2K" + text, flush=True)
            print("动作> " + self.buffer, end="", flush=True)
        else:
            print(text, flush=True)

    def start(self):
        if sys.stdin.isatty():
            import termios
            import tty
            self.saved_terminal = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        self.active = True
        print("动作> ", end="", flush=True)

    def read_input(self):
        import select
        if self.eof or not select.select([sys.stdin], [], [], 0)[0]:
            return
        data = os.read(sys.stdin.fileno(), 1024)
        if not data:
            self.eof = True
            self.q.put("quit")
            return
        for ch in self.decoder.decode(data):
            if self.escape:
                self.escape += ch
                if len(self.escape) > 2 and ch.isalpha():
                    self.escape = ""
                elif len(self.escape) > 8:
                    self.escape = ""
                continue
            if ch == "\x1b":
                self.escape = ch
            elif ch in ("\r", "\n"):
                command = self.buffer.strip()
                self.buffer = ""
                self.q.put(command)
                if sys.stdin.isatty():
                    print("\r\033[2K动作> " + command, flush=True)
                    print("动作> ", end="", flush=True)
            elif ch in ("\x7f", "\b"):
                self.buffer = self.buffer[:-1]
                if sys.stdin.isatty():
                    print("\r\033[2K动作> " + self.buffer, end="", flush=True)
            elif ch == "\x04":
                self.q.put("quit")
            elif ch.isprintable():
                self.buffer += ch
                if sys.stdin.isatty():
                    print(ch, end="", flush=True)

    def close(self):
        self.active = False
        if self.saved_terminal is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.saved_terminal)
            self.saved_terminal = None


def describe(k):
    lines = [f"\n厨房 {k.time:.1f}s / {k.c['round_seconds']}s  |  出餐 {k.served}  收入 {k.money} 元  差评 {k.bad_reviews}"]
    order_names = {"pending":"待出餐", "served":"已完成", "rejected":"差评退单", "expired":"已超时"}
    for o in k.orders:
        if o["status"] != "future":
            lines.append(f"  {o['id']} 牛排：{order_names[o['status']]}" + (f"，剩 {max(0,o['deadline']-k.time):.1f}s" if o['status']=='pending' else ""))
    for who, a in k.chefs.items():
        j = a.job
        hand = f"{a.hand.id} {STATES[a.hand.stage]}" if a.hand else "空手"
        task = f"{j.action.label}，移动剩 {j.travel:.1f}s / 操作剩 {j.work:.1f}s" if j else "空闲"
        lines.append(f"  {'你' if who=='human' else 'Jev'}：在{k.stations[a.location].name}，{hand}；{task}")
    for key in k.boards + k.pots:
        s = k.stations[key]
        f = s.food
        desc = "空" if not f else f"{f.id} {STATES[f.stage]}"
        if f and key in k.boards:
            desc += f"，切配 {f.chopped:.1f}/{k.c['chop_seconds']}s"
        if f and key in k.pots:
            if s.fire:
                desc += "，正在着火！"
            elif not s.heating:
                desc += "，火已灭，待清理"
            else:
                ready = k.c['cook_seconds']
                burn = ready+k.c['burn_after_ready']
                fire = burn+k.c['fire_after_burn']
                limit, title = (ready,"做熟") if f.heated < ready else ((burn,"糊锅") if f.heated < burn else (fire,"着火"))
                desc += f"，距{title} {max(0,limit-f.heated):.1f}s"
        lines.append(f"  {key} {s.name}：{desc}" + (f"（{'你' if s.lock=='human' else 'Jev'}操作中）" if s.lock else ""))
    for item in k.ground.values():
        lines.append(f"  地上：{item.food.id} {STATES[item.food.stage]}，在{k.stations[item.location].name}旁")
    return "\n".join(lines)


def show_menu(k, console):
    actions = k.actions("human")
    numbers = k.menu_numbers()
    console.write("\n你的可选动作（编号全局固定；过期动作会拒绝执行）：\n" + "\n".join(
        f"  {numbers[a.key]:2}. {a.label}  [{a.key}]" for a in actions) +
        "\n  m 菜单 | s 全局状态 | j Jev 状态 | pause 暂停全局 | resume 继续 | quit 退出")
    return {numbers[a.key]: a for a in actions}


def check_live(c):
    client = JevClient(c)
    k = Kitchen(c)
    actions = k.actions("jev")
    payload = client.payload(k.snapshot(), actions)
    journal = Journal("connection-check")
    try:
        journal("ai_request", {"payload":payload})
        result = client.ask(payload)
        journal("ai_response", result)
        print(f"实时调用成功：模型 {result['model']}，选择 {result['choice']}，延迟 {result['latency']:.2f}s，用量 {result['usage']}")
        print(f"核验日志：{journal.path}")
    finally:
        journal.close()


def play(args):
    c = load_config(args.config)
    if args.check:
        check_live(c)
        return
    client = JevClient(c)  # Fail before starting a clock if credentials are missing.
    print("\n人 × Jev 文字厨房\n")
    print(f"两个区域 · {c['boards']} 块案板 · {c['pots']} 口锅 · 一个出餐口。双方可做全部动作。")
    print(f"目标：{c['round_seconds']} 秒内成功出餐至少 {c['target_served']} 单，净收入至少 {c['target_money']} 元，差评不超过 {c['max_bad_reviews']} 次。")
    print(f"切配 {c['chop_seconds']}s；下锅自动加热 {c['cook_seconds']}s 做熟，再过 {c['burn_after_ready']}s 糊锅，再过 {c['fire_after_burn']}s 着火。")
    print("放案板→切配→拿半成品→下锅→取熟菜→出餐。锅不需要人守着，离开也继续加热。")
    print("所有操作自动包含走到目标的时间。选择新的动作会中断原动作。")
    print("Jev 使用真实 API；联网失败会明确提示，不用脚本替代。按菜单编号或输入方括号内命令操作。")
    print("输入 pause 可以暂停整个厨房；输入 m 查看当前动作，s 查看全局。Ctrl+C 可退出。")
    if not args.start:
        input("\n按回车开始计时和调用 Jev（现在尚未开局）…")
    k = Kitchen(c)
    journal = Journal("game")
    journal("start", {"config": c, "state": k.snapshot()})
    console = Console()
    ai = DecisionLoop(k, client, journal, lambda msg: console.write(f"[{k.time:6.1f}s] {msg}"))
    console.write(describe(k))
    menu = show_menu(k, console)
    console.start()
    cursor = 0
    paused = False
    last = time.monotonic()
    last_status = last
    try:
        while not k.ended:
            now = time.monotonic()
            if not paused:
                k.advance(now-last)
            last = now
            console.read_input()
            while True:
                try:
                    command = console.q.get_nowait()
                except queue.Empty:
                    break
                command = command.strip().lower()
                if command in ("quit", "q", "退出"):
                    k.aborted = True
                    k.ended = True
                    break
                if command in ("pause", "暂停"):
                    paused = True
                    ai.invalidate()
                    journal("pause", {"t":k.time})
                    console.write("已暂停整个厨房和新请求。输入 resume 继续。")
                elif command in ("resume", "继续"):
                    paused = False
                    ai.invalidate()
                    last = time.monotonic()
                    journal("resume", {"t":k.time})
                    console.write("继续计时。")
                elif command in ("s", "status", "状态"):
                    console.write(describe(k))
                elif command in ("m", "help", "?", "菜单", ""):
                    menu = show_menu(k, console)
                elif command in ("j", "jev"):
                    console.write(f"Jev：{'请求中' if ai.inflight else '待下次判断'}；最近选择 {ai.last_choice}；实际模型 {ai.actual_model}；成功 {ai.successes}/{ai.calls}；用量 {ai.tokens}")
                elif paused:
                    console.write("当前已暂停；输入 resume 后执行动作。")
                else:
                    if command.isdigit():
                        action = menu.get(int(command))
                    else:
                        action = next((a for a in k.actions('human') if a.key == command), None)
                    if action:
                        ok, message = k.start('human', action)
                        journal("human_input", {"t":k.time, "input":command, "action":action.key, "applied":ok, "message":message})
                        if not ok:
                            console.write(message)
                    else:
                        console.write("没有这个动作；输入 m 查看菜单。")
                    menu = show_menu(k, console)
            if not k.ended:
                ai.poll(enabled=not paused)
            refresh_menu = False
            for event in k.events[cursor:]:
                journal("event", event)
                console.write(f"[{event['t']:6.1f}s] {event['message']}")
                if event.get('actor') == 'human' and event.get('kind') in ('action_done','arrival_conflict'):
                    refresh_menu = True
            cursor = len(k.events)
            if refresh_menu and not k.ended:
                console.write(describe(k))
                menu = show_menu(k, console)
            # Compact heartbeat makes it clear that the game is running even while typing.
            if now-last_status >= 10 and not paused:
                console.write(describe(k))
                last_status = now
            k.assert_invariants()
            if args.seconds and k.time >= args.seconds:
                k.aborted = True
                k.ended = True
            time.sleep(.05)
    except KeyboardInterrupt:
        k.aborted = True
        k.ended = True
    finally:
        ai.closed = True
        ai.invalidate()
        journal("end", {"state":k.snapshot(), "result":k.result(), "aborted":k.aborted,
                        "ai_calls":ai.calls, "ai_successes":ai.successes, "usage":ai.tokens})
        console.close()
        console.write("\n" + k.result() + f"\n本局日志：{journal.path}")
        journal.close()


def main():
    parser = argparse.ArgumentParser(description="实时人机合作文字厨房")
    parser.add_argument("--config", help="自定义配置 JSON 路径")
    parser.add_argument("--check", action="store_true", help="只进行一次真实 Jev 调用验证")
    parser.add_argument("--start", action="store_true", help="跳过开局回车")
    parser.add_argument("--seconds", type=float, help="调试：运行指定秒数后退出")
    args = parser.parse_args()
    try:
        play(args)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"无法启动：{exc}", file=sys.stderr)
        sys.exit(1)
    except (EOFError, KeyboardInterrupt):
        print("\n尚未开局，已退出。")


if __name__ == "__main__":
    main()
