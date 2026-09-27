import unittest
from kitchen import Kitchen, Food, load_config
from spatial_kitchen import SpatialKitchen, EQUIPMENT


class CompletionTests(unittest.TestCase):
    def near_win(self, kitchen_type=Kitchen, who='human', **config):
        c=load_config();c.update(config)
        k=kitchen_type(c);k.advance(50)
        k.served=2;k.money=60
        for order in k.orders[:2]:order['status']='served'
        chef=k.chefs[who];chef.location='serve';chef.hand=Food('last','ready',6,12,plate_id=k.stations['plates'].food.id)
        k.stations['plates'].food=None
        if isinstance(k,SpatialKitchen):k.positions[who]=k.operation_point('serve',EQUIPMENT['serve']['access'])
        self.assertTrue(k.command(who,'serve')[0])
        return k

    def test_either_chef_ends_at_third_delivery_in_both_kitchens(self):
        for kind in (Kitchen,SpatialKitchen):
            for who in ('human','jeff'):
                with self.subTest(kitchen=kind.__name__,chef=who):
                    k=self.near_win(kind,who);k.advance(20)
                    self.assertTrue(k.ended);self.assertTrue(k.won())
                    self.assertEqual(k.served,3)
                    self.assertAlmostEqual(k.time,50.15)
                    self.assertTrue(any(o['status']=='future' for o in k.orders))
                    self.assertEqual(k.snapshot()['settlement'],{
                        'remaining_seconds':129,'time_bonus':129,'total_income':219})
                    before=k.snapshot();k.advance(1000);k._end()
                    self.assertEqual(k.snapshot(),before)
                    self.assertFalse(k.command(who,'fetch')[0])
                    self.assertEqual(sum(e['kind']=='round_end' for e in k.events),1)
                    k.assert_invariants()

    def test_winning_delivery_prevents_later_same_step_action_and_expiry(self):
        k=self.near_win()
        k.orders[2]['deadline']=50.15
        k.orders[3].update(status='pending',deadline=50.15)
        k.chefs['jeff'].location='bin';k.chefs['jeff'].hand=Food('other')
        self.assertTrue(k.command('jeff','discard')[0])
        k.advance(1)
        self.assertEqual((k.money,k.bad_reviews),(90,0))
        self.assertIsNotNone(k.chefs['jeff'].hand)
        self.assertEqual(k.orders[3]['status'],'pending')

    def test_bonus_does_not_make_up_missing_income_or_excess_bad_reviews(self):
        for updates in ({'target_money':100},{'max_bad_reviews':1}):
            k=self.near_win(**updates)
            if 'max_bad_reviews' in updates:k.bad_reviews=2
            k.advance(.2)
            self.assertEqual(k.served,3)
            self.assertFalse(k.ended);self.assertEqual(k.time_bonus,0)
            self.assertIsNone(k.snapshot()['settlement'])

    def test_failed_round_has_no_time_bonus(self):
        k=Kitchen();k.advance(10)
        for order in k.orders:order['status']='rejected'
        k.advance(.05)
        self.assertTrue(k.ended);self.assertFalse(k.won())
        self.assertGreater(k.reward_seconds,0);self.assertEqual(k.time_bonus,0)

    def test_reward_uses_whole_seconds_and_configured_rate(self):
        k=self.near_win(time_bonus_per_second=2)
        k.advance(.15)
        self.assertEqual(k.time_bonus,258)
        self.assertEqual(k.money,90)
