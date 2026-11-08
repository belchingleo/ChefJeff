"""CHANGELOG.md: one release section never lists the same change twice (both languages)."""
from pathlib import Path
import unittest

CHANGELOG = Path(__file__).resolve().parents[1] / 'CHANGELOG.md'


class ChangelogTests(unittest.TestCase):
    def test_no_release_section_repeats_a_bullet(self):
        section, seen, repeats = None, {}, []
        for number, line in enumerate(CHANGELOG.read_text(encoding='utf-8').splitlines(), 1):
            if line.startswith('## '):
                section, seen = line, {}
            elif line.startswith('- '):
                # Merges have left whole bullets twice, and an older version of a bullet beside its newer one;
                # both start the same way.
                key = line[:70]
                if key in seen:
                    repeats.append(f'line {number} repeats line {seen[key]} under {section!r}')
                seen.setdefault(key, number)
        self.assertEqual(repeats, [])


if __name__ == '__main__':
    unittest.main()
