import math
import random
import unittest
from kitchen import Food, load_config
from spatial_kitchen import SpatialKitchen, WALK_SPEED, tile_key
from level_one import FLOOR, EQUIPMENT, BLOCKED, shortest_path, clear_walk_line, walkable_point
from whitebox_server import SpatialJevClient
from web_server import GameSession
from test_web import Client, FakeJournal


class SpatialTests(unittest.TestCase):
    def make(self,**overrides):
        config=load_config()
        config.update(spawn_seed=0,round_seconds=500,order_patience=450,order_interval=100,**overrides)
        return SpatialKitchen(config)

    def do(self,k,who,key):
        ok,message=k.command(who,key)
        self.assertTrue(ok,(key,message))
        j=k.chefs[who].job
        if j:k.advance(j.travel+j.work+.00001)
        # Contact can delay arrival beyond the static map's initial ETA.
        for _ in range(100):
            if not k.chefs[who].job:break
            k.advance(.05)
        self.assertIsNone(k.chefs[who].job, 'Action did not finish after contact')
        k.assert_invariants()

    def test_every_floor_cell_and_station_are_reachable_without_crossing_equipment(self):
        for cell in FLOOR:
            route=shortest_path((2,2),cell)
            self.assertEqual(route[-1],cell)
            self.assertTrue(all(p not in BLOCKED for p in route))
            self.assertTrue(all(clear_walk_line(a,b) for a,b in zip(route,route[1:])))
        for e in EQUIPMENT.values():self.assertIn(e['access'],FLOOR)

    def test_open_floor_is_one_straight_diagonal_at_constant_speed(self):
        k=self.make()
        k.command('human','go floor_6_2')
        k.stop('human');k.positions['human']=(2.,3.)
        k.command('human','go floor_3_5')
        self.assertEqual(k.routes['human']['points'],[(2.,3.),(3,5)])
        self.assertAlmostEqual(k.chefs['human'].job.travel,math.sqrt(5)/WALK_SPEED)
        k.advance(.2)
        self.assertAlmostEqual(math.dist((2,3),k.positions['human']),WALK_SPEED*.2)

    def test_single_board_detour_uses_shortest_safe_corners(self):
        route=shortest_path((3,3),(5,3))
        length=sum(math.dist(a,b) for a,b in zip(route,route[1:]))
        # Round b1's back edge (walked up to) between its 0.35-cell side clearances: x 3.15..4.85 at y 2.5.
        self.assertAlmostEqual(length,2*math.hypot(.15,.5)+1.7)
        self.assertTrue(all(clear_walk_line(a,b) for a,b in zip(route,route[1:])))
        self.assertFalse(clear_walk_line((3,3),(5,3)))
        # A diagonal that clips the board cannot become a shortcut.
        self.assertFalse(clear_walk_line((3,3),(4,2)))

    def test_retarget_from_fractional_position_does_not_snap_to_center(self):
        k=self.make();k.positions['human']=(2.3,3.4)
        k.command('human','go floor_3_5')
        self.assertEqual(k.routes['human']['points'],[(2.3,3.4),(3,5)])
        k.advance(.1);current=k.positions['human']
        k.command('human','go floor_2_5')
        self.assertEqual(k.routes['human']['points'],[current,(2,5)])

    def test_the_snapshot_route_is_rounded_like_position(self):
        # Full floats differ in the last digit between machines; Jeff's request must not.
        k=self.make();k.positions['human']=(2.3000000000000003,3.4000000000000004)
        k.command('human','go floor_3_5');k.advance(.13)
        raw=k.routes['human']['points']
        self.assertNotEqual([round(v,4) for v in raw[0]],list(raw[0]))
        chef=k.snapshot()['chefs']['human']
        self.assertEqual(chef['route'],[[round(v,4) for v in point] for point in raw])
        self.assertEqual(chef['route'][0],chef['position'])
        k.advance(5)
        self.assertEqual(k.snapshot()['chefs']['human']['route'],[])

    def test_move_interrupt_keeps_real_position_and_replans_around_wall(self):
        k=self.make();k.command('human','go p1');k.advance(.73)
        position=k.positions['human']
        self.assertNotEqual(position,(2,2))
        k.command('human','go bin')
        self.assertEqual(k.positions['human'],position)
        self.assertAlmostEqual(k.routes['human']['length']/WALK_SPEED,k.chefs['human'].job.travel)
        j=k.chefs['human'].job;k.advance(j.travel+j.work)
        for got,want in zip(k.positions['human'],k.operation_point('bin',EQUIPMENT['bin']['access'])):
            self.assertAlmostEqual(got,want,places=6)
        k.assert_invariants()

    def test_drop_during_walk_uses_current_position_and_can_be_picked_up(self):
        k=self.make();self.do(k,'human','fetch beef')
        k.command('human','go p1');k.advance(2)
        point=k.anchor('human')
        self.do(k,'human','drop')
        item=next(iter(k.ground.values()))
        self.assertEqual(k.cell(item.location),point)
        self.assertNotEqual(k.cell(item.location),(2,2))
        self.do(k,'jeff','pickup F1')
        self.assertEqual(k.chefs['jeff'].hand.id,'F1')
        self.assertFalse(k.ground)

    def test_putting_down_where_the_chef_stands_keeps_the_facing(self):
        # As in Overcooked 2 the carrier just lets go: putting down on the chef's own tile moves and turns nobody
        # (before, the chef was walked to the tile's centre, half a cell back from a counter it stood against).
        for who in ('human','jeff'):
            for facing,offset in (('right',(.3,0)),('left',(-.3,0)),('down',(0,.3)),('up',(0,-.3))):
                k=self.make(level=2);k.positions[who]=(10+offset[0],3+offset[1]);k.facing[who]=facing
                k.chefs[who].hand=Food('T9',ingredient='tomato')
                self.assertTrue(k.command(who,'drop')[0])
                for _ in range(30):
                    k.advance(.02);self.assertEqual(k.facing[who],facing,(who,facing))
                    self.assertEqual(k.positions[who],(10+offset[0],3+offset[1]),(who,facing))
                self.assertEqual([g.location for g in k.ground.values()],['floor_10_3'])
                self.assertNotIn('route_slide',__import__('harness').model_kitchen(k.snapshot())['chefs'][who])

    def test_two_drops_cannot_overwrite_the_same_floor_cell(self):
        k=self.make()
        for who in k.chefs:
            k.positions[who]=(3,4)
            k.chefs[who].hand=Food(who)
        self.assertTrue(k.command('human','drop')[0]);self.assertTrue(k.command('jeff','drop')[0])
        k.advance(1.1)
        self.assertEqual(len(k.ground),1)
        self.assertEqual(sum(a.hand is not None for a in k.chefs.values()),1)
        self.do(k,'jeff','drop')
        self.assertEqual(len(k.ground),2)
        self.assertEqual(len({item.location for item in k.ground.values()}),2)
        k.assert_invariants()

    def test_full_floor_near_chef_does_not_destroy_held_food(self):
        from kitchen import GroundItem
        from level_one import neighbors
        k=self.make();origin=k.anchor('human')
        for i,cell in enumerate([origin]+neighbors(origin)):
            k.ground[str(i)]=GroundItem(Food(str(i)),tile_key(cell))
        k.chefs['human'].hand=Food('held')
        self.assertFalse(k.command('human','drop')[0])
        self.assertEqual(k.chefs['human'].hand.id,'held')
        k.assert_invariants()

    def test_full_chain_ground_handoff_and_serving(self):
        k=self.make()
        for key in ('fetch beef','put b1','chop b1','take b1','drop'):self.do(k,'human',key)
        for key in ('pickup F1','put p1'):self.do(k,'jeff',key)
        k.advance(12)
        for key in ('take plates','plate p1','drop'):self.do(k,'jeff',key)
        for key in ('pickup F1','serve'):self.do(k,'human',key)
        self.assertEqual((k.served,k.money),(1,k.rules.prices['steak']))
        self.assertFalse(k.ground)

    def test_fire_and_extinguish_still_work_with_spatial_walking(self):
        # Configuration is frozen at round start: set the spread interval up front.
        k=self.make(fire_flammability_seconds=1000);self.assertEqual(k.rules.flammability,1000);pot=k.stations['p1'];pot.food=Food('hot','cooking',6,0);pot.heating=True
        k.advance(31)
        self.assertTrue(pot.fire)
        self.do(k,'human','take extinguisher');self.do(k,'human','extinguish p1');self.do(k,'human','put extinguisher')
        self.do(k,'human','take pot p1');self.do(k,'human','discard');self.do(k,'human','put pot p1')
        self.assertIsNone(pot.food);self.assertFalse(pot.fire)
        self.assertEqual(k.money,-7)

    def test_snapshot_and_real_client_payload_describe_spatial_rules(self):
        k=self.make();self.do(k,'human','fetch beef');self.do(k,'human','drop')
        payload=SpatialJevClient(k.c,key='test-only').payload(k.snapshot(),k.actions('jeff'))
        self.assertIn('pickup F1',payload['questions']['next_action']['criteria'])
        self.assertIn('position',payload['state']['kitchen']['chefs']['jeff'])
        self.assertEqual(payload['state']['kitchen']['ground'][0]['position'],(2,2))
        self.assertNotIn('walk_cross_area',payload['state']['rules']['timing'])
        # No free floor destinations; only the partner approach walks to a floor tile.
        self.assertEqual([a.key for a in k.actions('jeff') if a.kind=='go' and a.target.startswith('floor_')],['go partner'])

    def test_walking_keeps_overcooked_pace_at_every_game_clock(self):
        # Reported: the game did not follow the hands. Overcooked 2 walks about 5 counters a real second; local play
        # runs the kitchen clock at 0.75, which used to slow walking with it. Both chefs now walk 5 a real second.
        for speed in (.5, .75, 1):
            g=GameSession(kitchen_factory=SpatialKitchen,client_factory=Client,journal_factory=FakeJournal)
            self.addCleanup(g.close)
            self.assertEqual(g.command('/api/start',{'game_id':g.game_id,'request_id':'s','speed':speed})[0],200)
            self.assertAlmostEqual(g.k.rules.walk_speed*speed,WALK_SPEED)
            self.assertAlmostEqual(g.public_state()['kitchen']['map']['walk_speed']*speed,WALK_SPEED)
            g.k.set_clock(speed)  # applying it again does not compound
            self.assertAlmostEqual(g.k.rules.walk_speed*speed,WALK_SPEED)
        # Without a session clock (simulations, payload fingerprints) the game second is a real second.
        self.assertEqual(self.make().rules.walk_speed,WALK_SPEED)

    def test_web_reset_keeps_spatial_engine_and_new_round_position(self):
        g=GameSession(kitchen_factory=SpatialKitchen,client_factory=Client,journal_factory=FakeJournal)
        self.addCleanup(g.close)
        g.k.positions['human']=(5,4)
        code,_=g.command('/api/reset',{'game_id':g.game_id,'request_id':'reset'})
        self.assertEqual(code,200);self.assertIsInstance(g.k,SpatialKitchen)
        self.assertIn(g.public_state()['kitchen']['chefs']['human']['position'],([3,4],[10,4]))
        self.assertNotEqual(g.k.positions['human'],g.k.positions['jeff'])

    def test_fixed_seed_random_transfers_and_interruptions(self):
        k=self.make();rng=random.Random(18)
        for _ in range(2200):
            who=rng.choice(['human','jeff'])
            actions=k.actions(who)
            if rng.random()<.22 and actions:k.start(who,rng.choice(actions))
            k.advance(.1);k.assert_invariants()  # includes walkable feet for both chefs
