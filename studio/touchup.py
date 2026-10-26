"""Face and hair touch-ups for his camera footage, with no seams and no flicker.

What it does (each step can be switched off or tuned in `Look`):
  hair   - tidies the hair outline: clumps and flyaways sticking up above a smooth head shape are replaced by the
           clean slat wall behind him (a wall plate built from the shot itself). Hair masks come from SAM 2 (Apache 2.0)
           on keyframes; the outline is stored relative to his head (MediaPipe landmarks) and smoothed over time, so
           it moves exactly with his head and never wobbles.
  skin   - gentle frequency-separation smoothing inside a skin mask from MediaPipe Face Mesh (eyes, brows, lips,
           nostrils left untouched; less on the stubble).
  shine  - pulls down shiny highlights on forehead / nose / cheeks.
  eyes   - a small lift on the irises and whites.

Why no seams: the patch is the full head region with an alpha that is exactly 0 wherever nothing changed, and
inside the touched area the patch pixels already carry their own soft blends; there is no rectangle edge anywhere.
(The 2026-10-17 Argon patch was a crop with a hard edge -> a line under the eyes.)

Output of `patch(src, a, d)`: a ProRes 4444 clip (HLG BT.2020, alpha) of the head region + its (x, y) position,
to overlay on the source frames of the same time range. Cached by source fingerprint, range and `Look`."""
import json, math, os, subprocess
from dataclasses import dataclass, asdict, field
import numpy as np
import cv2
from . import cache
from .media import ff, log, fingerprint, probe

from .config import path as _cfg_path
MODELS = _cfg_path("models")
FPS = 30


@dataclass
class Look:
    hair: bool = False               # opt-in only: reshaping his hair outline must never happen unasked
    hair_shave: float = 45.0        # max px (4K) the outline may come down to round off a clump
    hair_smooth: float = 70.0       # spatial smoothing of the outline (px)
    hair_feather: float = 4.0       # softness of the new hair edge (px)
    hair_time: float = 2.0          # temporal smoothing of the outline (frames, sigma)
    hair_stride: int = 2            # SAM 2 keyframe every N frames
    skin: float = 0.45              # 0..1 how much blemish-size detail is removed inside the skin mask
    skin_low_beard: float = 0.35    # factor below the nose (keeps stubble natural)
    shine: float = 0.5              # 0..1 share of shiny highlight removed
    eyes: float = 0.06              # iris/white lift (fraction)
    roi: tuple = None               # (x, y, w, h) head region in source px; None = from the face position

    def key(self): return asdict(self)


# ------------------------------------------------------------------ frames
def _wh(src):
    v = next(s for s in probe(src)["streams"] if s["codec_type"] == "video")
    return int(v["width"]), int(v["height"])


