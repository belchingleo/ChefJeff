import ast
from pathlib import Path
import copy
import json
import re
import unittest
from unittest.mock import patch
from kitchen import Food, load_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
from jev import DecisionLoop
from model_language import english_data, INPUT_LANGUAGE_VERSION

class ModelLanguageTests(unittest.TestCase):
    def assert_english(self,data):
        missing=[]
        def walk(value,path='root'):
            if isinstance(value,dict):
                for key,item in value.items():walk(item,path+'.'+key)
            elif isinstance(value,(list,tuple)):
                for n,item in enumerate(value):walk(item,path+str(n))
            elif isinstance(value,str) and re.search(r'[\u3400-\u9fff]',value):missing.append((path,value))
        walk(data);self.assertEqual(missing,[])
    def test_all_current_actions_states_and_rules_are_english_without_mutation(self):
        for stage in ('raw','chopped','clean_plate','dirty_plate','pot','extinguisher','ready'):
            k=SpatialKitchen(load_config());k.chefs['jev'].hand=Food('held',stage,plate_id='D1' if stage=='ready' else None)
            k.stations['b1'].food=Food('prep','raw');k.stations['p1'].food=Food('cooked','ready',6,12)
            state=k.snapshot();before=copy.deepcopy(state);actions=k.actions('jev')
            payload=SpatialJevClient(k.c,key='test').payload(state,actions)
            self.assert_english(payload);self.assertEqual(state,before)
            self.assertEqual(list(payload['questions']['next_action']['criteria']),[a.key for a in actions])
            self.assertEqual(payload['state']['rules']['timing']['handling'],.15)
    def test_logged_request_translates_memory_and_history_but_preserves_records(self):
        k=SpatialKitchen(load_config());k.emit('Jeff洗好了 D1，可取走盛菜或放到空柜台',kind='washed',actor='jev')
        memory={'enabled':True,'episodes':[{'events':[{'message':'你完成动作：切菜','action':'chop b1','target':[4,3]}]}]}
        original=copy.deepcopy(memory);rows=[]
        ai=DecisionLoop(k,SpatialJevClient(k.c,key='test'),lambda kind,data:rows.append((kind,data)),lambda text:None)
        ai.cooperation_memory=memory
        ai.recent_decisions=[{'choice':'wait','accepted':True,'result':'等待'}]
        with patch('jev.threading.Thread'):ai.poll()
        payload=next(d['payload'] for kind,d in rows if kind=='ai_request')
        self.assert_english(payload);self.assertEqual(payload['state']['input_language'],INPUT_LANGUAGE_VERSION)
        self.assertEqual(memory,original);self.assertIn('洗好了',k.events[-1]['message'])
    def test_integers_booleans_action_keys_and_coordinates_unchanged(self):
        source={'criteria':{'put b1':'将手中食材放到案板 1'},'target':[4,3],'accepted':False,'remaining':.15,'nullable':None}
        result=english_data(source)
        self.assertEqual(result['target'],[4,3]);self.assertIs(result['accepted'],False)
        self.assertEqual(result['remaining'],.15);self.assertIsNone(result['nullable'])
        self.assertEqual(list(result['criteria']),['put b1']);self.assertEqual(result['criteria']['put b1'],'Put the held ingredient on Board 1')

    def test_event_templates_and_provider_identifiers(self):
        self.assertEqual(english_data({'model':'我的模型','action':'go p1'}),{'model':'我的模型','action':'go p1'})
        for file in ('kitchen.py','spatial_kitchen.py'):
            for node in ast.walk(ast.parse(Path(file).read_text())):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='emit' and node.args:
                    value=node.args[0]
                    if isinstance(value,ast.JoinedStr):
                        source=''.join(v.value if isinstance(v,ast.Constant) else 'X' for v in value.values)
                        self.assert_english(english_data(source))
