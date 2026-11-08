"""Display localization never changes game/API inputs; Node runs the actual bundle."""
import ast
from html.parser import HTMLParser
import json
from pathlib import Path
import re
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
    def test_level_editor_copy_is_fully_translated(self):
        """Every Chinese literal of level-editor.js (placeholders filled), the release's ingredient and pan
        names it shows, and the strings it composes from them."""
        import re
        import level_design
        corpus = []
        for line in (ROOT / 'cocos-kitchen/level-editor.js').read_text().splitlines():
            if 'i18n: bilingual' in line:
                continue
            for literal in re.findall(r"'((?:[^'\\\n]|\\.)*)'", line):
                if re.search(r'[\u3400-\u9fff]', literal):
                    corpus.append(re.sub(r'\{\d+\}', '1', literal))
        catalog = level_design.editor_catalog()
        names = [i['name'] for i in catalog['items']] + list(catalog['containers'].values())
        corpus += names + ['还缺：%s食材箱' % names[0], '已摆：灶台·%s' % names[-1], '切好后放进%s加热' % names[-1],
                           '%s食材箱只能贴着外墙摆，点有橙色边框的格子' % names[0], '出餐口要贴着外墙摆']
        self.assertGreater(len(corpus), 150)
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
        corpus += [k.result(),'Jeff洗好了 D1，可取走盛菜或放到空柜台','灶台 1的 F1 熟了！8s 后糊锅','没有等待牛排的订单；扣 20 元']
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


# Where server text reaches the page: error replies, session notes and notices, and the exceptions whose messages
# become them. The guard reads these places in every module that serves the page, so a new or reworded Chinese
# message without an English entry fails here instead of reaching English players half translated.
PAGE_MODULES = ('web_server.py', 'player_api.py', 'hosted_server.py', 'hosted_jev.py', 'hosted_cloudflare.py',
                'hosted_free_models.py', 'hosted_records.py', 'hosted_capacity.py', 'hosted_usage.py',
                'player_level_queue.py', 'level_design.py', 'level_calibration.py', 'jev.py', 'whitebox_server.py',
                'cocos_server.py', 'free_model_client.py', 'model_status.py', 'feedback.py', 'cooperation_memory.py',
                'kitchen.py', 'spatial_kitchen.py')
MESSAGE_KEYS = ('error', 'message')
MESSAGE_CALLS = ('note', 'notify', 'ValueError', 'RuntimeError', 'ModelWait', 'GatewayError', 'PermissionError',
                 'LookupError')
# Messages that never reach a page, each with where it goes instead (file, Chinese text with placeholders as 7).
NOT_ON_A_PAGE = {
    ('kitchen.py', '配置 7 必须是 true 或 false'): 'config.json check at server start, printed in the terminal',
    ('kitchen.py', '配置 7 必须是正数'): 'config.json check at server start, printed in the terminal',
    ('kitchen.py', '配置 7 必须是整数'): 'config.json check at server start, printed in the terminal',
    ('kitchen.py', '文字原型最多支持 8 块案板和 8 口锅'): 'config.json check at server start, printed in the terminal',
    ('kitchen.py', 'ai_max_calls 不能超过 2000'): 'config.json check at server start, printed in the terminal',
    ('kitchen.py', '时间增量无效'): "engine guard on its own clock; the session's fixed ticks never trigger it",
    ('spatial_kitchen.py', '未知地面位置'): 'routing fallback caught inside the engine',
    ('spatial_kitchen.py', '工位没有可操作的一侧'): 'routing fallback caught inside the engine',
    ('spatial_kitchen.py', '操作停靠点超出安全地面'): 'routing fallback caught inside the engine',
}


def page_messages():
    """(file, line, text) for every Chinese message the page modules send to a page; f-string fields read 7."""
    cjk = re.compile(r'[㐀-鿿]')

    def text(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return ''.join(v.value if isinstance(v, ast.Constant) else '7' for v in node.values)
        return None

    found = []
    for name in PAGE_MODULES:
        for node in ast.walk(ast.parse((ROOT / name).read_text(encoding='utf-8'))):
            values = []
            if isinstance(node, ast.Dict):
                values = [v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and k.value in MESSAGE_KEYS]
            elif isinstance(node, ast.Call) and node.args:
                called = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', None)
                values = [node.args[0]] if called in MESSAGE_CALLS else []
            for value in values:
                message = text(value)
                if message and cjk.search(message):
                    found.append((name, node.lineno, message))
    return found


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed to verify the browser localization bundle')
class PageMessageGuardTests(LocalizationTests):
    def test_every_page_message_has_english(self):
        found = page_messages()
        self.assertGreater(len(found), 150)
        corpus = [message for name, _, message in found if (name, message) not in NOT_ON_A_PAGE]
        # Messages composed from others, as the page receives them.
        corpus += ['模型没有返回可执行的合法动作（不是 JSON；回复：\'wash now\'）；本次不执行。',
                   '模型没有返回可执行的合法动作（choice 不在候选动作里）；本次不执行。',
                   'Jeff 请求失败：模型接口连接失败或返回了无效数据；4s 后重试。无脚本队友代替。',
                   'Jeff 请求失败：TypeSafe 网络连接失败或超时；2s 后重试。无脚本队友代替。']
        self.run_js("const missing=corpus.filter(x=>/[\\u3400-\\u9fff]/.test(i.t(x)));assert.deepEqual(missing,[]);", corpus)

    def test_the_built_page_carries_the_current_catalog(self):
        # build_cocos.py writes kitchen-i18n.js from i18n.js and i18n.json; a catalog change needs it rewritten.
        built = (ROOT / 'cocos-kitchen/i18n.js').read_text().replace('__KITCHEN_CATALOG__', (ROOT / 'cocos-kitchen/i18n.json').read_text())
        self.assertEqual((ROOT / 'cocos-kitchen/build/web/kitchen-i18n.js').read_text(), built)

    def test_the_allowlist_names_only_messages_that_exist(self):
        found = {(name, message) for name, _, message in page_messages()}
        self.assertEqual(set(NOT_ON_A_PAGE) - found, set())


# Only the cases above; the inherited ones already run in LocalizationTests.
for _name in dir(LocalizationTests):
    if _name.startswith('test_'):
        setattr(PageMessageGuardTests, _name, None)
