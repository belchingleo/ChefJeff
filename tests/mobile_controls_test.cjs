// Touch input contract tests. These run without a browser or a model API.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');

function harness(path,{width=844,height=390,touch=true,language='zh'}={}){
 const elements=new Map(),observers=[],media=[],calls=[];
 class Target{
  constructor(){this.listeners={};}
  addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
  removeEventListener(type,fn){this.listeners[type]=(this.listeners[type]||[]).filter(f=>f!==fn);}
  dispatchEvent(event){
   if(!event.target)event.target=this;event.currentTarget=this;
   for(const fn of this.listeners[event.type]||[])fn(event);
   this['on'+event.type]?.(event);
   if(event.bubbles&&!event.stopped)this.parentElement?.dispatchEvent(event);
   return !event.defaultPrevented;
  }
 }
 class Element extends Target{
  constructor(tag='div'){super();this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.style={setProperty(name,value){this[name]=value;}};this.hidden=false;this.disabled=false;this.open=false;this.textContent='';this.dataset={};this.captured=new Set();this.classSet=new Set();this.classList={add:(...v)=>v.forEach(x=>this.classSet.add(x)),remove:(...v)=>v.forEach(x=>this.classSet.delete(x)),contains:v=>this.classSet.has(v),toggle:(v,force)=>{const on=force??!this.classSet.has(v);on?this.classSet.add(v):this.classSet.delete(v);return on;}};}
  set id(value){this._id=value;elements.set(value,this);}get id(){return this._id||'';}
  set className(value){this.classSet=new Set(value.split(/\s+/).filter(Boolean));}get className(){return [...this.classSet].join(' ');}
  set innerHTML(value){
   this.children=[];const stack=[this];
   for(const match of value.matchAll(/<\/?([\w-]+)([^>]*)>/g)){
    const [whole,tag,attrs]=match;if(whole.startsWith('</')){if(stack.length>1)stack.pop();continue;}
    const child=new Element(tag);
    for(const attr of attrs.matchAll(/([\w-]+)(?:="([^"]*)"|'([^']*)'|=([^\s>]+))?/g))child.setAttribute(attr[1],attr[2]??attr[3]??attr[4]??'');
    stack.at(-1).appendChild(child);
    if(!whole.endsWith('/>')&&!['input','br','hr','img','meta','link'].includes(tag))stack.push(child);
   }
  }
  appendChild(child){child.parentElement=this;this.children.push(child);return child;}
  append(...children){children.forEach(c=>this.appendChild(c));}
  replaceChildren(...children){this.children=[];this.append(...children);}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(c=>c!==this);}
  setAttribute(name,value){this.attributes[name]=String(value);if(name==='id')this.id=String(value);if(name==='class')this.className=String(value);if(name==='hidden')this.hidden=true;if(name==='open')this.open=true;if(name.startsWith('data-'))this.dataset[name.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=String(value);}
  getAttribute(name){return this.attributes[name]??null;}
  hasAttribute(name){return name in this.attributes;}
  removeAttribute(name){delete this.attributes[name];if(name==='hidden')this.hidden=false;if(name==='open')this.open=false;}
  matches(selector){return selector.split(',').some(part=>{part=part.trim();if(part.startsWith('#'))return this.id===part.slice(1);if(part.startsWith('.'))return this.classList.contains(part.slice(1));if(part==='dialog[open]')return this.tagName==='DIALOG'&&this.open;if(part==='dialog')return this.tagName==='DIALOG';return this.tagName.toLowerCase()===part;});}
  closest(selector){for(let el=this;el;el=el.parentElement)if(el.matches(selector))return el;return null;}
  querySelectorAll(selector){return this.children.flatMap(c=>[...(c.matches(selector)?[c]:[]),...c.querySelectorAll(selector)]);}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  contains(target){for(let el=target;el;el=el.parentElement)if(el===this)return true;return false;}
  setPointerCapture(id){this.captured.add(id);}releasePointerCapture(id){this.captured.delete(id);}hasPointerCapture(id){return this.captured.has(id);}
  getBoundingClientRect(){return this.rect||{left:20,top:220,width:120,height:120,right:140,bottom:340};}
  focus(){document.activeElement=this;}blur(){if(document.activeElement===this)document.activeElement=null;}
 }
 class Event{
  constructor(type,options={}){this.type=type;Object.assign(this,options);}
  preventDefault(){this.defaultPrevented=true;}stopPropagation(){this.stopped=true;}stopImmediatePropagation(){this.stopped=true;}
 }
 const document=new Target();document.readyState='complete';document.hidden=false;document.activeElement=null;
 document.documentElement=new Element('html');document.head=new Element('head');document.body=new Element('body');
 document.documentElement.append(document.head,document.body);document.createElement=tag=>new Element(tag);
 document.getElementById=id=>elements.get(id)||null;document.querySelector=selector=>document.documentElement.querySelector(selector);document.querySelectorAll=selector=>document.documentElement.querySelectorAll(selector);
 const w=new Target();w.innerWidth=width;w.innerHeight=height;w.navigator={maxTouchPoints:touch?5:0};w.performance={now:()=>0};
 w.getComputedStyle=()=>({paddingLeft:'0px',paddingRight:'0px',paddingTop:'0px',paddingBottom:'0px'});
 w.matchMedia=query=>{const m=new Target();m.matches=query.includes('coarse')&&touch;m.media=query;m.addListener=fn=>m.addEventListener('change',fn);m.removeListener=fn=>m.removeEventListener('change',fn);media.push(m);return m;};
 const locale={module:{exports:{}},globalThis:{localStorage:{getItem:()=>language}}};
 vm.runInNewContext(fs.readFileSync('cocos-kitchen/i18n.js','utf8').replace('__KITCHEN_CATALOG__',fs.readFileSync('cocos-kitchen/i18n.json','utf8')),locale);
 w.kitchenI18n=locale.module.exports;
 const state={phase:'running',connected:true,pending:false,canInteract:true,canThrow:true,canDash:true,holding:true,interaction:'拿起番茄',interactionHint:'',aiming:false,sprint:{active_remaining:0,cooldown_remaining:0},orders:[],money:0,served:0,timeLabel:'180',handLabel:'番茄',aiStatus:'',mainLabel:'开始',mainEnabled:true,game_id:'round'};
 const controls={getState:()=>({...state})};
 for(const name of ['move','press','release','cancel','dash','pause','resume','main','settings','help','end','record','bookmark','block'])controls[name]=(...args)=>{calls.push([name,...args]);};
 w.kitchenControls=controls;
 class MutationObserver{constructor(fn){this.fn=fn;observers.push(this);}observe(){}disconnect(){}}
 const context={window:w,document,navigator:w.navigator,innerWidth:width,innerHeight:height,Event,CustomEvent:Event,HTMLElement:Element,MutationObserver,performance:w.performance,queueMicrotask:fn=>fn(),setTimeout:fn=>{fn();return 1;},clearTimeout:()=>{},requestAnimationFrame:fn=>{fn();return 1;},cancelAnimationFrame:()=>{}};
 vm.runInNewContext(fs.readFileSync(path,'utf8'),context,{filename:path});
 const fire=(id,type,options={})=>{const el=document.getElementById(id);assert(el,`missing ${id}`);const e=new Event(type,{pointerId:1,pointerType:'touch',button:0,isPrimary:true,clientX:80,clientY:280,bubbles:true,...options});el.dispatchEvent(e);return e;};
 const publish=patch=>{Object.assign(state,patch);w.dispatchEvent(new Event('kitchen-controls-state',{detail:{...state}}));};
 const resize=(width,height)=>{w.innerWidth=width;w.innerHeight=height;context.innerWidth=width;context.innerHeight=height;w.dispatchEvent(new Event('resize'));};
 const clear=()=>{calls.length=0;};
 return {w,document,elements,calls,controls,state,fire,publish,resize,clear,observers,media,Event,Element};
}

// Test cases are intentionally expressed through pointer events and the shared
// action bridge, not synthetic keyboard events. Source and shipped files must match.
function check(path){
 const h=harness(path);h.publish({});
 const callNames=()=>h.calls.map(c=>c[0]);
 const pauseRequested=()=>h.calls.some(c=>c[0]==='pause'||(c[0]==='block'&&c[1]===true));
 h.clear();h.fire('touch-joystick','pointerdown');
 h.fire('touch-joystick','pointermove',{clientX:84,clientY:284});
 assert(!h.calls.some(c=>c[0]==='move'&&Math.hypot(c[1],c[2])>0),'joystick center has a dead zone');
 h.fire('touch-joystick','pointermove',{clientX:130,clientY:230});
 let movement=h.calls.filter(c=>c[0]==='move').at(-1);
 assert(movement&&movement[1]>0&&movement[2]<0,'diagonal joystick movement');
 assert(Math.abs(Math.hypot(movement[1],movement[2])-1)<1e-8,'diagonal movement keeps walking speed');
 const movesBeforeOtherFinger=h.calls.filter(c=>c[0]==='move').length;
 h.fire('touch-joystick','pointerdown',{pointerId:2});h.fire('touch-joystick','pointermove',{pointerId:2,clientX:20});
 assert.equal(h.calls.filter(c=>c[0]==='move').length,movesBeforeOtherFinger,'another finger cannot steal an active joystick');
 h.fire('touch-action','pointerdown',{pointerId:2});
 assert(callNames().includes('press'),'another finger can operate while moving');
 h.fire('touch-action','pointerup',{pointerId:3});assert(!callNames().includes('release'),'another finger cannot release the held action');
 h.fire('touch-action','pointerup',{pointerId:2});
 assert(callNames().includes('release'),'operation releases exactly once');
 h.clear();h.fire('touch-action','mouseup',{pointerId:2});h.fire('touch-action','click',{pointerId:2});
 assert.equal(h.calls.filter(c=>['press','release'].includes(c[0])).length,0,'compatibility mouse/click must not repeat operation');
 h.fire('touch-joystick','pointermove',{clientX:400,clientY:-60});
 movement=h.calls.filter(c=>c[0]==='move').at(-1);
 assert(movement&&Math.abs(Math.hypot(movement[1],movement[2])-1)<1e-8,'pointer capture tracks outside joystick');
 h.fire('touch-dash','pointerdown',{pointerId:3});h.fire('touch-dash','pointerup',{pointerId:3});
 assert.equal(h.calls.filter(c=>c[0]==='dash').length,1,'moving with a second finger triggers one dash');
 h.fire('touch-joystick','pointerup');movement=h.calls.filter(c=>c[0]==='move').at(-1);h.publish({canDash:false});
 assert.deepEqual(movement,['move',0,0],'lifting movement finger stops movement');
 h.clear();h.fire('touch-dash','pointerdown',{pointerId:3});h.fire('touch-dash','pointerup',{pointerId:3});
 assert(!callNames().includes('dash'),'stationary dash is disabled');
 h.fire('touch-joystick','pointerdown',{clientX:130});h.publish({canDash:true,sprint:{cooldown_remaining:2,active_remaining:0}});h.clear();
 h.fire('touch-dash','pointerdown',{pointerId:3});assert(!callNames().includes('dash'),'cooldown disables dash');
 h.fire('touch-joystick','pointerup');h.publish({canDash:false,sprint:{cooldown_remaining:0,active_remaining:0}});

 // A cancelled pointer, including browser interruption, never releases a throw.
 for(const type of ['pointercancel','lostpointercapture']){
  h.fire('touch-action','pointerdown',{pointerId:2});h.clear();h.fire('touch-action',type,{pointerId:2});
  assert(callNames().includes('cancel'),`${type} cancels the pending action`);
  assert(!callNames().includes('release'),`${type} must not release a throw`);
 }
 h.fire('touch-action','pointerdown',{pointerId:2});h.publish({aiming:true});h.clear();
 h.elements.get('touch-cancel').rect={left:400,top:200,right:500,bottom:250,width:100,height:50};
 h.fire('touch-action','pointermove',{pointerId:2,clientX:450,clientY:225});h.fire('touch-action','pointerup',{pointerId:2,clientX:450,clientY:225});
 assert(callNames().includes('cancel'),'cancel affordance cancels aiming');assert(!callNames().includes('release'),'cancelled aim does not throw');
 h.publish({aiming:false});

 h.fire('touch-joystick','pointerdown',{clientX:130});h.fire('touch-action','pointerdown',{pointerId:2});h.clear();h.resize(390,844);
 assert(callNames().includes('cancel'),'portrait clears pending input');assert(pauseRequested(),'rotation requests pause through the action bridge');
 assert(h.calls.some(c=>c[0]==='move'&&c[1]===0&&c[2]===0),'portrait stops movement');
 h.clear();h.fire('touch-action','pointerup',{pointerId:2});assert(!callNames().includes('release'),'old finger release after rotation is ignored');
 h.clear();h.resize(844,390);assert(!callNames().some(name=>['resume','main'].includes(name)),'returning to landscape does not resume automatically');h.publish({phase:'running'});
 h.fire('touch-action','pointerdown',{pointerId:2});h.clear();h.document.hidden=true;h.document.dispatchEvent(new h.Event('visibilitychange'));
 assert(callNames().includes('cancel'),'background clears pending action');assert(pauseRequested(),'background requests pause through the action bridge');
 h.clear();h.fire('touch-action','pointerup',{pointerId:2});assert(!callNames().includes('release'),'background pointer release is ignored');
 h.document.hidden=false;h.document.dispatchEvent(new h.Event('visibilitychange'));
 assert(!callNames().some(name=>['resume','main'].includes(name)),'returning to foreground does not resume automatically');

 for(const patch of [{connected:false},{connected:true,phase:'paused'},{phase:'running',pending:true},{pending:false,canInteract:false,canThrow:false}]){
  h.publish(patch);h.clear();h.fire('touch-action','pointerdown',{pointerId:2});h.fire('touch-action','pointerup',{pointerId:2});
  assert(!callNames().some(name=>['press','release'].includes(name)),'unavailable gameplay blocks touch action');
 }
 h.publish({connected:true,phase:'running',canInteract:true,canThrow:true});
 const dialog=h.document.createElement('dialog');dialog.open=true;h.document.body.appendChild(dialog);h.observers.forEach(o=>o.fn([]));
 h.clear();h.fire('touch-action','pointerdown',{pointerId:2});h.fire('touch-action','pointerup',{pointerId:2});
 assert(!callNames().some(name=>['press','release'].includes(name)),'open dialogs block gameplay');
 dialog.open=false;h.observers.forEach(o=>o.fn([]));
 // A soft keyboard can reshape the viewport. Editing keeps the prior phone
 // orientation and cancels gameplay, rather than flashing the rotate screen.
 const input=h.document.createElement('input');h.document.body.appendChild(input);input.focus();
 h.clear();h.document.dispatchEvent(new h.Event('focusin'));h.resize(390,844);
 assert(pauseRequested(),'editing blocks and pauses touch gameplay');
 assert(h.elements.get('kitchen-touch-landscape').hidden,'an editor viewport resize does not show the rotate screen');
 h.fire('touch-action','pointerdown',{pointerId:2});assert(!callNames().includes('press'),'editing blocks gameplay actions');
 input.blur();h.document.dispatchEvent(new h.Event('focusout'));h.resize(844,390);
 assert(!callNames().some(name=>['resume','main'].includes(name)),'finishing editing does not resume automatically');
 const desktop=harness(path,{width:1280,height:720,touch:false});desktop.publish({});
 const root=desktop.document.getElementById('kitchen-touch-ui');
 assert(root.hidden&&!desktop.document.body.classList.contains('kitchen-touch-mode'),'desktop does not activate touch layout');
 const touchLaptop=harness(path,{width:1280,height:720,touch:true});touchLaptop.publish({});
 assert(touchLaptop.document.getElementById('kitchen-touch-ui').hidden,'large touch laptops retain desktop layout');
 const english=harness(path,{language:'en'});english.publish({interaction:'操作',handLabel:'手中：干净餐盘',mainLabel:'开始经营'});
 const translated=['touch-action','touch-dash','touch-menu-title','touch-menu-copy','touch-main','touch-menu-toggle','touch-settings','touch-help','touch-end','touch-record','touch-bookmark','touch-communication','touch-pause','touch-cancel','touch-instructions','touch-rotate-title','touch-rotate-copy','touch-hand'];
 assert.deepEqual(translated.map(id=>[id,english.elements.get(id).textContent]).filter(([,value])=>/[\u3400-\u9fff]/.test(value)),[],
                  'English touch labels must all use the display catalog');
 english.w.kitchenI18n.setLanguage('zh');english.w.dispatchEvent(new english.Event('kitchen-language-changed'));
 assert.equal(english.elements.get('touch-action').textContent,'操作','touch labels switch back to Chinese');
 english.w.kitchenI18n.setLanguage('en');english.w.dispatchEvent(new english.Event('kitchen-language-changed'));
 assert.equal(english.elements.get('touch-action').textContent,'Action','touch labels switch back to English');
 console.log(`${path}: multi-touch movement/action/dash, deadzone, cancellation, orientation, background and input gates passed.`);
}

for(const path of ['cocos-kitchen/touch-controls.js','cocos-kitchen/build/web/touch-controls.js'])check(path);
