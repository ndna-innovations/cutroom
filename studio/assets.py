"""Assets the compiler needs: Remotion graphics, stills, face-box masks, touch-up patches, colour chains.

Asset paths are content-addressed, so the compiler can name a path before the asset exists; anything missing is
queued in PENDING and the renderer builds all of it (in parallel, Remotion in one batch) before running the graphs."""
import json, os, subprocess
import numpy as np
from . import cache
from . import color as C
from .media import probe, log, ff

PENDING = {}            # path -> job dict
FPS = 30
HERE = os.path.dirname(os.path.abspath(__file__))
GFX = os.path.join(os.path.dirname(HERE), "graphics")

THEMES = {
    # name: bg (sRGB), accent, text; graphics templates read the same names. "plain" (black, white, no accent colour)
    # is used when a timeline names no theme or look: nothing styled is added unless asked for.
    "plain": dict(bg=(0, 0, 0), accent=(255, 255, 255), text=(255, 255, 255)),
    "midnight": dict(bg=(8, 10, 24), accent=(245, 158, 11), text=(255, 255, 255)),
    "ink": dict(bg=(0, 0, 0), accent=(255, 196, 64), text=(255, 255, 255)),
    "studio": dict(bg=(14, 16, 22), accent=(90, 155, 255), text=(255, 255, 255)),
    "sunrise": dict(bg=(26, 10, 34), accent=(255, 110, 90), text=(255, 255, 255)),
    "mint": dict(bg=(6, 22, 24), accent=(60, 214, 160), text=(255, 255, 255)),
}


def theme(kit):
    t = dict(THEMES.get((kit or {}).get("theme") or "plain", THEMES["plain"]))
    t.update({k: tuple(v) for k, v in (kit or {}).get("colors", {}).items()})
    return t


def white_of(kit): return float((kit or {}).get("graphics_white", 0.75))


# ------------------------------------------------------------------ media facts
_P = {}
def _probe(p):
    if p not in _P: _P[p] = probe(p)
    return _P[p]


def size_of(p):
    v = next(s for s in _probe(p)["streams"] if s["codec_type"] == "video"); return int(v["width"]), int(v["height"])


def full_crop(p):
    w, h = size_of(p); return [0, 0, w, h]


def matrix_of(p):
    v = next(s for s in _probe(p)["streams"] if s["codec_type"] == "video")
    m = v.get("color_space", "bt709")
    return {"bt709": "bt709", "bt2020nc": "bt2020", "smpte170m": "bt601", "bt470bg": "bt601"}.get(m, "bt709")


def is_hlg(p):
    v = next(s for s in _probe(p)["streams"] if s["codec_type"] == "video")
    return v.get("color_transfer") == "arib-std-b67"


# ------------------------------------------------------------------ colour chains (ffmpeg)
def legacy_lut(path=None, n=33):
    """'legacy' graphics look: what the old pipeline did (sRGB code values, BT.601 matrix, played as HLG). Kept so
    new videos can match a warm/orange amber if preferred."""
    path = path or os.path.join(os.path.expanduser("~/VideoWork/studio-cache/luts"), f"legacy_{n}.cube")
    if os.path.exists(path): return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    g = np.linspace(0, 1, n); b, gg, r = np.meshgrid(g, g, g, indexing="ij")
    rgb = np.stack([r, gg, b], -1).reshape(-1, 3)
    y = rgb @ np.array([0.299, 0.587, 0.114]); cb = (rgb[:, 2] - y) / 1.772; cr = (rgb[:, 0] - y) / 1.402
    out = C.ycbcr_to_rgb(np.stack([y, cb, cr], -1))
    with open(path + ".tmp", "w") as f:
        f.write(f"LUT_3D_SIZE {n}\n"); np.savetxt(f, np.clip(out, 0, 1), fmt="%.6f")
    os.replace(path + ".tmp", path); return path


def lut_for(white, kit):
    if (kit or {}).get("graphics_mode") == "legacy": return legacy_lut()
    return C.hlg_lut(white=round(white, 3))


def sdr_to_hlg_chain(white, matrix, kit):
    """SDR (sRGB-ish screen / b-roll, given YUV matrix) -> HLG BT.2020 yuv444p10."""
    return (f"scale=in_color_matrix={matrix}:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb48le,"
            f"lut3d=file='{lut_for(white, kit)}':interp=tetrahedral,"
            f"scale=out_color_matrix=bt2020:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv444p10le")


def png16_to_yuv():
    """A 16-bit PNG that already holds HLG R'G'B' -> yuv444p10 (BT.2020 matrix)."""
    return "format=rgb48le,scale=out_color_matrix=bt2020:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv444p10le"


def png16_to_yuva():
    return "format=rgba64le,scale=out_color_matrix=bt2020:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuva444p10le"


def dim_level(item, path, t, crop, kit):
    """Graphics-white level for a screen item. Default: the normal graphics white. "dim": 'auto' dims bright pages
    (browser, docs, Gmail…) and leaves dark app screens at the normal level; a number sets the level."""
    base = white_of(kit)
    d = item.get("dim")
    if isinstance(d, (int, float)): return float(d)
    if d in (None, False, "off"): return base
    k = cache.key("luma1", path, round(t, 2), crop)
    p = cache.path("probe", "luma_" + k, "json")
    if os.path.exists(p): m = json.load(open(p))["m"]
    else:
        x, y, w, h = crop
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf",
                              f"crop={w}:{h}:{x}:{y},scale=320:-2,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        m = float(np.frombuffer(raw, np.uint8).mean() / 255) if raw else 0.2
        json.dump({"m": m}, open(p, "w"))
    if m > 0.55: return round(base * 0.82, 3)       # white page: about 0.62 HLG instead of 0.75
    if m > 0.40: return round(base * 0.9, 3)
    return base


