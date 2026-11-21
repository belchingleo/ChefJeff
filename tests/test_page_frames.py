"""The page's frame times reach the round's end row (POST /api/page-frames). No model."""
from pathlib import Path
import tempfile
import unittest
import uuid

from player_api import PlayerGameSession
from spatial_kitchen import SpatialKitchen
from test_jev import NoKeyClient
from test_web import FakeJournal

FRAMES = {'frames': 3318, 'p50_ms': 21.8, 'p90_ms': 23.6, 'max_ms': 95.4, 'over_25ms': 120, 'over_50ms': 3,
          'frame_rate': 45.9}


class PageFrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.g = PlayerGameSession(credential_path=Path(self.tmp.name) / 'settings.json', kitchen_factory=SpatialKitchen,
                                   journal_factory=FakeJournal, connector=lambda c, s: NoKeyClient(c))
        self.addCleanup(self.g.close)
        self.g.setting = {'provider': 'compatible', 'model': 'test-only', 'api_key': 'test-only-not-a-key'}

    def cmd(self, path, **data):
        return self.g.command('/api/' + path, {'game_id': self.g.game_id, 'request_id': uuid.uuid4().hex, **data})

    def test_the_page_is_told_to_send_them_and_the_end_row_keeps_the_latest(self):
        self.assertTrue(self.g.public_state()['page_frames'])
        self.assertEqual(self.cmd('start')[0], 200)
        log = self.g.journal
        self.assertEqual(self.cmd('page-frames', frames={**FRAMES, 'game_id': self.g.game_id})[0], 200)
        later = {**FRAMES, 'frames': 4000, 'game_id': self.g.game_id}
        self.assertEqual(self.cmd('page-frames', frames=later)[0], 200)
        self.assertEqual(self.cmd('end')[0], 200)
        end = next(v for k, v in log.rows if k == 'end')
        self.assertEqual(end['page_frames'], {**FRAMES, 'frames': 4000})

    def test_bad_or_foreign_frames_are_refused(self):
        self.assertEqual(self.cmd('start')[0], 200)
        self.assertEqual(self.cmd('page-frames', frames={**FRAMES, 'game_id': 'another round'})[0], 400)
        self.assertEqual(self.cmd('page-frames', frames={**FRAMES, 'game_id': self.g.game_id, 'p50_ms': 'fast'})[0], 400)
        self.assertEqual(self.cmd('page-frames', frames='nope')[0], 400)
        self.assertIsNone(self.g.page_frames)


if __name__ == '__main__':
    unittest.main()
