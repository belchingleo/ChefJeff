/* Hosted-only transport. The secret and native fetch stay in this closure. */
(() => {
  'use strict';
  const nativeFetch = window.fetch.bind(window);
  const storageName = 'chefjeff.browser-key.v1';
  const relayConsent = 'jev-relay-2026-10-v1';
  window.chefjeffJevRelayAvailable = true;
  // The shared service list (model-providers.js, loaded just before this script); 'none' is local-only.
  const providers = () => Object.fromEntries((window.chefjeffProviders?.providers || [])
    .filter(p => !p.disabled && p.hosted !== 'none').map(p => [p.id, p]));
  let setting = null, state = null, checks = 0, testing = false;
  const handled = new Set();
  const response = (status, data) => new Response(JSON.stringify(data), {
    status, headers: {'Content-Type': 'application/json'},
  });
  const connection = () => ({configured: !!setting, provider: setting?.provider || 'deepseek',
    base_url: setting?.base_url || '', model: setting?.model || '', remembered: !!setting?.remember,
    jev_relay: setting?.jev_relay === true,
    editable: !testing && (!state || ['ready', 'ended'].includes(state.phase))});
  // Browser-owned, bounded history. No model URL, name, key or visitor identifier
  // is sent to the game server as a scope. Active context is frozen at round start.
  const MEMORY_KEY = 'chefjeff.cooperation-memory.v2';
  const memoryKinds = new Set(['action_done','thrown','caught','landed','washed','served','bad_service','burn','fire','expired','arrival_conflict']);
  const workKinds = new Set(['fetch','chop','heat','assemble','serve','wash','collect_plates','pass','extinguish','discard']);
  const preferences = ['prep','cook','plate','deliver','wash',null];
  const memoryAction = /^(?:fetch|wash|serve|drop|discard|stop|continue|wait|(?:fetch|go|put|take|plate|chop|pickup|throw|clear|extinguish|assemble|merge|swap|load) [A-Za-z0-9_ .,-]{1,70})$/;
  const clone = value => JSON.parse(JSON.stringify(value));
  const fields = (value, names) => value && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === names.length && names.every(k=>Object.hasOwn(value,k));
  const count = n => Number.isInteger(n) && n >= 0 && n <= 1000000;
  const amount = (n, positive=true) => typeof n === 'number' && Number.isFinite(n) && Math.abs(n) <= 1e9 && (!positive || n >= 0);
  function validEpisode(r, level) {
    if (!fields(r,['version','round_id','duration','level_id','outcome','work','communication','events','eligible_event_count','sampled']) ||
        r.version!==2 || !/^[0-9a-f]{32}$/.test(r.round_id) || r.level_id!==level || !amount(r.duration) ||
        typeof r.sampled!=='boolean' || !count(r.eligible_event_count)) return false;
    const o=r.outcome,c=r.communication,w=r.work;
    if (!fields(o,['served','money','target_money','reached_target','expired','burns','fires']) ||
        !['served','expired','burns','fires'].every(k=>count(o[k])) || !amount(o.money,false) ||
        !amount(o.target_money) || typeof o.reached_target!=='boolean' ||
        !fields(c,['last_preference','corrections']) || !preferences.includes(c.last_preference) || !count(c.corrections) ||
        !fields(w,['human','jeff'])) return false;
    for(const actor of ['human','jeff']) {
      if (!w[actor] || typeof w[actor]!=='object' || Array.isArray(w[actor]) ||
          !Object.entries(w[actor]).every(([k,v])=>workKinds.has(k)&&count(v))) return false;
    }
    return Array.isArray(r.events) && r.events.length<=18 && r.events.every(e=>
      e && typeof e==='object' && !Array.isArray(e) && Object.keys(e).every(k=>['t','kind','actor','action'].includes(k)) &&
      amount(e.t) && memoryKinds.has(e.kind) && (!Object.hasOwn(e,'actor') || ['human','jeff'].includes(e.actor)) &&
      (!Object.hasOwn(e,'action') || (typeof e.action==='string' && memoryAction.test(e.action))));
  }
  let browserMemory={version:2,enabled:true,scopes:[]},memoryError='',activeMemory=null;
  const processedMemoryRounds = new Set();
  function readMemory() {
    let raw;
    try {raw=localStorage.getItem(MEMORY_KEY);}
    catch (_) {memoryError='浏览器无法保存记忆，暂时仅在本页使用。';return;}
    if (!raw) return;
    try {
      if(raw.length>300000)throw new Error();
      const value=JSON.parse(raw);
      if(!fields(value,['version','enabled','scopes']) || value.version!==2 || typeof value.enabled!=='boolean' ||
          !Array.isArray(value.scopes) || value.scopes.length>24)throw new Error();
      for(const entry of value.scopes){
        if(!fields(entry,['key','episodes']) || typeof entry.key!=='string' || entry.key.length>1500 ||
            !Array.isArray(entry.episodes) || entry.episodes.length>3)throw new Error();
        const parts=JSON.parse(entry.key);
        if(!Array.isArray(parts)||parts.length!==5||!parts.every(p=>typeof p==='string')||
            !entry.episodes.every(e=>validEpisode(e,parts[4])))throw new Error();
      }
      browserMemory=value;
    } catch (_) {browserMemory={version:2,enabled:false,scopes:[]};memoryError='跨局记录无法读取，已关闭记忆；可清空后重新启用。';}
  }
  function writeMemory() {
    while(browserMemory.scopes.length>24 || (JSON.stringify(browserMemory).length>280000 && browserMemory.scopes.length>1))browserMemory.scopes.shift();
    try {localStorage.setItem(MEMORY_KEY,JSON.stringify(browserMemory));memoryError='';}
    catch (_) {memoryError='浏览器无法保存记忆，暂时仅在本页使用。';}
  }
  readMemory();
  window.addEventListener('storage', event => {
    if(event.key===MEMORY_KEY || event.key===null){
      if(event.newValue===null)browserMemory={version:2,enabled:true,scopes:[]};
      readMemory();
    }
  });
  const memoryKey = (s, level=s?.memory?.level_id) => setting && s?.memory?.supported ?
    JSON.stringify([setting.provider,setting.base_url,setting.model,s.memory.namespace,level]) : null;
  const episodesFor = scope => browserMemory.scopes.find(e=>e.key===scope)?.episodes || [];
  function contextFor(s, scope) {
    const context={enabled:browserMemory.enabled,version:2,episodes:browserMemory.enabled?clone(episodesFor(scope)):[],
      description:s.memory.description,omitted_rounds:0,max_characters:s.memory.max_characters};
    while(JSON.stringify(context).length>context.max_characters && context.episodes.length){context.episodes.shift();context.omitted_rounds++;}
    return context;
  }
  function openingMemory(s, body, path) {
    if(!s?.memory?.supported || !setting)return null;
    readMemory();
    const requested=path==='/api/next'?body.level:s.memory.level_id;
    const level=typeof requested==='number'?'level-'+requested:requested;
    const scope=memoryKey(s,level);
    return {scope,level,context:contextFor(s,scope),game_id:path==='/api/start'?body.game_id || s.game_id:null,
      previous:path==='/api/start'?null:s.game_id};
  }
  function observeMemory(s) {
    if(!s?.memory?.supported)return s;
    if(activeMemory && !activeMemory.game_id && s.game_id!==activeMemory.previous && s.memory.level_id===activeMemory.level &&
        ['running','paused','ended'].includes(s.phase)) activeMemory.game_id=s.game_id;
    const record=s.memory.episode;
    if(record && activeMemory?.game_id===s.game_id && !processedMemoryRounds.has(s.game_id)) {
      processedMemoryRounds.add(s.game_id);
      while(processedMemoryRounds.size>100)processedMemoryRounds.delete(processedMemoryRounds.values().next().value);
      if(activeMemory.context.enabled && validEpisode(record,activeMemory.level)) {
        readMemory();
        if(browserMemory.enabled){
          const records=episodesFor(activeMemory.scope).filter(e=>e.round_id!==record.round_id);
          records.push(clone(record));
          browserMemory.scopes=browserMemory.scopes.filter(e=>e.key!==activeMemory.scope);
          browserMemory.scopes.push({key:activeMemory.scope,episodes:records.slice(-3)});writeMemory();
        }
      }
    }
    const scope=memoryKey(s);
    s.memory={...s.memory,enabled:browserMemory.enabled,saved_rounds:episodesFor(scope).length,
      used_rounds:activeMemory?.game_id===s.game_id?activeMemory.context.episodes.length:0,
      omitted_rounds:activeMemory?.game_id===s.game_id?activeMemory.context.omitted_rounds:0,error:memoryError,
      storage:'browser-local',editable:['ready','ended'].includes(s.phase)&&!testing};
    return s;
  }
  function changeBrowserMemory(body) {
    if(!state?.memory?.supported)return response(409,{error:'需要新版厨房服务。'});
    if(!['ready','ended'].includes(state.phase)||testing)return response(409,{error:'请在开局前或结算后修改记忆设置，保证一局内条件一致。'});
    if(body.game_id!==state.game_id)return response(409,{error:'对局已变化，请重试。'});
    if((body.enabled!==undefined&&typeof body.enabled!=='boolean') || (body.clear!==undefined&&typeof body.clear!=='boolean') ||
        (body.enabled===undefined&&body.clear!==true))return response(400,{error:'记忆设置无效。'});
    readMemory();
    if(body.clear)browserMemory.scopes=[];
    if(body.enabled!==undefined)browserMemory.enabled=body.enabled;
    writeMemory();observeMemory(state);
    return response(200,{ok:true,memory:state.memory});
  }
  let session = null, sessionToken = null, retryAt = 0, transportError = '', leaving = false;
  window.chefjeffHostedStatus = () => transportError;
  function notifyConnection(error) {
    transportError = error;
    window.dispatchEvent(new CustomEvent('kitchen-connection-error', {detail:error}));
  }
  function releaseSession() {
    if (!sessionToken) return;
    const token = sessionToken; sessionToken = null;
    nativeFetch('/api/session/close', {method:'POST', keepalive:true,
      headers:{'Content-Type':'application/json', 'X-ChefJeff-Session':token}, body:'{}'}).catch(() => {});
  }
  window.addEventListener('pagehide', event => {
    // A page kept in the back/forward cache still owns its kitchen.
    if (!event.persisted) {leaving = true; releaseSession();}
  });
  function getSession() {
    if (session && (sessionToken || performance.now() < retryAt)) return session;
    // Retry a full/unavailable server at most once every 15s, below the proxy's
    // creation quota. Keep normal state polls from creating a request storm.
    retryAt = performance.now() + 15000;
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 10000);
    session = nativeFetch('/api/session', {method:'POST', signal:controller.signal,
      headers:{'Content-Type':'application/json'}, body:'{}'})
      .then(async r => {
        const d = await r.json();
        if (!r.ok) throw new Error(r.status === 503 ?
          '厨房暂时已满或请求过于频繁。请关闭其他试玩页面；空位释放后会自动重试。' : '暂时无法创建厨房，请稍后重试。');
        sessionToken = d.session;
        if (leaving) releaseSession();
        else queueUsage(false);
        notifyConnection('');
        return d.session;
      }).catch(e => {
        const message = e.name === 'AbortError' ? '创建厨房超时，将自动重试。' :
          e instanceof TypeError ? '暂时无法连接厨房，请检查网络；页面会自动重试。' : e.message;
        notifyConnection(message);
        throw new Error(message);
      }).finally(() => clearTimeout(timer));
    session.catch(() => {});
    return session;
  }
  getSession();
  async function serverFetch(path, init = {}) {
    const headers = new Headers(init.headers);
    headers.set('X-ChefJeff-Session', await getSession());
    return nativeFetch(path, {...init, headers});
  }
  // Two local booleans, no visitor ID/fingerprint. These estimate browsers, never people.
  const USAGE_VISIT = 'chefjeff.usage-visited.v1', USAGE_PLAY = 'chefjeff.usage-played.v1';
  let usageVisitDone = false, usagePlayDone = false, usageWantsPlay = false, usageQueued = false, usageRetryAt = 0;
  function queueUsage(played) {
    if (played && !usageWantsPlay) {usageWantsPlay = true; usageRetryAt = 0;}
    if (leaving || usageQueued || (usageVisitDone && (!usageWantsPlay || usagePlayDone)) || performance.now() < usageRetryAt) return;
    usageQueued = true;
    setTimeout(async function reportUsage() {
      async function report() {
        let visit, play;
        try {
          visit = localStorage.getItem(USAGE_VISIT) !== '1';
          play = usageWantsPlay && localStorage.getItem(USAGE_PLAY) !== '1';
          usageVisitDone = !visit;
          usagePlayDone = localStorage.getItem(USAGE_PLAY) === '1';
          if (!visit && !play) return;
          // Verify writable storage before counting. Without it, skip browser estimates.
          const probe = visit ? USAGE_VISIT : USAGE_PLAY;
          localStorage.setItem(probe, '0'); localStorage.removeItem(probe);
        } catch (_) {usageVisitDone = usagePlayDone = true; return;}
        usageRetryAt = performance.now() + 15000;
        const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 5000);
        try {
          const r = await serverFetch('/api/usage', {method:'POST', signal:controller.signal,
            headers:{'Content-Type':'application/json'}, body:JSON.stringify({first_visit:visit, first_play:play})});
          if (!r.ok) return;
          // Server retries are also deduplicated in this page session's memory.
          if (visit) {localStorage.setItem(USAGE_VISIT, '1'); usageVisitDone = true;}
          if (play) {localStorage.setItem(USAGE_PLAY, '1'); usagePlayDone = true;}
        } finally {clearTimeout(timer);}
      }
      try {
        // Serialize cooperating tabs where Web Locks is available; older browsers can double-count a race.
        if (window.navigator?.locks?.request) await window.navigator.locks.request('chefjeff-usage', report);
        else await report();
      } catch (_) { /* A failed usage report must never block play. Retry on a later normal poll. */ }
      finally {usageQueued = false;}
    }, 0);
  }
  function validate(raw) {
    const provider = raw.provider, preset = providers()[provider];
    if (!preset) throw new Error('选择模型服务。');
    const api_key = typeof raw.api_key === 'string' ? raw.api_key.trim() : '';
    if (api_key.length < 8 || api_key.length > 2048 || /\s/.test(api_key)) throw new Error('请输入完整的 API Key。');
    const base_url = preset.custom ? String(raw.base_url || '').trim().replace(/\/+$/, '').replace(/\/chat\/completions$/, '') :
      preset.endpoint || preset.base_url;
    let u;try {u = new URL(base_url);} catch (_) {throw new Error('接口地址无效，请填写完整的 HTTPS 地址。');}
    if (u.protocol !== 'https:' || u.origin === location.origin || u.username || u.password || u.search || u.hash ||
        u.hostname === 'localhost' || /\.(local|localhost|internal)$/.test(u.hostname) ||
        /^[\d.]+$/.test(u.hostname) || u.hostname.includes(':')) throw new Error('请使用外部公开的 HTTPS 模型服务地址。');
    const model = (preset.model_editable && String(raw.model || '').trim()) || preset.model || '';
    if (!model || model.length > 120) throw new Error('请输入服务商提供的模型名称。');
    if (raw.jev_relay === true && provider !== 'jev') throw new Error('服务器转发仅适用于 Jev。');
    return {provider, base_url, model, api_key, remember: raw.remember === true,
      jev_relay: provider === 'jev' && raw.jev_relay === true};
  }
  try {
    const saved = JSON.parse(localStorage.getItem(storageName) || 'null');
    if (saved?.remember === true) setting = validate(saved);
  } catch (_) { /* Storage disabled/corrupted: use memory only. */ }

  async function modelRequest(config, payload, outerSignal, relayContext) {
    const memory=payload.state?.rules && activeMemory?.game_id===state?.game_id ? activeMemory.context:null;
    if(memory)payload={...payload,state:{...payload.state,past_episodes:clone(memory)}};
    const controller = new AbortController(), started = performance.now();
    const timer = setTimeout(() => controller.abort(), config.jev_relay ? 23000 : 20000);
    const abort = () => controller.abort();
    outerSignal?.addEventListener('abort', abort, {once:true});
    if (outerSignal?.aborted) controller.abort();
    if (config.jev_relay) {
      try {
        // mode 'cors' like every other game request: with the page's no-referrer policy, a POST in
        // 'same-origin' mode carries "Origin: null" (Fetch spec; Safari follows it), which the server rejects.
        const r = await serverFetch('/api/model/jev', {method:'POST',mode:'cors',
          credentials:'omit',redirect:'error',signal:controller.signal,
          headers:{'Content-Type':'application/json'},body:JSON.stringify({
            ...relayContext, ...(memory?{memory}:{}), api_key:config.api_key, consent:true, consent_version:relayConsent})});
        const d = await r.json();
        if (!r.ok) throw new Error(d.error || 'Jev 转发连接失败。');
        return d.answer;
      } catch (e) {
        if (e.name === 'AbortError') throw new Error('模型请求超时或已取消。');
        if (e instanceof TypeError) throw new Error('暂时无法连接试玩服务器，请检查网络后重试。');
        throw e;
      } finally {clearTimeout(timer);outerSignal?.removeEventListener('abort',abort);}
    }
    let body, endpoint;
    const preset = providers()[config.provider];
    if (preset.group === 'decision') {
      body = {...payload, model: config.model}; endpoint = config.base_url;
    } else {
      body = {model:config.model, max_tokens:128, messages:[
        {role:'system', content:'You control chef jeff in a shared kitchen. Using the supplied state and rules, choose exactly one action key from questions.next_action.criteria. Return only a JSON object of the form {"choice": "<action key>", "sprint": <true or false>}, where <action key> is one key of questions.next_action.criteria; include sprint only if questions.sprint is present. Do not explain or choose an action outside the candidate set.'},
        {role:'user', content:JSON.stringify({state:payload.state, questions:payload.questions})},
      ]};
      endpoint = config.base_url + '/chat/completions';
    }
    Object.assign(body, preset.extra || {});
    try {
      // No cookies, redirects, proxy fallback, or credentials in the URL/body.
      const r = await nativeFetch(endpoint, {method:'POST', mode:'cors', credentials:'omit', redirect:'error',
        referrerPolicy:'no-referrer', signal:controller.signal,
        headers:{Authorization:'Bearer ' + config.api_key, 'Content-Type':'application/json'}, body:JSON.stringify(body)});
      if (!r.ok) throw new Error(await refusal(r, config.api_key));
      const text = await r.text();
      if (text.length > 262144) throw new Error('模型回复过大。');
      let d, answer, usage;
      try {
        d = JSON.parse(text);
        if (preset.group === 'decision') {
          answer = {choice:d.answers?.next_action?.choice, sprint:d.answers?.sprint?.choice === 'yes'};
          if (d.answers?.next_action?.type !== 'choice' || ('sprint' in payload.questions &&
              !['yes','no'].includes(d.answers?.sprint?.choice))) throw new Error();
          usage = d.usage || {};
        } else {
          answer = JSON.parse(d.choices[0].message.content.trim().replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, ''));
          usage = {input_tokens:d.usage?.prompt_tokens || 0, output_tokens:d.usage?.completion_tokens || 0};
        }
        // A chat reply without sprint means no sprint, as in the local game; a sprint that is not a boolean is rejected.
        if (!Object.hasOwn(payload.questions.next_action.criteria, answer.choice) ||
            ('sprint' in payload.questions && preset.group !== 'decision' && 'sprint' in answer &&
             typeof answer.sprint !== 'boolean')) throw new Error();
      } catch (_) {throw new Error('模型返回了无效动作，未执行任何操作。');}
      return {choice:answer.choice, sprint:answer.sprint === true, usage:{
        input_tokens:boundedCount(usage.input_tokens), output_tokens:boundedCount(usage.output_tokens)},
        latency:(performance.now()-started)/1000};
    } catch (e) {
      if (e.name === 'AbortError') throw new Error('模型请求超时或已取消。');
      if (e instanceof TypeError && config.provider === 'jev') throw new Error('浏览器无法直连 Jev。请检查网络，或明确勾选服务器转发后重试；本次直连请求未通过试玩服务器转发 Key。');
      if (e instanceof TypeError) throw new Error('浏览器无法访问模型服务，请检查网络和跨域支持；本次直连请求未通过试玩服务器转发 Key。');
      throw e;
    } finally {clearTimeout(timer);outerSignal?.removeEventListener('abort', abort);}
  }
  // The status and the provider's short message (never headers), with the key redacted, as in the local game.
  async function refusal(r, key) {
    let message = '';
    try {
      const body = JSON.parse((await r.text()).slice(0, 4096) || '{}');
      const detail = body && typeof body === 'object' ? body.error ?? body : '';
      message = String((detail && typeof detail === 'object' ? detail.message : detail) || '').split(key).join('***').trim().slice(0, 160);
    } catch (_) {}
    const text = '模型接口 HTTP ' + r.status + (message ? '：' + message : '');
    const hint = {401:'Key 无效，请检查后重试。',402:'账号余额不足，请到服务商充值。',403:'账号无权访问这个模型。',429:'请求受限或额度不足，请稍后重试。'}[r.status];
    return hint ? hint + '（' + text + '）' : '连接失败（' + text + '）';
  }
  function boundedCount(n) {return Number.isInteger(n) && n >= 0 && n <= 10000000 ? n : 0;}
  async function markReady(connected, body) {
    return serverFetch('/api/browser-ready', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({game_id:body.game_id, request_id:crypto.randomUUID(), connected})});
  }
  async function configure(body, signal) {
    if (!connection().editable) return response(409, {error:'请结束本局后再更换 API。'});
    testing = true;
    try {
      if (body.clear) {
        const r = await markReady(false, body); if (!r.ok) return r;
        setting = null;
        try {localStorage.removeItem(storageName);} catch (_) {}
      } else {
        const candidate = validate(body);
        checks++;
        await modelRequest(candidate, {state:{connection_test:true}, questions:{next_action:{type:'choice',
          // Two options, as in the local game: a decision service may refuse a one-option question.
          instructions:'Choose ready and return the required format.', criteria:{ready:'Connection ready',wait:'Not ready yet'}}}}, signal,
          {game_id:body.game_id,request_id:crypto.randomUUID(),test:true});
        if (signal?.aborted) throw new Error('连接测试已取消。');
        const r = await markReady(true, body); if (!r.ok) return r;
        // Remove any older remembered key even when the new choice is memory-only.
        try {
          localStorage.removeItem(storageName);
          if (candidate.remember) localStorage.setItem(storageName, JSON.stringify(candidate));
        } catch (_) {candidate.remember = false;}
        setting = candidate;
      }
      return response(200, {ok:true, connection:{...connection(), editable:true}});
    } catch (e) {return response(400, {error:e.message});}
    finally {testing = false;}
  }

  const STATE_REPLIES = new Set(['/api/interact', '/api/throw', '/api/action']);
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return nativeFetch(input, init);
    try {
      if (url.pathname === '/api/connection') {
        return configure(JSON.parse(init.body || '{}'), init.signal); // This body NEVER reaches nativeFetch.
      }
      if (url.pathname === '/api/memory') return changeBrowserMemory(JSON.parse(init.body || '{}'));
      // Restored settings have a fresh server session on every page load.
      if (url.pathname === '/api/start' && setting && state) await markReady(true, state);
      if (url.pathname === '/api/start' && !setting) return response(428,{error:'请先在当前浏览器连接模型服务。'});
      if (url.pathname === '/api/next') {
        if (testing) return response(409,{error:'正在测试连接，请等测试完成后再开局。'});
        if (!setting) return response(428,{error:'请先在当前浏览器连接模型服务。'});
        // The old round must still exist when its consented record is saved.
        // Uploads time out separately; a failed upload never blocks the next round indefinitely.
        await pendingContribution.catch(() => {});
        if (init.signal?.aborted) throw new Error('下一局请求已取消。');
      }
      if (['/api/start','/api/restart','/api/next'].includes(url.pathname) && state?.hosted?.contribution_enabled) {
        // A server acknowledgement is required for automatic retention of an early close.
        await contributionCommand('/api/contribution/consent', {consent:autoOn(), consent_version:CONSENT,
          decision_telemetry:!!(autoOn() && choice.decision_telemetry)}, state.game_id);
      }
      const opening=['/api/start','/api/restart','/api/next'].includes(url.pathname)?openingMemory(state,JSON.parse(init.body||'{}'),url.pathname):null;
      const previousMemory=activeMemory;
      // Publish before awaiting the start acknowledgement: a state poll can see a
      // running kitchen first, and a lost acknowledgement must not lose its context.
      if(opening)activeMemory=opening;
      const result = await serverFetch(url.pathname, init);
      if(!result.ok && opening && activeMemory===opening)activeMemory=previousMemory;
      if(result.ok && ['/api/start','/api/restart','/api/next'].includes(url.pathname)) {
        const opened=await result.clone().json();if(opened.receipt)rememberReceipt(opened.receipt);
      }
      if (result.ok && ['/api/start', '/api/restart', '/api/next', '/api/resume'].includes(url.pathname)) queueUsage(true);
      if (!result.ok || (url.pathname !== '/api/state' && !STATE_REPLIES.has(url.pathname))) return result;
      // Gameplay replies carry the resulting state; both get this page's connection details.
      // Also this browser's contribution answer: the result card offers 贡献本局 after 暂不.
      const withConnection = d => {observeMemory(d);if(d.hosted?.contribution_receipt)rememberReceipt(d.hosted.contribution_receipt);state = d;queueUsage(d.phase === 'running');d.connection = connection();d.limits.connection_checks = checks;
        if (d.hosted) Object.assign(d.hosted, {contribution_offer: !!d.hosted.contribution_enabled && choice?.answer === 'later',
          contribution_busy: busyRound === d.game_id});
        return d;};
      const d = await result.json();
      if (url.pathname === '/api/state') return response(200, withConnection(d));
      if (d.state) d.state = withConnection(d.state);
      return response(200, d);
    } catch (_) {return response(503, {error:transportError || '厨房连接不可用，请刷新页面重新连接。'});}
  };

  // Cocos uses XMLHttpRequest locally. Its hosted hook shares this credential-free game transport.
  window.chefjeffHostedRequest = async (path, body) => {
    if (!path.startsWith('/api/')) throw new Error('游戏接口无效。');
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), path === '/api/next' ? 15000 : 5000);
    try {
      const r = await window.fetch(path, {method:body?'POST':'GET',signal:controller.signal,
        headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
      const d = await r.json();if (!r.ok) throw new Error(d.error || '厨房请求失败。');return d;
    } finally {clearTimeout(timer);}
  };

  async function poll() {
    try {
      if (document.hidden || !setting || !state || state.phase !== 'running') return;
      const r = await serverFetch('/api/model/request');
      if (!r.ok) return;
      const {request} = await r.json();
      if (!request || handled.has(request.id)) return;
      handled.add(request.id);
      while (handled.size > 100) handled.delete(handled.values().next().value);
      const reportedMemory=activeMemory?.game_id===state.game_id?activeMemory.context:null;
      let answer;
      const startedAt=performance.now();
      let errorType=null;
      try {answer = await modelRequest(setting, request.payload, undefined,
        {game_id:state.game_id,id:request.id,test:false});delete answer.latency;}
      catch (e) {
        answer = {failed:true};
        errorType=e.name==='AbortError'?'timeout':'transport_or_response_error';
        const label = document.getElementById('api-message');
        if (label) {label.textContent = e.message;label.className = 'error';}
      }
      const measuredDuration=Math.round(performance.now()-startedAt);
      await serverFetch('/api/model/result', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:request.id, ...answer,
          ...(autoOn() && choice.decision_telemetry && state.hosted?.research_active && Number.isFinite(measuredDuration) && measuredDuration>=0 && measuredDuration<=120000?{telemetry:{duration_ms:measuredDuration,error_type:errorType}}:{}),
          ...(reportedMemory?{memory_condition:{enabled:reportedMemory.enabled,version:2,
            used_rounds:reportedMemory.episodes.length,omitted_rounds:reportedMemory.omitted_rounds}}:{})})});
    } catch (_) { /* Next normal state poll displays session/network failures. */ }
    finally {setTimeout(poll, 200);}
  }
  setTimeout(poll, 200);
  const CHOICE_KEY = 'chefjeff.contribution-choice.v1', RECEIPTS_KEY = 'chefjeff.contribution-receipts.v1';
  // Equals hosted_records.CONSENT_VERSION: new terms ask again instead of carrying an old answer over.
  const CONSENT = 'pilot-session-2026-10-v4';
  let pendingContribution = Promise.resolve(), autoRound = '', busyRound = '', shown = null, askedAt = '', notice = {round:'', text:''};
  const stored = (name, fallback) => {try {return JSON.parse(localStorage.getItem(name) || 'null') ?? fallback;} catch (_) {return fallback;}};
  const keep = (name, value) => {try {value == null ? localStorage.removeItem(name) : localStorage.setItem(name,JSON.stringify(value));} catch (_) {}};
  keep('chefjeff.contribution-auto.v1', null); // Older opt-in under superseded terms; never read again.
  // The up-front answer: 'auto' (standing consent for later rounds) or 'later' (ask per round).
  let choice = stored(CHOICE_KEY, null);
  if (choice?.consent_version !== CONSENT || !['auto','later'].includes(choice.answer)) choice = null;
  const autoOn = () => choice?.answer === 'auto';
  let receipts = stored(RECEIPTS_KEY, []);
  receipts = (Array.isArray(receipts) ? receipts : []).filter(r => r && typeof r.id === 'string' && typeof r.deletion_token === 'string' && Date.parse(r.expires_at) > Date.now());
  const contributionStatus = text => {const n=document.getElementById('contribution-status');if(n)n.textContent=text;};
  function rememberReceipt(receipt) {
    receipts=[...receipts.filter(r=>r.id!==receipt.id),receipt];
    keep(RECEIPTS_KEY,receipts);showReceipts();
  }
  function showReceipts() {
    const box=document.getElementById('contribution-receipt'),download=document.getElementById('contribution-download');
    if(box)box.value=receipts.length?JSON.stringify(receipts.length===1?receipts[0]:receipts,null,2):'';
    if(download)download.hidden=!receipts.length;
  }
  function showChoice() {
    const n=document.getElementById('contribution-choice');
    if(n)n.textContent=autoOn()?'当前选择：以后每局结束自动贡献，保存 30 天。':
      choice?'当前选择：暂不自动贡献。结算画面可点「贡献本局」只贡献这一局。':'当前选择：尚未选择。';
  }
  function badge() {
    const n=document.getElementById('contribution-badge');if(!n)return;
    const s=shown || state;
    n.textContent=!s?.hosted?.contribution_enabled||s.phase==='running'?'':
      notice.round===s.game_id?notice.text:autoOn()?'自动贡献已开启。':'';
    n.hidden=!n.textContent;
  }
  const report = (round, text) => {notice={round,text};contributionStatus(text);badge();};
  async function contributionCommand(path, extra={}, round=state?.game_id) {
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try {
      const payload=['/api/contribution/delete','/api/contribution/download'].includes(path)?extra:{game_id:round,request_id:crypto.randomUUID(),...extra};
      const r=await serverFetch(path,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const d=await r.json();if(!r.ok)throw new Error(d.error||'请求失败。');return d;
    } catch(e) {if(e.name==='AbortError')throw new Error('贡献数据请求超时，请重试。');throw e;}
    finally {clearTimeout(timer);}
  }
  async function contribute(mode, round) {
    busyRound=round;
    try {
      const d=await contributionCommand('/api/contribution/save',{consent:true,consent_version:CONSENT,consent_mode:mode},round);
      receipts=[...receipts.filter(r=>r.id!==d.receipt.id),d.receipt];
      keep(RECEIPTS_KEY,receipts);showReceipts();
      return d.receipt;
    } finally {busyRound='';}
  }
  // One round under the same terms: the result card's 贡献本局 and the Settings button.
  function contributeRound() {
    const s=shown||state,round=s?.game_id;
    if(s?.phase!=='ended'||!s.hosted?.contribution_enabled||s.hosted.contributed||busyRound===round)return;
    pendingContribution=pendingContribution.catch(()=>{}).then(()=>contribute('round',round))
      .then(()=>report(round,'本局已贡献，保存 30 天。删除凭证在「设置 → 数据导出」。'))
      .catch(error=>report(round,'贡献失败：'+error.message));
  }
  window.addEventListener('kitchen-contribute', contributeRound);
  function ask(at) {
    const dialog=document.getElementById('contribution-ask');
    if(!dialog||document.querySelector('dialog[open]'))return; // Settings or help first; the next state asks.
    askedAt=at;dialog.showModal();
  }
  window.addEventListener('kitchen-state', e => {
    const s=e.detail;shown=s;
    if(s.hosted?.research_error)contributionStatus('贡献保存失败，请下载本局预览并稍后重试。');
    const button = document.getElementById('contribution-save');
    if (button) button.disabled = !(s.phase === 'ended' && s.hosted?.contribution_enabled && !s.hosted.contributed && busyRound !== s.game_id);
    if(autoOn()&&s.hosted?.contribution_enabled&&s.phase==='ended'&&autoRound!==s.game_id){
      const round=autoRound=s.game_id;
      pendingContribution=pendingContribution.catch(()=>{}).then(()=>contribute('standing',round))
        .then(()=>report(round,'本局已自动贡献，保存 30 天。'))
        .catch(error=>report(round,'自动贡献失败：'+error.message));
    }
    // Asked before the first round, with no default answer. Browsers may still close it on Esc without
    // an answer; then it comes back once at the next start or result screen until answered.
    const at=s.game_id+'/'+s.phase;
    if(!choice&&askedAt!==at&&s.hosted?.contribution_enabled&&['ready','ended'].includes(s.phase))ask(at);
    badge();
  });
  window.addEventListener('DOMContentLoaded', () => {
    const el = id => document.getElementById(id);
    const status = contributionStatus, command=contributionCommand, dialog=el('contribution-ask');
    showReceipts();showChoice();
    dialog.oncancel = e => e.preventDefault(); // Both answers are one click; Esc is not an answer.
    const answer = auto => {
      choice={consent_version:CONSENT,answer:auto?'auto':'later',decision_telemetry:!!el('ask-telemetry')?.checked,since:new Date().toISOString()};keep(CHOICE_KEY,choice);
      // Agreeing never uploads a round that had already ended.
      if(auto){const now=shown||state;autoRound=now?.phase==='ended'?now.game_id:'';}
      if(!auto && state?.hosted?.research_active) {
        pendingContribution=pendingContribution.catch(()=>{}).then(()=>command('/api/contribution/consent',
          {consent:false,consent_version:CONSENT,decision_telemetry:false})).catch(()=>status('关闭自动贡献未确认，请重试。'));
      }
      dialog.close();showChoice();badge();
      status(auto?'已开启自动贡献：此后每局结束自动保存 30 天。':'已选择暂不贡献，之后不会自动上传。');
    };
    el('ask-auto').onclick = () => answer(true);
    el('ask-later').onclick = () => answer(false);
    el('contribution-change').onclick = () => dialog.showModal();
    el('contribution-preview').onclick = async () => {
      try {const d = await command('/api/contribution/preview');el('contribution-data').value = JSON.stringify(d.record,null,2);el('contribution-data').hidden = false;}
      catch (e) {status(e.message);}
    };
    el('contribution-save').onclick = contributeRound;
    if(el('contribution-own-data'))el('contribution-own-data').onclick = async () => {
      try {
        const receipt=receipts[receipts.length-1];
        if(!receipt)throw new Error('尚无可下载的贡献记录。');
        const records=(await command('/api/contribution/download',{id:receipt.id,deletion_token:receipt.deletion_token})).record;
        const url=URL.createObjectURL(new Blob([JSON.stringify(records,null,2)],{type:'application/json'}));
        const link=document.createElement('a');link.href=url;link.download='chefjeff-my-contributions.json';link.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
      }catch(e){status(e.message);}
    };
    el('contribution-download').onclick = () => {
      if (!receipts.length) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(receipts.length===1?receipts[0]:receipts,null,2)],{type:'application/json'}));
      const a = document.createElement('a');a.href=url;a.download='chefjeff-deletion-receipt.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
    el('contribution-delete').onclick = async () => {
      try {
        let parsed;try {parsed=JSON.parse(el('contribution-receipt').value);} catch (_) {throw new Error('删除凭证格式不正确，请粘贴完整的凭证。');}
        const list=Array.isArray(parsed)?parsed:[parsed];
        if(!list.length||list.some(r=>!r||typeof r.id!=='string'||typeof r.deletion_token!=='string'))throw new Error('删除凭证格式不正确，请粘贴完整的凭证。');
        const failed=[];let deleted=0;
        for(const rcp of list){
          try {
            await command('/api/contribution/delete',{id:rcp.id,deletion_token:rcp.deletion_token});
            receipts=receipts.filter(r=>r.id!==rcp.id);keep(RECEIPTS_KEY,receipts);deleted++;
          }catch(_){failed.push(rcp);}
        }
        showReceipts();el('contribution-receipt').value=failed.length?JSON.stringify(failed.length===1?failed[0]:failed,null,2):'';
        status(failed.length?`已删除 ${deleted} 份记录；${failed.length} 份未删除，请检查凭证后重试。`:'已删除贡献数据。');
      } catch (e) {status(e.message);}
    };
    const select = document.getElementById('api-provider');
    if (select && !setting) {select.value = 'deepseek';select.dispatchEvent(new Event('change'));}
  });
})();
