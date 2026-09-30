# Session record v0.1 — one event stream per round

Status: stage E of the data-driven core. Module `session_record.py`; schemas `schemas/session.schema.json` and `schemas/event.schema.json`.

The record says **what conditions a round actually ran under, what each side could observe and do, what happened and how it ended**. It holds facts and conditions only: no cooperation, attention or quality score is computed or written back. Evaluation methods live outside and read these records.

## One stream, derived views

`SessionLog` is the only sink for a round. Engine events (forwarded from the kitchen), engine inputs, human inputs, model requests and responses, preset communication, bookmarks, pauses and the start/end records each receive one session-wide `seq`. The local file journal, the session bundle, the hosted contribution record (`hosted_records.pilot_record`) and feedback counts are all derived from this stream, so they cannot drift apart.

```text
event = {seq, type, source, game_time_ms, elapsed_wall_ms, clock_id,
         engine_seq?, actor_id?, action_id?, request_id?, order_id?, payload}
bundle = session.json + resolved-config.json + events.jsonl
       + engine-inputs.jsonl + model-requests.jsonl (local only)
```

Local rounds write the bundle to `logs/sessions/<session_id>/` (files are `0600`, written atomically). Hosted and test sessions keep records in memory only and never store model payloads.

## Clocks

- `game_time_ms` is engine time (fixed 50 ms ticks; see the configuration contract).
- `elapsed_wall_ms` is the server's monotonic clock since the log started; model latency is measured on the same clock as its request. Times from different machines are never subtracted; browser-supplied durations would be marked `client_reported`.

## Linking a decision to what happened

| Step | Record | Link |
|---|---|---|
| Agent observes | `ai_request` | `request_id`, `observed_state_seq` (engine event seq at snapshot time), `candidates` in their original order, `payload_sha256` → `model-requests.jsonl` |
| Agent chooses | `ai_response` | same `request_id`, `choice`, `fresh`, `applied`, `accepted_engine_seq`, `action_id` of the started job |
| Engine accepts and runs | `action_start` → `action_done` / `interrupted` / `arrival_conflict` | `action_id` |
| Human input | `human_input` | source, action key, applied/refused; there is no separate "selected" event because the human interface has no choice step |

## Collaboration facts (supplement §4)

- Opportunity vs choice: the configuration records shared-work rules and the map geometry decides second sides; the model request lists the join action among its candidates (opportunity); `shared_work_join` / `shared_work_leave` record who actually joined or left, and `derived.shared_work_overlap_game_ms` the time with two workers.
- Handoffs: `thrown` carries `handoff_id`; the matching `caught` or `landed` carries the same `handoff_id` and an `outcome` (`caught`, `landed_floor`, `landed_station`); unusable landings are `arrival_conflict` events with the throw's `action_id`. `plate partner` completions carry the receiver.

## Replay

The engine logs every outermost external call (`start`, `stop`, `set_manual`, `sprint`, `advance`, `abort`) in `engine-inputs.jsonl`. `kitchen.replay(factory, resolved, inputs)` rebuilds the round without calling any model. When a bundle is written, the recorder replays it and stores `recording_meta.replay.level`:

- `engine_events_verified`: replay reproduced every engine event (seq, type, game time);
- `replay_partial` with the first divergent index when state was changed outside recorded inputs.

Replay reproduces engine-level results, not a model's internal reasoning or pixel-identical rendering.

## session.json fields

| Group | Fields |
|---|---|
| Identity and configuration | `session_id`, `schema_version`, `deployment_mode`, `runtime_versions` (release, Python, engine class, engine semantics, rules and input-language versions), `resolved_config` (file + hash), `config_hash`, `level_id`, `initial_state_seq` |
| Participants and interfaces | `actors[]` with controller type and observation/action/communication interface; `agent_config`: provider, model, actual model, adapter, request policy, prompt versions, memory hash. Values the adapter does not expose are `null` with a reason. Never credentials. |
| Time and completeness | `started_at`, `ended_at`, `clock`, `recording_meta` (scope, sampling, dropped, truncated, clock sources, whether model payloads were collected, replay level), `artifacts` (path, sha256, record count) |
| Outcome and consent | `outcome` (engine result, end reason, goal status, served/expired/unresolved, money, raw score), `contribution_meta` |
| Derived facts | `derived` (`derived-v1`): action counts by actor, shared-work joins/leaves/overlap, handoff counts and outcomes, model call counts and latency range |

Privacy follows [privacy and costs](../privacy-and-costs.md): keys, authorization headers and deletion secrets are never recorded; hosted sessions store nothing unless the player contributes.
