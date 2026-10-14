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
    hint.style.cssText = 'position:fixed;left:calc(var(--gx,0px) + 1052px * var(--gs,1));right:calc(var(--gx,0px) + 12px * var(--gs,1));bottom:calc(var(--gy,0px) + 36px * var(--gs,1));z-index:17;box-sizing:border-box;padding:6px 8px;color:var(--paper);background:#2b1a12b8;border:1px solid var(--walnut);font:12px/18px var(--body);text-align:right;pointer-events:none;';
    document.body.appendChild(hint);
    let controls = window.kitchenControls || null, state = controls?.getState?.() || {};
    let activeIndex = null, activeId = '', owned = false, actionDown = false, armed = false;
    let lastMove = { x: 0, y: 0 }, lastMoveAt = -Infinity, previousButtons = {}, blocked = null;
    let focused = !document.hasFocus || document.hasFocus(), apiDisabled = false, hasStandard = false, hasAny = false;
    const t = source => window.kitchenI18n?.t(source) || source;
    const pressed = button => typeof button === 'number' ? button > .5 : !!button?.pressed || Number(button?.value) > .5;
    const axis = value => Number.isFinite(value) ? Math.max(-1, Math.min(1, value)) : 0;
    const mobile = () => document.body.classList.contains('kitchen-touch-mode');
    const hardBlocked = () => mobile() || document.hidden || !focused || (document.hasFocus && !document.hasFocus()) ||
      !!document.querySelector('dialog[open]') || !!document.activeElement?.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]') ||
      !controls || !state.connected || (state.phase === 'running' && state.canInput === false);
    function showHint() {
      hint.hidden = apiDisabled || !hasAny || mobile();
      if (hint.hidden) return;
      const message = !hasStandard ? t('此手柄未提供标准映射，请使用键盘和鼠标。') : !armed || hardBlocked()
        ? t('手柄已连接') + ' · ' + t('请松开按键并将左摇杆回中')
        : t('左摇杆或十字键移动 · A/× 操作（长按投掷） · X/□ 冲刺 · B/○ 取消 · Start/Options 暂停/继续');
      if (hint.textContent !== message) hint.textContent = message;
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
    function sample(pad) {
      const buttons = pad.buttons || [], x = axis(pad.axes?.[0]), y = axis(pad.axes?.[1]);
      const up = pressed(buttons[12]), down = pressed(buttons[13]), left = pressed(buttons[14]), right = pressed(buttons[15]);
      const dpad = up || down || left || right;
      let dx = dpad ? Number(right) - Number(left) : x, dy = dpad ? Number(down) - Number(up) : y;
      const length = Math.hypot(dx, dy);
      if ((!dpad && length <= DEADZONE) || !length) dx = dy = 0;
      else {
        dx /= length; dy /= length;
      }
      return { dx, dy, neutral: Math.hypot(x, y) <= DEADZONE && !buttons.some(pressed),
        a: pressed(buttons[0]), b: pressed(buttons[1]), x: pressed(buttons[2]), start: pressed(buttons[9]) };
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
      const standard = available.filter(pad => pad.mapping === 'standard');
      hasStandard = standard.length > 0;
      let pad = standard.find(p => p.index === activeIndex && p.id === activeId);
      if (activeIndex !== null && !pad) { interrupt(true); activeIndex = null; activeId = ''; }
      if (!pad && standard.length) {
        pad = standard[0]; activeIndex = pad.index; activeId = pad.id;
        armed = false; previousButtons = {}; lastMove = { x: 0, y: 0 }; lastMoveAt = -Infinity;
      }
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
        release: !input.a && !!previousButtons.a };
      previousButtons = input;
      const running = state.phase === 'running' && state.canInput !== false;
      if (edges.start && (running || !state.pending)) {
        const method = running ? 'pause' : state.phase === 'paused' ? 'resume' : state.phase === 'ready' && state.mainEnabled ? 'main' : null;
        if (method) { interrupt(); owned = true; controls[method](); showHint(); requestAnimationFrame(frame); return; }
      }
      if (!running) { showHint(); requestAnimationFrame(frame); return; }
      if (edges.b && owned && (actionDown || state.aiming)) {
        interrupt(); requestAnimationFrame(frame); return;
      }
      const moveTime = Number.isFinite(now) ? now : performance.now();
      move(input.dx, input.dy, moveTime);
      if (edges.a && !state.pending) { owned = actionDown = true; controls.press(); }
      if (edges.release && actionDown) { actionDown = false; controls.release(); }
      const sprint = state.sprint || {};
      if (edges.x && (input.dx || input.dy) && !state.aiming && sprint.available !== false && !(sprint.active_remaining > 0) && !(sprint.cooldown_remaining > 0)) {
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
