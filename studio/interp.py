"""New frames between real ones: smooth slow motion, morph cuts on jump cuts, and a gentle "extend" hold.

Backend: rife-ncnn-vulkan (nihui, MIT, https://github.com/nihui/rife-ncnn-vulkan) with the RIFE v4.6 model that ships
in its release zip (converted from hzwer's Practical-RIFE, MIT, https://github.com/hzwer/Practical-RIFE). Free for
commercial use. Runs on the M5 Pro GPU through MoltenVK (bundled in the binary); no PyTorch needed.
Binary: ~/models/studio/bin/rife-ncnn-vulkan; models: ~/models/studio/rife/rife-v4.6.

HDR: frames are read as 16-bit HLG BT.2020 R'G'B'. RIFE only takes 8-bit images, so it sees an 8-bit copy. Real
frames are passed through at full precision; for new frames, wherever RIFE's result matches the plain blend of the two
neighbours (still areas: the wall, the couch) the 16-bit blend is used, so gradients don't band. Only moving areas
(face, hands, hair) carry RIFE's 8-bit picture, where motion and grain hide it.
Output: ProRes 422 HQ 10-bit, 30 fps, tagged bt2020 / arib-std-b67 / bt2020nc (color.ENC_TAGS). All results cached."""
import os, subprocess, tempfile, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from . import cache
from .color import ENC_TAGS, HLG_TAGS
from .frames import probe_wh
from .media import ff, log

from .config import path as _cfg_path
RIFE_BIN = _cfg_path("rife_bin")
RIFE_MODEL = _cfg_path("rife_model")
VERSION = "interp1"
FPS = 30


# ---------------------------------------------------------------- frames in / out

def _read16(src, t, n):
    """n frames from t on the 30 fps grid as uint16 (h, w, 3) arrays, HLG R'G'B' code values (BT.2020 matrix)."""
    w, h = probe_wh(src)
    vf = f"fps={FPS},scale=in_color_matrix=bt2020:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb48le"
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{t:.4f}", "-i", src, "-map", "0:v:0", "-vf", vf,
           "-frames:v", str(n), "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint16).reshape(-1, h, w, 3)
    if len(a) < n: raise ValueError(f"only {len(a)} of {n} frames at {t:.2f}s in {src}")
    return list(a)


def _to8(f16):
    return ((f16.astype(np.uint32) * 255 + 32767) // 65535).astype(np.uint8)


def _png(path, rgb8):
    import cv2
    cv2.imwrite(path, rgb8[..., ::-1], [cv2.IMWRITE_PNG_COMPRESSION, 1])


def _rife(frames8, target, work):
    """Run RIFE over a folder of 8-bit frames. Output frame i sits at input time i*len(frames8)/target
    (rife-ncnn's own mapping, checked 2026-10-17). Returns the output paths in order."""
    d_in, d_out = os.path.join(work, "in"), os.path.join(work, "out")
    os.makedirs(d_in); os.makedirs(d_out)
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda a: _png(os.path.join(d_in, f"{a[0] + 1:08d}.png"), a[1]), enumerate(frames8)))
    cmd = [RIFE_BIN, "-m", RIFE_MODEL, "-i", d_in, "-o", d_out, "-n", str(target), "-j", "4:4:8"]   # fastest on M5 Pro
    r = subprocess.run(cmd, capture_output=True, text=True)
    outs = sorted(os.listdir(d_out))
    if r.returncode or len(outs) != target:
        raise RuntimeError(f"rife failed ({r.returncode}, {len(outs)}/{target} frames)\n{r.stderr[-2000:]}")
    return [os.path.join(d_out, x) for x in outs]


def _lift(rife8_path, s0, s1, t):
    """A new frame at fraction t between 16-bit frames s0, s1: RIFE's picture in moving areas, the exact 16-bit blend
    where nothing moved (so the 8-bit step never shows as banding on smooth walls)."""
    import cv2
    r = cv2.imread(rife8_path, cv2.IMREAD_UNCHANGED)[..., ::-1].astype(np.float32) / 255
    b = (s0.astype(np.float32) * (1 - t) + s1.astype(np.float32) * t) / 65535
    d = np.abs(r - b).max(-1) * 255                                  # difference in 8-bit steps
    d = cv2.GaussianBlur(d, (0, 0), 3)
    m = np.clip((4.0 - d) / 2.5, 0, 1)[..., None]                    # <1.5 steps: blend, >4 steps: RIFE
    out = m * b + (1 - m) * r
    return (np.clip(out, 0, 1) * 65535 + 0.5).astype(np.uint16)


