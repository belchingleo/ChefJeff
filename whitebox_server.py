#!/usr/bin/env python3
"""Local spatial whitebox; shares rules, API protections and real Jev scheduling."""
import argparse
from http.server import ThreadingHTTPServer
import threading
import webbrowser
from kitchen import ROOT
from spatial_kitchen import SpatialKitchen
from web_server import GameSession, Handler
from jev import JevClient
# Candidate pruning moved to harness.py; the name stays importable from here.
from harness import model_candidates  # noqa: F401


class SpatialJevClient(JevClient):
    """Jev client for the spatial kitchen: harness.payload adds its rules, pruning and sprint question."""
    spatial = True


class WhiteboxHandler(Handler):
    web_root = ROOT/'whitebox'


def main():
    parser = argparse.ArgumentParser(description='打开可走动的厨房白模')
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    game = GameSession(kitchen_factory=SpatialKitchen, client_factory=SpatialJevClient, log_prefix='whitebox')
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), WhiteboxHandler)
    except OSError as e:
        raise SystemExit(f'白模启动失败：{e}')
    server.game = game
    threading.Thread(target=game.run, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'厨房白模已就绪：{url}\n点击「开始做菜」才会计时和调用真实 Jev。Ctrl+C 关闭。', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        game.close()
        server.server_close()


if __name__ == '__main__':
    main()
