import unittest
from kitchen import Food, GroundItem, load_config
import math
from spatial_kitchen import SpatialKitchen, tile_key, neighbors, THROW_RANGE, PASS_RANGE
from whitebox_server import SpatialJevClient


class ThrowTests(unittest.TestCase):
    def make(self, stage='chopped'):
        k=SpatialKitchen(load_config() | {'spawn_seed':0})
        k.positions.update(jeff=(5.,5.),human=(10.,3.))
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
        self.assertIs(k.ground['pass'].food,food);self.assertIn(k.cell(k.ground['pass'].location),neighbors((10,3)))
        k.command('human','pickup pass');j=k.chefs['human'].job;k.advance(j.travel+j.work+.01)
        self.assertIs(k.chefs['human'].hand,food);self.assertEqual(food.heated,3);k.assert_invariants()

    def test_range_and_wall_block_flight_but_equipment_can_be_cleared(self):
        k=self.make()
        self.assertTrue(k.clear_throw_line((5,5),(10,3)))
        self.assertFalse(k.clear_throw_line((6,2),(8,2)))
        self.assertTrue(k.clear_throw_line((3,3),(5,3))) # board can be thrown over
        self.assertTrue(k.can_throw_to('jeff',tile_key((11,5))))
        self.assertFalse(k.can_throw_to('jeff',tile_key((12,4))))
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
            k=SpatialKitchen(load_config()|{'spawn_seed':0})
            plate=k.stations['plates'].food;k.stations['plates'].food=None;plate.stage='clean_plate'
            k.positions.update({other:(3.,4.),who:(3.,6.)});k.chefs[other].location='b2';k.chefs[who].hand=plate
            k.stations['b2'].food=Food('meat');self.assertTrue(k.command(other,'chop b2')[0]);k.advance(.5)
            job=k.chefs[other].job;self.assertTrue(job.working)
            self.assertTrue(k.command(who,'throw partner')[0]);k.advance(1)
            # The chopper keeps chopping; the plate lands intact beside them.
            self.assertIs(k.chefs[other].job,job);self.assertIsNone(k.chefs[other].hand)
            self.assertIs(k.ground[plate.id].food,plate);self.assertEqual(plate.stage,'clean_plate');k.assert_invariants()

    def test_extinguisher_passes_within_short_range_for_both_chefs(self):
        for who in ('human','jeff'):
            other='jeff' if who=='human' else 'human'
            # About 5.4 tiles apart: the pass falls short, on the floor at the 3-tile limit.
            k=self.make();tool=k.stations['extinguisher'].food;k.stations['extinguisher'].food=None
            k.chefs['jeff'].hand=None;k.chefs[who].hand=tool;start=k.positions[who]
            self.assertEqual(k.throw_range(who),PASS_RANGE)
            self.assertTrue(k.command(who,'throw partner')[0]);k.advance(1)
            self.assertIsNone(k.chefs[other].hand);self.assertIs(k.ground[tool.id].food,tool)
            self.assertLessEqual(math.dist(start,k.cell(k.ground[tool.id].location)),PASS_RANGE+1e-8);k.assert_invariants()
            # Within range an idle, empty-handed teammate catches it.
            k=self.make();tool=k.stations['extinguisher'].food;k.stations['extinguisher'].food=None
            k.positions.update(jeff=(5.,5.),human=(7.,5.));k.chefs['jeff'].hand=None;k.chefs[who].hand=tool
            self.assertTrue(k.command(who,'throw partner')[0]);k.advance(1)
            self.assertIs(k.chefs[other].hand,tool);k.assert_invariants()

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
        self.assertIn('Decide the destination',p['state']['rules']['throw'])
        k.command('jeff','throw partner');k.advance(.15)
        self.assertEqual(k.snapshot()['projectiles'][0]['id'],'pass')

    def test_full_swap_destination_filtered_and_rechecked_after_walk(self):
        k=self.make();origin=tuple(round(v) for v in k.path('jeff','fridge')[-1])
        self.assertTrue(k.command('jeff','fetch')[0])
        for i,p in enumerate([origin]+neighbors(origin)):
            k.ground[str(i)]=GroundItem(Food(str(i)),tile_key(p))
        k.advance(4)
        self.assertEqual(k.chefs['jeff'].hand.id,'pass');self.assertFalse(k.command('jeff','fetch')[0])
        k.ground.pop('0');self.assertTrue(k.command('jeff','fetch')[0]);k.assert_invariants()