def _encode(frames16, out, label):
    """uint16 HLG R'G'B' frames -> ProRes 422 HQ 10-bit, 30 fps, HLG BT.2020 tags (temp raw file, then ff())."""
    h, w, _ = frames16[0].shape
    fd, raw = tempfile.mkstemp(suffix=".rgb48", dir=os.path.dirname(out))
    try:
        with os.fdopen(fd, "wb") as f:
            for fr in frames16: f.write(np.ascontiguousarray(fr, np.uint16).astype("<u2").tobytes())
        ff(["-f", "rawvideo", "-pix_fmt", "rgb48le", "-s", f"{w}x{h}", "-r", FPS, "-i", raw,
            "-vf", "scale=in_range=pc:out_color_matrix=bt2020:out_range=tv:flags=accurate_rnd,format=p210le," + HLG_TAGS,
            "-c:v", "prores_videotoolbox", "-profile:v", "hq", "-pix_fmt", "p210le", *ENC_TAGS, "-r", FPS,
            cache.tmp(out)], label=label, retry_sw=False)
    finally:
        os.remove(raw)
    return cache.commit(out)


def _target(step, k, out):
    p = os.path.abspath(os.path.expanduser(out)) if out else cache.path("interp", f"{step}_{k}", "mov")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


# ---------------------------------------------------------------- public

def slowmo(src, a, b, factor=2.0, out=None):
    """src[a, b] played `factor` times slower with real new in-between frames (RIFE), 30 fps, duration (b-a)*factor.
    Every factor-th frame is the original frame at full precision. Cached."""
    src = os.path.abspath(os.path.expanduser(src))
    k = cache.key(VERSION, "slowmo", src, a, b, factor, os.path.basename(RIFE_MODEL))
    p = _target("slowmo", k, out)
    if cache.done(p): return p
    n = max(1, round((b - a) * FPS)); m = max(1, round(n * factor))
    s16 = _read16(src, a, n + 1)                                      # one past b, so the last new frames have both sides
    target = int(np.ceil((n + 1) * m / n))
    step = (n + 1) / target                                           # input frames per output frame (= 1/factor)
    t0 = time.time()
    with tempfile.TemporaryDirectory(dir=os.path.dirname(p)) as work:
        outs = _rife([_to8(f) for f in s16], target, work)
        def one(i):
            x = i * step; j = int(x); f = x - j
            return s16[min(j, n)] if f < 1e-6 or j >= n else _lift(outs[i], s16[j], s16[j + 1], f)
        with ThreadPoolExecutor(6) as ex: res = list(ex.map(one, range(m)))
        log(f"[slowmo] {n} -> {m} frames in {time.time() - t0:.1f}s ({(m - n) / max(time.time() - t0, 1e-6):.1f} new frames/s)")
        return _encode(res, p, "slowmo")


def morph(src, a_end, b_start, n=4, out=None):
    """A morph-cut bridge for a jump cut in one take: n new frames that move from the frame at a_end to the frame at
    b_start (both in src), at even steps 1/(n+1) .. n/(n+1). The two end frames are not included: place the bridge
    between them (or over the last/first frames at the cut). Cached."""
    src = os.path.abspath(os.path.expanduser(src))
    k = cache.key(VERSION, "morph", src, a_end, b_start, n, os.path.basename(RIFE_MODEL))
    p = _target("morph", k, out)
    if cache.done(p): return p
    A = _read16(src, a_end, 1)[0]; B = _read16(src, b_start, 1)[0]
    t0 = time.time()
    with tempfile.TemporaryDirectory(dir=os.path.dirname(p)) as work:
        outs = _rife([_to8(A), _to8(B)], 2 * (n + 1), work)           # output i sits at i/(n+1)
        res = [_lift(outs[i], A, B, i / (n + 1)) for i in range(1, n + 1)]
        log(f"[morph] {n} frames in {time.time() - t0:.1f}s")
        return _encode(res, p, "morph")


def extend(src, t, seconds, out=None, push=0.02):
    """Hold the frame at t for `seconds` with a slow eased push-in of `push` (2 %), drawn with sub-pixel Lanczos
    resampling at full 16-bit precision, so it reads as a held moment, not a frozen frame. No new content is made."""
    import cv2
    src = os.path.abspath(os.path.expanduser(src))
    k = cache.key(VERSION, "extend", src, t, seconds, push)
    p = _target("extend", k, out)
    if cache.done(p): return p
    f = _read16(src, t, 1)[0]; h, w, _ = f.shape
    m = max(1, round(seconds * FPS)); res = []
    for i in range(m):
        u = i / max(m - 1, 1); e = u * u * (3 - 2 * u)               # smoothstep: starts and ends at rest
        s = 1 + push * e
        M = np.array([[s, 0, (1 - s) * w / 2], [0, s, (1 - s) * h / 2]], np.float64)
        res.append(cv2.warpAffine(f, M, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT))
    return _encode(res, p, "extend")


def available():
    """True when the RIFE binary and model are installed."""
    return os.access(RIFE_BIN, os.X_OK) and os.path.isdir(RIFE_MODEL)
