"""Colour tools (Resolve's Color page, as numbers Claude can read): levels, clipping, colour cast, saturation, a
skin-tone check against the vectorscope skin line, shot matching (a grade that makes one shot look like another),
and waveform/vectorscope pictures to look at.

    report(path, t)                      -> levels, cast, saturation, clipping (+ skin if a face is found)
    skin(path, t)                        -> hue of his skin vs the skin line (degrees off), saturation, advice
    match(a, ta, b, tb)                  -> grade dict for color.grade / "grade" on a source or item: makes A look like B
    scope_image(path, t, out)            -> PNG: picture | waveform | vectorscope
All inputs are HLG BT.2020 (iPhone footage, Cutroom renders); SDR files are read as BT.709."""
import math, subprocess
import numpy as np
from . import color as C, frames as F

SKIN_LINE = 123.0        # vectorscope skin-tone line (I-line), degrees, measured counter-clockwise from +Cb


def _rgb(path, t, crop=None):
    from .assets import is_hlg
    hlg = is_hlg(path)
    x = F.read_rgb(path, t, 1, crop=crop, matrix="bt2020" if hlg else "bt709")[0]
    return x, hlg


def _display(x, hlg):
    """Display-referred sRGB (0..1) the way a viewer sees it (graphics white = 1)."""
    return np.clip(C.hlg_to_srgb(x.reshape(-1, 3)).reshape(x.shape), 0, 1) if hlg else x


def report(path, t, face=True):
    x, hlg = _rgb(path, t); d = _display(x, hlg)
    y = d @ np.array([0.2126, 0.7152, 0.0722])
    mx, mn = d.max(-1), d.min(-1); sat = np.where(mx > 0.02, (mx - mn) / np.maximum(mx, 1e-6), 0)
    neutral = sat < 0.12
    cast = (d[neutral].mean(0) - d[neutral].mean()) if neutral.sum() > 500 else np.zeros(3)
    out = dict(t=t, hdr=hlg,
               black=round(float(np.percentile(y, 1)) * 100, 1), mid=round(float(np.percentile(y, 50)) * 100, 1),
               white=round(float(np.percentile(y, 99)) * 100, 1),
               clipped_pct=round(float((x.max(-1) > 0.985).mean()) * 100, 2),        # at the top of the signal (true clipping)
               above_white_pct=round(float((mx > 0.995).mean()) * 100, 2),           # brighter than graphics white (HDR highlights) crushed_pct=round(float((mx < 0.01).mean()) * 100, 2),
               saturation=round(float(sat.mean()), 3),
               cast_rgb=[round(float(v) * 100, 2) for v in cast],
               cast=("warm" if cast[0] - cast[2] > 0.015 else "cool" if cast[2] - cast[0] > 0.015 else "neutral") +
                    (", green" if cast[1] - (cast[0] + cast[2]) / 2 > 0.012 else ", magenta" if (cast[0] + cast[2]) / 2 - cast[1] > 0.012 else ""))
    if face:
        try: out["skin"] = skin(path, t)
        except Exception as e: out["skin"] = f"no face ({str(e)[:60]})"
    return out


