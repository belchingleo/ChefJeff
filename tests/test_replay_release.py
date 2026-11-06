"""scripts/replay_release.py: research rounds replay with the code of the release that recorded them.

Synthetic loopback rounds through the real HTTP handlers (as test_research_replay); no model is called.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import release_info
from scripts import replay_release as rr
from scripts.research_export import export_package
import test_research_save_paths as paths

ROOT = Path(rr.__file__).resolve().parents[1]


class ReplayReleaseTests(paths.SavePathTests):
    def package(self, folder, close=False):
        """One finished (or page-closed) round, exported as a private research package."""
        receipt = self.play()
        if close:
            self.assertEqual(self.request('/api/session/close', {}, self.token)[0], 200)
        else:
            self.natural_end()
            self.assertEqual(self.contribute()[0], 200)
        path = Path(folder) / 'round.cjresearch.zip'
        export_package(self.game.store.path, path)
        return receipt, path

    def test_rounds_replay_in_their_releases_code_and_the_report_keeps_counts_only(self):
        with tempfile.TemporaryDirectory() as folder:
            _, package = self.package(folder, close=True)
            found, legacy = rr.records([folder])
            self.assertEqual((len(found), legacy), (1, 0))
            record = next(iter(found.values()))
            self.assertTrue(record['aborted'])                      # closed mid-round: the flag comes from the session
            self.assertEqual(record['release']['fingerprint'], release_info.release_info()['fingerprint'])
            table = Path(folder) / 'fingerprints.json'
            rr.write_table({record['release']['fingerprint']: {'commit': 'HEAD-test', 'version': 'x'}}, table)
            # The working tree is the release here (code_root would extract a commit).
            with patch.object(rr, 'code_root', lambda sha, cache: ROOT):
                report = rr.check([package], table=table, cache=Path(folder) / 'cache')
        self.assertEqual(report['replay'], {'verified': 1}, report['by_round'])
        self.assertEqual(report['requests'].keys(), {'verified'})
        self.assertGreater(report['requests']['verified'], 2)
        row = report['by_round'][0]
        self.assertEqual(row['commit'], 'HEAD-test')
        self.assertGreater(row['states_checked'], 2)
        text = json.dumps(report)
        for private in ('events', 'state', 'payload', 'player_communication', record['round_id']):
            self.assertNotIn(f'"{private}"' if private != record['round_id'] else private, text)

    def test_the_driver_takes_the_engine_from_the_release_and_the_checker_from_here(self):
        with tempfile.TemporaryDirectory() as folder:
            _, package = self.package(folder)
            record = next(iter(rr.records([package])[0].values()))
            # A copy of this build's runtime files stands for a release; then its engine is changed.
            release = Path(folder) / 'release'
            for name in release_info.RUNTIME_FILES:
                if (ROOT / name).is_file():
                    (release / name).parent.mkdir(parents=True, exist_ok=True)
                    (release / name).write_bytes((ROOT / name).read_bytes())
            same = rr.replay_group(release, [('r', record)])
            self.assertEqual(same[0]['replay'], 'verified', same)
            source = (release / 'kitchen.py').read_text(encoding='utf-8')
            marker = '    def advance(self, seconds):\n'
            self.assertIn(marker, source)
            (release / 'kitchen.py').write_text(source.replace(marker, marker + '        seconds = seconds * 1.5\n', 1),
                                                encoding='utf-8')
            changed = rr.replay_group(release, [('r', record)])
        self.assertEqual(changed[0]['replay'], 'diverged', changed)

    def test_record_adds_a_commit_and_an_unknown_table_format_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            table = Path(folder) / 'fingerprints.json'
            fp, entry = rr.record_commit('HEAD', table)
            self.assertEqual(entry['commit'], rr.full_sha('HEAD'))
            self.assertEqual(len(fp), 64)
            self.assertEqual(rr.read_table(table), {fp: entry})
            table.write_text(json.dumps({'format': 'other', 'releases': {}}))
            with self.assertRaises(rr.ReleaseError):
                rr.read_table(table)
        with self.assertRaises(rr.ReleaseError):
            rr.full_sha('no-such-commit-anywhere')

    def test_the_shipped_table_maps_fingerprints_to_known_commits(self):
        releases = rr.read_table()
        self.assertTrue(releases)
        for fp, entry in releases.items():
            self.assertEqual(len(fp), 64)
            self.assertEqual(rr.full_sha(entry['commit']), entry['commit'])
            self.assertTrue(entry['version'])


# Only the cases above; the inherited ones already run in their own modules.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(ReplayReleaseTests, _name, None)
