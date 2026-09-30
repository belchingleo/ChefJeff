"""Generate raw candidates for every sound in sound_manifest.json (resumable).

Run with the audio env (see scripts/audio/README.md):
    .tools/audio-venv/bin/python scripts/audio/generate_sounds.py [sound_id ...]
Writes art-candidates/audio-v1/raw/<id>/<seed>.wav; existing files are skipped.
"""
import json, os, sys, time
from pathlib import Path
import torch

sys.path.insert(0, str(Path(__file__).parent))
from sa3_local import load, generate, save

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((Path(__file__).parent / 'sound_manifest.json').read_text())
RAW = ROOT / 'art-candidates/audio-v1/raw'


def jobs(only):
    order = {'chip': 0, 'real': 1, 'ambience': 2, 'music': 3}
    for s in sorted(MANIFEST['sounds'], key=lambda s: (order[s['kind']], s['seconds'])):
        if only and s['id'] not in only or 'pick' in s:
            continue
        for take in s['takes']:
            for seed in take['seeds']:
                out = RAW / s['id'] / f'{seed}.wav'
                if not out.exists():
                    yield s, take, seed, out


def main():
    todo = list(jobs(set(sys.argv[1:])))
    print(f'{len(todo)} clips to generate', flush=True)
    if not todo:
        return
    torch.set_num_threads(os.cpu_count())
    model = load()
    start = time.time()
    for i, (s, take, seed, out) in enumerate(todo, 1):
        t0 = time.time()
        audio = generate(model, take['prompt'], take.get('seconds', s['seconds']), seed)
        out.parent.mkdir(parents=True, exist_ok=True)
        save(out, audio)
        print(f'[{i}/{len(todo)}] {s["id"]} seed {seed}: {time.time()-t0:.1f}s (elapsed {(time.time()-start)/60:.1f} min)', flush=True)


if __name__ == '__main__':
    main()
