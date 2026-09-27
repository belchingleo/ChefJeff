import random
import unittest
from kitchen import Kitchen, Food, load_config


class RulesTest(unittest.TestCase):
    def make(self, **updates):
        c = load_config()
        c.update(round_seconds=500, order_count=5, order_patience=300)
        c.update(updates)
        return Kitchen(c)

    def do(self, k, who, command):
        ok, why = k.command(who, command)
        self.assertTrue(ok, (command, why))
        j = k.chefs[who].job
        if j:
            k.advance(j.travel+j.work)
        k.assert_invariants()

    def pot(self, k, heated=0, stage='cooking'):
        s = k.stations['p1']
        s.food = Food('fixture', stage=stage, chopped=k.c['chop_seconds'], heated=heated)
        s.heating = True
        return s

    def test_full_chain_and_automatic_matching(self):
        k = self.make()
        for command in ('fetch','put b1','chop b1','take b1','put p1'):
            self.do(k, 'human', command)
        self.assertIsNone(k.stations['b1'].food)
        self.assertIsNone(k.chefs['human'].hand)
        k.advance(k.c['cook_seconds'])
        self.do(k, 'jev', 'take plates')
        self.do(k, 'jev', 'plate p1')
        self.do(k, 'jev', 'serve')
        self.assertEqual(k.served, 1)
        self.assertEqual(k.money, 30)
        self.assertEqual(k.orders[0]['status'], 'served')

    def test_both_chefs_have_same_abilities(self):
        k = self.make()
        self.assertEqual({a.key for a in k.actions('human') if a.kind!='go'}, {a.key for a in k.actions('jev') if a.kind!='go'})
        for command in ('fetch','put b1','chop b1','take b1','put p1'):
            self.do(k,'jev',command)
        k.advance(k.c['cook_seconds'])
        self.do(k,'human','take plates')
        self.do(k,'human','plate p1')
        self.do(k,'human','serve')
        self.assertEqual(k.served,1)

    def test_chopping_survives_interruption_and_handoff(self):
        k = self.make()
        self.do(k,'human','fetch')
        self.do(k,'human','put b1')
        k.command('human','chop b1')
        k.advance(2)
        k.command('human','stop')
        self.assertAlmostEqual(k.stations['b1'].food.chopped,2)
        self.do(k,'jev','chop b1')
        self.assertEqual(k.stations['b1'].food.stage,'chopped')

    def test_board_and_pot_capacity(self):
        k = self.make(boards=1)
        k.stations['b1'].food=Food('onboard','chopped',6)
        k.chefs['human'].hand=Food('held')
        self.assertFalse(k.command('human','put b1')[0])
        self.pot(k)
        k.chefs['human'].hand.stage='chopped'
        self.assertFalse(k.command('human','put p1')[0])
        self.assertFalse(any('window' in a.key for a in k.actions('human')))
        k.assert_invariants()

    def test_preselected_action_cannot_grab_replacement_food(self):
        k=self.make()
        k.stations['b1'].food=Food('old','chopped',6)
        old=next(a for a in k.actions('human') if a.key=='take b1')
        k.stations['b1'].food=Food('new','chopped',6)
        self.assertFalse(k.start('human',old)[0])

    def test_two_chefs_cannot_duplicate_one_item(self):
        k=self.make()
        k.stations['b1'].food=Food('only','chopped',6)
        k.chefs['human'].location=k.chefs['jev'].location='b1'
        self.assertTrue(k.command('human','take b1')[0])
        self.assertTrue(k.command('jev','take b1')[0])
        k.advance(1)
        self.assertEqual(sum(bool(a.hand) for a in k.chefs.values()),1)
        k.assert_invariants()

    def test_station_is_not_reserved_while_walking(self):
        k=self.make()
        k.stations['b1'].food=Food('only','chopped',6)
        k.command('jev','take b1')
        self.assertIsNone(k.stations['b1'].lock)
        self.do(k,'human','take b1')
        k.advance(5)
        self.assertIsNotNone(k.chefs['human'].hand)
        self.assertIsNone(k.chefs['jev'].hand)
        k.assert_invariants()

    def test_walking_to_a_station_does_not_depend_on_its_contents(self):
        k=self.make()
        self.assertTrue(k.command('jev','go b1')[0])
        k.stations['b1'].food=Food('arrived-later')
        k.advance(3)
        self.assertEqual(k.chefs['jev'].location,'b1')
        self.assertTrue(any(e.get('kind')=='action_done' for e in k.events))

    def test_cooking_continues_while_chef_leaves(self):
        k=self.make()
        s=self.pot(k)
        self.do(k,'jev','go fridge')
        self.assertGreater(s.food.heated,0)
        k.advance(35)
        self.assertTrue(s.fire)
        self.assertEqual((k.burns,k.fires,k.money),(1,1,-5))

    def test_extinguish_and_clear_allows_reuse_without_reignition(self):
        k=self.make()
        s=self.pot(k)
        k.advance(31)
        self.assertFalse(k.command('human','take p1')[0])
        self.do(k,'jev','take extinguisher')
        self.do(k,'jev','extinguish p1')
        k.advance(5)
        self.assertFalse(s.fire)
        self.assertFalse(s.heating)
        self.do(k,'jev','clear p1')
        self.assertIsNone(s.food)
        self.do(k,'jev','put extinguisher')
        k.chefs['jev'].hand=Food('fresh','chopped',6)
        self.do(k,'jev','put p1')
        self.assertTrue(s.heating)
        self.assertEqual(s.food.id,'fresh')

    def test_burnt_food_bad_review_and_penalty(self):
        k=self.make()
        self.pot(k,22,'burnt')
        self.do(k,'jev','take plates')
        self.do(k,'jev','plate p1')
        self.do(k,'jev','serve')
        self.assertEqual((k.served,k.bad_reviews,k.money),(0,1,-15))
        self.assertEqual(k.orders[0]['status'],'rejected')

    def test_food_can_burn_during_pickup(self):
        k=self.make()
        k.chefs['jev'].hand=k.stations['plates'].food;k.stations['plates'].food=None
        self.pot(k,22-k.c['handling_seconds']/2,'ready')
        self.do(k,'jev','plate p1')
        self.assertEqual(k.chefs['jev'].hand.stage,'burnt')

    def test_fire_interrupts_removal(self):
        k=self.make()
        k.chefs['jev'].hand=k.stations['plates'].food;k.stations['plates'].food=None
        s=self.pot(k,30-k.c['handling_seconds']/2,'burnt')
        self.do(k,'jev','plate p1')
        self.assertTrue(s.fire)
        self.assertEqual(k.chefs['jev'].hand.stage,'clean_plate')
        self.assertIsNotNone(s.food)

    def test_taken_food_does_not_keep_burning(self):
        k=self.make()
        k.chefs['jev'].hand=k.stations['plates'].food;k.stations['plates'].food=None
        self.pot(k,13,'ready')
        self.do(k,'jev','plate p1')
        k.advance(35)
        self.assertEqual(k.chefs['jev'].hand.stage,'ready')
        self.assertEqual(k.burns,0)

    def test_expired_order_penalty_only_once(self):
        k=self.make(order_count=2,order_interval=100,order_patience=10)
        k.advance(30)
        self.assertEqual((k.money,k.bad_reviews),(-10,1))

    def test_delivery_at_exact_deadline_is_accepted(self):
        k=self.make(order_count=1,order_patience=load_config()['handling_seconds'])
        a=k.chefs['human']
        a.location='serve'
        a.hand=Food('ready','ready',6,12,plate_id=k.stations['plates'].food.id)
        k.stations['plates'].food=None
        self.do(k,'human','serve')
        self.assertEqual(k.served,1)
        self.assertEqual(k.bad_reviews,0)

    def test_raw_dish_is_not_success(self):
        k=self.make()
        k.chefs['human'].hand=Food('raw')
        self.assertFalse(k.command('human','serve')[0])
        self.assertFalse(k.command('human','plate')[0])
        self.assertEqual(k.money,0)
        self.assertEqual(k.bad_reviews,0)

    def test_fixed_seed_random_interleaving_preserves_items_and_locks(self):
        k=self.make()
        rng=random.Random(42)
        for i in range(1600):
            who=rng.choice(['human','jev'])
            actions=k.actions(who)
            if actions and rng.random()<.2:
                k.start(who,rng.choice(actions))
            k.advance(.1)
            k.assert_invariants()

    def test_drop_and_partner_pickup_preserve_every_food_stage(self):
        for stage in ('raw','chopped','ready','burnt'):
            with self.subTest(stage=stage):
                k=self.make()
                food=Food('held',stage,2.5,13)
                k.chefs['human'].hand=food
                self.do(k,'human','drop')
                self.assertIsNone(k.chefs['human'].hand)
                self.assertIs(k.ground['held'].food,food)
                k.advance(35)
                self.do(k,'jev','pickup held')
                self.assertIs(k.chefs['jev'].hand,food)
                self.assertEqual((food.stage,food.chopped,food.heated),(stage,2.5,13))
                self.assertEqual((k.money,k.burns,k.fires),(0,0,0))
                self.assertFalse(k.ground)
                self.do(k,'jev','drop')
                self.do(k,'jev','pickup held')
                self.assertIs(k.chefs['jev'].hand,food)

    def test_ground_transfer_does_not_need_a_free_workstation(self):
        k=self.make()
        k.stations['b1'].food=Food('onboard')
        k.stations['b2'].food=Food('onboard2')
        k.chefs['human'].location=k.chefs['jev'].location='b1'
        k.chefs['human'].hand=Food('held')
        k.command('jev','chop b1')
        k.advance(.1)
        self.do(k,'human','drop')
        self.assertEqual(k.stations['b1'].lock,'jev')
        self.do(k,'human','pickup held')
        self.assertEqual(k.chefs['human'].hand.id,'held')

    def test_two_chefs_cannot_pick_up_same_ground_item(self):
        k=self.make()
        k.chefs['human'].hand=Food('only')
        self.do(k,'human','drop')
        k.chefs['jev'].location=k.chefs['human'].location
        k.command('human','pickup only')
        k.command('jev','pickup only')
        k.advance(1)
        self.assertEqual(sum(bool(a.hand) for a in k.chefs.values()),1)
        self.assertFalse(k.ground)
        k.assert_invariants()

    def test_interrupted_pickup_releases_food_and_stale_arrival_cancels(self):
        k=self.make()
        k.chefs['human'].hand=Food('only')
        self.do(k,'human','drop')
        k.command('human','pickup only')
        k.advance(k.c['handling_seconds']/2)
        self.assertEqual(k.ground['only'].lock,'human')
        k.command('human','stop')
        self.assertIsNone(k.ground['only'].lock)
        k.command('jev','pickup only')
        self.do(k,'human','pickup only')
        k.advance(5)
        self.assertIsNone(k.chefs['jev'].hand)
        self.assertIsNone(k.chefs['jev'].job)
        k.assert_invariants()

    def test_ground_ready_food_can_be_served_by_partner(self):
        k=self.make()
        k.chefs['human'].hand=Food('ready','ready',6,12,plate_id=k.stations['plates'].food.id)
        k.stations['plates'].food=None
        self.do(k,'human','drop')
        self.do(k,'jev','pickup ready')
        self.do(k,'jev','serve')
        self.assertEqual((k.served,k.money),(1,30))

    def test_ground_menu_ids_remain_stable_and_stale_drop_rejected(self):
        k=self.make()
        k.chefs['human'].hand=Food('one')
        old=next(a for a in k.actions('human') if a.key=='drop')
        self.do(k,'human','go b1')
        self.assertFalse(k.start('human',old)[0])
        self.do(k,'human','drop')
        number=k.menu_numbers()['pickup one']
        self.do(k,'human','pickup one')
        self.do(k,'human','drop')
        self.assertEqual(k.menu_numbers()['pickup one'],number)


if __name__=='__main__':
    unittest.main()
