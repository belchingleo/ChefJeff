import unittest
from kitchen import Food,Station,load_config
from spatial_kitchen import SpatialKitchen,tile_key
from navigation import Navigation

class SharedWorkTests(unittest.TestCase):
    def make(self):
        k=SpatialKitchen(load_config()|{'level':1,'spawn_seed':0,'round_seconds':500})
        k.stations['b1'].food=Food('shared-food')
        k.positions.update(human=(4,2.49),jeff=(3.3,3.3))
        return k

    def start_pair(self,k,kind='chop',target='b1'):
        command='wash' if kind=='wash' else 'chop '+target
        for who in ('human','jeff'):
            ok,message=k.command(who,command);self.assertTrue(ok,message)
        k.advance(.01)
        self.assertTrue(all(a.job and a.job.working for a in k.chefs.values()))
        k.assert_invariants()

    def test_shared_chop_is_double_rate_and_finishes_only_once(self):
        k=self.make();self.start_pair(k)
        before=k.stations['b1'].food.chopped;k.advance(1)
        self.assertAlmostEqual(k.stations['b1'].food.chopped-before,2)
        k.advance(2.1)
        self.assertEqual(k.stations['b1'].food.stage,'chopped')
        self.assertEqual(k.stations['b1'].food.chopped,k.c['chop_seconds'])
        self.assertTrue(all(a.job is None for a in k.chefs.values()))
        self.assertIsNone(k.stations['b1'].lock)
        k.assert_invariants()

    def test_leaving_keeps_progress_and_transfers_lock(self):
        k=self.make();self.start_pair(k);k.advance(.5)
        k.stop('human');before=k.stations['b1'].food.chopped
        self.assertEqual(k.stations['b1'].lock,'jeff')
        k.advance(1);self.assertAlmostEqual(k.stations['b1'].food.chopped-before,1)
        k.stop('jeff');self.assertIsNone(k.stations['b1'].lock)
        before=k.stations['b1'].food.chopped
        k.command('human','chop b1');k.advance(.5)
        self.assertAlmostEqual(k.stations['b1'].food.chopped-before,.5)
        k.assert_invariants()

    def test_second_chef_reserves_distinct_perpendicular_side(self):
        k=self.make();k.positions['jeff']=(4,2)
        k.command('human','chop b1');k.command('jeff','chop b1')
        a=k.routes['human']['points'][-1];b=k.routes['jeff']['points'][-1]
        self.assertNotEqual(a,b)
        self.assertEqual(a,(4,2.49))
        self.assertIn(b,[(3.3,3.3),(4.7,3.3)])
        k.advance(1);k.assert_invariants()

    def test_middle_board_without_corner_cannot_share(self):
        k=self.make();k.stations['b2'].food=Food('middle')
        k.positions.update(human=(3.3,4.3),jeff=(5,4))
        k.command('human','chop b2');k.advance(.01)
        self.assertNotIn('chop b2',[a.key for a in k.actions('jeff')])
        self.assertFalse(k.command('jeff','chop b2')[0])

    def test_fire_cancels_both_workers(self):
        k=self.make();self.start_pair(k);k.ignite('b1')
        self.assertTrue(all(a.job is None for a in k.chefs.values()))
        self.assertIsNone(k.stations['b1'].lock);k.assert_invariants()

    def test_late_arrival_cannot_reprocess_completed_food(self):
        k=self.make();k.stations['b1'].food.chopped=5.95;k.positions['jeff']=(2,2)
        k.command('human','chop b1');k.command('jeff','chop b1');k.advance(2)
        self.assertEqual(k.stations['b1'].food.chopped,6)
        self.assertTrue(all(a.job is None for a in k.chefs.values()))
        k.assert_invariants()

    def test_future_sink_with_corner_supports_shared_wash(self):
        k=self.make();k.equipment['sink']={'cell':(5,4),'access':(5,3)}
        k.nav=Navigation(k.width,k.height,k.walls,k.equipment,tuple(k.nav.contact_edges.items()),k.rules.cabinet_clearance)
        k.floor=k.nav.floor
        k.floor_places={tile_key(cell):Station(f'地面({cell[0]},{cell[1]})','处理区') for cell in k.floor}
        k.stations['sink'].food=k.stations['plates'].food;k.stations['plates'].food=None
        k.stations['sink'].food.stage='dirty_plate'
        k.configure_operation_points()
        k.positions.update(human=k.operation_point('sink',(5,3)),jeff=k.operation_point('sink',(6,4)))
        self.start_pair(k,'wash','sink')
        before=k.stations['sink'].food.washed;k.advance(.5)
        self.assertAlmostEqual(k.stations['sink'].food.washed-before,1)
        k.stop('human');self.assertEqual(k.stations['sink'].lock,'jeff')
        k.advance(4)
        self.assertEqual(k.stations['sink'].food.stage,'clean_plate')
        self.assertIsNone(k.chefs['jeff'].job);k.assert_invariants()
