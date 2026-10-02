#!/usr/bin/env python3
"""Build with the installed Creator. Android make requires a configured toolchain."""
import argparse
from pathlib import Path
import shutil
import subprocess
import os
import json
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('platform',choices=['web','android']);p.add_argument('--make',action='store_true');p.add_argument('--preview',action='store_true',help='Build Web into web-feedback without replacing the live web directory');args=p.parse_args()
if args.preview and args.platform!='web':p.error('--preview is available only for web')
creator=Path(os.environ.get('COCOS_CREATOR','/Applications/CocosCreator.app/Contents/MacOS/CocosCreator'))
if not creator.is_file():sys.exit('未找到 Cocos Creator；通过 COCOS_CREATOR 指定可执行文件。')
if args.platform=='android':
    local=ROOT/'.tools/android-env.json'
    if local.is_file():
        for key,value in json.loads(local.read_text()).items():
            os.environ.setdefault(key,value)
    missing=[name for name in ('ANDROID_SDK_ROOT','NDK_ROOT','JAVA_HOME') if not Path(os.environ.get(name,'/not-configured')).is_dir()]
    if missing:sys.exit('Android 构建环境未配置：'+', '.join(missing)+'。请参考 安卓Demo方案.md。')
config=ROOT/'cocos-kitchen'/f'build-{args.platform}.json'
with tempfile.TemporaryDirectory(prefix='chefjeff-build-') as temporary:
    build_config=config
    if args.preview:
        data=json.loads(config.read_text());data['outputName']='web-feedback'
        build_config=Path(temporary)/'build.json';build_config.write_text(json.dumps(data))
    result=subprocess.run([str(creator),'--project',str(config.parent),'--build',f'configPath={build_config};stage={"make" if args.make else "build"}'])
if result.returncode==36 and args.platform=='web':
    page=ROOT/'cocos-kitchen/build'/('web-feedback' if args.preview else 'web')/'index.html'
    content=page.read_text()
    shell=(ROOT/'cocos-kitchen/web-shell.html').read_text()
    catalog=(ROOT/'cocos-kitchen/i18n.json').read_text()
    (page.parent/'kitchen-i18n.js').write_text((ROOT/'cocos-kitchen/i18n.js').read_text().replace('__KITCHEN_CATALOG__',catalog))
    content=content.replace('<title>Cocos Creator | JevKitchen</title>','<title>ChefJeff · 一起出餐</title>')
    # Creator's template targets portrait phones and blocks zoom; this is a landscape game
    # whose text must stay zoomable (WCAG 1.4.4).
    content=content.replace('width=device-width,user-scalable=no,initial-scale=1,minimum-scale=1,maximum-scale=1,minimal-ui=true','width=device-width,initial-scale=1')
    content=content.replace('<meta name="screen-orientation" content="portrait"/>','<meta name="screen-orientation" content="landscape"/>')
    # Pixel pot icon and the subset pixel face (SIL OFL 1.1) ship beside the page.
    shutil.copyfile(ROOT/'cocos-kitchen/favicon.ico',page.parent/'favicon.ico')
    (page.parent/'fonts').mkdir(exist_ok=True)
    for name in ('chefjeff-pixel.woff2','OFL.txt'):shutil.copyfile(ROOT/'cocos-kitchen/fonts'/name,page.parent/'fonts'/name)
    page.write_text(content.replace('</body>',shell+'</body>'))
    # Desktop exports default to a fixed subframe. Track the browser viewport so
    # SHOW_ALL can letterbox correctly after resizing instead of stretching CSS.
    settings_path=page.parent/'src/settings.json'
    settings=json.loads(settings_path.read_text())
    settings['screen']['exactFitScreen']=True
    settings_path.write_text(json.dumps(settings,ensure_ascii=False,indent=2)+'\n')
sys.exit(0 if result.returncode==36 else result.returncode or 0)
