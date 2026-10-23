// Real browser transport + the engine-generated portable-memory contract. No paid API.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('hosted/browser-agent.js','utf8');
const providers=JSON.parse(fs.readFileSync('model-providers.json','utf8'));
const fixture=JSON.parse(fs.readFileSync('tests/fixtures/cooperation-memory-v2.json','utf8'));
const MEMORY='chefjeff.cooperation-memory.v2',KEY='memory-test-key-not-a-real-secret';
const clone=v=>JSON.parse(JSON.stringify(v));
function harness(data=new Map(),{provider='jev',key=KEY,blocked=false}={}){
 const calls=[],timers=[],listeners={};let serial=0,taskId=0;
 data.set('chefjeff.browser-key.v1',JSON.stringify({provider,api_key:key,remember:true,jev_relay:provider==='jev'}));
 let current={game_id:'0'.repeat(32),phase:'ready',limits:{},hosted:{},memory:{...clone(fixture.memory),episode:null}};
 const h={data,calls,timers,listeners,failStart:false,loseStartReply:false,
  get current(){return current;},set current(s){current=s;},
  finish(){current.phase='ended';current.memory.episode={...clone(fixture.episode),round_id:current.game_id,level_id:current.memory.level_id};},
  task(){return {id:'task-'+(++taskId),payload:{state:{kitchen:{},rules:{past_episodes:'historical evidence only'}},
    questions:{next_action:{type:'choice',criteria:{wait:'Wait'}},sprint:{type:'choice',criteria:{yes:'Run',no:'Walk'}}}}};}
 };
 const native=async(url,init={})=>{
  calls.push({url:String(url),init});const u=new URL(url,'https://kitchen.example');
  const body=init.body?JSON.parse(init.body):{};
  if(u.origin!=='https://kitchen.example')return new Response(JSON.stringify({choices:[{message:{content:'{"choice":"wait","sprint":false}'}}],
    answers:{next_action:{type:'choice',choice:'wait'},sprint:{type:'choice',choice:'no'}},usage:{prompt_tokens:2,completion_tokens:1,input_tokens:2,output_tokens:1}}));
  if(u.pathname==='/api/session')return new Response('{"session":"temporary-page-token"}',{status:201});
  if(u.pathname==='/api/state')return new Response(JSON.stringify(current));
  if(['/api/start','/api/restart','/api/next'].includes(u.pathname)){
   if(h.failStart)return new Response('{"error":"full"}',{status:503});
   if(u.pathname!=='/api/start')current.game_id=(++serial).toString(16).padStart(32,'0');
   if(u.pathname==='/api/next')current.memory.level_id=typeof body.level==='number'?'level-'+body.level:body.level;
   current.phase='running';current.memory.episode=null;
   if(h.loseStartReply)throw new TypeError('lost acknowledgement');
  }
  if(u.pathname==='/api/model/request')return new Response(JSON.stringify({request:h.task()}));
  if(u.pathname==='/api/model/jev')return new Response('{"answer":{"choice":"wait","sprint":false,"usage":{"input_tokens":2,"output_tokens":1}}}');
  return new Response('{"ok":true}');
 };
 const w={fetch:native,chefjeffProviders:providers,addEventListener:(n,f)=>listeners[n]=f,dispatchEvent(){}};
 vm.runInNewContext(source,{window:w,location:{href:'https://kitchen.example/',origin:'https://kitchen.example'},Response,Headers,URL,
  AbortController,performance:{now:()=>0},crypto:require('node:crypto').webcrypto,CustomEvent:class{},
  document:{getElementById:()=>null,querySelector:()=>null,hidden:false},
  setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},
  localStorage:{getItem:k=>{if(blocked&&k===MEMORY)throw Error();return data.get(k)||null;},
   setItem:(k,v)=>{if(blocked&&k===MEMORY)throw Error();data.set(k,v);},removeItem:k=>data.delete(k)}});
 h.w=w;h.read=async()=>JSON.parse(await (await w.fetch('/api/state')).text());
 h.command=async(path,body={})=>w.fetch(path,{method:'POST',body:JSON.stringify({game_id:current.game_id,request_id:'command',...body})});
 h.start=async(path='/api/start',body={})=>{await h.read();const r=await h.command(path,body);await h.read();return r;};
 h.poll=async()=>timers.find(fn=>fn.name==='poll')();
 return h;
}
async function savedRound(provider='jev'){
 const h=harness(new Map(),{provider});await h.start();h.finish();await h.read();return h;
}
function saved(h){return JSON.parse(h.data.get(MEMORY));}
(async()=>{
 let h=harness();let s=await h.read();assert.equal(s.memory.enabled,true);assert.equal(s.memory.editable,true);
 assert.equal(s.memory.saved_rounds,0);assert.equal(h.calls.filter(c=>c.url==='/api/memory').length,0);
 await h.start();s=await h.read();assert.equal(s.memory.editable,false);
 assert.equal((await h.command('/api/memory',{enabled:false})).status,409);
 h.finish();s=await h.read();assert.equal(s.memory.saved_rounds,1);
 assert.equal(saved(h).scopes[0].episodes[0].work.human.fetch,1);
 assert(!h.data.get(MEMORY).includes(KEY));
 await h.command('/api/memory',{clear:true});assert.equal(saved(h).scopes.length,0);
 await h.read();assert.equal(saved(h).scopes.length,0,'Clearing must not resave the ended round on the next poll');

 h=await savedRound();const data=h.data;
 const restored=harness(data,{key:'rotated-key-not-a-real-secret'});s=await restored.read();assert.equal(s.memory.saved_rounds,1);
 await restored.start();await restored.poll();
 let relay=restored.calls.find(c=>c.url==='/api/model/jev');let sent=JSON.parse(relay.init.body);
 assert.equal(sent.memory.episodes.length,1);assert.equal(sent.memory.episodes[0].work.human.fetch,1);
 const condition=JSON.parse(restored.calls.find(c=>c.url==='/api/model/result').init.body).memory_condition;
 assert.deepEqual(condition,{enabled:true,version:2,used_rounds:1,omitted_rounds:0});
 assert.equal(sent.api_key,'rotated-key-not-a-real-secret');
 for(const c of restored.calls.filter(c=>c!==relay))assert(!JSON.stringify(c).includes('rotated-key-not-a-real-secret'));
 assert.equal(restored.calls.filter(c=>c.url.startsWith('https://api.')).length,0,'Jev must use only its consented relay');
 const modelOther=harness(data,{provider:'deepseek'});assert.equal((await modelOther.read()).memory.saved_rounds,0);
 const levelOther=harness(data);levelOther.current.memory.level_id='level-2';assert.equal((await levelOther.read()).memory.saved_rounds,0);
 const contractOther=harness(data);contractOther.current.memory.namespace='new-rules';assert.equal((await contractOther.read()).memory.saved_rounds,0);
 const stranger=harness();assert.equal((await stranger.read()).memory.saved_rounds,0);

 h=await savedRound('deepseek');await h.start('/api/restart');
 // A second tab updates storage after start. This round must keep its opening snapshot.
 const changed=saved(h);changed.scopes[0].episodes.push({...clone(fixture.episode),round_id:'b'.repeat(32)});h.data.set(MEMORY,JSON.stringify(changed));
 await h.poll();let external=h.calls.find(c=>c.url==='https://api.deepseek.com/chat/completions');
 let payload=JSON.parse(JSON.parse(external.init.body).messages[1].content);
 assert.equal(payload.state.past_episodes.episodes.length,1);
 assert.equal(payload.state.rules.past_episodes,'historical evidence only');
 assert.equal(h.calls.filter(c=>c.url==='/api/model/jev').length,0);

 h=await savedRound();await h.command('/api/memory',{enabled:false});await h.start('/api/restart');await h.poll();
 sent=JSON.parse(h.calls.find(c=>c.url==='/api/model/jev').init.body);
 assert.equal(sent.memory.enabled,false);assert.equal(sent.memory.episodes.length,0);
 h.finish();await h.read();assert.equal(saved(h).scopes[0].episodes.length,1,'Disabled rounds must not be added');
 await h.command('/api/memory',{clear:true});assert.equal(saved(h).enabled,false);assert.equal(saved(h).scopes.length,0);

 h=await savedRound();await h.start('/api/next',{level:2});await h.poll();
 sent=JSON.parse(h.calls.find(c=>c.url==='/api/model/jev').init.body);
 assert.equal(sent.memory.episodes.length,0,'Next level must not inherit the previous level');

 h=harness();await h.start();await h.command('/api/end'); // server fixture deliberately has no episode
 h.current.phase='ended';h.current.memory.episode=null;await h.read();assert(!h.data.has(MEMORY),'Aborted rounds are not saved');
 h=harness();for(let i=0;i<5;i++){await h.start(i?'/api/restart':'/api/start');h.finish();await h.read();}
 assert.equal(saved(h).scopes[0].episodes.length,3);

 h=await savedRound();let content=saved(h);content.scopes[0].episodes[0].api_key=KEY;h.data.set(MEMORY,JSON.stringify(content));
 const corrupt=harness(h.data);s=await corrupt.read();assert.equal(s.memory.enabled,false);assert(s.memory.error);
 await corrupt.command('/api/memory',{clear:true,enabled:true});assert.equal(saved(corrupt).scopes.length,0);

 h=harness(new Map(),{blocked:true});await h.start();h.finish();s=await h.read();
 assert.equal(s.memory.saved_rounds,1);assert(s.memory.error);assert(!h.data.has(MEMORY));
 await h.start('/api/restart');await h.poll();sent=JSON.parse(h.calls.find(c=>c.url==='/api/model/jev').init.body);
 assert.equal(sent.memory.episodes.length,1,'Unavailable storage keeps useful memory within this page');

 h=await savedRound();content=saved(h);
 const large=clone(fixture.episode);large.events=Array.from({length:18},(_,i)=>({t:i,kind:'action_done',actor:i%2?'human':'jeff',action:'go '+'counter'.repeat(10)}));
 content.scopes[0].episodes=Array.from({length:3},(_,i)=>({...clone(large),round_id:String(i+1).repeat(32)}));
 h.data.set(MEMORY,JSON.stringify(content));
 const budget=harness(h.data);await budget.start();await budget.poll();sent=JSON.parse(budget.calls.find(c=>c.url==='/api/model/jev').init.body);
 assert(JSON.stringify(sent.memory).length<=8000);assert(sent.memory.omitted_rounds>0);
 assert(sent.memory.episodes.every(e=>e.events.length===18),'Only whole old episodes may be omitted');

 h=await savedRound();h.loseStartReply=true;await h.start('/api/restart');await h.poll();
 sent=JSON.parse(h.calls.find(c=>c.url==='/api/model/jev').init.body);assert.equal(sent.memory.episodes.length,1,'Lost start reply must not lose the frozen context');
 console.log('Hosted cooperation memory: browser persistence, direct/relay delivery, frozen rounds, isolation, controls, bounds and recovery passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