def read_frames(src, a, d, crop, scale=None, fmt="rgb48le"):
    """Frames of src[a, a+d] (constant 30 fps), cropped; HLG R'G'B' code values float32 0..1 (or uint8 for 'rgb24')."""
    x, y, w, h = crop
    vf = f"fps={FPS},crop={w}:{h}:{x}:{y}"
    ow, oh = (w, h) if not scale else (int(w * scale) // 2 * 2, int(h * scale) // 2 * 2)
    if scale: vf += f",scale={ow}:{oh}:flags=area"
    vf += f",scale=in_color_matrix=bt2020:in_range=tv:flags=accurate_rnd+full_chroma_int,format={fmt}"
    nf = int(round(d * FPS))
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{a:.4f}", "-i", src, "-vf", vf, "-frames:v", str(nf), "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    bpp = 6 if fmt == "rgb48le" else 3
    size = ow * oh * bpp
    try:
        while True:
            b = p.stdout.read(size)
            if len(b) < size: break
            if fmt == "rgb48le": yield np.frombuffer(b, np.uint16).reshape(oh, ow, 3).astype(np.float32) / 65535
            else: yield np.frombuffer(b, np.uint8).reshape(oh, ow, 3)
    finally:
        p.stdout.close(); p.wait()


# ------------------------------------------------------------------ landmarks
class OneEuro:
    """One-euro filter (Casiez et al.) over arrays: steady when still, no lag when moving."""
    def __init__(self, mincut=0.6, beta=0.02, dcut=1.0):
        self.mc, self.b, self.dc, self.x, self.dx = mincut, beta, dcut, None, None
    @staticmethod
    def _a(cut): r = 2 * math.pi * cut / FPS; return r / (r + 1)
    def __call__(self, x):
        if self.x is None: self.x, self.dx = x.copy(), np.zeros_like(x); return x
        dx = (x - self.x) * FPS
        self.dx = self.dx + self._a(self.dc) * (dx - self.dx)
        cut = self.mc + self.b * np.abs(self.dx)
        a = (2 * math.pi * cut / FPS) / (2 * math.pi * cut / FPS + 1)
        self.x = self.x + a * (x - self.x); return self.x


def landmarks(src, a, d, roi):
    """(n, 478, 2) face landmarks in source px for every frame of src[a, a+d] (smoothed), NaN where no face."""
    k = cache.key("lmk1", src, a, d, roi)
    p = cache.path("touchup", "lmk_" + k, "npy")
    if os.path.exists(p): return np.load(p)
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    opts = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=f"{MODELS}/face_landmarker.task"),
                                        running_mode=vision.RunningMode.VIDEO, num_faces=1)
    det = vision.FaceLandmarker.create_from_options(opts)
    x0, y0, w, h = roi; sc = 0.5
    out, f1 = [], OneEuro()
    for i, fr in enumerate(read_frames(src, a, d, roi, scale=sc, fmt="rgb24")):
        r = det.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(fr)), int(i * 1000 / FPS))
        if r.face_landmarks:
            pts = np.array([[q.x * fr.shape[1] / sc + x0, q.y * fr.shape[0] / sc + y0] for q in r.face_landmarks[0]], np.float32)
            out.append(f1(pts))
        else:
            out.append(np.full((478, 2), np.nan, np.float32))
    det.close()
    L = np.stack(out); np.save(p, L); return L


# MediaPipe Face Mesh index sets
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
             172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
L_EYE = [33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7]
R_EYE = [263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249]
L_BROW = [70, 63, 105, 66, 107, 55, 65, 52, 53, 46]
R_BROW = [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]
LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
NOSTRILS = [[98, 97, 2, 326, 327, 294, 278, 344, 440, 275, 4, 45, 220, 115, 48, 64]]
L_IRIS, R_IRIS = [468, 469, 470, 471, 472], [473, 474, 475, 476, 477]


# ------------------------------------------------------------------ hair
def _sam():
    import torch
    from sam2.build_sam import build_sam2_video_predictor
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    return build_sam2_video_predictor("configs/sam2.1/sam2.1_hiera_s.yaml", f"{MODELS}/sam2.1_hiera_small.pt", device=dev)


def hair_masks(src, a, d, roi, L, stride):
    """Person/hair masks (bool, roi size) on keyframes 0, stride, 2*stride, ... (+ last) from SAM 2 video tracking."""
    k = cache.key("sam1", src, a, d, roi, stride)
    p = cache.path("touchup", "sam_" + k, "npz")
    if os.path.exists(p): z = np.load(p); return z["idx"], z["m"]
    import torch, tempfile, shutil
    x0, y0, w, h = roi
    n = len(L); idx = list(range(0, n, stride))
    if idx[-1] != n - 1: idx.append(n - 1)
    tmp = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"), prefix="sam_")
    try:
        want = set(idx); j = 0
        for i, fr in enumerate(read_frames(src, a, d, roi, scale=0.5, fmt="rgb24")):
            if i in want: cv2.imwrite(f"{tmp}/{j:05d}.jpg", fr[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 95]); j += 1
        pred = _sam(); ms = []
        CH = 120   # SAM 2 keeps every frame in memory: chunks of 120 keyframes, each seeded with the last mask
        files = sorted(os.listdir(tmp)); prev = None
        for c0 in range(0, len(files), CH):
            sub = f"{tmp}/c{c0}"; os.makedirs(sub)
            for q, f in enumerate(files[c0:c0 + CH]): os.link(f"{tmp}/{f}", f"{sub}/{q:05d}.jpg")
            with torch.inference_mode():
                st = pred.init_state(video_path=sub)
                if prev is None:
                    l0 = L[idx[0]]
                    if np.isnan(l0).any(): l0 = np.nanmedian(L, 0)
                    q = (l0 - [x0, y0]) * 0.5
                    top = q[10]; chin = q[152]; fh = chin[1] - top[1]
                    pts = np.array([[top[0], top[1] - 0.25 * fh], [top[0], top[1] + 0.2 * fh], q[1]], np.float32)
                    xs = q[FACE_OVAL][:, 0]
                    box = np.array([xs.min() - 0.35 * fh, top[1] - 0.8 * fh, xs.max() + 0.35 * fh, chin[1]], np.float32)
                    pred.add_new_points_or_box(st, frame_idx=0, obj_id=1, points=pts, labels=np.ones(3, np.int32), box=box)
                else:
                    pred.add_new_mask(st, frame_idx=0, obj_id=1, mask=torch.from_numpy(prev))
                got = {}
                for fi, ids, logits in pred.propagate_in_video(st):
                    got[fi] = (logits[0, 0] > 0).cpu().numpy()
                part = [got[i] for i in range(len(got))]
                ms += part; prev = part[-1]
                pred.reset_state(st)
            shutil.rmtree(sub)
        M = np.stack(ms)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    np.savez_compressed(p, idx=np.array(idx), m=M)
    return np.array(idx), M


