# Capacity Analyzer v0.1

Status: stage D of the data-driven core. Module `capacity_analyzer.py`; sample reports in [`reports/`](reports/) (regenerate with `python scripts/capacity_reports.py`).

```text
analyze_capacity(resolved_config, analysis_profile=None) -> report
python capacity_analyzer.py level-2 --orders-seed 1 --spawn-seed 0
```

The analyzer reads a resolved configuration (draft or frozen), finds missing resources, production constraints and pacing risks, and **changes nothing**: not the map, recipes, orders, nor any chef decision. It is not a playability oracle and outputs no `playable=true`. To act on a finding, the author edits the source documents and re-runs resolve → analyze → freeze.

## What it computes

1. **Capabilities and reachability** on the real navigation graph: operation points of every station (the same ones chefs use), unreachable stations (ERROR only when no station of a needed type can be operated), and which boards/sinks have a second, perpendicular side for shared work.
2. **Per-dish production DAG** from recipe components and shared transforms:
   - `critical_path_game_ms`: longest component branch plus serving; parallel branches are not summed.
   - `chef_time_game_ms`: all attended work (handling, chopping; heating is unattended).
   - `first_dish_lower_bound_game_ms = max(critical path, chef time / chefs)`, transport excluded — an optimistic bound. Shared chopping shortens it only where geometry allows (level 1: b1, b3; levels 2–3 have no second side, which is not a defect).
   - `single_chef_walking_reference_game_ms`: one chef walks the item through each station on the real map, **for every spawn assignment and both chefs** (spawn sides are shuffled by the spawn seed). This is a reference, not a bound: throws and handoffs can shorten it.
3. **Steady-state load** per resource group *r* with dish mix *p_j*, per-dish occupancy *w_jr* and parallel capacity *C_r*: `I_resource_lb = max_r Σ_j p_j·w_jr / C_r` and, at the configured interval *I*, `load_r = Σ_j p_j·w_jr / (I·C_r)`. Groups: chefs (attended work + washing + plate handling), boards (chop work; shared-capable boards count their best multiplier), stoves holding a pot (`min(stoves, pots)`), sink, plates (dining + washing per dish).
4. **This round's plan**: orders whose window is shorter than the from-scratch bound (WARNING — food prepared ahead can still serve them), goal orders that arrive too late to cook from scratch (WARNING), and goals whose least demanding orders need more chef time than the round provides (ERROR — a provable impossibility).

## Reading a report

| Field | Meaning |
|---|---|
| `input_config_hash` | hash of the analyzed configuration; the report belongs to exactly that input |
| `schema_valid`, `structurally_valid`, `analysis_status` | kept separate; `analysis_status` is `partial` in v0.1 because transport, throws, fire and scheduling are not modelled |
| `assumptions`, `coverage` | what the numbers include and exclude |
| `spawns` | candidate cells, both assignments, and the configured one for a frozen input |
| `resource_lower_bounds_game_ms`, `I_resource_lb_game_ms`, `binding_resource` | necessary lower bounds on the average interval |
| `resource_loads` | average utilisation at the configured interval; > 1 is a WARNING, not proof of failure |
| `suggested_interval_game_ms` | `null`: without calibration (measured sessions or reference-schedule dry runs) the analyzer offers risks and bounds, not a "safe minimum" |

## Accepted levels (orders seed 1, spawn seed 0)

| Level | Steak / burger first-dish bound | I_resource_lb | Binding | Load at configured interval |
|---|---|---|---|---|
| 1 | 15.9 s / – | 12.0 s | stove | stove 0.50 at 24 s |
| 2 | – / 18.9 s | 12.5 s | chefs | chefs 0.42 at 30 s |
| 3 | 18.9 s / 18.9 s | 9.8 s | chefs | chefs 0.33 at 30 s |

These bounds are far below the configured intervals, consistent with the level review: average capacity is not the limiting factor; transport, plate return, assembly learning and the all-orders-must-succeed outcome rule are (see `review.md`). The analyzer does not judge those.
