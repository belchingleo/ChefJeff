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
 const cc={Component:function(){},sys:{isNative:true},game:{frameRate:15},
   _decorator:{ccclass:()=>cls=>cls},cclegacy:{_RF:{push:()=>{},pop:()=>{}}}};
 const art={LevelOneArt:class{}},audio={KitchenAudio:class{onState(){}}};
 const geometry={GRID_ART:{tile:48,originX:0,originY:0}};
 const context=vm.createContext({...cc,...art,...audio,...geometry,window:h.w,document:h.document,
   URLSearchParams,location:{search:''},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}}});
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
 if(require('node:module').stripTypeScriptTypes)await checkClientInteractions(true);
 else console.log('TypeScript source execution requires Node 22.13+; included runtime checked.');
 console.log('Browser transport: memory/remember/clear, reload, CORS failure, origin guard and no-key-to-server checks passed.');
 console.log('Client interactions: workstation/floor tap and hold, item changes, cancellation and hosted contribution state passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
