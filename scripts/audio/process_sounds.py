"""Clean raw candidates and build the local audition page.

    .tools/audio-venv/bin/python scripts/audio/process_sounds.py
Reads art-candidates/audio-v1/raw/<id>/<seed>.wav, writes <id>/<seed>.mp3 plus index.html beside it.
Every clip is de-combed (decoder whine) and low-passed; one-shots are trimmed and faded; loudness is
matched per kind so candidates compare fairly. Settled sounds (chop, wash) are rebuilt as reference.
"""
import html, json, subprocess, sys
from pathlib import Path
import numpy as np, soundfile as sf
from scipy.signal import butter, sosfiltfilt

sys.path.insert(0, str(Path(__file__).parent))
from decomb import decomb, comb_excess_db

SR = 44100
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'art-candidates/audio-v1'
RAW = OUT / 'raw'
MANIFEST = json.loads((Path(__file__).parent / 'sound_manifest.json').read_text())
# Wash solo: dip the harsh 3.8 kHz edge, shelve the top, gently expand away the room tail.
WASH_TAME = ('highpass=f=100,lowpass=f=16000,equalizer=f=3800:t=q:w=1.0:g=-5,highshelf=f=7000:g=-7,'
             'agate=threshold=0.06:ratio=1.8:range=0.35:attack=8:release=120:knee=4')


def ffmpeg(src, dst, af=None, extra=()):
    cmd = ['ffmpeg', '-loglevel', 'error', '-y', '-i', str(src)]
    if af:
        cmd += ['-af', af]
    subprocess.run(cmd + list(extra) + [str(dst)], check=True)


def lowpass(x, hz=16000, order=4):
    # Zero-phase IIR: a whole-clip FFT filter would wrap the attack around into the tail.
    return sosfiltfilt(butter(order, hz, fs=SR, output='sos'), x, axis=0)


def dewhine(x, kind):
    """Tonal chiptune/music: steep low-pass under the 12-18 kHz whine, leaving every note untouched.
    Realistic effects: clamp the whine bins above 6 kHz, then a gentle 16 kHz low-pass."""
    if kind in ('chip', 'music'):
        return lowpass(x, 11000, order=8)
    return lowpass(decomb(x, min_hz=6000), 16000)


# Chop and wash were approved with the full-band clamp; keep their processing unchanged.
SETTLED_DEWHINE = lambda x: lowpass(decomb(x, min_hz=150))


def first_event_end(env, start, drop_db=40, hold=0.03, frame=0.01):
    """Where the first event decays drop_db below its own peak and stays there for `hold`."""
    f = int(frame * SR)
    db = 20 * np.log10(np.array([env[i:i + f].max() for i in range(start, len(env), f)]) + 1e-9)
    peak_i = int(np.argmax(db[:max(1, int(.15 / frame))]))
    quiet, need = 0, int(hold / frame)
    for i in range(peak_i, len(db)):
        quiet = quiet + 1 if db[i] < db[peak_i] - drop_db else 0
        if quiet >= need:
            return start + (i - need + 1) * f
    return len(env)


def first_gap(env, after, gap_db=-24, hold=0.04, frame=0.01):
    """Start of the first pause (quieter than gap_db below peak for `hold`) after `after` samples."""
    f = int(frame * SR)
    lim = env.max() * 10 ** (gap_db / 20)
    quiet, need = 0, int(hold / frame)
    for k, i in enumerate(range(after, len(env), f)):
        quiet = quiet + 1 if env[i:i + f].max() < lim else 0
        if quiet >= need:
            return after + (k - need + 1) * f
    return None


