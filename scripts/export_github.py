#!/usr/bin/env python3
"""Export a reviewed source/runtime snapshot; never copy the working Git history."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.package_web import package
from scripts.audit_release import markers
from release_info import ROOT

EXTRAS = ('tests/hosted_browser_test.cjs','.github/workflows/offline-tests.yml','scripts/export_github.py',
          'scripts/preview_map_art.py','docs/agent-integration.md',
          'scenarios/fixed_entry_001/run.py','scenarios/fixed_entry_001/scenario.json',
          'scenarios/fixed_entry_001/README.md')
IGNORE = '''# Local credentials and private runtime records
.env
.env.*
.local.json
.player-api*
.player-memory*
logs/
__pycache__/
*.pyc
*.log
*.jsonl
*.sqlite3
*.sqlite3-*
hosted-data/
.DS_Store
.tools/
dist/
# Generated Cocos working files; reviewed web runtime is intentionally included
cocos-kitchen/library/
cocos-kitchen/temp/
cocos-kitchen/local/
cocos-kitchen/profiles/
cocos-kitchen/build/web-feedback/
*.keystore
*.jks
'''

def export(root, output):
    root=Path(root);output=Path(output)
    if output.exists():raise ValueError('Output already exists; use a new review directory')
    archive,manifest=package(root)
    files={}
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():files[name.removeprefix('chefjeff-web-demo/')]=z.read(name)
    extras=list(EXTRAS)+[p.relative_to(root).as_posix() for p in sorted((root/'tests').glob('test_*.py'))]
    for name in extras:
        p=root/name
        if p.is_symlink() or not p.is_file():raise ValueError('Missing or linked export file: '+name)
        files[name]=p.read_bytes()
    files['.gitignore']=IGNORE.encode()
    findings=[]
    for name,raw in files.items():
        reasons=markers(raw)
        if any(x in raw for x in (b'/' + b'Users/',b'/' + b'home/',b'/' + b'private/var/folders/',b'/' + b'tmp/codex-remote-attachments/')):
            reasons.append('local_path')
        if Path(name).name.startswith(('.env','.player-api','.player-memory')) or name.startswith(('logs/','art-candidates/')):
            reasons.append('private_path')
        if reasons:findings.append({'path':name,'reasons':reasons})
    if findings:raise ValueError(json.dumps(findings,ensure_ascii=False))
    output.mkdir(parents=True)
    for name,raw in files.items():
        p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        if name.endswith('.command'):p.chmod(0o755)
    report={'files':len(files),'bytes':sum(map(len,files.values())),
            'history_included':False,'private_configs_logs_memories_included':False,
            'known_secret_marker_findings':[],
            'sha256':{n:hashlib.sha256(r).hexdigest() for n,r in sorted(files.items())}}
    output.with_suffix('.audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        r=export(ROOT,args.output)
        print(json.dumps({k:v for k,v in r.items() if k!='sha256'},ensure_ascii=False,indent=2))
    except (OSError,ValueError) as e:raise SystemExit(str(e))
