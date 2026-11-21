"""Jeff drawn between polls (KitchenGeometry.jeffDraw, display only), checked against the engine's own walks. Engine
traces come from a SpatialKitchen ticking every 50 ms; a page like KitchenClient's (a poll checked every 0.05 s,
0.2 s apart, one in flight, a round trip of 0.1 to 0.45 s, the lower-bound game clock, the lead sized by the gaps
between states, 60 frames a second, game speed 1 or 0.75) draws him from them. Drawn Jeff never jumps, never steps
back along the engine's path, never leaves the floor, never walks into the player's chef (slides round them, waits
at contact in a 1-cell corridor), walks back the way he came when the engine turns him round, and walks with his
legs while he moves. Needs tsc and Node.js."""
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from test_visual_geometry import ROOT

sys.path.insert(0, str(ROOT / 'scripts'))
import audit_map  # noqa: E402

FIELDS = ('position', 'route', 'travel_remaining', 'working', 'knocked', 'sprint', 'action_kind', 'target')

PAGE = r"""
const g=require(process.argv[2]),cases=JSON.parse(require('fs').readFileSync(process.argv[3],'utf8'));
const J=g.JEFF_DRAW,NEAR=[[0,0],[.03,0],[-.03,0],[0,.03],[0,-.03],[.02,.02],[.02,-.02],[-.02,.02],[-.02,-.02]];
const out={};
for(const c of cases){
  const map=c.map,ticks=c.ticks,speed=c.speed,t0=ticks[0].t,t1=ticks[ticks.length-1].t,W1=(t1-t0)/speed;
  const tickAt=gt=>ticks[Math.max(0,Math.min(ticks.length-1,Math.floor((gt-t0)/.05+1e-9)))];
  const engineAt=gt=>{let i=0;while(i<ticks.length-2&&ticks[i+1].t<=gt)i++;const a=ticks[i],b=ticks[i+1]||a,u=b.t>a.t?Math.max(0,Math.min(1,(gt-a.t)/(b.t-a.t))):0;
    return [a.jeff.position[0]+(b.jeff.position[0]-a.jeff.position[0])*u,a.jeff.position[1]+(b.jeff.position[1]-a.jeff.position[1])*u];};
  // Polls: one in flight; the next starts once 0.2 s passed and the reply landed (checked every 0.05 s).
  const arrivals=[];let start=c.firstPoll||0;
  while(start<W1){const arrive=start+c.rtt;arrivals.push({at:arrive,tick:tickAt(t0+(start+c.rtt/2)*speed)});start=Math.ceil(Math.max(start+.19,arrive)/.05-1e-9)*.05;}
  let clock=null,stateArr=[],serial=0,next=0,k=null,walk=null,drawn=ticks[0].jeff.position.slice();
  const r={frames:0,snaps:0,maxStep:0,back:0,offFloor:0,offPath:0,minGap:Infinity,err:[],legsOff:0,moving:0};
  const path=ticks.map(x=>x.jeff.position);let lastAlong=null;
  for(let fw=1/60;fw<W1;fw+=1/60){
    while(next<arrivals.length&&arrivals[next].at<=fw){
      const s=arrivals[next++],tk=s.tick;serial++;k={time:+tk.t.toFixed(2),map,chefs:{jeff:tk.jeff,human:{position:tk.human}}};
      const bound=k.time-s.at*speed,gc=clock;   // KitchenClient.noteGameClock
      if(!gc||bound>gc.offset||gc.offset-bound>.75)clock={offset:bound,at:s.at};else{gc.offset=Math.max(bound,gc.offset-(s.at-gc.at)*.02);gc.at=s.at;}
      stateArr.push(s.at);if(stateArr.length>7)stateArr.shift();
    }
    if(!k)continue;
    let gap=0;for(let i=1;i<stateArr.length;i++)gap=Math.max(gap,stateArr[i]-stateArr[i-1]);
    const lead=Math.min(J.LEAD_LONGEST,Math.max(J.LEAD_SHORTEST,gap*speed+J.LEAD_MARGIN));   // KitchenClient.jeffLead
    const gt=t0+fw*speed,human=tickAt(gt).human;
    const res=g.jeffDraw(walk,{serial,k,now:fw*speed+clock.offset,dt:speed/60,wall:1/60,drawn,other:human,lead});
    walk=res.walk;r.frames++;if(res.snapped)r.snaps++;
    const step=Math.hypot(res.at[0]-drawn[0],res.at[1]-drawn[1]);if(step>r.maxStep)r.maxStep=step;
    const on=g.routeProject(path,res.at);if(on.offset>.15)r.offPath++;
    if(lastAlong!==null&&on.offset<=.15&&on.along<lastAlong-.02)r.back++;
    if(on.offset<=.15)lastAlong=Math.max(lastAlong??0,on.along);
    // Off the floor where the engine never was: routes run along walk-box edges, so no floor within 0.03 cells.
    if(on.offset>.02&&!NEAR.some(([x,y])=>g.footWalkable(map,res.at[0]+x,res.at[1]+y)))r.offFloor++;
    r.minGap=Math.min(r.minGap,Math.hypot(res.at[0]-human[0],res.at[1]-human[1]));
    const e=engineAt(gt);r.err.push(Math.hypot(res.at[0]-e[0],res.at[1]-e[1]));
    if(step*60/speed>1.5){r.moving++;if(!res.walking)r.legsOff++;}
    drawn=res.at;
  }
  r.err.sort((a,b)=>a-b);r.p90=r.err[Math.floor(r.err.length*.9)];delete r.err;
  r.end=drawn;r.engineEnd=ticks[ticks.length-1].jeff.position;r.rtt=c.rtt;out[c.name]=r;
}
console.log(JSON.stringify(out));
"""