def _face_box(path, t):
    from . import touchup as T
    W, H = F.probe_wh(path)
    L = T.landmarks(path, t, 0.1, (0, 0, W, H))
    pts = L[~np.isnan(L).any(-1).any(-1)]
    if not len(pts): raise RuntimeError("no face found")
    p = pts[0]
    # cheeks + forehead: mediapipe points 50 (left cheek), 280 (right cheek), 10 (forehead), 152 (chin)
    xs = [p[50][0], p[280][0]]; y_top, y_chin = p[10][1], p[152][1]
    x0, x1 = min(xs), max(xs); h = y_chin - y_top
    return [int(x0) // 2 * 2, int(y_top + 0.25 * h) // 2 * 2, int(x1 - x0) // 2 * 2, int(0.35 * h) // 2 * 2]


def skin(path, t):
    """His skin tone vs the skin line: hue angle on the vectorscope, and how far off it is."""
    box = _face_box(path, t)
    x, hlg = _rgb(path, t, crop=box); d = _display(x, hlg).reshape(-1, 3)
    yv = d @ np.array([0.2126, 0.7152, 0.0722])
    keep = (yv > 0.15) & (yv < 0.92)
    d = d[keep] if keep.sum() > 100 else d
    r, g, b = d.mean(0)
    Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    cb, cr = (b - Y) / 1.8556, (r - Y) / 1.5748
    hue = math.degrees(math.atan2(cr, cb)) % 360
    off = hue - SKIN_LINE
    satv = math.hypot(cb, cr)
    advice = "on the skin line" if abs(off) < 5 else ("too red/magenta: add a little green (tint -) or cool it (temp -)" if off < 0
                                                      else "too yellow/green: add a little magenta (tint +) or warm it")
    if satv > 0.16: advice += "; skin is very saturated (orange/red look): lower saturation"
    elif satv < 0.05: advice += "; skin looks pale/grey: raise saturation a little"
    return dict(hue=round(hue, 1), off_deg=round(off, 1), saturation=round(satv, 3), box=box, advice=advice)


def _lin(path, t):
    x, hlg = _rgb(path, t)
    return C.hlg_inv_oetf(x) if hlg else C.srgb_eotf(x), hlg


def match(a, ta, b, tb, keep_sat=False):
    """Grade (exposure, temp, tint, saturation) that makes shot A look like shot B, from their light, colour of the
    neutral parts and saturation. Check it with report() on a render; it is a starting point, not magic."""
    la, _ = _lin(a, ta); lb, _ = _lin(b, tb)
    def stats(l):
        Y = l @ C.Y2020; mid = np.percentile(Y, 50)
        mx, mn = l.max(-1), l.min(-1); s = np.where(mx > 1e-3, (mx - mn) / np.maximum(mx, 1e-6), 0)
        neu = (s < 0.2) & (Y > np.percentile(Y, 20)) & (Y < np.percentile(Y, 95))
        rgb = l[neu].mean(0) if neu.sum() > 500 else l.reshape(-1, 3).mean(0)
        return mid, rgb / max(rgb.mean(), 1e-6), s.mean()
    ma, ca, sa = stats(la); mb, cb, sb = stats(lb)
    exposure = math.log2(max(mb, 1e-6) / max(ma, 1e-6))
    ratio = cb / ca                       # per-channel gain that moves A's neutrals onto B's
    # grade(): r*(1+.5t+.25ti), g*(1-.5ti), b*(1-.5t+.25ti)  ->  solve for t, ti from the ratios (normalised to g)
    r_, b_ = ratio[0] / ratio[1], ratio[2] / ratio[1]
    temp = float(np.clip((r_ - b_) / 1.0, -1, 1)); tint = float(np.clip(((r_ + b_) / 2 - 1) / 0.75, -1, 1))
    g = dict(exposure=round(float(np.clip(exposure, -2, 2)), 3), temp=round(temp, 3), tint=round(tint, 3))
    if not keep_sat: g["saturation"] = round(float(np.clip(sb / max(sa, 1e-6), 0.6, 1.5)), 3)
    return g


def scope_image(path, t, out, width=1280):
    """One frame + its waveform + vectorscope side by side (sRGB PNG) to look at."""
    from .assets import is_hlg
    tm = ("lut3d=file='%s'," % _hlg_to_srgb_lut()) if is_hlg(path) else ""
    fc = (f"[0:v]scale=in_color_matrix={'bt2020' if tm else 'bt709'}:in_range=tv,format=rgb48le,{tm}scale={width}:-2,format=rgb24,split=3[p][w][v];"
          f"[w]waveform=mode=column:intensity=0.06:graticule=green:flags=numbers+dots,scale={width - width * 9 // 32}:{width * 9 // 32},format=rgb24[ww];"
          f"[v]format=yuv444p,vectorscope=mode=color3:graticule=color:flags=name,scale={width * 9 // 32}:{width * 9 // 32},format=rgb24[vv];"
          f"[ww][vv]hstack[sc];[p][sc]vstack[o]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", path, "-filter_complex", fc, "-map", "[o]", "-frames:v", "1", out], check=True)
    return out


_LUT = None
def _hlg_to_srgb_lut(n=33):
    global _LUT
    if _LUT: return _LUT
    import os
    p = os.path.expanduser(f"~/VideoWork/studio-cache/luts/hlg_to_srgb_{n}.cube")
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        g = np.linspace(0, 1, n); b, gg, r = np.meshgrid(g, g, g, indexing="ij")
        o = np.clip(C.hlg_to_srgb(np.stack([r, gg, b], -1).reshape(-1, 3)), 0, 1)
        with open(p + ".tmp", "w") as f: f.write(f"LUT_3D_SIZE {n}\n"); np.savetxt(f, o, fmt="%.6f")
        os.replace(p + ".tmp", p)
    _LUT = p; return p