def trim(x, max_seconds=None, single=False, cut_gap_after=None, head_db=-40, tail_db=-50, pre=0.005):
    env = np.abs(x).max(1)
    pk = env.max() + 1e-9
    loud = np.where(env > pk * 10 ** (head_db / 20))[0]
    tail = np.where(env > pk * 10 ** (tail_db / 20))[0]
    if not len(loud):
        return x
    s, e = max(0, loud[0] - int(pre * SR)), min(len(x), tail[-1] + int(.03 * SR))
    fade = .03
    if cut_gap_after is not None:
        # The model tacks a stray note on after the phrase has ended; stop at the first pause.
        g = first_gap(env, s + int(cut_gap_after * SR))
        if g is not None:
            e, fade = min(e, g + int(.02 * SR)), .12
    if single:
        # Keep the natural ring (a plate clink stays audible down to about -40 dB), then fade.
        e, fade = min(e, first_event_end(env, loud[0]) + int(.06 * SR)), .06
    if max_seconds and e - s > max_seconds * SR:
        # Content continues past the cap (the model filled the duration): fade out over the last quarter.
        e, fade = s + int(max_seconds * SR), max(.06, min(.25, max_seconds / 4))
    y = x[s:e].copy()
    n = min(int(fade * SR), len(y))
    y[-n:] *= np.linspace(1, 0, n)[:, None]
    return y


def level(x, kind, loop):
    if loop or kind in ('music', 'ambience'):
        target = {'music': -16, 'ambience': -24}.get(kind, -20)  # dBFS RMS
        x = x * 10 ** ((target - 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9)) / 20)
    return x / max(1.0, np.abs(x).max() / 0.89) if (loop or kind in ('music', 'ambience')) else x / (np.abs(x).max() + 1e-9) * 0.89


def clean(raw, s):
    kind, loop = s['kind'], bool(s.get('loop'))
    x = sf.read(raw)[0]
    before = comb_excess_db(x)
    y = dewhine(x, kind)
    if not loop and kind not in ('music', 'ambience'):
        y = trim(y, s.get('max_seconds'), s.get('single', False), s.get('cut_first_gap_after'))
    return level(y, kind, loop), before, comb_excess_db(y)


def export(x, mp3):
    mp3.parent.mkdir(parents=True, exist_ok=True)
    wav = mp3.with_suffix('.wav')
    sf.write(wav, x, SR, subtype='PCM_16')
    ffmpeg(wav, mp3, extra=['-b:a', '160k'])
    wav.unlink()


# ---- settled sounds -------------------------------------------------------------------------
def onsets(m, min_gap=0.12, thresh_db=-24, hop=256):
    hp = np.diff(m, prepend=0)
    e = np.sqrt(np.convolve(hp ** 2, np.ones(hop) / hop, 'same')[::hop])
    db = 20 * np.log10(e / e.max() + 1e-9)
    rise = np.diff(db, prepend=db[0])
    out, last = [], -1e9
    for i in range(len(db)):
        if db[i] > thresh_db and rise[i] > 6 and i * hop - last > min_gap * SR:
            out.append(i * hop); last = i * hop
    return out


def low_share(h):
    m = h.mean(1)
    S = np.abs(np.fft.rfft(m * np.hanning(len(m)))) + 1e-12
    f = np.fft.rfftfreq(len(m), 1 / SR)
    return S[f < 500].sum() / S.sum()


def chop_hits(seeds):
    """Single strikes from the approved chopping takes; boomy ones (>=20% energy <500 Hz) rejected."""
    hits = []
    for seed in seeds:
        a = SETTLED_DEWHINE(sf.read(RAW / 'chop_hits' / f'{seed}.wav')[0])
        ons = onsets(a.mean(1))
        for j, o in enumerate(ons):
            nxt = ons[j + 1] if j + 1 < len(ons) else len(a)
            s, e = max(0, o - int(.003 * SR)), min(o + int(.13 * SR), nxt - int(.005 * SR))
            if e - s < int(.06 * SR):
                continue
            h = a[s:e].copy()
            f = int(.025 * SR); h[-f:] *= np.linspace(1, 0, f)[:, None]; h[:32] *= np.linspace(0, 1, 32)[:, None]
            if low_share(h) < 0.20 and np.abs(h).max() > 0.25:
                hits.append(h / np.abs(h).max() * 0.89)
    return hits


