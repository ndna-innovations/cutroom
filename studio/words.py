"""Words: transcription with word timings, cue lookup, checked word lists, speech pieces, word-level cut points.

- `transcribe(media, lo, hi)` -> [[start, end, word], ...] (absolute seconds in the media). Long audio is split on
  silences and transcribed chunk by chunk (whole-file Whisper repeats lines and invents "Thank you").
- Whisper word times run early/late by up to ~0.5 s, so cut points are refined on the audio: `quiet_point` finds the
  quietest 10 ms near a boundary, `speech_pieces` cuts pauses with silencedetect, `extend_end` never clips a word.
- `checked(words, fixes)` applies a checked word list (e.g. {"Smart but worth it": "Smarter, but worth it"}):
  captions always come from checked words, never from a fresh re-transcription."""
import json, os, re, subprocess
import numpy as np
from . import cache
from .media import run, ff, log, fingerprint

from .config import path as _cfg_path, profile as _profile
MODEL = _cfg_path("whisper")
WHISPER = ["whisper-cli", "-m", MODEL, "-np", "-l", "en", "-ml", "1", "-sow"]
NAMES = {k.lower(): v for k, v in (_profile().get("word_fixes") or {}).items()}     # names the speech model mishears (profile)


def wav16(src, lo=None, hi=None):
    k = cache.key("wav16", src, lo, hi)
    out = cache.path("wav16", k, "wav")
    if os.path.exists(out): return out
    a = (["-ss", f"{lo:.3f}"] if lo is not None else []) + (["-to", f"{hi:.3f}"] if hi is not None else [])
    ff([*a, "-i", src, "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", cache.tmp(out)], label="wav16")
    return cache.commit(out)


def load_pcm(w):
    import soundfile as sf
    x, sr = sf.read(w, dtype="float32")
    return (x if x.ndim == 1 else x.mean(1)), sr


def envelope(src, lo=None, hi=None, hop=0.01):
    """RMS in dB per 10 ms (absolute time index: t = lo + i*hop)."""
    x, sr = load_pcm(wav16(src, lo, hi))
    n = int(sr * hop); m = len(x) // n
    r = np.sqrt((x[: m * n].reshape(m, n) ** 2).mean(1) + 1e-10)
    return 20 * np.log10(r), (lo or 0.0), hop


def silences(src, lo, hi, db=-45, d=0.35):
    e = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", wav16(src, lo, hi), "-af", f"silencedetect=n={db}dB:d={d}", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    st = [lo + float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", e)]
    en = [lo + float(x) for x in re.findall(r"silence_end: ([\d.]+)", e)]
    if len(en) < len(st): en.append(hi)
    return list(zip(st, en))


def speech_pieces(src, lo, hi, gap=0.35, pad=0.12, db=-45, fps=30):
    """Speech inside [lo, hi] with pauses longer than `gap` removed; `pad` s kept around each piece; whole frames."""
    regs, prev = [], lo
    for s0, s1 in silences(src, lo, hi, db, gap):
        if s0 - prev > 0.05: regs.append([prev, s0])
        prev = s1
    if hi - prev > 0.05: regs.append([prev, hi])
    out = []
    for a, b in regs:
        a, b = max(lo, a - pad), min(hi, b + pad)
        if out and a <= out[-1][1] + 0.02: out[-1][1] = b
        else: out.append([a, b])
    res = []
    for a, b in out:
        fa = round(a * fps) / fps; nf = max(1, round((b - a) * fps))
        res.append((fa, fa + nf / fps))
    return res


def quiet_point(src, t, search=0.25, lo=None, hi=None):
    """The quietest 10 ms within +-search of t (used to place a cut between words)."""
    a = max(0.0, t - search); b = t + search
    env, t0, hop = envelope(src, a, b)
    i = int(np.argmin(env))
    return t0 + i * hop + hop / 2


def _before(ws, i, pad):
    """Cut point just before word i: `pad` s early, but never back into the word before it (half the gap if tight)."""
    s = ws[i][0]
    return min(s, max(s - pad, (ws[i - 1][1] + s) / 2)) if i > 0 else s - pad


def _after(ws, i, pad):
    """Cut point just after word i: `pad` s late, but never into the next word (half the gap if tight)."""
    e = ws[i][1]
    return max(e, min(e + pad, (e + ws[i + 1][0]) / 2)) if i + 1 < len(ws) else e + pad


