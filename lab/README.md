# ChefJeff lab

A static page for `lab.chefjeff.online`: logged moments of real rounds, the exact request Jeff would be sent there
under each way of writing it, and the answers models gave to exactly that request in recorded re-asks. The page calls
no model.

## Build the data

```bash
python3 scripts/build_lab.py PATH/TO/RUNS
```

`PATH/TO/RUNS` is a folder of recorded re-ask runs (`<name>.requests.json` with each moment's requests per arm,
`<name>.answers.jsonl` with one answer per line); `scripts/build_lab.py` lists the runs it reads. For every moment the
script replays the round from its session bundle (`logs/sessions/`), rebuilds the request under each condition with
the current code and the local play set (the features override, with `off_for` read for each model service), and
attaches a recorded answer only when the request it was given is byte-identical (sha256 of the canonical JSON) to the
rebuilt one. A code change that alters a request therefore drops the old answers for it until they are recorded again.

The output goes to `lab/data/` (`index.json` and one file per moment), which git ignores: the moments come from the
researcher's own rounds and are not published until that is decided.

## Look at it locally

```bash
cd lab && python3 -m http.server 18801 --bind 127.0.0.1
```

then open <http://127.0.0.1:18801/>. The page is plain HTML, CSS and JavaScript with system fonts only, so it loads
without Google Fonts or any CDN.

## Conditions

- `today`: today's request (every request part and the go note off).
- `restructured`: four request parts (place names, timeline, links on options, rules by action) and the go note on.
- `with_kitchen_view`: the same with the kitchen view too (off in play: it made Jev take a plate first at every level-5 opening).

The results tab compares each condition with today's request over the same moments only (those with recorded answers
for both).
