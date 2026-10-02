System.register("chunks:///_virtual/KitchenAudio.ts", ['./rollupPluginModLoBabelHelpers.js', 'cc'], function (exports) {
  var _createForOfIteratorHelperLoose, _asyncToGenerator, _regeneratorRuntime, cclegacy, sys, resources, JsonAsset, AudioClip, Node, AudioSource;
  return {
    setters: [function (module) {
      _createForOfIteratorHelperLoose = module.createForOfIteratorHelperLoose;
      _asyncToGenerator = module.asyncToGenerator;
      _regeneratorRuntime = module.regeneratorRuntime;
    }, function (module) {
      cclegacy = module.cclegacy;
      sys = module.sys;
      resources = module.resources;
      JsonAsset = module.JsonAsset;
      AudioClip = module.AudioClip;
      Node = module.Node;
      AudioSource = module.AudioSource;
    }],
    execute: function () {
      cclegacy._RF.push({}, "ea8e3UwSytAOr39Sj8gvBv3", "KitchenAudio", undefined);
      var STORAGE = 'chefjeff-audio';
      var LOOPS = [
      // name, clip, fade in (s), fade out (s), start at a random offset
      ['ambience', 'amb_kitchen', 1.5, .6, false], ['sizzle', 'sizzle_loop', .15, .4, true], ['fire', 'fire_loop', .2, .5, true], ['wash_solo', 'wash_solo', .08, .1, true], ['wash_duo', 'wash_duo', .2, .2, true]];
      var EVENT_SOUNDS = {
        order: 'order_new',
        ready: 'food_ready',
        burn: 'burnt_warn',
        fire: 'fire_ignite',
        fire_spread: 'fire_spread',
        served: 'serve_ok',
        bad_service: 'serve_bad',
        expired: 'order_expired',
        thrown: 'throw',
        caught: 'catch',
        dropped: 'land',
        plate_returned: 'plate_return'
      };
      var board = function board(id) {
        return !!id && id.startsWith('b') && !id.startsWith('bin');
      };
      var cooking = function cooking(stage) {
        return !!stage && /^(pot_)?(cooking|chopped|ready|burnt)$/.test(stage);
      };

      /** Presentation only: reads kitchen snapshots and plays sounds; never alters observations or rules. */
      var KitchenAudio = exports('KitchenAudio', /*#__PURE__*/function () {
        function KitchenAudio() {
          var _this = this;
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
          this.volume = {
            music: .8,
            sfx: .8
          };
          this.ready = false;
          /** Cocos resumes its suspended Web Audio context only on a canvas click, but the kitchen is played
           *  from the keyboard. Resume the same context on any key or pointer gesture; Cocos then starts the
           *  queued sounds itself. If engine internals change, this quietly falls back to the canvas click. */
          this.unlock = function () {
            return _this.safely(function () {
              // Any source that already holds a clip has a player wired to the engine's shared context.
              for (var _i = 0, _arr = [].concat(_this.music.map(function (ch) {
                  return ch.src;
                }), Object.values(_this.channels).map(function (ch) {
                  return ch.src;
                })); _i < _arr.length; _i++) {
                var _player;
                var src = _arr[_i];
                var context = src == null || (_player = src._player) == null || (_player = _player._player) == null || (_player = _player._gainNode) == null ? void 0 : _player.context;
                if (!context) continue;
                if (context.state !== 'running') context.resume()["catch"](function () {});
                return;
              }
            });
          };
          this.onSettings = function (e) {
            return _this.safely(function () {
              Object.assign(_this.volume, e.detail || {});
            });
          };
        }
        var _proto = KitchenAudio.prototype;
        _proto.load = /*#__PURE__*/function () {
          var _load = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee(parent) {
            var _yield$Promise$all, index, clips, _iterator, _step, c, source, _i2, _LOOPS, _LOOPS$_i, name, clip, fadeIn, fadeOut, randomStart;
            return _regeneratorRuntime().wrap(function _callee$(_context) {
              while (1) switch (_context.prev = _context.next) {
                case 0:
                  _context.prev = 0;
                  _context.next = 3;
                  return Promise.all([new Promise(function (ok, no) {
                    return resources.load('audio/index', JsonAsset, function (e, a) {
                      return e ? no(e) : ok(a);
                    });
                  }), new Promise(function (ok, no) {
                    return resources.loadDir('audio', AudioClip, function (e, a) {
                      return e ? no(e) : ok(a);
                    });
                  })]);
                case 3:
                  _yield$Promise$all = _context.sent;
                  index = _yield$Promise$all[0];
                  clips = _yield$Promise$all[1];
                  this.index = index.json;
                  for (_iterator = _createForOfIteratorHelperLoose(clips); !(_step = _iterator()).done;) {
                    c = _step.value;
                    this.clips[c.name] = c;
                  }
                  source = function source(name) {
                    var n = new Node('audio-' + name);
                    parent.addChild(n);
                    var s = n.addComponent(AudioSource);
                    s.playOnAwake = false;
                    return s;
                  };
                  this.sfx = source('sfx');
                  for (_i2 = 0, _LOOPS = LOOPS; _i2 < _LOOPS.length; _i2++) {
                    _LOOPS$_i = _LOOPS[_i2], name = _LOOPS$_i[0], clip = _LOOPS$_i[1], fadeIn = _LOOPS$_i[2], fadeOut = _LOOPS$_i[3], randomStart = _LOOPS$_i[4];
                    this.channels[name] = {
                      src: source(name),
                      clip: clip,
                      level: 0,
                      target: 0,
                      fadeIn: fadeIn,
                      fadeOut: fadeOut,
                      randomStart: randomStart
                    };
                  }
                  // Two music players so the service/rush switch can crossfade.
                  this.music = [0, 1].map(function (i) {
                    return {
                      src: source('music-' + i),
                      clip: '',
                      level: 0,
                      target: 0,
                      fadeIn: 1.2,
                      fadeOut: .8,
                      randomStart: false
                    };
                  });
                  if (!sys.isNative) {
                    try {
                      Object.assign(this.volume, JSON.parse(localStorage.getItem(STORAGE) || '{}'));
                    } catch (_) {}
                    window.addEventListener('kitchen-audio-settings', this.onSettings);
                    window.addEventListener('keydown', this.unlock, true);
                    window.addEventListener('pointerdown', this.unlock, true);
                  }
                  this.ready = true;
                  _context.next = 19;
                  break;
                case 16:
                  _context.prev = 16;
                  _context.t0 = _context["catch"](0);
                  console.warn('ChefJeff audio unavailable; the kitchen stays silent.', _context.t0);
                case 19:
                case "end":
                  return _context.stop();
              }
            }, _callee, this, [[0, 16]]);
          }));
          function load(_x) {
            return _load.apply(this, arguments);
          }
          return load;
        }() /** Sound must never break play: an audio error is reported once and that sound is skipped. */;
        _proto.safely = function safely(run) {
          try {
            run();
          } catch (error) {
            if (!this.warned) {
              this.warned = true;
              console.warn('ChefJeff audio error; the kitchen carries on without this sound.', error);
            }
          }
        };
        _proto.destroy = function destroy() {
          if (sys.isNative) return;
          window.removeEventListener('kitchen-audio-settings', this.onSettings);
          window.removeEventListener('keydown', this.unlock, true);
          window.removeEventListener('pointerdown', this.unlock, true);
        };
        _proto.gain = function gain(name) {
          var _ref, _this$index$sounds$na, _this$index, _this$index2;
          return (_ref = (_this$index$sounds$na = (_this$index = this.index) == null || (_this$index = _this$index.sounds[name]) == null ? void 0 : _this$index.gain) != null ? _this$index$sounds$na : (_this$index2 = this.index) == null || (_this$index2 = _this$index2.wash[name]) == null ? void 0 : _this$index2.gain) != null ? _ref : .8;
        };
        _proto.play = function play(name, scale, minGap) {
          var _this2 = this;
          if (scale === void 0) {
            scale = 1;
          }
          if (minGap === void 0) {
            minGap = .06;
          }
          this.safely(function () {
            return _this2.playNow(name, scale, minGap);
          });
        };
        _proto.playNow = function playNow(name, scale, minGap) {
          var _this$recent$name;
          var clip = this.clips[name];
          if (!this.ready || !clip || !this.sfx || this.volume.sfx <= 0) return;
          if (this.clock - ((_this$recent$name = this.recent[name]) != null ? _this$recent$name : -1) < minGap) return;
          this.recent[name] = this.clock;
          this.sfx.playOneShot(clip, Math.min(1, this.gain(name) * this.volume.sfx * scale));
        }
        /** One knife strike, fired by the chop animation at the moment the blade meets the board. */;
        _proto.chop = function chop() {
          var _this3 = this;
          this.safely(function () {
            return _this3.chopNow();
          });
        };
        _proto.chopNow = function chopNow() {
          var _this$index3;
          var pool = ((_this$index3 = this.index) == null ? void 0 : _this$index3.chop) || [];
          if (!pool.length) return;
          var name = pool[Math.floor(Math.random() * pool.length)];
          if (name === this.lastChop && pool.length > 1) name = pool[(pool.indexOf(name) + 1) % pool.length];
          this.lastChop = name;
          this.playNow(name, .8 + Math.random() * .2, 0);
        };
        _proto.onState = function onState(s) {
          var _this4 = this;
          this.safely(function () {
            return _this4.applyState(s);
          });
        };
        _proto.applyState = function applyState(s) {
          var _this5 = this;
          if (!this.ready) return;
          var prev = this.last;
          this.last = s;
          var k = s.kitchen,
            fresh = !prev || prev.game_id !== s.game_id;
          if (fresh) {
            this.seen = new Set((s.events || []).map(function (e) {
              return e.t + '|' + e.message;
            }));
            this.urgent.clear();
          }
          this.phaseMusic(prev, s, fresh);
          var running = s.phase === 'running';
          if (!fresh && running) {
            var events = (s.events || []).filter(function (e) {
              return !_this5.seen.has(e.t + '|' + e.message);
            });
            for (var _iterator2 = _createForOfIteratorHelperLoose(events), _step2; !(_step2 = _iterator2()).done;) {
              var e = _step2.value;
              this.seen.add(e.t + '|' + e.message);
              if (e.kind === 'landed') this.play(/落到/.test(e.message) ? 'place_board' : 'land');else if (EVENT_SOUNDS[e.kind]) this.play(EVENT_SOUNDS[e.kind]);
            }
            if (this.seen.size > 80) this.seen = new Set([].concat(this.seen).slice(-40));
            var skip = new Set(events.filter(function (e) {
              return ['thrown', 'dropped', 'interrupted', 'served', 'bad_service'].includes(e.kind);
            }).map(function (e) {
              return e.actor;
            }));
            for (var _i3 = 0, _Object$keys = Object.keys(k.chefs); _i3 < _Object$keys.length; _i3++) {
              var who = _Object$keys[_i3];
              if (!skip.has(who)) this.chefChange(prev.kitchen.chefs[who], k.chefs[who]);
            }
            this.stationChanges(prev.kitchen, k);
            for (var _iterator3 = _createForOfIteratorHelperLoose(k.orders || []), _step3; !(_step3 = _iterator3()).done;) {
              var o = _step3.value;
              if (o.status === 'pending' && o.remaining <= 10 && o.remaining > 0 && !this.urgent.has(o.id)) {
                this.urgent.add(o.id);
                this.play('order_urgent');
              }
            }
          }
          var stations = Object.values(k.stations || {});
          var washers = Object.values(k.chefs).filter(function (c) {
            return c.action_kind === 'wash' && c.working;
          }).length;
          this.channels.ambience.target = running || s.phase === 'ready' ? 1 : 0;
          this.channels.sizzle.target = running && stations.some(function (st) {
            var _st$food;
            return st.stove && st.heating && !st.fire && cooking((_st$food = st.food) == null ? void 0 : _st$food.stage);
          }) ? 1 : 0;
          this.channels.fire.target = running && stations.some(function (st) {
            return st.fire;
          }) ? 1 : 0;
          this.channels.wash_solo.target = running && washers === 1 ? 1 : 0;
          this.channels.wash_duo.target = running && washers >= 2 ? 1 : 0;
        };
        _proto.chefChange = function chefChange(a, b) {
          var before = a.holding,
            after = b.holding,
            kind = a.action_kind || b.action_kind,
            target = a.target || b.target;
          var sameItem = before && after && before.id === after.id;
          if (sameItem && before.stage !== after.stage) {
            if (kind === 'assemble') this.play('assemble');else if (kind === 'empty_pot' || kind === 'discard') this.play('discard');else if (/^plate|merge/.test(kind || '')) this.play('plate_place');
            return;
          }
          if (after && !sameItem) {
            this.play(kind === 'fetch' && target === 'fridge' ? 'fridge_grab' : 'pickup');
            return;
          }
          if (before && !after) {
            var _this$last;
            if (['discard', 'empty_pot', 'clear'].includes(kind)) this.play('discard');else if (target === 'serve' || (_this$last = this.last) != null && (_this$last = _this$last.kitchen) != null && (_this$last = _this$last.stations) != null && (_this$last = _this$last[target]) != null && _this$last.stove) return; // serving/pan sounds come from events/stations
            else if (board(target)) this.play('place_board');else this.play(/plate/.test(before.stage) ? 'plate_place' : 'place_board');
            return;
          }
          // Finished an assembly or plating job without a hand change (e.g. building on the counter).
          if (a.job_id && a.job_id !== b.job_id && a.working && (a.action_kind === 'assemble' || /^plate|merge/.test(a.action_kind || ''))) this.play(a.action_kind === 'assemble' ? 'assemble' : 'plate_place');
        };
        _proto.stationChanges = function stationChanges(a, b) {
          var held = new Set(Object.values(b.chefs).map(function (c) {
            var _c$holding;
            return (_c$holding = c.holding) == null ? void 0 : _c$holding.id;
          }).filter(Boolean));
          for (var _i4 = 0, _Object$entries = Object.entries(b.stations || {}); _i4 < _Object$entries.length; _i4++) {
            var _a$stations, _n$food, _p$food;
            var _Object$entries$_i = _Object$entries[_i4],
              key = _Object$entries$_i[0],
              n = _Object$entries$_i[1];
            var p = (_a$stations = a.stations) == null ? void 0 : _a$stations[key];
            if (!p) continue;
            if (p.fire && !n.fire) this.play('extinguisher');
            if (n.stove && cooking((_n$food = n.food) == null ? void 0 : _n$food.stage) && /cooking|chopped/.test(n.food.stage) && !cooking((_p$food = p.food) == null ? void 0 : _p$food.stage)) this.play('pan_sizzle_start');
            // Burnt food cleared out of a pot without anyone carrying it away: it was dumped.
            if (p.food && /burnt/.test(p.food.stage) && !n.food && !held.has(p.food.id)) this.play('discard');
          }
        };
        _proto.phaseMusic = function phaseMusic(prev, s, fresh) {
          var was = prev == null ? void 0 : prev.phase,
            now = s.phase;
          if (!fresh && was === 'running' && now === 'paused') this.play('ui_pause');
          if (!fresh && was === 'paused' && now === 'running') this.play('ui_resume');
          if (now === 'ended' && !fresh && was !== 'ended' && this.endedGame !== s.game_id) {
            this.endedGame = s.game_id;
            this.setMusic('');
            this.play(s.won ? 'jingle_win' : 'jingle_lose', 1, 0);
            this.menuAfter = this.clock + (s.won ? 3.5 : 2.3);
            return;
          }
          if (now === 'ended') {
            if (this.menuAfter && this.clock < this.menuAfter) return;
            this.setMusic('bgm_menu');
            return;
          }
          if (now === 'running') this.setMusic(s.kitchen.round_remaining <= 30 ? 'bgm_rush' : 'bgm_service');else if (now === 'paused') this.setMusic('');else this.setMusic('bgm_menu');
        };
        _proto.setMusic = function setMusic(name) {
          if (name === this.musicClip) return;
          this.musicClip = name;
          for (var _iterator4 = _createForOfIteratorHelperLoose(this.music), _step4; !(_step4 = _iterator4()).done;) {
            var ch = _step4.value;
            if (ch.clip !== name) ch.target = 0;
          }
          if (!name) return;
          // Pausing keeps the position, so resuming the same piece continues where it stopped.
          var same = this.music.find(function (ch) {
            return ch.clip === name;
          });
          if (same) {
            same.target = 1;
            return;
          }
          var free = this.music[0].level <= this.music[1].level ? this.music[0] : this.music[1];
          free.src.stop();
          free.clip = name;
          free.src.clip = this.clips[name] || null;
          free.level = 0;
          free.target = 1;
        };
        _proto.update = function update(dt) {
          var _this6 = this;
          this.safely(function () {
            return _this6.tick(dt);
          });
        };
        _proto.tick = function tick(dt) {
          this.clock += dt;
          if (!this.ready) return;
          if (this.menuAfter && this.clock >= this.menuAfter) {
            var _this$last2;
            this.menuAfter = 0;
            if (((_this$last2 = this.last) == null ? void 0 : _this$last2.phase) === 'ended') this.setMusic('bgm_menu');
          }
          for (var _i5 = 0, _Object$values = Object.values(this.channels); _i5 < _Object$values.length; _i5++) {
            var ch = _Object$values[_i5];
            this.step(ch, dt, this.volume.sfx, true);
          }
          for (var _iterator5 = _createForOfIteratorHelperLoose(this.music), _step5; !(_step5 = _iterator5()).done;) {
            var _ch = _step5.value;
            this.step(_ch, dt, this.volume.music, false);
          }
        };
        _proto.step = function step(ch, dt, master, sfx) {
          var rate = ch.target > ch.level ? 1 / ch.fadeIn : 1 / ch.fadeOut;
          ch.level = ch.target > ch.level ? Math.min(ch.target, ch.level + dt * rate) : Math.max(ch.target, ch.level - dt * rate);
          var clip = this.clips[ch.clip];
          if (!clip) return;
          var src = ch.src;
          if (ch.level > 0 && master > 0) {
            if (src.clip !== clip) src.clip = clip;
            src.loop = true;
            if (!src.playing) {
              src.play();
              if (ch.randomStart && sfx) src.currentTime = Math.random() * Math.max(0, clip.getDuration() - .2);
            }
            src.volume = ch.level * this.gain(ch.clip) * master;
          } else if (src.playing) {
            // Loops pause at silence; texture loops restart elsewhere next time, music resumes in place.
            if (sfx && ch.randomStart) src.stop();else src.pause();
          }
        };
        return KitchenAudio;
      }());
      cclegacy._RF.pop();
    }
  };
});

