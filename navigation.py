"""Per-map navigation; no global geometry changes when switching levels."""
import heapq
import math
from functools import lru_cache
EPSILON = 1e-9
WALK_CLEARANCE = .2

def contact_fraction(start,end,center,radius):
    """Swept point/circle contact, including recovery from an old overlap."""
    dx,dy=end[0]-start[0],end[1]-start[1]
    ox,oy=start[0]-center[0],start[1]-center[1]
    a=dx*dx+dy*dy
    # a and disc scale with the squared step: absolute tolerances would wave
    # short steps (<~8e-5) straight into the circle.
    if a<EPSILON*EPSILON:return 1.
    b=ox*dx+oy*dy;c=ox*ox+oy*oy-radius*radius
    if c<-EPSILON:return 1. if b>=-EPSILON else 0.
    if b>=0:return 1.
    disc=b*b-a*c
    if disc<=EPSILON*a:return 1.
    return max(0.,min(1.,(-b-math.sqrt(disc))/a))

class Navigation:
    def __init__(self, width, height, walls, equipment, contact_edges=(), cabinet_clearance=None):
        self.width,self.height=width,height
        cabinets={tuple(c) for e in equipment.values() for c in e.get('cells',[e['cell']])}
        self.blocked=set(walls)|cabinets
        self.floor={(x,y) for x in range(width) for y in range(height)}-self.blocked
        self.contact_edges=dict(contact_edges)
        # Legacy: remove only approved board-face clearance; countertops remain solid.
        # With cabinet_clearance (front, side), every workstation keeps one body
        # size instead: feet stay `front` south of it, clear of its front panel,
        # and `side` from its east/west edges, the chef's half width. The north
        # (back) edge keeps the legacy rule, where the cabinet hides the legs.
        # Walls keep the ordinary clearance.
        def edge(cell,face):
            if cabinet_clearance and cell in cabinets and face!='down':
                return cabinet_clearance[0] if face=='up' else cabinet_clearance[1]
            return 0 if face in self.contact_edges.get(cell,()) else WALK_CLEARANCE
        self.walk_boxes=tuple((x-.5-edge((x,y),'right'),y-.5-edge((x,y),'down'),
                               x+.5+edge((x,y),'left'),y+.5+edge((x,y),'up'))
                              for x,y in sorted(self.blocked))
        self.graph=self.navigation_graph()
        self._cached_shortest_path=lru_cache(maxsize=1024)(self._cached_shortest_path)
        self._visible_corners=lru_cache(maxsize=256)(self._visible_corners)
    def neighbors(self, cell):
        x, y = cell
        return [(x+dx, y+dy) for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
                if (x+dx, y+dy) in self.floor]


    def walkable_point(self, point):
        x, y = point
        return (math.isfinite(x) and math.isfinite(y)
                and .5+WALK_CLEARANCE-EPSILON <= x <= self.width-1.5-WALK_CLEARANCE+EPSILON
                and .5+WALK_CLEARANCE-EPSILON <= y <= self.height-1.5-WALK_CLEARANCE+EPSILON
                and not any(left+EPSILON < x < right-EPSILON and top+EPSILON < y < bottom-EPSILON
                            for left, top, right, bottom in self.walk_boxes))


    def clear_walk_line(self, start, end):
        """Segments may touch expanded boundaries, but never enter an obstacle."""
        if not self.walkable_point(start) or not self.walkable_point(end):
            return False
        x0, x1 = min(start[0],end[0]), max(start[0],end[0])
        y0, y1 = min(start[1],end[1]), max(start[1],end[1])
        for left, top, right, bottom in self.walk_boxes:
            # A box whose shrunken interior lies beside the segment's bounds cannot be entered.
            if left+EPSILON >= x1 or right-EPSILON <= x0 or top+EPSILON >= y1 or bottom-EPSILON <= y0:
                continue
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


    def navigation_graph(self):
        # The shortest route in polygonal free space turns only at obstacle vertices.
        # This static visibility graph is shared by both chefs and all rounds.
        corners = sorted({p for left,top,right,bottom in self.walk_boxes
                          for p in ((left,top),(left,bottom),(right,top),(right,bottom))
                          if self.walkable_point(p)})
        edges = [[] for _ in corners]
        for i, a in enumerate(corners):
            for j in range(i):
                b = corners[j]
                if self.clear_walk_line(a,b):
                    length = math.dist(a,b)
                    edges[i].append((j,length));edges[j].append((i,length))
        return corners, edges


    def shortest_path(self, start, end):
        return list(self._cached_shortest_path(tuple(start),tuple(end)))

    def _cached_shortest_path(self, start, end):
        if not self.walkable_point(start) or not self.walkable_point(end):
            raise ValueError('目标不在可行走地面')
        if start == end:
            return [start]
        if self.clear_walk_line(start,end):
            return [start,end]
        corners, static_edges = self.graph
        points = corners+[start,end]
        edges = [list(e) for e in static_edges]+[[],[]]
        source, target = len(corners), len(corners)+1
        for i in (source,target):
            for j, length in self._visible_corners(points[i]):
                edges[i].append((j,length));edges[j].append((i,length))
        return _dijkstra(points,edges,source,target)

    def _visible_corners(self, point):
        """Graph corners in straight view of a point, in corner order.

        One chef position is routed to every station when its actions are listed;
        caching per point (not per start/end pair) checks its view once.
        """
        corners, _ = self.graph
        return [(j, math.dist(point,corner)) for j, corner in enumerate(corners)
                if self.clear_walk_line(point,corner)]

    def shortest_path_around(self, start, end, center, radius):
        """Shortest route that also keeps clear of one disc (the other chef).

        Used only to recover a stalled route. The disc is not static geometry,
        so this is planned on demand and never cached.
        """
        start,end,center=tuple(start),tuple(end),tuple(center)
        if not self.walkable_point(start) or not self.walkable_point(end):
            raise ValueError('目标不在可行走地面')
        if math.dist(end,center) < radius-EPSILON:
            raise ValueError('目标被占用')
        def outside(a,b):
            # Directional: a start already touching the disc may still leave it.
            return contact_fraction(a,b,center,radius) >= 1.-EPSILON
        if start == end:
            return [start]
        if self.clear_walk_line(start,end) and outside(start,end):
            return [start,end]
        corners, static_edges = self.graph
        # Vertices of the octagon circumscribing the disc: its sides lie outside
        # the disc, so these give the visibility graph its way around the chef.
        ring = radius/math.cos(math.pi/8)*(1+1e-6)
        extra = [p for p in ((center[0]+ring*math.cos(math.pi/8+i*math.pi/4),
                              center[1]+ring*math.sin(math.pi/8+i*math.pi/4)) for i in range(8))
                 if self.walkable_point(p)]
        usable = [math.dist(c,center) >= radius-EPSILON for c in corners]
        points = corners+extra+[start,end]
        edges = [[(j,length) for j,length in e if usable[i] and usable[j] and outside(corners[i],corners[j])]
                 for i,e in enumerate(static_edges)]+[[] for _ in range(len(extra)+2)]
        source, target = len(points)-2, len(points)-1
        for i in range(len(corners),len(points)):
            for j in range(i):
                if j < len(corners) and not usable[j]:
                    continue
                if (i,j) == (target,source):
                    continue  # already tested as a straight line above
                # Only the start may touch the disc, and it is always points[i].
                a, b = points[i], points[j]
                if self.clear_walk_line(a,b) and outside(a,b):
                    length = math.dist(a,b)
                    edges[i].append((j,length));edges[j].append((i,length))
        return _dijkstra(points,edges,source,target)


def _dijkstra(points, edges, source, target):
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
