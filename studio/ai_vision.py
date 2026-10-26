"""AI vision: hair-accurate person cut-outs (BiRefNet) and picture search over footage (SigLIP 2 via open_clip).

Models (both free for commercial use; weights live in ~/models/studio/hf):
- BiRefNet, ZhengPeng7/BiRefNet @ e2bf8e44 (MIT, https://huggingface.co/ZhengPeng7/BiRefNet ; code
  https://github.com/ZhengPeng7/BiRefNet, MIT). 444 MB fp32. Its model code comes from that pinned HF revision.
- Picture search: SigLIP 2 ViT-B-16 at 512 px through open_clip, timm/ViT-B-16-SigLIP2-512 (Apache-2.0,
  https://huggingface.co/timm/ViT-B-16-SigLIP2-512 ; open_clip code MIT, https://github.com/mlfoundations/open_clip).
  1.5 GB. Chosen over OpenCLIP ViT-B-32 laion2b (laion/CLIP-ViT-B-32-laion2B-s34B-b79K, MIT, 605 MB, 5x faster):
  on a Cap screen recording B-32 could not find a file-open dialog unless the query was worded just right;
  SigLIP 2 with 2x2 tiles put the right frame first. Set CLIP_HUB to the B-32 id to trade accuracy for speed.

Search tips: describe the picture fully ("a screenshot of a file selection dialog box", "a screenshot of a chat
conversation with long text replies"); short labels score worse. For words on screen, OCR (studio.ocr) is better.

Footage is iPhone HLG: frames are tone-mapped with color.hlg_to_sdr(rgb, 0.9, 0.95) so the models see a natural
sRGB picture. SDR files (screen recordings) are decoded as they are."""
import os, json, subprocess, functools
import numpy as np
from . import cache

from .config import path as _cfg_path
MODELS = _cfg_path("hf")
os.environ.setdefault("HF_HOME", MODELS)
BIREFNET, BIREFNET_REV = "ZhengPeng7/BiRefNet", "e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4"
CLIP_HUB = "hf-hub:timm/ViT-B-16-SigLIP2-512"
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".bmp")
_models = {}


def device():
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


def _is_image(p):
    return p.lower().endswith(IMAGE_EXT)


def _probe(p):
    """(width, height, is_hlg) of a video (remembered per file + mtime)."""
    return _probe_cached(p, os.path.getmtime(p))


@functools.lru_cache(256)
def _probe_cached(p, _mtime):
    o = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,color_transfer", "-of", "json", p],
                                  capture_output=True, text=True, check=True).stdout)["streams"][0]
    return o["width"], o["height"], o.get("color_transfer", "") == "arib-std-b67"


def to_srgb8(hlg):
    """HLG R'G'B' float frame -> natural-looking sRGB uint8 (same tone map as shorts.cutout)."""
    from . import color as C
    s = C.hlg_to_sdr(np.clip(np.asarray(hlg, np.float64), 0, 1), 0.9, 0.95)
    return (np.clip(s, 0, 1) * 255 + 0.5).astype(np.uint8)


def frame_srgb(src, t=0.0):
    """One frame of a video (or an image) as sRGB uint8 (h, w, 3)."""
    from PIL import Image
    if _is_image(src): return np.asarray(Image.open(src).convert("RGB"))
    from . import frames as F
    if _probe(src)[2]: return to_srgb8(F.read_rgb(src, t)[0])
    return (F.read_rgb(src, t, matrix="bt709")[0] * 255 + 0.5).astype(np.uint8)


# ---------------------------------------------------------------- cut-outs (BiRefNet)

def _birefnet():
    if "birefnet" not in _models:
        import torch
        from transformers import AutoModelForImageSegmentation
        m = AutoModelForImageSegmentation.from_pretrained(BIREFNET, revision=BIREFNET_REV, trust_remote_code=True,
                                                          cache_dir=os.path.join(MODELS, "hub"), dtype=torch.float32)
        torch.set_float32_matmul_precision("high")
        m.train(False)
        _models["birefnet"] = m.to(device(), torch.float16 if device() == "mps" else torch.float32)  # fp16 on MPS: ~2x faster
    return _models["birefnet"]


def guided_filter(guide, src, r=8, eps=1e-4):
    """Edge-aware smoothing of `src` (float 0..1) that follows the edges of `guide` (gray float 0..1)."""
    import cv2
    box = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1))
    mi, mp = box(guide), box(src)
    a = (box(guide * src) - mi * mp) / (box(guide * guide) - mi * mi + eps)
    b = mp - a * mi
    return box(a) * guide + box(b)


