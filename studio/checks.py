"""Built-in checks for any finished video (and helpers Claude uses to look at its own work).

check_all(video) runs:
  streams     colour tags (HLG BT.2020 10-bit), steady 30 fps, picture and sound the same length
  loudness    integrated LUFS and true peak against the target
  slips       re-transcribes the video: "cut", "action", "retake", repeated lines
  frozen      runs of identical frames (outside allowed stills) and black frames
  white       bright white stretches that should have been dimmed (mean luma over the HLG graphics white)
  facebox     stutter inside the face box: duplicated frames while the rest moves
  privacy     OCR of frames every 0.5 s: emails, IP addresses, phone numbers, keys, deny-listed names
  captions    burned captions vs what he said, and .srt cues never overlapping burned captions
  contrast, face, strips, cuts, reuse   (studio/review.py) caption contrast on the real pixels, no text on a face,
              frames around every cut, every word whole at every cut, no footage moment used twice in a Short
Each check returns ok + details; the report lists every problem with its time."""
import json, os, re, subprocess, tempfile
import numpy as np
from . import cache, words as W, ocr
from . import color as C
from .media import probe, log, ff, duration, RenderError


def _frames_small(video, fps=4, w=320, crop=None, gray=False):
    vf = (f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}," if crop else "") + f"fps={fps},scale={w}:-2:flags=area," + ("format=gray" if gray else "scale=in_color_matrix=bt2020:in_range=tv,format=rgb24")
    p = probe(video); v = next(s for s in p["streams"] if s["codec_type"] == "video")
    W_, H_ = int(v["width"]), int(v["height"])
    cw, ch = (crop[2], crop[3]) if crop else (W_, H_)
    h = int(round(ch * w / cw / 2)) * 2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", vf, "-f", "rawvideo", "-"], capture_output=True).stdout
    c = 1 if gray else 3
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, c) if c > 1 else np.frombuffer(raw, np.uint8).reshape(-1, h, w)


def streams(video):
    p = probe(video); v = next(s for s in p["streams"] if s["codec_type"] == "video")
    a = next((s for s in p["streams"] if s["codec_type"] == "audio"), None)
    probs = []
    if v.get("color_transfer") != "arib-std-b67": probs.append(f"transfer {v.get('color_transfer')} (want arib-std-b67/HLG)")
    if v.get("color_primaries") != "bt2020": probs.append(f"primaries {v.get('color_primaries')}")
    if v.get("color_space") != "bt2020nc": probs.append(f"matrix {v.get('color_space')}")
    if "10" not in v.get("pix_fmt", ""): probs.append(f"pix_fmt {v.get('pix_fmt')} (want 10-bit)")
    if v.get("avg_frame_rate") not in ("30/1",): probs.append(f"frame rate {v.get('avg_frame_rate')}")
    vd = float(v.get("duration", p["format"]["duration"])); ad = float(a.get("duration", 0)) if a else 0
    if a is None: probs.append("no sound")
    elif abs(vd - ad) > 0.1: probs.append(f"picture {vd:.2f}s vs sound {ad:.2f}s")
    return dict(ok=not probs, problems=probs, codec=v["codec_name"], size=f"{v['width']}x{v['height']}", duration=round(vd, 2))


def loudness(video, target=-14.4, tol=0.8, peak=-1.0):
    from .audio import loudness as L
    I, tp = L(video)
    probs = []
    if abs(I - target) > tol: probs.append(f"loudness {I:.1f} LUFS (target {target})")
    if tp > peak: probs.append(f"true peak {tp:.1f} dBTP (max {peak})")
    return dict(ok=not probs, problems=probs, lufs=I, true_peak=tp)


def slips(video):
    ws = W.transcribe(video)
    hits = [dict(t=round(t, 2), what=s) for t, s in W.slips(ws)]
    reps = [dict(t=round(b, 2), first=round(a, 2), what=g) for a, b, g in W.repeats(ws)]
    return dict(ok=not hits and not reps, problems=[f"{h['t']}s '{h['what']}'" for h in hits] + [f"{r['t']}s repeats '{r['what']}' from {r['first']}s" for r in reps],
                transcript=W.text(ws))


def frozen(video, allow=(), min_secs=1.5):
    """Runs of near-identical frames (4 fps) longer than min_secs outside `allow` [(t0, t1)]; black frames."""
    F = _frames_small(video, 4, 240, gray=True).astype(np.float32)
    d = np.abs(np.diff(F, axis=0)).mean(axis=(1, 2))
    probs, run_ = [], 0
    for i, v in enumerate(d):
        run_ = run_ + 1 if v < 0.15 else 0
        if run_ == int(min_secs * 4):
            t = (i - run_ + 1) / 4
            if not any(a - 0.3 <= t <= b for a, b in allow): probs.append(f"{t:.1f}s: picture frozen for {min_secs}s+")
    black = [i / 4 for i in range(len(F)) if F[i].mean() < 4]
    if black: probs.append(f"black frames at {', '.join(f'{t:.2f}s' for t in black[:8])}")
    return dict(ok=not probs, problems=probs)


