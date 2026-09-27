#!/usr/bin/env python3
"""Build an allowlisted runtime zip, independent of the Git staging area."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from release_info import ROOT, RUNTIME_FILES, release_info
from scripts.audit_release import markers

PUBLIC_FILES = ('hosted_server.py','hosted_records.py','hosted/browser-agent.js','hosted/contribution.html',
                'deploy/chefjeff.service','deploy/nginx-http.conf','deploy/nginx-https.conf','deploy/install_backend.py','docs/hosted-deployment.md','docs/device-support.md','docs/ui-design.md','docs/api-integration.md','docs/images/gameplay.png','README.md','LICENSE','LICENSE-STATUS.md','THIRD_PARTY_NOTICES.md','SECURITY.md','CONTRIBUTING.md',
                'start-web.command','start-web.bat','stop-web.command',
                'docs/map-format.md','docs/current-rules.md','docs/interaction-guide.md','docs/level-1-steak.md','docs/level-2-burger.md','docs/level-3-steak-burger.md','docs/status.md','docs/privacy-and-costs.md','docs/agent-integration.md',
                'cocos-kitchen/THIRD_PARTY_LICENSE.md','docs/art/integration.md',
                'scripts/build_cocos.py','scripts/package_web.py','scripts/audit_release.py',
                'cocos-kitchen/web-shell.html','cocos-kitchen/i18n.js','cocos-kitchen/i18n.json','cocos-kitchen/favicon.ico','cocos-kitchen/fonts/chefjeff-pixel.woff2','cocos-kitchen/fonts/OFL.txt','scripts/subset_pixel_font.py','cocos-kitchen/package.json','cocos-kitchen/build-web.json',
                'cocos-kitchen/tsconfig.json','cocos-kitchen/assets/scenes.meta','cocos-kitchen/assets/scripts.meta',
                'cocos-kitchen/assets/scripts/KitchenClient.ts','cocos-kitchen/assets/scripts/KitchenClient.ts.meta',
                'cocos-kitchen/assets/scripts/LevelOneArt.ts','cocos-kitchen/assets/scripts/LevelOneArt.ts.meta',
                'cocos-kitchen/assets/scripts/KitchenGeometry.ts','cocos-kitchen/assets/scripts/KitchenGeometry.ts.meta',
                'cocos-kitchen/assets/scenes/Kitchen.scene','cocos-kitchen/assets/scenes/Kitchen.scene.meta',
                'cocos-kitchen/settings/v2/packages/project.json','cocos-kitchen/settings/v2/packages/builder.json',
                'cocos-kitchen/settings/v2/packages/engine.json','cocos-kitchen/settings/v2/packages/device.json')


def package(root=ROOT, output=None):
    root=Path(root);output=Path(output or root/'dist/chefjeff-web-demo.zip')
    web=root/'cocos-kitchen/build/web'
    names=set(RUNTIME_FILES+PUBLIC_FILES)
    if (root/'LICENSE').is_file():names.add('LICENSE')
    if not (web/'index.html').is_file():raise ValueError('缺少网页构建：先运行 python3 scripts/build_cocos.py web')
    names.update(p.relative_to(root).as_posix() for p in web.rglob('*') if p.is_file())
    art=root/'cocos-kitchen/assets/resources'
    names.update(p.relative_to(root).as_posix() for p in art.rglob('*') if p.is_file() and p.suffix in ('.png','.json','.meta'))
    if art.with_suffix('.meta').is_file():names.add(art.with_suffix('.meta').relative_to(root).as_posix())
    files={}
    for name in sorted(names):
        p=root/name
        if any(part.startswith('.') for part in Path(name).parts) or p.suffix in ('.map','.log'):
            raise ValueError('构建含不允许分发的文件类型，请先检查构建输出。')
        if any(parent.is_symlink() for parent in [p,*p.parents] if parent!=root and root in parent.parents):
            raise ValueError('拒绝打包符号链接。')
        if not p.is_file():raise ValueError('缺少分发必需文件：'+name)
        raw=p.read_bytes()
        if ('/'+ 'Users/').encode() in raw or ('/'+ 'home/').encode() in raw or markers(raw):
            raise ValueError('分发文件含本机路径或敏感标记，请检查：'+name)
        files[name]=raw
    manifest={'schema_version':1,'release':release_info(root),
              'license_status':'see LICENSE' if 'LICENSE' in files else 'undecided; local review package only',
              'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()},
              'contents':'Runtime and matching project source. Rebuild using Cocos Creator 3.8.8 and scripts/build_cocos.py.'}
    files['release-manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    # Publish the complete zip atomically; a failed check never damages an older package.
    with tempfile.NamedTemporaryFile(dir=output.parent,suffix='.zip',delete=False) as tmp:temp=Path(tmp.name)
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,raw in files.items():
                info=zipfile.ZipInfo('chefjeff-web-demo/'+name,date_time=(2026,9,25,0,0,0))
                info.external_attr=(0o100755 if name.endswith('.command') else 0o100644)<<16
                info.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(info,raw)
        temp.replace(output)
    finally:temp.unlink(missing_ok=True)
    checksum=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(checksum+'  '+output.name+'\n')
    return output,manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        output,manifest=package(output=args.output)
        print(f'{output}\nVersion: {manifest["release"]["version"]}\nFiles: {len(manifest["files"])}\nBytes: {output.stat().st_size}')
    except (OSError,ValueError) as exc:raise SystemExit(str(exc))
