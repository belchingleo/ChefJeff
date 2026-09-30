# Configuration contract v0.1 — field dictionary

Status: stage B of the data-driven core. Schemas live in `schemas/` (JSON Schema Draft 2020-12); shipped content in `rulesets/`, `content/` and `maps/`. Entry points are in `config_contract.py`.

```text
validate_config(bundle)          -> diagnostics[]            format only
resolve_config(bundle, registry) -> (draft | None, diagnostics[])   references, defaults, units, semantic checks
freeze_config(draft)             -> (resolved, config_hash)  seeds + order plan fixed, then hashed
verify_frozen(resolved)          -> diagnostics[]            schema + hash integrity
```

`python config_contract.py level-2` (or a bundle `.json` path) prints diagnostics, the hash, seeds and order count.

## Principles

- **One source of truth per fact.** Equipment says what a device can do and how fast; the map places instances; recipes define items, shared transforms and dishes; orders define demand; the level composes versions and owns participants, initial inventory, clock, goal and end policy. Equipment counts come from the map, plates and pots from the level inventory.
- **Three different versions.** `schema_version` = document format; `version` (maps: `revision`) = content version; `ruleset_ref` = execution semantics. References are always `{id, version}` and resolve only to local files (`Registry`); nothing is downloaded.
- **Units.** Durations are integer game milliseconds (`*_game_ms`); speeds are cells per game second; money is an integer. NaN, infinities, negative durations and zero intervals are rejected by the schemas.
- **No silent repair.** The resolver fills only the defaults listed below and records each one in `applied_defaults`. It never changes difficulty or rewrites author choices.
- **Diagnostics** always carry `code`, `severity` (`ERROR`/`WARNING`), `field_path` and `message`, plus `evidence` where useful. Any ERROR means no draft.

## Documents

### Ruleset (`rulesets/<id>.json`)

Selects semantics the engine already implements; it cannot add mechanics.

Optional fields switch a behaviour on; when absent, the simpler behaviour named in the row applies. The values column shows the shipped `chefjeff-service` ruleset.

| Field | Meaning | `chefjeff-service` |
|---|---|---|
| `engine_semantics` | outcome rules the engine implements: `continuous-2026-09` (net revenue judged at closing, burnt-dish tiers, no bad reviews) | `continuous-2026-09` |
| `tick_game_ms` | fixed simulation step | 50 |
| `supported_equipment_types` | types with engine semantics | 9 types |
| `operations.handling_game_ms` / `extinguish_game_ms` / `clear_game_ms` | take/put/plate/serve; extinguish; clear pot | 150 / 4000 / 2000 |
| `operations.ground_assembly` | optional; multi-component menus may assemble with a plate or ingredient on the floor as on a counter (`assemble ground <item_id>`); absent: floor items only swap | `true` |
| `movement.*` | walk cells/s; sprint multiplier, duration and cooldown; chef separation; sprint push and food nudge | 4.5; 1.4× for 1000 ms, 3000 ms cooldown; 0.4; 0.25 / 0.25 |
| `movement.cabinet_clearance_cells` | optional one chef body size against workstations: feet stay `front` south of a cell, clear of its front panel, and `side` from its east/west edges (the measured half width of the chef art); stand points follow; the north side and walls keep 0.2. Absent: 0.2 everywhere, with board contact faces | `{front: 0.45, side: 0.35}` |
| `movement.operate_at_walk_limit` | optional; each face is worked from where walking toward it stops, in place when already there. Absent: fixed stand-offs | `true` |
| `movement.stall_replan` | optional; re-plan a stalled route around the other chef | after 300 ms below 0.05 cells |
| `movement.corner_slide_cells` | optional; a fully blocked single-direction key walk first slides sideways by at most this much when that clears the edge | 0.3 |
| `movement.approach_partner` | optional; offer "go partner", a walk into the other chef that ends on contact (contact pushes; a sprint adds one bounded shove) | `true` |
| `throw.*` | enabled; `range_cells` for throwable ingredients; optional `pass_range_cells` for plates, dishes, pots and the extinguisher (absent: not passable); speed; minimum flight; catch radius | on; 4; 4; 12 cells/s; 200 ms; 0.75 |
| `tableware.dining_game_ms` / `return_capacity` | customer plate return delay; return station capacity | 8000 / 1 |
| `fire.spread_interval_game_ms` / `loss_threshold` | spread cadence; simultaneous fires that end the round | 8000 / 5 |
| `penalties.*` | wrong dish (no shown order waits for it), expired order, new fire, discard/clear | −20, −10, −5, −2 |
| `burnt_service[]` | tiers by how long the worst component was burnt when it left the heat, `{max_overcook_game_ms, outcome, adjustment}`; ascending, last `null` | ≤ 5000 accepted −10; longer refused (order keeps waiting) |
| `abstract_travel.*` | travel of the non-spatial text prototype only | 1000 / 3000 |
| `limits.*` | technical safety limits measured on this engine, not difficulty; `max_visible_orders` is the order rail's ticket count | 2 actors, 256 instances, 500 orders, 1 h, 1 MiB, 64 objects, 5 tickets |