def white(video, crop=None, limit=0.70):
    """Bright stretches: share of pixels above the graphics-white HLG level (screens should be dimmed)."""
    F = _frames_small(video, 2, 320, crop=crop, gray=True).astype(np.float32) / 255
    # Y' limited range: 0.75 HLG ~ 64+0.75*876 = 721/1023 -> 8 bit ~ 180
    thr = (64 + limit * 876) / 1023
    probs = []
    for i, f in enumerate(F):
        share = (f > thr).mean()
        if share > 0.35: probs.append(f"{i / 2:.1f}s: {share * 100:.0f}% of the picture is above HLG {limit:.2f} (bright white screen)")
    return dict(ok=not probs, problems=probs[:20])


def facebox(video, box, windows=()):
    """Duplicated frames inside the face box while he moves = stutter (VFR screen recordings caused this)."""
    F = _frames_small(video, 30, 160, crop=box, gray=True).astype(np.float32)
    d = np.abs(np.diff(F, axis=0)).mean(axis=(1, 2))
    probs = []
    for i in range(1, len(d) - 1):
        t = (i + 1) / 30
        if windows and not any(a <= t < b for a, b in windows): continue
        if d[i] < 0.05 and d[i - 1] > 0.6 and d[i + 1] > 0.6: probs.append(f"{t:.2f}s")
    return dict(ok=not probs, problems=[f"face box repeats a frame at {', '.join(probs[:15])}"] if probs else [], count=len(probs))


def privacy(video, deny=(), every=0.5):
    tmp = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"), prefix="priv_")
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={1 / every},scale=in_color_matrix=bt2020:in_range=tv,format=rgb24", f"{tmp}/%05d.png"], check=True)
        hits = ocr.scan_dir(tmp, deny)
    finally:
        subprocess.run(["rm", "-rf", tmp])
    probs = [f"{(int(f[:5]) - 1) * every:.1f}s {k}: {s!r}" for f, k, s, b in hits]
    return dict(ok=not probs, problems=probs[:40])


def srt_cues(path):
    txt = open(path).read()
    def ts(x): h, m, r = x.replace(",", ".").split(":"); return int(h) * 3600 + int(m) * 60 + float(r)
    return [(ts(a), ts(b), t.strip()) for a, b, t in re.findall(r"(\S+) --> (\S+)\n(.*?)(?:\n\n|\Z)", txt, re.S)]


def captions(timeline=None, srt=None, video=None):
    """.srt cues must not overlap burned-caption stretches (no double captions); burned captions must match what is
    heard in the finished video (word match >= 90 %)."""
    probs = []
    if timeline and video:
        from . import model as M
        import difflib
        R = M.resolve(timeline); heard = W.transcribe(video)
        for s in R["scenes"]:
            for l in s["layers"]:
                if l["kind"] != "captions": continue
                a, b = (s["start"] + l["f0"]) / 30, (s["start"] + l["f1"]) / 30
                shown = " ".join(l.get("phrases") or [w[2] for w in s["words"] if l["f0"] / 30 <= w[0] < l["f1"] / 30])
                said = " ".join(w[2] for w in heard if a - 0.2 <= w[0] < b)
                r = difflib.SequenceMatcher(None, W.norm(shown).split(), W.norm(said).split()).ratio()
                if r < 0.9: probs.append(f"burned captions {a:.1f}-{b:.1f}s match the voice only {r * 100:.0f}%: shown '{shown[:60]}' heard '{said[:60]}'")
    if timeline and srt:
        from . import model as M
        R = M.resolve(timeline)
        burned = [((s["start"] + l["f0"]) / 30, (s["start"] + l["f1"]) / 30) for s in R["scenes"] for l in s["layers"] if l["kind"] == "captions"]
        for a, b, t in srt_cues(srt):
            for x, y in burned:
                if a < y and b > x: probs.append(f".srt cue {a:.2f}-{b:.2f} '{t[:40]}' overlaps burned captions {x:.2f}-{y:.2f}")
    return dict(ok=not probs, problems=probs)


