#!/usr/bin/env python3
"""Update the existing pilot from a pinned, locally verified package; roll back on failure."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile

DOMAIN = 'chefjeff.belchingleo.online'


def run(*args):
    subprocess.run(args, check=True)


def health():
    for _ in range(30):
        connection = http.client.HTTPConnection('127.0.0.1', 8780, timeout=2)
        try:
            connection.request('GET', '/healthz', headers={'Host':DOMAIN})
            response = connection.getresponse()
            if response.status == 200 and json.loads(response.read()).get('ok') is True:
                return
        except (OSError, ValueError):
            pass
        finally:
            connection.close()
        time.sleep(.2)
    raise RuntimeError('Backend health check failed.')


def switch_link(current, target):
    pending = current.with_name('next')
    if pending.exists() or pending.is_symlink():
        raise RuntimeError('Pending deployment exists; inspect it before retrying.')
    pending.symlink_to(target)
    pending.replace(current)


def install(release, current, site):
    previous = current.resolve(strict=True)
    previous_config = site.read_bytes()
    switched = False
    try:
        site.write_bytes((release / 'deploy/nginx-https.conf').read_bytes())
        run('nginx', '-t')
        switch_link(current, release)
        switched = True
        # Existing unit, two-room/memory drop-in, data and VPN configuration stay in place.
        run('systemctl', 'restart', 'chefjeff.service')
        health()
        run('systemctl', 'reload', 'nginx')
    except BaseException:
        site.write_bytes(previous_config)
        if switched:
            switch_link(current, previous)
            run('systemctl', 'restart', 'chefjeff.service')
        run('nginx', '-t')
        run('systemctl', 'reload', 'nginx')
        print('Update failed; previous release and Nginx configuration restored.', flush=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('commit', help='Full reviewed Git commit ID')
    parser.add_argument('package_sha256', help='SHA-256 of the package tested before deployment')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run inside the server SSH terminal as root (sudo -i).')
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit) or not re.fullmatch(r'[0-9a-f]{64}', args.package_sha256):
        parser.error('A full commit ID and package checksum are required.')
    current = Path('/opt/chefjeff/current')
    site = Path('/etc/nginx/sites-available/chefjeff')
    if not current.is_symlink() or not current.resolve(strict=True).is_relative_to('/opt/chefjeff/releases'):
        parser.error('Existing reviewed release symlink is required.')
    if not site.is_file() or site.is_symlink():
        parser.error('Expected a regular ChefJeff Nginx site configuration.')
    run('systemctl', 'is-active', '--quiet', 'chefjeff.service')
    run('nginx', '-t')
    with tempfile.TemporaryDirectory(prefix='chefjeff-update-') as temporary:
        directory = Path(temporary)
        source_zip = directory / 'source.zip'
        url = f'https://codeload.github.com/belchingleo/ChefJeff/zip/{args.commit}'
        print('Downloading pinned source ' + args.commit, flush=True)
        with urllib.request.urlopen(url, timeout=60) as response, source_zip.open('wb') as output:
            shutil.copyfileobj(response, output)
        with zipfile.ZipFile(source_zip) as archive:
            archive.extractall(directory / 'source')
        source = directory / 'source' / ('ChefJeff-' + args.commit)
        package = directory / 'runtime.zip'
        run('python3', str(source / 'scripts/package_web.py'), '--output', str(package))
        if hashlib.sha256(package.read_bytes()).hexdigest() != args.package_sha256:
            raise RuntimeError('Package checksum differs from the tested build; nothing installed.')
        release_parent = Path('/opt/chefjeff/releases') / ('verified-' + args.commit[:12])
        if release_parent.exists():
            raise RuntimeError('Release directory already exists; inspect before retrying.')
        release_parent.mkdir(mode=0o755)
        with zipfile.ZipFile(package) as archive:
            archive.extractall(release_parent)
        release = release_parent / 'chefjeff-web-demo'
        for item in [release, *release.rglob('*')]:
            if item.is_symlink():
                raise RuntimeError('Symlink in release rejected.')
            item.chmod(0o755 if item.is_dir() else 0o644)
        print('Package verified. Restarting ChefJeff ends current trial rounds.', flush=True)
        install(release, current, site)
        print('Updated ' + args.commit + '. Open https://' + DOMAIN + '/', flush=True)


if __name__ == '__main__':
    main()
