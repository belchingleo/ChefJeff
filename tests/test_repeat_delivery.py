import unittest
from kitchen import load_config, Food
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient

class RepeatDeliveryTests(unittest.TestCase):
    def finish(self,k,who,key):
        self.assertTrue(k.command(who,key)[0],key)
        while k.chefs[who].job:k.advance(.05)
        k.assert_invariants()
    def choices(self,k):
        return SpatialJevClient(k.c,key='offline').payload(k.snapshot(),k.actions('jeff'))['questions']['next_action']['criteria']
    def test_throws_onto_a_board_then_past_it_once_it_is_taken(self):
        # Jeff throws as the player does: straight up from (4,7), four cells, onto board 1.
        k=SpatialKitchen(load_config()|{'spawn_seed':0})
        k.positions.update(jeff=(4.,7.),human=(8.,6.))
        k.chefs['jeff'].hand=Food('m1','raw',ingredient='beef')
        self.assertEqual(self.choices(k)['throw up'],'Throw the held item up (lands at Board 1)')
        self.finish(k,'jeff','throw up');k.advance(1)
        self.assertEqual(k.stations['b1'].food.id,'m1')
        # Board 1 is taken: the next one comes down short of it, on the floor.
        k.chefs['jeff'].hand=Food('m2','raw',ingredient='beef')
        self.assertTrue(self.choices(k)['throw up'].startswith('Throw the held item up (lands at floor'))
        self.finish(k,'jeff','throw up');k.advance(1)
        self.assertIn('m2',k.ground);self.assertEqual(k.stations['b1'].food.id,'m1');k.assert_invariants()

    def test_order_and_inventory_information_is_visible_without_future_dishes(self):
        k=SpatialKitchen(load_config()|{'level':2,'spawn_seed':0,'order_seed':42})
        k.advance(65)
        self.finish(k,'jeff','fetch')
        state=SpatialJevClient(k.c,key='offline').payload(k.snapshot(),k.actions('jeff'))['state']['kitchen']
        self.assertEqual(len([o for o in state['orders'] if o['status']=='pending']),2)
        self.assertTrue(all(o['ingredients']==['bread','lettuce','tomato','beef'] for o in state['orders']))
        self.assertIsNotNone(state['chefs']['jeff']['holding'])
        self.assertIn('b1',state['stations']);self.assertIn('b2',state['stations'])
        fresh=SpatialKitchen(load_config()|{'level':3,'order_seed':42})
        state=fresh.snapshot()
        self.assertEqual(len(state['orders']),1);self.assertEqual(state['future_orders'],1)  # whether, not how many
        self.assertFalse(any(o['status']=='future' for o in state['orders']))