def chop_demo(hits, rate, secs, seed, pan=0.0, gain=1.0):
    rng = np.random.default_rng(seed)
    out = np.zeros((int(secs * SR) + SR, 2))
    t, last = rng.uniform(0, 1 / rate), -1
    while t < secs:
        k = int(rng.integers(len(hits)))
        if k == last and len(hits) > 1:
            continue
        last = k
        h = hits[k] * gain * rng.uniform(.8, 1) * np.array([1 - max(0, pan), 1 + min(0, pan)])
        i = int((t + rng.normal(0, .01)) * SR)
        out[i:i + len(h)] += h
        t += 1 / rate
    out = out[:int(secs * SR)]
    return out / np.abs(out).max() * 0.89


def settled():
    rows = []
    chop = next(s for s in MANIFEST['sounds'] if s['id'] == 'chop_hits')
    if all((RAW / 'chop_hits' / f'{s}.wav').exists() for s in chop['takes'][0]['seeds']):
        hits = chop_hits(chop['takes'][0]['seeds'])
        for i, h in enumerate(hits):
            export(h, OUT / 'chop_hits' / f'hit_{i:02d}.mp3')
        export(chop_demo(hits, 3.7, 5, 1), OUT / 'chop_hits' / 'demo_solo.mp3')
        export(chop_demo(hits, 3.7, 5, 3, -.35, .75) + chop_demo(hits, 3.7, 5, 4, .35, .75), OUT / 'chop_hits' / 'demo_duo.mp3')
        rows.append(('chop_hits', f'{len(hits)} 刀素材，每秒 3.7 刀随动画触发', ['demo_solo', 'demo_duo']))
    wash = next(s for s in MANIFEST['sounds'] if s['id'] == 'wash_loop')
    if all((RAW / 'wash_loop' / f'{s}.wav').exists() for s in wash['takes'][0]['seeds']):
        tmp = OUT / 'wash_loop'; tmp.mkdir(parents=True, exist_ok=True)
        tamed = {}
        for s in wash['takes'][0]['seeds']:
            sf.write(tmp / f'_dc{s}.wav', SETTLED_DEWHINE(sf.read(RAW / 'wash_loop' / f'{s}.wav')[0]), SR)
            ffmpeg(tmp / f'_dc{s}.wav', tmp / f'_t{s}.wav', WASH_TAME)
            tamed[s] = sf.read(tmp / f'_t{s}.wav')[0]
        a, b = wash['takes'][0]['seeds']
        pan = lambda x, p: x * np.array([1 - max(0, p), 1 + min(0, p)])
        duo = pan(tamed[a], -.45) + pan(tamed[b], .45)
        sf.write(tmp / '_duo.wav', duo / np.abs(duo).max() * .89, SR)
        ffmpeg(tmp / '_duo.wav', tmp / '_duo_fast.wav', 'atempo=1.5')
        fade = lambda x: x * np.r_[np.linspace(0, 1, int(.08 * SR)), np.ones(len(x) - int(.33 * SR)), np.linspace(1, 0, int(.25 * SR))][:, None]
        solo = tamed[a] / np.abs(tamed[a]).max() * .89
        duo_fast = sf.read(tmp / '_duo_fast.wav')[0]
        export(fade(solo[:4 * SR]), tmp / 'demo_solo_4s.mp3')
        export(fade(duo_fast[:2 * SR]), tmp / 'demo_duo_2s.mp3')
        for p in tmp.glob('_*.wav'):
            p.unlink()
        rows.append(('wash_loop', '单人 4 秒 / 双人 2 秒（1.5 倍速，左右声道）', ['demo_solo_4s', 'demo_duo_2s']))
    return rows


