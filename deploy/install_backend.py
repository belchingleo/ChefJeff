#!/usr/bin/env python3
"""Install this reviewed release as a loopback-only service. No public firewall/DNS/TLS changes."""
import os
from pathlib import Path
import pwd
import shutil
import subprocess

release=Path(__file__).resolve().parents[1]
if os.geteuid()!=0: raise SystemExit('Run as root on the deployment server.')
if not str(release).startswith('/opt/chefjeff/releases/'): raise SystemExit('Extract a reviewed release under /opt/chefjeff/releases first.')
try: pwd.getpwnam('chefjeff')
except KeyError:
    subprocess.run(['useradd','--system','--no-create-home','--shell','/usr/sbin/nologin','chefjeff'],check=True)
account=pwd.getpwnam('chefjeff')
data=Path('/var/lib/chefjeff');data.mkdir(mode=0o700,exist_ok=True);data.chmod(0o700)
os.chown(data,account.pw_uid,account.pw_gid)
# Keep release files immutable to the service user.
for item in [release,*release.rglob('*')]:
    if item.is_symlink():raise SystemExit('Symlink in release rejected.')
    os.chown(item,0,0);item.chmod(0o755 if item.is_dir() else 0o644)
current=Path('/opt/chefjeff/current')
if current.exists() and not current.is_symlink():raise SystemExit('Existing non-symlink installation; inspect before replacing.')
next_link=current.with_name('next')
if next_link.exists() or next_link.is_symlink():raise SystemExit('Pending deployment found; inspect before continuing.')
next_link.symlink_to(release);next_link.replace(current)
shutil.copyfile(release/'deploy/chefjeff.service','/etc/systemd/system/chefjeff.service')
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','chefjeff.service'],check=True)
subprocess.run(['systemctl','restart','chefjeff.service'],check=True)
print('Backend installed on loopback only; DNS/firewall/public HTTPS unchanged.')