def _anchor(L):
    """Head anchor per frame: forehead top (lmk 10) and face height (10 -> 152), filled where tracking failed."""
    top = L[:, 10].copy(); fh = np.linalg.norm(L[:, 152] - L[:, 10], axis=1)
    ok = ~np.isnan(top[:, 0])
    if not ok.any(): raise RuntimeError("no face found in this range")
    t = np.arange(len(L))
    for c in range(2): top[:, c] = np.interp(t, t[ok], top[ok, c])
    fh = np.interp(t, t[ok], fh[ok])
    return top, fh


def hair_outline(idx, M, L, roi, look):
    """Per-frame new outline (y per column in roi px, +inf where no head) and the real-top estimate."""
    x0, y0, w, h = roi
    top, fh = _anchor(L)
    n = len(L)
    xs = np.arange(w, dtype=np.float32)
    # keyframe tops in head-relative coordinates: u = (x - ax)/fh, v = (y - ay)/fh
    U = np.linspace(-1.6, 1.6, 641, dtype=np.float32)
    rel = np.full((len(idx), len(U)), np.nan, np.float32)
    for r, (i, m) in enumerate(zip(idx, M)):
        mm = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_LINEAR) > 0
        has = mm.any(0)
        t = np.where(has, mm.argmax(0), np.nan).astype(np.float32)
        ax, ay = top[i][0] - x0, top[i][1] - y0
        u = (xs - ax) / fh[i]; v = (t - ay) / fh[i]
        good = ~np.isnan(v)
        if good.sum() > 10: rel[r] = np.interp(U, u[good], v[good], left=np.nan, right=np.nan)
    # temporal smoothing at keyframes (in head coords), then per frame by interpolation
    from scipy.ndimage import gaussian_filter1d
    sig = max(0.5, look.hair_time / max(1, look.hair_stride))
    filled = np.where(np.isnan(rel), np.nanmedian(rel, 0, keepdims=True), rel)
    valid = ~np.isnan(np.nanmedian(rel, 0))
    sm = gaussian_filter1d(filled, sig, axis=0, mode="nearest")
    out = np.empty((n, w), np.float32)
    tk = idx.astype(np.float32)
    per = np.stack([np.interp(np.arange(n), tk, sm[:, c]) for c in range(len(U))], 1)   # (n, len(U))
    for i in range(n):
        ax, ay = top[i][0] - x0, top[i][1] - y0
        u = (xs - ax) / fh[i]
        v = np.interp(u, U, per[i], left=np.nan, right=np.nan)
        v[~np.interp(u, U, valid.astype(np.float32), left=0, right=0).astype(bool)] = np.nan
        y = ay + v * fh[i]
        out[i] = np.where(np.isnan(y), np.inf, y)
    # round off clumps: smooth along x, never move the outline up, at most `shave` down
    newl = np.empty_like(out)
    for i in range(n):
        t = out[i]; has = np.isfinite(t)
        if has.sum() < 50: newl[i] = np.inf; continue
        xs_ = np.nonzero(has)[0]
        s = t.copy(); s[xs_] = cv2.GaussianBlur(t[xs_].reshape(1, -1), (0, 0), look.hair_smooth).ravel()
        newl[i] = np.where(has, np.maximum(t, np.minimum(s, t + look.hair_shave)), np.inf)
    return newl, out