# ------------------------------------------------------------------ stills
def still_hlg(path, size, kit, fit="fit", alpha=False):
    """sRGB picture -> 16-bit PNG holding HLG R'G'B' at the output size (exact maths)."""
    k = cache.key("still3", path, size, white_of(kit), (kit or {}).get("graphics_mode"), fit, alpha)
    out = cache.path("assets", "still_" + k, "png")
    if os.path.exists(out): return out
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    W, H = size
    s = min(W / im.width, H / im.height) if fit == "fit" else max(W / im.width, H / im.height)
    im2 = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    bg = theme(kit)["bg"]
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0) if alpha else bg + (255,))
    canvas.alpha_composite(im2, ((W - im2.width) // 2, (H - im2.height) // 2))
    a = np.asarray(canvas, np.float64) / 255
    rgb = to_hlg(a[..., :3], kit)
    arr = np.concatenate([rgb, a[..., 3:]], -1) if alpha else rgb
    _save16(arr, out); return out


def to_hlg(rgb, kit):
    if (kit or {}).get("graphics_mode") == "legacy":
        y = rgb @ np.array([0.299, 0.587, 0.114]); cb = (rgb[..., 2] - y) / 1.772; cr = (rgb[..., 0] - y) / 1.402
        return np.clip(C.ycbcr_to_rgb(np.stack([y, cb, cr], -1)), 0, 1)
    return C.srgb_to_hlg(rgb, white_of(kit))


def _save16(arr, path):
    import cv2
    a = (np.clip(arr, 0, 1) * 65535 + 0.5).astype(np.uint16)
    a = a[..., [2, 1, 0, 3]] if a.shape[-1] == 4 else a[..., ::-1]
    cv2.imwrite(path + ".tmp.png", a); os.replace(path + ".tmp.png", path)


# ------------------------------------------------------------------ face box
def _rounded(w, h, r, feather=1.5):
    r = max(r, 1.0)     # the corner distance below only works for r >= 0.75 px (r = 0 gave 0.5 everywhere: a half-black box)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    dx = np.maximum(np.maximum(r - xx, xx - (w - r)), 0); dy = np.maximum(np.maximum(r - yy, yy - (h - r)), 0)
    d = np.sqrt(dx * dx + dy * dy) - r
    return np.clip(0.5 - d / feather, 0, 1)


def facebox(R, sc, tl):
    """Rounded face box (default 780x900 at 4K, bottom-left, soft shadow); crop = his head + shoulders."""
    ow, oh = R["profile"]["w"], R["profile"]["h"]; s = ow / (3840 if ow > oh else 1080)
    sinfo = tl["sources"][sc["source_id"]]
    fb = dict(R["kit"].get("facebox", {}), **sinfo.get("facebox", {}))
    bw, bh = int(round(fb.get("w", 780) * s / 2) * 2), int(round(fb.get("h", 900) * s / 2) * 2)
    rad, m = fb.get("radius", 44) * s, fb.get("margin", 40) * s
    crop = sinfo.get("face") or face_crop(sc["src"], sinfo, bw / bh)
    k = cache.key("fbox2", bw, bh, rad)
    mp, sp = cache.path("assets", "fbmask_" + k, "png"), cache.path("assets", "fbshadow_" + k, "png")
    if not os.path.exists(mp):
        import cv2
        a = _rounded(bw, bh, rad)
        cv2.imwrite(mp + ".tmp.png", (a * 65535).astype(np.uint16)); os.replace(mp + ".tmp.png", mp)
        pad = int(60 * s)
        sh = np.zeros((bh + 2 * pad, bw + 2 * pad), np.float32); sh[pad:pad + bh, pad:pad + bw] = a
        sh = cv2.GaussianBlur(sh, (0, 0), 22 * s) * 0.55
        rgba = np.zeros(sh.shape + (4,), np.float32); rgba[..., 3] = sh
        _save16(rgba, sp)
    pos = {"bottom-left": (int(m), int(oh - bh - m)), "bottom-right": (int(ow - bw - m), int(oh - bh - m)),
           "top-left": (int(m), int(m)), "top-right": (int(ow - bw - m), int(m))}
    if "x" in fb and "y" in fb: pos["custom"] = (int(fb["x"] * s), int(fb["y"] * s))
    border = (max(2, int(round(fb.get("border_w", 6) * s))), fb["border"]) if fb.get("border") else None
    return dict(mask=mp, shadow=sp, crop=[int(v) for v in crop], size=(bw, bh), pos=pos, shadow_off=(-int(60 * s), -int(60 * s) + int(10 * s)),
                radius=rad, border=border, fade=fb.get("fade", 0))


def _landmarks_median(src, sinfo):
    from . import touchup as T
    from .media import duration
    k = cache.key("headpt2", src)
    p = cache.path("probe", "head_" + k, "json")
    if os.path.exists(p): return json.load(open(p))
    d = duration(src); W, H = size_of(src)
    pts = []
    for t in np.linspace(min(5, d * 0.1), d * 0.9, 5):
        try: L = T.landmarks(src, float(t), 0.2, (0, 0, W, H))
        except Exception: continue
        if not np.isnan(L).all(): pts.append(np.nanmedian(L, 0))
    if not pts:   # no face in this footage (b-roll, a test card, someone off camera): use the frame centre
        log(f"no face found in {os.path.basename(src)}: face box / zooms use the frame centre (set 'face'/'head' on the source to override)")
        r = dict(top=[W / 2, H * 0.2], chin=[W / 2, H * 0.6], center=[W / 2, H * 0.42])
        json.dump(r, open(p, "w")); return r
    l = np.median(np.stack(pts), 0)
    r = dict(top=l[10].tolist(), chin=l[152].tolist(), center=l[FACE_C].mean(0).tolist())
    json.dump(r, open(p, "w")); return r


FACE_C = [10, 152, 234, 454]


def head_point(src, sinfo):
    return _landmarks_median(src, sinfo)["center"]


def face_crop(src, sinfo, aspect):
    """Head + shoulders box for the face box: hair top to below the chin, centred on the face."""
    h = _landmarks_median(src, sinfo); W, H = size_of(src)
    fh = h["chin"][1] - h["top"][1]
    # headroom: hair must never be cut at the top -> more room above the head
    room = sinfo.get("headroom", 0.95)
    ch = min(H, fh * (1.83 + room)); cw = ch * aspect
    cx = h["center"][0]; y = max(0, h["top"][1] - fh * room)
    x = min(max(cx - cw / 2, 0), W - cw)
    return [int(x) // 2 * 2, int(y) // 2 * 2, int(cw) // 2 * 2, int(min(ch, H - y)) // 2 * 2]


def vertical_frame(src, sinfo):
    """9:16 full-height window on the head (Shorts: never shrink him)."""
    W, H = size_of(src); h = _landmarks_median(src, sinfo)
    w = int(H * 9 / 16) // 2 * 2
    x = int(min(max(h["center"][0] - w / 2, 0), W - w)) // 2 * 2
    return [x, 0, w, H]


def seam_gradient(w, D, R):
    """Soft dark band where the top content meets his camera in a Short (reads as one picture, not two)."""
    k = cache.key("seam1", w, D)
    p = cache.path("assets", "seam_" + k, "png")
    if os.path.exists(p): return p
    h = max(8, int(D * 0.12)); a = np.zeros((h, w, 4), np.float32)
    ramp = (1 - np.linspace(0, 1, h)) ** 1.6 * 0.85
    a[..., 3] = ramp[:, None]
    _save16(a, p); return p


def pip_rect(R, sc, tl, item):
    """Face box rectangle in CANVAS px for a base item (None when no face box is shown over it)."""
    if not sc.get("pieces") or item.get("pip", sc["raw"].get("pip", "none")) == "none": return None
    fb = facebox(R, sc, tl); ow = R["profile"]["w"]
    cw = 3840 if ow > R["profile"]["h"] else 1080; s = ow / cw
    x, y = fb["pos"][item.get("pip", sc["raw"].get("pip", "none"))]; w, h = fb["size"]
    return (x / s, y / s, w / s, h / s)


def pip_label(R, text, center_px, n_total):
    """Step label pill inside the face box (bottom centre), full-canvas overlay for the whole scene."""
    ow = R["profile"]["w"]; dw = 1080 if R["profile"]["h"] > ow * 1.2 else 1920; k = ow / dw
    return graphic("Pill", dict(text=text, x=round(center_px[0] / k, 1), y=round(center_px[1] / k, 1), size=24, fade=False), n_total, R, alpha=True)


# ------------------------------------------------------------------ source fixes (paint-outs)
def source_fixes(sinfo):
    """Static clone patches, e.g. the wall socket: {"clone": [sx, sy, w, h], "to": [dx, dy], "feather": 14}."""
    out = []
    for p in sinfo.get("paint", []):
        sx, sy, w, h = p["clone"]; dx, dy = p["to"]; f = p.get("feather", 14)
        out.append(f"split[pa][pb];[pb]crop={w}:{h}:{sx}:{sy},format=yuva444p10le,"
                   f"geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='1023*min(1,min(min(X,W-1-X)/{f},min(Y,H-1-Y)/{f}))'[pc];"
                   f"[pa][pc]overlay={dx}:{dy}:format=yuv444p10")
    s = sinfo.get("slim")   # e.g. 0.92: the person looks 8% narrower; a band is cropped (40% from the top) and stretched back to full height
    if s:
        out.append(f"crop=iw:ih*{s}:0:(ih-ih*{s})*0.4,scale=iw:ceil(ih/{s}/2)*2:flags=lanczos")
    return out


# ------------------------------------------------------------------ touch-up
def touchup_look(sinfo):
    t = sinfo.get("touchup")
    if not t: return None
    from .touchup import Look
    return Look(**(t if isinstance(t, dict) else {}))


def touchup_patch(src, a, d, look):
    """Path + position of the touch-up patch; queued for the renderer if it isn't made yet."""
    from . import touchup as T
    p, xy = T.patch_path(src, a, d, look)
    if not cache.done(p): PENDING[p] = dict(kind="touchup", src=src, a=a, d=d, look=look)
    return p, xy


def bg_still(R):
    """Solid theme background at the output size (HLG-coded 16-bit PNG)."""
    from PIL import Image
    ow, oh = R["profile"]["w"], R["profile"]["h"]; bg = theme(R["kit"])["bg"]
    k = cache.key("bgsolid", ow, oh, bg)
    src = cache.path("assets", "bgsrgb_" + k, "png")
    if not os.path.exists(src): Image.new("RGB", (ow, oh), bg).save(src)
    return still_hlg(src, (ow, oh), R["kit"])


# ------------------------------------------------------------------ graphics (Remotion)
FFMPEG_FULL = next((p for p in ("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg", "/usr/local/opt/ffmpeg-full/bin/ffmpeg") if os.path.exists(p)), None)


def stabilized(path, a, d, smooth=15):
    """Steady copy of path[a, a+d] with vid.stab (two passes, needs ffmpeg-full); keeps HLG/BT.2020 10-bit tags. Cached."""
    import subprocess, tempfile
    k = cache.key("vstab1", path, round(a, 3), round(d, 3), smooth); out = cache.path("assets", "vstab_" + k, "mov")
    if os.path.exists(out): return out
    tf = tempfile.mktemp(suffix=".trf", dir=os.path.expanduser("~/VideoWork"))
    hlg = is_hlg(path)
    subprocess.run([FFMPEG_FULL, "-v", "error", "-y", "-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", path, "-vf",
                    f"vidstabdetect=shakiness=6:accuracy=15:result={tf}", "-f", "null", "-"], check=True)
    enc = ["-c:v", "prores_videotoolbox", "-profile:v", "hq", "-pix_fmt", "p210le"]
    tags = (["-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc"] if hlg else
            ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"])
    subprocess.run([FFMPEG_FULL, "-v", "error", "-y", "-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", path, "-vf",
                    f"vidstabtransform=input={tf}:smoothing={smooth}:zoom=0:optzoom=1:interpol=bicubic,unsharp=5:5:0.4", *enc, *tags, "-an", out + ".tmp.mov"], check=True)
    os.replace(out + ".tmp.mov", out); os.remove(tf)
    return out


def clip_for_graphic(spec, R):
    """{"source"|"path", "from", "dur", "width"} -> file:// URL of an SDR H.264 cut that a graphic can play (3D screens)."""
    from .model import src_path
    tl = R.get("tl") or {}
    p = src_path(tl, spec["source"]) if "source" in spec else os.path.expanduser(spec["path"])
    w = spec.get("width", 1920); a, d = float(spec.get("from", 0.0)), float(spec.get("dur", 5.0))
    k = cache.key("gclip1", p, a, d, w, spec.get("crop")); out = cache.path("assets", "gclip_" + k, "mp4")
    if not os.path.exists(out):
        crop = spec.get("crop") or (tl.get("sources", {}).get(spec.get("source"), {}) or {}).get("crop")
        vf = (f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}," if crop else "") + f"scale={w}:-2:flags=lanczos,format=yuv420p"
        if is_hlg(p):
            from .export import _sdr_chain
            vf = (f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}," if crop else "") + _sdr_chain(w)
        ff(["-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", p, "-vf", vf, "-an", "-c:v", "libx264", "-crf", "16", "-preset", "fast",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", cache.tmp(out)], label="graphic clip")
        cache.commit(out)
    return "file://" + out


def _clips(x, R):
    if isinstance(x, dict):
        if set(x) == {"$clip"}: return clip_for_graphic(x["$clip"], R)
        return {k: _clips(v, R) for k, v in x.items()}
    if isinstance(x, list): return [_clips(v, R) for v in x]
    return x


def graphic(template, props, nframes, R, alpha=True, layout=None, design=None):
    """Path of a rendered graphic (ProRes 4444 HLG with alpha, or 422 HQ opaque) at the output size."""
    props = _clips(props, R)
    ow, oh = R["profile"]["w"], R["profile"]["h"]
    kit = R["kit"]
    th = theme(kit)
    full = dict(props, _theme={k: list(v) for k, v in th.items()}, _kit=kit.get("graphics", {}))
    if template == "Look" or props.get("look"):   # the look's full design (studio/looks.py): props.look wins over kit.look
        from .looks import resolve
        full["_look"] = resolve(props.get("look") or kit.get("look"))
        if not full["_look"]: raise ValueError(f"template Look needs a look: looks.apply(tl, NAME) or props.look (cutroom looks list)")
    from .gfx import PIPELINE, design_of
    k = cache.key("gfx2", template, full, nframes, ow, oh, alpha, white_of(kit), kit.get("graphics_mode"), _gfx_version(), PIPELINE, design_of(ow, oh, design))
    out = cache.path("gfx", f"{template}_{k}", "mov")
    if not cache.done(out):
        PENDING[out] = dict(kind="remotion", template=template, props=full, frames=nframes, w=ow, h=oh, alpha=alpha,
                            white=white_of(kit), mode=kit.get("graphics_mode", "hlg"), design=design)
    return out


_GV = None
def _gfx_version():
    """Hash of the Remotion sources: editing a template invalidates its renders."""
    global _GV
    if _GV is None:
        import hashlib
        h = hashlib.sha1()
        for root, _, files in os.walk(os.path.join(GFX, "src")):
            for f in sorted(files):
                h.update(f.encode()); h.update(open(os.path.join(root, f), "rb").read())
        _GV = h.hexdigest()[:10]
    return _GV


def layer_asset(L, R, sc, tl):
    """(path, (x, y)) of a layer's overlay clip."""
    n = L["f1"] - L["f0"]
    kind = L["kind"]
    if kind == "graphic":
        if L.get("rect"):    # the template laid out inside a box (its own design size), placed at the box
            ow = R["profile"]["w"]; base = 3840 if ow > R["profile"]["h"] else 1080; s_ = ow / base
            x, y, w, h = [int(round(v * s_ / 2) * 2) for v in L["rect"]]
            R2 = dict(R, profile=dict(R["profile"], w=w, h=h))
            return graphic(L["template"], dict(L.get("props", {}), transparent=L.get("props", {}).get("transparent", True)), n, R2, alpha=True,
                           design=L.get("design")), (x, y)
        return graphic(L["template"], L.get("props", {}), n, R, alpha=True), (0, 0)
    if kind == "ring":
        box = ring_box(L, R, sc, tl)
        trk = L.pop("_track", None)
        if trk:
            dw = 1080 if R["profile"]["h"] > R["profile"]["w"] * 1.2 else 1920; kk = R["profile"]["w"] / dw
            trk = [[t_, round(x_ / kk, 1), round(y_ / kk, 1), round(w_ / kk, 1), round(h_ / kk, 1)] for t_, x_, y_, w_, h_ in trk]
        return graphic("Highlight", dict(_px=["box"], box=box, track=trk, color=L.get("color", "accent"), style=L.get("style", "ring"), delay=L.get("delay", 0.0),
                                         label=L.get("label")), n, R, alpha=True), (0, 0)
    if kind == "captions":
        src_words = L["words"] if isinstance(L.get("words"), list) else (sc["words"] if sc else [])
        ws = [w for w in src_words if L["f0"] / FPS - 0.05 <= w[0] < L["f1"] / FPS]
        ws = [[round(w[0] - L["f0"] / FPS, 3), round(w[1] - L["f0"] / FPS, 3), w[2]] for w in ws]
        if L.get("cues"):   # translated / hand-written captions: [[t0, t1, text]] in the layer's time base
            off = L["f0"] / FPS if not L.get("cues_relative") else 0
            props = dict(cues=[[round(a - off, 3), round(b - off, 3), t] for a, b, t in L["cues"]], words=[])
        elif L.get("phrases"): props = dict(phrases=L["phrases"], words=ws)
        else: props = dict(words=ws)
        props.update(style=L.get("style", "kinetic"), keys=L.get("keys", []), y=L.get("y"),
                     y_at=[[round(t - L["f0"] / FPS, 3), y] for t, y in L["y_at"]] if L.get("y_at") else None)
        return graphic("Captions", props, n, R, alpha=True), (0, 0)
    if kind == "cutout":
        return cutout_hlg(L, R, tl), (0, 0)
    raise ValueError(f"unknown layer kind {kind}")


def cutout_hlg(L, R, tl):
    """His face cut out of a camera frame, kept in HLG (exact colour: no sRGB round trip, no red or washed-out face),
    placed in rect [x, y, w, h] (output px), anchored at the bottom. {"kind": "cutout", "source": "cam", "src_at": 785.4, "rect": [...]}."""
    from .model import src_path
    from . import frames as F, color as Cc
    import cv2, tempfile
    src = src_path(tl, L["source"]); t = L["src_at"]
    ow, oh = R["profile"]["w"], R["profile"]["h"]
    dz = ow / (1080 if oh > ow else 1920)                                   # rect is in design units (1080 / 1920 wide): scale to this profile (drafts are half size)
    rect = [int(v * dz) for v in L["rect"]] if L.get("rect") else [0, int(oh * 0.45), ow, int(oh * 0.55)]
    k = cache.key("cutoutH2", src, round(t, 3), rect, ow, oh)
    p = cache.path("assets", "cutoutH_" + k, "png")
    if os.path.exists(p): return p
    f = F.read_rgb(src, t)[0]                                               # HLG R'G'B'
    prev = (np.clip(Cc.hlg_to_srgb(np.clip(f.astype(np.float64), 0, 1)), 0, 1) * 255).astype(np.uint8)
    d = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork")); cv2.imwrite(f"{d}/f.png", prev[..., ::-1])
    from .ocr import ensure_bin
    subprocess.run([ensure_bin(), "person", d, d + "/m"], check=True)
    m = cv2.GaussianBlur(cv2.imread(f"{d}/m/f.png", 0).astype(np.float32) / 255, (0, 0), 1.5)
    subprocess.run(["rm", "-rf", d])
    ys, xs = np.nonzero(m > 0.1)
    y0, x0, x1 = max(0, ys.min() - 10), max(0, xs.min() - 10), min(f.shape[1], xs.max() + 10)
    rgba = np.dstack([f, m])[y0:, x0:x1]
    x, y, w, h = rect
    sc_ = min(w / rgba.shape[1], h / rgba.shape[0])
    im = cv2.resize(rgba, (int(rgba.shape[1] * sc_), int(rgba.shape[0] * sc_)), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((oh, ow, 4), np.float32)
    px = int(x + (w - im.shape[1]) / 2); py = int(y + h - im.shape[0])
    canvas[py:py + im.shape[0], px:px + im.shape[1]] = im
    _save16(canvas, p)
    return p


def ring_box(L, R, sc, tl):
    """Box (canvas px at output size) for a ring: given in source px of the screen item under it, or found by OCR."""
    from .compile import map_box, _canvas
    f = L["f0"]
    item = next((b for b in sc["base"] if b["f0"] <= f < b["f1"]), None)
    if L.get("space") == "canvas" or item is None or item["kind"] not in ("screen", "broll", "angle"):
        return L["box"]
    path = os.path.join(tl.get("_dir", ""), item["path"]) if "path" in item else None
    from .model import src_path
    path = src_path(tl, item["source"]) if "source" in item else os.path.expanduser(item["path"])
    crop = item.get("crop") or tl["sources"].get(item.get("source"), {}).get("crop") or full_crop(path)
    box = L["box"]
    if isinstance(box, dict):
        from . import ocr
        at = box.get("at", item.get("from", 0.0) if item.get("freeze") else item.get("from", 0.0) + (f - item["f0"]) / FPS)
        box = ocr.find_box(path, at, box["ocr"], box.get("to"), half=box.get("half"), pad=box.get("pad", 14))
    s = R["profile"]["w"] / _canvas(R)[0]
    if L.get("track") and not item.get("freeze"):
        # the ring follows the content (scrolling page, moving window): track the box in the source, map every frame
        D = (item["f1"] - item["f0"]) / FPS
        sp_ = (item["to"] - item.get("from", 0.0)) / D if item.get("to") is not None else item.get("speed", 1.0)
        t0 = (f - item["f0"]) / FPS; n = L["f1"] - L["f0"]
        src_t0 = item.get("from", 0.0) + t0 * sp_
        boxes = track_box(path, src_t0, n, sp_, box)
        out = []
        for k, b in enumerate(boxes):
            m = map_box(item, crop, _canvas(R), t0 + k / FPS, pip_rect(R, sc, tl, item)); x, y, w, h = m(b)
            out.append([round(k / FPS, 3), round(x * s, 1), round(y * s, 1), round(w * s, 1), round(h * s, 1)])
        L["_track"] = out
        return out[0][1:]
    t_item = max((f - item["f0"]) / FPS, 99.0 if L.get("settled", True) else 0)
    if item["kind"] == "angle": t_item = (f - item["f0"]) / FPS + 0.3     # multicam: the view at the ring's own moment
    m = map_box(item, crop, _canvas(R), t_item, pip_rect(R, sc, tl, item))
    x, y, w, h = m(box)
    return [round(x * s, 1), round(y * s, 1), round(w * s, 1), round(h * s, 1)]


def track_box(path, t0, n, speed, box, search=240):
    """Follow a box through a recording by template matching (UI content moves rigidly): [x, y, w, h] per output frame."""
    import cv2
    k = cache.key("track1", path, round(t0, 3), n, round(speed, 4), [round(v, 1) for v in box])
    p = cache.path("probe", "track_" + k, "json")
    if os.path.exists(p): return json.load(open(p))
    from . import frames as F
    W_, H_ = size_of(path); sc = 0.5
    x, y, w, h = [int(round(v)) for v in box]
    def grab(t):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.4f}", "-i", path, "-frames:v", "1", "-vf", f"scale={int(W_ * sc)}:-2,format=gray",
                              "-f", "rawvideo", "-"], capture_output=True).stdout
        hh = len(raw) // int(W_ * sc); return np.frombuffer(raw, np.uint8).reshape(hh, int(W_ * sc))
    f0 = grab(t0); tx, ty, tw, th = int(x * sc), int(y * sc), max(8, int(w * sc)), max(8, int(h * sc))
    tpl = f0[max(0, ty): ty + th, max(0, tx): tx + tw].copy()
    out, cx, cy = [], tx, ty
    step = 2   # match every 2nd frame, interpolate between
    keys = {0: (cx, cy)}
    for i in range(step, n + step, step):
        fr = grab(t0 + min(i, n - 1) / FPS * speed)
        sx0, sy0 = max(0, cx - search), max(0, cy - search)
        win = fr[sy0: cy + th + search, sx0: cx + tw + search]
        if win.shape[0] < th or win.shape[1] < tw: keys[i] = (cx, cy); continue
        r = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED); _, mv, _, ml = cv2.minMaxLoc(r)
        if mv > 0.5: cx, cy = sx0 + ml[0], sy0 + ml[1]
        keys[i] = (cx, cy)
    ks = sorted(keys)
    for i in range(n):
        a = max(q for q in ks if q <= i); b = min((q for q in ks if q >= i), default=a)
        u = 0 if b == a else (i - a) / (b - a)
        X = keys[a][0] + (keys[b][0] - keys[a][0]) * u; Y = keys[a][1] + (keys[b][1] - keys[a][1]) * u
        out.append([round(X / sc, 1), round(Y / sc, 1), w, h])
    json.dump(out, open(p, "w")); return out


# ------------------------------------------------------------------ mouse pointer (Cap cursor.json)
def ring_mask(w, h, r, bw, color, R):
    """Rounded outline (border) as an HLG RGBA 16-bit PNG."""
    k = cache.key("ringm1", w, h, round(r, 1), bw, color, white_of(R["kit"]))
    p = cache.path("assets", "ringm_" + k, "png")
    if not os.path.exists(p):
        a = _rounded(w, h, r) - np.pad(_rounded(w - 2 * bw, h - 2 * bw, max(1, r - bw)), bw)
        rgb = to_hlg(np.ones((h, w, 3)) * np.array(color) / 255, R["kit"])
        _save16(np.concatenate([rgb, np.clip(a, 0, 1)[..., None]], -1), p)
    return p


def rounded_mask(w, h, r):
    k = cache.key("rmask2", w, h, round(r, 1))
    p = cache.path("assets", "rmask_" + k, "png")
    if not os.path.exists(p):
        import cv2
        cv2.imwrite(p + ".tmp.png", (_rounded(w, h, r) * 65535).astype(np.uint16)); os.replace(p + ".tmp.png", p)
    return p


def cursor_overlay(item, path, crop, R, sc, tl, tmap):
    """Remotion 'Cursor' overlay for a screen item: Cap's pointer track mapped through the item's view (zoom-aware)."""
    from .compile import map_box, _canvas
    seg = os.path.dirname(path); cj = os.path.join(seg, "cursor.json")
    if not os.path.exists(cj): return None
    cur_dir = os.path.join(os.path.dirname(os.path.dirname(seg)), "cursors")
    j = json.load(open(cj)); W, H = size_of(path)
    mv = sorted(j.get("moves", []), key=lambda m: m["time_ms"])
    if not mv: return None
    ts = np.array([m["time_ms"] / 1000 for m in mv])
    n = item["f1"] - item["f0"]
    canvas = _canvas(R); s = R["profile"]["w"] / canvas[0]
    avoid = pip_rect(R, sc, tl, item)
    track = []
    for k in range(n):
        tau = k / FPS; st = tmap(tau)
        i = int(np.searchsorted(ts, st, side="right") - 1)
        if i < 0: i = 0
        m = mv[i]
        if i + 1 < len(mv) and ts[i + 1] > ts[i]:
            u = min(1, max(0, (st - ts[i]) / (ts[i + 1] - ts[i]))); x = m["x"] + (mv[i + 1]["x"] - m["x"]) * u; y = m["y"] + (mv[i + 1]["y"] - m["y"]) * u
        else: x, y = m["x"], m["y"]
        f = map_box(item, crop, canvas, tau, avoid)
        X, Y, _, _ = f((x * W, y * H, 0, 0))
        track.append([round(tau, 3), round(X * s, 1), round(Y * s, 1), str(m.get("cursor_id", "0"))])
    clicks = []
    if not item.get("freeze"):
        src_t = [tmap(k / FPS) for k in range(n)]
        for c in j.get("clicks", []):
            if not c.get("down"): continue
            ct = c["time_ms"] / 1000
            k = next((q for q in range(n - 1) if src_t[q] <= ct < src_t[q + 1] + 1e-6 and src_t[q + 1] - src_t[q] < 0.5), None)
            if k is not None: clicks.append([round(k / FPS, 3), track[k][1], track[k][2]])
    if item.get("cursor_smooth", True) and len(track) > 2:      # glide like Screen Studio: smooth the pointer path
        xs = np.array([t_[1] for t_ in track]); ys = np.array([t_[2] for t_ in track])
        from scipy.ndimage import gaussian_filter1d
        sig = item.get("cursor_smooth_frames", 2.5)
        xs, ys = gaussian_filter1d(xs, sig, mode="nearest"), gaussian_filter1d(ys, sig, mode="nearest")
        track = [[t_[0], round(float(x), 1), round(float(y), 1), t_[3]] for t_, x, y in zip(track, xs, ys)]
    ids = {t_[3] for t_ in track}
    images = {i_: "file://" + os.path.join(cur_dir, f"cursor_{i_}.png") for i_ in ids if os.path.exists(os.path.join(cur_dir, f"cursor_{i_}.png"))}
    dw = 1080 if R["profile"]["h"] > R["profile"]["w"] * 1.2 else 1920; k_ = R["profile"]["w"] / dw
    track = [[t_, round(x_ / k_, 1), round(y_ / k_, 1), i_] for t_, x_, y_, i_ in track]
    clicks = [[t_, round(x_ / k_, 1), round(y_ / k_, 1)] for t_, x_, y_ in clicks]
    return graphic("Cursor", dict(track=track, clicks=clicks, images=images, size=item.get("cursor_size", 26)), n, R, alpha=True)


# ------------------------------------------------------------------ auto zoom on clicks (Screen Studio style)
def cap_cursor(path):
    """Cap's cursor.json next to a display.mp4 (moves/clicks in normalised coords, ms), or None."""
    cj = os.path.join(os.path.dirname(path), "cursor.json")
    return json.load(open(cj)) if os.path.exists(cj) else None


def activity_keys(item, path, D, tmap, opts):
    """Screen Studio-style "follow the action" when there are no clicks: sample the shot every 0.5 s, find where the
    screen changes (typing, an answer appearing, a dialog), zoom there; back to full when nothing changes. Cached."""
    import subprocess, cv2
    crop = item.get("crop") or [0, 0, *size_of(path)]
    z = opts.get("zoom", 1.7); dwell = opts.get("dwell", 2.5); quiet = opts.get("quiet", 3.0); ease = opts.get("ease", 0.7)
    ts = np.arange(0, D, 0.5)
    k = cache.key("act3", path, [round(float(tmap(t)), 2) for t in ts], crop, z)
    p = cache.path("probe", "act_" + k, "json")
    if os.path.exists(p): return json.load(open(p))
    sw = 432; sc_ = sw / crop[2]; sh = int(round(crop[3] * sc_))
    def grab(t):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, tmap(t)):.3f}", "-i", path, "-frames:v", "1", "-vf",
                            f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},scale={sw}:{sh},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        return np.frombuffer(r, np.uint8).reshape(sh, sw) if len(r) == sw * sh else None
    frames_ = [grab(t) for t in ts]
    bw, bh = crop[2] / z, crop[3] / z
    def box(cx, cy):
        x = min(max(cx - bw / 2, crop[0]), crop[0] + crop[2] - bw); y = min(max(cy - bh / 2, crop[1]), crop[1] + crop[3] - bh)
        return [round(x, 1), round(y, 1), round(bw, 1), round(bh, 1)]
    raw = []
    for i in range(1, len(frames_)):
        a_, b_ = frames_[i - 1], frames_[i]
        if a_ is None or b_ is None: raw.append(None); continue
        d = cv2.dilate((cv2.absdiff(a_, b_) > 18).astype(np.uint8), np.ones((5, 5), np.uint8))
        if d.mean() < 0.004 or d.mean() > 0.45: raw.append(None); continue        # nothing changed / the whole screen changed (scroll, new page)
        ys, xs = np.nonzero(d)
        raw.append((crop[0] + np.median(xs) / sc_, crop[1] + np.median(ys) / sc_))
    keys = [[0.0, "full"]]; cur = None; since = 0.0; last_act = 0.0
    for i, c in enumerate(raw):
        t = float(ts[i + 1])
        if c is None:
            if cur is not None and t - last_act >= quiet: keys.append([round(t, 3), "full"]); cur = None; since = t
            continue
        last_act = t
        if cur is None or abs(c[0] - cur[0]) > bw * 0.5 or abs(c[1] - cur[1]) > bh * 0.5:
            if t - since < dwell and cur is not None: continue                    # don't jump around: stay at least `dwell`
            keys.append([round(max(keys[-1][0] + 0.05, t - ease), 3), box(*c)]); cur = c; since = t
    keys = [k_ for i, k_ in enumerate(keys) if i == 0 or k_[0] > keys[i - 1][0]]
    keys = [k_ for i, k_ in enumerate(keys) if not (i and k_[1] == "full" and i + 1 < len(keys) and keys[i + 1][0] - k_[0] < 1.5)]   # no out-and-back flicker
    json.dump(keys, open(p, "w")); return keys


