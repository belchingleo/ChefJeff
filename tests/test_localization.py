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
    def test_hosted_connection_and_usage_copy_is_fully_translated(self):
        corpus=['浏览器直连模型',
            '：在线版由浏览器直连模型；服务商必须允许跨域访问。跨域失败不会改由服务器代发 Key。',
            '本局 0 / 200 次；成功回复 token：输入 0 / 输出 0；本页面连接测试 0 次']
        catalog=json.loads((ROOT/'cocos-kitchen/i18n.json').read_text())
        corpus += [s for s in catalog['messages'] if '仅保留到当前页面会话结束' in s or '在线版没有可追溯的服务器对局日志' in s]
        self.run_js("const missing=corpus.filter(x=>/[\\u3400-\\u9fff]/.test(i.t(x)));assert.deepEqual(missing,[]);",corpus)

    def test_live_station_action_and_event_labels(self):
        k=SpatialKitchen(load_config());corpus=[s.name for s in k.stations.values()]
        for stage in ('raw','chopped','clean_plate','dirty_plate','extinguisher'):
            k.chefs['human'].hand=Food('test',stage)
            corpus.extend(a.label.split('（')[0] for a in k.actions('human') if a.kind not in ('throw','go'))
        corpus += [k.result(),'Jeff洗好了 D1，可取走盛菜或放到空柜台','灶台 1的 F1 熟了！8s 后糊锅','顾客差评：糊菜；扣 15 元，O1失败']
        self.run_js("const missing=corpus.filter(x=>/[\\u3400-\\u9fff]/.test(i.t(x)));assert.deepEqual(missing,[]);",corpus)

    def test_service_rules_copy_is_fully_translated(self):
        import config_contract as cc
        bundle = cc.level_bundle('level-3', embed=True);bundle['level']['seeds'] = {'orders': 1, 'spawn': 0}
        k = SpatialKitchen(cc.freeze_bundle(bundle));k.advance(200.)
        target = k.rules.goal['min_money']
        corpus = [k.result(), '你和 AI 搭档，一起照顾这间小厨房。\n本局目标：关店时净收入达到 ¥%d' % target,
                  '出餐 3 单 · 净收入 ¥120 / ¥%d' % target, '你完成 O2，收入 +40 元（菜品糊了，扣 10 元）', 'Jeff完成 O1，收入 +80 元',
                  '没有等待汉堡的订单；扣 20 元', 'O3的顾客拒收糊菜，订单继续等待', 'O4超时，顾客离开，扣 10 元',
                  '已无法达成目标金额 %d 元；本局继续至关店' % target, 'O8在关店时仍未完成', 'Jeff加入案板 1的共同操作（2人）',
                  '你离开案板 1的共同操作，进度保留']
        corpus += [e['message'] for e in k.events]
        self.run_js("const missing=corpus.filter(x=>/[\\u3400-\\u9fff]/.test(i.t(x)));assert.deepEqual(missing,[]);",corpus)
