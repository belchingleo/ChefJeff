"""Fixed entry and offline reference trajectories; never calls a model or web server."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kitchen import Food
from spatial_kitchen import SpatialKitchen, tile_key

HERE = Path(__file__).resolve().parent


def build_scene():
    spec = json.loads((HERE / "scenario.json").read_text())
    k = SpatialKitchen(spec["config"])
    initial = spec["initial"]
    assert k.time == initial["clock"] == 0
    # All changes below author the initial state, before the clock or AI starts.
    plates = {}
    for s in k.stations.values():
        if s.food and s.food.stage == "clean_plate":
            plates[s.food.id] = s.food
            s.food = None
    for item in initial["plates"]:
        plate = plates.pop(item["id"])
        plate.stage = item["stage"]
        k.stations[item["station"]].food = plate
    assert not plates
    target = initial["target_food"]
    k.stations[target["station"]].food = Food(
        target["id"], target["stage"], target["chopped"], target["heated"])
    k.stations[target["station"]].heating = True
    prep = initial["prep_food"]
    k.stations[prep["station"]].food = Food(prep["id"], prep["stage"])
    k.serial = 2  # Future fetches start at F3, preserving object identity.
    for who, pos in initial["positions"].items():
        assert tuple(pos) in k.floor
        k.positions[who] = tuple(pos)
        k.chefs[who].location = tile_key(pos)
    # Start the visible player task at t=0; after completion it stays idle.
    ok, reason = k.command("human", spec["human_policy"]["entry_action"])
    assert ok, reason
    k.assert_invariants()
    state = k.snapshot()
    assert state["stations"]["p1"]["burn_in"] == 3
    assert state["stations"]["sink"]["food"]["wash_remaining"] == 4
    assert state["orders"][0]["remaining"] == 35
    assert state["chefs"]["human"]["work_remaining"] == 6
    return k


def run_reference(name, actions, decision_delay=0.0):
    """Each hand-authored decision is applied to fresh candidates, then completed.

    Fixed delay advances the whole game, including the human. This is a timing
    sensitivity check, not the production asynchronous DecisionLoop or API latency.
    """
    k = build_scene()
    trace = [{"kind": "initial_state", "game_time": 0, "state": k.snapshot()}]
    decisions = []
    cursor = 0
    served_target = False
    first_off_heat = None
    for command in actions:
        if decision_delay:
            k.advance(decision_delay)
        candidates = {a.key: a.label for a in k.actions("jeff")}
        assert command in candidates, (name, command, k.time, list(candidates))
        before = k.snapshot()
        hand = k.chefs["jeff"].hand
        delivering_target = command == "serve" and hand and hand.id == "F1" and hand.stage == "ready"
        decision = {"kind": "reference_decision", "controller": "handwritten_offline",
                    "game_time": round(k.time, 6), "action": command,
                    "candidate_actions": candidates, "state_before": before}
        ok, reason = k.command("jeff", command)
        assert ok, (name, command, reason)
        decision.update(accepted=ok, execution=reason)
        while k.chefs["jeff"].job and not k.ended:
            k.advance(.05)
            k.assert_invariants()
        if first_off_heat is None and not k.stations["p1"].heating:
            first_off_heat = round(k.time, 6)
        new_events = k.events[cursor:]
        if delivering_target and any(e.get("kind") == "served" and e.get("actor") == "jeff" for e in new_events):
            served_target = True
        cursor = len(k.events)
        decision["completed_at"] = round(k.time, 6)
        decision["state_after"] = k.snapshot()
        decisions.append(decision)
        trace.append(decision)
        trace.extend({"kind": "engine_event", "event": e} for e in new_events)
        if k.ended:
            break
    summary = {"name": name, "controller": "handwritten_offline_not_model",
               "fixed_delay_per_decision": decision_delay, "ended": k.ended,
               "time": round(k.time, 6), "served": k.served, "money": k.money,
               "burns": k.burns, "fires": k.fires, "bad_reviews": k.bad_reviews,
               "first_off_heat_observed_at": first_off_heat,
               "target_F1_served_unburnt": bool(served_target),
               "success": bool(served_target and k.won() and k.time <= 35 and k.burns == 0),
               "human_events": [e for e in k.events if e.get("actor") == "human"],
               "events": k.events, "final_state": k.snapshot()}
    trace.append({"kind": "reference_result", "result": summary})
    return summary, trace


def export():
    from whitebox_server import SpatialJevClient
    from model_language import INPUT_LANGUAGE_VERSION

    out = HERE / "data"
    out.mkdir(exist_ok=True)
    k = build_scene()
    write = lambda name, data: (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    write("initial_state.json", k.snapshot())
    # Explicit dummy key bypasses credential discovery. Only build the payload;
    # never call ask(), DecisionLoop, or a live GameSession.
    client = SpatialJevClient(k.c, key="offline-unused-placeholder")
    payload = client.payload(k.snapshot(), k.actions("jeff"))
    payload["state"]["input_language"] = INPUT_LANGUAGE_VERSION
    payload["state"]["recent_events"] = []
    payload["state"]["recent_decisions"] = []
    write("decision_input.json", payload)
    plans = [
        ("rescue_counter", ["take pot p1", "put counter2", "wash", "take sink", "plate counter2", "serve"], 0),
        ("rescue_ground", ["take pot p1", "drop", "wash", "take sink", "plate ground P1", "serve"], 0),
        ("wash_first", ["wash", "take sink", "plate p1", "serve"], 0),
        ("rescue_counter_delay1", ["take pot p1", "put counter2", "wash", "take sink", "plate counter2", "serve"], 1),
    ]
    summaries = []
    for name, actions, delay in plans:
        summary, trace = run_reference(name, actions, delay)
        (out / (name + ".jsonl")).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in trace))
        summaries.append({key: value for key, value in summary.items() if key not in ("events", "final_state")})
    write("results.json", summaries)
    sources = ["kitchen.py", "spatial_kitchen.py", "navigation.py", "levels.py", "jev.py",
               "whitebox_server.py", "model_language.py", "model-language-en-v1.json",
               "scenarios/fixed_entry_001/scenario.json", "scenarios/fixed_entry_001/run.py"]
    write("manifest.json", {"scenario": "fixed-entry-001", "model_calls": 0,
                           "integration": "standalone engine factory; not a game-menu entry",
                           "input_note": "Single-step payload with empty histories; future human policy and reference solutions are excluded. Not a production DecisionLoop replay.",
                           "sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}})
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    export()
