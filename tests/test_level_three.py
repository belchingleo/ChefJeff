import json
import math
import re
import unittest
from levels import level_config
from unittest.mock import patch
from kitchen import Food,GroundItem,load_config
from spatial_kitchen import SpatialKitchen,tile_key,WALK_SPEED
from whitebox_server import SpatialJevClient
from web_server import GameSession
from jev import DecisionLoop

class LevelThreeTests(unittest.TestCase):
    def kitchen(self,seed=42):return SpatialKitchen({**load_config(),'level':3,'order_seed':seed,'spawn_seed':0})
    def do(self,k,key,who='human'):
        a=next(a for a in k.actions(who) if a.key==key)
        k.positions[who]=k.path(who,a.target)[-1]
        self.assertTrue(k.start(who,a)[0],key)
        while k.chefs[who].job:k.advance(.05)
        k.assert_invariants()
    def take_plate(self,k):self.do(k,'take plates')
    def test_map_resources_reachability_and_old_level_isolation(self):
        old=SpatialKitchen(load_config());k=self.kitchen()
        self.assertEqual(len(k.pots),2);self.assertEqual(k.pot_count,3)
        self.assertEqual(k.stations['counter4'].food.id,'P3');self.assertEqual(k.plate_count,3)
        self.assertEqual(k.nav.floor & {(7,y) for y in range(9)},{(7,4)})
        for who in k.chefs:
            for station in k.stations:self.assertTrue(k.path(who,station))
        k.assert_invariants();old.assert_invariants()
        self.assertEqual(len(old.pots),1);self.assertEqual(old.snapshot()['map']['layout_version'],'level-1-4')
    def test_seeded_orders_counts_deadlines(self):
        k=self.kitchen();other=self.kitchen()
        self.assertEqual(k.orders,other.orders)
        self.assertEqual(len(k.orders),5);self.assertEqual(k.c['target_served'],5);self.assertEqual(k.c['target_money'],140)
        self.assertEqual(k.c['round_seconds'],360)
        self.assertEqual([o['dish'] for o in k.orders].count('burger'),3)
        self.assertEqual([o['dish'] for o in k.orders].count('steak'),2)
        self.assertGreater(len({tuple(o['dish'] for o in self.kitchen(seed).orders) for seed in range(10)}),1)
        self.assertLessEqual(max(o['deadline'] for o in k.orders),360)
    def test_bread_needs_no_chop_and_vegetables_cannot_cook(self):
        k=self.kitchen();self.do(k,'fetch bread');self.do(k,'put b1')
        self.assertNotIn('chop b1',[a.key for a in k.actions('human')])
        self.do(k,'take b1');self.do(k,'assemble plates')
        self.assertEqual(k.stations['plates'].food.components,('bread',))
        self.do(k,'fetch lettuce');self.do(k,'put b1');self.do(k,'chop b1');self.do(k,'take b1')
        self.assertFalse(any(a.kind=='put_pot' for a in k.actions('human')))
        self.do(k,'assemble plates');k.assert_invariants()
    def test_full_burger_real_actions_and_same_dish_order_matching(self):
        k=self.kitchen()
        for ingredient in ('bread','lettuce','tomato'):
            self.do(k,'fetch '+ingredient)
            if ingredient!='bread':
                self.do(k,'put b1');self.do(k,'chop b1');self.do(k,'take b1')
            self.do(k,'assemble plates')
        self.do(k,'fetch');self.do(k,'put b1');self.do(k,'chop b1');self.do(k,'take b1');self.do(k,'put p1')
        self.do(k,'take plates');k.advance(12)
        self.do(k,'plate p1')
        held=k.chefs['human'].hand;self.assertEqual(k.dish(held),'burger');self.assertEqual(held.stage,'ready')
        # Earliest order is steak; serving a burger must leave it untouched.
        for o in k.orders:o['status']='future';o['arrival']=350;o['deadline']=360
        k.orders[0].update(dish='steak',status='pending',deadline=k.time+60)
        k.orders[1].update(dish='burger',status='pending',deadline=k.time+80)
        self.do(k,'serve')
        self.assertEqual(k.orders[0]['status'],'pending');self.assertEqual(k.orders[1]['status'],'served');self.assertEqual(k.money,60)
    def test_incomplete_duplicate_and_dirty_plate_are_rejected(self):
        k=self.kitchen();self.do(k,'fetch bread');self.do(k,'assemble plates');self.do(k,'take plates')
        self.assertNotIn('serve',[a.key for a in k.actions('human')])
        # The accepted 0.5.9 ruleset cannot pass plates; the service Level 3 passes them up to 3 tiles.
        self.assertIsNone(k.throw_range('human'))
        service=SpatialKitchen(level_config(load_config(),3)|{'spawn_seed':0});service.chefs['human'].hand=k.chefs['human'].hand
        self.assertEqual(service.throw_range('human'),3.0)
        self.assertFalse(k.can_add(k.chefs['human'].hand,Food('x',ingredient='bread')))
        self.assertFalse(k.can_add(Food('dirty','dirty_plate'),Food('x',ingredient='bread')))
        self.assertFalse(k.can_add(Food('clean','clean_plate'),Food('x',ingredient='lettuce')))
    def test_plate_partial_burger_from_floor_pot_and_partner(self):
        k=self.kitchen();self.take_plate(k)
        k.chefs['human'].hand=k.merge_plate(k.chefs['human'].hand,Food('bun',ingredient='bread'))
        self.do(k,'take pot p1','jeff');pot=k.chefs['jeff'].hand;pot.contents=Food('meat','ready',heated=12)
        self.do(k,'drop','jeff');self.do(k,'plate ground P1')
        self.assertEqual(set(k.chefs['human'].hand.components),{'beef','bread'});self.assertIsNone(k.ground['P1'].food.contents)
        k.assert_invariants()
    def test_stale_assembly_does_not_overwrite_plate(self):
        k=self.kitchen();self.do(k,'fetch bread')
        action=next(a for a in k.actions('human') if a.key=='assemble plates')
        k.stations['plates'].food=k.merge_plate(k.stations['plates'].food,Food('tom','chopped',ingredient='tomato'))
        self.assertFalse(k.start('human',action)[0]);self.assertEqual(k.chefs['human'].hand.ingredient,'bread')
    def test_spare_pot_swap_preserves_food_heat(self):
        k=self.kitchen();k.stations['p1'].food=Food('beef','ready',heated=12);k.stations['p1'].heating=True
        counter=next(x for x in k.counters if k.stations[x].food is None)
        self.do(k,'take pot p1');self.do(k,'put '+counter);self.do(k,'take counter4');self.do(k,'put pot p1')
        k.advance(12);self.assertEqual(k.stations[counter].food.contents.stage,'ready');self.assertEqual(k.stations['p1'].pot_id,'P3')
    def test_sprint_distance_cooldown_and_work_not_accelerated(self):
        k=self.kitchen();k.positions['human']=(2,4);k.set_manual('human',1,0)
        self.assertTrue(k.sprint('human'));self.assertFalse(k.sprint('human'))
        k.advance(1);self.assertAlmostEqual(k.positions['human'][0],2+WALK_SPEED*1.4,places=6)
        self.assertFalse(k.sprint('human'));k.set_manual('human',0,0);k.advance(3)
        k.positions['human']=(2,4);k.set_manual('human',1,0);self.assertTrue(k.sprint('human'))
        k.set_manual('human',0,0);k.stations['b1'].food=Food('chop','raw');self.do(k,'chop b1')
        self.assertEqual(k.stations['b1'].food.chopped,6)
    def test_path_sprint_matches_manual_and_stops_at_wall(self):
        k=self.kitchen();k.positions['jeff']=(2,4)
        from kitchen import Action
        a=Action('go floor_6_4','go','go','floor_6_4')
        # Player floor paths and AI station paths share the same travel integration.
        k.positions['human']=(2,4);self.assertTrue(k.start('human',a)[0]);self.assertTrue(k.sprint('human'))
        k.advance(.5);self.assertAlmostEqual(k.positions['human'][0],2+WALK_SPEED*1.4*.5,places=6)
        k.advance(.5);self.assertAlmostEqual(k.positions['human'][0],6)
        k.positions['human']=(2,2);k.advance(3);k.set_manual('human',-1,0);self.assertTrue(k.sprint('human'));k.advance(1)
        self.assertTrue(k.nav.walkable_point(k.positions['human']));self.assertGreater(k.positions['human'][0],1.6)
    def test_english_state_and_sprint_question(self):
        k=self.kitchen();p=SpatialJevClient(k.c,key='offline').payload(k.snapshot(),k.actions('jeff'))
        self.assertIn('sprint',p['questions']);self.assertIn('3 seconds',p['state']['rules']['sprint'])
        self.assertFalse(re.search(r'[\u3400-\u9fff]',json.dumps(p,ensure_ascii=False)))
    def test_level_switch_and_rejected_paused_switch(self):
        g=GameSession(kitchen_factory=SpatialKitchen)
        self.assertEqual(g._command('/api/level',{'level':3})[0],200)
        self.assertEqual(g.c['pots'],2);self.assertEqual(g.k.snapshot()['level'],3)
        g.phase='paused';self.assertEqual(g._command('/api/level',{'level':1})[0],409)
        g.phase='ready';self.assertEqual(g._command('/api/level',{'level':1})[0],200)
        self.assertEqual(g.c['pots'],1);self.assertEqual(g.k.snapshot()['level'],1)
    def test_sprint_input_sequence_and_invalid_values(self):
        g=GameSession(kitchen_factory=SpatialKitchen);g._command('/api/level',{'level':3});g.phase='running'
        b={'seq':1,'dx':1,'dy':0,'sprint':True}
        self.assertEqual(g._move(b)[0],200);end=g.k.sprint_until['human']
        self.assertTrue(g._move(b)[1]['ignored']);self.assertEqual(end,g.k.sprint_until['human'])
        self.assertEqual(g._move({**b,'seq':2,'sprint':'true'})[0],400)
        g.phase='paused';g._move({**b,'seq':3});self.assertFalse(any(g.k.manual['human']))
    def test_same_reply_sprint_applies_only_to_accepted_fresh_travel(self):
        import time
        for stale in (False,True):
            k=self.kitchen();records=[]
            ai=DecisionLoop(k,SpatialJevClient(k.c,key='offline'),lambda t,d:records.append((t,d)),lambda _:None)
            action=next(a for a in k.actions('jeff') if a.key=='go fridge')
            context={'id':1,'sent':time.monotonic()-(20 if stale else 0),'epoch':ai.epoch,'job_id':None,'actions':{action.key:action}}
            ai.q.put((context,{'choice':action.key,'sprint':True,'model':'offline','usage':{},'latency':.1},None));ai.inflight=True
            with patch('jev.threading.Thread'):ai.poll()
            response=next(d for t,d in records if t=='ai_response')
            self.assertEqual(response['sprint_applied'],not stale)
            self.assertEqual(k.sprint_until['jeff']>0,not stale)
    def test_both_provider_adapters_parse_sprint_without_extra_request(self):
        import io
        from player_api import CompatibleClient
        k=self.kitchen();client=SpatialJevClient(k.c,key='offline');payload=client.payload(k.snapshot(),k.actions('jeff'))
        reply={'model':'offline','answers':{'next_action':{'type':'choice','choice':'wait'},'sprint':{'type':'choice','choice':'yes'}}}
        with patch('jev.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(reply).encode())) as request:
            self.assertTrue(client.ask(payload)['sprint']);self.assertEqual(request.call_count,1)
        compatible=CompatibleClient(k.c,{'provider':'compatible','model':'offline','api_key':'offline','base_url':'https://example.invalid'})
        reply={'choices':[{'message':{'content':'{"choice":"wait","sprint":false}'}}]}
        with patch('player_api.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=io.BytesIO(json.dumps(reply).encode())
            self.assertFalse(compatible.ask(payload)['sprint']);self.assertEqual(opener.return_value.open.call_count,1)
        reply['choices'][0]['message']['content']='{"choice":"wait","sprint":"yes"}'
        with patch('player_api.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=io.BytesIO(json.dumps(reply).encode())
            with self.assertRaises(RuntimeError):compatible.ask(payload)
    def test_new_ingredient_partial_plate_and_event_descriptions_are_english(self):
        for ingredient in ('bread','lettuce','tomato'):
            for stage in ('raw','chopped'):
                k=self.kitchen();k.chefs['jeff'].hand=Food('held',stage,ingredient=ingredient)
                k.stations['plates'].food=k.merge_plate(k.stations['plates'].food,Food('bun',ingredient='bread'))
                p=SpatialJevClient(k.c,key='offline').payload(k.snapshot(),k.actions('jeff'))
                self.assertFalse(re.search(r'[\u3400-\u9fff]',json.dumps(p,ensure_ascii=False)),ingredient)
