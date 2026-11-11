import math
import unittest
from kitchen import Food,Station,load_config
from spatial_kitchen import SpatialKitchen,tile_key
from navigation import Navigation

class SharedWorkTests(unittest.TestCase):
    def make(self):
        # A 3 s chop leaves room to watch shared rates and hand-offs, whatever the shipped duration.
        k=SpatialKitchen(load_config()|{'level':1,'spawn_seed':0,'round_seconds':500,'chop_seconds':3})
        k.stations['b1'].food=Food('shared-food')
        # Both where a routed chef stands on b1's north and west sides, so neither slides before working.
        k.positions.update(human=(4,2.49),jeff=k.operation_point('b1',(3,3)))
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

    def test_player_joins_a_shared_chop_where_they_stand(self):
        # Jeff chops b1 from the north; the player, pressed against b1's west side and facing it, joins
        # with E, sliding onto b1's row centre and up to the edge a routed chef stands at.
        k=self.make();k.positions.update(jeff=(4,2.49),human=(3.1,3.2));k.facing.update(jeff='down',human='right')
        self.assertTrue(k.command('jeff','chop b1')[0]);k.advance(.01)
        focus,action=k.facing_interaction('human','use')
        self.assertEqual((focus,action.key),('b1','chop b1'))
        self.assertTrue(k.start('human',action)[0]);k.advance(.2)
        self.assertEqual(k.positions['human'],(k.operation_point('b1',(3,3))[0],3.))
        self.assertTrue(all(a.job and a.job.working for a in k.chefs.values()))
        k.assert_invariants()
        # From the same (north) side, beside Jeff and within half a cell of the centre line, the
        # player joins too, as in Overcooked 2.
        k=self.make();k.positions.update(jeff=(4.,2.49),human=(3.55,2.49));k.facing.update(jeff='down',human='down')
        self.assertTrue(k.command('jeff','chop b1')[0]);k.advance(.01)
        self.assertEqual(k.selected_station('human'),'b1')
        self.assertEqual(k.path('human','b1'),[k.positions['human']])
        self.assertTrue(k.command('human','chop b1')[0]);k.advance(.2)
        self.assertTrue(all(a.job and a.job.working for a in k.chefs.values()))
        k.assert_invariants()

    def test_second_chef_reserves_a_distinct_side(self):
        k=self.make();k.positions['jeff']=(4,2)
        k.command('human','chop b1');k.command('jeff','chop b1')
        a=k.routes['human']['points'][-1];b=k.routes['jeff']['points'][-1]
        self.assertEqual(a,(4,2.49))
        # Jeff, standing behind the player's spot, does not chop from there: it takes a spot of its own
        # with its hands over the board, beside the player or on another side.
        self.assertTrue(k.in_work_reach('b1',b));self.assertGreaterEqual(math.dist(a,b),.4)
        k.advance(1);k.assert_invariants()

    def test_middle_board_is_shared_face_to_face(self):
        # Level 1's b2 sits between b1 and b3: Jeff chops it from the west, and the player standing on the
        # free east side, facing it, joins with E; both work and the chop runs at the shared rate.
        k=self.make();k.stations['b2'].food=Food('middle','raw',ingredient='beef')
        k.positions.update(jeff=(3.15,4.),human=(4.85,4.));k.facing.update(jeff='right',human='left')
        self.assertTrue(k.command('jeff','chop b2')[0]);k.advance(.01)
        focus,action=k.facing_interaction('human','use')
        self.assertEqual((focus,action.key),('b2','chop b2'))
        self.assertTrue(k.start('human',action)[0]);k.advance(.2)
        self.assertTrue(all(a.job and a.job.working and a.job.action.target=='b2' for a in k.chefs.values()))
        self.assertTrue(any(e.get('kind')=='shared_work_join' for e in k.events))
        before=k.stations['b2'].food.chopped;k.advance(1);self.assertAlmostEqual(k.stations['b2'].food.chopped-before,2)
        k.assert_invariants()

    def test_fire_cancels_both_workers(self):
        k=self.make();self.start_pair(k);k.ignite('b1')
        self.assertTrue(all(a.job is None for a in k.chefs.values()))
        self.assertIsNone(k.stations['b1'].lock);k.assert_invariants()

    def test_late_arrival_cannot_reprocess_completed_food(self):
        k=self.make();k.stations['b1'].food.chopped=k.c['chop_seconds']-.05;k.positions['jeff']=(2,2)
        k.command('human','chop b1');k.command('jeff','chop b1');k.advance(2)
        self.assertEqual(k.stations['b1'].food.chopped,k.c['chop_seconds'])
        self.assertTrue(all(a.job is None for a in k.chefs.values()))
        k.assert_invariants()

    def test_future_sink_with_corner_supports_shared_wash(self):
        k=self.make();k.equipment['sink']={'cell':(5,4),'access':(5,3)}
        k.nav=Navigation(k.width,k.height,k.walls,k.equipment,k.rules.cabinet_clearance)
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
        self.assertEqual(k.stations[k.dryer].food.stage,'clean_plate')
        self.assertIsNone(k.chefs['jeff'].job);k.assert_invariants()


