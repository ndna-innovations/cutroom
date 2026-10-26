"""Sound: his voice (cleaned), music from the sound library only, ducking, sound effects, loudness.

How it works (engine behaviour, not style):
- Music comes from the configured sound library (config paths.sound_library), so its licence is known. `music_path()` refuses others.
- Beds are looped seamlessly (crossfaded) and checked for silent tails first (the old E-bed went silent for 1.9 s).
- Bed level is set per scene ("music": 0.17 or null = off) with 0.5 s ramps; ducked under his voice (sidechain).
- Final loudness: one fixed gain to the target (default -14.4 LUFS) + a true-peak-safe limiter. Never dynamic loudnorm.
- Sound effects only where the timeline asks for them."""
import json, os, re, subprocess
import numpy as np
from . import cache
from .media import ff, log, run, duration
from .model import FPS

from .config import path as _cfg_path
LIBRARY = _cfg_path("sound_library")
VOICE = ("highpass=f=80,afftdn=nf=-45,equalizer=f=180:t=q:w=1:g=2,equalizer=f=3500:t=q:w=1.5:g=1,deesser=i=0.35,"
         "equalizer=f=3500:t=q:w=1.5:g=0.5,acompressor=threshold=-22dB:ratio=3:attack=5:release=90:makeup=2,treble=g=2:f=6500,"
         "agate=threshold=0.005:ratio=2:range=0.25:attack=5:release=300:knee=6")      # gentle expander: pauses settle back (compression lifted them)
SR = 48000


def music_path(p):
    """Music only from the sound library (known licences)."""
    full = os.path.realpath(os.path.expanduser(p if os.path.isabs(os.path.expanduser(p)) else os.path.join(LIBRARY, p)))
    if not full.startswith(os.path.realpath(LIBRARY)):
        raise ValueError(f"music must come from the sound library ({LIBRARY}), not {p}")
    if not os.path.exists(full): raise FileNotFoundError(full)
    return full


def silent_tail(path, db=-50):
    """Seconds of near-silence at the end of a file (so loops can skip it)."""
    e = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", f"silencedetect=n={db}dB:d=0.3", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    D = duration(path)
    st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", e)]
    en = re.findall(r"silence_end: ([\d.]+)", e)
    if st and (len(en) < len(st) or abs(float(en[-1]) - D) < 0.05): return D - st[-1]
    return 0.0


def seamless_bed(path, total, start=1.0, xf=1.5):
    """A bed at least `total` s long: [start, end - silent tail - fade] chained with xf-second crossfades."""
    D = duration(path); tail = silent_tail(path)
    # avoid the track's own fade-out: use the loudness envelope to find where it drops
    seg_end = D - tail - 2.0
    L = seg_end - start
    n = int(total / (L - xf)) + 2
    k = cache.key("bed2", path, round(total, 1), start, xf)
    out = cache.path("audio", "bed_" + k, "wav")
    if os.path.exists(out): return out
    ins = sum((["-ss", f"{start:.3f}", "-t", f"{L:.3f}", "-i", path] for _ in range(n)), [])
    chain, prev = "", "0:a"
    for i in range(1, n):
        chain += f"[{prev}][{i}:a]acrossfade=d={xf}:c1=qsin:c2=qsin[x{i}];"; prev = f"x{i}"
    ff([*ins, "-filter_complex", chain.rstrip(";") if chain else "[0:a]anull[x0]", "-map", f"[{prev if chain else 'x0'}]",
        "-ar", str(SR), "-ac", "2", cache.tmp(out)], label="bed")
    return cache.commit(out)


DEEPFILTER = _cfg_path("deepfilter")


