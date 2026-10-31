#!/usr/bin/env python3
"""Stage hash-pinned public files as root, without switching or restarting anything."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

BASE_MANIFEST_SHA='4fbf74567484dc6fc49c23ab6cbcf42fe43db1fa024f08958fece713b4c409c7'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_source(source, expected):
    manifest_file=source/'release-manifest.json'
    if sha(manifest_file)!=expected:raise ValueError('Release manifest differs from the fixed build')
    manifest=json.loads(manifest_file.read_text());files=manifest['files']
    if not isinstance(files,dict) or not 500<=len(files)<=1000:raise ValueError('Unexpected public manifest')
    for name,checksum in files.items():
        relative=Path(name)
        if (relative.is_absolute() or any(p.startswith('.') for p in relative.parts)
                or relative.suffix.lower() in ('.db','.sqlite','.sqlite3','.pem','.key','.env')):
            raise ValueError('Only allowlisted public files may be staged')
        path=source/relative
        if path.is_symlink() or not path.resolve().is_relative_to(source) or not path.is_file() or sha(path)!=checksum:
            raise ValueError('Public release file verification failed')
    for path in source.rglob('*'):
        if path.is_symlink() or (not path.is_dir() and path.relative_to(source).as_posix() not in {*files,'release-manifest.json'}):
            raise ValueError('Unexpected extra source file')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--site',choices=('cn','de'),required=True)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--manifest-sha',required=True)
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error('Run the reviewed staging command with sudo')
    if not re.fullmatch('[0-9a-f]{40}',args.commit) or not re.fullmatch('[0-9a-f]{64}',args.manifest_sha):
        parser.error('Use a fixed commit and SHA-256')
    source=args.source.resolve(strict=True)
    current=Path('/opt/chefjeff/current')
    if not current.is_symlink() or sha(current.resolve()/'release-manifest.json')!=BASE_MANIFEST_SHA:
        raise ValueError('Current release differs from the audited v7 baseline')
    manifest=verify_source(source,args.manifest_sha)
    parent=Path('/opt/chefjeff/releases')
    outer=parent/(('china' if args.site=='cn' else 'global')+'-free-'+args.commit[:12])
    if outer.exists() or outer.is_symlink():
        if outer.is_symlink():raise ValueError('Unexpected release link')
        verify_source(outer/'chefjeff-web-demo',args.manifest_sha)
    else:
        temporary=Path(tempfile.mkdtemp(prefix='.free-stage-',dir=parent))
        try:
            target=temporary/'chefjeff-web-demo';target.mkdir(mode=0o755)
            for name in [*manifest['files'],'release-manifest.json']:
                destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
                # Verify the copied bytes too, before making the release visible.
                shutil.copyfile(source/name,destination);destination.chmod(0o644)
            for path in target.rglob('*'):
                if path.is_dir():path.chmod(0o755)
            verify_source(target,args.manifest_sha)
            temporary.chmod(0o755);temporary.rename(outer)
        finally:
            if temporary.exists():shutil.rmtree(temporary)
    print(json.dumps({'status':'free-model-code-staged','site':args.site,'commit':args.commit,
        'new_release':str(outer/'chefjeff-web-demo'),'manifest_sha256':args.manifest_sha,
        'fingerprint':manifest['release']['fingerprint'],'current_changed':False,'services_restarted':False,
        'player_databases_opened':False,'api_requests_sent':0},indent=2))


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('Staging paused: public source or target validation failed. No live services changed.') from None
