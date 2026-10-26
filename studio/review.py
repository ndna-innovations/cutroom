"""Checks that look at a finished video the way a viewer would, and the cut review page (2026-10-26; ideas from Nate
Herk's MIT edit kit, written fresh for Cutroom).
  contrast   real pixels behind every burned caption: text vs its backing >= 4.5 : 1 (WCAG); a caption on screen that
             OCR can't read at all is flagged too (white on white reads as nothing)
  face       none of our text on a face, mouth or chin: every frame of a Short's first 2.5 s, then every 0.5 s
  strips     10 frames each side of every cut: one-frame flashes and black frames; a sheet Claude looks at
  cuts       every word whole at every voice cut: the source is not still sounding at a cut edge, and the words either
             side of the cut are heard in the final
  reuse      no footage moment used twice (Shorts)
cutreview(timeline, video) writes one self-contained HTML page: a kept/cut bar and every cut with what was removed and
the raw vs edited sound around it, small enough to publish as a review page."""
import base64, difflib, html, json, os, subprocess, tempfile
import numpy as np
from . import words as W, ocr, color as C
from .media import probe

FPS = 30
FILLERS = {"um", "uh", "er", "erm", "ah", "hmm", "mm"}


# --------------------------------------------------------------------------- frames
def _info(video):
    p = probe(video); v = next(s for s in p["streams"] if s["codec_type"] == "video")
    return int(v["width"]), int(v["height"]), v.get("color_transfer") == "arib-std-b67", v.get("color_space", "bt709")


def _dump(video, out_dir, fps=None, t=None, d=None, w=None):
    """PNG frames (code values, full range) into out_dir; returns the files in order."""
    W_, H_, hlg, cs = _info(video)
    vf = [f"fps={fps}"] if fps else []
    if w: vf.append(f"scale={w}:-2:flags=area")
    vf.append(f"scale=in_color_matrix={'bt2020' if cs.startswith('bt2020') else 'bt709'}:in_range=tv,format=rgb24")
    a = (["-ss", f"{t:.3f}"] if t is not None else []) + (["-t", f"{d:.3f}"] if d else [])
    subprocess.run(["ffmpeg", "-v", "error", *a, "-i", video, "-vf", ",".join(vf), f"{out_dir}/%05d.png"], check=True)
    return sorted(os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith(".png"))


def _display(img, hlg):
    """uint8 RGB code values -> display sRGB 0..1 (what a viewer sees)."""
    x = img.astype(np.float64) / 255
    return np.clip(C.hlg_to_srgb(x.reshape(-1, 3)).reshape(x.shape), 0, 1) if hlg else x


def _ocr(files):
    """{file: [[x, y, w, h, text, conf], ...]} in pixels, one Vision run per folder."""
    out = {}
    for d in sorted({os.path.dirname(f) for f in files}):
        r = subprocess.run([ocr.ensure_bin(), "ocrdir", d], capture_output=True, text=True, check=True)
        for line in r.stdout.splitlines():
            try: o = json.loads(line)
            except ValueError: continue
            out[os.path.join(d, os.path.basename(o["file"]))] = o.get("lines", [])
    return out


def _samples(video, tmp, every=0.5, first=2.5):
    """[(t, file)]: every frame of the first `first` s of a vertical video, then one every `every` s."""
    W_, H_, _, _ = _info(video)
    out = []
    if first and H_ > W_ * 1.5:
        d0 = os.path.join(tmp, "first"); os.makedirs(d0)
        out += [(i / FPS, f) for i, f in enumerate(_dump(video, d0, d=first))]
    d1 = os.path.join(tmp, "every"); os.makedirs(d1)
    out += [(i * every, f) for i, f in enumerate(_dump(video, d1, fps=1 / every)) if i * every >= (first if out else 0)]
    return out


# --------------------------------------------------------------------------- contrast
def _lum(rgb):
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return c @ np.array([0.2126, 0.7152, 0.0722])