class WorkReachTests(unittest.TestCase):
    """Chopping needs the hands over the board (WORK_REACH); both chefs may chop a one-sided board."""

    def make(self, human, jeff):
        # Level 2's b1 at (4,7) is worked only from the north tile (4,6).
        k=SpatialKitchen(load_config()|{'level':2,'spawn_seed':0,'round_seconds':500})
        k.stations['b1'].food=Food('x',ingredient='lettuce')
        k.positions.update(human=human,jeff=jeff);k._face_vector('human',0,1);k._face_vector('jeff',0,1)
        k.reported['human']=True   # the player at the keyboard works where they stand
        return k

    def test_the_player_does_not_chop_from_the_next_cell(self):
        # Diagonal from the board, one cell along the counter: as in Overcooked 2 (four cells, never a
        # diagonal) the board is not picked, so E has nothing to chop; started anyway, it is refused.
        k=self.make((4.95,6.5),(4.,6.49));k._face_vector('human',-.95,.5)
        self.assertNotIn('b1',k.selectable_stations('human'))
        self.assertIsNone(k.facing_interaction('human','use')[1])
        action=next(a for a in k.actions('human') if a.key=='chop b1')
        ok,message=k.start('human',action)
        self.assertFalse(ok);self.assertIn('正前方',message);self.assertIsNone(k.chefs['human'].job)

    def test_both_chefs_chop_a_one_sided_board_side_by_side(self):
        k=self.make((4.45,6.5),(4.,6.49))
        self.assertTrue(k.command('jeff','chop b1')[0]);k.advance(.05)
        focus,action=k.facing_interaction('human','use')
        self.assertEqual((focus,action.key),('b1','chop b1'))
        self.assertTrue(k.start('human',action)[0]);k.advance(.01)
        before=k.stations['b1'].food.chopped;k.advance(.5)
        self.assertAlmostEqual(k.stations['b1'].food.chopped-before,1)
        k.assert_invariants()

    def test_jeff_joins_beside_the_player(self):
        k=self.make((4.,6.49),(6.,6.49))
        self.assertTrue(k.command('human','chop b1')[0]);k.advance(.05)
        self.assertIn('chop b1',[a.key for a in k.actions('jeff')])
        self.assertTrue(k.command('jeff','chop b1')[0])
        for _ in range(30):k.advance(.1)
        self.assertEqual(k.positions['jeff'],(4.45,6.49))
        self.assertEqual(k.stations['b1'].food.stage,'chopped')
        self.assertTrue(any(e.get('kind')=='shared_work_join' and e.get('actor')=='jeff' for e in k.events))

    def test_jeff_chops_beside_a_player_standing_in_front(self):
        k=self.make((4.,6.49),(6.,6.49))
        self.assertTrue(k.command('jeff','chop b1')[0])
        for _ in range(40):k.advance(.1)
        self.assertEqual(k.positions['jeff'],(4.45,6.49))
        self.assertTrue(k.in_work_reach('b1',k.positions['jeff']))
        self.assertEqual(k.stations['b1'].food.stage,'chopped')
