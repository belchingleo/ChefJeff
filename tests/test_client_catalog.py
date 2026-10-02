"""The web client draws and names food and vessels from the server's recipe data, never from fixed ids."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / 'cocos-kitchen' / 'assets' / 'scripts').glob('*.ts'))
# Art atlas folders are asset paths, not recipe data; the one named fallback art stem is art too.
ALLOWED = re.compile(r"'art/[a-z0-9-]+'|const VESSEL_ART_FALLBACK='[a-z_]+';")


def catalog_words():
    """Every item, dish and vessel id and name in the shipped recipe catalogs. Plates are left out:
    clean and dirty plates are engine objects with their own stages, not a cooking vessel."""
    words = set()
    for path in (ROOT / 'content' / 'recipes').glob('*.json'):
        catalog = json.loads(path.read_text())
        for section in ('items', 'recipes', 'dishes', 'containers'):
            entries = catalog.get(section) or {}
            for key, entry in (entries.items() if isinstance(entries, dict) else ((e.get('id'), e) for e in entries)):
                if section == 'containers' and key == 'plate':
                    continue
                words.add(key)
                if isinstance(entry, dict) and entry.get('name'):
                    words.add(entry['name'])
    return {w for w in words if w}


class ClientCatalogTests(unittest.TestCase):
    def test_the_client_scripts_name_no_dish_or_ingredient(self):
        words = catalog_words()
        self.assertTrue({'beef', 'burger', 'pan', 'pot', '平底锅'} <= words, 'the catalog scan must see the shipped recipes')
        for script in SCRIPTS:
            code = re.sub(r'/\*.*?\*/|//[^\n]*', '', script.read_text(), flags=re.S)
            code = ALLOWED.sub("''", code)
            for word in sorted(words):
                pattern = re.escape(word) if re.search(r'[^\x00-\x7f]', word) else r'\b' + re.escape(word) + r'\b'
                self.assertIsNone(re.search(pattern, code), f'{script.name} names {word!r}')


    def test_the_client_lists_levels_from_the_server(self):
        """Level buttons come from state.levels: no level id, name or fixed level count in code."""
        words = set()
        for path in (ROOT / 'content' / 'levels').glob('*.json'):
            level = json.loads(path.read_text())
            words |= {level['id'], level['name']}
        self.assertTrue({'level-1', 'level-4'} <= words)
        for script in SCRIPTS:
            code = re.sub(r'/\*.*?\*/|//[^\n]*', '', script.read_text(), flags=re.S)
            for word in words:
                self.assertNotIn(word, code, f'{script.name} names {word!r}')
            for pattern in (r"'level[0-9]+'", r"'level'\s*\+", r"\[\s*1\s*,\s*2\s*,\s*3\s*\]"):
                self.assertIsNone(re.search(pattern, code), f'{script.name} hard-codes the levels ({pattern})')


if __name__ == '__main__':
    unittest.main()