def text_contrast(img, box):
    """WCAG contrast ratio between the text and what is behind it inside one OCR box (img: display sRGB 0..1).
    Two-level split of the box's luminance (Otsu); the smaller class is the letters."""
    x, y, w, h = (int(round(v)) for v in box[:4])
    L = _lum(img[max(0, y): y + h, max(0, x): x + w]).ravel()
    if L.size < 50: return None
    hist, edges = np.histogram(L, 64, (0, 1)); p = hist / hist.sum(); mids = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(p); m = np.cumsum(p * mids); mt = m[-1]
    var = np.where((w0 > 0) & (w0 < 1), (mt * w0 - m) ** 2 / np.maximum(w0 * (1 - w0), 1e-9), 0)
    thr = mids[int(np.argmax(var))]
    a, b = L[L <= thr], L[L > thr]
    if min(len(a), len(b)) < 10: return 1.0          # one flat level: no readable text
    text, back = (a, b) if len(a) < len(b) else (b, a)
    hi, lo = sorted((float(np.median(text)), float(np.median(back))), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _again(video, t, line, hlg, tmp):
    """Contrast of the same text a moment later (0 if it is gone)."""
    from PIL import Image
    d = tempfile.mkdtemp(dir=tmp); fs = _dump(video, d, t=t, d=0.04)
    if not fs: return 0.0
    L = [l for l in _ocr(fs[:1]).get(fs[0], []) if difflib.SequenceMatcher(None, W.norm(l[4]), W.norm(line[4])).ratio() > 0.6]
    img = _display(np.asarray(Image.open(fs[0]).convert("RGB")), hlg)
    return max([text_contrast(img, l) or 0.0 for l in L], default=0.0)


def _caption_windows(R):
    """[(t0, t1, {words})] for every burned-caption layer, in video seconds."""
    out = []
    for s in R["scenes"]:
        for l in s["layers"]:
            if l["kind"] != "captions": continue
            a, b = (s["start"] + l["f0"]) / FPS, (s["start"] + l["f1"]) / FPS
            ws = [(s["start"] / FPS + w[0], W.norm(w[2])) for w in s["words"] if l["f0"] / FPS <= w[0] < l["f1"] / FPS]
            out.append((a, b, ws))
    for o in R.get("overlays", []):             # Shorts: one timeline-wide captions layer with its own words
        if o["kind"] != "captions" or not o.get("words"): continue
        out.append((o["f0"] / FPS, o["f1"] / FPS, [(w[0], W.norm(w[2])) for w in o["words"]]))
    return out


def contrast(video, R=None, minimum=4.5, every=0.5):
    """Burned captions measured on the rendered frames. With a timeline: OCR lines that carry the caption words said
    around that moment; a caption window with words but no readable line is a problem. Without caption layers (no
    timeline, or captions baked into a picture layer): lines in the caption band (Shorts 60-80 % of the height, long
    videos 74-92 %) that carry words heard there, so screen text and logos don't count. A low reading is measured again
    0.3 s before and after (a phrase change cross-fades for ~0.2 s) and only counts if it stays low."""
    W_, H_, hlg, _ = _info(video)
    wins = (_caption_windows(R) or None) if R else None
    band = (0.60, 0.80) if H_ > W_ else (0.74, 0.92)
    heard = [(w[0], W.norm(w[2])) for w in W.transcribe(video)] if wins is None else None
    tmp = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"), prefix="contrast_")
    probs, worst = [], []
    try:
        S = _samples(video, tmp, every, first=0)
        found = _ocr([f for _, f in S])
        from PIL import Image
        for t, f in S:
            lines = [l for l in found.get(f, []) if l[4].strip() and l[5] > 0.3]
            if wins is not None:
                win = next((w for w in wins if w[0] <= t < w[1]), None)
                if not win: continue
                near = {x for tt, x in win[2] if abs(tt - t) < 1.2 and x not in FILLERS}
                if not near: continue
                lines = [l for l in lines if set(W.norm(l[4]).split()) & near]
                if not lines: probs.append(f"{t:.1f}s: caption on screen but no readable line found (too low contrast or covered)"); continue
            else:
                near = {x for tt, x in heard if abs(tt - t) < 1.5 and x not in FILLERS and len(x) > 2}
                def spoken(l):
                    ws_ = [x for x in W.norm(l[4]).split() if len(x) > 2]
                    return ws_ and sum(x in near for x in ws_) >= 0.6 * len(ws_)
                lines = [l for l in lines if band[0] * H_ <= l[1] + l[3] / 2 <= band[1] * H_ and spoken(l)]
            if not lines: continue
            img = _display(np.asarray(Image.open(f).convert("RGB")), hlg)
            for l in lines:
                r = text_contrast(img, l)
                if r is None: continue
                if r < minimum: r = max(r, _again(video, t + 0.3, l, hlg, tmp), _again(video, max(0.0, t - 0.3), l, hlg, tmp))
                worst.append(r)
                if r < minimum: probs.append(f"{t:.1f}s: '{l[4][:30]}' contrast {r:.1f}:1 (min {minimum}:1)")
    finally:
        subprocess.run(["rm", "-rf", tmp])
    return dict(ok=not probs, problems=probs[:30], lowest=round(min(worst), 2) if worst else None)


# --------------------------------------------------------------------------- face
_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
         172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
_BROWS = [70, 63, 105, 66, 107, 300, 293, 334, 296, 336]


def face_boxes(img, det):
    """[x, y, w, h] per face (eyebrows to chin, cheek to cheek) in img pixels, from MediaPipe landmarks."""
    import mediapipe as mp
    r = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img)))
    out = []
    for lm in r.face_landmarks or []:
        P = np.array([[q.x * img.shape[1], q.y * img.shape[0]] for q in lm])
        xs, ys = P[_OVAL, 0], P[_OVAL, 1]
        top = P[_BROWS, 1].min()
        out.append([float(xs.min()), float(top), float(xs.max() - xs.min()), float(ys.max() - top)])
    return out