### Equipment catalog (`content/equipment/<id>.json`)

`types.<type_id>`: `name`, `capabilities` (`dispense`, `chop`, `heat`, `store`, `assemble`, `serve`, `discard`, `wash`, `return_plates`, `store_tool`), `slots`, `worker_requirement` (`attended` needs a chef working; `unattended` progresses alone; `none`), `work_rates` per capability, optional `shared_work`, `holds_container`, typed `params`, `combustible`.

**Shared work** (collaboration supplement §3.1): `shared_work.<capability> = {max_workers, rate_multiplier}`. The effective rate with *n* active workers is `work_rate × rate_multiplier[n]`, so `duration(n) = work_game_ms / (work_rate × rate_multiplier[n])`. A second worker joining mid-way speeds up the remaining work immediately; leaving restores the single rate; progress is kept. Whether a *second operation side* exists is decided by map geometry, never by a level flag. Shipped boards and sinks: `{max_workers: 2, rate_multiplier: {"1": 1.0, "2": 2.0}}` — chopping 6 s alone / 3 s together, washing 4 s / 2 s. The analyzer may use these fields; agents are never told to cooperate.

The resolver rejects catalog types the ruleset does not support (`UNSUPPORTED_EQUIPMENT_TYPE`); e.g. a microwave is not silently treated as a stove.

### Map (`maps/<id>.json`, schema 2)

Geometry fields are unchanged (see `docs/map-format.md`). Schema 2 adds `areas` (`{area_id: {name}}`), optional `floor_areas` (`{axis, split, below, at_or_above}`) and per-instance `type` (catalog type), `name`, `area` and `params` (e.g. `{"item": "beef"}` for an ingredient source). Instance order is the engine's station order. Schema-1 maps remain loadable: `upgrade_map` infers types from the historical ID conventions.

### Recipe catalog (`content/recipes/<id>.json`)

| Field | Meaning |
|---|---|
| `items.<item>` | `name`, `states`, `initial_state`, `platable_states` (may go on a plate), `throwable_states` |
| `containers.plate.wash_work_game_ms` | washing work (shipped 4000); divided by the sink's wash rate |
| `transforms[]` | defined **once per item** and shared by all recipes: `operation` (`chop`/`heat`), `from` → `to`, `work_game_ms`, optional `container: pot` and `overcook {state, after_done_game_ms, fire_after_overcook_game_ms}` |
| `recipes.<id>` | `name`, `container: plate`, `components[{item, state}]` (order-free), `price` |

Each recipe's step DAG is derived from its components and the shared transforms, so chopping beef has one duration however many recipes use it. Customer patience is not a recipe field.

### Order policy (`content/orders/<id>.json`)

| Mode | Fields | Plan |
|---|---|---|
| `fixed_interval_seeded` | `menu[{recipe_ref, weight}]`, `first_spawn_game_ms` (t0), `interval_game_ms` (I), optional `stop_spawn_game_ms` (C, default = D: orders arrive until closing) | `a_i = t0 + i·I` for `a_i < C`; recipe by cumulative weights in stable `recipe_ref` order with a dedicated RNG; deadline `min(a_i + patience, D)` |
| `fixed_table` | `arrivals[{recipe_ref, arrival_game_ms, patience_game_ms?}]` | stable sort by arrival; deadline clipped to D |

Common: `patience_default_game_ms`, `patience_by_recipe`. The algorithm name is stored with the plan. There is no order total for the seeded mode: a finite round yields finite orders. Required: `0 ≤ t0 < C ≤ D`, `I > 0`, patience > 0.

