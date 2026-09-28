"""Spatial whitebox: the same kitchen rules on a walkable grid, without AI policy."""
from functools import lru_cache
import heapq
import math
import random
from kitchen import Kitchen, Action, Station, NAMES, TAKE_KINDS, Job, GroundItem, STATES

WIDTH, HEIGHT = 14, 9
THROW_RANGE = 4.0
# Plates, plated food, pots and the extinguisher; currently the same reach as ingredients.
PASS_RANGE = 4.0
THROW_SPEED = 12.0
WALK_SPEED = 4.5  # Both chefs: 1.5x the original 3 cells per game second
CHEF_SEPARATION = .4  # two small foot circles, not the full tall sprite
UP_STANDOFF = -.22  # tiles a south-side operator stands back from the cabinet
NUDGE_LIMIT = .25
from navigation import contact_fraction
from map_definition import load_map, geometry
# Legacy level-one inspection helpers retain the import-time reference layout.
# Live instances below always load their own document and geometry-keyed nav.
EQUIPMENT, WALLS = geometry(load_map(1))
BLOCKED = WALLS | {tuple(c) for v in EQUIPMENT.values() for c in v.get('cells',[v['cell']])}
FLOOR = {(x, y) for x in range(WIDTH) for y in range(HEIGHT)} - BLOCKED


def tile_key(cell):
    return f'floor_{cell[0]}_{cell[1]}'


def neighbors(cell):
    x, y = cell
    return [(x+dx, y+dy) for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
            if (x+dx, y+dy) in FLOOR]


# Expand obstacles by the chef's footprint so diagonal routes do not clip corners.
WALK_CLEARANCE = .2
EPSILON = 1e-9
WALK_BOXES = tuple((x-.5-WALK_CLEARANCE, y-.5-WALK_CLEARANCE,
                    x+.5+WALK_CLEARANCE, y+.5+WALK_CLEARANCE)
                   for x, y in sorted(BLOCKED))


def walkable_point(point):
    x, y = point
    return (math.isfinite(x) and math.isfinite(y)
            and .5+WALK_CLEARANCE-EPSILON <= x <= WIDTH-1.5-WALK_CLEARANCE+EPSILON
            and .5+WALK_CLEARANCE-EPSILON <= y <= HEIGHT-1.5-WALK_CLEARANCE+EPSILON
            and not any(left+EPSILON < x < right-EPSILON and top+EPSILON < y < bottom-EPSILON
                        for left, top, right, bottom in WALK_BOXES))


def clear_walk_line(start, end):
    """Segments may touch expanded boundaries, but never enter an obstacle."""
    if not walkable_point(start) or not walkable_point(end):
        return False
    for left, top, right, bottom in WALK_BOXES:
        low, high = 0., 1.
        for axis, lower, upper in ((0,left,right),(1,top,bottom)):
            delta = end[axis]-start[axis]
            lower += EPSILON
            upper -= EPSILON
            if abs(delta) < EPSILON:
                if not lower < start[axis] < upper:
                    low, high = 1., 0.
                    break
            else:
                a, b = (lower-start[axis])/delta, (upper-start[axis])/delta
                low, high = max(low,min(a,b)), min(high,max(a,b))
        if low <= high:
            return False
    return True


@lru_cache(maxsize=1)
def navigation_graph():
    # The shortest route in polygonal free space turns only at obstacle vertices.
    # This static visibility graph is shared by both chefs and all rounds.
    corners = sorted({p for left,top,right,bottom in WALK_BOXES
                      for p in ((left,top),(left,bottom),(right,top),(right,bottom))
                      if walkable_point(p)})
    edges = [[] for _ in corners]
    for i, a in enumerate(corners):
        for j in range(i):
            b = corners[j]
            if clear_walk_line(a,b):
                length = math.dist(a,b)
                edges[i].append((j,length));edges[j].append((i,length))
    return corners, edges


def shortest_path(start, end):
    return list(_cached_shortest_path(tuple(start),tuple(end)))


@lru_cache(maxsize=1024)
def _cached_shortest_path(start, end):
    if not walkable_point(start) or not walkable_point(end):
        raise ValueError('目标不在可行走地面')
    if start == end:
        return [start]
    if clear_walk_line(start,end):
        return [start,end]
    corners, static_edges = navigation_graph()
    points = corners+[start,end]
    edges = [list(e) for e in static_edges]+[[],[]]
    source, target = len(corners), len(corners)+1
    for i in (source,target):
        for j, corner in enumerate(corners):
            if clear_walk_line(points[i],corner):
                length = math.dist(points[i],corner)
                edges[i].append((j,length));edges[j].append((i,length))
    distances, previous, queue = {source:0.}, {}, [(0.,source)]
    while queue:
        distance, i = heapq.heappop(queue)
        if distance > distances[i]+EPSILON:
            continue
        if i == target:
            route = [points[i]]
            while i != source:
                i = previous[i];route.append(points[i])
            return list(reversed(route))
        for j, length in edges[i]:
            candidate = distance+length
            if candidate < distances.get(j,math.inf)-EPSILON:
                distances[j] = candidate;previous[j] = i
                heapq.heappush(queue,(candidate,j))
    raise ValueError('目标不可达')


