"""off_for: a feature is off by default for the rounds of the model services it names.

features.json gives option_links_partner and split_floor to every service but Perplexity (since 0.11.0, 2026-11-27;
the local play set's override did it from 2026-11-19). The session tests use option_links (步骤提示) with off_for set. There is no player
switch any more (2026-11-20): the service a round asks alone decides.
"""
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import Mock, patch
import uuid

import features
import links
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from test_one_press import Answering, with_features
from test_web import FakeJournal


def table_off_for_perplexity():
    # The links table alone (since 0.10.1-beta.1 the release also gives partner lines, 'partner' in the loop).
    return with_features(option_links={'off_for': ['perplexity']}, option_links_partner={'on': False})


def partner_and_split_but_perplexity():
    """As the local play set's override gives them (on, off for Perplexity), with the step hints on."""
    raw, _ = features._release()
    return features.with_override(raw, {name: {'on': True, 'off_for': ['perplexity']}
                                        for name in ('option_links_partner', 'split_floor')})


class FileTests(unittest.TestCase):
    def test_the_repository_file_turns_partner_lines_and_the_split_floor_off_only_for_perplexity(self):
        # The 8775 play set as the defaults (0.11.0, 2026-11-27): Perplexity needs neither.
        self.assertEqual({name: value['off_for'] for name, value in features.load().items() if value.get('off_for')},
                         {'option_links_partner': ['perplexity'], 'split_floor': ['perplexity']})

    def test_an_override_gives_partner_lines_and_the_split_floor_line_to_every_service_but_perplexity(self):
        value = partner_and_split_but_perplexity()
        for name in ('option_links_partner', 'split_floor'):
            self.assertEqual(value[name]['off_for'], ['perplexity'])
            self.assertEqual(features.model_defaults(value, 'perplexity')[name],
                             {**value[name], 'on': False, 'source': 'model'})
            self.assertTrue(features.model_defaults(value, 'jev')[name]['on'])
        self.assertEqual(features.links_option(features.model_defaults(value, 'perplexity')), True)
        self.assertEqual(features.links_option(features.model_defaults(value, 'jev')), 'partner')

    def test_off_for_names_distinct_listed_services(self):
        for wrong in ('perplexity', ['nobody'], ['perplexity', 'perplexity'], [1]):
            with self.subTest(off_for=wrong), self.assertRaises(ValueError):
                with_features(option_links={'off_for': wrong})
        self.assertEqual(with_features(option_links={'off_for': []})['option_links']['off_for'], [])

    def test_the_service_default_turns_off_only_what_is_on_and_names_it(self):
        # Only option_links names services here (the release's own off_for set aside, as the file had none until 0.11.0).
        value = with_features(option_links={'off_for': ['perplexity', 'jev']}, option_links_partner={'off_for': []},
                              split_floor={'off_for': []})
        off = features.model_defaults(value, 'perplexity')
        self.assertEqual(off['option_links'], {**value['option_links'], 'on': False, 'source': 'model'})
        self.assertEqual({k: v for k, v in off.items() if k != 'option_links'}, {k: v for k, v in value.items() if k != 'option_links'})
        self.assertIs(features.model_defaults(value, None), value)
        self.assertEqual(features.model_defaults(value, 'openrouter-decision')['option_links']['on'], True)
        self.assertEqual(features.snapshot(off)['option_links'], {'on': False, 'version': links.SWITCH_VERSION, 'source': 'model'})
        already_off = with_features(option_links={'on': False, 'off_for': ['perplexity']})
        self.assertNotIn('source', features.model_defaults(already_off, 'perplexity')['option_links'])

    def test_an_override_may_give_the_feature_to_every_service(self):
        raw, _ = features._release()
        value = features.with_override(raw, {'option_links': {'off_for': []}})
        self.assertTrue(features.model_defaults(value, 'perplexity')['option_links']['on'])
        with self.assertRaises(ValueError):
            features.with_override(raw, {'option_links': {'off_for': ['nobody']}})


class Session:
    """A local game session whose model service is set by the test."""

    def make(self, case, service=None, value=None):
        from web_server import GameSession
        with patch.object(features, 'current', lambda: value or table_off_for_perplexity()):
            g = GameSession(level_config(load_config(), 'level-2'), client_factory=lambda c: Answering(c),
                            journal_factory=FakeJournal, kitchen_factory=SpatialKitchen)
        case.addCleanup(g.close)
        g.service = service
        g.model_service = lambda: g.service
        return g


def start_row(g):
    return [d for kind, d in g.journal.journal.rows if kind == 'start'][-1]


class SessionTests(unittest.TestCase):
    def test_a_perplexity_round_starts_without_the_table_and_records_why(self):
        g = Session().make(self, 'perplexity')
        self.assertNotIn('links', g.communication_state())                        # no player switch
        self.assertEqual(g._command('/api/links', {'on': True})[0], 404)
        self.assertEqual(g._command('/api/start', {})[0], 200)
        self.assertIs(g.ai.links, False)
        self.assertEqual(start_row(g)['features']['option_links'], {'on': False, 'version': links.SWITCH_VERSION, 'source': 'model'})

    def test_other_services_keep_the_table(self):
        for service in ('jev', 'parallel', 'openrouter-decision', 'deepseek', None):
            with self.subTest(service=service):
                g = Session().make(self, service)
                self.assertEqual(g._command('/api/start', {})[0], 200)
                self.assertIs(g.ai.links, True)
                self.assertEqual(start_row(g)['features']['option_links'], {'on': True, 'version': links.SWITCH_VERSION})


