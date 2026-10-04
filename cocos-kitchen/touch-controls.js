/* Touch chrome for the Web build. All game actions go through KitchenClient's
 * controls bridge; this module never synthesizes keyboard events or calls APIs. */
(() => {
  'use strict';
  const mount = () => {
    if (document.getElementById('kitchen-touch-ui')) return;
    const style = document.createElement('style');
    style.textContent = `
      #kitchen-touch-ui{position:fixed;inset:0;z-index:18;box-sizing:border-box;padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);pointer-events:none;font:14px/1.35 var(--body);color:var(--ink)}
      #kitchen-touch-ui button{font-family:var(--body);-webkit-tap-highlight-color:transparent}
      .touch-toolbar{position:absolute;left:max(8px,env(safe-area-inset-left));right:max(8px,env(safe-area-inset-right));top:max(4px,env(safe-area-inset-top));height:38px;display:flex;align-items:center;gap:6px;padding:0 6px;background:var(--paper);border:2px solid var(--walnut);pointer-events:auto;box-sizing:border-box}
      .touch-clock{font-weight:750;font-size:16px;white-space:nowrap;font-variant-numeric:tabular-nums}.touch-money{font-weight:700;white-space:nowrap}.touch-spacer{flex:1;min-width:0}
      .touch-toolbar button{min-height:30px;padding:3px 8px;box-shadow:0 2px 0 var(--ink);font-size:12px;line-height:16px;touch-action:manipulation}
      .touch-orders{position:absolute;left:max(10px,env(safe-area-inset-left));right:max(10px,env(safe-area-inset-right));top:calc(max(4px,env(safe-area-inset-top)) + 42px);display:flex;gap:6px;height:26px;overflow-x:auto;scrollbar-width:none;pointer-events:auto;touch-action:pan-x;overscroll-behavior:contain}
      .touch-order{flex:none;padding:3px 8px;background:var(--paper);border:1px solid var(--walnut);font-size:13px;white-space:nowrap;font-variant-numeric:tabular-nums}.touch-order.urgent{border-color:var(--tomato);color:var(--tomato)}
      #touch-joystick{position:absolute;left:calc(max(8px,env(safe-area-inset-left)) + 2px);bottom:calc(max(8px,env(safe-area-inset-bottom)) + 4px);width:120px;height:120px;box-sizing:border-box;border:3px solid var(--walnut);border-radius:50%;background:#fdf3e1c9;box-shadow:0 3px 0 var(--ink),inset 0 0 0 16px #f0d9b56b;pointer-events:auto;touch-action:none;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none}
      #touch-joystick::before,#touch-joystick::after{content:'';position:absolute;left:15%;right:15%;top:50%;height:1px;background:#6b34184d;pointer-events:none}#touch-joystick::after{transform:rotate(90deg)}
      #touch-stick{position:absolute;left:50%;top:50%;width:48px;height:48px;margin:-24px;border:2px solid var(--ink);border-radius:50%;box-sizing:border-box;background:var(--honey);box-shadow:0 3px 0 var(--walnut);pointer-events:none;display:grid;place-items:center;font-size:11px;font-weight:650}
      #touch-joystick[aria-disabled=true]{opacity:.4}.touch-buttons{position:absolute;right:max(10px,env(safe-area-inset-right));bottom:calc(max(8px,env(safe-area-inset-bottom)) + 12px);display:flex;align-items:flex-end;gap:14px;pointer-events:none}
      .touch-round{display:grid;place-items:center;flex:none;border:3px solid var(--ink);border-radius:50%;box-shadow:0 4px 0 var(--walnut);color:var(--paper);pointer-events:auto;touch-action:none;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;font-size:15px;font-weight:750;padding:6px;box-sizing:border-box;line-height:1.2}
      #touch-action{width:72px;height:72px;background:var(--denim)}#touch-action[data-pressed=true]{background:var(--denim-hover);box-shadow:0 1px 0 var(--walnut)}
      #touch-dash{position:relative;width:54px;height:54px;font-size:12px;background:var(--herb)}
      .touch-round:disabled{color:var(--muted);background:var(--surface)!important;box-shadow:none;opacity:.7}#touch-dash[data-cooling=true]{opacity:1}#touch-dash[data-cooling=true]::before{content:'';position:absolute;inset:-8px;border-radius:50%;background:conic-gradient(var(--honey) var(--cooldown,0%),var(--walnut) 0);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 4px),#000 0);mask:radial-gradient(farthest-side,transparent calc(100% - 4px),#000 0);pointer-events:none}
      #touch-cancel{position:absolute;right:calc(max(10px,env(safe-area-inset-right)) + 7px);bottom:calc(max(8px,env(safe-area-inset-bottom)) + 102px);width:146px;min-height:48px;display:grid;place-items:center;box-sizing:border-box;border:2px dashed var(--tomato);background:var(--paper);color:var(--tomato);font-size:13px;pointer-events:none}#touch-cancel[data-selected=true]{border-style:solid;background:var(--tomato);color:var(--paper)}
      .touch-hint{position:absolute;left:146px;right:174px;bottom:max(9px,env(safe-area-inset-bottom));text-align:center;pointer-events:none;color:var(--paper);background:#2b1a12dd;padding:4px 8px;border:1px solid var(--walnut);font-size:12px;line-height:1.4;border-radius:2px;max-height:50px;overflow:hidden;box-sizing:border-box}
      #touch-ai{position:absolute;left:max(10px,env(safe-area-inset-left));bottom:calc(max(8px,env(safe-area-inset-bottom)) + 138px);width:124px;max-height:48px;box-sizing:border-box;padding:4px 6px;border:1px solid var(--walnut);background:#2b1a12dd;overflow:hidden;font-size:11px;line-height:1.3;color:var(--paper);text-align:left;pointer-events:none;overflow-wrap:anywhere}
      #touch-hand{display:block;font-weight:650;line-height:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}#touch-status{display:block;line-height:14px;max-height:28px;overflow:hidden}.touch-menu{position:absolute;left:max(12px,env(safe-area-inset-left));right:max(12px,env(safe-area-inset-right));top:calc(max(4px,env(safe-area-inset-top)) + 76px);bottom:max(8px,env(safe-area-inset-bottom));margin:auto;max-width:560px;box-sizing:border-box;overflow:auto;overscroll-behavior:contain;background:var(--paper);border:3px solid var(--walnut);box-shadow:5px 5px 0 var(--ink);padding:14px 18px;pointer-events:auto;touch-action:pan-y;text-align:center}
      .touch-menu h2{margin:0 0 5px;font-size:23px;line-height:1.2}.touch-menu p{white-space:pre-line;margin:5px 0 10px;font-size:14px;line-height:1.45;color:var(--muted)}.touch-menu-actions{display:flex;justify-content:center;gap:8px;flex-wrap:wrap}.touch-menu button{min-height:40px;font-size:14px;line-height:1.2;touch-action:manipulation}.touch-menu .primary{min-width:152px}.touch-menu-secondary{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;margin-top:10px}.touch-levels{display:flex;justify-content:center;gap:6px;flex-wrap:wrap;margin:10px 0}.touch-levels button{min-height:34px;padding:6px 10px;font-size:12px}.touch-levels button[aria-pressed=true]{background:var(--honey)}
      #kitchen-touch-landscape{position:fixed;inset:0;z-index:50;display:grid;place-items:center;padding:max(20px,env(safe-area-inset-top)) max(20px,env(safe-area-inset-right)) max(20px,env(safe-area-inset-bottom)) max(20px,env(safe-area-inset-left));box-sizing:border-box;background:var(--frame);text-align:center;color:var(--paper)}#kitchen-touch-landscape .panel{padding:24px;max-width:370px;text-align:center}#kitchen-touch-landscape h2{font-size:24px;margin:10px 0}#kitchen-touch-landscape p{color:var(--muted);font-size:15px;line-height:1.6;margin:8px 0 0}.touch-rotate-icon{font-size:46px;line-height:1}
      body.kitchen-touch-mode #kitchen-display-hint{display:none}body.kitchen-touch-mode #GameDiv{height:100dvh!important}body.kitchen-touch-mode #GameCanvas{touch-action:none;-webkit-touch-callout:none}
      body.kitchen-touch-mode #kitchen-communication{left:auto;right:max(10px,env(safe-area-inset-right));top:calc(max(4px,env(safe-area-inset-top)) + 44px);bottom:auto;transform:none;width:min(300px,calc(100vw - 24px));max-height:calc(var(--touch-vh,100dvh) - 58px);overflow:auto;z-index:30;font:14px/20px var(--body);touch-action:pan-y}body.kitchen-touch-mode #kitchen-communication:not([data-touch-open=true]){display:none!important}
      body.kitchen-touch-mode #kitchen-communication button{min-height:40px;font-size:14px}body.kitchen-touch-mode #kitchen-communication .key{display:none}body.kitchen-touch-mode #communication-toggle{display:none}
      body.kitchen-touch-mode dialog.panel{max-height:calc(var(--touch-vh,100dvh) - 12px);max-width:calc(100vw - env(safe-area-inset-left) - env(safe-area-inset-right) - 20px);font-size:15px;touch-action:pan-y;overscroll-behavior:contain}body.kitchen-touch-mode .dlg-head{padding:10px 14px;gap:8px}body.kitchen-touch-mode .dlg-head h2{font-size:20px;line-height:24px}body.kitchen-touch-mode .dlg-body{padding:12px 14px}body.kitchen-touch-mode .tabs{padding:0 14px 8px;gap:4px}body.kitchen-touch-mode .dlg-foot{padding:0 14px 14px}body.kitchen-touch-mode .sr-label{display:none}body.kitchen-touch-mode input,body.kitchen-touch-mode textarea,body.kitchen-touch-mode select{font-size:16px!important;-webkit-user-select:text;user-select:text;-webkit-touch-callout:default;touch-action:auto}
      body.kitchen-touch-mode #kitchen-bookmark-toast{left:50%;bottom:154px;transform:translateX(-50%);max-width:calc(100vw - 32px);font:13px/18px var(--body)}
      @media(max-width:700px){.touch-toolbar{gap:4px;padding:0 4px}.touch-toolbar button{padding:3px 6px}.touch-clock{font-size:14px}.touch-money{font-size:12px}#touch-served{display:none}#touch-joystick{width:112px;height:112px}.touch-buttons{gap:10px}.touch-hint{left:132px;right:160px;font-size:11px}.touch-menu{padding:10px 12px}.touch-menu h2{font-size:20px}.touch-menu button{min-height:36px;font-size:13px}}
    `;
    document.head.appendChild(style);
    const ui = document.createElement('div');
    ui.id = 'kitchen-touch-ui';
    ui.hidden = true;
    ui.setAttribute('data-no-i18n', '');
    ui.innerHTML = `
      <header class="touch-toolbar"><strong id="touch-clock" class="touch-clock"></strong><span id="touch-money" class="touch-money"></span><span id="touch-served"></span><span class="touch-spacer"></span><button id="touch-pause" class="btn" type="button"></button><button id="touch-communication" class="btn" type="button" aria-expanded="false" aria-controls="kitchen-communication"></button><button id="touch-bookmark" class="btn" type="button"></button><button id="touch-menu-toggle" class="btn" type="button" aria-expanded="false" aria-controls="touch-menu"></button></header>
      <div id="touch-orders" class="touch-orders" aria-label="订单"></div>
      <div id="touch-joystick" role="group" aria-label="移动" aria-disabled="true"><div id="touch-stick"></div></div>
      <div class="touch-buttons"><button id="touch-dash" class="touch-round" type="button"></button><button id="touch-action" class="touch-round" type="button"></button></div>
      <div id="touch-cancel" hidden></div>
      <div id="touch-hint" class="touch-hint"><span id="touch-hand"></span><span id="touch-status" role="status" aria-live="polite"></span></div>
      <div id="touch-ai"></div>
      <section id="touch-menu" class="touch-menu" aria-labelledby="touch-menu-title" hidden><h2 id="touch-menu-title">ChefJeff</h2><p id="touch-menu-copy"></p><div id="touch-levels" class="touch-levels"></div><div class="touch-menu-actions"><button id="touch-main" class="btn primary" type="button"></button><button id="touch-settings" class="btn" type="button"></button><button id="touch-help" class="btn" type="button"></button></div><div class="touch-menu-secondary"><button id="touch-end" class="btn danger" type="button"></button><button id="touch-record" class="btn" type="button"></button><button id="touch-language" class="btn" type="button" data-no-i18n></button><button id="touch-fullscreen" class="btn" type="button"></button><button id="touch-menu-close" class="btn" type="button"></button></div><p id="touch-instructions"></p></section>
    `;
    document.body.appendChild(ui);
    const portrait = document.createElement('div');
    portrait.id = 'kitchen-touch-landscape';
    portrait.hidden = true;
    portrait.setAttribute('data-no-i18n', '');
    portrait.innerHTML = '<div class="panel"><div class="touch-rotate-icon" aria-hidden="true">↻ ▭</div><h2 id="touch-rotate-title"></h2><p id="touch-rotate-copy"></p></div>';
    document.body.appendChild(portrait);

    const el = id => document.getElementById(id);
    const t = text => window.kitchenI18n?.t(text) || text;
    const text = (id, value) => { const n = el(id); const next = t(String(value ?? '')); if (n.textContent !== next) n.textContent = next; };
    const stick = el('touch-stick'), joystick = el('touch-joystick'), action = el('touch-action'), dash = el('touch-dash');
    const dock = el('kitchen-communication');
    let controls = window.kitchenControls || null, state = {}, active = false, landscape = true;
    let blockState = null, menuOpen = false, communicationOpen = false, joyPointer = null, actionPointer = null;
    let cancelSelected = false, ordersSignature = '', levelsSignature = '', previousGame = '', modeSignature = '';
    let lastEvent = '', eventNotice = '', eventTimer;
    let pausePending = false;
    const editor = () => document.activeElement?.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]');
    const modal = () => !!document.querySelector('dialog[open]');
    const stopped = () => !active || !landscape || document.hidden || modal() || !!editor() || menuOpen || communicationOpen;
    const canPlay = () => !!controls && active && landscape && !stopped() && state.connected && state.phase === 'running' && !state.pending;
    const capture = (n, id) => { try { n.setPointerCapture(id); } catch (_) {} };
    const uncapture = (n, id) => { if (id === null) return; try { if (n.hasPointerCapture(id)) n.releasePointerCapture(id); } catch (_) {} };
    function clearPointers() {
      const joy = joyPointer, press = actionPointer;
      joyPointer = actionPointer = null;
      uncapture(joystick, joy); uncapture(action, press);
      stick.style.transform = 'translate(0px,0px)';
      action.dataset.pressed = 'false';
      cancelSelected = false; el('touch-cancel').dataset.selected = 'false';
      if (joy !== null) controls?.move(0, 0);
      if (press !== null) controls?.cancel();
    }
    function block() {
      // Inactive desktop chrome must never pause keyboard play.
      const next = active && stopped();
      if (next !== blockState) {
        blockState = next;
        if (next) clearPointers();
        controls?.block(next);
      }
    }
    function mode() {
      const w = innerWidth, h = innerHeight;
      const focused = !!editor();
      const coarse = window.matchMedia?.('(pointer: coarse)').matches || navigator.maxTouchPoints > 0;
      const next = focused ? active : !!coarse && Math.min(w, h) <= 600 && Math.max(w, h) <= 1400;
      const nextLandscape = focused ? landscape : w > h;
      if (next !== active || nextLandscape !== landscape) clearPointers();
      active = next; landscape = nextLandscape;
      document.body.classList.toggle('kitchen-touch-mode', active);
      document.documentElement.style.setProperty('--touch-vh', (window.visualViewport?.height || h) + 'px');
      ui.hidden = !active;
      portrait.hidden = !active || landscape;
      // The kitchen occupies the gap between thumb controls, rather than hiding
      // its bottom row behind a full-width button bar. Env padding is resolved
      // by the browser (including Safari's notches and home indicator).
      const safe = window.getComputedStyle(ui);
      const left = (parseFloat(safe.paddingLeft) || 0) + (w <= 700 ? 132 : 146);
      const right = (parseFloat(safe.paddingRight) || 0) + (w <= 700 ? 160 : 174);
      const top = (parseFloat(safe.paddingTop) || 0) + 74;
      const bottom = (parseFloat(safe.paddingBottom) || 0) + 60;
      const detail = { active, landscape, width: w, height: h,
        boardRect: { left, top, width: Math.max(100, w - left - right), height: Math.max(100, h - top - bottom) } };
      const signature = JSON.stringify(detail);
      if (signature !== modeSignature) {
        if (modeSignature) clearPointers();
        modeSignature = signature;
        window.dispatchEvent(new CustomEvent('kitchen-touch-mode', { detail }));
      }
      block(); render();
    }
    function communication(open) {
      communicationOpen = open && !!state.communicationEnabled;
      if (dock) {
        dock.dataset.touchOpen = String(communicationOpen);
        if (communicationOpen) { el('communication-options').hidden = false; el('communication-toggle').setAttribute('aria-expanded', 'true'); }
      }
      el('touch-communication').setAttribute('aria-expanded', String(communicationOpen));
      block(); render();
    }
    function menu(open) {
      menuOpen = open;
      if (open) communication(false);
      block(); render();
    }
    function render() {
      if (!active) return;
      const playing = canPlay(), aiming = !!state.aiming;
      const hasModal = modal();
      const showMenu = landscape && !hasModal && !communicationOpen && (menuOpen || !state.connected || state.phase !== 'running');
      el('touch-menu').hidden = !showMenu;
      el('touch-menu-toggle').setAttribute('aria-expanded', String(showMenu));
      joystick.hidden = !landscape || showMenu || hasModal || communicationOpen;
      joystick.setAttribute('aria-disabled', String(!playing));
      action.hidden = dash.hidden = joystick.hidden;
      el('touch-hint').hidden = joystick.hidden;
      el('touch-ai').hidden = joystick.hidden;
      action.disabled = !playing || !(state.canInteract || state.canThrow);
      const sprint = state.sprint || {};
      const cooling = (sprint.cooldown_remaining || 0) > 0;
      dash.disabled = !playing || !state.canDash || aiming || cooling || (sprint.active_remaining || 0) > 0;
      dash.dataset.cooling = String(cooling);
      dash.style.setProperty('--cooldown', Math.max(0, Math.min(100, (sprint.cooldown_remaining || 0) / 3 * 100)) + '%');
      text('touch-dash', cooling ? Math.ceil(sprint.cooldown_remaining) + 's' : '冲刺');
      el('touch-cancel').hidden = !playing || actionPointer === null || !(state.holding && state.canThrow);
      text('touch-action', aiming ? '松开投掷' : state.interaction || '操作');
      text('touch-stick', aiming ? '瞄准' : '移动');
      text('touch-hand', state.handLabel || '');
      text('touch-ai', state.aiStatus || '');
      text('touch-status', cancelSelected ? '拖到这里取消' : aiming ? '松开投掷' : eventNotice || state.interactionHint || (state.holding && state.canThrow ? '长按投掷' : ''));
      text('touch-clock', state.timeLabel || '厨房连接中…');
      text('touch-money', state.money == null ? '' : '¥' + state.money);
      text('touch-served', state.served == null ? '' : t('已出餐') + ' ' + state.served);
      text('touch-pause', state.phase === 'paused' ? '继续' : '暂停');
      el('touch-pause').disabled = !state.connected || state.pending || !['running', 'paused'].includes(state.phase) || hasModal || communicationOpen;
      el('touch-bookmark').disabled = !state.connected || state.phase !== 'running' || state.pending;
      el('touch-communication').disabled = !state.communicationEnabled || !state.connected || hasModal;
      text('touch-menu-title', state.coverTitle || 'ChefJeff');
      text('touch-menu-copy', !state.connected ? '连接已中断' : state.coverText || '使用左侧摇杆移动，右侧按钮操作和冲刺。');
      text('touch-main', state.mainLabel || '开始经营');
      el('touch-main').disabled = !controls || state.mainEnabled === false || state.pending;
      el('touch-end').hidden = !['running', 'paused'].includes(state.phase);
      el('touch-end').disabled = !state.endEnabled;
      el('touch-record').hidden = !state.recordEnabled;
      el('touch-menu-close').hidden = state.phase !== 'running' || !menuOpen;
      const levels = state.levels || [];
      const nextLevels = JSON.stringify([levels, state.levelEnabled]);
      if (nextLevels !== levelsSignature) {
        levelsSignature = nextLevels; el('touch-levels').replaceChildren();
        for (const level of levels) {
          const button = document.createElement('button'); button.type = 'button'; button.className = 'btn';
          button.textContent = t(level.name); button.setAttribute('aria-pressed', String(!!level.selected));
          button.disabled = !state.levelEnabled; button.addEventListener('click', () => controls?.level(level.id)); el('touch-levels').appendChild(button);
        }
      }
      el('touch-levels').hidden = !levels.length || !['ready', 'ended'].includes(state.phase);
      const orders = state.orders || [];
      const orderRows = orders.map(o => [o.id, o.dishName || o.dish, Math.max(0, Math.ceil(o.remaining || 0))]);
      const nextOrders = JSON.stringify(orderRows);
      if (nextOrders !== ordersSignature) {
        ordersSignature = nextOrders; el('touch-orders').replaceChildren();
        for (const row of orderRows) {
          const ticket = document.createElement('span'); ticket.className = 'touch-order' + (row[2] <= 15 ? ' urgent' : '');
          ticket.textContent = t(String(row[1])) + ' · ' + row[2] + 's'; el('touch-orders').appendChild(ticket);
        }
      }
    }
    function language() {
      for (const [id, source] of Object.entries({ 'touch-pause': '暂停', 'touch-communication': '沟通', 'touch-bookmark': '标记',
        'touch-menu-toggle': '菜单', 'touch-settings': '设置', 'touch-help': '操作说明', 'touch-end': '结束本局', 'touch-record': '本局记录',
        'touch-fullscreen': '全屏', 'touch-menu-close': '返回厨房', 'touch-cancel': '拖到这里取消', 'touch-rotate-title': '请将手机横过来',
        'touch-rotate-copy': '横屏后点“继续经营”，厨房不会自动恢复。',
        'touch-instructions': '手持物品时长按操作瞄准，松开投掷；拖到取消区可取消。' })) text(id, source);
      el('touch-language').textContent = window.kitchenI18n?.language === 'en' ? '中文' : 'English';
      joystick.setAttribute('aria-label', t('移动')); el('touch-orders').setAttribute('aria-label', t('订单'));
      ordersSignature = levelsSignature = ''; render();
    }
    function joyMove(event) {
      const r = joystick.getBoundingClientRect(), radius = r.width / 2;
      let dx = (event.clientX - r.left - radius) / radius, dy = (event.clientY - r.top - radius) / radius;
      const magnitude = Math.hypot(dx, dy);
      if (magnitude <= .15) dx = dy = 0;
      else { dx /= magnitude; dy /= magnitude; }
      const travel = Math.min(1, magnitude) * (radius - 27);
      stick.style.transform = 'translate(' + (dx * travel) + 'px,' + (dy * travel) + 'px)';
      controls?.move(dx, dy);
    }
    joystick.addEventListener('pointerdown', event => {
      if (event.button > 0 || joyPointer !== null || !canPlay()) return;
      event.preventDefault(); joyPointer = event.pointerId; capture(joystick, joyPointer); joyMove(event);
    });
    joystick.addEventListener('pointermove', event => { if (event.pointerId !== joyPointer) return; event.preventDefault(); if (canPlay()) joyMove(event); else clearPointers(); });
    const joyEnd = event => { if (event.pointerId !== joyPointer) return; event.preventDefault(); const id = joyPointer; joyPointer = null; uncapture(joystick, id); stick.style.transform = 'translate(0px,0px)'; controls?.move(0, 0); };
    joystick.addEventListener('pointerup', joyEnd); joystick.addEventListener('pointercancel', joyEnd); joystick.addEventListener('lostpointercapture', joyEnd);
    action.addEventListener('pointerdown', event => {
      if (event.button > 0 || actionPointer !== null || action.disabled || !canPlay()) return;
      event.preventDefault(); actionPointer = event.pointerId; action.dataset.pressed = 'true'; capture(action, actionPointer);
      cancelSelected = false; controls.press(); render();
    });
    action.addEventListener('pointermove', event => {
      if (event.pointerId !== actionPointer) return;
      event.preventDefault(); const r = el('touch-cancel').getBoundingClientRect();
      cancelSelected = !el('touch-cancel').hidden && event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom;
      el('touch-cancel').dataset.selected = String(cancelSelected); render();
    });
    action.addEventListener('pointerup', event => {
      if (event.pointerId !== actionPointer) return;
      event.preventDefault(); const id = actionPointer; actionPointer = null; uncapture(action, id); action.dataset.pressed = 'false';
      if (cancelSelected || !canPlay()) controls?.cancel(); else controls?.release();
      cancelSelected = false; render();
    });
    const cancelAction = event => { if (event.pointerId !== actionPointer) return; event.preventDefault(); const id = actionPointer; actionPointer = null; uncapture(action, id); action.dataset.pressed = 'false'; cancelSelected = false; controls?.cancel(); render(); };
    action.addEventListener('pointercancel', cancelAction); action.addEventListener('lostpointercapture', cancelAction);
    dash.addEventListener('pointerdown', event => { if (event.button > 0 || dash.disabled || !canPlay()) return; event.preventDefault(); controls?.dash(); });
    for (const area of [joystick, action, dash]) area.addEventListener('contextmenu', event => event.preventDefault());
    el('touch-pause').addEventListener('click', () => {
      if (state.phase === 'running') { clearPointers(); controls?.pause(); }
      else if (state.phase === 'paused') { menuOpen = false; communication(false); block(); controls?.resume(); }
    });
    el('touch-main').addEventListener('click', () => { menuOpen = false; communication(false); block(); controls?.main(); });
    el('touch-menu-toggle').addEventListener('click', () => menu(!menuOpen));
    el('touch-menu-close').addEventListener('click', () => menu(false));
    el('touch-communication').addEventListener('click', () => communication(!communicationOpen));
    el('touch-bookmark').addEventListener('click', () => controls?.bookmark());
    for (const [id, method] of [['touch-settings', 'settings'], ['touch-help', 'help'], ['touch-end', 'end'], ['touch-record', 'record']])
      el(id).addEventListener('click', () => { clearPointers(); controls?.[method](); });
    el('touch-language').addEventListener('click', () => controls?.language());
    el('touch-fullscreen').hidden = !document.documentElement.requestFullscreen;
    el('touch-fullscreen').addEventListener('click', async () => {
      try { await document.documentElement.requestFullscreen(); try { await screen.orientation?.lock?.('landscape'); } catch (_) {} } catch (_) {}
    });
    // Native dialogs keep text selection, scrolling, pasting and the soft keyboard.
    // Only control surfaces disable default gestures. Closing any interruption
    // leaves a running round paused until the player explicitly resumes it.
    const interruptions = () => { block(); render(); };
    new MutationObserver(interruptions).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['open'] });
    document.addEventListener('focusin', interruptions); document.addEventListener('focusout', () => queueMicrotask(interruptions));
    document.addEventListener('visibilitychange', () => { if (document.hidden) clearPointers(); interruptions(); });
    window.addEventListener('blur', () => { clearPointers(); if (active && state.phase === 'running' && !pausePending) { pausePending = true; controls?.pause(); } });
    window.addEventListener('focus', () => { pausePending = false; interruptions(); });
    window.addEventListener('resize', mode); window.addEventListener('orientationchange', () => { clearPointers(); mode(); });
    window.visualViewport?.addEventListener('resize', mode);
    window.matchMedia?.('(pointer: coarse)').addEventListener?.('change', mode);
    window.addEventListener('kitchen-controls-state', event => {
      const next = event.detail || {};
      if ((previousGame && previousGame !== next.game_id) || !next.connected || next.phase !== 'running') clearPointers();
      previousGame = next.game_id || ''; state = next;
      if (next.event && next.event !== lastEvent) {
        lastEvent = eventNotice = next.event;
        clearTimeout(eventTimer); eventTimer = setTimeout(() => { eventNotice = ''; render(); }, 2500);
      }
      if (!state.communicationEnabled && communicationOpen) communication(false);
      if (!next.pending) pausePending = false;
      block(); render();
    });
    const ready = () => {
      controls = window.kitchenControls || null; blockState = null;
      if (controls?.getState) state = controls.getState() || {};
      // Ready may follow initial mode publication; send it again for the new client.
      modeSignature = ''; mode();
    };
    window.addEventListener('kitchen-controls-ready', ready);
    window.addEventListener('kitchen-language-changed', language);
    language(); ready();
    window.dispatchEvent(new CustomEvent('kitchen-client-ready'));
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
