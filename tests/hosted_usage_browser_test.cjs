// Test the real hosted usage reporter without a browser, credentials or paid API.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('hosted/browser-agent.js', 'utf8');
const VISIT = 'chefjeff.usage-visited.v1', PLAY = 'chefjeff.usage-played.v1';

function harness(data = new Map(), {blocked = false, fail = false, locks = null} = {}) {
  const calls = [], timers = [];
  let now = 0, phase = 'ready', reportFailure = fail;
  const native = async (url, init = {}) => {
    calls.push({url, init});
    const path = new URL(url, 'https://kitchen.example').pathname;
    if (path === '/api/session') return new Response('{"session":"ephemeral-page-token"}', {status:201});
    if (path === '/api/state') return new Response(JSON.stringify({game_id:'ephemeral-round',phase,limits:{},hosted:{}}));
    if (path === '/api/usage') return new Response('{}', {status:reportFailure ? 503 : 200});
    return new Response('{"ok":true}');
  };
  const w = {fetch:native,addEventListener(){},dispatchEvent(){},navigator:{locks}};
  const storage = {
    getItem(key) {if (blocked) throw Error('storage unavailable'); return data.get(key) ?? null;},
    setItem(key, value) {if (blocked) throw Error('storage unavailable'); data.set(key, value);},
    removeItem(key) {if (blocked) throw Error('storage unavailable'); data.delete(key);},
  };
  vm.runInNewContext(source, {window:w,localStorage:storage,
    location:{href:'https://kitchen.example/',origin:'https://kitchen.example'},
    document:{getElementById(){return null;}},Response,Headers,URL,AbortController,
    crypto:require('node:crypto').webcrypto,CustomEvent:class{},performance:{now:()=>now},
    setTimeout(fn) {timers.push(fn); return timers.length;},clearTimeout(){}});
  return {w,data,calls,timers,advance(ms){now+=ms;},running(){phase='running';},recover(){reportFailure=false;},
    reports:()=>calls.filter(call=>call.url==='/api/usage'),
    async flush() {
      for (let i=0;i<10;i++) await Promise.resolve();
      const index = timers.findIndex(fn=>fn.name==='reportUsage');
      if (index>=0) await timers.splice(index,1)[0]();
    }};
}

(async () => {
  const shared = new Map();
  let h = harness(shared);
  await h.flush();
  assert.equal(h.reports().length,1);
  assert.deepEqual(JSON.parse(h.reports()[0].init.body),{first_visit:true,first_play:false});
  assert.equal(h.reports()[0].init.headers.get('X-ChefJeff-Session'),'ephemeral-page-token');
  assert.equal(shared.get(VISIT),'1');
  assert.equal(shared.has(PLAY),false);
  // Reload/new tab uses the two booleans, not a unique browser ID.
  h = harness(shared); await h.flush(); assert.equal(h.reports().length,0);
  h.running(); await h.w.fetch('/api/state'); await h.flush();
  assert.deepEqual(JSON.parse(h.reports()[0].init.body),{first_visit:false,first_play:true});
  for (let i=0;i<3;i++) {await h.w.fetch('/api/state'); await h.flush();}
  assert.equal(h.reports().length,1); assert.equal(shared.get(PLAY),'1');
  assert.deepEqual([...shared.keys()].sort(),[PLAY,VISIT].sort());
  assert(!JSON.stringify([...shared.values()]).includes('ephemeral-page-token'));
  assert(!JSON.stringify(h.reports()).includes('ephemeral-round'));

  // A failed report leaves no counted flag; retries are throttled and don't block state requests.
  h = harness(new Map(), {fail:true}); await h.flush();
  assert.equal(h.data.size,0); assert.equal(h.reports().length,1);
  assert.equal((await h.w.fetch('/api/state')).status,200); await h.flush();
  assert.equal(h.reports().length,1);
  h.recover(); h.advance(15001); await h.w.fetch('/api/state'); await h.flush();
  assert.equal(h.reports().length,2); assert.equal(h.data.get(VISIT),'1');

  // Storage-disabled browsers are omitted from estimates; gameplay still works.
  h = harness(new Map(), {blocked:true}); await h.flush();
  h.running(); assert.equal((await h.w.fetch('/api/state')).status,200); await h.flush();
  assert.equal(h.reports().length,0); assert.equal(h.data.size,0);

  // Web Locks prevents two cooperating tabs from counting the same profile twice.
  let serial=Promise.resolve();
  const locks={request(name, fn){assert.equal(name,'chefjeff-usage'); const next=serial.then(fn); serial=next.catch(()=>{}); return next;}};
  const tabsStorage=new Map(), one=harness(tabsStorage,{locks}), two=harness(tabsStorage,{locks});
  await Promise.all([one.flush(),two.flush()]);
  assert.equal(one.reports().length+two.reports().length,1);

  // Clearing site data makes the next visit count again, a documented estimate limitation.
  tabsStorage.clear(); h=harness(tabsStorage); await h.flush(); assert.equal(h.reports().length,1);
  console.log('Hosted usage estimates: two booleans only, reload deduplication, first play, bounded retries, unavailable storage and cross-tab locking passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
