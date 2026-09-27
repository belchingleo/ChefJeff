"""Public build identity; no paths, credentials or Git metadata are exposed."""
import hashlib
from pathlib import Path

VERSION = '0.5.9-alpha'
ROOT = Path(__file__).resolve().parent
RUNTIME_FILES = ('hosted_server.py', 'hosted_records.py', 'hosted/browser-agent.js', 'hosted/contribution.html', 'map_definition.py', 'maps/level-1.json', 'maps/level-2.json', 'maps/level-3.json', 'levels.py', 'navigation.py', 'kitchen.py', 'spatial_kitchen.py', 'jev.py', 'model_language.py', 'model-language-en-v1.json', 'web_server.py',
                 'cocos_server.py', 'player_api.py', 'cooperation_memory.py', 'play.py',
                 'whitebox_server.py', 'feedback.py', 'release_info.py', 'config.json',
                 'scripts/launch_web.py', 'scripts/stop_web.py',
                 'rules.py', 'config_contract.py', 'schema_check.py', 'session_record.py',
                 'rulesets/chefjeff-legacy.json', 'rulesets/chefjeff-continuous.json',
                 'content/orders/pilot-draft-mixed.json', 'content/levels/pilot-draft-mixed.json', 'content/equipment/chefjeff-core.json',
                 'content/recipes/chefjeff-core.json', 'content/orders/level-1.json',
                 'content/orders/level-2.json', 'content/orders/level-3.json',
                 'content/levels/level-1.json', 'content/levels/level-2.json', 'content/levels/level-3.json',
                 'schemas/common.schema.json', 'schemas/configuration.schema.json', 'schemas/equipment.schema.json',
                 'schemas/level.schema.json', 'schemas/map.schema.json', 'schemas/order.schema.json',
                 'schemas/recipe.schema.json', 'schemas/resolved.schema.json', 'schemas/ruleset.schema.json',
                 'schemas/event.schema.json', 'schemas/session.schema.json')


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
