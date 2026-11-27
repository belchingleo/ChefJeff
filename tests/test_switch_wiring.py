"""One mapping from the features to Jeff's request switches (features.compose_options): a started round's decision
loop gets what compose_options gives, for the defaults, each trial switch alone and every feature on, and research
replay reads a round's recorded snapshot the same way (features.replay_options), the names of before 2026-11-19
included."""
import unittest

import features
from web_server import GameSession

# The decision loop's switch attributes a started round sets.
KEYS = ('one_press', 'ask_ahead', 'undo', 'reach', 'names', 'links', 'split', 'burn', 'serve_note', 'steps', 'clear',
        'walk', 'go', 'english', 'plate', 'parts', 'work')


class Client:
    def __init__(self, config):
        pass

    def payload(self, state, actions):
        return {'state': state}

    def ask(self, payload):
        raise RuntimeError('test-only')


class Journal:
    def __init__(self, name):
        pass

    def __call__(self, kind, data):
        pass

    def close(self):
        pass


def with_on(base, names, on=True):
    value = {name: dict(item) for name, item in base.items()}
    for name in names:
        value[name]['on'] = on
    return value


def combinations():
    """The defaults (features.json as written), each trial switch on alone and every feature on."""
    base = features.load()
    yield 'defaults', base
    for name, value in base.items():
        if value['stage'] == 'trial':
            yield name, with_on(base, [name])
    yield 'all', with_on(base, base)


def started(on):
    """The switches a round started with these features gives its decision loop."""
    game = GameSession(config=None, client_factory=Client, journal_factory=Journal)
    game.features = on
    try:
        code, body = game.command('/api/start', {'game_id': game.game_id, 'request_id': 'switch-wiring', 'speed': .75})
        if code != 200:
            raise AssertionError(body)
        return {key: getattr(game.ai, key) for key in KEYS}
    finally:
        game.close()


def expected(on):
    """compose_options as the loop holds it: parts and work None when off, and ask_ahead."""
    return {'parts': None, 'work': None, **features.compose_options(on), 'ask_ahead': on['ask_ahead']['on']}


class SwitchWiringTests(unittest.TestCase):
    def test_a_started_round_wires_what_compose_options_gives(self):
        labels = []
        for label, on in combinations():
            with self.subTest(label):
                self.assertEqual(expected(on), started(on))
            labels.append(label)
        self.assertEqual(len(labels), 10)       # defaults, 8 trial switches alone, all on

    def test_with_the_released_switches_off_too(self):
        for label, on in released_off():
            with self.subTest(label):
                self.assertEqual(expected(on), started(on))

    def test_the_session_takes_loop_switches(self):
        for label, on in [*combinations(), *released_off()]:
            with self.subTest(label):
                self.assertEqual(expected(on), features.loop_switches(on))
                self.assertEqual(set(KEYS), set(features.loop_switches(on)))

    def test_replay_reads_a_recorded_snapshot_as_the_round_had_it(self):
        for label, on in [*combinations(), *released_off()]:
            with self.subTest(label):
                round_wide = {key: value for key, value in expected(on).items()
                              if key not in ('one_press', 'undo', 'ask_ahead')}
                self.assertEqual(round_wide, features.replay_options(features.snapshot(on)))

    def test_replay_reads_the_names_of_before_2026_11_19(self):
        none = features.replay_options({})
        self.assertEqual(none, features.replay_options(features.snapshot(with_on(features.load(), features.load(),
                                                                                False))))
        for old, option in (('food_names', 'names'), ('clear_names', 'clear'), ('engine_english', 'english'),
                            ('plate_names', 'plate'), ('serve_note', 'serve_note')):
            with self.subTest(old):
                self.assertEqual({**none, option: True}, features.replay_options({old: {'on': True, 'version': 'v'}}))
                self.assertEqual(none, features.replay_options({old: {'on': False, 'version': 'v'}}))
        self.assertEqual(none, features.replay_options({'wait_note': {'on': True, 'version': 'wait-note-v2'}}))
        text = features.replay_options({'clear_text': {'on': True}})
        self.assertEqual(text, features.replay_options({'clear_text': {'on': True}, 'food_names': {'on': False}}))
        self.assertEqual(text, features.replay_options({name: {'on': True} for name in
                                                        ('food_names', 'clear_names', 'engine_english', 'plate_names')}))


def released_off():
    """Every feature off, and each released feature off alone."""
    base = features.load()
    yield 'none', with_on(base, base, False)
    for name, value in base.items():
        if value['stage'] == 'release':
            yield name + ' off', with_on(base, [name], False)


if __name__ == '__main__':
    unittest.main()
