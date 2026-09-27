import math
import unittest
from kitchen import Food,GroundItem,Action,Job,load_config
from spatial_kitchen import SpatialKitchen,CHEF_SEPARATION,WALK_SPEED


class GentleCollisionTests(unittest.TestCase):
    def make(self):
        k=SpatialKitchen(load_config()|{'level':1,'spawn_seed':0,'round_seconds':500})
        k.positions.update(human=(9.,4.),jeff=(11.,6.))
        return k

    def item(self,k,key='loose',stage='raw',cell='floor_10_4'):
        food=Food(key,stage)
        k.ground[key]=GroundItem(food,cell)
        return k.ground[key]

    def test_forward_input_slides_and_gently_pushes_without_changing_input(self):
        for who in ('human','jeff'):
            k=self.make();other='jeff' if who=='human' else 'human'
            k.positions.update({who:(9.,4.),other:(10.,4.)});k.set_manual(who,1,0)
            for _ in range(30):
                k.advance(.05)
                self.assertGreaterEqual(math.dist(*k.positions.values()),CHEF_SEPARATION-1e-8)
            self.assertGreater(k.positions[who][0],10.5)
            self.assertGreater(abs(k.positions[who][1]-4),.1)
            self.assertGreater(k.positions[other][0],10.)
            self.assertLess(k.positions[other][0],10.3)

    def test_sprint_bumps_once_per_dash_and_keeps_carried_food(self):
        k=self.make();k.positions.update(human=(9.6,4.),jeff=(10.,4.))
        k.chefs['jeff'].hand=Food('held');k.set_manual('human',1,0);k.sprint('human')
        k.advance(.05);self.assertAlmostEqual(k.positions['jeff'][0],10.25)
        # Repeated contact within the same sprint cannot add more displacement.
        for _ in range(3):
            k.positions['human']=(9.85,4.);k.advance(.05)
        self.assertAlmostEqual(k.positions['jeff'][0],10.25)
        self.assertEqual(k.chefs['jeff'].hand.id,'held')

    def test_bump_is_clipped_by_wall(self):
        k=self.make();k.positions.update(human=(10.8,4.),jeff=(11.2,4.))
        k.set_manual('human',1,0);k.sprint('human');k.advance(.05)
        self.assertLessEqual(k.positions['jeff'][0],11.3+1e-8)
        self.assertTrue(k.nav.walkable_point(k.positions['jeff']))

    def test_manual_contact_slides_without_crossing(self):
        k=self.make();k.positions.update(human=(9.6,4.),jeff=(10.,4.));k.set_manual('human',1,1)
        for _ in range(10):
            k.advance(.05);self.assertGreaterEqual(math.dist(*k.positions.values()),CHEF_SEPARATION-1e-8)
        self.assertGreater(k.positions['human'][1],4.5)

    def test_automatic_route_uses_contact_without_replanning(self):
        k=self.make();k.positions['jeff']=(10.,4.);k.command('human','go floor_11_4')
        self.assertEqual(k.routes['human']['points'],[(9.,4.),(11,4)])
        for _ in range(100):
            k.advance(.05);self.assertGreaterEqual(math.dist(*k.positions.values()),CHEF_SEPARATION-1e-8)
            if not k.chefs['human'].job:break
        self.assertIsNone(k.chefs['human'].job);self.assertEqual(k.positions['human'],(11,4))

    def test_head_on_routes_do_not_pass_through_each_other(self):
        k=self.make();k.positions['jeff']=(11.,4.)
        self.assertTrue(k.command('human','go floor_11_4')[0])
        # Exercise the same route executor directly; the AI menu lists stations, not floor clicks.
        action=Action('go floor_9_4','walk','go','floor_9_4')
        points=k.path('jeff',action.target);length=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
        k.chefs['jeff'].job=Job(99,action,length/WALK_SPEED,0)
        k.routes['jeff']={'job_id':99,'points':points,'length':length}
        for _ in range(120):
            k.advance(.05);self.assertGreaterEqual(math.dist(*k.positions.values()),CHEF_SEPARATION-1e-8)
        self.assertTrue(all(c.job is None for c in k.chefs.values()))

    def test_normal_walk_crosses_food_without_moving_it(self):
        k=self.make();item=self.item(k);k.set_manual('human',1,0);k.advance(.5)
        self.assertGreater(k.positions['human'][0],10)
        self.assertEqual(k.ground_position(item),(10,4));k.assert_invariants()

    def test_nudge_is_quarter_tile_total_not_per_frame(self):
        positions=[]
        for steps in ([.6],[.01]*60):
            k=self.make();item=self.item(k);k.set_manual('human',1,0);self.assertTrue(k.sprint('human'))
            for seconds in steps:k.advance(seconds)
            p=k.ground_position(item);positions.append(p)
            self.assertAlmostEqual(p[0],10.25);self.assertAlmostEqual(p[1],4)
            self.assertLessEqual(k.nudged_distance['human']['loose'],.25+1e-8)
            self.assertEqual(len(k.ground),1);self.assertIsNone(k.chefs['human'].hand)
        self.assertEqual(positions[0],positions[1])

    def test_dash_does_not_push_plates_finished_dishes_or_pots(self):
        for stage in ('clean_plate','dirty_plate','ready','pot'):
            k=self.make();item=self.item(k,stage=stage)
            if stage=='ready':item.food.plate_id='D1'
            k.set_manual('human',1,0);k.sprint('human');k.advance(.6)
            self.assertEqual(k.ground_position(item),(10,4))

    def test_food_overlap_does_not_trigger_assembly_or_chain_reaction(self):
        k=self.make();a=self.item(k);b=self.item(k,'other','chopped','floor_11_4');b.offset=(-.65,0.)
        k.set_manual('human',1,0);k.sprint('human');k.advance(.13)
        self.assertGreater(k.ground_position(a)[0],10)
        self.assertEqual(k.ground_position(b),(10.35,4))
        self.assertEqual(a.food.stage,'raw');self.assertEqual(b.food.stage,'chopped')
        # Co-located food is also legal; there is no physical repulsion.
        b.location=a.location;b.offset=a.offset;k.assert_invariants()

    def test_wall_limits_nudge_and_locked_items_stay_put(self):
        k=self.make();item=self.item(k,cell='floor_11_4');item.offset=(.25,0.)
        k.positions['human']=(10.5,4);k.set_manual('human',1,0);k.sprint('human');k.advance(.3)
        self.assertLessEqual(k.ground_position(item)[0],11.3+1e-8)
        self.assertTrue(k.nav.walkable_point(k.ground_position(item)))
        k=self.make();item=self.item(k);item.lock='jeff'
        k.set_manual('human',1,0);k.sprint('human');k.advance(.5)
        self.assertEqual(k.ground_position(item),(10,4))

    def test_pushed_food_remains_pickable_and_snapshot_matches_position(self):
        k=self.make();item=self.item(k);k.set_manual('human',1,0);k.sprint('human');k.advance(.35)
        k.set_manual('human',0,0)
        self.assertEqual(k.snapshot()['ground'][0]['position'],k.ground_position(item))
        self.assertTrue(k.command('human','pickup loose')[0]);k.advance(1)
        self.assertEqual(k.chefs['human'].hand.id,'loose');self.assertNotIn('loose',k.ground)

    def test_new_sprint_gets_new_budget_and_can_cross_cell_boundary(self):
        k=self.make();item=self.item(k)
        for _ in range(3):
            p=k.ground_position(item);k.positions['human']=(p[0]-.8,p[1])
            k.set_manual('human',1,0);self.assertTrue(k.sprint('human'));k.advance(.4)
            k.set_manual('human',0,0);k.advance(4)
        self.assertAlmostEqual(k.ground_position(item)[0],10.75)
        self.assertEqual(item.location,'floor_11_4')

    def test_one_tile_corridor_head_on_chefs_squeeze_past(self):
        from navigation import Navigation
        k=self.make()
        walls={(x,y) for x in range(14) for y in range(9) if not (1<=x<=12 and y==4)}
        k.nav=Navigation(14,9,walls,{});k.floor=k.nav.floor
        k.positions.update(human=(8.,4.),jeff=(10.,4.))
        k.set_manual('human',1,0);k.set_manual('jeff',-1,0)
        for _ in range(20):
            k.advance(.05)
            self.assertGreaterEqual(math.dist(*k.positions.values()),CHEF_SEPARATION-1e-8)
            self.assertTrue(all(k.nav.walkable_point(p) for p in k.positions.values()))
        self.assertGreater(k.positions['human'][0],k.positions['jeff'][0])

    def test_shared_movement_speed_is_one_and_a_half_for_both_chefs(self):
        self.assertEqual(WALK_SPEED,4.5)
        for who in ('human','jeff'):
            k=self.make();other='jeff' if who=='human' else 'human'
            k.positions.update({who:(8.,4.),other:(11.,6.)})
            k.set_manual(who,1,0);k.advance(.2)
            self.assertAlmostEqual(k.positions[who][0],8.9)
            self.assertEqual(k.snapshot()['map']['walk_speed'],4.5)

    def test_contact_cannot_displace_or_interrupt_active_chop_or_wash(self):
        for kind in ('chop','wash'):
            for worker in ('human','jeff'):
                for boosted in (False,True):
                    with self.subTest(kind=kind,worker=worker,boosted=boosted):
                        k=self.make();mover='jeff' if worker=='human' else 'human'
                        target='b1' if kind=='chop' else 'sink'
                        if kind=='chop':
                            k.stations[target].food=Food('contact-chop')
                            access=(4,2)
                        else:
                            k.stations[target].food=k.stations['plates'].food
                            k.stations['plates'].food=None
                            k.stations[target].food.stage='dirty_plate'
                            access=(8,2)
                        point=k.operation_point(target,access)
                        k.positions[worker]=point
                        k.positions[mover]=(11,5)
                        self.assertTrue(k.command(worker,'chop b1' if kind=='chop' else 'wash')[0])
                        k.advance(.1)
                        job=k.chefs[worker].job
                        self.assertTrue(job.working)
                        food=k.stations[target].food
                        before=food.chopped if kind=='chop' else food.washed
                        # Approach from accessible floor, as in the live sink crash.
                        side=-1 if kind=='chop' else 1
                        k.positions[mover]=(point[0],point[1]+side*CHEF_SEPARATION)
                        k._move_with_chef_contact(mover,(point[0],point[1]-side*.1),boosted)
                        self.assertEqual(k.positions[worker],point)
                        self.assertIs(k.chefs[worker].job,job)
                        self.assertTrue(job.working)
                        self.assertEqual(k.stations[target].lock,worker)
                        k.assert_invariants()
                        k.advance(.2)
                        after=food.chopped if kind=='chop' else food.washed
                        self.assertAlmostEqual(after-before,.2)
                        k.assert_invariants()

    def test_contact_does_not_pause_stove_heating(self):
        k=self.make();pot=k.stations['p1'];pot.food=Food('heating','cooking');pot.heating=True
        k.positions.update(human=(9.6,4.),jeff=(10.,4.))
        k.set_manual('human',1,0);k.sprint('human');k.advance(.2)
        self.assertAlmostEqual(pot.food.heated,.2)
        self.assertTrue(pot.heating);k.assert_invariants()
