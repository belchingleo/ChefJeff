#!/usr/bin/env python3
"""Web kitchen client and authoritative game API on one local origin.
"""
import argparse
import mimetypes
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, unquote
from kitchen import ROOT
from spatial_kitchen import SpatialKitchen
from web_server import Handler
from player_api import PlayerGameSession


class CocosHandler(Handler):
    web_root = ROOT / 'cocos-kitchen' / 'build' / 'web'

    def do_GET(self):
        if not self.local_request():
            return self.reply(403, {'error':'仅允许本机或 USB 转发访问。'})
        path=unquote(urlparse(self.path).path)
        if path=='/api/state':
            return self.reply(200,self.server.game.public_state())
        root=self.web_root.resolve()
        file=(root/path.lstrip('/')).resolve()
        if file==root:file=root/'index.html'
        if not file.is_relative_to(root) or not file.is_file():
            return self.reply(404,{'error':'请先构建 Cocos Web 预览，或检查路径。'})
        raw=file.read_bytes()
        self.send_response(200)
        mime=mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        # Creator's local debug engine/polyfills use Function() and inline SystemJS bootstrap.
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; frame-ancestors 'none'")
        self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass


def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8769);p.add_argument('--open',action='store_true');args=p.parse_args()
    session=PlayerGameSession(kitchen_factory=SpatialKitchen,log_prefix='cocos')
    try:server=ThreadingHTTPServer(('127.0.0.1',args.port),CocosHandler)
    except OSError as exc:
        session.close()
        raise SystemExit(f'启动失败：{exc}。若厨房已启动，请打开 http://127.0.0.1:{args.port}/；也可用 --port 指定其他端口。')
    server.game=session
    threading.Thread(target=session.run,daemon=True).start()
    print(f'网页版厨房已就绪：http://127.0.0.1:{args.port}/，请先在 API 设置中连接玩家自己的账号；测试连接和开局会调用所选模型。',flush=True)
    if args.open:webbrowser.open(f'http://127.0.0.1:{args.port}/')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:session.close();server.server_close()

if __name__=='__main__':main()
