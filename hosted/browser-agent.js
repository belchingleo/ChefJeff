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
  const session = nativeFetch('/api/session', {method: 'POST', headers: {'Content-Type':'application/json'}, body:'{}'})
    .then(async r => { const d = await r.json(); if (!r.ok) throw new Error(d.error); return d.session; });
  // Attach rejection handling before the game first polls state.
  session.catch(() => {});
  async function serverFetch(path, init = {}) {
    const headers = new Headers(init.headers);
    headers.set('X-ChefJeff-Session', await session);
    return nativeFetch(path, {...init, headers});
  }
  function validate(raw) {
    const provider = raw.provider;
    if (!['jev','deepseek','compatible'].includes(provider)) throw new Error('Select a model provider.');
    const api_key = typeof raw.api_key === 'string' ? raw.api_key.trim() : '';
    if (api_key.length < 8 || api_key.length > 2048 || /\s/.test(api_key)) throw new Error('Enter a complete API key.');
    const base_url = provider === 'jev' ? 'https://api.typesafe.ai/v1' : provider === 'deepseek' ?
      'https://api.deepseek.com' : String(raw.base_url || '').trim().replace(/\/+$/, '').replace(/\/chat\/completions$/, '');
    const u = new URL(base_url);
    if (u.protocol !== 'https:' || u.origin === location.origin || u.username || u.password || u.search || u.hash ||
        u.hostname === 'localhost' || /\.(local|localhost|internal)$/.test(u.hostname) ||
        /^[\d.]+$/.test(u.hostname) || u.hostname.includes(':')) throw new Error('Use an external public HTTPS model service.');
    const model = provider === 'jev' ? 'jev-latest' : String(raw.model || '').trim();
    if (!model || model.length > 120) throw new Error('Enter the model name supplied by your provider.');
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
        {role:'system', content:'Control chef jeff in this cooperative kitchen. Choose exactly one legal action key from questions.next_action.criteria. Return only JSON with choice and a boolean sprint. Use the supplied state and rules; do not invent actions.'},
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
      if (!r.ok) throw new Error('Model API returned HTTP ' + r.status + '. Check your account and model.');
      const text = await r.text();
      if (text.length > 262144) throw new Error('Model response is too large.');
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
      } catch (_) {throw new Error('Model returned an invalid action. No action was applied.');}
      return {choice:answer.choice, sprint:answer.sprint === true, usage:{
        input_tokens:boundedCount(usage.input_tokens), output_tokens:boundedCount(usage.output_tokens)},
        latency:(performance.now()-started)/1000};
    } catch (e) {
      if (e.name === 'AbortError') throw new Error('Model request timed out or was cancelled.');
      if (e instanceof TypeError) throw new Error('Browser could not reach this provider. Check network/CORS support; your key was not forwarded through our server.');
      throw e;
    } finally {clearTimeout(timer);outerSignal?.removeEventListener('abort', abort);}
  }
  function boundedCount(n) {return Number.isInteger(n) && n >= 0 && n <= 10000000 ? n : 0;}
  async function markReady(connected, body) {
    return serverFetch('/api/browser-ready', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({game_id:body.game_id, request_id:crypto.randomUUID(), connected})});
  }
  async function configure(body, signal) {
    if (!connection().editable) return response(409, {error:'Finish the round before changing your connection.'});
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
        if (signal?.aborted) throw new Error('Connection cancelled.');
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
      if (url.pathname === '/api/start' && !setting) return response(428,{error:'Connect your model in this browser first.'});
      const result = await serverFetch(url.pathname, init);
      if (url.pathname !== '/api/state' || !result.ok) return result;
      const d = await result.json(); state = d;
      d.connection = connection();
      d.limits.connection_checks = checks;
      return response(200, d);
    } catch (_) {return response(503, {error:'Kitchen connection unavailable. Refresh to create a new session.'});}
  };

  // Cocos uses XMLHttpRequest locally. Its hosted hook shares this credential-free game transport.
  window.chefjeffHostedRequest = async (path, body) => {
    if (!path.startsWith('/api/')) throw new Error('Invalid game endpoint.');
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 5000);
    try {
      const r = await window.fetch(path, {method:body?'POST':'GET',signal:controller.signal,
        headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
      const d = await r.json();if (!r.ok) throw new Error(d.error || 'Kitchen request failed.');return d;
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
  let receipt = null;
  window.addEventListener('kitchen-state', e => {
    const button = document.getElementById('contribution-save');
    if (button) button.disabled = !(e.detail.phase === 'ended' && e.detail.hosted?.contribution_enabled &&
      document.getElementById('contribution-consent').checked);
  });
  window.addEventListener('DOMContentLoaded', () => {
    const el = id => document.getElementById(id);
    const status = text => {el('contribution-status').textContent = text;};
    async function command(path, extra={}) {
      const r = await serverFetch(path, {method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({game_id:state?.game_id,request_id:crypto.randomUUID(),...extra})});
      const d = await r.json();if (!r.ok) throw new Error(d.error || 'Request failed.');return d;
    }
    el('contribution-consent').onchange = () => {
      el('contribution-save').disabled = !(state?.phase === 'ended' && state?.hosted?.contribution_enabled && el('contribution-consent').checked);
    };
    el('contribution-preview').onclick = async () => {
      try {const d = await command('/api/contribution/preview');el('contribution-data').value = JSON.stringify(d.record,null,2);el('contribution-data').hidden = false;}
      catch (e) {status(e.message);}
    };
    el('contribution-save').onclick = async () => {
      el('contribution-save').disabled = true;
      try {
        if (!el('contribution-consent').checked) return;
        const d = await command('/api/contribution/save',{consent:true,consent_version:'pilot-session-2026-09-v1'});
        receipt = d.receipt;
        el('contribution-receipt').value = JSON.stringify(receipt,null,2);
        el('contribution-download').hidden = false;
        el('contribution-consent').checked = false;
        status('Saved for 30 days. Download your deletion receipt before leaving. 已保存，请离开前下载删除凭证。');
      } catch(e) {status(e.message);}
    };
    el('contribution-download').onclick = () => {
      if (!receipt) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));
      const a = document.createElement('a');a.href=url;a.download='chefjeff-deletion-receipt.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
    el('contribution-delete').onclick = async () => {
      try {
        const rcp = JSON.parse(el('contribution-receipt').value);
        const r = await serverFetch('/api/contribution/delete',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({id:rcp.id,deletion_token:rcp.deletion_token})});
        if (!r.ok) throw new Error('Receipt invalid, record already deleted, or expired. 凭证无效，或记录已删除／过期。');
        status('Contribution deleted. 已删除贡献数据。');el('contribution-receipt').value='';receipt=null;
      } catch (e) {status(e.message);}
    };
    const select = document.getElementById('api-provider');
    if (select && !setting) {select.value = 'deepseek';select.dispatchEvent(new Event('change'));}
  });
})();
