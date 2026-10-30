#!/usr/bin/env python3
"""Authenticated backend-only data service; bind loopback behind a TLS proxy."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import signal
import sqlite3
import stat
import threading

from shared_data import Gone, SharedRecords, SharedUsage, encode

MAX_BODY = 14_000_000


def read_private_json(path):
    path = Path(path)
    mode = path.stat().st_mode
    if path.is_symlink() or not stat.S_ISREG(mode) or mode & 0o027:
        raise ValueError('Configuration must be a private regular file')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Invalid configuration')
    return value


class DataServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, port, directory, sites):
        if (not isinstance(sites, dict) or not 1 <= len(sites) <= 4
                or any(not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', site) for site in sites)
                or any(not isinstance(t, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', t) for t in sites.values())
                or len(set(sites.values())) != len(sites)):
            raise ValueError('Use distinct private tokens for the configured sites')
        self.sites = sites
        self.records = SharedRecords(directory)
        self.usage = SharedUsage(directory)
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(('127.0.0.1', port), DataHandler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        # Never log request bodies, tokens, receipt values or tracebacks containing them.
        pass


class DataHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def reply(self, status, value):
        raw = encode(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except OSError:
            pass

    def do_GET(self):
        self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        site = self.headers.get('X-ChefJeff-Site', '')
        expected = self.server.sites.get(site)
        actual = self.headers.get('Authorization', '')
        if (not expected or not hmac.compare_digest(actual.encode(), ('Bearer '+expected).encode())
                or self.headers.get('Origin') or self.headers.get('Cookie')):
            return self.reply(401, {'error': 'Unauthorized'})
        try:
            if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
                raise ValueError('Invalid request')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError('Invalid size')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Invalid request')
            records = self.server.records
            if self.path == '/v1/health' and not body:
                return self.reply(200, {'ok': True})
            if self.path == '/v1/records/save' and set(body) == {'request_id', 'created_at', 'deletion_token', 'record'}:
                value = records.create(body['request_id'], body['deletion_token'], body['created_at'], body['record'])
            elif self.path == '/v1/records/update' and set(body) == {'id', 'record'}:
                if not isinstance(body['id'], str) or not 1 <= len(body['id']) <= 100 or not isinstance(body['record'], dict):
                    raise ValueError('Invalid update')
                value = records.update(body['id'], body['record'])
            elif self.path == '/v1/records/delete' and set(body) == {'id', 'deletion_token'}:
                value = records.delete(body['id'], body['deletion_token'])
            elif self.path == '/v1/records/download' and set(body) == {'id', 'deletion_token'}:
                value = records.download(body['id'], body['deletion_token'])
            elif self.path == '/v1/usage/push' and set(body) == {'stream', 'aggregate', 'running'}:
                value = self.server.usage.apply(site, body['stream'], body['aggregate'], body['running'])
            elif self.path == '/v1/usage/read' and not body:
                value = self.server.usage.snapshot()
            else:
                return self.reply(404, {'error': 'Unknown operation'})
            return self.reply(200, {'value': value})
        except Gone:
            return self.reply(410, {'error': 'Record withdrawn or expired'})
        except (ValueError, TypeError, KeyError, OverflowError):
            return self.reply(400, {'error': 'Invalid data request'})
        except (OSError, sqlite3.Error):
            return self.reply(503, {'error': 'Data storage unavailable'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8790)
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--credentials', required=True, type=Path)
    args = parser.parse_args()
    credentials = read_private_json(args.credentials)
    if set(credentials) != {'sites'}:
        parser.error('Expected a private sites configuration')
    server = DataServer(args.port, args.data_dir, credentials['sites'])
    stopped = threading.Event()
    def shutdown(*_):
        stopped.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    def prune():
        while not stopped.wait(30):
            try:
                server.records.prune()
            except (OSError, sqlite3.Error):
                pass
    threading.Thread(target=prune, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        server.server_close()


if __name__ == '__main__':
    main()