def kitchen(level):
    return SpatialKitchen(level_config(load_config(), level))


def moves(k):
    return [a for a in k.actions('jeff') if a.kind not in ('wait', 'continue', 'stop', 'throw') and a.key != 'go partner']


def longest(k):
    return max(moves(k), key=lambda a: k.travel_time(k.chefs['jeff'], a.target))


def trace(k, seconds, events=(), human=None):
    """Jeff's chef data and the player's position every 50 ms tick. events: [(seconds, fn(k))]; human: fn(k, t)
    giving where the player stands (None: where the engine has them)."""
    ticks, todo, start = [], sorted(events, key=lambda e: e[0]), k.time
    for _ in range(int(seconds / .05) + 1):
        t = k.time - start
        while todo and todo[0][0] <= t + 1e-9:
            todo.pop(0)[1](k)
        if human:
            p = human(k, t)
            if p is not None:
                k.positions['human'] = tuple(p)
        snap = k.snapshot()
        ticks.append({'t': round(snap['time'], 4), 'jeff': {f: snap['chefs']['jeff'].get(f) for f in FIELDS},
                      'human': snap['chefs']['human']['position']})
        k.advance(.05)
    return k.snapshot()['map'], ticks


def walking(level, action=None, sprint=False):
    """A kitchen with Jeff starting `action(k)` (default: his longest listed walk)."""
    k = kitchen(level)
    ok, message = k.start('jeff', action(k) if action else longest(k))
    assert ok, message
    if sprint:
        assert k.sprint('jeff')
    return k


def longest_segment(k):
    """The middle of the longest leg of Jeff's route, the leg's direction, and how far along the route it lies."""
    route = [tuple(p) for p in k.routes['jeff']['points']]
    walked = 0.
    best = None
    for a, b in zip(route, route[1:]):
        length = math.dist(a, b)
        if best is None or length > best[0]:
            best = (length, [(a[i] + b[i]) / 2 for i in (0, 1)], ((b[0] - a[0]) / length, (b[1] - a[1]) / length),
                    walked + length / 2)
        walked += length
    return best[1], best[2], best[3]


class JeffDrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='jeff-draw-')
        cls.geometry = audit_map.compile_geometry(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def page(self, name, drawn, pages=((1, .1), (1, .3), (.75, .45)), first=0):
        """drawn: (map, ticks); pages: (game speed, round trip) pairs."""
        if self.geometry is None:
            self.skipTest('TypeScript compiler or Node.js unavailable')
        map_, ticks = drawn
        cases = [{'name': f'{name} speed {s} rtt {rtt}', 'map': map_, 'ticks': ticks, 'speed': s, 'rtt': rtt,
                  'firstPoll': first} for s, rtt in pages]
        data, runner = Path(self.temp.name) / 'cases.json', Path(self.temp.name) / 'page.js'
        data.write_text(json.dumps(cases))
        runner.write_text(PAGE)
        done = subprocess.run(['node', str(runner), str(self.geometry), str(data)], capture_output=True, text=True)
        if done.returncode:
            raise RuntimeError(done.stderr)
        return json.loads(done.stdout)

    def assert_smooth(self, result, step=.15, p90=.45, back=True, gap=None, end=.2, legs=True, pace=1.):
        """p90: how far drawn Jeff may be from the engine, 90% of the time, plus what the round trip costs (he is
        drawn from states that old: walking speed x pace x round trip)."""
        for key, r in result.items():
            with self.subTest(key):
                self.assertEqual(r['snaps'], 0, (key, r))
                # Never a jump: a frame's step is at most his catch-up pace (1.6 x walking: 0.12 cells; 0.24 sprinting).
                self.assertLess(r['maxStep'], step, (key, r))
                if back:
                    self.assertEqual(r['back'], 0, (key, r))
                self.assertEqual(r['offFloor'], 0, (key, r))
                self.assertLess(r['p90'], p90 + 4.5 * pace * r['rtt'], (key, r))
                if legs:
                    self.assertLess(r['legsOff'], max(3, r['moving'] * .03), (key, r))
                if gap is not None:
                    self.assertGreater(r['minGap'], gap, (key, r))
                if end is not None:
                    self.assertLess(math.dist(r['end'], r['engineEnd']), end, (key, r))

    def test_a_long_walk(self):
        k = walking(1)
        self.assert_smooth(self.page('walk', trace(k, k.chefs['jeff'].job.travel + 1.2)))

    def test_a_sprint(self):
        k = walking(1, sprint=True)
        self.assert_smooth(self.page('sprint', trace(k, k.chefs['jeff'].job.travel + 1.2)), step=.27, pace=2.)

    def test_a_walk_that_starts_between_polls_follows_the_engine_path(self):
        # The first state is taken 0.35 s into the walk: he is that far behind and catches up on the engine's path.
        k = walking(4)
        result = self.page('late start', trace(k, k.chefs['jeff'].job.travel + 1.2), first=.3)
        self.assert_smooth(result, p90=1.2)
        for key, r in result.items():
            self.assertLess(r['offPath'], 3, (key, r))

    def test_a_state_that_shows_him_arrived_while_drawn_behind_has_him_walk_there(self):
        k = kitchen(1)
        short = min(moves(k), key=lambda a: abs(k.travel_time(k.chefs['jeff'], a.target) - .55)).key
        k = walking(1, lambda k: next(a for a in moves(k) if a.key == short))
        drawn = trace(k, 1.6)
        travel = next(i for i, x in enumerate(drawn[1]) if not x['jeff']['travel_remaining']) * .05
        result = self.page('arrived', drawn, pages=((1, .1),), first=travel)
        self.assert_smooth(result, p90=2.5)     # behind by construction: the whole walk
        for key, r in result.items():
            self.assertGreater(r['moving'], 5, (key, r))

    def test_a_player_on_his_goal_stops_him_a_cell_short_without_a_step_back(self):
        k = walking(1)
        k.positions['human'] = tuple(k.routes['jeff']['points'][-1])
        self.assert_smooth(self.page('goal taken', trace(k, k.chefs['jeff'].job.travel + 1.5)), gap=.6)

    def test_walking_into_the_player_stops_at_contact(self):
        k = walking(1, lambda k: next(a for a in k.actions('jeff') if a.key == 'go partner'))
        self.assert_smooth(self.page('go partner', trace(k, k.chefs['jeff'].job.travel + 1.5)), gap=.37)

    def test_passing_the_player_slides_round_without_a_stall_or_a_jump(self):
        # Beside his line and right on it (where the side he steps round on must not flip).
        for level in (1, 2):
            for off in (.25, 0.):
                k = walking(level)
                mid, (ux, uy), _ = longest_segment(k)
                spot = (mid[0] - uy * off, mid[1] + ux * off)
                drawn = trace(k, k.chefs['jeff'].job.travel + 1.5, human=lambda k, t, spot=spot: spot if t >= .1 else None)
                # Right on his line the slide round settles fast for a frame or two (at most 0.3 cells a frame).
                self.assert_smooth(self.page(f'passing L{level} off {off}', drawn), step=.3 if off == 0 else .2,
                                   back=False, gap=.3 if off == 0 else .35, end=None)

    def test_a_player_crossing_in_front_of_him_never_makes_him_jump(self):
        # The player runs across his line at 4 cells a second as he comes (the page's own chef slides round the
        # engine's Jeff, so the drawn Jeff may touch it for a moment; he never jumps).
        for lag in (0., .1):
            k = walking(2)
            mid, (ux, uy), ahead = longest_segment(k)
            when = ahead / k.rules.walk_speed

            def human(k, t, lag=lag, when=when, mid=mid, ux=ux, uy=uy):
                d = max(-1.2, min(1.2, (t - when - lag) * 4.))
                return mid[0] - uy * d, mid[1] + ux * d
            drawn = trace(k, k.chefs['jeff'].job.travel + 1.0, human=human)
            self.assert_smooth(self.page(f'crossing lag {lag}', drawn, pages=((1, .1), (.75, .3))), step=.2,
                               back=False, gap=.2, end=None, p90=1.)

    def test_a_player_in_a_one_cell_corridor_holds_him_at_contact(self):
        # Level 3's centre corridor (x 6 to 8, y 4): the engine holds him at contact and re-plans; he is never drawn
        # through the player.
        k = kitchen(3)
        action = max((a for a in moves(k) if k.path('jeff', a.target)[-1][0] < 5.5),
                     key=lambda a: k.travel_time(k.chefs['jeff'], a.target))
        self.assertTrue(k.start('jeff', action)[0])
        drawn = trace(k, 4.0, human=lambda k, t: (7., 4.) if t >= .1 else None)
        self.assert_smooth(self.page('corridor', drawn, pages=((.75, .1), (1, .3))), step=.2, back=False, gap=.3,
                           end=None, p90=1., legs=False)

    def test_a_turn_round_walks_back_the_way_he_came(self):
        # The engine starts a walk back toward where he set out while the page still draws the first walk ahead of it.
        for level, when in ((1, .7), (1, 1.1), (3, 1.3)):
            k = walking(level)
            home = tuple(k.routes['jeff']['points'][0])

            def turn(k, home=home):
                assert k.start('jeff', min(moves(k), key=lambda b: math.dist(k.path('jeff', b.target)[-1], home)))[0]
            drawn = trace(k, when + 3.0, [(when, turn)])
            self.assert_smooth(self.page(f'turn L{level} at {when}', drawn, pages=((1, .1), (1, .3))), step=.2,
                               back=False, p90=1.5)

    def test_the_players_take_round_the_sink_is_drawn_along_its_route(self):
        # Level 4: washing from the notch west of the sink, Space with empty hands takes the drying rack's plate, and
        # the engine walks the chef round the sink to the rack. The page draws that walk (followRoute) on the floor,
        # never straight across the sink and the rack.
        if self.geometry is None:
            self.skipTest('TypeScript compiler or Node.js unavailable')
        k = kitchen(4)
        k.positions['jeff'] = (6.0, 2.0)
        k.positions['human'] = (4.15, 7.0)
        k.aim['human'] = (1., 0.)
        k._face_vector('human', 1., 0.)
        k.chefs['human'].location = 'floor_%d_%d' % k.anchor('human')
        plate = k.stations['counter1'].food
        k.stations['counter1'].food = None
        plate.stage = 'dirty_plate'
        k.chefs['human'].hand = plate

        def space(mode='hands'):
            k.face('human', *k.aim['human'])
            focus, action = k.facing_interaction('human', mode)
            self.assertIsNotNone(action, focus)
            if focus in k.equipment:
                k.pick_station('human', focus)
            self.assertTrue(k.start('human', action)[0])
            return action

        def finish():
            for _ in range(400):
                if not k.chefs['human'].job:
                    return
                k.advance(.05)
        space()
        finish()
        space('use')
        finish()
        take = space()
        self.assertEqual(take.target, k.dryer)
        states = []
        while k.chefs['human'].job:
            snap = k.snapshot()['chefs']['human']
            states.append({'route': snap['route'], 'travel': snap['travel_remaining'], 'position': snap['position']})
            k.advance(.05)
        self.assertGreater(len(states[0]['route']), 2, 'the take walks round the sink')
        script = Path(self.temp.name) / 'take.js'
        script.write_text(r"""
const g=require(process.argv[2]),d=JSON.parse(require('fs').readFileSync(process.argv[3],'utf8'));
const map=d.map,walk=map.walk_speed;let at=d.states[0].position.slice(),off=0,worst=0;
const NEAR=[[0,0],[.03,0],[-.03,0],[0,.03],[0,-.03],[.02,.02],[.02,-.02],[-.02,.02],[-.02,-.02]];
for(const every of [1,4]){                       // a state every tick (0.05 s), or every 0.2 s poll
  at=d.states[0].position.slice();
  for(let i=0;i<d.states.length;i++){
    const s=d.states[Math.floor(i/every)*every];
    for(let f=0;f<3;f++){                         // three frames a tick (60 a second)
      if(s.travel>0&&s.route.length)at=g.followRoute(s.route,at,walk/60);
      if(!NEAR.some(([x,y])=>g.footWalkable(map,at[0]+x,at[1]+y)))off++;
    }
  }
  worst=Math.max(worst,Math.hypot(at[0]-d.end[0],at[1]-d.end[1]));
}
console.log(JSON.stringify({off,worst}));
""")
        data = Path(self.temp.name) / 'take.json'
        data.write_text(json.dumps({'map': k.snapshot()['map'], 'states': states, 'end': list(k.positions['human'])}))
        done = subprocess.run(['node', str(script), str(self.geometry), str(data)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual(result['off'], 0, result)
        self.assertLess(result['worst'], .15, result)

    def test_a_knock_is_followed_at_once(self):
        if self.geometry is None:
            self.skipTest('TypeScript compiler or Node.js unavailable')
        script = Path(self.temp.name) / 'knock.js'
        script.write_text(r"""
const g=require(process.argv[2]);
const map={walk_speed:4.5,chef_separation:.4,width:12,height:8,walk_clearance:.2,walk_boxes:[]};
const chef=(p,knocked)=>({position:p,route:[],travel_remaining:0,working:false,knocked,sprint:{active_remaining:0,duration:.35,multiplier:2},action_kind:null});
let w=null,drawn=[3,3],t=0,serial=1,k={time:0,map,chefs:{jeff:chef([3,3],false),human:{position:[8,3]}}};
const trace=[];
for(let f=0;f<60;f++,t+=1/60){
  if(f===12){serial++;k={time:.2,map,chefs:{jeff:chef([3.75,3],true),human:{position:[8,3]}}};}
  if(f===24){serial++;k={time:.4,map,chefs:{jeff:chef([4,3],false),human:{position:[8,3]}}};}
  const r=g.jeffDraw(w,{serial,k,now:t,dt:1/60,wall:1/60,drawn,other:[8,3],lead:.25});w=r.walk;drawn=r.at;trace.push([f,r.at[0],r.walking]);
}
console.log(JSON.stringify(trace));
""")
        done = subprocess.run(['node', str(script), str(self.geometry)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        frames = json.loads(done.stdout)
        # Knocked state at frame 12 (3.75), landed at frame 24 (4.0): drawn there within 0.2 s each, legs still
        # while knocked.
        self.assertAlmostEqual(frames[23][1], 3.75, delta=.05)
        self.assertAlmostEqual(frames[24 + 12][1], 4.0, delta=.05)
        self.assertFalse(any(walks for f, x, walks in frames[12:24]))


if __name__ == '__main__':
    unittest.main()
