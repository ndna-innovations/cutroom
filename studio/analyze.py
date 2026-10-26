"""Footage analysis Claude uses while planning an edit.
  idle(path, a, b)        stretches where a screen recording doesn't change (waiting for an answer): cut or speed past them
  shots(path)             shot changes (b-roll / downloaded clips) via ffmpeg scdet
  beats(path)             music beats + downbeats (librosa, ISC) -> cut or pop graphics on the beat
  search(media, phrase)   where a phrase is said across every transcribed file (footage search)
  privacy_boxes(path, a, b, every)  OCR boxes of private text over a stretch -> blur entries (source px, item time)"""
import json, os, re, subprocess
import numpy as np
from . import cache, words as W
from .media import duration, log


def idle(path, a=0.0, b=None, min_secs=2.0, thr=0.6, fps=4):
    """[(start, end)] (source seconds) where the picture barely changes for at least min_secs."""
    b = b if b is not None else duration(path)
    k = cache.key("idle1", path, a, b, min_secs, thr, fps)
    p = cache.path("probe", "idle_" + k, "json")
    if os.path.exists(p): return [tuple(x) for x in json.load(open(p))]
    from .media import vstream
    v = vstream(path); hh = int(round(int(v["height"]) * 320 / int(v["width"]) / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", path, "-vf", f"fps={fps},scale=320:{hh},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8)
    F = fr[: len(fr) // (320 * hh) * 320 * hh].reshape(-1, hh, 320).astype(np.float32)
    d = np.abs(np.diff(F, axis=0)).mean(axis=(1, 2)) if len(F) > 1 else np.zeros(0)
    out, run_ = [], 0
    for i, v in enumerate(list(d) + [99]):
        if v < thr: run_ += 1
        else:
            if run_ / fps >= min_secs: out.append((round(a + (i - run_ + 1) / fps, 2), round(a + (i + 1) / fps, 2)))
            run_ = 0
    json.dump(out, open(p, "w")); return out


def shots(path, threshold=10.0):
    """Shot-change times (seconds) using ffmpeg's scdet."""
    e = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vf", f"scale=480:-2,scdet=threshold={threshold}", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return [round(float(x), 3) for x in re.findall(r"lavfi\.scd\.time:\s*([\d.]+)", e)]


def beats(path, start=0.0, dur=None):
    """{"tempo": bpm, "beats": [s...], "downbeats": [s...]} of a music file (librosa beat tracker; downbeats = every 4th
    beat starting at the strongest bar phase)."""
    k = cache.key("beats1", path, start, dur)
    p = cache.path("probe", "beats_" + k, "json")
    if os.path.exists(p): return json.load(open(p))
    import librosa
    y, sr = librosa.load(path, sr=22050, mono=True, offset=start, duration=dur)
    tempo, bf = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    bt = librosa.frames_to_time(bf, sr=sr)
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    strength = onset[np.minimum(bf, len(onset) - 1)] if len(bf) else np.zeros(0)
    phase = int(np.argmax([strength[i::4].sum() for i in range(4)])) if len(bt) >= 4 else 0
    r = dict(tempo=float(np.atleast_1d(tempo)[0]), beats=[round(float(start + t), 3) for t in bt], downbeats=[round(float(start + t), 3) for t in bt[phase::4]])
    json.dump(r, open(p, "w")); return r


def search(media, phrase, context=6):
    """Every place `phrase` is said in the transcribed media list from ingest() (or plain file paths)."""
    hits = []
    for m in media:
        path = m["path"] if isinstance(m, dict) else m
        try: ws = W.transcribe(path)
        except Exception: continue
        i = 0
        while i < len(ws):
            try: k = W.find(ws, phrase, start=i)
            except KeyError: break
            a, b = max(0, k - context), min(len(ws), k + len(phrase.split()) + context)
            hits.append(dict(path=path, t=round(ws[k][0], 2), text=" ".join(w[2] for w in ws[a:b])))
            i = k + 1
    return hits


def privacy_boxes(path, a, b, every=0.5, deny=(), pad=10, crop=None, patterns=True):
    """Blur entries for private text visible in path[a, b]: [{"box": [x,y,w,h], "from": item_t0, "to": item_t1}].
    patterns=False: only the deny words (demo data with made-up emails stays readable; only the real ones are hidden)."""
    from . import ocr
    hits = []
    for t in np.arange(a, b, every):
        for x, y, w, h, s, c in ocr.lines_at(path, float(t)):
            kinds = ([kd for kd, pat in ocr.PRIVATE if re.search(pat, s)] if patterns else []) + [d for d in deny if d.lower() in s.lower()]
            if kinds: hits.append((float(t), [x - pad, y - pad, w + 2 * pad, h + 2 * pad]))
    # merge the same box over consecutive samples
    out = []
    for t, bx in hits:
        m = next((o for o in out if abs(o["box"][1] - bx[1]) < 12 and abs(o["box"][0] - bx[0]) < 40 and t - o["_last"] <= every * 1.6), None)
        if m: m["_last"] = t; m["box"] = [min(m["box"][0], bx[0]), min(m["box"][1], bx[1]), max(m["box"][2], bx[2]), max(m["box"][3], bx[3])]
        else: out.append(dict(box=bx, _first=t, _last=t))
    return [dict(box=[round(v, 1) for v in o["box"]], **{"from": round(o["_first"] - a - every / 2, 2)}, to=round(o["_last"] - a + every / 2, 2)) for o in out]


def content_box(path, a, b, n=5, pad=40, top=60, within=None, aspect=None):
    """Where the content is in a screen recording between a and b: the union of all text OCR finds at n moments,
    padded (source px). Use it as the crop of a floating window so empty app areas don't waste a phone screen.
    within = [x, y, w, h] to search only inside (e.g. the app window); aspect = w/h to grow the box to."""
    from . import ocr
    import numpy as np
    xs = []
    for t in np.linspace(a, b, n):
        for x, y, w, h, s, c in ocr.lines_at(path, float(t)):
            if y < top or len(s.strip()) < 2: continue
            if within and not (within[0] <= x and x + w <= within[0] + within[2] and within[1] <= y and y + h <= within[1] + within[3]): continue
            xs.append((x, y, x + w, y + h))
    if not xs: return within
    A = np.array(xs, float)
    x0, y0 = np.percentile(A[:, 0], 2), np.percentile(A[:, 1], 2)
    x1, y1 = np.percentile(A[:, 2], 98), np.percentile(A[:, 3], 98)
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    if aspect:
        w, h = x1 - x0, y1 - y0
        if w / h < aspect: d = h * aspect - w; x0 -= d / 2; x1 += d / 2
        else: d = w / aspect - h; y0 -= d / 2; y1 += d / 2
    if within:
        x0, y0 = max(x0, within[0]), max(y0, within[1]); x1, y1 = min(x1, within[0] + within[2]), min(y1, within[1] + within[3])
    return [int(x0) // 2 * 2, int(y0) // 2 * 2, int(x1 - x0) // 2 * 2, int(y1 - y0) // 2 * 2]


def track_quad(path, t0, n, quad, fps=30, step=1):
    """Planar tracking (corner pin): follow a flat surface (phone screen, monitor, sign) from t0 for n frames.
    quad = 4 corners [[x,y] TL, TR, BR, BL] in source px at t0. Features inside the quad are tracked with optical flow;
    a homography per frame moves the corners. Returns [n][4][2] (smoothed). Cached."""
    import cv2, json, os
    from . import cache, frames as F
    k = cache.key("quad1", path, round(t0, 3), n, json.dumps(quad)); p = cache.path("probe", "quad_" + k, "json")
    if os.path.exists(p): return json.load(open(p))
    W, H = F.probe_wh(path); sc_ = 960 / W
    q = np.float32(quad) * sc_
    out = [np.float32(quad)]
    prev = None; pts = None
    import subprocess
    h_ = int(round(H * sc_ / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.4f}", "-i", path, "-vf", f"fps={fps},scale=960:{h_},format=gray",
                          "-frames:v", str(n), "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    frames_ = np.frombuffer(raw, np.uint8).reshape(-1, h_, 960)
    sc_y = h_ / H
    q = np.float32(quad) * np.float32([sc_, sc_y])
    for i in range(len(frames_)):
        g = frames_[i]
        if prev is None:
            m = np.zeros_like(g); cv2.fillConvexPoly(m, q.astype(np.int32), 255)
            pts = cv2.goodFeaturesToTrack(g, 200, 0.01, 6, mask=m)
            prev = g; continue
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, g, pts, None, winSize=(21, 21), maxLevel=3)
        good_a, good_b = pts[st == 1], nxt[st == 1]
        if len(good_a) >= 6:
            Hm, _ = cv2.findHomography(good_a, good_b, cv2.RANSAC, 3.0)
            if Hm is not None: q = cv2.perspectiveTransform(q.reshape(1, 4, 2), Hm)[0]
            pts = good_b.reshape(-1, 1, 2)
        prev = g
        out.append(q / np.float32([sc_, sc_y]))
    A = np.array(out[:n], np.float32)
    if len(A) > 4:     # light smoothing against jitter
        k_ = np.ones(5) / 5
        A = np.stack([np.convolve(np.pad(A[:, c, d], 2, mode="edge"), k_, "valid") for c in range(4) for d in range(2)], -1).reshape(-1, 4, 2)
    res = A.round(2).tolist(); json.dump(res, open(p, "w")); return res
