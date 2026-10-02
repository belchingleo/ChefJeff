import math
import unittest
from kitchen import load_config,Action,Job
from levels import level_config
from spatial_kitchen import SpatialKitchen,CHEF_SEPARATION,WALK_SPEED,STALL_SECONDS


class RouteStallTests(unittest.TestCase):
    """Two path-following chefs must never lock each other up (same rule for both)."""

    def make(self,human,jeff):
        # Stall re-planning is a service-ruleset rule (movement.stall_replan).
        k=SpatialKitchen(level_config(load_config(),2)|{'spawn_seed':0})
        k.positions.update(human=human,jeff=jeff)
        return k

    def route(self,k,who,target):
        # The route executor shared by clicks and Jeff's station actions.
        k.job_serial+=1
        action=Action('go '+target,'walk','go',target)
        points=k.path(who,target);length=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
        k.chefs[who].job=Job(k.job_serial,action,length/WALK_SPEED,0)
        k.routes[who]={'job_id':k.job_serial,'points':points,'length':length}

    def walk(self,k,seconds,start_jeff=None,delay=0):
        trace=[]
        for i in range(round(seconds/.05)):
            if start_jeff and i==delay:self.route(k,'jeff',start_jeff)
            k.advance(.05)
            trace.append((k.positions['human'],k.positions['jeff']))
            self.assertGreaterEqual(math.dist(*k.positions.values()),CHEF_SEPARATION-1e-8)
            self.assertTrue(all(k.nav.walkable_point(p) for p in k.positions.values()))
            if i>=delay and all(c.job is None for c in k.chefs.values()):break
        return trace

    def test_level_two_passage_head_on_routes_both_arrive(self):
        # Opposing routes through the x=10..11, y=4 gap used to pin both chefs
        # against the long counter's end with constant travel, indefinitely.
        for down,up in (('human','jeff'),('jeff','human')):
            with self.subTest(down=down):
                k=self.make(**{down:(11,3),up:(11,5)})
                self.route(k,down,'counter23');self.route(k,up,'p1')
                self.walk(k,4)
                self.assertTrue(all(c.job is None for c in k.chefs.values()),k.positions)
                self.assertEqual(k.positions[down],k.operation_point('counter23',(9,6)))
                self.assertEqual(k.positions[up],k.operation_point('p1',(9,2)))

    def test_crossing_routes_that_stall_replan_and_both_arrive(self):
        # With the service body clearance the x=10..11 gap above no longer stalls;
        # these crossing routes still do, and must recover by re-planning.
        k=self.make((9,6),(10,4))
        self.route(k,'human','counter5');self.route(k,'jeff','returns')
        self.walk(k,6)
        self.assertTrue(all(c.job is None for c in k.chefs.values()),k.positions)
        self.assertEqual(k.positions['human'],k.operation_point('counter5',(2,2)))
        self.assertEqual(k.positions['jeff'],k.operation_point('returns',(2,5)))
        self.assertTrue(any(e.get('kind')=='route_replanned' for e in k.events))

    def test_route_pushed_off_its_corner_waypoint_recovers(self):
        # Contact pushed the walker back past the counter corner it had already
        # reached; its next static waypoint was then behind the counter.
        k=self.make((6,5),(8,3))
        self.route(k,'human','floor_9_3')
        self.walk(k,4,start_jeff='floor_6_6',delay=3)
        self.assertTrue(all(c.job is None for c in k.chefs.values()),k.positions)
        self.assertEqual(k.positions,{'human':(9,3),'jeff':(6,6)})

    def test_recovery_is_deterministic_for_replay(self):
        traces,events=[],[]
        for _ in range(2):
            k=self.make((11,3),(11,5))
            self.route(k,'human','counter23');self.route(k,'jeff','p1')
            traces.append(self.walk(k,4));events.append(k.events)
        self.assertEqual(traces[0],traces[1]);self.assertEqual(events[0],events[1])

    def test_progressing_route_keeps_static_waypoints(self):
        k=self.make((3,5),(11,2));self.route(k,'human','floor_10_6')
        planned=list(k.routes['human']['points'])
        self.walk(k,4)
        self.assertEqual(k.positions['human'],planned[-1])
        self.assertFalse(any(e.get('kind')=='route_replanned' for e in k.events))

    def test_stall_is_rechecked_without_event_spam_when_goal_is_occupied(self):
        # An idle chef standing on the goal is not a routed deadlock. Arrival blocked
        # by the other chef stops the walker beside them (no back-and-forth sliding),
        # without a re-plan event every check.
        # Pressed against the counter, the idle chef cannot be nudged aside.
        k=self.make((6,2),(9.1,1.7));self.route(k,'human','floor_9_2')
        for _ in range(round(10*STALL_SECONDS/.05)):k.advance(.05)
        self.assertIsNone(k.chefs['human'].job)
        self.assertLess(math.dist(k.positions['human'],(9,2)),1.)
        self.assertLessEqual(sum(e.get('kind')=='route_replanned' for e in k.events),1)

    def test_listing_actions_checks_the_chef_view_once(self):
        # The page polls state several times a second while the chef walks. Routing
        # one new position to every station must not re-check its view per station:
        # that held the session lock for ~0.25 s and made the game clock jump.
        k=self.make((3.3,5.2),(11,2));nav=k.nav;calls=[0];check=nav.clear_walk_line
        stations=[key for key,e in k.equipment.items() if e.get('reach')!='corner']
        for key in stations:k.path('human',key)  # stand points' views, cached for the session
        def counted(a,b):calls[0]+=1;return check(a,b)
        nav.clear_walk_line=counted
        k.positions['human']=(3.4,5.3)
        for key in stations:k.path('human',key)
        corners,_=nav.graph
        # One view check of the new position plus direct lines, not one view per station.
        self.assertLess(calls[0],2*len(corners)+4*len(stations),calls[0])

    def test_detour_planner_keeps_clear_of_the_other_chef(self):
        k=self.make((6,5),(6,2));nav=k.nav
        other=(10.,4.8)
        points=nav.shortest_path_around((9.6,5.2),(10.5,2.),other,CHEF_SEPARATION)
        self.assertEqual(points[0],(9.6,5.2));self.assertEqual(points[-1],(10.5,2.))
        for a,b in zip(points,points[1:]):
            self.assertTrue(nav.clear_walk_line(a,b))
            # Closest approach of each segment to the other chef's centre.
            d=(b[0]-a[0],b[1]-a[1]);t=max(0.,min(1.,((other[0]-a[0])*d[0]+(other[1]-a[1])*d[1])/(d[0]**2+d[1]**2)))
            self.assertGreaterEqual(math.dist((a[0]+t*d[0],a[1]+t*d[1]),other),CHEF_SEPARATION-1e-6)
        with self.assertRaises(ValueError):
            nav.shortest_path_around((6,5),(10,4.9),other,CHEF_SEPARATION)
