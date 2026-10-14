// Check actual local/hosted settings copy, including closed disclosure panels,
// without translating user-entered values or raw record JSON.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{spawnSync}=require('node:child_process');
const result=spawnSync('python3',['-c',String.raw`
import ast, json, re
from html.parser import HTMLParser
from pathlib import Path
from hosted_server import hosted_html
class Copy(HTMLParser):
    def __init__(self):
        super().__init__(); self.tags=[]; self.active=False; self.copy=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='dialog' and attrs.get('id')=='kitchen-api-dialog': self.active=True
        if self.active:
            for name in ('placeholder','aria-label','title'):
                if attrs.get(name): self.copy.append(attrs[name])
        if tag not in ('input','br','img','meta','link','hr'): self.tags.append(tag)
    def handle_endtag(self, tag):
        if tag=='dialog': self.active=False
        if tag in self.tags: self.tags=self.tags[:len(self.tags)-1-self.tags[::-1].index(tag)]
    def handle_data(self, data):
        if self.active and not set(self.tags).intersection(('script','style','textarea')) and data.strip():
            self.copy.append(data.strip())
raw=Path('cocos-kitchen/build/web/index.html').read_bytes()
copies={}
for kind,html in [('local',raw),('hosted',hosted_html(raw))]:
    parser=Copy();parser.feed(html.decode());copies[kind]=parser.copy
copies['errors']=[]
for file in ('hosted_server.py','hosted_jev.py'):
    for node in ast.walk(ast.parse(Path(file).read_text())):
        if isinstance(node,ast.Dict):
            for key,value in zip(node.keys,node.values):
                if isinstance(key,ast.Constant) and key.value=='error' and isinstance(value,ast.Constant) and isinstance(value.value,str):
                    copies['errors'].append(value.value)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='ForwardError' and len(node.args)>1 and isinstance(node.args[1],ast.Constant):
            copies['errors'].append(node.args[1].value)
copies['browser']=re.findall(r"throw new Error\('([^']+)'\)",Path('hosted/browser-agent.js').read_text())
print(json.dumps(copies,ensure_ascii=False))
`],{encoding:'utf8'});
assert.equal(result.status,0,result.stderr);
const copies=JSON.parse(result.stdout),sandbox={module:{exports:{}},globalThis:{}};
vm.runInNewContext(fs.readFileSync('cocos-kitchen/build/web/kitchen-i18n.js','utf8'),sandbox);
const locale=sandbox.module.exports;
locale.setLanguage('en');
for(const [kind,strings] of Object.entries(copies))for(const source of strings){
 const english=locale.t(source);
 assert(!/[\u4e00-\u9fff]/u.test(english),kind+' has untranslated copy: '+english);
}
locale.setLanguage('zh');
for(const strings of Object.values(copies))for(const source of strings)assert.equal(locale.t(source),source);
assert(!fs.readFileSync('hosted/contribution.html','utf8').includes('class="contrib" data-no-i18n'));
assert.equal(locale.english('模型接口返回 HTTP 401，请检查账号和模型。'),'Model API returned HTTP 401. Check your account and model.');
assert.equal(locale.english('Jev 接口返回 HTTP 401，请检查账号和模型。'),'Jev API returned HTTP 401. Check your account and model.');
console.log('Settings localization: local and hosted copy, privacy, contribution, attributes and error messages switch completely between Chinese and English.');