def auto_zoom_keys(item, path, D, tmap, opts):
    """View keyframes that zoom in on clusters of clicks: ease in before the first click, follow the clicks, hold,
    ease back out. Boxes are in source px (the window is sized by `zoom`). opts: {zoom, gap, hold, ease, lead, follow}.
    No clicks (or follow: "activity") -> follow where the screen changes instead (activity_keys)."""
    if opts.get("follow") == "activity": return activity_keys(item, path, D, tmap, opts)
    j = cap_cursor(path)
    if not j: return activity_keys(item, path, D, tmap, opts)
    W, H = size_of(path)
    z = opts.get("zoom", 1.8); gap = opts.get("gap", 2.5); hold = opts.get("hold", 1.0); ease = opts.get("ease", 0.6); lead = opts.get("lead", 0.5)
    n = int(round(D * FPS)); st = np.array([tmap(k / FPS) for k in range(n)])
    clicks = []
    for c in j.get("clicks", []):
        if not c.get("down"): continue
        ct = c["time_ms"] / 1000
        k = int(np.argmin(np.abs(st - ct)))
        if abs(st[k] - ct) > 0.05: continue
        mv = min(j["moves"], key=lambda m: abs(m["time_ms"] - c["time_ms"])) if j.get("moves") else None
        if mv: clicks.append((k / FPS, mv["x"] * W, mv["y"] * H))
    if not clicks: return activity_keys(item, path, D, tmap, opts)
    clusters, cur = [], [clicks[0]]
    for c in clicks[1:]:
        if c[0] - cur[-1][0] <= gap: cur.append(c)
        else: clusters.append(cur); cur = [c]
    clusters.append(cur)
    bw, bh = W / z, H / z
    def box(x, y): return [round(min(max(x - bw / 2, 0), W - bw), 1), round(min(max(y - bh / 2, 0), H - bh), 1), round(bw, 1), round(bh, 1)]
    keys = [[0.0, "full"]]
    for cl in clusters:
        t0 = max(0.0, cl[0][0] - lead - ease); t_end = min(D, cl[-1][0] + hold)
        if t0 <= keys[-1][0]: t0 = keys[-1][0] + 0.05
        keys.append([round(t0, 3), "full"])
        for t, x, y in cl: keys.append([round(max(t0 + ease, t - 0.15), 3), box(x, y)])
        keys.append([round(t_end, 3), box(cl[-1][1], cl[-1][2])])
        keys.append([round(min(D, t_end + ease), 3), "full"])
    keys = [k for i, k in enumerate(keys) if i == 0 or k[0] > keys[i - 1][0]]
    return keys