def overlaps(face, line, share=0.08):
    """True when a text line covers at least `share` of its own area on the face box."""
    fx, fy, fw, fh = face; x, y, w, h = line[:4]
    ix = max(0.0, min(fx + fw, x + w) - max(fx, x)); iy = max(0.0, min(fy + fh, y + h) - max(fy, y))
    return w * h > 0 and ix * iy >= share * w * h


def face(video, every=0.5, first=2.5):
    """Our text on a face. A vertical video's first `first` s are read frame by frame (viewers judge the speaker there)."""
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    from PIL import Image
    model = os.path.expanduser("~/models/studio/face_landmarker.task")
    det = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=model), num_faces=2))
    tmp = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"), prefix="face_")
    probs, seen = [], 0
    try:
        S = _samples(video, tmp, every, first)
        found = _ocr([f for _, f in S])
        for t, f in S:
            lines = [l for l in found.get(f, []) if l[4].strip() and l[5] > 0.3]
            if not lines: continue
            img = np.asarray(Image.open(f).convert("RGB"))
            for fb in face_boxes(img, det):
                seen += 1
                hit = [l[4] for l in lines if overlaps(fb, l)]
                if hit: probs.append(f"{t:.2f}s: text on the face: {', '.join(repr(h[:24]) for h in hit[:3])}")
    finally:
        det.close(); subprocess.run(["rm", "-rf", tmp])
    return dict(ok=not probs, problems=probs[:30], faces_seen=seen)


# --------------------------------------------------------------------------- cut points + strips
def _src_end(p):
    return p["a"] + (p["n"] - p.get("tail", 0)) / FPS


