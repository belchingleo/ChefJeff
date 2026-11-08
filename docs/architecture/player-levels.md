# Player levels

Status: the level editor and its server side. Modules `level_design.py` (the editor's design and catalog), `level_calibration.py` (check, pacing, calibration, freeze), `player_level_queue.py` (the queue behind the endpoints) and the page's `cocos-kitchen/level-editor.js`.

```text
POST /api/player-level/submit   {"design": <design>} or {"level": <bundle>}  -> 202 queued | 200 done (seen before) | 400 refused | 409 | 503
GET  /api/player-level/status?job=<job>                  -> 200 {job, state, content_id, position | report | error} | 404
GET  /api/player-level/catalog                            -> 200 the editor's rules and ingredients | 404 (not offered)
POST /api/player-level/play     {"job", "game_id", "request_id"}  -> 200 | 404 (not this owner's, or not done) | 409
```

The editor page (`level-editor.js`) opens from the "+ 自定义关卡" card of the level list where the server offers player levels (the catalog answers 200). It keeps a player's levels in this browser only (`localStorage`, key `chefjeff.player-levels.v1`), with export to and import from a JSON file of the design. It has three steps: the kitchen layout (room size, stations, walls, drag to place or erase, a station of the held kind or a wall clicked again is removed, a serving window or plate return pressed away from the outer wall explains where it goes), the menu (it offers only the ingredients the layout can make: the ingredient's box, a board when it is chopped, a stove with its vessel when it is cooked; the rest are greyed out with the first thing each lacks), and calibration and play. Its live checks mirror the server's, from `GET /api/player-level/catalog` (`level_design.editor_catalog`): the room sizes and station rules, and each ingredient's name, plated state, the English name Jeff reads and its chop and heat steps. So the page names no ingredient and shows the release's times. Every design is still checked again on submit, and the server's diagnostics are shown with a sentence for the known codes. Editing is for a computer browser; on a phone the list only plays finished levels. "Play" submits the design again (answered at once from the server's memory of calibrated designs) and switches the session with `play`.

`play` switches the session to a calibrated, playable level between rounds, as `/api/level` does; a restart keeps it, `/api/next` with its own id plays it again (the result card's Again) and `/api/level` returns to a listed level. While it is active, `/api/state` carries `player_level: {id, name, names, looks, target, solo_reaches_target}` (`name` is the player's level name, for the start card only), `kitchen.level` is null and `kitchen.level_id` is the content id.

The local game server (`cocos_server.py`) offers both endpoints. The hosted server offers them only when started with `--player-levels`, because calibration costs CPU on a machine shared with live kitchens; hosted requests need the page's `X-ChefJeff-Session`, and a session sees only its own jobs.

## The design

The editor sends a design (`level_design.py`, `"format": "chefjeff-player-level-1"`): the level's name, the room size (12×8, 14×9 or 16×10), walls inside the room, the stations (`type`, `x`, `y`, plus `item` for an ingredient source and `vessel` `pan`/`pot` for a stove; the outer wall holds nothing, and serving windows and the plate return stand against it, facing into the room) and up to four dishes (`name`, `price`, `items`). The server builds the bundle from it:

- the map with `map_definition.build_map`. Station ids follow the client's drawing conventions (`serve`, `sink`, `returns`, `extinguisher`, `bin`, `b1`, `p1`, `counter1`, sources by item, beef as `fridge`), their names follow the authored maps (柜台 1, 案板 1, 灶台 1, 出餐口, 水槽, 脏盘回收, 灭火器架, 垃圾桶, 冰箱, 生菜箱: a source by its ingredient), so Jeff's request translates them like the release's, and each station faces the free floor neighbour most towards the room's centre;
- one chef spawning in each half of the longer side;
- the starting inventory: the extinguisher, three clean plates on counters and each stove's own pan or pot;
- the recipes, with each ingredient in the state its cooking step gives (cooked, chopped, or as dispensed).

Counters may split the room in two, one chef working each part and food thrown across ([map format](../map-format.md)); the scripted zoned pair plays such a kitchen, so it calibrates. It refuses a design whose walls cut the room in two, with two dishes of the same ingredients (`DISHES_ALIKE`), with other than exactly one sink, plate return and extinguisher rack, with no serving window or more than two, with a serving window or plate return away from the outer wall, with fewer than three counters, or with a station that has no floor in front of it. A whole level bundle is still accepted as `{"level": …}`.

A bundle is the part of a level a player controls: `level` (name, spawns, initial inventory), `map`, `order_policy` (its `menu`) and `recipe_catalog.recipes` (each dish: name, price, components). The request body may be up to 64 KB; every other command stays at 8 KB.

`level_calibration.normalize` puts the design on the release's rules: the ruleset, the equipment and every ingredient, container and cooking step come from the release, whatever the design carries. Prices must be 10–150 in steps of 10.

Jeff reads dish ids and names, so a player's text never enters the game (owner decision 2026-11-01): the dishes become `dish_1`, `dish_2`… in their order, each named by its components in English (`bread + chopped lettuce + cooked chicken`; component labels likewise). The player's own names, trimmed to 20 characters without control characters, are kept in the recipe catalog's `chefjeff.player_dish_names` for the page (`player_level.names`) and the research record. The page shows those names as written, never translated. `player_level.looks` maps a dish made of exactly an official dish's components (items and states) to that dish (`level_calibration.official_looks`), so the page draws it with the official picture in the release's art style (owner decision 2026-11-02); any other dish is drawn as its ingredients' layers on the plate, bread as the burger's bun. A normalized level normalizes to itself. The level, map, menu and dishes are named `player-` plus 12 hex digits of their content hash, so the same design keeps its id and never shares one with an authored level. A design the configuration contract cannot freeze (for example a dish whose ingredient has no source on the map) is refused with the contract's diagnostics before anything is queued.

## Pacing and target

Owner decision 2026-11-01:

- one order every 30 game seconds, as on levels 1 and 3;
- each dish waits 5 × its chop and cook seconds, rounded to 15 s, within 60–135 s. 135 s is the longest wait that keeps at most five tickets open at this pace, the most the order rail shows. Steak (60 s) and burger (90 s) come out as authored (Overcooked 2's 2.2 s chop and 10 s cook);
- the target is half the scripted pair's median income over 7 order seeds (both pairings and swapped roles, as in `scripts/reference_sweep.py`), rounded down to 10. Authored levels use 21 seeds; a player level reviewed into an official one is rerun on 21.

A level the pair serves nothing on is not playable. One the solo chef can pass (`solo_reaches_target`) is playable with a note.

## The queue

One calibration runs at a time, in its own spawned process at a lower priority (`nice` 10 hosted, 5 local), so it never holds the game server's interpreter lock. The hosted server calibrates each level on one process (about a minute); the local server uses up to four (about 15–20 s). An owner may have one job waiting or running; at most 8 wait; a job running past 300 s is stopped and reported as failed. Reports are kept by content id for the 64 most recent designs, so a design submitted again is answered at once. A failure never carries exception text to the page.

Statistics and research records count every player level as level 0 (`levels.PLAYER_LEVEL`); which design it was is in the record's resolved configuration.
