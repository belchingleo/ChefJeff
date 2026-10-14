// Pure JavaScript transport unit tests: no browser automation and no paid API.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('hosted/browser-agent.js','utf8');
const key='unit-test-key-not-a-real-credential';
function harness(saved=null, fail=false, sessions=[201]){
 const calls=[],data=new Map(saved?[['chefjeff.browser-key.v1',JSON.stringify(saved)]]:[]),timers=[];
 const listeners=new Map();let clock=0;
 const native=async(url,init={})=>{
  calls.push({url:String(url),init});
  const u=new URL(url,'https://kitchen.example');
  if(u.origin!=='https://kitchen.example'){
   if(fail)throw new TypeError('blocked');
   return new Response(JSON.stringify({choices:[{message:{content:'{"choice":"wait","sprint":false}'}}],usage:{prompt_tokens:3,completion_tokens:4}}));
  }
  if(u.pathname==='/api/session'){
   const status=sessions.length>1?sessions.shift():sessions[0];
   return new Response(JSON.stringify(status===201?{session:'test-session'}:{error:'Kitchens full.'}),{status});
  }
  if(u.pathname==='/api/state')return new Response(JSON.stringify({game_id:'round',phase:'ready',limits:{},connection:{configured:false}}));
  return new Response('{"ok":true}');
 };
 const w={fetch:native,addEventListener:(name,fn)=>listeners.set(name,fn),dispatchEvent:()=>{}};
 vm.runInNewContext(source,{window:w,location:{href:'https://kitchen.example/',origin:'https://kitchen.example'},
  Response,URL,Headers,AbortController,performance:{now:()=>clock},crypto:require('node:crypto').webcrypto,
  CustomEvent:class {constructor(type,options){this.type=type;this.detail=options.detail;}},
  setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout:()=>{},
  document:{getElementById:()=>null},localStorage:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}});
 return {w,calls,data,listeners,advance:ms=>{clock+=ms;}};
}
const cfg={provider:'deepseek',model:'test-model',api_key:key,remember:false};
function settingsHarness(){
 const html=fs.readFileSync('cocos-kitchen/web-shell.html','utf8');
 const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).find(s=>s.includes('let state=null,busy=false'));
 const elements=new Map(),listeners=new Map();
 const el=id=>{
  if(!elements.has(id))elements.set(id,{value:id==='api-provider'?'jev':'',disabled:false,checked:false,
   addEventListener:()=>{},showModal(){this.open=true;},close(){this.open=false;}});
  return elements.get(id);
 };
 let requests=0;
 vm.runInNewContext(script,{document:{getElementById:el},kitchenTabs:()=>()=>{},
  window:{addEventListener:(name,fn)=>listeners.set(name,fn),chefjeffHostedStatus:()=> '厨房暂时已满'},
  fetch:()=>{requests++;throw new Error('A draft must never request the model.');},AbortController,
  setTimeout:()=>0,clearTimeout:()=>{},crypto:require('node:crypto').webcrypto});
 return {el,listeners,requests:()=>requests};
}
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
 h=harness(null,false,[503,201]);
 r=await h.w.fetch('/api/state');assert.equal(r.status,503);assert((await r.json()).error.includes('厨房'));
 for(let i=0;i<5;i++)await h.w.fetch('/api/state');
 assert.equal(h.calls.filter(c=>c.url==='/api/session').length,1);
 h.advance(15001);r=await h.w.fetch('/api/state');assert.equal(r.status,200);
 assert.equal(h.w.chefjeffHostedStatus(),'');
 h.listeners.get('pagehide')({persisted:true});
 assert(!h.calls.some(c=>c.url==='/api/session/close'));
 h.listeners.get('pagehide')({persisted:false});
 const close=h.calls.find(c=>c.url==='/api/session/close');
 assert(close);assert.equal(close.init.keepalive,true);assert.equal(close.init.headers['X-ChefJeff-Session'],'test-session');
 assert(!JSON.stringify(close).includes(key));
 const ui=settingsHarness();ui.listeners.get('kitchen-open-connection')();
 assert.equal(ui.el('api-provider').disabled,false);assert.equal(ui.el('api-key').disabled,false);
 assert.equal(ui.el('api-connect').disabled,true);assert(ui.el('api-editing-status').textContent.includes('厨房暂时已满'));
 ui.el('api-key').value=key;
 ui.el('api-form').onsubmit({preventDefault(){}});assert.equal(ui.requests(),0);
 const detail={connection:{configured:false,editable:false},limits:{editable:false,usage:{input_tokens:0,output_tokens:0}}};
 ui.listeners.get('kitchen-state')({detail});
 assert.equal(ui.el('api-key').value,key);assert.equal(ui.el('api-key').disabled,false);
 assert.equal(ui.el('api-connect').disabled,true);
 ui.el('api-form').onsubmit({preventDefault(){}});assert.equal(ui.requests(),0);
 detail.connection.editable=true;ui.listeners.get('kitchen-state')({detail});
 assert.equal(ui.el('api-connect').disabled,false);assert.equal(ui.el('api-key').value,key);
 console.log('Browser transport and settings: credential isolation, session retry/release, editable drafts and guarded connection checks passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