def cut_points(R):
    """Every cut in the finished video: kind 'voice' (his speech jumps in the source: end -> resume), 'scene', 'shot'."""
    out = []
    for s in R["scenes"]:
        t0 = s["start"]
        if t0 > 0: out.append(dict(t=t0 / FPS, kind="scene", scene=s["id"]))
        ps = s["pieces"]
        for p, q in zip(ps, ps[1:]):
            if p["hold"] or q["hold"] or abs(_src_end(p) - q["a"]) > 1.5 / FPS:
                out.append(dict(t=(t0 + q["f0"]) / FPS, kind="voice", scene=s["id"], src=s["src"], end=_src_end(p), resume=q["a"],
                                hold=p["hold"] or q["hold"]))
        for b in s["base"][1:]: out.append(dict(t=(t0 + b["f0"]) / FPS, kind="shot", scene=s["id"]))
    out.sort(key=lambda c: (c["t"], c["kind"] != "voice"))
    ded = []
    for c in out:
        if ded and abs(c["t"] - ded[-1]["t"]) < 1.5 / FPS: continue
        ded.append(c)
    return ded


def _clip(video, t, n, w):
    W_, H_, hlg, cs = _info(video)
    h = int(round(H_ * w / W_ / 2)) * 2
    vf = f"scale={w}:{h}:flags=area,scale=in_color_matrix={'bt2020' if cs.startswith('bt2020') else 'bt709'}:in_range=tv,format=rgb24"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t - 0.4 / FPS):.4f}", "-i", video, "-vf", vf, "-frames:v", str(n), "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3), hlg


def flashes(frames, cut_index):
    """Indices of one-frame pops (different from both neighbours that match each other) and black frames.
    The change at the cut itself (cut_index - 1 -> cut_index) is expected."""
    g = frames.astype(np.float32).mean(-1)
    d = lambda i, j: float(np.abs(g[i] - g[j]).mean())
    steps = [d(i, i + 1) for i in range(len(g) - 1)]
    T = max(10.0, 3 * float(np.median(steps)) if steps else 10.0)
    bad = []
    for i in range(1, len(g) - 1):
        if d(i - 1, i) > T and d(i, i + 1) > T and d(i - 1, i + 1) < T / 2: bad.append(i)
    bad += [i for i in range(len(g)) if g[i].mean() < 4 and i not in bad]
    return sorted(bad)


def strips(video, R, out=None, side=10, w=160, rows_per_sheet=40):
    """A row of 2 x `side` frames around every cut, tiled into JPEG sheets (the cut frame outlined in amber, problems
    in red), plus the one-frame flashes and black frames found."""
    from PIL import Image, ImageDraw
    cuts = cut_points(R)
    out = out or os.path.splitext(video)[0] + "-cuts"
    rows, probs = [], []
    for c in cuts:
        F, hlg = _clip(video, c["t"] - side / FPS, 2 * side, w)
        if len(F) < 3: continue
        bad = flashes(F, side)
        for i in bad: probs.append(f"{c['t'] + (i - side) / FPS:.2f}s: one-frame flash or black frame near the {c['kind']} cut at {c['t']:.2f}s")
        disp = (_display(F, hlg) * 255).astype(np.uint8) if hlg else F
        rows.append((c, disp, bad))
    sheets = []
    for k in range(0, len(rows), rows_per_sheet):
        part = rows[k: k + rows_per_sheet]
        th = part[0][1].shape[1]; lab = 120
        sheet = Image.new("RGB", (lab + 2 * side * (w + 2), len(part) * (th + 4)), (18, 19, 24)); dr = ImageDraw.Draw(sheet)
        for r, (c, disp, bad) in enumerate(part):
            y = r * (th + 4)
            dr.text((6, y + 4), f"{c['t']:.2f}s\n{c['kind']}", fill=(255, 197, 61))
            for i, fr in enumerate(disp):
                x = lab + i * (w + 2)
                sheet.paste(Image.fromarray(fr), (x, y))
                if i == side: dr.rectangle([x - 1, y, x + w, y + th - 1], outline=(255, 197, 61), width=2)
                if i in bad: dr.rectangle([x, y, x + w - 1, y + th - 1], outline=(255, 90, 95), width=3)
        p = f"{out}-{k // rows_per_sheet + 1}.jpg"; sheet.save(p, quality=82); sheets.append(p)
    return dict(ok=not probs, problems=probs[:30], cuts=len(cuts), sheets=sheets)


