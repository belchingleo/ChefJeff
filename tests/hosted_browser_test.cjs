// Pure JavaScript transport unit tests: no browser automation and no paid API.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('hosted/browser-agent.js','utf8');
const key='unit-test-key-not-a-real-credential';
function harness(saved=null, fail=false, gameState={game_id:'round',phase:'ready',limits:{},connection:{configured:false}}){
 const calls=[],data=new Map(saved?[['chefjeff.browser-key.v1',JSON.stringify(saved)]]:[]),timers=[];
 const listeners={},elements={};
 for(const id of ['contribution-save','contribution-consent','contribution-preview','contribution-data',
   'contribution-download','contribution-delete','contribution-status','contribution-receipt'])elements[id]={disabled:true,checked:false};
 const document={getElementById:id=>elements[id]||null,querySelector:()=>null,activeElement:null};
 const native=async(url,init={})=>{
  calls.push({url:String(url),init});
  const u=new URL(url,'https://kitchen.example');
  if(u.origin!=='https://kitchen.example'){
   if(fail)throw new TypeError('blocked');
   return new Response(JSON.stringify({choices:[{message:{content:'{"choice":"wait","sprint":false}'}}],usage:{prompt_tokens:3,completion_tokens:4}}));
  }
  if(u.pathname==='/api/session')return new Response(JSON.stringify({session:'test-session'}),{status:201});
  if(u.pathname==='/api/state')return new Response(JSON.stringify(gameState));
  return new Response('{"ok":true}');
 };
 const w={fetch:native,addEventListener:(name,fn)=>{listeners[name]=fn;},
   dispatchEvent:e=>{listeners[e.type]?.(e);}};
 vm.runInNewContext(source,{window:w,location:{href:'https://kitchen.example/',origin:'https://kitchen.example'},
  Response,URL,Headers,AbortController,performance,crypto:require('node:crypto').webcrypto,
  setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout:()=>{},
  document,localStorage:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}});
 return {w,calls,data,listeners,elements,document};
}

