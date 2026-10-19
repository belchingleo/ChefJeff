"""Level 1's geometry for layout tests, read from a live kitchen (the engine has no global map)."""
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen

_kitchen = SpatialKitchen(level_config(load_config(), 1))
EQUIPMENT, FLOOR, BLOCKED = _kitchen.equipment, _kitchen.floor, _kitchen.nav.blocked
neighbors, walkable_point = _kitchen.nav.neighbors, _kitchen.nav.walkable_point
clear_walk_line, shortest_path = _kitchen.nav.clear_walk_line, _kitchen.nav.shortest_path
