"""Every shipped level can be recorded: the research schemas' level range covers content/levels.

Level 4 shipped with the range still ending at 3, so each of its research records failed validation and the
page reported the contribution as failed.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ResearchLevelTests(unittest.TestCase):
    def test_the_record_and_package_schemas_cover_every_level(self):
        numbers = sorted(int(re.fullmatch(r'level-(\d+)\.json', p.name).group(1)) for p in (ROOT / 'content/levels').glob('level-*.json'))
        for name in ('research-record.schema.json', 'research-metadata.schema.json'):
            level = json.loads((ROOT / 'schemas' / name).read_text())['properties']['level']
            self.assertEqual((level['minimum'], level['maximum']), (0, numbers[-1]), name)  # 0: a player's own level


if __name__ == '__main__':
    unittest.main()
