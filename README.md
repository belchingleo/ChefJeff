# ChefJeff · Cook Together

English · [中文](README.zh-CN.md)

What can't be computed? We seem to have been asking this ever since computers appeared: what can a computer not do?
My first answer was cooking. Does a computer know how to cook? Now we can ask: can an AI cook?

ChefJeff is a real-time cooking game in which a person and an AI cook together, and an extensible environment for human–AI collaboration experiments. Putting a person and an AI in one kitchen, it tests cooperation rather than competition. We want to offer a visual environment for understanding a world that people and AI share, and to grow an open human–AI collaboration benchmark together with the open-source community. Researchers in human–computer interaction, human factors and human–machine communication are welcome to use it in their own studies.

![Gameplay](docs/images/gameplay.png)

Where to start: [run it locally](#run-it-locally) · [connect your own model](#jeff-and-model-integration) · [change the configuration](#five-data-models) · [the environment and benchmark](#building-a-humanai-collaboration-environment-and-benchmark)

> Current version: **0.6.0-beta.1**, the first public test release. You need your own model API, and interfaces and analysis rules may still change. We suggest starting with Jev models: they don't play especially well, but they are cheap. Results from other models are welcome.

---

## Run it locally

You need Python 3.10 or later, a computer with a keyboard, and a browser that supports WebGL. The backend uses only the Python standard library. The web client is already built and included in the repository, so you don't need to rebuild it just to play.

```sh
git clone https://github.com/belchingleo/ChefJeff.git
cd ChefJeff
python3 scripts/launch_web.py
```

On Windows, use `py -3 scripts/launch_web.py`. You can also double-click `start-web.command` (macOS) or `start-web.bat` (Windows).

Then open <http://127.0.0.1:8775/> in your browser, enter your model API details under Settings, and start a round once the connection test succeeds. ChefJeff supports the TypeSafe Jev interface and Chat Completions-compatible interfaces. If you use another model, check for yourself that it returns actions in the required format and responds quickly enough.

> **About costs**: the connection test and every round use your own model account, and that account pays for the calls. By default a round makes at most 200 calls (adjustable from 1 to 2000). This limits the number of calls, not the amount of money. This is a real-time game and the kitchen never stops, so if the model is too slow, Jeff spends most of the round standing still, thinking.

Tested so far: macOS 15.6, Python 3.12, a Chromium-based browser, with TypeSafe Jev (jev-latest) and DeepSeek V4.1-Flash as models. Other systems and models have not been checked one by one yet; reports are welcome.

---

## How the game works

ChefJeff plays much like Overcooked: two chefs cook together. The difference is that the other chef is controlled by an AI.

You control one chef with the keyboard: walk, fetch ingredients, chop, cook, plate, serve and wash plates. Jeff is the other chef, driven by a large language model, and every few seconds he decides what to do next. You share one kitchen and the same physical rules (walking speed, throwing distance, collisions), but you see the kitchen and act in it in different ways; see [Jeff and model integration](#jeff-and-model-integration).

A round lasts 180 seconds. Orders arrive at regular intervals, each with its own countdown, and an order that expires costs you money. Reaching the target does not end the round early: the kitchen stays open until closing time, and the level is cleared if net revenue at closing meets the target. So once you've reached it, you and Jeff can keep going for more.

| Level | Menu | What's special | Target |
| --- | --- | --- | --- |
| Level 1 · Steak | Steak ¥50 | Practice level: learn to chop, fry, plate and serve | ¥150 |
| Level 2 · Burger | Burger ¥80 | A long counter splits the kitchen in two, so a lot has to be passed across it | ¥150 |
| Level 3 · Steak and burger | Steak, burger | Two stoves and three frying pans; both dishes at once | ¥190 |

Working together, you chop, cook, plate and serve between you. Along the way Jeff may pass you dishes, or chop, pass and wash up alongside you. He may also bump you aside to handle something himself, and you can do the same to him.
If the model isn't doing what you want, press 1–6 to tell Jeff what kind of work you'd like to do, or that he just made a mistake.

The controls work much as in Overcooked:

| Key | Action |
| --- | --- |
| WASD or arrow keys | Move; press **Q** while moving to dash |
| Space | Do whatever the thing in front of you needs: fetch, pick up, put down, put in the pan, plate, serve; it can also chop and wash |
| E | Processing only: chop, wash, put out a fire. If there is nothing to process in front of you and you are holding something, throw it forward |
| 1–6 | Tell Jeff what kind of work you want to do, or point out a mistake |
| Shift | Bookmark the current moment without pausing or interrupting anything; bookmarks are included in the run export |
| Esc or P | Pause (use P on iPad keyboards without an Esc key). Settings let you connect a model, switch language, adjust volume and export the run |

After each round, a round record pops up. It shows how many times you and Jeff each fetched ingredients, chopped, cooked, served and washed plates, and how much time each of you spent on getting dishes out.

The game has Chinese and English interfaces, with 8-bit style music and sound effects. A keyboard is required for now; phones and touch-only devices are not supported yet. See [device support](docs/device-support.md) and the [current rules](docs/current-rules.md).

---

## Technical foundations

### Five data models

"Model" here means a content configuration, not an AI model:

- **Map**: where the walls, counters and equipment are, and which side each one is worked from.
- **Recipes**: which ingredients exist, which need chopping and which need cooking, what each dish is made of (four ingredients at most) and what it sells for.
- **Orders**: which dishes come in, how often, and how long each order can wait.
- **Equipment**: what each type of equipment does, how fast, and whether two chefs can use it at once.
- **Level**: combines the other four, plus the plates and pans at the start, the target revenue and the random seeds.

All of these are JSON files in `content/` and `maps/`, validated against `schemas/`. Rules shared by every level, such as movement, throwing and penalties, live in `rulesets/`. The web client also reads ingredient, dish and equipment names from this data. Within the mechanics that the current engine and schemas support, a new level is made by combining these configurations, with no special code for any level. Gameplay beyond the existing mechanics still requires extending the engine. See the [configuration contract](docs/architecture/configuration-contract.md).

### Jeff and model integration

Jeff doesn't see the screen. He reads a structured game state and picks one of the actions that are legal right now:

```
Current kitchen state (orders, workstations, items on the floor, what each chef is doing)
        + rule descriptions + every action available right now
        ↓
      The model picks one action (for example "chop b1" or "assemble ground F2")
        ↓
      The kitchen engine checks that the action is legal, runs it, and writes the result to the event log
```

- **Different observation and control.** You press keys in real time and move step by step. Jeff picks whole steps such as "fetch", "chop" or "serve", and the engine walks him there and carries them out.
- **The default rule descriptions state only facts.** Everything sent to Jeff is in English, and the two chefs are always called `human` and `jeff`. The rules say what can be done and what will happen. They don't assign roles or suggest how to cooperate.
- **Two other inputs are run conditions.** The messages you send with 1–6, and summaries of earlier rounds from rolling cross-round memory (on by default; it can be turned off or cleared in Settings), are also sent to Jeff. When rounds are analysed, these are recorded separately from the rule descriptions.
- **Every decision is logged.** What was chosen, whether it was accepted and whether it was completed are recorded separately, so you can check afterwards what actually happened.

To connect your own model, implement two methods, `payload(state, actions)` and `ask(payload)`. See [agent integration](docs/agent-integration.md).

### Records and analysis

1. **Round records and replay**: when a round starts, its configuration is frozen and hashed; from then on every step is stored as one event stream, together with the player's inputs. `python3 collaboration_analyzer.py logs/sessions/<round id>` replays the round without calling any model and checks the replay against the original record. Replays are only guaranteed to match within the same version; a round recorded by an older version may replay differently. See [session records](docs/architecture/session-record.md).
2. **Item history and collaboration analysis**: the engine records whose hands every ingredient, plate and pan has passed through. Using the rules as currently defined, tracing back from each served dish shows how every action contributed to it, how much time each chef spent on served dishes, and each chef's share of the "critical path" that set the serving pace. These results can be recomputed exactly, but whether they reflect good cooperation still needs human interpretation. For example, ingredients prepared early but left unused because the orders changed don't mean the preparation was pointless at the time. The idea draws on the CCE metric from AgentWorld (arXiv 2609.31590); see [collaboration analysis](docs/architecture/collaboration-analyzer.md).

   **How the critical path is computed:** start from the serve and walk backwards. For each step, look at the items it touched (plate, ingredients, pan) and find where each was last handled; the one that finished latest becomes the previous step. Repeat until nothing earlier is found (usually a fetch). This chain is the sequence of actions that decided when the dish could go out. Each step counts its actual action time, minus any overlap with the previous step, and is credited to the chef who did it, split evenly when both chefs did it together. Gaps between steps, such as a pan frying unattended or one chef waiting for the other, are counted separately as waiting time and credited to no one.

### Code layout

| Area | Main files |
| --- | --- |
| Kitchen rules | `kitchen.py`, `rules.py`, `config_contract.py` |
| Maps and space | `maps/`, `spatial_kitchen.py`, `navigation.py` |
| Jeff's decision loop and model adapters | `jev.py`, `whitebox_server.py`, `player_api.py`, `model_language.py` |
| Round records and analysis | `session_record.py`, `provenance.py`, `collaboration_analyzer.py`, `round_summary.py`, `capacity_analyzer.py` |
| Local servers | `web_server.py`, `cocos_server.py` |
| Graphics and sound | `cocos-kitchen/` (Cocos Creator 3.8.8, TypeScript) |

```sh
python3 -m unittest discover -s tests     # offline tests (no paid model calls)
python3 scripts/audit_release.py          # pre-release check (keys, private files)
python3 scripts/build_cocos.py web        # rebuild the web client, only needed after changing client code (needs Cocos Creator 3.8.8)
```

---

## Data recording and collection

**Running locally:** ChefJeff never uploads round data on its own. Every record is written to your own computer, and whether to share it is up to you.

| Record | Location | Contents | Use |
| --- | --- | --- | --- |
| Session record bundle | `logs/sessions/<round id>/` | The frozen configuration, the event stream, engine inputs, and the exact requests sent to the model | Replay and collaboration analysis; contains no API key |
| Runtime logs | `logs/` | Full game state and model output | Troubleshooting; may contain the model's raw replies, so check before sharing |
| Run export | Pause menu → Settings → Export Run | An allowlist: version and round ids, timing, results, call counts and usage, event counts, bookmarks, preset messages, and recent action events | Attach to an issue; contains no key, model endpoint, cross-round memory, or full model requests and replies |
| Cross-round memory | `.player-memory.json` | The last three rounds with the same model, at most 18 sampled events each | Sent to Jeff as a run condition; can be turned off or cleared in Settings |

The export shows a preview first. If you'd like to contribute a round to research, attach the export to an issue and say which model and level you used; if a full replay is needed, the session record bundle can be shared on request.

---

## Building a human–AI collaboration environment and benchmark

With this game we want to answer one question: **when things move fast and time is short, how do people and AI work together?**

- **We care about the process.** The number of orders served is the result. What we want to know is who took on which task and when, how each responded to the other, and how they recovered when a plan fell apart.
- **We don't arrange the cooperation for Jeff.** The default rule descriptions assign no roles and offer no cooperation strategy. Whether and how cooperation happens is exactly what we want to observe.
- **We look in both directions.** We watch how the AI adapts to people, and how people work with the AI.

### Why a benchmark like this is needed

Most agent evaluations today test whether an agent can finish a task on its own: write code, look something up, operate a web page. Yet we are, and will long remain, in an era of people and agents working together. This is especially true in embodied settings, where fully autonomous agents are not yet a reality: AI and people share an environment, act at the same time, and may bear the consequences together. In human–AI collaboration, then, what matters is not only whether the AI knows what to do and how, but whether it responds in time, understands what its human partner is doing, and knows when to step back, when to step in and when to cover for them.

Overcooked-AI (Carroll et al., 2019) used an Overcooked-style environment to study how people coordinate with reinforcement-learning agents. ChefJeff targets large-language-model agents: the rules are described in text, actions are whole decisions such as "chop" or "serve", and the model decides in real time, under real latency. In this setting:

1. **Speed is part of the ability.** The kitchen doesn't wait for the model to finish thinking. The same decision made a few seconds late leads to a different outcome, so decision quality, response time and call cost all end up on the same bill.
2. **You can see where failure happens.** The history of every ingredient, whether each decision was accepted and completed, and each chef's share of the critical path are all recorded. When an agent does poorly, you can ask: is it unable to plan, unable to read its partner, or did the interface never give it a chance to plan?
3. **Reproducible and comparable.** Configuration hashes, fixed seeds, offline replay and the baseline ladder put rounds from different models and different players on the same scale.
4. **Run conditions can be controlled one at a time.** How much of the partner's state is visible, whether the two can communicate, whether there is cross-round memory: each can be switched on or off as a separate variable to see how it changes the cooperation.
5. **People are observed too.** How does an agent compare with a human partner? Would people rather direct the AI, or work with it?
6. **Cheap to extend.** A new scenario is a handful of JSON files, the backend uses only the Python standard library, and the community can keep adding scenarios and rounds.

### What the benchmark is made of

Each scenario is a single map:

- **Scenario**: one frozen five-model configuration, with its configuration hash, random seeds and the reference scores from the baseline ladder. The baseline ladder runs scripted chefs in three setups: one chef alone, one chef plus a partner who wanders at random, and two scripted chefs working together. The target revenue is half of what the scripted pair earns, and the solo script must fall short of it (Level 1, the practice level, is exempt). This only shows that the scripts can't reach the target alone; the real difficulty still has to be checked with people and other agents.
- **Participants and interface conditions**: people, models or scripted chefs, and how much each can observe and communicate.
- **Records**: replayable event streams and item histories.
- **Metrics**: outcomes (net revenue, level cleared) and process (division of labour, share of the critical path, how many decisions were accepted and completed, response time), reported separately.
- **Round collection**: rounds contributed by the community, with different players, models, maps and team setups.

### Creative workshop (planned; the parts already in place are listed below)

We want players to design their own levels, and to get a playable, difficulty-calibrated new level from a single sentence. The creative workshop will offer three ways to do it:

- **Generate with a coding agent**: in tools such as Codex or Claude Code, a level-generation skill turns a description into JSON files for the map, recipes, orders and level, which you then import into the workshop.
- **Use your own model in the workshop**: enter your own API, as you do for Jeff, and generate from a description right in the workshop.
- **Edit visually**: place and change things directly in a map editor and a recipe editor. Small changes cost no tokens, and levels become easier to tweak and play again.

All three produce the same data, and every imported level goes through the same validation and calibration before it can be played. Already in place:

- the five data models and their schemas: a level is described entirely by data, with no code;
- the configuration check, which points out problems before a round starts, such as a dish that can't be made or a dish with more than four ingredients;
- capacity analysis, which estimates a map's load before anyone plays it: which piece of equipment is busiest, and whether the order pace will overwhelm the kitchen (see [capacity analysis](docs/architecture/capacity-analyzer.md)); the baseline ladder can then set a target for a new level;
- a web client that reads ingredient, dish and equipment names from the configuration and builds walls, counters and equipment from modular pixel art, so a new layout needs no client code changes.

### Version history

- **0.5.9-alpha** (2026-09-27): the first playable version. Three maps, with the rules written directly in the code.
- **0.6.0-beta.1** (2026-10-01): the first public test release. Now driven by five data models, with one set of rules for all three levels (180-second rounds, judged on net revenue at closing); the old rules are gone. Adds round records and replay, behaviour fingerprints, collaboration analysis and the round record, along with reworked controls, music and sound effects.

See the [changelog](CHANGELOG.md) for everything.

---

## Get involved

| If you are | You can |
| --- | --- |
| A player | Play with different models as Jeff and share your experience and round records |
| An HCI or collaboration researcher | Study division of labour, responses and recovery from mistakes under time pressure, and how people treat an AI partner |
| An agent or model developer | Connect your own model and compare decision-making, memory and planning methods in the same environment |
| A multi-agent researcher | Extend human–agent cooperation to teams of several agents |
| A game developer, designer or artist | Make new maps, recipes, mechanics, interfaces and assets |

A few things you can do right now:

- **First-run test**: follow "Run it locally" from scratch on your system and tell us your OS, browser, Python and model versions, and where you got stuck.
- **Cases of Jeff shuffling items back and forth**: Jeff sometimes picks something up and puts it down again. If you see this, include the version, level, model, rough time in the round, and a log excerpt you have checked contains no key. A single reproducible case is a real help; you don't need to fix it.
- **A new map in the existing format**: start from the [map data format](docs/map-format.md) and the three levels' configuration files.

See [CONTRIBUTING](CONTRIBUTING.md) for how to contribute. Issues and pull requests are welcome.

---

## Privacy, costs and licences

- Running locally never connects to a ChefJeff server. The backend runs on your own computer and connects directly to the model service you choose.
- The model service receives the game state, the rule descriptions, the messages you send and, when cross-round memory is on, short summaries of earlier rounds.
- By default your API key is kept only in memory. If you tick "Remember on this device", the key is saved in plain text to the local file `.player-api.json`; "Clear credentials" in Settings deletes it.
- Check exported content before sharing it, and never put your key in an issue, a screenshot or a commit.

See [privacy and API costs](docs/privacy-and-costs.md) and the [security notes](SECURITY.md).

[Overcooked](https://www.ghosttowngames.com/overcooked/) is a wonderful game about cooperation, and ChefJeff's author has long played it on Nintendo Switch. ChefJeff's gameplay and early map designs were inspired by it; this borrowing is limited to gameplay and design and involves none of its code.

- Original code: [AGPL-3.0-only](LICENSE).
- Pixel font: Fusion Pixel by TakWolf, under the SIL Open Font License 1.1.
- Music and sound effects: generated offline with Stability AI's Stable Audio 3 Small SFX (Powered by Stability AI); a few cue sounds are synthesized in code.
- Licence status of other dependencies and assets: see the [third-party notices](THIRD_PARTY_NOTICES.md) and [licence status](LICENSE-STATUS.md).
