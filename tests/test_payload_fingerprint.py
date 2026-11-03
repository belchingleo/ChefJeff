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
                actual = pf.run(name)
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


if __name__ == '__main__':
    unittest.main()
