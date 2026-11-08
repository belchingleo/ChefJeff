"""Public build identity; no paths, credentials or Git metadata are exposed."""
import hashlib
from pathlib import Path

VERSION = '0.7.0-beta.1'
# The page/kitchen-server contract. The page refuses a server with another number (an old server still running
# after the page was updated); bump it, and KitchenClient.ts's CLIENT_PROTOCOL with it, only when the contract
# changes, so a release alone does not need the web build rebuilt.
CLIENT_PROTOCOL = 1
ROOT = Path(__file__).resolve().parent
RUNTIME_FILES = ('model_status.py', 'reach_note.py', 'free_model_diagnostics.py', 'free_model_budget.py', 'free_model_gateway.py', 'free_model_client.py', 'model_output.py', 'hosted_free_models.py', 'hosted_cloudflare.py', 'hosted/free-model-picker.html', 'hosted/free-model-picker.js', 'hosted/free-model-settings.html', 'shared_client.py', 'shared_data.py', 'shared_server.py', 'hosted_server.py', 'hosted_records.py', 'hosted_capacity.py', 'hosted_jev.py', 'hosted_usage.py', 'hosted/browser-agent.js', 'hosted/contribution.html', 'hosted/consent.html', 'map_definition.py', 'maps/level-1.json', 'maps/level-2.json', 'maps/level-3.json', 'maps/level-4.json', 'levels.py', 'navigation.py', 'kitchen.py', 'spatial_kitchen.py', 'jev.py', 'harness.py', 'environment.py', 'agent_loop.py', 'one_press.py', 'undo_note.py', 'wire_format.py', 'ask_ahead.py', 'features.py', 'features.json', 'model_language.py', 'model-language-en-v4.json', 'model-providers.json', 'web_server.py',
                 'cocos_server.py', 'player_api.py', 'cooperation_memory.py', 'play.py',
                 'whitebox_server.py', 'feedback.py', 'release_info.py', 'config.json', 'research_replay.py',
                 'scripts/launch_web.py', 'scripts/stop_web.py',
                 'rules.py', 'config_contract.py', 'schema_check.py', 'session_record.py', 'research_record.py', 'provenance.py', 'collaboration_analyzer.py', 'round_summary.py',
                 'reference_policy.py', 'level_calibration.py', 'player_level_queue.py', 'level_design.py')


# Contracts and authored content ship with the runtime; listed from disk so new documents are never missed.
RUNTIME_FILES += tuple(sorted(p.relative_to(ROOT).as_posix() for folder in ('schemas', 'content', 'rulesets')
                              for p in (ROOT / folder).rglob('*.json')))


def release_info(root=ROOT):
    paths = list(RUNTIME_FILES)
    web = root/'cocos-kitchen/build/web'
    paths += sorted(p.relative_to(root).as_posix() for p in web.rglob('*') if p.is_file())
    digest = hashlib.sha256()
    for name in paths:
        p=root/name
        digest.update(name.encode()+b'\0')
        digest.update(hashlib.sha256(p.read_bytes()).digest() if p.is_file() else b'missing')
    return {'version':VERSION,'fingerprint':digest.hexdigest(),'client_protocol':CLIENT_PROTOCOL,
            'scope':'runtime, config and built web files'}