def _env(path, a=None, d=None, hop=0.02):
    """Loudness envelope (dB per 20 ms) of a file or a stretch of it."""
    import subprocess
    args = ["ffmpeg", "-v", "error"] + (["-ss", f"{a:.3f}"] if a is not None else []) + (["-t", f"{d:.3f}"] if d else []) + \
           ["-i", path, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"]
    x = np.frombuffer(subprocess.run(args, capture_output=True).stdout, np.int16).astype(np.float32) / 32768
    h = int(8000 * hop); x = x[: len(x) // h * h].reshape(-1, h)
    return 20 * np.log10(np.sqrt((x ** 2).mean(1)) + 1e-9)


def dropouts(video, R, hop=0.02, min_len=0.06):
    """Voice dropouts: moments where he is talking in the raw recording but the finished video is (nearly) silent.
    Compares the finished audio with the source voice through every kept piece (what the viewer should hear)."""
    out_env = _env(video, hop=hop)
    probs, worst = [], []
    for s in R["scenes"]:
        if not s["pieces"]: continue
        t0 = s["start"] / 30
        for p in s["pieces"]:
            if p["hold"] or p["n"] < 6: continue
            a, d = p["a"], p["n"] / 30
            src = _env(s["src"], a, d, hop)
            i0 = int(round((t0 + p["f0"] / 30) / hop))
            seg = out_env[i0: i0 + len(src)]
            n = min(len(src), len(seg))
            if n < 4: continue
            src, seg = src[:n], seg[:n]
            ref = np.percentile(src, 90)
            talking = (src > ref - 18) & (src > -38)        # his voice in the source (not quiet clicks / keyboard)
            dead = seg < max(-50, np.percentile(seg, 90) - 30)    # the output went (nearly) silent
            bad = talking & dead
            bad[:3] = False; bad[-3:] = False              # piece edges have 4 ms fades by design
            run_, start = 0, None
            for k, v in enumerate(bad):
                if v:
                    run_ += 1; start = k if start is None else start
                else:
                    if run_ * hop >= min_len: probs.append((round((i0 + start) * hop, 2), round(run_ * hop, 2), s["id"]))
                    run_, start = 0, None
            if run_ * hop >= min_len: probs.append((round((i0 + start) * hop, 2), round(run_ * hop, 2), s["id"]))
    return dict(ok=not probs, problems=[f"voice drops out at {t:.2f}s for {d:.2f}s (scene {sid})" for t, d, sid in probs[:30]], count=len(probs))


def dead_air(video, min_len=0.06, edge=0.5):
    """Digital silence inside the video (room sound vanishing): listeners hear it as the audio cutting out."""
    e = _env(video); dead = e < -86; probs = []; k = 0          # true digital silence sits far below any room tone
    n = len(e)
    for i, v in enumerate(list(dead) + [False]):
        if v: k += 1
        else:
            t = (i - k) * 0.02
            if k * 0.02 >= min_len and t > edge and i * 0.02 < n * 0.02 - edge: probs.append(f"dead air at {t:.2f}s for {k * 0.02:.2f}s")
            k = 0
    return dict(ok=not probs, problems=probs[:30], count=len(probs))


def header_band(video, band=270, every=1.0, allow=()):
    """Shorts (9:16): Instagram/TikTok/YouTube lay their labels over the top ~270 px of a 1920-tall frame, so no text of
    ours may sit there (the badge sits just below it). Reports text found in the band, except `allow`ed words."""
    w, h = (int(v) for v in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                                             "-of", "csv=p=0", video], capture_output=True, text=True).stdout.strip().split(",")[:2])
    if h < w * 1.5: return dict(ok=True, problems=[], note="not a vertical video")
    bh = int(band * h / 1920) // 2 * 2
    tmp = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"), prefix="hdr_")
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={1 / every},crop={w}:{bh}:0:0,scale=in_color_matrix=bt2020:in_range=tv,format=rgb24",
                        f"{tmp}/%05d.png"], check=True)
        probs = []
        r = subprocess.run([ocr.ensure_bin(), "ocrdir", tmp], capture_output=True, text=True, check=True)
        for line in r.stdout.splitlines():
            try: o = json.loads(line)
            except ValueError: continue
            f = os.path.basename(o["file"])
            for x, y, w_, h_, txt, c in o.get("lines", []):
                if txt.strip() and c > 0.4 and not any(a.lower() in txt.lower() for a in allow):
                    probs.append(f"{(int(f[:5]) - 1) * every:.1f}s text in the app header band: {txt!r}")
        probs.sort(key=lambda p_: float(p_.split("s ")[0]))
    finally:
        subprocess.run(["rm", "-rf", tmp])
    return dict(ok=not probs, problems=probs[:30])


