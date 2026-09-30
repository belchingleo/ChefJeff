"""Remove the Stable Audio 3 decoder whine.

Every output carries faint steady tones at each multiple of SR/256 (172.27 Hz at 44.1 kHz), strongest
at 12-18 kHz; on sustained sounds it reads as a tinnitus-like ring. With a 4096-point STFT each harmonic
lands exactly on bin 16k, so bins 16k-1..16k+1 are clamped to the local background (median of nearby
non-comb bins). Phase and all other bins are untouched, so transients survive.

The clamp also cuts genuine harmonics that cross those bins, frame by frame (up to 40 dB on chiptune,
with ~2 dB jitter that sounds choppy and "broken"). So it is only applied above `min_hz` on realistic,
mostly noisy effects; tonal 8-bit sounds and music are low-passed below the whine band instead.
"""
import numpy as np

N, HOP, PERIOD = 4096, 1024, 256


def decomb(x, sr=44100, min_hz=6000.0):
    mono = x.ndim == 1
    x = x[:, None] if mono else x
    step = N // PERIOD
    win = np.hanning(N + 1)[:-1]
    pad = np.pad(x, ((N, N), (0, 0)))
    out = np.zeros_like(pad)
    wsum = np.zeros(len(pad))
    centers = np.array([b for b in range(step, N // 2 + 1 - 8, step) if b * sr / N >= min_hz])
    around = np.concatenate([np.arange(-6, -2), np.arange(3, 7)])
    for s in range(0, len(pad) - N, HOP):
        wsum[s:s + N] += win ** 2
        for c in range(x.shape[1]):
            X = np.fft.rfft(pad[s:s + N, c] * win)
            mag = np.abs(X)
            bg = np.median(mag[centers[:, None] + around[None, :]], axis=1)
            for off in (-1, 0, 1):
                j = centers + off
                over = mag[j] > bg
                X[j[over]] *= bg[over] / mag[j[over]]
            out[s:s + N, c] += np.fft.irfft(X, N) * win
    y = (out / np.maximum(wsum, 1e-8)[:, None])[N:N + len(x)]
    return y[:, 0] if mono else y


def comb_excess_db(x, sr=44100, lo=12000, hi=18000):
    """Median dB that comb bins stand above their neighbours in [lo, hi] — the regression check."""
    m = x.mean(1) if x.ndim > 1 else x
    if len(m) < N:
        m = np.pad(m, (0, N - len(m)))
    fr = np.lib.stride_tricks.sliding_window_view(m, N)[::HOP] * np.hanning(N)
    P = np.abs(np.fft.rfft(fr)) ** 2 + 1e-20
    vals = []
    for b in range(N // PERIOD, N // 2 - 8, N // PERIOD):
        if lo <= b * sr / N <= hi:
            nb = np.concatenate([P[:, b - 6:b - 2], P[:, b + 3:b + 7]], 1)
            vals.append(np.median(10 * np.log10(P[:, b] / np.median(nb, 1))))
    return float(np.median(vals)) if vals else 0.0
