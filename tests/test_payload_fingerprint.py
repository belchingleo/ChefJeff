"""Jeff's model input must not change by accident (see tests/payload_fingerprint.py)."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import payload_fingerprint as pf  # noqa: E402


def sections(requests):
    """Full section hashes per request, rebuilt from the stored deltas."""
    current, out = {}, []
    for row in requests:
        current = {k: v for k, v in current.items() if k not in row['removed']}
        current.update(row['sections'])
        out.append(dict(current))
    return out


def first_difference(golden, actual):
    """A readable account of the first request whose input or request bodies differ."""
    if len(golden) != len(actual):
        head = f'{len(actual)} requests instead of {len(golden)}. '
    else:
        head = ''
    full_g, full_a = sections(golden), sections(actual)
    for i, (g, a) in enumerate(zip(golden, actual)):
        if g == a:
            continue
        changed = sorted(k for k in set(full_g[i]) | set(full_a[i]) if full_g[i].get(k) != full_a[i].get(k))
        gw, aw = g.get('wire', {}), a.get('wire', {})
        wires = sorted(k for k in set(gw) | set(aw) if gw.get(k) != aw.get(k))
        return (f"{head}First difference at request {i} (game time {a['t']}, golden {g['t']}). "
                f"Changed payload sections: {changed or 'none'}. Changed request bodies: {wires or 'none'}.")
    return head + 'The common requests match.'


class PayloadFingerprintTests(unittest.TestCase):
    def test_scenarios_match_their_golden_files(self):
        for name in pf.SCENARIOS:
            with self.subTest(scenario=name):
                golden = json.loads((pf.GOLDEN / f'{name}.json').read_text())
                actual = pf.recorded(name)[0]
                self.assertEqual(golden['requests'], actual['requests'],
                                 first_difference(golden['requests'], actual['requests'])
                                 + ' If the change to Jeff\'s input is intended, run '
                                   '`python3 tests/payload_fingerprint.py --update` and explain it in the commit.')
                self.assertEqual(golden['sample_payload'], json.loads(json.dumps(actual['sample_payload'], ensure_ascii=False)))
                self.assertEqual(golden['result'], actual['result'])

    def test_every_client_and_section_is_covered(self):
        golden = json.loads((pf.GOLDEN / 'level2-messages-memory.json').read_text())
        first = golden['requests'][0]
        names = set(first['wire'])
        self.assertTrue({'local:jev', 'local:zhipu', 'local:startlux', 'hosted:jev', 'hosted:zhipu'} <= names)
        self.assertEqual({n for n in names if n.startswith('local:')}, {'local:' + p for p in pf.player_api.PROVIDERS})
        seen = set().union(*(row['sections'] for row in golden['requests']))
        for key in ('state.player_communication', 'rules.player_communication', 'state.past_episodes',
                    'rules.past_episodes', 'state.recent_events', 'state.recent_decisions', 'questions'):
            self.assertIn(key if key != 'questions' else 'top.questions', seen)


class SwitchSetTests(unittest.TestCase):
    """The links table and the trial switches, wired as a started session wires them (pf.switch_run)."""

    def test_switch_sets_match_their_golden_files(self):
        for level in pf.SWITCH_LEVELS:
            for name in pf.SWITCH_SETS:
                with self.subTest(level=level, set=name):
                    golden = json.loads(pf.switch_golden(level, name).read_text(encoding='utf-8'))
                    actual = json.loads(json.dumps(pf.switch_run(level, name), ensure_ascii=False))
                    self.assertEqual(golden['on'], actual['on'])
                    self.assertEqual(golden['switches'], actual['switches'],
                                     'A started round wires its decision loop differently.')
                    self.assertEqual(len(golden['windows']), len(actual['windows']))
                    for g, a in zip(golden['windows'], actual['windows']):
                        self.assertEqual(g['requests'], a['requests'],
                                         f"Window from {a['start']} s: "
                                         + first_difference(g['requests'], a['requests'])
                                         + ' If the change to Jeff\'s input is intended, run `python3 '
                                           'tests/payload_fingerprint.py --switches --update` and explain it in the '
                                           'commit.')
                        self.assertEqual(g, a)
                    self.assertEqual(golden['digest'], actual['digest'])

    def test_the_sets_are_the_ones_named(self):
        release = pf.features.load()
        trials = {name for name, value in release.items() if value['stage'] == 'trial'}
        on = {name: {key for key, value in pf.switch_set(name).items() if value['on']} for name in pf.SWITCH_SETS}
        self.assertEqual(on['release'], {key for key, value in release.items() if value['on']})
        self.assertIn('option_links', on['release'])
        self.assertEqual(on['all'], set(release))
        self.assertEqual(on['local'], set(release) - {'timeline', 'no_history'})
        self.assertTrue(trials - {'timeline', 'no_history'} <= on['local'])
        self.assertEqual(on['local-links-off'], on['local'] - {'option_links'})
        # no_history wins over timeline: this is the one set whose requests carry the timeline.
        self.assertEqual(on['all-but-no-history'], set(release) - {'no_history'})
        # The separate links table with the other chef's lines: option_links_partner on, links_on_options off.
        self.assertEqual(on['release-partner-links'], (on['release'] | {'option_links_partner'}) - {'links_on_options'})
        self.assertNotIn('links_on_options', on['release-partner-links'])
        golden = json.loads(pf.switch_golden('level-5', 'release').read_text(encoding='utf-8'))
        self.assertEqual(golden['switches']['links'], 'partner')         # partner lines released in 0.10.1-beta.1
        self.assertTrue(any('wire' in row for w in golden['windows'] for row in w['requests']))
        partner = json.loads(pf.switch_golden('level-2', 'release-partner-links').read_text(encoding='utf-8'))
        self.assertEqual(partner['switches']['links'], 'partner')

    def test_jeff_works_the_split_floor(self):
        """On level 5 the stand-in model takes, works and throws items, so requests where Jeff holds something are
        in the net (with the recipe roles there it only waited)."""
        self.assertIn('level-5', pf.ZONED)
        golden = json.loads(pf.switch_golden('level-5', 'local').read_text(encoding='utf-8'))
        choices = [row['choice'] for w in golden['windows'] for row in w['requests']]
        self.assertTrue(any(choice.startswith('throw') for choice in choices), choices)
        self.assertTrue(any(choice.startswith('take') for choice in choices), choices)


if __name__ == '__main__':
    unittest.main()
