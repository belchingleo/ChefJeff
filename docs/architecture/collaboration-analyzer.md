# Collaboration Analyzer v0.1

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

## Baseline ladder (`scripts/reference_sweep.py --ladder`)

Each level's configured round is played three ways. The fourth rung, a model-controlled Jeff, needs a paid model, so it is measured on real rounds with the analyzer.

| Rung | Players |
|---|---|
| solo | one scripted chef (`reference_policy.choose_solo`), the other idle |
| solo + random | the same chef, with a partner choosing uniformly among its legal actions (seeded) |
| pair | the best scripted reference pair (the calibration pair) |

Results for 2026-09-30, after stations are worked from the walk limit (`reports/baseline-ladder.json`):

| Level | Target | Solo | Solo + random | Pair | Pair contribution rate |
|---|---|---|---|---|---|
| 1 | 150 | **300** | 20 | 300 | 0.85 |
| 2 | 150 | 146 | −26 | 318 | 0.88 |
| 3 | 190 | 103 | 93 | 390 | 0.96 |

How to read this:

- A model-controlled Jeff should at least beat the human playing alone. A random partner costs far more than it helps.
- Level design must need both chefs, so the solo rung has to stay below the target (owner decision). Levels 2 and 3 meet this and `test_collaboration_analyzer` checks it. Level 1 is the practice tutorial and is exempt (owner decision, 2026-09-29): one scripted chef earns as much as the pair there.
- The solo policy is scripted and simple, so it is a lower bound on solo play. A skilled person could do better. The level-2 margin is ¥4.

## Limits

- **Deliberately inclusive.** Any handling of an item that ends up in an accepted dish counts, as in AgentWorld. The only exception is handling cancelled by a loop in the same life of the item.
- **Enabling work without item contact is not traced.** For example, extinguishing a fire so a stove can cook again is labelled `support`.
- **Not every kind of help is credited.** Standing in the right place to catch an item is not an action, so it earns nothing. The throw and the later handling of the item are credited.
- **One action unit for both chefs.** Keyboard movement is not an action, and neither is Jeff's walking.
