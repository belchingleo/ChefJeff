import unittest

from kitchen import Food, load_config
from spatial_kitchen import SpatialKitchen, WALK_SPEED


class OperationDockingTests(unittest.TestCase):
    def make(self):
        config=load_config();config.update(level=2,spawn_seed=0,order_seed=42)
        k=SpatialKitchen(config)
        return k

    def test_both_chefs_walk_to_safe_endpoint_before_chopping(self):
        for who in ('human','jeff'):
            with self.subTest(who=who):
                k=self.make();k.positions[who]=(4,6)
                k.stations['b1'].food=Food('test','raw',ingredient='beef')
                ok,message=k.command(who,'chop b1');self.assertTrue(ok,message)
                self.assertEqual(k.positions[who],(4,6))
                job=k.chefs[who].job
                self.assertAlmostEqual(job.travel,.49/WALK_SPEED)
                k.advance(.05)
                self.assertFalse(job.working)
                self.assertAlmostEqual(k.positions[who][1],6+WALK_SPEED*.05)
                k.advance(.12)
                self.assertTrue(job.working)
                self.assertAlmostEqual(k.positions[who][1],6.49)
                self.assertEqual(k.facing[who],'down')
                self.assertTrue(k.nav.walkable_point(k.positions[who]))
                self.assertFalse(k.nav.walkable_point((4,6.51)))
                k.assert_invariants()

    def test_stop_and_retarget_keep_continuous_real_position(self):
        k=self.make();k.positions['human']=(4,6)
        k.stations['b1'].food=Food('test','raw',ingredient='beef')
        k.command('human','chop b1');k.advance(.05)
        before=k.positions['human'];k.stop('human')
        self.assertEqual(k.positions['human'],before)
        k.command('human','go floor_5_6')
        route=k.routes['human']['points']
        self.assertEqual(route[0],before)
        self.assertTrue(all(k.nav.clear_walk_line(a,b) for a,b in zip(route,route[1:])))

    def test_non_walkable_access_keeps_endpoint(self):
        k=self.make()
        self.assertEqual(k.operation_point('b1',(3,7)),(3,7))
        self.assertEqual(k.operation_point('b2',(6,6)),(6,6.49))
        k.operation_insets={};k.positions['human']=(4,6)
        self.assertEqual(k.path('human','b1'),[(4,6)])

    def test_unsafe_endpoint_rejected(self):
        k=self.make();k.operation_insets['b1']['down']=.51
        with self.assertRaises(ValueError):k.operation_point('b1',(4,6))

    def test_all_maps_keep_countertops_solid_at_contact(self):
        for level in (1,2,3):
            config=load_config();config.update(level=level)
            k=SpatialKitchen(config)
            offsets={'down':(0,-1),'up':(0,1),'right':(-1,0),'left':(1,0)}
            for board,faces in k.operation_insets.items():
                x,y=k.equipment[board]['cell']
                for face in faces:
                    dx,dy=offsets[face]
                    endpoint=k.operation_point(board,(x+dx,y+dy))
                    self.assertTrue(k.nav.walkable_point(endpoint))
                    self.assertFalse(k.nav.walkable_point((x+dx*.49,y+dy*.49)))
                    self.assertFalse(k.nav.clear_walk_line(endpoint,(x,y)))

    def test_back_facing_feet_remain_below_visible_cabinet_front(self):
        for who in ('human','jeff'):
            k=SpatialKitchen(load_config()|{'level':1,'spawn_seed':0})
            k.positions[who]=(4,6)
            k.stations['b3'].food=Food('test-back','raw')
            ok,message=k.command(who,'chop b3');self.assertTrue(ok,message)
            k.advance(k.chefs[who].job.travel+.01)
            self.assertTrue(k.chefs[who].job.working)
            self.assertEqual(k.facing[who],'up')
            self.assertEqual(k.positions[who],(4,6))
            # Cabinet fascia is 22 art px; shoes must stay below it on the floor.
            gap=(k.positions[who][1]-5.5)*52
            self.assertGreaterEqual(gap,22*52/64+8)
            self.assertFalse(k.nav.clear_walk_line(k.positions[who],(4,5)))

    def test_corner_side_worker_stays_left_and_clear_of_north_worker(self):
        k=SpatialKitchen(load_config()|{'level':1,'spawn_seed':0})
        k.positions.update(human=(4,2),jeff=(3,3))
        k.stations['b1'].food=Food('corner')
        for who in ('human','jeff'):self.assertTrue(k.command(who,'chop b1')[0])
        k.advance(.3)
        self.assertEqual(k.facing['jeff'],'right')
        self.assertEqual(k.positions['jeff'],(3.3,3.3))
        self.assertLess(k.positions['jeff'][0],3.5)
        self.assertGreater(k.positions['jeff'][1]-k.positions['human'][1],.8)
        self.assertTrue(all(a.job and a.job.working for a in k.chefs.values()))

    def test_all_station_types_share_side_docking_and_floor_boundaries(self):
        for level in (1,2,3):
            k=SpatialKitchen(load_config()|{'level':level,'spawn_seed':0})
            for key,e in k.equipment.items():
                if e.get('reach')=='corner':continue
                x,y=e['cell']
                for access in k.nav.neighbors((x,y)):
                    p=k.operation_point(key,access)
                    self.assertTrue(k.nav.walkable_point(p),(level,key,access,p))
                    self.assertFalse(k.nav.clear_walk_line(p,(x,y)))
                    if access[1]==y:
                        self.assertAlmostEqual(abs(p[0]-x),.7)
                        self.assertGreaterEqual(p[1],y)
                    if access==(x,y+1):self.assertEqual(p,access)

    def test_level_two_sink_uses_same_side_anchor_as_board(self):
        k=self.make()
        self.assertEqual(k.operation_point('sink',(11,3)),(11.3,3.3))
        k.positions.update(human=(11,3),jeff=(3,2))
        k.stations['sink'].food=k.stations['plates'].food;k.stations['plates'].food=None
        k.stations['sink'].food.stage='dirty_plate'
        self.assertTrue(k.command('human','wash')[0]);k.advance(.2)
        self.assertEqual(k.positions['human'],(11.3,3.3))
        self.assertEqual(k.facing['human'],'right')
        self.assertTrue(k.chefs['human'].job.working)
