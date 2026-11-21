"""build/web against its sources, for every step of scripts/build_cocos.py that runs after Creator.

Creator compiles the TypeScript and writes the folder; build_cocos.py then copies, generates or patches
the files below. A source edited without a rebuild leaves build/web stale, and the packaged demo and the
online page serve the stale copy.

Checked elsewhere in the same way: touch-controls.js, gamepad-controls.js and level-editor.js
(test_release.py), privacy.html and model-guide.html (test_player_pages.py), and the source-sha256
markers in assets/main/index*.js (presentation_loading_test.cjs).
"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'cocos-kitchen'
WEB = SOURCE / 'build/web'
# Copied unchanged: the same path under cocos-kitchen/ and build/web/.
COPIED = ('favicon.ico', 'apple-touch-icon.png', 'fonts/chefjeff-pixel.woff2', 'fonts/OFL.txt')
# What build_cocos.py puts after the favicon link in the Creator page.
ICONS = ('<link rel="icon" href="favicon.ico"/>'
         '\n    <link rel="apple-touch-icon" href="apple-touch-icon.png"/>'
         '\n    <meta name="apple-mobile-web-app-title" content="ChefJeff"/>'
         '\n    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"/>')
# KitchenGeometry.ts has no source-sha256 marker in the bundle yet.


def text(path):
    return path.read_text(encoding='utf-8')


class WebBuildSyncTests(unittest.TestCase):
    def assertBuilt(self, name, actual, expected, unit):
        if actual != expected:
            self.fail(f'Rebuild the web client: build/web/{name} has {len(actual)} {unit}, '
                      f'its sources give {len(expected)}')

    def built(self, name):
        path = WEB / name
        self.assertTrue(path.is_file(), f'build/web/{name} is missing')
        return path

    def test_generated_scripts_match_their_sources(self):
        # test_localization.py compares kitchen-i18n.js too, but only when Node is installed.
        # Both sides are read as text, so a checkout with CRLF line endings compares the same.
        catalog = text(SOURCE / 'i18n.json')
        self.assertBuilt('kitchen-i18n.js', text(self.built('kitchen-i18n.js')),
                         text(SOURCE / 'i18n.js').replace('__KITCHEN_CATALOG__', catalog), 'characters')
        providers = json.loads(text(ROOT / 'model-providers.json'))
        self.assertBuilt('model-providers.js', text(self.built('model-providers.js')),
                         'window.chefjeffProviders=' + json.dumps(providers, ensure_ascii=False) + ';\n', 'characters')

    def test_copied_files_match_their_sources(self):
        for name in COPIED:
            with self.subTest(name=name):
                self.assertBuilt(name, self.built(name).read_bytes(), (SOURCE / name).read_bytes(), 'bytes')

    def test_index_page_carries_the_current_shell(self):
        page = text(WEB / 'index.html')
        self.assertEqual(page.count('</body>'), 1)
        # The shell goes right after Creator's last script, the one that starts the game.
        start = page.index('</script>', page.index('System.import(')) + len('</script>')
        shell = text(SOURCE / 'web-shell.html') + '</body>'
        rest = page[start:].lstrip()
        self.assertTrue(rest.startswith(shell) and rest[len(shell):].strip() == '</html>',
                        'Rebuild the web client: the end of index.html is not the current web-shell.html')

    def test_index_page_head_has_the_build_changes(self):
        page = text(WEB / 'index.html')
        head = page[:page.index('</head>')]
        self.assertEqual(re.findall(r'<title>(.*?)</title>', head), ['ChefJeff·不分手厨房'])
        # The text stays zoomable: no user-scalable=no or maximum-scale from Creator's template.
        self.assertEqual(re.findall(r'<meta name="viewport" content="([^"]*)"', head),
                         ['width=device-width,initial-scale=1,viewport-fit=cover'])
        self.assertEqual(re.findall(r'<meta name="screen-orientation" content="([^"]*)"', head), ['landscape'])
        self.assertEqual(head.count(ICONS), 1)

    def test_settings_track_the_browser_viewport(self):
        found = sorted(WEB.glob('src/settings*.json'))
        self.assertEqual(len(found), 1, [path.name for path in found])
        self.assertIs(json.loads(text(found[0]))['screen']['exactFitScreen'], True)


if __name__ == '__main__':
    unittest.main()
