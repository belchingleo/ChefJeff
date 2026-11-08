# Collaboration Analyzer v0.3

`collaboration_analyzer.py` answers one question about a finished round: **which completed actions actually made the dishes that were accepted, and who did them.** It is a deterministic counterpart of Causal Collaboration Effectiveness (CCE) from AgentWorld (arXiv 2609.31590). AgentWorld asks an LLM judge whether one action enabled another. This engine knows every item, so contribution is traced through item provenance and no model is involved.

```text
python collaboration_analyzer.py logs/sessions/<id>      replays the bundle (no model calls) and prints the report
analyze_collaboration(kitchen) -> report                 any finished kitchen (tests, calibration)
python scripts/reference_sweep.py --ladder               baseline ladder with the report of every rung
```

## Provenance (`provenance.py`)

The engine keeps a read-only `kitchen.provenance`. Around every completed job it compares where each item is before and after the job, and in what state. Items include:

- ingredients and dishes;
- plates and pots;
- the extinguisher;
- items in flight;
- plates with customers.

Every item that moved, changed, appeared or disappeared gets a *touch*: the step, the completed action ids (a shared chop completes both chefs), the actors, the action kind and where the item is afterwards.

It also records three kinds of links:

- **Merges:** an item that disappears into a plate becomes a parent of that dish, cut at the merge.
- **Containers:** food entering a pot records the pot as its container, cut at that moment.
- **Serves:** the dish served, its plate and the outcome (served, wrong dish or refused).

Events, snapshots and engine behaviour are unchanged. Behaviour fingerprints still match, and a replayed session rebuilds the same provenance.

## Definitions (owner decisions 2026-09-28)

| Term | Meaning |
|---|---|
| Action | A completed job other than go, wait, stop or continue. Walking, including "go partner", is not an action. |
| Contributing | On the provenance of a dish accepted at the serving window. That covers the dish's effective touches, the items merged into it (up to the merge), its plate since the plate's previous dish, and the pot handling since that pot last held food. The serve itself also counts. |
| Effective touch | A touch that brings an item back to a place and state it already had in the same life cancels the touches in between. A plate starts a new life after each dish, and a pot after each food it held. |
| Harmful | Penalised on completion: a dish nobody waited for, a refused dish, discarding, clearing or emptying a pot. Harmful actions are counted separately and are never contributing. |
| Wasted | Every other action. It is labelled `support` if it touched only tools, pots or nothing; `loop` if all its touches were cancelled; `unused` if its handling never reached an accepted dish, for example food still cooking at closing. |
| Cross-chef handoff | Consecutive effective touches of the same item on a dish's provenance, made by different chefs. |

Expired orders and fires come from time passing, not from one action. They are reported as `round_penalties`.

The report contains:

- the contribution rate, i.e. contributing actions divided by actions;
- per chef: actions, contributing actions, contribution rate, share of all contributing actions, harmful and wasted counts;
- for each accepted dish: who contributed and how many cross-chef handoffs it needed;
- harmful actions with their reasons.

## Contribution, delay and idle time (owner decision 2026-10-02, experimental)

The round record shows three measures per chef. They are experimental and open for community feedback.

- **Contribution**: each chef's share of the *standard time* of the accepted dishes. A step's standard time is its configured work (chopping or washing work, otherwise the handling time) plus the shortest walk its carried items needed from where their previous step finished (`provenance` records where each step finished; first touches count no walk). Cooking is nobody's work. Actual action time is not used because Jeff's actions include his walk and the player's keyboard walking is not an action.
- **Delay**: per accepted dish, its actual serve time minus an ideal serve time. The ideal runs the same steps at standard time, each starting as soon as its inputs are there and its chef has finished their earlier useful work; a first touch may start at the order. Cooked food arrives when it is ready. The delay is split over the chefs by Shapley value: each chef's average saving when the chefs are made ideal one at a time, in every order. A chef who is left as they were keeps the lag they actually had after their inputs arrived.
- **Idle**: seconds on actions labelled `loop` or `unused`, plus waiting. The player's own walking is not an action, so the player's idle time is a lower bound.

The **critical path** of each dish (the chain of last-arriving inputs, with cooked food arriving when it is ready) stays in the report but is not shown: it tells where a dish last waited, not who contributed.

## Baseline ladder (`scripts/reference_sweep.py --ladder`)

Each level's configured round is played three ways. The fourth rung, a model-controlled Jeff, needs a paid model, so it is measured on real rounds with the analyzer.

| Rung | Players |
|---|---|
| solo | one scripted chef (`reference_policy.choose_solo`), the other idle |
| solo + random | the same chef, with a partner choosing uniformly among its legal actions (seeded) |
| pair | the best scripted reference pair (the calibration pair) |

Results for 2026-11-08, on each level's configured round with Jeff deciding every 0.5 s (`reports/baseline-ladder.json`):

| Level | Target | Solo | Solo + random | Pair | Pair contribution rate |
|---|---|---|---|---|---|
| 1 | 200 | **450** | −30 | 450 | 0.87 |
| 2 | 200 | **209** | −81 | 560 | 0.95 |
| 3 | 160 | **283** | 6 | 490 | 0.95 |
| 4 | 100 | −50 | −54 | 440 | 0.91 |

How to read this:

- A model-controlled Jeff should at least beat the human playing alone. A random partner costs far more than it helps.
- Only Level 4 is built to need both chefs: a row of counters runs from wall to wall, the ingredients, stoves and serving window are on one side and the boards and sink on the other, so one chef alone serves nothing. The level says so (`requires_pair: true`), and `tests/test_level_four.py` checks it against the calibration run set (`reports/calibration.json`): no solo run of the 21 reaches the target, and the report's entry must have been made for the level's current configuration hash and run set, or the test fails until it is recalibrated.
- Levels 1–3 do not force cooperation. One scripted chef reaches the target on Level 1 on every calibration seed (more than the pair: the practice level, exempt since 2026-09-29), on Level 2 on 10 of 21 (its median, 116, stays below the target, which `test_collaboration_analyzer` checks; the configured round above is one of the 10), and on Level 3 on 19 of 21 (exempt since 2026-10-06). Two chefs are faster on Levels 2 and 3.
- `scripts/decision_stats.py` reports a cooperation gain for played rounds: net revenue minus the solo script's calibration median on the same level configuration, labelled relative to the solo script baseline.
- The solo policy is scripted and simple, so it is a lower bound on solo play. A skilled person could do better on Levels 1–3; on Level 4 the split floor, not the script, keeps one chef from serving.

## Limits

- **Deliberately inclusive.** Any handling of an item that ends up in an accepted dish counts, as in AgentWorld. The only exception is handling cancelled by a loop in the same life of the item.
- **Enabling work without item contact is not traced.** For example, extinguishing a fire so a stove can cook again is labelled `support`.
- **Not every kind of help is credited.** Standing in the right place to catch an item is not an action, so it earns nothing. The throw and the later handling of the item are credited.
- **One action unit for both chefs.** Keyboard movement is not an action, and neither is Jeff's walking.
