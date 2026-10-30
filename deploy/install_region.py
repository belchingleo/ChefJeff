#!/usr/bin/env python3
"""Install a verified regional backend on loopback, retaining rollback on failure."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy.render_region import domain_name, game_unit
from shared_client import SharedClient
from shared_server import read_private_json


def verify_release(release):
    manifest = json.loads((release/'release-manifest.json').read_text())
    for name, checksum in manifest['files'].items():
        path = release/name
        if (not path.resolve().is_relative_to(release) or path.is_symlink() or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != checksum):
            raise ValueError('Release manifest verification failed')


def run(*args):
    subprocess.run(args, check=True)


def preserve_limits(unit_text, previous_command):
    for flag, lower, upper in [('max-sessions', 1, 16), ('max-waiting', 0, 32), ('max-per-network', 1, 16)]:
        found = re.search(r'--'+flag+r'\s+(\d+)\b', previous_command)
        if not found:
            continue
        value = int(found[1])
        if not lower <= value <= upper:
            raise ValueError('Unexpected existing capacity')
        option = '--'+flag+' '+str(value)
        if '--'+flag+' ' in unit_text:
            unit_text = re.sub(r'--'+flag+r'\s+\d+', option, unit_text)
        else:
            unit_text = re.sub(r'(?m)^(ExecStart=.+)$', lambda m: m[1]+' '+option, unit_text)
    return unit_text


def health(domain):
    for _ in range(30):
        connection = http.client.HTTPConnection('127.0.0.1', 8780, timeout=2)
        try:
            connection.request('GET', '/healthz', headers={'Host': domain})
            response = connection.getresponse()
            if response.status == 200 and json.loads(response.read()).get('ok') is True:
                return
        except (OSError, ValueError):
            pass
        finally:
            connection.close()
        time.sleep(.2)
    raise RuntimeError('Regional backend failed health check')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--client-config', required=True, type=Path)
    parser.add_argument('--replace-existing', action='store_true')
    args = parser.parse_args()
    domain_name(args.domain)
    if os.geteuid() != 0:
        parser.error('Run on the target server as root')
    release = Path(__file__).resolve().parents[1]
    if not release.is_relative_to('/opt/chefjeff/releases'):
        parser.error('Extract the verified package under /opt/chefjeff/releases first')
    verify_release(release)
    SharedClient(read_private_json(args.client_config))
    current = Path('/opt/chefjeff/current')
    unit = Path('/etc/systemd/system/chefjeff.service')
    installed_config = Path('/etc/chefjeff/shared-client.json')
    override = Path('/etc/systemd/system/chefjeff.service.d/zzzz-chefjeff-region.conf')
    if any(path.is_symlink() for path in (unit, installed_config, override)):
        parser.error('Deployment configuration must be regular files')
    if current.exists() and not current.is_symlink():
        parser.error('Existing installation is not a release symlink')
    if (current.is_symlink() or unit.exists()) and not args.replace_existing:
        parser.error('Existing deployment requires the explicit replace-existing option')
    previous = current.resolve(strict=True) if current.is_symlink() else None
    previous_unit = unit.read_bytes() if unit.exists() else None
    previous_config = installed_config.read_bytes() if installed_config.exists() else None
    previous_override = override.read_bytes() if override.exists() else None
    rendered_unit = game_unit(args.domain)
    if previous_unit is not None:
        existing = subprocess.check_output(['systemctl', 'show', 'chefjeff.service', '--property=ExecStart', '--value'], text=True)
        rendered_unit = preserve_limits(rendered_unit, existing)
    try:
        account = pwd.getpwnam('chefjeff')
    except KeyError:
        run('useradd', '--system', '--no-create-home', '--shell', '/usr/sbin/nologin', 'chefjeff')
        account = pwd.getpwnam('chefjeff')
    for path in [release, *release.rglob('*')]:
        if path.is_symlink():
            raise ValueError('Symlink in release rejected')
        os.chown(path, 0, 0);path.chmod(0o755 if path.is_dir() else 0o644)
    data = Path('/var/lib/chefjeff');data.mkdir(mode=0o700, exist_ok=True)
    os.chown(data, account.pw_uid, account.pw_gid);data.chmod(0o700)
    directory = installed_config.parent;directory.mkdir(mode=0o750, exist_ok=True)
    os.chown(directory, 0, account.pw_gid);directory.chmod(0o750)
    pending = current.with_name('next')
    if pending.exists() or pending.is_symlink():
        raise RuntimeError('Pending deployment exists; inspect before continuing')
    try:
        if args.client_config.resolve() != installed_config.resolve():
            shutil.copyfile(args.client_config, installed_config)
        os.chown(installed_config, 0, account.pw_gid);installed_config.chmod(0o640)
        unit.write_text(rendered_unit)
        override.parent.mkdir(parents=True, exist_ok=True)
        command = next(line for line in rendered_unit.splitlines() if line.startswith('ExecStart='))
        override.write_text('[Service]\nExecStart=\n'+command+'\n')
        pending.symlink_to(release);pending.replace(current)
        run('systemctl', 'daemon-reload')
        print('Restarting the game backend ends active rounds.', flush=True)
        run('systemctl', 'restart', 'chefjeff.service')
        health(args.domain)
        effective = subprocess.check_output(['systemctl', 'show', 'chefjeff.service', '--property=ExecStart', '--value'], text=True)
        if '--origin https://'+args.domain not in effective or '--shared-config /etc/chefjeff/shared-client.json' not in effective:
            raise RuntimeError('Another service override replaced the regional command')
        run('systemctl', 'enable', 'chefjeff.service')
    except BaseException:
        run('systemctl', 'stop', 'chefjeff.service')
        if pending.is_symlink():
            pending.unlink()
        if previous:
            pending.symlink_to(previous);pending.replace(current)
        else:
            current.unlink(missing_ok=True)
        if previous_unit is not None: unit.write_bytes(previous_unit)
        else: unit.unlink(missing_ok=True)
        if previous_config is not None: installed_config.write_bytes(previous_config)
        else: installed_config.unlink(missing_ok=True)
        if previous_override is not None: override.write_bytes(previous_override)
        else: override.unlink(missing_ok=True)
        run('systemctl', 'daemon-reload')
        if previous_unit is not None: run('systemctl', 'restart', 'chefjeff.service')
        raise
    print('Regional backend verified on loopback. Configure/test the shared data service and HTTPS before DNS cutover.')


if __name__ == '__main__':
    main()
