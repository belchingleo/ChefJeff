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
      .touch-orders{position:absolute;left:max(10px,env(safe-area-inset-left));top:calc(max(4px,env(safe-area-inset-top)) + 44px);bottom:calc(max(8px,env(safe-area-inset-bottom)) + 132px);width:112px;display:flex;flex-direction:column;gap:6px;overflow-x:hidden;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--walnut) transparent;pointer-events:auto;touch-action:pan-y;overscroll-behavior:contain;padding-right:3px;box-sizing:border-box}
      .touch-order{flex:none;box-sizing:border-box;width:100%;padding:5px;background:var(--paper);border:1px solid var(--walnut);font-variant-numeric:tabular-nums;text-align:left}.touch-order.urgent{border-color:var(--tomato);color:var(--tomato)}
      .touch-order-heading{display:flex;align-items:baseline;gap:3px;min-width:0;font-size:12px;line-height:15px}.touch-order-name{flex:1;min-width:0;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.touch-order-time{flex:none;font-size:11px;color:var(--muted)}.touch-order.urgent .touch-order-time{color:var(--tomato)}
      .touch-order-patience{height:4px;border:1px solid var(--walnut);background:var(--surface);margin:3px 0 4px;overflow:hidden}.touch-order-fill{display:block;height:100%;background:var(--herb)}.touch-order.urgent .touch-order-fill{background:var(--tomato)}
      .touch-order-ingredients{display:grid;grid-template-columns:repeat(4,22px);gap:2px;justify-content:start;align-items:center;min-height:24px}.touch-order-ingredient{display:flex;align-items:center;justify-content:center;width:22px;min-height:24px}.touch-ingredient-icon{display:block;flex:none;background-repeat:no-repeat;image-rendering:pixelated}.touch-ingredient-fallback{font-size:10px;line-height:11px;max-height:22px;overflow:hidden;overflow-wrap:anywhere;text-align:center;color:var(--ink)}
      #touch-joystick{position:absolute;left:calc(max(8px,env(safe-area-inset-left)) + 2px);bottom:calc(max(8px,env(safe-area-inset-bottom)) + 4px);width:120px;height:120px;box-sizing:border-box;border:2px solid #2b1a12b3;border-radius:50%;background:transparent;box-shadow:0 0 0 1px #fdf3e1b3;pointer-events:auto;touch-action:none;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none}
      #touch-joystick::before,#touch-joystick::after{content:'';position:absolute;left:15%;right:15%;top:50%;height:1px;background:#6b34184d;pointer-events:none}#touch-joystick::after{transform:rotate(90deg)}
      #touch-stick{position:absolute;left:50%;top:50%;width:48px;height:48px;margin:-24px;border:2px solid var(--ink);border-radius:50%;box-sizing:border-box;background:transparent;box-shadow:0 0 0 1px #fdf3e1b3;color:var(--ink);text-shadow:0 0 3px var(--paper),0 0 3px var(--paper);pointer-events:none;display:grid;place-items:center;font-size:11px;font-weight:650}#touch-joystick:active #touch-stick{background:#e8983a26}
      #touch-joystick[aria-disabled=true]{opacity:.4}.touch-buttons{position:absolute;right:max(10px,env(safe-area-inset-right));bottom:calc(max(8px,env(safe-area-inset-bottom)) + 12px);display:flex;align-items:flex-end;gap:14px;pointer-events:none}
      .touch-round{display:grid;place-items:center;flex:none;border:2px solid #2b1a12cc;border-radius:50%;box-shadow:0 0 0 1px #fdf3e1b3;color:var(--ink);text-shadow:0 0 3px var(--paper),0 0 3px var(--paper);pointer-events:auto;touch-action:none;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;font-size:15px;font-weight:750;padding:6px;box-sizing:border-box;line-height:1.2}
      #touch-action{width:72px;height:72px;background:transparent}
      #touch-dash{position:relative;width:54px;height:54px;font-size:12px;background:transparent}
      .touch-round:disabled{color:var(--muted);opacity:.6}#touch-dash[data-cooling=true]{opacity:1}#touch-dash[data-cooling=true]::before{content:'';position:absolute;inset:-8px;border-radius:50%;background:conic-gradient(var(--honey) var(--cooldown,0%),var(--walnut) 0);-webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 4px),#000 0);mask:radial-gradient(farthest-side,transparent calc(100% - 4px),#000 0);pointer-events:none}
      #touch-cancel{position:absolute;right:calc(max(10px,env(safe-area-inset-right)) + 7px);bottom:calc(max(8px,env(safe-area-inset-bottom)) + 102px);width:146px;min-height:48px;display:grid;place-items:center;box-sizing:border-box;border:2px dashed var(--tomato);background:#fdf3e126;color:var(--tomato);text-shadow:0 0 3px var(--paper),0 0 3px var(--paper);font-size:13px;pointer-events:none}#touch-cancel[data-selected=true]{border-style:solid;background:#b8321e26}
      .touch-hint{position:absolute;left:146px;right:174px;bottom:max(9px,env(safe-area-inset-bottom));text-align:center;pointer-events:none;color:var(--paper);background:#2b1a1266;text-shadow:0 1px 2px var(--ink);padding:4px 8px;border:1px solid #6b341866;font-size:12px;line-height:1.4;border-radius:2px;max-height:50px;overflow:hidden;box-sizing:border-box}
      #touch-ai{position:absolute;right:max(10px,env(safe-area-inset-right));top:calc(max(4px,env(safe-area-inset-top)) + 40px);max-width:200px;max-height:32px;box-sizing:border-box;padding:3px 6px;border:1px solid #6b341866;background:#2b1a1266;text-shadow:0 1px 2px var(--ink);overflow:hidden;font-size:11px;line-height:12px;color:var(--paper);text-align:left;pointer-events:none;overflow-wrap:anywhere}
      #touch-hand{display:block;font-weight:650;line-height:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}#touch-status{display:block;line-height:14px;max-height:28px;overflow:hidden}.touch-menu{position:absolute;left:max(12px,env(safe-area-inset-left));right:max(12px,env(safe-area-inset-right));top:calc(max(4px,env(safe-area-inset-top)) + 76px);bottom:max(8px,env(safe-area-inset-bottom));margin:auto;max-width:560px;box-sizing:border-box;overflow:auto;overscroll-behavior:contain;background:var(--paper);border:3px solid var(--walnut);box-shadow:5px 5px 0 var(--ink);padding:14px 18px;pointer-events:auto;touch-action:pan-y;text-align:center}
      .touch-menu h2{margin:0 0 5px;font-size:23px;line-height:1.2}.touch-menu p{white-space:pre-line;margin:5px 0 10px;font-size:14px;line-height:1.45;color:var(--muted)}.touch-menu-actions{display:flex;justify-content:center;gap:8px;flex-wrap:wrap}.touch-menu button{min-height:40px;font-size:14px;line-height:1.2;touch-action:manipulation}.touch-menu .primary{min-width:152px}.touch-menu-secondary{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;margin-top:10px}.touch-levels{display:flex;justify-content:center;gap:6px;flex-wrap:wrap;margin:10px 0}.touch-levels button{min-height:34px;padding:6px 10px;font-size:12px}.touch-levels button[aria-pressed=true]{background:var(--honey)}
      #kitchen-touch-landscape{position:fixed;inset:0;z-index:50;display:grid;place-items:center;padding:max(20px,env(safe-area-inset-top)) max(20px,env(safe-area-inset-right)) max(20px,env(safe-area-inset-bottom)) max(20px,env(safe-area-inset-left));box-sizing:border-box;background:var(--frame);text-align:center;color:var(--paper)}#kitchen-touch-landscape .panel{padding:24px;max-width:370px;text-align:center}#kitchen-touch-landscape h2{font-size:24px;margin:10px 0}#kitchen-touch-landscape p{color:var(--muted);font-size:15px;line-height:1.6;margin:8px 0 0}.touch-rotate-icon{font-size:46px;line-height:1}
      body.kitchen-touch-mode #kitchen-display-hint{display:none}body.kitchen-touch-mode #GameDiv{height:100dvh!important}body.kitchen-touch-mode #GameCanvas{touch-action:none;-webkit-touch-callout:none}
      body.kitchen-touch-mode #kitchen-communication{left:auto;right:max(10px,env(safe-area-inset-right));top:calc(max(4px,env(safe-area-inset-top)) + 44px);bottom:auto;transform:none;width:min(300px,calc(100vw - 24px));max-height:calc(var(--touch-vh,100dvh) - 58px);overflow:auto;z-index:30;font:14px/20px var(--body);touch-action:pan-y}body.kitchen-touch-mode #kitchen-communication:not([data-touch-open=true]){display:none!important}
      body.kitchen-touch-mode #kitchen-communication button{min-height:40px;font-size:14px}body.kitchen-touch-mode #kitchen-communication .key{display:none}body.kitchen-touch-mode #communication-toggle{display:none}
      body.kitchen-touch-mode dialog.panel{max-height:calc(var(--touch-vh,100dvh) - 12px);max-width:calc(100vw - env(safe-area-inset-left) - env(safe-area-inset-right) - 20px);font-size:15px;touch-action:pan-y;overscroll-behavior:contain}body.kitchen-touch-mode .dlg-head{padding:10px 14px;gap:8px}body.kitchen-touch-mode .dlg-head h2{font-size:20px;line-height:24px}body.kitchen-touch-mode .dlg-body{padding:12px 14px}body.kitchen-touch-mode .tabs{padding:0 14px 8px;gap:4px}body.kitchen-touch-mode .dlg-foot{padding:0 14px 14px}body.kitchen-touch-mode .sr-label{display:none}body.kitchen-touch-mode input,body.kitchen-touch-mode textarea,body.kitchen-touch-mode select{font-size:16px!important;-webkit-user-select:text;user-select:text;-webkit-touch-callout:default;touch-action:auto}
      body.kitchen-touch-mode #kitchen-bookmark-toast{left:50%;bottom:154px;transform:translateX(-50%);max-width:calc(100vw - 32px);font:13px/18px var(--body)}
      @media(max-width:700px){.touch-toolbar{gap:4px;padding:0 4px}.touch-toolbar button{padding:3px 6px}.touch-clock{font-size:14px}.touch-money{font-size:12px}#touch-served{display:none}#touch-joystick{width:112px;height:112px}.touch-orders{bottom:calc(max(8px,env(safe-area-inset-bottom)) + 124px)}.touch-buttons{gap:10px}.touch-hint{left:132px;right:160px;font-size:11px}.touch-menu{padding:10px 12px}.touch-menu h2{font-size:20px}.touch-menu button{min-height:36px;font-size:13px}}
      /* Phone layout refinements: the hand/hint line lives in the toolbar so nothing covers the
         kitchen's bottom row; the stick floats to the thumb; the aim needle turns through 360 degrees. */
      #kitchen-touch-ui,#kitchen-touch-ui *{-webkit-user-select:none;user-select:none;-webkit-touch-callout:none}
      .touch-toolbar{height:34px}
      .touch-toolbar .touch-hint{position:static;flex:1;min-width:0;display:flex;align-items:baseline;justify-content:center;gap:8px;padding:2px 8px;margin:0 6px;background:transparent;color:var(--ink);text-shadow:none;font-size:12px;line-height:15px;overflow:hidden;white-space:nowrap}
      .touch-toolbar .touch-hint #touch-hand{flex:none;max-width:45%;overflow:hidden;text-overflow:ellipsis}
      .touch-toolbar .touch-hint #touch-status{flex:0 1 auto;min-width:0;max-height:none;overflow:hidden;text-overflow:ellipsis;color:var(--muted)}
      #touch-zone{position:absolute;left:0;bottom:0;width:42%;height:58%;pointer-events:auto;touch-action:none;background:transparent}
      #touch-joystick{z-index:1}#touch-joystick[data-floating=true]{bottom:auto;transition:none}
      .touch-buttons{flex-direction:column;align-items:center;gap:14px}
      #touch-action{position:relative;overflow:visible}
      .touch-order.urgent{animation:touch-urgent 1s steps(2,jump-none) infinite}
      @keyframes touch-urgent{50%{background:#f6d9c8}}
      @media(prefers-reduced-motion:reduce){.touch-order.urgent{animation:none}}
      .touch-menu button,.touch-menu-actions button,body.kitchen-touch-mode dialog.panel button{min-height:44px}
      @media(max-width:700px){.touch-toolbar .touch-hint{font-size:11px;gap:5px}.touch-buttons{gap:10px}}
      /* Plain translucent controls, as in most mobile games: a stick ring with a knob, round buttons with a
         one-word label. Dark see-through fill under a white outline reads on light and dark ground. */
      #touch-joystick{width:124px;height:124px;border:2px solid #ffffffbf;background:#2b1a1229;box-shadow:0 0 0 1px #2b1a1240}
      #touch-joystick::before,#touch-joystick::after{display:none}
      #touch-stick{width:54px;height:54px;margin:-27px;border:2px solid #ffffffe6;background:#2b1a1252;box-shadow:none;font-size:0;color:transparent;text-shadow:none}
      #touch-joystick[data-aiming=true] #touch-stick{background:#2a5a9e80}
      #touch-joystick[aria-disabled=true]{opacity:.45}
      .touch-round{border:2px solid #ffffffd9;box-shadow:0 0 0 1px #2b1a1259;color:#fff;text-shadow:0 1px 2px #2b1a12;font-weight:750;place-items:center;background-image:none;transition:background-color .06s,transform .06s}
      #touch-action{width:80px;height:80px;padding:0;font-size:16px;background-color:#2b1a1247}
      #touch-action[data-pressed=true]{background-color:#2b1a1275;transform:scale(.95)}
      #touch-action[data-aiming=true]{background-color:#2a5a9e80}
      #touch-dash{width:58px;height:58px;padding:0;font-size:14px;background-color:#2b1a1240}
      #touch-dash:active:not(:disabled){background-color:#2b1a1275;transform:scale(.95)}
            /* Unavailable keeps the label legible on any ground: lighter fill and outline, not a faded button. */
      #touch-action:disabled,#touch-dash:disabled{opacity:1;color:#ffffffd9;border-color:#ffffff8c;background-color:#2b1a1230;text-shadow:0 1px 2px #2b1a12,0 0 4px #2b1a12}
      #touch-dash[data-cooling=true]{opacity:1}
      /* Diagonal pair: Action in the corner, Dash up-left of it at 45 degrees; Cancel appears straight
         above Action while aiming, in the same round translucent style, red while the finger is on it. */
      .touch-buttons{width:80px;height:80px;display:block}
      #touch-action{position:absolute;right:0;bottom:0}
      /* Arc around Action (centre 40,40 from the corner, radius 82): Dash at 165deg, Cancel at 100deg. */
      #touch-dash{position:absolute;right:89px;bottom:32px}
      #touch-cancel{right:calc(max(10px,env(safe-area-inset-right)) + 28px);bottom:calc(max(8px,env(safe-area-inset-bottom)) + 12px + 95px);width:52px;height:52px;min-height:0;border:2px solid #ffffffd9;border-radius:50%;background:#2b1a1247;box-shadow:0 0 0 1px #2b1a1259;color:#fff;text-shadow:0 1px 2px #2b1a12;font-size:14px;font-weight:750}
      /* Narrow phones: slightly smaller arc (Action 72, Dash 52, Cancel 48, radius 74) so it clears the kitchen. */
      @media(max-width:700px){.touch-buttons{width:72px;height:72px}#touch-action{width:72px;height:72px}#touch-dash{width:52px;height:52px;right:81px;bottom:29px}#touch-cancel{width:48px;height:48px;right:calc(max(10px,env(safe-area-inset-right)) + 25px);bottom:calc(max(8px,env(safe-area-inset-bottom)) + 12px + 87px)}}
      #touch-cancel[data-selected=true]{border-style:solid;border-color:#fff;background:#b8321ecc;transform:scale(1.12)}
    `;
    document.head.appendChild(style);
    const ui = document.createElement('div');
    ui.id = 'kitchen-touch-ui';
    ui.hidden = true;
    ui.setAttribute('data-no-i18n', '');
    ui.innerHTML = `
      <header class="touch-toolbar"><strong id="touch-clock" class="touch-clock"></strong><span id="touch-money" class="touch-money"></span><span id="touch-served"></span><div id="touch-hint" class="touch-hint touch-spacer"><span id="touch-hand"></span><span id="touch-status" role="status" aria-live="polite"></span></div><button id="touch-pause" class="btn" type="button"></button><button id="touch-communication" class="btn" type="button" aria-expanded="false" aria-controls="kitchen-communication"></button><button id="touch-bookmark" class="btn" type="button"></button><button id="touch-menu-toggle" class="btn" type="button" aria-expanded="false" aria-controls="touch-menu"></button></header>
      <div id="touch-orders" class="touch-orders" role="region" aria-label="订单" tabindex="0"></div>
      <div id="touch-zone" aria-hidden="true"></div>
      <div id="touch-joystick" role="group" aria-label="移动" aria-disabled="true"><div id="touch-stick"></div></div>
      <div class="touch-buttons"><button id="touch-dash" class="touch-round" type="button"></button><button id="touch-action" class="touch-round" type="button"></button></div>
      <div id="touch-cancel" hidden></div>
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
    const orderNodes = new Map();
    let lastEvent = '', eventNotice = '', eventTimer;
    let pausePending = false, wasAiming = false;
    // Short haptic ticks where the browser supports them (Android Chrome); iOS Safari ignores this.
    const buzz = ms => { try { navigator.vibrate?.(ms); } catch (_) {} };
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
      if (joystick.dataset.floating === 'true') { joystick.dataset.floating = 'false'; joystick.style.left = joystick.style.top = ''; }
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
      // Transparent controls overlay the kitchen, leaving more room for its art.
      // Keep the narrow vertical order rail and a short bottom hint clear; the browser resolves
      // safe-area padding for notches and the home indicator.
      const safe = window.getComputedStyle(ui);
      // Equal side margins keep the kitchen centred (orders rail left, buttons right); the margin clears
      // the button arc's left edge (Dash) plus 8px, which is narrower on phones under 700px.
      const side = w <= 700 ? 152 : 166;
      const left = (parseFloat(safe.paddingLeft) || 0) + side;
      const right = (parseFloat(safe.paddingRight) || 0) + side;
      const top = (parseFloat(safe.paddingTop) || 0) + 40;
      const bottom = (parseFloat(safe.paddingBottom) || 0) + 6;
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
      el('touch-zone').hidden = joystick.hidden;
      el('touch-ai').hidden = joystick.hidden;
      action.disabled = !playing || !(state.canInteract || state.canThrow);
      const sprint = state.sprint || {};
      const cooling = (sprint.cooldown_remaining || 0) > 0;
      dash.disabled = !playing || !state.canDash || aiming || cooling || (sprint.active_remaining || 0) > 0;
      dash.dataset.cooling = String(cooling);
      dash.style.setProperty('--cooldown', Math.max(0, Math.min(100, (sprint.cooldown_remaining || 0) / 3 * 100)) + '%');
      text('touch-dash', cooling ? Math.ceil(sprint.cooldown_remaining) + 's' : '冲刺');
      el('touch-cancel').hidden = !playing || actionPointer === null || !(state.holding && state.canThrow);
      // One word, like other mobile games; the toolbar line names the exact action.
      text('touch-action', aiming ? '投掷' : '操作');
      text('touch-stick', aiming ? '瞄准' : '移动');
      joystick.dataset.aiming = String(aiming); action.dataset.aiming = String(aiming);
      if (aiming && !wasAiming) buzz(12);
      wasAiming = aiming;
      text('touch-hand', state.handLabel || '');
      text('touch-ai', state.aiStatus || '');
      text('touch-status', cancelSelected ? '松手取消' : aiming ? '松开投掷' : eventNotice || state.interactionHint || (state.holding && state.canThrow ? '长按投掷' : ''));
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
      renderOrders(state.orders || []);
    }
    function sprite(icon, label) {
      const image = document.createElement('span');
      image.setAttribute('title', label); image.setAttribute('aria-label', label);
      const values = icon && [icon.x, icon.y, icon.width, icon.height, icon.atlasWidth, icon.atlasHeight];
      if (!icon?.url || !values.every(Number.isFinite) || icon.width <= 0 || icon.height <= 0 || icon.atlasWidth <= 0 || icon.atlasHeight <= 0) {
        image.className = 'touch-ingredient-fallback'; image.textContent = label;
        return image;
      }
      let [left, top, right, bottom] = icon.alphaBBox || [0, 0, icon.width, icon.height];
      if (![left, top, right, bottom].every(Number.isFinite) || left < 0 || top < 0 || right > icon.width || bottom > icon.height || right <= left || bottom <= top)
        [left, top, right, bottom] = [0, 0, icon.width, icon.height];
      const scale = Math.min(22 / (right - left), 24 / (bottom - top));
      image.className = 'touch-ingredient-icon'; image.setAttribute('role', 'img');
      image.style.width = ((right - left) * scale) + 'px'; image.style.height = ((bottom - top) * scale) + 'px';
      image.style.backgroundImage = 'url(' + JSON.stringify(icon.url) + ')';
      image.style.backgroundSize = (icon.atlasWidth * scale) + 'px ' + (icon.atlasHeight * scale) + 'px';
      image.style.backgroundPosition = (-(icon.x + left) * scale) + 'px ' + (-(icon.y + top) * scale) + 'px';
      return image;
    }
    function renderOrders(orders) {
      const rail = el('touch-orders'), ids = orders.map(order => String(order.id));
      for (const [id, row] of orderNodes) if (!ids.includes(id)) { row.ticket.remove(); orderNodes.delete(id); }
      for (const order of orders) {
        const id = String(order.id), name = t(String(order.dishName || order.dish || ''));
        let row = orderNodes.get(id);
        if (!row) {
          const ticket = document.createElement('article'); ticket.className = 'touch-order'; ticket.dataset.orderId = id;
          const heading = document.createElement('div'); heading.className = 'touch-order-heading';
          const title = document.createElement('span'); title.className = 'touch-order-name';
          const time = document.createElement('span'); time.className = 'touch-order-time';
          heading.appendChild(title); heading.appendChild(time); ticket.appendChild(heading);
          const patience = document.createElement('div'); patience.className = 'touch-order-patience'; patience.setAttribute('role', 'progressbar'); patience.setAttribute('aria-valuemin', '0'); patience.setAttribute('aria-valuemax', '100');
          const fill = document.createElement('span'); fill.className = 'touch-order-fill'; patience.appendChild(fill); ticket.appendChild(patience);
          const ingredients = document.createElement('div'); ingredients.className = 'touch-order-ingredients'; ticket.appendChild(ingredients);
          row = { ticket, title, time, patience, fill, ingredients, content: '' }; orderNodes.set(id, row);
        }
        const remaining = Math.max(0, Math.ceil(order.remaining || 0));
        row.ticket.classList.toggle('urgent', remaining <= 15);
        if (row.title.textContent !== name) row.title.textContent = name;
        row.title.setAttribute('title', name);
        const timeText = remaining + 's'; if (row.time.textContent !== timeText) row.time.textContent = timeText;
        const fraction = Number.isFinite(order.patienceRemainingFraction) ? order.patienceRemainingFraction : order.patienceTotal > 0 ? Math.max(0, order.remaining || 0) / order.patienceTotal : 1;
        const percent = Math.round(Math.max(0, Math.min(1, fraction)) * 100);
        row.fill.style.width = percent + '%'; row.fill.style.backgroundColor = remaining <= 15 ? 'var(--tomato)' : fraction > .5 ? 'var(--herb)' : 'var(--honey)';
        row.patience.setAttribute('aria-valuenow', String(percent)); row.patience.setAttribute('aria-label', t('订单') + ' · ' + name);
        const details = order.ingredientDetails || (order.ingredients || []).map(ingredient => typeof ingredient === 'string' ? { id: ingredient, name: ingredient } : ingredient);
        const content = JSON.stringify([window.kitchenI18n?.language, details]);
        if (content !== row.content) {
          row.content = content; row.ingredients.replaceChildren();
          for (const ingredient of details) {
            const slot = document.createElement('span'); slot.className = 'touch-order-ingredient'; slot.dataset.ingredientId = String(ingredient.id || ingredient.name);
            const label = t(String(ingredient.name || ingredient.id || '')); slot.setAttribute('title', label);
            slot.appendChild(sprite(ingredient.icon, label)); row.ingredients.appendChild(slot);
          }
        }
      }
      const signature = JSON.stringify(ids);
      if (signature !== ordersSignature) {
        ordersSignature = signature;
        const scroll = rail.scrollTop;
        for (const id of ids) rail.appendChild(orderNodes.get(id).ticket);
        rail.scrollTop = scroll;
      }
    }
    function language() {
      for (const [id, source] of Object.entries({ 'touch-pause': '暂停', 'touch-communication': '沟通', 'touch-bookmark': '标记',
        'touch-menu-toggle': '菜单', 'touch-settings': '设置', 'touch-help': '操作说明', 'touch-end': '结束本局', 'touch-record': '本局记录',
        'touch-fullscreen': '全屏', 'touch-menu-close': '返回厨房', 'touch-cancel': '取消', 'touch-rotate-title': '请将手机横过来',
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
    // The stick returns to its corner when released; while held it stays where the thumb landed.
    const homeStick = () => { if (joystick.dataset.floating !== 'true') return; joystick.dataset.floating = 'false'; joystick.style.left = joystick.style.top = ''; };
    const joyEnd = event => { if (event.pointerId !== joyPointer) return; event.preventDefault(); const id = joyPointer; joyPointer = null; uncapture(joystick, id); stick.style.transform = 'translate(0px,0px)'; homeStick(); controls?.move(0, 0); };
    // Floating stick: a press anywhere in the lower-left zone puts the stick's centre under the thumb.
    el('touch-zone').addEventListener('pointerdown', event => {
      if (event.button > 0 || joyPointer !== null || !canPlay()) return;
      event.preventDefault();
      const size = joystick.getBoundingClientRect().width || 120, ui = el('kitchen-touch-ui').getBoundingClientRect();
      const x = Math.max(size / 2, Math.min(event.clientX - (ui.left || 0), (ui.width || innerWidth) - size / 2));
      const y = Math.max(size / 2 + 44, Math.min(event.clientY - (ui.top || 0), (ui.height || innerHeight) - size / 2));
      joystick.dataset.floating = 'true'; joystick.style.left = (x - size / 2) + 'px'; joystick.style.top = (y - size / 2) + 'px';
      joyPointer = event.pointerId; capture(joystick, joyPointer); joyMove(event);
    });
    el('touch-zone').addEventListener('contextmenu', event => event.preventDefault());
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
      if (cancelSelected || !canPlay()) controls?.cancel(); else { if (state.aiming) buzz(20); controls?.release(); }
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
      if (previousGame && previousGame !== next.game_id) { el('touch-orders').scrollTop = 0; ordersSignature = ''; }
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