# ---- audition page ----------------------------------------------------------------------------
GROUPS = [('music', '音乐（8-bit）'), ('ambience', '环境底噪'), ('chip', '界面 / 订单 / 出餐 / 结算（8-bit）'), ('real', '真实音效')]
TAKE_LABEL = {'v1': '第一版提示词', 'v2': '第二版提示词', 'v3': '第三版提示词（简化）', 'synth': '程序合成', 'reuse': '复用已选'}


def cand_html(sid, s, c, pickable=True):
    radio = f'<input type="radio" name="{sid}" value="{c["key"]}">' if pickable else ''
    title = c.get('title') or f'种子 {c["key"]}'
    return (f'<label class="cand"><span>{radio}{html.escape(title)}<small>{TAKE_LABEL.get(c["take"], "")} {c["dur"]:.1f}s'
            f'{" ⚠" + c["warn"] if c["warn"] else ""}</small></span>'
            f'<audio controls preload="none" {"loop" if s.get("loop") else ""} src="{sid}/{c["key"]}.mp3"></audio></label>')


def page(report, fixed):
    sounds = {s['id']: s for s in MANIFEST['sounds']}
    parts = []
    redo = [r for r in report if 'pick' not in sounds[r['id']]]
    picked = [r for r in report if 'pick' in sounds[r['id']]]
    if redo:
        parts.append('<h2>需要重选</h2><p class="prompt">订单与差评提示音、倒垃圾、组装汉堡：模型对“组合描述”生成的是整片噪声（原始输出里就没有音高），'
                     '这一轮改用最简单的游戏音效说法，并提供程序合成的 8-bit 版本或复用你已选的声音。失败乐句：每个候选都在第一处停顿后截断。</p>')
    for kind, title in GROUPS:
        rows = [r for r in redo if sounds[r['id']]['kind'] == kind]
        if not rows:
            continue
        parts.append(f'<h3 class="group">{title}</h3>')
        for r in rows:
            s = sounds[r['id']]
            shown = {c['take'] for c in r['cands']}
            prompts = '<br>'.join(f'{TAKE_LABEL[t["name"]]}：{html.escape(t["prompt"])}' for t in s['takes'] if t['name'] in shown)
            refs = ''
            for rid in s.get('compare', []):
                o = sounds[rid]
                refs += (f'<label class="cand ref"><span>对照：{html.escape(o["zh"])}<small>已选 {o["pick"]}</small></span>'
                         f'<audio controls preload="none" src="{rid}/{o["pick"]}.mp3"></audio></label>')
            if 'show_synth' in s:
                prompts = '三种不同听感的程序合成：C 两声低音“卜-卜”；D 不和谐的三全音蜂鸣；E 往下滑的滑稽“哇～”。旁边附上订单过期与操作不可用作对照。'
            parts.append(
                f'<section class="sound" data-id="{r["id"]}"><header><h3>{html.escape(s["zh"])}</h3><code>{r["id"]}</code>'
                f'{"<em>循环</em>" if s.get("loop") else ""}</header><p class="prompt">{prompts}</p>'
                f'<div class="cands">{"".join(cand_html(r["id"], s, c) for c in r["cands"])}{refs}'
                f'<label class="cand none"><span><input type="radio" name="{r["id"]}" value="redo">都不满意，重做</span></label></div>'
                f'<input class="note" name="{r["id"]}-note" placeholder="备注（可选），比如：再轻一点、要更短"></section>')
    if picked:
        parts.append(f'<details><summary><h2>已选（{len(picked)} 个，点开可复听）</h2></summary>')
        for r in picked:
            s = sounds[r['id']]
            parts.append(f'<section class="sound" data-id="{r["id"]}" data-picked="{s["pick"]}"><header><h3>{html.escape(s["zh"])}</h3><code>{r["id"]}</code>'
                         f'{"<em>循环</em>" if s.get("loop") else ""}</header><div class="cands">{cand_html(r["id"], s, r["cands"][0], False)}</div>'
                         f'<input class="note" name="{r["id"]}-note" placeholder="有问题才写"></section>')
        parts.append('</details>')
    if fixed:
        parts.append('<h2>已定稿（仅供对照，无需挑选）</h2>')
        for sid, desc, files in fixed:
            players = ''.join(f'<label class="cand"><span>{f}</span><audio controls preload="none" src="{sid}/{f}.mp3"></audio></label>' for f in files)
            parts.append(f'<section class="sound"><header><h3>{html.escape(sounds[sid]["zh"])}</h3><code>{sid}</code></header>'
                         f'<p class="prompt">{desc}</p><div class="cands">{players}</div></section>')
    tpl = (Path(__file__).parent / 'audition_template.html').read_text()
    (OUT / 'index.html').write_text(tpl.replace('<!--SOUNDS-->', '\n'.join(parts)))


