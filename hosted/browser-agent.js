/* Hosted-only transport. The secret and native fetch stay in this closure. */
(() => {
  'use strict';
  const nativeFetch = window.fetch.bind(window);
  const storageName = 'chefjeff.browser-key.v1';
  let setting = null, state = null, checks = 0, testing = false;
  const handled = new Set();
  const response = (status, data) => new Response(JSON.stringify(data), {
    status, headers: {'Content-Type': 'application/json'},
  });
  const connection = () => ({configured: !!setting, provider: setting?.provider || 'deepseek',
    base_url: setting?.base_url || '', model: setting?.model || '', remembered: !!setting?.remember,
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
    return {provider, base_url, model, api_key, remember: raw.remember === true};
  }
  try {
    const saved = JSON.parse(localStorage.getItem(storageName) || 'null');
    if (saved?.remember === true) setting = validate(saved);
  } catch (_) { /* Storage disabled/corrupted: use memory only. */ }

  async function modelRequest(config, payload, outerSignal) {
    const controller = new AbortController(), started = performance.now();
    const timer = setTimeout(() => controller.abort(), 20000);
    const abort = () => controller.abort();
    outerSignal?.addEventListener('abort', abort, {once:true});
    if (outerSignal?.aborted) controller.abort();
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
      if (e instanceof TypeError) throw new Error('浏览器无法访问模型服务，请检查网络和跨域支持；Key 不会通过我们的服务器转发。');
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
          instructions:'Connection test. Choose wait.', criteria:{wait:'Wait'}}}}, signal);
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
      if (url.pathname !== '/api/state' || !result.ok) return result;
      const d = await result.json(); state = d;
      d.connection = connection();
      d.limits.connection_checks = checks;
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
      if (!setting || !state || state.phase !== 'running') return;
      const r = await serverFetch('/api/model/request');
      if (!r.ok) return;
      const {request} = await r.json();
      if (!request || handled.has(request.id)) return;
      handled.add(request.id);
      while (handled.size > 100) handled.delete(handled.values().next().value);
      let answer;
      try {answer = await modelRequest(setting, request.payload);delete answer.latency;}
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
  const AUTO_KEY = 'chefjeff.contribution-auto.v1', RECEIPTS_KEY = 'chefjeff.contribution-receipts.v1';
  const CONSENT = 'pilot-session-2026-09-v1';
  let pendingContribution = Promise.resolve(), autoRound = '', uploadedRound = '', shown = null;
  const stored = (name, fallback) => {try {return JSON.parse(localStorage.getItem(name) || 'null') ?? fallback;} catch (_) {return fallback;}};
  const keep = (name, value) => {try {value == null ? localStorage.removeItem(name) : localStorage.setItem(name,JSON.stringify(value));} catch (_) {}};
  let autoConsent = stored(AUTO_KEY, null);
  const autoOn = () => autoConsent?.consent_version === CONSENT;
  const setAuto = value => {autoConsent=value;keep(AUTO_KEY,value);};
  let receipts = stored(RECEIPTS_KEY, []);
  receipts = (Array.isArray(receipts) ? receipts : []).filter(r => r && typeof r.id === 'string' && typeof r.deletion_token === 'string' && Date.parse(r.expires_at) > Date.now());
  const contributionStatus = text => {const n=document.getElementById('contribution-status');if(n)n.textContent=text;};
  function showReceipts() {
    const box=document.getElementById('contribution-receipt'),download=document.getElementById('contribution-download');
    if(box)box.value=receipts.length?JSON.stringify(receipts.length===1?receipts[0]:receipts,null,2):'';
    if(download)download.hidden=!receipts.length;
  }
  function badge() {
    const n=document.getElementById('contribution-badge');if(!n)return;
    const s=shown || state;
    n.textContent=!autoOn()||!s?.hosted?.contribution_enabled||s.phase==='running'?'':
      uploadedRound===s.game_id?'本局已自动上传，保存 30 天。':'自动上传已开启。';
    n.hidden=!n.textContent;
  }
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
    const d=await contributionCommand('/api/contribution/save',{consent:true,consent_version:CONSENT,consent_mode:mode},round);
    receipts=[...receipts.filter(r=>r.id!==d.receipt.id),d.receipt];
    keep(RECEIPTS_KEY,receipts);showReceipts();
    if(mode==='standing')uploadedRound=round;
    return d.receipt;
  }
  window.addEventListener('kitchen-state', e => {
    const s=e.detail;shown=s;
    const button = document.getElementById('contribution-save');
    if (button) button.disabled = !(e.detail.phase === 'ended' && e.detail.hosted?.contribution_enabled &&
      document.getElementById('contribution-consent').checked);
    if(autoOn()&&s.hosted?.contribution_enabled&&s.phase==='ended'&&autoRound!==s.game_id){
      autoRound=s.game_id;
      pendingContribution=pendingContribution.catch(()=>{}).then(()=>contribute('standing',s.game_id))
        .then(()=>contributionStatus('本局已自动上传，保存 30 天。'))
        .catch(error=>contributionStatus('自动上传失败：'+error.message))
        .finally(()=>badge());
    }
    badge();
  });
  window.addEventListener('DOMContentLoaded', () => {
    const el = id => document.getElementById(id);
    const status = text => {el('contribution-status').textContent = text;};
    const command=contributionCommand;
    showReceipts();
    if(el('contribution-auto'))el('contribution-auto').checked=autoOn();
    if(autoOn())el('contribution-consent').checked=true;
    el('contribution-consent').onchange = () => {
      el('contribution-save').disabled = !(state?.phase === 'ended' && state?.hosted?.contribution_enabled && el('contribution-consent').checked);
      if(!el('contribution-consent').checked){
        setAuto(null);if(el('contribution-auto'))el('contribution-auto').checked=false;badge();
      }
    };
    if(el('contribution-auto'))el('contribution-auto').onchange=()=>{
      const box=el('contribution-auto');
      if(box.checked&&!el('contribution-consent').checked&&!autoOn()){
        box.checked=false;status('请先勾选同意上方条款。');return;
      }
      if(box.checked){const now=shown||state;autoRound=now?.phase==='ended'?now.game_id:'';setAuto({consent_version:CONSENT,since:new Date().toISOString()});}
      else setAuto(null);
      status(box.checked?'自动上传已开启，此后每局结束自动保存 30 天。':'已关闭自动上传。');badge();
    };
    el('contribution-preview').onclick = async () => {
      try {const d = await command('/api/contribution/preview');el('contribution-data').value = JSON.stringify(d.record,null,2);el('contribution-data').hidden = false;}
      catch (e) {status(e.message);}
    };
    el('contribution-save').onclick = async () => {
      el('contribution-save').disabled = true;
      try {
        if (!el('contribution-consent').checked) return;
        const round=(shown||state)?.game_id;
        pendingContribution=pendingContribution.catch(()=>{}).then(()=>contribute('round',round));
        await pendingContribution;
        if(!autoOn())el('contribution-consent').checked = false;
        status('已保存，将保留 30 天；请在离开前下载删除凭证。');
      } catch(e) {status(e.message);}
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
