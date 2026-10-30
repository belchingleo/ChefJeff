#!/usr/bin/env python3
"""Create/verify a short-lived, private transfer; preserve record IDs and expiry."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import subprocess
import tempfile
import time
import zipfile

FILES = ('contributions.sqlite3', 'usage.sqlite3')
MAX_FILE = 512_000_000


def integrity(path):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Database integrity check failed')
        if path.name == 'contributions.sqlite3':
            columns = [row[1] for row in db.execute('PRAGMA table_info(records)')]
            if columns != ['id', 'deletion_hash', 'expires', 'record']:
                raise ValueError('Unexpected contribution schema')
            return {'rows': db.execute('SELECT count(*) FROM records').fetchone()[0],
                    'unexpired_rows': db.execute('SELECT count(*) FROM records WHERE expires>?', (time.time(),)).fetchone()[0]}
        required = {'totals', 'levels', 'durations'}
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= tables or db.execute('SELECT count(*) FROM totals').fetchone()[0] != 1:
            raise ValueError('Unexpected usage schema')
        return {'totals_rows': 1}


def export_transfer(source, output):
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError('Transfer output already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='chefjeff-transfer-') as temporary:
        stage = Path(temporary)
        manifest = {'purpose': 'one-time-migration', 'created_at': time.time(), 'valid_until': time.time()+3600, 'files': {}}
        for name in FILES:
            original, destination = source/name, stage/name
            if original.is_symlink() or not original.is_file() or original.stat().st_size > MAX_FILE:
                raise ValueError('Missing or invalid source database')
            with closing(sqlite3.connect(original.resolve().as_uri()+'?mode=ro', uri=True)) as src:
                with closing(sqlite3.connect(destination)) as target:
                    src.backup(target)
            destination.chmod(0o600)
            manifest['files'][name] = {'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                                     'integrity': integrity(destination)}
        (stage/'transfer.json').write_text(json.dumps(manifest))
        descriptor, archive_path = tempfile.mkstemp(prefix='.chefjeff-transfer-', dir=output.parent)
        os.close(descriptor)
        try:
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name in (*FILES, 'transfer.json'):
                    archive.write(stage/name, name)
            os.link(archive_path, output)
            output.chmod(0o600)
        finally:
            Path(archive_path).unlink(missing_ok=True)
    return manifest


def import_transfer(archive_path, destination):
    destination = Path(destination)
    if any((destination/name).exists() or (destination/name).is_symlink() for name in FILES):
        raise ValueError('Destination already contains a database; inspect before continuing')
    destination.mkdir(parents=True, mode=0o700, exist_ok=True)
    destination.chmod(0o700)
    created = []
    with tempfile.TemporaryDirectory(prefix='.import-', dir=destination) as temporary:
        stage = Path(temporary)
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if (len(members) != 3 or {item.filename for item in members} != {*FILES, 'transfer.json'}
                    or any(item.file_size > MAX_FILE or item.is_dir() for item in members)):
                raise ValueError('Invalid migration archive')
            if archive.getinfo('transfer.json').file_size > 16384:
                raise ValueError('Invalid migration manifest')
            manifest = json.loads(archive.read('transfer.json'))
            now = time.time()
            if (manifest.get('purpose') != 'one-time-migration' or set(manifest.get('files', {})) != set(FILES)
                    or not now-3600 <= manifest['created_at'] <= now+60
                    or not now < manifest['valid_until'] <= manifest['created_at']+3601):
                raise ValueError('Migration transfer expired or invalid')
            for name in FILES:
                p = stage/name
                with archive.open(name) as incoming, p.open('xb') as output:
                    p.chmod(0o600);shutil.copyfileobj(incoming, output)
                if hashlib.sha256(p.read_bytes()).hexdigest() != manifest['files'][name]['sha256']:
                    raise ValueError('Transfer checksum differs')
                integrity(p)
        try:
            for name in FILES:
                (stage/name).replace(destination/name);created.append(destination/name)
            receipt = destination/'migration-receipt.json'
            with receipt.open('x') as output:
                receipt.chmod(0o600);json.dump(manifest, output)
        except BaseException:
            for p in created:p.unlink(missing_ok=True)
            raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    export = sub.add_parser('export')
    export.add_argument('--source-dir', type=Path, default=Path('/var/lib/chefjeff'))
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--owner', help='Local SSH account allowed to transfer this private file')
    importer = sub.add_parser('import')
    importer.add_argument('--archive', type=Path, required=True)
    importer.add_argument('--destination', type=Path, default=Path('/var/lib/chefjeff-data'))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run on the deployment server as root')
    service = 'chefjeff.service' if args.operation == 'export' else 'chefjeff-data.service'
    if subprocess.run(['systemctl', 'is-active', '--quiet', service]).returncode == 0:
        parser.error('Stop '+service+' before the final data transfer')
    if args.operation == 'export':
        manifest = export_transfer(args.source_dir, args.output)
        if args.owner:
            account = pwd.getpwnam(args.owner);os.chown(args.output, account.pw_uid, account.pw_gid)
    else:
        manifest = import_transfer(args.archive, args.destination)
        account = pwd.getpwnam('chefjeff')
        os.chown(args.destination, account.pw_uid, account.pw_gid)
        for name in (*FILES, 'migration-receipt.json'):
            os.chown(args.destination/name, account.pw_uid, account.pw_gid)
    print(json.dumps({'verified_files': manifest['files'], 'valid_until': manifest['valid_until']}, indent=2))


if __name__ == '__main__':
    main()