def piece_levels(src, pieces, max_db=3.0):
    """Gain (dB) per voice piece so loud and quiet sentences sit closer together (pro "clip gain" levelling):
    each piece's speech loudness vs the scene's median, corrected by up to +/- max_db; holds and near-silent pieces 0."""
    import numpy as np
    out = []
    for p in pieces:
        if p["hold"] or p["n"] < 0.6 * FPS: out.append(0.0); continue        # too short to judge: leave it
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{p['a']:.3f}", "-t", f"{p['n'] / FPS:.3f}", "-i", src, "-ac", "1", "-ar", "8000",
                              "-f", "s16le", "-"], capture_output=True).stdout
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        if len(x) < 800: out.append(None); continue
        fr_ = x[: len(x) // 400 * 400].reshape(-1, 400); db = 20 * np.log10(np.sqrt((fr_ ** 2).mean(1)) + 1e-9)
        sp_ = db[db > db.max() - 25]                       # speech frames only
        out.append(float(np.percentile(sp_, 70)) if len(sp_) > 3 else None)
    vals = [v for v in out if v not in (None, 0.0)]
    if len(vals) < 2: return [0.0] * len(pieces)
    med = float(np.median(vals))
    return [0.0 if v in (None, 0.0) else float(np.clip(med - v, -max_db, max_db)) for v in out]


def scene_voice(sc, enhance=None):
    """Processed voice for one scene, exactly nf frames long; holds are silent; 4 ms fades at every join (no clicks).
    enhance: {"model": "deepfilter", "atten": 28} -> DeepFilterNet 3 (MIT/Apache) removes room noise first, keeping
    up to `atten` dB of it so pauses sound natural, then the voice chain (without its own denoiser)."""
    enhance = enhance if enhance is not None else sc.get("enhance")
    lev = sc.get("level", True)
    fin = max(0.004, float((sc.get("spine") or {}).get("fade_in", 0.004)))   # spine "fade_in": softer start on each piece (Shorts: 0.04)
    k = cache.key("voice6", sc["src"], [(p["a"], p["n"], p["hold"], p.get("tail", 0)) for p in sc["pieces"]], sc["nf"], VOICE, enhance, lev, fin)
    out = cache.path("audio", "voice_" + k, "wav")
    if os.path.exists(out): return out
    ins, fc, labs = [], [], []
    gains = piece_levels(sc["src"], sc["pieces"], lev if isinstance(lev, (int, float)) and lev is not True else 3.0) if lev else [0.0] * len(sc["pieces"])
    for i, p in enumerate(sc["pieces"]):
        d = p["n"] / FPS
        ins += ["-ss", f"{p['a']:.4f}", "-t", f"{d + 0.05:.4f}", "-i", sc["src"]]
        v = ",volume=0" if p["hold"] else (f",volume={gains[i]:.2f}dB" if abs(gains[i]) > 0.2 else "")
        da = d - p.get("tail", 0) / FPS        # a scene "tail" holds the (frozen) picture after his last word: silent, never the next words of the take
        fc.append(f"[{i}:a:0]aresample={SR},pan=mono|c0=c0,atrim=0:{da:.5f},asetpts=PTS-STARTPTS,afade=t=in:d={min(fin, da / 3):.4f},afade=t=out:st={max(0, da - 0.004):.5f}:d=0.004{v},apad=whole_dur={d:.5f}[a{i}]")
        labs.append(f"[a{i}]")
    chain = VOICE
    if enhance and os.path.exists(DEEPFILTER):
        raw = out + ".raw.wav"
        fc.append("".join(labs) + f"concat=n={len(labs)}:v=0:a=1[v]")
        ff([*ins, "-filter_complex", ";".join(fc), "-map", "[v]", "-ar", str(SR), "-c:a", "pcm_s16le", raw], label=f"voice-raw {sc['id']}")
        d = out + ".df"; os.makedirs(d, exist_ok=True)
        subprocess.run([DEEPFILTER, "-D", "-a", str(enhance.get("atten", 28)), "-o", d, raw], check=True, capture_output=True)
        ins, fc, labs = ["-i", os.path.join(d, os.path.basename(raw))], [], ["[0:a]"]
        chain = VOICE.replace("afftdn=nf=-45,", "")
        fc.append(f"[0:a]{chain},pan=stereo|c0=c0|c1=c0,apad=whole_dur={sc['nf'] / FPS:.5f},atrim=0:{sc['nf'] / FPS:.5f}[v]")
        ff([*ins, "-filter_complex", ";".join(fc), "-map", "[v]", "-ar", str(SR), "-c:a", "pcm_s24le", cache.tmp(out)], label=f"voice {sc['id']}")
        import shutil; shutil.rmtree(d, ignore_errors=True); os.remove(raw)
        return cache.commit(out)
    fc.append("".join(labs) + f"concat=n={len(labs)}:v=0:a=1,{chain},pan=stereo|c0=c0|c1=c0,apad=whole_dur={sc['nf'] / FPS:.5f},atrim=0:{sc['nf'] / FPS:.5f}[v]")
    ff([*ins, "-filter_complex", ";".join(fc), "-map", "[v]", "-ar", str(SR), "-c:a", "pcm_s24le", cache.tmp(out)], label=f"voice {sc['id']}")
    if sc.get("declick", True):
        dc, n = declick(cache.tmp(out), cache.tmp(out) + ".dc.wav")
        if n: os.replace(dc, cache.tmp(out)); log(f"voice {sc['id']}: removed {n} click(s)")
    return cache.commit(out)


def _ramp_expr(spans, total):
    """volume expression: sum of plateaus with 0.5 s ramps; spans = [(t0, t1, level)]."""
    if not spans: return "0"
    terms = [f"{lv:.3f}*clip((t-{a - 0.25:.3f})/0.5,0,1)*clip(({b + 0.25:.3f}-t)/0.5,0,1)" for a, b, lv in spans]
    return "min(1," + "+".join(terms) + ")"


PINK_RMS_DB = -23.6      # RMS of anoisesrc pink amplitude 0.5 after the 90 Hz-7 kHz band (measured once; see room_tone_level)


def room_tone_level(voice_files, floor=-90.0, ceil=-48.0):
    """The natural level of his pauses (dBFS RMS): the median of the quiet-but-not-silent 20 ms frames in the voice tracks."""
    import numpy as np
    qs = []
    for f in voice_files:
        x = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout,
                          np.int16).astype(np.float32) / 32768
        h = 160; x = x[: len(x) // h * h].reshape(-1, h)
        db = 20 * np.log10(np.sqrt((x ** 2).mean(1)) + 1e-9)
        qs.append(db[(db > floor) & (db < ceil)])
    q = np.concatenate(qs) if qs else np.array([])
    if len(q) < 50: return -78.0          # a very clean recording: still lay a whisper of tone so shots without voice aren't dead
    return float(np.clip(np.percentile(q, 20), -84, -74))      # just under his real pauses: fills holes, never adds hiss (final gain adds ~+6 dB)


def mix(R, out_wav):
    """The whole soundtrack: voice of every scene (crossfaded at dissolves), music bed with per-scene levels and
    ducking, intro/outro stings, sound effects; then fixed gain to the loudness target + limiter."""
    tl = R["tl"]; A = tl.get("audio", {})
    total = R["total"] / FPS
    ins, fc, mixl = [], [], []
    n = 0
    for sc in R["scenes"]:
        t0 = sc["start"] / FPS
        if sc["pieces"]:
            ins += ["-i", scene_voice(sc, enhance=tl["sources"].get(sc["source_id"], {}).get("enhance"))]
            fi = f",afade=t=in:d={sc['trans'] / FPS:.3f}" if sc["trans"] else ""
            nxt = next((s for s in R["scenes"] if s["index"] == sc["index"] + 1), None)
            fo = f",afade=t=out:st={(sc['nf'] - nxt['trans']) / FPS:.3f}:d={nxt['trans'] / FPS:.3f}" if nxt and nxt["trans"] else ""
            # each piece padded to the full length: amix (duration=longest) sometimes ended when the first scene's voice ended,
            # leaving the rest of the video silent (seen 2026-10-24 on Short drafts, not on every run)
            fc.append(f"[{n}:a]asetpts=PTS-STARTPTS{fi}{fo},adelay={int(round(t0 * 1000))}:all=1,apad=whole_dur={total:.4f}[vo{n}]"); mixl.append(f"[vo{n}]"); n += 1
    voice = "voice"
    fc.append("".join(mixl) + f"amix=inputs={len(mixl)}:normalize=0:duration=longest,apad=whole_dur={total:.4f},atrim=0:{total:.4f}[{voice}]" if mixl
              else f"anullsrc=r={SR}:cl=stereo,atrim=0:{total:.4f}[{voice}]")
    layers = []
    # room tone under everything: pauses, cuts and voice-less shots never fall to digital silence (sounds like a dropout)
    rt = A.get("room_tone", "auto")
    if rt and mixl:
        lvl = room_tone_level([ins[i + 1] for i in range(0, len(ins), 2)]) if rt == "auto" else float(rt)
        if lvl is not None:
            g_ = 10 ** ((lvl - PINK_RMS_DB) / 20)
            fc.append(f"anoisesrc=r={SR}:color=pink:amplitude=0.5:seed=7,highpass=f=90,lowpass=f=7000,volume={g_:.6f},"
                      f"pan=stereo|c0=c0|c1=c0,atrim=0:{total:.4f}[rtone]"); layers.append("[rtone]")
    bed = A.get("bed")
    spans = [(s["start"] / FPS, (s["start"] + s["nf"]) / FPS, s["music"]) for s in R["scenes"] if s.get("music")]
    for sp_ in A.get("music_spots", []): spans.append(tuple(sp_))
    if bed and spans:
        bp = music_path(tl["sources"][bed]["path"] if bed in tl["sources"] else bed)
        ins += ["-i", seamless_bed(bp, total + 2, start=A.get("bed_start", 1.0))]   # "bed_start": where in the track the bed begins (skip a silent intro)
        fc.append(f"[{n}:a]atrim=0:{total:.4f},asetpts=PTS-STARTPTS,volume='{_ramp_expr(spans, total)}':eval=frame,lowpass=f={A.get('bed_lowpass', 10000)}[bd{n}]")
        fc.append(f"[{voice}]asplit=2[{voice}m][{voice}k];[bd{n}][{voice}k]sidechaincompress=threshold={A.get('duck_threshold', 0.03)}:ratio={A.get('duck_ratio', 5)}:attack=20:release=350[bdd]")
        voice = f"{voice}m"; layers.append("[bdd]"); n += 1
    for cue in A.get("cues", []):         # stings: {"path", "at", "from", "dur", "gain", "fade_in", "fade_out"}
        p = music_path(cue["path"]) if cue.get("music", True) else os.path.expanduser(cue["path"])
        if cue.get("fit") and cue.get("dur"): p = fit_music(cue["path"], cue["dur"]); cue = dict(cue, **{"from": 0})
        at = cue["at"] if isinstance(cue["at"], (int, float)) else _scene_time(R, cue["at"])
        if at is None: log(f"audio: cue {os.path.basename(cue['path'])} skipped (its scene {cue['at'].get('scene')} is not in this timeline)"); continue
        ins += ["-ss", f"{cue.get('from', 0):.3f}", "-i", p]
        dur_ = cue.get("dur")
        tr = f"atrim=0:{dur_:.3f}," if dur_ else ""
        fo = f",afade=t=out:st={dur_ - cue.get('fade_out', 0.8):.3f}:d={cue.get('fade_out', 0.8):.3f}" if dur_ else ""
        fc.append(f"[{n}:a]{tr}asetpts=PTS-STARTPTS,afade=t=in:d={cue.get('fade_in', 0.05):.3f}{fo},volume={cue.get('gain', 0.5)},aresample={SR},adelay={int(round(at * 1000))}:all=1[c{n}]")
        layers.append(f"[c{n}]"); n += 1
    for sc in R["scenes"]:
        for fx in sc["sfx"]:
            p = os.path.expanduser(fx["path"]); at = sc["start"] / FPS + fx.get("at", 0)
            ins += ["-i", p]
            fc.append(f"[{n}:a]volume={fx.get('gain', 1.0)},aresample={SR},adelay={int(round(max(0, at) * 1000))}:all=1[f{n}]")
            layers.append(f"[f{n}]"); n += 1
    fc.append(f"[{voice}]" + "".join(layers) + f"amix=inputs={1 + len(layers)}:normalize=0:duration=first,atrim=0:{total:.4f}[pre]")
    pre = out_wav + ".pre.wav"
    ff([*ins, "-filter_complex", ";".join(fc), "-map", "[pre]", "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s24le", pre], label="mix")
    I, TP = loudness(pre)
    target = A.get("loudness", -14.4); g = round(target - I, 2)
    lim = A.get("limit", 0.85)
    for _ in range(3):     # limiter runs 4x oversampled (catches inter-sample peaks); tighten if the true peak still tops -1 dBTP
        ff(["-i", pre, "-af", f"volume={g}dB,aresample={SR * 4},alimiter=limit={lim}:level=false:attack=3:release=60,aresample={SR}",
            "-ar", str(SR), "-c:a", "pcm_s24le", cache.tmp(out_wav)], label="loudness")
        I2, TP2 = loudness(cache.tmp(out_wav))
        if TP2 <= -1.0: break
        lim = round(lim * 10 ** ((-1.1 - TP2) / 20), 3)
    os.replace(cache.tmp(out_wav), out_wav); os.remove(pre)
    log(f"audio: {I:.1f} LUFS -> gain {g:+.2f} dB -> {I2:.1f} LUFS, true peak {TP2:.1f} dBTP")
    return dict(lufs=I2, true_peak=TP2, gain=g)


def _scene_time(R, a):
    """{"scene": id, "at": t} -> timeline seconds."""
    sc = next((s for s in R["scenes"] if s["id"] == a["scene"]), None)
    if sc is None: return None                      # the scene was cut: the cue is skipped
    return sc["start"] / FPS + a.get("at", 0) + (sc["nf"] / FPS if a.get("from_end") else 0)


def loudness(path):
    e = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    I = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", e)[-1])
    tp = re.findall(r"Peak:\s+(-?[\d.]+|-inf) dBFS", e)
    return I, (float(tp[-1]) if tp and tp[-1] != "-inf" else -99.0)


# ---------------------------------------------------------------------- mouth clicks / mic knocks
def declick(path, out=None, max_ms=3.0):
    """Remove mouth clicks and mic knocks without touching words (conservative on purpose):
    a click = a burst of <= `max_ms` in the high band (> 3 kHz) that is (a) at least 20x the high-band level of the
    50 ms around it, (b) isolated (no other burst within 40 ms: fricatives like "s" are long, so they never qualify),
    and (c) in a pause (surroundings quieter than -50 dBFS): speech is never touched. Only those few ms are bridged.
    Returns (path, n_clicks)."""
    import soundfile as sf
    from scipy.signal import butter, sosfiltfilt
    from scipy.ndimage import uniform_filter1d
    x, sr = sf.read(path, dtype="float64", always_2d=True)
    mono = x.mean(1)
    hp = sosfiltfilt(butter(4, 3000, "highpass", fs=sr, output="sos"), mono)
    e = hp ** 2
    burst = uniform_filter1d(e, max(1, int(sr * 0.001)))                       # 1 ms energy
    around = uniform_filter1d(e, int(sr * 0.05)) + 1e-12                        # 50 ms energy
    broad = np.sqrt(uniform_filter1d(mono ** 2, int(sr * 0.03))) + 1e-9
    r = burst / around
    cand = np.nonzero(r > 20)[0]
    if not len(cand): return path, 0
    groups, a0, prev = [], cand[0], cand[0]
    for i in cand[1:]:
        if i - prev > sr * 0.001: groups.append((a0, prev)); a0 = i
        prev = i
    groups.append((a0, prev))
    keep = []
    for gi, (a, b) in enumerate(groups):
        if (b - a) / sr * 1000 > max_ms: continue
        near = [g for g in groups if g is not groups[gi] and abs(g[0] - a) < sr * 0.04]
        if near: continue
        ctx = np.concatenate([mono[max(0, a - int(sr * 0.03)): max(0, a - int(sr * 0.003))], mono[b + int(sr * 0.003): b + int(sr * 0.03)]])
        quiet = 20 * np.log10(np.sqrt((ctx ** 2).mean()) + 1e-9) < -50 if len(ctx) else False
        if quiet: keep.append((a, b))          # pauses only: never touch speech
    y = x.copy(); pad = int(sr * 0.0015)
    for a, b in keep:
        a1, b1 = max(1, a - pad), min(len(y) - 2, b + pad)
        w = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, b1 - a1 + 1)))[:, None]
        y[a1:b1 + 1] = y[a1 - 1] * (1 - w) + y[b1 + 1] * w
    out = out or path.replace(".wav", ".declick.wav")
    sf.write(out, y, sr, subtype="PCM_24")
    return out, len(keep)


