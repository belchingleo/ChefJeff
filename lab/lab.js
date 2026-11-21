// ChefJeff lab: recorded answers only. Reads data/index.json and data/moments/<id>.json (scripts/build_lab.py).
(function () {
  'use strict';

  const TEXT = {
    zh: {
      title: 'ChefJeff 实验室', subtitle: '同一个厨房、同一时刻，给 Jeff 不同的信息，他会怎么选',
      tab_overview: '概览', tab_moments: '时刻', tab_results: '结果', f_level: '关卡', f_label: '类型', all: '全部',
      pick: '从左边选一个时刻。', foot: '这里的回答都是事先记录的，页面不会调用任何模型。',
      model: '模型', left: '左边', right: '右边', level: '第 {n} 关', holding: 'Jeff 手里', nothing: '没有东西',
      answers: '记录的回答', no_answers: '这个请求还没有记录的回答。', chars: '{n} 字符',
      chosen: '选了', avg_p: '平均概率（前 5 个选项）', options: '选项', rules: '规则', kitchen: '厨房',
      history: '历史（时间线或最近事件）', step_check: '步骤检查', other: '其余部分',
      legend_step: '这一刻该做的那一步', legend_played: '实际玩时选的（退回上一步）', legend_chosen: '记录里有模型选了',
      loading: '读取中…', load_failed: '数据读不到：{e}。本地请在 lab 目录运行 python3 -m http.server。',
      res_intro: '每一格是记录的回答里的比例，括号里是回答数。每组只比同一批时刻：这些时刻上两种请求都有记录的回答。Jev 每个请求问 3 遍，Perplexity 问 1 遍（它对同一请求的回答不变）。只统计请求和页面上完全一致的回答。',
      res_answers: '回答数', res_step: '选对该做的那一步', res_go: '空手或拿着别的东西跑出餐口', res_plate: '开局先拿盘子',
      res_back: '重复退回上一步', none: '—', paired: '“{c}”和今天的请求，同一批 {n} 个时刻',
    },
    en: {
      title: 'ChefJeff Lab', subtitle: 'Same kitchen, same moment, different information: what does Jeff choose?',
      tab_overview: 'Overview', tab_moments: 'Moments', tab_results: 'Results', f_level: 'Level', f_label: 'Kind', all: 'All',
      pick: 'Pick a moment on the left.', foot: 'Every answer here was recorded beforehand; this page calls no model.',
      model: 'Model', left: 'Left', right: 'Right', level: 'Level {n}', holding: 'Jeff holds', nothing: 'nothing',
      answers: 'Recorded answers', no_answers: 'No answers recorded for this request yet.', chars: '{n} characters',
      chosen: 'chose', avg_p: 'Mean probability (top 5 options)', options: 'Options', rules: 'Rules', kitchen: 'Kitchen',
      history: 'History (timeline or recent events)', step_check: 'Step check', other: 'Everything else',
      legend_step: 'the step this moment calls for', legend_played: 'chosen in play (undoing the step before)',
      legend_chosen: 'a recorded model chose it',
      loading: 'Loading…', load_failed: 'Could not read the data: {e}. Locally, run python3 -m http.server in the lab folder.',
      res_intro: 'Each cell is the share of recorded answers, with the number of answers in brackets. Each group compares the same moments: those with recorded answers for both requests. Jev was asked each request 3 times, Perplexity once (it gives the same answer to the same request). Only answers to requests identical to the ones shown are counted.',
      res_answers: 'Answers', res_step: 'Chose the step the moment calls for', res_go: 'Walked to the serving window with nothing to serve',
      res_plate: 'Took a plate first at the opening', res_back: 'Undid the previous step again', none: '—',
      paired: '"{c}" against today\'s request, the same {n} moments',
    },
  };
  const CONDITION = {
    today: { zh: '今天的请求', en: "Today's request" },
    restructured: { zh: '重构后的请求（四块 + 走路提示）', en: 'Restructured (four parts + walk note)' },
    with_kitchen_view: { zh: '再加精简厨房（五块 + 走路提示）', en: 'Plus the kitchen view (five parts + walk note)' },
  };
  const LABEL = {
    pan_ready: { zh: '锅里的菜熟了', en: 'Cooked food in a pan' }, serve: { zh: '手里有做好的菜', en: 'Holding a finished dish' },
    hand_over: { zh: '该递给队友', en: 'Should pass to the partner' }, to_chop: { zh: '该去切菜', en: 'Should go and chop' },
    other: { zh: '其他', en: 'Other' }, go: { zh: '跑出餐口', en: 'Walked to the serving window' },
    open: { zh: '开局', en: 'Opening' }, back: { zh: '退回上一步', en: 'Undid the step before' },
    audit: { zh: '检查举例', en: 'Audit example' }, fire: { zh: '锅快烧焦', en: 'Pan about to burn' },
    parts: { zh: '关键时刻', en: 'Key moment' },
  };
  const MODEL = { jev: 'Jev', perplexity: 'Perplexity' };
  const OVERVIEW = {
    zh: `
      <div class="card"><h2>这是什么</h2>
        <p>ChefJeff 是一个人和 AI 一起做菜的游戏。AI 厨师 Jeff 每走一步，游戏都给它发一份请求：厨房现在的样子、规则、能做的选项。它从选项里挑一个。</p>
        <p>这里收的是真实对局里的时刻。每个时刻按几种不同的写法重新生成请求（就是游戏会发出的那一份），再附上模型对这份请求的回答。你可以把两种写法并排看，看信息不同时模型选得有什么不同。</p></div>
      <div class="card"><h2>几种请求</h2><ul class="plain">
        <li><b>今天的请求</b>：游戏现在发给 Jeff 的样子。</li>
        <li><b>重构后的请求</b>：打开名字、时间线、联动挂到选项上、规则按动作挑这四块，加走路提示。</li>
        <li><b>再加精简厨房</b>：在上面基础上再打开精简厨房。它让请求小了一半，但 Jev 在第 5 关开局总是先拿盘子、也更常把刚做的一步退回去，所以试玩时关着。</li></ul></div>
      <div class="card"><h2>五块改写分别做什么</h2><ul class="plain">
        <li><b>名字</b>：规则和历史里光写编号的工作台写上名字（“Board 1 (b1)”）。</li>
        <li><b>时间线</b>：最近事件和最近决定合成一张按时间排的表：Jeff 自己的每一步和他选的选项、连续等待、扔出去的东西落到哪、没执行的选择和原因、厨房里出的问题。</li>
        <li><b>联动挂到选项上</b>：做完这个选项以后能做什么，直接写在选项后面。</li>
        <li><b>规则按动作挑</b>：讲某类动作的规则段，只在列出这类选项（或厨房里有相关情况）时才发。</li>
        <li><b>精简厨房</b>：厨房写成一段段文字：时钟、钱、订单、两位厨师、每个工作台、地上和空中的东西；墙、地图、坐标这类原始数据不发。</li></ul>
        <p class="note">走路提示：“走到某处”的选项，到了那里拿着手里的东西什么也做不了时写明。</p></div>
      <div class="card"><h2>怎么读这些数字</h2><ul class="plain">
        <li>回答都是事先记录的，页面不调用模型。</li>
        <li>只有当模型收到的请求和页面上显示的这份逐字节相同，回答才会显示在它下面。</li>
        <li>Jev 每份请求问 3 遍（它每次答得可能不同），Perplexity 问 1 遍。</li>
        <li>时刻来自研究者自己在本地打的对局。</li></ul></div>`,
    en: `
      <div class="card"><h2>What this is</h2>
        <p>ChefJeff is a cooking game a person plays with an AI chef, Jeff. For each of Jeff's steps the game sends a request: the kitchen as it is, the rules and the options. Jeff picks one option.</p>
        <p>The lab holds moments from real rounds. Each moment's request is rebuilt under a few ways of writing it (exactly what the game would send), together with the answers models gave to that request. Put two side by side to see how the choice changes with the information.</p></div>
      <div class="card"><h2>The requests</h2><ul class="plain">
        <li><b>Today's request</b>: what the game sends Jeff now.</li>
        <li><b>Restructured</b>: four parts on (place names, timeline, links on options, rules by action) and the walk note.</li>
        <li><b>Plus the kitchen view</b>: the same with the kitchen view too. It halves the request, but with it Jev took a plate first at every level-5 opening and undid his own steps far more often, so it is off in play.</li></ul></div>
      <div class="card"><h2>The five parts</h2><ul class="plain">
        <li><b>Place names</b>: stations listed by id in the rules and the history get their names ("Board 1 (b1)").</li>
        <li><b>Timeline</b>: recent events and decisions become one time-ordered list: Jeff's own steps with the option chosen, runs of waiting, where his throws came down, choices not done and why, what went wrong in the kitchen.</li>
        <li><b>Links on options</b>: what an option makes possible next is written after the option itself.</li>
        <li><b>Rules by action</b>: a rule paragraph about a kind of action comes only while such an option is listed (or the kitchen calls for it).</li>
        <li><b>Kitchen view</b>: the kitchen written out: clock, money, orders, both chefs, every station, the floor and the air; walls, the map and coordinates are left out.</li></ul>
        <p class="note">Walk note: a "walk to X" option says when, on arrival, nothing at X takes what Jeff holds.</p></div>
      <div class="card"><h2>Reading the numbers</h2><ul class="plain">
        <li>Every answer was recorded beforehand; the page calls no model.</li>
        <li>An answer is shown under a request only when the request the model was given is byte-identical to the one shown.</li>
        <li>Jev was asked each request 3 times (its answers vary), Perplexity once.</li>
        <li>The moments come from the researcher's own local rounds.</li></ul></div>`,
  };

  const state = { lang: 'zh', index: null, moment: null, model: 'jev', left: 'today', right: 'restructured', cache: {} };
  try { const saved = localStorage.getItem('lab-lang'); if (saved === 'en' || saved === 'zh') state.lang = saved; } catch (e) { /* no storage */ }
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const t = (key, vars) => (TEXT[state.lang][key] || key).replace(/\{(\w+)\}/g, (_, k) => (vars || {})[k]);
  const lab = (map, key) => (map[key] ? map[key][state.lang] : key);

  function applyLang() {
    document.documentElement.lang = state.lang === 'zh' ? 'zh-CN' : 'en';
    document.title = t('title');
    document.querySelectorAll('[data-t]').forEach((el) => { el.textContent = t(el.dataset.t); });
    $('lang').textContent = state.lang === 'zh' ? 'English' : '中文';
    renderOverview(); renderFilters(); renderList(); renderDetail(); renderResults();
  }

  function selectTab(name) {
    document.querySelectorAll('.tab').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
    document.querySelectorAll('.panel').forEach((p) => { p.hidden = p.id !== name; });
    if (location.hash !== '#' + name) history.replaceState(null, '', '#' + name);
  }

  function renderOverview() {
    const idx = state.index;
    let counts = '';
    if (idx) {
      const answers = idx.moments.reduce((n, m) => n + Object.values(m.answered).reduce((a, c) => a + Object.values(c).reduce((x, y) => x + y, 0), 0), 0);
      counts = state.lang === 'zh' ? `<p class="note">现有 ${idx.moments.length} 个时刻、${answers} 条记录的回答。</p>`
        : `<p class="note">${idx.moments.length} moments, ${answers} recorded answers.</p>`;
    }
    $('overview').innerHTML = OVERVIEW[state.lang] + counts;
  }

  function filtered() {
    if (!state.index) return [];
    const level = $('f-level').value, label = $('f-label').value;
    return state.index.moments.filter((m) => (!level || String(m.level) === level) && (!label || m.labels.includes(label)));
  }

  function renderFilters() {
    if (!state.index) return;
    const levels = [...new Set(state.index.moments.map((m) => m.level))].sort();
    const labels = [...new Set(state.index.moments.flatMap((m) => m.labels))].sort();
    const fill = (sel, values, name) => {
      const keep = sel.value;
      sel.innerHTML = `<option value="">${t('all')}</option>` + values.map((v) => `<option value="${esc(v)}">${esc(name(v))}</option>`).join('');
      sel.value = values.map(String).includes(keep) ? keep : '';
    };
    fill($('f-level'), levels, (v) => t('level', { n: v }));
    fill($('f-label'), labels, (v) => lab(LABEL, v));
  }

  function renderList() {
    const list = $('moment-list');
    list.innerHTML = filtered().map((m) => {
      const kinds = m.labels.map((l) => lab(LABEL, l)).join(' · ');
      return `<li><button type="button" data-id="${esc(m.id)}" aria-current="${state.moment && state.moment.id === m.id}">
        <span>${esc(t('level', { n: m.level }))} · ${m.t} s · ${esc(m.round)}</span><small>${esc(kinds)}</small></button></li>`;
    }).join('');
  }

  function answerBlock(entry, moment) {
    const answers = entry.answers || [];
    if (!answers.length) return `<p class="note">${t('no_answers')}</p>`;
    const counts = {};
    answers.forEach((a) => { counts[a.choice] = (counts[a.choice] || 0) + 1; });
    const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([choice, n]) => {
      const tag = moment.steps && moment.steps.includes(choice) ? ' <span class="pill">✓</span>' : (moment.played === choice ? ' <span class="pill warn">↺</span>' : '');
      return `<div class="ans"><span><code>${esc(choice)}</code>${tag}</span><b>${n}/${answers.length}</b>
        <span class="bar"><i style="width:${(100 * n / answers.length).toFixed(0)}%"></i></span></div>`;
    }).join('');
    const mean = {};
    const withP = answers.filter((a) => a.probabilities && Object.keys(a.probabilities).length);
    withP.forEach((a) => Object.entries(a.probabilities).forEach(([k, v]) => { mean[k] = (mean[k] || 0) + v / withP.length; }));
    const top = Object.entries(mean).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k, v]) =>
      `<div class="ans"><span><code>${esc(k)}</code></span><b>${v.toFixed(2)}</b><span class="bar"><i style="width:${(100 * v).toFixed(0)}%"></i></span></div>`).join('');
    return `<div class="answers"><div class="note">${t('chosen')}</div>${rows}</div>` +
      (top ? `<div class="answers"><div class="note">${t('avg_p')}</div>${top}</div>` : '');
  }

  function section(title, value) {
    if (value === undefined || value === null) return '';
    const text = typeof value === 'string' ? value : JSON.stringify(value, null, 1);
    return `<details><summary>${esc(title)}</summary><pre class="json">${esc(text)}</pre></details>`;
  }

  function column(condition, moment) {
    const entry = moment.services[state.model][condition];
    const body = entry.request, st = body.state || {};
    const chosen = new Set((entry.answers || []).map((a) => a.choice));
    const steps = new Set(moment.steps || []);
    const options = Object.entries(body.questions.next_action.criteria).map(([key, label]) => {
      const cls = [steps.has(key) ? 'step' : '', moment.played === key ? 'played' : '', chosen.has(key) ? 'chosen' : ''].join(' ');
      return `<li class="${cls}"><code>${esc(key)}</code>${esc(label)}</li>`;
    }).join('');
    const history = st.timeline || (st.recent_events || st.recent_decisions ? { recent_events: st.recent_events, recent_decisions: st.recent_decisions } : undefined);
    const shown = new Set(['kitchen', 'rules', 'timeline', 'recent_events', 'recent_decisions', 'step_check']);
    const rest = Object.fromEntries(Object.entries(st).filter(([k]) => !shown.has(k)));
    return `<div class="col"><h3>${esc(lab(CONDITION, condition))}<small>${t('chars', { n: entry.chars.toLocaleString() })}</small></h3>
      <div><h3>${t('answers')}</h3>${answerBlock(entry, moment)}</div>
      <div><h3>${t('options')}</h3><ul class="opts">${options}</ul></div>
      ${section(t('kitchen'), st.kitchen)}${section(t('history'), history)}${section(t('step_check'), st.step_check)}
      ${section(t('rules'), st.rules)}${Object.keys(rest).length ? section(t('other'), rest) : ''}</div>`;
  }

  function renderDetail() {
    const m = state.moment;
    if (!m) { $('detail').innerHTML = `<p class="hint">${t('pick')}</p>`; return; }
    const conds = state.index.conditions;
    const opt = (sel) => conds.map((c) => `<option value="${c}"${c === sel ? ' selected' : ''}>${esc(lab(CONDITION, c))}</option>`).join('');
    const models = Object.keys(m.services).map((s) => `<option value="${s}"${s === state.model ? ' selected' : ''}>${MODEL[s] || s}</option>`).join('');
    const kinds = m.labels.map((l) => `<span class="pill">${esc(lab(LABEL, l))}</span>`).join(' ');
    $('detail').innerHTML = `
      <div class="card"><h2>${esc(t('level', { n: m.level }))} · ${m.t} s · ${esc(m.round)} #${m.request_id}</h2>
        <p>${kinds}</p><p class="muted">${t('holding')}：${esc(m.holding || t('nothing'))}</p>
        <div class="legend"><span class="l-step">${t('legend_step')}</span><span class="l-played">${t('legend_played')}</span><span class="l-chosen">${t('legend_chosen')}</span></div></div>
      <div class="controls">
        <label>${t('model')}<select id="c-model">${models}</select></label>
        <label>${t('left')}<select id="c-left">${opt(state.left)}</select></label>
        <label>${t('right')}<select id="c-right">${opt(state.right)}</select></label></div>
      <div class="cols">${column(state.left, m)}${column(state.right, m)}</div>`;
    $('c-model').onchange = (e) => { state.model = e.target.value; renderDetail(); };
    $('c-left').onchange = (e) => { state.left = e.target.value; renderDetail(); };
    $('c-right').onchange = (e) => { state.right = e.target.value; renderDetail(); };
  }

  function cell(r, key) {
    const v = r && r[key];
    if (!v || !v[1]) return `<td class="num">${t('none')}</td>`;
    return `<td class="num">${(100 * v[0] / v[1]).toFixed(0)}% <span class="muted">(${v[1]})</span></td>`;
  }

  function renderResults() {
    if (!state.index) { $('results').innerHTML = ''; return; }
    const res = state.index.results || {};
    const tables = Object.keys(state.index.models).map((model) => {
      const row = (name, r) => `<tr><td>${esc(name)}</td><td class="num">${r ? r.answers : t('none')}</td>
          ${cell(r, 'step')}${cell(r, 'go_serve')}${cell(r, 'plate_first')}${cell(r, 'back_repeated')}</tr>`;
      const rows = state.index.conditions.filter((c) => c !== 'today').map((c) => {
        const r = (res[model] || {})[c];
        if (!r) return '';
        return `<tr class="group"><th colspan="6">${esc(t('paired', { n: r.moments, c: lab(CONDITION, c) }))}</th></tr>`
          + row(lab(CONDITION, 'today'), r.today) + row(lab(CONDITION, c), r.this);
      }).join('') || `<tr><td colspan="6" class="muted">${t('none')}</td></tr>`;
      return `<div class="card"><h2>${MODEL[model] || model}</h2><div class="table"><table>
        <thead><tr><th></th><th>${t('res_answers')}</th><th>${t('res_step')}</th><th>${t('res_go')}</th><th>${t('res_plate')}</th><th>${t('res_back')}</th></tr></thead>
        <tbody>${rows}</tbody></table></div></div>`;
    }).join('');
    $('results').innerHTML = `<p class="note">${t('res_intro')}</p>` + tables;
  }

  async function openMoment(id) {
    $('detail').innerHTML = `<p class="hint">${t('loading')}</p>`;
    try {
      if (!state.cache[id]) {
        const r = await fetch(`data/moments/${encodeURIComponent(id)}.json`);
        if (!r.ok) throw new Error(r.status);
        state.cache[id] = await r.json();
      }
      state.moment = state.cache[id];
      if (!state.moment.services[state.model]) state.model = Object.keys(state.moment.services)[0];
      renderList(); renderDetail();
    } catch (e) {
      $('detail').innerHTML = `<p class="hint">${esc(t('load_failed', { e: e.message }))}</p>`;
    }
  }

  async function start() {
    document.querySelectorAll('.tab').forEach((b) => { b.onclick = () => selectTab(b.dataset.tab); });
    $('lang').onclick = () => {
      state.lang = state.lang === 'zh' ? 'en' : 'zh';
      try { localStorage.setItem('lab-lang', state.lang); } catch (e) { /* no storage */ }
      applyLang();
    };
    $('f-level').onchange = renderList;
    $('f-label').onchange = renderList;
    $('moment-list').onclick = (e) => { const b = e.target.closest('button[data-id]'); if (b) openMoment(b.dataset.id); };
    const fromHash = () => {
      const tab = (location.hash || '#overview').slice(1);
      selectTab(['overview', 'moments', 'results'].includes(tab) ? tab : 'overview');
    };
    window.addEventListener('hashchange', fromHash);
    fromHash();
    applyLang();
    try {
      const r = await fetch('data/index.json');
      if (!r.ok) throw new Error(r.status);
      state.index = await r.json();
    } catch (e) {
      $('overview').insertAdjacentHTML('beforeend', `<p class="hint">${esc(t('load_failed', { e: e.message }))}</p>`);
      return;
    }
    applyLang();
  }
  start();
}());
