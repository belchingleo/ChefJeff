/* Hosted-only transport. The secret and native fetch stay in this closure. */
(() => {
  'use strict';
  const nativeFetch = window.fetch.bind(window);
  const storageName = 'chefjeff.browser-key.v1';
  const relayConsent = 'jev-relay-2026-10-v1';
  window.chefjeffJevRelayAvailable = true;
  let setting = null, state = null, checks = 0, testing = false;
  const handled = new Set();
  const response = (status, data) => new Response(JSON.stringify(data), {
    status, headers: {'Content-Type': 'application/json'},
  });
  const connection = () => ({configured: !!setting, provider: setting?.provider || 'deepseek',
    base_url: setting?.base_url || '', model: setting?.model || '', remembered: !!setting?.remember,
    jev_relay: setting?.jev_relay === true,
    editable: !testing && (!state || ['ready', 'ended'].includes(state.phase))});
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
  function validate(raw) {
    const provider = raw.provider;
    if (!['jev','deepseek','compatible'].includes(provider)) throw new Error('选择模型服务。');
    const api_key = typeof raw.api_key === 'string' ? raw.api_key.trim() : '';
    if (api_key.length < 8 || api_key.length > 2048 || /\s/.test(api_key)) throw new Error('请输入完整的 API Key。');
    const base_url = provider === 'jev' ? 'https://api.typesafe.ai/v1' : provider === 'deepseek' ?
      'https://api.deepseek.com' : String(raw.base_url || '').trim().replace(/\/+$/, '').replace(/\/chat\/completions$/, '');
    let u;try {u = new URL(base_url);} catch (_) {throw new Error('接口地址无效，请填写完整的 HTTPS 地址。');}
    if (u.protocol !== 'https:' || u.origin === location.origin || u.username || u.password || u.search || u.hash ||
        u.hostname === 'localhost' || /\.(local|localhost|internal)$/.test(u.hostname) ||
        /^[\d.]+$/.test(u.hostname) || u.hostname.includes(':')) throw new Error('请使用外部公开的 HTTPS 模型服务地址。');
    const model = provider === 'jev' ? 'jev-latest' : String(raw.model || '').trim();
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
            ...relayContext, api_key:config.api_key, consent:true, consent_version:relayConsent})});
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
    if (config.provider === 'jev') {
      body = {...payload, model: config.model}; endpoint = config.base_url + '/systemone';
    } else {
      body = {model:config.model, max_tokens:128, messages:[
        {role:'system', content:'Control chef jeff in this shared kitchen. Choose exactly one legal action key from questions.next_action.criteria. Return only JSON with choice and a boolean sprint. Use the supplied state and rules; do not invent actions.'},
        {role:'user', content:JSON.stringify({state:payload.state, questions:payload.questions})},
      ]};
      if (config.provider === 'deepseek') {body.response_format = {type:'json_object'};body.thinking = {type:'disabled'};}
      endpoint = config.base_url + '/chat/completions';
    }
    try {
      // No cookies, redirects, proxy fallback, or credentials in the URL/body.
      const r = await nativeFetch(endpoint, {method:'POST', mode:'cors', credentials:'omit', redirect:'error',
        referrerPolicy:'no-referrer', signal:controller.signal,
        headers:{Authorization:'Bearer ' + config.api_key, 'Content-Type':'application/json'}, body:JSON.stringify(body)});
      if (!r.ok) throw new Error('模型接口返回 HTTP ' + r.status + '，请检查账号和模型。');
      const text = await r.text();
      if (text.length > 262144) throw new Error('模型回复过大。');
      let d, answer, usage;
      try {
        d = JSON.parse(text);
        if (config.provider === 'jev') {
          answer = {choice:d.answers?.next_action?.choice, sprint:d.answers?.sprint?.choice === 'yes'};
          if (d.answers?.next_action?.type !== 'choice' || ('sprint' in payload.questions &&
              !['yes','no'].includes(d.answers?.sprint?.choice))) throw new Error();
          usage = d.usage || {};
        } else {
          answer = JSON.parse(d.choices[0].message.content.trim().replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, ''));
          usage = {input_tokens:d.usage?.prompt_tokens || 0, output_tokens:d.usage?.completion_tokens || 0};
        }
        if (!Object.hasOwn(payload.questions.next_action.criteria, answer.choice) ||
            ('sprint' in payload.questions && typeof answer.sprint !== 'boolean')) throw new Error();
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
          instructions:'Connection test. Choose wait.', criteria:{wait:'Wait'}}}}, signal,
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
      const result = await serverFetch(url.pathname, init);
      if (!result.ok || (url.pathname !== '/api/state' && !STATE_REPLIES.has(url.pathname))) return result;
      // Gameplay replies carry the resulting state; both get this page's connection details.
      // Also this browser's contribution answer: the result card offers 贡献本局 after 暂不.
      const withConnection = d => {state = d;d.connection = connection();d.limits.connection_checks = checks;
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
      let answer;
      try {answer = await modelRequest(setting, request.payload, undefined,
        {game_id:state.game_id,id:request.id,test:false});delete answer.latency;}
      catch (e) {
        answer = {failed:true};
        const label = document.getElementById('api-message');
        if (label) {label.textContent = e.message;label.className = 'error';}
      }
      await serverFetch('/api/model/result', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:request.id, ...answer})});
    } catch (_) { /* Next normal state poll displays session/network failures. */ }
    finally {setTimeout(poll, 200);}
  }
  setTimeout(poll, 200);
  const CHOICE_KEY = 'chefjeff.contribution-choice.v1', RECEIPTS_KEY = 'chefjeff.contribution-receipts.v1';
  // Equals hosted_records.CONSENT_VERSION: new terms ask again instead of carrying an old answer over.
  const CONSENT = 'pilot-session-2026-10-v2';
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
      const payload=path==='/api/contribution/delete'?extra:{game_id:round,request_id:crypto.randomUUID(),...extra};
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
      choice={consent_version:CONSENT,answer:auto?'auto':'later',since:new Date().toISOString()};keep(CHOICE_KEY,choice);
      // Agreeing never uploads a round that had already ended.
      if(auto){const now=shown||state;autoRound=now?.phase==='ended'?now.game_id:'';}
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