# --------------------------------------------------------------------------- every word whole
_NUM = dict(zip("0 1 2 3 4 5 6 7 8 9 10 11 12".split(), "zero one two three four five six seven eight nine ten eleven twelve".split()))


def _wn(s):
    n = W.norm(s).replace("-", "").replace("'", "").strip(".")
    return _NUM.get(n, n)


def missing_words(expected, heard, ratio=0.75):
    """Expected words (fillers and one-letter words skipped) that no heard word matches closely. Numbers match their
    words ("1" = "one"); hyphens and apostrophes are ignored; a heard pair may form one expected word ("read only")."""
    H = [_wn(h) for h in heard]
    H += [a + b for a, b in zip(H, H[1:])]
    miss = []
    for e in expected:
        n = _wn(e)
        if len(n) < 2 or n in FILLERS: continue
        if not any(h == n or difflib.SequenceMatcher(None, h, n).ratio() >= ratio for h in H): miss.append(e)
    return miss


def _sounding(src, t, ref, hop=0.02):
    """True when the source is still carrying his voice right at t (a cut there clips the word)."""
    from .checks import _env
    e = _env(src, max(0.0, t - 0.03), 0.06, hop)
    return len(e) > 0 and float(e.max()) > ref - 14


def cuts(video, R, heard=None, edge_words=2, listen=2.5):
    """Every voice cut: (1) the source is quiet at both edges (no word cut in half); (2) the source words just before and
    just after the cut are heard in the final video. A transcript can guess a clipped word right, so (1) is the strict one."""
    from .checks import _env
    heard = heard if heard is not None else W.transcribe(video)
    probs, n = [], 0
    src_words, refs = {}, {}
    for c in cut_points(R):
        if c["kind"] != "voice" or c.get("hold"): continue
        n += 1
        src = c["src"]
        if src not in src_words: src_words[src] = W.transcribe(src)
        if src not in refs:
            e = _env(src); refs[src] = float(np.percentile(e, 90))
        ws = src_words[src]
        for edge, t in (("end", c["end"]), ("start", c["resume"])):
            if _sounding(src, t, refs[src]):
                w = next((x for x in ws if x[0] - 0.05 <= t <= x[1] + 0.05), None)
                probs.append(f"{c['t']:.2f}s: cut {edge}s while he is still speaking" + (f" ('{w[2]}', source {t:.2f}s)" if w else f" (source {t:.2f}s)"))
        before = [x[2] for x in ws if c["end"] - 1.5 <= x[1] <= c["end"] + 0.05][-edge_words:]
        after = [x[2] for x in ws if c["resume"] - 0.05 <= x[0] <= c["resume"] + 1.5][:edge_words]
        exp = before + after
        got = [x[2] for x in heard if c["t"] - listen <= x[0] <= c["t"] + listen]
        miss = missing_words(exp, got)
        if miss: probs.append(f"{c['t']:.2f}s: not heard around the cut: {', '.join(repr(m) for m in miss[:4])}")
    return dict(ok=not probs, problems=probs[:40], voice_cuts=n)