System.register("chunks:///_virtual/KitchenClient.ts", ['./rollupPluginModLoBabelHelpers.js', 'cc', './LevelOneArt.ts', './KitchenAudio.ts', './KitchenGeometry.ts'], function (exports) {
  var _inheritsLoose, _createForOfIteratorHelperLoose, _createClass, _extends, _asyncToGenerator, _regeneratorRuntime, cclegacy, _decorator, sys, profiler, view, ResolutionPolicy, director, Camera, Color, UITransform, Label, Node, Graphics, game, Game, Layers, Sprite, Vec2, Mask, Component, LevelOneArt, KitchenAudio, predictWalk, footWalkable, plateLayers, stationView, wallNeighbours, GRID_ART, surfaceOffset, trashView, behindCounter, depthOrder, heatCountdown, flightDepth, workingChefDepth;
  return {
    setters: [function (module) {
      _inheritsLoose = module.inheritsLoose;
      _createForOfIteratorHelperLoose = module.createForOfIteratorHelperLoose;
      _createClass = module.createClass;
      _extends = module.extends;
      _asyncToGenerator = module.asyncToGenerator;
      _regeneratorRuntime = module.regeneratorRuntime;
    }, function (module) {
      cclegacy = module.cclegacy;
      _decorator = module._decorator;
      sys = module.sys;
      profiler = module.profiler;
      view = module.view;
      ResolutionPolicy = module.ResolutionPolicy;
      director = module.director;
      Camera = module.Camera;
      Color = module.Color;
      UITransform = module.UITransform;
      Label = module.Label;
      Node = module.Node;
      Graphics = module.Graphics;
      game = module.game;
      Game = module.Game;
      Layers = module.Layers;
      Sprite = module.Sprite;
      Vec2 = module.Vec2;
      Mask = module.Mask;
      Component = module.Component;
    }, function (module) {
      LevelOneArt = module.LevelOneArt;
    }, function (module) {
      KitchenAudio = module.KitchenAudio;
    }, function (module) {
      predictWalk = module.predictWalk;
      footWalkable = module.footWalkable;
      plateLayers = module.plateLayers;
      stationView = module.stationView;
      wallNeighbours = module.wallNeighbours;
      GRID_ART = module.GRID_ART;
      surfaceOffset = module.surfaceOffset;
      trashView = module.trashView;
      behindCounter = module.behindCounter;
      depthOrder = module.depthOrder;
      heatCountdown = module.heatCountdown;
      flightDepth = module.flightDepth;
      workingChefDepth = module.workingChefDepth;
    }],
    execute: function () {
      var _dec, _class;
      cclegacy._RF.push({}, "7dafalzrH9GT4bSNEmN6gVT", "KitchenClient", undefined);
      var ccclass = _decorator.ccclass;
      // Tokens from the "ChefJeff 厨房 UI" design system: every colour is sampled from the art
      // (denim overalls, copper-eared Jeff, honey floorboards, walnut walls, steel stoves).
      var COLORS = {
        ink: '#2b1a12',
        muted: '#6e4e38',
        bg: '#f0d9b5',
        paper: '#fdf3e1',
        honeyTint: '#fbe3b8',
        walnut: '#6b3418',
        honey: '#e8983a',
        steel: '#3d5566',
        human: '#2a5a9e',
        humanHover: '#224a82',
        jeff: '#a8520e',
        herb: '#3c7a2a',
        hot: '#b8321e',
        hotHover: '#9c2a19',
        // alert: danger text on the surface ground (the hot red itself is 4.35:1 there).
        alert: '#9c2a19',
        frame: '#4a2616',
        // Fallback programmer art only.
        wood: '#6b3418',
        wall: '#ae8055',
        counter: '#8baab7',
        counterEdge: '#587582',
        counterLight: '#c6d9de'
      };
      // Pixel face for titles, buttons, tags and HUD numbers (loaded by the web shell); body text stays system.
      var PIXEL = 'ChefJeffPixel, sans-serif';
      // Result events reach the player; AI decision notes have their own status line.
      var RESULT_ANNOUNCE = new Set(['order', 'served', 'expired', 'ready', 'burn', 'fire', 'fire_spread', 'fire_loss']);
      var TAB_ORDER = ['language', 'level1', 'level2', 'level3', 'main', 'reset', 'cover-connection', 'help', 'record', 'resume', 'pause', 'end'];
      // Labels for things that are not recipe items; item and dish names come from the server's catalog.
      var STAGES = {
        extinguisher: '灭火器',
        clean_plate: '干净餐盘',
        dirty_plate: '脏餐盘'
      };
      // Art stem for a vessel kind that has no art of its own yet (the soup pot's frames).
      var VESSEL_ART_FALLBACK = 'pot';
      // Fallback tints by stage, for items without a colour; burnt is charred for every item.
      var FOOD_COLORS = {
        raw: '#d68f8c',
        chopped: '#dcaa86',
        cooking: '#b58359',
        ready: '#846144',
        burnt: '#3e3733',
        extinguisher: '#c65138'
      };
      var TILE = GRID_ART.tile,
        MAPX = GRID_ART.originX,
        MAPY = GRID_ART.originY;
      var color = function color(hex) {
        return new Color().fromHEX(hex);
      };
      var KitchenClient = exports('KitchenClient', (_dec = ccclass('KitchenClient'), _dec(_class = /*#__PURE__*/function (_Component) {
        _inheritsLoose(KitchenClient, _Component);
        function KitchenClient() {
          var _this;
          for (var _len = arguments.length, args = new Array(_len), _key = 0; _key < _len; _key++) {
            args[_key] = arguments[_key];
          }
          _this = _Component.call.apply(_Component, [this].concat(args)) || this;
          _this.state = null;
          _this.art = new LevelOneArt();
          _this.artLoaded = false;
          _this.audio = new KitchenAudio();
          _this.knifePhase = {};
          _this.pending = false;
          _this.polling = false;
          _this.lastScheduledPoll = -Infinity;
          _this.hidden = false;
          _this.connected = false;
          _this.clock = 0;
          _this.activeClock = 0;
          _this.heldKeys = new Set();
          _this.moveSeq = Date.now() * 1000;
          _this.lastMoveAt = 0;
          _this.manualDirection = {
            x: 0,
            y: 0
          };
          // Held-key walking is predicted locally so the chef answers on the same frame, then eased onto server state.
          _this.predicted = null;
          /** Held-key walk in whole server ticks: position at the last tick, the next one, and the progress between. */
          _this.walkPlan = null;
          _this.releasedAt = null;
          _this.stateSentAt = 0;
          _this.handsBusyUntil = -1;
          _this.qaNoMotion = !sys.isNative && new URLSearchParams(location.search).get('qaMotion') === 'off';
          // Isolated visual pilot; not enabled at the fixed gameplay entry.
          _this.prepSample = !sys.isNative && new URLSearchParams(location.search).get('prepSample') === '1';
          _this.prepPoses = {};
          // Knife-only comparison: same normal scene and actor in both variants.
          _this.knifeSample = !sys.isNative && new URLSearchParams(location.search).get('knifeSample') === '1';
          _this.knifeProbe = null;
          _this.cutProbe = null;
          _this.chopImpacts = {};
          _this.received = 0;
          _this.labels = {};
          _this.buttons = {};
          _this.controlAccess = null;
          _this.reduceMotion = !sys.isNative && !!(window.matchMedia != null && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
          _this.eventsGame = '';
          _this.seenEvents = new Set();
          _this.lastAiError = null;
          _this.pops = [];
          _this.flashes = {};
          _this.tickets = [];
          _this.orderArt = [];
          _this.focusId = "";
          _this.meters = {};
          _this.overlayPhase = "";
          _this.recordShown = "";
          _this.devices = {};
          _this.people = {};
          _this.motions = {};
          _this.potEffects = {};
          _this.cabinetFires = {};
          _this.foodStages = {};
          _this.readyUntil = {};
          _this.jeffThinking = null;
          _this.jeffError = null;
          _this.ground = {};
          _this.groundStages = {};
          _this.flights = {};
          _this.flightOrder = {};
          _this.menu = null;
          _this.menuSignature = '';
          _this.cover = null;
          _this.mounted = false;
          _this.world = null;
          _this.depthEntries = [];
          _this.mapNodes = [];
          _this.mountedLayout = "";
          // Native debug builds use USB forwarding: adb reverse tcp:8769 tcp:8769.
          // Production releases replace this with the operator's HTTPS game backend, never a Jev API key.
          _this.endpoint = sys.isNative ? 'http://127.0.0.1:8769' : '';
          _this.onBlur = function () {
            return _this.clearInput();
          };
          _this.onVisibility = function () {
            if (document.hidden) _this.clearInput();
          };
          _this.onContextMenu = function (e) {
            var _e$target;
            if ((_e$target = e.target) != null && _e$target.closest('canvas')) e.preventDefault();
          };
          _this.onMouseDown = function (e) {
            var _e$target2;
            if (e.button === 2 && (_e$target2 = e.target) != null && _e$target2.closest('canvas')) {
              e.preventDefault();
              e.stopImmediatePropagation();
            }
          };
          _this.onMouseUp = function (e) {
            var _e$target3;
            if (e.button === 2 && (_e$target3 = e.target) != null && _e$target3.closest('canvas')) {
              e.preventDefault();
              e.stopImmediatePropagation();
            }
          };
          _this.onKey = function (e) {
            var _document$activeEleme, _document$activeEleme2, _this$state, _this$state2;
            // The communication dock keeps native Tab/Enter/Space; Esc hands the keyboard back.
            var dock = !sys.isNative ? (_document$activeEleme = document.activeElement) == null ? void 0 : _document$activeEleme.closest('#kitchen-communication') : null;
            if (e.key === 'Escape') {
              if (dock) {
                document.activeElement.blur();
                return;
              }
              if (e.repeat || !sys.isNative && document.querySelector('dialog[open]')) return;
              _this.togglePause(e);
              return;
            }
            if (e.isComposing || e.keyCode === 229) return;
            if (!sys.isNative && (document.querySelector('dialog[open]') || (_document$activeEleme2 = document.activeElement) != null && _document$activeEleme2.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]'))) return;
            // P pauses and resumes like Esc, for keyboards without an Esc key (iPad Magic Keyboard).
            // Typing fields and open dialogs are excluded above.
            if (e.code === 'KeyP' && !e.ctrlKey && !e.altKey && !e.metaKey) {
              if (!e.repeat) _this.togglePause(e);else e.preventDefault();
              return;
            }
            if (dock && (e.key === 'Enter' || e.code === 'Space' || e.key === 'Tab')) return;
            if (e.key === 'Shift' && ((_this$state = _this.state) == null ? void 0 : _this$state.phase) === 'running') {
              e.preventDefault();
              e.stopImmediatePropagation();
              if (!e.repeat && !e.ctrlKey && !e.altKey && !e.metaKey) _this.bookmark();
              return;
            }
            if (((_this$state2 = _this.state) == null ? void 0 : _this$state2.phase) === 'running' && _this.connected) {
              // Overcooked layout, browser-safe keys: Space = whatever the faced target needs (pick up,
              // put down, and chop/wash too), E = chop, wash, extinguish or throw ahead (Overcooked's
              // Ctrl), Q = dash (Overcooked's Alt). Held direction keys survive both.
              if (e.code === 'Space' || e.code === 'KeyE') {
                e.preventDefault();
                if (!e.repeat && !e.ctrlKey && !e.altKey && !e.metaKey) {
                  var _this$state$kitchen$c;
                  var use = e.code === 'KeyE';
                  if (!use) _this.handsBusyUntil = _this.clock + .35;
                  _this.post('/api/interact', _extends({
                    expected_item: ((_this$state$kitchen$c = _this.state.kitchen.chefs.human.holding) == null ? void 0 : _this$state$kitchen$c.id) || null
                  }, use ? {
                    mode: 'use'
                  } : {}));
                }
                return;
              }
              if (e.code === 'KeyQ') {
                e.preventDefault();
                if (!e.repeat && (_this.manualDirection.x !== 0 || _this.manualDirection.y !== 0)) _this.sendMove(_this.manualDirection.x, _this.manualDirection.y, true);
                return;
              }
              var key = e.key.toLowerCase();
              if (['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(key)) {
                e.preventDefault();
                _this.heldKeys.add(key);
                _this.refreshMovement();
                return;
              }
            }
            if (e.key === 'Tab') {
              e.preventDefault();
              var ids = TAB_ORDER.filter(function (id) {
                return _this.buttons[id].enabled && _this.buttons[id].node.activeInHierarchy;
              });
              if (!ids.length) return;
              var at = ids.indexOf(_this.focusId);
              _this.setFocus(ids[(at + (e.shiftKey ? -1 : 1) + ids.length) % ids.length]);
            } else if (e.key === 'Enter' && _this.focusId) {
              var b = _this.buttons[_this.focusId];
              if (b != null && b.enabled && b.node.activeInHierarchy) {
                e.preventDefault();
                _this.audio.play('ui_click');
                b.callback();
              }
            }
          };
          _this.onConfirmed = function (e) {
            var _this$state3;
            var d = e.detail;
            if (d.ok) _this.post(d.kind === 'end' ? '/api/end' : '/api/restart');else if (d.resume && ((_this$state3 = _this.state) == null ? void 0 : _this$state3.phase) === 'paused') _this.post('/api/resume');
          };
          _this.onKeyUp = function (e) {
            var key = e.key.toLowerCase();
            if (_this.heldKeys["delete"](key)) _this.refreshMovement();
          };
          _this.labelSources = new WeakMap();
          _this.onLanguage = function () {
            _this.clearInput();
            for (var _iterator = _createForOfIteratorHelperLoose(_this.node.getComponentsInChildren(Label)), _step; !(_step = _iterator()).done;) {
              var label = _step.value;
              var source = _this.labelSources.get(label);
              if (source !== undefined) _this.writeLabel(label, source);
            }
            _this.render();
          };
          _this.scheduledPoll = function () {
            var _this$state4;
            var interval = ((_this$state4 = _this.state) == null ? void 0 : _this$state4.phase) === 'running' ? .2 : 1;
            if (_this.clock - _this.lastScheduledPoll < interval - .01) return;
            _this.lastScheduledPoll = _this.clock;
            _this.poll();
          };
          _this.poll = /*#__PURE__*/_asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee() {
            var _next$kitchen, _next$release, _this$state5, _this$state6, _this$state7, sent, next, _i, _arr, id, _i2, _arr2, n, _i3, _arr3, who, frameRate;
            return _regeneratorRuntime().wrap(function _callee$(_context) {
              while (1) switch (_context.prev = _context.next) {
                case 0:
                  if (!(_this.polling || _this.hidden || !_this.artLoaded)) {
                    _context.next = 2;
                    break;
                  }
                  return _context.abrupt("return");
                case 2:
                  _this.polling = true;
                  _context.prev = 3;
                  sent = _this.clock;
                  _context.next = 7;
                  return _this.request('/api/state');
                case 7:
                  next = _context.sent;
                  if (!(!/^level-[123]-[1-9][0-9]*$/.test(((_next$kitchen = next.kitchen) == null || (_next$kitchen = _next$kitchen.map) == null ? void 0 : _next$kitchen.layout_version) || '') || ((_next$release = next.release) == null ? void 0 : _next$release.version) !== '0.6.0-beta.1')) {
                    _context.next = 17;
                    break;
                  }
                  _this.connected = false;
                  _this.clearInput();
                  _this.cover.active = true;
                  _this.set('coverTitle', '等待厨房更新');
                  _this.set('coverText', '新版页面已就绪，厨房服务仍在保留旧对局。\n服务更新后会自动连接，请先完成更新确认。');
                  for (_i = 0, _arr = ['main', 'reset', 'cover-connection']; _i < _arr.length; _i++) {
                    id = _arr[_i];
                    _this.enable(id, false);
                  }
                  _this.hideLoading();
                  return _context.abrupt("return");
                case 17:
                  _this.enable('cover-connection', true);
                  if (_this.mounted && _this.mountedLayout !== next.kitchen.map.layout_version) {
                    for (_i2 = 0, _arr2 = [].concat(_this.mapNodes, Object.values(_this.ground), Object.values(_this.flights)); _i2 < _arr2.length; _i2++) {
                      n = _arr2[_i2];
                      n.destroy();
                    }
                    _this.devices = {};
                    _this.people = {};
                    _this.motions = {};
                    _this.potEffects = {};
                    _this.cabinetFires = {};
                    _this.ground = {};
                    _this.flights = {};
                    _this.groundStages = {};
                    _this.mounted = false;
                  }
                  if (next.game_id !== ((_this$state5 = _this.state) == null ? void 0 : _this$state5.game_id) || !_this.connected) {
                    _this.menuSignature = '';
                    _this.foodStages = {};
                    _this.readyUntil = {};
                    _this.activeClock = 0;
                    if (_this.mounted) for (_i3 = 0, _arr3 = ['human', 'jeff']; _i3 < _arr3.length; _i3++) {
                      who = _arr3[_i3];
                      _this.locate(_this.people[who], next.kitchen.chefs[who].position);
                    }
                  }
                  if (next.phase !== 'running' || next.game_id !== ((_this$state6 = _this.state) == null ? void 0 : _this$state6.game_id)) _this.clearInput();
                  if (next.game_id !== ((_this$state7 = _this.state) == null ? void 0 : _this$state7.game_id)) _this.moveSeq = Date.now() * 1000;
                  _this.state = next;
                  _this.connected = true;
                  _this.received = _this.clock;
                  _this.stateSentAt = sent;
                  frameRate = next.phase === 'running' ? 60 : 15;
                  if (game.frameRate !== frameRate) game.frameRate = frameRate;
                  if (!sys.isNative) window.dispatchEvent(new CustomEvent('kitchen-state', {
                    detail: {
                      game_id: next.game_id,
                      phase: next.phase,
                      connection: next.connection,
                      memory: next.memory,
                      limits: next.limits,
                      release: next.release,
                      communication: next.communication
                    }
                  }));
                  if (!_this.mounted) _this.mountMap();
                  _this.processEvents();
                  _this.render();
                  _this.hideLoading();
                  _this.audio.onState(next);
                  _context.next = 51;
                  break;
                case 36:
                  _context.prev = 36;
                  _context.t0 = _context["catch"](3);
                  _this.hideLoading();
                  game.frameRate = 15;
                  _this.clearInput();
                  _this.connected = false;
                  if (_this.jeffThinking) _this.jeffThinking.active = false;
                  _this.set('event', String(_context.t0.message) + '，厨房会自动暂停。');
                  _this.cover.active = true;
                  _this.set('coverTitle', '连接厨房');
                  _this.set('coverText', '暂时连接不上厨房，请稍后重试。\n连接中断时，游戏会自动暂停。');
                  _this.writeLabel(_this.buttons.main.label, '重新连接');
                  _this.buttons.reset.node.active = false;
                  _this.buttons.record.node.active = false;
                  _this.labels['welcome-tip'].node.active = true;
                case 51:
                  _context.prev = 51;
                  _this.polling = false;
                  return _context.finish(51);
                case 54:
                case "end":
                  return _context.stop();
              }
            }, _callee, null, [[3, 36, 51, 54]]);
          }));
          _this.tagText = {};
          return _this;
        }
        var _proto = KitchenClient.prototype;
        _proto.registerDepth = function registerDepth(node, getDepth) {
          this.depthEntries.push({
            node: node,
            getDepth: getDepth
          });
        };
        _proto.sortWorld = function sortWorld() {
          this.depthEntries = this.depthEntries.filter(function (e) {
            return e.node.isValid;
          });
          this.depthEntries.sort(function (a, b) {
            return a.getDepth() - b.getDepth();
          });
          this.depthEntries.forEach(function (e, i) {
            return e.node.setSiblingIndex(i);
          });
        };
        _proto.start = function start() {
          var _this2 = this,
            _fonts;
          if (!sys.isNative && new URLSearchParams(location.search).has('qaPerf')) profiler.showStats();else profiler.hideStats();
          view.setDesignResolutionSize(1280, 720, ResolutionPolicy.SHOW_ALL);
          // Letterbox bands match the page's wall-plank frame instead of the engine's default grey.
          for (var _iterator2 = _createForOfIteratorHelperLoose(((_director$getScene = director.getScene()) == null ? void 0 : _director$getScene.getComponentsInChildren(Camera)) || []), _step2; !(_step2 = _iterator2()).done;) {
            var _director$getScene;
            var cam = _step2.value;
            cam.clearColor = color(COLORS.frame);
          }
          this.node.getComponent(UITransform).setContentSize(1280, 720);
          this.box(this.node, 'background', 640, 360, 1280, 720, COLORS.bg);
          this.box(this.node, 'header', 640, 35, 1280, 70, COLORS.paper);
          this.icon(this.node, 'brand-icon', 45, 35, 'vessel', 1.1);
          this.pixel(this.text('brand', 'ChefJeff', 80, 30, 170, 36, 24), 24);
          this.text('edition', '和AI一起经营餐馆', 81, 53, 290, 20, 11).color = color(COLORS.muted);
          for (var _i4 = 0, _arr4 = [[0, 'served', '完成订单'], [1, 'money', '营业收入']]; _i4 < _arr4.length; _i4++) {
            var _arr4$_i = _arr4[_i4],
              i = _arr4$_i[0],
              id = _arr4$_i[1],
              title = _arr4$_i[2];
            var x = 690 + i * 130;
            this.text(id + '-title', title, x, 19, 120, 20, 12).color = color(COLORS.muted);
            this.pixel(this.text(id, '—', x, 46, 120, 32, 24), 24);
          }
          this.pixel(this.text('clock', '准备开店', 470, 34, 220, 28, 24), 24).color = color(COLORS.muted);
          this.box(this.node, 'order-rail', 640, 81, 812, 8, COLORS.walnut);
          for (var _i5 = 0; _i5 < 5; _i5++) {
            var _x = 234 + _i5 * 164,
              n = this.make('ticket-' + _i5, _x + 78, 112, 156, 67);
            this.tickets.push(n);
            this.pixel(this.text('order-id-' + _i5, '', _x + 12, 96, 100, 16, 12), 12);
            this.pixel(this.text('order-name-' + _i5, '', _x + 12, 117, 132, 26, 24), 24);
            this.pixel(this.text('order-time-' + _i5, '', _x + 104, 96, 40, 16, 12), 12).horizontalAlign = Label.HorizontalAlign.RIGHT;
          }
          // Map geometry has a shared projection; the exterior remains plain.
          this.text('sprint-status', '', 1070, 63, 190, 16, 11).horizontalAlign = Label.HorizontalAlign.RIGHT;
          this.text('fire-status', '', 1060, 112, 205, 25, 14).color = color(COLORS.alert);
          // End sits apart from pause/resume; both destructive actions ask first.
          this.button('pause', 'Ⅱ', 1100, 34, 44, 36, function () {
            return _this2.post('/api/pause');
          });
          this.button('resume', '▶', 1152, 34, 44, 36, function () {
            return _this2.post('/api/resume');
          }, this.node, 'primary');
          this.button('end', '■', 1226, 34, 44, 36, function () {
            return _this2.confirm('end');
          }, this.node, 'danger');
          for (var _i6 = 0, _arr5 = ['pause', 'resume', 'end']; _i6 < _arr5.length; _i6++) {
            var _id = _arr5[_i6];
            this.pixel(this.buttons[_id].label, 24);
          }
          this.text('hand', '', 234, 691, 235, 22, 14).color = color(COLORS.ink);
          this.text('interaction', '', 470, 691, 575, 22, 14).color = color(COLORS.ink);
          this.text('event', '', 234, 709, 500, 18, 13).color = color(COLORS.ink);
          this.text('ai-status', '', 744, 709, 302, 18, 13).horizontalAlign = Label.HorizontalAlign.RIGHT;
          this.cover = this.make('cover', 640, 360, 1280, 720);
          this.cover.on(Node.EventType.TOUCH_END, function (e) {
            e.propagationStopped = true;
          });
          var shade = this.cover.addComponent(Graphics);
          shade.fillColor = new Color(43, 26, 18, 170);
          shade.rect(-640, -360, 1280, 720);
          shade.fill();
          // A cafe awning frames the start/pause board; the kitchen stays visible behind it.
          this.box(this.cover, 'welcome-shadow', 646, 367, 736, 464, COLORS.ink);
          this.box(this.cover, 'welcome-board', 640, 358, 736, 464, COLORS.paper);
          for (var _i7 = 0; _i7 < 16; _i7++) this.box(this.cover, 'awning', 295 + _i7 * 46, 145, 46, 38, _i7 % 2 ? COLORS.paper : COLORS.human);
          this.text('welcome-kicker', '和AI一起经营餐馆', 340, 193, 600, 25, 13, this.cover).horizontalAlign = Label.HorizontalAlign.CENTER;
          this.pixel(this.text('coverTitle', 'ChefJeff', 316, 244, 648, 56, 48, this.cover), 48);
          this.labels.coverTitle.horizontalAlign = Label.HorizontalAlign.CENTER;
          this.chef(this.cover, 'welcome-human', 550, 332, 'human', 1.25);
          this.chef(this.cover, 'welcome-jeff', 730, 332, 'jeff', 1.25);
          this.icon(this.cover, 'welcome-food', 640, 332, 'ready', 1.05);
          this.text('coverText', '正在连接厨房…', 330, 404, 620, 78, 19, this.cover).horizontalAlign = Label.HorizontalAlign.CENTER;
          this.button('main', '开始经营', 379, 520, 158, 48, function () {
            var _this2$state, _this2$state2;
            if (!_this2.connected) {
              _this2.poll();
              return;
            }
            var phase = (_this2$state = _this2.state) == null ? void 0 : _this2$state.phase;
            if (phase === 'ready' && (_this2$state2 = _this2.state) != null && _this2$state2.connection && !_this2.state.connection.configured) {
              _this2.set('coverText', '请先从下方「设置」连接自己的 API，再开始经营。');
              return;
            }
            _this2.post(phase === 'ready' ? '/api/start' : phase === 'paused' ? '/api/resume' : '/api/reset', phase === 'ready' ? {
              speed: .75
            } : {});
          }, this.cover, 'primary');
          this.button('reset', '重新开局', 553, 520, 158, 48, function () {
            return _this2.confirm('restart');
          }, this.cover);
          this.buttons.reset.node.active = false;
          this.button('cover-connection', '设置', 727, 520, 158, 48, function () {
            return _this2.openConnection();
          }, this.cover);
          this.button('help', '操作说明', 901, 520, 158, 48, function () {
            return _this2.openHelp();
          }, this.cover);
          var _loop = function _loop() {
            var n = _arr6[_i8];
            _this2.pixel(_this2.button('level' + n, '', 188 + n * 226, 464, 210, 30, function () {
              return _this2.post('/api/level', {
                level: n
              });
            }, _this2.cover).getComponentInChildren(Label), 12);
          };
          for (var _i8 = 0, _arr6 = [1, 2, 3]; _i8 < _arr6.length; _i8++) {
            _loop();
          }
          // Language sits on the board where people look first, not only inside Settings.
          this.pixel(this.button('language', 'English', 944, 196, 88, 30, function () {
            var i18n = window.kitchenI18n;
            i18n == null || i18n.setLanguage(i18n.language === 'en' ? 'zh' : 'en');
          }, this.cover).getComponentInChildren(Label), 12);
          if (sys.isNative) this.buttons.language.node.active = false;
          this.text('welcome-tip', '先看操作说明，准备好了就开店。', 333, 577, 614, 19, 11, this.cover).horizontalAlign = Label.HorizontalAlign.CENTER;
          // The round record shares the tip's row: the tip shows before a round, the record after it.
          this.button('record', '本局记录', 561, 566, 158, 36, function () {
            return _this2.openRecord();
          }, this.cover);
          this.buttons.record.node.active = false;
          if (!sys.isNative) {
            // Screen-reader proxies for every canvas button. Canvas focus moves DOM
            // focus to the matching proxy so assistive technology follows it.
            this.controlAccess = document.createElement('div');
            this.controlAccess.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);';
            var _loop2 = function _loop2() {
              var id = _TAB_ORDER[_i9];
              var b = document.createElement('button');
              b.dataset.control = id;
              b.tabIndex = -1;
              b.onclick = function () {
                if (_this2.buttons[id].enabled) _this2.buttons[id].callback();
              };
              _this2.controlAccess.appendChild(b);
            };
            for (var _i9 = 0, _TAB_ORDER = TAB_ORDER; _i9 < _TAB_ORDER.length; _i9++) {
              _loop2();
            }
            document.body.appendChild(this.controlAccess);
            var canvas = document.getElementById('GameCanvas');
            canvas == null || canvas.setAttribute('role', 'img');
            canvas == null || canvas.setAttribute('aria-label', 'ChefJeff 厨房画面');
          }
          game.on(Game.EVENT_HIDE, this.onHide, this);
          game.on(Game.EVENT_SHOW, this.onShow, this);
          if (!sys.isNative) {
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
          game.frameRate = 15;
          this.audio.load(this.node);
          this.art.load().then(function () {
            _this2.artLoaded = true;
            _this2.loadingStep('正在连接厨房…');
            if (_this2.isValid) _this2.poll();
          });
          if (!sys.isNative) (_fonts = document.fonts) == null || _fonts.load('24px ChefJeffPixel').then(function () {
            // Labels drawn before the pixel face arrived keep the fallback until re-rendered.
            for (var _iterator3 = _createForOfIteratorHelperLoose(_this2.node.getComponentsInChildren(Label)), _step3; !(_step3 = _iterator3()).done;) {
              var l = _step3.value;
              l.updateRenderData(true);
            }
            _this2.tagText = {};
            if (_this2.state && _this2.mounted) _this2.render();
          })["catch"](function () {});
          this.schedule(this.scheduledPoll, .2);
        }
        // The page's loading screen stays up until the kitchen first answers (or fails), so the
        // cover never flashes placeholder art or a second "connecting" state.
        ;

        _proto.loadingStep = function loadingStep(text) {
          var el = !sys.isNative && document.querySelector('#kitchen-loading span');
          if (el) el.textContent = text;
        };
        _proto.hideLoading = function hideLoading() {
          var _document$getElementB;
          if (!sys.isNative) (_document$getElementB = document.getElementById('kitchen-loading')) == null || _document$getElementB.remove();
        };
        _proto.onDestroy = function onDestroy() {
          var _this$controlAccess;
          this.audio.destroy();
          (_this$controlAccess = this.controlAccess) == null || _this$controlAccess.remove();
          this.clearInput();
          game.off(Game.EVENT_HIDE, this.onHide, this);
          game.off(Game.EVENT_SHOW, this.onShow, this);
          if (!sys.isNative) {
            window.removeEventListener('kitchen-language-changed', this.onLanguage);
            window.removeEventListener('kitchen-confirmed', this.onConfirmed);
            window.removeEventListener('keydown', this.onKey, true);
            window.removeEventListener('keyup', this.onKeyUp, true);
            window.removeEventListener('mousedown', this.onMouseDown, true);
            window.removeEventListener('mouseup', this.onMouseUp, true);
            window.removeEventListener('blur', this.onBlur);
            document.removeEventListener('visibilitychange', this.onVisibility);
            document.removeEventListener('contextmenu', this.onContextMenu);
          }
        };
        _proto.onHide = function onHide() {
          var _this$state8;
          this.hidden = true;
          this.clearInput();
          if (((_this$state8 = this.state) == null ? void 0 : _this$state8.phase) === 'running') this.post('/api/pause', {
            reason: 'hidden'
          });
        };
        _proto.onShow = function onShow() {
          this.hidden = false;
          this.poll();
        };
        _proto.openRecord = function openRecord() {
          var _this$state9;
          if (!sys.isNative && (_this$state9 = this.state) != null && _this$state9.round_summary) window.dispatchEvent(new CustomEvent('kitchen-open-record', {
            detail: this.state.round_summary
          }));
        };
        _proto.openHelp = function openHelp() {
          this.clearInput();
          if (!sys.isNative) window.dispatchEvent(new Event('kitchen-open-help'));
        };
        _proto.openConnection = function openConnection() {
          this.clearInput();
          if (!sys.isNative) window.dispatchEvent(new Event('kitchen-open-connection'));
        };
        _proto.togglePause = function togglePause(e) {
          var _this$state10, _this$state11;
          if (((_this$state10 = this.state) == null ? void 0 : _this$state10.phase) === 'running') {
            e.preventDefault();
            this.clearInput();
            this.post('/api/pause');
          } else if (((_this$state11 = this.state) == null ? void 0 : _this$state11.phase) === 'paused' && this.connected) {
            e.preventDefault();
            this.post('/api/resume');
          }
        };
        _proto.setFocus = function setFocus(id) {
          var _this$controlAccess2, _this$controlAccess3;
          var old = this.focusId;
          this.focusId = id;
          this.styleButton(old);
          this.styleButton(id);
          var proxy = (_this$controlAccess2 = this.controlAccess) == null ? void 0 : _this$controlAccess2.querySelector("[data-control=\"" + id + "\"]");
          if (proxy && !proxy.hidden) proxy.focus({
            preventScroll: true
          });else if ((_this$controlAccess3 = this.controlAccess) != null && _this$controlAccess3.contains(document.activeElement)) document.activeElement.blur();
        }
        // Ending or abandoning a live round asks first; the round is paused meanwhile.
        ;

        _proto.confirm = /*#__PURE__*/
        function () {
          var _confirm = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee2(kind) {
            var _this$state12;
            var phase, resume;
            return _regeneratorRuntime().wrap(function _callee2$(_context2) {
              while (1) switch (_context2.prev = _context2.next) {
                case 0:
                  phase = (_this$state12 = this.state) == null ? void 0 : _this$state12.phase;
                  if (!(sys.isNative || kind === 'restart' && phase !== 'paused')) {
                    _context2.next = 4;
                    break;
                  }
                  this.post(kind === 'end' ? '/api/end' : '/api/restart');
                  return _context2.abrupt("return");
                case 4:
                  this.clearInput();
                  resume = phase === 'running';
                  if (!resume) {
                    _context2.next = 9;
                    break;
                  }
                  _context2.next = 9;
                  return this.post('/api/pause');
                case 9:
                  window.dispatchEvent(new CustomEvent('kitchen-confirm', {
                    detail: {
                      kind: kind,
                      resume: resume
                    }
                  }));
                case 10:
                case "end":
                  return _context2.stop();
              }
            }, _callee2, this);
          }));
          function confirm(_x2) {
            return _confirm.apply(this, arguments);
          }
          return confirm;
        }();
        _proto.announce = function announce(message) {
          if (!sys.isNative && message) window.dispatchEvent(new CustomEvent('kitchen-announce', {
            detail: {
              message: message
            }
          }));
        };
        // Anything held can be thrown or passed; the server applies each item's range (currently 4 tiles for all).
        _proto.sendMove = /*#__PURE__*/
        function () {
          var _sendMove = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee3(dx, dy, sprint) {
            var seq;
            return _regeneratorRuntime().wrap(function _callee3$(_context3) {
              while (1) switch (_context3.prev = _context3.next) {
                case 0:
                  if (sprint === void 0) {
                    sprint = false;
                  }
                  if (!(!this.state || this.state.phase !== 'running' || !this.connected)) {
                    _context3.next = 3;
                    break;
                  }
                  return _context3.abrupt("return");
                case 3:
                  seq = ++this.moveSeq;
                  this.lastMoveAt = this.clock;
                  _context3.prev = 5;
                  _context3.next = 8;
                  return this.request('/api/move', {
                    game_id: this.state.game_id,
                    dx: dx,
                    dy: dy,
                    seq: seq,
                    sprint: sprint
                  });
                case 8:
                  _context3.next = 13;
                  break;
                case 10:
                  _context3.prev = 10;
                  _context3.t0 = _context3["catch"](5);
                  this.set('event', _context3.t0.message);
                case 13:
                case "end":
                  return _context3.stop();
              }
            }, _callee3, this, [[5, 10]]);
          }));
          function sendMove(_x3, _x4, _x5) {
            return _sendMove.apply(this, arguments);
          }
          return sendMove;
        }();
        _proto.refreshMovement = function refreshMovement() {
          var x = (this.heldKeys.has('d') || this.heldKeys.has('arrowright') ? 1 : 0) - (this.heldKeys.has('a') || this.heldKeys.has('arrowleft') ? 1 : 0);
          var y = (this.heldKeys.has('s') || this.heldKeys.has('arrowdown') ? 1 : 0) - (this.heldKeys.has('w') || this.heldKeys.has('arrowup') ? 1 : 0),
            mag = Math.hypot(x, y);
          var dx = mag ? x / mag : 0,
            dy = mag ? y / mag : 0;
          if (dx === this.manualDirection.x && dy === this.manualDirection.y) return;
          this.manualDirection = {
            x: dx,
            y: dy
          };
          this.sendMove(dx, dy);
        };
        _proto.predictHuman = function predictHuman(k, c, dt, n) {
          var _c$sprint, _k$chefs$jeff;
          var d = this.manualDirection;
          if (!c.position) {
            this.predicted = this.releasedAt = null;
            return null;
          }
          if (this.clock < this.handsBusyUntil) {
            this.predicted = this.releasedAt = null;
            return null;
          }
          if (d.x === 0 && d.y === 0) {
            // Released: stay put until a state requested after the stop arrives, then ease onto it (no stale pull-back).
            if (this.predicted && this.releasedAt === null) this.releasedAt = this.clock;
            if (this.predicted && this.stateSentAt <= this.releasedAt && this.clock - this.releasedAt < .6) return this.predicted;
            this.predicted = this.releasedAt = null;
            return null;
          }
          this.releasedAt = null;
          var walk = (k.map.walk_speed || 4.5) * (((_c$sprint = c.sprint) == null ? void 0 : _c$sprint.active_remaining) > 0 ? 1.4 : 1),
            rate = walk * this.state.speed,
            other = (_k$chefs$jeff = k.chefs.jeff) == null ? void 0 : _k$chefs$jeff.position;
          // The server moves the chef in 50 ms game ticks (tick_game_ms); stepping the same distances from
          // the same rules keeps diagonal slides along counters on its path. Drawn between ticks.
          var tick = walk * .05,
            step = function step(p) {
              return predictWalk(k.map, p, d.x * tick, d.y * tick, other, tick);
            };
          var plan = this.walkPlan;
          if (!this.predicted || !plan || plan.dx !== d.x || plan.dy !== d.y) {
            var from = this.predicted || [(n.position.x + 640 - MAPX) / TILE - .5, (360 - MAPY - n.position.y) / TILE - .5];
            plan = this.walkPlan = {
              dx: d.x,
              dy: d.y,
              at: from,
              next: step(from),
              frac: 0
            };
          }
          plan.frac += dt * this.state.speed / .05;
          while (plan.frac >= 1) {
            plan.frac -= 1;
            plan.at = plan.next;
            plan.next = step(plan.at);
          }
          var next = [plan.at[0] + (plan.next[0] - plan.at[0]) * plan.frac, plan.at[1] + (plan.next[1] - plan.at[1]) * plan.frac];
          // Until the server reports this same direction it has not received the key yet: trust the prediction.
          // Afterwards ease toward its position carried forward to now; snap only on a large disagreement (e.g. a push).
          var heading = c.move_direction || [0, 0],
            synced = !!c.manual_moving && Math.abs(heading[0] - d.x) < 1e-6 && Math.abs(heading[1] - d.y) < 1e-6;
          var age = synced ? Math.min(.3, Math.max(0, this.clock - this.received)) : 0,
            server = predictWalk(k.map, c.position, d.x * rate * age, d.y * rate * age, other, tick);
          var ex = server[0] - next[0],
            ey = server[1] - next[1],
            pull = Math.min(1, dt * 4);
          if (Math.hypot(ex, ey) > 1.2) {
            next = server;
            this.walkPlan = {
              dx: d.x,
              dy: d.y,
              at: server,
              next: step(server),
              frac: 0
            };
          } else if (synced) {
            // Ease toward the server by shifting the whole tick plan, keeping its tick phase.
            var sx = ex * pull,
              sy = ey * pull,
              eased = [next[0] + sx, next[1] + sy];
            if (footWalkable(k.map, eased[0], eased[1])) {
              next = eased;
              plan.at = [plan.at[0] + sx, plan.at[1] + sy];
              plan.next = step(plan.at);
            }
          }
          return this.predicted = next;
        };
        _proto.clearInput = function clearInput() {
          this.heldKeys.clear();
          var wasMoving = this.manualDirection.x !== 0 || this.manualDirection.y !== 0;
          this.manualDirection = {
            x: 0,
            y: 0
          };
          if (wasMoving) this.sendMove(0, 0);
        };
        _proto.make = function make(name, x, y, w, h, parent) {
          if (parent === void 0) {
            parent = this.node;
          }
          var n = new Node(name);
          n.layer = Layers.Enum.UI_2D;
          parent.addChild(n);
          n.addComponent(UITransform).setContentSize(w, h);
          n.setPosition(x - 640, 360 - y);
          return n;
        };
        _proto.child = function child(parent, name, w, h, x, y) {
          if (x === void 0) {
            x = 0;
          }
          if (y === void 0) {
            y = 0;
          }
          var n = new Node(name);
          n.layer = Layers.Enum.UI_2D;
          parent.addChild(n);
          n.addComponent(UITransform).setContentSize(w, h);
          n.setPosition(x, y);
          return n;
        };
        _proto.rect = function rect(g, x, y, w, h, fill) {
          g.fillColor = color(fill);
          g.rect(x, y, w, h);
          g.fill();
        };
        _proto.pixel = function pixel(l, size) {
          l.fontFamily = PIXEL;
          l.fontSize = size;
          l.lineHeight = size + 4;
          l.isBold = false;
          return l;
        }
        // What Space or E would act on: a faint lift of that surface (Overcooked-style), no frame.
        ;

        _proto.facedGlow = function facedGlow(g, x, y, w, h) {
          g.fillColor = new Color(255, 250, 236, 70);
          g.rect(x, y, w, h);
          g.fill();
        };
        _proto.paintBox = function paintBox(n, w, h, fill) {
          var g = n.getComponent(Graphics) || n.addComponent(Graphics);
          g.clear();
          this.rect(g, -w / 2, -h / 2 - 3, w, h, COLORS.wood);
          this.rect(g, -w / 2, -h / 2, w, h, fill);
          return g;
        };
        _proto.box = function box(parent, name, x, y, w, h, fill) {
          var n = this.make(name, x, y, w, h, parent);
          this.paintBox(n, w, h, fill);
          return n;
        };
        _proto.text = function text(id, value, x, y, w, h, size, parent) {
          if (size === void 0) {
            size = 18;
          }
          if (parent === void 0) {
            parent = this.node;
          }
          var n = this.make(id, x + w / 2, y, w, h, parent);
          var l = n.addComponent(Label);
          this.writeLabel(l, value);
          l.fontSize = size;
          l.lineHeight = size + 6;
          l.color = color(COLORS.ink);
          l.fontFamily = 'sans-serif';
          l.horizontalAlign = Label.HorizontalAlign.LEFT;
          l.verticalAlign = Label.VerticalAlign.CENTER;
          l.overflow = Label.Overflow.SHRINK;
          this.labels[id] = l;
          return l;
        };
        _proto.button = function button(id, title, x, y, w, h, callback, parent, tone) {
          var _this3 = this;
          if (parent === void 0) {
            parent = this.node;
          }
          if (tone === void 0) {
            tone = 'normal';
          }
          var n = this.make('button-' + id, x, y, w, h, parent);
          var labelNode = new Node('label');
          labelNode.layer = Layers.Enum.UI_2D;
          n.addChild(labelNode);
          labelNode.addComponent(UITransform).setContentSize(w - 22, h - 6);
          var l = labelNode.addComponent(Label);
          this.writeLabel(l, title);
          this.pixel(l, 24);
          l.overflow = Label.Overflow.SHRINK;
          l.verticalAlign = Label.VerticalAlign.CENTER;
          this.buttons[id] = {
            node: n,
            label: l,
            callback: callback,
            enabled: true,
            width: w,
            height: h,
            tone: tone,
            hover: false
          };
          this.styleButton(id);
          n.on(Node.EventType.MOUSE_ENTER, function () {
            var b = _this3.buttons[id];
            if (b) {
              b.hover = true;
              _this3.styleButton(id);
            }
          });
          n.on(Node.EventType.MOUSE_LEAVE, function () {
            var b = _this3.buttons[id];
            if (b) {
              b.hover = false;
              _this3.styleButton(id);
            }
          });
          n.on(Node.EventType.TOUCH_END, function () {
            var b = _this3.buttons[id];
            if (b != null && b.enabled) {
              _this3.audio.play('ui_click');
              b.callback();
            } else if (b) _this3.audio.play('ui_blocked');
          });
          return n;
        };
        _proto.styleButton = function styleButton(id) {
          var b = this.buttons[id];
          if (!b) return;
          // Pressable: 2px ink border over a 3px ink shadow. Selected sits pressed-in on honey;
          // disabled goes flat on the surface so the two never look alike.
          var sel = !!b.selected,
            flat = sel || !b.enabled,
            dy = sel ? -3 : 0,
            w = b.width,
            h = b.height;
          var fill = sel ? COLORS.honey : !b.enabled ? COLORS.bg : b.tone === 'primary' ? b.hover ? COLORS.humanHover : COLORS.human : b.tone === 'danger' ? b.hover ? COLORS.hotHover : COLORS.hot : b.hover ? COLORS.honeyTint : COLORS.paper;
          var g = b.node.getComponent(Graphics) || b.node.addComponent(Graphics);
          g.clear();
          if (!flat) this.rect(g, -w / 2, -h / 2 - 3, w, h, COLORS.ink);
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
        };
        _proto.enable = function enable(id, enabled) {
          var b = this.buttons[id];
          if (!b) return;
          if (b.enabled !== enabled) {
            b.enabled = enabled;
            this.styleButton(id);
          }
        };
        _proto.writeLabel = function writeLabel(label, value) {
          var _kitchenI18n$t, _kitchenI18n;
          this.labelSources.set(label, value);
          label.string = !sys.isNative ? (_kitchenI18n$t = (_kitchenI18n = window.kitchenI18n) == null ? void 0 : _kitchenI18n.t(value)) != null ? _kitchenI18n$t : value : value;
        };
        _proto.set = function set(id, value) {
          if (this.labels[id]) this.writeLabel(this.labels[id], value);
        };
        _proto.icon = function icon(parent, name, x, y, type, scale) {
          if (scale === void 0) {
            scale = 1;
          }
          var n = this.make(name, x, y, 42, 42, parent);
          n.setScale(scale, scale, 1);
          var g = n.addComponent(Graphics);
          this.drawIcon(g, type);
          return n;
        };
        _proto.drawIcon = function drawIcon(g, type) {
          var _this4 = this;
          g.clear();
          if (this.useArt && this.artIcon(g.node, type)) return;
          this.art.hide(g.node);
          var r = function r(x, y, w, h, c) {
            return _this4.rect(g, x, y, w, h, c);
          };
          if (type.startsWith('vessel:')) {
            var _type$split = type.split(':'),
              item = _type$split[2],
              stage = _type$split[3];
            this.drawIcon(g, 'vessel');
            if (item) r(-10, -4, 20, 13, this.itemColor(item, stage));
          } else if (type === 'stove') {
            r(-23, -19, 46, 35, COLORS.wood);
            r(-20, -15, 40, 28, '#a3aaa0');
            r(-12, -6, 24, 16, COLORS.ink);
            r(-8, -3, 16, 10, '#6e746b');
          } else if (type === 'continuous_counter') ;else if (type.startsWith('source:')) {
            this.drawIcon(g, 'item:' + type.slice(7) + ':raw');
          } else if (type.startsWith('item:')) {
            var _type$split2 = type.split(':'),
              _item = _type$split2[1],
              _stage = _type$split2[2],
              c = this.itemColor(_item, _stage);
            if (this.cooks(_item)) {
              // Items that cook: a piece on a paper card; ingredients that don't: a plain shape.
              r(-19, -13, 38, 26, COLORS.paper);
              r(-14, -10, 28, 20, COLORS.ink);
              r(-13, -6, 26, 15, c);
              r(-9, 9, 18, 3, c);
              r(-6, -2, 4, 4, '#efd3ae');
              r(3, 3, 6, 3, '#efd3ae');
            } else {
              r(-18, -12, 36, 24, c);
              r(-12, 12, 24, 5, c);
              if (_stage === 'chopped') {
                r(-2, -12, 3, 27, COLORS.paper);
                r(-18, -1, 36, 3, COLORS.paper);
              }
            }
          } else if (type.startsWith('assembly:')) {
            this.drawIcon(g, 'clean_plate');
            var parts = type.slice(9).split(','),
              burnt = parts.includes('burnt');
            var y = -8;
            for (var _iterator4 = _createForOfIteratorHelperLoose(this.plateLayers(parts.filter(function (x) {
                return x !== 'burnt';
              }))), _step4; !(_step4 = _iterator4()).done;) {
              var layer = _step4.value;
              r(-13, y, 26, 5, this.itemColor(layer.item, burnt && this.burns(layer.item) ? 'burnt' : 'ready'));
              y += 5;
            }
          } else if (type === 'counter') {
            r(-24, -19, 48, 36, COLORS.wood);
            r(-20, -14, 40, 26, '#b48b5e');
            r(-24, 12, 48, 8, '#dfbd88');
            r(-2, -10, 3, 20, COLORS.wood);
          } else if (type.startsWith('dish:')) {
            var _this$dishById;
            var _type$split3 = type.split(':'),
              dish = _type$split3[1],
              _stage2 = _type$split3[2],
              _item2 = (_this$dishById = this.dishById(dish)) == null || (_this$dishById = _this$dishById.components) == null || (_this$dishById = _this$dishById[0]) == null ? void 0 : _this$dishById.item;
            r(-23, -17, 46, 7, '#829fac');
            r(-21, -14, 42, 30, COLORS.paper);
            r(-17, -11, 34, 24, '#c4dce0');
            r(-15, -9, 30, 20, COLORS.paper);
            r(-12, -5, 24, 15, this.itemColor(_item2, _stage2));
            r(-7, 3, 4, 3, '#d6af74');
          } else if (type === 'clean_plate' || type === 'dirty_plate' || type === 'plates' || type === 'returns') {
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
          } else if (type === 'sink') {
            r(-23, -18, 46, 36, '#718f95');
            r(-19, -13, 38, 26, '#bbd6d6');
            r(-15, -8, 30, 16, '#729ca8');
            r(8, 13, 5, 14, COLORS.ink);
            r(-4, 23, 16, 5, COLORS.ink);
            r(-5, 14, 5, 10, '#b9d6dc');
          } else if (type === 'vessel') {
            r(-18, -13, 36, 27, COLORS.ink);
            r(-14, -10, 28, 21, '#747e75');
            r(-21, 7, 42, 5, COLORS.ink);
            r(-24, 1, 7, 7, COLORS.ink);
            r(17, 1, 7, 7, COLORS.ink);
            r(-9, 15, 18, 4, '#aab7a4');
            r(-3, 19, 6, 4, COLORS.ink);
          } else if (type === 'board') {
            r(-21, -15, 42, 30, COLORS.wood);
            r(-18, -11, 36, 23, '#dcb16b');
            r(-13, -6, 20, 2, '#bd8849');
            r(-3, 2, 17, 7, '#e8e7dc');
            r(-13, 3, 10, 5, COLORS.ink);
          } else if (type === 'serve') {
            r(-23, -19, 46, 39, COLORS.wood);
            r(-19, -13, 38, 29, '#4e6654');
            r(-15, -4, 30, 5, COLORS.paper);
            r(-10, 1, 20, 5, COLORS.paper);
            r(-4, 9, 8, 3, '#e7b94c');
            r(-25, -20, 50, 7, '#c1965c');
          } else if (type === 'bin') {
            r(-14, -19, 28, 34, '#656b59');
            r(-18, 14, 36, 5, COLORS.ink);
            r(-6, 19, 12, 4, COLORS.ink);
            r(-8, -13, 3, 24, '#939c84');
            r(4, -13, 3, 24, '#939c84');
          } else if (type === 'extinguisher') {
            r(-10, -21, 20, 34, COLORS.hot);
            r(-7, -18, 14, 29, '#d6694a');
            r(-10, -1, 20, 10, COLORS.paper);
            r(-4, 13, 8, 9, COLORS.ink);
            r(4, 16, 13, 4, COLORS.ink);
            r(14, 3, 4, 16, COLORS.ink);
          } else if (type === 'fire') {
            r(-12, -18, 24, 27, '#c94d30');
            r(-6, 9, 12, 14, '#c94d30');
            r(-17, -10, 8, 17, '#c94d30');
            r(9, -10, 8, 14, '#c94d30');
            r(-8, -15, 16, 19, '#efae3e');
            r(-3, -13, 6, 12, '#ffe29a');
          } else {
            var _c = FOOD_COLORS[type] || FOOD_COLORS.raw;
            r(-19, -13, 38, 26, COLORS.paper);
            r(-14, -10, 28, 20, COLORS.ink);
            r(-13, -6, 26, 15, _c);
            r(-9, 9, 18, 3, _c);
            r(-6, -2, 4, 4, '#d6af74');
            r(3, 3, 6, 3, '#d6af74');
          }
        }
        // Recipe data from the server snapshot: names, colours, cooking states and plating order.
        ;

        _proto.itemDef = function itemDef(item) {
          var _this$state13;
          return item ? (_this$state13 = this.state) == null || (_this$state13 = _this$state13.kitchen.items) == null ? void 0 : _this$state13[item] : undefined;
        };
        _proto.itemLabel = function itemLabel(item) {
          var _this$itemDef;
          return ((_this$itemDef = this.itemDef(item)) == null ? void 0 : _this$itemDef.name) || item;
        };
        _proto.cooks = function cooks(item) {
          var _this$itemDef2;
          return !!((_this$itemDef2 = this.itemDef(item)) != null && (_this$itemDef2 = _this$itemDef2.states) != null && _this$itemDef2.includes('cooking'));
        };
        _proto.burns = function burns(item) {
          var _this$itemDef3;
          return !!((_this$itemDef3 = this.itemDef(item)) != null && (_this$itemDef3 = _this$itemDef3.states) != null && _this$itemDef3.includes('burnt'));
        }
        /** Fallback swatch (no art): burnt is charred, every other stage is the item's own colour. */;
        _proto.itemColor = function itemColor(item, stage) {
          var _this$itemDef4;
          if (stage === 'burnt') return FOOD_COLORS.burnt;
          return ((_this$itemDef4 = this.itemDef(item)) == null ? void 0 : _this$itemDef4.color) || FOOD_COLORS[stage] || FOOD_COLORS.ready;
        };
        _proto.dishById = function dishById(id) {
          var _this$state14, _this$state15;
          return id ? (((_this$state14 = this.state) == null ? void 0 : _this$state14.kitchen.dishes) || ((_this$state15 = this.state) == null ? void 0 : _this$state15.kitchen.menu) || []).find(function (d) {
            return d.id === id;
          }) : undefined;
        }
        /** The menu dish a plate is heading for: one whose components include every item on it. */;
        _proto.targetDish = function targetDish(components) {
          var _this$state16;
          return (((_this$state16 = this.state) == null ? void 0 : _this$state16.kitchen.menu) || []).find(function (d) {
            return components.every(function (x) {
              var _d$components;
              return (_d$components = d.components) == null ? void 0 : _d$components.some(function (c) {
                return c.item === x;
              });
            });
          });
        };
        _proto.plateLayers = function plateLayers$1(components) {
          var _this$targetDish;
          return plateLayers((_this$targetDish = this.targetDish(components)) == null ? void 0 : _this$targetDish.plating, components);
        }
        /** The item an ingredient source hands out (equipment data; the station id is the last resort). */;
        _proto.sourceItem = function sourceItem(id) {
          var _this$state17, _e$params;
          var e = (_this$state17 = this.state) == null ? void 0 : _this$state17.kitchen.map.equipment[id];
          return (e == null ? void 0 : e.item) || (e == null || (_e$params = e.params) == null ? void 0 : _e$params.item) || id;
        };
        _proto.artIcon = function artIcon(node, type) {
          var _this5 = this;
          for (var _iterator5 = _createForOfIteratorHelperLoose(node.children), _step5; !(_step5 = _iterator5()).done;) {
            var _child = _step5.value;
            if (_child.name === 'assembly-parts' || _child.name === 'supply-symbol' || _child.name === 'vessel-contents' || _child.name === 'burnt-cue') _child.active = false;
          }
          if (this.useModularArt) {
            if (type === 'bin') {
              this.art.hide(node);
              return true;
            }
            var tops = {
              board: 'top_board',
              sink: 'top_sink',
              stove: 'top_stove',
              returns: 'top_returns',
              serve: 'serving_window',
              bin: 'bin'
            };
            // The rack is a plain counter top; its extinguisher is drawn as the station's item while present.
            if (type === 'extinguisher_rack') {
              this.art.hide(node);
              return true;
            }
            if (type === 'serve') {
              var _this$state18;
              var facing = (_this$state18 = this.state) == null || (_this$state18 = _this$state18.kitchen.map.equipment.serve) == null ? void 0 : _this$state18.facing;
              return this.art.tile(node, facing === 'east' ? 'serving_east' : 'serving_west', TILE);
            }
            if (tops[type] && this.art.tile(node, tops[type], TILE)) return true;
            if (type.startsWith('source:')) {
              this.art.hide(node);
              var symbol = node.getChildByName('supply-symbol');
              if (!symbol) {
                symbol = this.child(node, 'supply-symbol', 40, 32, 0, 22 * TILE / 64);
                symbol.addComponent(Graphics);
              }
              symbol.active = true;
              var g = symbol.getComponent(Graphics);
              g.clear();
              var sourceKey = 'modular/source_' + type.slice(7);
              if (!this.art.centered(symbol, sourceKey, 28, 28)) {
                var fallback = symbol.getChildByName('fallback') || this.child(symbol, 'fallback', 28, 28);
                var fg = fallback.getComponent(Graphics) || fallback.addComponent(Graphics);
                fallback.setScale(.6, .6, 1);
                this.drawIcon(fg, 'item:' + type.slice(7) + ':raw');
              }
              return true;
            }
          }
          if (type.startsWith('item:')) {
            var _type$split4 = type.split(':'),
              item = _type$split4[1],
              stage = _type$split4[2],
              art = this.itemArt(item, stage, true);
            return !!art && this.art.centered(node, art.key, art.size, art.size);
          }
          if (type.startsWith('dish:')) {
            var _type$split5 = type.split(':'),
              dish = _type$split5[1],
              _stage3 = _type$split5[2];
            if (!this.art.has("dishes/" + dish + "/" + _stage3) || !this.art.centered(node, "dishes/" + dish + "/" + _stage3, TILE * .76, TILE * .76)) return false;
            if (_stage3 === 'burnt') this.burntCue(node);
            return true;
          }
          var assembly = type.startsWith('assembly:') ? type.slice(9).split(',') : null;
          if (assembly && this.plateLayers(assembly.filter(function (x) {
            return x !== 'burnt';
          })).every(function (l) {
            return _this5.art.has('feedback/' + l.layer);
          })) {
            this.art.centered(node, 'objects/clean_plate', TILE * .76, TILE * .76);
            var parts = node.getChildByName('assembly-parts');
            if (!parts) parts = this.child(node, 'assembly-parts', 44, 44);
            parts.active = true;
            for (var _iterator6 = _createForOfIteratorHelperLoose(parts.children), _step6; !(_step6 = _iterator6()).done;) {
              var child = _step6.value;
              child.active = false;
            }
            var burnt = assembly.includes('burnt');
            this.plateLayers(assembly.filter(function (x) {
              return x !== 'burnt';
            })).forEach(function (layer, i) {
              var _item$getChildByName;
              var item = parts.getChildByName(layer.layer) || _this5.child(parts, layer.layer, 36, 24);
              item.active = true;
              item.setPosition(0, -3 + i * 4);
              item.setSiblingIndex(parts.children.length - 1);
              _this5.art.centered(item, 'feedback/' + layer.layer, 34, 22);
              // No separate charred sprite: char the layers whose item can burn; reused nodes reset to white.
              var sprite = (_item$getChildByName = item.getChildByName('reviewed-art')) == null ? void 0 : _item$getChildByName.getComponent(Sprite);
              if (sprite) sprite.color = burnt && _this5.burns(layer.item) ? new Color(44, 36, 34, 255) : Color.WHITE;
            });
            if (burnt) this.burntCue(node);
            return true;
          }
          var keys = {
            board: 'workstations/board',
            stove: 'workstations/stove',
            sink: 'workstations/sink',
            serve: 'workstations/serve',
            returns: 'workstations/returns',
            bin: 'workstations/bin',
            extinguisher_rack: 'workstations/extinguisher_rack',
            extinguisher: 'objects/extinguisher',
            clean_plate: 'objects/clean_plate',
            dirty_plate: 'objects/dirty_plate',
            fire: 'vfx/fire_0'
          };
          if (type === 'continuous_counter') {
            this.art.hide(node);
            return true;
          }
          if (type.startsWith('vessel:')) {
            var _type$split6 = type.split(':'),
              kind = _type$split6[1],
              _item3 = _type$split6[2],
              _stage4 = _type$split6[3];
            if (!this.drawVessel(node, kind)) return false;
            var _contents = node.getChildByName('vessel-contents');
            if (!_contents) _contents = this.child(node, 'vessel-contents', 22, 22, 0, 4);
            var _art = _item3 ? this.itemArt(_item3, _stage4, false) : null;
            _contents.active = !!_art && this.art.centered(_contents, _art.key, 20, 20);
            return true;
          }
          var contents = node.getChildByName('vessel-contents');
          if (contents) contents.active = false;
          var key = keys[type];
          if (!key) return false;
          var size = key.startsWith('workstations/') ? 49 : key.startsWith('ingredients/') ? 29 : TILE * .76;
          if (!this.art.centered(node, key, size, size)) return false;
          return true;
        }
        /** Smoke over a burnt dish, wherever it is: upper layers can hide the charred layer. */;
        _proto.burntCue = function burntCue(node) {
          var _cue$getChildByName;
          var cue = node.getChildByName('burnt-cue');
          if (!cue) cue = this.child(node, 'burnt-cue', 26, 32, 14, 20);
          cue.active = this.art.show(cue, 'vfx/smoke_3', 26, 32);
          cue.setSiblingIndex(node.children.length - 1);
          var sprite = (_cue$getChildByName = cue.getChildByName('reviewed-art')) == null ? void 0 : _cue$getChildByName.getComponent(Sprite);
          if (sprite) sprite.color = new Color(120, 112, 106, 255);
        }
        /** Art for one item state: a chopped item that is plated chopped shows its plating layer
         * (when allowed), then food/<item>_<stage>, then ingredients/<item>/<stage> (chopped: prepared). */;
        _proto.itemArt = function itemArt(item, stage, layer) {
          var _this$itemDef5;
          if (layer && stage === 'chopped' && (_this$itemDef5 = this.itemDef(item)) != null && (_this$itemDef5 = _this$itemDef5.platable_states) != null && _this$itemDef5.includes('chopped') && this.art.has('feedback/' + item)) return {
            key: 'feedback/' + item,
            size: 30
          };
          if (this.art.has("food/" + item + "_" + stage)) return {
            key: "food/" + item + "_" + stage,
            size: 30
          };
          for (var _i10 = 0, _arr7 = ["ingredients/" + item + "/" + stage, "ingredients/" + item + "/" + (stage === 'chopped' ? 'prepared' : stage)]; _i10 < _arr7.length; _i10++) {
            var key = _arr7[_i10];
            if (this.art.has(key)) return {
              key: key,
              size: 29
            };
          }
          return null;
        }
        /** A vessel of the given kind (server data), turned along its station or the holder's facing. */;
        _proto.drawVessel = function drawVessel(node, kind, scale) {
          var _node$parent,
            _node$parent2,
            _node$parent$parent,
            _this$state19,
            _this6 = this;
          if (scale === void 0) {
            scale = 1;
          }
          var station = (_node$parent = node.parent) != null && _node$parent.name.startsWith('station-') ? node.parent.name.slice(8) : '';
          var holder = ((_node$parent2 = node.parent) == null ? void 0 : _node$parent2.name) === 'body' ? (_node$parent$parent = node.parent.parent) == null ? void 0 : _node$parent$parent.name : '';
          var facing = holder ? (_this$state19 = this.state) == null || (_this$state19 = _this$state19.kitchen.chefs[holder]) == null ? void 0 : _this$state19.facing : '';
          var axis = station ? stationView(this.state.kitchen.map, station).device_axis : facing === 'up' || facing === 'down' ? 'vertical' : 'horizontal';
          var stem = [kind, VESSEL_ART_FALLBACK].find(function (stem) {
            return !!stem && _this6.art.has("modular/" + stem + "_" + axis);
          });
          var key = stem ? "modular/" + stem + "_" + axis : this.art.has('objects/' + kind) ? 'objects/' + kind : 'objects/' + VESSEL_ART_FALLBACK;
          return this.art.centered(node, key, TILE * (axis === 'vertical' ? .62 : .76) * scale, TILE * .76 * scale);
        };
        _proto.closingSummary = function closingSummary(k, won) {
          var count = function count(status) {
              return k.orders.filter(function (o) {
                return o.status === status;
              }).length;
            },
            target = k.goals.target_money;
          // Each line ends in fixed text so its translation template cannot swallow the next line.
          return "\u51C0\u6536\u5165 \xA5" + k.money + "\uFF08\u76EE\u6807 \xA5" + target + "\uFF09" + (won ? '' : "\uFF0C\u8FD8\u5DEE \xA5" + Math.max(0, target - k.money) + " \u5143") + ("\n\u5B8C\u6210 " + k.served + " \u5355 \xB7 \u8D85\u65F6 " + count('expired') + " \u5355 \xB7 \u5173\u5E97\u65F6\u672A\u5B8C\u6210 " + count('unresolved_at_close') + " \u5355") + '\n本局已结束，点“准备下一局”再来一局。';
        };
        _proto.itemName = function itemName(f) {
          var _this7 = this;
          if (!f) return '空手';
          if (f.plate_id) {
            if (f.stage === 'burnt') return '糊菜';
            var dish = this.dishById(f.dish) || this.wholeDish(f);
            return dish ? dish.name : '待组装 · ' + this.plateItems(f).map(function (x) {
              return _this7.itemLabel(x);
            }).join('+');
          }
          return f.meaning || STAGES[f.stage] || f.stage;
        };
        _proto.plateItems = function plateItems(f) {
          var _f$components;
          return (_f$components = f.components) != null && _f$components.length ? f.components : f.ingredient ? [f.ingredient] : [];
        }
        /** A menu dish drawn as one plated sprite: no plating layers, and exactly the plate's items. */;
        _proto.wholeDish = function wholeDish(f) {
          var _this$state20;
          var items = Array.from(new Set(this.plateItems(f))).sort().join();
          return (((_this$state20 = this.state) == null ? void 0 : _this$state20.kitchen.menu) || []).find(function (d) {
            return !d.plating && Array.from(new Set((d.components || []).map(function (c) {
              return c.item;
            }))).sort().join() === items;
          });
        };
        _proto.itemStage = function itemStage(f) {
          var _f$contents;
          // Vessels (any kind) carry their contents; the kind comes from the server.
          if (f && (f.vessel || 'contents' in f)) return "vessel:" + (f.vessel || '') + ((_f$contents = f.contents) != null && _f$contents.ingredient ? ":" + f.contents.ingredient + ":" + f.contents.stage : '');
          if (f != null && f.plate_id && this.plateItems(f).length) {
            var whole = this.wholeDish(f);
            if (whole) return "dish:" + whole.id + ":" + f.stage;
            // Burnt plates keep their layers (burnt dishes can be served); items that burn are drawn charred.
            return 'assembly:' + this.plateItems(f).join(',') + (f.stage === 'burnt' ? ',burnt' : '');
          }
          if (f != null && f.ingredient) {
            var _this$state21;
            var chopping = this.useArt && f.stage === 'raw' && f.chop_remaining < (((_this$state21 = this.state) == null || (_this$state21 = _this$state21.rules) == null ? void 0 : _this$state21.chop_seconds) || 6) && this.art.has("ingredients/" + f.ingredient + "/processing");
            return "item:" + f.ingredient + ":" + (chopping ? 'processing' : f.stage);
          }
          return f == null ? void 0 : f.stage;
        };
        _proto.chef = function chef(parent, name, x, y, who, scale) {
          var _this8 = this;
          if (scale === void 0) {
            scale = 1;
          }
          var n = this.make(name, x, y, 40, 64, parent);
          n.setScale(scale, scale, 1);
          var shadow = this.child(n, 'contact-shadow', 40, 10, 0, -29),
            sg = shadow.addComponent(Graphics);
          if (this.useModularArt) shadow.setPosition(0, 0);
          var shade = new Color(65, 48, 31, 46);
          sg.fillColor = shade;
          sg.rect(-16, -3, 32, 6);
          sg.rect(-12, -5, 24, 10);
          sg.fill();
          var body = this.child(n, 'body', 40, 64),
            g = body.addComponent(Graphics);
          var r = function r(x, y, w, h, c) {
            return _this8.rect(g, x, y, w, h, c);
          };
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
          var eyes = this.child(body, 'eyes', 20, 8, 0, 19),
            eyeG = eyes.addComponent(Graphics);
          this.rect(eyeG, -7, -1, 3, 4, COLORS.ink);
          this.rect(eyeG, 4, -1, 3, 4, COLORS.ink);
          var profile = this.child(body, 'profile', 26, 24),
            profileG = profile.addComponent(Graphics);
          this.rect(profileG, -10, 10, 20, 18, '#e4b888');
          this.rect(profileG, 10, 15, 4, 7, '#e4b888');
          this.rect(profileG, 5, 18, 3, 4, COLORS.ink);
          profile.active = false;
          var back = this.child(body, 'back', 32, 40),
            backG = back.addComponent(Graphics);
          this.rect(backG, -10, 10, 20, 18, '#78624b');
          this.rect(backG, -10, -10, 20, 18, COLORS[who]);
          back.active = false;
          var limb = function limb(id, w, h, x, y, fill) {
            var node = _this8.child(body, id, w, h, x, y),
              lg = node.addComponent(Graphics);
            _this8.rect(lg, -w / 2, -h / 2, w, h, fill);
            return node;
          };
          var leftLeg = limb('left-leg', 8, 15, -7, -24, COLORS.ink),
            rightLeg = limb('right-leg', 8, 15, 7, -24, COLORS.ink);
          var leftArm = limb('left-arm', 6, 14, -19, -4, '#dbab7c'),
            rightArm = limb('right-arm', 6, 14, 19, -4, '#dbab7c');
          var knife = this.child(rightArm, 'knife', 14, 5, 9, -5),
            kg = knife.addComponent(Graphics);
          this.rect(kg, -1, -2, 11, 4, '#d8ded5');
          this.rect(kg, 9, -1, 4, 3, COLORS.ink);
          knife.active = false;
          return n;
        };
        _proto.request = /*#__PURE__*/function () {
          var _request = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee4(path, body) {
            var _this9 = this;
            var hosted;
            return _regeneratorRuntime().wrap(function _callee4$(_context4) {
              while (1) switch (_context4.prev = _context4.next) {
                case 0:
                  hosted = typeof window !== 'undefined' ? window.chefjeffHostedRequest : null;
                  if (!hosted) {
                    _context4.next = 3;
                    break;
                  }
                  return _context4.abrupt("return", hosted(path, body));
                case 3:
                  return _context4.abrupt("return", new Promise(function (resolve, reject) {
                    var xhr = new XMLHttpRequest();
                    xhr.open(body ? 'POST' : 'GET', _this9.endpoint + path, true);
                    xhr.timeout = 5000;
                    xhr.onload = function () {
                      try {
                        var data = JSON.parse(xhr.responseText);
                        xhr.status === 200 ? resolve(data) : reject(new Error(data.error || '操作失败'));
                      } catch (e) {
                        reject(new Error('厨房返回了无效数据'));
                      }
                    };
                    xhr.onerror = function () {
                      return reject(new Error('无法连接厨房后端'));
                    };
                    xhr.ontimeout = function () {
                      return reject(new Error('厨房连接超时'));
                    };
                    if (body) xhr.setRequestHeader('Content-Type', 'application/json');
                    xhr.send(body ? JSON.stringify(body) : null);
                  }));
                case 4:
                case "end":
                  return _context4.stop();
              }
            }, _callee4);
          }));
          function request(_x6, _x7) {
            return _request.apply(this, arguments);
          }
          return request;
        }();
        _proto.bookmark = /*#__PURE__*/function () {
          var _bookmark = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee5() {
            var _this10 = this;
            var round, notice, data;
            return _regeneratorRuntime().wrap(function _callee5$(_context5) {
              while (1) switch (_context5.prev = _context5.next) {
                case 0:
                  if (!(!this.state || this.hidden)) {
                    _context5.next = 2;
                    break;
                  }
                  return _context5.abrupt("return");
                case 2:
                  round = this.state.game_id;
                  notice = function notice(message) {
                    var _this10$state;
                    if (!sys.isNative && ((_this10$state = _this10.state) == null ? void 0 : _this10$state.game_id) === round) window.dispatchEvent(new CustomEvent('kitchen-bookmark-notice', {
                      detail: {
                        message: message
                      }
                    }));
                  };
                  if (this.connected) {
                    _context5.next = 7;
                    break;
                  }
                  notice('标记未保存，请重试。');
                  return _context5.abrupt("return");
                case 7:
                  _context5.prev = 7;
                  _context5.next = 10;
                  return this.request('/api/bookmark', {
                    game_id: round,
                    request_id: Date.now().toString(36) + '-' + Math.random().toString(36).slice(2)
                  });
                case 10:
                  data = _context5.sent;
                  notice(data.merged ? '已延长标记片段' : '已标记当前片段');
                  _context5.next = 17;
                  break;
                case 14:
                  _context5.prev = 14;
                  _context5.t0 = _context5["catch"](7);
                  notice('标记未确认，请检查导出记录。');
                case 17:
                case "end":
                  return _context5.stop();
              }
            }, _callee5, this, [[7, 14]]);
          }));
          function bookmark() {
            return _bookmark.apply(this, arguments);
          }
          return bookmark;
        }();
        _proto.post = /*#__PURE__*/function () {
          var _post = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee6(path, extra) {
            return _regeneratorRuntime().wrap(function _callee6$(_context6) {
              while (1) switch (_context6.prev = _context6.next) {
                case 0:
                  if (extra === void 0) {
                    extra = {};
                  }
                  if (path === '/api/action' || path === '/api/pause' || path === '/api/end' || path === '/api/reset' || path === '/api/restart') this.clearInput();
                  if (!(this.pending && path !== '/api/pause' || !this.state)) {
                    _context6.next = 4;
                    break;
                  }
                  return _context6.abrupt("return");
                case 4:
                  if (!(['/api/action', '/api/interact'].includes(path) && this.state.phase !== 'running')) {
                    _context6.next = 6;
                    break;
                  }
                  return _context6.abrupt("return");
                case 6:
                  this.pending = true;
                  this.render();
                  _context6.prev = 8;
                  _context6.next = 11;
                  return this.request(path, _extends({
                    game_id: this.state.game_id,
                    request_id: Date.now().toString(36) + '-' + Math.random().toString(36).slice(2)
                  }, extra));
                case 11:
                  _context6.next = 17;
                  break;
                case 13:
                  _context6.prev = 13;
                  _context6.t0 = _context6["catch"](8);
                  this.audio.play('ui_blocked');
                  this.set('event', _context6.t0.message);
                case 17:
                  _context6.prev = 17;
                  this.pending = false;
                  this.poll();
                  return _context6.finish(17);
                case 21:
                case "end":
                  return _context6.stop();
              }
            }, _callee6, this, [[8, 13, 17, 21]]);
          }));
          function post(_x8, _x9) {
            return _post.apply(this, arguments);
          }
          return post;
        }();
        _proto.act = function act(key) {
          var _this$state22;
          var a = (_this$state22 = this.state) == null ? void 0 : _this$state22.actions.find(function (a) {
            return a.key === key;
          });
          if (a) this.post('/api/action', {
            action: key,
            expected: a.expected
          });
        };
        _proto.modularWallDecor = function modularWallDecor(wallNode, x, y, hasSouth) {
          if (y !== 0 || hasSouth) return;
          var faceH = GRID_ART.northFace * TILE / GRID_ART.unit;
          for (var _iterator7 = _createForOfIteratorHelperLoose(((_kitchen$map$presenta = this.state.kitchen.map.presentation) == null ? void 0 : _kitchen$map$presenta.decorations) || []), _step7; !(_step7 = _iterator7()).done;) {
            var _kitchen$map$presenta;
            var decor = _step7.value;
            if (decor.cell[0] !== x) continue;
            var n = this.child(wallNode, 'wall-decor-' + decor.asset, TILE, TILE, 0, -TILE / 2 + faceH / 2);
            this.art.centered(n, 'modular/' + decor.asset, TILE * .65, faceH * .64);
          }
        };
        _proto.drawWall = function drawWall(n, x, y, map, walls) {
          var neighbours = wallNeighbours(walls, x, y);
          // One logical tile is one visible boundary tile. The north-facing wall
          // uses an inset cutaway face, rather than shifting other walls/counters.
          var cap = this.child(n, 'wall-top', TILE, TILE);
          this.art.centered(cap, 'modular/wall_cap', TILE, TILE);
          if (y === 0 && !neighbours.south) {
            var h = GRID_ART.northFace * TILE / GRID_ART.unit;
            var face = this.child(n, 'wall-front', TILE, h, 0, -TILE / 2 + h / 2);
            this.art.region(face, 'modular/wall_face', 0, 0, 64, GRID_ART.northFace, TILE, h);
          }
          var serve = map.equipment.serve;
          var boundary = serve && (serve.facing === 'west' ? map.width - 1 : serve.facing === 'east' ? 0 : -1);
          if (x === boundary && y === (serve == null ? void 0 : serve.cell[1])) {
            var slot = this.child(n, 'serving-aperture', TILE * .82, TILE * .42),
              g = slot.addComponent(Graphics);
            this.rect(g, -TILE * .41, -TILE * .21, TILE * .82, TILE * .42, '#344756');
            this.rect(g, -TILE * .36, -TILE * .15, TILE * .72, TILE * .30, '#75543a');
            this.rect(g, -TILE * .36, -TILE * .15, TILE * .72, 3, '#c99551');
          }
          this.modularWallDecor(n, x, y, neighbours.south);
        };
        _proto.cabinetArt = function cabinetArt(n, id) {
          var map = this.state.kitchen.map,
            axis = stationView(map, id).run_axis;
          var cabinet = this.child(n, 'cabinet-base', TILE, TILE);
          // One body per station. Runs reuse fixed-camera modules, never rotated sprites.
          var key = axis === 'horizontal' ? 'counter_south' : 'counter_east';
          this.art.tile(cabinet, key, TILE, 0, this.prepSampleBoard(id) ? 0 : -GRID_ART.cabinetSpriteLift * TILE / GRID_ART.unit);
          cabinet.setSiblingIndex(0);
        };
        _proto.prepSampleBoard = function prepSampleBoard(id) {
          return this.prepSample && this.state.kitchen.level === 2 && id === 'b1';
        };
        _proto.workSurfaceY = function workSurfaceY(id) {
          return this.prepSampleBoard(id) ? GRID_ART.cabinetSpriteLift * TILE / GRID_ART.unit : surfaceOffset();
        };
        _proto.equipmentArt = function equipmentArt(n, id) {
          var _kitchen$map$equipmen;
          var st = this.state.kitchen.stations[id],
            axis = stationView(this.state.kitchen.map, id).device_axis;
          var g = n.getComponent(Graphics);
          g.clear();
          this.art.hide(n);
          for (var _i11 = 0, _arr8 = ['supply-symbol', 'assembly-parts', 'vessel-contents']; _i11 < _arr8.length; _i11++) {
            var name = _arr8[_i11];
            var child = n.getChildByName(name);
            if (child) child.active = false;
          }
          n.setPosition(0, this.workSurfaceY(id));
          if (this.prepSampleBoard(id)) n.setPosition(0, this.workSurfaceY(id) + 11);
          if (id.startsWith('bin')) {
            var _view = trashView(this.state.kitchen.map, id);
            n.setScale(_view.mirror ? -1 : 1, 1, 1);
            this.art.centered(n, _view.axis === 'vertical' ? 'feedback/trash_opening_vertical' : 'feedback/trash_opening', TILE * .8, TILE * .8);
            return;
          }
          if (st.counter) return;
          if (id === 'serve') {
            // Neutral double chevron points from the chef into the serving boundary.
            var east = this.state.kitchen.map.equipment[id].facing === 'west',
              d = east ? 1 : -1;
            g.fillColor = color('#344756');
            for (var _i12 = 0, _arr9 = [-10, 5]; _i12 < _arr9.length; _i12++) {
              var x = _arr9[_i12];
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
          var kind = /^b[0-9]+$/.test(id) ? 'board' : id === 'returns' ? 'returns' : id === 'sink' ? 'sink' : '';
          if (kind) {
            this.art.centered(n, 'modular/device_' + kind + '_' + axis, TILE * .84, this.prepSampleBoard(id) ? 28 : TILE * .84);
            return;
          }
          if (st.stove) {
            this.art.centered(n, 'modular/top_stove', TILE * .82, TILE * .82);
            return;
          }
          if (((_kitchen$map$equipmen = this.state.kitchen.map.equipment[id]) == null ? void 0 : _kitchen$map$equipmen.type) === 'ingredient_source') {
            this.art.centered(n, 'modular/source_' + this.sourceItem(id), TILE * .6, TILE * .6);
            return;
          }
        };
        _proto.mountMap = function mountMap() {
          var _this11 = this;
          var previous = new Set(this.node.children);
          var map = this.state.kitchen.map,
            walls = new Set(map.walls.map(function (p) {
              return p.join(',');
            })),
            cells = new Set(Object.values(map.equipment).reduce(function (all, e) {
              return all.concat((e.cells || [e.cell]).map(function (c) {
                return c.join(',');
              }));
            }, []));
          var cabinetCells = new Set(Object.values(map.equipment).reduce(function (all, e) {
            return all.concat((e.cells || [e.cell]).map(function (c) {
              return c.join(',');
            }));
          }, []));
          if (this.useModularArt) {
            for (var y = 0; y < map.height; y++) for (var x = 0; x < map.width; x++) {
              if (walls.has(x + "," + y) && (x === 0 || y === 0 || x === map.width - 1 || y === map.height - 1)) continue;
              var floor = this.make('floor-art', MAPX + (x + .5) * TILE, MAPY + (y + .5) * TILE, TILE, TILE);
              this.art.centered(floor, "modular/floor_" + (x - 1 + 4) % 4 + "_" + (y - 1 + 4) % 4, TILE, TILE);
            }
          }
          this.depthEntries = [];
          this.world = this.child(this.node, 'kitchen-world', 1280, 720);
          var _loop3 = function _loop3(_y) {
            var _loop6 = function _loop6() {
              var wall = walls.has(_x11 + "," + _y),
                n = _this11.make('tile', MAPX + (_x11 + .5) * TILE, MAPY + (_y + .5) * TILE, TILE, TILE, _this11.world);
              n.setScale(TILE / 52, TILE / 52, 1);
              var g = n.addComponent(Graphics),
                r = function r(a, b, w, h, c) {
                  return _this11.rect(g, a, b, w, h, c);
                };
              if (wall) {
                r(-26, -26, 52, 52, COLORS.wood);
                r(-26, -15, 52, 41, COLORS.wall);
                r(-24, 5, 48, 17, '#c5a074');
                r(-24, -13, 23, 15, '#bb9062');
                r(2, -13, 22, 15, '#bb9062');
                r(-26, -24, 52, 7, '#634a37');
              } else {
                r(-26, -26, 52, 52, '#c7bea0');
                r(-25, -24, 49, 49, (_x11 + _y) % 2 ? _x11 < 7 ? '#e1d4ad' : '#cbd3b6' : _x11 < 7 ? '#eee3c1' : '#dce0c7');
                r(-23, 22, 45, 2, '#f1e7cc');
                if (cells.has(_x11 + "," + _y)) {
                  r(-26, -26, 52, 52, COLORS.counter);
                  if (!cells.has(_x11 + "," + (_y - 1))) r(-26, 22, 52, 4, COLORS.counterLight);
                  if (!cells.has(_x11 + "," + (_y + 1))) r(-26, -26, 52, 4, COLORS.counterEdge);
                }
              }
              if (_this11.useModularArt) {
                n.setScale(1, 1, 1);
                g.clear();
                if (wall) {
                  _this11.drawWall(n, _x11, _y, map, walls);
                  _this11.registerDepth(n, function () {
                    return depthOrder(_y, 'solid');
                  });
                }
              } else if (_this11.useArt) {
                var key = wall ? _y === 0 ? 'environment/wall' : 'environment/counter' : cells.has(_x11 + "," + _y) ? 'environment/counter' : 'environment/floor_cream';
                if (_this11.art.show(n, key, 52, 52)) {
                  g.clear();
                  if (wall && _y !== 0) {
                    var edge = _this11.child(n, 'wall-border', 52, 52),
                      _eg = edge.addComponent(Graphics);
                    _eg.strokeColor = color(COLORS.wood);
                    _eg.lineWidth = 3;
                    _eg.rect(-25, -25, 50, 50);
                    _eg.stroke();
                  }
                }
              }
              if (!wall) _this11.registerDepth(n, function () {
                return -1000;
              });
              if (wall && _this11.useModularArt) n.getComponent(UITransform).setAnchorPoint(.5, .5 - (_y === map.height - 1 ? GRID_ART.frontWallHeight / 64 : GRID_ART.wallHeight / 64));
            };
            for (var _x11 = 0; _x11 < map.width; _x11++) {
              _loop6();
            }
          };
          for (var _y = 0; _y < map.height; _y++) {
            _loop3(_y);
          }
          // Signs sit on the wall, leaving all walkable tiles visible.

          this.text('prep-sign', this.useModularArt ? '' : this.state.kitchen.level === 2 ? '长 台 厨 房' : '备 菜 区', MAPX + TILE, MAPY + 25, 295, 24, 14).horizontalAlign = Label.HorizontalAlign.CENTER;
          this.text('cook-sign', this.useModularArt ? '' : this.state.kitchen.level === 2 ? '' : '烹 饪 区', MAPX + 8 * TILE, MAPY + 25, 225, 24, 14).horizontalAlign = Label.HorizontalAlign.CENTER;
          var _loop4 = function _loop4() {
            var _Object$entries$_i = _Object$entries[_i13],
              id = _Object$entries$_i[0],
              entry = _Object$entries$_i[1];
            var e = entry,
              n = _this11.make('station-' + id, MAPX + (e.cell[0] + .5) * TILE, MAPY + (e.cell[1] + .5) * TILE, TILE, TILE, _this11.world);
            var overlay = _this11.child(n, 'surface-feedback', TILE, TILE),
              g = overlay.addComponent(Graphics);
            if (_this11.useModularArt) _this11.cabinetArt(n, id);
            _this11.registerDepth(n, function () {
              return depthOrder(e.cell[1], 'solid') + .01;
            });
            var art = new Node('equipment');
            art.layer = Layers.Enum.UI_2D;
            n.addChild(art);
            art.addComponent(UITransform).setContentSize(44, 44);
            art.setPosition(0, 6);
            if (_this11.useModularArt) art.setPosition(0, 0);
            _this11.drawIcon(art.addComponent(Graphics), _this11.state.kitchen.stations[id].counter ? 'continuous_counter' : _this11.state.kitchen.stations[id].stove ? 'vessel' : id.startsWith('bin') ? 'bin' : /^b[0-9]/.test(id) ? 'board' : e.type === 'ingredient_source' ? 'source:' + _this11.sourceItem(id) : _this11.useArt && id === 'extinguisher' ? 'extinguisher_rack' : id);
            if (_this11.useModularArt) _this11.equipmentArt(art, id);
            if (_this11.useModularArt) {
              var scorch = _this11.child(n, 'scorch', TILE, TILE);
              _this11.art.tile(scorch, 'scorch', TILE);
              scorch.active = false;
            }
            var ln = new Node('label');
            ln.layer = Layers.Enum.UI_2D;
            n.addChild(ln);
            ln.setPosition(0, -19);
            ln.addComponent(UITransform).setContentSize(56, 18);
            var l = ln.addComponent(Label);
            l.fontSize = 10;
            l.lineHeight = 13;
            l.isBold = true;
            l.color = color(COLORS.ink);
            l.overflow = Label.Overflow.SHRINK;
            var status = new Node('food');
            status.layer = Layers.Enum.UI_2D;
            n.addChild(status);
            status.addComponent(UITransform).setContentSize(30, 30);
            status.setPosition(11, 7);
            status.setScale(_this11.useModularArt ? 1 : .6, _this11.useModularArt ? 1 : .6, 1);
            status.addComponent(Graphics);
            if (_this11.useModularArt) {
              status.setPosition(0, _this11.workSurfaceY(id) + (_this11.prepSampleBoard(id) ? 18 : 0));
              if (_this11.prepSampleBoard(id)) status.setScale(.5, .5, 1);
              ln.active = false; // Workstations are identified by equipment, not map captions.
            }

            if (id === 'sink') {
              var bubbles = new Node('washing');
              bubbles.layer = Layers.Enum.UI_2D;
              n.addChild(bubbles);
              var bg = bubbles.addComponent(Graphics);
              _this11.rect(bg, -16, 0, 6, 6, '#eaf7f5');
              _this11.rect(bg, 0, 7, 7, 7, '#eaf7f5');
              _this11.rect(bg, 12, -2, 5, 5, '#eaf7f5');
              bubbles.active = false;
            }
            if (_this11.useModularArt) n.getComponent(UITransform).setAnchorPoint(.5, .5 - _this11.workSurfaceY(id) / TILE);
            _this11.devices[id] = {
              node: n,
              graphics: g,
              label: l
            };
            if (!_this11.state.kitchen.stations[id].stove) {
              var flame = _this11.child(n, 'cabinet-fire', 58, 64, 0, 18);
              flame.addComponent(Graphics);
              flame.active = false;
              _this11.cabinetFires[id] = flame;
              var smoke = _this11.child(flame, 'smoke', 36, 44, 8, 36);
              smoke.addComponent(Graphics);
            }
            if (_this11.state.kitchen.stations[id].stove) {
              var steam = _this11.child(n, 'cooking-steam', 32, 40, -11, 38),
                sg = steam.addComponent(Graphics);
              _this11.rect(sg, -2, -17, 4, 8, '#f6e8ca');
              _this11.rect(sg, -9, -7, 4, 8, '#f6e8ca');
              _this11.rect(sg, 7, 2, 4, 8, '#f6e8ca');
              _this11.rect(sg, -2, 13, 4, 8, '#f6e8ca');
              var _smoke = _this11.child(n, 'burnt-smoke', 36, 30, 13, 38),
                _bg = _smoke.addComponent(Graphics);
              _this11.rect(_bg, -12, -6, 9, 8, '#665e57');
              _this11.rect(_bg, -3, 1, 10, 8, '#504a45');
              _this11.rect(_bg, 5, 8, 8, 7, '#746b62');
              var fire = _this11.child(n, 'fire-flame', 32, 34, 0, 39),
                fg = fire.addComponent(Graphics);
              _this11.drawIcon(fg, 'fire');
              fire.setScale(.55, .55, 1);
              var ready = _this11.child(n, 'ready-pop', 76, 24, 0, 38),
                rg = ready.addComponent(Graphics);
              _this11.rect(rg, -35, -11, 70, 22, COLORS.honey);
              _this11.rect(rg, -32, -8, 64, 16, COLORS.paper);
              var cue = _this11.child(ready, 'cue', 70, 22).addComponent(Label);
              _this11.writeLabel(cue, '熟了！');
              _this11.pixel(cue, 12);
              cue.color = color(COLORS.ink);
              cue.horizontalAlign = Label.HorizontalAlign.CENTER;
              cue.verticalAlign = Label.VerticalAlign.CENTER;
              steam.active = false;
              _smoke.active = false;
              fire.active = false;
              ready.active = false;
              _this11.potEffects[id] = {
                steam: steam,
                smoke: _smoke,
                fire: fire,
                ready: ready
              };
            }
            overlay.setSiblingIndex(n.children.length - 1);
          };
          for (var _i13 = 0, _Object$entries = Object.entries(map.equipment); _i13 < _Object$entries.length; _i13++) {
            _loop4();
          }
          var _loop5 = function _loop5() {
            var who = _arr10[_i14];
            var n = _this11.chef(_this11.world, who, 0, 0, who, _this11.useModularArt ? .8 : .65);
            var dust = _this11.child(n, 'sprint-dust', 55, 28, -18, -24);
            dust.addComponent(Graphics);
            dust.active = false;
            dust.setSiblingIndex(0);
            _this11.locate(n, _this11.state.kitchen.chefs[who].position);
            _this11.registerDepth(n, function () {
              var c = _this11.state.kitchen.chefs[who],
                e = _this11.state.kitchen.map.equipment[c.target];
              return workingChefDepth((360 - MAPY - n.position.y) / TILE - .5, e == null ? void 0 : e.cell[1], c.facing, !!c.working && !!e);
            });
            // Name tag: a solid pixel plate in the identity colour, sized to the text in drawNameTag.
            var ln = _this11.child(n, 'name', 155, 25, 0, _this11.useModularArt ? -12 : -39);
            _this11.child(ln, 'tag', 40, 18).addComponent(Graphics);
            var l = _this11.pixel(_this11.child(ln, 'text', 40, 18).addComponent(Label), 12);
            delete _this11.tagText[who]; // new nodes after a layout change need their plate drawn
            l.overflow = Label.Overflow.NONE;
            _this11.labels['person-' + who] = l;
            var body = n.getChildByName('body'),
              held = _this11.child(body, 'held', 25, 25, 22, 0);
            held.setScale(.9, .9, 1);
            held.addComponent(Graphics);
            _this11.people[who] = n;
            // What the chef carries, above the head: readable from behind, where the hand is hidden.
            var bubble = _this11.child(n, 'held-bubble', 40, 38, 0, _this11.useModularArt ? 104 : 78),
              bg = bubble.addComponent(Graphics);
            _this11.rect(bg, -17, -13, 34, 30, COLORS.ink);
            _this11.rect(bg, -16, -10, 32, 26, COLORS.paper);
            _this11.rect(bg, -4, -17, 8, 5, COLORS.ink);
            _this11.rect(bg, -2, -15, 4, 4, COLORS.paper);
            var icon = _this11.child(bubble, 'icon', 42, 42, 0, 3);
            icon.setScale(.62, .62, 1);
            icon.addComponent(Graphics);
            bubble.active = false;
            if (_this11.prepSample) {
              var pose = _this11.child(_this11.world, 'prep-pose-' + who, 68, 88);
              pose.active = false;
              _this11.prepPoses[who] = pose;
              _this11.registerDepth(pose, function () {
                var _e$cell$;
                var c = _this11.state.kitchen.chefs[who],
                  e = _this11.state.kitchen.map.equipment[c.target];
                return depthOrder((_e$cell$ = e == null ? void 0 : e.cell[1]) != null ? _e$cell$ : c.position[1], 'solid') + .02;
              });
            }
            _this11.motions[who] = {
              body: body,
              leftLeg: body.getChildByName('left-leg'),
              rightLeg: body.getChildByName('right-leg'),
              leftArm: body.getChildByName('left-arm'),
              rightArm: body.getChildByName('right-arm'),
              knife: body.getChildByName('right-arm').getChildByName('knife'),
              facing: 'down',
              step: 0
            };
          };
          for (var _i14 = 0, _arr10 = ['human', 'jeff']; _i14 < _arr10.length; _i14++) {
            _loop5();
          }
          var marker = function marker(name, fill) {
            var n = _this11.child(_this11.people.jeff, name, 30, 18, 0, 65),
              g = n.addComponent(Graphics);
            g.fillColor = color(COLORS.paper);
            g.circle(0, 0, 8);
            g.fill();
            for (var _i15 = 0, _arr11 = [-5, 0, 5]; _i15 < _arr11.length; _i15++) {
              var _x10 = _arr11[_i15];
              _this11.rect(g, _x10 - 1, -1, 2, 3, fill);
            }
            return n;
          };
          this.jeffThinking = marker('jeff-thinking', COLORS.jeff);
          var error = this.child(this.people.jeff, 'jeff-api-error', 24, 23, 0, 66),
            eg = error.addComponent(Graphics);
          this.rect(eg, -9, -9, 18, 18, COLORS.hot);
          this.rect(eg, -2, -6, 4, 8, COLORS.paper);
          this.rect(eg, -2, 4, 4, 3, COLORS.paper);
          this.jeffError = error;
          this.jeffThinking.active = false;
          this.jeffError.active = false;
          this.mapNodes = this.node.children.filter(function (n) {
            return !previous.has(n);
          });
          this.mountedLayout = map.layout_version;
          this.sortWorld();
          this.refreshArtCharacters();
          this.drawIcon(this.cover.getChildByName('welcome-food').getComponent(Graphics), 'plated_ready');
          this.cover.setSiblingIndex(this.node.children.length - 1);
          for (var _i16 = 0, _arr12 = ['pause', 'resume', 'end']; _i16 < _arr12.length; _i16++) {
            var id = _arr12[_i16];
            this.buttons[id].node.setSiblingIndex(this.node.children.length - 1);
          }
          this.mounted = true;
        };
        _proto.characterArt = function characterArt(body, who, facing, walking, working) {
          var _this$state23, _this$state24, _URLSearchParams$get;
          if (walking === void 0) {
            walking = false;
          }
          if (working === void 0) {
            working = false;
          }
          var kind = who === 'human' ? 'player' : 'jeff',
            chef = (_this$state23 = this.state) == null ? void 0 : _this$state23.kitchen.chefs[who];
          var station = (_this$state24 = this.state) == null ? void 0 : _this$state24.kitchen.map.equipment[chef == null ? void 0 : chef.target];
          var inWorld = !!body.parent && ['human', 'jeff'].includes(body.parent.name);
          var chopping = !!working && inWorld && (chef == null ? void 0 : chef.action_kind) === 'chop' && !!station;
          var sampleFrame = this.prepSample ? Number((_URLSearchParams$get = new URLSearchParams(location.search).get('prepFrame')) != null ? _URLSearchParams$get : -1) : -1;
          var knifePilot = this.knifeSample && chopping && who === 'jeff' && facing === 'down' && this.state.kitchen.level === 2 && chef.target === 'b1';
          // Raise, swing, strike, recover: the chop frames move arms and knife together.
          var beat = ((this.activeClock / .4 + (who === 'human' ? 0 : .27)) % 1 + 1) % 1;
          var phase = knifePilot ? 1 : Number.isInteger(sampleFrame) && sampleFrame >= 0 && sampleFrame < 4 ? sampleFrame : beat < .3 ? 0 : beat < .45 ? 1 : beat < .75 ? 2 : 3;
          var actionKey = "characters/" + kind + "/" + facing + "/chop_" + phase;
          var hasAction = chopping && this.art.has(actionKey);
          var pilot = hasAction && who === 'jeff' && facing === 'down' && this.prepSampleBoard(chef.target) && this.art.has('prep/jeff/down/contact-body');
          var frame = walking ? "walk_" + Math.floor(this.activeClock * 12) % 8 : 'idle_0';
          // All poses share the actor's floor anchor and depth. An upper-body slice
          // is not a tool: painting it above the station puts the chef on the board.
          var key = pilot ? 'prep/jeff/down/contact-body' : hasAction ? actionKey : "characters/" + kind + "/" + facing + "/" + frame;
          var shown = this.useArt && this.art.show(body, key, 68, 88, 0, inWorld && this.useModularArt ? 0 : -29);
          if (who === 'jeff' && inWorld) this.knifeOnlySample(knifePilot, actionKey);
          var prep = this.prepPoses[who];
          if (inWorld && prep) {
            prep.active = !!pilot;
            if (pilot) {
              // Only the actual hands/blade overlap the surface; never paint feet above it.
              var actor = this.people[who];
              prep.setPosition(actor.position);
              prep.setScale(actor.scale);
              this.art.show(prep, 'prep/jeff/down/contact-tool', 68, 88);
            }
          }
          body.getComponent(Graphics).enabled = !shown;
          for (var _iterator8 = _createForOfIteratorHelperLoose(body.children), _step8; !(_step8 = _iterator8()).done;) {
            var child = _step8.value;
            if (!['held', 'reviewed-art'].includes(child.name)) child.active = !shown;
          }
          if (inWorld) this.chopImpact(who, hasAction && phase === 2 && beat < .62, (beat - .45) / .17);
          if (inWorld && chopping) this.knifeStrike(who, beat, .45);
          if (shown) {
            // Behind a waist-high counter the body sinks so the counter hides the legs; by
            // position only (never by action), so walking up and starting work look the same.
            var sink = inWorld && this.useModularArt ? behindCounter(this.state.kitchen.map, this.mapPoint(body.parent)) : 0;
            body.setScale(1, 1, 1);
            body.angle = 0;
            body.setPosition(0, -10 * sink);
            if (inWorld && this.useModularArt) {
              var _getChildByName, _getChildByName2;
              (_getChildByName = body.parent.getChildByName('contact-shadow')) == null || _getChildByName.setPosition(0, 0);
              (_getChildByName2 = body.parent.getChildByName('name')) == null || _getChildByName2.setPosition(0, -12);
            }
            var held = body.getChildByName('held');
            if (held) {
              held.setPosition(facing === 'left' ? -24 : facing === 'right' ? 24 : 0, (inWorld && this.useModularArt ? 29 : 0) + (facing === 'up' ? 8 : -5));
              held.setSiblingIndex(facing === 'up' ? 0 : body.children.length - 1);
            }
          } else {
            this.art.hide(body);
            for (var _i17 = 0, _arr13 = ['profile', 'back']; _i17 < _arr13.length; _i17++) {
              var name = _arr13[_i17];
              body.getChildByName(name).active = false;
            }
            body.getChildByName('right-arm').getChildByName('knife').active = false;
          }
          return shown;
        }
        /** Sound one knife strike when the swing phase passes the board-contact point. */;
        _proto.knifeStrike = function knifeStrike(who, t, contact) {
          var before = this.knifePhase[who];
          this.knifePhase[who] = t;
          if (before !== undefined && t >= contact && (before < contact || before > t)) this.audio.chop();
        }
        /** A short spark on the board while the knife lands (strike frame only). */;
        _proto.chopImpact = function chopImpact(who, active, p) {
          var _impact,
            _this12 = this;
          var impact = this.chopImpacts[who];
          if (!((_impact = impact) != null && _impact.isValid)) {
            if (!active) return;
            impact = this.child(this.world, 'knife-impact-' + who, 52, 52);
            impact.addComponent(Graphics);
            this.chopImpacts[who] = impact;
            this.registerDepth(impact, function () {
              var _kitchen$map$equipmen2, _kitchen$map$equipmen3;
              var c = _this12.state.kitchen.chefs[who];
              return depthOrder((_kitchen$map$equipmen2 = (_kitchen$map$equipmen3 = _this12.state.kitchen.map.equipment[c.target]) == null ? void 0 : _kitchen$map$equipmen3.cell[1]) != null ? _kitchen$map$equipmen2 : c.position[1], 'solid') + .04;
            });
          }
          impact.active = active;
          var g = impact.getComponent(Graphics);
          g.clear();
          if (!active) return;
          var target = this.state.kitchen.chefs[who].target;
          this.locate(impact, this.state.kitchen.map.equipment[target].cell);
          g.strokeColor = new Color(255, 246, 220, Math.round(255 * (1 - p)));
          g.lineWidth = 2;
          g.moveTo(-9 + 5 * p, -5);
          g.lineTo(7 + 5 * p, 7);
          g.stroke();
          g.lineWidth = 1;
          g.moveTo(-4, 8);
          g.lineTo(4, -7);
          g.stroke();
          for (var _i18 = 0, _arr14 = [[-1, 1], [1, 1], [-1, -1], [1, -1]]; _i18 < _arr14.length; _i18++) {
            var _arr14$_i = _arr14[_i18],
              dx = _arr14$_i[0],
              dy = _arr14$_i[1];
            var r = 6 + 7 * p;
            this.rect(g, dx * r, dy * r * .6, 2, 2, p < .6 ? '#fff1c9' : '#ddb471');
          }
        };
        _proto.knifeOnlySample = function knifeOnlySample(active, key) {
          var _this13 = this;
          if (this.knifeProbe) this.knifeProbe.active = active;
          if (this.cutProbe) this.cutProbe.active = active;
          if (!active) return;
          var params = new URLSearchParams(location.search);
          var length = Math.max(1, Math.min(4, Number(params.get('knifeScale') || 2.5) || 2.5));
          var handleLength = Math.max(1, Math.min(3, Number(params.get('knifeHandle') || 2) || 2));
          if (!this.knifeProbe) {
            var _root = this.child(this.world, 'knife-only-probe', 68, 88);
            // Separate length axes keep both thicknesses unchanged. Existing pixels only.
            var part = function part(name, pivot, points) {
              var stretch = _this13.child(_root, name, 68, 88);
              stretch.angle = -40;
              var stencil = _this13.child(stretch, name + '-mask', 68, 88);
              stencil.angle = 40;
              stencil.addComponent(Mask).type = Mask.Type.GRAPHICS_STENCIL;
              var g = stencil.getComponent(Graphics);
              g.clear();
              points.forEach(function (_ref2, i) {
                var x = _ref2[0],
                  y = _ref2[1];
                return i ? g.lineTo(x - pivot[0], pivot[1] - y) : g.moveTo(x - pivot[0], pivot[1] - y);
              });
              g.close();
              g.fill();
              _this13.art.show(stencil, key, 68, 88, 34 - pivot[0], pivot[1] - 82);
            };
            part('handle', [29, 61], [[29, 61], [31, 61], [34, 64], [31, 66], [29, 64]]);
            part('length', [31, 63], [[31, 63], [34, 64], [44, 72], [37, 73], [31, 69]]);
            this.knifeProbe = _root;
            this.registerDepth(_root, function () {
              return depthOrder(_this13.state.kitchen.map.equipment.b1.cell[1], 'solid') + .02;
            });
            var _fx = this.child(this.world, 'cut-impact-probe', 52, 52);
            _fx.addComponent(Graphics);
            this.cutProbe = _fx;
            this.registerDepth(_fx, function () {
              return depthOrder(_this13.state.kitchen.map.equipment.b1.cell[1], 'solid') + .03;
            });
          }
          var actor = this.people.jeff,
            root = this.knifeProbe;
          root.active = length > 1 || handleLength > 1;
          root.setScale(actor.scale);
          // Pivot remains at the original grip; neither the actor nor the board moves.
          root.setPosition(actor.position.x - 5 * actor.scale.x, actor.position.y + 21 * actor.scale.y);
          root.getChildByName('handle').setScale(handleLength, 1, 1);
          var blade = root.getChildByName('length');
          // Move blade base with the handle tip; never scale the grip/hand or whole actor.
          var a = -40 * Math.PI / 180,
            dx = 2,
            dy = -2,
            along = dx * Math.cos(a) + dy * Math.sin(a);
          blade.setPosition(dx + (handleLength - 1) * along * Math.cos(a), dy + (handleLength - 1) * along * Math.sin(a));
          blade.setScale(length, 1, 1);
          var fx = this.cutProbe,
            g = fx.getComponent(Graphics);
          g.clear();
          var impact = params.get('cutFx') === '1';
          var t = params.has('cutPhase') ? Math.max(0, Math.min(.999, Number(params.get('cutPhase')) || 0)) : this.activeClock * 3 % 1;
          fx.active = impact && t < .28;
          if (!fx.active) return;
          var cell = this.state.kitchen.map.equipment.b1.cell;
          this.locate(fx, cell);
          var p = t / .28;
          g.strokeColor = color('#fff3cf');
          g.lineWidth = 2;
          g.moveTo(-9 + 6 * p, -5);
          g.lineTo(5 + 6 * p, 6);
          g.stroke();
          g.strokeColor = color('#f4cf81');
          g.lineWidth = 1;
          for (var _i19 = 0, _arr15 = [[-1, 1], [1, 1], [-1, -1], [1, -1]]; _i19 < _arr15.length; _i19++) {
            var _arr15$_i = _arr15[_i19],
              _dx = _arr15$_i[0],
              _dy = _arr15$_i[1];
            var r = 5 + 7 * p;
            g.moveTo(_dx * r, _dy * r * .65);
            g.lineTo(_dx * (r + 2), _dy * (r + 2) * .65);
            g.stroke();
          }
        };
        _proto.refreshArtCharacters = function refreshArtCharacters() {
          for (var _i20 = 0, _arr16 = ['human', 'jeff']; _i20 < _arr16.length; _i20++) {
            var _this$cover$getChildB;
            var who = _arr16[_i20];
            if (this.useArt) this.characterArt(this.motions[who].body, who, this.state.kitchen.chefs[who].facing || 'down');
            var welcome = (_this$cover$getChildB = this.cover.getChildByName('welcome-' + who)) == null ? void 0 : _this$cover$getChildB.getChildByName('body');
            if (welcome) this.characterArt(welcome, who, 'down');
          }
        };
        _proto.foodNode = function foodNode(id, stage, airborne) {
          var _this14 = this;
          if (airborne === void 0) {
            airborne = false;
          }
          var n = this.make('food-' + id, 0, 0, 44, 40, this.world || this.node);
          n.setScale(.9, .9, 1);
          this.registerDepth(n, function () {
            var _this14$flightOrder$i;
            return airborne ? (_this14$flightOrder$i = _this14.flightOrder[id]) != null ? _this14$flightOrder$i : 0 : depthOrder((360 - MAPY - n.position.y) / TILE - .5, 'item');
          });
          this.drawIcon(n.addComponent(Graphics), stage);
          var child = new Node('id');
          child.layer = Layers.Enum.UI_2D;
          n.addChild(child);
          child.addComponent(UITransform).setContentSize(64, 19);
          child.setPosition(0, -23);
          var l = child.addComponent(Label);
          this.writeLabel(l, id);
          l.fontSize = 13;
          l.lineHeight = 16;
          l.color = color(COLORS.ink);
          child.active = !this.useModularArt;
          return n;
        };
        _proto.statColor = function statColor(id) {
          var f = this.flashes[id];
          if (f && f.until > this.clock) return f.fill;
          return COLORS.ink;
        }
        // New result events: a short pop where it happened, a header pulse, and a
        // screen-reader announcement. Events already present when a round loads stay quiet.
        ;

        _proto.processEvents = function processEvents() {
          var s = this.state,
            fresh = s.game_id !== this.eventsGame;
          if (fresh) {
            this.eventsGame = s.game_id;
            this.seenEvents.clear();
          }
          for (var _iterator9 = _createForOfIteratorHelperLoose(s.events), _step9; !(_step9 = _iterator9()).done;) {
            var e = _step9.value;
            var key = e.t + '|' + e.message;
            if (this.seenEvents.has(key)) continue;
            this.seenEvents.add(key);
            if (!fresh) this.feedback(e);
          }
          if (this.seenEvents.size > 300) this.seenEvents = new Set(s.events.map(function (e) {
            return e.t + '|' + e.message;
          }));
        };
        _proto.feedback = function feedback(e) {
          var _exec, _k$map$equipment$serv;
          var k = this.state.kitchen,
            amount = ((_exec = /(\d+) 元/.exec(e.message)) == null ? void 0 : _exec[1]) || '',
            serve = (_k$map$equipment$serv = k.map.equipment.serve) == null ? void 0 : _k$map$equipment$serv.cell;
          var at = function at(cell) {
            return cell ? [MAPX + (cell[0] + .5) * TILE, MAPY + (cell[1] - .1) * TILE] : [640, 150];
          };
          if (e.kind === 'served') {
            this.pop(at(serve), '+¥' + amount, COLORS.herb);
            this.flash(['served', 'money'], COLORS.herb);
          } else if (e.kind === 'expired') {
            var _exec2;
            this.pop([312, 180], (((_exec2 = /^(\S+?)超时/.exec(e.message)) == null ? void 0 : _exec2[1]) || '') + " \u8D85\u65F6 -\xA5" + amount, COLORS.alert);
            this.flash(['money'], COLORS.alert);
          } else if (e.kind === 'fire' || e.kind === 'fire_spread') this.flash(['money'], COLORS.alert);
          if (e.kind && RESULT_ANNOUNCE.has(e.kind)) this.announce(e.message);
        };
        _proto.flash = function flash(ids, fill) {
          for (var _iterator10 = _createForOfIteratorHelperLoose(ids), _step10; !(_step10 = _iterator10()).done;) {
            var id = _step10.value;
            this.flashes[id] = {
              until: this.clock + 1.2,
              fill: fill
            };
            this.labels[id].color = color(fill);
          }
        };
        _proto.pop = function pop(p, text, fill) {
          var n = this.make('result-pop', p[0], p[1], 220, 28),
            l = n.addComponent(Label);
          this.writeLabel(l, text);
          this.pixel(l, 24);
          l.horizontalAlign = Label.HorizontalAlign.CENTER;
          l.enableShadow = true;
          l.shadowColor = color(COLORS.ink);
          l.shadowOffset = new Vec2(2, -2);
          l.shadowBlur = 0;
          l.color = color(fill); // hard pixel shadow
          this.pops.push({
            node: n,
            label: l,
            born: this.clock,
            y: n.position.y,
            fill: color(fill)
          });
        };
        _proto.drawOrders = function drawOrders() {
          var _this15 = this;
          var s = this.state,
            k = s.kitchen,
            orders = k.orders.filter(function (o) {
              return o.status === 'pending';
            });
          // The goal is net revenue at closing.
          this.set('served', "" + k.served);
          this.set('money', "\xA5 " + k.money + " / " + k.goals.target_money);
          for (var _i21 = 0, _arr17 = ['served', 'money']; _i21 < _arr17.length; _i21++) {
            var id = _arr17[_i21];
            this.labels[id].color = color(this.statColor(id));
          }
          var _loop7 = function _loop7() {
            var _this15$dishById2;
            var o = orders[i],
              n = _this15.tickets[i],
              g = n.getComponent(Graphics) || n.addComponent(Graphics),
              urgent = o && o.remaining <= 15;
            g.clear();
            // Paper slip clipped to the walnut rail; empty clips stay bare instead of drawing blank slips.
            _this15.rect(g, -10, 26, 20, 6, COLORS.walnut);
            if (o || i === 0) {
              _this15.rect(g, -78, -36, 156, 62, COLORS.walnut);
              _this15.rect(g, -77, -34, 154, 59, COLORS.paper);
              if (o) {
                var _s$rules;
                // Patience: herb while comfortable, honey past half, hot red when urgent (the label also says so).
                var left = Math.max(0, Math.min(1, o.remaining / (o.patience || ((_s$rules = s.rules) == null ? void 0 : _s$rules.order_patience) || 90)));
                _this15.rect(g, -67, -30, 134, 7, COLORS.ink);
                _this15.rect(g, -66, -29, 132, 5, COLORS.bg);
                _this15.rect(g, -66, -29, 132 * left, 5, urgent ? COLORS.hot : left > .5 ? COLORS.herb : COLORS.honey);
              }
            }
            var signature = o ? JSON.stringify(o.ingredients || []) : '';
            if (_this15.orderArt[i] !== signature) {
              _this15.orderArt[i] = signature;
              var prev = n.getChildByName('ingredients');
              if (prev) prev.destroy();
              if (o) {
                var row = _this15.child(n, 'ingredients', 150, 16, 0, -5);
                var ingredients = o.ingredients || [];
                // Each item as the dish needs it, but whole: a chopped item reads better uncut at this size.
                var need = function need(name) {
                  var _this15$dishById;
                  var st = (_this15$dishById = _this15.dishById(o.dish)) == null || (_this15$dishById = _this15$dishById.components) == null || (_this15$dishById = _this15$dishById.find(function (c) {
                    return c.item === name;
                  })) == null ? void 0 : _this15$dishById.state;
                  return st && st !== 'chopped' ? st : 'raw';
                };
                ingredients.forEach(function (name, j) {
                  var item = _this15.child(row, 'ingredient-' + j, 30, 14, 66 - (ingredients.length - 1 - j) * 15, 0);
                  item.setScale(_this15.useArt ? .5 : .32, _this15.useArt ? .5 : .32, 1);
                  _this15.drawIcon(item.addComponent(Graphics), "item:" + name + ":" + need(name));
                });
              }
            }
            _this15.set('order-id-' + i, o ? o.id + " \xB7 " + (urgent ? '快超时了' : '待出餐') : i === 0 ? '订单夹' : '');
            _this15.labels['order-id-' + i].color = color(urgent ? COLORS.hot : COLORS.muted);
            _this15.set('order-name-' + i, o ? ((_this15$dishById2 = _this15.dishById(o.dish)) == null ? void 0 : _this15$dishById2.name) || o.dish : i === 0 ? k.future_orders ? '等待新订单' : '订单已结清' : '');
            _this15.set('order-time-' + i, o ? Math.max(0, Math.ceil(o.remaining)) + "s" : '');
            _this15.labels['order-time-' + i].color = color(urgent ? COLORS.hot : COLORS.muted);
          };
          for (var i = 0; i < 5; i++) {
            _loop7();
          }
        };
        _proto.drawNameTag = function drawNameTag(who) {
          var l = this.labels['person-' + who];
          if (this.tagText[who] === l.string) return;
          this.tagText[who] = l.string;
          l.updateRenderData(true);
          var w = Math.ceil(l.node.getComponent(UITransform).width) + 10,
            h = 18;
          var g = l.node.parent.getChildByName('tag').getComponent(Graphics);
          g.clear();
          // 1px ink border with a 2px hard ink shadow below, like the game's buttons.
          // You: denim plate, paper text. Jeff: paper plate (his white body), copper text.
          this.rect(g, -w / 2 - 1, -h / 2 - 3, w + 2, h + 4, COLORS.ink);
          this.rect(g, -w / 2, -h / 2, w, h, who === 'human' ? COLORS.human : COLORS.paper);
          l.color = color(who === 'human' ? COLORS.paper : COLORS.jeff);
        }
        /** Map cell coordinates of a world node (inverse of locate). */;
        _proto.mapPoint = function mapPoint(n) {
          return [(n.position.x + 640 - MAPX) / TILE - .5, (360 - MAPY - n.position.y) / TILE - .5];
        };
        _proto.locate = function locate(n, p, height) {
          if (height === void 0) {
            height = 0;
          }
          n.setPosition(MAPX + (p[0] + .5) * TILE - 640, 360 - MAPY - (p[1] + .5) * TILE + height);
        };
        _proto.render = function render() {
          var _k$fire_safety,
            _s$connection,
            _this16 = this,
            _s$limits,
            _kitchenI18n2;
          if (!this.state || !this.mounted) return;
          var s = this.state,
            k = s.kitchen,
            active = s.phase === 'running' && !this.pending && this.connected;
          var remaining = Math.max(0, Math.ceil(k.round_remaining));
          this.set('clock', String(Math.floor(remaining / 60)).padStart(2, '0') + ":" + String(remaining % 60).padStart(2, '0') + "  " + (s.phase === 'running' ? '营业中' : s.phase === 'ended' ? '已结算' : '休息中'));
          var sprint = k.chefs.human.sprint;
          this.set('sprint-status', !sprint ? '' : sprint.active_remaining > 0 ? '冲刺中' : sprint.cooldown_remaining > 0 ? '冲刺冷却 ' + Math.ceil(sprint.cooldown_remaining) + 's' : '冲刺 · Q');
          this.set('fire-status', (_k$fire_safety = k.fire_safety) != null && _k$fire_safety.burning_count ? "\u7740\u706B\u5DE5\u4F4D " + k.fire_safety.burning_count + "/" + k.fire_safety.loss_threshold : '');
          this.labels.clock.color = color(remaining <= 30 ? COLORS.hot : COLORS.muted);
          this.drawOrders();
          for (var _i22 = 0, _Object$entries2 = Object.entries(this.devices); _i22 < _Object$entries2.length; _i22++) {
            var _st$food, _s$interaction, _s$use_interaction, _kitchen$map$equipmen4, _st$food2, _st$food3, _s$rules2, _s$rules3;
            var _Object$entries2$_i = _Object$entries2[_i22],
              id = _Object$entries2$_i[0],
              dev = _Object$entries2$_i[1];
            var st = k.stations[id],
              g = dev.graphics;
            g.clear();
            var scorch = dev.node.getChildByName('scorch');
            if (scorch) scorch.active = !!st.scorched;
            var prior = this.foodStages[id];
            var foodKey = st.food ? st.food.id + ":" + st.food.stage : '';
            if (((_st$food = st.food) == null ? void 0 : _st$food.stage) === 'ready' && prior === st.food.id + ":cooking") this.readyUntil[id] = this.activeClock + 1.1;
            this.foodStages[id] = foodKey;
            if (st.fire && !this.useArt) {
              this.rect(g, -26, -26, 52, 52, '#f1b589');
            }
            if (((_s$interaction = s.interaction) == null ? void 0 : _s$interaction.target) === id || ((_s$use_interaction = s.use_interaction) == null ? void 0 : _s$use_interaction.target) === id) {
              if (this.useModularArt) this.facedGlow(g, -TILE / 2, this.workSurfaceY(id) - TILE / 2, TILE, TILE);else this.facedGlow(g, -27, -27, 54, 54);
            }
            this.writeLabel(dev.label, st.fire ? '着火了！' : st.food ? this.itemName(st.food) + (st.food.stage === 'cooking' ? " " + Math.ceil(st.ready_in) + "s" : st.food.stage === 'ready' && st.heating && st.burn_in !== undefined ? " " + Math.ceil(st.burn_in) + "s \u540E\u7CCA" : '') : ((_kitchen$map$equipmen4 = this.state.kitchen.map.equipment[id]) == null ? void 0 : _kitchen$map$equipmen4.type) === 'ingredient_source' && this.useModularArt ? this.itemLabel(this.sourceItem(id)) : st.name);
            var countdown = heatCountdown(st);
            var timer = dev.node.getChildByName('heat-countdown');
            if (countdown && !timer) {
              timer = this.child(dev.node, 'heat-countdown', 48, 15, 0, this.workSurfaceY(id) + TILE / 2 - 5);
              timer.addComponent(Graphics);
              var text = this.child(timer, 'time', 48, 15).addComponent(Label);
              this.pixel(text, 12);
              text.overflow = Label.Overflow.SHRINK;
            }
            if (timer) {
              timer.active = !!countdown;
              if (countdown) {
                timer.setSiblingIndex(dev.node.children.length - 1);
                var tg = timer.getComponent(Graphics);
                tg.clear();
                this.rect(tg, -24, -7.5, 48, 15, countdown.paused ? COLORS.steel : countdown.ready ? COLORS.hot : COLORS.walnut);
                var label = timer.getChildByName('time').getComponent(Label);
                label.color = color(COLORS.paper);
                this.writeLabel(label, "" + (countdown.paused ? 'Ⅱ ' : '') + countdown.seconds + "s " + (countdown.ready ? '糊' : '熟'));
              }
            }
            dev.label.color = color(st.fire || ((_st$food2 = st.food) == null ? void 0 : _st$food2.stage) === 'ready' || ((_st$food3 = st.food) == null ? void 0 : _st$food3.stage) === 'burnt' ? COLORS.hot : COLORS.ink);
            var food = dev.node.getChildByName('food');
            food.active = !!st.food || st.fire;
            if (food.active) this.drawIcon(food.getComponent(Graphics), st.fire ? 'fire' : this.itemStage(st.food));
            if (this.cabinetFires[id]) {
              this.cabinetFires[id].active = !!st.fire;
              if (st.fire) food.active = false;
            }
            if (st.counter && !st.fire) this.writeLabel(dev.label, st.food ? this.itemName(st.food) : s.interaction_focus !== id ? '' : '空柜台');
            if (st.stove) {
              if (this.useModularArt) this.equipmentArt(dev.node.getChildByName('equipment'), id);else this.drawIcon(dev.node.getChildByName('equipment').getComponent(Graphics), this.useArt ? 'stove' : st.vessel ? 'vessel:' + st.vessel : 'stove');
              if (this.useArt) {
                var vessel = dev.node.getChildByName('stove-vessel');
                if (!vessel) {
                  vessel = this.child(dev.node, 'stove-vessel', 34, 34, 0, this.useModularArt ? this.workSurfaceY(id) : 10);
                  vessel.setSiblingIndex(dev.node.getChildByName('equipment').getSiblingIndex() + 1);
                }
                vessel.active = !!(st.vessel || st.pot_id);
                if (vessel.active) this.drawVessel(vessel, st.vessel || '', .96);
                food.setPosition(0, this.useModularArt ? this.workSurfaceY(id) + 3 : 13);
                food.setScale(.58, .58, 1);
              }
            }
            if (id === 'returns') this.writeLabel(dev.label, st.food ? '脏盘待洗' : '脏盘回收');
            if (id === 'sink' && st.food) this.writeLabel(dev.label, st.food.stage === 'dirty_plate' ? "\u5F85\u6D17 " + Math.ceil(st.food.wash_remaining) + "s" : '洗好了');
            var progress = -1;
            if (id === 'sink' && st.food) progress = 1 - st.food.wash_remaining / k.tableware.wash_seconds;
            if (st.food && id.startsWith('b') && !id.startsWith('bin')) progress = 1 - st.food.chop_remaining / (((_s$rules2 = s.rules) == null ? void 0 : _s$rules2.chop_seconds) || 6);
            if (st.food && st.stove) progress = Math.min(1, st.food.heat_elapsed / (((_s$rules3 = s.rules) == null ? void 0 : _s$rules3.cook_seconds) || 12));
            if (progress >= 0) {
              var py = this.useModularArt ? this.workSurfaceY(id) - TILE / 2 + 3 : -18;
              this.rect(g, -23, py - 1, 46, 6, COLORS.ink);
              this.rect(g, -22, py, 44 * progress, 4, st.fire ? COLORS.hot : COLORS.paper);
            }
            var effects = this.potEffects[id];
            if (effects) {
              effects.steam.active = !!st.food && st.food.stage === 'cooking' && !!st.heating && !st.fire;
              effects.smoke.active = !!st.food && st.food.stage === 'burnt' && !!st.heating && !st.fire;
              effects.fire.active = !!st.fire;
              effects.ready.active = (this.readyUntil[id] || 0) > this.activeClock && !!st.food && st.food.stage === 'ready';
            }
          }
          var ids = new Set(k.ground.map(function (g) {
            return g.food.id;
          }));
          for (var _i23 = 0, _Object$entries3 = Object.entries(this.ground); _i23 < _Object$entries3.length; _i23++) {
            var _Object$entries3$_i = _Object$entries3[_i23],
              _id2 = _Object$entries3$_i[0],
              n = _Object$entries3$_i[1];
            if (!ids.has(_id2)) {
              n.destroy();
              delete this.ground[_id2];
              delete this.groundStages[_id2];
            }
          }
          for (var _iterator11 = _createForOfIteratorHelperLoose(k.ground), _step11; !(_step11 = _iterator11()).done;) {
            var item = _step11.value;
            var _id6 = item.food.id,
              stage = this.itemStage(item.food);
            if (!this.ground[_id6]) {
              this.ground[_id6] = this.foodNode(_id6, stage);
              this.groundStages[_id6] = stage;
            }
            if (this.groundStages[_id6] !== stage) {
              this.drawIcon(this.ground[_id6].getComponent(Graphics), stage);
              this.groundStages[_id6] = stage;
            }
            this.writeLabel(this.ground[_id6].getChildByName('id').getComponent(Label), this.itemName(item.food));
            this.locate(this.ground[_id6], item.position);
          }
          for (var _i24 = 0, _arr18 = ['human', 'jeff']; _i24 < _arr18.length; _i24++) {
            var _c$sprint2;
            var who = _arr18[_i24];
            var c = k.chefs[who];
            this.set('person-' + who, (who === 'human' ? '你' : 'Jeff') + (((_c$sprint2 = c.sprint) == null ? void 0 : _c$sprint2.active_remaining) > 0 ? ' »' : ''));
            this.drawNameTag(who);
            var _held = this.motions[who].body.getChildByName('held');
            _held.active = !!c.holding;
            if (c.holding) this.drawIcon(_held.getComponent(Graphics), this.itemStage(c.holding));
            var bubble = this.people[who].getChildByName('held-bubble');
            bubble.active = !!c.holding;
            if (c.holding) this.drawIcon(bubble.getChildByName('icon').getComponent(Graphics), this.itemStage(c.holding));
          }
          var apiConfigured = !!((_s$connection = s.connection) != null && _s$connection.configured) && s.phase !== 'ready' && s.phase !== 'ended';
          if (this.jeffThinking) this.jeffThinking.active = this.connected && apiConfigured && !!s.ai.thinking && !s.ai.error;
          if (this.jeffError) this.jeffError.active = apiConfigured && !!s.ai.error;
          var flightIds = new Set((k.projectiles || []).map(function (p) {
            return p.id;
          }));
          for (var _i25 = 0, _Object$entries4 = Object.entries(this.flights); _i25 < _Object$entries4.length; _i25++) {
            var _Object$entries4$_i = _Object$entries4[_i25],
              _id3 = _Object$entries4$_i[0],
              _n = _Object$entries4$_i[1];
            if (!flightIds.has(_id3)) {
              _n.destroy();
              delete this.flights[_id3];
              delete this.flightOrder[_id3];
            }
          }
          for (var _iterator12 = _createForOfIteratorHelperLoose(k.projectiles || []), _step12; !(_step12 = _iterator12()).done;) {
            var p = _step12.value;
            if (!this.flights[p.id]) this.flights[p.id] = this.foodNode(p.id, this.itemStage(p), true);
          }
          this.enable('pause', active);
          this.enable('resume', s.phase === 'paused' && !this.pending && this.connected);
          this.enable('end', ['running', 'paused'].includes(s.phase) && !this.pending && this.connected);
          for (var _i26 = 0, _arr19 = ['pause', 'resume', 'end']; _i26 < _arr19.length; _i26++) {
            var _id4 = _arr19[_i26];
            this.buttons[_id4].node.active = true;
          }
          var held = k.chefs.human.holding;
          this.set('hand', '手中：' + (held ? this.itemName(held) : '空手'));
          if ((held == null ? void 0 : held.stage) === 'assembled') this.set('hand', '缺少：' + held.missing.map(function (x) {
            return _this16.itemLabel(x);
          }).join('+'));
          {
            var _s$interaction2;
            var _short = function _short(a) {
                return a.label.split('（')[0];
              },
              parts = [];
            if (s.interaction) parts.push('空格 · ' + _short(s.interaction));
            if (s.use_interaction && s.use_interaction.key !== ((_s$interaction2 = s.interaction) == null ? void 0 : _s$interaction2.key)) parts.push('E · ' + (s.use_interaction.kind === 'throw' ? '向前抛出' : _short(s.use_interaction)));
            this.set('interaction', parts.length ? parts.join('　') : s.interaction_hint || '面向工位或物品按空格');
          }
          // Game results keep the event line; Jeff's decisions and errors use their own status.
          var results = s.events.filter(function (e) {
            return !_this16.isAiNote(e);
          });
          this.set('event', results.length ? results[results.length - 1].message : '');
          this.set('ai-status', this.aiStatus(s));
          this.labels['ai-status'].color = color(s.ai.error || (_s$limits = s.limits) != null && _s$limits.reached && s.phase === 'running' ? COLORS.alert : COLORS.muted);
          var _loop8 = function _loop8() {
            var _s$levels;
            var n = _arr20[_i27];
            var b = _this16.buttons['level' + n],
              sel = k.level === n;
            b.node.active = s.phase === 'ready' || s.phase === 'ended';
            _this16.writeLabel(b.label, (((_s$levels = s.levels) == null || (_s$levels = _s$levels.find(function (l) {
              return l.menu_order === n;
            })) == null ? void 0 : _s$levels.name) || '') + (sel ? ' · 当前' : ''));
            if (b.selected !== sel) {
              b.selected = sel;
              _this16.styleButton('level' + n);
            }
            _this16.enable('level' + n, !_this16.pending && !sel);
          };
          for (var _i27 = 0, _arr20 = [1, 2, 3]; _i27 < _arr20.length; _i27++) {
            _loop8();
          }
          var lang = ((_kitchenI18n2 = window.kitchenI18n) == null ? void 0 : _kitchenI18n2.language) === 'en' ? '中文' : 'English';
          if (this.buttons.language.label.string !== lang) this.buttons.language.label.string = lang;
          this.cover.active = s.phase !== 'running';
          this.buttons.reset.node.active = true;
          this.enable('main', !this.pending);
          this.buttons.main.node.active = true;
          this.enable('reset', !this.pending && s.phase !== 'ready');
          this.writeLabel(this.buttons.main.label, s.phase === 'ready' ? '开始经营' : s.phase === 'paused' ? '继续经营' : '准备下一局');
          if (s.phase === 'ready' && s.connection && !s.connection.configured) this.writeLabel(this.buttons.main.label, '先连接搭档');
          this.labels['welcome-tip'].node.active = s.phase === 'ready';
          this.buttons.record.node.active = s.phase === 'ended' && !!s.round_summary;
          // Shown once per round, as soon as its record exists; the button reopens it.
          if (s.phase === 'ended' && s.round_summary && this.recordShown !== s.game_id) {
            this.recordShown = s.game_id;
            this.openRecord();
          }
          // Rounds close at the time limit: say so plainly, whatever the outcome.
          var closed = s.phase === 'ended' && !s.aborted && k.failure_reason !== 'fire_spread';
          this.set('coverTitle', s.phase === 'ready' ? 'ChefJeff' : s.phase === 'paused' ? '歇一小会儿' : k.failure_reason === 'fire_spread' ? '火势失控' : s.aborted ? '本局已结束' : closed ? s.won ? '关店结算 · 达成目标' : '关店结算 · 未达目标' : s.won ? '今天，配合得不错！' : '明天再接再厉');
          this.set('coverText', s.phase === 'ready' ? "\u4F60\u548C AI \u642D\u6863\uFF0C\u4E00\u8D77\u7167\u987E\u8FD9\u95F4\u5C0F\u53A8\u623F\u3002\n\u672C\u5C40\u76EE\u6807\uFF1A\u5173\u5E97\u65F6\u51C0\u6536\u5165\u8FBE\u5230 \xA5" + k.goals.target_money : s.phase === 'paused' ? '锅火和订单都按下了暂停。\n准备好了，就和 Jeff 接着做菜。' : closed ? this.closingSummary(k, !!s.won) : "\u51FA\u9910 " + k.served + " \u5355 \xB7 \u51C0\u6536\u5165 \xA5" + k.money + " / \xA5" + k.goals.target_money);
          this.syncAccess();
          if (this.overlayPhase !== s.phase) {
            // Pause defaults to "Resume" so Enter, Space or Esc all return to the kitchen.
            var first = !this.overlayPhase;
            this.overlayPhase = s.phase;
            this.setFocus(s.phase === 'paused' ? 'main' : '');
            if (!first && s.phase !== 'running') this.announce(this.labelSources.get(this.labels.coverTitle) + '\n' + this.labelSources.get(this.labels.coverText));
          }
          if (s.ai.error && s.ai.error !== this.lastAiError) this.announce(s.ai.error);
          this.lastAiError = s.ai.error;
          this.cover.setSiblingIndex(this.node.children.length - 1);
          for (var _i28 = 0, _arr21 = ['pause', 'resume', 'end']; _i28 < _arr21.length; _i28++) {
            var _id5 = _arr21[_i28];
            this.buttons[_id5].node.setSiblingIndex(this.node.children.length - 1);
          }
        };
        _proto.isAiNote = function isAiNote(e) {
          return !e.kind && /^(Jeff |本局 AI)/.test(e.message);
        };
        _proto.aiStatus = function aiStatus(s) {
          var _s$limits2,
            _this17 = this;
          if ((_s$limits2 = s.limits) != null && _s$limits2.reached && s.phase === 'running') return 'Jeff 已达本局调用上限';
          if (s.ai.error) return 'Jeff 暂时连不上，正在重试';
          var note = [].concat(s.events).reverse().find(function (e) {
            return _this17.isAiNote(e);
          });
          var m = note && /^Jeff \u9009\u62E9\uFF1A([\s\S]*?) \| [\d.]+s(?: \| \u672A\u6267\u884C\uFF1A([\s\S]*))?$/.exec(note.message);
          if (m) return m[2] ? "Jeff\uFF1A" + m[1] + "\uFF08\u672A\u6267\u884C\uFF09" : "Jeff\uFF1A" + m[1]; // full reason stays in the event log/export
          return note != null && note.message.startsWith('Jeff 请求失败') ? 'Jeff 暂时连不上，正在重试' : '';
        }
        // Keeps the screen-reader proxies in step with the visible canvas buttons.
        ;

        _proto.syncAccess = function syncAccess() {
          if (!this.controlAccess) return;
          var icons = {
            pause: '暂停',
            resume: '继续经营',
            end: '结束本局'
          };
          for (var _i29 = 0, _TAB_ORDER2 = TAB_ORDER; _i29 < _TAB_ORDER2.length; _i29++) {
            var id = _TAB_ORDER2[_i29];
            var b = this.buttons[id],
              proxy = this.controlAccess.querySelector("[data-control=\"" + id + "\"]");
            if (!proxy) continue;
            var text = id === 'language' ? b.label.string : icons[id] || this.labelSources.get(b.label) || id;
            if (id === 'language') proxy.setAttribute('data-no-i18n', '');
            if (proxy.dataset.source !== text) {
              proxy.dataset.source = text;
              proxy.textContent = text;
            }
            proxy.disabled = !b.enabled;
            proxy.hidden = !b.node.activeInHierarchy;
          }
        };
        _proto.update = function update(dt) {
          var _this18 = this,
            _this$devices$sink;
          this.clock += dt;
          this.audio.update(dt);
          if (!this.state || !this.mounted) return;
          var k = this.state.kitchen;
          // Result pops rise and fade over 1.4s (no rise with reduced motion); header numbers pulse.
          this.pops = this.pops.filter(function (p) {
            var age = (_this18.clock - p.born) / 1.4;
            if (age >= 1 || !p.node.isValid) {
              p.node.destroy();
              return false;
            }
            if (!_this18.reduceMotion) p.node.setPosition(p.node.position.x, p.y + 34 * (1 - (1 - age) * (1 - age)));
            var a = Math.round(255 * (age < .6 ? 1 : 1 - (age - .6) / .4));
            p.label.color = new Color(p.fill.r, p.fill.g, p.fill.b, a);
            p.label.shadowColor = new Color(43, 26, 18, a);
            return true;
          });
          for (var _i30 = 0, _Object$entries5 = Object.entries(this.flashes); _i30 < _Object$entries5.length; _i30++) {
            var _Object$entries5$_i = _Object$entries5[_i30],
              id = _Object$entries5$_i[0],
              f = _Object$entries5$_i[1];
            var left = f.until - this.clock,
              n = this.labels[id].node;
            if (left <= 0) {
              delete this.flashes[id];
              n.setScale(1, 1, 1);
              this.labels[id].color = color(this.statColor(id));
              continue;
            }
            var s = this.reduceMotion ? 1 : 1 + .18 * Math.max(0, left - .9) / .3;
            n.setScale(s, s, 1);
          }
          var running = this.connected && !this.hidden && this.state.phase === 'running';
          var animate = running && !this.qaNoMotion;
          if (animate) this.activeClock += dt;
          for (var _i31 = 0, _arr22 = ['human', 'jeff']; _i31 < _arr22.length; _i31++) {
            var _c$sprint3;
            var who = _arr22[_i31];
            var c = k.chefs[who],
              p = c.position,
              _n2 = this.people[who],
              motion = this.motions[who];
            var dust = _n2.getChildByName('sprint-dust');
            dust.active = !!animate && ((_c$sprint3 = c.sprint) == null ? void 0 : _c$sprint3.active_remaining) > 0 && (c.manual_moving || c.travel_remaining > 0);
            if (dust.active) {
              var frame = Math.floor(this.activeClock * 10) % 7,
                g = dust.getComponent(Graphics);
              dust.setPosition(motion.facing === 'left' ? 22 : motion.facing === 'right' ? -22 : 0, this.useModularArt ? motion.facing === 'up' ? -12 : motion.facing === 'down' ? 12 : -2 : -25);
              if (this.useModularArt && this.art.centered(dust, "modular/sprint_dust_" + frame % 4, 32, 14)) g.clear();else if (this.useArt && this.art.show(dust, "vfx/landing_" + frame, 52, 28)) g.clear();else {
                g.clear();
                for (var i = 0; i < 3; i++) this.rect(g, -20 + i * 13, -3 + (frame + i) % 3 * 3, 7, 5, '#d8bf93');
              }
            }
            if (running && p) {
              var predicted = who === 'human' ? this.predictHuman(k, c, dt, _n2) : null,
                at = predicted || p;
              var x = MAPX + (at[0] + .5) * TILE - 640,
                y = 360 - MAPY - (at[1] + .5) * TILE,
                t = predicted ? 1 : Math.min(1, dt * 16);
              var oldX = _n2.position.x,
                oldY = _n2.position.y;
              _n2.setPosition(oldX + (x - oldX) * t, oldY + (y - oldY) * t);
              var dx = _n2.position.x - oldX,
                dy = _n2.position.y - oldY,
                moved = Math.hypot(dx, dy) > .08 && (!!predicted || (c.travel_remaining || 0) > 0 || Math.hypot(x - _n2.position.x, y - _n2.position.y) > 1);
              if (moved) {
                if ((c.manual_moving || predicted) && who === 'human' && (this.manualDirection.x !== 0 || this.manualDirection.y !== 0)) {
                  if (Math.abs(this.manualDirection.x) >= Math.abs(this.manualDirection.y)) motion.facing = this.manualDirection.x < 0 ? 'left' : 'right';else motion.facing = this.manualDirection.y < 0 ? 'up' : 'down';
                } else if (Math.abs(dx) >= Math.abs(dy)) motion.facing = dx < 0 ? 'left' : 'right';else motion.facing = dy > 0 ? 'up' : 'down';
              }
              // Authoritative orientation survives short actions between polls.
              if (!moved && c.facing) motion.facing = c.facing;
              if (c.working && c.facing) motion.facing = c.facing;
              var held = who === 'human' && (this.manualDirection.x !== 0 || this.manualDirection.y !== 0);
              var walkIntent = (predicted ? held : !!c.manual_moving) || !c.working && (c.travel_remaining || 0) > 0;
              if (this.characterArt(motion.body, who, motion.facing, animate && walkIntent, !!c.working)) continue;
              motion.body.angle = 0;
              var side = motion.facing === 'left' || motion.facing === 'right';
              motion.body.getChildByName('eyes').active = motion.facing !== 'up' && !side;
              motion.body.getChildByName('profile').active = side;
              motion.body.getChildByName('eyes').setPosition(side ? 4 : 0, 19);
              motion.body.getChildByName('eyes').setScale(side ? .65 : 1, 1, 1);
              motion.body.getChildByName('back').active = motion.facing === 'up';
              var facingScale = motion.facing === 'left' ? -.87 : motion.facing === 'right' ? .87 : 1;
              var walking = animate && walkIntent;
              var chopping = animate && !walking && c.action_kind === 'chop' && c.working && (c.work_remaining || 0) > .02;
              motion.knife.active = chopping;
              if (walking || chopping) {
                motion.step += dt * (chopping ? 13 : 16.5);
                var swing = Math.sin(motion.step);
                motion.leftLeg.setPosition(-7, walking ? -24 + Math.max(0, swing) * 3 : -24);
                motion.rightLeg.setPosition(7, walking ? -24 + Math.max(0, -swing) * 3 : -24);
                motion.leftArm.angle = walking ? -swing * 15 : 0;
                motion.rightArm.angle = chopping ? Math.sin(motion.step * 1.8) * 48 : walking ? swing * 15 : 0;
                if (chopping) this.knifeStrike(who, (motion.step * 1.8 / (2 * Math.PI) + .75) % 1, .5);
                motion.body.setPosition(0, walking ? Math.abs(swing) * 1.2 : 0);
                motion.body.setScale(facingScale, 1, 1);
              } else {
                motion.leftLeg.setPosition(-7, -24);
                motion.rightLeg.setPosition(7, -24);
                motion.leftArm.angle = 0;
                motion.rightArm.angle = 0;
                var breath = c.action_kind || !animate ? 0 : Math.sin(this.activeClock * 2.2);
                motion.body.setPosition(0, breath * .7);
                motion.body.setScale(facingScale, 1 + breath * .008, 1);
              }
            }
          }
          for (var _i32 = 0, _Object$values = Object.values(this.cabinetFires); _i32 < _Object$values.length; _i32++) {
            var flame = _Object$values[_i32];
            if (flame.active) {
              var _g = flame.getComponent(Graphics);
              if (this.useArt && this.art.show(flame, "vfx/fire_" + Math.floor(this.activeClock * 8) % 7, 58, 72)) _g.clear();else this.drawIcon(_g, 'fire');
              var smoke = flame.getChildByName('smoke');
              if (this.useArt) this.art.show(smoke, "vfx/smoke_" + Math.floor(this.activeClock * 6) % 7, 42, 42);
            }
          }
          if (animate) {
            var _this$jeffThinking;
            for (var _i33 = 0, _Object$entries6 = Object.entries(this.potEffects); _i33 < _Object$entries6.length; _i33++) {
              var _Object$entries6$_i = _Object$entries6[_i33],
                _id7 = _Object$entries6$_i[0],
                e = _Object$entries6$_i[1];
              if (this.useArt) {
                var _frame = Math.floor(this.activeClock * 8) % 7;
                for (var _i34 = 0, _arr23 = [[e.steam, 'steam'], [e.smoke, 'smoke'], [e.fire, 'fire']]; _i34 < _arr23.length; _i34++) {
                  var _node$getComponent;
                  var _arr23$_i = _arr23[_i34],
                    node = _arr23$_i[0],
                    key = _arr23$_i[1];
                  if (node.active && this.art.show(node, "vfx/" + key + "_" + _frame, key === 'fire' ? 75 : 42, key === 'fire' ? 75 : 42)) (_node$getComponent = node.getComponent(Graphics)) == null || _node$getComponent.clear();
                }
              }
              if (e.steam.active) e.steam.setPosition(-11 + Math.sin(this.activeClock * 3 + _id7.length) * 3, 38 + Math.sin(this.activeClock * 4 + _id7.length) * 3);
              if (e.smoke.active) e.smoke.setPosition(13 + Math.sin(this.activeClock * 2.4 + _id7.length) * 2, 38 + Math.sin(this.activeClock * 3 + _id7.length) * 2);
              if (e.fire.active) e.fire.setScale(.55 + Math.sin(this.activeClock * 12) * .035, .55 + Math.sin(this.activeClock * 12 + 1) * .06, 1);
              if (e.ready.active) e.ready.setScale(.85 + Math.sin(this.activeClock * 12) * .12, .85 + Math.sin(this.activeClock * 12) * .12, 1);
            }
            if ((_this$jeffThinking = this.jeffThinking) != null && _this$jeffThinking.active) this.jeffThinking.setScale(.92 + Math.sin(this.activeClock * 5) * .08, .92 + Math.sin(this.activeClock * 5) * .08, 1);
          }
          var sink = (_this$devices$sink = this.devices.sink) == null ? void 0 : _this$devices$sink.node.getChildByName('washing');
          if (sink) {
            var _sink$getComponent;
            var washing = Object.values(k.chefs).some(function (c) {
              return c.action_kind === 'wash' && c.working;
            });
            sink.active = washing;
            if (this.useArt && washing && this.art.show(sink, "vfx/splash_" + Math.floor(this.activeClock * 8) % 7, 38, 38)) (_sink$getComponent = sink.getComponent(Graphics)) == null || _sink$getComponent.clear();
            if (washing && this.state.phase === 'running' && this.connected && !this.hidden) {
              sink.setPosition(0, this.workSurfaceY('sink') + Math.sin(this.clock * 7) * 3);
              sink.setScale(1 + .12 * Math.sin(this.clock * 5), 1, 1);
            }
          }
          if (running && (this.manualDirection.x !== 0 || this.manualDirection.y !== 0) && this.clock - this.lastMoveAt >= .15) this.sendMove(this.manualDirection.x, this.manualDirection.y);
          var time = k.time + (this.state.phase === 'running' && this.connected ? (this.clock - this.received) * this.state.speed : 0);
          for (var _iterator13 = _createForOfIteratorHelperLoose(k.projectiles || []), _step13; !(_step13 = _iterator13()).done;) {
            var _p = _step13.value;
            var _t = Math.max(0, Math.min(1, (time - _p.started) / (_p.lands_at - _p.started))),
              arc = Math.sin(_t * Math.PI) * 35;
            var point = [_p.from[0] + (_p.to[0] - _p.from[0]) * _t, _p.from[1] + (_p.to[1] - _p.from[1]) * _t];
            // A board/counter landing ends on its work surface, drawn over the cabinet like a resting item.
            var onto = _p.onto && k.map.equipment[_p.onto] ? _p.onto : null,
              height = arc + (onto ? _t * this.workSurfaceY(onto) : 0);
            this.locate(this.flights[_p.id], point, height);
            this.flightOrder[_p.id] = onto && _t >= .5 ? Math.max(flightDepth(point[1], height), depthOrder(k.map.equipment[onto].cell[1], 'solid') + .02) : flightDepth(point[1], height);
          }
          this.sortWorld();
        };
        _createClass(KitchenClient, [{
          key: "useArt",
          get: function get() {
            return this.art.ready;
          }
        }, {
          key: "useModularArt",
          get: function get() {
            return this.useArt && this.art.modular;
          }
        }]);
        return KitchenClient;
      }(Component)) || _class));
      cclegacy._RF.pop();
    }
  };
});

