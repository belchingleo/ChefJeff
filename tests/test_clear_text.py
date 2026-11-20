"""clear_text (clear-text-v1): one switch for food_names, clear_names, engine_english and plate_names.

No model is called: the switch's options are composed locally, and the round is a loopback relay round.
"""
import copy
import unittest

import clear_names
import engine_english
import features
import food_names
import plate_names
import research_replay
from research_record import validate_record
import test_research_save_paths as paths

PARTS = ('names', 'clear', 'english', 'plate')
OLD = ('food_names', 'clear_names', 'engine_english', 'plate_names')


class SwitchTests(unittest.TestCase):
    def test_a_trial_on_by_default_without_a_page_switch(self):
        self.assertEqual(features.current()['clear_text'],
                         {'stage': 'trial', 'on': True, 'version': 'clear-text-v1'})
        for name in OLD:
            self.assertNotIn(name, features.current())

    def test_its_version_names_the_four_parts_it_turns_on(self):
        # A new version of any part needs a new clear_text version too.
        self.assertEqual((food_names.VERSION, clear_names.VERSION, engine_english.VERSION, plate_names.VERSION),
                         ('names-v1', 'clear-names-v3', 'engine-english-v1', 'plate-names-v1'))

    def test_it_turns_the_four_parts_on_and_off_together(self):
        on = features.compose_options(features.current())
        off = features.compose_options({**features.current(), 'clear_text': {**features.current()['clear_text'], 'on': False}})
        self.assertEqual({p: on[p] for p in PARTS}, dict.fromkeys(PARTS, True))
        self.assertEqual({p: off[p] for p in PARTS}, dict.fromkeys(PARTS, False))


class ClearTextReplayTests(paths.SavePathTests):
    def test_a_round_replays_exactly_and_a_record_naming_the_four_switches_does_too(self):
        receipt = self.play()                   # clear_text on, as released
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['features']['clear_text'], {'on': True, 'version': 'clear-text-v1'})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        off = copy.deepcopy(record)
        off['conditions']['features']['clear_text']['on'] = False
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(off)}, {'diverged'})
        # A record from before the merge names the four switches; all four on is this round.
        old = copy.deepcopy(record)
        del old['conditions']['features']['clear_text']
        old['conditions']['features'].update({name: {'on': True, 'version': 'v'} for name in OLD})
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(old)}, {'verified'})
        old['conditions']['features']['plate_names']['on'] = False
        self.assertIn('diverged', {row['status'] for row in research_replay.rebuild_requests(old)})


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(ClearTextReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
