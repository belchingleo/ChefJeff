"""Spatial whitebox: the same kitchen rules on a walkable grid, without AI policy."""
from functools import lru_cache
import math
import random
from kitchen import Kitchen, Action, Station, NAMES, TAKE_KINDS, Job, GroundItem, STATES, engine_input
from map_definition import geometry
from navigation import WALK_CLEARANCE, Navigation, contact_fraction
FACING_STEPS = {'up':(0,-1),'down':(0,1),'left':(-1,0),'right':(1,0)}
# Jeff throws along the player's eight aim directions, always to full reach (see aimed_throw).
THROW_DIRECTIONS = {'up':((0,-1),'上方'),'down':((0,1),'下方'),'left':((-1,0),'左方'),'right':((1,0),'右方'),
                    'up-left':((-1,-1),'左上方'),'up-right':((1,-1),'右上方'),'down-left':((-1,1),'左下方'),'down-right':((1,1),'右下方')}
USE_KINDS = ('chop','wash','extinguish')  # E; Space takes, puts, plates and serves

THROW_RANGE = 4.0
# Plates, plated food and pots; reference values of the service ruleset
# (throw.range_cells / throw.pass_range_cells). Live kitchens read the ruleset.
PASS_RANGE = 4.0
WALK_SPEED = 4.5  # Both chefs: 1.5x the original 3 cells per game second
CHEF_SEPARATION = .4  # two small foot circles, not the full tall sprite
UP_STANDOFF = -.22  # tiles a south-side operator stands back from the cabinet
# Facing left or right, the hands and knife are drawn about this far above the feet (side chop poses:
# fist 0.38-0.48 cells up at the strike, blade landing 0.06-0.22), so the front point is raised to hand
# height and the station the knife points at is the target. Up and down are unchanged.
SIDE_HAND_RISE = .35
# Space's station, as Overcooked 2 picks it (PlayerControls.FindNearbyObjects, InteractWithItemHelper
# .GetFacingGridOccupant): among the stations in the eight cells around the chef's own cell, the one
# whose direction best matches where the chef last aimed; ties go to the one nearest a point SELECT_AHEAD
# ahead (at hand height when aiming sideways). Only stations ahead count, never beside or behind, and
# within SELECT_REACH cells of the feet. The pick is purely geometric, so what is highlighted is what
# Space acts on: a station with nothing to do never hands Space to another one.
# Unlike Overcooked 2, which scores the raw offset (a diagonal cell, 1.41 long, wins as soon as the
# stick leans a little its way), directions are compared by angle and the straight cells get
# SELECT_STRAIGHT_BONUS: a phone stick is never exactly straight, so a diagonal station is picked only
# when the aim is about 30 degrees or more off the straight one.
SELECT_AHEAD = .5
SELECT_STRAIGHT_BONUS = .1
SELECT_REACH = .85  # Overcooked 2's 1-unit radius, about 1.2 units per cell
# Overcooked-style local movement: the player's own browser moves its chef and reports where it is
# (report_position); the engine walks there with the same physics. The walk is limited to
# REPORT_SPEED_MARGIN x the walking speed (sprint included), banked up to REPORT_BUDGET cells so a late
# report catches up at once. A target more than REPORT_MAX_LEAD away, a push, or REPORT_STALL seconds
# without progress resyncs: the browser then takes the engine's position.
REPORT_SPEED_MARGIN = 1.25
REPORT_BUDGET = 2.
REPORT_MAX_LEAD = 2.5
REPORT_STALL = .25
# Reference values of movement.stall_replan in the service ruleset: a routed chef whose
# remaining route has not shortened by STALL_PROGRESS for STALL_SECONDS re-plans from
# where contact left it, around the other chef. Live kitchens read the ruleset.
STALL_SECONDS = .3
STALL_PROGRESS = .05


def tile_key(cell):
    return f'floor_{cell[0]}_{cell[1]}'


def _segment_distance(point, start, end):
    dx,dy=end[0]-start[0],end[1]-start[1];length=dx*dx+dy*dy
    t=0. if length<1e-12 else max(0.,min(1.,((point[0]-start[0])*dx+(point[1]-start[1])*dy)/length))
    return math.dist(point,(start[0]+dx*t,start[1]+dy*t))


@lru_cache(maxsize=12)
def _map_navigation(size,walls,cells,cabinet_clearance=None):
    return Navigation(*size,walls,{key:{'cell':cell} for key,cell in cells},cabinet_clearance)


