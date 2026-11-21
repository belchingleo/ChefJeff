// Hosted transport: a same-origin /api/ request keeps its query string when browser-agent.js forwards it.
// (Before 2026-11-21 it forwarded url.pathname only, so the level editor's /api/player-level/status?job=... poll
// reached the server without its job and was answered 404.) No browser, no network, no keys.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('hosted/browser-agent.js','utf8');
const chefjeffProviders=JSON.parse(fs.readFileSync('model-providers.json','utf8'));
const calls=[],data=new Map(),timers=[];
const elements={};
for(const id of ['contribution-save','contribution-choice','contribution-change','contribution-preview','contribution-data',
  'contribution-download','contribution-delete','contribution-status','contribution-receipt','ask-auto','ask-later'])elements[id]={disabled:true,checked:false};
elements['contribution-ask']={open:false,showModal(){this.open=true;},close(){this.open=false;}};
const document={getElementById:id=>elements[id]||null,querySelector:()=>null,activeElement:null};
const native=async(url,init={})=>{
  calls.push({url:String(url),init});
  const u=new URL(url,'https://kitchen.example');
  if(u.pathname==='/api/session')return new Response(JSON.stringify({session:'test-session'}),{status:201});
  if(u.pathname==='/api/state')return new Response(JSON.stringify({game_id:'round',phase:'ready',limits:{},connection:{configured:false}}));
  if(u.pathname==='/api/model/free/catalog')return new Response(JSON.stringify({enabled:false,models:[]}));
  if(u.pathname==='/api/player-level/status'){
    const job=u.searchParams.get('job');
    return new Response(JSON.stringify(job?{status:'running',job}:{error:'没有这项校准。'}),{status:job?200:404});
  }
  return new Response('{"ok":true}');
};
const w={fetch:native,chefjeffProviders,addEventListener:()=>{},dispatchEvent:()=>{}};
vm.runInNewContext(source,{window:w,location:{href:'https://kitchen.example/',origin:'https://kitchen.example'},
  Response,URL,Headers,AbortController,performance:{now:()=>0},crypto:require('node:crypto').webcrypto,
  CustomEvent:class {constructor(type,options){this.type=type;this.detail=options.detail;}},
  setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout:()=>{},
  document,localStorage:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}});
(async()=>{
  const r=await w.fetch('/api/player-level/status?job='+encodeURIComponent('job 7/a'));
  assert.equal(r.status,200,'the job reaches the server');
  assert.equal((await r.json()).job,'job 7/a');
  const sent=calls.filter(c=>new URL(c.url,'https://kitchen.example').pathname==='/api/player-level/status');
  assert.equal(sent.length,1);
  assert.equal(new URL(sent[0].url,'https://kitchen.example').search,'?job=job%207%2Fa');
  assert.equal(new Headers(sent[0].init.headers).get('X-ChefJeff-Session'),'test-session','still the hosted session');
  const plain=await w.fetch('/api/state');
  assert.equal(plain.status,200);
  assert(calls.some(c=>c.url==='/api/state'),'a request without a query is forwarded as before');
  console.log('hosted query tests passed');
})().catch(e=>{console.error(e);process.exit(1);});
