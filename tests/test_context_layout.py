import math
import unittest
from kitchen import Food, GroundItem, load_config
from spatial_kitchen import SpatialKitchen, EQUIPMENT, FLOOR, neighbors, tile_key, clear_walk_line

class LayoutInteractionTests(unittest.TestCase):
    def make(self,seed=0):
        return SpatialKitchen(load_config() | {'spawn_seed':seed,'round_seconds':500,'order_patience':450,'order_interval':100})
    def press(self,k):
        a=k.quick_interaction('human');self.assertIsNotNone(a)
        self.assertTrue(k.start('human',a)[0]);j=k.chefs['human'].job
        if j:k.advance(j.travel+j.work+.001)
        k.assert_invariants();return a.kind
    def stand(self,k,key):
        k.positions['human']=EQUIPMENT[key]['access'];k.chefs['human'].location=key
    def test_operating_faces_station_from_each_side_and_persists(self):
        for who in ('human','jeff'):
            for cell,expected in (((3,3),'right'),((5,3),'left'),((4,2),'down')):
                k=self.make();k.positions[who]=cell;k.stations['b1'].food=Food('raw')
                self.assertTrue(k.command(who,'chop b1')[0]);k.advance(k.chefs[who].job.travel+.1)
                self.assertEqual(k.snapshot()['chefs'][who]['facing'],expected)
                k.advance(6)
                self.assertIsNone(k.chefs[who].job)
                self.assertEqual(k.snapshot()['chefs'][who]['facing'],expected)
    def test_short_fetch_and_wash_face_target_then_manual_overrides(self):
        k=self.make();self.stand(k,'fridge');self.press(k)
        self.assertEqual(k.snapshot()['chefs']['human']['facing'],'up')
        k.chefs['human'].hand=None
        plate=k.stations['plates'].food;k.stations['plates'].food=None
        plate.stage='dirty_plate';k.stations['sink'].food=plate;self.stand(k,'sink')
        self.assertTrue(k.command('human','wash')[0]);k.advance(.1)
        self.assertEqual(k.snapshot()['chefs']['human']['facing'],'up')
        k.set_manual('human',-1,0);k.advance(.1)
        self.assertEqual(k.snapshot()['chefs']['human']['facing'],'left')

    def test_random_room_assignment_is_reproducible_and_clear(self):
        sides=set()
        for seed in range(12):
            k=self.make(seed);same=self.make(seed)
            self.assertEqual(k.positions,same.positions)
            self.assertEqual(set(k.positions.values()),{(3,4),(10,4)})
            self.assertTrue(all(p in FLOOR for p in k.positions.values()))
            self.assertEqual(k.chefs['human'].location,tile_key(k.positions['human']))
            sides.add(k.positions['human'][0]<7);k.assert_invariants()
        self.assertEqual(sides,{True,False})
    def test_all_equipment_has_a_reachable_service_side(self):
        k=self.make();self.assertEqual(len(k.boards),3);self.assertEqual(len(k.counters),12)
        for key in EQUIPMENT:
            route=k.path('human',key)
            sides=[EQUIPMENT[key]['access']] if EQUIPMENT[key].get('reach')=='corner' else [n for c in EQUIPMENT[key].get('cells',[EQUIPMENT[key]['cell']]) for n in neighbors(c)]
            self.assertIn(route[-1],[k.operation_point(key,side) for side in sides])
            self.assertTrue(all(k.nav.clear_walk_line(a,b) for a,b in zip(route,route[1:])))
    def test_each_accessible_board_side_works_without_circling(self):
        k=self.make()
        for cell in neighbors(EQUIPMENT['b1']['cell']):
            k.positions['human']=cell
            endpoint={(4,2):(4,2.49),(3,3):(3.15,3.3),(5,3):(4.85,3.3)}[cell]
            expected=[cell,endpoint]
            self.assertEqual(k.path('human','b1'),expected)
    def test_swap_drops_at_actual_service_side(self):
        k=self.make();k.positions['human']=(3.,3.);k.chefs['human'].hand=Food('old')
        k.stations['b1'].food=Food('cut','chopped',6)
        k.command('human','take b1');job=k.chefs['human'].job;k.advance(job.travel+job.work+.001)
        self.assertEqual(k.ground['old'].location,'floor_3_3');k.assert_invariants()
    def test_space_cooking_chain_and_washing(self):
        k=self.make();self.stand(k,'fridge');self.assertEqual(self.press(k),'fetch')
        self.stand(k,'b1');self.assertEqual(self.press(k),'put_board')
        self.assertEqual(self.press(k),'chop');self.assertEqual(self.press(k),'take_board')
        self.stand(k,'p1');self.assertEqual(self.press(k),'put_pot');k.advance(12)
        self.stand(k,'plates');self.assertEqual(self.press(k),'take_plate')
        self.stand(k,'p1');self.assertEqual(self.press(k),'plate_pot')
        self.stand(k,'serve');self.assertEqual(self.press(k),'serve');k.advance(8)
        self.stand(k,'returns');self.assertEqual(self.press(k),'take_return')
        self.stand(k,'sink');self.assertEqual(self.press(k),'put_sink')
        self.assertEqual(self.press(k),'wash');self.assertEqual(self.press(k),'take_sink')
        self.assertEqual(k.chefs['human'].hand.stage,'clean_plate')
    def test_space_ground_plating_and_counters(self):
        k=self.make();st=k.stations['p1'];pot=Food(st.pot_id,'pot',contents=Food('meal','ready',6,12));st.pot_id=None
        k.positions['human']=(10.,4.);k.ground[pot.id]=GroundItem(pot,tile_key((10,4)))
        k.chefs['human'].hand=k.stations['plates'].food;k.stations['plates'].food=None
        self.assertEqual(self.press(k),'plate_ground');self.assertIsNone(pot.contents)
        self.stand(k,'counter4');self.assertEqual(self.press(k),'put_counter')
        self.assertEqual(self.press(k),'take_counter')
    def test_space_cancels_work_without_losing_progress(self):
        k=self.make();self.stand(k,'b1');k.stations['b1'].food=Food('meat')
        k.start('human',k.quick_interaction('human'));k.advance(1)
        self.assertEqual(k.quick_interaction('human').kind,'stop')
        self.press(k);self.assertGreater(k.stations['b1'].food.chopped,0)
        self.assertEqual(k.quick_interaction('human').kind,'chop')
    def test_both_bins_discard_food_and_preserve_pot(self):
        for key in ('bin',):
            k=self.make();self.stand(k,key);k.chefs['human'].hand=Food('meat')
            self.assertEqual(self.press(k),'discard');self.assertEqual(k.money,-2)
            st=k.stations['p1'];k.chefs['human'].hand=Food(st.pot_id,'pot',contents=Food('burnt','burnt'));st.pot_id=None
            # Space acts on the faced bin, not on the counter that is slightly nearer.
            target,a=k.facing_interaction('human');self.assertEqual((target,a.kind),(key,'empty_pot'))
            self.assertTrue(k.start('human',a)[0]);j=k.chefs['human'].job;k.advance(j.travel+j.work+.001)
            self.assertIsNone(k.chefs['human'].hand.contents)
    def test_space_drop_pickup_in_open_aisle_and_no_wall_interaction(self):
        k=self.make();k.positions['human']=(6.,4.);k.chefs['human'].hand=Food('meat')
        self.assertEqual(self.press(k),'drop');self.assertEqual(self.press(k),'pickup')
        k.chefs['human'].hand=None;k.positions['human']=(6.,2.)
        # No interaction with the sink through the partition.
        a=k.quick_interaction('human');self.assertTrue(a is None or a.target!='sink')

if __name__=='__main__':unittest.main()


class FacingWallTests(unittest.TestCase):
    def test_facing_a_bare_wall_never_breaks_the_state(self):
        # Level 1's divider (x=7, y=1..3): facing it used to raise on every /api/state.
        from levels import level_config
        from web_server import GameSession
        from spatial_kitchen import SpatialKitchen as SK
        for level in (1, 2, 3):
            with self.subTest(level=level):
                g = GameSession(level_config(load_config(), level), kitchen_factory=SK)
                k = g.k
                for cell in sorted(k.floor):
                    for facing in ('up', 'down', 'left', 'right'):
                        k.positions['human'], k.facing['human'] = cell, facing
                        state = g.public_state()
                self.assertIn('kitchen', state)
                if level == 1:
                    k.positions['human'], k.facing['human'] = (8, 3), 'left'
                    state = g.public_state()
                    self.assertEqual(state['interaction_focus'], 'floor_7_3')
                    self.assertIsNone(state['interaction_cell'])
                    self.assertEqual(state['interaction_hint'], '面前没有可操作目标')
