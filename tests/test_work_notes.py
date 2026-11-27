"""Work notes (trials, off): own_chain, plate_result, board_taken (work_notes.py). No model."""
import unittest
from unittest.mock import patch

from jev import NO_MEMORY, compose_payload
from kitchen import Food, load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from test_one_press import BOTH, start
from whitebox_server import SpatialJevClient
import features
import work_notes
from jev import DecisionLoop
from links_test_client import Answering
from loop_helpers import Inline

PARTS = {'place': True, 'links_on': True, 'rules': True, 'view': True}
ALL = {'own': True, 'plate': True, 'board': True}


def request(k, work):
    return compose_payload(SpatialJevClient(k.c, key='x'), k, k.snapshot(), k.actions('jeff'), [], None, NO_MEMORY, BOTH,
                           reach=True, names=True, links='partner', split=True, walk=True, clear=True, english=True,
                           plate=True, parts=PARTS, go=True, work=work)


def level5():
    k = SpatialKitchen(level_config(load_config(), 'level-5'))
    k.stations['b1'].food = Food('F50', 'chopped', chopped=2.2, ingredient='beef')
    k.stations['counter5'].food = Food('F51', 'raw', ingredient='tomato')
    return k


class WorkNoteTests(unittest.TestCase):
    def test_own_chain_names_the_hand_over_and_the_other_chefs_work(self):
        criteria = request(level5(), ALL)['questions']['next_action']['criteria']
        self.assertIn('. If nothing else changes first, then you could: Put the held beef (chopped) on Counter',
                      criteria['take b1'])
        self.assertIn('then the other chef could: Take beef (chopped) from Counter', criteria['take b1'])
        self.assertIn('into the frying pan on Stove 1', criteria['take b1'])
        self.assertIn('then you could: Put the held tomato (as fetched) on Board 2 (one item per tile), then Chop',
                      criteria['take counter5'])
        self.assertNotIn('then you could', criteria['take counter2'])          # a clean plate: no run to work

    def test_own_chain_never_puts_the_item_back_where_it_was_taken_from(self):
        k = level5()
        k.stations['b2'].food = Food('F52', 'raw', ingredient='lettuce')    # chopped right there, not taken away
        criteria = request(k, ALL)['questions']['next_action']['criteria']
        self.assertNotIn('on Board 2 (one item per tile), then Chop', criteria.get('take b2', ''))

    def test_plate_result_names_the_dish_and_the_order_waiting(self):
        k = SpatialKitchen(level_config(load_config(), 'level-1'))
        for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
            start(k, 'jeff', key)
        while k.stations['p1'].food.stage != 'ready':
            k.advance(0.1)
        start(k, 'jeff', next(a.key for a in k.actions('jeff') if a.kind == 'take_plate' or
                              (a.kind == 'take_counter' and k.stations[a.target].food.stage == 'clean_plate')))
        criteria = request(k, ALL)['questions']['next_action']['criteria']
        self.assertRegex(criteria['plate p1'], r'\(makes a Steak; order O1 waits for a Steak, [\d.]+ s left\)')

    def test_board_taken_on_a_put_of_something_not_chopped_there(self):
        k = level5()
        start(k, 'jeff', 'take counter2')                                           # a clean plate
        payload = request(k, ALL)
        boards = [key for key in payload['questions']['next_action']['criteria'] if key.startswith('put b')]
        self.assertTrue(boards)
        for key in boards:
            self.assertRegex(payload['questions']['next_action']['criteria'][key],
                             r'\(Board \d is then taken; 1 ingredient you can reach still needs chopping\)')
        for key, text in payload['questions']['put_where']['criteria'].items():
            if key.startswith('put b'):
                self.assertIn('is then taken', text)

    def test_off_the_request_is_as_before_and_each_switch_adds_only_its_own(self):
        k = level5()
        off = request(k, None)
        self.assertEqual(request(k, {'own': False, 'plate': False, 'board': False}), off)
        board_only = request(k, {'own': False, 'plate': False, 'board': True})
        self.assertNotIn('then you could', str(board_only['questions']))
        self.assertEqual(board_only['state']['board_taken_version'], work_notes.BOARD_TAKEN_VERSION)
        self.assertNotIn('own_chain_version', board_only['state'])

    def test_the_loop_works_them_out_off_the_game_loop_and_sends_what_replay_rebuilds(self):
        # The notes fork the kitchen per option: with the links table on they run in its thread, not in the game loop
        # (where they held both chefs still 0.1-0.45 s a request), and the request sent is the one compose_payload builds.
        k = level5()
        records, clock = [], [1000.]
        loop = DecisionLoop(k, Answering(k.c), lambda kind, data: records.append((kind, data)), lambda _: None)
        loop.player_messages = []
        loop.one_press, loop.links, loop.parts, loop.work = dict(BOTH), 'partner', dict(PARTS), dict(ALL)
        loop.reach = loop.names = loop.split = loop.walk = loop.clear = loop.english = loop.plate = loop.go = True
        expected = request(k, ALL)
        with patch('work_notes.apply', wraps=work_notes.apply) as applied, patch('jev.threading.Thread') as thread:
            with patch('jev.time.monotonic', lambda: clock[0]):
                loop.poll()                                    # composed in the game loop: no work notes yet
            self.assertFalse(applied.called)
            thread.call_args.kwargs['target']()                # the links thread
            self.assertTrue(applied.called)
            with patch('jev.time.monotonic', lambda: clock[0]):
                loop.poll()                                    # sent at the next poll
        sent = next(d for kind, d in records if kind == 'ai_request')['payload']
        self.assertEqual(sent['questions'], expected['questions'])
        self.assertIn('then you could', sent['questions']['next_action']['criteria']['take b1'])

    def test_plate_result_and_board_taken_are_released_and_own_chain_is_a_trial(self):
        # plate_result and board_taken released with the 8775 play set as the defaults (0.11.0, 2026-11-27).
        loaded = features.load()
        for name, (short, version) in work_notes.SWITCHES.items():
            stage, on = ('trial', False) if name == 'own_chain' else ('release', True)
            self.assertEqual(loaded[name], {'stage': stage, 'on': on, 'version': version} | {k: v for k, v in loaded[name].items() if k not in ('stage', 'on', 'version')})
        self.assertEqual(work_notes.flags(loaded), {'own': False, 'plate': True, 'board': True})
        off = {**loaded, 'plate_result': {'on': False}, 'board_taken': {'on': False}}
        self.assertIsNone(work_notes.flags(off))
        self.assertEqual(work_notes.flags({**off, 'plate_result': {'on': True}}), {'own': False, 'plate': True, 'board': False})


if __name__ == '__main__':
    unittest.main()
