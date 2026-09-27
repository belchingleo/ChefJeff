import unittest
from kitchen import Food, GroundItem, TAKE_KINDS, load_config
from spatial_kitchen import SpatialKitchen, EQUIPMENT, neighbors, tile_key
from whitebox_server import SpatialJevClient


class HandlingTests(unittest.TestCase):
    def make(self):
        c=load_config();c.update(round_seconds=500,order_patience=400)
        return SpatialKitchen(c)
    def do(self,k,who,key):
        ok,msg=k.command(who,key);self.assertTrue(ok,(key,msg))
        j=k.chefs[who].job
        if j:k.advance(j.travel+j.work+1e-6)
        # Contact can delay arrival beyond the static map's initial ETA.
        for _ in range(100):
            if not k.chefs[who].job:break
            k.advance(.05)
        self.assertIsNone(k.chefs[who].job, 'Action did not finish after contact')
        k.assert_invariants()

    def test_fast_fetch_put_take_drop_pickup_and_serve_for_both_chefs(self):
        for who in ('human','jeff'):
            k=self.make()
            for key in ('fetch','put b1','chop b1','take b1','drop','pickup F1','put p1'):
                ok,msg=k.command(who,key);self.assertTrue(ok,msg)
                j=k.chefs[who].job
                self.assertAlmostEqual(j.work,6 if key=='chop b1' else .15)
                k.advance(j.travel+j.work+1e-6)
                for _ in range(100):
                    if not k.chefs[who].job:break
                    k.advance(.05)
                self.assertIsNone(k.chefs[who].job)
            k.advance(12)
            self.do(k,who,'take plates')
            self.do(k,who,'plate p1')
            k.command(who,'serve');j=k.chefs[who].job;self.assertEqual(j.work,.15)
            k.advance(j.travel+j.work+1e-6)
            for _ in range(100):
                if not k.chefs[who].job:break
                k.advance(.05)
            self.assertEqual(k.served,1);k.assert_invariants()

    def test_meat_swaps_for_extinguisher_then_partner_can_pick_meat(self):
        k=self.make();old=Food('meat','chopped',6,3)
        k.chefs['human'].hand=old
        self.do(k,'human','take extinguisher')
        self.assertEqual(k.chefs['human'].hand.id,'E1')
        self.assertIs(k.ground['meat'].food,old)
        self.assertEqual(old.heated,3)
        self.assertEqual(k.money,0)
        self.do(k,'jeff','pickup meat')
        self.assertIs(k.chefs['jeff'].hand,old)
        self.do(k,'human','put extinguisher')
        self.assertEqual(k.stations['extinguisher'].food.id,'E1')

    def test_fetch_with_full_hand_preserves_old_item(self):
        k=self.make();k.chefs['human'].hand=Food('old','ready',6,12)
        self.do(k,'human','fetch')
        self.assertEqual(k.chefs['human'].hand.id,'F1')
        self.assertEqual(k.ground['old'].food.stage,'ready')

    def test_take_board_and_pot_with_full_hands(self):
        for key in ('b1','p1'):
            k=self.make();k.chefs['human'].hand=Food('old')
            k.stations[key].food=Food('new','chopped' if key=='b1' else 'ready',6,12)
            self.do(k,'human',('take ' if key=='b1' else 'take pot ')+key)
            item=k.chefs['human'].hand
            self.assertEqual((item if key=='b1' else item.contents).id,'new')
            self.assertEqual(k.ground['old'].food.id,'old')
            self.assertIsNone(k.stations[key].food)

    def test_ground_swap_uses_picked_up_cell_even_when_neighbors_full(self):
        k=self.make();cell=(3,4);key=tile_key(cell)
        k.positions['human']=cell;k.chefs['human'].hand=Food('old')
        k.ground['new']=GroundItem(Food('new'),key)
        for i,p in enumerate(neighbors(cell)):
            f=Food('block'+str(i));k.ground[f.id]=GroundItem(f,tile_key(p))
        self.do(k,'human','pickup new')
        self.assertEqual(k.chefs['human'].hand.id,'new')
        self.assertEqual(k.ground['old'].location,key)
        self.assertNotIn('new',k.ground)

    def test_full_floor_rejects_tool_swap_without_losing_any_item(self):
        k=self.make();cell=EQUIPMENT['extinguisher']['access']
        k.chefs['human'].hand=Food('old')
        for i,p in enumerate([cell]+neighbors(cell)):
            f=Food('block'+str(i));k.ground[f.id]=GroundItem(f,tile_key(p))
        self.assertFalse(k.command('human','take extinguisher')[0])
        self.assertEqual(k.chefs['human'].hand.id,'old')
        self.assertEqual(k.stations['extinguisher'].food.id,'E1')
        self.assertFalse(k.swap_slots);self.assertFalse(k.drop_locks)

    def test_interrupted_swap_leaves_both_items_untouched(self):
        k=self.make();k.positions['human']=k.operation_point('extinguisher',EQUIPMENT['extinguisher']['access'])
        k.chefs['human'].hand=Food('old')
        k.command('human','take extinguisher');k.advance(.05)
        self.assertTrue(k.drop_locks)
        k.command('human','stop')
        self.assertFalse(k.drop_locks);self.assertFalse(k.swap_slots)
        self.assertEqual(k.chefs['human'].hand.id,'old')
        self.assertEqual(k.stations['extinguisher'].food.id,'E1')
        k.assert_invariants()

    def test_fire_requires_actual_shared_extinguisher_and_allows_ground_handoff(self):
        k=self.make();pot=k.stations['p1'];pot.food=Food('burnt','burnt',6,30);pot.fire=True
        self.assertFalse(k.command('human','extinguish p1')[0])
        self.do(k,'human','take extinguisher')
        self.assertFalse(k.command('jeff','take extinguisher')[0])
        self.assertFalse(k.command('human','discard')[0])
        self.assertFalse(k.command('human','serve')[0])
        self.do(k,'human','drop');self.do(k,'jeff','pickup E1')
        self.do(k,'jeff','extinguish p1')
        self.assertFalse(pot.fire);self.assertEqual(k.chefs['jeff'].hand.id,'E1')
        self.do(k,'jeff','fetch')
        self.assertEqual(k.ground['E1'].food.stage,'extinguisher')

    def test_two_chefs_swapping_for_same_tool_cannot_duplicate(self):
        k=self.make()
        for who in k.chefs:
            k.positions[who]=EQUIPMENT['extinguisher']['access'];k.chefs[who].hand=Food(who)
            self.assertTrue(k.command(who,'take extinguisher')[0])
        k.advance(.2);k.assert_invariants()
        self.assertEqual(sum(a.hand.id=='E1' for a in k.chefs.values()),1)
        self.assertEqual(len(k.ground),1)

    def test_jev_has_drop_discard_auto_swap_and_tool_rules(self):
        k=self.make();k.chefs['jeff'].hand=Food('meat')
        actions=k.actions('jeff');keys={a.key for a in actions}
        self.assertTrue({'drop','discard','take extinguisher','fetch'}<=keys)
        payload=SpatialJevClient(k.c,key='test-only').payload(k.snapshot(),actions)
        self.assertEqual(payload['state']['rules']['timing']['handling'],.15)
        self.assertIn('automatically',payload['state']['rules']['ground'])
        self.do(k,'jeff','discard');self.assertEqual(k.money,-2)
        self.assertIsNone(k.chefs['jeff'].hand)
