// Pure JavaScript transport unit tests: no browser automation and no paid API.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('hosted/browser-agent.js','utf8');
const key='unit-test-key-not-a-real-credential';
function harness(saved=null, fail=false){
 const calls=[],data=new Map(saved?[['chefjeff.browser-key.v1',JSON.stringify(saved)]]:[]),timers=[];
 const native=async(url,init={})=>{
  calls.push({url:String(url),init});
  const u=new URL(url,'https://kitchen.example');
  if(u.origin!=='https://kitchen.example'){
   if(fail)throw new TypeError('blocked');
   return new Response(JSON.stringify({choices:[{message:{content:'{"choice":"wait","sprint":false}'}}],usage:{prompt_tokens:3,completion_tokens:4}}));
  }
  if(u.pathname==='/api/session')return new Response(JSON.stringify({session:'test-session'}),{status:201});
  if(u.pathname==='/api/state')return new Response(JSON.stringify({game_id:'round',phase:'ready',limits:{},connection:{configured:false}}));
  return new Response('{"ok":true}');
 };
 const w={fetch:native,addEventListener:()=>{}};
 vm.runInNewContext(source,{window:w,location:{href:'https://kitchen.example/',origin:'https://kitchen.example'},
  Response,URL,Headers,AbortController,performance,crypto:require('node:crypto').webcrypto,
  setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout:()=>{},
  document:{getElementById:()=>null},localStorage:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}});
 return {w,calls,data};
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
 console.log('Browser transport: memory/remember/clear, reload, CORS failure, origin guard and no-key-to-server checks passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