def _infer(img):
    """One BiRefNet pass: sRGB uint8 crop -> alpha at the crop's size (model runs at 1024x1024)."""
    import torch, cv2
    m = _birefnet()
    x = cv2.resize(img, (1024, 1024), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    x = torch.from_numpy(x.transpose(2, 0, 1)[None].copy()).to(device(), next(m.parameters()).dtype)
    with torch.no_grad():
        a = m(x)[-1].sigmoid()[0, 0].float().cpu().numpy()
    return cv2.resize(a, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_CUBIC).clip(0, 1)


def _square_at(cx, y0, s, w, h):
    s = min(s, w, h)
    return int(np.clip(cx - s // 2, 0, w - s)), int(np.clip(y0, 0, h - s)), s


def _blend_tile(a, tile, x0, y0, feather):
    """Paste a tile's alpha into `a`, fading it in over `feather` px on sides that are inside the frame."""
    s = tile.shape[0]; h, w = a.shape
    ramp = lambda edge_in: np.clip(np.arange(s) / feather, 0, 1) if edge_in else np.ones(s)
    wy = np.minimum(ramp(y0 > 0), ramp(y0 + s < h)[::-1]); wx = np.minimum(ramp(x0 > 0), ramp(x0 + s < w)[::-1])
    k = np.minimum(wy[:, None], wx[None, :]).astype(np.float32)
    a[y0:y0 + s, x0:x0 + s] = k * tile + (1 - k) * a[y0:y0 + s, x0:x0 + s]


def matte_birefnet(rgb_srgb_uint8, refine=True):
    """Alpha (float32 h x w, 0..1) of the person/foreground in an sRGB uint8 image.
    Pass 1: the whole frame at 1024x1024 finds the person. Pass 2: a square crop around the person. Pass 3 (big
    frames only): a ~1024 px tile on the top of the head, so hair is matted near full resolution. Tiles are
    feathered together; then a gentle guided filter (r 4, eps 1e-3) in the soft edge band adds strand detail
    without picking up background stripes. ~0.6 s for a 4K frame on M5 Pro MPS."""
    import cv2
    img = np.ascontiguousarray(np.asarray(rgb_srgb_uint8)[..., :3])
    h, w = img.shape[:2]
    a = _infer(img)
    ys, xs = np.nonzero(a > 0.5)
    if len(ys) and max(h, w) > 1100:
        x0, y0, s = _square_at((xs.min() + xs.max()) // 2, ys.min() - 40, max(xs.max() - xs.min(), h - ys.min()) + 80, w, h)
        _blend_tile(a, _infer(img[y0:y0 + s, x0:x0 + s]), x0, y0, 60)
        if s > 1536:                                            # head tile
            ys, xs = np.nonzero(a > 0.5); top = ys.min()
            cx = int(np.mean(xs[ys < top + s // 8]))
            hx, hy, hs = _square_at(cx, top - s // 14, max(1024, s // 2), w, h)
            _blend_tile(a, _infer(img[hy:hy + hs, hx:hx + hs]), hx, hy, hs // 9)
    if refine:
        g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
        r = max(2, round(max(h, w) / 3840 * 4))
        ref = guided_filter(g, a, r, 1e-3).clip(0, 1)
        band = cv2.dilate(((a > 0.02) & (a < 0.98)).astype(np.uint8), np.ones((2 * r + 1,) * 2, np.uint8)) > 0
        a = np.where(band, ref, a)
    return a.astype(np.float32)


def cutout_birefnet(src, t=0.0, out=None, crop=True):
    """sRGB RGBA PNG of the person at time t of a video (or in an image). Drop-in for shorts.cutout with
    hair-accurate edges. crop=True trims to the person (20 px margin, bottom kept) like shorts.cutout."""
    import cv2
    src = os.path.abspath(os.path.expanduser(src))
    t = 0.0 if _is_image(src) else float(t)
    k = cache.key("cutout_birefnet2", src, round(t, 3), crop, BIREFNET_REV)
    p = out or cache.path("assets", "cutoutb_" + k, "png")
    if os.path.exists(p): return p
    rgb = frame_srgb(src, t)
    m = (matte_birefnet(rgb) * 255 + 0.5).astype(np.uint8)
    rgba = np.dstack([rgb, m])
    if crop:
        ys, xs = np.nonzero(m > 20)
        if len(ys):
            y0, x0, x1 = max(0, ys.min() - 20), max(0, xs.min() - 20), min(rgb.shape[1], xs.max() + 20)
            rgba = rgba[y0:, x0:x1]
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    tmp = cache.tmp(p); cv2.imwrite(tmp, cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)); os.replace(tmp, p)
    return p


# ---------------------------------------------------------------- picture search (SigLIP 2 via open_clip)

def _clip():
    if "clip" not in _models:
        import open_clip
        m, _, pre = open_clip.create_model_and_transforms(CLIP_HUB, cache_dir=os.path.join(MODELS, "hub"))
        m.train(False)
        _models["clip"] = (m.to(device()), pre, open_clip.get_tokenizer(CLIP_HUB))
    return _models["clip"]


def _square(img):
    """Pad to a square (grey bars) so the model sees the whole frame, not a centre crop of a wide shot."""
    from PIL import Image
    w, h = img.size; s = max(w, h)
    sq = Image.new("RGB", (s, s), (124, 116, 104)); sq.paste(img, ((s - w) // 2, (s - h) // 2))
    return sq


def embed_images(imgs, batch=64):
    """L2-normalised image embeddings (n, 768) of sRGB uint8 arrays."""
    import torch
    from PIL import Image
    m, pre, _ = _clip(); out = []
    for i in range(0, len(imgs), batch):
        x = torch.stack([pre(_square(Image.fromarray(a))) for a in imgs[i:i + batch]]).to(device())
        with torch.no_grad():
            e = m.encode_image(x).float()
        out.append(torch.nn.functional.normalize(e, dim=-1).cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, 768), np.float32)


def embed_text(texts):
    """L2-normalised text embeddings (n, 768) of queries."""
    import torch
    m, _, tok = _clip()
    with torch.no_grad():
        e = m.encode_text(tok(list(texts)).to(device())).float()
    return torch.nn.functional.normalize(e, dim=-1).cpu().numpy()


def _decode(src, w, h, hlg, vf_pre, extra):
    fmt, dt = ("rgb48le", np.uint16) if hlg else ("rgb24", np.uint8)
    vf = (f"{vf_pre}scale={w}:{h}:in_color_matrix={'bt2020' if hlg else 'bt709'}:in_range=tv:flags=area,"
          f"showinfo,format={fmt}")
    hw = ["-hwaccel", "videotoolbox"] if hlg else []    # VideoToolbox: ~30x faster on iPhone HEVC, slower on Cap h264
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", *hw, *extra, "-i", src,
                        "-vf", vf, "-fps_mode", "passthrough", "-f", "rawvideo", "-"], capture_output=True, check=True)
    ts = [float(x.split(b" ")[0]) for x in r.stderr.split(b"pts_time:")[1:]]
    arr = np.frombuffer(r.stdout, dt).reshape(-1, h, w, 3)
    assert len(arr) == len(ts), (len(arr), len(ts))
    return ts, arr


def sample_frames(src, every=2.0, width=512):
    """(times, sRGB uint8 frames) about every `every` seconds, decoded small in one ffmpeg pass. Fast path:
    keyframes only, thinned inside ffmpeg (iPhone puts one every ~1 s, so times are real frame times, at most a
    keyframe gap off the grid). If keyframes are sparser than that, every frame is decoded and sampled exactly.
    HLG uses the same BT.2020 read as frames.read_rgb, then the natural tone map."""
    w0, h0, hlg = _probe(src)
    h = round(h0 * width / w0 / 2) * 2
    sel = f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{every * 0.75})',"
    ts, arr = _decode(src, width, h, hlg, sel, ["-skip_frame", "nokey"])
    if len(ts) < 2 or np.max(np.diff(ts)) > every * 1.5:
        ts, arr = _decode(src, width, h, hlg, f"fps=1/{every}:round=down,", [])
        ts = [i * every for i in range(len(arr))]          # fps filter output: frame i is at i * every
    frames = [to_srgb8(f.astype(np.float32) / 65535) for f in arr] if hlg else list(arr)
    return [round(t, 3) for t in ts], frames


def _views(img, grid):
    """The whole frame plus a grid x grid set of tiles (grid=1: just the frame). Small UI on screen recordings
    (a dialog, a button) gets lost when a whole 16:9 screen is shrunk to the model's 512 px; a tile keeps it big enough."""
    if grid <= 1: return [img]
    h, w = img.shape[:2]
    return [img] + [img[r * h // grid:(r + 1) * h // grid, c * w // grid:(c + 1) * w // grid]
                    for r in range(grid) for c in range(grid)]


def index(paths, every=2.0, grid=None):
    """Embed a frame every `every` seconds of each video (images: one frame). Screen recordings / SDR files also
    embed a 2x2 grid of tiles (grid=None picks: 1 for HLG camera, 2 for SDR). Cached as npz per file, keyed by
    file fingerprint + every + grid. Returns {path: (times, embeddings (n, views, 768))}."""
    res = {}
    for p in [paths] if isinstance(paths, str) else paths:
        p = os.path.abspath(os.path.expanduser(p))
        g = grid or (1 if (not _is_image(p) and _probe(p)[2]) else 2)
        c = cache.path("clip_index", cache.key("clip_index7", p, every, g, CLIP_HUB), "npz")
        if not os.path.exists(c):
            ts, fr = ([0.0], [frame_srgb(p)]) if _is_image(p) else sample_frames(p, every, 512 * g)
            v = len(_views(fr[0], g))
            e = embed_images([x for f in fr for x in _views(f, g)]).reshape(len(fr), v, -1)
            tmp = c[:-4] + ".part.npz"
            np.savez(tmp, t=np.array(ts, np.float32), e=e.astype(np.float16)); os.replace(tmp, c)
        z = np.load(c); res[p] = (z["t"], z["e"].astype(np.float32))
    return res


def search(paths, query, top=10, every=2.0):
    """Frames that best match a text description, best first: [{path, t, score}]. Score = cosine similarity of
    the best-matching view (whole frame or a tile)."""
    q = embed_text([query])[0]
    hits = [(float(s), p, float(t)) for p, (ts, e) in index(paths, every).items() for t, s in zip(ts, (e @ q).max(1))]
    hits.sort(reverse=True)
    return [{"path": p, "t": t, "score": round(s, 4)} for s, p, t in hits[:top]]
