import unittest,time,json,re
from kitchen import Food,GroundItem,load_config
from spatial_kitchen import SpatialKitchen,tile_key
from web_server import GameSession
from test_web import Client,FakeJournal
from whitebox_server import SpatialJevClient

class SelectedTargetTests(unittest.TestCase):
    def make(self,level=3):return SpatialKitchen({**load_config(),'level':level,'spawn_seed':0})
    def finish(self,k,who,a):
        k.positions[who]=k.path(who,a.target)[-1]
        self.assertTrue(k.start(who,a)[0]);k.advance(.4);k.assert_invariants()
    def test_board_beats_adjacent_bin_when_selected(self):
        k=self.make();k.positions['human']=(2,6);k.chefs['human'].hand=Food('meat')
        a=k.quick_interaction('human',preferred='b1');self.assertEqual(a.key,'put b1')
        self.finish(k,'human',a);self.assertEqual(k.money,0);self.assertEqual(k.stations['b1'].food.id,'meat')
    def test_stove_beats_adjacent_counter_when_selected(self):
        k=self.make();s=k.stations['p1'];k.chefs['human'].hand=Food(s.pot_id,'pot');s.pot_id=None;k.positions['human']=(9,2)
        a=k.quick_interaction('human',preferred='p1');self.assertEqual(a.kind,'return_pot')
        self.finish(k,'human',a);self.assertEqual(s.pot_id,'P1');self.assertIsNone(k.stations['counter18'].food)
    def test_blocked_selected_target_never_discards_or_drops(self):
        k=self.make();k.positions['human']=(2,6);k.chefs['human'].hand=Food('meat');k.stations['b1'].food=Food('other')
        self.assertIsNone(k.quick_interaction('human',preferred='b1'))
        self.assertIsNotNone(k.interaction_hint('human','b1'));self.assertIsNone(k.quick_interaction('human',preferred='p1'))
    def setup_floor_pot(self,k,who):
        s=k.stations['p1'];p=Food(s.pot_id,'pot');s.pot_id=None
        k.ground[p.id]=GroundItem(p,tile_key((9,4)));k.positions[who]=(9,4);k.chefs[who].location=tile_key((9,4))
        k.chefs[who].hand=Food('meat','chopped',chopped=6)
        return p
    def test_load_ground_then_pickup_both_chefs_both_levels(self):
        for level in (1,3):
            for who in ('human','jeff'):
                k=self.make(level);p=self.setup_floor_pot(k,who)
                a=k.quick_interaction(who,preferred='item:P1');self.assertEqual(a.kind,'load_ground')
                self.finish(k,who,a);self.assertIsNone(k.chefs[who].hand);self.assertEqual(p.contents.id,'meat')
                k.advance(5);self.assertEqual(p.contents.heated,0)
                a=k.quick_interaction(who,preferred='item:P1');self.assertEqual(a.kind,'pickup');self.finish(k,who,a)
                self.assertEqual(k.chefs[who].hand.contents.id,'meat');self.assertNotIn('P1',k.ground)
                a=next(a for a in k.actions(who) if a.key=='put pot p1');self.finish(k,who,a);k.advance(2)
                self.assertGreater(k.stations['p1'].food.heated,0)
    def test_ground_pot_raw_vegetables_full_and_competition(self):
        for stage,ingredient in [('raw','beef'),('chopped','lettuce'),('raw','bread')]:
            k=self.make();p=self.setup_floor_pot(k,'human');k.chefs['human'].hand.stage=stage;k.chefs['human'].hand.ingredient=ingredient
            self.assertNotIn('load ground P1',[a.key for a in k.actions('human')])
            self.assertIsNone(k.quick_interaction('human',preferred='item:P1'));self.assertIsNotNone(k.chefs['human'].hand)
        k=self.make();p=self.setup_floor_pot(k,'human');a=next(a for a in k.actions('human') if a.key=='load ground P1')
        k.start('human',a);k.advance(.05)
        k.chefs['jeff'].hand=Food('meat2','chopped');self.assertNotIn('load ground P1',[a.key for a in k.actions('jeff')])
        k.advance(.3);self.assertEqual(p.contents.id,'meat');k.assert_invariants()
    def test_stale_floor_action_rejected(self):
        k=self.make();p=self.setup_floor_pot(k,'human');a=next(a for a in k.actions('human') if a.key=='load ground P1')
        p.contents=Food('other','chopped');k.start('human',a);k.advance(1)
        self.assertEqual(k.chefs['human'].hand.id,'meat');self.assertEqual(p.contents.id,'other');k.assert_invariants()
    def test_counter_pot_loading_same_rules(self):
        for level in (1,3):
            k=self.make(level);p=self.setup_floor_pot(k,'human');del k.ground[p.id];key=next(c for c in k.counters if not k.stations[c].food);k.stations[key].food=p
            a=next(a for a in k.actions('human') if a.key=='load '+key);self.finish(k,'human',a)
            self.assertEqual(p.contents.id,'meat');self.assertIsNone(k.chefs['human'].hand);k.advance(5);self.assertEqual(p.contents.heated,0)
    def test_http_click_walks_there_and_space_uses_the_facing(self):
        g=GameSession(config={**load_config(),'level':3},kitchen_factory=SpatialKitchen,client_factory=Client,journal_factory=FakeJournal);self.addCleanup(g.close)
        def cmd(path,**kw):return g.command('/api/'+path,{'game_id':g.game_id,'request_id':str(time.monotonic_ns()),**kw})
        cmd('start');g.k.positions['human']=(2,6);g.k.facing['human']='right';g.k.chefs['human'].hand=Food('meat')
        self.assertEqual(cmd('select',target='b1')[0],200);g.k.advance(.5)
        state=g.public_state();self.assertEqual(state['interaction_focus'],'b1');self.assertEqual(state['interaction']['key'],'put b1')
        self.assertEqual(cmd('interact',expected_item='meat')[0],200);g.k.advance(.5);self.assertEqual(g.k.stations['b1'].food.id,'meat')
        # Nothing is remembered: turning away changes what Space acts on.
        g.k.facing['human']='left';self.assertEqual(g.public_state()['interaction_focus'],'bin')
        self.assertEqual(cmd('select',target='item:missing')[0],409)
    def test_ground_focus_at_feet_survives_two_space_presses(self):
        g=GameSession(config={**load_config(),'level':3},kitchen_factory=SpatialKitchen,client_factory=Client,journal_factory=FakeJournal);self.addCleanup(g.close)
        def cmd(path,**kw):return g.command('/api/'+path,{'game_id':g.game_id,'request_id':str(time.monotonic_ns()),**kw})
        cmd('start');self.setup_floor_pot(g.k,'human')
        self.assertEqual(cmd('select',target='item:P1')[0],200)
        self.assertEqual(cmd('interact',expected_item='meat')[0],200);g.k.advance(.5)
        self.assertEqual(cmd('interact',expected_item=None)[0],200);g.k.advance(.5)
        self.assertEqual(g.k.chefs['human'].hand.id,'P1');g.k.assert_invariants()
    def test_facing_locks_front_and_explicit_selection_overrides(self):
        k=self.make();k.positions['human']=(2,6);k.chefs['human'].hand=Food('meat')
        for facing,target,kind in [('down','b1','put_board'),('left','bin','discard'),('right','floor_3_6','drop')]:
            k.facing['human']=facing
            focus=k.interaction_target('human');self.assertEqual(focus,target)
            self.assertEqual(k.quick_interaction('human',preferred=focus).kind,kind)
        k.facing['human']='left';self.assertEqual(k.interaction_target('human','b1'),'b1')
        self.assertEqual(k.quick_interaction('human',preferred=k.interaction_target('human','b1')).kind,'put_board')
    def test_facing_ground_pot_and_selected_item_removed(self):
        k=self.make();self.setup_floor_pot(k,'human');k.positions['human']=(8,4);k.facing['human']='right'
        self.assertEqual(k.interaction_target('human'),'item:P1')
        self.assertEqual(k.interaction_cell('human','item:P1'),(9,4))
        del k.ground['P1'];self.assertIsNone(k.quick_interaction('human',preferred='item:P1'))
        self.assertIsNone(k.interaction_cell('human','item:P1'))

    def test_front_before_feet_and_an_idle_station_falls_through(self):
        for level in (1,3):
            k=self.make(level);k.positions['human']=(2,6);k.chefs['human'].hand=None
            k.ground['feet']=GroundItem(Food('feet'),tile_key((2,6)))
            k.ground['front']=GroundItem(Food('front'),tile_key((3,6)))
            k.facing['human']='right'
            self.assertEqual(k.facing_interaction('human')[1].key,'pickup front')
            # Facing an empty board with empty hands: nothing to do there, so the feet item.
            k.facing['human']='down';self.assertIsNone(k.stations['b1'].food)
            focus,a=k.facing_interaction('human');self.assertEqual((focus,a.key),('item:feet','pickup feet'))
            self.finish(k,'human',a)
            self.assertEqual(k.chefs['human'].hand.id,'feet');self.assertIn('front',k.ground)

    def test_feet_do_not_override_explicit_target_or_full_hands(self):
        k=self.make();k.positions['human']=(2,6);k.facing['human']='down'
        k.ground['feet']=GroundItem(Food('feet'),tile_key((2,6)))
        self.assertEqual(k.interaction_target('human','b1'),'b1')
        k.chefs['human'].hand=Food('held')
        focus=k.interaction_target('human');self.assertEqual(focus,'b1')
        self.assertEqual(k.quick_interaction('human',preferred=focus).key,'put b1')

    def test_feet_focus_and_interact_agree_without_mouse_selection(self):
        g=GameSession(config={**load_config(),'level':3},kitchen_factory=SpatialKitchen,client_factory=Client,journal_factory=FakeJournal);self.addCleanup(g.close)
        def cmd(path,**kw):return g.command('/api/'+path,{'game_id':g.game_id,'request_id':str(time.monotonic_ns()),**kw})
        cmd('start');g.k.positions['human']=(2,6);g.k.facing['human']='down';g.k.chefs['human'].hand=None
        g.k.ground['feet']=GroundItem(Food('feet'),tile_key((2,6)))
        state=g.public_state();self.assertEqual(state['interaction_focus'],'item:feet')
        self.assertEqual(state['interaction']['key'],'pickup feet')
        self.assertEqual(cmd('interact',expected_item=None)[0],200);g.k.advance(.5)
        self.assertEqual(g.k.chefs['human'].hand.id,'feet');g.k.assert_invariants()

    def test_focused_ground_ingredient_swaps_without_losing_old_item(self):
        for level in (1,3):
            for cell,explicit in [((2,6),'item:new'),((3,6),None)]:
                k=self.make(level);k.positions['human']=(2,6);k.facing['human']='right'
                k.chefs['human'].hand=Food('old','chopped')
                k.ground['new']=GroundItem(Food('new'),tile_key(cell))
                focus=k.interaction_target('human',explicit);self.assertEqual(focus,'item:new')
                a=k.quick_interaction('human',preferred=focus);self.assertEqual(a.key,'pickup new')
                self.finish(k,'human',a)
                self.assertEqual(k.chefs['human'].hand.id,'new')
                self.assertIn('old',k.ground);self.assertNotIn('new',k.ground)
                self.assertEqual(k.ground['old'].food.stage,'chopped');self.assertEqual(k.money,0)

    def test_new_actions_in_english_model_payload(self):
        k=self.make();self.setup_floor_pot(k,'jeff');payload=SpatialJevClient(k.c,key="offline-test-only").payload(k.snapshot(),k.actions('jeff'))
        self.assertIn('load ground P1',payload['questions']['next_action']['criteria'])
        self.assertFalse(re.search('[\u3400-\u9fff]',json.dumps(payload,ensure_ascii=False)))

if __name__=='__main__':unittest.main()