def voiced(src, ws, gap=0.15, reach=0.25):
    """Words moved to where their sound is: speech-model word times are rough (a word often runs on over the pause
    after it, starts late or ends early), which would make a cut look like it is inside a word when it is in a pause,
    or the other way round. Each word starts at its first loud 10 ms and ends at its first quiet stretch of `gap` s,
    reaching up to `reach` s past the model's times while the sound goes on (never into the neighbouring words).
    "Loud" = 15 dB over the clip's noise floor (at least -60 dB). Words with under 40 ms of sound are left out."""
    if not ws: return ws
    env, t0, hop = envelope(src, max(0.0, ws[0][0] - reach), ws[-1][1] + reach)
    db = max(float(np.percentile(env, 10)) + 15, -60.0)
    loud = env > db; R = int(reach / hop)
    out = []
    for n, w in enumerate(ws):
        i0, i1 = max(0, int((w[0] - t0) / hop)), min(len(env), int((w[1] - t0) / hop) + 1)
        on = np.nonzero(loud[i0:i1])[0]
        if not len(on): out.append(list(w)); continue
        lo = max(0, i0 - R, int((out[-1][1] - t0) / hop) if out else 0)
        hi = min(len(env), i1 + R, int((ws[n + 1][0] - t0) / hop) if n + 1 < len(ws) else len(env))
        a = i0 + on[0]
        while a - 1 >= lo and loud[a - 1]: a -= 1
        b, q = a, 0
        for k in range(a, hi):
            if loud[k]: b, q = k, 0
            else:
                q += 1
                if q * hop >= gap or k >= i1: break
        if (b + 1 - a) * hop < 0.04: continue      # under 40 ms of sound: a mis-timed scrap (e.g. a word's onset given to the one before)
        out.append([round(float(t0 + a * hop), 3), round(float(t0 + (b + 1) * hop), 3), w[2]])
    return out


def sound_runs(src, lo, hi, gap=0.05):
    """Stretches of sound in src[lo:hi] (absolute seconds) split by quiet of at least `gap` s: [[start, end], ...].
    "Sound" = 15 dB over the stretch's noise floor (at least -60 dB)."""
    env, t0, hop = envelope(src, lo, hi)
    loud = env > max(float(np.percentile(env, 10)) + 15, -60.0)
    out, q = [], 0
    for k, on in enumerate(loud):
        if on:
            if out and q * hop < gap: out[-1][1] = round(t0 + (k + 1) * hop, 3)
            else: out.append([round(t0 + k * hop, 3), round(t0 + (k + 1) * hop, 3)])
            q = 0
        else: q += 1
    return out


def _run_edge(runs, t, pad, near):
    """A cut inside a stretch of sound and within `near` s of its edge goes to that edge (+ pad into the pause)."""
    for i, r in enumerate(runs):
        if r[0] < t < r[1]:
            if min(t - r[0], r[1] - t) >= near: return None
            return _before(runs, i, pad) if t - r[0] <= r[1] - t else _after(runs, i, pad)
    return None


def snap_start(ws, t, pad=0.06, runs=None, near=0.25):
    """Where kept speech starts (a range start, the end of a cut), moved off any word: a word that t falls inside is
    kept whole when most of it is after t, else left out whole. ws = [[start, end, text]] in the same seconds as t.
    With `runs` (sound_runs) the sound decides first: a cut in a pause stays (pad rule only), a cut just inside a
    stretch of sound goes to its nearer edge; only deep inside a stretch do the (rougher) word times decide."""
    if runs is not None:
        e = _run_edge(runs, t, pad, near)
        if e is not None: return e
        if not any(r[0] < t < r[1] for r in runs): ws = runs
    for i, w in enumerate(ws):
        if w[0] < t < w[1]: return _before(ws, i, pad) if (w[0] + w[1]) / 2 >= t else _after(ws, i, pad)
    for i, w in enumerate(ws):
        if w[0] - pad < t <= w[0]: return min(t, _before(ws, i, pad))
    return t


def snap_end(ws, t, pad=0.06, runs=None, near=0.25):
    """Where kept speech ends (a range end, the start of a cut), moved off any word: a word that t falls inside is kept
    whole when most of it is before t, else left out whole. `runs`: as in snap_start."""
    if runs is not None:
        e = _run_edge(runs, t, pad, near)
        if e is not None: return e
        if not any(r[0] < t < r[1] for r in runs): ws = runs
    for i, w in enumerate(ws):
        if w[0] < t < w[1]: return _after(ws, i, pad) if (w[0] + w[1]) / 2 <= t else _before(ws, i, pad)
    for i, w in enumerate(ws):
        if w[1] <= t < w[1] + pad: return max(t, _after(ws, i, pad))
    return t


def extend_end(src, t, limit=0.8, db=-42):
    """Push an end time forward until the audio is quiet (Whisper ends words early: never clip his last word)."""
    env, t0, hop = envelope(src, t, t + limit)
    below = np.nonzero(env < db)[0]
    if not len(below): return t + limit
    # first run of >= 60 ms quiet
    run_ = 0
    for i in range(len(env)):
        run_ = run_ + 1 if env[i] < db else 0
        if run_ >= 6: return t0 + (i - 5) * hop + 0.06
    return t0 + below[0] * hop


def _whisper(w16):
    o = run(WHISPER + ["-f", w16]).stdout
    def ts(x): h, mi, r = x.split(":"); return int(h) * 3600 + int(mi) * 60 + float(r)
    ws = []
    for l in o.splitlines():
        mm = re.match(r"\[(\S+) --> (\S+)\]\s*(.*)", l.strip())
        if mm and mm.group(3).strip(): ws.append([ts(mm.group(1)), ts(mm.group(2)), mm.group(3).strip()])
    return ws


