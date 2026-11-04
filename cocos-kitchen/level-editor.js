/* The level editor of the web page: a player's own levels, kept in this browser only, built in three
 * steps (kitchen layout, menu, calibration) and played on this server. The server checks and calibrates
 * every design (level_design.py, player_level_queue.py). Its rules and ingredients come from
 * /api/player-level/catalog, so this page names no ingredient of its own; it mirrors the checks only
 * to show mistakes while a player edits. Chinese text is translated by kitchen-i18n on the page; a
 * player's own names sit in data-no-i18n elements and are never translated. */
(() => {
  'use strict';
  const STORE = 'chefjeff.player-levels.v1';
  const RED = '#b8321e', INK = '#2b1a12', MUTED = '#6e4e38';
  // Station drawing: the engine's station types, not recipe data. Short labels for a 34 px cell.
  const TOOLS = {
    wall: {name: '墙', bg: '#6b3418', fg: '#fdf3e1', line: '#3f2112'},
    counter: {name: '柜台', bg: '#fdf3e1', fg: INK, line: INK},
    board: {name: '案板', bg: '#fbe3b8', fg: INK, line: INK},
    stove: {name: '灶台', bg: '#3d5566', fg: '#fdf3e1', line: INK},
    ingredient_source: {name: '食材箱', bg: '#fdf3e1', fg: '#6b3418', line: '#6b3418'},
    serving_window: {name: '出餐口', bg: '#2a5a9e', fg: '#fdf3e1', line: INK},
    sink: {name: '水槽', bg: '#3d5566', fg: '#fdf3e1', line: INK},
    plate_return: {name: '脏盘回收', bg: '#f0d9b5', fg: INK, line: INK},
    bin: {name: '垃圾桶', bg: INK, fg: '#fdf3e1', line: INK},
    tool_rack: {name: '灭火器架', bg: '#b8321e', fg: '#fdf3e1', line: INK}
  };
  const GLYPHS = {counter: ['柜', 'Ctr'], board: ['板', 'Brd'], serving_window: ['出', 'Out'], sink: ['洗', 'Sink'], plate_return: ['收', 'Ret'], bin: ['桶', 'Bin'], tool_rack: ['灭', 'Ext']}; // i18n: bilingual
  const FLOOR = [['#f0d9b5', '#ecd0a6'], ['#fbe3b8', '#f6d79f'], ['#e7cfa9', '#dfc49a']];
  const STEPS = [[1, 0], [-1, 0], [0, 1], [0, -1]];

  let catalog = null, loading = null, dialog = null, view = {screen: 'list'};
  const session = {};  // per level id: {job, state, position, error} for this page only
  const english = () => window.kitchenI18n?.language === 'en';
  const tr = text => window.kitchenI18n?.t(text) || text;  // for text inside data-no-i18n elements
  const controls = () => window.kitchenControls;
  const fmt = (text, ...args) => text.replace(/\{(\d+)\}/g, (_, n) => String(args[Number(n)]));
  const touch = () => document.body.classList.contains('kitchen-touch-mode');

  // ---- Storage: this browser only, exported as a file to move a level elsewhere.
  function readLevels() {
    try {const v = JSON.parse(localStorage.getItem(STORE) || '[]'); return Array.isArray(v) ? v.filter(r => r && r.id && r.design) : [];}
    catch (_) {return [];}
  }
  let storageFailed = false;
  function writeLevels(list) {
    try {localStorage.setItem(STORE, JSON.stringify(list)); storageFailed = false;} catch (_) {storageFailed = true;}
  }
  function saveLevel(rec) {
    rec.updated = Date.now();
    const list = readLevels(), i = list.findIndex(r => r.id === rec.id);
    if (i < 0) list.unshift(rec); else list[i] = rec;
    writeLevels(list);
  }
  const newId = () => 'L' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

  async function api(path, body) {
    try {
      const r = await fetch(path, {method: body ? 'POST' : 'GET', cache: 'no-store',
        headers: body ? {'Content-Type': 'application/json'} : {}, body: body ? JSON.stringify(body) : undefined});
      let data = {};
      try {data = await r.json();} catch (_) {}
      return {status: r.status, data};
    } catch (_) {return {status: 0, data: {error: '无法连接厨房后端'}};}
  }
  async function loadCatalog() {
    if (catalog) return catalog;
    if (!loading) loading = api('/api/player-level/catalog').then(({status, data}) => {
      if (status === 200 && Array.isArray(data.items)) catalog = data;
      else if (status === 0) loading = null;  // the kitchen was not reachable: ask again next time
      window.dispatchEvent(new Event('kitchen-editor-ready'));
      return catalog;
    });
    return loading;
  }

  // ---- Recipe data from the server.
  const itemOf = id => catalog.items.find(i => i.id === id);
  const heatStep = it => it.steps.find(s => s.operation === 'heat');
  const chops = it => it.steps.some(s => s.operation === 'chop');
  const workMs = it => it.steps.reduce((sum, s) => sum + s.work_game_ms, 0);
  const containerName = id => catalog.containers[id] || id;
  function method(it) {
    const heat = heatStep(it);
    if (heat && chops(it)) return fmt('切好后放进{0}加热', containerName(heat.container));
    if (heat) return fmt('直接放进{0}加热', containerName(heat.container));
    return chops(it) ? '在案板上切好' : '直接放进盘子';
  }
  function patienceMs(work) {
    const p = catalog.patience, rounded = p.step_game_ms * Math.floor(p.factor * work / p.step_game_ms + .5);
    return Math.min(p.max_game_ms, Math.max(p.min_game_ms, rounded));
  }
  function suggestedPrice(items) {
    const p = catalog.price, cooked = items.filter(id => heatStep(itemOf(id))).length;
    return Math.min(p.max, Math.max(p.min, p.base + p.per_item * items.length + p.per_cooked * cooked));
  }
  // A short label for a cell: the ingredient's own name in Chinese, its first letters in English.
  const shortName = name => english() ? tr(name).slice(0, 4) : name;

  // ---- A design: {format, name, size, walls, stations, dishes} as level_design.bundle reads it.
  function starter() {
    const [pan, pot] = catalog.vessels, first = catalog.items[0];
    const at = (type, x, y, extra) => Object.assign({type, x, y}, extra || {});
    return {format: catalog.format, name: '新关卡', size: [14, 9], walls: [],
      stations: [at('ingredient_source', 2, 1, {item: first.id}), at('counter', 7, 1), at('counter', 8, 1), at('counter', 9, 1),
        at('serving_window', 12, 2), at('board', 1, 3), at('board', 1, 4), at('counter', 1, 5), at('stove', 12, 3, {vessel: pan}),
        at('stove', 12, 4, {vessel: pot}), at('counter', 12, 5), at('counter', 6, 4), at('counter', 7, 4), at('sink', 3, 7),
        at('plate_return', 4, 7), at('counter', 6, 7), at('bin', 9, 7), at('tool_rack', 10, 7)],
      dishes: [{name: '新菜', price: suggestedPrice([first.id]), items: [first.id]}]};
  }
  function clean(design) {
    const g = geometry(design);
    return Object.assign({}, design, {name: (design.name || '').trim(), walls: [...g.walls].map(k => k.split(',').map(Number)),
      stations: design.stations.filter(s => g.stations[s.x + ',' + s.y] === s),
      dishes: design.dishes.map(d => ({name: (d.name || '').trim(), price: d.price, items: d.items.slice()}))});
  }
  const signature = design => JSON.stringify(clean(design));
  const toolKey = s => s.type === 'stove' ? 'stove:' + s.vessel : s.type === 'ingredient_source' ? 'source:' + s.item : s.type;
  function toolStation(tool, x, y) {
    const [type, extra] = tool.split(':');
    if (type === 'stove') return {type, x, y, vessel: extra};
    if (type === 'source') return {type: 'ingredient_source', x, y, item: extra};
    return {type, x, y};
  }
  function toolLook(tool) {
    const [type, extra] = tool.split(':');
    if (type === 'wall') return TOOLS.wall;
    if (type === 'stove') {
      const name = containerName(extra);
      return Object.assign({}, TOOLS.stove, {name: fmt('灶台·{0}', name), glyph: english() ? extra.charAt(0).toUpperCase() + extra.slice(1, 3) : name.slice(0, 1)});
    }
    if (type === 'source') {
      const it = itemOf(extra), name = it ? it.name : extra;
      return Object.assign({}, TOOLS.ingredient_source, {name: fmt('{0}食材箱', name), glyph: shortName(name)});
    }
    const glyph = GLYPHS[type];
    return Object.assign({}, TOOLS[type], {glyph: glyph ? glyph[english() ? 1 : 0] : ''});
  }

  function geometry(design) {
    const [W, H] = design.size;
    // The outer wall is wall and holds nothing; everything stands inside it.
    const inside = (x, y) => x > 0 && y > 0 && x < W - 1 && y < H - 1;
    const outer = (x, y) => x === 0 || y === 0 || x === W - 1 || y === H - 1;
    const againstWall = (x, y) => inside(x, y) && (x === 1 || y === 1 || x === W - 2 || y === H - 2);
    const walls = new Set(design.walls.filter(([x, y]) => inside(x, y)).map(([x, y]) => x + ',' + y));
    const stations = {};
    design.stations.forEach(s => {if (inside(s.x, s.y)) stations[s.x + ',' + s.y] = s;});
    const isFloor = (x, y) => inside(x, y) && !walls.has(x + ',' + y) && !stations[x + ',' + y];
    const regions = open => {
      const seen = new Set(), out = [];
      for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) {
        if (!open(x, y) || seen.has(x + ',' + y)) continue;
        const cells = new Set(), queue = [[x, y]]; seen.add(x + ',' + y);
        while (queue.length) {
          const [px, py] = queue.shift(); cells.add(px + ',' + py);
          STEPS.forEach(([dx, dy]) => {const k = (px + dx) + ',' + (py + dy); if (open(px + dx, py + dy) && !seen.has(k)) {seen.add(k); queue.push([px + dx, py + dy]);}});
        }
        out.push(cells);
      }
      return out.sort((a, b) => b.size - a.size);
    };
    // Walls may not cut the kitchen in two (nothing passes through a wall); counters may, food is thrown over them.
    const rooms = regions((x, y) => inside(x, y) && !walls.has(x + ',' + y));
    const floors = regions(isFloor);
    const part = {};
    floors.forEach((cells, n) => cells.forEach(k => {part[k] = n;}));
    // A station needs floor in front of it; a counter boxed in by counters may be reached round the corner.
    // A serving window or plate return faces the room with the outer wall at its back (level_design._facing).
    const standable = (x, y) => {
      const back = catalog.against_the_wall.includes(stations[x + ',' + y]?.type);
      if (STEPS.some(([dx, dy]) => part[(x + dx) + ',' + (y + dy)] !== undefined && (!back || outer(x - dx, y - dy)))) return true;
      if (stations[x + ',' + y]?.type !== 'counter') return false;
      return [-1, 1].some(a => [-1, 1].some(b => part[(x + a) + ',' + (y + b)] !== undefined && stations[x + ',' + (y + b)] && stations[(x + a) + ',' + y]));
    };
    return {W, H, inside, againstWall, walls, stations, rooms, floors, part, standable};
  }

  // ---- Checks the server makes too, shown as the player edits: [{text, error}] (text may be a node).
  function layoutChecks(design) {
    const g = geometry(design), out = [], count = {}, sources = {};
    const err = text => out.push({text, error: true});
    if (g.rooms.length > 1) err(fmt('墙把厨房隔成了 {0} 块，隔开的两边没法传递东西', g.rooms.length));
    if (g.floors.length > 2) err(fmt('地板被隔成了 {0} 块，两位厨师最多各管一块', g.floors.length));
    const stuck = [], loose = [];
    Object.entries(g.stations).forEach(([key, s]) => {
      count[s.type] = (count[s.type] || 0) + 1;
      if (s.type === 'ingredient_source') sources[s.item] = true;
      if (s.type === 'stove') count['stove:' + s.vessel] = (count['stove:' + s.vessel] || 0) + 1;
      const [x, y] = key.split(',').map(Number);
      if (catalog.against_the_wall.includes(s.type) && !g.againstWall(x, y)) loose.push(toolLook(toolKey(s)).name);
      else if (!g.standable(x, y)) stuck.push(toolLook(toolKey(s)).name);
    });
    catalog.exactly_one.forEach(type => {
      const have = count[type] || 0;
      if (have === 0) err(fmt('还缺：{0}', TOOLS[type].name));
      else if (have > 1) err(fmt('{0}只能有 1 个，现在有 {1} 个', TOOLS[type].name, have));
    });
    const [low, high] = catalog.serving_windows, windows = count.serving_window || 0;
    if (windows < low) err(fmt('还缺：{0}', TOOLS.serving_window.name));
    if (windows > high) err(fmt('出餐口最多 {0} 个，现在有 {1} 个', high, windows));
    if ((count.counter || 0) < catalog.plates) err(fmt('柜台至少 {0} 个，用来放开局的盘子', catalog.plates));
    if (!count.bin) err(fmt('还缺：{0}', TOOLS.bin.name));
    needs(design).forEach(n => {if (!n.placed(count, sources)) err(fmt('还缺：{0}', n.name));});
    loose.forEach(name => err(fmt('{0}要贴着外墙摆', name)));
    stuck.forEach(name => err(fmt('{0}跟前没有地方站，人够不着', name)));
    if (g.floors.length === 2 && g.rooms.length === 1) out.push({text: '地板被柜台隔成了两块：两位厨师各站一边，隔着柜台扔东西'});
    return out;
  }
  // What the menu needs on the map: a source per ingredient, a board to chop, a stove per vessel.
  function needs(design) {
    const items = [...new Set(design.dishes.flatMap(d => d.items))].map(itemOf).filter(Boolean), out = [];
    items.forEach(it => out.push({name: fmt('{0}食材箱', it.name), placed: (c, s) => !!s[it.id]}));
    if (items.some(chops)) out.push({name: TOOLS.board.name, placed: c => !!c.board});
    [...new Set(items.map(heatStep).filter(Boolean).map(h => h.container))].forEach(v =>
      out.push({name: fmt('灶台·{0}', containerName(v)), placed: c => !!c['stove:' + v]}));
    return out;
  }
  // What this kitchen still lacks to make one ingredient, in the order the cook needs it: its source, a
  // board when it is chopped, a stove with its vessel when it is cooked. Empty when the kitchen can make it.
  function lacks(it, design) {
    const have = {}, heat = heatStep(it), out = [];
    Object.values(geometry(design).stations).forEach(s => {have[toolKey(s)] = true; have[s.type] = true;});
    if (!have['source:' + it.id]) out.push(TOOLS.ingredient_source.name);
    if (chops(it) && !have.board) out.push(TOOLS.board.name);
    if (heat && !have['stove:' + heat.container]) out.push(fmt('灶台·{0}', containerName(heat.container)));
    return out;
  }
  const ready = design => catalog.items.filter(it => !lacks(it, design).length);
  // A dish's choices for one ingredient: what the kitchen can make, then the rest greyed out with the first
  // thing each one lacks. The ingredient already chosen stays selectable so the select can show it.
  function ingredientOptions(design, dish, id) {
    const can = [], cannot = [];
    catalog.items.filter(o => o.id === id || !dish.items.includes(o.id)).forEach(o => {
      const lack = lacks(o, design);
      (lack.length ? cannot : can).push(h('option', {value: o.id, selected: o.id === id, disabled: !!lack.length && o.id !== id},
        lack.length && o.id !== id ? fmt('{0}（缺{1}）', o.name, lack[0]) : o.name));
    });
    return [can.length ? h('optgroup', {label: '厨房里能做'}, can) : null, cannot.length ? h('optgroup', {label: '厨房里还做不了'}, cannot) : null];
  }
  function menuChecks(design) {
    const out = [], p = catalog.price, err = text => out.push({text, error: true});
    if (!design.dishes.length) err('菜单上至少要有 1 道菜');
    const seen = {};
    design.dishes.forEach((d, n) => {
      const name = (d.name || '').trim();
      if (!name) err(fmt('第 {0} 道菜还没起名', n + 1));
      if (!d.items.length) err(fmt('第 {0} 道菜还没选配料', n + 1));
      if (d.price < p.min || d.price > p.max || d.price % p.step) err(fmt('第 {0} 道菜的价格要在 {1} 到 {2} 元之间', n + 1, p.min, p.max));
      const key = d.items.slice().sort().join('+');
      if (d.items.length && seen[key] !== undefined) err(fmt('第 {0} 道菜和第 {1} 道菜的配料一样，端上去分不清', n + 1, seen[key] + 1));
      else seen[key] = n;
    });
    return out;
  }
  const problems = design => [...layoutChecks(design), ...menuChecks(design)].filter(c => c.error);

  // ---- DOM helpers. Text nodes are translated by kitchen-i18n as they are added; `user` is never translated.
  function h(tag, props, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'style') e.style.cssText = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === 'user') {e.textContent = v; e.setAttribute('data-no-i18n', '');}
      else if (k === 'value') e.value = v;
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : String(kid));
    return e;
  }
  // Element.append would write null as text: leave out what a condition left empty.
  const add = (parent, ...kids) => {for (const k of kids.flat()) if (k != null && k !== false) parent.append(k.nodeType ? k : String(k));};
  const button = (label, onClick, cls = 'btn', extra = {}) => h('button', Object.assign({class: cls, type: 'button', onclick: onClick}, extra), label);
  // A dish as the game draws it on the plate: an official dish's own picture when the ingredients are the
  // same, else its layers on a clean plate, bread as the burger's bun (the server's plating rule). The
  // sprites are the release's, as the kitchen already loaded them; without them there is no picture.
  function dishPicture(items, size) {
    const sprite = key => controls()?.sprite?.(key) || null;
    const look = catalog.official.find(o => o.items.join('+') === items.slice().sort().join('+'));
    const whole = look && sprite(`dishes/${look.id}/ready`), plate = !whole && sprite('objects/clean_plate');
    if (!whole && !plate) return null;
    const box = h('span', {class: 'ed-pic', 'aria-hidden': 'true', style: `width:${size}px;height:${size}px`});
    box.append(spriteImage(whole || plate, size, size, 0));
    if (whole) return box;
    const unit = size / 40, outer = items.filter(i => catalog.wraps[i]);
    const layers = [...outer.map(i => catalog.wraps[i][0]), ...items.filter(i => !catalog.wraps[i]), ...outer.map(i => catalog.wraps[i][1]).reverse()];
    layers.forEach((layer, n) => {const icon = sprite('feedback/' + layer); if (icon) box.append(spriteImage(icon, 34 * unit, 22 * unit, (3 - n * 4) * unit));});
    return box;
  }
  function spriteImage(icon, width, height, dy) {
    let [left, top, right, bottom] = icon.alphaBBox || [0, 0, icon.width, icon.height];
    if (!(right > left && bottom > top)) [left, top, right, bottom] = [0, 0, icon.width, icon.height];
    const scale = Math.min(width / (right - left), height / (bottom - top)), e = h('span', {class: 'ed-sprite'});
    Object.assign(e.style, {width: (right - left) * scale + 'px', height: (bottom - top) * scale + 'px',
      transform: `translate(-50%, -50%) translateY(${dy}px)`, backgroundImage: 'url(' + JSON.stringify(icon.url) + ')',
      backgroundSize: `${icon.atlasWidth * scale}px ${icon.atlasHeight * scale}px`,
      backgroundPosition: `${-(icon.x + left) * scale}px ${-(icon.y + top) * scale}px`});
    return e;
  }
  const dishNames = design => design.dishes.map(d => (d.name || '').trim()).filter(Boolean).join(' · ');

  // ---- The dialog and its screens.
  function ensureDialog() {
    if (dialog) return dialog;
    const style = h('style', {id: 'level-editor-style'});
    style.textContent = `
      dialog.card-page.editor-page{width:min(1100px,calc(100vw - 24px));height:min(720px,calc(100vh - 24px));translate:none}
      .card-page.editor-page .dlg-head{padding:12px 24px 10px;gap:12px}
      .card-page.editor-page .dlg-head h2{font-size:28px;line-height:32px}
      .ed-body{flex:1;min-height:0;overflow:auto;padding:2px 24px 16px;display:flex;flex-direction:column;gap:12px}
      .ed-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
      .ed-hint{margin:0;font-size:13px;line-height:20px;color:var(--muted)}
      .ed-steps{margin-left:auto;display:flex;gap:6px}
      .ed-step{font:12px/16px var(--pixel);padding:6px 10px;border:1px solid var(--muted);background:transparent;color:var(--muted);cursor:pointer}
      .ed-step:hover{background:var(--honey-tint)}
      .ed-step[aria-current="step"]{background:var(--honey);color:var(--ink);border-color:var(--ink)}
      .ed-input{height:40px;box-sizing:border-box;padding:0 10px;font:22px/1 var(--pixel);color:var(--ink);background:var(--paper);border:2px solid var(--ink);min-width:0}
      .ed-quiet{font:13px/20px var(--body);cursor:pointer;border:0;background:transparent;color:var(--muted);text-decoration:underline;padding:0}
      .ed-quiet:hover{color:var(--ink)}
      .ed-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-content:start}
      .ed-card{padding:14px 16px;background:var(--paper);border:2px solid var(--ink);box-shadow:0 3px 0 var(--ink);display:flex;flex-direction:column;gap:8px;min-width:0}
      .ed-card-name{font:22px/26px var(--pixel);overflow-wrap:anywhere}
      .ed-new{font:inherit;cursor:pointer;min-height:180px;border:2px dashed var(--muted);background:transparent;color:var(--muted);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px}
      .ed-new:hover{background:var(--honey-tint)}
      .ed-badge{align-self:flex-start;font:12px/16px var(--pixel);padding:4px 8px;background:var(--surface);color:var(--ink);border:1px solid var(--muted)}
      .ed-badge.ok{background:var(--denim);color:var(--paper);border-color:var(--denim)}
      .ed-badge.bad{background:var(--tomato);color:var(--paper);border-color:var(--tomato)}
      .ed-badge.busy{background:var(--steel);color:var(--paper);border-color:var(--steel)}
      .ed-badge.note{background:var(--honey);border-color:var(--honey)}
      .ed-main{flex:1;min-height:0;display:flex;gap:16px}
      .ed-side{flex:none;display:flex;flex-direction:column;gap:6px;min-height:0;overflow:auto}
      .ed-tool{display:flex;align-items:center;gap:8px;min-height:32px;padding:3px 8px;font:13px/18px var(--body);color:var(--ink);background:var(--paper);border:2px solid var(--ink);box-shadow:0 2px 0 var(--ink);cursor:pointer;text-align:left}
      .ed-tool:hover{background:var(--honey-tint)}
      .ed-tool[aria-pressed="true"]{background:var(--honey);box-shadow:none;transform:translateY(2px)}
      .ed-swatch{width:22px;height:22px;flex:none;display:grid;place-items:center;font:10px/1 var(--pixel);overflow:hidden}
      .ed-board{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px}
      .ed-stage{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;background:var(--frame);border:2px solid var(--ink);overflow:auto;padding:8px}
      .ed-grid{position:relative;display:grid;user-select:none;-webkit-user-select:none;touch-action:none}
      .ed-cell{box-sizing:border-box;padding:0;border:0;display:grid;place-items:center;font:11px/12px var(--pixel);overflow:hidden;cursor:pointer}
      .ed-cell.fixed{cursor:default}
      .ed-cell:focus-visible{outline:3px solid var(--ink);outline-offset:-3px}
      .ed-notice{position:absolute;z-index:2;pointer-events:none;white-space:nowrap;padding:6px 10px;background:var(--paper);color:var(--ink);border:2px solid var(--ink);box-shadow:0 3px 0 var(--ink);font:13px/18px var(--body)}
      .ed-checks{padding:10px 12px;background:var(--surface);border:1px solid var(--muted);display:flex;flex-direction:column;gap:4px;font-size:13px;line-height:20px}
      .ed-checks .err{color:var(--tomato)}
      .ed-foot{flex:none;display:flex;align-items:center;justify-content:space-between;gap:12px}
      .ed-foot .btn,.ed-big{min-height:44px;padding:0 18px;font-size:18px;line-height:18px}
      .ed-dish{display:flex;flex-direction:column;align-items:flex-start;gap:2px;padding:8px 10px;border:2px solid var(--ink);background:var(--paper);box-shadow:0 3px 0 var(--ink);cursor:pointer;text-align:left;font:inherit;color:var(--ink)}
      .ed-dish[aria-pressed="true"]{background:var(--honey);box-shadow:none;transform:translateY(2px)}
      .ed-panel{flex:1;min-width:0;display:flex;flex-direction:column;gap:10px;padding:12px 16px;border:2px solid var(--ink);box-shadow:0 3px 0 var(--ink);overflow:auto}
      .ed-box{padding:10px 12px;background:var(--surface);border:1px solid var(--muted);display:flex;flex-direction:column;gap:2px;font-size:13px;line-height:20px}
      .ed-box b,.ed-label{font:12px/16px var(--pixel);font-weight:400}
      .ed-select{height:34px;padding:0 6px;font:15px var(--body);color:var(--ink);background:var(--paper);border:2px solid var(--ink)}
      .ed-result{flex:1;min-width:0;display:flex;flex-direction:column;gap:12px;padding:18px 22px;border:3px solid var(--walnut);box-shadow:6px 6px 0 var(--ink);overflow:auto}
      .ed-big-title{font:32px/40px var(--pixel)}
      .ed-dots{display:flex;gap:8px}.ed-dots span{width:10px;height:10px;background:var(--steel);animation:ed-dot 1.2s infinite}
      .ed-dots span:nth-child(2){animation-delay:.2s}.ed-dots span:nth-child(3){animation-delay:.4s}
      @keyframes ed-dot{50%{opacity:.25}}
      .ed-pic{position:relative;display:inline-block;flex:none}
      .ed-sprite{position:absolute;left:50%;top:50%;background-repeat:no-repeat;image-rendering:pixelated}
      @media (prefers-reduced-motion:reduce){.ed-dots span{animation:none}}
    `;
    document.head.appendChild(style);
    dialog = h('dialog', {id: 'kitchen-editor-dialog', class: 'panel card-page editor-page', 'aria-labelledby': 'editor-title'});
    dialog.addEventListener('close', () => {view = {screen: 'list'};});
    document.body.appendChild(dialog);
    window.addEventListener('pointerup', endStroke);
    window.addEventListener('kitchen-language-changed', () => {if (dialog.open) render();});
    return dialog;
  }
  // Where ← 返回 leads: the all-levels list, or the start card when ▶ opened this from there.
  let back = 'levels';
  async function open(e) {
    back = e?.detail?.from === 'card' ? 'card' : 'levels';
    if (!await loadCatalog()) return;
    ensureDialog();
    view = {screen: 'list'};
    render();
    if (!dialog.open) dialog.showModal();
  }
  function render() {
    const keep = document.activeElement?.dataset?.focus;
    dialog.replaceChildren(h('div', {class: 'card-awning', 'aria-hidden': 'true'}));
    if (view.screen === 'list') renderList();
    else {
      const rec = view.rec;
      const steps = h('nav', {class: 'ed-steps', 'aria-label': '编辑步骤'},
        [[1, '1 厨房布局'], [2, '2 菜单'], [3, '3 校准与试玩']].map(([n, label]) =>
          h('button', {class: 'ed-step', type: 'button', 'aria-current': view.step === n ? 'step' : false, onclick: () => {view.step = n; render();}}, label)));
      const name = h('input', {class: 'ed-input', id: 'editor-level-name', 'data-focus': 'level-name', 'data-no-i18n': true, type: 'text',
        maxlength: String(catalog.name_length), value: rec.design.name, 'aria-label': '关卡名字', style: 'width:220px',
        oninput: e => {rec.design.name = e.target.value; saveLevel(rec);}});
      dialog.append(h('div', {class: 'dlg-head'}, button('← 我的关卡', () => {view = {screen: 'list'}; render();}), h('h2', {id: 'editor-title', style: 'position:absolute;left:-9999px'}, '编辑关卡'), name, steps));
      const body = h('div', {class: 'ed-body'});
      dialog.append(body);
      if (view.step === 1) renderLayout(body, rec);
      else if (view.step === 2) renderMenu(body, rec);
      else renderCalibrate(body, rec);
    }
    if (keep) dialog.querySelector(`[data-focus="${keep}"]`)?.focus();
  }

  // ---- My levels.
  function status(rec) {
    const issues = problems(rec.design), job = session[rec.id], result = rec.result;
    if (job && ['queued', 'running'].includes(job.state)) return {badge: '校准中', cls: 'busy',
      line: job.state === 'queued' && job.position ? fmt('排在第 {0} 位', job.position) : '脚本厨师正在试做', note: '算完会自动更新，可以先去玩别的关卡'};
    if (issues.length) return {badge: '草稿', cls: '', line: issues.slice(0, 2).map(i => i.text).join('；'), note: '补齐以后才能提交校准', edit: '继续编辑'};
    if (!result || result.json !== signature(rec.design)) return {badge: '待校准', cls: '', line: '设计好了，还没交给服务器计算', note: '在第 3 步提交校准', edit: '继续编辑'};
    if (result.state === 'done' && result.report?.playable) return {badge: '可以玩', cls: 'ok', target: result.report.target,
      note: result.report.solo_reaches_target ? '提示：一个人也能过' : '需要两个人配合，一个人过不了', play: true};
    if (result.state === 'done') return {badge: '不能玩', cls: 'bad', line: '两个脚本厨师一道菜都没做出来', note: '常见原因：案板或灶台被围住，人站不到跟前', edit: '回去修改'};
    return {badge: '不能玩', cls: 'bad', line: '服务器的检查没通过', note: '打开第 3 步看具体原因', edit: '回去修改'};
  }
  function renderList() {
    const list = readLevels(), picker = h('input', {type: 'file', accept: '.json,application/json', hidden: true, onchange: e => importFile(e.target.files[0])});
    dialog.append(h('div', {class: 'dlg-head'}, button('← 返回', () => {dialog.close(); if (back === 'levels') window.dispatchEvent(new Event('kitchen-open-levels'));}),
      h('h2', {id: 'editor-title'}, '我的关卡'),
      h('div', {class: 'ed-row', style: 'margin-left:auto'}, picker, button('导入关卡文件', () => picker.click()),
        touch() ? null : button('+ 新建关卡', () => createLevel(), 'btn primary'))));
    const body = h('div', {class: 'ed-body'});
    add(body, h('p', {class: 'ed-hint'}, '自己摆厨房、配菜，服务器算出订单节奏和目标以后就能开局。关卡只保存在这个浏览器里，换电脑或发给朋友，先导出成文件。'));
    if (storageFailed) add(body, h('p', {class: 'ed-hint', style: 'color:' + RED}, '这个浏览器不让网页保存数据，关卡关掉页面就没了。请先导出成文件。'));
    if (view.message) add(body, h('p', {class: 'ed-hint', style: 'color:' + (view.message.error ? RED : INK)}, view.message.text));
    const cards = h('div', {class: 'ed-cards'});
    list.forEach(rec => {
      const st = status(rec), card = h('div', {class: 'ed-card'});
      add(card, h('div', {class: 'ed-card-name', user: rec.design.name || '未命名'}));
      add(card, h('div', {class: 'ed-hint', user: dishNames(rec.design) || '—'}));
      add(card, h('div', {class: 'ed-row'}, h('span', {class: 'ed-badge ' + st.cls}, st.badge),
        st.target != null ? h('span', {style: 'font-weight:650'}, fmt('目标 ¥{0}', st.target)) : null,
        st.line ? h('span', {class: 'ed-hint', style: 'color:' + INK}, st.line) : null));
      if (st.note) add(card, h('div', {class: 'ed-hint'}, st.note));
      const actions = h('div', {class: 'ed-row', style: 'margin-top:auto'});
      if (st.play) add(actions, button('开始经营', () => play(rec, actions), 'btn primary'));
      if (!touch()) add(actions, button(st.edit || '编辑', () => {view = {screen: 'edit', rec, step: st.play ? 3 : 1}; render();}));
      add(actions, button('导出', () => exportLevel(rec), 'ed-quiet'));
      if (view.confirm === rec.id) add(actions, h('span', {class: 'ed-hint', style: 'color:' + RED}, '确定删除？'),
        button('删除', () => {writeLevels(readLevels().filter(r => r.id !== rec.id)); view.confirm = null; render();}, 'btn danger'),
        button('取消', () => {view.confirm = null; render();}, 'ed-quiet'));
      else add(actions, button('删除', () => {view.confirm = rec.id; render();}, 'ed-quiet'));
      add(card, actions);
      add(cards, card);
    });
    if (!touch()) add(cards, h('button', {class: 'ed-new', type: 'button', onclick: () => createLevel()},
      h('span', {style: 'font:36px/40px var(--pixel)', 'aria-hidden': 'true'}, '+'), h('span', {style: 'font:22px/26px var(--pixel)'}, '新建关卡'),
      h('span', {class: 'ed-hint'}, '从一间摆好基本设备的示例厨房开始')));
    add(body, cards);
    add(body, h('p', {class: 'ed-hint'}, touch() ? '手机上可以玩已经做好的关卡；编辑关卡请用电脑浏览器。' : '编辑器只在电脑浏览器里打开；手机上可以玩已经做好的关卡。'));
    dialog.append(body);
  }
  function createLevel() {
    const rec = {id: newId(), design: starter()};
    saveLevel(rec);
    view = {screen: 'edit', rec, step: 1};
    render();
  }
  function exportLevel(rec) {
    const blob = new Blob([JSON.stringify(clean(rec.design), null, 2)], {type: 'application/json'});
    const a = h('a', {href: URL.createObjectURL(blob), download: (rec.design.name || 'level').replace(/[\\/:*?"<>|]/g, '_') + '.chefjeff-level.json'});
    document.add(body, a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  async function importFile(file) {
    if (!file) return;
    let design = null;
    try {design = JSON.parse(await file.text());} catch (_) {}
    if (design && design.design) design = design.design;
    const ok = design && design.format === catalog.format && Array.isArray(design.size) && Array.isArray(design.stations) && Array.isArray(design.dishes);
    if (!ok) {view.message = {text: '这个文件不是关卡文件，没有导入。', error: true}; render(); return;}
    design.walls = Array.isArray(design.walls) ? design.walls : [];
    design.dishes = design.dishes.map(d => ({name: String(d.name || ''), price: Number(d.price) || catalog.price.min, items: Array.isArray(d.items) ? d.items.filter(itemOf) : []}));
    saveLevel({id: newId(), design});
    view.message = {text: '导入好了。'};
    render();
  }

  // ---- Step 1: the kitchen layout.
  let stroke = null;
  function endStroke() {stroke = null;}
  function renderLayout(body, rec) {
    const design = rec.design;
    const tools = ['wall', 'counter', 'board', ...catalog.vessels.map(v => 'stove:' + v), 'source', 'serving_window', 'sink', 'plate_return', 'bin', 'tool_rack'];
    view.tool = view.tool || 'counter';
    view.item = view.item && itemOf(view.item) ? view.item : catalog.items[0].id;
    const toolOf = () => view.tool === 'source' ? 'source:' + view.item : view.tool;
    const side = h('div', {class: 'ed-side', style: 'width:180px'});
    add(side, h('span', {class: 'ed-label'}, '工具'));
    tools.forEach(t => {
      const look = toolLook(t === 'source' ? 'source:' + view.item : t);
      add(side, h('button', {class: 'ed-tool', type: 'button', 'aria-pressed': String(view.tool === t), onclick: () => {view.tool = t; render();}},
        h('span', {class: 'ed-swatch', 'data-no-i18n': true, style: `background:${look.bg};color:${look.fg};border:1px solid ${look.line}`}, t === 'wall' ? '' : look.glyph),
        h('span', {}, t === 'source' ? TOOLS.ingredient_source.name : look.name)));
      if (t === 'source' && view.tool === 'source') {
        add(side, h('select', {class: 'ed-select', 'aria-label': '食材箱里放什么', onchange: e => {view.item = e.target.value; render();}},
          catalog.items.map(it => h('option', {value: it.id, selected: it.id === view.item}, it.name))));
      }
    });
    add(side, h('button', {class: 'ed-tool', type: 'button', 'aria-pressed': String(view.tool === 'erase'), onclick: () => {view.tool = 'erase'; render();}},
      h('span', {class: 'ed-swatch', style: 'border:1px dashed #6e4e38;background:#f0d9b5'}), h('span', {}, '擦除')));

    const sizes = h('div', {class: 'ed-row'}, h('span', {class: 'ed-label', style: 'color:' + MUTED}, '房间大小'),
      catalog.sizes.map(([w, hgt], i) => button(fmt(['小 {0}×{1}', '中 {0}×{1}', '大 {0}×{1}'][i] || '{0}×{1}', w, hgt), () => {design.size = [w, hgt]; saveLevel(rec); render();},
        'btn', {'aria-pressed': String(design.size[0] === w && design.size[1] === hgt), style: design.size[0] === w && design.size[1] === hgt ? 'background:var(--honey);box-shadow:none;transform:translateY(2px)' : ''})));
    const board = h('div', {class: 'ed-board'}, sizes,
      h('p', {class: 'ed-hint'}, '按住拖动能连续摆；在同种设备上再点一下就擦掉；选「擦除」能拖着成片擦。外圈是墙，不能放东西；出餐口和脏盘回收只能贴着外墙摆。里面也可以画墙。'));
    const stage = h('div', {class: 'ed-stage'}), grid = h('div', {class: 'ed-grid', role: 'grid', 'aria-label': '厨房格子'});
    stage.append(grid); board.append(stage);
    const right = h('div', {class: 'ed-side', style: 'width:250px'});
    add(body, h('div', {class: 'ed-main'}, side, board, right));
    add(body, h('div', {class: 'ed-foot'}, h('span'), button('下一步：菜单 →', () => {view.step = 2; render();}, 'btn primary')));

    const cell = 34;
    const same = s => !!s && toolKey(s) === (view.tool === 'source' ? 'source:' + view.item : view.tool);
    // Walls are kept apart from stations, so a wall clicked with the wall tool is matched there.
    const sameAt = (g, key) => view.tool === 'wall' ? g.walls.has(key) : same(g.stations[key]);
    const strokeAt = (x, y, g) => view.tool === 'erase' ? {erase: true, any: true} : sameAt(g, x + ',' + y) ? {erase: true} : {};
    function apply(x, y, how) {
      const g = geometry(design), key = x + ',' + y, tool = toolOf();
      const wallHere = g.walls.has(key), here = g.stations[key];
      if (how.erase) {
        if (!how.any && !sameAt(g, key)) return;
        if (!wallHere && !here) return;
        design.walls = design.walls.filter(([wx, wy]) => wx + ',' + wy !== key);
        design.stations = design.stations.filter(s => s.x + ',' + s.y !== key);
      } else {
        if (!g.inside(x, y)) return;
        // Serving windows and the plate return stand only against the outer wall.
        if (catalog.against_the_wall.includes(tool) && !g.againstWall(x, y)) return;
        design.walls = design.walls.filter(([wx, wy]) => wx + ',' + wy !== key);
        design.stations = design.stations.filter(s => s.x + ',' + s.y !== key);
        if (tool === 'wall') design.walls.push([x, y]); else design.stations.push(toolStation(tool, x, y));
      }
      saveLevel(rec);
      paint();
    }
    function warnInside(x, y, how) {
      const g = geometry(design);
      if (how.erase || !catalog.against_the_wall.includes(view.tool) || !g.inside(x, y) || g.againstWall(x, y)) return;
      const n = (view.notice?.n || 0) + 1;
      view.notice = {n, x, y, text: fmt('{0}只能贴着外墙摆，点有橙色边框的格子', TOOLS[view.tool].name)};
      paint();
      setTimeout(() => {if (view.notice?.n === n) {view.notice = null; paint();}}, 2600);
    }
    // One stroke per press. Every change redraws the cells, which would drop the pressed one and with it the
    // release, so the grid itself holds the pointer for the stroke; a move without the button held also ends it.
    let lastCell = '';
    grid.addEventListener('pointerdown', e => {
      const b = e.target.closest('[data-x]');
      if (!b || e.button) return;
      e.preventDefault();
      try {grid.setPointerCapture(e.pointerId);} catch (_) {}
      const x = +b.dataset.x, y = +b.dataset.y;
      stroke = strokeAt(x, y, geometry(design)); lastCell = x + ',' + y;
      apply(x, y, stroke); warnInside(x, y, stroke);
      grid.querySelector(`[data-x="${x}"][data-y="${y}"]`)?.focus({preventScroll: true});
    });
    grid.addEventListener('pointermove', e => {
      if (!stroke) return;
      if (!(e.buttons & 1)) {endStroke(); return;}
      const b = document.elementFromPoint(e.clientX, e.clientY)?.closest?.('.ed-grid [data-x]');
      if (!b || !grid.contains(b) || b.dataset.x + ',' + b.dataset.y === lastCell) return;
      lastCell = b.dataset.x + ',' + b.dataset.y;
      apply(+b.dataset.x, +b.dataset.y, stroke);
    });
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) grid.addEventListener(type, endStroke);
    grid.addEventListener('click', e => {
      const b = e.target.closest('[data-x]');
      if (!b || e.detail !== 0) return;  // Enter or Space on a focused cell
      const x = +b.dataset.x, y = +b.dataset.y, how = strokeAt(x, y, geometry(design));
      apply(x, y, how); warnInside(x, y, how);
    });
    function paint() {
      const g = geometry(design), focus = document.activeElement?.dataset?.x != null ? document.activeElement.dataset.x + ',' + document.activeElement.dataset.y : null;
      grid.style.gridTemplateColumns = `repeat(${g.W}, ${cell}px)`;
      const kids = [];
      for (let y = 0; y < g.H; y++) for (let x = 0; x < g.W; x++) {
        const key = x + ',' + y, s = g.stations[key], base = `width:${cell}px;height:${cell}px;`;
        if (!g.inside(x, y)) {kids.push(h('span', {class: 'ed-cell fixed', 'aria-hidden': 'true', style: base + 'background:#6b3418;border:1px solid #3f2112'})); continue;}
        let style, label = '', aria;
        if (s) {
          const look = toolLook(toolKey(s)), stuck = !g.standable(x, y);
          const wrong = catalog.against_the_wall.includes(s.type) && !g.againstWall(x, y);
          style = `${base}background:${look.bg};color:${look.fg};border:2px ${stuck || wrong ? 'dashed ' + RED : 'solid ' + look.line}`;
          label = look.glyph; aria = look.name + (stuck ? '，跟前没有地方站' : '');
        } else if (g.walls.has(key)) {
          style = `${base}background:#6b3418;border:1px solid #3f2112`;
          aria = TOOLS.wall.name;
        } else {
          // Outlined while a serving window or plate return is in hand: the floor along the outer wall.
          const tint = FLOOR[Math.min(g.part[key] || 0, FLOOR.length - 1)], offer = g.againstWall(x, y) && catalog.against_the_wall.includes(view.tool);
          style = `${base}background:${tint[(x + y) % 2]}${offer ? ';box-shadow:inset 0 0 0 2px #e8983a' : ''}`;
          aria = '地板';
        }
        kids.push(h('button', {class: 'ed-cell', type: 'button', 'data-x': x, 'data-y': y, 'data-no-i18n': true, 'aria-label': tr(aria) + ' ' + key, style}, label));
      }
      if (view.notice) {
        const n = view.notice, below = n.y <= 2, left = Math.max(150, Math.min(g.W * cell - 150, n.x * cell + cell / 2));
        kids.push(h('div', {class: 'ed-notice', 'aria-live': 'polite',
          style: `left:${left}px;top:${below ? (n.y + 1) * cell + 6 : n.y * cell - 6}px;transform:translate(-50%,${below ? '0' : '-100%'})`}, n.text));
      }
      grid.replaceChildren(...kids);
      if (focus) grid.querySelector(`[data-x="${focus.split(',')[0]}"][data-y="${focus.split(',')[1]}"]`)?.focus({preventScroll: true});
      const checks = layoutChecks(design), errors = checks.filter(c => c.error).length;
      right.replaceChildren(h('div', {class: 'ed-checks'}, h('div', {class: 'ed-row', style: 'justify-content:space-between'},
        h('span', {class: 'ed-label'}, '检查'), h('span', {style: `font-weight:650;color:${errors ? RED : INK}`}, errors ? fmt('还有 {0} 处要改', errors) : '可以进入下一步')),
        errors ? null : h('div', {}, '设备齐了，每台设备跟前都能站人'),
        checks.map(c => h('div', {class: c.error ? 'err' : ''}, c.text))));
    }
    paint();
  }

  // ---- Step 2: the menu.
  function renderMenu(body, rec) {
    const design = rec.design, max = catalog.max_dishes, p = catalog.price;
    view.dish = Math.min(view.dish || 0, design.dishes.length - 1);
    const i = Math.max(0, view.dish), cur = design.dishes[i];
    const change = (fn, again = true) => {fn(); saveLevel(rec); if (again) render();};
    const list = h('div', {class: 'ed-side', style: 'width:200px'}, h('span', {class: 'ed-label', style: 'font-size:20px;line-height:24px'}, '菜单'),
      design.dishes.map((d, j) => h('button', {class: 'ed-dish', type: 'button', 'aria-pressed': String(j === i), onclick: () => {view.dish = j; render();},
          style: 'flex-direction:row;align-items:center;gap:8px'}, dishPicture(d.items, 36),
        h('span', {style: 'display:flex;flex-direction:column;gap:2px;min-width:0'},
          h('span', {user: (d.name || '').trim() || '未命名', style: 'font:12px/16px var(--pixel)'}),
          h('span', {class: 'ed-hint'}, fmt('¥{0} · {1} 样配料', d.price, d.items.length))))),
      button('+ 加一道菜', () => change(() => {
        const can = ready(design), free = can.find(it => !design.dishes.some(d => d.items.length === 1 && d.items[0] === it.id)) || can[0];
        design.dishes.push({name: '新菜', price: suggestedPrice([free.id]), items: [free.id]}); view.dish = design.dishes.length - 1;
      }), 'btn', {disabled: design.dishes.length >= max || !ready(design).length}),
      h('p', {class: 'ed-hint'}, fmt('最多 {0} 道菜。每 {1} 秒来一单，菜单上的菜轮流出现。', max, catalog.interval_game_ms / 1000)));
    const panel = h('div', {class: 'ed-panel'});
    if (cur) {
      add(panel, h('div', {class: 'ed-row', style: 'flex-wrap:nowrap'}, dishPicture(cur.items, 56), h('label', {class: 'ed-label', for: 'editor-dish-name', style: 'color:' + MUTED}, '菜名'),
        h('input', {class: 'ed-input', id: 'editor-dish-name', 'data-focus': 'dish-name', 'data-no-i18n': true, type: 'text', maxlength: String(catalog.dish_name_length), value: cur.name, style: 'flex:1',
          oninput: e => change(() => {cur.name = e.target.value;}, false), onchange: () => render()}),
        button('删掉这道菜', () => change(() => {design.dishes.splice(i, 1); view.dish = Math.max(0, i - 1);}), 'btn', {disabled: design.dishes.length === 1})));
      add(panel, h('p', {class: 'ed-hint'}, fmt('菜名只显示给人看，最多 {0} 个字。', catalog.dish_name_length)));
      add(panel, h('span', {class: 'ed-label'}, fmt('配料（最多 {0} 样，做法由食材决定）', catalog.max_items)),
        h('p', {class: 'ed-hint'}, '这里只能选厨房里做得出来的食材。一样食材要有它的食材箱，要切的还得有案板，要下锅的还得有对应的灶台。想用别的食材，先回第 1 步把这些摆上。'));
      cur.items.forEach((id, n) => {
        const it = itemOf(id);
        add(panel, h('div', {class: 'ed-row', style: 'flex-wrap:nowrap'}, h('span', {class: 'ed-hint', style: 'width:52px'}, fmt('第 {0} 样', n + 1)),
          h('select', {class: 'ed-select', 'aria-label': fmt('第 {0} 样配料', n + 1), onchange: e => change(() => {cur.items[n] = e.target.value;})},
            ingredientOptions(design, cur, id)),
          it && lacks(it, design).length ? h('span', {style: 'flex:1;font-size:13px;line-height:20px;color:' + RED}, fmt('厨房里还缺{0}', lacks(it, design)[0]))
            : h('span', {style: 'flex:1;font-size:13px;line-height:20px'}, it ? method(it) : ''),
          button('×', () => change(() => {cur.items.splice(n, 1);}), 'btn', {'aria-label': '去掉这样配料', disabled: cur.items.length === 1, style: 'min-width:34px'})));
      });
      const more = ready(design).find(o => !cur.items.includes(o.id));
      add(panel, button('+ 加一样配料', () => change(() => {cur.items.push(more.id);}), 'btn',
        {disabled: !more || cur.items.length >= catalog.max_items, style: 'align-self:flex-start'}));
      const suggested = suggestedPrice(cur.items);
      add(panel, h('div', {class: 'ed-row'}, h('span', {class: 'ed-label', style: 'color:' + MUTED}, '售价'),
        button('-', () => change(() => {cur.price = Math.max(p.min, cur.price - p.step);}), 'btn', {'aria-label': fmt('便宜 {0} 元', p.step), disabled: cur.price <= p.min}),
        h('span', {style: 'font:22px/1 var(--pixel);min-width:64px;text-align:center'}, '¥' + cur.price),
        button('+', () => change(() => {cur.price = Math.min(p.max, cur.price + p.step);}), 'btn', {'aria-label': fmt('贵 {0} 元', p.step), disabled: cur.price >= p.max}),
        h('span', {class: 'ed-hint'}, fmt('按做法算的建议价 ¥{0}', suggested)), button('用建议价', () => change(() => {cur.price = suggested;}), 'btn')));
      add(panel, h('p', {class: 'ed-hint'}, fmt('{0} 到 {1} 元，每档 {2} 元。建议价 = {3} + 每样配料 {4} + 每样要下锅的再加 {5}。', p.min, p.max, p.step, p.base, p.per_item, p.per_cooked)));
      menuChecks(design).forEach(c => add(panel, h('div', {class: 'ed-hint', style: 'color:' + RED}, c.text)));
    }
    const work = cur ? cur.items.map(itemOf).filter(Boolean).reduce((s, it) => s + workMs(it), 0) : 0;
    const right = h('div', {class: 'ed-side', style: 'width:270px'},
      h('div', {class: 'ed-box', style: 'background:var(--paper);border-color:var(--ink)'}, h('b', {}, 'Jeff 看到的名字'),
        h('span', {'data-no-i18n': true, style: 'font-family:ui-monospace,Menlo,Consolas,monospace;overflow-wrap:anywhere'}, cur ? cur.items.map(itemOf).filter(Boolean).map(it => it.english).join(' + ') : ''),
        h('span', {style: 'color:' + MUTED}, 'Jeff 读不到你起的菜名，只看到英文配料。')),
      h('div', {class: 'ed-box'}, h('b', {}, '顾客能等多久'),
        h('span', {style: 'font-size:15px;line-height:24px'}, fmt('切和煮一共 {0} 秒 → 最多等 {1} 秒', work / 1000, patienceMs(work) / 1000)),
        h('span', {style: 'color:' + MUTED}, fmt('按工时的 {0} 倍算，在 {1} 到 {2} 秒之间。', catalog.patience.factor, catalog.patience.min_game_ms / 1000, catalog.patience.max_game_ms / 1000))),
      h('div', {class: 'ed-box'}, h('b', {}, '这份菜单要的设备'), needsList(design)));
    add(body, h('div', {class: 'ed-main'}, list, panel, right));
    add(body, h('div', {class: 'ed-foot'}, button('← 厨房布局', () => {view.step = 1; render();}), button('下一步：校准 →', () => {view.step = 3; render();}, 'btn primary')));
  }
  function needsList(design) {
    const g = geometry(design), count = {}, sources = {};
    Object.values(g.stations).forEach(s => {count[s.type] = (count[s.type] || 0) + 1; if (s.type === 'stove') count['stove:' + s.vessel] = 1; if (s.type === 'ingredient_source') sources[s.item] = true;});
    let missing = false;
    const rows = needs(design).map(n => {
      const ok = n.placed(count, sources); missing = missing || !ok;
      return h('span', {style: 'color:' + (ok ? INK : RED)}, fmt(ok ? '已摆：{0}' : '还缺：{0}', n.name));
    });
    if (missing) rows.push(h('span', {style: 'color:' + MUTED}, '回第 1 步把缺的摆上'));
    const used = new Set(design.dishes.flatMap(d => d.items));
    Object.keys(sources).filter(id => !used.has(id)).map(itemOf).filter(Boolean).forEach(it =>
      rows.push(h('span', {style: 'color:' + MUTED}, fmt('菜单没用上：{0}', fmt('{0}食材箱', it.name)))));
    return rows;
  }

  // ---- Step 3: calibrate on the server, then play.
  function renderCalibrate(body, rec) {
    const design = rec.design, issues = problems(design), job = session[rec.id], result = rec.result;
    const fresh = result && result.json === signature(design);
    const sizeIndex = catalog.sizes.findIndex(([w, hgt]) => w === design.size[0] && hgt === design.size[1]);
    const worst = Math.max(0, ...design.dishes.map(d => patienceMs(d.items.map(itemOf).filter(Boolean).reduce((s, it) => s + workMs(it), 0))));
    const facts = [
      ['厨房', fmt(['小 {0}×{1}', '中 {0}×{1}', '大 {0}×{1}'][sizeIndex] || '{0}×{1}', design.size[0], design.size[1]) + ' · ' + fmt('{0} 台设备', design.stations.length)],
      ['订单', fmt('每 {0} 秒一单，菜单上的菜轮流出现', catalog.interval_game_ms / 1000)],
      ['顾客', fmt('每道菜最多等 {0} 秒', worst / 1000)],
      ['盘子', fmt('开局 {0} 个，用过要洗了再用', catalog.plates)],
      ['一局', fmt('{0} 分钟，关店时看净收入', catalog.round_game_ms / 60000)]];
    const left = h('div', {class: 'ed-side', style: 'width:330px'}, h('span', {class: 'ed-label', style: 'font-size:20px;line-height:24px'}, '要交给服务器的关卡'),
      h('div', {class: 'ed-box', style: 'font-size:15px;line-height:24px'},
        h('span', {}, h('b', {style: 'font:inherit;font-weight:650'}, '菜单'), ' ', h('span', {user: design.dishes.map(d => `${(d.name || '').trim()} ¥${d.price}`).join(' · ')})),
        facts.map(([k, v]) => h('span', {}, h('b', {style: 'font:inherit;font-weight:650'}, k), ' ', v))),
      h('p', {class: 'ed-hint'}, fmt('规则、走路速度和切煮时间都和官方关卡一样，不能改。服务器让两个脚本厨师照这张关卡试做 {0} 局，取收入中位数的一半作为目标。', catalog.seeds)),
      button(fresh && result.state === 'done' ? '重新校准' : '提交校准', () => calibrate(rec), 'btn primary ed-big', {disabled: !!issues.length || (job && ['queued', 'running'].includes(job.state))}),
      h('p', {class: 'ed-hint'}, '同一份设计算过一次就记住了，再交会立刻出结果。'));
    const box = h('div', {class: 'ed-result'});
    if (issues.length) {
      add(box, h('span', {class: 'ed-badge'}, '草稿'), h('div', {class: 'ed-big-title'}, fmt('还有 {0} 处要改', issues.length)),
        h('ul', {style: 'margin:0;padding-left:20px;font-size:15px;line-height:24px'}, issues.map(i => h('li', {}, i.text))),
        h('div', {class: 'ed-row', style: 'margin-top:auto'}, button('回厨房布局', () => {view.step = 1; render();}, 'btn ed-big'), button('回菜单', () => {view.step = 2; render();}, 'btn ed-big')));
    } else if (job && job.state === 'queued') {
      add(box, h('span', {class: 'ed-badge busy'}, '排队中'), h('div', {class: 'ed-big-title'}, fmt('排在第 {0} 位', job.position || 1)),
        h('p', {class: 'ed-hint', style: 'font-size:15px;line-height:24px;color:' + INK}, '服务器一次只算一张关卡，前面的算完就轮到这张。'),
        h('p', {class: 'ed-hint'}, '每个页面同时只能排一张；排队的关卡多了，会请你稍后再交。'));
    } else if (job && job.state === 'running') {
      add(box, h('span', {class: 'ed-badge busy'}, '计算中'), h('div', {class: 'ed-big-title'}, '脚本厨师正在试做'),
        h('div', {class: 'ed-dots', 'aria-hidden': 'true'}, h('span'), h('span'), h('span')),
        h('p', {class: 'ed-hint', style: 'font-size:15px;line-height:24px;color:' + INK}, fmt('一共试做 {0} 局，大约 1 分钟。服务器只告诉我们“在算”和“算完了”，所以这里不画进度条。', catalog.seeds)),
        h('p', {class: 'ed-hint'}, '算的时候可以离开这一页，回到「我的关卡」也能看到进度。'));
    } else if (job && job.error) {
      add(box, h('span', {class: 'ed-badge bad'}, '没交上去'), h('div', {class: 'ed-big-title'}, '服务器没收下这张关卡'),
        h('p', {class: 'ed-hint', style: 'font-size:15px;line-height:24px;color:' + INK}, job.error));
    } else if (fresh && result.state === 'done' && result.report?.playable) {
      const r = result.report;
      add(box, h('div', {class: 'ed-row'}, h('span', {class: 'ed-badge ok'}, '可以玩'), r.solo_reaches_target ? h('span', {class: 'ed-badge note'}, '提示：一个人也能过') : null),
        h('div', {class: 'ed-row', style: 'align-items:baseline'}, h('span', {style: 'font:22px/1 var(--pixel)'}, '目标'),
          h('span', {style: 'font:48px/52px var(--pixel)'}, '¥' + r.target), h('span', {class: 'ed-hint'}, '关店时净收入达到就算过关')),
        h('div', {style: 'display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px'},
          h('div', {class: 'ed-box'}, h('b', {}, '两个脚本厨师'), h('span', {style: 'font-size:15px;line-height:24px'}, fmt('{0} 局收入中位数 ¥{1}，目标取一半', catalog.seeds, r.pair_median))),
          h('div', {class: 'ed-box'}, h('b', {}, '一个脚本厨师'), h('span', {style: 'font-size:15px;line-height:24px'}, fmt('中位数 ¥{0} · {1}', r.solo_median, r.solo_reaches_target ? '能达到目标' : '达不到目标')))),
        r.solo_reaches_target ? h('p', {class: 'ed-hint', style: 'color:' + INK}, '一个人也能达到目标，照样可以玩。想让两个人非得配合，可以少放一块案板，或把食材箱和灶台拉远一些，再交一次。') : null,
        h('p', {class: 'ed-hint'}, '脚本厨师只是用来定目标的参照，不代表真人和 Jeff 能打多少分。'),
        view.playError ? h('p', {class: 'ed-hint', style: 'color:' + RED}, view.playError) : null);
      const go = h('div', {class: 'ed-row', style: 'margin-top:auto'});
      add(go, button('开始经营', () => play(rec, go), 'btn primary ed-big'), button('回去修改', () => {view.step = 1; render();}, 'btn ed-big'));
      add(box, go);
    } else if (fresh && result.state === 'done') {
      add(box, h('span', {class: 'ed-badge bad'}, '不能玩'), h('div', {class: 'ed-big-title'}, '这张关卡还玩不了'),
        h('ul', {style: 'margin:0;padding-left:20px;font-size:15px;line-height:24px'},
          h('li', {}, fmt('两个脚本厨师 {0} 局一道菜都没做出来。', catalog.seeds)),
          h('li', {}, '最常见的原因：案板或灶台被柜台围住，人站不到跟前；或者出餐口离厨房太远。'),
          h('li', {}, '第 1 步的检查会标出“跟前没有地方站”的设备。')),
        h('div', {class: 'ed-row', style: 'margin-top:auto'}, button('回去修改', () => {view.step = 1; render();}, 'btn primary ed-big')));
    } else if (fresh && result.state === 'refused') {
      add(box, h('span', {class: 'ed-badge bad'}, '不能玩'), h('div', {class: 'ed-big-title'}, '服务器的检查没通过'),
        h('ul', {style: 'margin:0;padding-left:20px;font-size:15px;line-height:24px'}, (result.diagnostics || []).map(d => h('li', {}, explain(d)))),
        h('div', {class: 'ed-row', style: 'margin-top:auto'}, button('回去修改', () => {view.step = 1; render();}, 'btn primary ed-big')));
    } else {
      add(box, h('div', {class: 'ed-big-title'}, '还没校准'),
        h('p', {class: 'ed-hint', style: 'font-size:15px;line-height:24px;color:' + INK}, '交上去以后，服务器先当场检查一遍：价格对不对、菜在这张地图上做不做得出来。检查通过才会排队计算。'),
        h('p', {class: 'ed-hint', style: 'font-size:15px;line-height:24px;color:' + INK}, '算的时候可以离开这一页，回到「我的关卡」也能看到进度。'));
    }
    add(body, h('div', {class: 'ed-main'}, left, box));
  }
  // The server's diagnostics, in words for a player where the code is known; the raw message otherwise.
  const CODES = {
    WALLS_SPLIT_KITCHEN: '墙把厨房隔开了，两边没法传递东西',
    STATION_UNREACHABLE: '有设备跟前没有地方站',
    STATION_NOT_AGAINST_WALL: '出餐口和脏盘回收要贴着外墙摆',
    UNSUPPORTED_EQUIPMENT_COUNT: '水槽、脏盘回收、灭火器架要各有 1 个，出餐口 1 到 2 个',
    INVENTORY_NO_FREE_STATION: '柜台不够放开局的盘子',
    FLOOR_PARTS_OUT_OF_REACH: '柜台隔开的两块地板离得太远，东西扔不过去',
    PRICE_OUT_OF_RANGE: '有菜的价格超出了范围',
    DISHES_ALIKE: '有两道菜的配料一样',
    MAP_INVALID: '地图不成立'
  };
  function explain(d) {
    const words = CODES[d.code];
    return h('span', {}, words || '服务器的检查没通过', ' ', h('span', {class: 'ed-hint', 'data-no-i18n': true}, `(${d.code}: ${d.message})`));
  }

  async function calibrate(rec) {
    const design = clean(rec.design), json = signature(rec.design);
    session[rec.id] = {state: 'queued', position: 1};
    view.playError = null;
    render();
    const {status, data} = await api('/api/player-level/submit', {design});
    if (status === 400 && data.state === 'refused') {
      delete session[rec.id];
      rec.result = {json, state: 'refused', diagnostics: data.diagnostics || []};
      saveLevel(rec); render(); return;
    }
    if (status !== 200 && status !== 202) {session[rec.id] = {error: data.error || '服务器暂时不能校准，请稍后再试。'}; render(); return;}
    track(rec, json, data);
  }
  function track(rec, json, data) {
    if (data.state === 'done') {
      delete session[rec.id];
      rec.result = {json, state: 'done', report: data.report, content_id: data.content_id};
      rec.job = data.job;
      saveLevel(rec);
      if (dialog?.open) render();
      return;
    }
    if (data.state === 'failed') {session[rec.id] = {error: data.error || '计算出错了，请再交一次。'}; if (dialog?.open) render(); return;}
    session[rec.id] = {job: data.job, state: data.state, position: data.position};
    if (dialog?.open) render();
    setTimeout(async () => {
      const {status, data: next} = await api('/api/player-level/status?job=' + encodeURIComponent(data.job));
      if (status === 200) track(rec, json, next);
      else {session[rec.id] = {error: next.error || '和服务器的连接断了，请再交一次。'}; if (dialog?.open) render();}
    }, 1500);
  }
  async function play(rec, row) {
    // A problem shows where the player pressed: on the list, or in step 3.
    const fail = text => {
      if (view.screen === 'list') view.message = {text, error: true}; else view.playError = text;
      render();
    };
    const s = controls()?.getState();
    if (!s?.game_id) return fail('厨房还没连上，请稍等再试。');
    if (!['ready', 'ended'].includes(s.phase)) return fail('这一局结束以后才能换关卡。');
    row.querySelectorAll('button').forEach(b => {b.disabled = true;});
    // The server remembers a calibrated design, so asking again returns its result at once (and a job of this page).
    const {status, data} = await api('/api/player-level/submit', {design: clean(rec.design)});
    if (status !== 200 || data.state !== 'done' || !data.report?.playable) return fail(data.error || '这张关卡要重新校准，请到第 3 步再交一次。');
    const reply = await api('/api/player-level/play', {job: data.job, game_id: s.game_id, request_id: 'editor-' + newId()});
    if (reply.status !== 200) return fail(reply.data.error || '没能换到这张关卡。');
    dialog.close();
  }

  async function edit(e) {
    await open();
    if (!dialog?.open) return;
    const rec = readLevels().find(r => r.result?.content_id && r.result.content_id === e?.detail?.id);
    if (rec) {view = {screen: 'edit', rec, step: 1}; render();}
  }
  window.chefjeffEditor = {available: () => !!catalog, open};
  window.addEventListener('kitchen-open-editor', open);
  window.addEventListener('kitchen-edit-level', edit);
  loadCatalog();
})();