def wall_plate(frames_sample, masks_sample):
    """Clean wall (roi size) from sample frames, never using pixels near him; unseen pixels copied from straight
    above (the slats are vertical)."""
    kd = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61))
    st = np.stack(frames_sample)
    ok = np.stack([cv2.dilate(m.astype(np.uint8), kd) == 0 for m in masks_sample])[..., None]
    pl = np.nanmedian(np.where(ok, st, np.nan), axis=0)
    holes = np.isnan(pl[..., 0])
    for x in np.nonzero(holes.any(0))[0]:
        ys = np.nonzero(~holes[:, x])[0]
        if not len(ys): pl[:, x] = pl[:, x - 1] if x else 0; continue
        for yy in np.nonzero(holes[:, x])[0]:
            up = ys[ys < yy]; pl[yy, x] = pl[up.max() if len(up) else ys.min(), x]
    return pl.astype(np.float32)


# ------------------------------------------------------------------ skin / shine / eyes
def _poly(mask, pts, val=1.0):
    cv2.fillPoly(mask, [np.round(pts).astype(np.int32)], val)


def face_masks(l, shape, offset):
    """skin (0..1, feathered), beard weight, iris and white masks for one frame's landmarks (roi px)."""
    h, w = shape; q = l - offset
    fh = np.linalg.norm(q[152] - q[10])
    skin = np.zeros((h, w), np.float32); _poly(skin, q[FACE_OVAL])
    cut = np.zeros((h, w), np.float32)
    for g in (L_EYE, R_EYE, L_BROW, R_BROW, LIPS): _poly(cut, q[g])
    for g in NOSTRILS: _poly(cut, q[g])
    cut = cv2.dilate(cut, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(fh * 0.06) | 1,) * 2))
    skin = np.clip(skin - cut, 0, 1)
    skin = cv2.erode(skin, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(fh * 0.03) | 1,) * 2))
    skin = cv2.GaussianBlur(skin, (0, 0), fh * 0.025)
    yy = np.arange(h, dtype=np.float32)[:, None]
    nose_y = q[2][1]
    beard = np.clip((yy - nose_y) / (fh * 0.08), 0, 1)                        # 0 above the nose tip, 1 below
    eyes = np.zeros((h, w), np.float32); iris = np.zeros((h, w), np.float32)
    for e in (L_EYE, R_EYE): _poly(eyes, q[e])
    for ir in (L_IRIS, R_IRIS):
        c = q[ir[0]]; r = np.linalg.norm(q[ir[1:]] - c, axis=1).mean()
        cv2.circle(iris, tuple(np.round(c).astype(int)), max(1, int(round(r))), 1.0, -1)
    iris *= eyes
    white = np.clip(eyes - cv2.dilate(iris, np.ones((3, 3), np.uint8)), 0, 1)
    eyes_soft = cv2.GaussianBlur(eyes, (0, 0), 2)
    return skin, beard, cv2.GaussianBlur(iris, (0, 0), 1.5) * eyes_soft, cv2.GaussianBlur(white, (0, 0), 1.5) * eyes_soft


