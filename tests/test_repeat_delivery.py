import unittest
from kitchen import load_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient

class RepeatDeliveryTests(unittest.TestCase):
    def finish(self,k,who,key):
        self.assertTrue(k.command(who,key)[0],key)
        while k.chefs[who].job:k.advance(.05)
        k.assert_invariants()
    def choices(self,k):
        return SpatialJevClient(k.c,key='offline').payload(k.snapshot(),k.actions('jev'))['questions']['next_action']['criteria']
    def test_fetch_throw_fetch_throw_and_then_prep_own_meat(self):
        k=SpatialKitchen(load_config()|{'spawn_seed':0})
        k.positions['jev']=(2,2);k.positions['human']=(3,3)
        self.finish(k,'jev','fetch');first=k.chefs['jev'].hand.id
        self.assertIn('throw b1',self.choices(k));self.finish(k,'jev','throw b1')
        self.assertIn('fetch',self.choices(k));self.finish(k,'jev','fetch');second=k.chefs['jev'].hand.id
        k.advance(.5);self.assertEqual(k.stations['b1'].food.id,first)
        self.assertNotIn('throw b1',self.choices(k))
        self.assertTrue(k.command('human','chop b1')[0]);k.advance(.1)
        self.assertIn('throw b2',self.choices(k));self.finish(k,'jev','throw b2')
        self.finish(k,'jev','fetch');third=k.chefs['jev'].hand.id
        self.finish(k,'jev','put b3');self.finish(k,'jev','chop b3')
        self.assertEqual(k.stations['b1'].food.stage,'chopped')
        self.assertEqual(k.stations['b2'].food.id,second)
        self.assertEqual(k.stations['b3'].food.id,third)
        self.assertEqual(k.stations['b3'].food.stage,'chopped');k.assert_invariants()

    def test_order_and_inventory_information_is_visible_without_future_dishes(self):
        k=SpatialKitchen(load_config()|{'level':2,'spawn_seed':0,'order_seed':42})
        k.advance(65)
        self.finish(k,'jev','fetch')
        state=SpatialJevClient(k.c,key='offline').payload(k.snapshot(),k.actions('jev'))['state']['kitchen']
        self.assertEqual(len([o for o in state['orders'] if o['status']=='pending']),3)
        self.assertTrue(all(o['ingredients']==['bread','lettuce','tomato','beef'] for o in state['orders']))
        self.assertIsNotNone(state['chefs']['jev']['holding'])
        self.assertIn('b1',state['stations']);self.assertIn('b2',state['stations'])
        fresh=SpatialKitchen(load_config()|{'level':3,'order_seed':42})
        state=fresh.snapshot()
        self.assertEqual(len(state['orders']),1);self.assertEqual(state['future_orders'],4)
        self.assertFalse(any(o['status']=='future' for o in state['orders']))