class SpatialKitchen(Kitchen):
    def __init__(self, config=None, rng=None):
        super().__init__(config, rng)
        self.map_document=self.resolved['map']
        self.width,self.height=self.map_document['size']
        self.equipment,self.walls=geometry(self.map_document)
        self.nav=_map_navigation(tuple(self.map_document['size']),tuple(sorted(self.walls)),
                                 tuple(sorted((key+':'+str(i),tuple(c)) for key,e in self.equipment.items() for i,c in enumerate(e.get('cells',[e['cell']])))),
                                 self.rules.cabinet_clearance)
        self.floor=self.nav.floor
        self.sprint_until={who:0. for who in self.chefs}
        self.sprint_ready_at={who:0. for who in self.chefs}
        self.nudged_distance={who:{} for who in self.chefs}
        self.bumped_chefs={who:set() for who in self.chefs}
        self.knockback={who:None for who in self.chefs}
        # One spawn near each center on its side of the partition; sides shuffled by the spawn seed.
        spec = self.resolved['level']['spawns']
        axis = 0 if spec['partition']['axis'] == 'x' else 1
        split = spec['partition']['split']
        spawns = [min((c for c in self.floor if (c[axis]<split)==(center[axis]<split)),
                      key=lambda c:(math.dist(c,center),c[1-axis],c[axis]))
                  for center in (tuple(center) for center in spec['centers'])]
        random.Random(self.resolved['seeds']['spawn']).shuffle(spawns)
        self.positions = dict(zip(('human','jeff'),spawns))
        for who in self.chefs:self.chefs[who].location=tile_key(self.positions[who])
        self.facing = {who: 'down' for who in self.chefs}
        # Where each chef last aimed (held direction, any angle): what Space's station is picked by.
        self.aim = {who: (0., 1.) for who in self.chefs}
        # The station Space just picked (pick_station): its action is worked where the chef stands.
        self.space_pick = {who: None for who in self.chefs}
        self.routes = {}
        self.route_progress = {}
        self.configure_operation_points()
        self.drop_locks = {}
        self.projectiles = {}
        self.manual = {who: (0., 0.) for who in self.chefs}
        self.reported = {who: False for who in self.chefs}  # chef moved by position reports
        self.report_target = {who: None for who in self.chefs}
        self.report_budget = {who: REPORT_BUDGET for who in self.chefs}  # a chef starts standing still
        self.report_stalled = {who: 0. for who in self.chefs}
        self.resync = {who: 0 for who in self.chefs}  # reports must carry the current count as `base`
        self.report_press = {who: False for who in self.chefs}
        self.report_best = {who: 0. for who in self.chefs}  # closest the chase has come to its point
        self.floor_places = {tile_key(cell): Station(f'地面({cell[0]},{cell[1]})', self.floor_area(cell))
                             for cell in self.floor}

    def floor_area(self, cell):
        areas, rule = self.map_document['areas'], self.map_document.get('floor_areas')
        if not rule:
            return next(iter(areas.values()))['name']
        coordinate = cell[0 if rule['axis'] == 'x' else 1]
        return areas[rule['below'] if coordinate < rule['split'] else rule['at_or_above']]['name']

    def configure_operation_points(self):
        # All stations use the same direction contract (see Navigation: every cabinet's back edge is
        # walked up to). Neither actor artwork nor table is moved.
        self.operation_insets={}
        # With one body size, side operators stand exactly at the side walk limit.
        side=.30 if self.rules.cabinet_clearance is None else .5-self.rules.cabinet_clearance[1]
        # operate_at_walk_limit: every face works from where walking toward it stops,
        # so a chef never steps back or aside when an action starts.
        up=.5-self.rules.cabinet_clearance[0] if self.at_walk_limit else UP_STANDOFF
        for key,e in self.equipment.items():
            if e.get('reach')=='corner':continue
            faces={}
            x,y=e['cell']
            for face,dx,dy in [('down',0,-1),('up',0,1),('right',-1,0),('left',1,0)]:
                if (x+dx,y+dy) not in self.floor:continue
                # 'up' is negative: the chef steps back from the cabinet so the tall
                # back-view sprite reads as standing in front of it, not on it.
                faces[face]=up if face=='up' else side if face in ('left','right') else .49
            self.operation_insets[key]=faces

    def sprint_extra(self, who, seconds):
        """Extra walking time a sprint adds to the step that ends now. As Overcooked's dash, the speed
        starts at sprint_multiplier and eases back to walking along a sine S-curve over the sprint:
        boost(r) = (m-1)(1-cos(pi r/D))/2 with r the sprint time left; this is its integral."""
        d=self.rules.sprint_duration
        if d<=0:return 0.
        late,early=(min(d,max(0.,self.sprint_until[who]-t)) for t in (self.time,self.time-seconds))
        wave=lambda r:r-d/math.pi*math.sin(math.pi*r/d)
        return self.rules.sprint_boost*(wave(early)-wave(late))/2

    @engine_input
    def sprint(self, who):
        if self.ended or self.time < self.sprint_ready_at[who]-1e-8:
            return False
        job=self.chefs[who].job
        if not any(self.manual[who]) and not (job and not job.working and job.travel>1e-8):return False
        self.sprint_until[who]=self.time+self.rules.sprint_duration
        self.sprint_ready_at[who]=self.time+self.rules.sprint_duration+self.rules.sprint_cooldown
        self.nudged_distance[who]={}
        self.bumped_chefs[who]=set()
        self.emit(f'{NAMES[who]}开始冲刺',kind='sprint',actor=who,duration=float(self.rules.sprint_duration),
                  multiplier=self.rules.sprint_multiplier,cooldown=float(self.rules.sprint_cooldown))
        return True

    def _travel_step(self,who,job,seconds):
        route=self.routes.get(who)
        if not route or route['job_id']!=job.id:return super()._travel_step(who,job,seconds)
        start=self.time-seconds
        fast=max(0.,min(seconds,self.sprint_until[who]-start))
        walk=self.rules.walk_speed
        speed=walk*(1.+self.sprint_extra(who,seconds)/seconds) if seconds else walk
        budget=seconds*speed;spent=0.
        points=list(route['points'][1:])
        approach=job.action.key=='go partner'
        while points and budget>1e-9:
            if approach and len(points)==1:
                points[0]=self.positions['jeff' if who=='human' else 'human']
            before=self.positions[who];goal=points[0];distance=math.dist(before,goal)
            # Floor interactions use the same nearby reach as keyboard actions;
            # their approach must not push the recipient off the target.
            if len(points)==1 and job.action.kind not in ('go','chop','wash','drop') and distance<=.5 and self.nav.clear_walk_line(before,goal) and (job.action.kind in ('pickup','plate_ground','plate_partner') or math.dist(goal,self.positions['jeff' if who=='human' else 'human'])<self.rules.chef_separation):
                points.clear();break
            if distance<1e-8:points.pop(0);continue
            step=min(budget,distance)
            end=tuple(before[i]+(goal[i]-before[i])*step/distance for i in (0,1))
            other_pos=self.positions['jeff' if who=='human' else 'human']
            if not approach and len(points)==1 and distance<=1. and math.dist(goal,other_pos)<CHEF_SEPARATION:
                # The teammate stands on this spot and working chefs are not pushed:
                # stop beside them instead of sliding back and forth every frame.
                self._face_vector(who,goal[0]-before[0],goal[1]-before[1])
                points.clear();break
            self._move_with_chef_contact(who,end,fast>0)
            moved=math.dist(before,self.positions[who])
            # Facing follows real progress, not a sideways contact slide or the centring slide.
            if moved>step*.5 and not route.get('slide'):self._face_vector(who,goal[0]-before[0],goal[1]-before[1])
            if fast>0:self._nudge_food(who,before,self.positions[who])
            spent+=step;budget-=step
            if approach and math.dist(self.positions[who],self.positions['jeff' if who=='human' else 'human'])<=self.rules.chef_separation+.05:
                # Contact made (and pushed): the approach is complete.
                self._face_vector(who,goal[0]-before[0],goal[1]-before[1])
                points.clear();break
            if math.dist(self.positions[who],goal)<1e-8:points.pop(0)
            if math.dist(self.positions[who],end)>1e-8:break
        # Keep the static-map waypoints while the route is making progress.
        route['points']=[self.positions[who]]+points
        route['length']=sum(math.dist(a,b) for a,b in zip(route['points'],route['points'][1:]))
        if points and self.rules.stall_after is not None:self._check_route_stall(who,job,route)
        job.travel=route['length']/walk
        return seconds if points else min(seconds,spent/speed)

    def _check_route_stall(self,who,job,route):
        """Same rule for every chef: a stalled route is re-planned, never abandoned.

        Contact can leave a chef where its remaining waypoints are blocked by a
        counter, or two routed chefs can press into each other with no slide
        free on either side. Progress is judged on remaining length (not raw
        position) so sliding back and forth cannot hide a stall.
        """
        progress=self.route_progress.get(who)
        if not progress or progress['job_id']!=job.id or route['length']<progress['best']-self.rules.stall_progress:
            self.route_progress[who]={'job_id':job.id,'best':route['length'],'since':self.time}
            return
        if self.time-progress['since']<self.rules.stall_after-1e-8:return
        start,goal=self.positions[who],route['points'][-1]
        other=self.positions['jeff' if who=='human' else 'human']
        try:points=self.nav.shortest_path_around(start,goal,other,self.rules.chef_separation)
        except ValueError:
            # The other chef closes every way round (or stands on the goal): in a one-chef-wide passage one
            # of them steps aside first (_give_way); otherwise still drop waypoints contact has made unreachable.
            points=self._give_way(who,goal)
            if not points:
                try:points=self.nav.shortest_path(start,goal)
                except ValueError:points=route['points']
        changed=points!=route['points']
        route['points']=points
        route['length']=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
        self.route_progress[who]={'job_id':job.id,'best':route['length'],'since':self.time}
        if changed:self.emit(f'{NAMES[who]}受阻，重新规划路线',kind='route_replanned',actor=who)

    def _give_way(self, who, goal):
        """Head-on in a passage too narrow to pass: the chef with farther to go (Jeff on a tie, and always
        Jeff against the player's own walking) backs off to the nearest cell clear of the other's way,
        then goes on. None when this chef keeps going."""
        other='jeff' if who=='human' else 'human'
        theirs=self.routes.get(other) if self.chefs[other].job else None
        if theirs:
            mine=self.routes[who]['length']
            if mine<theirs['length']-1e-6 or (abs(mine-theirs['length'])<=1e-6 and who!='jeff'):return None
            way=theirs['points']
        elif who=='jeff':way=[self.positions[other]]
        else:return None
        clear=lambda c:min([math.dist(c,way[0])]+[_segment_distance(c,a,b) for a,b in zip(way,way[1:])])>self.rules.chef_separation+.1
        start=self.positions[who];seen={self.anchor(who)};frontier=[self.anchor(who)]
        while frontier:
            for cell in sorted(frontier,key=lambda c:(math.dist(c,start),c)):
                if clear(cell):
                    try:return self.nav.shortest_path_around(start,cell,self.positions[other],self.rules.chef_separation)+self.nav.shortest_path(cell,goal)[1:]
                    except ValueError:continue
            frontier=[n for c in frontier for n in self.nav.neighbors(c) if n not in seen and not seen.add(n)]
        return None

    def ground_position(self,item):
        cell=self.cell(item.location)
        return (cell[0]+item.offset[0],cell[1]+item.offset[1])

    def _nudge_food(self,who,start,end):
        distance=math.dist(start,end)
        if distance<1e-8:return
        direction=((end[0]-start[0])/distance,(end[1]-start[1])/distance)
        budget=self.nudged_distance[who]
        for key,item in self.ground.items():
            food=item.food
            if item.lock or food.plate_id or food.stage not in ('raw','chopped','ready','burnt'):continue
            position=self.ground_position(item)
            if contact_fraction(start,end,position,.36)>=1.-1e-8 and math.dist(start,position)>.36:continue
            amount=min(distance,max(0.,self.rules.sprint_food_nudge-budget.get(key,0.)))
            if amount<1e-8:continue
            target=tuple(position[i]+direction[i]*amount for i in (0,1))
            # Walls/counters stop the nudge; food and chefs do not repel food.
            if not self.nav.clear_walk_line(position,target):
                low,high=0.,amount
                for _ in range(14):
                    mid=(low+high)/2;p=tuple(position[i]+direction[i]*mid for i in (0,1))
                    if self.nav.clear_walk_line(position,p):low=mid
                    else:high=mid
                amount=low;target=tuple(position[i]+direction[i]*amount for i in (0,1))
            if amount<1e-6:continue
            cell=tuple(int(math.floor(v+.5)) for v in target)
            if cell not in self.floor:continue
            if key not in budget:self.emit(f'{NAMES[who]}轻推了地面食材 {key}',kind='ground_nudge',actor=who,item=key,max_distance=self.rules.sprint_food_nudge)
            budget[key]=budget.get(key,0.)+amount
            item.location=tile_key(cell);item.offset=tuple(target[i]-cell[i] for i in (0,1))

    def _wall_limited(self,start,end):
        if self.nav.clear_walk_line(start,end):return end
        low,high=0.,1.
        for _ in range(16):
            mid=(low+high)/2
            point=tuple(start[i]+(end[i]-start[i])*mid for i in (0,1))
            if self.nav.clear_walk_line(start,point):low=mid
            else:high=mid
        return tuple(start[i]+(end[i]-start[i])*low for i in (0,1))

    def corner_offset(self,start,vector):
        """Smallest sideways shift (signed, cells) that lets a blocked step continue along its main axis, as
        Stardew Valley nudges a farmer whose body only half covers an opening. A stick that is not exactly
        straight counts by its main axis; at an equal shift the side it leans to goes first."""
        if not any(vector):return None
        axis=0 if abs(vector[0])>=abs(vector[1]) else 1
        side=1-axis;probe=.05;lean=-1. if vector[side]<0 else 1.
        for n in range(1,int(round(self.rules.corner_slide/.01))+1):
            for sign in (lean,-lean):
                shifted=list(start);shifted[side]+=sign*n*.01
                ahead=list(shifted);ahead[axis]+=math.copysign(probe,vector[axis])
                if self.nav.clear_walk_line(start,tuple(shifted)) and self.nav.clear_walk_line(tuple(shifted),tuple(ahead)):
                    return sign*n*.01,side
        return None

    def _corner_slide(self,who,vector,budget,boosted):
        # Walking into an edge an opening is just beside: slide sideways by at most the ruleset's
        # corner_slide_cells, then keep walking.
        found=self.corner_offset(self.positions[who],vector)
        if not found:return 0.
        offset,side=found
        before=self.positions[who]
        target=list(before);target[side]+=math.copysign(min(abs(offset),budget),offset)
        self._move_with_chef_contact(who,tuple(target),boosted,True)
        return math.dist(before,self.positions[who])

    def _knock(self,who,unit):
        """Start a dash knockback along unit (see _move_with_chef_contact). A chef pinned against a cabinet
        or wall that way is not moved and keeps working; one knocked away stops work, keeping its progress,
        and a reporting chef's browser follows the engine until the chef lands."""
        here=self.positions[who]
        if math.dist(here,self._wall_limited(here,tuple(here[i]+unit[i]*self.rules.sprint_push for i in (0,1))))<.1:return
        if self.chefs[who].job and self.chefs[who].job.working:self.stop(who)
        self.knockback[who]={'unit':unit,'start':self.time,'done':0.}
        if self.reported[who]:self._resync(who,'knocked')
        self.emit(f'{NAMES[who]}被推开',kind='knocked',actor=who)

    def _knockback_step(self,who):
        """The knockback distance due by now (sprint_push cells over sprint_push_duration, eased out), stopped
        by walls and by the other chef."""
        k=self.knockback[who];d=self.rules.sprint_push_duration
        t=1. if d<=0 else min(1.,(self.time-k['start'])/d)
        reach=self.rules.sprint_push*(1.-(1.-t)**2);step=reach-k['done'];k['done']=reach
        if t>=1.:self.knockback[who]=None
        if step<=1e-9:return
        before=self.positions[who];other=self.positions['jeff' if who=='human' else 'human']
        end=self._wall_limited(before,tuple(before[i]+k['unit'][i]*step for i in (0,1)))
        fraction=contact_fraction(before,end,other,self.rules.chef_separation)
        self.positions[who]=tuple(before[i]+(end[i]-before[i])*fraction for i in (0,1))
        self.chefs[who].location=tile_key(self.anchor(who))

    def _push_chef(self,other,delta):
        # Active interactions are anchored: contact must not displace the chef,
        # interrupt shared progress or invalidate station/ground reservations.
        job=self.chefs[other].job
        if job and job.working:
            return
        before=self.positions[other]
        after=self._wall_limited(before,tuple(before[i]+delta[i] for i in (0,1)))
        self.positions[other]=after
        self.chefs[other].location=tile_key(self.anchor(other))
        # A pushed reporting chef is no longer where its browser drew it.
        if self.reported[other] and math.dist(before,after)>1e-6:self._resync(other,'pushed')

    @engine_input
    def report_position(self, who, x, y, base, settle=False, press=False):
        """The player's browser says where it has moved its own chef (Overcooked-style local movement).

        The engine walks there with its own physics on the next steps; `settle` walks there now, as far
        as the speed budget allows, before an interaction uses the position. Reports made before the
        latest resync (`base` behind) are ignored. `press`: the browser is pressing into the other chef
        and follows the engine, which walks with the held direction until a plain report arrives."""
        if self.ended or base != self.resync[who] or self.knockback[who]:return False
        target=(float(x),float(y))
        if not all(math.isfinite(v) for v in target):return False
        self.reported[who]=True
        self.report_press[who]=bool(press)
        if press:
            self.report_target[who]=None;self.report_stalled[who]=0.
            return True
        if math.dist(target,self.positions[who])>REPORT_MAX_LEAD:
            self._resync(who,'too_far');return False
        self.report_target[who]=target
        self.report_stalled[who]=0.
        self.report_best[who]=math.dist(target,self.positions[who])
        if settle:self._chase(who,0.)
        return True

    def _resync(self, who, reason):
        self.resync[who]+=1
        self.report_target[who]=None
        self.report_stalled[who]=0.
        self.emit(f'{NAMES[who]}的位置以引擎为准',kind='position_resync',actor=who,reason=reason,
                  position=tuple(round(v,4) for v in self.positions[who]))

    def _chase(self, who, seconds):
        """Walk a reporting chef toward its reported point with the keyboard walking physics."""
        target=self.report_target[who]
        if target is None or self.chefs[who].job:return
        start=self.positions[who];gap=math.dist(start,target)
        if gap<1e-6:
            self.report_target[who]=None;return
        step=min(gap,self.report_budget[who])
        boosted=self.time<self.sprint_until[who]-1e-8
        if step>1e-9:
            end=tuple(start[i]+(target[i]-start[i])*step/gap for i in (0,1))
            if self.nav.clear_walk_line(start,end):
                self._move_with_chef_contact(who,end,boosted)
            else:
                # Slide along the blocking edge, axis by axis, as keyboard walking does.
                for axis in (0,1):
                    here=self.positions[who];candidate=list(here);candidate[axis]=end[axis]
                    if abs(candidate[axis]-here[axis])>1e-9:self._move_with_chef_contact(who,tuple(candidate),boosted)
            moved=math.dist(start,self.positions[who])
            self.report_budget[who]=max(0.,self.report_budget[who]-moved)
            if boosted:self._nudge_food(who,start,self.positions[who])
            self.chefs[who].location=tile_key(self.anchor(who))
        else:
            moved=0.
        if self.report_target[who] is None:return  # resynced by a push during the walk
        gap=math.dist(self.positions[who],target)
        if gap<1e-6:
            self.report_target[who]=None;self.report_stalled[who]=0.
        elif gap<self.report_best[who]-.01:
            self.report_best[who]=gap;self.report_stalled[who]=0.
        else:
            # Not getting closer (blocked, or sliding to and fro along the other chef): the engine's
            # position stands and the browser takes it.
            self.report_stalled[who]+=seconds
            if self.report_stalled[who]>=REPORT_STALL-1e-9:self._resync(who,'blocked')

    def _move_with_chef_contact(self,who,end,boosted=False,held=False):
        start=self.positions[who];other_id='jeff' if who=='human' else 'human'
        other=self.positions[other_id];distance=math.dist(start,end)
        if distance<1e-9:return
        direction=tuple((end[i]-start[i])/distance for i in (0,1))
        separation=self.rules.chef_separation
        fraction=contact_fraction(start,end,other,separation)
        if fraction>=1.-1e-8:
            self.positions[who]=self._wall_limited(start,end);return
        # A sprint that reaches the other chef knocks them back once (Overcooked's dash); two sprinting chefs
        # both bounce and both sprints end. Sustained normal pressure only nudges.
        if boosted and other_id not in self.bumped_chefs[who]:
            self.bumped_chefs[who].add(other_id)
            gap=math.dist(start,other);away=tuple((other[i]-start[i])/gap for i in (0,1)) if gap>1e-9 else direction
            if self.time<self.sprint_until[other_id]-1e-8:
                self.sprint_until[who]=self.sprint_until[other_id]=self.time
                self._knock(who,tuple(-v for v in away))
            self._knock(other_id,away)
        elif not boosted:self._push_chef(other_id,tuple(d*distance*.18 for d in direction))
        other=self.positions[other_id]
        fraction=contact_fraction(start,end,other,separation)
        point=tuple(start[i]+(end[i]-start[i])*fraction for i in (0,1))
        point=self._wall_limited(start,point);self.positions[who]=point
        if fraction>=1.-1e-8:return
        gap=math.dist(point,other)
        if gap<1e-9:return
        normal=tuple((point[i]-other[i])/gap for i in (0,1))
        tangent=(-normal[1],normal[0])
        alignment=sum(tangent[i]*direction[i] for i in (0,1))
        if alignment < -1e-8:tangent=tuple(-v for v in tangent)
        elif abs(alignment)<=1e-8:
            # Same right-hand bias for every actor; opposing movers separate.
            right=(-direction[1],direction[0])
            if sum(tangent[i]*right[i] for i in (0,1))<0:tangent=tuple(-v for v in tangent)
        remaining=distance*(1.-fraction)
        for sign in (1.,-1.):
            # Held-direction walking never slides back against the walk: pressed into a chef who cannot
            # give way, the chef stays put instead of stepping back and pressing in again (a jitter in
            # narrow corridors). Routed walking keeps its reviewed behaviour.
            if held and sign*sum(tangent[i]*direction[i] for i in (0,1))< -1e-8:continue
            slide=tuple(point[i]+sign*tangent[i]*remaining for i in (0,1))
            slide=self._wall_limited(point,slide)
            if math.dist(point,slide)>1e-6 and contact_fraction(point,slide,other,separation)>=1.-1e-8:
                self.positions[who]=slide;break

    def place(self, key):
        return self.stations[key] if key in self.stations else self.floor_places[key]

    def cell(self, key):
        if key in self.equipment:
            return self.equipment[key]['access']
        if key not in self.floor_places:
            raise ValueError('未知地面位置')
        _, x, y = key.split('_')
        return int(x), int(y)

    def anchor(self, who):
        p = self.positions[who]
        return min(self.floor, key=lambda c: (math.dist(c, p), c[1], c[0]))

    @property
    def at_walk_limit(self):
        return bool(self.rules.operate_at_walk_limit and self.rules.cabinet_clearance)

    def at_station_face(self, who, target):
        """Already standing where walking toward one of the station's faces stops."""
        station=self.equipment.get(target)
        if not station or station.get('reach')=='corner':return False
        here=self.positions[who];anchor=self.anchor(who)
        for cell in station.get('cells',[station['cell']]):
            if abs(cell[0]-anchor[0])+abs(cell[1]-anchor[1])!=1:continue
            axis=0 if cell[0]!=anchor[0] else 1
            spot=self.operation_point(target,anchor)
            if abs(here[axis]-spot[axis])<=.02 and abs(here[1-axis]-cell[1-axis])<=.5:return True
        return False

    def path(self, who, target):
        if target in self.equipment:
            station=self.equipment[target]
            shared=self.shared_access(who,target)
            # Never repositioned at a station it already faces (or stands against): work where it stands,
            # unless a shared job needs another side than this one.
            here=(self.station_ahead(who)==target or (self.at_walk_limit and self.at_station_face(who,target))
                  or self.space_pick[who]==target)
            if here and (not shared or self.station_side(target,self.positions[who]) in shared):
                return [self.positions[who]]
            access=[station['access']] if station.get('reach')=='corner' else sorted({n for c in station.get('cells',[station['cell']]) for n in self.nav.neighbors(c)})
            if shared is not None and shared:access=shared
            other='jeff' if who=='human' else 'human'
            taken=[self.positions[other]]+([self.routes[other]['points'][-1]] if self.routes.get(other) else [])
            free=[cell for cell in access if all(math.dist(self.operation_point(target,cell),p)>=CHEF_SEPARATION for p in taken)]
            if free:access=free
            routes = [self.nav.shortest_path(self.positions[who],self.operation_point(target,cell)) for cell in access]
            if not routes:raise ValueError('工位没有可操作的一侧')
            return min(routes,key=lambda route:sum(math.dist(a,b) for a,b in zip(route,route[1:])))
        return self.nav.shortest_path(self.positions[who],self.cell(target))

    def shared_capability(self, target):
        """The capability this station lets several chefs work on together, if any."""
        kind=self.rules.station_types.get(target)
        shared=self.rules.types[kind].get('shared_work',{}) if kind else {}
        return next((cap for cap,rule in shared.items() if rule['max_workers']>1),None)

    def shared_access(self, who, target):
        """Reserve a perpendicular, reachable side; never stack two chefs."""
        if target not in self.equipment:return None
        kind=self.shared_capability(target)
        if not kind:return None
        other=next((p for p,a in self.chefs.items() if p!=who and a.job
                    and a.job.action.target==target and a.job.action.kind==kind),None)
        if other is None:return None
        others=[p for p,a in self.chefs.items() if p!=who and a.job and a.job.action.target==target and a.job.action.kind==kind]
        if len(others)>=self.rules.max_workers(target,kind):return []
        station=self.equipment[target]
        if station.get('reach')=='corner':return []
        center=station['cell'];access=self.nav.neighbors(center)
        route=self.routes.get(other)
        point=route['points'][-1] if route else self.positions[other]
        occupied=self.station_side(target,point)
        ox,oy=occupied[0]-center[0],occupied[1]-center[1]
        return [a for a in access if (a[0]-center[0])*ox+(a[1]-center[1])*oy==0
                and math.dist(self.operation_point(target,a),point)>.4]

    def station_side(self, target, point):
        """The tile beside the station on the side ``point`` is on (the face a chef there works from)."""
        station=self.equipment[target]
        cell=min(station.get('cells',[station['cell']]),key=lambda c:math.dist(c,point))
        dx,dy=point[0]-cell[0],point[1]-cell[1]
        return (cell[0]+(1 if dx>0 else -1),cell[1]) if abs(dx)>=abs(dy) else (cell[0],cell[1]+(1 if dy>0 else -1))

    def can_share_work(self, who, kind, target):
        if kind!=self.shared_capability(target):return False
        station=self.stations[target]
        return not station.fire and not self.chefs[who].hand and bool(self.shared_access(who,target))

    def _centred(self, who, target):
        """Where a chef working in place slides to first: the station's centre line along its run, at the
        same distance from it (never a step toward it), at most 0.6 cells (about 0.1 s of walking). None when already there,
        blocked or too near the other chef."""
        here=self.positions[who];cell=min(self.equipment[target].get('cells',[self.equipment[target]['cell']]),key=lambda c:math.dist(c,here))
        side=self.station_side(target,here)
        point=(cell[0],here[1]) if side[0]==cell[0] else (here[0],cell[1])
        other=self.positions['jeff' if who=='human' else 'human']
        if not 1e-6<math.dist(here,point)<=.6 or not self.nav.clear_walk_line(here,point) or math.dist(point,other)<CHEF_SEPARATION:return None
        return point

    def operation_point(self, target, access):
        """Move an explicitly enabled access endpoint toward its working edge.

        Shared by cutting, washing, taking, putting, serving and station travel.
        North approaches stay behind the surface; side wrists face its center;
        south approaches keep shoes below the cabinet fascia. Authored diagonal
        corner access keeps its explicit endpoint.
        """
        station=self.equipment[target]
        cell=station['cell']
        dx,dy=cell[0]-access[0],cell[1]-access[1]
        if station.get('reach')=='corner' or abs(dx)+abs(dy)!=1:return access
        facing={(0,1):'down',(0,-1):'up',(1,0):'right',(-1,0):'left'}[(dx,dy)]
        inset=self.operation_insets.get(target,{}).get(facing,0.)
        if not inset:return access
        if inset<0:
            # Step back only as far as the floor behind allows (narrow aisles keep the reference point).
            for scale in (1.,.6,.3):
                point=(access[0]+dx*inset*scale,access[1]+dy*inset*scale)
                if self.nav.clear_walk_line(access,point):return point
            return access
        # Centred on the side: a routed chef's feet sit on the station's row (or column) centre.
        # A chef whose Space pick is already the station, straight ahead, works in place (see path).
        point=(access[0]+dx*inset,access[1]+dy*inset)
        if not 0<=inset<.5 or not self.nav.clear_walk_line(access,point):
            raise ValueError('操作停靠点超出安全地面')
        return point

    def travel_time(self, chef, target):
        who = next(who for who, a in self.chefs.items() if a is chef)
        points = self.path(who, target)
        return sum(math.dist(a, b) for a, b in zip(points, points[1:])) / self.rules.walk_speed

    def occupied_floor(self, who, excluding=None):
        cells = {self.cell(item.location) for key, item in self.ground.items() if key != excluding}
        cells |= {self.cell(p['target']) for p in self.projectiles.values() if p['target'] in self.floor_places}
        cells |= {self.cell(key) for key, owner in self.drop_locks.items() if owner != who and key in self.floor_places}
        return cells

    def drop_cell(self, who):
        occupied = self.occupied_floor(who)
        origin = self.anchor(who)
        return next((cell for cell in [origin] + self.nav.neighbors(origin) if cell not in occupied), None)

    def swap_cell(self, who, target, incoming=None):
        occupied = self.occupied_floor(who, excluding=incoming)
        origin = tuple(round(v) for v in self.path(who,target)[-1]) if target in self.equipment else self.cell(target)
        return next((p for p in [origin] + self.nav.neighbors(origin) if p not in occupied), None)

    def clear_throw_line(self, start, end):
        # Segment vs closed wall tiles; even a corner clip blocks the throw.
        for wall in self.walls:
            low, high = 0., 1.
            for axis in (0, 1):
                delta = end[axis] - start[axis]
                left, right = wall[axis]-.5, wall[axis]+.5
                if abs(delta) < 1e-9:
                    if not left <= start[axis] <= right:
                        low, high = 1., 0.
                        break
                else:
                    a, b = (left-start[axis])/delta, (right-start[axis])/delta
                    low, high = max(low, min(a,b)), min(high, max(a,b))
            if low <= high:
                return False
        return True

    def can_throw(self, who):
        return self.rules.throw_enabled and self.throw_range(who) is not None

    def throw_range(self, who):
        # Loose ingredients fly the full throw range; other held items (plates, plated food,
        # pots) pass at the ruleset's shorter pass range, if it allows passing. The extinguisher never flies.
        return self.rules.throw_reach(self.chefs[who].hand)

    def can_throw_to(self, who, target):
        if not self.can_throw(who):return False
        if target in self.equipment:
            cell = tuple(self.equipment[target]['cell'])
            return (self.throw_station(who,cell) == target
                    and math.dist(self.positions[who],cell) <= self.throw_range(who)+1e-8
                    and self.clear_throw_line(self.positions[who],cell))
        if target not in self.floor_places:
            return False
        cell = self.cell(target)
        return (cell not in self.occupied_floor(who)
                and math.dist(self.positions[who], cell) <= self.throw_range(who) + 1e-8
                and self.clear_throw_line(self.positions[who], cell))

    def throw_station(self, who, cell):
        """The station a thrown ingredient coming down on ``cell`` rests on, as in Overcooked 2: an empty
        board or counter, or an empty pan on a stove that cooks it. None: it falls to the floor."""
        hand = self.chefs[who].hand
        key = next((k for k in self.boards + self.counters + self.pots
                    if tuple(cell) in map(tuple, self.equipment[k].get('cells', [self.equipment[k]['cell']]))), None)
        if key is None or not self.rules.throwable(hand) or not self.station_catches(key, hand, who):
            return None
        return key

    def station_catches(self, key, food, who=None):
        s = self.stations[key]
        if s.fire or s.lock is not None or self.board_reserved(key, who):
            return False
        if key in self.pots:
            return bool(s.pot_id and not s.food and self.rules.potable(food, self.rules.vessels.get(s.pot_id)))
        return s.food is None

    def board_reserved(self, target, who=None):
        return (any(p['target']==target for p in self.projectiles.values())
                or (target in self.drop_locks and self.drop_locks[target] != who))

    def throw_landing(self, who, target):
        """Clip a requested ray at range/first wall; reserve a real free floor tile."""
        start = self.positions[who]
        reach = self.throw_range(who)
        delta = (target[0]-start[0], target[1]-start[1])
        distance = math.hypot(*delta)
        scale = min(1., reach/distance) if distance else 1.
        end = (start[0]+delta[0]*scale, start[1]+delta[1]*scale)
        limit = 1.
        for x, y in self.walls:
            low, high = 0., 1.
            for axis, center in enumerate((x,y)):
                d = end[axis]-start[axis]
                if abs(d) < 1e-9:
                    if not center-.5 <= start[axis] <= center+.5:
                        low, high = 1., 0.; break
                else:
                    a, b = (center-.5-start[axis])/d, (center+.5-start[axis])/d
                    low, high = max(low,min(a,b)), min(high,max(a,b))
            if low <= high:
                limit = min(limit, max(0., low-1e-6))
        end = tuple(start[i]+(end[i]-start[i])*limit for i in (0,1))
        occupied = self.occupied_floor(who)
        def available(cell):
            return (cell in self.floor and cell not in occupied
                    and math.dist(start,cell) <= reach+1e-8
                    and self.clear_throw_line(start,cell))
        cell = tuple(math.floor(v+.5) for v in end)
        other = 'jeff' if who == 'human' else 'human'
        # A missed/busy catch lands beside the chef, never on top of their work.
        if math.dist(end,self.positions[other]) <= self.rules.catch_radius:
            candidates = sorted(self.nav.neighbors(self.anchor(other)),key=lambda p:(math.dist(p,end),p))
            beside = next((p for p in candidates if available(p)),None)
            if beside is not None:
                return tile_key(beside), end
            return None
        station = self.throw_station(who, cell)
        if station:
            return station, tuple(cell)
        if available(cell):
            return tile_key(cell), tuple(cell)
        if cell in self.floor and cell in occupied:
            # Resolve competing throws locally and deterministically. Reserve the
            # actual landing cell, so two items never share a pickup location.
            candidates = sorted(self.nav.neighbors(cell),key=lambda p:(math.dist(p,end),math.dist(p,start),p))
            beside = next((p for p in candidates if available(p)),None)
            return (tile_key(beside),tuple(beside)) if beside is not None else None
        # Walk the same ray back towards the thrower. No teleporting across walls.
        for i in range(1, int(math.dist(start,end)*40)+2):
            length = math.dist(start,end)
            fraction = max(0., 1-i*.025/max(length,.025))
            point = tuple(start[j]+(end[j]-start[j])*fraction for j in (0,1))
            candidate = tuple(math.floor(v+.5) for v in point)
            if available(candidate):
                return tile_key(candidate), tuple(candidate)
        return None

    def throw_action(self, who, target, key=None, toward=None):
        """Throw toward ``target``; it comes down where throw_landing says (partner, station or floor)."""
        hand = self.chefs[who].hand
        if not self.can_throw(who) or self.ended:
            return None
        landing = self.throw_landing(who,target)
        if not landing:
            return None
        place, aim = landing
        where = self.place(place).name
        label = (f'抛给队友（接不住时落到{where}）' if key == 'throw partner'
                 else f'向{toward}抛出手中物品（落到{where}）' if toward else f'抛出手中物品（落到{where}）')
        return Action(key or f'throw {target[0]:g} {target[1]:g}', label, 'throw', place, (hand.id, place, aim[0], aim[1]))

    def handoff_target(self, who):
        other = 'jeff' if who == 'human' else 'human'
        landing = self.throw_landing(who,self.positions[other])
        return landing[0] if landing else None

    @engine_input
    def set_manual(self, who, dx, dy):
        length = math.hypot(dx,dy)
        vector = (dx/max(1.,length),dy/max(1.,length))
        if vector == self.manual[who]:
            return
        if length:
            self.stop(who)
            self.aim[who] = (dx/length, dy/length)
        self.manual[who] = vector
        self.chefs[who].location = tile_key(self.anchor(who))
        self.emit(f'{NAMES[who]}'+('手动移动' if length else '停止手动移动'),
                  kind='manual_move',actor=who,direction=vector)

    def partner_signature(self, who):
        other = 'jeff' if who == 'human' else 'human'
        donor, plate = self.chefs[who].hand, self.chefs[other].hand
        def item_signature(item):
            if not item:return None
            return (item.id,item.stage,item.plate_id,tuple(item.components),
                    item_signature(item.contents))
        return (repr(item_signature(donor)),repr(item_signature(plate)))

    def can_plate_partner(self, who, nearby=False):
        other = 'jeff' if who == 'human' else 'human'
        donor, plate = self.chefs[who].hand, self.chefs[other].hand
        ingredient=donor.contents if donor and donor.stage=='pot' else donor
        compatible=self.can_add(plate,ingredient) or (self.rules.multi_component and self.can_merge_plates(plate,donor))
        # Do not change a hand while its existing operation is consuming it.
        receiver=self.chefs[other]
        return bool(compatible and not (receiver.job and receiver.job.working)
                    and (not nearby or (math.dist(self.positions[who],self.positions[other]) <= 1.1
                                        and self.nav.clear_walk_line(self.positions[who],self.positions[other]))))

    def actions(self, who):
        actions = [a for a in super().actions(who) if a.kind != 'drop']
        actions = [a for a in actions if not (a.kind in ('put_board','put_counter','put_pot') and self.board_reserved(a.target))]
        actions = [a for a in actions if not (a.kind in ('chop','wash')
                   and self.shared_access(who,a.target)==[])]
        if self.ended:
            return actions
        chef = self.chefs[who]
        discard = next((a for a in actions if a.key=='discard'),None)
        for extra in (self.bins[1:] if discard else []):
            actions.append(Action('discard '+extra,discard.label.replace(self.stations[self.bins[0]].name,self.stations[extra].name),discard.kind,extra,self.signature(who,extra)))
        if any(self.manual[who]) and not chef.job:
            actions.append(Action('stop','停止手动移动','stop'))
        if chef.hand:
            actions = [a for a in actions if a.kind not in TAKE_KINDS or self.swap_cell(
                who, a.target, a.expected[1] if a.kind == 'pickup' else None) is not None]
        target = self.drop_cell(who)
        if chef.hand and target is not None and not (chef.job and chef.job.action.kind == 'drop'):
            location = tile_key(target)
            actions.append(Action('drop', f'把手中物品放到{self.place(location).name}（可捡回、不扣钱）',
                                  'drop', location, (chef.hand.id, location)))
        if self.can_throw(who) and not (chef.job and chef.job.action.kind == 'throw'):
            other = 'jeff' if who == 'human' else 'human'
            action = self.throw_action(who,self.positions[other],'throw partner')
            if action: actions.append(action)
            # The player's throws: an aim direction, always to full reach.
            for name, (step, toward) in THROW_DIRECTIONS.items():
                action = self.aimed_throw(who, step, key='throw '+name, toward=toward)
                if action: actions.append(action)
        if self.can_plate_partner(who):
            other = 'jeff' if who == 'human' else 'human'
            actions.append(Action('plate partner','走近，把食材加入队友手中的盘（容器留在原持有者手中）',
                                  'plate_partner',tile_key(self.anchor(other)),self.partner_signature(who)))
        # Both chefs can walk into the other on purpose; contact then pushes (sprint: one bounded shove).
        other = 'jeff' if who == 'human' else 'human'
        if self.rules.approach_partner and math.dist(self.positions[who], self.positions[other]) > self.rules.chef_separation + .05:
            actions.append(Action('go partner', '走到对方厨师当前的位置（接触时会推挤）', 'go', tile_key(self.anchor(other))))
        # Ground clicks are player movement intents. Jev can choose station positions or any food.
        if who == 'human':
            for cell in sorted(self.floor):
                key = tile_key(cell)
                if math.dist(self.positions[who], cell) > .01:
                    action = Action(f'go {key}', f'走到{self.place(key).name}', 'go', key)
                    if not chef.job or chef.job.action.key != action.key:
                        actions.append(action)
        return actions

    @engine_input
    def face(self, who, dx, dy):
        """Aim as the player's page last drew it (sent with Space), so the station it highlighted is picked."""
        length=math.hypot(dx,dy)
        if not length or not math.isfinite(length):return False
        self.aim[who]=(dx/length,dy/length)
        self._face_vector(who,dx,dy)
        return True

    @engine_input
    def pick_station(self, who, target):
        """Space picked this station (see selectable_stations): the next start works it in place."""
        self.space_pick[who]=target if target in self.selectable_stations(who) else None
        return self.space_pick[who] is not None

    def selectable_stations(self,who):
        """Stations Space may pick, best first (see SELECT_AHEAD): ahead of the aim, around the chef's cell."""
        ax,ay=self.aim_of(who);x,y=self.positions[who];cx,cy=self.anchor(who)
        probe=(x+ax*SELECT_AHEAD,y+ay*SELECT_AHEAD-SIDE_HAND_RISE*abs(ax))
        hx,hy=self.hand_cell(who)
        ranked={}
        for key,e in self.equipment.items():
            corner=e.get('reach')=='corner'
            if corner and tuple(e['access'])!=(cx,cy):continue
            for c in (e.get('cells',[e['cell']]) if not corner else [e['cell']]):
                ox,oy=(c[0]-cx,c[1]-cy) if corner else (c[0]-hx,c[1]-hy)
                if not corner and max(abs(ox),abs(oy))!=1:continue
                if ax*ox+ay*oy<=1e-6:continue
                score=(ax*ox+ay*oy)/math.hypot(ox,oy)+(SELECT_STRAIGHT_BONUS if abs(ox)+abs(oy)==1 else 0)
                if max(abs(x-c[0]),abs(y-c[1]))-.5>SELECT_REACH+1e-9:continue
                rank=(-round(score,6),round(math.dist(probe,c),6),key)
                if key not in ranked or rank<ranked[key]:ranked[key]=rank
        return [key for key,_ in sorted(ranked.items(),key=lambda kv:kv[1])]

    def hand_cell(self,who):
        """The floor cell the hands are over: Space's directions are taken from it (raised when aiming
        sideways, as the knife is drawn), so the board the knife points at is the straight one."""
        x,y=self.positions[who];hand=(x,y-SIDE_HAND_RISE*abs(self.aim_of(who)[0]))
        return min(self.floor,key=lambda c:(math.dist(c,hand),c[1],c[0]))

    def selected_station(self,who):
        found=self.selectable_stations(who)
        return found[0] if found else None

    def station_ahead(self,who):
        """The Space pick when it is straight ahead of the hands' cell (or an authored corner reached from
        here), never a diagonal one: a chef there works in place instead of walking to the station."""
        key=self.selected_station(who)
        if not key:return None
        e=self.equipment[key];hx,hy=self.hand_cell(who)
        return key if e.get('reach')=='corner' or any(abs(c[0]-hx)+abs(c[1]-hy)==1 for c in e.get('cells',[e['cell']])) else None

    def facing_candidates(self,who,station=None):
        """What Space acts on, best first (Overcooked 2-style, no remembered selection).

        The selected station (see selectable_stations; `station` picks another one from that list,
        as the player's page highlighted it), then a loose item on the aimed tile, one at the feet
        and the partner standing there; the aimed floor tile comes last. Stations beside or behind
        are never picked. Returns (candidates, whether a station is ahead): facing a counter that is
        still out of reach never drops the held item on the floor instead.
        """
        x,y=self.anchor(who)
        ax,ay=self.aim_of(who)
        # The neighbouring cell the aim points into (eight directions).
        dx,dy=((1 if ax>0 else -1) if abs(ax)>=.38 else 0),((1 if ay>0 else -1) if abs(ay)>=.38 else 0)
        front=(x+dx,y+dy)
        stations=self.selectable_stations(who)
        if station not in stations:station=stations[0] if stations else None
        ahead=bool(station) or any(front in e.get('cells',[e['cell']]) for e in self.equipment.values())
        # As Overcooked 2's ScanForObject: the picked station and the loose items on the aimed tile and at
        # the feet go nearest-first to a point SELECT_AHEAD ahead (the station's at hand height when
        # aiming sideways); ties keep station, aimed tile, feet.
        px,py=self.positions[who]
        ranked=[]
        if station:
            cell=min(self.equipment[station].get('cells',[self.equipment[station]['cell']]),key=lambda c:math.dist(c,(px,py)))
            ranked.append((math.dist((px+ax*SELECT_AHEAD,py+ay*SELECT_AHEAD-SIDE_HAND_RISE*abs(ax)),cell),0,station))
        for order,cell in ((1,front),(2,(x,y))):
            for key,item in self.ground.items():
                if self.cell(item.location)==cell:
                    ranked.append((math.dist((px+ax*SELECT_AHEAD,py+ay*SELECT_AHEAD),self.ground_position(item)),order,'item:'+key));break
        out=[key for *_,key in sorted(ranked,key=lambda r:(round(r[0],6),r[1]))]
        other='jeff' if who=='human' else 'human'
        if self.anchor(other)==front:out.append('partner')
        out.append(tile_key(front))
        return out,ahead

    def facing_interaction(self,who,mode='hands',actions=None,station=None):
        """(target, action) for Space ('hands') or E ('use').

        Space does whatever the target needs: take, put, plate, serve, and also
        chop, wash or extinguish. E only chops, washes or extinguishes. A candidate
        with nothing to do falls through to the next; facing a station never
        drops the held item on the floor instead.
        """
        actions=self.actions(who) if actions is None else actions
        chef=self.chefs[who]
        # Work is sticky, as in Overcooked: no button stops it; walking away does.
        if chef.job and chef.job.working:return None,None
        kinds=USE_KINDS if mode=='use' else None
        candidates,ahead=self.facing_candidates(who,station)
        if mode=='use':candidates=[c for c in candidates if c in self.equipment]
        for target in candidates:
            if target.startswith('floor_') and ahead:break
            action=self.quick_interaction(who,actions,preferred=target,kinds=kinds)
            if action:return target,action
        return (candidates[0] if candidates else None),None

    def interaction_target(self,who,preferred=None):
        """Explicit target wins; otherwise what the chef faces (see facing_interaction)."""
        if preferred:return preferred
        target,_=self.facing_interaction(who)
        return target

    def interaction_cell(self,who,target):
        if target in self.equipment:return min(self.equipment[target].get('cells',[self.equipment[target]['cell']]),key=lambda c:math.dist(c,self.positions[who]))
        if target=='partner':return self.anchor('jeff' if who=='human' else 'human')
        if target and target.startswith('item:'):
            item=self.ground.get(target[5:]);return self.cell(item.location) if item else None
        # Facing a wall or the map edge yields a non-floor key: there is no cell to highlight.
        if target and target.startswith('floor_') and target not in self.floor_places:return None
        return self.cell(target) if target else None

    def quick_interaction(self, who, actions=None, preferred=None, kinds=None):
        """One local, legal action. This is a player control, not an AI policy."""
        chef = self.chefs[who]
        actions = self.actions(who) if actions is None else actions
        if chef.job and chef.job.working:return None
        priority = {'swap_pot':0,'swap_ground_pot':0,'load_ground':0,'assemble_ground':0,'load_counter':0,'plate_ground':0,'plate_pot':0,'plate_counter':0,'plate_from_counter':0,
                    'plate_partner':0,'extinguish':0,'put_board':1,'put_pot':1,'return_pot':1,
                    'put_counter':1,'put_sink':1,'put_tool':1,'serve':1,'wash':1,'chop':1,
                    'pickup':2,'take_board':3,'take_plate':3,'take_counter':3,'take_return':3,
                    'take_sink':3,'take_tool':3,'fetch':4,'lift_pot':4,'discard':1,'empty_pot':1,'assemble':0,'merge_plates':0}
        nearby=[]
        # A station Space picked (in reach and ahead, see selectable_stations) is worked where the chef stands.
        picked=set(self.selectable_stations(who)) if preferred in self.equipment else set()
        for a in actions:
            if a.kind not in priority:continue
            if kinds and a.kind not in kinds:continue
            if preferred:
                if preferred.startswith('item:'):
                    if a.kind not in ('pickup','plate_ground','load_ground','swap_ground_pot','assemble_ground') or a.expected[1]!=preferred[5:]:continue
                elif preferred=='partner':
                    if a.kind!='plate_partner':continue
                elif a.target!=preferred:continue
            # Full hands swap only by aiming at that loose ingredient (actions() applies hand_swap_allowed).
            if chef.hand and a.kind=='pickup' and not (preferred and preferred.startswith('item:')):continue
            if a.kind=='plate_partner':
                if not self.can_plate_partner(who,True):continue
                distance=math.dist(self.positions[who],self.positions['jeff' if who=='human' else 'human'])
            elif a.target in picked:
                distance=math.dist(self.positions[who],self.interaction_cell(who,a.target))
            else:
                origin=self.interaction_cell(who,a.target)
                distance=math.dist(self.positions[who],origin)
                if distance>1.5:continue
                try:route=self.path(who,a.target)
                except ValueError:continue
                if sum(math.dist(x,y) for x,y in zip(route,route[1:]))>1.5:continue
            nearby.append((round(distance,5),priority[a.kind],a.key,a))
        closest=min(nearby,key=lambda row:row[:3]) if nearby else None
        if self.interaction_hint(who) and (not preferred or preferred=='serve'):
            distance=math.dist(self.positions[who],self.interaction_cell(who,'serve'))
            if closest is None or distance<=closest[0]+1e-5:return None
        if closest:return closest[3]
        if kinds or (preferred and not preferred.startswith('floor_')):return None
        return next((a for a in actions if a.kind=='drop'),None) if chef.hand else None

    def forward_throw(self, who):
        """Throw the held item straight ahead along the facing (see aimed_throw)."""
        return self.aimed_throw(who,FACING_STEPS[self.facing[who]],key='throw forward')

    def aimed_throw(self, who, direction, key='throw aimed', toward=None):
        """Throw the held item along ``direction`` (Overcooked-style: hold to aim, release).

        Aims at the partner when they stand roughly in that direction within reach, otherwise
        at full reach; walls and range clip it as for any throw.
        """
        if not self.chefs[who].hand or not self.can_throw(who):return None
        length=math.hypot(*direction)
        if not length:return None
        dx,dy=direction[0]/length,direction[1]/length
        (x,y),reach=self.positions[who],self.throw_range(who)
        other=self.positions['jeff' if who=='human' else 'human']
        ahead=(other[0]-x)*dx+(other[1]-y)*dy;side=abs((other[0]-x)*dy-(other[1]-y)*dx)
        aim=other if 0<ahead<=reach and side<=self.rules.catch_radius else (x+dx*reach,y+dy*reach)
        return self.throw_action(who,aim,key=key,toward=toward)

    def interaction_hint(self, who, preferred=None):
        if preferred and preferred.startswith('floor_'):return '面前没有可操作目标'
        if preferred in self.stations:
            # Name the ingredient a plate already holds, instead of the generic hint.
            plate,held=self.stations[preferred].food,self.chefs[who].hand
            if (plate and plate.plate_id and held and not held.plate_id and held.ingredient
                    and held.ingredient in self.parts(plate)):
                return f'盘里已经有{self.rules.component_labels.get(held.ingredient,held.ingredient)}了'
        if preferred and preferred!='serve':return '选中目标暂不可操作，请靠近或检查物品状态'
        hand=self.chefs[who].hand
        if not hand or not hand.plate_id or self.dish(hand):return '选中目标暂不可操作，请靠近或检查物品状态' if preferred else None
        target=self.interaction_cell(who,'serve')
        if math.dist(self.positions[who],target)>1.5:return '请靠近选中的出餐口' if preferred else None
        route=self.path(who,'serve')
        if sum(math.dist(a,b) for a,b in zip(route,route[1:]))>1.5:return None
        missing=self.rules.missing(self.parts(hand))
        return '暂不能出餐，还缺：'+'、'.join(self.rules.component_labels[x] for x in missing)

    @engine_input
    def stop(self, who):
        self.manual[who] = (0.,0.)
        had_job = bool(self.chefs[who].job)
        super().stop(who)
        if had_job:
            self.chefs[who].location = tile_key(self.anchor(who))
        self.routes.pop(who, None)
        self.drop_locks = {key: owner for key, owner in self.drop_locks.items() if owner != who}

    @engine_input
    def start(self, who, action):
        try:
            return self._start(who, action)
        finally:
            self.space_pick[who]=None

    def _start(self, who, action):
        if action.kind == 'throw':
            hand = self.chefs[who].hand
            if (not self.can_throw(who) or hand.id != action.expected[0]
                    or not self.can_throw_to(who,action.target) or self.ended):
                return False, '抛递目标已变化，请重新选择'
            self.stop(who)
            self.job_serial += 1
            self.chefs[who].job = Job(self.job_serial,action,0,self.c.get('handling_seconds',.15))
            self.emit(f'{NAMES[who]}开始：{action.label}',kind='action_start',actor=who,action=action.key,action_id=self.job_serial)
            return True, '开始抛递'
        if action.kind == 'plate_partner':
            if not self.can_plate_partner(who) or action.expected != self.partner_signature(who) or self.ended:
                return False, '队友或锅中的物品已变化'
            self.stop(who)
            self.job_serial += 1
            self.chefs[who].job = Job(self.job_serial,action,self.travel_time(self.chefs[who],action.target),self.c.get('handling_seconds',.15))
            self.emit(f'{NAMES[who]}开始给队友装盘',kind='action_start',actor=who,action=action.key,action_id=self.job_serial)
            ok, message = True, '开始'
        else:
            ok, message = super().start(who, action)
        if ok and action.kind not in ('continue', 'wait', 'stop'):
            job = self.chefs[who].job
            points = self.path(who, action.target)
            slide = action.kind in USE_KINDS and len(points) == 1 and self._centred(who, action.target)
            if slide:points = [points[0], slide]
            self.routes[who] = {'job_id': job.id, 'points': points, 'slide': bool(slide),
                                'length': sum(math.dist(a,b) for a,b in zip(points,points[1:]))}
            if slide:job.travel = self.routes[who]['length']/self.rules.walk_speed
        return ok, message

    def _face_vector(self, who, dx, dy):
        length=math.hypot(dx,dy)
        if length < 1e-8:return
        self.facing[who] = (('left' if dx<0 else 'right') if abs(dx)>=abs(dy)
                            else ('up' if dy<0 else 'down'))
        self.aim[who] = (dx/length, dy/length)

    def aim_of(self, who):
        """The aim Space's station is picked by: the last held direction while it agrees with the facing
        (keeping its exact angle, e.g. a diagonal), otherwise the facing itself."""
        ax,ay=self.aim[who]
        facing=('left' if ax<0 else 'right') if abs(ax)>=abs(ay) else ('up' if ay<0 else 'down')
        return (ax,ay) if facing==self.facing[who] else FACING_STEPS[self.facing[who]]

    def _travel(self, who, job, seconds):
        route = self.routes.get(who)
        if not route or route['job_id'] != job.id:
            return
        distance = max(0, route['length'] - job.travel * self.rules.walk_speed)
        points = route['points']
        previous = self.positions[who]
        for a, b in zip(points, points[1:]):
            length = math.dist(a, b)
            if distance <= length:
                t = distance / length if length else 1
                self.positions[who] = (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t)
                self._face_vector(who,self.positions[who][0]-previous[0],self.positions[who][1]-previous[1])
                return
            distance -= length
        self.positions[who] = points[-1]
        self._face_vector(who,self.positions[who][0]-previous[0],self.positions[who][1]-previous[1])

    def _reserve_hand_swap(self, who, job):
        if not self.chefs[who].hand or job.action.kind not in TAKE_KINDS:
            return True
        incoming = job.action.expected[1] if job.action.kind == 'pickup' else None
        cell = self.swap_cell(who, job.action.target, incoming)
        if cell is None:
            self.emit(f'{NAMES[who]}附近没有空位换手，物品保持原样', kind='arrival_conflict', actor=who, action_id=job.id)
            return False
        key = tile_key(cell)
        self.swap_slots[job.id] = key
        self.drop_locks[key] = who
        return True

    def _begin_work(self, who, job):
        if not self._begin_work_checked(who,job):return False
        action = job.action
        if action.kind == 'plate_partner':
            target = self.positions['jeff' if who=='human' else 'human']
        elif action.kind == 'throw':
            target = action.expected[2:4]
        elif action.target in self.equipment:
            target = self.interaction_cell(who,action.target)
        else:
            target = self.cell(action.target)
        origin = self.positions[who]
        self._face_vector(who,target[0]-origin[0],target[1]-origin[1])
        return True

    def _begin_work_checked(self, who, job):
        if job.action.kind in ('chop','wash'):
            access=self.shared_access(who,job.action.target)
            if access is not None and self.station_side(job.action.target,self.positions[who]) not in access:
                self.emit('共同操作的位置已被占用，本次操作取消',kind='arrival_conflict',actor=who,action_id=job.id)
                self.stop(who);return False
        if job.action.kind in ('put_board','put_counter') and self.board_reserved(job.action.target):
            self.emit('工位有食材正在飞入，本次放置取消',kind='arrival_conflict',actor=who,action_id=job.id)
            self.stop(who); return False
        if job.action.kind == 'plate_partner':
            if not self.can_plate_partner(who,True) or job.action.expected != self.partner_signature(who):
                self.emit('队友已移动或物品变化，装盘取消',kind='arrival_conflict',actor=who,action_id=job.id)
                self.stop(who); return False
            job.working = True
            return True
        if job.action.kind == 'throw':
            hand = self.chefs[who].hand
            if not hand or hand.id != job.action.expected[0] or not self.can_throw_to(who,job.action.target):
                self.emit(f'{NAMES[who]}的抛递落点不可用，仍拿着物品',kind='arrival_conflict',actor=who,action_id=job.id)
                self.stop(who)
                return False
            self.drop_locks[job.action.target] = who
            job.working = True
            return True
        if job.action.kind == 'drop':
            target = job.action.target
            occupied = self.cell(target) in self.occupied_floor(who)
            if occupied or self.drop_locks.get(target) not in (None, who):
                self.emit(f'{NAMES[who]}发现落点被占用，仍拿着食物', kind='arrival_conflict', actor=who, action_id=job.id)
                self.chefs[who].job = None
                self.routes.pop(who, None)
                return False
        if not super()._begin_work(who, job):
            self.routes.pop(who, None)
            return False
        if job.action.kind == 'drop':
            self.drop_locks[job.action.target] = who
        return True

    def _finish(self, who, job):
        if job.action.kind == 'plate_partner':
            if not self.can_plate_partner(who,True) or job.action.expected != self.partner_signature(who):
                self.emit('装盘时队友或物品变化，物品保持原样',kind='arrival_conflict',actor=who,action_id=job.id)
                self.stop(who); return
            other = 'jeff' if who == 'human' else 'human'
            pot, plate = self.chefs[who].hand, self.chefs[other].hand
            if self.can_merge_plates(plate,pot):
                self.chefs[other].hand,self.chefs[who].hand=self.merge_plates(plate,pot)
            else:
                food=pot.contents if pot.stage=='pot' else pot
                self.chefs[other].hand=self.merge_plate(plate,food)
                if pot.stage=='pot':pot.contents=None
                else:self.chefs[who].hand=None
            self.chefs[who].job = None
            self.emit(f'{NAMES[who]}把食材加入{NAMES[other]}手中的盘',kind='action_done',actor=who,action='plate partner',
                      action_id=job.id,receiver=other)
        elif job.action.kind == 'throw':
            chef = self.chefs[who]
            food = chef.hand
            target = (self.equipment[job.action.target]['cell'] if job.action.target in self.equipment
                      else self.cell(job.action.target))
            duration = max(self.rules.min_flight, math.dist(self.positions[who],job.action.expected[2:4])/self.rules.throw_speed)
            self.projectiles[food.id] = {'food': food, 'target': job.action.target,
                'from': self.positions[who], 'to': tuple(job.action.expected[2:4]), 'started': self.time,
                'lands_at': self.time+duration, 'actor': who, 'catch_at': tuple(job.action.expected[2:4]), 'handoff_id': job.id}
            receiver = self.chefs['jeff' if who == 'human' else 'human']
            if receiver.hand or (receiver.job and receiver.job.action.kind != 'go'):
                # Busy chefs cannot catch: show the reserved landing point too,
                # rather than drawing both ingredients through their hands.
                self.projectiles[food.id]['to'] = tuple(target)
            chef.hand = None
            chef.job = None
            self.emit(f'{NAMES[who]}抛出了 {food.id}，落点为 {target}',kind='thrown',actor=who,item=food.id,action_id=job.id,handoff_id=job.id,
                      stage=food.stage,source=self.positions[who],target=target,aim=tuple(job.action.expected[2:4]))
            self.emit(f'{NAMES[who]}完成动作：抛出物品',kind='action_done',actor=who,action=job.action.key,action_id=job.id)
        else:
            super()._finish(who, job)
        self.routes.pop(who, None)
        self.drop_locks = {key: owner for key, owner in self.drop_locks.items() if owner != who}

    def _keyboard_walk(self, who, vector, seconds):
        """One step of held-direction walking: wall slides, corner slides, contact with the other chef."""
        self._face_vector(who,*vector)
        start = self.positions[who]
        move_start=start
        boosted=max(0.,min(seconds,self.sprint_until[who]-(self.time-seconds)))
        move_seconds=seconds+self.sprint_extra(who,seconds)
        walk=self.rules.walk_speed
        end = tuple(start[i]+vector[i]*walk*move_seconds for i in (0,1))
        if self.nav.clear_walk_line(start,end):
            self._move_with_chef_contact(who,end,boosted>0,True)
        else:
            # Slide along the blocking edge; each axis walks up to the wall, not a step short of it.
            for axis in (0,1):
                if not vector[axis]:continue
                start = self.positions[who]
                candidate = list(start);candidate[axis] += vector[axis]*walk*move_seconds
                self._move_with_chef_contact(who,tuple(candidate),boosted>0,True)
        remaining=walk*move_seconds*math.hypot(*vector)-math.dist(move_start,self.positions[who])
        # Corner slides leave counter notches. Held up by the other chef instead (the full step is clear of
        # walls), sliding aside only to meet them again made a chef jitter in narrow corridors.
        walled=not self.nav.clear_walk_line(move_start,tuple(move_start[i]+vector[i]*walk*move_seconds for i in (0,1)))
        if self.rules.corner_slide and remaining>1e-9 and walled:
            # The rest of this step's distance slides out of the notch and walks on, as the client predicts.
            slid=self._corner_slide(who,vector,remaining,boosted>0)
            left=remaining-slid
            if slid>1e-9 and left>1e-9:
                here=self.positions[who];ahead=tuple(here[i]+vector[i]*left for i in (0,1))
                if self.nav.clear_walk_line(here,ahead):self._move_with_chef_contact(who,ahead,boosted>0,True)
        if boosted>0:self._nudge_food(who,move_start,self.positions[who])
        self.chefs[who].location = tile_key(self.anchor(who))

    def _after_step(self, seconds):
        for who in self.chefs:
            if self.knockback[who]:self._knockback_step(who)
        for who, vector in self.manual.items():
            if self.reported[who]:
                allowance=self.rules.walk_speed*(seconds+self.sprint_extra(who,seconds))*REPORT_SPEED_MARGIN
                self.report_budget[who]=min(REPORT_BUDGET,self.report_budget[who]+allowance)
                if self.report_press[who]:
                    # The browser is pressing into the other chef: walk with the held direction exactly as
                    # keyboard walking does (push an idle chef, slide by a busy one) while it follows.
                    if any(vector) and not self.chefs[who].job:self._keyboard_walk(who,vector,seconds)
                    continue
                # Moved by its browser's reports: the held direction only turns the chef.
                if any(vector):self._face_vector(who,*vector)
                self._chase(who,seconds)
                continue
            if not any(vector): continue
            self._keyboard_walk(who,vector,seconds)
        for key, p in list(self.projectiles.items()):
            if self.time >= p['lands_at']-1e-8:
                del self.projectiles[key]
                self._land(key, p)

    def _land(self, key, p):
        food, target = p['food'], p['target']
        other = 'jeff' if p['actor'] == 'human' else 'human'
        chef = self.chefs[other]
        # As in Overcooked, a throw is caught when it passes within reach on its way, not only where it lands.
        if (not chef.hand and (not chef.job or chef.job.action.kind == 'go')
                and _segment_distance(self.positions[other],p['from'],p.get('catch_at',p['to'])) <= self.rules.catch_radius
                and self.clear_throw_line(p['from'],self.positions[other])):
            chef.hand = food
            self.emit(f'{NAMES[other]}接住了 {key}',kind='caught',item=key,actor=other,handoff_id=p['handoff_id'],outcome='caught',thrower=p['actor'])
            return
        if target in self.equipment:
            station = self.stations[target]
            if self.station_catches(target, food, p['actor']):
                station.food = food
                if target in self.pots:
                    food.stage, station.heating = 'cooking', True
                    self.emit(f'{key} 落进{station.name}的{self.vessel_name(station.pot_id)}，开始加热',kind='landed',handoff_id=p['handoff_id'],
                              outcome='landed_station',item=key,actor=p['actor'],target=target)
                else:
                    self.emit(f'{key} 落到{station.name}，可取走',kind='landed',handoff_id=p['handoff_id'],outcome='landed_station',
                              item=key,actor=p['actor'],target=target)
                return
            # The station changed mid-flight (a pan lifted, food put there): it falls beside it.
            cell = tuple(self.equipment[target]['cell'])
            occupied = self.occupied_floor(p['actor'])
            spot = min((c for c in self.floor if c not in occupied), key=lambda c:(math.dist(c,cell),c), default=None)
            if spot is None:
                raise AssertionError('厨房地面已满，抛出的物品无处落下')
            target = tile_key(spot)
        self.ground[key] = GroundItem(food,target)
        self.emit(f'{key} 落在地上，可拾取',kind='landed',item=key,actor=p['actor'],handoff_id=p['handoff_id'],outcome='landed_floor')

    def fire_neighbors(self, key):
        combustible = {k for k in self.stations if self.rules.combustible(k)}
        if key not in combustible or key not in self.equipment:
            return []
        x,y = self.equipment[key]['cell']
        return sorted(n for n in combustible if n != key and n in self.equipment
                      and abs(self.equipment[n]['cell'][0]-x)+abs(self.equipment[n]['cell'][1]-y)==1)

    def snapshot(self):
        state = super().snapshot()
        for board in self.boards + self.counters + self.pots:
            state['stations'][board]['incoming_item'] = next((key for key,p in self.projectiles.items() if p['target']==board),None)
        state['projectiles'] = [{'id': key, 'stage': p['food'].stage, 'ingredient':p['food'].ingredient, 'plate_id': p['food'].plate_id,
            'components': list(p['food'].components),
            'contents': {'stage': p['food'].contents.stage, 'ingredient': p['food'].contents.ingredient} if p['food'].contents else None,
            # A passed vessel names its kind, so nothing else in flight is drawn as one.
            **({'vessel': self.rules.vessels.get(key)} if p['food'].stage == 'pot' else {}),
            'actor': p['actor'], 'onto': p['target'] if p['target'] in self.equipment else None, 'from': p['from'], 'to': p['to'], 'landing_cell': self.equipment[p['target']]['cell'] if p['target'] in self.equipment else self.cell(p['target']), 'started': p['started'], 'lands_at': p['lands_at']} for key,p in self.projectiles.items()]
        r = self.rules
        state['map'] = {'throw_range': r.throw_range, 'pass_range': r.pass_range, 'throw_speed': r.throw_speed, 'width': self.width, 'height': self.height, 'walls': sorted(self.walls),
                        # Ingredient sources name their item, so the client can pick the source symbol.
                        'equipment': {key: {**e, **({'item': r.sources[key]} if key in r.sources else {})} for key, e in self.equipment.items()},
                        'walk_speed': r.walk_speed,
                        # Exact foot-blocking boxes, so the client can predict held-key movement.
                        'walk_boxes': [list(b) for b in self.nav.walk_boxes], 'walk_clearance': WALK_CLEARANCE, 'chef_separation': r.chef_separation,
                        # An aimed throw targets the teammate within this distance of the aim line (aimed_throw).
                        'catch_radius': r.catch_radius,
                        **({'corner_slide': r.corner_slide} if r.corner_slide else {}),
                        'presentation': self.map_document['presentation'],
                        'layout_version': self.map_document['id']+'-'+str(self.map_document['revision']), 'spawn_rule': 'One chef near the center of each working area; assigned sides are randomized',
                        'movement_rule': '工位可从相邻可达空地就近操作。墙和设备不能穿过；厨师接触时贴边滑动并缓慢推挤，冲刺可轻撞对方至多四分之一格。人类和 AI 共用接触规则，不自动重新规划绕人路线。普通走路可穿过地面食物。',
                        'ground_rule': f'放下优先选脚下或相邻空格。冲刺每次最多推动散落食材{r.sprint_food_nudge:g}格，允许食物重叠；盘子锅具不被推动，不自动装盘，不弹飞或损坏。地面不能切配或加热。',
                        'collision':{'chef_separation':r.chef_separation,'sprint_food_limit':r.sprint_food_nudge,'food_blocks_walking':False,'food_repulsion':False,
                                      'sprint_push':r.sprint_push,'stall_replan_after':r.stall_after}}
        for who, data in state['chefs'].items():
            data['can_throw'] = self.can_throw(who)
            data['throw_range'] = self.throw_range(who) if self.can_throw(who) else None
            data['knocked']=bool(self.knockback[who])
            data['sprint']={'available':self.time>=self.sprint_ready_at[who], 'active_remaining':round(max(0,self.sprint_until[who]-self.time),3), 'cooldown_remaining':round(max(0,self.sprint_ready_at[who]-self.time),3),'multiplier':r.sprint_multiplier,'duration':float(r.sprint_duration),'cooldown_after':float(r.sprint_cooldown)}
            data['handoff_target'] = self.handoff_target(who) if self.can_throw(who) else None
            data['manual_moving'] = any(self.manual[who]) and not self.ended
            data['move_direction'] = self.manual[who]
            if data['manual_moving']:
                data.update(action_kind='manual_move',task='手动移动',working=False)
            data['facing'] = self.facing[who]
            data['position'] = [round(v, 4) for v in self.positions[who]]
            data['resync'] = self.resync[who]
            data['location_name'] = self.place(self.chefs[who].location).name
            data['route'] = self.routes.get(who, {}).get('points', []) if self.chefs[who].job else []
        for item in state['ground']:
            item['position'] = self.ground_position(self.ground[item['food']['id']])
        return state

    def assert_invariants(self):
        super().assert_invariants()
        # Nudge may overlap ground food; reserved projectile destinations remain unique.
        locations = [p['target'] for p in self.projectiles.values()]
        assert len(locations) == len(set(locations)), '同一格有多份在途物品'
        foods = [s.food for s in self.stations.values() if s.food]+[c.hand for c in self.chefs.values() if c.hand]+[g.food for g in self.ground.values()]+[p['food'] for p in self.projectiles.values()]
        assert len({f.id for f in foods}) == len(foods), '在途物品重复'
        for who in self.chefs:
            assert self.nav.walkable_point(self.positions[who]), '角色进入障碍物'
        for key, owner in self.drop_locks.items():
            job = self.chefs[owner].job
            assert job and job.working and ((job.action.kind in ('drop','throw') and job.action.target == key) or self.swap_slots.get(job.id) == key)
