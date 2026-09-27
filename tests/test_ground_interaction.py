"""Container identity, competing cooks and keyboard interaction; no model calls."""
import unittest
from kitchen import Food, GroundItem, Kitchen, load_config
from spatial_kitchen import SpatialKitchen, tile_key
from web_server import GameSession
from test_web import Client, FakeJournal


class GroundInteractionTests(unittest.TestCase):
    def make(self, spatial=True):
        config=load_config();config.update(round_seconds=500,order_patience=450)
        return (SpatialKitchen if spatial else Kitchen)(config)

    def setup_pot(self,k,who='human',stage='ready'):
        stove=k.stations['p1']
        pot=Food(stove.pot_id,'pot',contents=Food('meal',stage,6,12))
        stove.pot_id=None
        k.ground[pot.id]=GroundItem(pot,tile_key((9,4)) if isinstance(k,SpatialKitchen) else 'p1')
        k.chefs[who].hand=k.stations['plates'].food;k.stations['plates'].food=None
        if isinstance(k,SpatialKitchen):k.positions.update(human=(8.,4.),jev=(10.,4.))
        return pot

    def test_plate_ground_preserves_plate_and_empty_pot_both_chefs(self):
        for spatial in (False,True):
            for who in ('human','jev'):
                for stage in ('ready','burnt'):
                    k=self.make(spatial);pot=self.setup_pot(k,who,stage)
                    plate=k.chefs[who].hand.id;location=k.ground[pot.id].location
                    self.assertTrue(k.command(who,f'plate ground {pot.id}')[0])
                    k.advance(15)
                    self.assertEqual(k.chefs[who].hand.plate_id,plate)
                    self.assertEqual(k.chefs[who].hand.stage,stage)
                    self.assertIsNone(pot.contents)
                    self.assertEqual(k.ground[pot.id].location,location)
                    self.assertIsNone(k.ground[pot.id].lock);k.assert_invariants()

    def test_dirty_plate_unfinished_food_and_empty_pot_cannot_plate(self):
        for invalid in ('dirty_plate','cooking','empty'):
            k=self.make();pot=self.setup_pot(k)
            if invalid=='dirty_plate':k.chefs['human'].hand.stage=invalid
            elif invalid=='empty':pot.contents=None
            else:pot.contents.stage=invalid
            self.assertFalse(k.command('human',f'plate ground {pot.id}')[0]);k.assert_invariants()

    def test_two_chefs_cannot_serve_same_ground_pot_twice(self):
        k=self.make();pot=self.setup_pot(k)
        k.chefs['jev'].hand=k.stations['counter2'].food;k.stations['counter2'].food=None
        for who in ('human','jev'):self.assertTrue(k.command(who,f'plate ground {pot.id}')[0])
        k.advance(2)
        self.assertEqual(sum(bool(c.hand and c.hand.plate_id) for c in k.chefs.values()),1)
        k.assert_invariants()

    def test_pot_moved_while_walking_cancels_plating(self):
        k=self.make();pot=self.setup_pot(k);k.positions['human']=(2.,2.);k.positions['jev']=(9.,4.)
        self.assertTrue(k.command('human',f'plate ground {pot.id}')[0])
        self.assertTrue(k.command('jev',f'pickup {pot.id}')[0]);k.advance(8)
        self.assertEqual(k.chefs['human'].hand.stage,'clean_plate')
        self.assertIs(k.chefs['jev'].hand,pot);self.assertEqual(pot.contents.id,'meal');k.assert_invariants()

    def test_stop_releases_ground_pot_for_pickup(self):
        k=self.make();pot=self.setup_pot(k);k.positions['human']=(9.,4.)
        k.command('human',f'plate ground {pot.id}');k.advance(.05)
        self.assertEqual(k.ground[pot.id].lock,'human')
        self.assertFalse(k.command('jev',f'pickup {pot.id}')[0])
        k.stop('human')
        self.assertTrue(k.command('jev',f'pickup {pot.id}')[0]);k.advance(1);k.assert_invariants()

    def test_stale_plate_action_rejects_replacement_contents(self):
        k=self.make();pot=self.setup_pot(k)
        action=next(a for a in k.actions('human') if a.kind=='plate_ground')
        pot.contents=Food('replacement','ready',6,12)
        self.assertFalse(k.start('human',action)[0]);k.assert_invariants()

    def test_arrival_does_not_chop_food_another_chef_finished(self):
        k=self.make(False);k.stations['b1'].food=Food('meat')
        k.chefs['human'].location='b1'
        k.command('human','chop b1');k.command('jev','chop b1')
        k.chefs['jev'].job.travel=8
        k.advance(16)
        done=[e for e in k.events if e['kind']=='action_done' and e.get('action')=='chop b1']
        self.assertEqual(len(done),1)
        self.assertEqual(k.stations['b1'].food.chopped,k.c['chop_seconds']);k.assert_invariants()

    def test_chopped_food_on_board_is_storage_not_choppable(self):
        k=self.make();k.chefs['jev'].hand=Food('cut','chopped',6)
        self.assertTrue(k.command('jev','put b1')[0]);k.advance(10)
        self.assertNotIn('chop b1',[a.key for a in k.actions('jev')])
        self.assertIn('take b1',[a.key for a in k.actions('jev')]);k.assert_invariants()

    def test_quick_pickup_nearest_reachable_only_and_full_hand_drop(self):
        k=self.make();k.positions['human']=(5.,4.)
        k.ground['near']=GroundItem(Food('near'),tile_key((5,5)))
        k.ground['far']=GroundItem(Food('far'),tile_key((6,5)))
        self.assertEqual(k.quick_interaction('human').key,'pickup near')
        k.positions['human']=(1.,4.);self.assertIsNone(k.quick_interaction('human'))
        k.chefs['human'].hand=Food('held')
        self.assertEqual(k.quick_interaction('human').key,'drop')
        k.assert_invariants()

    def test_quick_pickup_does_not_reach_around_equipment(self):
        k=self.make();k.positions['human']=(3.25,2.9)
        k.ground['blocked']=GroundItem(Food('blocked'),tile_key((5,3)))
        self.assertIsNone(k.quick_interaction('human'))

    def test_quick_http_stale_hand_duplicate_and_pause(self):
        g=GameSession(client_factory=Client,journal_factory=FakeJournal,kitchen_factory=SpatialKitchen)
        self.addCleanup(g.close)
        def cmd(path,request,**kw):return g.command('/api/'+path,dict(game_id=g.game_id,request_id=request,**kw))
        self.assertEqual(cmd('start','start')[0],200)
        g.k.positions['human']=(6.,4.);g.k.chefs['human'].hand=Food('held')
        self.assertEqual(cmd('interact','stale',expected_item=None)[0],409)
        self.assertEqual(cmd('interact','tap',expected_item='held')[0],200)
        g.k.advance(1)
        self.assertEqual(cmd('interact','tap',expected_item='held')[0],200)
        self.assertIsNone(g.k.chefs['human'].hand)
        self.assertEqual(cmd('interact','pickup',expected_item=None)[0],200)
        g.k.advance(1);self.assertEqual(g.k.chefs['human'].hand.id,'held')
        self.assertEqual(cmd('pause','pause')[0],200)
        self.assertEqual(cmd('interact','paused',expected_item='held')[0],409)


if __name__=='__main__':unittest.main()