# ------------------------------------------------------------------ face-following reframe (Shorts)
def head_track(src, pieces, smooth=30):
    """Head centre x (source px) for every scene frame of these spine pieces, smoothed (calm, no jitter)."""
    from . import touchup as T
    k = cache.key("headtrack1", src, [(p["a"], p["n"]) for p in pieces], smooth)
    pth = cache.path("probe", "htrack_" + k, "json")
    if os.path.exists(pth): return json.load(open(pth))
    W, H = size_of(src); xs = []
    for p in pieces:
        try: L = T.landmarks(src, p["a"], p["n"] / FPS, (0, 0, W, H))
        except Exception: L = np.full((p["n"], 478, 2), np.nan)
        cx = np.nanmean(L[:, FACE_OVAL_IDX, 0], axis=1) if L.shape[0] else np.zeros(0)
        cx = list(cx[: p["n"]]) + [np.nan] * max(0, p["n"] - len(cx))
        xs += cx
    xs = np.array(xs, np.float64); ok = ~np.isnan(xs)
    if not ok.any(): xs[:] = W / 2
    else: xs = np.interp(np.arange(len(xs)), np.nonzero(ok)[0], xs[ok])
    from scipy.ndimage import gaussian_filter1d
    xs = gaussian_filter1d(xs, smooth, mode="nearest")
    out = [round(float(x), 1) for x in xs]
    json.dump(out, open(pth, "w")); return out


FACE_OVAL_IDX = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
                 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