# --------------------------------------------------------------------------- reuse
def reuse(R, tl, min_overlap=0.3):
    """Footage moments that appear twice: camera pieces, screen / b-roll / slow-motion shots and video layers whose
    source ranges overlap by `min_overlap` s or more at two different places in the video."""
    from . import model as M
    def path(k): return k if (os.sep in str(k) or str(k).endswith((".mov", ".mp4", ".m4v"))) else M.src_path(tl, k)
    spans = []
    for s in R["scenes"]:
        t0 = s["start"] / FPS
        for p in s["pieces"]:
            if not p["hold"]: spans.append((path(s["src"]), p["a"], _src_end(p), t0 + p["f0"] / FPS, "camera"))
        for b in s["base"]:
            if b["kind"] in ("screen", "broll", "slowmo") and b.get("source") and not b.get("freeze"):
                d = (b["f1"] - b["f0"]) / FPS; a = b.get("from", 0.0)
                e = b["to"] if b.get("to") is not None else a + d * b.get("speed", 1.0)
                spans.append((path(b["source"]), a, e, t0 + b["f0"] / FPS, b["kind"]))
        for l in s["layers"]:
            if l["kind"] == "video" and l.get("source"):
                a = l.get("from", 0.0); spans.append((path(l["source"]), a, a + (l["f1"] - l["f0"]) / FPS * l.get("speed", 1.0), t0 + l["f0"] / FPS, "video"))
    probs = []
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            A, B = spans[i], spans[j]
            if A[0] != B[0] or abs(A[3] - B[3]) < 0.05: continue
            ov = min(A[2], B[2]) - max(A[1], B[1])
            if ov >= min_overlap:
                probs.append(f"{A[4]} at {A[3]:.2f}s and {B[4]} at {B[3]:.2f}s show the same {ov:.1f}s of {os.path.basename(A[0])} (source {max(A[1], B[1]):.2f}s)")
    return dict(ok=not probs, problems=probs[:30])


# --------------------------------------------------------------------------- cut review page
def _audio_uri(path, t, d, kbps=40):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-t", f"{d:.3f}", "-i", path, "-vn", "-ac", "1", "-ar", "24000",
                          "-b:a", f"{kbps}k", "-f", "mp3", "-"], capture_output=True).stdout
    return "data:audio/mpeg;base64," + base64.b64encode(raw).decode()


def cut_list(R):
    """Every voice cut with what was removed: [{t, src, end, resume, removed_s, words, kind}]."""
    out, cache_ = [], {}
    for c in cut_points(R):
        if c["kind"] != "voice" or c.get("hold"): continue
        if c["src"] not in cache_: cache_[c["src"]] = W.transcribe(c["src"])
        ws = cache_[c["src"]]
        gone = [x[2] for x in ws if c["end"] - 0.02 <= (x[0] + x[1]) / 2 <= c["resume"] + 0.02] if c["resume"] > c["end"] else []
        kind = ("pause" if not gone else "filler" if all(W.norm(g) in FILLERS for g in gone) else
                "jump back (retake)" if c["resume"] < c["end"] else "words")
        out.append(dict(t=round(c["t"], 2), src=c["src"], end=round(c["end"], 2), resume=round(c["resume"], 2),
                        removed_s=round(c["resume"] - c["end"], 2), words=" ".join(gone), kind=kind))
    return out


def cutreview(tl, video, out=None, title=None, pad=1.5, max_raw=8.0, R=None):
    """One HTML page for approving word cuts: summary, a kept/cut bar per source, and every cut with the removed words,
    the raw sound (with the removed part) and the edited sound around the join. Audio only, so it stays small."""
    from . import model as M
    R = R or M.resolve(tl)
    L = cut_list(R)
    srcs = {}
    for s in R["scenes"]:
        for p in s["pieces"]:
            if not p["hold"]: srcs.setdefault(s["src"], []).append((p["a"], _src_end(p)))
    bars = []
    for src, kept in srcs.items():
        lo, hi = min(a for a, _ in kept), max(b for _, b in kept); span = max(hi - lo, 1e-3)
        segs = "".join(f'<i style="left:{(a - lo) / span * 100:.3f}%;width:{max((b - a) / span * 100, 0.08):.3f}%"></i>' for a, b in kept)
        bars.append(f'<div class="src"><span>{html.escape(os.path.basename(src))} · {lo:.1f}–{hi:.1f}s</span><div class="bar">{segs}</div></div>')
    rows = []
    for i, c in enumerate(L, 1):
        a = c["end"] - pad; d = min(c["resume"] + pad, c["end"] + max_raw) - a
        raw = _audio_uri(c["src"], a, max(d, 2 * pad)); ed = _audio_uri(video, c["t"] - pad, 2 * pad)
        what = html.escape(c["words"]) if c["words"] else "<em>silence</em>"
        rows.append(f'<tr id="c{i}"><td class="n">{i}</td><td class="t">{c["t"]:.2f}s</td><td><span class="k k-{c["kind"].split()[0]}">{c["kind"]}</span></td>'
                    f'<td class="w">{what}<small>{c["removed_s"]:+.2f}s of source</small></td>'
                    f'<td><audio controls preload="none" src="{raw}"></audio></td><td><audio controls preload="none" src="{ed}"></audio></td></tr>')
    kinds = {}
    for c in L: kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    removed = sum(max(0, c["removed_s"]) for c in L)
    title = title or tl.get("name", "Cuts")
    page = _PAGE.format(title=html.escape(f"{title} cuts"), name=html.escape(title), n=len(L), removed=f"{removed:.1f}",
                        kinds=" · ".join(f"{v} {k}" for k, v in sorted(kinds.items(), key=lambda x: -x[1])) or "no cuts",
                        bars="".join(bars), rows="".join(rows) or '<tr><td colspan="6">No voice cuts.</td></tr>')
    out = out or os.path.splitext(video)[0] + "-cuts.html"
    open(out, "w").write(page)
    return out


