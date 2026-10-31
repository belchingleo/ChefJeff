#!/usr/bin/env python3
"""Build a deterministic, allowlisted private-console archive without runtime data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.audit_release import markers

FILES=('admin_server.py','admin_data.py','source_observer.py','authority_runner.py',
       'app.js','dashboard.js','charts.js','app.css','index.html','login.html',
       'chefjeff-pixel.woff2','OFL.txt','install_admin.py','upgrade_admin.py')


def package(root=ROOT,output=None):
    root=Path(root)
    output=Path(output or root/'dist/chefjeff-admin-v2.zip')
    files={}
    sources={name:root/'ops/research_admin'/name for name in FILES}
    sources['README.md']=root/'docs/research-admin.md'
    for name,path in sources.items():
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p!=root and root in p.parents):
            raise ValueError('Refusing a linked package source: '+name)
        raw=path.read_bytes()
        if markers(raw):raise ValueError('Sensitive marker in package source: '+name)
        files[name]=raw
    hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}
    bundle_id=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()[:16]
    manifest={'format':'chefjeff-private-admin-v2','bundle_id':bundle_id,'files':hashes,
              'target':'Shanghai registered game host only','production_data_included':False}
    files['manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent,suffix='.zip',delete=False) as f:temporary=Path(f.name)
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,raw in sorted(files.items()):
                info=zipfile.ZipInfo('chefjeff-admin-v2/'+name,date_time=(2026,10,31,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                archive.writestr(info,raw)
        temporary.replace(output)
    finally:temporary.unlink(missing_ok=True)
    checksum=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(checksum+'  '+output.name+'\n')
    return output,manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    output,manifest=package(output=args.output)
    print(json.dumps({'archive':str(output),'bundle_id':manifest['bundle_id'],
                     'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'files':len(manifest['files'])+1},indent=2))