System.register("chunks:///_virtual/KitchenGeometry.ts", ['cc'], function (exports) {
  var cclegacy;
  return {
    setters: [function (module) {
      cclegacy = module.cclegacy;
    }],
    execute: function () {
      exports({
        behindCounter: behindCounter,
        clearWalkLine: clearWalkLine,
        cornerOffset: cornerOffset,
        depthOrder: depthOrder,
        flightDepth: flightDepth,
        footWalkable: footWalkable,
        heatCountdown: heatCountdown,
        plateLayers: plateLayers,
        predictWalk: predictWalk,
        stationView: stationView,
        surfaceOffset: surfaceOffset,
        trashView: trashView,
        wallNeighbours: wallNeighbours,
        wallOffset: wallOffset,
        workingChefDepth: workingChefDepth
      });
      cclegacy._RF.push({}, "f232cZ06kxIVbuxNuyDHzfa", "KitchenGeometry", undefined);
      /** Pure rendering contract. Simulation positions, reach and collision stay in map data. */
      var GRID_ART = exports('GRID_ART', {
        tile: 52,
        originX: 276,
        originY: 170,
        unit: 64,
        counterHeight: 0,
        wallHeight: 0,
        frontWallHeight: 0,
        cabinetSpriteLift: 22,
        northFace: 44,
        floorRepeat: 4
      });
      function stationView(map, id) {
        var _map$presentation, _map$equipment$id;
        var authored = (_map$presentation = map.presentation) == null || (_map$presentation = _map$presentation.station_views) == null ? void 0 : _map$presentation[id];
        if (authored) return authored;
        // Compatibility for older maps: infer the cabinet run from neighbouring surfaces,
        // never from the chef's access side. Ambiguous isolated pieces default horizontal.
        var p = ((_map$equipment$id = map.equipment[id]) == null ? void 0 : _map$equipment$id.cell) || [0, 0],
          occupied = new Set(Object.values(map.equipment).reduce(function (all, e) {
            return all.concat((e.cells || [e.cell]).map(function (c) {
              return c.join(',');
            }));
          }, []));
        var h = Number(occupied.has(p[0] - 1 + "," + p[1])) + Number(occupied.has(p[0] + 1 + "," + p[1]));
        var v = Number(occupied.has(p[0] + "," + (p[1] - 1))) + Number(occupied.has(p[0] + "," + (p[1] + 1)));
        var axis = v > h ? 'vertical' : 'horizontal';
        return {
          run_axis: axis,
          device_axis: axis
        };
      }
      /** The long edge faces the authored service side, independent of cabinet run. */
      function trashView(map, id) {
        var e = map.equipment[id],
          dx = e.access[0] - e.cell[0],
          dy = e.access[1] - e.cell[1];
        var side = e.facing === 'west' || e.facing === 'east' || Math.abs(dx) > Math.abs(dy);
        return {
          axis: side ? 'vertical' : 'horizontal',
          mirror: side && dx > 0
        };
      }
      function wallNeighbours(walls, x, y) {
        return {
          north: walls.has(x + "," + (y - 1)),
          east: walls.has(x + 1 + "," + y),
          south: walls.has(x + "," + (y + 1)),
          west: walls.has(x - 1 + "," + y)
        };
      }
      /** Cell-aligned cutaway: tabletop and wall bounds share the logical grid.
       * Cabinet artwork has its own ground anchor offset; remove it at placement. */
      function surfaceOffset() {
        return GRID_ART.counterHeight * GRID_ART.tile / GRID_ART.unit;
      }
      function wallOffset() {
        return GRID_ART.wallHeight * GRID_ART.tile / GRID_ART.unit;
      }
      /** Stable painter ordering; larger southward feet/footprints cover northern objects.
       * A solid sorts by its north edge: feet at or behind that edge stay behind it, while
       * feet further south in its row can only stand beside it and draw in front. */
      function depthOrder(y, kind) {
        return y + (kind === 'solid' ? -.495 : kind === 'actor' ? 0 : -.12);
      }
      /** Station-working chefs stand outside the cabinet footprint; the cabinet must
       * not cover their face. North/back bodies retain ordinary grounded depth. */
      function workingChefDepth(y, row, facing, working) {
        if (working && row !== undefined && (facing === 'left' || facing === 'right')) return depthOrder(row, 'solid') + .015;
        return depthOrder(y, 'actor');
      }
      /** Airborne objects keep ground depth; elevation may clear a cabinet, never move behind it. */
      function flightDepth(groundRow, height) {
        return depthOrder(groundRow, 'item') + (height >= GRID_ART.tile * .22 ? .62 : 0);
      }
      /** Mirrors the server's foot test (navigation.walkable_point) using the map's walk boxes. */
      function footWalkable(map, x, y) {
        var _map$walk_clearance;
        var c = (_map$walk_clearance = map.walk_clearance) != null ? _map$walk_clearance : .2,
          e = 1e-9;
        if (!(x >= .5 + c - e && x <= map.width - 1.5 - c + e && y >= .5 + c - e && y <= map.height - 1.5 - c + e)) return false;
        return !(map.walk_boxes || []).some(function (b) {
          return b[0] + e < x && x < b[2] - e && b[1] + e < y && y < b[3] - e;
        });
      }
      var EPS = 1e-9;
      /** Mirrors navigation.clear_walk_line: a segment may touch walk boxes, never enter one. */
      function clearWalkLine(map, a, b) {
        if (!footWalkable(map, a[0], a[1]) || !footWalkable(map, b[0], b[1])) return false;
        var x0 = Math.min(a[0], b[0]),
          x1 = Math.max(a[0], b[0]),
          y0 = Math.min(a[1], b[1]),
          y1 = Math.max(a[1], b[1]);
        for (var _i = 0, _arr = map.walk_boxes || []; _i < _arr.length; _i++) {
          var _arr$_i = _arr[_i],
            left = _arr$_i[0],
            top = _arr$_i[1],
            right = _arr$_i[2],
            bottom = _arr$_i[3];
          if (left + EPS >= x1 || right - EPS <= x0 || top + EPS >= y1 || bottom - EPS <= y0) continue;
          var low = 0,
            high = 1;
          for (var _i2 = 0, _arr2 = [[0, left, right], [1, top, bottom]]; _i2 < _arr2.length; _i2++) {
            var _arr2$_i = _arr2[_i2],
              axis = _arr2$_i[0],
              lower = _arr2$_i[1],
              upper = _arr2$_i[2];
            var d = b[axis] - a[axis],
              lo = lower + EPS,
              hi = upper - EPS;
            if (Math.abs(d) < EPS) {
              if (!(lo < a[axis] && a[axis] < hi)) {
                low = 1;
                high = 0;
                break;
              }
            } else {
              var p = (lo - a[axis]) / d,
                q = (hi - a[axis]) / d;
              low = Math.max(low, Math.min(p, q));
              high = Math.min(high, Math.max(p, q));
            }
          }
          if (low <= high) return false;
        }
        return true;
      }
      /** Mirrors SpatialKitchen._wall_limited: as far along the segment as the walk boxes allow. */
      function wallLimited(map, a, b) {
        if (clearWalkLine(map, a, b)) return b;
        var low = 0,
          high = 1;
        for (var i = 0; i < 16; i++) {
          var mid = (low + high) / 2;
          if (clearWalkLine(map, a, [a[0] + (b[0] - a[0]) * mid, a[1] + (b[1] - a[1]) * mid])) low = mid;else high = mid;
        }
        return [a[0] + (b[0] - a[0]) * low, a[1] + (b[1] - a[1]) * low];
      }
      /** Mirrors navigation.contact_fraction: how far a step goes before touching a chef's disc. */
      function contactFraction(a, b, c, r) {
        var dx = b[0] - a[0],
          dy = b[1] - a[1],
          ox = a[0] - c[0],
          oy = a[1] - c[1],
          aa = dx * dx + dy * dy;
        if (aa < EPS * EPS) return 1;
        var bb = ox * dx + oy * dy,
          cc = ox * ox + oy * oy - r * r;
        if (cc < -EPS) return bb >= -EPS ? 1 : 0;
        if (bb >= 0) return 1;
        var disc = bb * bb - aa * cc;
        if (disc <= EPS * aa) return 1;
        return Math.max(0, Math.min(1, (-bb - Math.sqrt(disc)) / aa));
      }
      /** Sideways shift (signed cells) and its axis that lets a blocked single-direction step
       * continue: the server's corner_offset, within map.corner_slide. */
      function cornerOffset(map, p, v) {
        var limit = map.corner_slide;
        var axis = v[0] && !v[1] ? 0 : v[1] && !v[0] ? 1 : -1;
        if (!limit || axis < 0) return null;
        var side = 1 - axis;
        for (var n = 1; n <= Math.round(limit / .01); n++) for (var _i3 = 0, _arr3 = [-1, 1]; _i3 < _arr3.length; _i3++) {
          var sign = _arr3[_i3];
          var shifted = [p[0], p[1]];
          shifted[side] += sign * n * .01;
          var ahead = [shifted[0], shifted[1]];
          ahead[axis] += v[axis] * .05;
          if (clearWalkLine(map, p, shifted) && clearWalkLine(map, shifted, ahead)) return [sign * n * .01, side];
        }
        return null;
      }
      /** One server tick of a held-key walk (SpatialKitchen._after_step): straight when the whole
       * line is clear, otherwise each axis in turn up to the blocking edge, then any distance left
       * slides out of a shallow notch. The teammate is a disc the step stops at (the server may also
       * slide or push; the eased server position corrects that). */
      function walkTick(map, from, v, distance, other) {
        var _map$chef_separation;
        var sep = (_map$chef_separation = map.chef_separation) != null ? _map$chef_separation : .4;
        var move = function move(a, b) {
          if (other && Math.hypot(b[0] - a[0], b[1] - a[1]) > EPS) {
            var f = contactFraction(a, b, other, sep);
            if (f < 1 - 1e-8) b = [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
          }
          return wallLimited(map, a, b);
        };
        var p = from;
        var end = [from[0] + v[0] * distance, from[1] + v[1] * distance];
        if (clearWalkLine(map, p, end)) p = move(p, end);else for (var _i4 = 0, _arr4 = [0, 1]; _i4 < _arr4.length; _i4++) {
          var axis = _arr4[_i4];
          if (!v[axis]) continue;
          var c = [p[0], p[1]];
          c[axis] += v[axis] * distance;
          p = move(p, c);
        }
        var remaining = distance * Math.hypot(v[0], v[1]) - Math.hypot(p[0] - from[0], p[1] - from[1]);
        if (map.corner_slide && remaining > 1e-9) {
          var found = cornerOffset(map, p, v);
          if (found) {
            var offset = found[0],
              side = found[1],
              before = p,
              target = [p[0], p[1]];
            target[side] += Math.sign(offset) * Math.min(Math.abs(offset), remaining);
            p = move(p, target);
            var slid = Math.hypot(p[0] - before[0], p[1] - before[1]),
              left = remaining - slid;
            if (slid > 1e-9 && left > 1e-9) {
              var ahead = [p[0] + v[0] * left, p[1] + v[1] * left];
              if (clearWalkLine(map, p, ahead)) p = move(p, ahead);
            }
          }
        }
        return p;
      }
      /** Local prediction of a held-key walk (dx, dy in cells), computed in the server's own steps:
       * `tick` is the distance one 50 ms game tick covers at the current speed. Same geometry, same
       * step size, so diagonal slides along counters land where the server's do. */
      function predictWalk(map, from, dx, dy, other, tick) {
        if (tick === void 0) {
          var _map$walk_speed;
          tick = ((_map$walk_speed = map.walk_speed) != null ? _map$walk_speed : 4.5) * .05;
        }
        var total = Math.hypot(dx, dy);
        if (total < 1e-12) return [from[0], from[1]];
        var v = [dx / total, dy / total];
        var p = [from[0], from[1]],
          left = total;
        while (left > 1e-12) {
          var d = Math.min(tick, left);
          p = walkTick(map, p, v, d, other);
          left -= d;
        }
        return p;
      }
      /** 0..1: how far a foot at (x, y) stands right behind a cabinet whose top edge is south of
       * it. Full within 0.2 cells of the edge (every north stand point and walk limit), fading out
       * by 0.45 away or 0.35 past the cabinet's side, so walking along a counter never jumps. */
      function behindCounter(map, p) {
        var best = 0;
        for (var _i5 = 0, _arr5 = Object.values(map.equipment || {}); _i5 < _arr5.length; _i5++) {
          var e = _arr5[_i5];
          for (var _i6 = 0, _arr6 = e.cells || [e.cell]; _i6 < _arr6.length; _i6++) {
            var c = _arr6[_i6];
            var d = c[1] - .5 - p[1];
            if (d < -.02 || d > .45) continue;
            var along = d <= .2 + 1e-9 ? 1 : (.45 - d) / .25,
              side = Math.max(0, Math.abs(p[0] - c[0]) - .5);
            best = Math.max(best, along * Math.max(0, 1 - side / .35));
          }
        }
        return best;
      }
      /** A plate's layers from bottom to top: the dish's plating (server recipe data), keeping the layers
       * whose item is on the plate, independent of the order items reached it. Without a plating the
       * components are stacked as they are. */
      function plateLayers(plating, components) {
        var present = new Set(components);
        if (plating != null && plating.length) return plating.filter(function (layer) {
          return present.has(layer.item);
        });
        return Array.from(present).map(function (item) {
          return {
            layer: item,
            item: item
          };
        });
      }
      function heatCountdown(st) {
        if (!st.stove || !st.food || st.fire) return null;
        var ready = st.food.stage === 'ready',
          cooking = ['chopped', 'cooking'].includes(st.food.stage);
        if (!ready && !cooking) return null;
        var seconds = ready ? st.burn_in : st.ready_in;
        if (!Number.isFinite(seconds)) return null;
        return {
          seconds: Math.max(0, Math.ceil(seconds)),
          ready: ready,
          paused: !st.heating
        };
      }
      cclegacy._RF.pop();
    }
  };
});

System.register("chunks:///_virtual/LevelOneArt.ts", ['./rollupPluginModLoBabelHelpers.js', 'cc'], function (exports) {
  var _asyncToGenerator, _regeneratorRuntime, cclegacy, UITransform, SpriteFrame, Rect, Size, Sprite, Node, Layers, Texture2D, resources, JsonAsset;
  return {
    setters: [function (module) {
      _asyncToGenerator = module.asyncToGenerator;
      _regeneratorRuntime = module.regeneratorRuntime;
    }, function (module) {
      cclegacy = module.cclegacy;
      UITransform = module.UITransform;
      SpriteFrame = module.SpriteFrame;
      Rect = module.Rect;
      Size = module.Size;
      Sprite = module.Sprite;
      Node = module.Node;
      Layers = module.Layers;
      Texture2D = module.Texture2D;
      resources = module.resources;
      JsonAsset = module.JsonAsset;
    }],
    execute: function () {
      cclegacy._RF.push({}, "38097jSoUBAqoV/u270QjNs", "LevelOneArt", undefined);
      /** Reviewed, local sprites only. Rendering never changes kitchen observations or rules. */
      var LevelOneArt = exports('LevelOneArt', /*#__PURE__*/function () {
        function LevelOneArt() {
          this.frames = {};
          this.definitions = {};
          this.slices = {};
          this.ready = false;
          this.modular = false;
        }
        var _proto = LevelOneArt.prototype;
        _proto.loadAtlas = /*#__PURE__*/function () {
          var _loadAtlas = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee(path, prefix) {
            var _yield$Promise$all, manifest, texture, _i, _Object$entries, _Object$entries$_i, key, value, _value$rect, x, y, w, h, frame;
            return _regeneratorRuntime().wrap(function _callee$(_context) {
              while (1) switch (_context.prev = _context.next) {
                case 0:
                  if (prefix === void 0) {
                    prefix = '';
                  }
                  _context.next = 3;
                  return Promise.all([new Promise(function (resolve, reject) {
                    return resources.load(path + '/manifest', JsonAsset, function (e, a) {
                      return e ? reject(e) : resolve(a);
                    });
                  }), new Promise(function (resolve, reject) {
                    return resources.load(path + '/atlas/texture', Texture2D, function (e, a) {
                      return e ? reject(e) : resolve(a);
                    });
                  })]);
                case 3:
                  _yield$Promise$all = _context.sent;
                  manifest = _yield$Promise$all[0];
                  texture = _yield$Promise$all[1];
                  texture.setFilters(Texture2D.Filter.NEAREST, Texture2D.Filter.NEAREST);
                  _i = 0, _Object$entries = Object.entries(manifest.json.frames);
                case 8:
                  if (!(_i < _Object$entries.length)) {
                    _context.next = 22;
                    break;
                  }
                  _Object$entries$_i = _Object$entries[_i], key = _Object$entries$_i[0], value = _Object$entries$_i[1];
                  _value$rect = value.rect, x = _value$rect[0], y = _value$rect[1], w = _value$rect[2], h = _value$rect[3];
                  if (!(w <= 0 || h <= 0 || x < 0 || y < 0 || x + w > texture.width || y + h > texture.height)) {
                    _context.next = 13;
                    break;
                  }
                  throw new Error('Invalid art frame ' + key);
                case 13:
                  frame = new SpriteFrame();
                  frame.texture = texture;
                  frame.rect = new Rect(x, y, w, h);
                  frame.originalSize = new Size(w, h);
                  this.frames[prefix + key] = frame;
                  this.definitions[prefix + key] = value;
                case 19:
                  _i++;
                  _context.next = 8;
                  break;
                case 22:
                case "end":
                  return _context.stop();
              }
            }, _callee, this);
          }));
          function loadAtlas(_x, _x2) {
            return _loadAtlas.apply(this, arguments);
          }
          return loadAtlas;
        }();
        _proto.load = /*#__PURE__*/function () {
          var _load = _asyncToGenerator( /*#__PURE__*/_regeneratorRuntime().mark(function _callee2() {
            return _regeneratorRuntime().wrap(function _callee2$(_context2) {
              while (1) switch (_context2.prev = _context2.next) {
                case 0:
                  _context2.prev = 0;
                  _context2.next = 3;
                  return this.loadAtlas('art/level1');
                case 3:
                  _context2.prev = 3;
                  _context2.next = 6;
                  return this.loadAtlas('art/level1-modular', 'modular/');
                case 6:
                  this.modular = true;
                  _context2.next = 12;
                  break;
                case 9:
                  _context2.prev = 9;
                  _context2.t0 = _context2["catch"](3);
                  console.warn('Modular kitchen art unavailable; retaining previous level art.', _context2.t0);
                case 12:
                  _context2.prev = 12;
                  _context2.next = 15;
                  return this.loadAtlas('art/kitchen-modules-v2', 'modular/');
                case 15:
                  _context2.next = 20;
                  break;
                case 17:
                  _context2.prev = 17;
                  _context2.t1 = _context2["catch"](12);
                  console.warn('Updated modular art not yet available.', _context2.t1);
                case 20:
                  _context2.prev = 20;
                  _context2.next = 23;
                  return this.loadAtlas('art/serving-side-v1', 'modular/');
                case 23:
                  _context2.next = 28;
                  break;
                case 25:
                  _context2.prev = 25;
                  _context2.t2 = _context2["catch"](20);
                  console.warn('Directional serving art unavailable.', _context2.t2);
                case 28:
                  _context2.prev = 28;
                  _context2.next = 31;
                  return this.loadAtlas('art/burger-food', 'food/');
                case 31:
                  _context2.next = 36;
                  break;
                case 33:
                  _context2.prev = 33;
                  _context2.t3 = _context2["catch"](28);
                  console.warn('Burger food art unavailable; retaining readable ingredient icons.', _context2.t3);
                case 36:
                  _context2.next = 38;
                  return this.loadAtlas('art/grid-foundation-v1');
                case 38:
                  _context2.next = 40;
                  return this.loadAtlas('art/action-feedback-v1');
                case 40:
                  _context2.next = 42;
                  return this.loadAtlas('art/knife-v1');
                case 42:
                  _context2.next = 44;
                  return this.loadAtlas('art/trash-directions-v1');
                case 44:
                  _context2.prev = 44;
                  _context2.next = 47;
                  return this.loadAtlas('art/ingredient-pack-v1');
                case 47:
                  _context2.next = 52;
                  break;
                case 49:
                  _context2.prev = 49;
                  _context2.t4 = _context2["catch"](44);
                  console.warn('Ingredient pack art unavailable; new ingredients keep their fallback icons.', _context2.t4);
                case 52:
                  if (!(typeof location !== 'undefined' && new URLSearchParams(location.search).get('prepSample') === '1')) {
                    _context2.next = 55;
                    break;
                  }
                  _context2.next = 55;
                  return this.loadAtlas('art/prep-pose-v3');
                case 55:
                  this.ready = true;
                  _context2.next = 61;
                  break;
                case 58:
                  _context2.prev = 58;
                  _context2.t5 = _context2["catch"](0);
                  console.warn('ChefJeff level 1 art unavailable; retaining readable fallback.', _context2.t5);
                case 61:
                case "end":
                  return _context2.stop();
              }
            }, _callee2, this, [[0, 58], [3, 9], [12, 17], [20, 25], [28, 33], [44, 49]]);
          }));
          function load() {
            return _load.apply(this, arguments);
          }
          return load;
        }();
        _proto.has = function has(key) {
          return !!this.frames[key];
        }
        /** Natural pixel proportions, one 64 px art unit per gameplay cell. */;
        _proto.tile = function tile(parent, key, cellSize, x, y) {
          if (x === void 0) {
            x = 0;
          }
          if (y === void 0) {
            y = 0;
          }
          var name = 'modular/' + key,
            definition = this.definitions[name];
          if (!definition) return false;
          var _definition$rect = definition.rect,
            w = _definition$rect[2],
            h = _definition$rect[3];
          return this.show(parent, name, w * cellSize / 64, h * cellSize / 64, x, y);
        }
        /** Align the working surface, independently of transparent canvas and floor anchor. */;
        _proto.surface = function surface(parent, key, cellSize, x, y, depth) {
          if (depth === void 0) {
            depth = 1;
          }
          var name = 'modular/' + key,
            d = this.definitions[name];
          if (!(d != null && d.workSurfaceAnchor) || !d.groundAnchor) return false;
          var scale = cellSize / 64,
            _d$rect = d.rect,
            w = _d$rect[2],
            h = _d$rect[3];
          return this.show(parent, name, w * scale, h * scale * depth, x - (d.workSurfaceAnchor[0] - d.groundAnchor[0]) * scale, y - (d.groundAnchor[1] - d.workSurfaceAnchor[1]) * scale * depth);
        }
        /** Decorations use a centre anchor independent of floor-based sprite anchors. */;
        _proto.centered = function centered(parent, key, w, h) {
          var d = this.definitions[key];
          if (!d) return false;
          var _d$rect2 = d.rect,
            cw = _d$rect2[2],
            ch = _d$rect2[3],
            _ref = d.alpha_bbox || [0, 0, cw, ch],
            left = _ref[0],
            top = _ref[1],
            right = _ref[2],
            bottom = _ref[3];
          var scale = Math.min(w / (right - left), h / (bottom - top));
          if (!this.show(parent, key, cw * scale, ch * scale, (cw / 2 - (left + right) / 2) * scale, ((top + bottom) / 2 - ch / 2) * scale)) return false;
          parent.getChildByName('reviewed-art').getComponent(UITransform).setAnchorPoint(.5, .5);
          return true;
        };
        _proto.hide = function hide(parent) {
          var n = parent.getChildByName('reviewed-art');
          if (n) n.active = false;
        }
        /** Repeatable material crop, retaining the source's pixel density. */;
        _proto.region = function region(parent, key, x, y, w, h, displayW, displayH) {
          var base = this.frames[key];
          if (!base) return false;
          var cache = [key, x, y, w, h].join(':');
          if (!this.slices[cache]) {
            var f = new SpriteFrame();
            f.texture = base.texture;
            f.rect = new Rect(base.rect.x + x, base.rect.y + y, w, h);
            f.originalSize = new Size(w, h);
            this.slices[cache] = f;
          }
          this.show(parent, key, displayW, displayH);
          var n = parent.getChildByName('reviewed-art');
          n.getComponent(Sprite).spriteFrame = this.slices[cache];
          n.getComponent(UITransform).setAnchorPoint(.5, .5);
          return true;
        };
        _proto.show = function show(parent, key, w, h, x, y) {
          if (x === void 0) {
            x = 0;
          }
          if (y === void 0) {
            y = 0;
          }
          var frame = this.frames[key];
          if (!frame) {
            this.hide(parent);
            return false;
          }
          var n = parent.getChildByName('reviewed-art');
          if (!n) {
            n = new Node('reviewed-art');
            n.layer = Layers.Enum.UI_2D;
            parent.addChild(n);
            n.addComponent(UITransform);
            n.addComponent(Sprite);
          }
          n.active = true;
          n.setPosition(x, y);
          var transform = n.getComponent(UITransform);
          var anchor = this.definitions[key].anchor || [.5, .5];
          transform.setAnchorPoint(anchor[0], anchor[1]);
          var sprite = n.getComponent(Sprite);
          sprite.sizeMode = Sprite.SizeMode.CUSTOM;
          sprite.trim = false;
          if (sprite.spriteFrame !== frame) sprite.spriteFrame = frame;
          transform.setContentSize(w, h);
          return true;
        };
        return LevelOneArt;
      }());
      cclegacy._RF.pop();
    }
  };
});

System.register("chunks:///_virtual/main", ['./KitchenAudio.ts', './KitchenClient.ts', './KitchenGeometry.ts', './LevelOneArt.ts'], function () {
  return {
    setters: [null, null, null, null],
    execute: function () {}
  };
});

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