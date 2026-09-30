"""Export the approved sounds into the Cocos client.

    .tools/audio-venv/bin/python scripts/audio/export_sounds.py
Reads the picks in sound_manifest.json and writes cocos-kitchen/assets/resources/audio/<id>.mp3 plus
audio/index.json (loop flags, mix gains, chop strike list). Loops are made seamless: music loops at the
point where the piece best repeats its opening (so the beat stays in phase), noisy textures use an
equal-power crossfade of the tail into the head.
"""
import json, subprocess, sys
from pathlib import Path
import numpy as np, soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from chiptune import CUES
from process_sounds import (MANIFEST, RAW, SR, WASH_TAME, SETTLED_DEWHINE, chop_hits, clean, ffmpeg)

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'cocos-kitchen/assets/resources/audio'
# Relative mix, applied in the client (0-1). One-shots are peak-normalised, loops RMS-normalised.
GAIN = {'music': 0.55, 'ambience': 0.45, 'chip': 0.6, 'real': 0.8}
GAIN_OVERRIDE = {'ui_click': 0.35, 'order_urgent': 0.5, 'sizzle_loop': 0.5, 'fire_loop': 0.6, 'jingle_win': 0.7,
                 'jingle_lose': 0.7}


def equal_power_loop(x, fade):
    """Loop x seamlessly: its last `fade` seconds are crossfaded into its first."""
    n = int(fade * SR)
    t = np.linspace(0, np.pi / 2, n)[:, None]
    y = x[:-n].copy()
    y[:n] = x[:n] * np.sin(t) + x[-n:] * np.cos(t)
    return y


def steady(x, block=0.25, drop_db=6):
    """The model fades textures in and out (fire starts ~20 dB low, ambience ends in silence): keep only
    the span whose 250 ms loudness stays within drop_db of the median before looping it."""
    h = int(block * SR)
    rms = np.array([np.sqrt((x[i:i + h] ** 2).mean()) for i in range(0, len(x) - h + 1, h)])
    ok = np.where(20 * np.log10(rms / np.median(rms) + 1e-9) > -drop_db)[0]
    return x[ok[0] * h:(ok[-1] + 1) * h]


def envelope(x, hop=441):
    m = np.abs(x).mean(1)
    return np.sqrt(np.convolve(m ** 2, np.ones(hop) / hop, 'same')[::hop])


def music_loop(x, fade=0.25, min_frac=0.6):
    """Cut where the piece best repeats its opening, then crossfade so the loop point is inaudible."""
    env = envelope(x)
    hop = 441
    head = env[:int(4 * SR / hop)]                            # first 4 s define the "opening"
    head = (head - head.mean()) / (head.std() + 1e-9)
    best, best_score = None, -1
    for i in range(int(len(env) * min_frac), len(env) - len(head)):
        w = env[i:i + len(head)]
        score = float(((w - w.mean()) / (w.std() + 1e-9) * head).mean())
        if score > best_score:
            best, best_score = i, score
    cut = best * hop
    # Refine to the sample with the best waveform match around the coarse point (±10 ms).
    probe = x[:2048].mean(1)
    r = int(.01 * SR)
    cands = range(max(0, cut - r), min(len(x) - 2048, cut + r))
    cut = max(cands, key=lambda c: float(np.dot(x[c:c + 2048].mean(1), probe)))
    n = int(fade * SR)
    looped = equal_power_loop(np.concatenate([x[:cut], x[cut:cut + n]]), fade)
    return looped, cut / SR, best_score


def pick_audio(s, sounds):
    pick = s['pick']
    if str(pick).startswith('synth'):
        return CUES[s['id']][pick]()
    if pick == 'reuse':
        src = sounds[s['reuse']['id']]
        return clean(RAW / src['id'] / f'{s["reuse"]["seed"]}.wav', src)[0]
    return clean(RAW / s['id'] / f'{pick}.wav', s)[0]


def write(x, name, stereo, kbps):
    DEST.mkdir(parents=True, exist_ok=True)
    tmp = DEST / f'_{name}.wav'
    x = x if stereo else x.mean(1, keepdims=True)
    sf.write(tmp, x, SR, subtype='PCM_16')
    # LAME writes the gapless header (encoder delay / padding) so browsers can trim it on decode.
    ffmpeg(tmp, DEST / f'{name}.mp3', extra=['-codec:a', 'libmp3lame', '-b:a', f'{kbps}k', '-ac', '2' if stereo else '1'])
    tmp.unlink()
    return len(x) / SR


def main():
    sounds = {s['id']: s for s in MANIFEST['sounds']}
    index = {'sounds': {}, 'chop': [], 'wash': {}}
    for s in MANIFEST['sounds']:
        if s.get('fixed'):
            continue
        x = pick_audio(s, sounds)
        loop = bool(s.get('loop'))
        note = ''
        if loop and s['kind'] == 'music':
            x, at, score = music_loop(x)
            note = f'loop at {at:.2f}s (match {score:.2f})'
        elif loop:
            x = steady(x)
            x = equal_power_loop(x, 1.0 if len(x) > 12 * SR else 0.5)
        stereo = s['kind'] in ('music', 'ambience') or loop
        dur = write(x, s['id'], stereo, 128 if s['kind'] == 'music' else 96)
        index['sounds'][s['id']] = {'loop': loop, 'kind': s['kind'], 'gain': GAIN_OVERRIDE.get(s['id'], GAIN[s['kind']]),
                                    'seconds': round(dur, 2)}
        print(f'{s["id"]:16s} {dur:6.2f}s {"loop " if loop else ""}{note}')

    chop = sounds['chop_hits']
    for i, h in enumerate(chop_hits(chop['takes'][0]['seeds'])):
        write(h, f'chop_{i:02d}', False, 96)
        index['chop'].append(f'chop_{i:02d}')
    print(f'chop strikes     {len(index["chop"])}')

    wash = sounds['wash_loop']
    a, b = wash['takes'][0]['seeds']
    tmp = DEST / '_wash'
    tmp.mkdir(parents=True, exist_ok=True)
    tamed = {}
    for seed in (a, b):
        sf.write(tmp / f'dc{seed}.wav', SETTLED_DEWHINE(sf.read(RAW / 'wash_loop' / f'{seed}.wav')[0]), SR)
        ffmpeg(tmp / f'dc{seed}.wav', tmp / f't{seed}.wav', WASH_TAME)
        tamed[seed] = sf.read(tmp / f't{seed}.wav')[0]
    pan = lambda x, p: x * np.array([1 - max(0, p), 1 + min(0, p)])
    duo = pan(tamed[a], -.45) + pan(tamed[b], .45)
    sf.write(tmp / 'duo.wav', duo / np.abs(duo).max() * .89, SR)
    ffmpeg(tmp / 'duo.wav', tmp / 'duo_fast.wav', 'atempo=1.5')
    solo = tamed[a] / np.abs(tamed[a]).max() * .89
    duo_fast = sf.read(tmp / 'duo_fast.wav')[0]
    for name, x in (('wash_solo', solo), ('wash_duo', duo_fast)):
        dur = write(equal_power_loop(steady(x), 0.4), name, True, 96)
        index['wash'][name] = {'loop': True, 'gain': 0.7, 'seconds': round(dur, 2)}
        print(f'{name:16s} {dur:6.2f}s loop')
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()
    (DEST / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1) + '\n')
    total = sum(p.stat().st_size for p in DEST.glob('*.mp3'))
    print(f'{len(list(DEST.glob("*.mp3")))} files, {total / 1e6:.1f} MB -> {DEST.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
