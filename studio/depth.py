"""Photo -> depth -> parallax layers (2.5D moves on stills and screenshots, the "Johnny Harris" photo look).
Depth Anything V2 Small (Apache-2.0, HF: depth-anything/Depth-Anything-V2-Small-hf); holes behind near layers are
filled with LaMa (Apache-2.0, ONNX: Carve/LaMa-ONNX) so the background never shows a black gap when layers move.

    depth_map(image)                 -> grey PNG (white = near)
    layers(image, n=3)               -> [far.png, ..., near.png] (RGBA, sRGB) for the Parallax template
    inpaint(image, mask)             -> image with the masked area filled (also: object removal on stills)"""
import os
import numpy as np
from . import cache

from .config import path as _cfg_path
HF = _cfg_path("hf")
_M = {}


def _depth_model():
    if "d" not in _M:
        os.environ.setdefault("HF_HOME", HF)
        from transformers import pipeline
        _M["d"] = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf", device="mps")
    return _M["d"]


def depth_map(image):
    from PIL import Image
    k = cache.key("depth1", image); out = cache.path("assets", "depth_" + k, "png")
    if os.path.exists(out): return out
    im = Image.open(image).convert("RGB")
    d = np.asarray(_depth_model()(im)["depth"].resize(im.size), np.float32)
    d = (d - d.min()) / max(1e-6, d.max() - d.min())
    Image.fromarray((d * 255).astype(np.uint8)).save(out); return out


def _lama():
    if "l" not in _M:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        p = hf_hub_download("Carve/LaMa-ONNX", "lama_fp32.onnx", cache_dir=os.path.join(HF, "hub"))
        _M["l"] = ort.InferenceSession(p, providers=["CoreMLExecutionProvider", "CPUExecutionProvider"])
    return _M["l"]


def inpaint(image, mask, out=None):
    """Fill the white area of mask (same size as image) with LaMa. Works at 512 px, upscales the fill, keeps the rest."""
    from PIL import Image, ImageFilter
    im = Image.open(image).convert("RGB") if isinstance(image, str) else image.convert("RGB")
    mk = Image.open(mask).convert("L") if isinstance(mask, str) else mask.convert("L")
    W, H = im.size
    a = np.asarray(im.resize((512, 512), Image.LANCZOS), np.float32).transpose(2, 0, 1)[None] / 255
    m = (np.asarray(mk.resize((512, 512), Image.NEAREST), np.float32) > 127).astype(np.float32)[None, None]
    s = _lama(); names = [i.name for i in s.get_inputs()]
    r = s.run(None, {names[0]: a, names[1]: m})[0][0]
    r = r if r.max() > 1.5 else r * 255
    fill = Image.fromarray(np.clip(r.transpose(1, 2, 0), 0, 255).astype(np.uint8)).resize((W, H), Image.LANCZOS)
    soft = mk.filter(ImageFilter.GaussianBlur(4))
    res = Image.composite(fill, im, soft)
    if out: res.save(out); return out
    return res


def _otsu(d, n, bins=64):
    """Depth cut-offs that best separate the picture into n groups (multi-level Otsu, brute force on a histogram)."""
    import itertools
    h, e = np.histogram(d, bins=bins, range=(0, 1)); p = h / h.sum(); c = (e[:-1] + e[1:]) / 2
    best, cut = -1, None
    for ks in itertools.combinations(range(1, bins), n - 1):
        b = (0, *ks, bins); v = 0.0
        for a, z in zip(b[:-1], b[1:]):
            w = p[a:z].sum()
            if w > 0: v += w * ((p[a:z] * c[a:z]).sum() / w) ** 2
        if v > best: best, cut = v, ks
    return [float(e[k]) for k in cut]


def layers(image, n=2, feather=6):
    """Split a photo into n depth layers (far -> near) as RGBA PNGs; each farther layer has the nearer parts filled in."""
    from PIL import Image, ImageFilter
    k = cache.key("plx2", image, n, feather); base = cache.path("assets", "plx_" + k, "")
    outs = [f"{base}_{i}.png" for i in range(n)]
    if all(os.path.exists(o) for o in outs): return outs
    im = Image.open(image).convert("RGB"); d = np.asarray(Image.open(depth_map(image)).resize(im.size), np.float32) / 255
    edges = _otsu(d, n)
    for i in range(n):
        lo = edges[i - 1] if i > 0 else -1; near = d > (edges[i] if i < n - 1 else 2)
        keep = d > lo
        if i == 0:      # far layer: the whole picture with everything nearer painted out
            src = inpaint(im, Image.fromarray((near * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(15))) if near.any() else im
            src.convert("RGBA").save(outs[i]); continue
        a = Image.fromarray(((keep & ~near if i < n - 1 else keep) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(feather))
        if i < n - 1 and near.any():
            src = inpaint(im, Image.fromarray((near * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(15)))
            a = Image.fromarray(np.maximum(np.asarray(a), 0).astype(np.uint8))
        else: src = im
        rgba = src.convert("RGBA"); rgba.putalpha(a); rgba.save(outs[i])
    return outs
