import json
import re
import unittest
from kitchen import Food, load_config
from spatial_kitchen import WALK_SPEED, SpatialKitchen
from whitebox_server import SpatialJevClient
from web_server import GameSession

class CounterLevelTests(unittest.TestCase):
    def make(self,level=2):return SpatialKitchen({**load_config(),'level':level,'spawn_seed':0,'order_seed':42})
    def do(self,k,key,who='human'):
        a=next(a for a in k.actions(who) if a.key==key)
        if a.target:k.positions[who]=k.path(who,a.target)[-1]
        self.assertTrue(k.start(who,a)[0],key)
        while k.chefs[who].job:k.advance(.05)
        k.assert_invariants()
    def test_new_map_resources_orders_and_every_workstation_reachable(self):
        k=self.make()
        self.assertEqual((len(k.pots),k.pot_count,k.plate_count,len(k.boards)),(1,1,2,2))
        self.assertEqual([o['dish'] for o in k.orders],['burger']*5)
        self.assertEqual(k.c['round_seconds'],180)
        self.assertTrue(all(o['deadline']<=180 for o in k.orders))
        self.assertEqual(k.floor & {(x,4) for x in range(14)},{(10,4),(11,4)})
        self.assertEqual({p[1] for p in k.positions.values()},{2,5})
        for who in k.chefs:
            for station in k.stations:self.assertTrue(k.path(who,station))
        k.assert_invariants()
    def test_three_burgers_with_two_plates_requires_and_supports_recycling(self):
        k=self.make()
        # Real processing actions, with walking removed to isolate recipe/resource flow.
        for i in range(3):
            if i==2:
                k.advance(8);self.do(k,'take returns');self.do(k,'put sink');self.do(k,'wash');self.do(k,'take sink');self.do(k,'put plates')
            counter='counter2' if i==1 else 'plates'
            for ingredient in ('bread','lettuce','tomato'):
                self.do(k,'fetch '+ingredient)
                if ingredient!='bread':
                    self.do(k,'put b1');self.do(k,'chop b1');self.do(k,'take b1')
                self.do(k,'assemble '+counter)
            self.do(k,'fetch');self.do(k,'put b2');self.do(k,'chop b2');self.do(k,'take b2');self.do(k,'put p1')
            self.do(k,'take '+counter);k.advance(12);self.do(k,'plate p1')
            if k.orders[i]['arrival']>k.time:k.advance(k.orders[i]['arrival']-k.time+.01)
            self.do(k,'serve')
        self.assertEqual(k.served,3);self.assertTrue(k.won());k.assert_invariants()
    def test_all_levels_sprint_and_english_model_contract(self):
        for level in (1,2,3):
            k=self.make(level);k.positions['human']=(2,2);k.set_manual('human',1,0)
            self.assertTrue(k.sprint('human'));k.advance(.1)
            self.assertAlmostEqual(k.positions['human'][0],2+WALK_SPEED*1.4*.1)
            payload=SpatialJevClient(k.c,key='offline').payload(k.snapshot(),k.actions('jeff'))
            self.assertIn('sprint',payload['questions'])
            self.assertIn('Off-stove pots never heat food',payload['state']['rules']['off_stove_pots'])
            self.assertFalse(re.search(r'[\u3400-\u9fff]',json.dumps(payload,ensure_ascii=False)))
    def test_three_level_switch_does_not_leak_resources(self):
        g=GameSession(kitchen_factory=SpatialKitchen)
        for level,pots,plates in ((3,3,3),(2,1,2),(1,1,2)):
            self.assertEqual(g._command('/api/level',{'level':level})[0],200)
            self.assertEqual((g.k.pot_count,g.k.plate_count),(pots,plates))
            self.assertEqual(g.k.resolved['level']['id'],f'level-{level}')
            self.assertEqual(len(g.k.orders),len(g.k.resolved['order_plan']['orders']))
            g.k.assert_invariants()
    def test_practice_left_wall_clear_and_single_bin(self):
        k=self.make(1)
        self.assertEqual([s for s in k.stations if s.startswith('bin')],['bin'])
        self.assertFalse(any(v['cell'][0]==1 for v in k.equipment.values()))
        for who in k.chefs:
            for station in k.stations:self.assertTrue(k.path(who,station))