// Execute the real key handler and state poll with rendering stubbed out. Check both
// TypeScript source and the included web runtime so a stale build cannot hide a fix.
function clientHarness(h, fromSource){
 const cc={Component:function(){},Camera:class{},UITransform:class{},sys:{isNative:true},game:{frameRate:15},
   _decorator:{ccclass:()=>cls=>cls},cclegacy:{_RF:{push:()=>{},pop:()=>{}}}};
 const art={LevelOneArt:class{}},audio={KitchenAudio:class{onState(){}}};
 const geometry={GRID_ART:{tile:48,originX:0,originY:0}};
 const context=vm.createContext({...cc,...art,...audio,...geometry,window:h.w,document:h.document,
   URLSearchParams,location:{search:''},Event:class{constructor(type){this.type=type;}},
   CustomEvent:class{constructor(type,options={}){this.type=type;this.detail=options.detail;}}});
 let Client;
 if(fromSource){
  const ts=fs.readFileSync('cocos-kitchen/assets/scripts/KitchenClient.ts','utf8')
   .replace(/^import[\s\S]*?;\n/gm,'').replace(/^@ccclass\('KitchenClient'\)\n/m,'')
   .replace('export class KitchenClient','class KitchenClient');
  vm.runInContext(require('node:module').stripTypeScriptTypes(ts)+'\nglobalThis.TestClient=KitchenClient;',context);
  Client=context.TestClient;
 }else{
  const modules=new Map(),cache=new Map([['cc',cc],['chunks:///_virtual/LevelOneArt.ts',art],
   ['chunks:///_virtual/KitchenAudio.ts',audio],['chunks:///_virtual/KitchenGeometry.ts',geometry]]);
  context.System={register:(name,deps,factory)=>{
   if(typeof name!=='string'){deps(name=>name).execute();return;}
   modules.set(name,{deps,factory});
  }};
  for(const path of ['cocos-kitchen/build/web/src/chunks/bundle.js','cocos-kitchen/build/web/assets/main/index.js'])
   vm.runInContext(fs.readFileSync(path,'utf8'),context);
  const load=name=>{
   if(cache.has(name))return cache.get(name);
   const out={},module=modules.get(name);
   const instance=module.factory((key,value)=>{if(typeof key==='string')out[key]=value;else Object.assign(out,key);return value;});
   cache.set(name,out);
   module.deps.forEach((dep,i)=>instance.setters?.[i]?.(load(dep==='cc'?dep:'chunks:///_virtual/'+dep.replace(/^\.\//,''))));
   instance.execute();return out;
  };
  Client=load('chunks:///_virtual/KitchenClient.ts').KitchenClient;
 }
 const client=new Client();cc.sys.isNative=false;
 for(const method of ['enable','render','processEvents','hideLoading'])client[method]=()=>{};
 client.mounted=client.artLoaded=client.connected=true;client.mountedLayout='level-2-1';
 client.state={game_id:'round'};
 return client;
}

async function checkClientInteractions(fromSource){
 const gameState={game_id:'round',phase:'ended',limits:{},release:{version:'0.6.0-beta.1'},
  hosted:{contribution_enabled:true},interaction:null,interaction_focus:'counter14',
  kitchen:{map:{layout_version:'level-2-1'},stations:{counter14:{}},chefs:{human:{holding:{id:'held'}}}}};
 const h=harness(null,false,gameState),client=clientHarness(h,fromSource);
 h.listeners.DOMContentLoaded();
 client.request=async()=>await (await h.w.fetch('/api/state')).json();
 await client.poll();
 h.elements['contribution-consent'].checked=true;h.elements['contribution-consent'].onchange();
 assert.equal(h.elements['contribution-save'].disabled,false);
 await client.poll();
 assert.equal(h.elements['contribution-save'].disabled,false,'state polling must preserve explicit consent');
 gameState.phase='running';await client.poll();
 assert.equal(h.elements['contribution-save'].disabled,true,'unfinished rounds cannot be contributed');
 gameState.phase='ended';gameState.hosted.contribution_enabled=false;await client.poll();
 assert.equal(h.elements['contribution-save'].disabled,true,'disabled storage must keep contribution disabled');

 const posts=[];client.post=(path,body)=>{posts.push({path,body});};client.state.phase='running';
 const human=client.state.kitchen.chefs.human;
 const press=(extra={})=>client.onKey({key:' ',code:'Space',preventDefault:()=>{},...extra});
 const release=()=>client.onKeyUp({key:' ',code:'Space'});
 const reset=()=>{client.clearInput();posts.length=0;client.clock=5;human.holding={id:'held'};human.can_throw=true;human.facing='up';};
 // A hold must not first consume the item through a legal station action. A tap
 // still sends interact once, including blocked targets whose reason comes from the server.
 for(const [focus,kind] of [['counter14',null],['counter14','put_counter'],['serve','serve'],
   ['bin','discard'],['burning_stove','stop'],['floor_5_6',null],['floor_5_6','drop'],['floor_5_6','swap']]){
  reset();client.state.interaction_focus=focus;client.state.interaction=kind?{kind}:null;
  press();assert.equal(client.spaceDownAt,5);assert.equal(posts.length,0,`keydown must defer ${kind||'blocked'} interaction`);
  client.clock+=.1;press({repeat:true});assert.equal(client.spaceDownAt,5,'repeat must not restart the hold');
  release();release();assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/interact');
  assert.equal(posts[0].body.expected_item,'held');

  reset();press();client.clock+=.31;client.startAim();
  assert.deepEqual({...client.aiming},{x:0,y:-1},`holding Space can aim at ${focus}`);
  client.onKey({key:'d',code:'KeyD',preventDefault:()=>{}});
  client.onKeyUp({key:'d',code:'KeyD'});press({repeat:true});
  assert.equal(posts.length,0,'aiming must not interact with the workstation');
  release();release();assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/throw');
  assert.equal(posts[0].body.expected_item,'held');assert.deepEqual([...posts[0].body.direction],[1,0]);
 }
 // Empty hands and rulesets that prohibit throwing keep their immediate interaction.
 for(const hand of [null,{id:'held'}]){
  reset();human.holding=hand;human.can_throw=false;
  press();release();assert.equal(client.spaceDownAt,null);assert.equal(posts.length,1);
  assert.equal(posts[0].path,'/api/interact');assert.equal(posts[0].body.expected_item,hand?.id||null);
 }
 // Never interact with or throw a replacement item acquired while Space was held.
 for(const alreadyAiming of [false,true]){
  reset();press();if(alreadyAiming)client.startAim();human.holding={id:'replacement'};
  release();assert.equal(posts.length,0);assert.equal(client.aiming,null);
 }
 reset();press();human.holding=null;client.startAim();release();
 assert.equal(posts.length,0);assert.equal(client.aiming,null);
 reset();press();client.connected=false;release();client.connected=true;
 assert.equal(posts.length,0,'disconnect cancels the pending action');
 reset();press();client.onKey({key:'Escape',preventDefault:()=>{}});release();
 assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/pause','pausing cancels the pending action');
 reset();press();client.startAim();client.onBlur();release();
 assert.equal(posts.length,0,'losing focus cancels aiming');
}

async function checkClientTouchBridge(fromSource){
 const h=harness(),client=clientHarness(h,fromSource),posts=[],moves=[];
 client.clock=5;
 client.state={game_id:'touch-round',phase:'running',speed:1,limits:{},connection:{configured:true},
  interaction:{kind:'put_counter',label:'放下'},interaction_focus:'counter14',interaction_hint:'',
  kitchen:{map:{layout_version:'level-2-1'},stations:{counter14:{}},orders:[],goals:{target_money:100},
   chefs:{human:{holding:{id:'held'},can_throw:true,facing:'up',sprint:{available:true,cooldown_remaining:0,active_remaining:0}}}},
  ai:{thinking:false,error:null}};
 client.post=(path,body)=>{posts.push({path,body});};
 client.request=async(path,body)=>{if(path==='/api/move')moves.push(body);return {ok:true};};
 client.installControls();
 const controls=h.w.kitchenControls;
 assert(controls,'client installs a touch bridge without rendering');
 for(const method of ['move','press','release','cancel','dash','pause','resume','main','settings','help','end','record','bookmark','block','getState'])
  assert.equal(typeof controls[method],'function',`bridge method ${method}`);
 assert.equal(controls.getState().game_id,'touch-round');assert.equal(controls.getState().phase,'running');
 assert.equal(controls.getState().canThrow,true);
 const human=client.state.kitchen.chefs.human;
 const flush=()=>client.flushTouchMove();
 const clear=()=>{client.clearInput();posts.length=0;moves.length=0;client.clock+=1;human.holding={id:'held'};human.can_throw=true;human.sprint={available:true,cooldown_remaining:0,active_remaining:0};};
 controls.move(NaN,1);controls.move(1,Infinity);flush();assert.equal(moves.length,0,'non-finite touch coordinates are ignored');
 for(let i=1;i<=100;i++)controls.move(1,i);
 assert.equal(moves.length,0,'pointer movement is buffered instead of sending one request per event');
 flush();assert.equal(moves.length,1,'a buffered movement flush sends the latest direction once');
 controls.move(0,0);assert.equal(moves.length,2,'releasing the joystick bypasses the movement buffer');
 clear();
 controls.move(1,1);flush();
 assert(Math.abs(moves.at(-1).dx-Math.SQRT1_2)<1e-8&&Math.abs(moves.at(-1).dy-Math.SQRT1_2)<1e-8,'touch diagonals share keyboard walking speed');
 controls.press();assert.equal(posts.length,0,'holding a throwable item defers station interaction');
 client.clock+=.31;client.startAim();assert(controls.getState().aiming,'bridge exposes active aiming');
 assert.deepEqual({...client.manualDirection},{x:0,y:0},'aiming stops walking');
 controls.move(-1,0);flush();assert.deepEqual({...client.aiming},{x:-1,y:0});
 controls.release();controls.release();assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/throw');
 assert.deepEqual([...posts[0].body.direction],[-1,0]);assert.equal(posts[0].body.expected_item,'held');
 const count=moves.length;controls.move(-1,0);flush();
 assert.deepEqual({...client.manualDirection},{x:0,y:0},'after throwing, a displaced joystick cannot start walking');
 assert(!moves.slice(count).some(m=>m.dx||m.dy),'after throwing, a displaced joystick sends no walking request');
 controls.move(0,0);controls.move(0,-1);flush();assert.equal(client.manualDirection.y,-1,'returning the joystick to neutral unlocks walking');
 controls.move(0,0);assert.deepEqual({...client.manualDirection},{x:0,y:0});
 assert.equal(moves.at(-1).dx,0);assert.equal(moves.at(-1).dy,0,'touch stop flushes immediately');

 clear();controls.press();controls.release();controls.release();assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/interact');
 clear();human.holding=null;controls.press();controls.release();assert.equal(posts.length,1);assert.equal(posts[0].body.expected_item,null,'empty-hand interaction uses the same action path');
 for(const aiming of [false,true]){
  clear();controls.press();if(aiming){client.clock+=.31;client.startAim();}
  human.holding={id:'replacement'};controls.release();assert.equal(posts.length,0,'touch cannot act on an item replaced during a hold');
  assert.equal(client.aiming,null);
 }
 // State polling cancels the arrow immediately when the held item disappears
 // or the rules change, instead of waiting for a finger to lift.
 const moveRequest=client.request;
 for(const changed of [{holding:{id:'replacement'}},{holding:null},{can_throw:false}]){
  clear();controls.press();client.clock+=.31;client.startAim();assert(client.aiming);
  Object.assign(human,changed);
  client.request=async()=>({...client.state,release:{version:'0.6.0-beta.1'}});
  await client.poll();assert.equal(client.aiming,null,'a changed held-item snapshot cancels aiming immediately');
  controls.release();assert.equal(posts.length,0,'a cancelled snapshot cannot throw or tap');
 }
 client.request=moveRequest;
 clear();controls.move(1,0);flush();controls.press();client.clock+=.31;client.startAim();controls.cancel();controls.release();
 assert.equal(posts.length,0,'touch cancellation cannot release a throw');assert.equal(client.aiming,null);assert.deepEqual({...client.manualDirection},{x:0,y:0});
 clear();controls.press();client.state.phase='paused';controls.release();assert.equal(posts.length,0,'paused state cancels a pending tap');client.state.phase='running';
 clear();controls.press();client.connected=false;controls.release();assert.equal(posts.length,0,'disconnect cancels a pending touch action');client.connected=true;

 clear();controls.dash();assert(!moves.some(m=>m.sprint),'stationary touch cannot dash');
 controls.move(1,0);flush();controls.dash();assert.equal(moves.filter(m=>m.sprint).length,1,'moving touch dashes through the existing move endpoint');
 human.sprint={available:false,cooldown_remaining:2,active_remaining:0};controls.dash();assert.equal(moves.filter(m=>m.sprint).length,1,'touch respects sprint cooldown');
 human.sprint={available:true,cooldown_remaining:0,active_remaining:0};controls.press();client.clock+=.31;client.startAim();controls.dash();assert.equal(moves.filter(m=>m.sprint).length,1,'aiming cannot dash');

 clear();controls.move(1,0);flush();controls.press();controls.block(true);controls.release();
 assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/pause','blocking controls pauses the live round');
 assert.equal(client.aiming,null);assert.deepEqual({...client.manualDirection},{x:0,y:0});
 posts.length=0;moves.length=0;controls.move(1,0);flush();controls.press();controls.release();controls.dash();
 assert.equal(posts.length,0,'blocked gameplay sends no actions');assert(!moves.some(m=>m.dx||m.dy),'blocked gameplay sends no movement');
 controls.block(false);assert.equal(posts.length,0,'unblocking never resumes a round automatically');
 clear();client.onKey({key:'w',code:'KeyW',preventDefault:()=>{}});assert.equal(client.manualDirection.y,-1,'desktop keyboard walking remains available');
 client.onKeyUp({key:'w',code:'KeyW'});assert.equal(client.manualDirection.y,0);
 // Phone players can connect from the primary button; feedback on the hidden
 // desktop canvas would otherwise make this first-use button appear inert.
 let settingsOpened=0,mainCalled=0;
 client.openConnection=()=>{settingsOpened++;};client.buttons.main={enabled:true,callback:()=>{mainCalled++;}};
 client.state.phase='ready';client.state.connection={configured:false};client.touchLayout={active:true,landscape:true};
 controls.main();assert.equal(settingsOpened,1,'unconfigured phone main opens connection settings');assert.equal(mainCalled,0);
 client.state.connection.configured=true;controls.main();assert.equal(mainCalled,1,'configured phone main runs the existing start action');assert.equal(settingsOpened,1);
 client.touchLayout={active:false,landscape:true};client.state.connection.configured=false;controls.main();
 assert.equal(mainCalled,2,'desktop main preserves its existing callback');assert.equal(settingsOpened,1);
 client.touchLayout={active:true,landscape:false};controls.main();assert.equal(settingsOpened,1,'portrait cannot activate the primary button');
 client.touchLayout.landscape=true;client.pending=true;controls.main();assert.equal(settingsOpened,1,'a pending action cannot reopen settings');
 // The scene's Camera is a child of Canvas too. Hiding phone HUD siblings must
 // leave that camera running, otherwise the canvas freezes without an error.
 const node=(name,active=true)=>({name,active,isValid:true,children:[],position:{x:0,y:0},
  getComponent:type=>type?.name==='UITransform'&&!['Camera','audio'].includes(name)?{}:null,
  getComponentsInChildren:()=>name==='Camera'?[{}]:[],
  setScale(x,y,z){this.scale={x,y,z};},setPosition(x,y){this.position={x,y};}});
 const camera=node('Camera'),audio=node('audio'),world=node('kitchen-world'),background=node('background'),cover=node('cover'),hud=node('header');
 client.node={children:[camera,audio,background,world,cover,hud]};client.world=world;
 client.state.kitchen.map.width=15;client.state.kitchen.map.height=11;
 client.touchLayout={active:true,landscape:true,width:844,height:390,boardRect:{left:146,top:74,width:524,height:308}};
 client.applyTouchLayout();
 assert.equal(camera.active,true,'phone layout must keep the scene camera active');assert.equal(audio.active,true,'phone layout must keep audio nodes active');assert.equal(world.active,true);assert.equal(background.active,true);
 assert.equal(cover.active,false);assert.equal(hud.active,false,'phone HTML replaces desktop HUD');
 assert(Number.isFinite(world.scale.x)&&world.scale.x>0&&Number.isFinite(world.position.x)&&Number.isFinite(world.position.y),'phone kitchen transform stays finite');
 client.touchLayout.active=false;client.applyTouchLayout();
 assert.equal(camera.active,true);assert.equal(audio.active,true);assert.equal(cover.active,true);assert.equal(hud.active,true,'desktop layout restores HUD visibility');
 assert.deepEqual({...world.scale},{x:1,y:1,z:1});assert.deepEqual({...world.position},{x:0,y:0});
 // The transport error path restores the desktop reconnect cover. It must then
 // apply the phone layout too, while publishing the disconnected HTML state.
 client.touchLayout.active=true;client.connected=true;client.pending=false;client.cover=cover;
 client.buttons.main.label={};client.buttons.reset={node:{active:true}};client.buttons.record={node:{active:true}};
 client.labels['welcome-tip']={node:{active:false}};client.set=()=>{};client.writeLabel=()=>{};
 let lastControlsState;
 h.w.addEventListener('kitchen-controls-state',event=>{lastControlsState=event.detail;});
 client.request=async()=>{throw new Error('offline test');};
 await client.poll();
 assert.equal(client.connected,false);assert.equal(cover.active,false,'a disconnected phone must not show the desktop reconnect cover');
 assert.equal(camera.active,true);assert.equal(audio.active,true);assert.equal(world.active,true);
 assert.equal(controls.getState().connected,false);assert.equal(lastControlsState.connected,false,'disconnect reaches phone HTML controls');
}
const cfg={provider:'deepseek',model:'test-model',api_key:key,remember:false};
(async()=>{
 let h=harness();await h.w.fetch('/api/state');
 let r=await h.w.fetch('/api/connection',{method:'POST',body:JSON.stringify(cfg)});assert.equal(r.status,200);
 assert.equal(h.data.size,0);
 assert(h.calls.some(c=>c.url.startsWith('https://api.deepseek.com')));
 for(const c of h.calls.filter(c=>!c.url.startsWith('https://api.deepseek.com'))){assert(!JSON.stringify(c).includes(key));assert(!c.url.includes('/api/connection'));}
 const state=await (await h.w.fetch('/api/state')).json();assert(state.connection.configured);assert(!JSON.stringify(state).includes(key));
 h=harness();r=await h.w.fetch('/api/connection',{body:JSON.stringify({...cfg,remember:true})});assert.equal(r.status,200);assert.equal(h.data.size,1);
 await h.w.fetch('/api/connection',{body:JSON.stringify({...cfg,remember:false})});assert.equal(h.data.size,0);
 h=harness(null,true);r=await h.w.fetch('/api/connection',{body:JSON.stringify(cfg)});assert.equal(r.status,400);assert.equal(h.data.size,0);
 assert(!h.calls.some(c=>c.url==='/api/browser-ready'));assert(!h.calls.some(c=>c.url==='/api/connection'));
 h=harness();r=await h.w.fetch('/api/connection',{body:JSON.stringify({...cfg,provider:'compatible',base_url:'https://kitchen.example'})});assert.equal(r.status,400);
 h=harness();let d=await (await h.w.fetch('/api/state')).json();assert.equal(d.connection.configured,false);
 await checkClientInteractions(false);
 await checkClientTouchBridge(false);
 if(require('node:module').stripTypeScriptTypes){await checkClientInteractions(true);await checkClientTouchBridge(true);}
 else console.log('TypeScript source execution requires Node 22.13+; included runtime checked.');
 console.log('Browser transport: memory/remember/clear, reload, CORS failure, origin guard and no-key-to-server checks passed.');
 console.log('Client interactions: workstation/floor tap and hold, item changes, cancellation and hosted contribution state passed.');
 console.log('Client touch bridge: normalized movement, station tap/throw hold, neutral reset, cancellation, sprint and keyboard compatibility passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
