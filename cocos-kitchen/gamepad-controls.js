/* Standard desktop gamepads share the client's action bridge. No keyboard
 * events or network requests are synthesized here. */
(() => {
  'use strict';
  const DEADZONE = .18, MOVE_INTERVAL = 50;
  const mount = () => {
    if (!navigator.getGamepads || window.isSecureContext === false || document.getElementById('kitchen-gamepad-hint')) return;
    const hint = document.createElement('aside');
    hint.id = 'kitchen-gamepad-hint'; hint.hidden = true;
    hint.setAttribute('data-no-i18n', ''); hint.setAttribute('role', 'status'); hint.setAttribute('aria-live', 'polite');
    // As in Overcooked 2's prompts, each action is its button and a picture of the action, in a narrow column at
    // the right edge that clears the start and result cards. Words stay in the accessible label (and in the help).
    hint.style.cssText = 'position:fixed;right:calc(var(--gx,0px) + 12px * var(--gs,1));bottom:calc(var(--gy,0px) + 36px * var(--gs,1));transform:scale(var(--gs,1));transform-origin:right bottom;z-index:17;box-sizing:border-box;padding:6px;color:var(--paper);background:#2b1a12b8;border:1px solid var(--walnut);font:12px/16px var(--body);pointer-events:none;';
    document.body.appendChild(hint);
    const SVG = 'http://www.w3.org/2000/svg';
    // 8x8 pixel pictures, drawn in the page's paper colour (# is a filled pixel).
    const PICTURES = {
      hand: ['..#.#.#.', '..#.#.#.', '#.#####.', '########', '.#######', '.######.', '..#####.', '..####..'],
      knife: ['........', '#####...', '########', '#####.##', '#####...', '#####...', '.####...', '........'],
      // Dash: the puffs of dust a dashing chef kicks up behind them in the kitchen.
      dash: ['........', '.....##.', '....####', '..#.####', '.###.##.', '#####...', '.###....', '........'],
      pause: ['........', '.##..##.', '.##..##.', '.##..##.', '.##..##.', '.##..##.', '.##..##.', '........'],
      menu: ['........', '........', '.######.', '........', '.######.', '........', '.######.', '........'],
      cross: ['#......#', '.#....#.', '..#..#..', '...##...', '...##...', '..#..#..', '.#....#.', '#......#'],
      circle: ['..####..', '.#....#.', '#......#', '#......#', '#......#', '#......#', '.#....#.', '..####..'],
      square: ['########', '#......#', '#......#', '#......#', '#......#', '#......#', '#......#', '########'],
      // The four round buttons of a sideways Joy-Con; the filled one is the button to press.
      right: ['...##...', '...##...', '........', '##....##', '##....##', '........', '...##...', '...##...'],
      left: ['...##...', '...##...', '........', '##....##', '##....##', '........', '...##...', '...##...'],
      bottom: ['...##...', '...##...', '........', '##....##', '##....##', '........', '...##...', '...##...'],
      minus: ['........', '........', '........', '.######.', '.######.', '........', '........', '........'],
    };
    const LIT = { right: [[6, 3], [7, 3], [6, 4], [7, 4]], left: [[0, 3], [1, 3], [0, 4], [1, 4]], bottom: [[3, 6], [4, 6], [3, 7], [4, 7]] };
    function picture(name, size, colour, dim) {
      const svg = document.createElementNS(SVG, 'svg');
      svg.setAttribute('viewBox', '0 0 8 8'); svg.setAttribute('width', size); svg.setAttribute('height', size);
      svg.setAttribute('shape-rendering', 'crispEdges'); svg.setAttribute('aria-hidden', 'true');
      const lit = new Set((LIT[name] || []).map(([x, y]) => x + ',' + y));
      PICTURES[name].forEach((row, y) => [...row].forEach((c, x) => {
        if (c !== '#') return;
        const r = document.createElementNS(SVG, 'rect');
        r.setAttribute('x', x); r.setAttribute('y', y); r.setAttribute('width', 1); r.setAttribute('height', 1);
        r.setAttribute('fill', lit.size && !lit.has(x + ',' + y) ? dim : colour); svg.appendChild(r);
      }));
      return svg;
    }
    // A key cap in the page's keyboard-key style, holding a letter or a pixel picture, then the action's picture.
    function row(cap, action) {
      const line = document.createElement('div');
      line.style.cssText = 'display:flex;align-items:center;gap:6px;height:24px;';
      const key = document.createElement('span');
      key.style.cssText = 'display:inline-grid;place-items:center;box-sizing:border-box;width:24px;height:22px;background:var(--paper);color:var(--ink);border:2px solid var(--ink);box-shadow:0 2px 0 var(--ink);font:12px/12px var(--pixel);';
      if (PICTURES[cap]) key.appendChild(picture(cap, 12, 'var(--ink)', '#c9b08a')); else key.textContent = cap;
      line.append(key, picture(action, 16, 'var(--paper)'));
      return line;
    }
    const PLAYSTATION = /playstation|dualsense|dualshock|054c/i;
    const LAYOUTS = {
      letters: [['A', 'hand'], ['X', 'knife'], ['B', 'dash'], ['menu', 'pause']],
      shapes: [['cross', 'hand'], ['square', 'knife'], ['circle', 'dash'], ['menu', 'pause']],
      sideways: [['right', 'hand'], ['left', 'knife'], ['bottom', 'dash'], ['minus', 'pause']],
    };
    let drawn = '';
    let controls = window.kitchenControls || null, state = controls?.getState?.() || {};
    let activeIndex = null, activeId = '', owned = false, actionDown = false, armed = false;
    let lastMove = { x: 0, y: 0 }, lastMoveAt = -Infinity, previousButtons = {}, blocked = null;
    let focused = !document.hasFocus || document.hasFocus(), apiDisabled = false, hasStandard = false, hasAny = false, sidewaysActive = false;
    const t = source => window.kitchenI18n?.t(source) || source;
    const pressed = button => typeof button === 'number' ? button > .5 : !!button?.pressed || Number(button?.value) > .5;
    const axis = value => Number.isFinite(value) ? Math.max(-1, Math.min(1, value)) : 0;
    const mobile = () => document.body.classList.contains('kitchen-touch-mode');
    const hardBlocked = () => mobile() || document.hidden || !focused || (document.hasFocus && !document.hasFocus()) ||
      !!document.querySelector('dialog[open]') || !!document.activeElement?.closest('input:not([data-kitchen-haptic]),textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]') ||
      !controls || !state.connected || (state.phase === 'running' && state.canInput === false);
    function showHint() {
      hint.hidden = apiDisabled || !hasAny || mobile();
      if (hint.hidden) return;
      const waiting = !armed || hardBlocked();
      const message = !hasStandard ? t('此手柄未提供标准映射，请使用键盘和鼠标。')
        : (waiting ? t('手柄已连接') + ' · ' + t('请松开按键并将左摇杆回中') + ' · ' : '') + (sidewaysActive
          ? t('摇杆移动 · 右键 拿放 · 左键 切洗扔（长按瞄准） · 下键 冲刺 · − 暂停/继续')
          : t('左摇杆或十字键移动 · A/× 拿放 · X/□ 切洗扔（长按瞄准） · B/○ 冲刺 · Start/Options 暂停/继续'));
      const kind = !hasStandard ? 'words' : sidewaysActive ? 'sideways' : PLAYSTATION.test(activeId) ? 'shapes' : 'letters';
      if (hint.getAttribute('aria-label') !== message) { hint.setAttribute('aria-label', message); hint.title = message; }
      // The pictures stay faint until the stick is centred and the buttons released (the gamepad is not yet in use).
      hint.style.opacity = waiting && hasStandard ? '.55' : '1';
      if (drawn === kind + message) return;
      drawn = kind + message;
      hint.replaceChildren();
      if (kind === 'words') {
        // An unsupported controller gets the sentence, kept inside the right-hand column.
        hint.style.width = '160px'; hint.textContent = message; return;
      }
      hint.style.width = '';
      hint.append(...LAYOUTS[kind].map(([cap, action]) => row(cap, action)));
    }
    function interrupt(pause = false) {
      const wasOwned = owned;
      const moving = lastMove.x !== 0 || lastMove.y !== 0;
      // Reset before bridge calls: cancelling can synchronously publish state.
      owned = actionDown = armed = false; previousButtons = {};
      lastMove = { x: 0, y: 0 }; lastMoveAt = -Infinity;
      if (wasOwned) {
        if (moving) controls?.move(0, 0);
        controls?.cancel();
        if (pause && state.connected && state.phase === 'running') controls?.pause();
      }
      showHint();
    }
    function updateState(next) {
      const old = state; state = next || {};
      if ((old.game_id && old.game_id !== state.game_id) || (old.phase && old.phase !== state.phase) ||
          (old.connected && !state.connected) || (old.canInput && state.phase === 'running' && state.canInput === false)) interrupt();
    }
    function pads() {
      try { return Array.from(navigator.getGamepads() || []).filter(pad => pad && pad.connected !== false); }
      catch (_) { apiDisabled = true; interrupt(true); hint.hidden = true; return []; }
    }
    // Button indices: a takes and puts, x chops/washes/throws, b dashes, start pauses; then the D-pad.
    const STANDARD = { a: 0, b: 1, x: 2, start: 9, up: 12, down: 13, left: 14, right: 15 };
    // macOS merges a pair of Joy-Cons into one "Joy-Con (L/R)" device that Chromium reads in the Joy-Con's simple
    // mode: the left stick (and the left arrow buttons) arrive as the D-pad, turned for a Joy-Con held sideways
    // (stick up is reported as left, down as right, left as down, right as up). Turn it back for the pair held upright.
    const MERGED_PAIR = { ...STANDARD, up: 14, down: 15, left: 13, right: 12 };
    // One left Joy-Con held sideways, as Safari reports it ("Joy-Con (L) Gamepad", no standard mapping): the stick
    // arrives as the D-pad already turned for the sideways hold, and the four round buttons are placed as on an
    // Switch controller by label: right (A) takes and puts, left (Y position, Overcooked's chop) chops, bottom (B)
    // dashes; − pauses.
    const SIDEWAYS_LEFT = { a: 2, b: 0, x: 1, start: 9, up: 12, down: 13, left: 14, right: 15 };
    // Safari reads the same pair through Apple's game controller framework ("Joy-Con (L/R) Extended Gamepad"),
    // which reports the stick on its axes and the arrow buttons upright, so only the browser's own reading turns.
    const merged = id => /joy-con \(l\/r\)/i.test(id) && !/extended gamepad/i.test(id);
    const layout = pad => pad.mapping === 'standard' ? (merged(pad.id || '') ? MERGED_PAIR : STANDARD)
      : /joy-con \(l\)/i.test(pad.id || '') ? SIDEWAYS_LEFT : null;
    const sideways = pad => layout(pad) === SIDEWAYS_LEFT;
    function sample(pad) {
      const buttons = pad.buttons || [], at = layout(pad) || STANDARD;
      const x = sideways(pad) ? 0 : axis(pad.axes?.[0]), y = sideways(pad) ? 0 : axis(pad.axes?.[1]);
      const up = pressed(buttons[at.up]), down = pressed(buttons[at.down]), left = pressed(buttons[at.left]), right = pressed(buttons[at.right]);
      const dpad = up || down || left || right;
      let dx = dpad ? Number(right) - Number(left) : x, dy = dpad ? Number(down) - Number(up) : y;
      const length = Math.hypot(dx, dy);
      if ((!dpad && length <= DEADZONE) || !length) dx = dy = 0;
      else {
        dx /= length; dy /= length;
      }
      return { dx, dy, neutral: Math.hypot(x, y) <= DEADZONE && !buttons.some(pressed),
        a: pressed(buttons[at.a]), b: pressed(buttons[at.b]), x: pressed(buttons[at.x]), start: pressed(buttons[at.start]) };
    }
    function move(dx, dy, now, force = false) {
      if (dx === lastMove.x && dy === lastMove.y) return;
      // Suppress tiny hardware drift while retaining the actual direction of
      // a deliberate analog input. Starting and stopping are always immediate;
      // actions can force their current direction through the steering throttle.
      const steering = (dx || dy) && (lastMove.x || lastMove.y);
      if (!force && steering && Math.hypot(dx - lastMove.x, dy - lastMove.y) < .005) return;
      if (!force && steering && now - lastMoveAt < MOVE_INTERVAL) return;
      lastMove = { x: dx, y: dy }; lastMoveAt = now;
      if (dx || dy) owned = true;
      controls.move(dx, dy);
    }
    function frame(now) {
      if (apiDisabled) return;
      const available = pads();
      hasAny = available.length > 0;
      const standard = available.filter(pad => layout(pad));
      hasStandard = standard.length > 0;
      let pad = standard.find(p => p.index === activeIndex && p.id === activeId);
      if (activeIndex !== null && !pad) { interrupt(true); activeIndex = null; activeId = ''; }
      if (!pad && standard.length) {
        pad = standard[0]; activeIndex = pad.index; activeId = pad.id;
        armed = false; previousButtons = {}; lastMove = { x: 0, y: 0 }; lastMoveAt = -Infinity;
      }
      sidewaysActive = !!pad && sideways(pad);
      if (pad && controls?.getState) updateState(controls.getState());
      const unavailable = hardBlocked();
      if (unavailable !== blocked) { blocked = unavailable; if (unavailable) interrupt(); }
      if (!pad || unavailable) { showHint(); requestAnimationFrame(frame); return; }
      const input = sample(pad);
      if (!armed) {
        if (input.neutral) { armed = true; previousButtons = input; }
        showHint(); requestAnimationFrame(frame); return;
      }
      const edges = { a: input.a && !previousButtons.a, b: input.b && !previousButtons.b,
        x: input.x && !previousButtons.x, start: input.start && !previousButtons.start,
        release: !input.x && !!previousButtons.x };
      previousButtons = input;
      const running = state.phase === 'running' && state.canInput !== false;
      if (edges.start && (running || !state.pending)) {
        const method = running ? 'pause' : state.phase === 'paused' ? 'resume' : ['ready', 'ended'].includes(state.phase) && state.mainEnabled ? 'main' : null;
        if (method) { interrupt(); owned = true; controls[method](); showHint(); requestAnimationFrame(frame); return; }
      }
      // A on the result card presses its main button (next level); the page ignores it for the card's first second.
      if (!running && edges.a && state.phase === 'ended' && state.mainEnabled && !state.pending) { owned = true; controls.main(); }
      if (!running) { showHint(); requestAnimationFrame(frame); return; }
      const moveTime = Number.isFinite(now) ? now : performance.now();
      move(input.dx, input.dy, moveTime);
      // Overcooked 2's buttons: A picks up and puts down; X chops, washes, sprays, or with a throwable item
      // arms a throw (a tap throws ahead, holding aims, releasing X throws); B dashes. As in Overcooked, no button
      // cancels an aim: releasing X throws.
      if (edges.a && !state.pending) { owned = true; controls.act(); }
      if (edges.x && !state.pending && !state.aiming) {
        owned = true;
        if (state.holding && state.canThrow) { actionDown = true; controls.toss(); } else controls.use?.();
      }
      if (edges.release && actionDown) { actionDown = false; controls.release(); }
      const sprint = state.sprint || {};
      if (edges.b && (input.dx || input.dy) && !state.aiming && sprint.available !== false && !(sprint.active_remaining > 0) && !(sprint.cooldown_remaining > 0)) {
        move(input.dx, input.dy, moveTime, true);
        owned = true; controls.dash();
      }
      showHint(); requestAnimationFrame(frame);
    }
    const manual = () => {
      // Root dispatches this before its keyboard handler. The DOM fallback can
      // follow it, but must never cancel the fresh keyboard input a second time.
      interrupt();
    };
    const fallback = event => { if (event.isTrusted && owned) interrupt(); };
    window.addEventListener('kitchen-manual-input', manual);
    window.addEventListener('keydown', fallback, true);
    window.addEventListener('mousedown', fallback, true);
    window.addEventListener('pointerdown', fallback, true);
    window.addEventListener('blur', () => { focused = false; interrupt(true); });
    window.addEventListener('focus', () => { focused = true; armed = false; showHint(); });
    document.addEventListener('visibilitychange', () => { if (document.hidden) interrupt(true); else { armed = false; showHint(); } });
    document.addEventListener('focusin', () => { if (hardBlocked()) interrupt(); });
    new MutationObserver(() => { if (hardBlocked()) interrupt(); }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['open', 'class'] });
    window.addEventListener('kitchen-controls-state', event => updateState(event.detail));
    window.addEventListener('kitchen-controls-ready', () => { interrupt(); controls = window.kitchenControls || null; updateState(controls?.getState?.()); });
    window.addEventListener('kitchen-language-changed', showHint);
    window.addEventListener('gamepaddisconnected', event => {
      if (event.gamepad?.index !== activeIndex || (event.gamepad.id && event.gamepad.id !== activeId)) return;
      interrupt(true); activeIndex = null; activeId = '';
    });
    window.addEventListener('gamepadconnected', showHint);
    requestAnimationFrame(frame);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
