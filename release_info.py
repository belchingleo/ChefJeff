"""Public build identity; no paths, credentials or Git metadata are exposed."""
import hashlib
from pathlib import Path

VERSION = '0.5.9-alpha'
ROOT = Path(__file__).resolve().parent
RUNTIME_FILES = ('map_definition.py', 'maps/level-1.json', 'maps/level-2.json', 'maps/level-3.json', 'levels.py', 'navigation.py', 'kitchen.py', 'spatial_kitchen.py', 'jev.py', 'model_language.py', 'model-language-en-v1.json', 'web_server.py',
                 'cocos_server.py', 'player_api.py', 'cooperation_memory.py', 'play.py',
                 'whitebox_server.py', 'feedback.py', 'release_info.py', 'config.json',
                 'scripts/launch_web.py', 'scripts/stop_web.py')


def release_info(root=ROOT):
    paths = list(RUNTIME_FILES)
    web = root/'cocos-kitchen/build/web'
    paths += sorted(p.relative_to(root).as_posix() for p in web.rglob('*') if p.is_file())
    digest = hashlib.sha256()
    for name in paths:
        p=root/name
        digest.update(name.encode()+b'\0')
        digest.update(hashlib.sha256(p.read_bytes()).digest() if p.is_file() else b'missing')
    return {'version':VERSION,'fingerprint':digest.hexdigest(),
            'scope':'runtime, config and built web files'}