def _board_contacts(equipment,walls):
    blocked=set(walls)|{tuple(c) for e in equipment.values() for c in e.get('cells',[e['cell']])}
    contacts=[]
    for key,e in equipment.items():
        if not (key.startswith('b') and key[1:].isdigit()) or e.get('reach')=='corner':continue
        x,y=e['cell']
        faces=tuple(face for face,dx,dy in [('down',0,-1),('up',0,1),('right',-1,0),('left',1,0)]
                    if (x+dx,y+dy) not in blocked)
        if faces:contacts.append(((x,y),faces))
    return tuple(sorted(contacts))


def map_navigation(level):
    document=load_map(level)
    equipment,walls=geometry(document)
    return _map_navigation(tuple(document['size']),tuple(sorted(walls)),
                           tuple(sorted((key+':'+str(i),tuple(c)) for key,e in equipment.items() for i,c in enumerate(e.get('cells',[e['cell']])))),
                           _board_contacts(equipment,walls))


@lru_cache(maxsize=6)
def _map_navigation(size,walls,cells,contact_edges=()):
    from navigation import Navigation
    return Navigation(*size,walls,{key:{'cell':cell} for key,cell in cells},contact_edges)

class SpatialKitchen(Kitchen):
    def __init__(self, config=None):
        from levels import level_config, burger_map, counter_map
        from navigation import Navigation
        config=level_config(config or __import__('kitchen').load_config(), (config or {}).get('level',1))
        super().__init__(config)
        self.map_document=load_map(self.c.get('level',1))
        self.width,self.height=self.map_document['size']
        self.equipment,self.walls=geometry(self.map_document)
        if self.c.get('level')==1 and (self.c['boards'] != 3 or self.c['pots'] != 1):
            raise ValueError('当前地图固定使用三块案板和一口锅')
        self.nav=_map_navigation(tuple(self.map_document['size']),tuple(sorted(self.walls)),
                                 tuple(sorted((key+':'+str(i),tuple(c)) for key,e in self.equipment.items() for i,c in enumerate(e.get('cells',[e['cell']])))),
                                 _board_contacts(self.equipment,self.walls))
        self.floor=self.nav.floor
        self.sprint_until={who:0. for who in self.chefs}
        self.sprint_ready_at={who:0. for who in self.chefs}
        self.nudged_distance={who:{} for who in self.chefs}
        self.bumped_chefs={who:set() for who in self.chefs}
        if 'bin2' in self.equipment:self.stations['bin2'] = Station('垃圾桶 2', '烹饪区')
        self.stations['bin'].area='烹饪区' if self.c.get('level')!=3 else '处理区'
        self.stations['sink'].area = '处理区' if self.c.get('level')==3 else '烹饪区'
        for key in (k for k in self.equipment if k.startswith('counter') and k not in self.counters):
            self.counters.append(key)
            self.stations[key] = Station('柜台 '+key.removeprefix('counter'), '处理区' if self.equipment[key]['cell'][0]<7 else '烹饪区')
        if self.c.get('level')==3:
            self.stations['counter4'].food=__import__('kitchen').Food('P3','pot')
        centers = [(3.5,4.),(10.,4.)]
        spawns = [min((c for c in self.floor if (c[0]<7)==(center[0]<7)),
                      key=lambda c:(math.dist(c,center),c[1],c[0])) for center in centers]
        if self.c.get('level')==2:
            spawns=[min((c for c in self.floor if (c[1]<4)==(center[1]<4)),key=lambda c:(math.dist(c,center),c))
                    for center in ((6,2.5),(6,5.5))]
        rng = random.Random(self.c.get('spawn_seed'))
        rng.shuffle(spawns)
        self.positions = dict(zip(('human','jeff'),spawns))
        for who in self.chefs:self.chefs[who].location=tile_key(self.positions[who])
        self.facing = {who: 'down' for who in self.chefs}
        self.routes = {}
        self.configure_operation_points()
        self.drop_locks = {}
        self.projectiles = {}
        self.manual = {who: (0., 0.) for who in self.chefs}
        self.floor_places = {tile_key(cell): Station(f'地面({cell[0]},{cell[1]})',
                                                   '处理区' if cell[0] < 7 else '烹饪区')
                             for cell in self.floor}

    def configure_operation_points(self):
        # All stations use the same direction contract. Board contact edges
        # permit the reviewed closer north approach; other solids retain their
        # existing physical clearance. Neither actor artwork nor table is moved.
        self.operation_insets={}
        for key,e in self.equipment.items():
            if e.get('reach')=='corner':continue
            faces={}
            x,y=e['cell']
            for face,dx,dy in [('down',0,-1),('up',0,1),('right',-1,0),('left',1,0)]:
                if (x+dx,y+dy) not in self.floor:continue
                # 'up' is negative: the chef steps back from the cabinet so the tall
                # back-view sprite reads as standing in front of it, not on it.
                faces[face]=UP_STANDOFF if face=='up' else .30 if face in ('left','right') else (.49 if face in self.nav.contact_edges.get(e['cell'],()) else .30)
            self.operation_insets[key]=faces

    def speed_factor(self, who):
        return 1.4 if self.time < self.sprint_until[who]-1e-8 else 1.

    def sprint(self, who):
        if self.ended or self.time < self.sprint_ready_at[who]-1e-8:
            return False
        job=self.chefs[who].job
        if not any(self.manual[who]) and not (job and not job.working and job.travel>1e-8):return False
        self.sprint_until[who]=self.time+1.
        self.sprint_ready_at[who]=self.time+4.
        self.nudged_distance[who]={}
        self.bumped_chefs[who]=set()
        self.emit(f'{who} started sprinting',kind='sprint',actor=who,duration=1.,multiplier=1.4,cooldown=3.)
        return True

    def _travel_step(self,who,job,seconds):
        route=self.routes.get(who)
        if not route or route['job_id']!=job.id:return super()._travel_step(who,job,seconds)
        start=self.time-seconds
        fast=max(0.,min(seconds,self.sprint_until[who]-start))
        speed=WALK_SPEED*(1.+.4*fast/seconds) if seconds else WALK_SPEED
        budget=seconds*speed;spent=0.
        points=list(route['points'][1:])
        while points and budget>1e-9:
            before=self.positions[who];goal=points[0];distance=math.dist(before,goal)
            # Floor interactions use the same nearby reach as keyboard actions;
            # their approach must not push the recipient off the target.
            if len(points)==1 and job.action.kind not in ('go','chop','wash','drop') and distance<=.5 and self.nav.clear_walk_line(before,goal) and (job.action.kind in ('pickup','plate_ground','plate_partner') or math.dist(goal,self.positions['jeff' if who=='human' else 'human'])<CHEF_SEPARATION):
                points.clear();break
            if distance<1e-8:points.pop(0);continue
            step=min(budget,distance)
            end=tuple(before[i]+(goal[i]-before[i])*step/distance for i in (0,1))
            other_pos=self.positions['jeff' if who=='human' else 'human']
            if len(points)==1 and distance<=1. and math.dist(goal,other_pos)<CHEF_SEPARATION:
                # The teammate stands on this spot and working chefs are not pushed:
                # stop beside them instead of sliding back and forth every frame.
                self._face_vector(who,goal[0]-before[0],goal[1]-before[1])
                points.clear();break
            self._move_with_chef_contact(who,end,fast>0)
            moved=math.dist(before,self.positions[who])
            # Facing follows real progress, not a sideways contact slide.
            if moved>step*.5:self._face_vector(who,goal[0]-before[0],goal[1]-before[1])
            if fast>0:self._nudge_food(who,before,self.positions[who])
            spent+=step;budget-=step
            if math.dist(self.positions[who],goal)<1e-8:points.pop(0)
            if math.dist(self.positions[who],end)>1e-8:break
        # Retain the original static-map waypoints. Contact does not plan a detour.
        route['points']=[self.positions[who]]+points
        route['length']=sum(math.dist(a,b) for a,b in zip(route['points'],route['points'][1:]))
        job.travel=route['length']/WALK_SPEED
        return seconds if points else min(seconds,spent/speed)

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
            amount=min(distance,max(0.,NUDGE_LIMIT-budget.get(key,0.)))
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
            if key not in budget:self.emit(f'{NAMES[who]}轻推了地面食材 {key}',kind='ground_nudge',actor=who,item=key,max_distance=NUDGE_LIMIT)
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

    def _move_with_chef_contact(self,who,end,boosted=False):
        start=self.positions[who];other_id='jeff' if who=='human' else 'human'
        other=self.positions[other_id];distance=math.dist(start,end)
        if distance<1e-9:return
        direction=tuple((end[i]-start[i])/distance for i in (0,1))
        fraction=contact_fraction(start,end,other,CHEF_SEPARATION)
        if fraction>=1.-1e-8:
            self.positions[who]=self._wall_limited(start,end);return
        # A single small sprint impulse; sustained normal pressure is much slower.
        impulse=.25 if boosted and other_id not in self.bumped_chefs[who] else 0.
        if impulse:self.bumped_chefs[who].add(other_id)
        self._push_chef(other_id,tuple(d*(impulse if boosted else distance*.18) for d in direction))
        other=self.positions[other_id]
        fraction=contact_fraction(start,end,other,CHEF_SEPARATION)
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
            slide=tuple(point[i]+sign*tangent[i]*remaining for i in (0,1))
            slide=self._wall_limited(point,slide)
            if math.dist(point,slide)>1e-6 and contact_fraction(point,slide,other,CHEF_SEPARATION)>=1.-1e-8:
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

    def path(self, who, target):
        if target in self.equipment:
            station=self.equipment[target]
            access=[station['access']] if station.get('reach')=='corner' else sorted({n for c in station.get('cells',[station['cell']]) for n in self.nav.neighbors(c)})
            shared=self.shared_access(who,target)
            if shared is not None and shared:access=shared
            other='jeff' if who=='human' else 'human'
            taken=[self.positions[other]]+([self.routes[other]['points'][-1]] if self.routes.get(other) else [])
            free=[cell for cell in access if all(math.dist(self.operation_point(target,cell),p)>=CHEF_SEPARATION for p in taken)]
            if free:access=free
            routes = [self.nav.shortest_path(self.positions[who],self.operation_point(target,cell)) for cell in access]
            if not routes:raise ValueError('工位没有可操作的一侧')
            return min(routes,key=lambda route:sum(math.dist(a,b) for a,b in zip(route,route[1:])))
        return self.nav.shortest_path(self.positions[who],self.cell(target))

    def shared_access(self, who, target):
        """Reserve a perpendicular, reachable side; never stack two chefs."""
        if target not in self.equipment:return None
        kind='chop' if target in self.boards else 'wash' if target=='sink' else None
        if not kind:return None
        other=next((p for p,a in self.chefs.items() if p!=who and a.job
                    and a.job.action.target==target and a.job.action.kind==kind),None)
        if other is None:return None
        station=self.equipment[target]
        if station.get('reach')=='corner':return []
        center=station['cell'];access=self.nav.neighbors(center)
        route=self.routes.get(other)
        point=route['points'][-1] if route else self.positions[other]
        occupied=min(access,key=lambda a:math.dist(self.operation_point(target,a),point))
        ox,oy=occupied[0]-center[0],occupied[1]-center[1]
        return [a for a in access if (a[0]-center[0])*ox+(a[1]-center[1])*oy==0
                and math.dist(self.operation_point(target,a),point)>.4]

    def can_share_work(self, who, kind, target):
        if kind not in ('chop','wash'):return False
        station=self.stations[target]
        return not station.fire and not self.chefs[who].hand and bool(self.shared_access(who,target))

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
        # Side poses have their wrist above the foot anchor. Place the feet
        # toward the front of the side edge, so the wrist faces the board center.
        side_drop=.30 if facing in ('left','right') else 0.
        point=(access[0]+dx*inset,access[1]+dy*inset+side_drop)
        if side_drop and not self.nav.clear_walk_line(access,point):
            point=(access[0]+dx*inset,access[1]+dy*inset)
        if not 0<=inset<.5 or not self.nav.clear_walk_line(access,point):
            raise ValueError('操作停靠点超出安全地面')
        return point

    def travel_time(self, chef, target):
        who = next(who for who, a in self.chefs.items() if a is chef)
        points = self.path(who, target)
        return sum(math.dist(a, b) for a, b in zip(points, points[1:])) / WALK_SPEED

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
        # Any held item can be thrown or passed; throw_range decides how far it flies.
        return bool(self.chefs[who].hand)

    def throw_range(self, who):
        hand = self.chefs[who].hand
        return THROW_RANGE if hand and hand.stage in ('raw','chopped') and not hand.plate_id else PASS_RANGE

    def can_throw_to(self, who, target):
        if not self.can_throw(who):return False
        if target in self.boards + self.counters:
            hand = self.chefs[who].hand
            station = self.stations[target]
            cell = self.equipment[target]['cell']
            return (bool(hand) and hand.stage in ('raw','chopped') and not hand.plate_id
                    and station.food is None and station.lock is None and not station.fire
                    and not self.board_reserved(target,who)
                    and math.dist(self.positions[who],cell) <= THROW_RANGE+1e-8
                    and self.clear_throw_line(self.positions[who],cell))
        if target not in self.floor_places:
            return False
        cell = self.cell(target)
        return (cell not in self.occupied_floor(who)
                and math.dist(self.positions[who], cell) <= self.throw_range(who) + 1e-8
                and self.clear_throw_line(self.positions[who], cell))

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
        if math.dist(end,self.positions[other]) <= .75:
            candidates = sorted(self.nav.neighbors(self.anchor(other)),key=lambda p:(math.dist(p,end),p))
            beside = next((p for p in candidates if available(p)),None)
            if beside is not None:
                return tile_key(beside), end
            return None
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

    def throw_action(self, who, target, key=None):
        hand = self.chefs[who].hand
        if not self.can_throw(who) or self.ended:
            return None
        board = next((b for b in self.boards + self.counters if tuple(self.equipment[b]['cell']) == tuple(target)),None)
        if board and self.can_throw_to(who,board):
            return Action(key or f'throw {board}',f'把手中食材抛到空的{self.stations[board].name}',
                          'throw',board,(hand.id,board,target[0],target[1]))
        landing = self.throw_landing(who,target)
        if not landing:
            return None
        floor, aim = landing
        return Action(key or f'throw {target[0]:g} {target[1]:g}',
                      f'向地面({target[0]:g},{target[1]:g})抛出手中物品（落点由射程和墙确定）',
                      'throw',floor,(hand.id, floor, aim[0], aim[1]))

    def handoff_target(self, who):
        other = 'jeff' if who == 'human' else 'human'
        landing = self.throw_landing(who,self.positions[other])
        return landing[0] if landing else None

    def set_manual(self, who, dx, dy):
        length = math.hypot(dx,dy)
        vector = (dx/max(1.,length),dy/max(1.,length))
        if vector == self.manual[who]:
            return
        if length:
            self.stop(who)
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
        compatible=self.can_add(plate,ingredient) or (self.c.get('level') in (2,3) and self.can_merge_plates(plate,donor))
        # Do not change a hand while its existing operation is consuming it.
        receiver=self.chefs[other]
        return bool(compatible and not (receiver.job and receiver.job.working)
                    and (not nearby or (math.dist(self.positions[who],self.positions[other]) <= 1.1
                                        and self.nav.clear_walk_line(self.positions[who],self.positions[other]))))

    def actions(self, who):
        actions = [a for a in super().actions(who) if a.kind != 'drop']
        actions = [a for a in actions if not (a.kind in ('put_board','put_counter') and self.board_reserved(a.target))]
        actions = [a for a in actions if not (a.kind in ('chop','wash')
                   and self.shared_access(who,a.target)==[])]
        if self.ended:
            return actions
        chef = self.chefs[who]
        discard = next((a for a in actions if a.key=='discard'),None)
        if discard and 'bin2' in self.stations:actions.append(Action('discard bin2',discard.label.replace('垃圾桶','垃圾桶 2'),discard.kind,'bin2',self.signature(who,'bin2')))
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
            for board in self.boards + self.counters:
                if self.can_throw_to(who,board):
                    actions.append(self.throw_action(who,self.equipment[board]['cell'],f'throw {board}'))
            # Both chefs have the same targetable floor cells. Choice count stays
            # bounded by this map; no scripted preference is inserted.
            for cell in sorted(self.floor):
                if self.can_throw_to(who,tile_key(cell)):
                    action = self.throw_action(who,cell)
                    if action: actions.append(action)
        if self.can_plate_partner(who):
            other = 'jeff' if who == 'human' else 'human'
            actions.append(Action('plate partner','走近，把食材加入队友手中的盘（容器留在原持有者手中）',
                                  'plate_partner',tile_key(self.anchor(other)),self.partner_signature(who)))
        # Ground clicks are player movement intents. Jev can choose station positions or any food.
        if who == 'human':
            for cell in sorted(self.floor):
                key = tile_key(cell)
                if math.dist(self.positions[who], cell) > .01:
                    action = Action(f'go {key}', f'走到{self.place(key).name}', 'go', key)
                    if not chef.job or chef.job.action.key != action.key:
                        actions.append(action)
        return actions

    def interaction_target(self,who,preferred=None):
        """Explicit click wins; empty hands can retrieve an item at their feet."""
        if preferred:return preferred
        x,y=self.anchor(who)
        if self.chefs[who].hand is None:
            pickable={a.expected[1] for a in self.actions(who) if a.kind=='pickup'}
            item=next((key for key,item in self.ground.items()
                       if self.cell(item.location)==(x,y) and key in pickable),None)
            if item:return 'item:'+item
        dx,dy={'up':(0,-1),'down':(0,1),'left':(-1,0),'right':(1,0)}[self.facing[who]]
        front=(x+dx,y+dy)
        station=next((key for key,e in self.equipment.items() if front in e.get('cells',[e['cell']])),None)
        if station:return station
        other='jeff' if who=='human' else 'human'
        if self.anchor(other)==front and self.can_plate_partner(who,True):return 'partner'
        # A pot at the chef's feet remains accessible when the forward tile is empty.
        for cell in (front,(x,y)):
            item=next((key for key,item in self.ground.items() if self.cell(item.location)==cell),None)
            if item:return 'item:'+item
        return tile_key(front)

    def interaction_cell(self,who,target):
        if target in self.equipment:return min(self.equipment[target].get('cells',[self.equipment[target]['cell']]),key=lambda c:math.dist(c,self.positions[who]))
        if target=='partner':return self.anchor('jeff' if who=='human' else 'human')
        if target and target.startswith('item:'):
            item=self.ground.get(target[5:]);return self.cell(item.location) if item else None
        return self.cell(target) if target else None

    def quick_interaction(self, who, actions=None, preferred=None):
        """One local, legal action. This is a player control, not an AI policy."""
        chef = self.chefs[who]
        actions = self.actions(who) if actions is None else actions
        if chef.job and chef.job.working:
            return next((a for a in actions if a.kind=='stop'),None)
        priority = {'swap_pot':0,'swap_ground_pot':0,'load_ground':0,'load_counter':0,'plate_ground':0,'plate_pot':0,'plate_counter':0,'plate_from_counter':0,
                    'plate_partner':0,'extinguish':0,'put_board':1,'put_pot':1,'return_pot':1,
                    'put_counter':1,'put_sink':1,'put_tool':1,'serve':1,'wash':1,'chop':1,
                    'pickup':2,'take_board':3,'take_plate':3,'take_counter':3,'take_return':3,
                    'take_sink':3,'take_tool':3,'fetch':4,'lift_pot':4,'discard':1,'empty_pot':1,'assemble':0,'merge_plates':0}
        nearby=[]
        for a in actions:
            if a.kind not in priority:continue
            if preferred:
                if preferred.startswith('item:'):
                    if a.kind not in ('pickup','plate_ground','load_ground','swap_ground_pot') or a.expected[1]!=preferred[5:]:continue
                elif preferred=='partner':
                    if a.kind!='plate_partner':continue
                elif a.target!=preferred:continue
            # Only the focused loose ground ingredient opts into quick hand swapping.
            # Nearby station take actions must not displace a carried dish implicitly.
            if chef.hand and a.kind in TAKE_KINDS and a.kind!='take_tool':
                incoming=self.ground.get(a.expected[1]) if a.kind=='pickup' else None
                if not (preferred and preferred.startswith('item:') and incoming
                        and incoming.food.stage in ('raw','chopped') and not incoming.food.plate_id):continue
            if a.kind=='plate_partner':
                if not self.can_plate_partner(who,True):continue
                distance=math.dist(self.positions[who],self.positions['jeff' if who=='human' else 'human'])
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
        if preferred and not preferred.startswith('floor_'):return None
        return next((a for a in actions if a.kind=='drop'),None) if chef.hand else None

    def interaction_hint(self, who, preferred=None):
        if preferred and preferred.startswith('floor_'):return '面前没有可操作目标'
        if preferred and preferred!='serve':return '选中目标暂不可操作，请靠近或检查物品状态'
        hand=self.chefs[who].hand
        if not hand or not hand.plate_id or self.dish(hand):return '选中目标暂不可操作，请靠近或检查物品状态' if preferred else None
        target=self.interaction_cell(who,'serve')
        if math.dist(self.positions[who],target)>1.5:return '请靠近选中的出餐口' if preferred else None
        route=self.path(who,'serve')
        if sum(math.dist(a,b) for a,b in zip(route,route[1:]))>1.5:return None
        missing={'beef','bread','lettuce','tomato'}-set(hand.components or ('beef',))
        names={'beef':'熟牛肉','bread':'面包','lettuce':'切好的生菜','tomato':'切好的番茄'}
        return '暂不能出餐，还缺：'+'、'.join(names[x] for x in sorted(missing))

    def stop(self, who):
        self.manual[who] = (0.,0.)
        had_job = bool(self.chefs[who].job)
        super().stop(who)
        if had_job:
            self.chefs[who].location = tile_key(self.anchor(who))
        self.routes.pop(who, None)
        self.drop_locks = {key: owner for key, owner in self.drop_locks.items() if owner != who}

    def start(self, who, action):
        if action.kind == 'throw':
            hand = self.chefs[who].hand
            if (not self.can_throw(who) or hand.id != action.expected[0]
                    or not self.can_throw_to(who,action.target) or self.ended):
                return False, '抛递目标已变化，请重新选择'
            self.stop(who)
            self.job_serial += 1
            self.chefs[who].job = Job(self.job_serial,action,0,self.c.get('handling_seconds',.15))
            self.emit(f'{NAMES[who]}开始：{action.label}',kind='action_start',actor=who,action=action.key)
            return True, '开始抛递'
        if action.kind == 'plate_partner':
            if not self.can_plate_partner(who) or action.expected != self.partner_signature(who) or self.ended:
                return False, '队友或锅中的物品已变化'
            self.stop(who)
            self.job_serial += 1
            self.chefs[who].job = Job(self.job_serial,action,self.travel_time(self.chefs[who],action.target),self.c.get('handling_seconds',.15))
            self.emit(f'{NAMES[who]}开始给队友装盘',kind='action_start',actor=who,action=action.key)
            ok, message = True, '开始'
        else:
            ok, message = super().start(who, action)
        if ok and action.kind not in ('continue', 'wait', 'stop'):
            job = self.chefs[who].job
            points = self.path(who, action.target)
            self.routes[who] = {'job_id': job.id, 'points': points,
                                'length': sum(math.dist(a,b) for a,b in zip(points,points[1:]))}
        return ok, message

    def _face_vector(self, who, dx, dy):
        if math.hypot(dx,dy) < 1e-8:return
        self.facing[who] = (('left' if dx<0 else 'right') if abs(dx)>=abs(dy)
                            else ('up' if dy<0 else 'down'))

    def _travel(self, who, job, seconds):
        route = self.routes.get(who)
        if not route or route['job_id'] != job.id:
            return
        distance = max(0, route['length'] - job.travel * WALK_SPEED)
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
            self.emit(f'{NAMES[who]}附近没有空位换手，物品保持原样', kind='arrival_conflict', actor=who)
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
            if access is not None and not any(math.dist(self.positions[who],self.operation_point(job.action.target,p))<.05 for p in access):
                self.emit('共同操作的位置已被占用，本次操作取消',kind='arrival_conflict',actor=who)
                self.stop(who);return False
        if job.action.kind in ('put_board','put_counter') and self.board_reserved(job.action.target):
            self.emit('工位有食材正在飞入，本次放置取消',kind='arrival_conflict',actor=who)
            self.stop(who); return False
        if job.action.kind == 'plate_partner':
            if not self.can_plate_partner(who,True) or job.action.expected != self.partner_signature(who):
                self.emit('队友已移动或物品变化，装盘取消',kind='arrival_conflict',actor=who)
                self.stop(who); return False
            job.working = True
            return True
        if job.action.kind == 'throw':
            hand = self.chefs[who].hand
            if not hand or hand.id != job.action.expected[0] or not self.can_throw_to(who,job.action.target):
                self.emit(f'{NAMES[who]}的抛递落点不可用，仍拿着物品',kind='arrival_conflict',actor=who)
                self.stop(who)
                return False
            self.drop_locks[job.action.target] = who
            job.working = True
            return True
        if job.action.kind == 'drop':
            target = job.action.target
            occupied = self.cell(target) in self.occupied_floor(who)
            if occupied or self.drop_locks.get(target) not in (None, who):
                self.emit(f'{NAMES[who]}发现落点被占用，仍拿着食物', kind='arrival_conflict', actor=who)
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
                self.emit('装盘时队友或物品变化，物品保持原样',kind='arrival_conflict',actor=who)
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
            self.emit(f'{NAMES[who]}把食材加入{NAMES[other]}手中的盘',kind='action_done',actor=who,action='plate partner')
        elif job.action.kind == 'throw':
            chef = self.chefs[who]
            food = chef.hand
            target = (self.equipment[job.action.target]['cell'] if job.action.target in self.equipment
                      else self.cell(job.action.target))
            duration = max(.2, math.dist(self.positions[who],job.action.expected[2:4])/THROW_SPEED)
            self.projectiles[food.id] = {'food': food, 'target': job.action.target,
                'from': self.positions[who], 'to': tuple(job.action.expected[2:4]), 'started': self.time,
                'lands_at': self.time+duration, 'actor': who, 'catch_at': tuple(job.action.expected[2:4])}
            receiver = self.chefs['jeff' if who == 'human' else 'human']
            if receiver.hand or (receiver.job and receiver.job.action.kind != 'go'):
                # Busy chefs cannot catch: show the reserved landing point too,
                # rather than drawing both ingredients through their hands.
                self.projectiles[food.id]['to'] = tuple(target)
            chef.hand = None
            chef.job = None
            self.emit(f'{NAMES[who]}抛出了 {food.id}，落点为 {target}',kind='thrown',actor=who,item=food.id,
                      stage=food.stage,source=self.positions[who],target=target,aim=tuple(job.action.expected[2:4]))
            self.emit(f'{NAMES[who]}完成动作：抛出物品',kind='action_done',actor=who,action=job.action.key)
        else:
            super()._finish(who, job)
        self.routes.pop(who, None)
        self.drop_locks = {key: owner for key, owner in self.drop_locks.items() if owner != who}

    def _after_step(self, seconds):
        for who, vector in self.manual.items():
            if not any(vector): continue
            self._face_vector(who,*vector)
            start = self.positions[who]
            move_start=start
            boosted=max(0.,min(seconds,self.sprint_until[who]-(self.time-seconds)))
            move_seconds=seconds+.4*boosted
            end = tuple(start[i]+vector[i]*WALK_SPEED*move_seconds for i in (0,1))
            if self.nav.clear_walk_line(start,end):
                self._move_with_chef_contact(who,end,boosted>0)
            else:
                for axis in (0,1):
                    start = self.positions[who]
                    candidate = list(start);candidate[axis] += vector[axis]*WALK_SPEED*move_seconds
                    if self.nav.clear_walk_line(start,candidate):self._move_with_chef_contact(who,tuple(candidate),boosted>0)
            if boosted>0:self._nudge_food(who,move_start,self.positions[who])
            self.chefs[who].location = tile_key(self.anchor(who))
        for key, p in list(self.projectiles.items()):
            if self.time >= p['lands_at']-1e-8:
                if p['target'] in self.boards + self.counters:
                    board = self.stations[p['target']]
                    assert board.food is None, '已预留的台面被覆盖'
                    board.food = p['food']
                    self.emit(f'{key} 落到{board.name}，可取走',kind='landed',
                              item=key,actor=p['actor'],target=p['target'])
                    del self.projectiles[key]
                    continue
                other = 'jeff' if p['actor'] == 'human' else 'human'
                chef = self.chefs[other]
                can_catch = (not chef.hand and (not chef.job or chef.job.action.kind == 'go')
                             and math.dist(self.positions[other],p.get('catch_at',p['to'])) <= .75
                             and self.clear_throw_line(p['from'],self.positions[other]))
                if can_catch:
                    chef.hand = p['food']
                    self.emit(f'{NAMES[other]}接住了 {key}',kind='caught',item=key,actor=other)
                else:
                    self.ground[key] = GroundItem(p['food'],p['target'])
                    self.emit(f'{key} 落在地上，可拾取',kind='landed',item=key,actor=p['actor'])
                del self.projectiles[key]

    def fire_neighbors(self, key):
        combustible = set(self.boards + self.pots + self.counters)
        if key not in combustible or key not in self.equipment:
            return []
        x,y = self.equipment[key]['cell']
        return sorted(n for n in combustible if n != key and n in self.equipment
                      and abs(self.equipment[n]['cell'][0]-x)+abs(self.equipment[n]['cell'][1]-y)==1)

    def snapshot(self):
        state = super().snapshot()
        for board in self.boards + self.counters:
            state['stations'][board]['incoming_item'] = next((key for key,p in self.projectiles.items() if p['target']==board),None)
        state['projectiles'] = [{'id': key, 'stage': p['food'].stage, 'ingredient':p['food'].ingredient, 'plate_id': p['food'].plate_id,
            'components': list(p['food'].components), 'contents': {'stage': p['food'].contents.stage} if p['food'].contents else None,
            'onto': p['target'] if p['target'] in self.equipment else None, 'from': p['from'], 'to': p['to'], 'landing_cell': self.equipment[p['target']]['cell'] if p['target'] in self.equipment else self.cell(p['target']), 'started': p['started'], 'lands_at': p['lands_at']} for key,p in self.projectiles.items()]
        state['map'] = {'throw_range': THROW_RANGE, 'pass_range': PASS_RANGE, 'throw_speed': THROW_SPEED, 'width': self.width, 'height': self.height, 'walls': sorted(self.walls),
                        'equipment': self.equipment, 'walk_speed': WALK_SPEED,
                        'presentation': self.map_document['presentation'],
                        'layout_version': self.map_document['id']+'-'+str(self.map_document['revision']), 'spawn_rule': 'One chef near the center of each working area; assigned sides are randomized',
                        'movement_rule': '工位可从相邻可达空地就近操作。墙和设备不能穿过；厨师接触时贴边滑动并缓慢推挤，冲刺可轻撞对方至多四分之一格。人类和 AI 共用接触规则，不自动重新规划绕人路线。普通走路可穿过地面食物。',
                        'ground_rule': '放下优先选脚下或相邻空格。冲刺每次最多推动散落食材0.25格，允许食物重叠；盘子锅具不被推动，不自动装盘，不弹飞或损坏。地面不能切配或加热。',
                        'collision':{'chef_separation':CHEF_SEPARATION,'sprint_food_limit':NUDGE_LIMIT,'food_blocks_walking':False,'food_repulsion':False}}
        for who, data in state['chefs'].items():
            data['can_throw'] = self.can_throw(who)
            data['throw_range'] = self.throw_range(who) if self.can_throw(who) else None
            data['sprint']={'available':self.time>=self.sprint_ready_at[who], 'active_remaining':round(max(0,self.sprint_until[who]-self.time),3), 'cooldown_remaining':round(max(0,self.sprint_ready_at[who]-self.time),3),'multiplier':1.4,'duration':1.,'cooldown_after':3.}
            data['handoff_target'] = self.handoff_target(who) if self.can_throw(who) else None
            data['manual_moving'] = any(self.manual[who]) and not self.ended
            data['move_direction'] = self.manual[who]
            if data['manual_moving']:
                data.update(action_kind='manual_move',task='手动移动',working=False)
            data['facing'] = self.facing[who]
            data['position'] = [round(v, 4) for v in self.positions[who]]
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
