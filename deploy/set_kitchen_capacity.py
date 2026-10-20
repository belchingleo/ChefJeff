#!/usr/bin/env python3
"""Explicitly change the existing pilot's active slots (and optionally waiting pages); restore its drop-in on failure."""
import argparse
import http.client
import json
import os
from pathlib import Path
import subprocess
import time

DOMAIN = 'chefjeff.belchingleo.online'
DROPIN = Path('/etc/systemd/system/chefjeff.service.d/zz-chefjeff-capacity.conf')


def run(*args):
    subprocess.run(args, check=True)


def read_metrics():
    c = http.client.HTTPConnection('127.0.0.1',8780,timeout=3)
    try:
        c.request('GET','/ops/capacity',headers={'Host':DOMAIN})
        response = c.getresponse()
        if response.status != 200:
            raise RuntimeError('Deploy the reviewed capacity runtime before changing its limit.')
        return json.loads(response.read())
    finally:
        c.close()


def apply(capacity, dropin=DROPIN, waiting=None):
    if type(capacity) is not int or capacity not in (2,4,8,12,16):
        raise ValueError('Choose 2, 4, 8, 12 or 16 active kitchens.')
    if waiting is not None and (type(waiting) is not int or not 0 <= waiting <= 32):
        raise ValueError('Choose 0–32 waiting pages.')
    before = read_metrics()['capacity']
    current = before['session_limit']-before['limit']
    if not 0 <= current <= 32:
        raise RuntimeError('Unexpected page-session configuration; nothing changed.')
    waiting = current if waiting is None else waiting
    if before['limit'] == capacity and current == waiting:
        print('Active kitchen limit is already '+str(capacity)+' with '+str(waiting)+' waiting pages. No restart needed.')
        return
    unit = subprocess.check_output(['systemctl','show','chefjeff.service','--property=ExecStart','--value'],text=True)
    for expected in ('/usr/bin/python3','/opt/chefjeff/current/hosted_server.py',
                     '--port 8780','--origin https://'+DOMAIN,'--data-dir /var/lib/chefjeff'):
        if expected not in unit:
            raise RuntimeError('Unexpected pilot service command; nothing changed.')
    if dropin.is_symlink():
        raise RuntimeError('Capacity drop-in must be a regular file.')
    previous = dropin.read_bytes() if dropin.exists() else None
    dropin.parent.mkdir(parents=True,exist_ok=True)
    body = ('[Service]\nExecStart=\nExecStart=/usr/bin/python3 /opt/chefjeff/current/hosted_server.py'
            ' --port 8780 --origin https://'+DOMAIN+' --max-sessions '+str(capacity)+
            ' --max-waiting '+str(waiting)+' --data-dir /var/lib/chefjeff\n')
    print('Restarting ChefJeff ends current trial rounds. Memory, data and VPN settings remain in place.',flush=True)
    try:
        dropin.write_text(body)
        dropin.chmod(0o644)
        run('systemctl','daemon-reload')
        run('systemctl','restart','chefjeff.service')
        for _ in range(30):
            try:
                after = read_metrics()['capacity']
                if after['limit'] == capacity and after['session_limit'] == capacity+waiting:
                    print('Verified active kitchen limit: '+str(capacity)+'; waiting pages: '+str(waiting))
                    return
            except (OSError,ValueError,RuntimeError):
                pass
            time.sleep(.2)
        raise RuntimeError('Running capacity does not match the requested limit.')
    except BaseException:
        if previous is None:dropin.unlink(missing_ok=True)
        else:dropin.write_bytes(previous)
        run('systemctl','daemon-reload')
        run('systemctl','restart','chefjeff.service')
        print('Capacity change failed; the previous drop-in was restored.',flush=True)
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capacity',type=int,choices=(2,4,8,12,16))
    p.add_argument('--waiting',type=int,choices=range(0,33),metavar='0-32',help='Waiting page sessions beyond the active kitchens (default: keep the current number).')
    args = p.parse_args()
    if os.geteuid()!=0:p.error('Run inside the server SSH terminal as root (sudo -i).')
    current=Path('/opt/chefjeff/current')
    if not current.is_symlink() or not current.resolve(strict=True).is_relative_to('/opt/chefjeff/releases'):
        p.error('An existing reviewed release is required.')
    run('systemctl','is-active','--quiet','chefjeff.service')
    apply(args.capacity, waiting=args.waiting)


if __name__=='__main__':main()