_PAGE = """<title>{title}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@800&family=Inter:wght@400;600&family=JetBrains+Mono:wght@500&display=swap">
<style>
:root{{--bg:#F3F1EC;--fg:#15171D;--muted:#5D6170;--line:#DCD7CC;--card:#FFFDF8;--keep:#2ECC71;--cut:#FF5A5F;--amber:#8A5A00;color-scheme:light}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#121318;--fg:#EDEBE6;--muted:#A4A7B3;--line:#2B2E38;--card:#1A1C23;--amber:#FFC53D;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#121318;--fg:#EDEBE6;--muted:#A4A7B3;--line:#2B2E38;--card:#1A1C23;--amber:#FFC53D;color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 Inter,system-ui,sans-serif;padding-block:28px 60px;
padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}}
.wrap{{max-width:1000px;margin:0 auto;display:grid;gap:22px}}
h1{{font:800 30px/1.15 "Inter Tight",Inter,sans-serif;margin:0;text-wrap:balance}}
.sum{{color:var(--muted)}} .sum b{{color:var(--fg);font-family:"JetBrains Mono",monospace}}
.src{{display:grid;gap:6px;font:500 12px "JetBrains Mono",monospace;color:var(--muted)}}
.bar{{position:relative;height:18px;border-radius:4px;background:var(--cut);overflow:hidden}}
.bar i{{position:absolute;top:0;bottom:0;background:var(--keep)}}
.tbl{{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--card)}}
table{{border-collapse:collapse;width:100%;min-width:760px}}
th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:middle}}
th{{font:500 11px "JetBrains Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
td.n,td.t{{font:500 13px "JetBrains Mono",monospace;font-variant-numeric:tabular-nums;white-space:nowrap}}
td.w small{{display:block;color:var(--muted);font-size:12px}}
.k{{font:500 11px "JetBrains Mono",monospace;padding:3px 7px;border-radius:5px;border:1.5px solid currentColor;white-space:nowrap}}
.k-pause{{color:var(--muted)}} .k-filler{{color:var(--amber)}} .k-words,.k-jump{{color:var(--cut)}}
audio{{width:190px;height:32px}}
</style>
<div class="wrap">
<h1>{name}: every cut</h1>
<p class="sum"><b>{n}</b> cuts · <b>{removed}s</b> removed · {kinds}. Green is kept, red is cut. <b>Raw</b> plays the source with the removed part; <b>edited</b> plays the join.</p>
{bars}
<div class="tbl"><table><thead><tr><th>#</th><th>At</th><th>Kind</th><th>Removed</th><th>Raw</th><th>Edited</th></tr></thead><tbody>{rows}</tbody></table></div>
</div>
"""