def check_all(video, timeline=None, srt=None, deny=()):
    rep = {}
    try:
        from .config import profile as _prof
        deny = tuple(deny) + tuple(_prof().get("privacy_deny", []))     # the creator's folder/project names, accounts
    except Exception: pass
    rep["streams"] = streams(video)
    rep["loudness"] = loudness(video, timeline.get("audio", {}).get("loudness", -14.4) if timeline else -14.4)
    rep["slips"] = slips(video)
    allow = []
    if timeline:
        from . import model as M
        R = M.resolve(timeline)
        for s in R["scenes"]:
            for b in s["base"]:
                if b.get("freeze") or b["kind"] in ("graphic", "still"): allow.append(((s["start"] + b["f0"]) / 30, (s["start"] + b["f1"]) / 30))
            for p in s["pieces"]:   # holds and tails freeze his face on purpose (voice off: no moving lips)
                if p["hold"]: allow.append(((s["start"] + p["f0"]) / 30, (s["start"] + p["f0"] + p["n"]) / 30))
                elif p.get("tail"): allow.append(((s["start"] + p["f0"] + p["n"] - p["tail"]) / 30, (s["start"] + p["f0"] + p["n"]) / 30))
    rep["frozen"] = frozen(video, allow)
    if timeline:   # face box smoothness inside every face-box window
        from . import assets as A
        wins, box = [], None
        for s in R["scenes"]:
            if not s["pieces"]: continue
            for b in s["base"]:
                if b["kind"] in ("camera", "stack") or b.get("pip", s["raw"].get("pip", "none")) == "none": continue
                fb = A.facebox(R, s, timeline); x, y = fb["pos"][b.get("pip", s["raw"].get("pip", "none"))]
                box = [x, y, *fb["size"]]; wins.append(((s["start"] + b["f0"]) / 30, (s["start"] + b["f1"]) / 30))
        if box: rep["facebox"] = facebox(video, box, wins)
    rep["dead_air"] = dead_air(video)
    if timeline: rep["dropouts"] = dropouts(video, R)
    rep["white"] = white(video)
    rep["privacy"] = privacy(video, deny)
    rep["header_band"] = header_band(video)
    rep["captions"] = captions(timeline, srt, video)
    from . import review as RV
    rep["contrast"] = RV.contrast(video, R if timeline else None)
    rep["face"] = RV.face(video)
    if timeline:
        rep["strips"] = RV.strips(video, R)
        rep["cuts"] = RV.cuts(video, R)
        if R["profile"]["h"] > R["profile"]["w"]: rep["reuse"] = RV.reuse(R, timeline)
    rep["ok"] = all(v["ok"] for v in rep.values() if isinstance(v, dict))
    rep["summary"] = [f"{k}: {p}" for k, v in rep.items() if isinstance(v, dict) for p in v.get("problems", [])]
    return rep


def contact_sheet(video, timeline=None, every=2.0, out=None, cols=6, w=640):
    """Frames every `every` s as a viewer sees them (HLG -> sRGB), with time stamps, tiled into one JPEG."""
    from PIL import Image, ImageDraw, ImageFont
    from . import frames as Fr
    if video is None:
        from .render import render
        raise RenderError("contact_sheet needs a rendered video (use 'frame' for single frames before rendering)")
    D = duration(video)
    ts = list(np.arange(0, D - 0.05, every))
    tiles = []
    for t in ts:
        f = Fr.read_rgb(video, float(t))[0]
        p = C.hlg_to_srgb(np.clip(f[::6, ::6].astype(np.float64), 0, 1))
        im = Image.fromarray((np.clip(p, 0, 1) * 255).astype(np.uint8)).resize((w, int(w * f.shape[0] / f.shape[1])))
        ImageDraw.Draw(im).text((10, 8), f"{t:6.1f}s", fill=(255, 255, 0), font=ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 24))
        tiles.append(im)
    rows = -(-len(tiles) // cols); th = tiles[0].height
    sheet = Image.new("RGB", (cols * w, rows * th))
    for i, im in enumerate(tiles): sheet.paste(im, ((i % cols) * w, (i // cols) * th))
    out = out or os.path.splitext(video)[0] + "-sheet.jpg"
    sheet.save(out, quality=85); return out


def gfx_preview(template, props, secs=3.0, tall=False, out=None):
    """Render one template alone (cached like any graphic) and return a sheet of 6 frames."""
    from . import assets as A, gfx
    R = dict(profile=dict(w=1080 if tall else 3840, h=1920 if tall else 2160), kit=props.pop("_kit_override", {}))
    p = A.graphic(template, props, int(secs * 30), R, alpha=False)
    if A.PENDING: gfx.render_jobs(dict(A.PENDING)); A.PENDING.clear()
    return contact_sheet(p, every=secs / 6, out=out, cols=3, w=640)