class PartnerAndSplitTests(unittest.TestCase):
    def test_a_jev_round_gets_them_and_a_perplexity_round_starts_without_them(self):
        for service, partner in (('jev', True), ('perplexity', False)):
            with self.subTest(service=service):
                g = Session().make(self, service, partner_and_split_but_perplexity())
                self.assertEqual(g._command('/api/start', {})[0], 200)
                self.assertEqual(g.ai.links, 'partner' if partner else True)
                self.assertIs(g.ai.split, partner)
                row = start_row(g)['features']
                for name in ('option_links_partner', 'split_floor'):
                    self.assertEqual(row[name]['on'], partner)
                    self.assertEqual(row[name].get('source'), 'server' if partner else 'model')


class LocalConnectionTests(unittest.TestCase):
    def setUp(self):
        from player_api import PlayerGameSession
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        client = Mock()
        client.ask.return_value = {'choice': 'ready'}
        with patch.object(features, 'current', table_off_for_perplexity):
            self.g = PlayerGameSession(credential_path=Path(folder.name) / '.player-api.json', connector=Mock(return_value=client),
                                       journal_factory=FakeJournal)
        self.addCleanup(self.g.close)

    def connect(self, provider, **extra):
        return self.g.command('/api/connection', {'game_id': self.g.game_id, 'request_id': uuid.uuid4().hex,
                                                  'provider': provider, 'api_key': 'test-not-a-real-key', **extra})

    def start(self):
        self.assertEqual(self.g._command('/api/start', {})[0], 200)
        on = self.g.ai.links
        self.assertEqual(self.g._command('/api/end', {})[0], 200)
        self.assertEqual(self.g._command('/api/reset', {})[0], 200)
        return on

    def test_the_start_row_names_the_connection_s_service_and_model_without_the_key(self):
        # config.model is the game's default request field (jev-latest); the start row says what the round asks.
        self.assertEqual(self.connect('perplexity')[0], 200)
        self.assertEqual(self.g._command('/api/start', {})[0], 200)
        row = start_row(self.g)
        self.assertEqual(row['connection'], {'service': 'perplexity', 'model': self.g.setting['model']})
        self.assertTrue(row['connection']['model'])
        self.assertNotIn('test-not-a-real-key', json.dumps(row))

    def test_the_saved_connection_s_service_sets_the_table(self):
        self.assertEqual(self.connect('jev')[0], 200)
        self.assertIs(self.start(), True)
        self.assertEqual(self.connect('perplexity')[0], 200)
        self.assertIs(self.start(), False)
        self.assertEqual(self.g.command('/api/connection', {'game_id': self.g.game_id, 'request_id': 'clear', 'clear': True})[0], 200)
        self.assertEqual(self.g.model_service(), None)


class HostedTests(unittest.TestCase):
    def session(self):
        from hosted_server import HostedSession
        with patch.object(features, 'current', table_off_for_perplexity):
            s = HostedSession()
        self.addCleanup(s.close)
        return s

    def test_the_browser_reports_only_the_preset_service_and_the_round_takes_its_default(self):
        s = self.session()
        self.assertEqual(s._command('/api/browser-ready', {'connected': True, 'provider': 'perplexity'})[0], 200)
        self.assertEqual(s._command('/api/start', {})[0], 200)
        self.assertIs(s.ai.links, False)
        self.assertEqual(s.features['option_links']['source'], 'model')

    def test_a_bad_report_is_refused_and_an_old_page_s_report_keeps_the_table(self):
        s = self.session()
        for body in ({'connected': True, 'provider': 'https://api.perplexity.ai'}, {'connected': 'yes', 'provider': 'perplexity'}):
            with self.subTest(body=body):
                self.assertEqual(s._command('/api/browser-ready', body)[0], 400)
        self.assertEqual(s._command('/api/browser-ready', {'connected': True})[0], 200)
        self.assertIs(s.model_service(), None)
        self.assertEqual(s._command('/api/start', {})[0], 200)
        self.assertIs(s.ai.links, True)

    def test_a_disconnected_report_names_no_service(self):
        s = self.session()
        s._command('/api/browser-ready', {'connected': True, 'provider': 'perplexity'})
        self.assertEqual(s.model_service(), 'perplexity')
        s._command('/api/browser-ready', {'connected': False, 'provider': 'perplexity'})
        self.assertIs(s.model_service(), None)

    def test_the_start_row_names_the_reported_service(self):
        s = self.session()
        s._command('/api/browser-ready', {'connected': True, 'provider': 'perplexity'})
        self.assertEqual(s.model_connection(), {'service': 'perplexity'})
        s._command('/api/browser-ready', {'connected': False, 'provider': 'perplexity'})
        self.assertIsNone(s.model_connection())

    def test_a_free_model_is_the_site_s_own_service(self):
        s = self.session()
        s.free_model_provider, s.connected = 'zhipu', True
        self.assertEqual(s.model_service(), 'zhipu')


class RoundRunnerTests(unittest.TestCase):
    def test_rounds_take_the_default_of_the_service_asked(self):
        from scripts import model_rounds
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder, 'perplexity.key')
            key.write_text('test-not-a-real-key\n')
            key.chmod(0o600)
            with patch.object(model_rounds, 'PERPLEXITY_KEY', key), redirect_stderr(io.StringIO()):
                self.assertEqual(model_rounds.connect(perplexity='pplx-decider-v1.3').service, 'perplexity')
            saved = Path(folder, '.player-api.json')
            saved.write_text(json.dumps({'provider': 'parallel', 'api_key': 'test-not-a-real-key'}))
            self.assertEqual(model_rounds.saved_service(saved), 'parallel')
            self.assertEqual(model_rounds.saved_service(Path(folder, 'none.json')), 'jev')


if __name__ == '__main__':
    unittest.main()
