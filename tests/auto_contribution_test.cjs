// Exercise the shipped browser agent with only same-origin mock records; no paid model calls.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('hosted/browser-agent.js','utf8');
const consent='pilot-session-2026-09-v1',autoKey='chefjeff.contribution-auto.v1',receiptsKey='chefjeff.contribution-receipts.v1';
const fakeKey='unit-test-key-not-a-real-credential';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function harness(options={}){
 const data=new Map(options.data||[]),calls=[],elements=new Map(),listeners={},timers=[];
 data.set('chefjeff.browser-key.v1',JSON.stringify({provider:'deepseek',model:'fixture',api_key:fakeKey,remember:true}));
 const el=id=>{if(!elements.has(id))elements.set(id,{checked:false,disabled:false,value:'',textContent:''});return elements.get(id);};
 let current={game_id:'round-a',phase:'ready',hosted:{contribution_enabled:true},limits:{}};
 let release;const gate=new Promise(resolve=>{release=resolve;});
 const native=async(url,init={})=>{
  calls.push({url,init});assert(!String(url).startsWith('https://api.'),'Automatic contributions must never request a model.');
  const body=init.body?JSON.parse(init.body):{};
  if(url==='/api/session')return new Response('{"session":"fixture-session"}',{status:201});
  if(url==='/api/state')return new Response(JSON.stringify(current));
  if(url==='/api/contribution/save'){
   if(options.delay)await new Promise((resolve,reject)=>{gate.then(resolve);init.signal.addEventListener('abort',()=>reject(new DOMException('cancelled','AbortError')),{once:true});});
   if(options.fail)return new Response('{"error":"fixture save failed"}',{status:503});
   return new Response(JSON.stringify({receipt:{id:body.game_id,deletion_token:'fixture-token',expires_at:'2035-01-01T00:00:00Z'}}));
  }
  if(url==='/api/contribution/delete'){
   assert.deepEqual(Object.keys(body).sort(),['deletion_token','id']);
   return new Response('{}',{status:options.failDelete===body.id?404:200});
  }
  return new Response('{"ok":true}');
 };
 const w={fetch:native,addEventListener:(name,fn)=>{listeners[name]=fn;},dispatchEvent:e=>listeners[e.type]?.(e)};
 vm.runInNewContext(source,{window:w,document:{getElementById:el},location:{origin:'https://kitchen.example',href:'https://kitchen.example/'},
  localStorage:{getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)},
  URL,Response,Headers,AbortController,performance,crypto:require('node:crypto').webcrypto,
  Event:class{constructor(type){this.type=type;}},CustomEvent:class{constructor(type,o){this.type=type;this.detail=o.detail;}},
  setTimeout:(fn,ms)=>{const row={fn,ms,active:true};timers.push(row);return row;},clearTimeout:row=>{if(row)row.active=false;}});
 listeners.DOMContentLoaded();
 const publish=async patch=>{current={...current,...patch};const detail=await (await w.fetch('/api/state')).json();listeners['kitchen-state']({detail});};
 const enable=()=>{el('contribution-consent').checked=true;el('contribution-consent').onchange();el('contribution-auto').checked=true;el('contribution-auto').onchange();};
 return {w,data,calls,el,publish,enable,release,timers};
}
const guard=setTimeout(()=>{console.error('Automatic contribution test did not complete.');process.exit(1);},5000);
(async()=>{
 let h=harness();await h.publish({});
 h.el('contribution-auto').checked=true;h.el('contribution-auto').onchange();
 assert.equal(h.el('contribution-auto').checked,false);assert(!h.data.has(autoKey));
 h.enable();await h.publish({phase:'ended'});await flush();
 assert.equal(h.calls.filter(c=>c.url==='/api/contribution/save').length,1);
 const save=h.calls.find(c=>c.url==='/api/contribution/save');const payload=JSON.parse(save.init.body);
 assert.equal(payload.game_id,'round-a');assert.equal(payload.consent,true);assert.equal(payload.consent_mode,'standing');assert.equal(payload.consent_version,consent);
 await h.publish({phase:'ended'});await flush();assert.equal(h.calls.filter(c=>c.url==='/api/contribution/save').length,1);
 h.el('contribution-consent').checked=false;h.el('contribution-consent').onchange();
 assert(!h.data.has(autoKey));assert.equal(h.el('contribution-auto').checked,false);
 await h.publish({game_id:'round-b',phase:'ended'});await flush();assert.equal(h.calls.filter(c=>c.url==='/api/contribution/save').length,1);
 h.enable();await h.publish({phase:'ended'});await flush();assert.equal(h.calls.filter(c=>c.url==='/api/contribution/save').length,1,'Enabling on a finished round must not upload it retroactively.');
 await h.publish({game_id:'round-c',phase:'running'});await h.publish({phase:'ended'});await flush();
 assert.equal(JSON.parse(h.data.get(receiptsKey)).length,2);
 const restored=harness({data:h.data});assert(restored.el('contribution-auto').checked);assert(restored.el('contribution-consent').checked);
 assert(restored.el('contribution-receipt').value.includes('round-c'));
 await restored.el('contribution-delete').onclick();assert.equal(JSON.parse(restored.data.get(receiptsKey)).length,0);
 const partial=harness({data:h.data,failDelete:'round-c'});await partial.el('contribution-delete').onclick();
 assert.equal(JSON.parse(partial.data.get(receiptsKey)).length,1);assert(partial.el('contribution-receipt').value.includes('round-c'));
 h=harness({delay:true});await h.publish({});h.enable();await h.publish({phase:'ended'});await flush();
 const next=h.w.chefjeffHostedRequest('/api/next',{game_id:'round-a',request_id:'next',level:'level-2'});
 await flush();assert(!h.calls.some(c=>c.url==='/api/next'),'Next round must wait while the old record is being saved.');
 h.release();await next;assert(h.calls.some(c=>c.url==='/api/next'));
 assert(h.calls.findIndex(c=>c.url==='/api/contribution/save')<h.calls.findIndex(c=>c.url==='/api/next'));
 h=harness({fail:true});await h.publish({});h.enable();await h.publish({phase:'ended'});await flush();
 await h.w.chefjeffHostedRequest('/api/next',{game_id:'round-a',level:'level-2'});assert(h.el('contribution-status').textContent.includes('失败'));
 h=harness({delay:true});await h.publish({});h.enable();await h.publish({phase:'ended'});await flush();
 const timedNext=h.w.chefjeffHostedRequest('/api/next',{game_id:'round-a',level:'level-2'});await flush();
 assert(h.timers.some(t=>t.ms===15000));h.timers.find(t=>t.ms===10000&&t.active).fn();await timedNext;
 assert(h.el('contribution-status').textContent.includes('超时'));
 for(const call of h.calls)assert(!JSON.stringify(call).includes(fakeKey));
 console.log('Automatic contribution: opt-in, withdrawal, no backfill, deduplication, receipt restore/delete and next-round upload ordering/timeout passed.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>clearTimeout(guard));
