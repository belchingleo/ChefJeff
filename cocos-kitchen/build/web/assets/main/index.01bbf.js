System.register("chunks:///_virtual/KitchenAudio.ts", ["cc"], function (exports_1, context_1) {
    // source-sha256: 465d654d4be7042204f0007e4c41df7770d69cc8910dbddc0122f9f445204a92
    "use strict";
    var cc_1, STORAGE, LOOPS, MUSIC, EVENT_SOUNDS, board, cooking, KitchenAudio;
    var __moduleName = context_1 && context_1.id;
    return {
        setters: [
            function (cc_1_1) {
                cc_1 = cc_1_1;
            }
        ],
        execute: function () {
            STORAGE = 'chefjeff-audio';
            LOOPS = [
                // name, clip, fade in (s), fade out (s), start at a random offset
                ['ambience', 'amb_kitchen', 1.5, .6, false],
                ['sizzle', 'sizzle_loop', .15, .4, true],
                ['fire', 'fire_loop', .2, .5, true],
                ['wash_solo', 'wash_solo', .08, .1, true],
                ['wash_duo', 'wash_duo', .2, .2, true],
            ];
            MUSIC = ['bgm_menu', 'bgm_service', 'bgm_rush'];
            EVENT_SOUNDS = { order: 'order_new', ready: 'food_ready', burn: 'burnt_warn', fire: 'fire_ignite',
                fire_spread: 'fire_spread', served: 'serve_ok', bad_service: 'serve_bad', expired: 'order_expired', thrown: 'throw',
                caught: 'catch', dropped: 'land', plate_returned: 'plate_return' };
            board = (id) => !!id && id.startsWith('b') && !id.startsWith('bin');
            cooking = (stage) => !!stage && /^(pot_)?(cooking|chopped|ready|burnt)$/.test(stage);
            /** Presentation only: reads kitchen snapshots and plays sounds; never alters observations or rules. */
            KitchenAudio = class KitchenAudio {
                constructor() {
                    this.index = null;
                    this.clips = {};
                    this.sfx = null;
                    this.channels = {};
                    this.music = [];
                    this.musicClip = '';
                    this.last = null;
                    this.seen = new Set();
                    this.urgent = new Set();
                    this.recent = {};
                    this.lastChop = '';
                    this.endedGame = '';
                    this.menuAfter = 0;
                    this.clock = 0;
                    this.warned = false;
                    this.destroyed = false;
                    this.started = cc_1.sys.isNative;
                    this.loading = {};
                    this.volume = { music: .8, sfx: .8 };
                    this.ready = false;
                    /** Cocos resumes its suspended Web Audio context only on a canvas click, but the kitchen is played
                     *  from the keyboard. Resume the same context on any key or pointer gesture; Cocos then starts the
                     *  queued sounds itself. If engine internals change, this quietly falls back to the canvas click. */
                    this.unlock = () => this.safely(() => {
                        var _a, _b, _c;
                        this.started = true;
                        // Any source that already holds a clip has a player wired to the engine's shared context.
                        for (const src of [...this.music.map(ch => ch.src), ...Object.values(this.channels).map(ch => ch.src)]) {
                            const context = (_c = (_b = (_a = src === null || src === void 0 ? void 0 : src._player) === null || _a === void 0 ? void 0 : _a._player) === null || _b === void 0 ? void 0 : _b._gainNode) === null || _c === void 0 ? void 0 : _c.context;
                            if (!context)
                                continue;
                            if (context.state !== 'running')
                                context.resume().catch(() => { });
                            return;
                        }
                    });
                    this.onSettings = (e) => this.safely(() => { Object.assign(this.volume, e.detail || {}); });
                }
                async load(parent) {
                    try {
                        const [index, clips] = await Promise.all([
                            new Promise((ok, no) => cc_1.resources.load('audio/index', cc_1.JsonAsset, (e, a) => e ? no(e) : ok(a))),
                            // Native builds keep their existing loading path. Web audio is
                            // requested by name after a gesture, rather than downloading all
                            // 51 clips while the player is waiting for the first kitchen.
                            cc_1.sys.isNative ? new Promise((ok, no) => cc_1.resources.loadDir('audio', cc_1.AudioClip, (e, a) => e ? no(e) : ok(a))) : Promise.resolve([]),
                        ]);
                        if (this.destroyed || !parent.isValid)
                            return;
                        this.index = index.json;
                        for (const c of clips)
                            this.clips[c.name] = c;
                        const source = (name) => { const n = new cc_1.Node('audio-' + name); parent.addChild(n); const s = n.addComponent(cc_1.AudioSource); s.playOnAwake = false; return s; };
                        this.sfx = source('sfx');
                        for (const [name, clip, fadeIn, fadeOut, randomStart] of LOOPS)
                            this.channels[name] = { src: source(name), clip, level: 0, target: 0, fadeIn, fadeOut, randomStart };
                        // Two music players so the service/rush switch can crossfade.
                        this.music = [0, 1].map(i => ({ src: source('music-' + i), clip: '', level: 0, target: 0, fadeIn: 1.2, fadeOut: .8, randomStart: false }));
                        if (!cc_1.sys.isNative) {
                            try {
                                Object.assign(this.volume, JSON.parse(localStorage.getItem(STORAGE) || '{}'));
                            }
                            catch (_) { }
                            window.addEventListener('kitchen-audio-settings', this.onSettings);
                            window.addEventListener('keydown', this.unlock, true);
                            window.addEventListener('pointerdown', this.unlock, true);
                        }
                        this.ready = true;
                    }
                    catch (error) {
                        console.warn('ChefJeff audio unavailable; the kitchen stays silent.', error);
                    }
                }
                /** Sound must never break play: an audio error is reported once and that sound is skipped. */
                safely(run) {
                    try {
                        run();
                    }
                    catch (error) {
                        if (!this.warned) {
                            this.warned = true;
                            console.warn('ChefJeff audio error; the kitchen carries on without this sound.', error);
                        }
                    }
                }
                destroy() {
                    this.destroyed = true;
                    if (cc_1.sys.isNative)
                        return;
                    window.removeEventListener('kitchen-audio-settings', this.onSettings);
                    window.removeEventListener('keydown', this.unlock, true);
                    window.removeEventListener('pointerdown', this.unlock, true);
                }
                gain(name) { var _a, _b, _c, _d, _e, _f; return (_f = (_c = (_b = (_a = this.index) === null || _a === void 0 ? void 0 : _a.sounds[name]) === null || _b === void 0 ? void 0 : _b.gain) !== null && _c !== void 0 ? _c : (_e = (_d = this.index) === null || _d === void 0 ? void 0 : _d.wash[name]) === null || _e === void 0 ? void 0 : _e.gain) !== null && _f !== void 0 ? _f : .8; }
                ensureClip(name) {
                    if (this.clips[name])
                        return Promise.resolve(this.clips[name]);
                    if (!this.started || this.destroyed || !name)
                        return Promise.resolve(null);
                    if (!this.loading[name])
                        this.loading[name] = new Promise(resolve => {
                            cc_1.resources.load('audio/' + name, cc_1.AudioClip, (error, clip) => {
                                if (error || this.destroyed) {
                                    if (error && !this.warned) {
                                        this.warned = true;
                                        console.warn('ChefJeff sound unavailable: ' + name, error);
                                    }
                                    resolve(null);
                                    return;
                                }
                                this.clips[name] = clip;
                                resolve(clip);
                            });
                        });
                    return this.loading[name];
                }
                play(name, scale = 1, minGap = .06) { this.safely(() => this.playNow(name, scale, minGap)); }
                playNow(name, scale, minGap) {
                    var _a;
                    if (!this.ready || !this.sfx || this.volume.sfx <= 0 || this.destroyed)
                        return;
                    const clip = this.clips[name];
                    if (!clip) {
                        const at = this.clock;
                        this.ensureClip(name).then(loaded => {
                            // Never replay an old event after a slow download.
                            if (loaded && !this.destroyed && this.clock - at <= .35)
                                this.play(name, scale, minGap);
                        });
                        return;
                    }
                    if (this.clock - ((_a = this.recent[name]) !== null && _a !== void 0 ? _a : -1) < minGap)
                        return;
                    this.recent[name] = this.clock;
                    this.sfx.playOneShot(clip, Math.min(1, this.gain(name) * this.volume.sfx * scale));
                }
                /** One knife strike, fired by the chop animation at the moment the blade meets the board. */
                chop() { this.safely(() => this.chopNow()); }
                chopNow() {
                    var _a;
                    const pool = ((_a = this.index) === null || _a === void 0 ? void 0 : _a.chop) || [];
                    if (!pool.length)
                        return;
                    let name = pool[Math.floor(Math.random() * pool.length)];
                    if (name === this.lastChop && pool.length > 1)
                        name = pool[(pool.indexOf(name) + 1) % pool.length];
                    this.lastChop = name;
                    this.playNow(name, .8 + Math.random() * .2, 0);
                }
                onState(s) { this.safely(() => this.applyState(s)); }
                applyState(s) {
                    if (!this.ready)
                        return;
                    const prev = this.last;
                    this.last = s;
                    const k = s.kitchen, fresh = !prev || prev.game_id !== s.game_id;
                    if (fresh) {
                        this.seen = new Set((s.events || []).map((e) => e.t + '|' + e.message));
                        this.urgent.clear();
                    }
                    this.phaseMusic(prev, s, fresh);
                    const running = s.phase === 'running';
                    if (!fresh && running) {
                        const events = (s.events || []).filter((e) => !this.seen.has(e.t + '|' + e.message));
                        for (const e of events) {
                            this.seen.add(e.t + '|' + e.message);
                            if (e.kind === 'landed')
                                this.play(/落到/.test(e.message) ? 'place_board' : 'land');
                            else if (EVENT_SOUNDS[e.kind])
                                this.play(EVENT_SOUNDS[e.kind]);
                        }
                        if (this.seen.size > 80)
                            this.seen = new Set(Array.from(this.seen).slice(-40));
                        const skip = new Set(events.filter((e) => ['thrown', 'dropped', 'interrupted', 'served', 'bad_service'].includes(e.kind)).map((e) => e.actor));
                        for (const who of Object.keys(k.chefs))
                            if (!skip.has(who))
                                this.chefChange(prev.kitchen.chefs[who], k.chefs[who]);
                        this.stationChanges(prev.kitchen, k);
                        for (const o of k.orders || [])
                            if (o.status === 'pending' && o.remaining <= 10 && o.remaining > 0 && !this.urgent.has(o.id)) {
                                this.urgent.add(o.id);
                                this.play('order_urgent');
                            }
                    }
                    const stations = Object.values(k.stations || {});
                    const washers = Object.values(k.chefs).filter((c) => c.action_kind === 'wash' && c.working).length;
                    this.channels.ambience.target = running || s.phase === 'ready' ? 1 : 0;
                    this.channels.sizzle.target = running && stations.some(st => { var _a; return st.stove && st.heating && !st.fire && cooking((_a = st.food) === null || _a === void 0 ? void 0 : _a.stage); }) ? 1 : 0;
                    this.channels.fire.target = running && stations.some(st => st.fire) ? 1 : 0;
                    this.channels.wash_solo.target = running && washers === 1 ? 1 : 0;
                    this.channels.wash_duo.target = running && washers >= 2 ? 1 : 0;
                }
                chefChange(a, b) {
                    var _a, _b, _c, _d;
                    const before = a.holding, after = b.holding, kind = a.action_kind || b.action_kind, target = a.target || b.target;
                    const sameItem = before && after && before.id === after.id;
                    // Sounds follow confirmed hand changes only (Overcooked 2's OnCarriedItemChanged): a failed press is silent.
                    if (sameItem && before.contents && !after.contents && (kind === 'empty_pot' || kind === 'discard')) {
                        this.play('discard');
                        return;
                    }
                    if (sameItem && before.stage !== after.stage) {
                        if (kind === 'assemble')
                            this.play('assemble');
                        else if (kind === 'empty_pot' || kind === 'discard')
                            this.play('discard');
                        else if (/^plate|merge/.test(kind || ''))
                            this.play('plate_place');
                        return;
                    }
                    if (after && !sameItem) {
                        this.play(kind === 'fetch' && target === 'fridge' ? 'fridge_grab' : 'pickup');
                        return;
                    }
                    if (before && !after) {
                        if (['discard', 'empty_pot'].includes(kind))
                            this.play('discard');
                        else if (target === 'serve' || ((_d = (_c = (_b = (_a = this.last) === null || _a === void 0 ? void 0 : _a.kitchen) === null || _b === void 0 ? void 0 : _b.stations) === null || _c === void 0 ? void 0 : _c[target]) === null || _d === void 0 ? void 0 : _d.stove))
                            return; // serving/pan sounds come from events/stations
                        else if (board(target))
                            this.play('place_board');
                        else
                            this.play(/plate/.test(before.stage) ? 'plate_place' : 'place_board');
                        return;
                    }
                    // Finished an assembly or plating job without a hand change (e.g. building on the counter).
                    if (a.job_id && a.job_id !== b.job_id && a.working && (a.action_kind === 'assemble' || /^plate|merge/.test(a.action_kind || '')))
                        this.play(a.action_kind === 'assemble' ? 'assemble' : 'plate_place');
                }
                stationChanges(a, b) {
                    var _a, _b, _c;
                    for (const [key, n] of Object.entries(b.stations || {})) {
                        const p = (_a = a.stations) === null || _a === void 0 ? void 0 : _a[key];
                        if (!p)
                            continue;
                        if (p.fire && !n.fire)
                            this.play('extinguisher');
                        if (n.stove && cooking((_b = n.food) === null || _b === void 0 ? void 0 : _b.stage) && /cooking|chopped/.test(n.food.stage) && !cooking((_c = p.food) === null || _c === void 0 ? void 0 : _c.stage))
                            this.play('pan_sizzle_start');
                    }
                }
                phaseMusic(prev, s, fresh) {
                    const was = prev === null || prev === void 0 ? void 0 : prev.phase, now = s.phase;
                    if (!fresh && was === 'running' && now === 'paused')
                        this.play('ui_pause');
                    if (!fresh && was === 'paused' && now === 'running')
                        this.play('ui_resume');
                    if (now === 'ended' && !fresh && was !== 'ended' && this.endedGame !== s.game_id) {
                        this.endedGame = s.game_id;
                        this.setMusic('');
                        this.play(s.won ? 'jingle_win' : 'jingle_lose', 1, 0);
                        this.menuAfter = this.clock + (s.won ? 3.5 : 2.3);
                        return;
                    }
                    if (now === 'ended') {
                        if (this.menuAfter && this.clock < this.menuAfter)
                            return;
                        this.setMusic('bgm_menu');
                        return;
                    }
                    if (now === 'running')
                        this.setMusic(s.kitchen.round_remaining <= 30 ? 'bgm_rush' : 'bgm_service');
                    else if (now === 'paused')
                        this.setMusic('');
                    else
                        this.setMusic('bgm_menu');
                }
                setMusic(name) {
                    if (name === this.musicClip)
                        return;
                    this.musicClip = name;
                    for (const ch of this.music)
                        if (ch.clip !== name)
                            ch.target = 0;
                    if (!name)
                        return;
                    // Pausing keeps the position, so resuming the same piece continues where it stopped.
                    const same = this.music.find(ch => ch.clip === name);
                    if (same) {
                        same.target = 1;
                        return;
                    }
                    const free = this.music[0].level <= this.music[1].level ? this.music[0] : this.music[1];
                    free.src.stop();
                    free.clip = name;
                    free.src.clip = this.clips[name] || null;
                    free.level = 0;
                    free.target = 1;
                }
                update(dt) { this.safely(() => this.tick(dt)); }
                tick(dt) {
                    var _a;
                    this.clock += dt;
                    if (!this.ready)
                        return;
                    if (this.menuAfter && this.clock >= this.menuAfter) {
                        this.menuAfter = 0;
                        if (((_a = this.last) === null || _a === void 0 ? void 0 : _a.phase) === 'ended')
                            this.setMusic('bgm_menu');
                    }
                    for (const ch of Object.values(this.channels))
                        this.step(ch, dt, this.volume.sfx, true);
                    for (const ch of this.music)
                        this.step(ch, dt, this.volume.music, false);
                }
                step(ch, dt, master, sfx) {
                    const clip = this.clips[ch.clip];
                    if (!clip) {
                        ch.level = 0;
                        if (master > 0 && ch.target > 0)
                            this.ensureClip(ch.clip);
                        return;
                    }
                    const rate = ch.target > ch.level ? 1 / ch.fadeIn : 1 / ch.fadeOut;
                    ch.level = ch.target > ch.level ? Math.min(ch.target, ch.level + dt * rate) : Math.max(ch.target, ch.level - dt * rate);
                    const src = ch.src;
                    if (ch.level > 0 && master > 0) {
                        if (src.clip !== clip)
                            src.clip = clip;
                        src.loop = true;
                        if (!src.playing) {
                            src.play();
                            if (ch.randomStart && sfx)
                                src.currentTime = Math.random() * Math.max(0, clip.getDuration() - .2);
                        }
                        src.volume = ch.level * this.gain(ch.clip) * master;
                    }
                    else if (src.playing) {
                        // Loops pause at silence; texture loops restart elsewhere next time, music resumes in place.
                        if (sfx && ch.randomStart)
                            src.stop();
                        else
                            src.pause();
                    }
                }
            };
            exports_1("KitchenAudio", KitchenAudio);
        }
    };
});

