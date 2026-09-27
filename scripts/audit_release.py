#!/usr/bin/env python3
"""Read-only sensitive-marker audit. Report locations/counts, never matched values."""
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PATTERNS={
 'private_key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'provider_key':re.compile(rb'(?<![\w-])(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})(?![\w-])'),
}
PRIVATE={'.env','.local.json','.player-api.json','.player-memory.json'}

def markers(raw):
 return [name for name,pattern in PATTERNS.items() if pattern.search(raw)]

def audit(root=ROOT):
 def git(*args):return subprocess.check_output(['git',*args],cwd=root)
 findings=[];checked=0
 for name in git('ls-files','-z').decode().split('\0'):
  if not name:continue
  p=root/name
  if Path(name).name in PRIVATE or name.startswith(('logs/','.tools/')):
   findings.append({'scope':'tracked_path','path':name,'reason':'private_path'})
  if p.is_file() and not p.is_symlink():
   checked+=1
   for match in markers(p.read_bytes()):findings.append({'scope':'working_tree','path':name,'reason':match})
 # Inspect reachable historical blobs without printing their contents.
 objects=git('rev-list','--objects','--all').decode().splitlines();history=0
 for row in objects:
  oid,_,name=row.partition(' ')
  if not name:continue
  if git('cat-file','-t',oid).strip()!=b'blob':continue
  history+=1
  if Path(name).name in PRIVATE or name.startswith(('logs/','.tools/')):
   findings.append({'scope':'history_path','path':name,'object':oid[:12],'reason':'private_path'})
  for match in markers(git('cat-file','blob',oid)):
   findings.append({'scope':'history_blob','path':name,'object':oid[:12],'reason':match})
 return {'tracked_files_checked':checked,'historical_blobs_checked':history,'findings':findings,
         'limitations':'Pattern-based local reachable Git history audit, not a guarantee or a check of remote forks/untracked private files.'}

if __name__=='__main__':
 result=audit();print(json.dumps(result,ensure_ascii=False,indent=2))
 raise SystemExit(1 if result['findings'] else 0)
