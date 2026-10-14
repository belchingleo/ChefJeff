// Gamepad API simulation: no physical controller, browser automation or model API.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const buttons={A:0,B:1,X:2,Start:9,Up:12,Down:13,Left:14,Right:15};
function pad(index=0,mapping='standard'){
 return {index,id:'test-controller-'+index,mapping,connected:true,axes:[0,0,0,0],
  buttons:Array.from({length:17},()=>({pressed:false,touched:false,value:0}))};
}
function neutral(controller){controller.axes.fill(0);controller.buttons.forEach(button=>{button.pressed=button.touched=false;button.value=0;});}
function button(controller,name,pressed){const value=controller.buttons[typeof name==='number'?name:buttons[name]];value.pressed=value.touched=pressed;value.value=pressed?1:0;}
function harness(path,{available=true,denied=false,secure=true}={}){
 const listeners={},documentListeners={},calls=[],frames=new Map(),elements=new Map();let nextFrame=0,clock=0;
 const pads=[];
 class Event{
  constructor(type,options={}){this.type=type;Object.assign(this,options);}
  preventDefault(){this.defaultPrevented=true;}stopPropagation(){}stopImmediatePropagation(){}
 }
 const target=list=>({addEventListener:(type,fn)=>{(list[type]??=[]).push(fn);},
  removeEventListener:(type,fn)=>{list[type]=(list[type]||[]).filter(f=>f!==fn);},
  dispatchEvent:event=>{for(const fn of list[event.type]||[])fn(event);}});
 class Element{
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.style={setProperty(name,value){this[name]=value;}};this.dataset={};this.children=[];this.attributes={};this.hidden=false;this.textContent='';this.classes=new Set();this.classList={add:(...values)=>values.forEach(value=>this.classes.add(value)),remove:(...values)=>values.forEach(value=>this.classes.delete(value)),contains:value=>this.classes.has(value),toggle:(value,force)=>{const next=force??!this.classes.has(value);next?this.classes.add(value):this.classes.delete(value);return next;}};}
  set id(value){this._id=value;elements.set(value,this);}get id(){return this._id||'';}
  appendChild(child){child.parentElement=this;this.children.push(child);return child;}
  setAttribute(name,value){this.attributes[name]=String(value);}getAttribute(name){return this.attributes[name]??null;}
  removeAttribute(name){delete this.attributes[name];}addEventListener(){}removeEventListener(){}remove(){}
  closest(selector){if(selector.split(',').some(part=>part.trim()===this.tagName.toLowerCase()))return this;return null;}
 }
 const document={...target(documentListeners),readyState:'complete',hidden:false,activeElement:null,
  body:new Element('body'),head:new Element('head'),documentElement:new Element('html'),
  createElement:tag=>new Element(tag),getElementById:id=>elements.get(id)||null,
  querySelector:selector=>selector==='dialog[open]'&&document.modal?document.modal:null,
  querySelectorAll:()=>[],hasFocus:()=>document.focused!==false};
 const requestAnimationFrame=fn=>{const id=++nextFrame;frames.set(id,fn);return id;};
 const cancelAnimationFrame=id=>frames.delete(id);
 const navigator={maxTouchPoints:0,denied};if(available)navigator.getGamepads=()=>{if(navigator.denied)throw new Error('Gamepad access denied');return pads;};
 const w={...target(listeners),navigator,requestAnimationFrame,cancelAnimationFrame,
  performance:{now:()=>clock},matchMedia:()=>({matches:false}),kitchenI18n:{language:'zh',t:text=>text},innerWidth:1280,innerHeight:720,isSecureContext:secure};
 const state={phase:'running',game_id:'round',connected:true,pending:false,canInput:true,canInteract:true,canThrow:true,canDash:true,aiming:null,holding:{id:'held'},mainEnabled:true};
 const controls={getState:()=>({...state})};
 for(const name of ['move','press','release','cancel','dash','pause','resume','main','block'])controls[name]=(...args)=>{calls.push([name,...args]);if(name==='cancel'||name==='release')state.aiming=null;};
 w.kitchenControls=controls;
 const timeout=fn=>{return ++nextFrame;};
 vm.runInNewContext(fs.readFileSync(path,'utf8'),{window:w,document,navigator,Event,CustomEvent:Event,
  requestAnimationFrame,cancelAnimationFrame,performance:w.performance,setTimeout:timeout,clearTimeout:()=>{},queueMicrotask:fn=>fn(),
  HTMLElement:Element,MutationObserver:class{constructor(){}observe(){}disconnect(){}},location:{protocol:'https:'}},{filename:path});
 const step=(count=1)=>{for(let i=0;i<count;i++){clock+=16;const queued=[...frames.values()];frames.clear();queued.forEach(fn=>fn(clock));}};
 const connect=controller=>{while(pads.length<=controller.index)pads.push(null);pads[controller.index]=controller;controller.connected=true;w.dispatchEvent(new Event('gamepadconnected',{gamepad:controller}));};
 const disconnect=controller=>{pads[controller.index]=null;controller.connected=false;w.dispatchEvent(new Event('gamepaddisconnected',{gamepad:controller}));};
 const publish=patch=>{Object.assign(state,patch);w.dispatchEvent(new Event('kitchen-controls-state',{detail:{...state}}));};
 const emit=(type,options={})=>{if(type==='kitchen-touch-mode')document.body.classList.toggle('kitchen-touch-mode',!!options.detail?.active);const event=new Event(type,options);w.dispatchEvent(event);if(['keydown','mousedown','pointerdown'].includes(type))document.dispatchEvent(event);};
 return {w,document,calls,pads,state,controls,frames,step,connect,disconnect,publish,emit,Event,Element,
  clear:()=>{calls.length=0;},count:name=>calls.filter(call=>call[0]===name).length,
  moves:()=>calls.filter(call=>call[0]==='move'&&Math.hypot(call[1],call[2])>0)};
}
function armed(path){const h=harness(path),controller=pad();h.connect(controller);h.step(2);h.clear();return {h,controller};}
function check(path){
 // The adapter does not claim keyboard input merely because a controller exists.
 let {h,controller}=armed(path);h.step(30);assert.equal(h.calls.length,0,'an unused neutral controller must not affect keyboard play');
 controller.axes=[.1,.1,0,0];h.step();assert.equal(h.moves().length,0,'radial dead zone ignores stick drift');
 controller.axes=[.17,.17,0,0];h.step(4);let movement=h.moves().at(-1);assert(movement,'radial input can leave the dead zone even when each individual axis is smaller');
 controller.axes=[.5,0,0,0];h.step(4);movement=h.moves().at(-1);assert(movement);assert.equal(movement[1],1);assert.equal(movement[2],0,'analog stick uses the current walking speed');
 controller.axes=[.41,.83,0,0];h.step(4);movement=h.moves().at(-1);const magnitude=Math.hypot(.41,.83);
 assert(Math.abs(movement[1]-.41/magnitude)<1e-8&&Math.abs(movement[2]-.83/magnitude)<1e-8,'analog direction retains precision between eight-way directions');
 const heldMoveCount=h.moves().length;h.step(30);assert.equal(h.moves().length,heldMoveCount,'holding an unchanged stick does not flood the action bridge');
 controller.axes=[1,1,0,0];h.step(4);movement=h.moves().at(-1);assert(Math.abs(movement[1]-Math.SQRT1_2)<1e-8&&Math.abs(movement[2]-Math.SQRT1_2)<1e-8,'diagonal movement is normalized');
 button(controller,'Up',true);button(controller,'Right',true);controller.axes=[-1,0,0,0];h.step(4);movement=h.moves().at(-1);
 assert(Math.abs(movement[1]-Math.SQRT1_2)<1e-8&&Math.abs(movement[2]+Math.SQRT1_2)<1e-8,'D-pad takes priority over the analog stick');
 neutral(controller);h.step();assert.deepEqual(h.calls.filter(call=>call[0]==='move').at(-1),['move',0,0],'neutral movement stops immediately');
 button(controller,'A',true);h.step(60);assert.equal(h.count('press'),1,'holding A sends one press, preserving long-hold aiming');assert.equal(h.count('release'),0);
 button(controller,'A',false);h.step(2);assert.equal(h.count('release'),1,'lifting A releases once');
 controller.axes=[1,0,0,0];h.step();button(controller,'X',true);h.step(15);assert.equal(h.count('dash'),1,'X is an edge-triggered dash');
 button(controller,'X',false);h.step();h.publish({canDash:false,sprint:{available:false,active_remaining:0,cooldown_remaining:2}});button(controller,'X',true);h.step();assert.equal(h.count('dash'),1,'unavailable sprint is not sent');

 // X must flush this frame's direction before dashing, including a new push
 // 16 ms after stopping and a turn inside the movement throttle/noise window.
 ({h,controller}=armed(path));controller.axes=[1,0,0,0];h.step();neutral(controller);h.step();h.clear();
 controller.axes=[0,-1,0,0];h.step();
 assert.deepEqual(h.calls.filter(call=>call[0]==='move').at(-1),['move',0,-1],'a new push 16 ms after stopping starts walking immediately');
 for(const timing of ['after-stop','fast-turn','small-turn']){
  ({h,controller}=armed(path));let lastDirection={x:0,y:0};
  h.controls.move=(x,y)=>{lastDirection={x,y};h.calls.push(['move',x,y]);};
  const desired=timing==='small-turn'?{x:1/Math.hypot(1,.001),y:.001/Math.hypot(1,.001)}:{x:0,y:-1};
  h.controls.dash=()=>{assert(Math.abs(lastDirection.x-desired.x)<1e-8&&Math.abs(lastDirection.y-desired.y)<1e-8,`${timing} dash must use the latest direction`);h.calls.push(['dash']);};
  controller.axes=[1,0,0,0];h.step();
  if(timing==='after-stop'){neutral(controller);h.step();assert.deepEqual(lastDirection,{x:0,y:0});}
  h.clear();controller.axes=timing==='small-turn'?[1,.001,0,0]:[0,-1,0,0];button(controller,'X',true);h.step();
  assert.equal(h.count('dash'),1,`${timing} X triggers the dash within one frame`);
  const moveAt=h.calls.findIndex(call=>call[0]==='move'),dashAt=h.calls.findIndex(call=>call[0]==='dash');
  assert(moveAt>=0&&moveAt<dashAt,`${timing} direction is sent before the dash`);
 }
 ({h,controller}=armed(path));const moveTimes=[];
 h.controls.move=(x,y)=>{h.calls.push(['move',x,y]);if(x||y)moveTimes.push(h.w.performance.now());};
 for(let i=0;i<60;i++){controller.axes=[Math.cos(i*.02),Math.sin(i*.02),0,0];h.step();}
 assert(moveTimes.length>=10,'sustained steering continues to update direction');
 for(let i=1;i<moveTimes.length;i++)assert(moveTimes[i]-moveTimes[i-1]>=50,'ordinary continuous steering stays at most 20 Hz');

 ({h,controller}=armed(path));button(controller,'A',true);h.step();h.publish({aiming:{x:0,y:1}});button(controller,'B',true);h.step();
 assert.equal(h.count('cancel'),1,'B cancels the owned interaction or aim');button(controller,'B',false);button(controller,'A',false);h.step();
 assert.equal(h.count('release'),0,'the cancelled A release cannot throw');button(controller,'A',true);h.step();assert.equal(h.count('press'),2,'a fresh A press works after cancellation');

 ({h,controller}=armed(path));button(controller,'Start',true);h.step(20);assert.equal(h.count('pause'),1,'Start pauses once');
 h.publish({phase:'paused',canInput:false});h.clear();h.step(5);assert.equal(h.count('resume'),0,'held Start does not immediately resume');
 neutral(controller);h.step();button(controller,'Start',true);h.step();assert.equal(h.count('resume'),1,'a fresh Start resumes a paused round');
 h.publish({phase:'ready',canInput:false,mainEnabled:true});neutral(controller);h.step();button(controller,'Start',true);h.step();assert.equal(h.count('main'),1,'Start activates ready main after neutral');
 h.publish({phase:'ended',canInput:false});neutral(controller);h.step();button(controller,'Start',true);h.step();assert.equal(h.count('main'),1,'ended rounds do not restart from a gamepad button');

 ({h,controller}=armed(path));h.publish({pending:true});button(controller,'Start',true);h.step();
 assert.equal(h.count('pause'),1,'a pending interaction cannot block an emergency Start pause');
 h.publish({phase:'paused',canInput:false,pending:true});neutral(controller);h.step();button(controller,'Start',true);h.step();
 assert.equal(h.count('resume'),0,'resume still waits for a pending request');
 neutral(controller);h.step();h.publish({pending:false});button(controller,'Start',true);h.step();assert.equal(h.count('resume'),1);
 h.publish({phase:'ready',canInput:false,pending:true,mainEnabled:true});neutral(controller);h.step();button(controller,'Start',true);h.step();
 assert.equal(h.count('main'),0,'starting a round waits for a pending request');
 neutral(controller);h.step();h.publish({pending:false});button(controller,'Start',true);h.step();assert.equal(h.count('main'),1);

 // On connection, even unassigned buttons must return to neutral first.
 h=harness(path);controller=pad();controller.axes=[1,0,0,0];button(controller,'A',true);button(controller,5,true);h.connect(controller);h.step(10);
 assert.equal(h.moves().length,0);assert.equal(h.count('press'),0,'connecting a held controller sends no action');
 controller.axes.fill(0);button(controller,'A',false);h.step();button(controller,'A',true);h.step();assert.equal(h.count('press'),0,'an unassigned held button still prevents arming');
 neutral(controller);h.step();button(controller,'A',true);h.step();assert.equal(h.count('press'),1,'neutral then fresh input arms the controller');

 // Interruptions clear owned state and require a fresh neutral/button cycle.
 for(const kind of ['blur','hidden','editor','dialog','paused','new-round','offline','blocked','touch-mode']){
  ({h,controller}=armed(path));controller.axes=[1,0,0,0];button(controller,'A',true);h.step();h.clear();
  if(kind==='blur')h.emit('blur');
  if(kind==='hidden'){h.document.hidden=true;h.document.dispatchEvent(new h.Event('visibilitychange'));}
  if(kind==='editor')h.document.activeElement=new h.Element('input');
  if(kind==='dialog')h.document.modal=new h.Element('dialog');
  if(kind==='paused')h.publish({phase:'paused',canInput:false});
  if(kind==='new-round')h.publish({game_id:'next-round'});
  if(kind==='offline')h.publish({connected:false,canInput:false});
  if(kind==='blocked')h.publish({canInput:false});
  if(kind==='touch-mode')h.emit('kitchen-touch-mode',{detail:{active:true,landscape:true}});
  h.step(3);assert(h.count('cancel')>=1,`${kind} cancels the controller's action`);assert.equal(h.count('release'),0,`${kind} cannot release a throw`);
  h.clear();h.emit('focus');h.document.hidden=false;h.document.activeElement=null;h.document.modal=null;
  h.publish({phase:'running',connected:true,canInput:true});h.emit('kitchen-touch-mode',{detail:{active:false}});h.step(5);
  assert.equal(h.moves().length,0);assert.equal(h.count('press'),0,`${kind} recovery must not reuse held input`);
  neutral(controller);h.step();button(controller,'A',true);h.step();assert.equal(h.count('press'),1,`${kind} accepts a fresh press after neutral`);
 }

 ({h,controller}=armed(path));controller.axes=[1,0,0,0];button(controller,'A',true);h.step();h.clear();h.disconnect(controller);h.step();
 assert(h.count('cancel')>=1,'disconnect cancels active gamepad input');assert.equal(h.count('release'),0);assert.equal(h.count('pause'),1,'disconnect pauses an owned live round');
 h.clear();h.connect(controller);h.step(5);assert.equal(h.moves().length,0);assert.equal(h.count('press'),0,'reconnecting cannot reuse the previously held controls');
 neutral(controller);h.step();button(controller,'A',true);h.step();assert.equal(h.count('press'),1,'reconnection accepts a fresh action after neutral');
 ({h,controller}=armed(path));h.clear();h.disconnect(controller);h.step();assert.equal(h.calls.length,0,'disconnecting an unused gamepad leaves keyboard input alone');

 for(const type of ['kitchen-manual-input','keydown','mousedown','pointerdown']){
  ({h,controller}=armed(path));controller.axes=[1,0,0,0];h.step();h.clear();h.emit(type,{key:'d',code:'KeyD',button:0,isTrusted:true,target:new h.Element('canvas')});
  h.step(5);assert(h.count('cancel')>=1,`${type} hands input back to keyboard/mouse`);assert.equal(h.moves().length,0,`${type} cannot be overridden by the held stick`);
  h.clear();h.disconnect(controller);h.step();assert.equal(h.calls.length,0,`${type} takeover stops the disconnected gamepad from pausing keyboard play`);
 }
 h=harness(path);controller=pad(1);h.connect(controller);h.step(2);controller.axes=[1,0,0,0];h.step();
 const second=pad(0);second.axes=[-1,0,0,0];button(second,'Start',true);h.clear();h.connect(second);h.step(5);
 assert.equal(h.count('pause'),0,'a second gamepad cannot interrupt the selected controller');assert(!h.moves().some(call=>call[1]<0),'a second gamepad cannot steal movement');
 h.disconnect(second);h.step();assert.equal(h.count('cancel'),0,'disconnecting another gamepad does not cancel the selected one');
 h=harness(path);controller=pad(0,'');controller.axes=[1,0,0,0];button(controller,'A',true);h.connect(controller);h.step(5);assert.equal(h.calls.length,0,'unmapped controllers are not guessed');
 for(const options of [{available:false},{denied:true},{secure:false}]){h=harness(path,options);h.step(10);assert.equal(h.calls.length,0,'unsupported, insecure or denied Gamepad API does not disturb keyboard play');}
 ({h,controller}=armed(path));controller.axes=[1,0,0,0];button(controller,'A',true);h.step();h.clear();h.w.navigator.denied=true;h.step(3);
 assert(h.count('cancel')>=1);assert.equal(h.count('release'),0);assert.equal(h.count('pause'),1,'loss of Gamepad API access pauses owned gameplay safely');
 console.log(`${path}: mapping, movement, button edges, cancellation, neutral recovery, ownership and unsupported API checks passed.`);
}
const entries=['cocos-kitchen/gamepad-controls.js','cocos-kitchen/build/web/gamepad-controls.js'];
assert.equal(fs.readFileSync(entries[0],'utf8'),fs.readFileSync(entries[1],'utf8'),'source and shipped gamepad controls must match');
for(const path of entries)check(path);
