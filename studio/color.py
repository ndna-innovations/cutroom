"""Colour: sRGB graphics -> HLG BT.2020 (the iPhone footage), done the standard way (ITU-R BT.2408 / BT.2100).

Why: the camera footage is HLG BT.2020. A graphic drawn in sRGB and dropped into that file unconverted looks wrong
(too saturated, too bright; an sRGB end card made his face red on 2026-10-17). ffmpeg's own overlay also converts RGBA
with the BT.601 matrix unless told otherwise. So every graphic goes through `srgb_to_hlg` (exact) or the 3D LUT made
from it (`hlg_lut()`, used by ffmpeg lut3d for video), and is turned into YUV with the BT.2020 matrix explicitly.

Mapping (BT.2408): sRGB 1.0 = 203 cd/m2 "graphics white" on a 1000 cd/m2 HLG display = HLG signal 75 %.
`white` lets a card sit a little lower (default 0.75 = the BT.2408 graphics white)."""
import os
import numpy as np

# BT.709 -> BT.2020 primaries (linear light), ITU-R BT.2087
M709_2020 = np.array([[0.6274, 0.3293, 0.0433],
                      [0.0691, 0.9195, 0.0114],
                      [0.0164, 0.0880, 0.8956]])
M2020_709 = np.linalg.inv(M709_2020)
Y2020 = np.array([0.2627, 0.6780, 0.0593])
A, B, C = 0.17883277, 0.28466892, 0.55991073
LW, GAMMA = 1000.0, 1.2          # nominal HLG display (BT.2100: gamma 1.2 at 1000 nits)
REF_WHITE = 203.0                # BT.2408 graphics white


def srgb_eotf(v):
    v = np.asarray(v, np.float64)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def srgb_oetf(l):
    l = np.clip(np.asarray(l, np.float64), 0, 1)
    return np.where(l <= 0.0031308, l * 12.92, 1.055 * l ** (1 / 2.4) - 0.055)


def hlg_oetf(e):
    e = np.clip(np.asarray(e, np.float64), 0, 1)
    return np.where(e <= 1 / 12, np.sqrt(3 * e), A * np.log(np.maximum(12 * e - B, 1e-12)) + C)


def hlg_inv_oetf(v):
    v = np.clip(np.asarray(v, np.float64), 0, 1)
    return np.where(v <= 0.5, v * v / 3, (np.exp((v - C) / A) + B) / 12)


def ref_nits_for(white=0.75):
    """Display nits that a graphic's sRGB white should land on so its HLG signal equals `white` (0.75 = 203 nits)."""
    ys = hlg_inv_oetf(white)
    return float(ys ** GAMMA * LW)


def srgb_to_hlg(rgb, white=0.75):
    """rgb: (..., 3) sRGB 0..1 -> (..., 3) HLG BT.2020 R'G'B' 0..1 (display-referred conversion, BT.2408 method)."""
    lin = srgb_eotf(rgb) @ M709_2020.T                          # linear, BT.2020 primaries, 1.0 = graphics white
    disp = np.clip(lin, 0, None) * ref_nits_for(white) / LW      # display light, 1.0 = 1000 nits
    yd = disp @ Y2020
    ys = np.power(np.maximum(yd, 1e-12), 1 / GAMMA)              # inverse OOTF (luminance based, keeps hue)
    scene = disp * (ys / np.maximum(yd, 1e-12))[..., None]
    scene = np.where((yd > 1e-12)[..., None], scene, 0)
    return hlg_oetf(scene)


def hlg_to_srgb(rgb, white=0.75):
    """Inverse of srgb_to_hlg (for stills/previews made from HLG frames, e.g. thumbnails, covers)."""
    scene = hlg_inv_oetf(rgb)
    ys = scene @ Y2020
    disp = scene * np.power(np.maximum(ys, 1e-12), GAMMA - 1)[..., None]
    lin = disp * LW / ref_nits_for(white)
    return srgb_oetf(lin @ M2020_709.T)