def touch_frame(f, l, offset, look):
    """Skin/shine/eyes on one roi frame (HLG R'G'B' float). Returns (result, alpha-support).
    Work happens only inside the face's bounding box (5x faster than the whole head region)."""
    sup = np.zeros(f.shape[:2], np.float32)
    if np.isnan(l).any() or (look.skin <= 0 and look.shine <= 0 and look.eyes <= 0): return f, sup
    skin, beard, iris, white = face_masks(l, f.shape[:2], offset)
    fh = float(np.linalg.norm(l[152] - l[10]))
    ys, xs = np.nonzero((skin > 1e-3) | (iris > 1e-3) | (white > 1e-3))
    if not len(ys): return f, sup
    m = 24
    y0, y1, x0, x1 = max(0, ys.min() - m), min(f.shape[0], ys.max() + m), max(0, xs.min() - m), min(f.shape[1], xs.max() + m)
    S = (slice(y0, y1), slice(x0, x1))
    fs, sk, bd, ir, wh = f[S], skin[S], beard[S[0]], iris[S], white[S]
    o = fs
    if look.skin > 0 or look.shine > 0:
        s1, s2 = max(1.0, fh * 0.0016), max(4.0, fh * 0.012)     # ~1 px fine grain kept; blemish band ~1..8 px softened
        g1 = cv2.GaussianBlur(fs, (0, 0), s1)
        low = cv2.bilateralFilter(fs, d=11, sigmaColor=0.06, sigmaSpace=s2)
        fine, mid = fs - g1, g1 - low
        k = look.skin * sk * (1 - (1 - look.skin_low_beard) * bd)
        o = low + mid * (1 - k)[..., None] + fine
        if look.shine > 0:
            Y = o @ np.array([0.2627, 0.6780, 0.0593], np.float32)
            base = cv2.GaussianBlur(Y, (0, 0), fh * 0.05)
            ex = np.clip(Y - base - 0.015, 0, None)
            o = o - (look.shine * sk * ex)[..., None]
    if look.eyes > 0:
        o = o * (1 + look.eyes * ir)[..., None]
        gray = o.mean(-1, keepdims=True)
        o = o + (look.eyes * wh)[..., None] * ((gray - o) * 0.25 + 0.04)   # whites: a touch less red, a touch brighter
    out = f.copy(); out[S] = np.clip(o, 0, 1)
    sup[S] = np.maximum(sk, np.maximum(ir, wh))
    return out, sup


# ------------------------------------------------------------------ the patch
def default_roi(src, a, d):
    """Head region from the face position (a few frames): wide enough for hair + face, top of frame down to chin."""
    W, H = _wh(src)
    L = landmarks(src, a, min(d, 1.0), (0, 0, W, H))
    l = np.nanmedian(L, 0); fh = np.linalg.norm(l[152] - l[10])
    cx = l[FACE_OVAL][:, 0].mean()
    w = int(fh * 2.6) // 16 * 16; x = int(max(0, min(W - w, cx - w / 2))) // 2 * 2
    h = int(min(H, l[152][1] + fh * 0.15)) // 16 * 16
    return (x, 0, w, h)


def _frame_at(src, t, roi):
    return next(read_frames(src, t, 1 / FPS, roi))


def _prep(src, a, d, look, roi):
    """Everything that needs the whole range: landmarks, hair outline, wall plate."""
    x0, y0, w, h = roi
    L = landmarks(src, a, d, roi)
    n = len(L)
    P = dict(L=L, n=n)
    if look.hair:
        idx, M = hair_masks(src, a, d, roi, L, look.hair_stride)
        newl, real = hair_outline(idx, M, L, roi, look)
        pick = np.unique(np.linspace(0, n - 1, min(n, 24)).astype(int))
        fs, ms = [], []
        for i in pick:
            near = int(idx[np.argmin(np.abs(idx - i))])
            fs.append(_frame_at(src, a + i / FPS, roi)); ms.append(cv2.resize(M[list(idx).index(near)].astype(np.uint8), (w, h)) > 0)
        plate = wall_plate(fs, ms)
        band = (slice(0, 100), slice(None))
        P.update(newl=newl, real=real, plate=plate, plref=plate[band].reshape(-1, 3).mean(0),
                 noise=float(np.median([np.std(f[band] - plate[band]) for f in fs[:6]])))
    return P


