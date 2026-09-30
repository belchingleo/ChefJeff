"""Code-synthesised NES-style blips for short cues the model renders as noise.

Stable Audio 3 Small SFX handles 'coin', 'cash register' and 'error buzz' style prompts, but a two-note
chime, a sad descending tone or an 'uh-oh' came out as broadband noise in two rounds. These cues are
plain square-wave notes, so they are rendered directly: pulse wave with NES duty cycles, fast attack,
exponential decay, and a short silent gap between notes.
"""
import numpy as np

SR = 44100
NOTE = {n: i for i, n in enumerate(['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'])}


def hz(name):
    """'A4' -> 440.0 (equal temperament)."""
    pitch, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((NOTE[pitch] + 12 * (octave + 1) - 69) / 12)


def pulse(freq, seconds, duty=0.25, decay=6.0, slide=0.0, vibrato=0.0, depth=0.006):
    t = np.arange(int(seconds * SR)) / SR
    wave = np.zeros_like(t)
    for fr in np.atleast_1d(freq):                     # several frequencies = a two-channel chord
        f = fr * (1 + slide * t / seconds)             # optional pitch slide over the note
        if vibrato:
            f = f * (1 + depth * np.sin(2 * np.pi * vibrato * t))
        phase = np.cumsum(f) / SR % 1.0
        wave += np.where(phase < duty, 1.0, -1.0)
    wave -= wave.mean()
    env = np.minimum(1, t / 0.004) * np.exp(-decay * t)
    env[-int(.008 * SR):] *= np.linspace(1, 0, int(.008 * SR))  # click-free release
    return wave * env


def sequence(notes, gap=0.012, **kw):
    """notes: [(name, seconds, overrides)]"""
    parts = []
    for name, secs, *extra in notes:
        opts = {**kw, **(extra[0] if extra else {})}
        parts += [pulse([hz(n) for n in name.split('+')], secs, **opts), np.zeros(int(gap * SR))]
    x = np.concatenate(parts)
    # Soften the square edges a little (NES output was band-limited too).
    k = np.hanning(9); k /= k.sum()
    x = np.convolve(x, k, 'same')
    x = x / np.abs(x).max() * 0.89
    return np.stack([x, x], 1)


CUES = {
    # New order: friendly rising "ding-dong".
    'order_new': {
        'synth_a': lambda: sequence([('B5', .09), ('E6', .22)], duty=.25, decay=7),
        'synth_b': lambda: sequence([('C6', .07), ('E6', .07), ('G6', .20)], duty=.125, decay=8),
    },
    # Order expired: gentle falling two notes.
    'order_expired': {
        'synth_a': lambda: sequence([('G5', .12), ('C5', .30)], duty=.25, decay=4.5),
        'synth_b': lambda: sequence([('E5', .12), ('C5', .12), ('G4', .30, {'slide': -.04})], duty=.5, decay=4),
    },
    # Bad review. Round 3: the falling "uh-oh" (a/b) was too close to order_expired, so c-e are
    # different gestures: repeated low "bu-bu", a dissonant tritone buzz, and a sliding comic "wah".
    'serve_bad': {
        'synth_a': lambda: sequence([('E4', .14), ('C4', .28)], duty=.5, decay=4, gap=.03),
        'synth_b': lambda: sequence([('D#4', .12), ('A3', .30, {'vibrato': 9})], duty=.25, decay=3.5, gap=.03),
        'synth_c': lambda: sequence([('C3', .11), ('C3', .20)], duty=.125, decay=5, gap=.06),
        'synth_d': lambda: sequence([('C4+F#4', .34, {'vibrato': 14, 'depth': .01})], duty=.5, decay=3),
        'synth_e': lambda: sequence([('G3', .48, {'slide': -.33, 'vibrato': 7, 'depth': .015})], duty=.25, decay=2.2),
    },
}