def candidate(s, take, key, x, before=0.0, after=0.0, title=None):
    warn = ''
    # Chip/music are low-passed as a whole band, so relative comb excess is not meaningful there.
    if s['kind'] not in ('chip', 'music') and after > 4:
        warn = f'残留耳鸣 {after:.0f}dB'
    elif len(x) < 0.05 * SR:
        warn = '几乎无声'
    export(x, OUT / s['id'] / f'{key}.mp3')
    return {'key': key, 'take': take, 'title': title, 'dur': len(x) / SR,
            'comb_before': round(before, 1), 'comb_after': round(after, 1), 'warn': warn}


def model_candidate(s, take, seed):
    raw = RAW / s['id'] / f'{seed}.wav'
    if not raw.exists():
        return None
    return candidate(s, take, seed, *clean(raw, s))


def main():
    from chiptune import CUES
    sounds = {s['id']: s for s in MANIFEST['sounds']}
    report = []
    for s in MANIFEST['sounds']:
        if s.get('fixed'):
            continue
        cands = []
        if 'pick' in s:
            pick = s['pick']
            take = next((t['name'] for t in s['takes'] if pick in t['seeds']), 'synth' if str(pick).startswith('synth') else 'reuse')
            if take == 'synth':
                cands.append(candidate(s, 'synth', pick, CUES[s['id']][pick](), title=f'合成 {pick[-1].upper()}'))
            elif take == 'reuse':
                src = sounds[s['reuse']['id']]
                cands.append(candidate(s, 'reuse', 'reuse', clean(RAW / src['id'] / f'{s["reuse"]["seed"]}.wav', src)[0], title=f'复用 {src["zh"]}'))
            else:
                cands.append(model_candidate(s, take, pick))
        elif 'show_synth' in s:
            cands = [candidate(s, 'synth', k, CUES[s['id']][k](), title=f'合成 {k[-1].upper()}') for k in s['show_synth']]
        else:
            # Once a simplified third take exists, earlier takes were rejected twice: only show the new options.
            takes = [t for t in s['takes'] if t['name'] == 'v3'] or s['takes']
            cands = [model_candidate(s, t['name'], seed) for t in takes for seed in t['seeds']]
            if s.get('synth'):
                cands += [candidate(s, 'synth', k, fn(), title=f'合成 {k[-1].upper()}') for k, fn in CUES[s['id']].items()]
            if 'reuse' in s:
                src = sounds[s['reuse']['id']]
                cands.append(candidate(s, 'reuse', 'reuse', clean(RAW / src['id'] / f'{s["reuse"]["seed"]}.wav', src)[0], title=f'复用 {src["zh"]}'))
        cands = [c for c in cands if c]
        if cands:
            report.append({'id': s['id'], 'cands': cands})
            print(s['id'], ' '.join(f'{c["key"]}:{c["dur"]:.1f}s{" !" + c["warn"] if c["warn"] else ""}' for c in cands), flush=True)
    fixed = settled()
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    page(report, fixed)
    print(f'audition page: {OUT / "index.html"}')


if __name__ == '__main__':
    main()