# Y'CbCr BT.2020 non-constant luminance
KR, KB = 0.2627, 0.0593
def rgb_to_ycbcr(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    y = KR * r + (1 - KR - KB) * g + KB * b
    return np.stack([y, (b - y) / (2 * (1 - KB)), (r - y) / (2 * (1 - KR))], -1)


def ycbcr_to_rgb(ycc):
    y, cb, cr = ycc[..., 0], ycc[..., 1], ycc[..., 2]
    r = y + 2 * (1 - KR) * cr; b = y + 2 * (1 - KB) * cb
    g = (y - KR * r - KB * b) / (1 - KR - KB)
    return np.stack([r, g, b], -1)


def to_limited10(ycc):
    """Normalised Y'CbCr -> 10-bit limited-range code values."""
    return np.stack([64 + 876 * ycc[..., 0], 512 + 896 * ycc[..., 1], 512 + 896 * ycc[..., 2]], -1)


def from_limited(codes, bits=10):
    s = 2 ** (bits - 8)
    return np.stack([(codes[..., 0] - 16 * s) / (219 * s), (codes[..., 1] - 128 * s) / (224 * s), (codes[..., 2] - 128 * s) / (224 * s)], -1)


def hlg_lut(path=None, white=0.75, n=65):
    """Write a .cube 3D LUT (sRGB in -> HLG BT.2020 out) for ffmpeg lut3d; cached by its settings."""
    path = path or os.path.expanduser(f"~/VideoWork/studio-cache/luts/srgb_to_hlg_w{white:.3f}_{n}.cube")
    if os.path.exists(path): return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    g = np.linspace(0, 1, n)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")              # .cube order: red changes fastest
    out = srgb_to_hlg(np.stack([r, gg, b], -1).reshape(-1, 3), white)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(f"TITLE \"sRGB to HLG BT.2020 (BT.2408, white {white})\"\nLUT_3D_SIZE {n}\n")
        np.savetxt(f, out, fmt="%.6f")
    os.replace(tmp, path)
    return path


# ffmpeg filter snippets ------------------------------------------------------
HLG_TAGS = "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc:range=tv"
ENC_TAGS = ["-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc", "-color_range", "tv"]


def overlay_chain(white=0.75, fmt="yuva444p10le"):
    """ffmpeg filters that turn an sRGB RGBA input into HLG BT.2020 YUVA (alpha kept, straight)."""
    return (f"format=rgba64le,lut3d=file='{hlg_lut(white=white)}':interp=tetrahedral,"
            f"scale=out_color_matrix=bt2020:out_range=tv,format={fmt},{HLG_TAGS}")


def opaque_chain(white=0.75, fmt="yuv444p10le"):
    return (f"format=rgb48le,lut3d=file='{hlg_lut(white=white)}':interp=tetrahedral,"
            f"scale=out_color_matrix=bt2020:out_range=tv,format={fmt},{HLG_TAGS}")


def png_to_hlg_png(src, dst, white=0.75):
    """Exact (numpy) conversion of an sRGB PNG to a 16-bit HLG-coded RGBA PNG (for stills baked into HLG video)."""
    from PIL import Image
    im = np.asarray(Image.open(src).convert("RGBA"), np.float64) / 255
    rgb = srgb_to_hlg(im[..., :3], white)
    out = np.concatenate([rgb, im[..., 3:]], -1)
    import cv2
    cv2.imwrite(dst, (np.clip(out[..., [2, 1, 0, 3]], 0, 1) * 65535 + 0.5).astype(np.uint16))
    return dst


def hlg_to_sdr(rgb, white=0.85, knee=0.92):
    """HLG R'G'B' -> sRGB with a soft shoulder above `knee` x graphics white (no clipped foreheads in stills/SDR)."""
    rgb = np.asarray(rgb, np.float64)
    scene = hlg_inv_oetf(rgb); ys = scene @ Y2020
    disp = scene * np.power(np.maximum(ys, 1e-12), GAMMA - 1)[..., None]
    lin = np.clip((disp * LW / ref_nits_for(white)) @ M2020_709.T, 0, None)
    mx = lin.max(-1, keepdims=True); over = np.maximum(mx - knee, 0); room = 1 - knee
    comp = np.where(mx > knee, knee + room * over / (over + room), mx)
    return srgb_oetf(np.clip(lin * (comp / np.maximum(mx, 1e-9)), 0, 1))


# ---------------------------------------------------------------------- grading (HDR-safe)
LOOKS = {   # ready-made looks (all gentle; skin first)
    "clean": dict(contrast=1.04, saturation=1.02),
    "warm": dict(temp=0.06, saturation=1.05, contrast=1.04),
    "cool": dict(temp=-0.06, tint=0.01, contrast=1.05),
    "punchy": dict(contrast=1.07, saturation=1.06, gamma=0.98),
    "film": dict(contrast=1.06, saturation=0.92, lift=(0.012, 0.010, 0.016), gain=(1.0, 0.99, 0.97)),
    "teal-orange": dict(contrast=1.05, saturation=0.98, split=dict(shadows=(-0.02, 0.01, 0.03), highlights=(0.015, 0.005, -0.01))),
    "bright": dict(exposure=0.25, contrast=1.02),
    "moody": dict(exposure=-0.2, contrast=1.1, saturation=0.9),
}


def grade(rgb, p):
    """Grade HLG R'G'B' (0..1). Works in scene-linear light (exposure, white balance), then on a log-ish signal for
    contrast / lift / gamma / gain / split toning, saturation around the BT.2020 luminance; output HLG again.
    p: exposure (stops), temp (-1..1, + = warmer), tint (+ = magenta), contrast (1 = none, pivot mid-grey),
    saturation, lift/gamma/gain (scalar or per-channel), split {shadows: rgb offset, highlights: rgb offset}."""
    p = dict(LOOKS.get(p, {})) if isinstance(p, str) else dict(p)
    if "look" in p: base = dict(LOOKS[p.pop("look")]); base.update(p); p = base
    lin = hlg_inv_oetf(rgb)                                         # scene linear, 0..1
    lin = lin * 2 ** p.get("exposure", 0.0)
    t, ti = p.get("temp", 0.0), p.get("tint", 0.0)
    lin = lin * np.array([1 + 0.5 * t + 0.25 * ti, 1 - 0.5 * ti, 1 - 0.5 * t + 0.25 * ti])
    v = hlg_oetf(np.clip(lin, 0, 1))                                # back to the HLG signal (perceptual)
    piv = 0.5
    v = piv + (v - piv) * p.get("contrast", 1.0)
    lift, gam, gain = (np.broadcast_to(np.asarray(p.get(k, d), float), (3,)) for k, d in (("lift", 0.0), ("gamma", 1.0), ("gain", 1.0)))
    v = np.clip(v * gain + lift * (1 - v), 0, 1) ** (1 / gam)
    if "split" in p:
        y = (v @ Y2020)[..., None]
        v = v + np.asarray(p["split"].get("shadows", (0, 0, 0))) * (1 - y) ** 2 + np.asarray(p["split"].get("highlights", (0, 0, 0))) * y ** 2
    y = (v @ Y2020)[..., None]
    v = y + (v - y) * p.get("saturation", 1.0)
    return np.clip(v, 0, 1)


def grade_lut(p, n=33):
    """.cube for ffmpeg lut3d that applies grade(p) to HLG R'G'B' (cached by the settings)."""
    import json, hashlib
    key = hashlib.sha1(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()[:12]
    path = os.path.expanduser(f"~/VideoWork/studio-cache/luts/grade_{key}_{n}.cube")
    if os.path.exists(path): return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    g = np.linspace(0, 1, n); b, gg, r = np.meshgrid(g, g, g, indexing="ij")
    out = grade(np.stack([r, gg, b], -1).reshape(-1, 3), p)
    with open(path + ".tmp", "w") as f:
        f.write(f"LUT_3D_SIZE {n}\n"); np.savetxt(f, out, fmt="%.6f")
    os.replace(path + ".tmp", path); return path


def grade_chain(p):
    """ffmpeg filters: yuv444p10 HLG -> graded yuv444p10 HLG."""
    return (f"scale=in_color_matrix=bt2020:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb48le,lut3d=file='{grade_lut(p)}':interp=tetrahedral,"
            f"scale=out_color_matrix=bt2020:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv444p10le")
