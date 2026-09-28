"""Model-visible rules state facts and legal actions, not collaboration values.

The environment affords shared work and handoffs; it must not instruct Jeff to
cooperate with, help or prioritise the human. See the collaboration rules
supplement v0.1, section 2.
"""
import json
import re
import unittest
from pathlib import Path

from kitchen import ROOT, load_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
import jev
import player_api
from levels import level_config

VALUE_WORDING = re.compile(r'cooperat|teammate|\bhelp|assist|support the|you may consider|coordinating|coordinate with', re.I)


def rule_text(payload):
    rules = payload['state']['rules']
    return json.dumps(rules, ensure_ascii=False) + payload['questions']['next_action']['instructions']


class NeutralRulesTests(unittest.TestCase):
    def test_rules_and_question_have_no_collaboration_value_wording(self):
        for level in (1, 2, 3, 'legacy-level-1', 'legacy-level-2', 'legacy-level-3'):
            with self.subTest(level=level):
                k = SpatialKitchen(level_config(load_config(), level) if isinstance(level, int)
                                   else load_config() | {'level': int(level[-1]), 'order_seed': 1, 'spawn_seed': 0})
                payload = SpatialJevClient(k.c, key='test').payload(k.snapshot(), k.actions('jeff'))
                self.assertIsNone(VALUE_WORDING.search(rule_text(payload)))

    def test_system_prompts_are_neutral(self):
        source = (Path(player_api.__file__).read_text() + (ROOT / 'hosted' / 'browser-agent.js').read_text())
        prompts = re.findall(r"(?:content'?\s*:\s*)'([^']*)'", source)
        self.assertTrue(prompts)
        for prompt in prompts:
            self.assertIsNone(VALUE_WORDING.search(prompt), prompt)

    def test_rules_version_is_published(self):
        self.assertEqual(jev.AGENT_RULES_VERSION, 'rules-v4')


if __name__ == '__main__':
    unittest.main()
