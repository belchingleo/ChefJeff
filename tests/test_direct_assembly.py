"""Direct assembly conserves containers and rechecks asynchronous handoffs."""
import unittest
from kitchen import Food,load_config
from spatial_kitchen import SpatialKitchen,tile_key
from whitebox_server import SpatialJevClient
from model_language import english_data
import json,re

class DirectAssemblyTests(unittest.TestCase):
    def make(self):return SpatialKitchen({**load_config(),'level':3,'spawn_seed':0,'order_seed':42})
    def plate(self,k,who,station='plates',parts=()):
        p=k.stations[station].food;k.stations[station].food=None
        for name in parts:
            p=k.merge_plate(p,Food('test-'+name+station,'ready' if name=='beef' else 'raw' if name=='bread' else 'chopped',ingredient=name))
        k.chefs[who].hand=p
        return p
    def do(self,k,who,key):
        a=next(a for a in k.actions(who) if a.key==key)
        k.positions[who]=k.path(who,a.target)[-1]
        self.assertTrue(k.start(who,a)[0]);k.advance(.3);k.assert_invariants()
    def test_board_to_held_plate_both_chefs(self):
        for who in ('human','jeff'):
            for board in ('b1','b2','b3'):
                k=self.make();self.plate(k,who,parts=('bread',))
                k.stations[board].food=Food('veg','chopped',ingredient='lettuce')
                self.do(k,who,'assemble '+board)
                self.assertEqual(set(k.chefs[who].hand.components),{'bread','lettuce'})
                self.assertIsNone(k.stations[board].food)
    def test_board_raw_beef_veg_duplicate_and_dirty_rejected(self):
        for ingredient,stage,parts,dirty in [('beef','chopped',(),False),('tomato','raw',(),False),('tomato','chopped',('tomato',),False),('tomato','chopped',(),True)]:
            k=self.make();p=self.plate(k,'human',parts=parts)
            if dirty:p.stage='dirty_plate'
            k.stations['b1'].food=Food('veg',stage,ingredient=ingredient)
            self.assertNotIn('assemble b1',[a.key for a in k.actions('human')])
    def test_partner_ingredient_and_plate_merge_both_directions(self):
        for who in ('human','jeff'):
            other='jeff' if who=='human' else 'human'
            for donor_plate in (False,True):
                k=self.make();k.positions.update(human=(9,4),jeff=(10,4))
                self.plate(k,other,parts=('bread','lettuce','tomato'))
                if donor_plate:self.plate(k,who,'counter2',('beef',))
                else:k.chefs[who].hand=Food('meat','ready')
                self.do(k,who,'plate partner')
                self.assertEqual(k.dish(k.chefs[other].hand),'burger')
                if donor_plate:self.assertEqual(k.chefs[who].hand.id,'D2');self.assertEqual(k.chefs[who].hand.stage,'clean_plate')
                else:self.assertIsNone(k.chefs[who].hand)
    def test_counter_plate_merge_leaves_original_empty_plate(self):
        for who in ('human','jeff'):
            k=self.make();self.plate(k,who,parts=('beef',))
            p=k.stations['counter2'].food
            for name in ('bread','lettuce','tomato'):p=k.merge_plate(p,Food('x'+name,'raw' if name=='bread' else 'chopped',ingredient=name))
            k.stations['counter2'].food=p
            self.do(k,who,'merge counter2')
            self.assertEqual(k.dish(k.chefs[who].hand),'burger');self.assertEqual(k.chefs[who].hand.plate_id,'D1')
            self.assertEqual(k.stations['counter2'].food,Food('D2','clean_plate'))
    def test_merge_duplicates_and_dirty_rejected_burnt_preserved(self):
        k=self.make();a=self.plate(k,'human',parts=('beef',));b=self.plate(k,'jeff','counter2',('beef',))
        self.assertFalse(k.can_merge_plates(a,b));b.components=('bread',);b.stage='burnt'
        merged,empty=k.merge_plates(a,b);self.assertEqual(merged.stage,'burnt');self.assertEqual(empty.id,'D2')
        a.stage='dirty_plate';self.assertFalse(k.can_merge_plates(a,b))
    def test_partner_rechecks_same_id_changed_components(self):
        k=self.make();k.positions.update(human=(9,4),jeff=(10,4));p=self.plate(k,'jeff',parts=('bread',))
        k.chefs['human'].hand=Food('veg','chopped',ingredient='tomato')
        a=next(a for a in k.actions('human') if a.key=='plate partner');self.assertTrue(k.start('human',a)[0]);k.advance(.05)
        k.chefs['jeff'].hand=k.merge_plate(p,Food('lettuce','chopped',ingredient='lettuce'))
        k.advance(.3);self.assertEqual(k.chefs['human'].hand.id,'veg');self.assertNotIn('tomato',k.chefs['jeff'].hand.components);k.assert_invariants()
    def test_board_rechecks_arrival_and_lock(self):
        k=self.make();self.plate(k,'human');k.stations['b1'].food=Food('veg','chopped',ingredient='tomato')
        a=next(a for a in k.actions('human') if a.key=='assemble b1')
        k.stations['b1'].lock='jeff';self.assertNotIn('assemble b1',[a.key for a in k.actions('human')]);k.start('human',a);k.advance(12)
        self.assertEqual(k.chefs['human'].hand.stage,'clean_plate');self.assertIsNotNone(k.stations['b1'].food)
    def test_space_at_hatch_explains_missing_bread_without_dropping(self):
        k=self.make();self.plate(k,'human',parts=('beef','lettuce','tomato'));k.positions['human']=(11,4)
        self.assertIsNone(k.quick_interaction('human'));self.assertIn('面包',k.interaction_hint('human'))
        k.chefs['human'].hand=k.merge_plate(k.chefs['human'].hand,Food('bun',ingredient='bread'))
        self.assertEqual(k.quick_interaction('human').key,'serve');self.assertIsNone(k.interaction_hint('human'))
        k.orders[0].update(dish='burger',status='pending',deadline=100)
        self.do(k,'human','serve');self.assertEqual(k.served,1)
    def test_english_model_has_all_boards_and_new_actions(self):
        k=self.make();self.plate(k,'jeff');k.stations['b2'].food=Food('veg','chopped',ingredient='tomato')
        payload=SpatialJevClient(k.c,key="offline-test-only").payload(k.snapshot(),k.actions('jeff'))
        rendered=json.dumps(english_data(payload),ensure_ascii=False)
        self.assertFalse(re.search('[\u3400-\u9fff]',rendered))
        self.assertIn('assemble b2',rendered)
        for b in ('b1','b2','b3'):self.assertIn(b,payload['state']['kitchen']['stations'])

if __name__=='__main__':unittest.main()