System.register("chunks:///_virtual/KitchenClient.ts", ["cc", "./LevelOneArt.ts", "./KitchenAudio.ts", "./KitchenGeometry.ts"], function (exports_1, context_1) {
    // source-sha256: 37f1382af61252b0e2b56992d850ccb8de1a0a9da597eb39dc38fc0f11179375
    "use strict";
    var __decorate = (this && this.__decorate) || function (decorators, target, key, desc) {
        var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
        if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
        else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
        return c > 3 && r && Object.defineProperty(target, key, r), r;
    };
    var cc_1, cc_2, LevelOneArt_1, KitchenAudio_1, KitchenGeometry_1, ccclass, COLORS, PIXEL, CUE_SECONDS, NETWORK_GRACE_SECONDS, RESULT_ANNOUNCE, TAB_ORDER, STAGES, VESSEL_ART_FALLBACK, FOOD_COLORS, TILE, MAPX, MAPY, KNIFE_VIEW, color, AIM_HOLD, FACING_DIR, KitchenClient;
    var __moduleName = context_1 && context_1.id;
    return {
        setters: [
            function (cc_1_1) {
                cc_1 = cc_1_1;
                cc_2 = cc_1_1;
            },
            function (LevelOneArt_1_1) {
                LevelOneArt_1 = LevelOneArt_1_1;
            },
            function (KitchenAudio_1_1) {
                KitchenAudio_1 = KitchenAudio_1_1;
            },
            function (KitchenGeometry_1_1) {
                KitchenGeometry_1 = KitchenGeometry_1_1;
            }
        ],
        execute: function () {
            cc_1.cclegacy._RF.push({}, "7dafalzrH9GT4bSNEmN6gVT", 'KitchenClient', undefined);
            ccclass = cc_2._decorator.ccclass;
            // Tokens from the "ChefJeff 厨房 UI" design system: every colour is sampled from the art
            // (denim overalls, copper-eared Jeff, honey floorboards, walnut walls, steel stoves).
            COLORS = { ink: '#2b1a12', muted: '#6e4e38', bg: '#f0d9b5', paper: '#fdf3e1', honeyTint: '#fbe3b8', walnut: '#6b3418', honey: '#e8983a', steel: '#3d5566',
                human: '#2a5a9e', humanHover: '#224a82', jeff: '#a8520e', herb: '#3c7a2a', hot: '#b8321e', hotHover: '#9c2a19',
                // alert: danger text on the surface ground (the hot red itself is 4.35:1 there).
                alert: '#9c2a19', frame: '#4a2616',
                // Fallback programmer art only.
                wood: '#6b3418', wall: '#ae8055', counter: '#8baab7', counterEdge: '#587582', counterLight: '#c6d9de' };
            // Pixel face for titles, buttons, tags and HUD numbers (loaded by the web shell); body text stays system.
            PIXEL = 'ChefJeffPixel, sans-serif';
            // Result events reach the player; AI decision notes have their own status line.
            CUE_SECONDS = .16;
            // Seconds without any state before the page calls it a disconnect (below the server's 8 s auto-pause).
            NETWORK_GRACE_SECONDS = 6;
            RESULT_ANNOUNCE = new Set(['order', 'served', 'expired', 'ready', 'burn', 'fire', 'fire_spread', 'fire_loss']);
            // Keyboard order; the level buttons (one per listed level, from the server) follow the language button.
            TAB_ORDER = ['language', 'more', 'level-picker', 'main', 'reset', 'cover-connection', 'help', 'record', 'contribute', 'resume', 'pause', 'end'];
            // Labels for things that are not recipe items; item and dish names come from the server's catalog.
            STAGES = { extinguisher: '灭火器', clean_plate: '干净餐盘', dirty_plate: '脏餐盘' };
            // Art stem for a vessel kind that has no art of its own yet (the soup pot's frames).
            VESSEL_ART_FALLBACK = 'pot';
            // Fallback tints by stage, for items without a colour; burnt is charred for every item.
            FOOD_COLORS = { raw: '#d68f8c', chopped: '#dcaa86', cooking: '#b58359', ready: '#846144', burnt: '#3e3733', extinguisher: '#c65138' };
            TILE = KitchenGeometry_1.GRID_ART.tile, MAPX = KitchenGeometry_1.GRID_ART.originX, MAPY = KitchenGeometry_1.GRID_ART.originY;
            // Knife frames per facing: front view toward the viewer, top view up-screen, side view (mirrored for left).
            KNIFE_VIEW = { down: ['knife/v1/front_', false], up: ['knife/v1/top_', false], right: ['knife/v1/side_', false], left: ['knife/v1/side_', true] };
            color = (hex) => new cc_2.Color().fromHEX(hex);
            AIM_HOLD = .3;
            FACING_DIR = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
            KitchenClient = class KitchenClient extends cc_2.Component {
                constructor() {
                    var _a;
                    super(...arguments);
                    this.state = null;
                    this.art = new LevelOneArt_1.LevelOneArt();
                    this.artLoaded = false;
                    this.audio = new KitchenAudio_1.KitchenAudio();
                    this.knifePhase = {};
                    this.pending = false;
                    this.polling = false;
                    this.lastScheduledPoll = -Infinity;
                    this.hidden = false;
                    this.connected = false;
                    this.clock = 0;
                    this.activeClock = 0;
                    this.heldKeys = new Set();
                    this.moveSeq = Date.now() * 1000;
                    this.lastMoveAt = 0;
                    this.manualDirection = { x: 0, y: 0 };
                    this.touchDirection = { x: 0, y: 0 };
                    this.touchMoveDirty = false;
                    this.touchMoveAt = -Infinity;
                    /** As in Overcooked: after a throw or once work starts, the direction still held does not walk until it
                     * returns to neutral or turns 15 degrees, so a held stick or key cannot cancel or follow the action. */
                    this.heldThrough = null;
                    this.pickedAt = -Infinity;
                    this.sprintAt = -Infinity;
                    this.touchBlocked = false;
                    this.touchLayout = null;
                    this.touchNodeVisibility = new Map();
                    this.controls = null;
                    this.controlsSignature = '';
                    // Hold Space to aim a throw (Overcooked-style): after AIM_HOLD seconds the chef stops, a translucent
                    // arc guides the direction and maximum range; direction keys turn it, and releasing Space throws along it.
                    this.spaceDownAt = null;
                    this.spaceItemId = null;
                    // Touch Throw arms the same hold, but a release before AIM_HOLD throws straight ahead instead of interacting.
                    this.tossOnly = false;
                    this.aiming = null;
                    this.aimArrow = null;
                    // Overcooked-style local movement: this page walks the player's chef itself and reports where it is
                    // (/api/position); the engine follows with the same physics. Only a resync from the engine (a push,
                    // a blocked walk, a report too far ahead) moves the chef here to the engine's position.
                    this.predicted = null;
                    /** Held-key walk in whole server ticks: position at the last tick, the next one, and the progress between. */
                    this.walkRamp = 0;
                    this.resyncSeen = -1;
                    /** Jeff blocks the local walk: the engine walks with the held direction (pushing or sliding) and this page follows. */
                    this.pressing = false;
                    this.lastPress = false;
                    this.lastReported = null;
                    this.lastReportAt = -1;
                    /** Space's station as this page picks it each frame (Overcooked 2-style, highlighted at once);
                     * undefined outside a round, where the engine's own focus is shown. */
                    this.localPick = undefined;
                    /** The last held direction (any angle): what the station is picked by. */
                    this.lastAim = null;
                    this.stateSentAt = 0;
                    this.handsBusyUntil = -1;
                    /** Until when the chef leans toward what it acts on: instant feedback while the action goes to the server. */
                    this.cueUntil = -1;
                    /** Page diagnostics for the data export (never sent anywhere by the page): the last 30 s of running
                     * frames, sampled 5 times a second, and update-loop errors, each kept once with a count. */
                    this.frames = [];
                    this.frameAt = -Infinity;
                    this.loopErrors = [];
                    this.qaNoMotion = !cc_2.sys.isNative && new URLSearchParams(location.search).get('qaMotion') === 'off';
                    // Isolated visual pilot; not enabled at the fixed gameplay entry.
                    this.prepSample = !cc_2.sys.isNative && new URLSearchParams(location.search).get('prepSample') === '1';
                    this.prepPoses = {};
                    // Knife-only comparison: same normal scene and actor in both variants.
                    this.knifeSample = !cc_2.sys.isNative && new URLSearchParams(location.search).get('knifeSample') === '1';
                    this.knifeProbe = null;
                    this.cutProbe = null;
                    this.chopImpacts = {};
                    // Throw poses: the human winds up while aiming; either chef shows the release briefly after a throw.
                    this.throwReleases = {};
                    this.knives = {};
                    this.knifeHands = {};
                    this.knifeEdges = {};
                    this.received = 0;
                    // Clock of the last state that arrived. One slow or failed poll on an unsteady network is not a disconnect.
                    this.lastStateAt = 0;
                    this.labels = {};
                    this.buttons = {};
                    this.controlAccess = null;
                    this.reduceMotion = !cc_2.sys.isNative && !!((_a = window.matchMedia) === null || _a === void 0 ? void 0 : _a.call(window, '(prefers-reduced-motion: reduce)').matches);
                    this.eventsGame = '';
                    this.seenEvents = new Set();
                    this.lastAiError = null;
                    this.pops = [];
                    this.flashes = {};
                    this.tickets = [];
                    this.orderArt = [];
                    this.focusId = "";
                    this.meters = {};
                    this.overlayPhase = "";
                    this.countdown = 0;
                    this.endedSeen = { round: '', at: 0 };
                    this.devices = {};
                    this.people = {};
                    this.motions = {};
                    this.potEffects = {};
                    this.cabinetFires = {};
                    this.foodStages = {};
                    this.readyUntil = {};
                    this.jeffThinking = null;
                    this.jeffError = null;
                    this.ground = {};
                    this.groundStages = {};
                    this.flights = {};
                    this.flightOrder = {};
                    this.menu = null;
                    this.menuSignature = '';
                    this.cover = null;
                    this.mounted = false;
                    this.world = null;
                    this.depthEntries = [];
                    this.mapNodes = [];
                    this.mountedLayout = "";
                    // Native debug builds use USB forwarding: adb reverse tcp:8769 tcp:8769.
                    // Production releases replace this with the operator's HTTPS game backend, never a Jev API key.
                    this.endpoint = cc_2.sys.isNative ? 'http://127.0.0.1:8769' : '';
                    this.onBlur = () => this.clearInput();
                    this.onVisibility = () => { if (document.hidden)
                        this.clearInput(); };
                    this.onContextMenu = (e) => { var _a; if ((_a = e.target) === null || _a === void 0 ? void 0 : _a.closest('canvas'))
                        e.preventDefault(); };
                    this.onMouseDown = (e) => {
                        var _a;
                        if (!cc_2.sys.isNative && e.isTrusted)
                            window.dispatchEvent(new CustomEvent('kitchen-manual-input', { detail: { source: 'mouse' } }));
                        if (e.button === 2 && ((_a = e.target) === null || _a === void 0 ? void 0 : _a.closest('canvas'))) {
                            e.preventDefault();
                            e.stopImmediatePropagation();
                        }
                    };
                    this.onMouseUp = (e) => { var _a; if (e.button === 2 && ((_a = e.target) === null || _a === void 0 ? void 0 : _a.closest('canvas'))) {
                        e.preventDefault();
                        e.stopImmediatePropagation();
                    } };
                    this.onTouchMode = (e) => {
                        var _a;
                        const next = e.detail || {}, old = this.touchLayout;
                        this.touchLayout = next;
                        if ((old === null || old === void 0 ? void 0 : old.active) !== next.active || (old === null || old === void 0 ? void 0 : old.landscape) !== next.landscape)
                            this.clearInput();
                        if (next.active && !next.landscape)
                            this.blockTouch(true);
                        if (this.connected)
                            cc_2.game.frameRate = ((_a = this.state) === null || _a === void 0 ? void 0 : _a.phase) === 'running' ? (next.active ? 30 : 60) : 15;
                        this.applyTouchLayout();
                        if (this.mounted)
                            this.render();
                        this.publishControls();
                    };
                    this.onKey = (e) => {
                        var _a, _b, _c, _d, _e;
                        // Give a held controller back to the keyboard before applying this key.
                        if (!cc_2.sys.isNative && e.isTrusted)
                            window.dispatchEvent(new CustomEvent('kitchen-manual-input', { detail: { source: 'keyboard' } }));
                        // The communication dock keeps native Tab/Enter/Space; Esc hands the keyboard back.
                        const dock = !cc_2.sys.isNative ? (_a = document.activeElement) === null || _a === void 0 ? void 0 : _a.closest('#kitchen-communication') : null;
                        if (e.key === 'Escape') {
                            if (dock) {
                                document.activeElement.blur();
                                return;
                            }
                            if (e.repeat || (!cc_2.sys.isNative && document.querySelector('dialog[open]')))
                                return;
                            this.togglePause(e);
                            return;
                        }
                        if (e.isComposing || e.keyCode === 229)
                            return;
                        if (!cc_2.sys.isNative && (document.querySelector('dialog[open]') || ((_b = document.activeElement) === null || _b === void 0 ? void 0 : _b.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]'))))
                            return;
                        // P pauses and resumes like Esc, for keyboards without an Esc key (iPad Magic Keyboard).
                        // Typing fields and open dialogs are excluded above.
                        if (e.code === 'KeyP' && !e.ctrlKey && !e.altKey && !e.metaKey) {
                            if (!e.repeat)
                                this.togglePause(e);
                            else
                                e.preventDefault();
                            return;
                        }
                        if (dock && (e.key === 'Enter' || e.code === 'Space' || e.key === 'Tab'))
                            return;
                        // On the result screen Space presses the focused main button (next level), like Enter.
                        if (e.code === 'Space' && ((_c = this.state) === null || _c === void 0 ? void 0 : _c.phase) === 'ended' && this.focusId === 'main') {
                            e.preventDefault();
                            const b = this.buttons.main;
                            if (!e.repeat && (b === null || b === void 0 ? void 0 : b.enabled) && b.node.activeInHierarchy) {
                                this.audio.play('ui_click');
                                b.callback();
                            }
                            return;
                        }
                        // Enter bookmarks the moment, unless a focused on-screen control should be pressed.
                        if (e.key === 'Enter' && ((_d = this.state) === null || _d === void 0 ? void 0 : _d.phase) === 'running' && !(this.focusId && ((_e = this.buttons[this.focusId]) === null || _e === void 0 ? void 0 : _e.enabled) && this.buttons[this.focusId].node.activeInHierarchy)) {
                            e.preventDefault();
                            e.stopImmediatePropagation();
                            if (!e.repeat && !e.ctrlKey && !e.altKey && !e.metaKey)
                                this.bookmark();
                            return;
                        }
                        if (this.canInput()) {
                            // Keys that keep the WASD fingers in place: Space (thumb) = whatever the faced target needs,
                            // including chop, wash and extinguish; hold Space to aim a throw; Shift (little finger) =
                            // dash (Overcooked's Alt, which browsers reserve).
                            if (e.key === 'Shift') {
                                e.preventDefault();
                                if (!e.repeat)
                                    this.dash();
                                return;
                            }
                            if (e.code === 'Space') {
                                e.preventDefault();
                                if (!e.repeat && !e.ctrlKey && !e.altKey && !e.metaKey) {
                                    this.pressInteract();
                                }
                                return;
                            }
                            const key = e.key.toLowerCase();
                            if (['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(key)) {
                                e.preventDefault();
                                this.heldKeys.add(key);
                                if (this.aiming)
                                    this.steerAim();
                                else
                                    this.refreshMovement();
                                return;
                            }
                        }
                        if (e.key === 'Tab') {
                            e.preventDefault();
                            const ids = this.tabOrder().filter(id => { var _a; return ((_a = this.buttons[id]) === null || _a === void 0 ? void 0 : _a.enabled) && this.buttons[id].node.activeInHierarchy; });
                            if (!ids.length)
                                return;
                            const at = ids.indexOf(this.focusId);
                            this.setFocus(ids[(at + (e.shiftKey ? -1 : 1) + ids.length) % ids.length]);
                        }
                        else if (e.key === 'Enter' && this.focusId) {
                            const b = this.buttons[this.focusId];
                            if ((b === null || b === void 0 ? void 0 : b.enabled) && b.node.activeInHierarchy) {
                                e.preventDefault();
                                this.audio.play('ui_click');
                                b.callback();
                            }
                        }
                    };
                    this.onConfirmed = (e) => {
                        var _a;
                        const d = e.detail;
                        if (d.ok)
                            this.post(d.kind === 'end' ? '/api/end' : '/api/restart');
                        else if (d.resume && ((_a = this.state) === null || _a === void 0 ? void 0 : _a.phase) === 'paused')
                            this.post('/api/resume');
                    };
                    this.onKeyUp = (e) => {
                        if (e.code === 'Space') {
                            this.releaseInteract();
                            return;
                        }
                        const key = e.key.toLowerCase();
                        if (this.heldKeys.delete(key)) {
                            if (this.aiming)
                                this.steerAim();
                            else
                                this.refreshMovement();
                        }
                    };
                    this.levelIds = [];
                    this.labelSources = new WeakMap();
                    this.onLanguage = () => {
                        this.clearInput();
                        for (const label of this.node.getComponentsInChildren(cc_2.Label)) {
                            const source = this.labelSources.get(label);
                            if (source !== undefined)
                                this.writeLabel(label, source);
                        }
                        this.render();
                    };
                    this.scheduledPoll = () => {
                        var _a;
                        const interval = ((_a = this.state) === null || _a === void 0 ? void 0 : _a.phase) === 'running' ? .2 : 1;
                        if (this.clock - this.lastScheduledPoll < interval - .01)
                            return;
                        this.lastScheduledPoll = this.clock;
                        this.poll();
                    };
                    this.poll = async () => {
                        if (this.polling || this.hidden || !this.artLoaded)
                            return;
                        this.polling = true;
                        try {
                            const sent = this.clock, next = await this.request('/api/state');
                            this.applyState(next, sent);
                        }
                        catch (e) {
                            // Keep the picture and held keys through brief gaps; the next state that arrives replaces this note.
                            // The server still pauses a running round after 8 s without any request.
                            if (this.connected && this.clock - this.lastStateAt < NETWORK_GRACE_SECONDS) {
                                this.set('event', '网络不稳定，正在重连…');
                                return;
                            }
                            this.hideLoading();
                            cc_2.game.frameRate = 15;
                            this.clearInput();
                            this.connected = false;
                            if (this.jeffThinking)
                                this.jeffThinking.active = false;
                            this.set('event', String(e.message) + '，厨房会自动暂停。');
                            this.cover.active = true;
                            this.set('coverTitle', '连接厨房');
                            this.set('coverText', '暂时连接不上厨房，请稍后重试。\n连接中断时，游戏会自动暂停。');
                            this.writeLabel(this.buttons.main.label, '重新连接');
                            this.buttons.reset.node.active = false;
                            this.buttons.record.node.active = false;
                            this.labels['welcome-tip'].node.active = true;
                        }
                        finally {
                            this.polling = false;
                            this.applyTouchLayout();
                            this.publishControls();
                        }
                    };
                    this.tagText = {};
                }
                get useArt() { return this.art.ready; }
                get useModularArt() { return this.useArt && this.art.modular; }
                registerDepth(node, getDepth) { this.depthEntries.push({ node, getDepth }); }
                sortWorld() {
                    this.depthEntries = this.depthEntries.filter(e => e.node.isValid);
                    this.depthEntries.sort((a, b) => a.getDepth() - b.getDepth());
                    this.depthEntries.forEach((e, i) => e.node.setSiblingIndex(i));
                }
                start() {
                    var _a, _b;
                    if (!cc_2.sys.isNative && new URLSearchParams(location.search).has('qaPerf'))
                        cc_2.profiler.showStats();
                    else
                        cc_2.profiler.hideStats();
                    cc_2.view.setDesignResolutionSize(1280, 720, cc_2.ResolutionPolicy.SHOW_ALL);
                    // Letterbox bands match the page's wall-plank frame instead of the engine's default grey.
                    for (const cam of ((_a = cc_2.director.getScene()) === null || _a === void 0 ? void 0 : _a.getComponentsInChildren(cc_2.Camera)) || [])
                        cam.clearColor = color(COLORS.frame);
                    this.node.getComponent(cc_2.UITransform).setContentSize(1280, 720);
                    this.box(this.node, 'background', 640, 360, 1280, 720, COLORS.bg);
                    this.box(this.node, 'header', 640, 35, 1280, 70, COLORS.paper);
                    this.icon(this.node, 'brand-icon', 45, 35, 'vessel', 1.1);
                    this.pixel(this.text('brand', 'ChefJeff', 80, 30, 170, 36, 24), 24);
                    this.text('edition', '和AI一起经营餐馆', 81, 53, 290, 20, 11).color = color(COLORS.muted);
                    for (const [i, id, title] of [[0, 'served', '完成订单'], [1, 'money', '营业收入']]) {
                        const x = 690 + i * 130;
                        this.text(id + '-title', title, x, 19, 120, 20, 12).color = color(COLORS.muted);
                        this.pixel(this.text(id, '—', x, 46, 120, 32, 24), 24);
                    }
                    this.pixel(this.text('clock', '准备开店', 470, 34, 220, 28, 24), 24).color = color(COLORS.muted);
                    this.box(this.node, 'order-rail', 640, 81, 812, 8, COLORS.walnut);
                    for (let i = 0; i < 5; i++) {
                        const x = 234 + i * 164, n = this.make('ticket-' + i, x + 78, 112, 156, 67);
                        this.tickets.push(n);
                        this.pixel(this.text('order-id-' + i, '', x + 12, 96, 100, 16, 12), 12);
                        this.pixel(this.text('order-name-' + i, '', x + 12, 117, 132, 26, 24), 24);
                        this.pixel(this.text('order-time-' + i, '', x + 104, 96, 40, 16, 12), 12).horizontalAlign = cc_2.Label.HorizontalAlign.RIGHT;
                    }
                    // Map geometry has a shared projection; the exterior remains plain.
                    this.text('sprint-status', '', 1070, 63, 190, 16, 11).horizontalAlign = cc_2.Label.HorizontalAlign.RIGHT;
                    this.text('fire-status', '', 1060, 112, 205, 25, 14).color = color(COLORS.alert);
                    // End sits apart from pause/resume; both destructive actions ask first.
                    this.button('pause', 'Ⅱ', 1100, 34, 44, 36, () => this.post('/api/pause'));
                    this.button('resume', '▶', 1152, 34, 44, 36, () => this.post('/api/resume'), this.node, 'primary');
                    this.button('end', '■', 1226, 34, 44, 36, () => this.confirm('end'), this.node, 'danger');
                    for (const id of ['pause', 'resume', 'end'])
                        this.pixel(this.buttons[id].label, 24);
                    this.text('hand', '', 234, 691, 235, 22, 14).color = color(COLORS.ink);
                    this.text('interaction', '', 470, 691, 575, 22, 14).color = color(COLORS.ink);
                    this.text('event', '', 234, 709, 500, 18, 13).color = color(COLORS.ink);
                    this.text('ai-status', '', 744, 709, 302, 18, 13).horizontalAlign = cc_2.Label.HorizontalAlign.RIGHT;
                    this.cover = this.make('cover', 640, 360, 1280, 720);
                    this.cover.on(cc_2.Node.EventType.TOUCH_END, (e) => { e.propagationStopped = true; });
                    const shade = this.cover.addComponent(cc_2.Graphics);
                    shade.fillColor = new cc_2.Color(43, 26, 18, 170);
                    shade.rect(-640, -360, 1280, 720);
                    shade.fill();
                    // A cafe awning frames the start/pause board; the kitchen stays visible behind it.
                    this.box(this.cover, 'welcome-shadow', 646, 367, 736, 464, COLORS.ink);
                    this.box(this.cover, 'welcome-board', 640, 358, 736, 464, COLORS.paper);
                    for (let i = 0; i < 16; i++)
                        this.box(this.cover, 'awning', 295 + i * 46, 145, 46, 38, i % 2 ? COLORS.paper : COLORS.human);
                    this.text('welcome-kicker', '和AI一起经营餐馆', 340, 193, 600, 25, 13, this.cover).horizontalAlign = cc_2.Label.HorizontalAlign.CENTER;
                    this.pixel(this.text('coverTitle', 'ChefJeff', 316, 244, 648, 56, 48, this.cover), 48);
                    this.labels.coverTitle.horizontalAlign = cc_2.Label.HorizontalAlign.CENTER;
                    this.chef(this.cover, 'welcome-human', 550, 332, 'human', 1.25);
                    this.chef(this.cover, 'welcome-jeff', 730, 332, 'jeff', 1.25);
                    this.icon(this.cover, 'welcome-food', 640, 332, 'vessel', 1.05);
                    this.text('coverText', '正在连接厨房…', 330, 404, 620, 78, 19, this.cover).horizontalAlign = cc_2.Label.HorizontalAlign.CENTER;
                    this.button('main', '开始经营', 379, 520, 158, 48, () => {
                        var _a, _b, _c;
                        if (!this.connected) {
                            this.poll();
                            return;
                        }
                        const phase = (_a = this.state) === null || _a === void 0 ? void 0 : _a.phase;
                        if (phase === 'ready' && ((_b = this.state) === null || _b === void 0 ? void 0 : _b.connection) && !this.state.connection.configured) {
                            this.set('coverText', '请先从下方「设置」连接自己的 API，再开始经营。');
                            return;
                        }
                        if (phase === 'ended') {
                            this.startNext();
                            return;
                        }
                        // The online version plays at the real clock (1x); the local default stays at 0.75.
                        this.post(phase === 'ready' ? '/api/start' : phase === 'paused' ? '/api/resume' : '/api/reset', phase === 'ready' ? { speed: ((_c = this.state) === null || _c === void 0 ? void 0 : _c.hosted) ? 1 : .75 } : {});
                    }, this.cover, 'primary');
                    this.button('reset', '重新开局', 553, 520, 158, 48, () => this.confirm('restart'), this.cover);
                    this.buttons.reset.node.active = false;
                    this.button('cover-connection', '设置', 727, 520, 158, 48, () => this.openConnection(), this.cover);
                    this.button('help', '操作说明', 901, 520, 158, 48, () => this.openHelp(), this.cover);
                    // Language sits on the board where people look first, not only inside Settings.
                    this.pixel(this.button('language', 'English', 944, 196, 88, 30, () => { const i18n = window.kitchenI18n; i18n === null || i18n === void 0 ? void 0 : i18n.setLanguage(i18n.language === 'en' ? 'zh' : 'en'); }, this.cover).getComponentInChildren(cc_2.Label), 12);
                    if (cc_2.sys.isNative)
                        this.buttons.language.node.active = false;
                    this.button('more', '更多', 944, 196, 88, 30, () => this.openCoverMenu('more'), this.cover);
                    this.button('level-picker', '关卡选择', 772, 464, 158, 36, () => this.openCoverMenu('levels'), this.cover);
                    this.pixel(this.text('selected-level', '', 390, 464, 270, 24, 13, this.cover), 13).horizontalAlign = cc_2.Label.HorizontalAlign.CENTER;
                    this.buttons.more.node.active = this.buttons['level-picker'].node.active = false;
                    this.text('welcome-tip', '先看操作说明，准备好了就开店。', 333, 577, 614, 19, 11, this.cover).horizontalAlign = cc_2.Label.HorizontalAlign.CENTER;
                    // The round record shares the tip's row: the tip shows before a round, the record after it.
                    this.button('record', '本局记录', 561, 566, 158, 36, () => this.openRecord(), this.cover);
                    this.buttons.record.node.active = false;
                    // Online, after 暂不: one tap contributes this round under the terms already shown (the hosted agent uploads it).
                    this.button('contribute', '贡献本局', 735, 566, 158, 36, () => window.dispatchEvent(new Event('kitchen-contribute')), this.cover);
                    this.buttons.contribute.node.active = false;
                    if (!cc_2.sys.isNative) {
                        // Screen-reader proxies for every canvas button. Canvas focus moves DOM
                        // focus to the matching proxy so assistive technology follows it.
                        this.controlAccess = document.createElement('div');
                        this.controlAccess.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);';
                        for (const id of TAB_ORDER)
                            this.controlAccess.appendChild(this.proxyButton(id));
                        document.body.appendChild(this.controlAccess);
                        const canvas = document.getElementById('GameCanvas');
                        canvas === null || canvas === void 0 ? void 0 : canvas.setAttribute('role', 'img');
                        canvas === null || canvas === void 0 ? void 0 : canvas.setAttribute('aria-label', 'ChefJeff 厨房画面');
                    }
                    this.installControls();
                    cc_2.game.on(cc_2.Game.EVENT_HIDE, this.onHide, this);
                    cc_2.game.on(cc_2.Game.EVENT_SHOW, this.onShow, this);
                    if (!cc_2.sys.isNative) {
                        window.addEventListener('kitchen-language-changed', this.onLanguage);
                        window.addEventListener('kitchen-confirmed', this.onConfirmed);
                        window.addEventListener('keydown', this.onKey, true);
                        window.addEventListener('keyup', this.onKeyUp, true);
                        window.addEventListener('mousedown', this.onMouseDown, true);
                        window.addEventListener('mouseup', this.onMouseUp, true);
                        window.addEventListener('blur', this.onBlur);
                        document.addEventListener('visibilitychange', this.onVisibility);
                        document.addEventListener('contextmenu', this.onContextMenu);
                    }
                    // Idle screens need neither gameplay frame rate nor five snapshots a second.
                    cc_2.game.frameRate = 15;
                    this.audio.load(this.node);
                    this.art.load().then(() => { this.artLoaded = true; this.loadingStep('正在连接厨房…'); if (this.isValid)
                        this.poll(); });
                    if (!cc_2.sys.isNative)
                        (_b = document.fonts) === null || _b === void 0 ? void 0 : _b.load('24px ChefJeffPixel').then(() => {
                            // Labels drawn before the pixel face arrived keep the fallback until re-rendered.
                            for (const l of this.node.getComponentsInChildren(cc_2.Label))
                                l.updateRenderData(true);
                            this.tagText = {};
                            if (this.state && this.mounted)
                                this.render();
                        }).catch(() => { });
                    this.schedule(this.scheduledPoll, .2);
                }
                // The page's loading screen stays up until the kitchen first answers (or fails), so the
                // cover never flashes placeholder art or a second "connecting" state.
                loadingStep(text) { const el = !cc_2.sys.isNative && document.querySelector('#kitchen-loading span'); if (el)
                    el.textContent = text; }
                hideLoading() { var _a; if (!cc_2.sys.isNative)
                    (_a = document.getElementById('kitchen-loading')) === null || _a === void 0 ? void 0 : _a.remove(); }
                onDestroy() { var _a; this.audio.destroy(); (_a = this.controlAccess) === null || _a === void 0 ? void 0 : _a.remove(); this.clearInput(); cc_2.game.off(cc_2.Game.EVENT_HIDE, this.onHide, this); cc_2.game.off(cc_2.Game.EVENT_SHOW, this.onShow, this); if (!cc_2.sys.isNative) {
                    window.removeEventListener('kitchen-touch-mode', this.onTouchMode);
                    if (window.kitchenControls === this.controls)
                        delete window.kitchenControls;
                    window.removeEventListener('kitchen-language-changed', this.onLanguage);
                    window.removeEventListener('kitchen-confirmed', this.onConfirmed);
                    window.removeEventListener('keydown', this.onKey, true);
                    window.removeEventListener('keyup', this.onKeyUp, true);
                    window.removeEventListener('mousedown', this.onMouseDown, true);
                    window.removeEventListener('mouseup', this.onMouseUp, true);
                    window.removeEventListener('blur', this.onBlur);
                    document.removeEventListener('visibilitychange', this.onVisibility);
                    document.removeEventListener('contextmenu', this.onContextMenu);
                } }
                onHide() { var _a; this.hidden = true; this.clearInput(); if (((_a = this.state) === null || _a === void 0 ? void 0 : _a.phase) === 'running')
                    this.post('/api/pause', { reason: 'hidden' }); }
                onShow() { this.hidden = false; this.poll(); }
                openRecord() { var _a; if (!cc_2.sys.isNative && ((_a = this.state) === null || _a === void 0 ? void 0 : _a.round_summary))
                    window.dispatchEvent(new CustomEvent('kitchen-open-record', { detail: this.state.round_summary })); }
                openCoverMenu(kind) {
                    var _a;
                    if (cc_2.sys.isNative || this.pending || !['ready', 'ended'].includes(((_a = this.state) === null || _a === void 0 ? void 0 : _a.phase) || ''))
                        return;
                    this.clearInput();
                    window.dispatchEvent(new Event('kitchen-open-' + kind));
                }
                openHelp() { var _a; this.clearInput(); if ((_a = this.touchLayout) === null || _a === void 0 ? void 0 : _a.active)
                    this.blockTouch(true); if (!cc_2.sys.isNative)
                    window.dispatchEvent(new Event('kitchen-open-help')); }
                openConnection() { var _a; this.clearInput(); if ((_a = this.touchLayout) === null || _a === void 0 ? void 0 : _a.active)
                    this.blockTouch(true); if (!cc_2.sys.isNative)
                    window.dispatchEvent(new Event('kitchen-open-connection')); }
                // Keyboard and touch share gameplay actions; the web shell only owns pointer gestures and layout.
                installControls() {
                    if (cc_2.sys.isNative)
                        return;
                    this.controls = {
                        getState: () => this.controlsState(), move: (x, y) => this.setTouchMove(x, y),
                        press: () => this.pressInteract(), release: () => this.releaseInteract(),
                        act: () => this.pressInteract('act'), toss: () => this.pressInteract('toss'),
                        cancel: () => this.clearInput(), dash: () => this.dash(), block: (blocked) => this.blockTouch(blocked),
                        pause: () => { var _a; this.clearInput(); if (this.connected && ((_a = this.state) === null || _a === void 0 ? void 0 : _a.phase) === 'running')
                            this.post('/api/pause'); },
                        resume: () => this.controlButton('resume'), main: () => this.controlButton('main'), restart: () => this.controlButton('reset'),
                        settings: () => this.openConnection(), help: () => this.openHelp(), end: () => this.controlButton('end'),
                        record: () => this.openRecord(), contribute: () => this.controlButton('contribute'), bookmark: () => { if (this.canInput())
                            this.bookmark(); },
                        levels: () => this.openCoverMenu('levels'), more: () => this.openCoverMenu('more'),
                        level: (id) => { var _a, _b, _c; if (this.connected && !this.pending && ['ready', 'ended'].includes(((_a = this.state) === null || _a === void 0 ? void 0 : _a.phase) || '') && ((_c = (_b = this.state) === null || _b === void 0 ? void 0 : _b.levels) === null || _c === void 0 ? void 0 : _c.some((l) => l.id === id)))
                            return this.post('/api/level', { level: id }); },
                        language: () => { const i18n = window.kitchenI18n; i18n === null || i18n === void 0 ? void 0 : i18n.setLanguage(i18n.language === 'en' ? 'zh' : 'en'); }
                    };
                    window.kitchenControls = this.controls;
                    window.kitchenDiagnostics = () => this.diagnostics();
                    window.addEventListener('kitchen-touch-mode', this.onTouchMode);
                    window.dispatchEvent(new CustomEvent('kitchen-controls-ready'));
                    this.publishControls();
                }
                controlButton(id) {
                    var _a, _b;
                    if (this.pending)
                        return;
                    if (((_a = this.touchLayout) === null || _a === void 0 ? void 0 : _a.active) && !this.touchLayout.landscape)
                        return;
                    if (!cc_2.sys.isNative && document.querySelector('dialog[open]'))
                        return;
                    if (id === 'main' && ((_b = this.state) === null || _b === void 0 ? void 0 : _b.phase) === 'ready' && this.state.connection && !this.state.connection.configured) {
                        this.openConnection();
                        return;
                    }
                    const b = this.buttons[id];
                    if ((b === null || b === void 0 ? void 0 : b.enabled) && !this.pending)
                        b.callback();
                }
                canInput() { return !!this.state && this.connected && !this.hidden && !this.touchBlocked && this.state.phase === 'running' && (cc_2.sys.isNative || !document.querySelector('dialog[open]')); }
                blockTouch(blocked) {
                    var _a;
                    if (this.touchBlocked === !!blocked)
                        return;
                    this.touchBlocked = !!blocked;
                    if (blocked) {
                        this.clearInput();
                        if (this.connected && ((_a = this.state) === null || _a === void 0 ? void 0 : _a.phase) === 'running')
                            this.post('/api/pause');
                    }
                    this.publishControls();
                }
                controlsState() {
                    var _a, _b, _c, _d, _e, _f;
                    const s = this.state, k = s === null || s === void 0 ? void 0 : s.kitchen, c = (_a = k === null || k === void 0 ? void 0 : k.chefs) === null || _a === void 0 ? void 0 : _a.human;
                    const text = (id) => this.labels[id] ? this.labelSources.get(this.labels[id]) || '' : '';
                    return { game_id: s === null || s === void 0 ? void 0 : s.game_id, phase: (s === null || s === void 0 ? void 0 : s.phase) || 'loading', connected: this.connected, pending: this.pending, canInput: this.canInput(),
                        canInteract: !!(s === null || s === void 0 ? void 0 : s.interaction), canThrow: !!(c === null || c === void 0 ? void 0 : c.holding) && c.can_throw !== false,
                        canDash: this.canInput() && !this.aiming && !!((_b = c === null || c === void 0 ? void 0 : c.sprint) === null || _b === void 0 ? void 0 : _b.available) && (this.manualDirection.x !== 0 || this.manualDirection.y !== 0),
                        holding: (c === null || c === void 0 ? void 0 : c.holding) || null, interaction: ((_c = s === null || s === void 0 ? void 0 : s.interaction) === null || _c === void 0 ? void 0 : _c.label.split('（')[0]) || '', interactionHint: (s === null || s === void 0 ? void 0 : s.interaction_hint) || '',
                        aiming: this.aiming ? Object.assign({}, this.aiming) : null, sprint: (c === null || c === void 0 ? void 0 : c.sprint) || {}, event: text('event'),
                        orders: ((k === null || k === void 0 ? void 0 : k.orders) || []).filter((o) => o.status === 'pending').map((o) => this.touchOrder(o)),
                        money: (k === null || k === void 0 ? void 0 : k.money) || 0, served: (k === null || k === void 0 ? void 0 : k.served) || 0, timeLabel: text('clock'), handLabel: text('hand'), aiStatus: text('ai-status'),
                        coverTitle: text('coverTitle'), coverText: text('coverText'), mainLabel: this.buttons.main ? this.labelSources.get(this.buttons.main.label) || '' : '',
                        mainEnabled: !!((_d = this.buttons.main) === null || _d === void 0 ? void 0 : _d.enabled) && !this.pending,
                        communicationEnabled: !!((_e = s === null || s === void 0 ? void 0 : s.communication) === null || _e === void 0 ? void 0 : _e.allowed), endEnabled: ['running', 'paused'].includes((s === null || s === void 0 ? void 0 : s.phase) || '') && this.connected && !this.pending,
                        recordEnabled: !!(s === null || s === void 0 ? void 0 : s.round_summary) && (s === null || s === void 0 ? void 0 : s.phase) === 'ended',
                        contribute: (s === null || s === void 0 ? void 0 : s.phase) === 'ended' && ((_f = s === null || s === void 0 ? void 0 : s.hosted) === null || _f === void 0 ? void 0 : _f.contribution_offer) ? { label: this.labelSources.get(this.buttons.contribute.label) || '', enabled: this.buttons.contribute.enabled } : null, levels: ((s === null || s === void 0 ? void 0 : s.levels) || []).map((l) => ({ id: l.id, name: l.name, selected: l.id === (k === null || k === void 0 ? void 0 : k.level_id) })),
                        levelEnabled: this.connected && !this.pending && ['ready', 'ended'].includes((s === null || s === void 0 ? void 0 : s.phase) || '') };
                }
                touchOrder(order) {
                    var _a, _b, _c;
                    const dish = this.dishById(order.dish), ingredients = order.ingredients || ((_a = dish === null || dish === void 0 ? void 0 : dish.components) === null || _a === void 0 ? void 0 : _a.map((c) => c.item)) || [];
                    const patienceTotal = order.patience || ((_c = (_b = this.state) === null || _b === void 0 ? void 0 : _b.rules) === null || _c === void 0 ? void 0 : _c.order_patience) || 90;
                    const recipeKey = [`dishes/${order.dish}/ready`, `food/${order.dish}_ready`].find(key => this.art.has(key));
                    return Object.assign(Object.assign({}, order), { dishName: (dish === null || dish === void 0 ? void 0 : dish.name) || order.dish, patienceTotal, patienceRemainingFraction: Math.max(0, Math.min(1, (order.remaining || 0) / patienceTotal)), recipeIcon: recipeKey ? this.art.spriteInfo(recipeKey) : null, ingredientDetails: ingredients.map(id => {
                            var _a, _b;
                            const required = (_b = (_a = dish === null || dish === void 0 ? void 0 : dish.components) === null || _a === void 0 ? void 0 : _a.find((c) => c.item === id)) === null || _b === void 0 ? void 0 : _b.state, state = required && required !== 'chopped' ? required : 'raw';
                            const art = this.itemArt(id, state, true);
                            return { id, name: this.itemLabel(id), state, icon: art ? this.art.spriteInfo(art.key) : null };
                        }) });
                }
                publishControls() {
                    if (cc_2.sys.isNative || !this.controls)
                        return;
                    const detail = this.controlsState(), signature = JSON.stringify(detail);
                    if (signature === this.controlsSignature)
                        return;
                    this.controlsSignature = signature;
                    window.dispatchEvent(new CustomEvent('kitchen-controls-state', { detail }));
                }
                setTouchMove(x, y) {
                    if (!Number.isFinite(x) || !Number.isFinite(y))
                        return;
                    const length = Math.hypot(x, y), d = length ? { x: x / length, y: y / length } : { x: 0, y: 0 };
                    if (length && !this.canInput())
                        return;
                    this.touchDirection = d;
                    if (this.aiming) {
                        if (length) {
                            this.aiming = d;
                            this.drawAim();
                            this.publishControls();
                        }
                        return;
                    }
                    this.touchMoveDirty = true;
                    if (!length)
                        this.flushTouchMove();
                }
                flushTouchMove() {
                    if (!this.touchMoveDirty)
                        return;
                    this.touchMoveDirty = false;
                    this.touchMoveAt = this.clock;
                    this.refreshMovement();
                    this.publishControls();
                }
                /** Space ('hands'): with a throwable item the press arms a hold-to-aim, a tap acts on release. Touch
                 *  Action ('act') does everything but throw, at once on press; touch Throw ('toss') only arms the throw. */
                pressInteract(kind = 'hands') {
                    if (!this.canInput() || this.pending || this.spaceDownAt !== null || this.aiming)
                        return;
                    // Work is sticky (no button stops it), and a second press just after a pick-up is ignored (Overcooked's 0.5 s).
                    const c = this.state.kitchen.chefs.human, held = c.holding;
                    if (c.working || this.clock - this.pickedAt < .5)
                        return;
                    if (kind !== 'act' && held && c.can_throw !== false) {
                        this.spaceDownAt = this.clock;
                        this.spaceItemId = held.id;
                        this.tossOnly = kind === 'toss';
                    }
                    else if (kind !== 'toss')
                        this.interact();
                }
                interact() {
                    var _a;
                    const s = this.state;
                    this.handsBusyUntil = this.clock + .35;
                    this.actionCue();
                    this.post('/api/interact', Object.assign(Object.assign({ expected_item: ((_a = s.kitchen.chefs.human.holding) === null || _a === void 0 ? void 0 : _a.id) || null }, this.atBody()), this.pickBody()));
                }
                releaseInteract() {
                    var _a;
                    const held = (_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.chefs.human.holding;
                    if (this.spaceItemId !== null && (!this.canInput() || (held === null || held === void 0 ? void 0 : held.id) !== this.spaceItemId)) {
                        this.clearInput();
                        return;
                    }
                    if (this.aiming) {
                        const d = this.aiming;
                        this.endAim();
                        this.throwAlong(held, d);
                        this.refreshMovement();
                    }
                    else if (this.tossOnly && this.spaceDownAt !== null) {
                        // A quick Throw tap throws where the aim would have started.
                        const d = this.aimStart();
                        this.endAim();
                        this.throwAlong(held, d);
                        this.refreshMovement();
                    }
                    else if (this.spaceDownAt !== null) {
                        this.spaceDownAt = null;
                        this.spaceItemId = null;
                        this.interact();
                    }
                    this.publishControls();
                }
                /** Throws along d; the direction still held then waits for neutral or a 15 degree turn (heldThrough). */
                throwAlong(held, d) {
                    this.heldThrough = this.rawDirection();
                    if (held && this.canInput()) {
                        this.throwReleases.human = { dx: d.x, dy: d.y, until: this.clock + .3 };
                        this.post('/api/throw', Object.assign({ expected_item: held.id, direction: [d.x, d.y] }, this.atBody()));
                    }
                }
                dash() {
                    var _a;
                    if (!this.canInput() || this.aiming)
                        return;
                    const sprint = (_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.chefs.human.sprint;
                    if (sprint && (sprint.available === false || sprint.active_remaining > 0 || sprint.cooldown_remaining > 0 || this.sprintFactor(this.state.kitchen.chefs.human) > 1))
                        return;
                    this.flushTouchMove();
                    if (this.manualDirection.x !== 0 || this.manualDirection.y !== 0) {
                        this.sprintAt = this.clock;
                        this.sendMove(this.manualDirection.x, this.manualDirection.y, true);
                    }
                }
                /** The local chef's speed multiplier, eased like the engine's sprint_extra (starts at the dash's
                 * multiplier, back to walking along a sine S-curve); timed from the press so the dash starts at once. */
                sprintFactor(c) {
                    const s = c === null || c === void 0 ? void 0 : c.sprint, d = (s === null || s === void 0 ? void 0 : s.duration) || 0;
                    if (!d || !this.state)
                        return 1;
                    const left = d - (this.clock - this.sprintAt) * this.state.speed;
                    return left > 0 && left <= d ? 1 + ((s.multiplier || 1) - 1) * (1 - Math.cos(Math.PI * left / d)) / 2 : 1;
                }
                togglePause(e) {
                    var _a, _b;
                    if (((_a = this.state) === null || _a === void 0 ? void 0 : _a.phase) === 'running') {
                        e.preventDefault();
                        this.clearInput();
                        this.post('/api/pause');
                    }
                    else if (((_b = this.state) === null || _b === void 0 ? void 0 : _b.phase) === 'paused' && this.connected) {
                        e.preventDefault();
                        this.post('/api/resume');
                    }
                }
                setFocus(id) {
                    var _a, _b;
                    const old = this.focusId;
                    this.focusId = id;
                    this.styleButton(old);
                    this.styleButton(id);
                    const proxy = (_a = this.controlAccess) === null || _a === void 0 ? void 0 : _a.querySelector(`[data-control="${id}"]`);
                    if (proxy && !proxy.hidden)
                        proxy.focus({ preventScroll: true });
                    else if ((_b = this.controlAccess) === null || _b === void 0 ? void 0 : _b.contains(document.activeElement))
                        document.activeElement.blur();
                }
                // Ending or abandoning a live round asks first; the round is paused meanwhile.
                async confirm(kind) {
                    var _a;
                    const phase = (_a = this.state) === null || _a === void 0 ? void 0 : _a.phase;
                    if (cc_2.sys.isNative || (kind === 'restart' && phase !== 'paused')) {
                        this.post(kind === 'end' ? '/api/end' : '/api/restart');
                        return;
                    }
                    this.clearInput();
                    const resume = phase === 'running';
                    if (resume)
                        await this.post('/api/pause');
                    window.dispatchEvent(new CustomEvent('kitchen-confirm', { detail: { kind, resume } }));
                }
                announce(message) { if (!cc_2.sys.isNative && message)
                    window.dispatchEvent(new CustomEvent('kitchen-announce', { detail: { message } })); }
                rawDirection() {
                    const x = (this.heldKeys.has('d') || this.heldKeys.has('arrowright') ? 1 : 0) - (this.heldKeys.has('a') || this.heldKeys.has('arrowleft') ? 1 : 0);
                    const y = (this.heldKeys.has('s') || this.heldKeys.has('arrowdown') ? 1 : 0) - (this.heldKeys.has('w') || this.heldKeys.has('arrowup') ? 1 : 0), mag = Math.hypot(x, y);
                    if (mag)
                        return { x: x / mag, y: y / mag };
                    return this.touchDirection.x !== 0 || this.touchDirection.y !== 0 ? this.touchDirection : null;
                }
                /** The walking direction: the held one, unless it is still the one held through an action (heldThrough). */
                keyDirection() {
                    const d = this.rawDirection(), h = this.heldThrough;
                    if (!d) {
                        this.heldThrough = null;
                        return null;
                    }
                    if (h && d.x * h.x + d.y * h.y >= Math.cos(Math.PI / 12))
                        return null;
                    this.heldThrough = null;
                    return d;
                }
                /** Space held long enough: stop, and aim along the held direction (or the facing). */
                startAim() {
                    var _a, _b;
                    const human = (_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.chefs.human;
                    if (!this.connected || ((_b = this.state) === null || _b === void 0 ? void 0 : _b.phase) !== 'running' || !(human === null || human === void 0 ? void 0 : human.holding) || human.holding.id !== this.spaceItemId || human.can_throw === false) {
                        this.endAim();
                        return;
                    }
                    this.spaceDownAt = null;
                    this.aiming = this.aimStart();
                    if (this.manualDirection.x !== 0 || this.manualDirection.y !== 0) {
                        this.manualDirection = { x: 0, y: 0 };
                        this.sendMove(0, 0);
                    }
                    this.drawAim();
                    this.publishControls();
                }
                /** The held direction (even one held through an action), else the facing. */
                aimStart() { var _a, _b; const f = FACING_DIR[(_b = (_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.chefs.human) === null || _b === void 0 ? void 0 : _b.facing] || [0, 1]; return this.rawDirection() || { x: f[0], y: f[1] }; }
                steerAim() { const d = this.rawDirection(); if (d && this.aiming) {
                    this.aiming = d;
                    this.drawAim();
                } }
                endAim() { var _a; this.aiming = null; this.spaceDownAt = null; this.spaceItemId = null; this.tossOnly = false; if ((_a = this.aimArrow) === null || _a === void 0 ? void 0 : _a.isValid)
                    this.aimArrow.active = false; }
                drawAim() {
                    var _a, _b, _c, _d, _e, _f;
                    const chef = this.people['human'];
                    if (!this.aiming || !this.world || !chef)
                        return;
                    if (!((_a = this.aimArrow) === null || _a === void 0 ? void 0 : _a.isValid)) {
                        this.aimArrow = this.child(this.world, 'aim-arrow', 10, 10);
                        this.aimArrow.addComponent(cc_2.Graphics);
                    }
                    const a = this.aimArrow, k = this.state.kitchen, reach = (k.map.pass_range || k.map.throw_range || 4) * TILE;
                    a.active = true;
                    a.setSiblingIndex(this.world.children.length - 1);
                    a.setPosition(chef.position.x, chef.position.y + 18);
                    const g = a.getComponent(cc_2.Graphics);
                    g.clear();
                    // Same rule as the server's aimed throw: a teammate roughly on the aim line, within reach,
                    // is the target, so the ribbon bends to them and they are ringed; otherwise full reach.
                    const me = (_c = (_b = k.chefs) === null || _b === void 0 ? void 0 : _b.human) === null || _c === void 0 ? void 0 : _c.position, mate = (_e = (_d = k.chefs) === null || _d === void 0 ? void 0 : _d.jeff) === null || _e === void 0 ? void 0 : _e.position, range = k.map.pass_range || k.map.throw_range || 4;
                    let ex = this.aiming.x * reach, ey = -this.aiming.y * reach, toMate = false;
                    if (me && mate) {
                        const ox = mate[0] - me[0], oy = mate[1] - me[1], ahead = ox * this.aiming.x + oy * this.aiming.y, side = Math.abs(ox * this.aiming.y - oy * this.aiming.x);
                        if (ahead > 0 && ahead <= range && side <= ((_f = k.map.catch_radius) !== null && _f !== void 0 ? _f : .75)) {
                            ex = ox * TILE;
                            ey = -oy * TILE;
                            toMate = true;
                        }
                    }
                    const left = [], right = [];
                    // The ground path is still straight. Only the item's height bends the
                    // screen projection; the hand starts 18px above the ground endpoint.
                    for (let i = 0; i <= 32; i++) {
                        const t = i / 32, x = ex * t, y = ey * t + 35 * Math.sin(Math.PI * t) - 18 * t;
                        const tx = ex, ty = ey + 35 * Math.PI * Math.cos(Math.PI * t) - 18, length = Math.hypot(tx, ty) || 1;
                        const nx = -ty / length * 5, ny = tx / length * 5;
                        left.push([x + nx, y + ny]);
                        right.push([x - nx, y - ny]);
                    }
                    g.fillColor = new cc_2.Color(59, 146, 180, 72);
                    g.strokeColor = new cc_2.Color(42, 90, 158, 120);
                    g.lineWidth = 1;
                    g.moveTo(left[0][0], left[0][1]);
                    for (let i = 1; i < left.length; i++)
                        g.lineTo(left[i][0], left[i][1]);
                    for (let i = right.length - 1; i >= 0; i--)
                        g.lineTo(right[i][0], right[i][1]);
                    g.close();
                    g.fill();
                    g.stroke();
                    if (toMate) {
                        // Aimed at Jeff: ring his feet in the player's denim (the UI's navy), the throw goes to him.
                        g.fillColor = new cc_2.Color(42, 90, 158, 56);
                        g.strokeColor = color(COLORS.human);
                        g.lineWidth = 2.5;
                        g.ellipse(ex, ey - 18, 22, 11);
                        g.fill();
                        g.stroke();
                    }
                    else {
                        // A maximum-range guide, not a prediction of collision or catching.
                        g.fillColor = new cc_2.Color(59, 146, 180, 36);
                        g.strokeColor = new cc_2.Color(42, 90, 158, 145);
                        g.lineWidth = 1.5;
                        g.ellipse(ex, ey - 18, 13, 7);
                        g.fill();
                        g.stroke();
                    }
                }
                // Anything held can be thrown or passed; the server applies each item's range (currently 4 tiles for all).
                async sendMove(dx, dy, sprint = false) { if (!this.state || this.state.phase !== 'running' || !this.connected)
                    return; const seq = ++this.moveSeq; this.lastMoveAt = this.clock; try {
                    await this.request('/api/move', { game_id: this.state.game_id, dx, dy, seq, sprint });
                }
                catch (e) {
                    this.set('event', e.message);
                } }
                refreshMovement() {
                    if (this.aiming)
                        return;
                    const d = this.canInput() ? this.keyDirection() : null, dx = (d === null || d === void 0 ? void 0 : d.x) || 0, dy = (d === null || d === void 0 ? void 0 : d.y) || 0;
                    if (dx === this.manualDirection.x && dy === this.manualDirection.y)
                        return;
                    this.manualDirection = { x: dx, y: dy };
                    this.sendMove(dx, dy);
                }
                predictHuman(k, c, dt, n) {
                    var _a, _b, _c, _d, _e;
                    if (!c.position) {
                        this.predicted = null;
                        return null;
                    }
                    if (((_a = c.resync) !== null && _a !== void 0 ? _a : 0) !== this.resyncSeen) {
                        this.resyncSeen = (_b = c.resync) !== null && _b !== void 0 ? _b : 0;
                        this.predicted = null;
                    }
                    if (!this.predicted)
                        this.predicted = [c.position[0], c.position[1]];
                    // Knocked back by a dash: the engine moves the chef; follow it until it lands.
                    if (c.knocked) {
                        const pull = Math.min(1, dt * 14);
                        this.predicted = [this.predicted[0] + (c.position[0] - this.predicted[0]) * pull, this.predicted[1] + (c.position[1] - this.predicted[1]) * pull];
                        this.walkRamp = 0;
                        return this.predicted;
                    }
                    const d = this.manualDirection, walk = (k.map.walk_speed || 4.5) * this.sprintFactor(c), other = (_c = k.chefs.jeff) === null || _c === void 0 ? void 0 : _c.position, game = dt * this.state.speed;
                    // A quick take/put finishes before the held direction starts, as on the server.
                    if (this.clock < this.handsBusyUntil || (d.x === 0 && d.y === 0)) {
                        this.pressing = false;
                        this.walkRamp = 0;
                        // Work started in place first slides to the station's centre (the engine's route): follow it.
                        const end = (c.travel_remaining || 0) > 0 && ((_d = c.route) === null || _d === void 0 ? void 0 : _d.length) ? c.route[c.route.length - 1] : null;
                        if (end) {
                            const p = this.predicted, gap = Math.hypot(end[0] - p[0], end[1] - p[1]), step = Math.min(gap, walk * game);
                            if (gap > 1e-6)
                                this.predicted = [p[0] + (end[0] - p[0]) * step / gap, p[1] + (end[1] - p[1]) * step / gap];
                        }
                        return this.predicted;
                    }
                    // As in Overcooked, the page moves its own chef in 60 steps a game second, so every drawn point is a
                    // real step (never a line cut through a counter's corner); a start eases to full speed over 0.08 s.
                    const tick = walk / 60, moved = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-4;
                    // Jeff in the way (not a wall): the engine pushes an idle Jeff aside or stops at a busy one, as it
                    // always has. Follow its position and keep asking for a short step ahead until the way is clear.
                    const free = moved(this.predicted, KitchenGeometry_1.predictWalk(k.map, this.predicted, d.x * tick, d.y * tick, undefined, tick));
                    // Once pressing, keep following the engine until clear of Jeff, so the walk does not flip between modes.
                    const near = !!other && Math.hypot(this.predicted[0] - other[0], this.predicted[1] - other[1]) < ((_e = k.map.chef_separation) !== null && _e !== void 0 ? _e : .4) + .25;
                    if (other && free && (!moved(this.predicted, KitchenGeometry_1.predictWalk(k.map, this.predicted, d.x * tick, d.y * tick, other, tick)) || (this.pressing && near))) {
                        const pull = Math.min(1, dt * 8);
                        this.predicted = [this.predicted[0] + (c.position[0] - this.predicted[0]) * pull, this.predicted[1] + (c.position[1] - this.predicted[1]) * pull];
                        this.pressing = true;
                        this.walkRamp = 0;
                        return this.predicted;
                    }
                    // Leaving the press: walk on from where the engine has got to, never report a point behind it.
                    if (this.pressing) {
                        this.pressing = false;
                        this.predicted = [c.position[0], c.position[1]];
                    }
                    for (let left = game; left > 1e-9;) {
                        const sub = Math.min(left, 1 / 60);
                        left -= sub;
                        this.walkRamp = Math.min(1, this.walkRamp + sub / .08);
                        const step = walk * sub * this.walkRamp;
                        this.predicted = KitchenGeometry_1.predictWalk(k.map, this.predicted, d.x * step, d.y * step, other, step);
                    }
                    return this.predicted;
                }
                updatePick(k, c) {
                    const d = this.manualDirection;
                    if (d.x !== 0 || d.y !== 0)
                        this.lastAim = [d.x, d.y];
                    const pick = KitchenGeometry_1.spaceTarget(k.map, this.predicted || c.position, this.aimNow(c), k.ground || []);
                    if (pick !== this.localPick) {
                        this.localPick = pick;
                        if (this.mounted)
                            this.render();
                    }
                }
                aimNow(c) {
                    const f = c === null || c === void 0 ? void 0 : c.facing;
                    return this.lastAim || (f === 'up' ? [0, -1] : f === 'left' ? [-1, 0] : f === 'right' ? [1, 0] : [0, 1]);
                }
                /** What Space was aimed at as drawn: the engine picks the same station from it (see facing_interaction). */
                pickBody() {
                    var _a;
                    const c = (_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.chefs.human;
                    if (!c || this.localPick === undefined)
                        return {};
                    return Object.assign({ aim: this.aimNow(c) }, (this.localPick ? { target: this.localPick } : {}));
                }
                /** Instant feedback that the press registered: a lean and (phones) a short buzz. The action's sound
                 *  waits for the engine's confirmed hand change, as in Overcooked 2, so a press that does nothing is silent. */
                actionCue() {
                    var _a, _b, _c;
                    this.cueUntil = this.clock + CUE_SECONDS;
                    // Touch controls' haptic tick (Vibration API, or the iOS 18 switch tap); keyboards get none.
                    if (((_a = this.touchLayout) === null || _a === void 0 ? void 0 : _a.active) && !cc_2.sys.isNative)
                        (_c = (_b = window).kitchenBuzz) === null || _c === void 0 ? void 0 : _c.call(_b, 12);
                }
                /** Tell the engine where this page has walked the chef: 10 times a second while walking, once on stopping. */
                reportPosition() {
                    const p = this.predicted, last = this.lastReported, press = this.pressing;
                    if (!p || !this.state || this.state.phase !== 'running' || !this.connected)
                        return;
                    if (last && press === this.lastPress && Math.hypot(p[0] - last[0], p[1] - last[1]) < .005)
                        return;
                    if ((this.manualDirection.x !== 0 || this.manualDirection.y !== 0) && this.clock - this.lastReportAt < .1)
                        return;
                    this.lastReported = [p[0], p[1]];
                    this.lastPress = press;
                    this.lastReportAt = this.clock;
                    this.request('/api/position', Object.assign(Object.assign({ game_id: this.state.game_id, seq: ++this.moveSeq }, this.atBody(p)), (press ? { press: true } : {})))
                        .catch(() => { this.lastReported = null; });
                }
                /** Where the chef is drawn, sent with an interaction so the engine targets from the same spot. */
                atBody(p = this.predicted) {
                    return p && this.resyncSeen >= 0 ? { at: [Math.round(p[0] * 1e4) / 1e4, Math.round(p[1] * 1e4) / 1e4], base: this.resyncSeen } : {};
                }
                clearInput() { this.endAim(); this.heldKeys.clear(); this.touchDirection = { x: 0, y: 0 }; this.touchMoveDirty = false; this.heldThrough = null; const wasMoving = this.manualDirection.x !== 0 || this.manualDirection.y !== 0; this.manualDirection = { x: 0, y: 0 }; if (wasMoving)
                    this.sendMove(0, 0); this.publishControls(); }
                applyTouchLayout() {
                    var _a;
                    if (!this.node || !this.world || !this.state)
                        return;
                    const mobile = !!((_a = this.touchLayout) === null || _a === void 0 ? void 0 : _a.active);
                    // All kitchen art shares one transform; desktop HUD and cover have a readable HTML counterpart on phones.
                    if (mobile) {
                        for (const n of this.node.children)
                            if (n !== this.world && n.name !== 'background' && n.getComponent(cc_2.UITransform)) {
                                if (!this.touchNodeVisibility.has(n))
                                    this.touchNodeVisibility.set(n, n.active);
                                n.active = false;
                            }
                    }
                    else {
                        for (const [n, active] of this.touchNodeVisibility)
                            if (n.isValid)
                                n.active = active;
                        this.touchNodeVisibility.clear();
                        this.world.setScale(1, 1, 1);
                        this.world.setPosition(0, 0);
                        return;
                    }
                    const r = this.touchLayout.boardRect;
                    if (!r || !this.touchLayout.landscape)
                        return;
                    const w = this.touchLayout.width || innerWidth, h = this.touchLayout.height || innerHeight;
                    const screenScale = Math.min(w / 1280, h / 720), gx = (w - 1280 * screenScale) / 2, gy = (h - 720 * screenScale) / 2;
                    const map = this.state.kitchen.map, bw = map.width * TILE + 24, bh = map.height * TILE + 44;
                    const scale = Math.min(r.width / bw, r.height / bh) / screenScale;
                    const cx = MAPX + map.width * TILE / 2 - 640, cy = 360 - (MAPY + map.height * TILE / 2 - 10);
                    this.world.setScale(scale, scale, 1);
                    this.world.setPosition((r.left + r.width / 2 - gx) / screenScale - 640 - cx * scale, 360 - (r.top + r.height / 2 - gy) / screenScale - cy * scale);
                }
                make(name, x, y, w, h, parent = this.node) {
                    const n = new cc_2.Node(name);
                    n.layer = cc_2.Layers.Enum.UI_2D;
                    parent.addChild(n);
                    n.addComponent(cc_2.UITransform).setContentSize(w, h);
                    n.setPosition(x - 640, 360 - y);
                    return n;
                }
                child(parent, name, w, h, x = 0, y = 0) {
                    const n = new cc_2.Node(name);
                    n.layer = cc_2.Layers.Enum.UI_2D;
                    parent.addChild(n);
                    n.addComponent(cc_2.UITransform).setContentSize(w, h);
                    n.setPosition(x, y);
                    return n;
                }
                rect(g, x, y, w, h, fill) { g.fillColor = color(fill); g.rect(x, y, w, h); g.fill(); }
                pixel(l, size) { l.fontFamily = PIXEL; l.fontSize = size; l.lineHeight = size + 4; l.isBold = false; return l; }
                // What Space or E would act on: a faint lift of that surface (Overcooked-style), no frame.
                /** The station Space/E acts on (the one under the chef's front point): a light fill and a 2px denim
                 * frame when there is something to do there, an ink frame alone when it is targeted but idle. */
                facedGlow(g, x, y, w, h, actionable = true) {
                    if (actionable) {
                        g.fillColor = new cc_2.Color(255, 250, 236, 70);
                        g.rect(x, y, w, h);
                        g.fill();
                    }
                    const c = color(actionable ? COLORS.human : COLORS.ink);
                    if (!actionable)
                        c.a = 150;
                    g.strokeColor = c;
                    g.lineWidth = 2;
                    g.rect(x + 1, y + 1, w - 2, h - 2);
                    g.stroke();
                }
                paintBox(n, w, h, fill) {
                    const g = n.getComponent(cc_2.Graphics) || n.addComponent(cc_2.Graphics);
                    g.clear();
                    this.rect(g, -w / 2, -h / 2 - 3, w, h, COLORS.wood);
                    this.rect(g, -w / 2, -h / 2, w, h, fill);
                    return g;
                }
                box(parent, name, x, y, w, h, fill) { const n = this.make(name, x, y, w, h, parent); this.paintBox(n, w, h, fill); return n; }
                text(id, value, x, y, w, h, size = 18, parent = this.node) {
                    const n = this.make(id, x + w / 2, y, w, h, parent);
                    const l = n.addComponent(cc_2.Label);
                    this.writeLabel(l, value);
                    l.fontSize = size;
                    l.lineHeight = size + 6;
                    l.color = color(COLORS.ink);
                    l.fontFamily = 'sans-serif';
                    l.horizontalAlign = cc_2.Label.HorizontalAlign.LEFT;
                    l.verticalAlign = cc_2.Label.VerticalAlign.CENTER;
                    l.overflow = cc_2.Label.Overflow.SHRINK;
                    this.labels[id] = l;
                    return l;
                }
                button(id, title, x, y, w, h, callback, parent = this.node, tone = 'normal') {
                    const n = this.make('button-' + id, x, y, w, h, parent);
                    const labelNode = new cc_2.Node('label');
                    labelNode.layer = cc_2.Layers.Enum.UI_2D;
                    n.addChild(labelNode);
                    labelNode.addComponent(cc_2.UITransform).setContentSize(w - 22, h - 6);
                    const l = labelNode.addComponent(cc_2.Label);
                    this.writeLabel(l, title);
                    this.pixel(l, 24);
                    l.overflow = cc_2.Label.Overflow.SHRINK;
                    l.verticalAlign = cc_2.Label.VerticalAlign.CENTER;
                    this.buttons[id] = { node: n, label: l, callback, enabled: true, width: w, height: h, tone, hover: false };
                    this.styleButton(id);
                    n.on(cc_2.Node.EventType.MOUSE_ENTER, () => { const b = this.buttons[id]; if (b) {
                        b.hover = true;
                        this.styleButton(id);
                    } });
                    n.on(cc_2.Node.EventType.MOUSE_LEAVE, () => { const b = this.buttons[id]; if (b) {
                        b.hover = false;
                        this.styleButton(id);
                    } });
                    n.on(cc_2.Node.EventType.TOUCH_END, () => { const b = this.buttons[id]; if (b === null || b === void 0 ? void 0 : b.enabled) {
                        this.audio.play('ui_click');
                        b.callback();
                    }
                    else if (b)
                        this.audio.play('ui_blocked'); });
                    return n;
                }
                styleButton(id) {
                    const b = this.buttons[id];
                    if (!b)
                        return;
                    // Pressable: 2px ink border over a 3px ink shadow. Selected sits pressed-in on honey;
                    // disabled goes flat on the surface so the two never look alike.
                    const sel = !!b.selected, flat = sel || !b.enabled, dy = sel ? -3 : 0, w = b.width, h = b.height;
                    const fill = sel ? COLORS.honey : !b.enabled ? COLORS.bg : b.tone === 'primary' ? (b.hover ? COLORS.humanHover : COLORS.human)
                        : b.tone === 'danger' ? (b.hover ? COLORS.hotHover : COLORS.hot) : b.hover ? COLORS.honeyTint : COLORS.paper;
                    const g = b.node.getComponent(cc_2.Graphics) || b.node.addComponent(cc_2.Graphics);
                    g.clear();
                    if (!flat)
                        this.rect(g, -w / 2, -h / 2 - 3, w, h, COLORS.ink);
                    this.rect(g, -w / 2, -h / 2 + dy, w, h, fill);
                    g.strokeColor = color(flat && !sel ? COLORS.muted : COLORS.ink);
                    g.lineWidth = 2;
                    g.rect(-w / 2 + 1, -h / 2 + 1 + dy, w - 2, h - 2);
                    g.stroke();
                    // Keyboard focus: an ink ring outside the button (and its shadow) with a gap.
                    if (this.focusId === id) {
                        g.strokeColor = color(COLORS.ink);
                        g.lineWidth = 3;
                        g.rect(-w / 2 - 5, -h / 2 - 8, w + 10, h + 13);
                        g.stroke();
                    }
                    b.label.node.setPosition(0, dy);
                    b.label.color = color(sel ? COLORS.ink : !b.enabled ? COLORS.muted : b.tone === 'primary' || b.tone === 'danger' ? COLORS.paper : COLORS.ink);
                }
                proxyButton(id) {
                    const b = document.createElement('button');
                    b.dataset.control = id;
                    b.tabIndex = -1;
                    b.onclick = () => { var _a; if ((_a = this.buttons[id]) === null || _a === void 0 ? void 0 : _a.enabled)
                        this.buttons[id].callback(); };
                    return b;
                }
                tabOrder() { return cc_2.sys.isNative ? [TAB_ORDER[0], ...this.levelIds.map(id => 'level:' + id), ...TAB_ORDER.slice(1)] : TAB_ORDER; }
                /** One button per level the server lists (menu order), laid out to fit the cover; rebuilt when the list changes. */
                syncLevelButtons(levels) {
                    var _a, _b, _c, _d;
                    if (!cc_2.sys.isNative)
                        return; // Web uses one bounded, scrollable picker instead of a row per level.
                    const sorted = [...levels].sort((a, b) => { var _a, _b; return ((_a = a.menu_order) !== null && _a !== void 0 ? _a : 0) - ((_b = b.menu_order) !== null && _b !== void 0 ? _b : 0); }), ids = sorted.map(l => l.id);
                    if (ids.join() === this.levelIds.join())
                        return;
                    for (const id of this.levelIds) {
                        (_a = this.buttons['level:' + id]) === null || _a === void 0 ? void 0 : _a.node.destroy();
                        delete this.buttons['level:' + id];
                        (_c = (_b = this.controlAccess) === null || _b === void 0 ? void 0 : _b.querySelector(`[data-control="level:${id}"]`)) === null || _c === void 0 ? void 0 : _c.remove();
                    }
                    this.levelIds = ids;
                    const slots = KitchenGeometry_1.levelButtonLayout(ids.length), anchor = (_d = this.controlAccess) === null || _d === void 0 ? void 0 : _d.querySelector('[data-control="main"]');
                    ids.forEach((id, i) => {
                        const r = slots[i];
                        this.pixel(this.button('level:' + id, '', r.x, r.y, r.w, r.h, () => this.post('/api/level', { level: id }), this.cover).getComponentInChildren(cc_2.Label), 12);
                        if (this.controlAccess)
                            this.controlAccess.insertBefore(this.proxyButton('level:' + id), anchor || null);
                    });
                }
                enable(id, enabled) { const b = this.buttons[id]; if (!b)
                    return; if (b.enabled !== enabled) {
                    b.enabled = enabled;
                    this.styleButton(id);
                } }
                writeLabel(label, value) {
                    var _a, _b;
                    this.labelSources.set(label, value);
                    label.string = !cc_2.sys.isNative ? (_b = (_a = window.kitchenI18n) === null || _a === void 0 ? void 0 : _a.t(value)) !== null && _b !== void 0 ? _b : value : value;
                }
                set(id, value) { if (this.labels[id])
                    this.writeLabel(this.labels[id], value); }
                icon(parent, name, x, y, type, scale = 1) {
                    const n = this.make(name, x, y, 42, 42, parent);
                    n.setScale(scale, scale, 1);
                    const g = n.addComponent(cc_2.Graphics);
                    this.drawIcon(g, type);
                    return n;
                }
                drawIcon(g, type) {
                    var _a, _b, _c;
                    g.clear();
                    if (this.useArt && this.artIcon(g.node, type))
                        return;
                    this.art.hide(g.node);
                    const r = (x, y, w, h, c) => this.rect(g, x, y, w, h, c);
                    if (type.startsWith('vessel:')) {
                        const [, , item, stage] = type.split(':');
                        this.drawIcon(g, 'vessel');
                        if (item)
                            r(-10, -4, 20, 13, this.itemColor(item, stage));
                    }
                    else if (type === 'stove') {
                        r(-23, -19, 46, 35, COLORS.wood);
                        r(-20, -15, 40, 28, '#a3aaa0');
                        r(-12, -6, 24, 16, COLORS.ink);
                        r(-8, -3, 16, 10, '#6e746b');
                    }
                    else if (type === 'continuous_counter') {
                        // Continuous worktop is painted once in the map layer.
                    }
                    else if (type.startsWith('source:')) {
                        this.drawIcon(g, 'item:' + type.slice(7) + ':raw');
                    }
                    else if (type.startsWith('item:')) {
                        const [, item, stage] = type.split(':'), c = this.itemColor(item, stage);
                        if (this.cooks(item)) {
                            // Items that cook: a piece on a paper card; ingredients that don't: a plain shape.
                            r(-19, -13, 38, 26, COLORS.paper);
                            r(-14, -10, 28, 20, COLORS.ink);
                            r(-13, -6, 26, 15, c);
                            r(-9, 9, 18, 3, c);
                            r(-6, -2, 4, 4, '#efd3ae');
                            r(3, 3, 6, 3, '#efd3ae');
                        }
                        else {
                            r(-18, -12, 36, 24, c);
                            r(-12, 12, 24, 5, c);
                            if (stage === 'chopped') {
                                r(-2, -12, 3, 27, COLORS.paper);
                                r(-18, -1, 36, 3, COLORS.paper);
                            }
                        }
                    }
                    else if (type.startsWith('assembly:')) {
                        this.drawIcon(g, 'clean_plate');
                        const parts = type.slice(9).split(','), burnt = parts.includes('burnt');
                        let y = -8;
                        for (const layer of this.plateLayers(parts.filter(x => x !== 'burnt'))) {
                            r(-13, y, 26, 5, this.itemColor(layer.item, burnt && this.burns(layer.item) ? 'burnt' : 'ready'));
                            y += 5;
                        }
                    }
                    else if (type === 'counter') {
                        r(-24, -19, 48, 36, COLORS.wood);
                        r(-20, -14, 40, 26, '#b48b5e');
                        r(-24, 12, 48, 8, '#dfbd88');
                        r(-2, -10, 3, 20, COLORS.wood);
                    }
                    else if (type.startsWith('dish:')) {
                        const [, dish, stage] = type.split(':'), item = (_c = (_b = (_a = this.dishById(dish)) === null || _a === void 0 ? void 0 : _a.components) === null || _b === void 0 ? void 0 : _b[0]) === null || _c === void 0 ? void 0 : _c.item;
                        r(-23, -17, 46, 7, '#829fac');
                        r(-21, -14, 42, 30, COLORS.paper);
                        r(-17, -11, 34, 24, '#c4dce0');
                        r(-15, -9, 30, 20, COLORS.paper);
                        r(-12, -5, 24, 15, this.itemColor(item, stage));
                        r(-7, 3, 4, 3, '#d6af74');
                    }
                    else if (type === 'clean_plate' || type === 'dirty_plate' || type === 'plates' || type === 'returns') {
                        r(-22, -15, 44, 28, '#8ca7ac');
                        r(-19, -12, 38, 24, COLORS.paper);
                        r(-14, -8, 28, 16, '#dbe7df');
                        if (type === 'dirty_plate' || type === 'returns') {
                            r(-11, -5, 12, 5, '#917451');
                            r(5, 2, 6, 4, '#917451');
                        }
                        if (type === 'plates') {
                            r(-22, -20, 44, 3, COLORS.paper);
                            r(-22, -24, 44, 3, '#8ca7ac');
                        }
                    }
                    else if (type === 'sink') {
                        r(-23, -18, 46, 36, '#718f95');
                        r(-19, -13, 38, 26, '#bbd6d6');
                        r(-15, -8, 30, 16, '#729ca8');
                        r(8, 13, 5, 14, COLORS.ink);
                        r(-4, 23, 16, 5, COLORS.ink);
                        r(-5, 14, 5, 10, '#b9d6dc');
                    }
                    else if (type === 'vessel') {
                        r(-18, -13, 36, 27, COLORS.ink);
                        r(-14, -10, 28, 21, '#747e75');
                        r(-21, 7, 42, 5, COLORS.ink);
                        r(-24, 1, 7, 7, COLORS.ink);
                        r(17, 1, 7, 7, COLORS.ink);
                        r(-9, 15, 18, 4, '#aab7a4');
                        r(-3, 19, 6, 4, COLORS.ink);
                    }
                    else if (type === 'board') {
                        r(-21, -15, 42, 30, COLORS.wood);
                        r(-18, -11, 36, 23, '#dcb16b');
                        r(-13, -6, 20, 2, '#bd8849');
                        r(-3, 2, 17, 7, '#e8e7dc');
                        r(-13, 3, 10, 5, COLORS.ink);
                    }
                    else if (type === 'serve') {
                        r(-23, -19, 46, 39, COLORS.wood);
                        r(-19, -13, 38, 29, '#4e6654');
                        r(-15, -4, 30, 5, COLORS.paper);
                        r(-10, 1, 20, 5, COLORS.paper);
                        r(-4, 9, 8, 3, '#e7b94c');
                        r(-25, -20, 50, 7, '#c1965c');
                    }
                    else if (type === 'bin') {
                        r(-14, -19, 28, 34, '#656b59');
                        r(-18, 14, 36, 5, COLORS.ink);
                        r(-6, 19, 12, 4, COLORS.ink);
                        r(-8, -13, 3, 24, '#939c84');
                        r(4, -13, 3, 24, '#939c84');
                    }
                    else if (type === 'extinguisher') {
                        r(-10, -21, 20, 34, COLORS.hot);
                        r(-7, -18, 14, 29, '#d6694a');
                        r(-10, -1, 20, 10, COLORS.paper);
                        r(-4, 13, 8, 9, COLORS.ink);
                        r(4, 16, 13, 4, COLORS.ink);
                        r(14, 3, 4, 16, COLORS.ink);
                    }
                    else if (type === 'fire') {
                        r(-12, -18, 24, 27, '#c94d30');
                        r(-6, 9, 12, 14, '#c94d30');
                        r(-17, -10, 8, 17, '#c94d30');
                        r(9, -10, 8, 14, '#c94d30');
                        r(-8, -15, 16, 19, '#efae3e');
                        r(-3, -13, 6, 12, '#ffe29a');
                    }
                    else {
                        const c = FOOD_COLORS[type] || FOOD_COLORS.raw;
                        r(-19, -13, 38, 26, COLORS.paper);
                        r(-14, -10, 28, 20, COLORS.ink);
                        r(-13, -6, 26, 15, c);
                        r(-9, 9, 18, 3, c);
                        r(-6, -2, 4, 4, '#d6af74');
                        r(3, 3, 6, 3, '#d6af74');
                    }
                }
                // Recipe data from the server snapshot: names, colours, cooking states and plating order.
                itemDef(item) { var _a, _b; return item ? (_b = (_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.items) === null || _b === void 0 ? void 0 : _b[item] : undefined; }
                itemLabel(item) { var _a; return ((_a = this.itemDef(item)) === null || _a === void 0 ? void 0 : _a.name) || item; }
                cooks(item) { var _a, _b; return !!((_b = (_a = this.itemDef(item)) === null || _a === void 0 ? void 0 : _a.states) === null || _b === void 0 ? void 0 : _b.includes('cooking')); }
                burns(item) { var _a, _b; return !!((_b = (_a = this.itemDef(item)) === null || _a === void 0 ? void 0 : _a.states) === null || _b === void 0 ? void 0 : _b.includes('burnt')); }
                /** Fallback swatch (no art): burnt is charred, every other stage is the item's own colour. */
                itemColor(item, stage) {
                    var _a;
                    if (stage === 'burnt')
                        return FOOD_COLORS.burnt;
                    return ((_a = this.itemDef(item)) === null || _a === void 0 ? void 0 : _a.color) || FOOD_COLORS[stage] || FOOD_COLORS.ready;
                }
                dishById(id) { var _a, _b; return id ? (((_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.dishes) || ((_b = this.state) === null || _b === void 0 ? void 0 : _b.kitchen.menu) || []).find((d) => d.id === id) : undefined; }
                /** The menu dish a plate is heading for: one whose components include every item on it. */
                targetDish(components) {
                    var _a;
                    return (((_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.menu) || []).find((d) => components.every(x => { var _a; return (_a = d.components) === null || _a === void 0 ? void 0 : _a.some((c) => c.item === x); }));
                }
                plateLayers(components) { var _a; return KitchenGeometry_1.plateLayers((_a = this.targetDish(components)) === null || _a === void 0 ? void 0 : _a.plating, components); }
                /** The item an ingredient source hands out (equipment data; the station id is the last resort). */
                sourceItem(id) { var _a, _b; const e = (_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.map.equipment[id]; return (e === null || e === void 0 ? void 0 : e.item) || ((_b = e === null || e === void 0 ? void 0 : e.params) === null || _b === void 0 ? void 0 : _b.item) || id; }
                artIcon(node, type) {
                    var _a, _b;
                    for (const child of node.children)
                        if (child.name === 'assembly-parts' || child.name === 'supply-symbol' || child.name === 'vessel-contents' || child.name === 'burnt-cue')
                            child.active = false;
                    if (this.useModularArt) {
                        if (type === 'bin') {
                            this.art.hide(node);
                            return true;
                        }
                        const tops = { board: 'top_board', sink: 'top_sink', stove: 'top_stove', returns: 'top_returns', serve: 'serving_window', bin: 'bin' };
                        // The rack is a plain counter top; its extinguisher is drawn as the station's item while present.
                        if (type === 'extinguisher_rack') {
                            this.art.hide(node);
                            return true;
                        }
                        if (type === 'serve') {
                            const facing = (_b = (_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.map.equipment.serve) === null || _b === void 0 ? void 0 : _b.facing;
                            return this.art.tile(node, facing === 'east' ? 'serving_east' : 'serving_west', TILE);
                        }
                        if (tops[type] && this.art.tile(node, tops[type], TILE))
                            return true;
                        if (type.startsWith('source:')) {
                            this.art.hide(node);
                            let symbol = node.getChildByName('supply-symbol');
                            if (!symbol) {
                                symbol = this.child(node, 'supply-symbol', 40, 32, 0, 22 * TILE / 64);
                                symbol.addComponent(cc_2.Graphics);
                            }
                            symbol.active = true;
                            const g = symbol.getComponent(cc_2.Graphics);
                            g.clear();
                            const sourceKey = 'modular/source_' + type.slice(7);
                            if (!this.art.centered(symbol, sourceKey, 28, 28)) {
                                const fallback = symbol.getChildByName('fallback') || this.child(symbol, 'fallback', 28, 28);
                                const fg = fallback.getComponent(cc_2.Graphics) || fallback.addComponent(cc_2.Graphics);
                                fallback.setScale(.6, .6, 1);
                                this.drawIcon(fg, 'item:' + type.slice(7) + ':raw');
                            }
                            return true;
                        }
                    }
                    if (type.startsWith('item:')) {
                        const [, item, stage] = type.split(':'), art = this.itemArt(item, stage, true);
                        return !!art && this.art.centered(node, art.key, art.size, art.size);
                    }
                    if (type.startsWith('dish:')) {
                        const [, dish, stage] = type.split(':');
                        if (!this.art.has(`dishes/${dish}/${stage}`) || !this.art.centered(node, `dishes/${dish}/${stage}`, TILE * .76, TILE * .76))
                            return false;
                        if (stage === 'burnt')
                            this.burntCue(node);
                        return true;
                    }
                    const assembly = type.startsWith('assembly:') ? type.slice(9).split(',') : null;
                    if (assembly && this.plateLayers(assembly.filter(x => x !== 'burnt')).every(l => this.art.has('feedback/' + l.layer))) {
                        this.art.centered(node, 'objects/clean_plate', TILE * .76, TILE * .76);
                        let parts = node.getChildByName('assembly-parts');
                        if (!parts)
                            parts = this.child(node, 'assembly-parts', 44, 44);
                        parts.active = true;
                        for (const child of parts.children)
                            child.active = false;
                        const burnt = assembly.includes('burnt');
                        this.plateLayers(assembly.filter(x => x !== 'burnt')).forEach((layer, i) => {
                            var _a;
                            const item = parts.getChildByName(layer.layer) || this.child(parts, layer.layer, 36, 24);
                            item.active = true;
                            item.setPosition(0, -3 + i * 4);
                            item.setSiblingIndex(parts.children.length - 1);
                            this.art.centered(item, 'feedback/' + layer.layer, 34, 22);
                            // No separate charred sprite: char the layers whose item can burn; reused nodes reset to white.
                            const sprite = (_a = item.getChildByName('reviewed-art')) === null || _a === void 0 ? void 0 : _a.getComponent(cc_2.Sprite);
                            if (sprite)
                                sprite.color = burnt && this.burns(layer.item) ? new cc_2.Color(44, 36, 34, 255) : cc_2.Color.WHITE;
                        });
                        if (burnt)
                            this.burntCue(node);
                        return true;
                    }
                    const keys = { board: 'workstations/board', stove: 'workstations/stove',
                        sink: 'workstations/sink', serve: 'workstations/serve', returns: 'workstations/returns',
                        bin: 'workstations/bin', extinguisher_rack: 'workstations/extinguisher_rack', extinguisher: 'objects/extinguisher',
                        clean_plate: 'objects/clean_plate', dirty_plate: 'objects/dirty_plate',
                        fire: 'vfx/fire_0' };
                    if (type === 'continuous_counter') {
                        this.art.hide(node);
                        return true;
                    }
                    if (type.startsWith('vessel:')) {
                        const [, kind, item, stage] = type.split(':'), drawn = this.drawVessel(node, kind, 1, item, stage);
                        if (!drawn)
                            return false;
                        let contents = node.getChildByName('vessel-contents');
                        if (!contents)
                            contents = this.child(node, 'vessel-contents', 22, 22, 0, 4);
                        const art = item && drawn === 'empty' ? this.itemArt(item, stage, false) : null;
                        contents.active = !!art && this.art.centered(contents, art.key, 20, 20);
                        return true;
                    }
                    const contents = node.getChildByName('vessel-contents');
                    if (contents)
                        contents.active = false;
                    const key = keys[type];
                    if (!key)
                        return false;
                    const size = key.startsWith('workstations/') ? 49 : key.startsWith('ingredients/') ? 29 : TILE * .76;
                    if (!this.art.centered(node, key, size, size))
                        return false;
                    return true;
                }
                /** Smoke over a burnt dish, wherever it is: upper layers can hide the charred layer. */
                burntCue(node) {
                    var _a;
                    let cue = node.getChildByName('burnt-cue');
                    if (!cue)
                        cue = this.child(node, 'burnt-cue', 26, 32, 14, 20);
                    cue.active = this.art.show(cue, 'vfx/smoke_3', 26, 32);
                    cue.setSiblingIndex(node.children.length - 1);
                    const sprite = (_a = cue.getChildByName('reviewed-art')) === null || _a === void 0 ? void 0 : _a.getComponent(cc_2.Sprite);
                    if (sprite)
                        sprite.color = new cc_2.Color(120, 112, 106, 255);
                }
                /** Art for one item state: a chopped item that is plated chopped shows its plating layer
                 * (when allowed), then food/<item>_<stage>, then ingredients/<item>/<stage> (chopped: prepared). */
                itemArt(item, stage, layer) {
                    var _a, _b;
                    if (layer && stage === 'chopped' && ((_b = (_a = this.itemDef(item)) === null || _a === void 0 ? void 0 : _a.platable_states) === null || _b === void 0 ? void 0 : _b.includes('chopped')) && this.art.has('feedback/' + item))
                        return { key: 'feedback/' + item, size: 30 };
                    if (this.art.has(`food/${item}_${stage}`))
                        return { key: `food/${item}_${stage}`, size: 30 };
                    for (const key of [`ingredients/${item}/${stage}`, `ingredients/${item}/${stage === 'chopped' ? 'prepared' : stage}`])
                        if (this.art.has(key))
                            return { key, size: 29 };
                    return null;
                }
                /** A vessel of the given kind (server data), turned along its station or the holder's facing. */
                /** A vessel of the given kind (server data), turned along its station or the holder's facing.
                 * A frame drawn with the contents in it (<vessel frame>/<item>/<stage>) is used when it exists:
                 * returns 'filled' then, so the caller does not draw the contents again; 'empty' for the
                 * vessel alone; '' when there is no art. */
                drawVessel(node, kind, scale = 1, item, stage) {
                    var _a, _b, _c, _d, _e;
                    const station = ((_a = node.parent) === null || _a === void 0 ? void 0 : _a.name.startsWith('station-')) ? node.parent.name.slice(8) : '';
                    const holder = ((_b = node.parent) === null || _b === void 0 ? void 0 : _b.name) === 'body' ? (_c = node.parent.parent) === null || _c === void 0 ? void 0 : _c.name : '';
                    const facing = holder ? (_e = (_d = this.state) === null || _d === void 0 ? void 0 : _d.kitchen.chefs[holder]) === null || _e === void 0 ? void 0 : _e.facing : '';
                    const axis = station ? KitchenGeometry_1.stationView(this.state.kitchen.map, station).device_axis : (facing === 'up' || facing === 'down' ? 'vertical' : 'horizontal');
                    // A pan's handle points at the chef: on a station, toward its operation side; in hand, back
                    // toward the holder. vertical = handle south, horizontal = east, plus pan_west / pan_north.
                    const handle = station ? KitchenGeometry_1.panHandleSide(this.state.kitchen.map.equipment[station]) : holder ? { down: 'north', up: 'south', left: 'east', right: 'west' }[facing] || 'east' : '';
                    const handleKey = handle ? `modular/${kind}_${{ south: 'vertical', east: 'horizontal', west: 'west', north: 'north' }[handle]}` : '';
                    const turned = !!handleKey && this.art.has(handleKey);
                    const stem = [kind, VESSEL_ART_FALLBACK].find(stem => !!stem && this.art.has(`modular/${stem}_${axis}`));
                    const base = turned ? handleKey : stem ? `modular/${stem}_${axis}` : this.art.has('objects/' + kind) ? 'objects/' + kind : 'objects/' + VESSEL_ART_FALLBACK;
                    const upright = turned ? handle === 'north' || handle === 'south' : axis === 'vertical';
                    const filled = item ? `${base}/${item}/${stage}` : '';
                    const key = filled && this.art.has(filled) ? filled : base;
                    if (!this.art.centered(node, key, TILE * (upright ? .62 : .76) * scale, TILE * .76 * scale))
                        return '';
                    return key === filled ? 'filled' : 'empty';
                }
                closingSummary(k, won, summary) {
                    const target = k.goals.target_money;
                    // Each line ends in fixed text so its translation template cannot swallow the next line.
                    return `净收入 ¥${k.money}（目标 ¥${target}）` + (won ? '' : `，还差 ¥${Math.max(0, target - k.money)} 元`)
                        + `\n完成 ${k.served} 单`;
                }
                // The result screen's one button: the next level after a win, the same level otherwise.
                nextRound(s) {
                    var _a;
                    const levels = [...(s.levels || [])].sort((a, b) => { var _a, _b; return ((_a = a.menu_order) !== null && _a !== void 0 ? _a : 0) - ((_b = b.menu_order) !== null && _b !== void 0 ? _b : 0); });
                    const here = levels.findIndex((l) => { var _a; return l.id === ((_a = s.kitchen) === null || _a === void 0 ? void 0 : _a.level_id); }), next = levels[here + 1];
                    if (!s.won || here < 0)
                        return { id: (_a = s.kitchen) === null || _a === void 0 ? void 0 : _a.level_id, label: '再来一次' };
                    return next ? { id: next.id, label: '下一关' } : { id: levels[here].id, label: '再玩一遍' };
                }
                // A short 3·2·1 on the result card, then one request chooses the level and starts at the same pace.
                startNext() {
                    if (this.countdown || !this.state || this.pending)
                        return;
                    // Ignore presses in the card's first second: Space/A may still be mashed from the last order.
                    if (this.endedSeen.round !== this.state.game_id || Date.now() - this.endedSeen.at < 1000)
                        return;
                    const { id } = this.nextRound(this.state), round = this.state.game_id;
                    const step = (n) => {
                        var _a, _b;
                        if (((_a = this.state) === null || _a === void 0 ? void 0 : _a.game_id) !== round || ((_b = this.state) === null || _b === void 0 ? void 0 : _b.phase) !== 'ended') {
                            this.countdown = 0;
                            return;
                        }
                        if (n === 0) {
                            this.countdown = 0;
                            this.post('/api/next', { level: id });
                            return;
                        }
                        this.countdown = n;
                        this.set('coverTitle', String(n));
                        this.set('coverText', '');
                        this.scheduleOnce(() => step(n - 1), .3);
                    };
                    step(3);
                }
                itemName(f) {
                    if (!f)
                        return '空手';
                    if (f.plate_id) {
                        if (f.stage === 'burnt')
                            return '糊菜';
                        const dish = this.dishById(f.dish) || this.wholeDish(f);
                        return dish ? dish.name : '待组装 · ' + this.plateItems(f).map((x) => this.itemLabel(x)).join('+');
                    }
                    return f.meaning || STAGES[f.stage] || f.stage;
                }
                plateItems(f) { var _a; return ((_a = f.components) === null || _a === void 0 ? void 0 : _a.length) ? f.components : f.ingredient ? [f.ingredient] : []; }
                /** A dish drawn as one plated sprite: exactly the plate's items and no plating layers. */
                wholeDish(f) {
                    var _a, _b;
                    const items = Array.from(new Set(this.plateItems(f))).sort().join();
                    const same = (d) => Array.from(new Set((d.components || []).map((c) => c.item))).sort().join() === items;
                    // The menu decides first; a servable dish that is off this level's menu still gets its plate art.
                    const dish = (((_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.menu) || []).find(same) || (((_b = this.state) === null || _b === void 0 ? void 0 : _b.kitchen.dishes) || []).find(same);
                    return dish && !dish.plating ? dish : undefined;
                }
                itemStage(f) {
                    var _a, _b, _c;
                    // Vessels (any kind) carry their contents; the kind comes from the server.
                    // Only real vessels: in-flight items always carry a contents field, null unless they are one.
                    if (f && (f.vessel || f.contents))
                        return `vessel:${f.vessel || ''}` + (((_a = f.contents) === null || _a === void 0 ? void 0 : _a.ingredient) ? `:${f.contents.ingredient}:${f.contents.stage}` : '');
                    if ((f === null || f === void 0 ? void 0 : f.plate_id) && this.plateItems(f).length) {
                        const whole = this.wholeDish(f);
                        if (whole)
                            return `dish:${whole.id}:${f.stage}`;
                        // Burnt plates keep their layers (burnt dishes can be served); items that burn are drawn charred.
                        return 'assembly:' + this.plateItems(f).join(',') + (f.stage === 'burnt' ? ',burnt' : '');
                    }
                    if (f === null || f === void 0 ? void 0 : f.ingredient) {
                        const chopping = this.useArt && f.stage === 'raw' && f.chop_remaining < (((_c = (_b = this.state) === null || _b === void 0 ? void 0 : _b.rules) === null || _c === void 0 ? void 0 : _c.chop_seconds) || 6) && this.art.has(`ingredients/${f.ingredient}/processing`);
                        return `item:${f.ingredient}:${chopping ? 'processing' : f.stage}`;
                    }
                    return f === null || f === void 0 ? void 0 : f.stage;
                }
                chef(parent, name, x, y, who, scale = 1) {
                    const n = this.make(name, x, y, 40, 64, parent);
                    n.setScale(scale, scale, 1);
                    const shadow = this.child(n, 'contact-shadow', 40, 10, 0, -29), sg = shadow.addComponent(cc_2.Graphics);
                    if (this.useModularArt)
                        shadow.setPosition(0, 0);
                    const shade = new cc_2.Color(65, 48, 31, 46);
                    sg.fillColor = shade;
                    sg.rect(-16, -3, 32, 6);
                    sg.rect(-12, -5, 24, 10);
                    sg.fill();
                    const body = this.child(n, 'body', 40, 64), g = body.addComponent(cc_2.Graphics);
                    const r = (x, y, w, h, c) => this.rect(g, x, y, w, h, c);
                    // Pixel-art body stays upright as a single directional sprite; limbs are
                    // separate nodes so footsteps and chopping never move the chef's position.
                    r(-17, -30, 34, 5, '#a99470');
                    r(-16, -12, 32, 23, COLORS[who]);
                    r(-9, -10, 18, 17, COLORS.paper);
                    r(-12, 8, 24, 21, COLORS.ink);
                    r(-10, 10, 20, 18, '#e4b888');
                    r(-17, 29, 34, 8, COLORS.paper);
                    r(-12, 37, 24, 7, COLORS.paper);
                    r(-14, 28, 28, 4, '#d4ccb4');
                    const eyes = this.child(body, 'eyes', 20, 8, 0, 19), eyeG = eyes.addComponent(cc_2.Graphics);
                    this.rect(eyeG, -7, -1, 3, 4, COLORS.ink);
                    this.rect(eyeG, 4, -1, 3, 4, COLORS.ink);
                    const profile = this.child(body, 'profile', 26, 24), profileG = profile.addComponent(cc_2.Graphics);
                    this.rect(profileG, -10, 10, 20, 18, '#e4b888');
                    this.rect(profileG, 10, 15, 4, 7, '#e4b888');
                    this.rect(profileG, 5, 18, 3, 4, COLORS.ink);
                    profile.active = false;
                    const back = this.child(body, 'back', 32, 40), backG = back.addComponent(cc_2.Graphics);
                    this.rect(backG, -10, 10, 20, 18, '#78624b');
                    this.rect(backG, -10, -10, 20, 18, COLORS[who]);
                    back.active = false;
                    const limb = (id, w, h, x, y, fill) => {
                        const node = this.child(body, id, w, h, x, y), lg = node.addComponent(cc_2.Graphics);
                        this.rect(lg, -w / 2, -h / 2, w, h, fill);
                        return node;
                    };
                    const leftLeg = limb('left-leg', 8, 15, -7, -24, COLORS.ink), rightLeg = limb('right-leg', 8, 15, 7, -24, COLORS.ink);
                    const leftArm = limb('left-arm', 6, 14, -19, -4, '#dbab7c'), rightArm = limb('right-arm', 6, 14, 19, -4, '#dbab7c');
                    const knife = this.child(rightArm, 'knife', 14, 5, 9, -5), kg = knife.addComponent(cc_2.Graphics);
                    this.rect(kg, -1, -2, 11, 4, '#d8ded5');
                    this.rect(kg, 9, -1, 4, 3, COLORS.ink);
                    knife.active = false;
                    return n;
                }
                async request(path, body) {
                    const hosted = typeof window !== 'undefined' ? window.chefjeffHostedRequest : null;
                    if (hosted)
                        return hosted(path, body);
                    return new Promise((resolve, reject) => {
                        const xhr = new XMLHttpRequest();
                        xhr.open(body ? 'POST' : 'GET', this.endpoint + path, true);
                        xhr.timeout = 5000;
                        xhr.onload = () => { try {
                            const data = JSON.parse(xhr.responseText);
                            xhr.status === 200 ? resolve(data) : reject(new Error(data.error || '操作失败'));
                        }
                        catch (e) {
                            reject(new Error('厨房返回了无效数据'));
                        } };
                        xhr.onerror = () => reject(new Error('无法连接厨房后端'));
                        xhr.ontimeout = () => reject(new Error('厨房连接超时'));
                        if (body)
                            xhr.setRequestHeader('Content-Type', 'application/json');
                        xhr.send(body ? JSON.stringify(body) : null);
                    });
                }
                /** Show a state from a poll or from a gameplay reply; an older reply arriving late is ignored. */
                applyState(next, sent) {
                    var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m, _o, _p, _q;
                    const older = typeof next.state_seq === 'number' && typeof ((_a = this.state) === null || _a === void 0 ? void 0 : _a.state_seq) === 'number' && next.state_seq <= this.state.state_seq;
                    if (older && this.connected && next.game_id === this.state.game_id)
                        return;
                    // A live old round may keep its backend until the player approves
                    // restarting it. Do not pair new Space controls with old rules.
                    if (!((_c = (_b = next.kitchen) === null || _b === void 0 ? void 0 : _b.map) === null || _c === void 0 ? void 0 : _c.layout_version) || ((_d = next.release) === null || _d === void 0 ? void 0 : _d.version) !== '0.6.0-beta.2') {
                        this.connected = false;
                        this.clearInput();
                        this.cover.active = true;
                        this.set('coverTitle', '等待厨房更新');
                        this.set('coverText', '新版页面已就绪，厨房服务仍在保留旧对局。\n服务更新后会自动连接，请先完成更新确认。');
                        for (const id of ['main', 'reset', 'cover-connection'])
                            this.enable(id, false);
                        this.hideLoading();
                        return;
                    }
                    this.enable('cover-connection', true);
                    if (this.mounted && this.mountedLayout !== next.kitchen.map.layout_version) {
                        for (const n of [...this.mapNodes, ...Object.values(this.ground), ...Object.values(this.flights)])
                            n.destroy();
                        this.devices = {};
                        this.people = {};
                        this.motions = {};
                        this.potEffects = {};
                        this.cabinetFires = {};
                        this.ground = {};
                        this.flights = {};
                        this.groundStages = {};
                        this.mounted = false;
                    }
                    if (next.game_id !== ((_e = this.state) === null || _e === void 0 ? void 0 : _e.game_id) || !this.connected) {
                        this.menuSignature = '';
                        this.foodStages = {};
                        this.readyUntil = {};
                        this.activeClock = 0;
                        if (this.mounted)
                            for (const who of ['human', 'jeff'])
                                this.locate(this.people[who], next.kitchen.chefs[who].position);
                    }
                    if (next.phase !== 'running' || next.game_id !== ((_f = this.state) === null || _f === void 0 ? void 0 : _f.game_id) || (this.spaceItemId !== null && (((_g = next.kitchen.chefs.human.holding) === null || _g === void 0 ? void 0 : _g.id) !== this.spaceItemId || next.kitchen.chefs.human.can_throw === false)))
                        this.clearInput();
                    if (next.game_id !== ((_h = this.state) === null || _h === void 0 ? void 0 : _h.game_id)) {
                        this.moveSeq = Date.now() * 1000;
                        this.predicted = this.lastReported = this.lastAim = null;
                        this.resyncSeen = -1;
                        this.sprintAt = -Infinity;
                    }
                    if (next.phase !== 'running')
                        this.localPick = undefined;
                    const was = next.game_id === ((_j = this.state) === null || _j === void 0 ? void 0 : _j.game_id) ? (_m = (_l = (_k = this.state) === null || _k === void 0 ? void 0 : _k.kitchen) === null || _l === void 0 ? void 0 : _l.chefs) === null || _m === void 0 ? void 0 : _m.human : null, now = (_p = (_o = next.kitchen) === null || _o === void 0 ? void 0 : _o.chefs) === null || _p === void 0 ? void 0 : _p.human;
                    const working = (c) => !!c && ['chop', 'wash', 'extinguish'].includes(c.action_kind) && (c.working || (c.travel_remaining || 0) > 0);
                    if (was && !was.holding && (now === null || now === void 0 ? void 0 : now.holding))
                        this.pickedAt = this.clock;
                    this.state = next;
                    this.connected = true;
                    this.received = this.lastStateAt = this.clock;
                    this.stateSentAt = sent;
                    if (working(now) && !working(was)) {
                        this.heldThrough = this.rawDirection();
                        this.refreshMovement();
                    }
                    const frameRate = next.phase === 'running' ? (((_q = this.touchLayout) === null || _q === void 0 ? void 0 : _q.active) ? 30 : 60) : 15;
                    if (cc_2.game.frameRate !== frameRate)
                        cc_2.game.frameRate = frameRate;
                    if (!cc_2.sys.isNative)
                        window.dispatchEvent(new CustomEvent('kitchen-state', { detail: { game_id: next.game_id, phase: next.phase, connection: next.connection, memory: next.memory, limits: next.limits, release: next.release, communication: next.communication, hosted: next.hosted } }));
                    if (!this.mounted)
                        this.mountMap();
                    this.processEvents();
                    this.render();
                    this.hideLoading();
                    this.audio.onState(next);
                }
                async bookmark() {
                    if (!this.state || this.hidden)
                        return;
                    const round = this.state.game_id;
                    const notice = (message) => {
                        var _a;
                        if (!cc_2.sys.isNative && ((_a = this.state) === null || _a === void 0 ? void 0 : _a.game_id) === round)
                            window.dispatchEvent(new CustomEvent('kitchen-bookmark-notice', { detail: { message } }));
                    };
                    if (!this.connected) {
                        notice('标记未保存，请重试。');
                        return;
                    }
                    // Independent request: do not set pending, clear input, poll, or stop a job.
                    try {
                        const data = await this.request('/api/bookmark', { game_id: round,
                            request_id: Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) });
                        notice(data.merged ? '已延长标记片段' : '已标记当前片段');
                    }
                    catch (_) {
                        notice('标记未确认，请检查导出记录。');
                    }
                }
                async post(path, extra = {}) {
                    if (path === '/api/action' || path === '/api/pause' || path === '/api/end' || path === '/api/reset' || path === '/api/restart' || path === '/api/next')
                        this.clearInput();
                    if ((this.pending && path !== '/api/pause') || !this.state)
                        return;
                    // After closing (or while paused) gameplay input is not sent: the server would only refuse it.
                    if (['/api/action', '/api/interact'].includes(path) && this.state.phase !== 'running')
                        return;
                    this.pending = true;
                    this.render();
                    let reply = null;
                    const sent = this.clock;
                    try {
                        reply = await this.request(path, Object.assign({ game_id: this.state.game_id, request_id: Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) }, extra));
                    }
                    catch (e) {
                        this.audio.play('ui_blocked');
                        this.set('event', e.message);
                    }
                    finally {
                        this.pending = false;
                        // Gameplay replies carry the resulting state: draw it now instead of a round trip later.
                        if (reply === null || reply === void 0 ? void 0 : reply.state) {
                            try {
                                this.applyState(reply.state, sent);
                            }
                            catch (_) {
                                this.poll();
                            }
                        }
                        else
                            this.poll();
                    }
                }
                act(key) { var _a; const a = (_a = this.state) === null || _a === void 0 ? void 0 : _a.actions.find(a => a.key === key); if (a)
                    this.post('/api/action', { action: key, expected: a.expected }); }
                modularWallDecor(wallNode, x, y, hasSouth) {
                    var _a;
                    if (y !== 0 || hasSouth)
                        return;
                    const faceH = KitchenGeometry_1.GRID_ART.northFace * TILE / KitchenGeometry_1.GRID_ART.unit;
                    for (const decor of ((_a = this.state.kitchen.map.presentation) === null || _a === void 0 ? void 0 : _a.decorations) || []) {
                        if (decor.cell[0] !== x)
                            continue;
                        const n = this.child(wallNode, 'wall-decor-' + decor.asset, TILE, TILE, 0, -TILE / 2 + faceH / 2);
                        this.art.centered(n, 'modular/' + decor.asset, TILE * .65, faceH * .64);
                    }
                }
                drawWall(n, x, y, map, walls) {
                    const neighbours = KitchenGeometry_1.wallNeighbours(walls, x, y);
                    // One logical tile is one visible boundary tile. The north-facing wall
                    // uses an inset cutaway face, rather than shifting other walls/counters.
                    const cap = this.child(n, 'wall-top', TILE, TILE);
                    this.art.centered(cap, 'modular/wall_cap', TILE, TILE);
                    if (y === 0 && !neighbours.south) {
                        const h = KitchenGeometry_1.GRID_ART.northFace * TILE / KitchenGeometry_1.GRID_ART.unit;
                        const face = this.child(n, 'wall-front', TILE, h, 0, -TILE / 2 + h / 2);
                        this.art.region(face, 'modular/wall_face', 0, 0, 64, KitchenGeometry_1.GRID_ART.northFace, TILE, h);
                    }
                    const serve = map.equipment.serve;
                    const boundary = serve && (serve.facing === 'west' ? map.width - 1 : serve.facing === 'east' ? 0 : -1);
                    if (x === boundary && y === (serve === null || serve === void 0 ? void 0 : serve.cell[1])) {
                        const slot = this.child(n, 'serving-aperture', TILE * .82, TILE * .42), g = slot.addComponent(cc_2.Graphics);
                        this.rect(g, -TILE * .41, -TILE * .21, TILE * .82, TILE * .42, '#344756');
                        this.rect(g, -TILE * .36, -TILE * .15, TILE * .72, TILE * .30, '#75543a');
                        this.rect(g, -TILE * .36, -TILE * .15, TILE * .72, 3, '#c99551');
                    }
                    this.modularWallDecor(n, x, y, neighbours.south);
                }
                cabinetArt(n, id) {
                    const cabinet = this.child(n, 'cabinet-base', TILE, TILE);
                    // One body per station. Runs reuse fixed-camera modules, never rotated sprites.
                    this.art.tile(cabinet, KitchenGeometry_1.cabinetModule(this.state.kitchen.map, id), TILE, 0, this.prepSampleBoard(id) ? 0 : -KitchenGeometry_1.GRID_ART.cabinetSpriteLift * TILE / KitchenGeometry_1.GRID_ART.unit);
                    cabinet.setSiblingIndex(0);
                }
                prepSampleBoard(id) { return this.prepSample && this.state.kitchen.level === 2 && id === 'b1'; }
                workSurfaceY(id) { return this.prepSampleBoard(id) ? KitchenGeometry_1.GRID_ART.cabinetSpriteLift * TILE / KitchenGeometry_1.GRID_ART.unit : KitchenGeometry_1.surfaceOffset(); }
                equipmentArt(n, id) {
                    var _a;
                    const st = this.state.kitchen.stations[id], axis = KitchenGeometry_1.stationView(this.state.kitchen.map, id).device_axis;
                    const g = n.getComponent(cc_2.Graphics);
                    g.clear();
                    this.art.hide(n);
                    for (const name of ['supply-symbol', 'assembly-parts', 'vessel-contents']) {
                        const child = n.getChildByName(name);
                        if (child)
                            child.active = false;
                    }
                    n.setPosition(0, this.workSurfaceY(id));
                    if (this.prepSampleBoard(id))
                        n.setPosition(0, this.workSurfaceY(id) + 11);
                    if (id.startsWith('bin')) {
                        const view = KitchenGeometry_1.trashView(this.state.kitchen.map, id);
                        n.setScale(view.mirror ? -1 : 1, 1, 1);
                        this.art.centered(n, view.axis === 'vertical' ? 'feedback/trash_opening_vertical' : 'feedback/trash_opening', TILE * .8, TILE * .8);
                        return;
                    }
                    if (st.counter)
                        return;
                    if (id === 'serve') {
                        // Neutral double chevron points from the chef into the serving boundary.
                        const east = this.state.kitchen.map.equipment[id].facing === 'west', d = east ? 1 : -1;
                        g.fillColor = color('#344756');
                        for (const x of [-10, 5]) {
                            g.moveTo(d * (x - 5), -12);
                            g.lineTo(d * (x + 6), 0);
                            g.lineTo(d * (x - 5), 12);
                            g.lineTo(d * (x - 5), 5);
                            g.lineTo(d * (x - 1), 0);
                            g.lineTo(d * (x - 5), -5);
                            g.close();
                            g.fill();
                        }
                        return;
                    }
                    const kind = /^b[0-9]+$/.test(id) ? 'board' : id === 'returns' ? 'returns' : id === 'sink' ? 'sink' : '';
                    if (kind) {
                        this.art.centered(n, 'modular/device_' + kind + '_' + axis, TILE * .84, this.prepSampleBoard(id) ? 28 : TILE * .84);
                        return;
                    }
                    if (st.stove) {
                        this.art.centered(n, 'modular/top_stove', TILE * .82, TILE * .82);
                        return;
                    }
                    if (((_a = this.state.kitchen.map.equipment[id]) === null || _a === void 0 ? void 0 : _a.type) === 'ingredient_source') {
                        this.art.centered(n, 'modular/source_' + this.sourceItem(id), TILE * .6, TILE * .6);
                        return;
                    }
                }
                mountMap() {
                    const previous = new Set(this.node.children);
                    const map = this.state.kitchen.map, walls = new Set(map.walls.map((p) => p.join(','))), cells = new Set(Object.values(map.equipment).reduce((all, e) => all.concat((e.cells || [e.cell]).map((c) => c.join(','))), []));
                    const cabinetCells = new Set(Object.values(map.equipment).reduce((all, e) => all.concat((e.cells || [e.cell]).map((c) => c.join(','))), []));
                    if (this.useModularArt) {
                        for (let y = 0; y < map.height; y++)
                            for (let x = 0; x < map.width; x++) {
                                if (walls.has(`${x},${y}`) && (x === 0 || y === 0 || x === map.width - 1 || y === map.height - 1))
                                    continue;
                                const floor = this.make('floor-art', MAPX + (x + .5) * TILE, MAPY + (y + .5) * TILE, TILE, TILE);
                                this.art.centered(floor, `modular/floor_${(x - 1 + 4) % 4}_${(y - 1 + 4) % 4}`, TILE, TILE);
                            }
                    }
                    this.depthEntries = [];
                    this.world = this.child(this.node, 'kitchen-world', 1280, 720);
                    for (let y = 0; y < map.height; y++)
                        for (let x = 0; x < map.width; x++) {
                            const wall = walls.has(`${x},${y}`), n = this.make('tile', MAPX + (x + .5) * TILE, MAPY + (y + .5) * TILE, TILE, TILE, this.world);
                            n.setScale(TILE / 52, TILE / 52, 1);
                            const g = n.addComponent(cc_2.Graphics), r = (a, b, w, h, c) => this.rect(g, a, b, w, h, c);
                            if (wall) {
                                r(-26, -26, 52, 52, COLORS.wood);
                                r(-26, -15, 52, 41, COLORS.wall);
                                r(-24, 5, 48, 17, '#c5a074');
                                r(-24, -13, 23, 15, '#bb9062');
                                r(2, -13, 22, 15, '#bb9062');
                                r(-26, -24, 52, 7, '#634a37');
                            }
                            else {
                                r(-26, -26, 52, 52, '#c7bea0');
                                r(-25, -24, 49, 49, (x + y) % 2 ? (x < 7 ? '#e1d4ad' : '#cbd3b6') : (x < 7 ? '#eee3c1' : '#dce0c7'));
                                r(-23, 22, 45, 2, '#f1e7cc');
                                if (cells.has(`${x},${y}`)) {
                                    r(-26, -26, 52, 52, COLORS.counter);
                                    if (!cells.has(`${x},${y - 1}`))
                                        r(-26, 22, 52, 4, COLORS.counterLight);
                                    if (!cells.has(`${x},${y + 1}`))
                                        r(-26, -26, 52, 4, COLORS.counterEdge);
                                }
                            }
                            if (this.useModularArt) {
                                n.setScale(1, 1, 1);
                                g.clear();
                                if (wall) {
                                    this.drawWall(n, x, y, map, walls);
                                    this.registerDepth(n, () => KitchenGeometry_1.depthOrder(y, 'solid'));
                                }
                            }
                            else if (this.useArt) {
                                const key = wall ? (y === 0 ? 'environment/wall' : 'environment/counter') : cells.has(`${x},${y}`) ? 'environment/counter' : 'environment/floor_cream';
                                if (this.art.show(n, key, 52, 52)) {
                                    g.clear();
                                    if (wall && y !== 0) {
                                        const edge = this.child(n, 'wall-border', 52, 52), eg = edge.addComponent(cc_2.Graphics);
                                        eg.strokeColor = color(COLORS.wood);
                                        eg.lineWidth = 3;
                                        eg.rect(-25, -25, 50, 50);
                                        eg.stroke();
                                    }
                                }
                            }
                            if (!wall)
                                this.registerDepth(n, () => -1000);
                            if (wall && this.useModularArt)
                                n.getComponent(cc_2.UITransform).setAnchorPoint(.5, .5 - (y === map.height - 1 ? KitchenGeometry_1.GRID_ART.frontWallHeight / 64 : KitchenGeometry_1.GRID_ART.wallHeight / 64));
                        }
                    // Signs sit on the wall, leaving all walkable tiles visible.
                    this.text('prep-sign', this.useModularArt ? '' : this.state.kitchen.level === 2 ? '长 台 厨 房' : '备 菜 区', MAPX + TILE, MAPY + 25, 295, 24, 14).horizontalAlign = cc_2.Label.HorizontalAlign.CENTER;
                    this.text('cook-sign', this.useModularArt ? '' : this.state.kitchen.level === 2 ? '' : '烹 饪 区', MAPX + 8 * TILE, MAPY + 25, 225, 24, 14).horizontalAlign = cc_2.Label.HorizontalAlign.CENTER;
                    for (const [id, entry] of Object.entries(map.equipment)) {
                        const e = entry, n = this.make('station-' + id, MAPX + (e.cell[0] + .5) * TILE, MAPY + (e.cell[1] + .5) * TILE, TILE, TILE, this.world);
                        const overlay = this.child(n, 'surface-feedback', TILE, TILE), g = overlay.addComponent(cc_2.Graphics);
                        if (this.useModularArt)
                            this.cabinetArt(n, id);
                        this.registerDepth(n, () => KitchenGeometry_1.depthOrder(e.cell[1], 'solid') + .01);
                        const art = new cc_2.Node('equipment');
                        art.layer = cc_2.Layers.Enum.UI_2D;
                        n.addChild(art);
                        art.addComponent(cc_2.UITransform).setContentSize(44, 44);
                        art.setPosition(0, 6);
                        if (this.useModularArt)
                            art.setPosition(0, 0);
                        this.drawIcon(art.addComponent(cc_2.Graphics), this.state.kitchen.stations[id].counter ? 'continuous_counter' : this.state.kitchen.stations[id].stove ? 'vessel' : id.startsWith('bin') ? 'bin' : /^b[0-9]/.test(id) ? 'board' : e.type === 'ingredient_source' ? 'source:' + this.sourceItem(id) : this.useArt && id === 'extinguisher' ? 'extinguisher_rack' : id);
                        if (this.useModularArt)
                            this.equipmentArt(art, id);
                        const ln = new cc_2.Node('label');
                        ln.layer = cc_2.Layers.Enum.UI_2D;
                        n.addChild(ln);
                        ln.setPosition(0, -19);
                        ln.addComponent(cc_2.UITransform).setContentSize(56, 18);
                        const l = ln.addComponent(cc_2.Label);
                        l.fontSize = 10;
                        l.lineHeight = 13;
                        l.isBold = true;
                        l.color = color(COLORS.ink);
                        l.overflow = cc_2.Label.Overflow.SHRINK;
                        const status = new cc_2.Node('food');
                        status.layer = cc_2.Layers.Enum.UI_2D;
                        n.addChild(status);
                        status.addComponent(cc_2.UITransform).setContentSize(30, 30);
                        status.setPosition(11, 7);
                        status.setScale(this.useModularArt ? 1 : .6, this.useModularArt ? 1 : .6, 1);
                        status.addComponent(cc_2.Graphics);
                        if (this.useModularArt) {
                            status.setPosition(0, this.workSurfaceY(id) + (this.prepSampleBoard(id) ? 18 : 0));
                            if (this.prepSampleBoard(id))
                                status.setScale(.5, .5, 1);
                            ln.active = false; // Workstations are identified by equipment, not map captions.
                        }
                        if (id === 'sink') {
                            const bubbles = new cc_2.Node('washing');
                            bubbles.layer = cc_2.Layers.Enum.UI_2D;
                            n.addChild(bubbles);
                            const bg = bubbles.addComponent(cc_2.Graphics);
                            this.rect(bg, -16, 0, 6, 6, '#eaf7f5');
                            this.rect(bg, 0, 7, 7, 7, '#eaf7f5');
                            this.rect(bg, 12, -2, 5, 5, '#eaf7f5');
                            bubbles.active = false;
                        }
                        if (this.useModularArt)
                            n.getComponent(cc_2.UITransform).setAnchorPoint(.5, .5 - this.workSurfaceY(id) / TILE);
                        this.devices[id] = { node: n, graphics: g, label: l };
                        if (!this.state.kitchen.stations[id].stove) {
                            const flame = this.child(n, 'cabinet-fire', 58, 64, 0, 18);
                            flame.addComponent(cc_2.Graphics);
                            flame.active = false;
                            this.cabinetFires[id] = flame;
                            const smoke = this.child(flame, 'smoke', 36, 44, 8, 36);
                            smoke.addComponent(cc_2.Graphics);
                        }
                        if (this.state.kitchen.stations[id].stove) {
                            const steam = this.child(n, 'cooking-steam', 32, 40, -11, 38), sg = steam.addComponent(cc_2.Graphics);
                            this.rect(sg, -2, -17, 4, 8, '#f6e8ca');
                            this.rect(sg, -9, -7, 4, 8, '#f6e8ca');
                            this.rect(sg, 7, 2, 4, 8, '#f6e8ca');
                            this.rect(sg, -2, 13, 4, 8, '#f6e8ca');
                            const smoke = this.child(n, 'burnt-smoke', 36, 30, 13, 38), bg = smoke.addComponent(cc_2.Graphics);
                            this.rect(bg, -12, -6, 9, 8, '#665e57');
                            this.rect(bg, -3, 1, 10, 8, '#504a45');
                            this.rect(bg, 5, 8, 8, 7, '#746b62');
                            const fire = this.child(n, 'fire-flame', 32, 34, 0, 39), fg = fire.addComponent(cc_2.Graphics);
                            this.drawIcon(fg, 'fire');
                            fire.setScale(.55, .55, 1);
                            const ready = this.child(n, 'ready-pop', 76, 24, 0, 38), rg = ready.addComponent(cc_2.Graphics);
                            this.rect(rg, -35, -11, 70, 22, COLORS.honey);
                            this.rect(rg, -32, -8, 64, 16, COLORS.paper);
                            const cue = this.child(ready, 'cue', 70, 22).addComponent(cc_2.Label);
                            this.writeLabel(cue, '熟了！');
                            this.pixel(cue, 12);
                            cue.color = color(COLORS.ink);
                            cue.horizontalAlign = cc_2.Label.HorizontalAlign.CENTER;
                            cue.verticalAlign = cc_2.Label.VerticalAlign.CENTER;
                            steam.active = false;
                            smoke.active = false;
                            fire.active = false;
                            ready.active = false;
                            this.potEffects[id] = { steam, smoke, fire, ready };
                        }
                        overlay.setSiblingIndex(n.children.length - 1);
                    }
                    for (const who of ['human', 'jeff']) {
                        const n = this.chef(this.world, who, 0, 0, who, this.useModularArt ? TILE / 64 : .65); // chefs-v2 frames: 64 art px per tile, like the counters
                        const dust = this.child(n, 'sprint-dust', 55, 28, -18, -24);
                        dust.addComponent(cc_2.Graphics);
                        dust.active = false;
                        dust.setSiblingIndex(0);
                        this.locate(n, this.state.kitchen.chefs[who].position);
                        this.registerDepth(n, () => { const c = this.state.kitchen.chefs[who], e = this.state.kitchen.map.equipment[c.target]; return KitchenGeometry_1.workingChefDepth((360 - MAPY - n.position.y) / TILE - .5, e === null || e === void 0 ? void 0 : e.cell[1], c.facing, !!c.working && !!e); });
                        // Name tag: a solid pixel plate in the identity colour, sized to the text in drawNameTag.
                        const ln = this.child(n, 'name', 155, 25, 0, this.useModularArt ? -12 : -39);
                        this.child(ln, 'tag', 40, 18).addComponent(cc_2.Graphics);
                        const l = this.pixel(this.child(ln, 'text', 40, 18).addComponent(cc_2.Label), 12);
                        delete this.tagText[who]; // new nodes after a layout change need their plate drawn
                        l.overflow = cc_2.Label.Overflow.NONE;
                        this.labels['person-' + who] = l;
                        const body = n.getChildByName('body'), held = this.child(body, 'held', 25, 25, 22, 0);
                        held.setScale(.9, .9, 1);
                        held.addComponent(cc_2.Graphics);
                        this.people[who] = n;
                        // What the chef carries, above the head: readable from behind, where the hand is hidden.
                        const bubble = this.child(n, 'held-bubble', 40, 38, 0, this.useModularArt ? 104 : 78), bg = bubble.addComponent(cc_2.Graphics);
                        this.rect(bg, -17, -13, 34, 30, COLORS.ink);
                        this.rect(bg, -16, -10, 32, 26, COLORS.paper);
                        this.rect(bg, -4, -17, 8, 5, COLORS.ink);
                        this.rect(bg, -2, -15, 4, 4, COLORS.paper);
                        const icon = this.child(bubble, 'icon', 42, 42, 0, 3);
                        icon.setScale(.62, .62, 1);
                        icon.addComponent(cc_2.Graphics);
                        bubble.active = false;
                        if (this.prepSample) {
                            const pose = this.child(this.world, 'prep-pose-' + who, 68, 88);
                            pose.active = false;
                            this.prepPoses[who] = pose;
                            this.registerDepth(pose, () => { var _a; const c = this.state.kitchen.chefs[who], e = this.state.kitchen.map.equipment[c.target]; return KitchenGeometry_1.depthOrder((_a = e === null || e === void 0 ? void 0 : e.cell[1]) !== null && _a !== void 0 ? _a : c.position[1], 'solid') + .02; });
                        }
                        this.motions[who] = { body, leftLeg: body.getChildByName('left-leg'), rightLeg: body.getChildByName('right-leg'),
                            leftArm: body.getChildByName('left-arm'), rightArm: body.getChildByName('right-arm'), knife: body.getChildByName('right-arm').getChildByName('knife'), facing: 'down', step: 0 };
                    }
                    const marker = (name, fill) => {
                        const n = this.child(this.people.jeff, name, 30, 18, 0, 65), g = n.addComponent(cc_2.Graphics);
                        g.fillColor = color(COLORS.paper);
                        g.circle(0, 0, 8);
                        g.fill();
                        for (const x of [-5, 0, 5])
                            this.rect(g, x - 1, -1, 2, 3, fill);
                        return n;
                    };
                    this.jeffThinking = marker('jeff-thinking', COLORS.jeff);
                    const error = this.child(this.people.jeff, 'jeff-api-error', 24, 23, 0, 66), eg = error.addComponent(cc_2.Graphics);
                    this.rect(eg, -9, -9, 18, 18, COLORS.hot);
                    this.rect(eg, -2, -6, 4, 8, COLORS.paper);
                    this.rect(eg, -2, 4, 4, 3, COLORS.paper);
                    this.jeffError = error;
                    this.jeffThinking.active = false;
                    this.jeffError.active = false;
                    // Floor art and signs used to be root siblings; group them with the kitchen before fitting a phone viewport.
                    for (const n of this.node.children.filter(n => !previous.has(n) && n !== this.world)) {
                        n.setParent(this.world);
                        this.registerDepth(n, () => n.name === 'floor-art' ? -2000 : 1000);
                    }
                    this.mapNodes = [this.world];
                    this.mountedLayout = map.layout_version;
                    this.sortWorld();
                    this.refreshArtCharacters();
                    // The cover shows a soup pot between the two chefs, like the loading card.
                    const coverIcon = this.cover.getChildByName('welcome-food'), coverG = coverIcon.getComponent(cc_2.Graphics);
                    coverG.clear();
                    if (!(this.useArt && this.art.centered(coverIcon, 'objects/' + VESSEL_ART_FALLBACK, 40, 40)))
                        this.drawIcon(coverG, 'vessel');
                    this.cover.setSiblingIndex(this.node.children.length - 1);
                    for (const id of ['pause', 'resume', 'end'])
                        this.buttons[id].node.setSiblingIndex(this.node.children.length - 1);
                    this.mounted = true;
                    this.applyTouchLayout();
                }
                throwPoseFor(who) {
                    const release = this.throwReleases[who];
                    if (release && this.clock < release.until)
                        return Object.assign(Object.assign({}, KitchenGeometry_1.throwPose(release.dx, release.dy, 'release')), { dx: release.dx, dy: release.dy, phase: 'release' });
                    if (who === 'human' && this.aiming)
                        return Object.assign(Object.assign({}, KitchenGeometry_1.throwPose(this.aiming.x, this.aiming.y, 'windup')), { dx: this.aiming.x, dy: this.aiming.y, phase: 'windup' });
                    return null;
                }
                characterArt(body, who, facing, walking = false, working = false) {
                    var _a, _b, _c, _d, _e, _f, _g;
                    const kind = who === 'human' ? 'player' : 'jeff', chef = (_a = this.state) === null || _a === void 0 ? void 0 : _a.kitchen.chefs[who];
                    const station = (_b = this.state) === null || _b === void 0 ? void 0 : _b.kitchen.map.equipment[chef === null || chef === void 0 ? void 0 : chef.target];
                    const inWorld = !!body.parent && ['human', 'jeff'].includes(body.parent.name);
                    const chopping = !!working && inWorld && (chef === null || chef === void 0 ? void 0 : chef.action_kind) === 'chop' && !!station;
                    // Aiming / just thrown: turn the body to the throw and use the painted arm (any aim angle).
                    const throwing = inWorld && !chopping ? this.throwPoseFor(who) : null;
                    // Painted diagonal bodies (art/throw-diagonal-v1) take the four diagonal sectors when present;
                    // otherwise the four-view body leans the chop arm (throwPose).
                    const diagonal = throwing ? KitchenGeometry_1.throwDiagonal(throwing.dx, throwing.dy) : '';
                    const diagonalKey = diagonal ? `throw/${kind}/${diagonal}/${throwing.phase}` : '';
                    const useDiagonal = !!diagonalKey && this.art.has(diagonalKey) && !!((_c = this.art.meta(diagonalKey)) === null || _c === void 0 ? void 0 : _c.grip);
                    // A straight left/right wind-up keeps the carry pose, turned to the aim: the chop lift frame
                    // raises the fist in front of the face, so the item would cover it or the fist sit on it.
                    const sideWindup = !useDiagonal && !!throwing && throwing.phase === 'windup' && (throwing.view === 'left' || throwing.view === 'right');
                    // A straight-down wind-up uses the painted down-diagonal wind-up (arm cocked across the chest),
                    // so all three downward aims match; the chop lift would put the fist and item over the face.
                    const downKey = !useDiagonal && (throwing === null || throwing === void 0 ? void 0 : throwing.phase) === 'windup' && throwing.view === 'down' ? `throw/${kind}/${throwing.dx < 0 ? 'down_left' : 'down_right'}/windup` : '';
                    const useDown = !!downKey && this.art.has(downKey) && !!((_d = this.art.meta(downKey)) === null || _d === void 0 ? void 0 : _d.grip);
                    const throwKey = useDiagonal ? diagonalKey : useDown ? downKey : throwing && !sideWindup ? `knifeless/characters/${kind}/${throwing.view}/chop_${throwing.frame}` : '';
                    const throwMeta = throwKey && this.art.has(throwKey) ? this.art.meta(throwKey) : null;
                    if ((throwMeta === null || throwMeta === void 0 ? void 0 : throwMeta.grip) || sideWindup)
                        facing = throwing.view;
                    // Held item behind the body when the chef faces away (back view, or an upward diagonal).
                    const itemBehind = useDiagonal ? diagonal.startsWith('up') : facing === 'up';
                    const sampleFrame = this.prepSample ? Number((_e = new URLSearchParams(location.search).get('prepFrame')) !== null && _e !== void 0 ? _e : -1) : -1;
                    const knifePilot = this.knifeSample && chopping && who === 'jeff' && facing === 'down' && this.state.kitchen.level === 2 && chef.target === 'b1';
                    // Raise, swing, strike, recover: the chop frames move arms and knife together, one strike every
                    // 0.27 s (about 3.7 a second, Overcooked's pace); each strike's sound follows the beat.
                    const beat = ((this.activeClock / .27 + (who === 'human' ? 0 : .27)) % 1 + 1) % 1;
                    const phase = knifePilot ? 1 : Number.isInteger(sampleFrame) && sampleFrame >= 0 && sampleFrame < 4 ? sampleFrame : beat < .3 ? 0 : beat < .45 ? 1 : beat < .75 ? 2 : 3;
                    const paintedKey = `characters/${kind}/${facing}/chop_${phase}`, knifeless = 'knifeless/' + paintedKey;
                    // With the knife layer, the body comes from the knife-free poses; the painted knife is a fallback.
                    const layered = chopping && this.art.has(knifeless) && this.art.has(KNIFE_VIEW[facing][0] + '0');
                    const actionKey = layered ? knifeless : paintedKey;
                    const hasAction = chopping && this.art.has(actionKey);
                    const pilot = hasAction && who === 'jeff' && facing === 'down' && this.prepSampleBoard(chef.target) && this.art.has('prep/jeff/down/contact-body');
                    const frame = walking ? `walk_${Math.floor(this.activeClock * 12) % 8}` : 'idle_0';
                    // All poses share the actor's floor anchor and depth. An upper-body slice
                    // is not a tool: painting it above the station puts the chef on the board.
                    const key = pilot ? 'prep/jeff/down/contact-body' : hasAction ? actionKey : (throwMeta === null || throwMeta === void 0 ? void 0 : throwMeta.grip) ? throwKey : `characters/${kind}/${facing}/${frame}`;
                    const shown = this.useArt && this.art.show(body, key, 68, 88, 0, inWorld && this.useModularArt ? 0 : -29);
                    if (who === 'jeff' && inWorld)
                        this.knifeOnlySample(knifePilot, actionKey);
                    const prep = this.prepPoses[who];
                    if (inWorld && prep) {
                        prep.active = !!pilot;
                        if (pilot) {
                            // Only the actual hands/blade overlap the surface; never paint feet above it.
                            const actor = this.people[who];
                            prep.setPosition(actor.position);
                            prep.setScale(actor.scale);
                            this.art.show(prep, 'prep/jeff/down/contact-tool', 68, 88);
                        }
                    }
                    body.getComponent(cc_2.Graphics).enabled = !shown;
                    for (const child of body.children)
                        if (!['held', 'held-hand', 'reviewed-art'].includes(child.name))
                            child.active = !shown;
                    if (inWorld && chopping)
                        this.knifeStrike(who, beat, .45);
                    if (shown) {
                        // Behind a waist-high counter the body sinks so the counter hides the legs; by
                        // position only (never by action), so walking up and starting work look the same.
                        const sink = inWorld && this.useModularArt ? KitchenGeometry_1.behindCounter(this.state.kitchen.map, this.mapPoint(body.parent)) : 0;
                        body.setScale(1, 1, 1);
                        body.angle = 0;
                        body.setPosition(0, -10 * sink);
                        if (inWorld && this.useModularArt) {
                            (_f = body.parent.getChildByName('contact-shadow')) === null || _f === void 0 ? void 0 : _f.setPosition(0, 0);
                            (_g = body.parent.getChildByName('name')) === null || _g === void 0 ? void 0 : _g.setPosition(0, -12);
                        }
                        const held = body.getChildByName('held');
                        let hand = body.getChildByName('held-hand');
                        if (held && (throwMeta === null || throwMeta === void 0 ? void 0 : throwMeta.grip)) {
                            // The item sits in the painted hand at the usual carry size: canvas px -> body coords (feet anchor at y=83).
                            const [px, py] = KitchenGeometry_1.throwItemPoint(throwMeta.grip, throwMeta.arm_deg || 0), lift = inWorld && this.useModularArt ? 0 : -29;
                            held.setPosition(px - 34, 83 - py + lift);
                            held.setScale(.9, .9, 1);
                            held.setSiblingIndex(itemBehind ? 0 : body.children.length - 1);
                            // The fist closes over the item (the pose's own hand overlay), except behind the back.
                            const handKey = throwKey + '_hand';
                            if (!itemBehind && held.active && this.art.has(handKey)) {
                                if (!hand) {
                                    hand = this.child(body, 'held-hand', 68, 88);
                                }
                                hand.active = true;
                                this.art.show(hand, handKey, 68, 88, 0, lift);
                                hand.setSiblingIndex(body.children.length - 1);
                            }
                            else if (hand)
                                hand.active = false;
                        }
                        else if (held) {
                            held.setScale(.9, .9, 1);
                            if (hand)
                                hand.active = false;
                            held.setPosition(facing === 'left' ? -24 : facing === 'right' ? 24 : 0, (inWorld && this.useModularArt ? 29 : 0) + (facing === 'up' ? 8 : -5));
                            held.setSiblingIndex(facing === 'up' ? 0 : body.children.length - 1);
                        }
                    }
                    else {
                        this.art.hide(body);
                        for (const name of ['profile', 'back'])
                            body.getChildByName(name).active = false;
                        body.getChildByName('right-arm').getChildByName('knife').active = false;
                    }
                    // After the sink offset, so the knife stays in the hand.
                    if (inWorld)
                        this.chopKnife(who, layered && hasAction && !!shown ? actionKey : '', facing, phase);
                    if (inWorld)
                        this.chopImpact(who, hasAction && phase === 2 && beat < .62, (beat - .45) / .17);
                    return shown;
                }
                /** The knife (art standard v1) as its own layer, pivoting on the pose's grip. It is drawn just
                 * above the food on the board, so the blade lands on board and food in every facing, and stays
                 * behind a chef who faces up at the board. A pose's fist overlay (<pose>_hand) goes on top of
                 * the knife so the hand closes around the handle. Poses name their knife frame (older poses map
                 * lift, half, strike (held), half to the view's frames 2, 1, 0, 1), and the knife is turned to
                 * the pose's grip_angle, so the blade sweeps a real arc in every view. */
                chopKnife(who, poseKey, facing, phase) {
                    var _a, _b;
                    let knife = this.knives[who], hand = this.knifeHands[who];
                    const pose = poseKey ? this.art.meta(poseKey) : null;
                    this.knifeEdges[who] = null;
                    if (!(pose === null || pose === void 0 ? void 0 : pose.grip) || pose.knife_hidden) {
                        if (knife === null || knife === void 0 ? void 0 : knife.isValid)
                            knife.active = false;
                        if (hand === null || hand === void 0 ? void 0 : hand.isValid)
                            hand.active = false;
                        return;
                    }
                    const depth = (lift) => () => { var _a; const c = this.state.kitchen.chefs[who], e = this.state.kitchen.map.equipment[c.target]; return KitchenGeometry_1.depthOrder((_a = e === null || e === void 0 ? void 0 : e.cell[1]) !== null && _a !== void 0 ? _a : c.position[1], 'item') + lift; };
                    if (!(knife === null || knife === void 0 ? void 0 : knife.isValid)) {
                        knife = this.child(this.world, 'chop-knife-' + who, 64, 64);
                        this.knives[who] = knife;
                        this.registerDepth(knife, depth(.01));
                    }
                    if (!(hand === null || hand === void 0 ? void 0 : hand.isValid)) {
                        hand = this.child(this.world, 'chop-hand-' + who, 68, 88);
                        this.knifeHands[who] = hand;
                        this.registerDepth(hand, depth(.011));
                    }
                    const [view, mirror] = KNIFE_VIEW[facing], key = pose.knife || view + [2, 1, 0, 1][phase], frame = this.art.meta(key);
                    if (!(frame === null || frame === void 0 ? void 0 : frame.pivot)) {
                        knife.active = false;
                        hand.active = false;
                        return;
                    }
                    knife.active = true;
                    // Pose canvas px (top-left origin) -> the 68x88 box the body is drawn in, above its foot anchor.
                    const [cw, ch] = pose.canvasSize || [68, 88], footY = (pose.anchor || [.5, .068])[1] * 88, handKey = poseKey + '_hand', overlay = this.art.has(handKey);
                    // With a fist overlay, grip is the fist centre. Older poses give where the painted blade
                    // began, and the hand closes about 3 px behind it.
                    const a = (pose.grip_angle || 0) * Math.PI / 180, g = overlay ? pose.grip : [pose.grip[0] - 3 * Math.cos(a), pose.grip[1] + 3 * Math.sin(a)];
                    const actor = this.people[who], body = actor.getChildByName('body'), sx = actor.scale.x, sy = actor.scale.y;
                    const bodyX = actor.position.x + sx * body.position.x, bodyY = actor.position.y + sy * body.position.y;
                    knife.setPosition(bodyX + sx * (g[0] * 68 / cw - 34), bodyY + sy * (88 - footY - g[1] * 88 / ch));
                    // Turn the knife about the grip so the blade points along the pose's grip_angle (degrees
                    // counter-clockwise from +x). Arc frames are drawn at their screen angle (pose.screen_angle_deg)
                    // and need no turn, which keeps their pixels crisp. A side knife pointing left is mirrored
                    // rather than turned past 90 degrees, keeping its edge underneath.
                    const built = (_b = (_a = frame.pose) === null || _a === void 0 ? void 0 : _a.screen_angle_deg) !== null && _b !== void 0 ? _b : Math.atan2(frame.pivot[1] - frame.tip[1], frame.tip[0] - frame.pivot[0]) * 180 / Math.PI;
                    const want = typeof pose.grip_angle === 'number' ? pose.grip_angle : null, side = key.includes('/side_');
                    const flip = side && (want === null ? mirror : Math.cos(want * Math.PI / 180) < 0);
                    const turn = want === null ? 0 : ((want - (flip ? 180 - built : built)) % 360 + 540) % 360 - 180;
                    knife.setScale(flip ? -sx : sx, sy, 1);
                    knife.angle = Math.abs(turn) < .5 ? 0 : turn;
                    // Where the edge meets the board, in world units: the strike spark sits there.
                    const edge = frame.edge || frame.tip, ex = (edge[0] - frame.pivot[0]) * (flip ? -sx : sx), ey = (frame.pivot[1] - edge[1]) * sy, r = knife.angle * Math.PI / 180;
                    this.knifeEdges[who] = [knife.position.x + ex * Math.cos(r) - ey * Math.sin(r), knife.position.y + ex * Math.sin(r) + ey * Math.cos(r)];
                    this.art.show(knife, key, 64, 64, 32 - frame.pivot[0], frame.pivot[1] - 32);
                    hand.active = overlay;
                    if (overlay) {
                        hand.setPosition(bodyX, bodyY);
                        hand.setScale(sx, sy, 1);
                        this.art.show(hand, handKey, 68, 88);
                    }
                }
                /** Sound one knife strike when the swing phase passes the board-contact point. */
                knifeStrike(who, t, contact) {
                    const before = this.knifePhase[who];
                    this.knifePhase[who] = t;
                    if (before !== undefined && t >= contact && (before < contact || before > t))
                        this.audio.chop();
                }
                /** A short spark on the board while the knife lands (strike frame only). */
                chopImpact(who, active, p) {
                    let impact = this.chopImpacts[who];
                    if (!(impact === null || impact === void 0 ? void 0 : impact.isValid)) {
                        if (!active)
                            return;
                        impact = this.child(this.world, 'knife-impact-' + who, 52, 52);
                        impact.addComponent(cc_2.Graphics);
                        this.chopImpacts[who] = impact;
                        this.registerDepth(impact, () => { var _a, _b; const c = this.state.kitchen.chefs[who]; return KitchenGeometry_1.depthOrder((_b = (_a = this.state.kitchen.map.equipment[c.target]) === null || _a === void 0 ? void 0 : _a.cell[1]) !== null && _b !== void 0 ? _b : c.position[1], 'solid') + .04; });
                    }
                    impact.active = active;
                    const g = impact.getComponent(cc_2.Graphics);
                    g.clear();
                    if (!active)
                        return;
                    const target = this.state.kitchen.chefs[who].target;
                    const edge = this.knifeEdges[who];
                    if (edge)
                        impact.setPosition(edge[0], edge[1]);
                    else
                        this.locate(impact, this.state.kitchen.map.equipment[target].cell);
                    g.strokeColor = new cc_2.Color(255, 246, 220, Math.round(255 * (1 - p)));
                    g.lineWidth = 2;
                    g.moveTo(-9 + 5 * p, -5);
                    g.lineTo(7 + 5 * p, 7);
                    g.stroke();
                    g.lineWidth = 1;
                    g.moveTo(-4, 8);
                    g.lineTo(4, -7);
                    g.stroke();
                    for (const [dx, dy] of [[-1, 1], [1, 1], [-1, -1], [1, -1]]) {
                        const r = 6 + 7 * p;
                        this.rect(g, dx * r, dy * r * .6, 2, 2, p < .6 ? '#fff1c9' : '#ddb471');
                    }
                }
                knifeOnlySample(active, key) {
                    if (this.knifeProbe)
                        this.knifeProbe.active = active;
                    if (this.cutProbe)
                        this.cutProbe.active = active;
                    if (!active)
                        return;
                    const params = new URLSearchParams(location.search);
                    const length = Math.max(1, Math.min(4, Number(params.get('knifeScale') || 2.5) || 2.5));
                    const handleLength = Math.max(1, Math.min(3, Number(params.get('knifeHandle') || 2) || 2));
                    if (!this.knifeProbe) {
                        const root = this.child(this.world, 'knife-only-probe', 68, 88);
                        // Separate length axes keep both thicknesses unchanged. Existing pixels only.
                        const part = (name, pivot, points) => {
                            const stretch = this.child(root, name, 68, 88);
                            stretch.angle = -40;
                            const stencil = this.child(stretch, name + '-mask', 68, 88);
                            stencil.angle = 40;
                            stencil.addComponent(cc_2.Mask).type = cc_2.Mask.Type.GRAPHICS_STENCIL;
                            const g = stencil.getComponent(cc_2.Graphics);
                            g.clear();
                            points.forEach(([x, y], i) => i ? g.lineTo(x - pivot[0], pivot[1] - y) : g.moveTo(x - pivot[0], pivot[1] - y));
                            g.close();
                            g.fill();
                            this.art.show(stencil, key, 68, 88, 34 - pivot[0], pivot[1] - 82);
                        };
                        part('handle', [29, 61], [[29, 61], [31, 61], [34, 64], [31, 66], [29, 64]]);
                        part('length', [31, 63], [[31, 63], [34, 64], [44, 72], [37, 73], [31, 69]]);
                        this.knifeProbe = root;
                        this.registerDepth(root, () => KitchenGeometry_1.depthOrder(this.state.kitchen.map.equipment.b1.cell[1], 'solid') + .02);
                        const fx = this.child(this.world, 'cut-impact-probe', 52, 52);
                        fx.addComponent(cc_2.Graphics);
                        this.cutProbe = fx;
                        this.registerDepth(fx, () => KitchenGeometry_1.depthOrder(this.state.kitchen.map.equipment.b1.cell[1], 'solid') + .03);
                    }
                    const actor = this.people.jeff, root = this.knifeProbe;
                    root.active = length > 1 || handleLength > 1;
                    root.setScale(actor.scale);
                    // Pivot remains at the original grip; neither the actor nor the board moves.
                    root.setPosition(actor.position.x - 5 * actor.scale.x, actor.position.y + 21 * actor.scale.y);
                    root.getChildByName('handle').setScale(handleLength, 1, 1);
                    const blade = root.getChildByName('length');
                    // Move blade base with the handle tip; never scale the grip/hand or whole actor.
                    const a = -40 * Math.PI / 180, dx = 2, dy = -2, along = dx * Math.cos(a) + dy * Math.sin(a);
                    blade.setPosition(dx + (handleLength - 1) * along * Math.cos(a), dy + (handleLength - 1) * along * Math.sin(a));
                    blade.setScale(length, 1, 1);
                    const fx = this.cutProbe, g = fx.getComponent(cc_2.Graphics);
                    g.clear();
                    const impact = params.get('cutFx') === '1';
                    const t = params.has('cutPhase') ? Math.max(0, Math.min(.999, Number(params.get('cutPhase')) || 0)) : (this.activeClock * 3) % 1;
                    fx.active = impact && t < .28;
                    if (!fx.active)
                        return;
                    const cell = this.state.kitchen.map.equipment.b1.cell;
                    this.locate(fx, cell);
                    const p = t / .28;
                    g.strokeColor = color('#fff3cf');
                    g.lineWidth = 2;
                    g.moveTo(-9 + 6 * p, -5);
                    g.lineTo(5 + 6 * p, 6);
                    g.stroke();
                    g.strokeColor = color('#f4cf81');
                    g.lineWidth = 1;
                    for (const [dx, dy] of [[-1, 1], [1, 1], [-1, -1], [1, -1]]) {
                        const r = 5 + 7 * p;
                        g.moveTo(dx * r, dy * r * .65);
                        g.lineTo(dx * (r + 2), dy * (r + 2) * .65);
                        g.stroke();
                    }
                }
                refreshArtCharacters() {
                    var _a;
                    for (const who of ['human', 'jeff']) {
                        if (this.useArt)
                            this.characterArt(this.motions[who].body, who, this.state.kitchen.chefs[who].facing || 'down');
                        const welcome = (_a = this.cover.getChildByName('welcome-' + who)) === null || _a === void 0 ? void 0 : _a.getChildByName('body');
                        if (welcome)
                            this.characterArt(welcome, who, 'down');
                    }
                }
                foodNode(id, stage, airborne = false) {
                    const n = this.make('food-' + id, 0, 0, 44, 40, this.world || this.node);
                    n.setScale(.9, .9, 1);
                    // Food and tools lying on the floor: in front of the cabinets one row up, under nearby chefs
                    // (floorItemDepth); in flight they keep the flight order above the ground.
                    this.registerDepth(n, () => { var _a; return airborne ? ((_a = this.flightOrder[id]) !== null && _a !== void 0 ? _a : 0) : KitchenGeometry_1.floorItemDepth((360 - MAPY - n.position.y) / TILE - .5); });
                    this.drawIcon(n.addComponent(cc_2.Graphics), stage);
                    // Overcooked's anticipation: the item Space would take, or a throw this chef will catch, is ringed in denim.
                    const focus = this.child(n, 'focus', 48, 26, 0, -12);
                    focus.setSiblingIndex(0);
                    focus.active = false;
                    const g = focus.addComponent(cc_2.Graphics);
                    g.fillColor = new cc_2.Color(42, 90, 158, 56);
                    g.strokeColor = color(COLORS.human);
                    g.lineWidth = 2.5;
                    g.ellipse(0, 0, 20, 10);
                    g.fill();
                    g.stroke();
                    const child = new cc_2.Node('id');
                    child.layer = cc_2.Layers.Enum.UI_2D;
                    n.addChild(child);
                    child.addComponent(cc_2.UITransform).setContentSize(64, 19);
                    child.setPosition(0, -23);
                    const l = child.addComponent(cc_2.Label);
                    this.writeLabel(l, id);
                    l.fontSize = 13;
                    l.lineHeight = 16;
                    l.color = color(COLORS.ink);
                    child.active = !this.useModularArt;
                    return n;
                }
                statColor(id) {
                    const f = this.flashes[id];
                    if (f && f.until > this.clock)
                        return f.fill;
                    return COLORS.ink;
                }
                // New result events: a short pop where it happened, a header pulse, and a
                // screen-reader announcement. Events already present when a round loads stay quiet.
                processEvents() {
                    const s = this.state, fresh = s.game_id !== this.eventsGame;
                    if (fresh) {
                        this.eventsGame = s.game_id;
                        this.seenEvents.clear();
                    }
                    for (const e of s.events) {
                        const key = e.t + '|' + e.message;
                        if (this.seenEvents.has(key))
                            continue;
                        this.seenEvents.add(key);
                        if (!fresh)
                            this.feedback(e);
                    }
                    if (this.seenEvents.size > 300)
                        this.seenEvents = new Set(s.events.map(e => e.t + '|' + e.message));
                }
                feedback(e) {
                    var _a, _b, _c;
                    const k = this.state.kitchen, amount = ((_a = /(\d+) 元/.exec(e.message)) === null || _a === void 0 ? void 0 : _a[1]) || '', serve = (_b = k.map.equipment.serve) === null || _b === void 0 ? void 0 : _b.cell;
                    const at = (cell) => cell ? [MAPX + (cell[0] + .5) * TILE, MAPY + (cell[1] - .1) * TILE] : [640, 150];
                    if (e.kind === 'served') {
                        this.pop(at(serve), '+¥' + amount, COLORS.herb);
                        this.flash(['served', 'money'], COLORS.herb);
                    }
                    else if (e.kind === 'expired') {
                        this.pop([312, 180], `${((_c = /^(\S+?)超时/.exec(e.message)) === null || _c === void 0 ? void 0 : _c[1]) || ''} 超时 -¥${amount}`, COLORS.alert);
                        this.flash(['money'], COLORS.alert);
                    }
                    else if (e.kind === 'fire' || e.kind === 'fire_spread')
                        this.flash(['money'], COLORS.alert);
                    if (e.kind && RESULT_ANNOUNCE.has(e.kind))
                        this.announce(e.message);
                }
                flash(ids, fill) { for (const id of ids) {
                    this.flashes[id] = { until: this.clock + 1.2, fill };
                    this.labels[id].color = color(fill);
                } }
                pop(p, text, fill) {
                    const n = this.make('result-pop', p[0], p[1], 220, 28, this.world || this.node), l = n.addComponent(cc_2.Label);
                    this.writeLabel(l, text);
                    this.pixel(l, 24);
                    l.horizontalAlign = cc_2.Label.HorizontalAlign.CENTER;
                    l.enableShadow = true;
                    l.shadowColor = color(COLORS.ink);
                    l.shadowOffset = new cc_2.Vec2(2, -2);
                    l.shadowBlur = 0;
                    l.color = color(fill); // hard pixel shadow
                    this.pops.push({ node: n, label: l, born: this.clock, y: n.position.y, fill: color(fill) });
                }
                drawOrders() {
                    var _a, _b;
                    const s = this.state, k = s.kitchen, orders = k.orders.filter((o) => o.status === 'pending');
                    // The goal is net revenue at closing.
                    this.set('served', `${k.served}`);
                    this.set('money', `¥ ${k.money} / ${k.goals.target_money}`);
                    for (const id of ['served', 'money'])
                        this.labels[id].color = color(this.statColor(id));
                    for (let i = 0; i < 5; i++) {
                        const o = orders[i], n = this.tickets[i], g = n.getComponent(cc_2.Graphics) || n.addComponent(cc_2.Graphics), urgent = o && o.remaining <= 15;
                        g.clear();
                        // Paper slip clipped to the walnut rail; empty clips stay bare instead of drawing blank slips.
                        this.rect(g, -10, 26, 20, 6, COLORS.walnut);
                        if (o || i === 0) {
                            this.rect(g, -78, -36, 156, 62, COLORS.walnut);
                            this.rect(g, -77, -34, 154, 59, COLORS.paper);
                            if (o) {
                                // Patience: herb while comfortable, honey past half, hot red when urgent (the label also says so).
                                const left = Math.max(0, Math.min(1, o.remaining / (o.patience || ((_a = s.rules) === null || _a === void 0 ? void 0 : _a.order_patience) || 90)));
                                this.rect(g, -67, -30, 134, 7, COLORS.ink);
                                this.rect(g, -66, -29, 132, 5, COLORS.bg);
                                this.rect(g, -66, -29, 132 * left, 5, urgent ? COLORS.hot : left > .5 ? COLORS.herb : COLORS.honey);
                            }
                        }
                        const signature = o ? JSON.stringify(o.ingredients || []) : '';
                        if (this.orderArt[i] !== signature) {
                            this.orderArt[i] = signature;
                            const prev = n.getChildByName('ingredients');
                            if (prev)
                                prev.destroy();
                            if (o) {
                                const row = this.child(n, 'ingredients', 150, 16, 0, -5);
                                const ingredients = o.ingredients || [];
                                // Each item as the dish needs it, but whole: a chopped item reads better uncut at this size.
                                const need = (name) => { var _a, _b, _c; const st = (_c = (_b = (_a = this.dishById(o.dish)) === null || _a === void 0 ? void 0 : _a.components) === null || _b === void 0 ? void 0 : _b.find((c) => c.item === name)) === null || _c === void 0 ? void 0 : _c.state; return st && st !== 'chopped' ? st : 'raw'; };
                                ingredients.forEach((name, j) => { const item = this.child(row, 'ingredient-' + j, 30, 14, 66 - (ingredients.length - 1 - j) * 15, 0); item.setScale(this.useArt ? .5 : .32, this.useArt ? .5 : .32, 1); this.drawIcon(item.addComponent(cc_2.Graphics), `item:${name}:${need(name)}`); });
                            }
                        }
                        this.set('order-id-' + i, o ? `${o.id} · ${urgent ? '快超时了' : '待出餐'}` : i === 0 ? '订单夹' : '');
                        this.labels['order-id-' + i].color = color(urgent ? COLORS.hot : COLORS.muted);
                        this.set('order-name-' + i, o ? (((_b = this.dishById(o.dish)) === null || _b === void 0 ? void 0 : _b.name) || o.dish) : i === 0 ? (k.future_orders ? '等待新订单' : '订单已结清') : '');
                        this.set('order-time-' + i, o ? `${Math.max(0, Math.ceil(o.remaining))}s` : '');
                        this.labels['order-time-' + i].color = color(urgent ? COLORS.hot : COLORS.muted);
                    }
                }
                drawNameTag(who) {
                    const l = this.labels['person-' + who];
                    if (this.tagText[who] === l.string)
                        return;
                    this.tagText[who] = l.string;
                    l.updateRenderData(true);
                    const w = Math.ceil(l.node.getComponent(cc_2.UITransform).width) + 10, h = 18;
                    const g = l.node.parent.getChildByName('tag').getComponent(cc_2.Graphics);
                    g.clear();
                    // 1px ink border with a 2px hard ink shadow below, like the game's buttons.
                    // You: denim plate, paper text. Jeff: paper plate (his white body), copper text.
                    this.rect(g, -w / 2 - 1, -h / 2 - 3, w + 2, h + 4, COLORS.ink);
                    this.rect(g, -w / 2, -h / 2, w, h, who === 'human' ? COLORS.human : COLORS.paper);
                    l.color = color(who === 'human' ? COLORS.paper : COLORS.jeff);
                }
                /** Map cell coordinates of a world node (inverse of locate). */
                mapPoint(n) { return [(n.position.x + 640 - MAPX) / TILE - .5, (360 - MAPY - n.position.y) / TILE - .5]; }
                locate(n, p, height = 0) { n.setPosition(MAPX + (p[0] + .5) * TILE - 640, 360 - MAPY - (p[1] + .5) * TILE + height); }
                render() {
                    var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m, _o, _p, _q, _r;
                    if (!this.state || !this.mounted)
                        return;
                    const s = this.state, k = s.kitchen, active = s.phase === 'running' && !this.pending && this.connected;
                    const remaining = Math.max(0, Math.ceil(k.round_remaining));
                    this.set('clock', `${String(Math.floor(remaining / 60)).padStart(2, '0')}:${String(remaining % 60).padStart(2, '0')}  ${s.phase === 'running' ? '营业中' : s.phase === 'ended' ? '已结算' : '休息中'}`);
                    const sprint = k.chefs.human.sprint;
                    this.set('sprint-status', !sprint ? '' : sprint.active_remaining > 0 ? '冲刺中' : sprint.cooldown_remaining > 0 ? '冲刺冷却 ' + Math.ceil(sprint.cooldown_remaining) + 's' : '冲刺 · Shift');
                    this.set('fire-status', ((_a = k.fire_safety) === null || _a === void 0 ? void 0 : _a.burning_count) ? `着火工位 ${k.fire_safety.burning_count}/${k.fire_safety.loss_threshold}` : '');
                    this.labels.clock.color = color(remaining <= 30 ? COLORS.hot : COLORS.muted);
                    this.drawOrders();
                    for (const [id, dev] of Object.entries(this.devices)) {
                        const st = k.stations[id], g = dev.graphics;
                        g.clear();
                        const prior = this.foodStages[id];
                        const foodKey = st.food ? `${st.food.id}:${st.food.stage}` : '';
                        if (((_b = st.food) === null || _b === void 0 ? void 0 : _b.stage) === 'ready' && prior === `${st.food.id}:cooking`)
                            this.readyUntil[id] = this.activeClock + 1.1;
                        this.foodStages[id] = foodKey;
                        if (st.fire && !this.useArt) {
                            this.rect(g, -26, -26, 52, 52, '#f1b589');
                        }
                        // The player's own chop/wash station keeps its frame while they work on it.
                        const me = k.chefs.human, busy = !!(me === null || me === void 0 ? void 0 : me.working) && ['chop', 'wash'].includes(me.action_kind) && me.target === id;
                        // This page's own pick is framed at once; the engine's state says whether there is something to
                        // do there (denim) once it has caught up with the same pick.
                        const focus = this.localPick !== undefined ? this.localPick : s.interaction_focus;
                        const offered = (((_c = s.interaction) === null || _c === void 0 ? void 0 : _c.target) === id || ((_d = s.use_interaction) === null || _d === void 0 ? void 0 : _d.target) === id) && (this.localPick === undefined || this.localPick === id);
                        const actionable = busy || offered;
                        if (actionable || focus === id) {
                            if (this.useModularArt)
                                this.facedGlow(g, -TILE / 2, this.workSurfaceY(id) - TILE / 2, TILE, TILE, actionable);
                            else
                                this.facedGlow(g, -27, -27, 54, 54, actionable);
                        }
                        this.writeLabel(dev.label, st.fire ? '着火了！' : st.food ? (this.itemName(st.food) + (st.food.stage === 'cooking' ? ` ${Math.ceil(st.ready_in)}s` : st.food.stage === 'ready' && st.heating && st.burn_in !== undefined ? ` ${Math.ceil(st.burn_in)}s 后糊` : '')) : ((_e = this.state.kitchen.map.equipment[id]) === null || _e === void 0 ? void 0 : _e.type) === 'ingredient_source' && this.useModularArt ? this.itemLabel(this.sourceItem(id)) : st.name);
                        const countdown = KitchenGeometry_1.heatCountdown(st);
                        let timer = dev.node.getChildByName('heat-countdown');
                        if (countdown && !timer) {
                            timer = this.child(dev.node, 'heat-countdown', 48, 15, 0, this.workSurfaceY(id) + TILE / 2 - 5);
                            timer.addComponent(cc_2.Graphics);
                            const text = this.child(timer, 'time', 48, 15).addComponent(cc_2.Label);
                            this.pixel(text, 12);
                            text.overflow = cc_2.Label.Overflow.SHRINK;
                        }
                        if (timer) {
                            timer.active = !!countdown;
                            if (countdown) {
                                timer.setSiblingIndex(dev.node.children.length - 1);
                                const tg = timer.getComponent(cc_2.Graphics);
                                tg.clear();
                                this.rect(tg, -24, -7.5, 48, 15, countdown.paused ? COLORS.steel : countdown.ready ? COLORS.hot : COLORS.walnut);
                                const label = timer.getChildByName('time').getComponent(cc_2.Label);
                                label.color = color(COLORS.paper);
                                this.writeLabel(label, `${countdown.paused ? 'Ⅱ ' : ''}${countdown.seconds}s ${countdown.ready ? '糊' : '熟'}`);
                            }
                        }
                        dev.label.color = color(st.fire || ((_f = st.food) === null || _f === void 0 ? void 0 : _f.stage) === 'ready' || ((_g = st.food) === null || _g === void 0 ? void 0 : _g.stage) === 'burnt' ? COLORS.hot : COLORS.ink);
                        // What rests on a burning station stays drawn (the flames go over it), so an item never seems to vanish.
                        const food = dev.node.getChildByName('food');
                        food.active = !!st.food || st.fire;
                        if (food.active)
                            this.drawIcon(food.getComponent(cc_2.Graphics), st.food ? this.itemStage(st.food) : 'fire');
                        if (this.cabinetFires[id]) {
                            this.cabinetFires[id].active = !!st.fire;
                            if (st.fire && !st.food)
                                food.active = false;
                        }
                        if (st.counter && !st.fire)
                            this.writeLabel(dev.label, st.food ? this.itemName(st.food) : ((this.localPick !== undefined ? this.localPick : s.interaction_focus) !== id ? '' : '空柜台'));
                        if (st.stove) {
                            if (this.useModularArt)
                                this.equipmentArt(dev.node.getChildByName('equipment'), id);
                            else
                                this.drawIcon(dev.node.getChildByName('equipment').getComponent(cc_2.Graphics), this.useArt ? 'stove' : st.vessel ? 'vessel:' + st.vessel : 'stove');
                            if (this.useArt) {
                                let vessel = dev.node.getChildByName('stove-vessel');
                                if (!vessel) {
                                    vessel = this.child(dev.node, 'stove-vessel', 34, 34, 0, this.useModularArt ? this.workSurfaceY(id) : 10);
                                    vessel.setSiblingIndex(dev.node.getChildByName('equipment').getSiblingIndex() + 1);
                                }
                                vessel.active = !!(st.vessel || st.pot_id);
                                // A filled vessel frame already shows what is cooking: the separate food icon stays hidden.
                                if (vessel.active && this.drawVessel(vessel, st.vessel || '', .96, (_h = st.food) === null || _h === void 0 ? void 0 : _h.ingredient, (_j = st.food) === null || _j === void 0 ? void 0 : _j.stage) === 'filled' && !st.fire)
                                    food.active = false;
                                food.setPosition(0, this.useModularArt ? this.workSurfaceY(id) + 3 : 13);
                                food.setScale(.58, .58, 1);
                            }
                        }
                        if (id === 'returns')
                            this.writeLabel(dev.label, st.food ? '脏盘待洗' : '脏盘回收');
                        if (id === 'sink' && st.food)
                            this.writeLabel(dev.label, st.food.stage === 'dirty_plate' ? `待洗 ${Math.ceil(st.food.wash_remaining)}s` : '洗好了');
                        let progress = -1;
                        if (id === 'sink' && st.food)
                            progress = 1 - st.food.wash_remaining / k.tableware.wash_seconds;
                        if (st.food && id.startsWith('b') && !id.startsWith('bin'))
                            progress = 1 - st.food.chop_remaining / (((_k = s.rules) === null || _k === void 0 ? void 0 : _k.chop_seconds) || 6);
                        if (st.food && st.stove)
                            progress = Math.min(1, st.food.heat_elapsed / (((_l = s.rules) === null || _l === void 0 ? void 0 : _l.cook_seconds) || 12));
                        // As in Overcooked 2, a station a fire next to it is heating shows a fire bar until it ignites.
                        const igniting = !st.fire && st.fire_heat > 0;
                        if (igniting)
                            progress = st.fire_heat;
                        // A fire being sprayed shows how much is left (Overcooked 2's fire bar); full fires show none.
                        if (st.fire && st.fire_strength < 1)
                            progress = st.fire_strength;
                        if (progress >= 0) {
                            const py = this.useModularArt ? this.workSurfaceY(id) - TILE / 2 + 3 : -18;
                            this.rect(g, -23, py - 1, 46, 6, COLORS.ink);
                            this.rect(g, -22, py, 44 * progress, 4, st.fire || igniting ? COLORS.hot : COLORS.paper);
                        }
                        const effects = this.potEffects[id];
                        if (effects) {
                            effects.steam.active = !!st.food && st.food.stage === 'cooking' && !!st.heating && !st.fire;
                            effects.smoke.active = !!st.food && st.food.stage === 'burnt' && !!st.heating && !st.fire;
                            effects.fire.active = !!st.fire;
                            effects.ready.active = (this.readyUntil[id] || 0) > this.activeClock && !!st.food && st.food.stage === 'ready';
                        }
                    }
                    const ids = new Set(k.ground.map((g) => g.food.id));
                    for (const [id, n] of Object.entries(this.ground))
                        if (!ids.has(id)) {
                            n.destroy();
                            delete this.ground[id];
                            delete this.groundStages[id];
                        }
                    for (const item of k.ground) {
                        const id = item.food.id, stage = this.itemStage(item.food);
                        if (!this.ground[id]) {
                            this.ground[id] = this.foodNode(id, stage);
                            this.groundStages[id] = stage;
                        }
                        if (this.groundStages[id] !== stage) {
                            this.drawIcon(this.ground[id].getComponent(cc_2.Graphics), stage);
                            this.groundStages[id] = stage;
                        }
                        this.writeLabel(this.ground[id].getChildByName('id').getComponent(cc_2.Label), this.itemName(item.food));
                        this.locate(this.ground[id], item.position);
                        this.ground[id].getChildByName('focus').active = this.localPick === 'item:' + id;
                    }
                    for (const who of ['human', 'jeff']) {
                        const c = k.chefs[who];
                        this.set('person-' + who, (who === 'human' ? '你' : 'Jeff') + (((_m = c.sprint) === null || _m === void 0 ? void 0 : _m.active_remaining) > 0 ? ' »' : ''));
                        this.drawNameTag(who);
                        const held = this.motions[who].body.getChildByName('held');
                        held.active = !!c.holding;
                        if (c.holding)
                            this.drawIcon(held.getComponent(cc_2.Graphics), this.itemStage(c.holding));
                        const bubble = this.people[who].getChildByName('held-bubble');
                        bubble.active = !!c.holding;
                        if (c.holding)
                            this.drawIcon(bubble.getChildByName('icon').getComponent(cc_2.Graphics), this.itemStage(c.holding));
                    }
                    const apiConfigured = !!((_o = s.connection) === null || _o === void 0 ? void 0 : _o.configured) && s.phase !== 'ready' && s.phase !== 'ended';
                    if (this.jeffThinking)
                        this.jeffThinking.active = this.connected && apiConfigured && !!s.ai.thinking && !s.ai.error;
                    if (this.jeffError)
                        this.jeffError.active = apiConfigured && !!s.ai.error;
                    const flightIds = new Set((k.projectiles || []).map((p) => p.id));
                    for (const [id, n] of Object.entries(this.flights))
                        if (!flightIds.has(id)) {
                            n.destroy();
                            delete this.flights[id];
                            delete this.flightOrder[id];
                        }
                    for (const p of k.projectiles || [])
                        if (!this.flights[p.id]) {
                            this.flights[p.id] = this.foodNode(p.id, this.itemStage(p), true);
                            const from = p.from || [0, 0], to = p.to || from, dist = (w) => { var _a, _b, _c, _d; return Math.hypot(((_b = (_a = k.chefs[w].position) === null || _a === void 0 ? void 0 : _a[0]) !== null && _b !== void 0 ? _b : 0) - from[0], ((_d = (_c = k.chefs[w].position) === null || _c === void 0 ? void 0 : _c[1]) !== null && _d !== void 0 ? _d : 0) - from[1]); };
                            const thrower = dist('human') <= dist('jeff') ? 'human' : 'jeff';
                            if (to[0] !== from[0] || to[1] !== from[1])
                                this.throwReleases[thrower] = { dx: to[0] - from[0], dy: to[1] - from[1], until: this.clock + .3 };
                        }
                    this.enable('pause', active);
                    this.enable('resume', s.phase === 'paused' && !this.pending && this.connected);
                    this.enable('end', ['running', 'paused'].includes(s.phase) && !this.pending && this.connected);
                    for (const id of ['pause', 'resume', 'end'])
                        this.buttons[id].node.active = true;
                    const held = k.chefs.human.holding;
                    this.set('hand', '手中：' + (held ? this.itemName(held) : '空手'));
                    if ((held === null || held === void 0 ? void 0 : held.stage) === 'assembled')
                        this.set('hand', '缺少：' + held.missing.map((x) => this.itemLabel(x)).join('+'));
                    {
                        const short = (a) => a.label.split('（')[0], parts = [];
                        if (s.interaction)
                            parts.push('空格 · ' + short(s.interaction));
                        else if (s.interaction_hint)
                            parts.push(s.interaction_hint);
                        if (held && k.chefs.human.can_throw !== false)
                            parts.push('长按空格 · 瞄准投掷');
                        this.set('interaction', this.aiming ? '松开空格投掷 · 方向键改方向' : parts.length ? parts.join('　') : (s.interaction_hint || '面向工位或物品按空格'));
                    }
                    // Game results keep the event line; Jeff's decisions and errors use their own status.
                    const results = s.events.filter(e => !this.isAiNote(e));
                    this.set('event', results.length ? results[results.length - 1].message : '');
                    this.set('ai-status', this.aiStatus(s));
                    this.labels['ai-status'].color = color(s.ai.error || (((_p = s.limits) === null || _p === void 0 ? void 0 : _p.reached) && s.phase === 'running') ? COLORS.alert : COLORS.muted);
                    this.syncLevelButtons(s.levels || []);
                    for (const level of s.levels || []) {
                        const id = 'level:' + level.id, b = this.buttons[id], sel = k.level_id === level.id;
                        if (!b)
                            continue;
                        b.node.active = s.phase === 'ready' || s.phase === 'ended';
                        this.writeLabel(b.label, level.name + (sel ? ' · 当前' : ''));
                        if (b.selected !== sel) {
                            b.selected = sel;
                            this.styleButton(id);
                        }
                        this.enable(id, !this.pending && !sel);
                    }
                    const lang = ((_q = window.kitchenI18n) === null || _q === void 0 ? void 0 : _q.language) === 'en' ? '中文' : 'English';
                    if (this.buttons.language.label.string !== lang)
                        this.buttons.language.label.string = lang;
                    this.cover.active = s.phase !== 'running';
                    this.buttons.reset.node.active = true;
                    this.enable('main', !this.pending);
                    this.buttons.main.node.active = true;
                    this.enable('reset', !this.pending && s.phase !== 'ready');
                    this.writeLabel(this.buttons.main.label, s.phase === 'ready' ? '开始经营' : s.phase === 'paused' ? '继续经营' : s.phase === 'ended' ? this.nextRound(s).label : '准备下一局');
                    if (s.phase === 'ready' && s.connection && !s.connection.configured)
                        this.writeLabel(this.buttons.main.label, '先连接搭档');
                    this.labels['welcome-tip'].node.active = s.phase === 'ready';
                    this.buttons.record.node.active = s.phase === 'ended' && !!s.round_summary;
                    const h = s.hosted, offer = s.phase === 'ended' && !!(h === null || h === void 0 ? void 0 : h.contribution_offer);
                    this.buttons.contribute.node.active = offer;
                    if (offer) {
                        this.writeLabel(this.buttons.contribute.label, h.contributed ? '已贡献' : h.contribution_busy ? '正在贡献…' : '贡献本局');
                        this.enable('contribute', !h.contributed && !h.contribution_busy && !this.pending);
                    }
                    if (!cc_2.sys.isNative) {
                        // Reflow existing controls inside the original 736 x 464 panel. Artwork,
                        // 1280 x 720 scaling and the centre soup-pot frame remain unchanged.
                        const ended = s.phase === 'ended', ready = s.phase === 'ready';
                        const move = (id, x, y) => this.buttons[id].node.setPosition(x - 640, 360 - y);
                        this.buttons.more.node.active = ended;
                        this.buttons.reset.node.active = !ready;
                        this.buttons.language.node.active = !ended;
                        this.buttons['cover-connection'].node.active = this.buttons.help.node.active = !ended;
                        this.buttons.contribute.node.active = false; // Offered in More, under the same consent state.
                        this.buttons['level-picker'].node.active = ready || ended;
                        this.enable('level-picker', !this.pending);
                        this.enable('more', !this.pending);
                        const current = (s.levels || []).find((l) => l.id === k.level_id);
                        this.labels['selected-level'].node.active = ready;
                        this.set('selected-level', (current === null || current === void 0 ? void 0 : current.name) || '');
                        if (ended) {
                            move('main', 553, 506);
                            move('reset', 727, 506);
                            move('record', 553, 562);
                            move('level-picker', 727, 562);
                        }
                        else if (ready) {
                            move('main', 466, 520);
                            move('cover-connection', 640, 520);
                            move('help', 814, 520);
                            move('level-picker', 772, 464);
                        }
                        else {
                            move('main', 379, 520);
                            move('reset', 553, 520);
                            move('cover-connection', 727, 520);
                            move('help', 901, 520);
                        }
                    }
                    // The record stays one tap away (本局记录) instead of covering the result card.
                    if (s.phase === 'ended' && this.endedSeen.round !== s.game_id)
                        this.endedSeen = { round: s.game_id, at: Date.now() };
                    // Rounds close at the time limit: say so plainly, whatever the outcome.
                    const closed = s.phase === 'ended' && !s.aborted && k.failure_reason !== 'fire_spread';
                    if (!this.countdown) { // the 3·2·1 owns the card until the next round starts
                        this.set('coverTitle', s.phase === 'ready' ? 'ChefJeff' : s.phase === 'paused' ? '歇一小会儿' : k.failure_reason === 'fire_spread' ? '火势失控' : s.aborted ? '本局已结束' : closed ? (s.won ? '关店结算 · 达成目标' : '关店结算 · 未达目标') : s.won ? '今天，配合得不错！' : '明天再接再厉');
                        this.set('coverText', s.phase === 'ready' ? `你和 AI 搭档，一起照顾这间小厨房。\n本局目标：关店时净收入达到 ¥${k.goals.target_money}` : s.phase === 'paused' ? '锅火和订单都按下了暂停。\n准备好了，就和 Jeff 接着做菜。' : closed ? this.closingSummary(k, !!s.won, s.round_summary) : `出餐 ${k.served} 单 · 净收入 ¥${k.money} / ¥${k.goals.target_money}`);
                    }
                    if (((_r = s.capacity) === null || _r === void 0 ? void 0 : _r.can_start) === false && s.phase !== 'running') {
                        this.enable('resume', false);
                        const configuring = s.phase === 'ready' && s.connection && !s.connection.configured;
                        if (!configuring) {
                            this.enable('main', false);
                            this.writeLabel(this.buttons.main.label, '等待空位');
                        }
                        if (!this.countdown) {
                            // Full overall, or this network already holds its share of kitchens (hosted per-network limit).
                            const network = s.capacity.reason === 'network';
                            if (s.phase === 'ready')
                                this.set('coverTitle', network ? '同一网络的厨房已满' : '厨房暂时已满');
                            this.set('coverText', (this.labelSources.get(this.labels.coverText) || '') + (network ?
                                `\n你所在的网络已同时开了 ${s.capacity.per_network} 个厨房。其中一个结束后按钮会恢复，请再点击继续。` :
                                '\n厨房名额暂时已满。空位释放后按钮会恢复，请再点击继续。'));
                        }
                    }
                    this.syncAccess();
                    if (this.overlayPhase !== s.phase) {
                        // Pause defaults to "Resume" and the result card to the next round, so Enter or Space continues.
                        const first = !this.overlayPhase;
                        this.overlayPhase = s.phase;
                        this.setFocus(s.phase === 'paused' || s.phase === 'ended' ? 'main' : '');
                        if (!first && s.phase !== 'running')
                            this.announce(this.labelSources.get(this.labels.coverTitle) + '\n' + this.labelSources.get(this.labels.coverText));
                    }
                    if (s.ai.error && s.ai.error !== this.lastAiError)
                        this.announce(s.ai.error);
                    this.lastAiError = s.ai.error;
                    this.cover.setSiblingIndex(this.node.children.length - 1);
                    for (const id of ['pause', 'resume', 'end'])
                        this.buttons[id].node.setSiblingIndex(this.node.children.length - 1);
                    this.applyTouchLayout();
                    this.syncAccess();
                    this.publishControls();
                }
                isAiNote(e) { return !e.kind && /^(Jeff |本局 AI)/.test(e.message); }
                aiStatus(s) {
                    var _a;
                    if (((_a = s.limits) === null || _a === void 0 ? void 0 : _a.reached) && s.phase === 'running')
                        return 'Jeff 已达本局调用上限';
                    if (s.ai.error)
                        return 'Jeff 暂时连不上，正在重试';
                    const note = [...s.events].reverse().find(e => this.isAiNote(e));
                    const m = note && /^Jeff 选择：(.*?) \| [\d.]+s(?: \| 未执行：(.*))?$/s.exec(note.message);
                    if (m)
                        return m[2] ? `Jeff：${m[1]}（未执行）` : `Jeff：${m[1]}`; // full reason stays in the event log/export
                    return (note === null || note === void 0 ? void 0 : note.message.startsWith('Jeff 请求失败')) ? 'Jeff 暂时连不上，正在重试' : '';
                }
                // Keeps the screen-reader proxies in step with the visible canvas buttons.
                syncAccess() {
                    if (!this.controlAccess)
                        return;
                    const icons = { pause: '暂停', resume: '继续经营', end: '结束本局' };
                    for (const id of this.tabOrder()) {
                        const b = this.buttons[id], proxy = this.controlAccess.querySelector(`[data-control="${id}"]`);
                        if (!proxy)
                            continue;
                        const text = id === 'language' ? b.label.string : icons[id] || this.labelSources.get(b.label) || id;
                        if (id === 'language')
                            proxy.setAttribute('data-no-i18n', '');
                        if (proxy.dataset.source !== text) {
                            proxy.dataset.source = text;
                            proxy.textContent = text;
                        }
                        proxy.disabled = !b.enabled;
                        proxy.hidden = !b.node.activeInHierarchy;
                    }
                }
                // One exception is recorded for the export instead of silently skipping every later frame.
                update(dt) { try {
                    this.frame(dt);
                }
                catch (e) {
                    this.recordLoopError(e);
                } }
                recordLoopError(e) {
                    var _a;
                    const message = String((_a = e === null || e === void 0 ? void 0 : e.message) !== null && _a !== void 0 ? _a : e).slice(0, 200), stack = String((e === null || e === void 0 ? void 0 : e.stack) || '').split('\n').slice(0, 4).join('\n').slice(0, 600);
                    const seen = this.loopErrors.find(x => x.message === message && x.stack === stack);
                    if (seen) {
                        seen.count++;
                        seen.last = Math.round(this.clock * 100) / 100;
                        return;
                    }
                    console.error('ChefJeff update loop:', e);
                    if (this.loopErrors.length < 10)
                        this.loopErrors.push({ message, stack, count: 1, first: Math.round(this.clock * 100) / 100, last: Math.round(this.clock * 100) / 100 });
                }
                sampleFrame(k) {
                    var _a, _b, _c;
                    if (((_a = this.state) === null || _a === void 0 ? void 0 : _a.phase) !== 'running' || this.clock - this.frameAt < .2)
                        return;
                    this.frameAt = this.clock;
                    const r = (p) => p ? [Math.round(p[0] * 1e3) / 1e3, Math.round(p[1] * 1e3) / 1e3] : null;
                    this.frames.push({ t: Math.round(k.time * 100) / 100, clock: Math.round(this.clock * 100) / 100, engine: r((_c = (_b = k.chefs) === null || _b === void 0 ? void 0 : _b.human) === null || _c === void 0 ? void 0 : _c.position), predicted: r(this.predicted),
                        reported: r(this.lastReported), direction: [this.manualDirection.x, this.manualDirection.y], pressing: this.pressing,
                        hands_busy: this.clock < this.handsBusyUntil, resync: this.resyncSeen, connected: this.connected, hidden: this.hidden });
                    if (this.frames.length > 150)
                        this.frames.shift();
                }
                diagnostics() {
                    var _a;
                    return { schema: 'chefjeff-page-diagnostics-v1', sample_hz: 5, window_seconds: 30, frames: this.frames.slice(), loop_errors: this.loopErrors.map(e => (Object.assign({}, e))),
                        viewport: [innerWidth, innerHeight], device_pixel_ratio: devicePixelRatio, touch_layout: !!((_a = this.touchLayout) === null || _a === void 0 ? void 0 : _a.active), user_agent: navigator.userAgent,
                        coverage: 'Running frames only, newest last; no keys, typed text or model data.' };
                }
                frame(dt) {
                    var _a, _b, _c, _d, _e;
                    this.clock += dt;
                    this.audio.update(dt);
                    if (!this.state || !this.mounted)
                        return;
                    const k = this.state.kitchen;
                    if (this.touchMoveDirty && this.clock - this.touchMoveAt >= .05)
                        this.flushTouchMove();
                    if (this.spaceDownAt !== null && this.clock - this.spaceDownAt >= AIM_HOLD)
                        this.startAim();
                    if (this.aiming && this.state.phase !== 'running')
                        this.endAim();
                    if (this.aiming)
                        this.drawAim();
                    // Result pops rise and fade over 1.4s (no rise with reduced motion); header numbers pulse.
                    this.pops = this.pops.filter(p => {
                        const age = (this.clock - p.born) / 1.4;
                        if (age >= 1 || !p.node.isValid) {
                            p.node.destroy();
                            return false;
                        }
                        if (!this.reduceMotion)
                            p.node.setPosition(p.node.position.x, p.y + 34 * (1 - (1 - age) * (1 - age)));
                        const a = Math.round(255 * (age < .6 ? 1 : 1 - (age - .6) / .4));
                        p.label.color = new cc_2.Color(p.fill.r, p.fill.g, p.fill.b, a);
                        p.label.shadowColor = new cc_2.Color(43, 26, 18, a);
                        return true;
                    });
                    for (const [id, f] of Object.entries(this.flashes)) {
                        const left = f.until - this.clock, n = this.labels[id].node;
                        if (left <= 0) {
                            delete this.flashes[id];
                            n.setScale(1, 1, 1);
                            this.labels[id].color = color(this.statColor(id));
                            continue;
                        }
                        const s = this.reduceMotion ? 1 : 1 + .18 * Math.max(0, left - .9) / .3;
                        n.setScale(s, s, 1);
                    }
                    const running = this.connected && !this.hidden && this.state.phase === 'running';
                    const animate = running && !this.qaNoMotion;
                    if (animate)
                        this.activeClock += dt;
                    for (const who of ['human', 'jeff']) {
                        const c = k.chefs[who], p = c.position, n = this.people[who], motion = this.motions[who];
                        // A chef who isn't chopping never shows a knife, even on frames that skip characterArt.
                        if (!(c.working && c.action_kind === 'chop'))
                            for (const layer of [this.knives[who], this.knifeHands[who]])
                                if (layer === null || layer === void 0 ? void 0 : layer.isValid)
                                    layer.active = false;
                        const dust = n.getChildByName('sprint-dust');
                        dust.active = !!animate && ((_a = c.sprint) === null || _a === void 0 ? void 0 : _a.active_remaining) > 0 && (c.manual_moving || c.travel_remaining > 0);
                        if (dust.active) {
                            const frame = Math.floor(this.activeClock * 10) % 7, g = dust.getComponent(cc_2.Graphics);
                            dust.setPosition(motion.facing === 'left' ? 22 : motion.facing === 'right' ? -22 : 0, this.useModularArt ? (motion.facing === 'up' ? -12 : motion.facing === 'down' ? 12 : -2) : -25);
                            if (this.useModularArt && this.art.centered(dust, `modular/sprint_dust_${frame % 4}`, 32, 14))
                                g.clear();
                            else if (this.useArt && this.art.show(dust, `vfx/landing_${frame}`, 52, 28))
                                g.clear();
                            else {
                                g.clear();
                                for (let i = 0; i < 3; i++)
                                    this.rect(g, -20 + i * 13, -3 + (frame + i) % 3 * 3, 7, 5, '#d8bf93');
                            }
                        }
                        if (running && p) {
                            const predicted = who === 'human' ? this.predictHuman(k, c, dt, n) : null, at = predicted || p;
                            if (predicted) {
                                this.reportPosition();
                                this.updatePick(k, c);
                            }
                            const x = MAPX + (at[0] + .5) * TILE - 640, y = 360 - MAPY - (at[1] + .5) * TILE, t = predicted ? 1 : Math.min(1, dt * 16);
                            const oldX = n.position.x, oldY = n.position.y;
                            n.setPosition(oldX + (x - oldX) * t, oldY + (y - oldY) * t);
                            if (who === 'human' && predicted && this.clock < this.cueUntil) {
                                // A short lean toward the faced station (peaks at 4 px) on the key press.
                                const lean = 4 * Math.sin(Math.PI * (1 - (this.cueUntil - this.clock) / CUE_SECONDS)), f = c.facing || 'down';
                                n.setPosition(n.position.x + (f === 'left' ? -lean : f === 'right' ? lean : 0), n.position.y + (f === 'up' ? lean : f === 'down' ? -lean : 0));
                            }
                            const dx = n.position.x - oldX, dy = n.position.y - oldY, moved = Math.hypot(dx, dy) > .08 && (!!predicted || (c.travel_remaining || 0) > 0 || Math.hypot(x - n.position.x, y - n.position.y) > 1);
                            if (moved) {
                                if ((c.manual_moving || predicted) && who === 'human' && (this.manualDirection.x !== 0 || this.manualDirection.y !== 0)) {
                                    if (Math.abs(this.manualDirection.x) >= Math.abs(this.manualDirection.y))
                                        motion.facing = this.manualDirection.x < 0 ? 'left' : 'right';
                                    else
                                        motion.facing = this.manualDirection.y < 0 ? 'up' : 'down';
                                }
                                else if (Math.abs(dx) >= Math.abs(dy))
                                    motion.facing = dx < 0 ? 'left' : 'right';
                                else
                                    motion.facing = dy > 0 ? 'up' : 'down';
                            }
                            // Authoritative orientation survives short actions between polls.
                            if (!moved && c.facing)
                                motion.facing = c.facing;
                            if (c.working && c.facing)
                                motion.facing = c.facing;
                            const held = who === 'human' && (this.manualDirection.x !== 0 || this.manualDirection.y !== 0);
                            const walkIntent = (predicted ? held : !!c.manual_moving) || (!c.working && (c.travel_remaining || 0) > 0);
                            if (this.characterArt(motion.body, who, motion.facing, animate && walkIntent, !!c.working))
                                continue;
                            motion.body.angle = 0;
                            const side = motion.facing === 'left' || motion.facing === 'right';
                            motion.body.getChildByName('eyes').active = motion.facing !== 'up' && !side;
                            motion.body.getChildByName('profile').active = side;
                            motion.body.getChildByName('eyes').setPosition(side ? 4 : 0, 19);
                            motion.body.getChildByName('eyes').setScale(side ? .65 : 1, 1, 1);
                            motion.body.getChildByName('back').active = motion.facing === 'up';
                            const facingScale = motion.facing === 'left' ? -.87 : motion.facing === 'right' ? .87 : 1;
                            const walking = animate && walkIntent;
                            const chopping = animate && !walking && c.action_kind === 'chop' && c.working && (c.work_remaining || 0) > .02;
                            motion.knife.active = chopping;
                            if (walking || chopping) {
                                motion.step += dt * (chopping ? 13 : 16.5);
                                const swing = Math.sin(motion.step);
                                motion.leftLeg.setPosition(-7, walking ? -24 + Math.max(0, swing) * 3 : -24);
                                motion.rightLeg.setPosition(7, walking ? -24 + Math.max(0, -swing) * 3 : -24);
                                motion.leftArm.angle = walking ? -swing * 15 : 0;
                                motion.rightArm.angle = chopping ? Math.sin(motion.step * 1.8) * 48 : walking ? swing * 15 : 0;
                                if (chopping)
                                    this.knifeStrike(who, (motion.step * 1.8 / (2 * Math.PI) + .75) % 1, .5);
                                motion.body.setPosition(0, walking ? Math.abs(swing) * 1.2 : 0);
                                motion.body.setScale(facingScale, 1, 1);
                            }
                            else {
                                motion.leftLeg.setPosition(-7, -24);
                                motion.rightLeg.setPosition(7, -24);
                                motion.leftArm.angle = 0;
                                motion.rightArm.angle = 0;
                                const breath = c.action_kind || !animate ? 0 : Math.sin(this.activeClock * 2.2);
                                motion.body.setPosition(0, breath * .7);
                                motion.body.setScale(facingScale, 1 + breath * .008, 1);
                            }
                        }
                    }
                    for (const flame of Object.values(this.cabinetFires))
                        if (flame.active) {
                            const g = flame.getComponent(cc_2.Graphics);
                            if (this.useArt && this.art.show(flame, `vfx/fire_${Math.floor(this.activeClock * 8) % 7}`, 58, 72))
                                g.clear();
                            else
                                this.drawIcon(g, 'fire');
                            const smoke = flame.getChildByName('smoke');
                            if (this.useArt)
                                this.art.show(smoke, `vfx/smoke_${Math.floor(this.activeClock * 6) % 7}`, 42, 42);
                        }
                    if (animate) {
                        for (const [id, e] of Object.entries(this.potEffects)) {
                            if (this.useArt) {
                                const frame = Math.floor(this.activeClock * 8) % 7;
                                for (const [node, key] of [[e.steam, 'steam'], [e.smoke, 'smoke'], [e.fire, 'fire']]) {
                                    if (node.active && this.art.show(node, `vfx/${key}_${frame}`, key === 'fire' ? 75 : 42, key === 'fire' ? 75 : 42))
                                        (_b = node.getComponent(cc_2.Graphics)) === null || _b === void 0 ? void 0 : _b.clear();
                                }
                            }
                            if (e.steam.active)
                                e.steam.setPosition(-11 + Math.sin(this.activeClock * 3 + id.length) * 3, 38 + Math.sin(this.activeClock * 4 + id.length) * 3);
                            if (e.smoke.active)
                                e.smoke.setPosition(13 + Math.sin(this.activeClock * 2.4 + id.length) * 2, 38 + Math.sin(this.activeClock * 3 + id.length) * 2);
                            if (e.fire.active)
                                e.fire.setScale(.55 + Math.sin(this.activeClock * 12) * .035, .55 + Math.sin(this.activeClock * 12 + 1) * .06, 1);
                            if (e.ready.active)
                                e.ready.setScale(.85 + Math.sin(this.activeClock * 12) * .12, .85 + Math.sin(this.activeClock * 12) * .12, 1);
                        }
                        if ((_c = this.jeffThinking) === null || _c === void 0 ? void 0 : _c.active)
                            this.jeffThinking.setScale(.92 + Math.sin(this.activeClock * 5) * .08, .92 + Math.sin(this.activeClock * 5) * .08, 1);
                    }
                    const sink = (_d = this.devices.sink) === null || _d === void 0 ? void 0 : _d.node.getChildByName('washing');
                    if (sink) {
                        const washing = Object.values(k.chefs).some((c) => c.action_kind === 'wash' && c.working);
                        sink.active = washing;
                        if (this.useArt && washing && this.art.show(sink, `vfx/splash_${Math.floor(this.activeClock * 8) % 7}`, 38, 38))
                            (_e = sink.getComponent(cc_2.Graphics)) === null || _e === void 0 ? void 0 : _e.clear();
                        if (washing && this.state.phase === 'running' && this.connected && !this.hidden) {
                            sink.setPosition(0, this.workSurfaceY('sink') + Math.sin(this.clock * 7) * 3);
                            sink.setScale(1 + .12 * Math.sin(this.clock * 5), 1, 1);
                        }
                    }
                    if (running && (this.manualDirection.x !== 0 || this.manualDirection.y !== 0) && this.clock - this.lastMoveAt >= .15)
                        this.sendMove(this.manualDirection.x, this.manualDirection.y);
                    const time = k.time + (this.state.phase === 'running' && this.connected ? (this.clock - this.received) * this.state.speed : 0);
                    const human = k.chefs.human, at = this.predicted || human.position;
                    for (const p of k.projectiles || []) {
                        const t = Math.max(0, Math.min(1, (time - p.started) / (p.lands_at - p.started))), arc = Math.sin(t * Math.PI) * 35;
                        // Caught on the way before it lands anywhere, station or floor (as the engine resolves it).
                        this.flights[p.id].getChildByName('focus').active = p.actor === 'jeff' && !human.holding && !!at && KitchenGeometry_1.segmentDistance(at, p.from, p.to) <= (k.map.catch_radius || .75);
                        const point = [p.from[0] + (p.to[0] - p.from[0]) * t, p.from[1] + (p.to[1] - p.from[1]) * t];
                        // A board/counter landing ends on its work surface, drawn over the cabinet like a resting item.
                        const onto = p.onto && k.map.equipment[p.onto] ? p.onto : null, height = arc + (onto ? t * this.workSurfaceY(onto) : 0);
                        this.locate(this.flights[p.id], point, height);
                        this.flightOrder[p.id] = onto && t >= .5 ? Math.max(KitchenGeometry_1.flightDepth(point[1], height), KitchenGeometry_1.depthOrder(k.map.equipment[onto].cell[1], 'solid') + .02) : KitchenGeometry_1.flightDepth(point[1], height);
                    }
                    this.sortWorld();
                    this.sampleFrame(k);
                }
            };
            exports_1("KitchenClient", KitchenClient);
            exports_1("KitchenClient", KitchenClient = __decorate([
                ccclass('KitchenClient')
            ], KitchenClient));
            cc_1.cclegacy._RF.pop();
        }
    };
});

System.register("chunks:///_virtual/KitchenGeometry.ts",["./rollupPluginModLoBabelHelpers.js","cc"],(function(t){var r,e;return{setters:[function(t){r=t.createForOfIteratorHelperLoose},function(t){e=t.cclegacy}],execute:function(){t({anchorCell:c,behindCounter:function(t,r){for(var e=0,n=0,a=Object.values(t.equipment||{});n<a.length;n++)for(var i=a[n],o=0,u=i.cells||[i.cell];o<u.length;o++){var h=u[o],l=h[1]-.5-r[1];if(!(l<-.02||l>.45)){var f=l<=.2+1e-9?1:(.45-l)/.25,c=Math.max(0,Math.abs(r[0]-h[0])-.5);e=Math.max(e,f*Math.max(0,1-c/.35))}}return e},cabinetModule:function(t,r){var e=t.equipment[r].cell,n=e[0],i=e[1],o=n+","+(i+1),u=(t.walls||[]).some((function(t){return t.join(",")===o}))||Object.values(t.equipment).some((function(t){return(t.cells||[t.cell]).some((function(t){return t.join(",")===o}))}));return"vertical"===a(t,r).run_axis&&u?"counter_east":"counter_south"},clearWalkLine:h,cornerOffset:l,depthOrder:i,flightDepth:function(t,r){return i(t,"item")+(r>=.22*n.tile?.62:0)},floorItemDepth:function(t){return i(Math.round(t)-1,"solid")+.012},footWalkable:o,heatCountdown:function(t){if(!t.stove||!t.food||t.fire)return null;var r="ready"===t.food.stage,e=["chopped","cooking"].includes(t.food.stage);if(!r&&!e)return null;var n=r?t.burn_in:t.ready_in;return Number.isFinite(n)?{seconds:Math.max(0,Math.ceil(n)),ready:r,paused:!t.heating}:null},levelButtonLayout:function(t,r,e){void 0===r&&(r={left:309,right:971,top:432,bottom:486});void 0===e&&(e=16);if(t<=0)return[];for(var n=t<=3?1:2,a=Math.ceil(t/n),i=1===n?30:24,o=1===n?0:(r.bottom-r.top-n*i)/(n-1),u=[],h=0;h<t;h++){var l=Math.floor(h/a),f=Math.min(a,t-l*a),c=h-l*a,s=(r.right-r.left-e*(a-1))/a,v=f*s+e*(f-1),M=(r.left+r.right)/2-v/2,p=1===n?464:r.top+i/2+l*(i+o);u.push({x:M+c*(s+e)+s/2,y:p,w:s,h:i})}return u},panHandleSide:function(t){if(!t)return"east";if(["north","south","east","west"].includes(t.facing))return t.facing;var r=t.cell||[0,0],e=t.access||r,n=e[0]-r[0],a=e[1]-r[1];return Math.abs(n)>=Math.abs(a)&&0!==n?n>0?"east":"west":a<0?"north":"south"},plateLayers:function(t,r){var e=new Set(r);return null!=t&&t.length?t.filter((function(t){return e.has(t.item)})):Array.from(e).map((function(t){return{layer:t,item:t}}))},predictWalk:function(t,r,e,n,a,i){var o;void 0===i&&(i=.05*(null!=(o=t.walk_speed)?o:4.5));var u=Math.hypot(e,n);if(u<1e-12)return[r[0],r[1]];var h=[e/u,n/u],l=[r[0],r[1]],c=u;for(;c>1e-12;){var s=Math.min(i,c);l=f(t,l,h,s,a),c-=s}return l},segmentDistance:function(t,r,e){var n=e[0]-r[0],a=e[1]-r[1],i=n*n+a*a,o=i<1e-12?0:Math.max(0,Math.min(1,((t[0]-r[0])*n+(t[1]-r[1])*a)/i));return Math.hypot(t[0]-r[0]-n*o,t[1]-r[1]-a*o)},selectableStations:s,spaceTarget:function(t,r,e,n){var a=Math.hypot(e[0],e[1]),i=c(t,r);if(!a||!i)return null;var o=e[0]/a,u=e[1]/a,h=function(t){return Math.round(1e6*t)/1e6},l=[],f=s(t,r,e)[0];if(f){var v=t.equipment[f],M=(v.cells||[v.cell]).reduce((function(t,e){return Math.hypot(e[0]-r[0],e[1]-r[1])<Math.hypot(t[0]-r[0],t[1]-r[1])?e:t}));l.push([h(Math.hypot(r[0]+.5*o-M[0],r[1]+.5*u-.35*Math.abs(o)-M[1])),0,f])}return[[i[0]+(Math.abs(o)>=.38?Math.sign(o):0),i[1]+(Math.abs(u)>=.38?Math.sign(u):0)],i].forEach((function(t,e){var a=n.find((function(r){return r.position&&r.location==="floor_"+t[0]+"_"+t[1]}));a&&l.push([h(Math.hypot(r[0]+.5*o-a.position[0],r[1]+.5*u-a.position[1])),e+1,"item:"+a.food.id])})),l.sort((function(t,r){return t[0]-r[0]||t[1]-r[1]})),l.length?l[0][2]:null},stationView:a,surfaceOffset:function(){return n.counterHeight*n.tile/n.unit},throwDiagonal:function(t,r){if(!t&&!r)return"";for(var e=(180*Math.atan2(r,t)/Math.PI%360+360)%360,n=["down_right","down_left","up_left","up_right"],a=0;a<4;a++){var i=45+90*a;if(Math.abs(((e-i)%360+540)%360-180)<22.5)return n[a]}return""},throwItemPoint:function(t,r,e){void 0===e&&(e=4);var n=r*Math.PI/180;return[t[0]+Math.cos(n)*e,t[1]-Math.sin(n)*e]},throwPose:function(t,r,e){var n=(180*Math.atan2(r,t)/Math.PI%360+360)%360,a=n<=60||n>=300?"right":n<120?"down":n<=240?"left":"up";if("windup"===e)return{view:a,frame:0};if("down"===a)return{view:a,frame:1};if("up"===a)return{view:a,frame:3};var i=((n-("right"===a?0:180))%360+540)%360-180;return Math.abs(i)<=20?{view:a,frame:1}:{view:a,frame:("right"===a?i>0:i<0)?2:3}},trashView:function(t,r){var e=t.equipment[r],n=e.access[0]-e.cell[0],a=e.access[1]-e.cell[1],i="west"===e.facing||"east"===e.facing||Math.abs(n)>Math.abs(a);return{axis:i?"vertical":"horizontal",mirror:i&&n>0}},wallNeighbours:function(t,r,e){return{north:t.has(r+","+(e-1)),east:t.has(r+1+","+e),south:t.has(r+","+(e+1)),west:t.has(r-1+","+e)}},wallOffset:function(){return n.wallHeight*n.tile/n.unit},workingChefDepth:function(t,r,e,n){return!n||void 0===r||"left"!==e&&"right"!==e?i(t,"actor"):i(r,"solid")+.015}}),e._RF.push({},"f232cZ06kxIVbuxNuyDHzfa","KitchenGeometry",void 0);var n=t("GRID_ART",{tile:52,originX:276,originY:170,unit:64,counterHeight:0,wallHeight:0,frontWallHeight:0,cabinetSpriteLift:22,northFace:44,floorRepeat:4});function a(t,r){var e,n,a=null==(e=t.presentation)||null==(e=e.station_views)?void 0:e[r];if(a)return a;var i=(null==(n=t.equipment[r])?void 0:n.cell)||[0,0],o=new Set(Object.values(t.equipment).reduce((function(t,r){return t.concat((r.cells||[r.cell]).map((function(t){return t.join(",")})))}),[])),u=Number(o.has(i[0]-1+","+i[1]))+Number(o.has(i[0]+1+","+i[1])),h=Number(o.has(i[0]+","+(i[1]-1)))+Number(o.has(i[0]+","+(i[1]+1)))>u?"vertical":"horizontal";return{run_axis:h,device_axis:h}}function i(t,r){return t+("solid"===r?-.495:"actor"===r?0:-.12)}function o(t,r,e){var n,a=null!=(n=t.walk_clearance)?n:.2,i=1e-9;return r>=.5+a-i&&r<=t.width-1.5-a+i&&e>=.5+a-i&&e<=t.height-1.5-a+i&&!(t.walk_boxes||[]).some((function(t){return t[0]+i<r&&r<t[2]-i&&t[1]+i<e&&e<t[3]-i}))}var u=1e-9;function h(t,r,e){if(!o(t,r[0],r[1])||!o(t,e[0],e[1]))return!1;for(var n=Math.min(r[0],e[0]),a=Math.max(r[0],e[0]),i=Math.min(r[1],e[1]),h=Math.max(r[1],e[1]),l=0,f=t.walk_boxes||[];l<f.length;l++){var c=f[l],s=c[0],v=c[1],M=c[2],p=c[3];if(!(s+u>=a||M-u<=n||v+u>=h||p-u<=i)){for(var m=0,d=1,g=0,b=[[0,s,M],[1,v,p]];g<b.length;g++){var w=b[g],y=w[0],_=w[1],x=w[2],k=e[y]-r[y],q=_+u,O=x-u;if(Math.abs(k)<u){if(!(q<r[y]&&r[y]<O)){m=1,d=0;break}}else{var j=(q-r[y])/k,H=(O-r[y])/k;m=Math.max(m,Math.min(j,H)),d=Math.min(d,Math.max(j,H))}}if(m<=d)return!1}}return!0}function l(t,r,e){var n=t.corner_slide;if(!n||!e[0]&&!e[1])return null;for(var a=Math.abs(e[0])>=Math.abs(e[1])?0:1,i=1-a,o=e[i]<0?-1:1,u=1;u<=Math.round(n/.01);u++)for(var l=0,f=[o,-o];l<f.length;l++){var c=f[l],s=[r[0],r[1]];s[i]+=c*u*.01;var v=[s[0],s[1]];if(v[a]+=.05*Math.sign(e[a]),h(t,r,s)&&h(t,s,v))return[c*u*.01,i]}return null}function f(t,r,e,n,a){var i,o=null!=(i=t.chef_separation)?i:.4,f=function(r,e){if(a&&Math.hypot(e[0]-r[0],e[1]-r[1])>u){var n=function(t,r,e,n){var a=r[0]-t[0],i=r[1]-t[1],o=t[0]-e[0],h=t[1]-e[1],l=a*a+i*i;if(l<1e-18)return 1;var f=o*a+h*i,c=o*o+h*h-n*n;if(c<-u)return f>=-u?1:0;if(f>=0)return 1;var s=f*f-l*c;return s<=u*l?1:Math.max(0,Math.min(1,(-f-Math.sqrt(s))/l))}(r,e,a,o);n<1-1e-8&&(e=[r[0]+(e[0]-r[0])*n,r[1]+(e[1]-r[1])*n])}return function(t,r,e){if(h(t,r,e))return e;for(var n=0,a=1,i=0;i<16;i++){var o=(n+a)/2;h(t,r,[r[0]+(e[0]-r[0])*o,r[1]+(e[1]-r[1])*o])?n=o:a=o}return[r[0]+(e[0]-r[0])*n,r[1]+(e[1]-r[1])*n]}(t,r,e)},c=r,s=[r[0]+e[0]*n,r[1]+e[1]*n],v=!h(t,c,s);if(v)for(var M=0,p=[0,1];M<p.length;M++){var m=p[M];if(e[m]){var d=[c[0],c[1]];d[m]+=e[m]*n,c=f(c,d)}}else c=f(c,s);var g=n*Math.hypot(e[0],e[1])-Math.hypot(c[0]-r[0],c[1]-r[1]);if(t.corner_slide&&g>1e-9&&v){var b=l(t,c,e);if(b){var w=b[0],y=b[1],_=c,x=[c[0],c[1]];x[y]+=Math.sign(w)*Math.min(Math.abs(w),g),c=f(c,x);var k=Math.hypot(c[0]-_[0],c[1]-_[1]),q=g-k;if(k>1e-9&&q>1e-9){var O=[c[0]+e[0]*q,c[1]+e[1]*q];h(t,c,O)&&(c=f(c,O))}}}return c}function c(t,e){for(var n=function(t,r){return t+","+r},a=new Set((t.walls||[]).map((function(t){return n(t[0],t[1])}))),i=0,o=Object.values(t.equipment||{});i<o.length;i++)for(var u,h=o[i],l=r(h.cells||[h.cell]);!(u=l()).done;){var f=u.value;a.add(n(f[0],f[1]))}for(var c=null,s=1/0,v=0;v<t.height;v++)for(var M=0;M<t.width;M++)if(!a.has(n(M,v))){var p=Math.hypot(M-e[0],v-e[1]);p<s-1e-12&&(s=p,c=[M,v])}return c}function s(t,r,e){var n=Math.hypot(e[0],e[1]);if(!n)return[];var a=e[0]/n,i=e[1]/n,o=c(t,r);if(!o)return[];for(var u=o[0],h=o[1],l=[r[0]+.5*a,r[1]+.5*i-.35*Math.abs(a)],f=c(t,[r[0],r[1]-.35*Math.abs(a)])||o,s=f[0],v=f[1],M=new Map,p=0,m=Object.entries(t.equipment||{});p<m.length;p++){var d,g,b=m[p],w=b[0],y=b[1],_="corner"===y.reach;if(!_||(null==(d=y.access)?void 0:d[0])===u&&(null==(g=y.access)?void 0:g[1])===h)for(var x=0,k=_?[y.cell]:y.cells||[y.cell];x<k.length;x++){var q=k[x],O=q[0]-(_?u:s),j=q[1]-(_?h:v);if((_||1===Math.max(Math.abs(O),Math.abs(j)))&&!(a*O+i*j<=1e-6)){var H=(a*O+i*j)/Math.hypot(O,j)+(Math.abs(O)+Math.abs(j)===1?.1:0);if(!(Math.max(Math.abs(r[0]-q[0]),Math.abs(r[1]-q[1]))-.5>.85+1e-9)){var I=[-Math.round(1e6*H)/1e6,Math.round(1e6*Math.hypot(l[0]-q[0],l[1]-q[1]))/1e6],D=M.get(w);(!D||I[0]<D[0]||I[0]===D[0]&&I[1]<D[1])&&M.set(w,I)}}}}return Array.from(M.entries()).sort((function(t,r){return t[1][0]-r[1][0]||t[1][1]-r[1][1]||(t[0]<r[0]?-1:t[0]>r[0]?1:0)})).map((function(t){return t[0]}))}e._RF.pop()}}}));

System.register("chunks:///_virtual/LevelOneArt.ts", ["cc"], function (exports_1, context_1) {
    // source-sha256: 1e2a561c9191c100db563799b8a369c49aa162fa1a9d2bbc4ce0630c2ab494c1
    "use strict";
    var cc_1, LevelOneArt;
    var __moduleName = context_1 && context_1.id;
    return {
        setters: [
            function (cc_1_1) {
                cc_1 = cc_1_1;
            }
        ],
        execute: function () {
            /** Reviewed, local sprites only. Rendering never changes kitchen observations or rules. */
            LevelOneArt = class LevelOneArt {
                constructor() {
                    this.frames = {};
                    this.definitions = {};
                    this.slices = {};
                    this.ready = false;
                    this.modular = false;
                }
                async loadAtlas(path, prefix = '') {
                    const [manifest, texture] = await Promise.all([
                        new Promise((resolve, reject) => cc_1.resources.load(path + '/manifest', cc_1.JsonAsset, (e, a) => e ? reject(e) : resolve(a))),
                        new Promise((resolve, reject) => cc_1.resources.load(path + '/atlas/texture', cc_1.Texture2D, (e, a) => e ? reject(e) : resolve(a)))
                    ]);
                    texture.setFilters(cc_1.Texture2D.Filter.NEAREST, cc_1.Texture2D.Filter.NEAREST);
                    for (const [key, value] of Object.entries(manifest.json.frames)) {
                        const [x, y, w, h] = value.rect;
                        if (w <= 0 || h <= 0 || x < 0 || y < 0 || x + w > texture.width || y + h > texture.height)
                            throw new Error('Invalid art frame ' + key);
                    }
                    // Download concurrently, but apply in source order: newer atlases override
                    // older frames regardless of which network response finishes first.
                    return () => {
                        for (const [key, value] of Object.entries(manifest.json.frames)) {
                            const [x, y, w, h] = value.rect;
                            const frame = new cc_1.SpriteFrame();
                            frame.texture = texture;
                            frame.rect = new cc_1.Rect(x, y, w, h);
                            frame.originalSize = new cc_1.Size(w, h);
                            this.frames[prefix + key] = frame;
                            this.definitions[prefix + key] = value;
                        }
                    };
                }
                async load() {
                    try {
                        const atlases = [
                            ['art/level1', '', true], ['art/level1-modular', 'modular/', false],
                            ['art/kitchen-modules-v2', 'modular/', false], ['art/serving-side-v1', 'modular/', false],
                            ['art/burger-food', 'food/', false], ['art/grid-foundation-v1', '', true],
                            ['art/action-feedback-v1', '', true], ['art/chefs-v2', '', false],
                            ['art/knife-v1', '', true], ['art/knife-arc-v1', '', false],
                            ['art/trash-directions-v1', '', true], ['art/throw-diagonal-v1', '', false], ['art/ingredient-pack-v1', '', false],
                        ];
                        if (typeof location !== 'undefined' && new URLSearchParams(location.search).get('prepSample') === '1')
                            atlases.push(['art/prep-pose-v3', '', true]);
                        const apply = await Promise.all(atlases.map(async ([path, prefix]) => {
                            try {
                                return await this.loadAtlas(path, prefix);
                            }
                            catch (error) {
                                console.warn('Kitchen art unavailable: ' + path + '; retaining readable fallback.', error);
                                return null;
                            }
                        }));
                        for (const install of apply)
                            install === null || install === void 0 ? void 0 : install();
                        this.modular = !!apply[1];
                        this.ready = atlases.every(([, , required], i) => !required || !!apply[i]);
                    }
                    catch (error) {
                        console.warn('ChefJeff level 1 art unavailable; retaining readable fallback.', error);
                    }
                }
                has(key) { return !!this.frames[key]; }
                /** Manifest entry of a frame (grip, pivot, edge points), or undefined. */
                meta(key) { return this.definitions[key]; }
                /** Let the browser HUD crop the same loaded atlas used by the kitchen. */
                spriteInfo(key) {
                    var _a;
                    const frame = this.frames[key], definition = this.definitions[key], texture = frame === null || frame === void 0 ? void 0 : frame.texture, url = (_a = texture === null || texture === void 0 ? void 0 : texture.image) === null || _a === void 0 ? void 0 : _a.nativeUrl;
                    if (!definition || !texture || !url)
                        return null;
                    const [x, y, width, height] = definition.rect;
                    return { url, x, y, width, height, atlasWidth: texture.width, atlasHeight: texture.height, alphaBBox: definition.alpha_bbox || [0, 0, width, height] };
                }
                /** Natural pixel proportions, one 64 px art unit per gameplay cell. */
                tile(parent, key, cellSize, x = 0, y = 0) {
                    const name = 'modular/' + key, definition = this.definitions[name];
                    if (!definition)
                        return false;
                    const [, , w, h] = definition.rect;
                    return this.show(parent, name, w * cellSize / 64, h * cellSize / 64, x, y);
                }
                /** Align the working surface, independently of transparent canvas and floor anchor. */
                surface(parent, key, cellSize, x, y, depth = 1) {
                    const name = 'modular/' + key, d = this.definitions[name];
                    if (!(d === null || d === void 0 ? void 0 : d.workSurfaceAnchor) || !d.groundAnchor)
                        return false;
                    const scale = cellSize / 64, [, , w, h] = d.rect;
                    return this.show(parent, name, w * scale, h * scale * depth, x - (d.workSurfaceAnchor[0] - d.groundAnchor[0]) * scale, y - (d.groundAnchor[1] - d.workSurfaceAnchor[1]) * scale * depth);
                }
                /** Decorations use a centre anchor independent of floor-based sprite anchors. */
                centered(parent, key, w, h) {
                    const d = this.definitions[key];
                    if (!d)
                        return false;
                    const [, , cw, ch] = d.rect, [left, top, right, bottom] = d.alpha_bbox || [0, 0, cw, ch];
                    const scale = Math.min(w / (right - left), h / (bottom - top));
                    if (!this.show(parent, key, cw * scale, ch * scale, (cw / 2 - (left + right) / 2) * scale, ((top + bottom) / 2 - ch / 2) * scale))
                        return false;
                    parent.getChildByName('reviewed-art').getComponent(cc_1.UITransform).setAnchorPoint(.5, .5);
                    return true;
                }
                hide(parent) { const n = parent.getChildByName('reviewed-art'); if (n)
                    n.active = false; }
                /** Repeatable material crop, retaining the source's pixel density. */
                region(parent, key, x, y, w, h, displayW, displayH) {
                    const base = this.frames[key];
                    if (!base)
                        return false;
                    const cache = [key, x, y, w, h].join(':');
                    if (!this.slices[cache]) {
                        const f = new cc_1.SpriteFrame();
                        f.texture = base.texture;
                        f.rect = new cc_1.Rect(base.rect.x + x, base.rect.y + y, w, h);
                        f.originalSize = new cc_1.Size(w, h);
                        this.slices[cache] = f;
                    }
                    this.show(parent, key, displayW, displayH);
                    const n = parent.getChildByName('reviewed-art');
                    n.getComponent(cc_1.Sprite).spriteFrame = this.slices[cache];
                    n.getComponent(cc_1.UITransform).setAnchorPoint(.5, .5);
                    return true;
                }
                show(parent, key, w, h, x = 0, y = 0) {
                    const frame = this.frames[key];
                    if (!frame) {
                        this.hide(parent);
                        return false;
                    }
                    let n = parent.getChildByName('reviewed-art');
                    if (!n) {
                        n = new cc_1.Node('reviewed-art');
                        n.layer = cc_1.Layers.Enum.UI_2D;
                        parent.addChild(n);
                        n.addComponent(cc_1.UITransform);
                        n.addComponent(cc_1.Sprite);
                    }
                    n.active = true;
                    n.setPosition(x, y);
                    const transform = n.getComponent(cc_1.UITransform);
                    const anchor = this.definitions[key].anchor || [.5, .5];
                    transform.setAnchorPoint(anchor[0], anchor[1]);
                    const sprite = n.getComponent(cc_1.Sprite);
                    sprite.sizeMode = cc_1.Sprite.SizeMode.CUSTOM;
                    sprite.trim = false;
                    if (sprite.spriteFrame !== frame)
                        sprite.spriteFrame = frame;
                    transform.setContentSize(w, h);
                    return true;
                }
            };
            exports_1("LevelOneArt", LevelOneArt);
        }
    };
});

System.register("chunks:///_virtual/main",["./KitchenAudio.ts","./KitchenClient.ts","./KitchenGeometry.ts","./LevelOneArt.ts"],(function(){return{setters:[null,null,null,null],execute:function(){}}}));

(function(r) {
  r('virtual:///prerequisite-imports/main', 'chunks:///_virtual/main');
})(function(mid, cid) {
    System.register(mid, [cid], function (_export, _context) {
    return {
        setters: [function(_m) {
            var _exportObj = {};

            for (var _key in _m) {
              if (_key !== "default" && _key !== "__esModule") _exportObj[_key] = _m[_key];
            }

            _export(_exportObj);
        }],
        execute: function () { }
    };
    });
});