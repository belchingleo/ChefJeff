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
    if a<EPSILON:return 1.
    b=ox*dx+oy*dy;c=ox*ox+oy*oy-radius*radius
    if c<-EPSILON:return 1. if b>=-EPSILON else 0.
    if b>=0:return 1.
    disc=b*b-a*c
    if disc<=EPSILON:return 1.
    return max(0.,min(1.,(-b-math.sqrt(disc))/a))

class Navigation:
    def __init__(self, width, height, walls, equipment, contact_edges=()):
        self.width,self.height=width,height
        self.blocked=set(walls)|{tuple(c) for e in equipment.values() for c in e.get('cells',[e['cell']])}
        self.floor={(x,y) for x in range(width) for y in range(height)}-self.blocked
        self.contact_edges=dict(contact_edges)
        # Remove only approved board-face clearance; countertops remain solid.
        self.walk_boxes=tuple((x-.5-(0 if 'right' in self.contact_edges.get((x,y),()) else WALK_CLEARANCE),
                               y-.5-(0 if 'down' in self.contact_edges.get((x,y),()) else WALK_CLEARANCE),
                               x+.5+(0 if 'left' in self.contact_edges.get((x,y),()) else WALK_CLEARANCE),
                               y+.5+(0 if 'up' in self.contact_edges.get((x,y),()) else WALK_CLEARANCE))
                              for x,y in sorted(self.blocked))
        self.graph=self.navigation_graph()
        self._cached_shortest_path=lru_cache(maxsize=1024)(self._cached_shortest_path)
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
        for left, top, right, bottom in self.walk_boxes:
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
            for j, corner in enumerate(corners):
                if self.clear_walk_line(points[i],corner):
                    length = math.dist(points[i],corner)
                    edges[i].append((j,length));edges[j].append((i,length))
        return _dijkstra(points,edges,source,target)

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
