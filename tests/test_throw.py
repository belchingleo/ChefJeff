import unittest
from kitchen import Food, GroundItem, load_config
import math
from spatial_kitchen import SpatialKitchen, tile_key, THROW_RANGE, THROW_DIRECTIONS
from level_one import neighbors
from whitebox_server import SpatialJevClient
from levels import level_config


class ThrowTests(unittest.TestCase):
    def make(self, stage='chopped', service=True):
        # service=True: a Level 1 service kitchen, whose ruleset allows passing plates, pots and tools.
        k=SpatialKitchen((level_config(load_config(),1) if service else load_config()) | {'spawn_seed':0})
        k.positions.update(jeff=(5.,5.),human=(8.,4.))
        k.chefs['jeff'].location='b2';k.chefs['human'].location='p1'
        k.chefs['jeff'].hand=Food('pass',stage,6,3)
        return k

    def test_throw_has_flight_then_pickup_without_moving_sender_or_interrupting_receiver(self):
        k=self.make();food=k.chefs['jeff'].hand
        k.command('human','go serve');job=k.chefs['human'].job
        self.assertTrue(k.command('jeff','throw partner')[0]);k.advance(.15)
        self.assertIsNone(k.chefs['jeff'].hand);self.assertIn('pass',k.projectiles)
        self.assertNotIn('pass',k.ground);self.assertIs(k.chefs['human'].job,job)
        self.assertEqual(k.positions['jeff'],(5.,5.));self.assertEqual(k.chefs['jeff'].location,'b2')
        self.assertNotIn('pickup pass',[a.key for a in k.actions('human')])
        k.assert_invariants();k.advance(1)
        self.assertIs(k.ground['pass'].food,food);self.assertIn(k.cell(k.ground['pass'].location),neighbors((8,4)))
        k.command('human','pickup pass');j=k.chefs['human'].job;k.advance(j.travel+j.work+.01)
        self.assertIs(k.chefs['human'].hand,food);self.assertEqual(food.heated,3);k.assert_invariants()

    def test_range_and_wall_block_flight_but_equipment_can_be_cleared(self):
        k=self.make()
        self.assertTrue(k.clear_throw_line((5,5),(8,4)))
        self.assertFalse(k.clear_throw_line((6,2),(8,2)))
        self.assertTrue(k.clear_throw_line((3,3),(5,3))) # board can be thrown over
        self.assertTrue(k.can_throw_to('jeff',tile_key((9,5))))  # exactly the 4-tile limit
        self.assertFalse(k.can_throw_to('jeff',tile_key((9,6))))
        k.positions.update(jeff=(6,1),human=(8,1))
        self.assertEqual(k.handoff_target('jeff'),'floor_6_1')
        self.assertTrue(k.command('jeff','throw partner')[0]);k.advance(1)
        self.assertEqual(k.ground['pass'].location,'floor_6_1')

    def test_fixed_landing_does_not_follow_receiver(self):
        k=self.make();k.command('jeff','throw partner');k.advance(.15)
        landing=k.projectiles['pass']['target'];k.command('human','go bin');k.advance(1)
        self.assertEqual(k.ground['pass'].location,landing)
        self.assertNotEqual(k.positions['human'],k.cell(landing));k.assert_invariants()

    def test_both_roles_can_throw_raw_and_chopped_food(self):
        for who in ('human','jeff'):
            for stage in ('raw','chopped'):
                k=self.make(stage);k.chefs[who].hand,k.chefs['jeff'].hand=k.chefs['jeff'].hand,k.chefs[who].hand
                self.assertEqual(k.throw_range(who),THROW_RANGE)
                self.assertTrue(k.command(who,'throw partner')[0]);k.advance(1)
                other='jeff' if who=='human' else 'human'
                self.assertEqual(k.chefs[other].hand.stage,stage);k.assert_invariants()

    def test_pass_to_a_chopping_teammate_lands_beside_without_interrupting(self):
        for who in ('human','jeff'):
            other='jeff' if who=='human' else 'human'
            k=SpatialKitchen(level_config(load_config(),1)|{'spawn_seed':0})
            plate=k.stations['plates'].food;k.stations['plates'].food=None;plate.stage='clean_plate'
            k.positions.update({other:(3.,4.),who:(3.,6.)});k.chefs[other].location='b2';k.chefs[who].hand=plate
            k.stations['b2'].food=Food('meat');self.assertTrue(k.command(other,'chop b2')[0]);k.advance(.5)
            job=k.chefs[other].job;self.assertTrue(job.working)
            self.assertTrue(k.command(who,'throw partner')[0]);k.advance(1)
            # The chopper keeps chopping; the plate lands intact beside them.
            self.assertIs(k.chefs[other].job,job);self.assertIsNone(k.chefs[other].hand)
            self.assertIs(k.ground[plate.id].food,plate);self.assertEqual(plate.stage,'clean_plate');k.assert_invariants()

    def test_jeffs_throws_are_the_players_aimed_throws(self):
        # No chosen landing points and no station-only throws: Jeff's menu is the player's eight aim
        # directions at full reach, plus a throw toward the player.
        for position in ((5.,5.),(4.,7.),(9.,3.)):
            k=self.make();k.positions['jeff']=position
            menu={a.key:a.target for a in k.actions('jeff') if a.kind=='throw'}
            self.assertEqual(set(menu),{'throw partner'}|{'throw '+name for name in THROW_DIRECTIONS})
            for name,(step,_) in THROW_DIRECTIONS.items():
                self.assertEqual(menu['throw '+name],k.aimed_throw('jeff',step).target)

    def test_extinguisher_cannot_be_thrown_by_either_chef(self):
        # As in Overcooked 2, the extinguisher is carried to the fire, never thrown.
        for who in ('human','jeff'):
            k=self.make(service=True);tool=k.stations['extinguisher'].food;k.stations['extinguisher'].food=None
            k.positions.update(jeff=(5.,5.),human=(7.,5.));k.chefs['jeff'].hand=None;k.chefs['human'].hand=None
            k.chefs[who].hand=tool
            self.assertFalse(k.can_throw(who));self.assertIsNone(k.throw_range(who))
            self.assertFalse(k.command(who,'throw partner')[0])
            self.assertIs(k.chefs[who].hand,tool);self.assertFalse(k.projectiles);k.assert_invariants()

    def test_invariants_hold_while_tableware_flies(self):
        # A passed plate or pot is in no hand and on no station mid-flight.
        for source in ('plates','pot'):
            k=self.make();k.chefs['jeff'].hand=None
            if source=='pot':
                st=k.stations[next(s for s in k.pots if k.stations[s].pot_id)]
                item=Food(st.pot_id,'pot',contents=st.food);st.pot_id,st.food,st.heating=None,None,False
            else:
                item=k.stations[source].food;k.stations[source].food=None
            k.chefs['jeff'].hand=item
            self.assertTrue(k.command('jeff','throw partner')[0])
            for _ in range(12):
                k.advance(.05);k.assert_invariants()
            self.assertFalse(k.projectiles);self.assertIs(k.chefs['human'].hand,item)

    def test_occupied_landing_uses_neighbor_and_full_area_disables_throw(self):
        k=self.make();origin=k.anchor('human')
        for i,p in enumerate([origin]+neighbors(origin)):
            k.ground[str(i)]=GroundItem(Food(str(i)),tile_key(p))
            if i==0:self.assertNotEqual(k.handoff_target('jeff'),tile_key(origin))
        self.assertIsNone(k.handoff_target('jeff'));k.assert_invariants()

    def test_windup_and_flight_reserve_landing_from_drop_and_swap(self):
        k=self.make();k.chefs['human'].hand=Food('held')
        k.command('jeff','throw partner');landing=k.cell(k.chefs['jeff'].job.action.target);k.advance(.05)
        self.assertNotEqual(k.drop_cell('human'),landing)
        self.assertNotEqual(k.swap_cell('human','p1'),landing)
        k.assert_invariants();k.advance(.1)
        self.assertNotEqual(k.drop_cell('human'),landing);k.assert_invariants()
        k.command('human','drop');k.advance(1);k.assert_invariants()
        self.assertEqual(len(k.ground),1)
        self.assertEqual(k.chefs['human'].hand.id,'pass')  # Drop freed hands before arrival.

    def test_cancel_before_release_retains_food_and_releases_slot(self):
        k=self.make();k.command('jeff','throw partner');k.advance(.05);k.command('jeff','stop');k.advance(1)
        self.assertEqual(k.chefs['jeff'].hand.id,'pass');self.assertFalse(k.projectiles)
        self.assertFalse(k.drop_locks);k.assert_invariants()

    def test_departed_projectile_survives_senders_next_job(self):
        k=self.make();k.command('jeff','throw partner');k.advance(.15)
        k.command('jeff','fetch');k.command('jeff','stop');k.advance(1)
        self.assertEqual(k.chefs['human'].hand.id,'pass');k.assert_invariants()

    def test_stale_target_and_competing_drop_revalidate(self):
        k=self.make();action=next(a for a in k.actions('jeff') if a.kind=='throw')
        k.ground['occupied']=GroundItem(Food('occupied'),action.target)
        self.assertFalse(k.start('jeff',action)[0]);self.assertEqual(k.chefs['jeff'].hand.id,'pass')
        k=self.make();k.command('jeff','throw partner')
        k.ground['occupied']=GroundItem(Food('occupied'),k.chefs['jeff'].job.action.target);k.advance(.2)
        self.assertEqual(k.chefs['jeff'].hand.id,'pass');self.assertFalse(k.projectiles);k.assert_invariants()

    def test_ai_sees_handoff_choice_and_flight_state(self):
        k=self.make();client=SpatialJevClient(k.c,key='test-only')
        p=client.payload(k.snapshot(),k.actions('jeff'))
        self.assertIn('throw partner',p['questions']['next_action']['criteria'])
        self.assertEqual(p['state']['kitchen']['map']['throw_range'],THROW_RANGE)
        self.assertIn('throw <direction>',p['state']['rules']['throw'])
        k.command('jeff','throw partner');k.advance(.15)
        self.assertEqual(k.snapshot()['projectiles'][0]['id'],'pass')

    def test_full_swap_destination_filtered_and_rechecked_after_walk(self):
        # Taking the extinguisher is one of the swaps full hands may make (both chefs).
        k=self.make();origin=tuple(round(v) for v in k.path('jeff','extinguisher')[-1])
        self.assertTrue(k.command('jeff','take extinguisher')[0])
        for i,p in enumerate([origin]+neighbors(origin)):
            k.ground[str(i)]=GroundItem(Food(str(i)),tile_key(p))
        k.advance(4)
        self.assertEqual(k.chefs['jeff'].hand.id,'pass');self.assertFalse(k.command('jeff','take extinguisher')[0])
        k.ground.pop('0');self.assertTrue(k.command('jeff','take extinguisher')[0]);k.assert_invariants()
