import unittest
from kitchen import Food,load_config
from spatial_kitchen import SpatialKitchen


class SurfaceTests(unittest.TestCase):
    """As in Overcooked 2: a board is a counter that also chops, and an ingredient source holds one object on top."""

    def make(self):
        return SpatialKitchen(load_config()|{'level':2,'spawn_seed':0,'round_seconds':500})

    def keys(self,k,who='human'):
        return {a.key:a.kind for a in k.actions(who)}

    def do(self,k,who,command):
        ok,why=k.command(who,command);self.assertTrue(ok,(command,why))
        j=k.chefs[who].job
        if j:k.advance(j.travel+j.work+.01)
        self.assertIsNone(k.chefs[who].job)
        k.assert_invariants()

    def test_a_board_takes_a_plate_and_does_not_chop_it(self):
        k=self.make();plate=k.stations['counter2'].food
        k.chefs['human'].hand,k.stations['counter2'].food=plate,None
        self.assertEqual(self.keys(k).get('put b1'),'put_board')
        self.do(k,'human','put b1')
        self.assertIs(k.stations['b1'].food,plate)
        keys=self.keys(k)
        self.assertNotIn('chop b1',keys)
        self.assertEqual(keys.get('take b1'),'take_board')
        # A prepared ingredient goes onto the plate resting on the board, as on a counter.
        k.chefs['human'].hand=Food('L1','chopped',ingredient='lettuce')
        self.assertIn('assemble b1',self.keys(k))
        self.do(k,'human','assemble b1')
        self.assertIsNone(k.chefs['human'].hand)
        self.assertEqual(list(k.stations['b1'].food.components),['lettuce'])
        self.do(k,'human','take b1')
        self.assertEqual(k.chefs['human'].hand.plate_id,plate.id)

    def test_a_raw_ingredient_on_a_board_still_chops(self):
        k=self.make();k.chefs['human'].hand=Food('T1',ingredient='tomato')
        self.do(k,'human','put b1')
        self.assertEqual(self.keys(k).get('chop b1'),'chop')

    def test_a_source_holds_one_object_and_gives_no_ingredient_meanwhile(self):
        k=self.make();k.chefs['human'].hand=Food('L1','chopped',ingredient='lettuce')
        self.assertEqual(self.keys(k).get('put tomato'),'put_counter')
        self.do(k,'human','put tomato')
        self.assertEqual(k.stations['tomato'].food.id,'L1')
        for who in ('human','jeff'):
            keys=self.keys(k,who)
            self.assertNotIn('fetch tomato',keys)
            self.assertIn('fetch lettuce',keys)
            self.assertEqual(keys.get('take tomato'),'take_counter')
        self.do(k,'human','take tomato')
        self.assertEqual(k.chefs['human'].hand.id,'L1')
        self.assertIsNone(k.stations['tomato'].food)
        k.chefs['human'].hand=None
        self.assertIn('fetch tomato',self.keys(k))

    def test_the_first_source_loses_its_fetch_key_while_occupied(self):
        k=self.make();k.stations['fridge'].food=Food('X1','clean_plate')
        self.assertNotIn('fetch',self.keys(k))
        self.assertIn('take fridge',self.keys(k))

    def test_space_puts_on_an_empty_source_and_takes_from_an_occupied_one(self):
        # The player's control: facing the bread source from below.
        k=self.make();k.positions['human']=(6,2);k.facing['human']='up'
        k.chefs['human'].hand=Food('T1',ingredient='tomato')
        action=k.quick_interaction('human',preferred='bread')
        self.assertEqual((action.key,action.kind),('put bread','put_counter'))
        self.do(k,'human','put bread')
        action=k.quick_interaction('human',preferred='bread')
        self.assertEqual((action.key,action.kind),('take bread','take_counter'))

    def test_space_facing_a_source_puts_on_top_and_facing_away_drops_in_place(self):
        # The player, one step below the bread source: facing it puts the item on top; turned away,
        # however close, Space puts it on the floor in front, as facing any open floor does.
        k=self.make();k.positions['human']=(6,2);k.chefs['human'].hand=Food('T1',ingredient='tomato')
        k.facing['human']='up'
        target,action=k.facing_interaction('human')
        self.assertEqual((target,action.key),('bread','put bread'))
        k.facing['human']='down'
        target,action=k.facing_interaction('human')
        self.assertTrue(target.startswith('floor_'),target)
        self.assertEqual(action.kind,'drop')
        ok,why=k.start('human',action);self.assertTrue(ok,why)
        k.advance(k.chefs['human'].job.travel+k.chefs['human'].job.work+.01)
        self.assertIsNone(k.stations['bread'].food)
        self.assertIn('T1',k.ground)
        k.assert_invariants()

    def test_jeff_puts_on_a_source_only_by_choosing_it(self):
        # Jeff's options name the place: put <source> goes on top, drop goes on the floor beside him.
        k=self.make();k.positions['jeff']=(6,2);k.chefs['jeff'].hand=Food('T1',ingredient='tomato')
        keys=self.keys(k,'jeff')
        self.assertEqual(keys.get('put bread'),'put_counter')
        drop=next(key for key,kind in keys.items() if kind=='drop')
        self.do(k,'jeff',drop)
        self.assertIsNone(k.stations['bread'].food)
        self.assertIn('T1',k.ground)
        k=self.make();k.positions['jeff']=(6,2);k.chefs['jeff'].hand=Food('T1',ingredient='tomato')
        self.do(k,'jeff','put bread')
        self.assertEqual(k.stations['bread'].food.id,'T1')
        self.assertNotIn('T1',k.ground)

    def test_an_ingredient_thrown_onto_an_empty_source_rests_there(self):
        k=self.make();k.chefs['human'].hand=Food('T1',ingredient='tomato')
        self.assertEqual(k.throw_station('human',k.equipment['lettuce']['cell']),'lettuce')
        k.stations['lettuce'].food=Food('X1','clean_plate')
        self.assertIsNone(k.throw_station('human',k.equipment['lettuce']['cell']))


if __name__=='__main__':
    unittest.main()
