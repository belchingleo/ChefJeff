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

    def test_audio_errors_cannot_break_play(self):
        # KitchenClient calls these from poll(), update() and button handlers; an audio exception there
        # would read as a lost connection (auto-pause), skip a frame, or swallow a click.
        source = CLIENT.read_text()
        public = re.findall(r'^    (?!private\b)(\w+)\([^)]*\)\{(.*)$', source, re.M)
        names = {name for name, _ in public}
        self.assertTrue({'play', 'chop', 'onState', 'update'} <= names, names)
        unguarded = [name for name, body in public
                     if name not in ('load', 'destroy') and not body.startswith('this.safely(')]
        self.assertEqual(unguarded, [], 'every public KitchenAudio entry point must run inside safely()')
        # load() is async and guards itself: a failed download leaves the kitchen silent, not broken.
        self.assertRegex(source.split('async load(')[1].split('\n    }\n')[0], r'catch\(error\)\{console\.warn')

    def test_composed_music_loops_on_bar_lines(self):
        # The client moves from service to rush on the service's next bar line; that only works if every loop
        # is a whole number of bars, so bar lines fall in the same place on every pass.
        manifest = {s['id']: s for s in json.loads(MANIFEST.read_text())['sounds']}
        for name in ('bgm_menu', 'bgm_service', 'bgm_rush'):
            entry = self.index['sounds'][name]
            self.assertEqual((entry.get('source'), manifest[name]['pick']), ('composed', 'composed'), name)
            bars = entry['seconds'] / entry['bar']
            self.assertAlmostEqual(bars, round(bars), delta=.002, msg=f'{name}: {bars} bars')
        # Starting a round must not wait for the menu's bar line; only the rush enters on a bar line, and the
        # march pieces start at full level so their first beat is heard.
        flags = {n: (bool(self.index['sounds'][n].get('crisp')), bool(self.index['sounds'][n].get('on_bar')))
                 for n in ('bgm_menu', 'bgm_service', 'bgm_rush')}
        self.assertEqual(flags, {'bgm_menu': (False, False), 'bgm_service': (True, False), 'bgm_rush': (True, True)})
        composer = (ROOT / 'scripts/audio/compose_music.py').read_text()
        self.assertIn("PIECES = {'bgm_menu': menu, 'bgm_service': service, 'bgm_rush': rush}", composer)
        tick = CLIENT.read_text().split('private tick(')[1].split('\n    }\n')[0]
        self.assertIn('this.stepPendingMusic(dt);', tick, 'the bar-line switch must be checked every frame')
        # Only pause -> resume continues a piece in place; a new round or the rush must start from the top
        # (the service's oom-pah opening, the rush's first bar).
        self.assertIn("was==='paused'&&!fresh", CLIENT.read_text())

    def test_loops_end_just_inside_the_buffer(self):
        # The embedded Chromium froze the in-round music for good at its first loop point when the loop ran to the
        # buffer's very end; every playing loop gets an explicit loop end a little inside it, each frame, since the
        # engine makes a new source node on every play or seek.
        source = CLIENT.read_text()
        step = source.split('private step(')[1].split('\n    }\n')[0]
        self.assertIn('this.holdLoopEnd(src);', step.split('}else if(src.playing)')[0])
        hold = source.split('private holdLoopEnd(')[1].split('\n    }\n')[0]
        self.assertIn('node.loopEnd=Math.max(0,node.buffer.duration-LOOP_END_INSET)', hold)
        inset = float(re.search(r'const LOOP_END_INSET=([\d.]+);', source).group(1))
        self.assertTrue(.0005 <= inset <= .002, inset)

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
