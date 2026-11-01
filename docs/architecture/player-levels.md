# Player levels

Status: server side of the level editor. Modules `level_calibration.py` (check, pacing, calibration, freeze) and `player_level_queue.py` (the queue behind the endpoints). There is no editor page yet; the endpoints are ready for one.

```text
POST /api/player-level/submit   {"level": <design>}      -> 202 queued | 200 done (seen before) | 400 refused | 409 | 503
GET  /api/player-level/status?job=<job>                  -> 200 {job, state, content_id, position | report | error} | 404
POST /api/player-level/play     {"job", "game_id", "request_id"}  -> 200 | 404 (not this owner's, or not done) | 409
```

`play` switches the session to a calibrated, playable level between rounds, as `/api/level` does; a restart keeps it and `/api/level` returns to a listed level. While it is active, `/api/state` carries `player_level: {id, names, target, solo_reaches_target}`, `kitchen.level` is null and `kitchen.level_id` is the content id.

The local game server (`cocos_server.py`) offers both endpoints. The hosted server offers them only when started with `--player-levels`, because calibration costs CPU on a machine shared with live kitchens; hosted requests need the page's `X-ChefJeff-Session`, and a session sees only its own jobs.

## The design

A design is the part of a level bundle a player controls: `level` (name, spawns, initial inventory), `map`, `order_policy` (its `menu`) and `recipe_catalog.recipes` (each dish: name, price, components). The request body may be up to 64 KB; every other command stays at 8 KB.

`level_calibration.normalize` puts the design on the release's rules: the ruleset, the equipment and every ingredient, container and cooking step come from the release, whatever the design carries. Prices must be 10–150 in steps of 10.

Jeff reads dish ids and names, so a player's text never enters the game (owner decision 2026-11-01): the dishes become `dish_1`, `dish_2`… in their order, each named by its components in English (`bread + chopped lettuce + cooked chicken`; component labels likewise). The player's own names, trimmed to 20 characters without control characters, are kept in the recipe catalog's `chefjeff.player_dish_names` for the page (`player_level.names`) and the research record. A normalized level normalizes to itself. The level, map, menu and dishes are named `player-` plus 12 hex digits of their content hash, so the same design keeps its id and never shares one with an authored level. A design the configuration contract cannot freeze (for example a dish whose ingredient has no source on the map) is refused with the contract's diagnostics before anything is queued.

## Pacing and target

Owner decision 2026-11-01:

- one order every 30 game seconds, as on levels 1 and 3;
- each dish waits 5 × its chop and cook seconds, rounded to 15 s, within 60–135 s. 135 s is the longest wait that keeps at most five tickets open at this pace, the most the order rail shows. Steak (75 s) and burger (105 s) come out as authored;
- the target is half the scripted pair's median income over 7 order seeds (both pairings and swapped roles, as in `scripts/reference_sweep.py`), rounded down to 10. Authored levels use 21 seeds; a player level reviewed into an official one is rerun on 21.

A level the pair serves nothing on is not playable. One the solo chef can pass (`solo_reaches_target`) is playable with a note.

## The queue

One calibration runs at a time, in its own spawned process at a lower priority (`nice` 10 hosted, 5 local), so it never holds the game server's interpreter lock. The hosted server calibrates each level on one process (about a minute); the local server uses up to four (about 15–20 s). An owner may have one job waiting or running; at most 8 wait; a job running past 300 s is stopped and reported as failed. Reports are kept by content id for the 64 most recent designs, so a design submitted again is answered at once. A failure never carries exception text to the page.

Statistics and research records count every player level as level 0 (`levels.PLAYER_LEVEL`); which design it was is in the record's resolved configuration.
