"""Display localization never changes game/API inputs; Node runs the actual bundle."""
import ast
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from kitchen import ROOT, load_config, Food
from spatial_kitchen import SpatialKitchen

class ShellTexts(HTMLParser):
    def __init__(self):super().__init__();self.skip=0;self.texts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if not self.skip:
            self.texts += [v for k,v in attrs if k in ('placeholder','aria-label','title')]
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip-=1
    def handle_data(self,text):
        if not self.skip and text.strip():self.texts.append(text.strip())

@unittest.skipUnless(shutil.which('node'),'Node.js is needed to verify the browser localization bundle')
class LocalizationTests(unittest.TestCase):
    def run_js(self,body,corpus=None):
        script="""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let saved='en';
const root={localStorage:{getItem:()=>saved,setItem:(k,v)=>{saved=v}}};
const ctx={module:{exports:{}},globalThis:root};
vm.runInNewContext(fs.readFileSync('cocos-kitchen/i18n.js','utf8').replace('__KITCHEN_CATALOG__',fs.readFileSync('cocos-kitchen/i18n.json','utf8')),ctx);
const i=ctx.module.exports;
"""+"const corpus="+json.dumps(corpus or [],ensure_ascii=False)+";\n"+body
        result=subprocess.run(['node','-e',script],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_switch_persistence_reversibility_and_user_identifiers(self):
        self.run_js("""
assert.equal(i.language,'en');assert.equal(i.t('继续经营'),'Resume');
assert.equal(i.t('已连接：我的模型 · 玩家账号付费'),'Connected: 我的模型 · Your account pays');
i.setLanguage('zh');assert.equal(saved,'zh');assert.equal(i.t('继续经营'),'继续经营');
i.setLanguage('en');assert.equal(i.t('手中：干净餐盘'),'Holding: Clean plate');
assert.equal(i.t('到案板 1切 F2'),'Chop F2 at Board 1');
assert.equal(i.t('空格 · 洗碗'),'Space · Wash dishes');
assert.equal(i.t('熟牛排 5s 后糊'),'Cooked steak · burns in 5s');
assert.equal(i.t('Kitchen timeout'),'Kitchen timeout');
""")
    def test_shell_and_server_errors_are_translated(self):
        parser=ShellTexts();parser.feed((ROOT/'cocos-kitchen/web-shell.html').read_text());corpus=parser.texts
        for file in ('web_server.py','player_api.py'):
            for node in ast.walk(ast.parse((ROOT/file).read_text())):
                if isinstance(node,ast.Dict):
                    for key,value in zip(node.keys,node.values):
                        if isinstance(key,ast.Constant) and key.value=='error' and isinstance(value,ast.Constant) and isinstance(value.value,str):corpus.append(value.value)
        self.run_js("const missing=corpus.filter(x=>/[\\u3400-\\u9fff]/.test(i.t(x)));assert.deepEqual(missing,[]);",corpus)
    def test_live_station_action_and_event_labels(self):
        k=SpatialKitchen(load_config());corpus=[s.name for s in k.stations.values()]
        for stage in ('raw','chopped','clean_plate','dirty_plate','extinguisher'):
            k.chefs['human'].hand=Food('test',stage)
            corpus.extend(a.label.split('（')[0] for a in k.actions('human') if a.kind not in ('throw','go'))
        corpus += [k.result(),'Jeff洗好了 D1，可取走盛菜或放到空柜台','灶台 1的 F1 熟了！8s 后糊锅','顾客差评：糊菜；扣 15 元，O1失败']
        self.run_js("const missing=corpus.filter(x=>/[\\u3400-\\u9fff]/.test(i.t(x)));assert.deepEqual(missing,[]);",corpus)
