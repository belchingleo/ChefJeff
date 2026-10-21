// Exercise the shipped browser agent with only same-origin mock records; no paid model calls.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('hosted/browser-agent.js','utf8');
const chefjeffProviders=JSON.parse(fs.readFileSync('model-providers.json','utf8'));
const consent=/CONSENT_VERSION = '([^']+)'/.exec(fs.readFileSync('hosted_records.py','utf8'))[1];
const choiceKey='chefjeff.contribution-choice.v1',receiptsKey='chefjeff.contribution-receipts.v1',oldKey='chefjeff.contribution-auto.v1';
const fakeKey='unit-test-key-not-a-real-credential';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function harness(options={}){
 const data=new Map(options.data||[]),calls=[],elements=new Map(),listeners={},timers=[];
 data.set('chefjeff.browser-key.v1',JSON.stringify({provider:'deepseek',model:'fixture',api_key:fakeKey,remember:true}));
 const el=id=>{if(!elements.has(id))elements.set(id,{checked:false,disabled:false,value:'',textContent:'',open:false,
  showModal(){this.open=true;},close(){this.open=false;}});return elements.get(id);};
 let current={game_id:'round-a',phase:'ready',hosted:{contribution_enabled:true},limits:{}};
 let release;const gate=new Promise(resolve=>{release=resolve;});
 const native=async(url,init={})=>{
  calls.push({url,init});assert(!String(url).startsWith('https://api.'),'Contributions must never request a model.');
  const body=init.body?JSON.parse(init.body):{};
  if(url==='/api/session')return new Response('{"session":"fixture-session"}',{status:201});
  if(url==='/api/state')return new Response(JSON.stringify(current));
  if(url==='/api/contribution/save'){
   if(options.delay)await new Promise((resolve,reject)=>{gate.then(resolve);init.signal.addEventListener('abort',()=>reject(new DOMException('cancelled','AbortError')),{once:true});});
   if(options.fail)return new Response('{"error":"fixture save failed"}',{status:503});
   if(body.game_id===current.game_id)current.hosted={...current.hosted,contributed:true};
   return new Response(JSON.stringify({receipt:{id:body.game_id,deletion_token:'fixture-token',expires_at:'2035-01-01T00:00:00Z'}}));
  }
  if(url==='/api/contribution/delete'){
   assert.deepEqual(Object.keys(body).sort(),['deletion_token','id']);
   return new Response('{}',{status:options.failDelete===body.id?404:200});
  }
  return new Response('{"ok":true}');
 };
 const w={fetch:native,chefjeffProviders,addEventListener:(name,fn)=>{listeners[name]=fn;},dispatchEvent:e=>listeners[e.type]?.(e)};
 vm.runInNewContext(source,{window:w,location:{origin:'https://kitchen.example',href:'https://kitchen.example/'},
  document:{getElementById:el,querySelector:selector=>selector==='dialog[open]'?[...elements.values()].find(e=>e.open)||null:null},
  localStorage:{getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)},
  URL,Response,Headers,AbortController,performance,crypto:require('node:crypto').webcrypto,
  Event:class{constructor(type){this.type=type;}},CustomEvent:class{constructor(type,o){this.type=type;this.detail=o.detail;}},
  setTimeout:(fn,ms)=>{const row={fn,ms,active:true};timers.push(row);return row;},clearTimeout:row=>{if(row)row.active=false;}});
 listeners.DOMContentLoaded();
 // The page reads state through the agent's fetch, so it carries this browser's contribution flags.
 const publish=async patch=>{if(patch.game_id)current.hosted={...current.hosted,contributed:false};current={...current,...patch};const detail=await (await w.fetch('/api/state')).json();listeners['kitchen-state']({detail});return detail;};
 const answer=auto=>{if(!el('contribution-ask').open)el('contribution-change').onclick();el(auto?'ask-auto':'ask-later').onclick();};
 const saves=()=>calls.filter(c=>c.url==='/api/contribution/save');
 return {w,data,calls,el,publish,answer,saves,release,timers,listeners};
}
const guard=setTimeout(()=>{console.error('Automatic contribution test did not complete.');process.exit(1);},5000);
(async()=>{
 assert.match(source,new RegExp(`const CONSENT = '${consent}'`),'The page and server must use one consent version.');
 // Asked once before the first round, with no preselected answer; an older opt-in is not carried over.
 let h=harness({data:[[oldKey,JSON.stringify({consent_version:'pilot-session-2026-09-v1'})]]});
 assert(!h.data.has(oldKey));assert.equal(h.el('contribution-choice').textContent,'当前选择：尚未选择。');
 await h.publish({});assert.equal(h.el('contribution-ask').open,true);assert.equal(h.saves().length,0);
 h.answer(true);assert.equal(h.el('contribution-ask').open,false);
 assert.equal(JSON.parse(h.data.get(choiceKey)).answer,'auto');assert.equal(JSON.parse(h.data.get(choiceKey)).consent_version,consent);
 let state=await h.publish({phase:'ended'});await flush();
 assert.equal(state.hosted.contribution_offer,false,'Automatic contributors are not asked per round.');
 assert.equal(h.saves().length,1);
 const payload=JSON.parse(h.saves()[0].init.body);
 assert.equal(payload.game_id,'round-a');assert.equal(payload.consent,true);assert.equal(payload.consent_mode,'standing');assert.equal(payload.consent_version,consent);
 await h.publish({phase:'ended'});await flush();assert.equal(h.saves().length,1);
 // Changing to 暂不 stops automatic uploads; the result card then offers this round alone.
 h.answer(false);assert.equal(JSON.parse(h.data.get(choiceKey)).answer,'later');
 state=await h.publish({game_id:'round-b',phase:'ended'});await flush();
 assert.equal(h.saves().length,1);assert.equal(state.hosted.contribution_offer,true);
 h.w.dispatchEvent({type:'kitchen-contribute'});await flush();
 assert.equal(h.saves().length,2);assert.equal(JSON.parse(h.saves()[1].init.body).consent_mode,'round');
 assert(h.el('contribution-badge').textContent.includes('本局已贡献'));
 state=await h.publish({});assert.equal(state.hosted.contributed,true);
 h.w.dispatchEvent({type:'kitchen-contribute'});await flush();assert.equal(h.saves().length,2,'A contributed round is not sent again.');
 await h.publish({game_id:'round-c',phase:'running'});
 h.w.dispatchEvent({type:'kitchen-contribute'});await flush();assert.equal(h.saves().length,2,'Only an ended round can be contributed.');
 // Agreeing on a finished round never uploads it retroactively.
 await h.publish({phase:'ended'});h.answer(true);await h.publish({phase:'ended'});await flush();
 assert.equal(h.saves().length,2,'Enabling on a finished round must not upload it retroactively.');
 await h.publish({game_id:'round-d',phase:'running'});await h.publish({phase:'ended'});await flush();
 assert.equal(JSON.parse(h.data.get(receiptsKey)).length,3);
 const restored=harness({data:h.data});await restored.publish({});
 assert.equal(restored.el('contribution-ask').open,false,'A remembered answer is not asked again.');
 assert(restored.el('contribution-choice').textContent.includes('自动贡献'));
 assert(restored.el('contribution-receipt').value.includes('round-d'));
 await restored.el('contribution-delete').onclick();assert.equal(JSON.parse(restored.data.get(receiptsKey)).length,0);
 // Dismissed without an answer (a browser may close it on Esc): asked again at the next result, not on every poll.
 const dismissed=harness();await dismissed.publish({});dismissed.el('contribution-ask').close();
 await dismissed.publish({});assert.equal(dismissed.el('contribution-ask').open,false);
 await dismissed.publish({phase:'ended'});assert.equal(dismissed.el('contribution-ask').open,true);
 const renewed=harness({data:[[choiceKey,JSON.stringify({consent_version:'older-terms',answer:'auto'})]]});
 await renewed.publish({phase:'ended'});await flush();
 assert.equal(renewed.el('contribution-ask').open,true,'New terms ask again.');assert.equal(renewed.saves().length,0);
 const partial=harness({data:[[receiptsKey,JSON.stringify([{id:'round-c',deletion_token:'t',expires_at:'2035-01-01T00:00:00Z'},{id:'round-d',deletion_token:'t',expires_at:'2035-01-01T00:00:00Z'}])]],failDelete:'round-c'});
 await partial.el('contribution-delete').onclick();
 assert.equal(JSON.parse(partial.data.get(receiptsKey)).length,1);assert(partial.el('contribution-receipt').value.includes('round-c'));
 h=harness({delay:true});await h.publish({});h.answer(true);await h.publish({phase:'ended'});await flush();
 const next=h.w.chefjeffHostedRequest('/api/next',{game_id:'round-a',request_id:'next',level:'level-2'});
 await flush();assert(!h.calls.some(c=>c.url==='/api/next'),'Next round must wait while the old record is being saved.');
 h.release();await next;assert(h.calls.some(c=>c.url==='/api/next'));
 assert(h.calls.findIndex(c=>c.url==='/api/contribution/save')<h.calls.findIndex(c=>c.url==='/api/next'));
 h=harness({fail:true});await h.publish({});h.answer(true);await h.publish({phase:'ended'});await flush();
 await h.w.chefjeffHostedRequest('/api/next',{game_id:'round-a',level:'level-2'});assert(h.el('contribution-status').textContent.includes('失败'));
 h=harness({delay:true});await h.publish({});h.answer(true);await h.publish({phase:'ended'});await flush();
 const timedNext=h.w.chefjeffHostedRequest('/api/next',{game_id:'round-a',level:'level-2'});await flush();
 assert(h.timers.some(t=>t.ms===15000));h.timers.find(t=>t.ms===10000&&t.active).fn();await timedNext;
 assert(h.el('contribution-status').textContent.includes('超时'));
 for(const call of h.calls)assert(!JSON.stringify(call).includes(fakeKey));
 console.log('Contribution consent: one up-front question without a default, automatic and per-round uploads, withdrawal, no backfill, re-ask on new terms, receipts and next-round ordering/timeout passed.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>clearTimeout(guard));
