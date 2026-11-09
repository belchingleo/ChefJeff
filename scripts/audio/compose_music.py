"""The game's three music loops, composed note by note and synthesised in code.

    .tools/audio-venv/bin/python scripts/audio/compose_music.py
writes bgm_menu.mp3, bgm_service.mp3 and bgm_rush.mp3 to cocos-kitchen/assets/resources/audio/ and updates
their entries (gain, loop length, bar length) in index.json. Needs numpy, scipy, soundfile and ffmpeg only.

- bgm_menu   "午后小馆": C major, 92 BPM, gentle broken chords. Played before the round.
- bgm_service "厨房进行曲": a march with an oom-pah bass and chords, 112 BPM. One bar of oom-pah-oom-pah opens
  every loop, so the melody enters about 2 s after the round starts.
- bgm_rush   the same march in harmonic minor at 160 BPM with the oom-pah doubled and a soft clock tick, for the
  last 30 s. The lead keeps the in-round sound, so the switch does not sound like a different piece. The file is
  32 bars (48 s); the rush lasts about 30 s, so it does not loop at normal speed.

The client switches from service to rush on the service's next bar line (index.json "bar"), so the rush's
first beat lands where the next downbeat would have been. Every melody bar has four beats and no melody note on
a strong beat sits a semitone from its chord (tests/test_audio_assets.py checks the rendered files' loop
lengths; the composition checks run in check()).
"""
import json, subprocess, sys
from pathlib import Path
import numpy as np, soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from music_synth import SR, Track, note, kick, hat, brush, echo, soften, parse, midi

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'cocos-kitchen/assets/resources/audio'
PITCH = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
TARGET_RMS_DB = -16.0          # same loudness as the other music the client mixes at gain 0.55


