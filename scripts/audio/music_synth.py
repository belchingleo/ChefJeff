"""Small chiptune engine for the composed game music: band-limited pulse, sawtooth and triangle, soft noise drums."""
import numpy as np
from scipy.signal import butter, sosfiltfilt

SR = 44100
NAMES = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6,
         'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}


def midi(name):
    pitch, octave = name[:-1], int(name[-1])
    return NAMES[pitch] + 12 * (octave + 1)


def hz(name):
    return 440.0 * 2 ** ((midi(name) - 69) / 12)


def _blep(t, dt):
    out = np.zeros_like(t)
    a = t < dt
    x = t[a] / dt[a]; out[a] = x + x - x * x - 1
    b = t > 1 - dt
    x = (t[b] - 1) / dt[b]; out[b] = x * x + x + x + 1
    return out


def osc(kind, freq, n, duty=0.5, vibrato=0.0, vib_delay=0.25):
    """Band-limited pulse (polyBLEP) or triangle; freq may carry a gentle delayed vibrato."""
    t = np.arange(n) / SR
    f = np.full(n, float(freq))
    if vibrato:
        depth = np.clip((t - vib_delay) / 0.3, 0, 1) * vibrato
        f = f * (1 + depth * np.sin(2 * np.pi * 5.2 * t))
    dt = f / SR
    phase = np.cumsum(dt) % 1.0
    if kind == 'tri':
        return 4 * np.abs(phase - 0.5) - 1
    if kind == 'saw':                                   # band-limited sawtooth (brass-like)
        return (2 * phase - 1) - _blep(phase, dt)
    sq = np.where(phase < duty, 1.0, -1.0)
    sq += _blep(phase, dt) - _blep((phase - duty) % 1.0, dt)
    return sq - (2 * duty - 1)


def adsr(n, gate, a=0.01, d=0.15, s=0.6, r=0.12):
    t = np.arange(n) / SR
    env = np.where(t < a, t / max(a, 1e-4), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4)))
    off = t >= gate
    if off.any():
        level = env[~off][-1] if (~off).any() else 0
        env[off] = level * np.exp(-(t[off] - gate) / max(r, 1e-4))
    return env


def note(kind, name, seconds, gate=0.9, vol=1.0, duty=0.5, env=None, vibrato=0.0, tail=0.4):
    n = int((seconds + tail) * SR)
    e = adsr(n, seconds * gate, **(env or {}))
    return osc(kind, hz(name), n, duty, vibrato) * e * vol


def kick(vol=1.0):
    n = int(0.22 * SR); t = np.arange(n) / SR
    f = 50 + 70 * np.exp(-t / 0.03)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.07) * vol


def hat(vol=1.0, decay=0.035, seed=0):
    rng = np.random.default_rng(seed)
    n = int(0.15 * SR); t = np.arange(n) / SR
    x = rng.standard_normal(n)
    x = sosfiltfilt(butter(2, [6000, 12000], 'bandpass', fs=SR, output='sos'), x)
    return x * np.exp(-t / decay) * vol


def brush(vol=1.0, seed=0):
    rng = np.random.default_rng(seed)
    n = int(0.3 * SR); t = np.arange(n) / SR
    x = sosfiltfilt(butter(2, [2500, 7000], 'bandpass', fs=SR, output='sos'), rng.standard_normal(n))
    return x * np.minimum(1, t / 0.02) * np.exp(-t / 0.09) * vol


class Track:
    """Mono track placed into a stereo mix with a pan (-1 left .. 1 right)."""
    def __init__(self, seconds, pan=0.0):
        self.buf = np.zeros(int(seconds * SR) + SR * 2)
        self.pan = pan

    def add(self, at_seconds, sig):
        i = int(at_seconds * SR)
        j = min(len(self.buf), i + len(sig))
        self.buf[i:j] += sig[:j - i]

    def stereo(self):
        l = np.cos((self.pan + 1) * np.pi / 4); r = np.sin((self.pan + 1) * np.pi / 4)
        return np.stack([self.buf * l, self.buf * r], 1) * np.sqrt(2)


def echo(x, seconds, feedback=0.3, taps=4, wet=0.35, pingpong=True):
    d = int(seconds * SR)
    out = x.copy()
    for k in range(1, taps + 1):
        g = wet * feedback ** (k - 1)
        src = x[:-k * d] * g
        if pingpong:
            src = src[:, ::-1] if k % 2 else src
        out[k * d:] += src
    return out


def soften(x, cutoff=7000):
    return sosfiltfilt(butter(2, cutoff, fs=SR, output='sos'), x, axis=0)


def parse(line):
    """'E5:1.5 D5:.5 r:1 | ...' -> [(name or None, beats)]; bars marked with | are ignored."""
    out = []
    for tok in line.replace('|', ' ').split():
        name, beats = tok.split(':')
        out.append((None if name == 'r' else name, float(beats)))
    return out
