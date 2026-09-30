"""Game audio stays consistent: every sound the client plays is shipped, and nothing picked is missing."""
import json
import re
import unittest
from pathlib import Path
from kitchen import Kitchen, ROOT, load_config
from web_server import GameSession

AUDIO = ROOT / 'cocos-kitchen/assets/resources/audio'
CLIENT = ROOT / 'cocos-kitchen/assets/scripts/KitchenAudio.ts'
MANIFEST = ROOT / 'scripts/audio/sound_manifest.json'


class AudioAssetTests(unittest.TestCase):
    def setUp(self):
        self.index = json.loads((AUDIO / 'index.json').read_text())

    def names(self):
        return set(self.index['sounds']) | set(self.index['wash']) | set(self.index['chop'])

    def test_every_indexed_sound_has_a_file(self):
        missing = sorted(n for n in self.names() if not (AUDIO / f'{n}.mp3').is_file())
        self.assertEqual(missing, [])
        self.assertGreater(len(self.index['chop']), 4, 'chopping needs several strikes to avoid a machine-gun repeat')

    def test_client_only_plays_shipped_sounds(self):
        source = CLIENT.read_text()
        used = set(re.findall(r"play\('([a-z_]+)'", source))
        used |= set(re.findall(r"'([a-z_]+)'", re.search(r'const MUSIC=\[([^\]]*)\]', source).group(1)))
        loops = re.search(r'const LOOPS[^=]*=\[(.*?)\n\];', source, re.S).group(1)
        used |= {m[1] for m in re.findall(r"\['([a-z_]+)','([a-z_]+)',", loops)}  # loop channel -> clip
        table = re.search(r'EVENT_SOUNDS[^{]*\{([^}]*)\}', source).group(1)
        used |= set(re.findall(r":'([a-z_]+)'", table))
        used |= set(re.findall(r"'(bgm_[a-z]+|jingle_[a-z]+)'", source))
        self.assertTrue(used, 'the pattern no longer finds sound names in KitchenAudio.ts')
        self.assertEqual(sorted(used - self.names()), [])

    def test_manifest_picks_match_the_export(self):
        manifest = json.loads(MANIFEST.read_text())
        unpicked = [s['id'] for s in manifest['sounds'] if not s.get('fixed') and 'pick' not in s]
        self.assertEqual(unpicked, [])
        exported = {s['id'] for s in manifest['sounds'] if not s.get('fixed')}
        self.assertEqual(exported, set(self.index['sounds']))
        for dropped in manifest.get('dropped', {}):
            self.assertNotIn(dropped, self.index['sounds'])

    def test_state_events_name_the_actor(self):
        # The client tells a throw from a put-down by who acted; the payload must carry it.
        g = GameSession(config=load_config() | {'order_seed': 1, 'spawn_seed': 0}, client_factory=lambda c: None,
                        journal_factory=lambda *a: (lambda *b: None), kitchen_factory=Kitchen)
        g.k.emit('test throw', kind='thrown', actor='human')
        event = next(e for e in g.public_state()['events'] if e['message'] == 'test throw')
        self.assertEqual((event['kind'], event['actor']), ('thrown', 'human'))


if __name__ == '__main__':
    unittest.main()