def shift(name, semis):
    m = midi(name) + semis
    return PITCH[m % 12] + str(m // 12 - 1)


def render(piece):
    """Render one seamless loop: play it twice and keep the second pass so echo tails wrap into the start."""
    beat = 60 / piece['bpm']
    L = piece['beats'] * beat
    n = round(L * SR)                       # whole samples, so both passes place every note identically
    tracks = {name: Track(2 * L + 4, pan) for name, pan in piece['pans'].items()}
    for base in (0, n):
        for name, at_beat, sig in piece['events']:
            buf = tracks[name].buf
            i = base + round(at_beat * beat * SR)
            j = min(len(buf), i + len(sig))
            buf[i:j] += sig[:j - i]
    mix = sum(t.stereo() for t in tracks.values())
    mix = echo(mix, beat * piece['echo_beats'], feedback=.35, taps=4, wet=piece['echo_wet'])
    mix = soften(mix, piece['cutoff'])
    out = mix[n:2 * n]
    return out / (np.abs(out).max() + 1e-9) * .89


# ---------------------------------------------------------------- 午后小馆 (menu)
def menu():
    bpm = 92; beat = 60 / bpm
    A = ['C', 'Am', 'F', 'G', 'C', 'Am', 'Dm G', 'C']
    B = ['F', 'G', 'Em', 'Am', 'F', 'G', 'Am', 'G']
    form = A + A + B + A
    chord = {'C': ['C4', 'E4', 'G4'], 'Am': ['A3', 'C4', 'E4'], 'F': ['F3', 'A3', 'C4'], 'G': ['G3', 'B3', 'D4'],
             'Dm': ['D4', 'F4', 'A4'], 'Em': ['E3', 'G3', 'B3']}
    root = {'C': 'C3', 'Am': 'A2', 'F': 'F2', 'G': 'G2', 'Dm': 'D3', 'Em': 'E2'}
    fifth = {'C': 'G2', 'Am': 'E2', 'F': 'C3', 'G': 'D3', 'Dm': 'A2', 'Em': 'B2'}
    a1 = ('E5:1.5 D5:.5 C5:1 E5:1 | A4:2 C5:1 E5:1 | F5:1.5 E5:.5 D5:1 C5:1 | D5:3 r:1 | '
          'E5:1.5 D5:.5 C5:1 G5:1 | A5:1.5 G5:.5 E5:2 | F5:1 D5:1 B4:1 D5:1 | C5:3 r:1')
    a2 = ('E5:1.5 D5:.5 C5:1 E5:1 | A4:2 C5:1 E5:1 | A5:1 G5:1 F5:1 E5:1 | D5:2 G4:1 B4:1 | '
          'C5:1.5 D5:.5 E5:1 G5:1 | A5:1 G5:1 E5:1 C5:1 | F5:1 E5:1 D5:1 B4:1 | C5:4')
    b = ('A4:1 C5:1 F5:2 | G5:1.5 F5:.5 E5:1 D5:1 | E5:2 B4:2 | C5:1.5 B4:.5 A4:2 | '
         'A4:1 C5:1 F5:1 A5:1 | G5:2 F5:1 D5:1 | E5:1.5 D5:.5 C5:1 A4:1 | B4:2 D5:1 r:1')
    ev = []
    t = 0
    for line in (a1, a2, b, a1):
        for name, beats in parse(line):
            if name:
                ev.append(('lead', t, note('pulse', name, beats * beat, gate=.85, vol=.42, duty=.25, vibrato=.004,
                                           env={'a': .012, 'd': .25, 's': .55, 'r': .15})))
            t += beats
    for bar, sym in enumerate(form):
        parts = sym.split()
        for k, c in enumerate(parts):
            span = 4 / len(parts); at = bar * 4 + k * span
            tones = chord[c]
            for i, idx in enumerate([0, 2, 1, 2, 0, 2, 1, 2][:int(span * 2)]):      # gentle broken chord in eighths
                ev.append(('arp', at + i * .5, note('pulse', tones[idx], .5 * beat, gate=.6, vol=.13, duty=.125,
                                                    env={'a': .005, 'd': .12, 's': .3, 'r': .1}, tail=.3)))
            for i, bn in enumerate([root[c], fifth[c]][:max(1, int(span / 2))]):
                ev.append(('bass', at + i * 2, note('tri', bn, 2 * beat, gate=.9, vol=.55,
                                                    env={'a': .01, 'd': .4, 's': .7, 'r': .1})))
        ev.append(('drums', bar * 4, kick(.32)))
        ev.append(('drums', bar * 4 + 2, kick(.22)))
        for off in (1, 3):
            ev.append(('drums', bar * 4 + off, hat(.05, seed=bar * 4 + off)))
    return {'bpm': bpm, 'beats': len(form) * 4, 'events': ev, 'pans': {'lead': 0, 'arp': -.35, 'bass': 0, 'drums': .15},
            'echo_beats': .75, 'echo_wet': .18, 'cutoff': 6500, 'melody': [a1, a2, b, a1], 'form': form,
            'chords': {k: v + [root[k]] for k, v in chord.items()}}


# ---------------------------------------------------------------- 厨房进行曲 (service) and its rush
CHORD = {  # comp tones, bass root, bass fifth (written in F; the pieces are transposed)
    'F': (['F3', 'A3', 'C4'], 'F2', 'C3'), 'C': (['C4', 'E4', 'G4'], 'C3', 'G2'), 'Bb': (['Bb3', 'D4', 'F4'], 'Bb2', 'F2'),
    'Dm': (['D4', 'F4', 'A4'], 'D3', 'A2'), 'Am': (['A3', 'C4', 'E4'], 'A2', 'E2'), 'Gm': (['G3', 'Bb3', 'D4'], 'G2', 'D3'),
    'Fm': (['F3', 'Ab3', 'C4'], 'F2', 'C3'), 'Bbm': (['Bb3', 'Db4', 'F4'], 'Bb2', 'F2'),
}
MARCH_A = ['F', 'C', 'F', 'C', 'Bb', 'F', 'C', 'F']
MARCH_B = ['Dm', 'Am', 'Bb', 'F', 'Gm', 'C', 'Bb C', 'F']
A1 = ('C5:.5 C5:.5 F5:1 A5:1 F5:1 | G5:1.5 F5:.5 E5:1 C5:1 | A4:.5 C5:.5 F5:1 A5:1 C6:1 | G5:3 r:1 | '
      'F5:1 D5:1 Bb4:1 D5:1 | C5:1.5 D5:.5 C5:1 A4:1 | G4:1 C5:1 E5:1 G5:1 | F5:3 r:1')
A2 = ('C5:.5 C5:.5 F5:1 A5:1 F5:1 | G5:1.5 F5:.5 E5:1 C5:1 | A4:.5 C5:.5 F5:1 A5:1 C6:1 | G5:3 r:1 | '
      'D5:.5 F5:.5 Bb5:1 F5:1 D5:1 | A5:1.5 G5:.5 F5:1 C5:1 | E5:1 G5:1 Bb5:1 G5:1 | F5:2 C5:1 r:1')
B1 = ('D5:1 F5:1 A5:2 | E5:1 C5:1 A4:2 | D5:.5 D5:.5 F5:1 Bb5:1 A5:1 | A5:2 F5:1 r:1 | '
      'G5:1 Bb5:1 D5:1 G5:1 | E5:1.5 F5:.5 G5:2 | F5:1 D5:1 E5:1 C5:1 | F5:3 r:1')
LEAD = (.5, .015, .72)                       # duty, attack, gate: a round, soft square for both march pieces
OOMPAH_LIFT = 10 ** (3 / 20)                 # the oom-pah sits 3 dB forward in the mix


def arrange(bpm, form, lines, bass, comp, transpose, vamp=0):
    beat = 60 / bpm
    T = lambda n: shift(n, transpose)
    bass_vol, comp_vol, drum = .5 * OOMPAH_LIFT, .07 * OOMPAH_LIFT, .7
    bass_env = {'a': .006, 'd': .2, 's': .55, 'r': .05}
    comp_env = {'a': .004, 'd': .1, 's': .3, 'r': .06}
    ev = []
    t = vamp
    for line in lines:
        for name, beats in parse(line):
            if name:
                duty, attack, gate = LEAD
                env = {'a': attack, 'd': .18, 's': .5, 'r': .08}
                ev.append(('lead', t, note('pulse', T(name), beats * beat, gate=gate, vol=.38, duty=duty, vibrato=.003, env=env)))
            t += beats
    assert abs(t - vamp - len(form) * 4) < 1e-9, (t, len(form) * 4)
    if vamp:                                                  # oom-pah-oom-pah before the melody enters
        tones, root, fifth = CHORD[form[0].split()[0]]
        for off in range(int(vamp)):
            if off % 2 == 0:
                ev.append(('bass', off, note('tri', T(root if off % 4 == 0 else fifth), beat, gate=.75, vol=bass_vol, env=bass_env, tail=.2)))
                ev.append(('drums', off, kick(.3 * drum)))
            else:
                for tone in tones:
                    ev.append(('comp', off, note('pulse', T(tone), .45 * beat, gate=.9, vol=comp_vol, duty=.125, env=comp_env, tail=.2)))
                ev.append(('drums', off, brush(.055 * drum, seed=99)))
    for bar, sym in enumerate(form):
        parts = sym.split()
        for k, c in enumerate(parts):
            span = 4 / len(parts); at = vamp + bar * 4 + k * span
            tones, root, fifth = CHORD[c]
            if bass == 'oompah':                               # root on 1, fifth on 3
                hits = [(0, root), (2, fifth)]
            else:                                              # 'doubled': oom on every beat, root and fifth alternating
                hits = [(i, root if i % 2 == 0 else fifth) for i in range(4)]
            for off, bn in hits:
                if off < span:
                    ev.append(('bass', at + off, note('tri', T(bn), beat, gate=.75, vol=bass_vol, env=bass_env, tail=.2)))
            offs = [1, 3] if comp == 'stabs' else [.5, 1.5, 2.5, 3.5]   # pah on 2 and 4, or on every off-beat eighth
            for off in offs:
                if off < span:
                    for tone in tones:
                        ev.append(('comp', at + off, note('pulse', T(tone), .45 * beat, gate=.9, vol=comp_vol, duty=.125, env=comp_env, tail=.2)))
        b = vamp + bar * 4
        ev += [('drums', b, kick(.3 * drum)), ('drums', b + 2, kick(.22 * drum))]
        ev += [('drums', b + 1, brush(.055 * drum, seed=bar * 3)), ('drums', b + 3, brush(.055 * drum, seed=bar * 3 + 1))]
        ev += [('drums', b + 1, hat(.045, seed=bar * 5)), ('drums', b + 3, hat(.045, seed=bar * 5 + 1))]
    return {'bpm': bpm, 'beats': vamp + len(form) * 4, 'events': ev, 'pans': {'lead': 0, 'comp': -.3, 'bass': 0, 'drums': .15},
            'echo_beats': .5, 'echo_wet': .14, 'cutoff': 4500, 'melody': lines, 'form': form, 'transpose': transpose,
            'chords': {k: v[0] + [v[1]] for k, v in CHORD.items()}}


def service():
    return arrange(112, MARCH_A * 2 + MARCH_B + MARCH_A, [A1, A2, B1, A1], 'oompah', 'stabs', transpose=-5, vamp=4)


def minorize(line, form):
    """F major -> F harmonic minor: lower A and D, and E except over the C (dominant) chord."""
    out, t = [], 0
    for tok in line.split():
        if tok == '|':                                         # keep bar lines so check() can count beats per bar
            out.append(tok); continue
        (name, beats), = parse(tok)
        if name:
            pc = (midi(name) - 5) % 12
            if pc in (4, 9) or (pc == 11 and form[int(t // 4)].split()[0] != 'C'):
                name = shift(name, -1)
        out.append(f'{name or "r"}:{beats:g}')
        t += beats
    return ' '.join(out)


def woodblock(vol):
    """A soft clock tick: a short hollow knock around 900 Hz, nothing bright."""
    n = int(.06 * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 900 * t) + .4 * np.sin(2 * np.pi * 1530 * t)) * np.exp(-t / .012) * vol


def rush(passes=2):
    minor = [{'F': 'Fm', 'Bb': 'Bbm'}.get(c, c) for c in MARCH_A]
    lines = [minorize(A1, MARCH_A), minorize(A2, MARCH_A)] * passes
    piece = arrange(160, minor * 2 * passes, lines, 'doubled', 'offbeats', transpose=-3)
    piece['events'] += [('drums', b, woodblock(.05)) for b in range(piece['beats'])]
    return piece


PIECES = {'bgm_menu': menu, 'bgm_service': service, 'bgm_rush': rush}
# How the client brings each piece in: the march pieces start at full level (their first beat matters) and the
# rush waits for the service's next bar line; the menu piece keeps a gentle fade-in.
ENTRY_FLAGS = {'bgm_service': {'crisp': True}, 'bgm_rush': {'crisp': True, 'on_bar': True}}


def check(piece):
    """Every melody bar has four beats; no strong-beat melody note sits a semitone from its chord."""
    form, problems, t = piece['form'], [], 0
    vamp = piece['beats'] - len(form) * 4
    pcs = {k: {midi(n) % 12 for n in v} for k, v in piece['chords'].items()}
    for line in piece['melody']:
        for i, seg in enumerate(line.split('|')):
            if abs(sum(b for _, b in parse(seg)) - 4) > 1e-9:
                problems.append(f'bar {i + 1} of a line is not 4 beats')
        for name, beats in parse(line):
            if name and t % 2 == 0:
                parts = form[int(t // 4)].split(); c = parts[min(len(parts) - 1, int((t % 4) // (4 / len(parts))))]
                pc = midi(name) % 12
                if pc not in pcs[c] and any((pc - q) % 12 in (1, 11) for q in pcs[c]):
                    problems.append(f'beat {t + vamp}: {name} against {c}')
            t += beats
    return problems


def export(name):
    """Render, level and write one track; return its index.json entry."""
    piece = PIECES[name]()
    problems = check(piece)
    if problems:
        raise SystemExit(f'{name}: ' + '; '.join(problems))
    x = render(piece)
    x = x * 10 ** ((TARGET_RMS_DB - 20 * np.log10(np.sqrt((x ** 2).mean()))) / 20)
    x = x / max(1.0, np.abs(x).max() / .97)
    DEST.mkdir(parents=True, exist_ok=True)
    wav = DEST / f'_{name}.wav'
    sf.write(wav, x, SR, subtype='PCM_16')
    # LAME's gapless header lets browsers drop the encoder delay, so the loop stays seamless.
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(wav), '-codec:a', 'libmp3lame', '-b:a', '128k',
                    str(DEST / f'{name}.mp3')], check=True)
    wav.unlink()
    entry = {'loop': True, 'kind': 'music', 'gain': .55, 'seconds': round(len(x) / SR, 3), 'bar': round(240 / piece['bpm'], 6),
             'source': 'composed'}
    entry.update(ENTRY_FLAGS.get(name, {}))
    return entry


def main():
    index_path = DEST / 'index.json'
    index = json.loads(index_path.read_text())
    for name in PIECES:
        index['sounds'][name] = export(name)
        print(f'{name}: {index["sounds"][name]["seconds"]}s, bar {index["sounds"][name]["bar"]}s')
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1) + '\n')


if __name__ == '__main__':
    main()