def transcribe(src, lo=None, hi=None, chunk=28.0):
    """Word timings for src[lo:hi] (absolute seconds). Cached by file fingerprint + range."""
    k = cache.key("words2", src, lo, hi, chunk, MODEL)
    jp = cache.path("words", k, "json")
    if os.path.exists(jp): return json.load(open(jp))
    from .media import duration
    lo = lo or 0.0; hi = hi if hi is not None else duration(src)
    # chunk boundaries at silences
    cuts, cur = [lo], lo
    sil = silences(src, lo, hi, -40, 0.3)
    while hi - cur > chunk:
        cand = [(s0 + s1) / 2 for s0, s1 in sil if cur + chunk * 0.5 < (s0 + s1) / 2 < cur + chunk]
        cur = cand[-1] if cand else cur + chunk
        cuts.append(cur)
    cuts.append(hi)
    ws = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a < 0.2: continue
        for w in _whisper(wav16(src, a, b)):
            ws.append([round(a + w[0], 3), round(a + w[1], 3), w[2]])
    json.dump(ws, open(jp, "w"))
    return ws


def text(ws):
    return " ".join(w[2] for w in ws)


def norm(s):
    return re.sub(r"[^a-z0-9%#.' ]", "", s.lower()).strip(" .")


def find(ws, phrase, n=1, after=0.0, start=0):
    """Index of the n-th occurrence of `phrase` (one or more words; '|' = alternatives) starting at/after `after`
    (seconds) and at/after word index `start`."""
    for alt in phrase.split("|"):
        toks = [norm(t) for t in alt.split() if norm(t)]
        k = 0
        for i, w in enumerate(ws):
            if i < start or w[0] < after - 0.01: continue
            if all(i + j < len(ws) and toks[j] in norm(ws[i + j][2]) for j in range(len(toks))):
                k += 1
                if k == n: return i
    raise KeyError(f"cue not found: {phrase!r} #{n} after {after:.2f}. Heard: " + text(ws)[:600])


def cue(ws, phrase, n=1, after=0.0, lead=0.08):
    """Start time of a spoken phrase (a hair early so a graphic lands ON the word)."""
    return max(0.0, ws[find(ws, phrase, n, after)][0] - lead)


def cue_end(ws, phrase, n=1, after=0.0):
    toks = [t for t in phrase.split("|")[0].split() if norm(t)]
    i = find(ws, phrase, n, after)
    return ws[min(len(ws) - 1, i + len(toks) - 1)][1]


def checked(ws, fixes=None):
    """Apply a checked word list. fixes: {"heard phrase": "correct phrase"} (same or different word count) and NAMES."""
    out = [list(w) for w in ws]
    for w in out:
        k = norm(w[2])
        if k in NAMES: w[2] = re.sub(re.escape(k), NAMES[k], w[2], flags=re.I) if k in w[2].lower() else NAMES[k]
    for bad, good in (fixes or {}).items():
        bt = bad.split(); gt = good.split()
        i = 0
        while i <= len(out) - len(bt):
            if all(norm(out[i + j][2]) == norm(bt[j]) for j in range(len(bt))):
                a, b = out[i][0], out[i + len(bt) - 1][1]
                step = (b - a) / len(gt)
                out[i:i + len(bt)] = [[a + j * step, a + (j + 1) * step, gt[j]] for j in range(len(gt))]
                i += len(gt)
            else: i += 1
    return out


def remap(ws, pieces, fps=30):
    """Map absolute source word times through a list of kept pieces [(a, b), ...] to output time; drops cut words."""
    out, t = [], 0.0
    for a, b in pieces:
        for w in ws:
            mid = (w[0] + w[1]) / 2
            if a <= mid < b: out.append([round(t + max(0, w[0] - a), 3), round(t + min(b, w[1]) - a, 3), w[2]])
        t += b - a
    return out


SLIPS = r"\b(cut|action|retake|take two|let me (say|start|do) (that|it) again|start (that )?again|one more time)\b"


def slips(ws):
    """Spots where he said 'cut', 'action', 'retake'… (to remove from the edit)."""
    t = [(w[0], norm(w[2])) for w in ws]
    hits = []
    s = " ".join(x[1] for x in t)
    for m in re.finditer(SLIPS, s):
        i = s[: m.start()].count(" ")
        hits.append((t[min(i, len(t) - 1)][0], m.group(0)))
    return hits


def repeats(ws, n=4):
    """Repeated n-word runs (a line said twice = a retake left in)."""
    toks = [norm(w[2]) for w in ws]; seen = {}; hits = []
    for i in range(len(toks) - n):
        g = tuple(toks[i:i + n])
        if any(not x for x in g): continue
        if g in seen and ws[i][0] - ws[seen[g]][0] < 60: hits.append((ws[seen[g]][0], ws[i][0], " ".join(g)))
        seen[g] = i
    return hits