### Level (`content/levels/<id>.json`)

| Field | Meaning |
|---|---|
| `*_ref` | exact versions of ruleset, map, equipment catalog, recipe catalog and order policy |
| `actors[]` | `human` and `jeff` with `controller_type`; model/provider settings and keys are bound at round start, never stored here |
| `spawns` | `nearest_floor_to_center_shuffled`: nearest floor cell to each center on its side of `partition`, then shuffled with the spawn seed |
| `initial_inventory[]` | `{object: plate|pot|extinguisher, id, state?, at}`; IDs `D1..Dn`, `P1..Pn`, exactly one `E1`; one object per slot |
| `clock` | default and allowed game-per-real-time speeds (shipped 0.75; options 0.5 / 0.75 / 1) |
| `round_limit_game_ms` | D |
| `goal` | `minimum_money {min_money}`: net revenue at closing |
| `end_policy` | `fixed_round`: the round always runs to D and settles there |
| `seeds.orders` / `seeds.spawn` | fixed integers, or `null` to draw at freeze time (recorded) |

## Defaults filled by the resolver

| Path | Default |
|---|---|
| `order_policy.first_spawn_game_ms` | 0 |
| `order_policy.stop_spawn_game_ms` (seeded) | the round limit |
| `order_policy.patience_by_recipe` | `{}` |
| `level.initial_inventory[i].state` (plates) | `clean` |

## Resolved configuration (frozen)

Contains the full text of every referenced document, `sources` (id, version, sha256 of each), `stations` (instances in engine order with resolved type), `applied_defaults`, `overrides`, `seeds` (`orders`, `spawn`, `source`), `order_plan` (`algorithm`, orders with arrival/deadline/patience in game ms) and `config_hash` (`sha256:` over the canonical JSON of everything else). A hash alone is not enough to restore a configuration; sessions store the resolved text or an immutable reference to it.

## Diagnostic codes

| Code | Severity | When |
|---|---|---|
| `SCHEMA_INVALID` | ERROR | a document violates its schema |
| `REF_MISSING`, `REF_VERSION_MISMATCH`, `REF_MISMATCH` | ERROR | a reference cannot be resolved exactly |
| `MAP_INVALID` | ERROR | geometry rules (boundary, footprints, access, connectivity) |
| `MAP_UNKNOWN_EQUIPMENT_TYPE`, `MAP_UNKNOWN_PARAM`, `MAP_MISSING_PARAM`, `MAP_UNKNOWN_ITEM` | ERROR | instance does not match the catalog/recipes |
| `UNSUPPORTED_EQUIPMENT_TYPE`, `UNSUPPORTED_EQUIPMENT_COUNT` | ERROR | catalog/map needs semantics this engine lacks |
| `SHARED_WORK_RATE_MISSING`, `SHARED_WORK_CAPABILITY` | ERROR | a shared-work rule lacks a rate for some allowed worker count, or names a capability the type does not have |
| `RECIPE_UNKNOWN_ITEM`, `RECIPE_STATE_INVALID` | ERROR | inconsistent recipe catalog |
| `NO_PRODUCTION_CHAIN` | ERROR | an ordered dish's component has no source or no equipment for a needed transform |
| `ORDER_UNKNOWN_RECIPE`, `ORDER_MODE_FIELD`, `ORDER_TIMING` | ERROR | invalid demand definition |
| `GOAL_EXCEEDS_REVENUE` | ERROR | the goal needs more money than the plan can offer at full price |
| `ORDER_BACKLOG_EXCEEDS_DISPLAY` | ERROR | `floor(longest countdown / interval) + 1` tickets could wait at once, more than `max_visible_orders` |
| `RULESET_BURNT_TIERS` | ERROR | burnt tiers do not ascend or do not end with an open tier |
| `INVENTORY_*` | ERROR | unknown/incompatible/duplicate placements, ID sequences, extinguisher count, no plates |
| `ACTORS_UNSUPPORTED`, `CLOCK_DEFAULT`, `SPAWN_NO_FLOOR` | ERROR | participants, clock or spawns not supported |
| `LIMIT_*` | ERROR | technical limits exceeded |
| `PATIENCE_SHORT` | WARNING | patience under 10 s |

Balance and load findings (average overload, long transport, tight patience) belong to the Capacity Analyzer and are warnings, not errors.
