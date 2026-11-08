"""The page tells boards from other stations by the station's type, never by its id.

Board ids start with "b" (b1, b2), but so do the bread crate and the bins: judging by the id once drew a
chop bar under raw meat put on the bread crate.
"""
import re
import unittest
from kitchen import ROOT, load_config
from spatial_kitchen import SpatialKitchen

SCRIPTS = [ROOT / 'cocos-kitchen/assets/scripts' / name for name in ('KitchenClient.ts', 'KitchenAudio.ts')]


class StationKindTests(unittest.TestCase):
    def test_the_snapshot_types_boards_and_the_bread_crate_is_not_one(self):
        config = load_config()
        config.update(level=4)
        stations = SpatialKitchen(config).snapshot()['stations']
        self.assertEqual(stations['bread']['type'], 'ingredient_source')
        boards = {name for name, station in stations.items() if station['type'] == 'board'}
        self.assertTrue(boards)
        self.assertTrue(all(name.startswith('b') for name in boards))

    def test_page_scripts_do_not_guess_boards_from_the_id(self):
        for path in SCRIPTS:
            source = path.read_text(encoding='utf-8')
            self.assertIsNone(re.search(r"startsWith\('b'\)", source), path.name)


if __name__ == '__main__':
    unittest.main()
