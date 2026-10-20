"""Privacy/contact and model-guide pages: one Markdown source, rendered into the web build."""
from pathlib import Path
import re
import unittest
from scripts.player_pages import PAGES, render

ROOT = Path(__file__).resolve().parents[1]


class PlayerPageTests(unittest.TestCase):
    def page(self, name):
        return render((ROOT / 'docs' / name).read_text())

    def test_privacy_page_covers_storage_retention_deletion_and_contact(self):
        page = self.page('privacy.md')
        self.assertIn('href="https://github.com/belchingleo/ChefJeff/issues" target="_blank"', page)
        self.assertNotRegex(page, r'[\w.+-]+@[\w-]+\.[\w.]+')  # contact is GitHub only, no invented email
        for text in ('localStorage', '10 分钟', '30 天', '删除凭证', '本地版', 'id="english"'):
            self.assertIn(text, page)
        self.assertLess(page.index('隐私说明与反馈'), page.index('Online version'))  # Chinese first

    def test_model_guide_names_each_provider_and_links_privacy(self):
        page = self.page('model-guide.md')
        for text in ('openrouter.ai/api/v1', 'api.siliconflow.cn/v1', '同意通过试玩服务器调用 Jev', '估算', 'href="privacy.html"'):
            self.assertIn(text, page)
        # Every service the online settings list is explained (model-providers.json).
        import json
        catalog = json.loads((Path(__file__).resolve().parents[1] / 'model-providers.json').read_text())
        for preset in catalog['providers']:
            if preset.get('hosted') != 'none' and not preset.get('custom') and not preset.get('disabled'):
                self.assertIn(preset['label'], page)

    def test_built_pages_match_their_sources(self):
        web = ROOT / 'cocos-kitchen/build/web'
        for source, target in PAGES.items():
            self.assertEqual((web / target).read_text(), self.page(source), f'Rebuild the web client: {target} is stale')
        shell = (ROOT / 'cocos-kitchen/web-shell.html').read_text()
        self.assertIn('href="privacy.html" target="_blank"', shell)
        self.assertIn('href="model-guide.html" target="_blank"', shell)

    def test_markup_is_escaped_and_links_are_restricted(self):
        self.assertIn('&lt;script&gt;', render('<script>alert(1)</script>'))
        with self.assertRaises(ValueError):
            render('[x](javascript:alert(1))')
        self.assertEqual(re.findall(r'<li>', render('- a\n  - b\n- c')), ['<li>'] * 3)


if __name__ == '__main__':
    unittest.main()
