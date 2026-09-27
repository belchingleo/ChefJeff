"""Real spatial/HTTP rules with no model calls."""
import math
import time
import unittest
from unittest.mock import patch
from kitchen import Food, GroundItem, load_config
from spatial_kitchen import SpatialKitchen, WALK_SPEED, FLOOR, tile_key, neighbors, walkable_point
from web_server import GameSession
from test_web import Client, FakeJournal

class ControlsTests(unittest.TestCase):
    def make(self):
        c=load_config();c.update(spawn_seed=0,round_seconds=500,order_patience=450)
        return SpatialKitchen(c)

    def throw(self,k,who,target):
        a=k.throw_action(who,target);self.assertIsNotNone(a)
        self.assertTrue(k.start(who,a)[0]);k.advance(1);k.assert_invariants()

    def test_free_aim_exact_range_and_wall(self):
        k=self.make();k.positions['human']=(3.,4.);k.chefs['human'].hand=Food('test')
        self.throw(k,'human',(6,4));self.assertEqual(k.ground['test'].location,'floor_6_4')
        k=self.make();k.positions['human']=(2.,4.);k.positions['jeff']=(11.,6.);k.chefs['human'].hand=Food('test')
        self.throw(k,'human',(40,4));self.assertEqual(k.ground['test'].location,'floor_9_4')
        k=self.make();k.positions['human']=(5.,1.);k.chefs['human'].hand=Food('test')
        self.throw(k,'human',(10,1));self.assertEqual(k.ground['test'].location,'floor_6_1')

    def test_throw_raw_or_chopped_onto_board_both_chefs(self):
        from spatial_kitchen import EQUIPMENT
        for who in ('human','jeff'):
            for stage in ('raw','chopped'):
                k=self.make();k.positions[who]=(3.,4.)
                food=Food('ingredient',stage,2 if stage=='raw' else 6)
                k.chefs[who].hand=food
                self.assertIn('throw b1',[a.key for a in k.actions(who)])
                self.throw(k,who,EQUIPMENT['b1']['cell'])
                self.assertIs(k.stations['b1'].food,food)
                self.assertIsNone(k.chefs[who].hand)
                self.assertNotIn(food.id,k.ground)
                if stage=='raw':self.assertIn('chop b1',[a.key for a in k.actions(who)])

    def test_board_throw_reserves_slot_against_other_throw_or_put(self):
        from spatial_kitchen import EQUIPMENT
        k=self.make();k.positions.update(human=(3.,4.),jeff=(3.,3.))
        k.chefs['human'].hand=Food('flying');k.chefs['jeff'].hand=Food('held')
        stale=k.throw_action('jeff',EQUIPMENT['b1']['cell'])
        k.start('human',k.throw_action('human',EQUIPMENT['b1']['cell']));k.advance(.16)
        self.assertEqual(k.snapshot()['stations']['b1']['incoming_item'],'flying')
        self.assertNotIn('put b1',[a.key for a in k.actions('jeff')])
        self.assertFalse(k.start('jeff',stale)[0])
        k.advance(1)
        self.assertEqual(k.stations['b1'].food.id,'flying')
        self.assertEqual(k.chefs['jeff'].hand.id,'held');k.assert_invariants()

    def test_occupied_board_throw_falls_to_ground(self):
        from spatial_kitchen import EQUIPMENT
        k=self.make();k.positions['human']=(3.,4.)
        k.chefs['human'].hand=Food('new');k.stations['b1'].food=Food('old')
        a=k.throw_action('human',EQUIPMENT['b1']['cell'])
        self.assertNotEqual(a.target,'b1')
        self.throw(k,'human',EQUIPMENT['b1']['cell'])
        self.assertIn('new',k.ground)
        self.assertEqual(k.stations['b1'].food.id,'old')

    def test_board_throw_cannot_cross_wall_and_interrupt_releases_slot(self):
        from spatial_kitchen import EQUIPMENT
        k=self.make();k.positions['human']=(10.,2.);k.chefs['human'].hand=Food('test')
        self.assertFalse(k.can_throw_to('human','b1'))
        k.positions['human']=(3.,4.)
        k.start('human',k.throw_action('human',EQUIPMENT['b1']['cell']));k.advance(.05)
        k.stop('human')
        self.assertEqual(k.chefs['human'].hand.id,'test')
        self.assertFalse(k.board_reserved('b1'));k.assert_invariants()

    def test_diagonal_clip_never_lands_beyond_range_or_wall(self):
        k=self.make();k.positions['human']=(2.3,4.1);k.chefs['human'].hand=Food('test')
        for point in ((20,20),(40,-8),(-40,20),(7,1),(7,7)):
            a=k.throw_action('human',point)
            if a:
                dest=k.cell(a.target)
                self.assertLessEqual(math.dist(k.positions['human'],dest),7.000001)
                self.assertTrue(k.clear_throw_line(k.positions['human'],dest))

    def test_idle_catch_and_full_hand_fall_beside(self):
        for busy_hand in (False,True):
            k=self.make();k.positions.update(human=(8.,4.),jeff=(10.,4.));k.chefs['human'].hand=Food('test')
            if busy_hand:k.chefs['jeff'].hand=Food('held')
            self.throw(k,'human',(10,4))
            if busy_hand:
                self.assertEqual(k.chefs['jeff'].hand.id,'held')
                self.assertIn(k.cell(k.ground['test'].location),neighbors((10,4)))
            else:self.assertEqual(k.chefs['jeff'].hand.id,'test');self.assertNotIn('test',k.ground)

    def test_chopping_and_washing_do_not_catch_or_interrupt(self):
        for task in ('chop b1','wash'):
            k=self.make();k.chefs['human'].hand=Food('test')
            if task=='wash':
                plate=k.stations['plates'].food;k.stations['plates'].food=None;plate.stage='dirty_plate'
                k.stations['sink'].food=plate;k.positions.update(jeff=(8.,2.),human=(9.,2.));k.chefs['jeff'].location='sink'
            else:
                k.stations['b1'].food=Food('cut');k.positions.update(jeff=(3.,3.),human=(5.,4.));k.chefs['jeff'].location='b1'
            k.command('jeff',task);k.advance(.05);job=k.chefs['jeff'].job
            self.throw(k,'human',k.positions['jeff'])
            self.assertIsNone(k.chefs['jeff'].hand);self.assertIs(k.chefs['jeff'].job,job)
            self.assertIn('test',k.ground);self.assertNotEqual(k.cell(k.ground['test'].location),k.anchor('jeff'))

    def test_receiver_moves_or_changes_hands_during_flight(self):
        k=self.make();k.positions.update(human=(5.,4.),jeff=(10.,4.));k.chefs['human'].hand=Food('test')
        k.start('human',k.throw_action('human',(10,4)));k.advance(.15)
        k.positions['jeff']=(10,6);k.advance(1)
        self.assertIsNone(k.chefs['jeff'].hand);self.assertIn('test',k.ground);k.assert_invariants()

    def test_no_free_neighbor_retains_throwable(self):
        k=self.make();k.positions.update(human=(8.,4.),jeff=(10.,4.));k.chefs['human'].hand=Food('test')
        for i,c in enumerate(neighbors((10,4))):k.ground[str(i)]=GroundItem(Food(str(i)),tile_key(c))
        self.assertIsNone(k.throw_action('human',(10,4)));self.assertEqual(k.chefs['human'].hand.id,'test')

    def test_direct_movement_speed_release_and_collision(self):
        for vector in ((1,0),(1,1)):
            k=self.make();k.positions['human']=(5.,4.)
            k.set_manual('human',*vector);k.advance(.2)
            self.assertAlmostEqual(math.dist((5,4),k.positions['human']),WALK_SPEED*.2)
            k.set_manual('human',0,0);p=k.positions['human'];k.advance(.3);self.assertEqual(k.positions['human'],p)
        k=self.make();k.positions['human']=(6.,2.);k.set_manual('human',1,0);k.advance(2)
        self.assertLess(k.positions['human'][0],6.31);self.assertTrue(walkable_point(k.positions['human']));k.assert_invariants()

    def test_keyboard_and_click_take_over_each_other(self):
        k=self.make();k.command('human','go p1');k.advance(.1);p=k.positions['human']
        k.set_manual('human',0,1);self.assertIsNone(k.chefs['human'].job);self.assertEqual(k.positions['human'],p)
        k.command('human','go b1');self.assertFalse(any(k.manual['human']));self.assertIsNotNone(k.chefs['human'].job)

    def setup_partner(self,who='human'):
        k=self.make();other='jeff' if who=='human' else 'human'
        st=k.stations['p1'];k.chefs[who].hand=Food(st.pot_id,'pot',contents=Food('meal','ready',6,12));st.pot_id=None
        k.chefs[other].hand=k.stations['plates'].food;k.stations['plates'].food=None
        k.positions.update({who:(8.,4.),other:(10.,4.)})
        return k,other

    def test_partner_plating_both_directions_keeps_containers(self):
        for who in ('human','jeff'):
            k,other=self.setup_partner(who);plate=k.chefs[other].hand.id
            self.assertTrue(k.command(who,'plate partner')[0]);k.advance(2)
            self.assertEqual(k.chefs[other].hand.plate_id,plate)
            self.assertEqual(k.chefs[who].hand.stage,'pot');self.assertIsNone(k.chefs[who].hand.contents)
            k.assert_invariants()

    def test_partner_move_or_hand_change_cancels_without_loss(self):
        for change in ('move','hand'):
            k,other=self.setup_partner();k.command('human','plate partner')
            if change=='move':k.positions[other]=(3.,4.)
            else:
                k.stations['counter3'].food=k.chefs[other].hand;k.chefs[other].hand=None
            k.advance(2);self.assertEqual(k.chefs['human'].hand.contents.id,'meal');k.assert_invariants()

    def test_partner_change_during_pour_is_rechecked(self):
        k,other=self.setup_partner();k.positions['human']=(10.,4.);k.command('human','plate partner');k.advance(.05)
        k.positions[other]=(3.,4.);k.advance(.2)
        self.assertEqual(k.chefs['human'].hand.contents.id,'meal');self.assertEqual(k.chefs[other].hand.stage,'clean_plate');k.assert_invariants()

    def session(self):
        g=GameSession(client_factory=Client,journal_factory=FakeJournal,kitchen_factory=SpatialKitchen)
        self.addCleanup(g.close);self.cmd(g,'start');return g
    def cmd(self,g,path,**kw):
        return g.command('/api/'+path,dict(game_id=g.game_id,request_id=str(time.monotonic_ns()),**kw))

    def test_input_sequence_release_pause_and_watchdog(self):
        g=self.session();g.k.positions['human']=(5.,4.)
        with patch('web_server.time.monotonic',return_value=100):
            g.last_tick=g.last_seen=100
            self.assertEqual(self.cmd(g,'move',dx=1,dy=0,seq=10)[0],200)
            self.cmd(g,'move',dx=0,dy=0,seq=12);self.cmd(g,'move',dx=1,dy=0,seq=11)
            self.assertEqual(g.k.manual['human'],(0,0))
            self.cmd(g,'move',dx=1,dy=0,seq=13)
        with patch.object(g.ai,'poll'):g.tick(101)
        # Movement expiry is applied at fixed game-tick boundaries: within one tick.
        self.assertLessEqual(abs(g.k.positions['human'][0]-(5+.5*g.speed*WALK_SPEED)),g.k.rules.tick*WALK_SPEED+1e-9)
        self.assertFalse(any(g.k.manual['human']))
        self.cmd(g,'move',dx=1,dy=0,seq=14);self.cmd(g,'pause')
        self.assertFalse(any(g.k.manual['human']))
        self.assertEqual(self.cmd(g,'move',dx=1,dy=0,seq=15)[0],409)

    def test_api_rejects_plate_throw_without_losing_plate(self):
        g=self.session();k=g.k
        plate=k.stations['plates'].food;k.stations['plates'].food=None
        k.chefs['human'].hand=plate;k.positions['human']=(3.,4.)
        for stage in ('clean_plate','dirty_plate'):
            plate.stage=stage
            self.assertEqual(self.cmd(g,'throw',target=[6,4],expected_item=plate.id)[0],409)
            self.assertIs(k.chefs['human'].hand,plate);self.assertFalse(k.projectiles)
        k.assert_invariants()

    def test_api_rejects_invalid_input_and_old_item(self):
        g=self.session()
        for v in (float('nan'),2,True,'1'):
            self.assertEqual(self.cmd(g,'move',dx=v,dy=0,seq=1)[0],400)
        self.assertEqual(self.cmd(g,'throw',target=[3,4],expected_item='missing')[0],409)
        for target in ([float('inf'),4],[1],['a',3]):
            self.assertEqual(self.cmd(g,'throw',target=target,expected_item='x')[0],400)
        g.k.chefs['human'].hand=Food('test');g.k.positions['human']=(3.,4.)
        self.assertEqual(self.cmd(g,'throw',target=[6,4],expected_item='test')[0],200)
        g.k.advance(1);self.assertIn('test',g.k.ground);g.k.assert_invariants()
