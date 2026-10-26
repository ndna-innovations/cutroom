"""Object masks with SAM 2 (Apache 2.0): click (or default: him) -> a steady mask for every frame of a range.
Used by scene "subject_fx": text behind the person, background blur, spotlight, outline glow.

person_masks(src, a, n, point=None) -> path of a lossless gray mask video (source size, 30 fps on the same grid as
the camera pieces). SAM 2 tracks on keyframes (every 2nd frame) with memory; frames in between are blended, then
the edge is feathered. Cached by source fingerprint, range and point."""
import os, subprocess, tempfile, shutil
import numpy as np
from . import cache
from .media import ff, log

from .config import path as _cfg_path
MODELS = _cfg_path("models")
FPS = 30


def person_masks(src, a, n, point=None, stride=2, feather=2.0):
    from . import assets as A
    k = cache.key("pmask2", src, round(a, 4), n, point, stride, feather)
    out = cache.path("masks", "pm_" + k, "mkv")
    if cache.done(out): return out
    import torch, cv2
    from sam2.build_sam import build_sam2_video_predictor
    W, H = A.size_of(src); sc = 1024 / max(W, H)
    w, h = int(W * sc) // 2 * 2, int(H * sc) // 2 * 2
    tmp = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"), prefix="pm_")
    try:
        sel = f"select='not(mod(n\\,{stride}))'," if stride > 1 else ""
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, a - 1):.3f}", "-copyts", "-i", src, "-vf",
                        f"setpts=PTS-{a:.6f}/TB,fps={FPS}:round=near,trim=start=0:end={n / FPS:.6f},setpts=PTS-STARTPTS,{sel}"
                        f"scale={w}:{h},scale=in_color_matrix=bt2020:in_range=tv,format=rgb24", "-fps_mode", "passthrough", "-q:v", "2",
                        "-start_number", "0", f"{tmp}/%05d.jpg"], check=True)
        if point is None:
            hp = A.head_point(src, {}); point = [hp[0], hp[1] + (A._landmarks_median(src, {})["chin"][1] - hp[1]) * 1.6]
            pts = np.array([[hp[0] * sc, hp[1] * sc], [point[0] * sc, min(h - 2, point[1] * sc)]], np.float32)
        else:
            pts = np.array([[point[0] * sc, point[1] * sc]], np.float32)
        dev = "mps" if torch.backends.mps.is_available() else "cpu"
        pred = build_sam2_video_predictor("configs/sam2.1/sam2.1_hiera_s.yaml", f"{MODELS}/sam2.1_hiera_small.pt", device=dev)
        keys = {}
        with torch.inference_mode():
            st = pred.init_state(video_path=tmp)
            pred.add_new_points_or_box(st, frame_idx=0, obj_id=1, points=pts, labels=np.ones(len(pts), np.int32))
            for fi, ids, logits in pred.propagate_in_video(st):
                keys[fi * stride] = torch.sigmoid(logits[0, 0]).float().cpu().numpy()
        ks = sorted(keys)
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                                "-c:v", "ffv1", "-pix_fmt", "gray", cache.tmp(out)], stdin=subprocess.PIPE)
        for i in range(n):
            lo = max(q for q in ks if q <= i) if any(q <= i for q in ks) else ks[0]
            hi = min((q for q in ks if q >= i), default=lo)
            m = keys[lo] if hi == lo else keys[lo] * (1 - (i - lo) / (hi - lo)) + keys[hi] * ((i - lo) / (hi - lo))
            m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)
            m = cv2.GaussianBlur(np.clip((m - 0.5) * 6 + 0.5, 0, 1), (0, 0), feather * W / 1920)
            enc.stdin.write((m * 255).astype(np.uint8).tobytes())
        enc.stdin.close(); enc.wait()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return cache.commit(out)