def _render_chunk(args):
    src, a, i0, i1, roi, look, P, out = args
    x0, y0, w, h = roi
    off = np.array([x0, y0], np.float32)
    yy = np.arange(h, dtype=np.float32)[:, None]
    band = (slice(0, 100), slice(None))
    rng = np.random.default_rng(1000 + i0)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "rawvideo", "-pix_fmt", "rgba64le", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
                            "-vf", "scale=out_color_matrix=bt2020:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuva444p10le",
                            "-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits", "16", "-color_primaries", "bt2020", "-color_trc", "arib-std-b67",
                            "-colorspace", "bt2020nc", out], stdin=subprocess.PIPE)
    k = np.ones((17, 17), np.uint8)
    try:
        for j, f in enumerate(read_frames(src, a + i0 / FPS, (i1 - i0) / FPS, roi)):
            i = i0 + j
            if i >= i1: break
            res, sup = touch_frame(f, P["L"][i], off, look)
            if look.hair and np.isfinite(P["newl"][i]).any():
                nl = P["newl"][i]; fin = np.isfinite(nl)
                fh = float(np.linalg.norm(P["L"][i][152] - P["L"][i][10])) if not np.isnan(P["L"][i]).any() else 700.0
                edge = np.where(fin, nl, -1e6).astype(np.float32)
                # 1 above the new outline, inside a band that reaches 0.3 face-heights above it (flyaways too)
                cut = np.clip((edge[None, :] + look.hair_feather - yy) / (2 * look.hair_feather), 0, 1)
                reach = np.clip((yy - (edge[None, :] - 0.38 * fh)) / (0.1 * fh), 0, 1)
                side = cv2.GaussianBlur(fin.astype(np.float32).reshape(1, -1), (0, 0), 25).reshape(1, -1)
                hal = cut * reach * np.clip(side * 2 - 0.5, 0, 1)
                g = f[band].reshape(-1, 3).mean(0) - P["plref"]
                pl = P["plate"] + g + rng.normal(0, P["noise"], P["plate"].shape).astype(np.float32) * 0.9
                res = res * (1 - hal[..., None]) + pl * hal[..., None]
                sup = np.maximum(sup, hal)
            al = cv2.dilate((sup > 1e-3).astype(np.uint8), k).astype(np.float32)
            al = np.clip(cv2.GaussianBlur(al, (0, 0), 3) * 1.6, 0, 1)
            al[:, :3] = 0; al[:, -3:] = 0; al[-3:] = 0
            enc.stdin.write((np.clip(np.concatenate([res, al[..., None]], -1), 0, 1) * 65535 + 0.5).astype(np.uint16).tobytes())
    finally:
        enc.stdin.close(); enc.wait()
    return out


def patch_path(src, a, d, look=None, roi=None):
    look = look or Look()
    roi = tuple(look.roi or roi or default_roi(src, a, d))
    k = cache.key("patch4", src, round(a, 3), round(d, 3), look.key(), roi)
    return cache.path("touchup", "patch_" + k, "mov"), roi[:2]


def patch(src, a, d, look=None, roi=None, workers=None):
    """Render the touch-up patch for src[a, a+d] (parallel chunks). Returns (path, (x, y))."""
    look = look or Look()
    roi = tuple(look.roi or roi or default_roi(src, a, d))
    k = cache.key("patch4", src, round(a, 3), round(d, 3), look.key(), roi)
    out = cache.path("touchup", "patch_" + k, "mov")
    if cache.done(out): return out, roi[:2]
    import time, multiprocessing as mp
    t0 = time.time()
    P = _prep(src, a, d, look, roi)
    n = P["n"]; t1 = time.time()
    workers = workers or max(1, min(8, (os.cpu_count() or 8) // 2))
    size = max(30, -(-n // workers))
    parts = [(src, a, i, min(n, i + size), roi, look, P, cache.path("touchup", f"part_{k}_{i:06d}", "mov")) for i in range(0, n, size)]
    with mp.get_context("spawn").Pool(len(parts)) as pool:
        files = pool.map(_render_chunk, parts)
    lst = cache.path("touchup", f"list_{k}", "txt")
    open(lst, "w").write("".join(f"file '{f}'\n" for f in files))
    ff(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", cache.tmp(out)], label="patch-join")
    for f in files: os.remove(f)
    os.remove(lst)
    cache.commit(out)
    log(f"touchup {os.path.basename(src)} {a:.2f}+{d:.2f}s: prep {t1 - t0:.0f}s, frames {time.time() - t1:.0f}s ({n} frames)")
    return out, roi[:2]


def apply_filter(px, py):
    """ffmpeg snippet: [base][patch] -> touched (both HLG, yuv444p10 overlay so no matrix guesswork)."""
    return f"overlay={px}:{py}:format=yuv444p10:eof_action=pass"
