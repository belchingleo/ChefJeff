"""A running station action cannot keep progressing after its operator turns away."""
import time
import unittest

from kitchen import Food, load_config
from spatial_kitchen import SpatialKitchen
from web_server import GameSession
from test_web import Client, FakeJournal


class WorkContinuityTests(unittest.TestCase):
    def make(self, who='human'):
        k=SpatialKitchen(load_config()|{'level':1,'spawn_seed':0})
        other='jeff' if who=='human' else 'human'
        k.positions.update({who:(3.15,3.),other:(10.,6.)})
        k.face(who,1,0)
        k.stations['b1'].food=Food('work-food','raw',ingredient='beef')
        self.assertTrue(k.command(who,'chop b1')[0])
        k.advance(.2)
        self.assertTrue(k.chefs[who].job.working)
        return k

    def test_turning_away_stops_both_chefs_and_keeps_existing_progress(self):
        for who in ('human','jeff'):
            with self.subTest(who=who):
                k=self.make(who);progress=k.stations['b1'].food.chopped
                self.assertTrue(k.face(who,0,1))
                self.assertIsNone(k.chefs[who].job)
                self.assertIsNone(k.stations['b1'].lock)
                k.advance(.5)
                self.assertEqual(k.stations['b1'].food.chopped,progress)
                self.assertTrue(any(e['kind']=='interrupted' and e['actor']==who for e in k.events))
                k.face(who,1,0)
                self.assertTrue(k.command(who,'chop b1')[0])
                k.advance(.2)
                self.assertAlmostEqual(k.stations['b1'].food.chopped,progress+.2)
                k.assert_invariants()

    def test_repeated_aim_at_the_board_does_not_interrupt_work(self):
        k=self.make();job=k.chefs['human'].job
        k.face('human',1,0)
        self.assertIs(k.chefs['human'].job,job)
        progress=k.stations['b1'].food.chopped;k.advance(.2)
        self.assertAlmostEqual(k.stations['b1'].food.chopped,progress+.2)

    def test_a_displaced_worker_cannot_gain_another_tick_of_progress(self):
        k=self.make();progress=k.stations['b1'].food.chopped
        k.positions['human']=(2.,5.)
        k.advance(.2)
        self.assertIsNone(k.chefs['human'].job)
        self.assertEqual(k.stations['b1'].food.chopped,progress)
        k.assert_invariants()

    def test_turning_away_leaves_shared_work_at_the_single_worker_rate(self):
        k=self.make()
        k.positions['jeff']=(4.,2.49)
        self.assertTrue(k.command('jeff','chop b1')[0]);k.advance(.2)
        self.assertTrue(k.chefs['jeff'].job.working)
        progress=k.stations['b1'].food.chopped
        overlap=k.shared_overlap['b1']
        k.face('human',0,1);k.advance(.5)
        self.assertIsNone(k.chefs['human'].job)
        self.assertEqual(k.stations['b1'].lock,'jeff')
        self.assertAlmostEqual(k.stations['b1'].food.chopped-progress,.5)
        self.assertEqual(k.shared_overlap['b1'],overlap)
        k.assert_invariants()

    def test_movement_still_interrupts_work_without_waiting_for_position_reports(self):
        k=self.make();progress=k.stations['b1'].food.chopped
        k.set_manual('human',0,1)
        self.assertIsNone(k.chefs['human'].job)
        k.advance(.2)
        self.assertGreater(k.positions['human'][1],3.)
        self.assertEqual(k.stations['b1'].food.chopped,progress)

    def test_browser_aim_on_an_unsuccessful_interaction_still_stops_old_work(self):
        g=GameSession(kitchen_factory=SpatialKitchen,client_factory=Client,journal_factory=FakeJournal)
        self.addCleanup(g.close)
        def command(path,**extra):
            return g.command('/api/'+path,{'game_id':g.game_id,'request_id':str(time.monotonic_ns()),**extra})
        self.assertEqual(command('start')[0],200)
        k=g.k;k.positions.update(human=(3.15,3.),jeff=(10.,6.))
        k.stations['b1'].food=Food('work-food','raw',ingredient='beef')
        self.assertEqual(command('interact',expected_item=None,aim=[1,0],target='b1')[0],200)
        k.advance(.2);self.assertTrue(k.chefs['human'].job.working)
        progress=k.stations['b1'].food.chopped
        # The new facing points away; there is nothing to use there. Even a rejected
        # interaction must not leave the old job cutting behind the chef's back.
        self.assertEqual(command('interact',expected_item=None,aim=[-1,0],mode='use')[0],409)
        self.assertIsNone(k.chefs['human'].job)
        k.advance(.2)
        self.assertEqual(k.stations['b1'].food.chopped,progress)


if __name__=='__main__':
    unittest.main()