# ---------------------------------------------------------------------- fit music to a length
def fit_music(path, length, ending=8.0, xf=0.35):
    """The track cut to exactly `length` s so it ENDS on its real ending (not a fade in the middle): keep the start,
    jump to the last `ending` s at a beat, crossfade there. Both cut points sit on downbeats, so it stays in time."""
    from . import analyze
    p = music_path(path)
    k = cache.key("fit2", p, round(length, 2), ending, xf)
    out = cache.path("audio", "fit_" + k, "wav")
    if os.path.exists(out): return out
    D = duration(p) - silent_tail(p)
    if length >= D - 0.05:
        ff(["-i", p, "-t", f"{length:.3f}", "-ar", str(SR), "-ac", "2", cache.tmp(out)], label="fit"); return cache.commit(out)
    b = analyze.beats(p); db = b["downbeats"] or b["beats"]
    e0 = min((t for t in db if t >= D - ending - 2), key=lambda t: abs(t - (D - ending)), default=D - ending)
    tail = D - e0
    c = min((t for t in db if t <= length - tail + 1), key=lambda t: abs(t - (length - tail)), default=length - tail)
    head = max(1.0, c)
    total = head + tail - xf
    # small mismatch: absorb it in the head so the file is exactly `length`
    head += length - total
    ff(["-i", p, "-i", p, "-filter_complex",
        f"[0:a]atrim=0:{head:.4f},asetpts=PTS-STARTPTS[a];[1:a]atrim={e0:.4f}:{D:.4f},asetpts=PTS-STARTPTS[b];[a][b]acrossfade=d={xf}:c1=qsin:c2=qsin,atrim=0:{length:.4f}[o]",
        "-map", "[o]", "-ar", str(SR), "-ac", "2", cache.tmp(out)], label="fit")
    return cache.commit(out)
