"""Compile a window [f0, f1) of a resolved timeline into ONE ffmpeg filter graph (video only).

Every window is self-contained, so the renderer can split the video into chunks, render them in parallel, cache each by
content hash and join them without re-encoding (tested frame-exact). Working format inside the graph: yuv444p10le,
HLG BT.2020, constant 30 fps. Sources are put on the 30 fps grid by timestamp (-copyts + fps=30 on the item's own
time axis), so a variable-frame-rate screen recording can't stutter and chunk joins are exact.

Layers, bottom to top: base (camera / screen / graphic / still / broll, one at a time) -> face box (only when a scene or
item sets "pip": "bottom-left" | "bottom-right" | ...) -> layers (graphics, rings, captions) in list order."""
import math, os
from . import assets as A
from . import color as C
from .model import FPS, src_path


class Graph:
    def __init__(self):
        self.inputs, self.chains, self.n = [], [], 0

    def inp(self, args):
        self.inputs += [str(a) for a in args]; i = self.n; self.n += 1; return f"{i}:v"

    def add(self, s): self.chains.append(s)

    def lab(self, p="x"):
        self.n_lab = getattr(self, "n_lab", 0) + 1; return f"{p}{self.n_lab}"

    def script(self): return ";\n".join(self.chains)


W10 = "format=yuv444p10le"


def seek_args(t):
    """Fast + exact: seek ~1 s early and keep absolute timestamps; trims happen on the 30 fps grid."""
    return ["-ss", f"{max(0.0, t - 1.0):.3f}", "-copyts"]


def _source_frames(g, path, t0, speed, k0, k1, hw=True):
    """Frames k0..k1 of an item that starts at source time t0 and plays at `speed` (item time = (src - t0)/speed)."""
    v = g.inp([*(["-hwaccel", "videotoolbox"] if hw else []), *seek_args(t0 + k0 / FPS * speed), "-i", path])
    lb = g.lab("s")
    g.add(f"[{v}]setpts=(PTS-{t0:.6f}/TB)/{speed:.6f},fps={FPS}:round=near,trim=start={k0 / FPS:.6f}:end={k1 / FPS:.6f},setpts=PTS-STARTPTS[{lb}]")
    return lb


def _freeze(g, path, t, n, hw=True):
    v = g.inp([*seek_args(t), "-i", path])
    lb = g.lab("z")
    g.add(f"[{v}]setpts=PTS-{t:.6f}/TB,trim=start=0,setpts=PTS-STARTPTS,trim=end_frame=1,loop=loop={n}:size=1,setpts=N/{FPS}/TB,trim=end_frame={n}[{lb}]")
    return lb


# ------------------------------------------------------------------ geometry
def fit_rect(sw, sh, cw, ch, mode="fit", align="center"):
    """Where a sw x sh picture lands on a cw x ch canvas: (x, y, w, h) in canvas px. align: center | left | right."""
    k = min(cw / sw, ch / sh) if mode == "fit" else max(cw / sw, ch / sh)
    w, h = sw * k, sh * k
    x = {"left": 0.0, "right": cw - w}.get(align, (cw - w) / 2)
    return (x, (ch - h) / 2, w, h)


def _avoid(win, box_c, avoid, canvas, margin=60):
    """Shift a zoom window so the target box (canvas px) lands clear of the face box (canvas px)."""
    if not avoid: return win
    cw, ch = canvas; X, Y, w, h = win; z = cw / w
    bx, by, bw, bh = box_c
    ox, oy = (bx - X) * z, (by - Y) * z; ow_, oh_ = bw * z, bh * z
    ax, ay, aw, ah = avoid
    if not (ox < ax + aw and ox + ow_ > ax and oy < ay + ah and oy + oh_ > ay): return win
    # first try moving the content up (window down), then right (window left)
    dy = (oy + oh_) - (ay - margin)
    Y2 = min(max(Y + dy / z, 0), ch - h)
    oy2 = (by - Y2) * z
    if oy2 + oh_ <= ay - margin + 1 and oy2 >= 0: return (X, Y2, w, h)
    dx = (ax + aw + margin) - ox
    X2 = min(max(X - dx / z, 0), cw - w)
    return (X2, Y, w, h)


def view_keys(item, crop, canvas, avoid=None):
    """Normalised view keyframes for a screen/broll item: [(t, (x, y, w, h) window in CANVAS px, ease)]."""
    cw, ch = canvas
    full = (0.0, 0.0, cw, ch)
    v = item.get("view", "fit")
    if not isinstance(v, dict): return [(0.0, full, None)]
    fx, fy, fw, fh = fit_rect(crop[2], crop[3], cw, ch, item.get("fit", "fit"), item.get("align", "center"))
    k = fw / crop[2]
    def to_canvas(b):   # source px box -> canvas window with the canvas aspect, kept inside the picture
        x, y, w, h = b
        x, y = fx + (x - crop[0]) * k, fy + (y - crop[1]) * k; w, h = w * k, h * k
        pad = v.get("pad", 0.08)
        w2 = max(w * (1 + 2 * pad), h * (1 + 2 * pad) * cw / ch); w2 = min(w2, cw); h2 = w2 * ch / cw
        cx, cy = x + w / 2 + v.get("dx", 0) * k, y + h / 2 + v.get("dy", 0) * k
        X = min(max(cx - w2 / 2, min(fx, 0) if fx < 0 else 0), cw - w2); Y = min(max(cy - h2 / 2, 0), ch - h2)
        return _avoid((X, Y, w2, h2), (x, y, w, h), avoid, canvas)
    if "keys" in v:
        return [(t, full if b == "full" else to_canvas(b), v.get("ease_fn", "cubic")) for t, b in v["keys"]]
    hold, ease = v.get("hold", 0.4), v.get("ease", 0.8)
    if v.get("instant"): return [(0.0, to_canvas(v["box"]), None)]
    return [(0.0, full, None), (hold, full, None), (hold + ease, to_canvas(v["box"]), "cubic")]


def _ease_expr(u, fn):
    if fn == "spring": return f"min(1,1-(1+7.5*{u})*exp(-7.5*{u}))/0.9953"     # critically damped spring (camera feel)
    if fn == "cubic": return f"(1-pow(1-{u},3))"
    if fn == "inout": return f"({u}*{u}*(3-2*{u}))"
    return u


def perspective(keys, kf_off, canvas):
    """perspective filter (sub-pixel, cubic) for keyframed windows; `on` = output frame in this window."""
    if len(keys) == 1 and keys[0][1] == (0.0, 0.0, canvas[0], canvas[1]): return None
    if len(keys) == 1:
        x, y, w, h = keys[0][1]
        exprs = [f"{x:.3f}", f"{y:.3f}", f"{x + w:.3f}", f"{y:.3f}", f"{x:.3f}", f"{y + h:.3f}", f"{x + w:.3f}", f"{y + h:.3f}"]
    else:
        t = f"((on+{kf_off})/{FPS})"
        def comp(i):
            e = f"{keys[-1][1][i]:.3f}"
            for (ta, ba, _), (tb, bb, fn) in reversed(list(zip(keys[:-1], keys[1:]))):
                if tb <= ta: continue
                u = f"min(max(({t}-{ta:.4f})/{tb - ta:.4f},0),1)"
                seg = f"({ba[i]:.3f}+({bb[i] - ba[i]:.3f})*{_ease_expr(u, fn)})"
                e = f"if(lt({t},{tb:.4f}),{seg},{e})"
            return f"if(lt({t},{keys[0][0]:.4f}),{keys[0][1][i]:.3f},{e})"
        X, Y, Wd, Hd = comp(0), comp(1), comp(2), comp(3)
        exprs = [X, Y, f"({X}+{Wd})", Y, X, f"({Y}+{Hd})", f"({X}+{Wd})", f"({Y}+{Hd})"]
    ks = ["x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"]
    return "perspective=" + ":".join(f"{k}='{e}'" for k, e in zip(ks, exprs)) + ":interpolation=cubic:eval=frame"


def map_box(item, crop, canvas, t_item, avoid=None):
    """Source px box -> canvas px box at item time t (rings follow the view)."""
    keys = view_keys(item, crop, canvas, avoid)
    cw, ch = canvas
    # window at t (linear search; same easing as the filter)
    win = keys[0][1]
    for (ta, ba, _), (tb, bb, fn) in zip(keys[:-1], keys[1:]):
        if t_item >= tb: win = bb; continue
        if t_item >= ta and tb > ta:
            u = (t_item - ta) / (tb - ta)
            e = (1 - (1 - u) ** 3 if fn == "cubic" else min(1, (1 - (1 + 7.5 * u) * math.exp(-7.5 * u)) / 0.9953) if fn == "spring"
                 else u * u * (3 - 2 * u) if fn == "inout" else u)
            win = tuple(a + (b - a) * e for a, b in zip(ba, bb))
        break
    fx, fy, fw, fh = fit_rect(crop[2], crop[3], cw, ch, item.get("fit", "fit"), item.get("align", "center")); k = fw / crop[2]
    def m(b):
        x, y, w, h = b
        X, Y = fx + (x - crop[0]) * k, fy + (y - crop[1]) * k
        z = cw / win[2]
        return ((X - win[0]) * z, (Y - win[1]) * z, w * k * z, h * k * z)
    return m


# ------------------------------------------------------------------ base items
def _canvas(R):
    p = R["profile"]
    if p.get("canvas"): return tuple(p["canvas"])
    return (3840, 2160) if p["w"] > p["h"] else (1080, 1920)


def _out_size(R): return R["profile"]["w"], R["profile"]["h"]


def ramp_segments(r, D, cover=None, steps=6):
    """[(output seconds, speed)] for a speed ramp over D output seconds: `hold` s at 1x, `ease` s ramping up in
    `steps` steps (smoothstep), the middle at `speed`, then back down. With `cover` (source seconds to get through),
    the top speed is solved so the ramp covers exactly that much source."""
    hold, ease = r.get("hold", 0.4), r.get("ease", 0.6)
    mid = max(0.0, D - 2 * hold - 2 * ease)
    def build(S):
        sg = [(hold, 1.0)]
        for i in range(steps):
            u = (i + 0.5) / steps; sg.append((ease / steps, 1 + (S - 1) * u * u * (3 - 2 * u)))
        sg.append((mid, S))
        for i in range(steps):
            u = 1 - (i + 0.5) / steps; sg.append((ease / steps, 1 + (S - 1) * u * u * (3 - 2 * u)))
        sg.append((max(0.0, D - hold - 2 * ease - mid), 1.0))
        return [x for x in sg if x[0] > 1e-6]
    if cover is None: return build(r.get("speed", 4.0))
    lo, hi = 1.0, 200.0
    for _ in range(60):
        S = (lo + hi) / 2; c = sum(d * sp for d, sp in build(S))
        lo, hi = (S, hi) if c < cover else (lo, S)
    return build((lo + hi) / 2)


def merge_blur_boxes(boxes, max_boxes=8, gap=40, join=0.6):
    """Fewer, bigger privacy boxes: scrolling or sped-up text gives one OCR box per sample (dozens), and each box is a
    full-frame split in the filter graph, which stalls ffmpeg. Boxes that touch in space (within `gap` px) and in time
    (within `join` s) become one union box; if more than `max_boxes` remain, the pair whose union adds the least area
    is merged until it fits. Merging only ever blurs more, never less."""
    bs = [dict(box=list(b["box"]), **{"from": b.get("from", -1e6)}, to=b.get("to", 1e6)) for b in boxes]
    def union(a, b):
        x0, y0 = min(a["box"][0], b["box"][0]), min(a["box"][1], b["box"][1])
        x1 = max(a["box"][0] + a["box"][2], b["box"][0] + b["box"][2]); y1 = max(a["box"][1] + a["box"][3], b["box"][1] + b["box"][3])
        return dict(box=[x0, y0, x1 - x0, y1 - y0], **{"from": min(a["from"], b["from"])}, to=max(a["to"], b["to"]))
    def touch(a, b):
        (ax, ay, aw, ah), (bx, by, bw, bh) = a["box"], b["box"]
        near = ax - gap <= bx + bw and bx - gap <= ax + aw and ay - gap <= by + bh and by - gap <= ay + ah
        return near and a["from"] - join <= b["to"] and b["from"] - join <= a["to"]
    changed = True
    while changed:
        changed = False
        for i in range(len(bs)):
            for j in range(i + 1, len(bs)):
                if touch(bs[i], bs[j]):
                    bs[i] = union(bs[i], bs.pop(j)); changed = True; break
            if changed: break
    area = lambda b: b["box"][2] * b["box"][3]
    while len(bs) > max_boxes:
        _, i, j = min((area(union(bs[i], bs[j])) - area(bs[i]) - area(bs[j]), i, j) for i in range(len(bs)) for j in range(i + 1, len(bs)))
        bs[i] = union(bs[i], bs.pop(j))
    return bs


def _inverse_time(tmap, s, D):
    """Item time whose source time is s (tmap is increasing over [0, D]); clamps to the ends."""
    lo, hi = 0.0, D
    if s <= tmap(lo): return lo
    if s >= tmap(hi): return hi
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if tmap(mid) < s else (lo, mid)
    return (lo + hi) / 2


def screen_post(g, R, sc, tl, item, lb, path, srcinfo, k0, k1, tmap):
    """Frames of a recording -> privacy blur (source px) -> sRGB to HLG (+ dimming) -> fit on the canvas -> zoom ->
    his mouse pointer. Shared by screen, broll and angle shots and by split-screen panels."""
    n = k1 - k0
    cw, ch = _canvas(R); ow, oh = _out_size(R); s = ow / cw
    crop = item.get("crop") or srcinfo.get("crop") or A.full_crop(path)
    auto = []
    ab = item.get("auto_blur", srcinfo.get("auto_blur"))
    if ab:   # privacy: blur whatever OCR finds (emails, IPs, phones, keys, deny list); {"only": [words]} = just those words
        from . import analyze
        deny, pats = (ab["only"], False) if isinstance(ab, dict) and ab.get("only") else (tl.get("privacy_deny", []), True)
        D = (item["f1"] - item["f0"]) / FPS
        s0, s1 = tmap(0), tmap(max(0, D - 1 / FPS))
        if s1 - s0 > 0.05:
            # box times are source seconds after s0; map them through the item's own time map (exact on speed ramps)
            pad = 0.25
            for bx in analyze.privacy_boxes(path, s0, s1 + 0.01, deny=deny, patterns=pats):
                auto.append(dict(box=bx["box"], **{"from": max(0.0, _inverse_time(tmap, s0 + bx["from"], D) - pad)},
                                 to=_inverse_time(tmap, s0 + bx["to"], D) + pad))
        else:
            for bx in analyze.privacy_boxes(path, s0, s0 + 0.01, deny=deny, patterns=pats):
                auto.append(dict(box=bx["box"]))
        auto = merge_blur_boxes(auto)
    for bl in (item.get("blur") or []) + (srcinfo.get("blur") or []) + auto:
        box = bl["box"] if isinstance(bl, dict) else bl
        x, y, w, h = [int(round(v)) for v in box]
        # keep the box inside the visible part of the recording (a merged box can grow past the edge)
        x0, y0 = max(x, crop[0]), max(y, crop[1]); x1, y1 = min(x + w, crop[0] + crop[2]), min(y + h, crop[1] + crop[3])
        if x1 - x0 < 4 or y1 - y0 < 4: continue
        x, y, w, h = x0 // 2 * 2, y0 // 2 * 2, (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2
        r = max(2, min(40, h // 4, w // 4)); cr = max(1, min(r, h // 4, w // 4) // 2 - 1)   # chroma planes are half size
        b1, b2, b3 = g.lab("ba"), g.lab("bb"), g.lab("bc")
        en = ""
        if isinstance(bl, dict) and ("from" in bl or "to" in bl):
            ta = (bl.get("from", 0) * FPS - k0) / FPS; tb = (bl.get("to", 1e6) * FPS - k0) / FPS
            en = f":enable='between(t,{ta:.3f},{tb:.3f})'"
        g.add(f"[{lb}]split[{b1}][{b2}];[{b2}]crop={w}:{h}:{x}:{y},boxblur=lr={r}:lp=3:cr={cr}:cp=3[{b3}];[{b1}][{b3}]overlay={x}:{y}{en}[{b3}o]")
        lb = f"{b3}o"
    if item.get("auto_zoom") and not isinstance(item.get("view"), dict):
        D = (item["f1"] - item["f0"]) / FPS
        keys = A.auto_zoom_keys(dict(item, crop=crop), path, D, tmap, item["auto_zoom"] if isinstance(item["auto_zoom"], dict) else {})
        if keys: item = dict(item, view={"keys": keys, "ease_fn": (item["auto_zoom"] if isinstance(item["auto_zoom"], dict) else {}).get("ease_fn", "spring"), "pad": 0})
    if item.get("stabilize"):
        o0 = g.lab("dsk"); g.add(f"[{lb}]deshake=rx=32:ry=32[{o0}]"); lb = o0
    white = A.dim_level(item, path, tmap(0), crop, R["kit"])
    fx, fy, fw, fh = fit_rect(crop[2], crop[3], cw, ch, item.get("fit", "fit"), item.get("align", "center"))
    W_, H_ = int(round(fw * s / 2) * 2), int(round(fh * s / 2) * 2)
    out = g.lab("sc")
    conv = A.sdr_to_hlg_chain(white, A.matrix_of(path), R["kit"]) if not A.is_hlg(path) else W10
    X, Y = int(round(fx * s)), int(round(fy * s))
    if fw <= cw + 0.5 and fh <= ch + 0.5:
        bgi = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.1:.3f}", "-i", A.bg_still(R)])
        g.add(f"[{lb}]crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},scale={W_}:{H_}:flags=lanczos,{conv}[{out}s];"
              f"[{bgi}]{A.png16_to_yuv()},trim=end_frame={n}[{out}b];[{out}b][{out}s]overlay={X}:{Y}:format=yuv444p10[{out}p]")
    else:
        g.add(f"[{lb}]crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},scale={W_}:{H_}:flags=lanczos,{conv},crop={ow}:{oh}:{-X}:{-Y}[{out}p]")
    pp = perspective([(t, tuple(v * s for v in b), fn) for t, b, fn in view_keys(item, crop, (cw, ch), A.pip_rect(R, sc, tl, item))], k0, (ow, oh))
    gr = item.get("grade") or srcinfo.get("grade")
    g.add(f"[{out}p]{pp + ',' if pp else ''}{W10}{',' + C.grade_chain(gr) if gr else ''},setsar=1[{out}]")
    for rt in (item.get("retype") or []):        # re-type pasted text in the app's own box, letter by letter
        out = retype_overlay(g, R, sc, tl, item, out, path, crop, rt, k0, k1, tmap, white)
    if item.get("cursor") and "source" in item:
        cp = A.cursor_overlay(item, path, crop, R, sc, tl, tmap)
        if cp:
            v = g.inp(["-ss", f"{k0 / FPS:.4f}", "-i", cp]); o2 = g.lab("cr")
            g.add(f"[{v}]setpts=PTS-STARTPTS,format=yuva444p10le[{o2}i];[{out}][{o2}i]overlay=0:0:format=yuv444p10:eof_action=pass,trim=end_frame={n}[{o2}]")
            return o2
    return out


SPLITS = {   # panel rects as fractions of the canvas (x, y, w, h), before the gap
    "lr": [(0, 0, 0.5, 1), (0.5, 0, 0.5, 1)], "tb": [(0, 0, 1, 0.5), (0, 0.5, 1, 0.5)],
    "3": [(0, 0, 1 / 3, 1), (1 / 3, 0, 1 / 3, 1), (2 / 3, 0, 1 / 3, 1)], "grid": [(0, 0, 0.5, 0.5), (0.5, 0, 0.5, 0.5), (0, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5)],
    "main-side": [(0, 0, 0.68, 1), (0.68, 0, 0.32, 1)],
}


def split_panels(item, ow, oh):
    lay = item.get("layout", "lr" if ow > oh else "tb")
    rects = item.get("rects") or SPLITS[lay]
    gap = item.get("gap", 24) * ow / (3840 if ow > oh else 1080); top = item.get("top_pad", 0) * oh
    out = []
    for (x, y, w, h) in rects[: len(item["panels"])]:
        X, Y, Wd, Hd = x * ow + gap / 2, top + y * (oh - top) + gap / 2, w * ow - gap, h * (oh - top) - gap
        out.append([int(X) // 2 * 2, int(Y) // 2 * 2, int(Wd) // 2 * 2, int(Hd) // 2 * 2])
    return out


STAGE_REST = dict(ry=-7.0, rx=2.5, s=1.0, dx=0.0, dy=0.0)
STAGE_ENTER = dict(ry=-30.0, rx=12.0, s=0.72, dx=160.0, dy=140.0)


def stage_pose(st, t, t_float=None):
    """Window pose at item time t: spring moves between poses + a slow float (degrees, scale, canvas px)."""
    def spring(u): return 0.0 if u <= 0 else min(1.0, (1 - (1 + 7.0 * u) * math.exp(-7.0 * u)) / 0.9927)
    rest = dict(STAGE_REST, **{k: v for k, v in st.items() if k in STAGE_REST})
    pose = dict(STAGE_ENTER if st.get("enter", True) else rest)
    moves = ([dict(rest, t=0.0, d=st.get("enter_d", 1.2))] if st.get("enter", True) else [])
    for m in sorted(st.get("moves", []), key=lambda m: m["t"]): moves.append(dict(rest, **m))
    for m in moves:
        u = (t - m["t"]) / m.get("d", 0.9)
        if u <= 0: break
        e = spring(u)
        pose = {k: pose[k] + (m[k] - pose[k]) * e for k in STAGE_REST}
    fl = st.get("float", 1.0); tf = t if t_float is None else t_float     # float runs on scene time: no jump between shots
    pose["ry"] += fl * 1.1 * math.sin(2 * math.pi * tf / 9.0)
    pose["rx"] += fl * 0.7 * math.sin(2 * math.pi * tf / 7.0 + 1.0)
    pose["dy"] += fl * 10 * math.sin(2 * math.pi * tf / 6.0 + 2.0)
    return pose


def stage_corners(pose, win, out_wh):
    """Source points (on the padded canvas) that land on the output corners: perspective 'sense=source'."""
    import numpy as np, cv2
    x, y, w, h = win; cx, cy = x + w / 2, y + h / 2; f = 2.2 * max(w, h)
    ry, rx = math.radians(pose["ry"]), math.radians(pose["rx"])
    Ry = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    src = np.float32([[x, y], [x + w, y], [x, y + h], [x + w, y + h]])
    dst = []
    for px, py in src:
        P = Rx @ Ry @ np.array([(px - cx) * pose["s"], (py - cy) * pose["s"], 0.0])
        dst.append([cx + pose["dx"] + f * P[0] / (f + P[2]), cy + pose["dy"] + f * P[1] / (f + P[2])])
    H = cv2.getPerspectiveTransform(np.float32(dst), src)       # output -> source
    ow, oh = out_wh
    return cv2.perspectiveTransform(np.float32([[[0, 0], [ow, 0], [0, oh], [ow, oh]]]), H)[0]


def render_stage(g, R, sc, item, k0, k1, tl, cam_full):
    """A screen recording as a floating window on an animated backdrop: rounded corners, soft shadow, 3D tilt that
    swings in on a spring, slow float, and poses on cues ("stage": {"rect", "ry", "rx", "moves": [{"t", "ry", "s", ...}],
    "backdrop", "enter", "radius"}). Zoom views, pointer, dimming all still work inside the window."""
    import numpy as np
    st = item["stage"] if isinstance(item["stage"], dict) else {}
    n = k1 - k0; cw, ch = _canvas(R); ow, oh = _out_size(R); s = ow / cw
    path = src_path(tl, item["source"]) if "source" in item else os.path.expanduser(item["path"])
    crop = item.get("crop") or tl["sources"].get(item.get("source"), {}).get("crop") or A.full_crop(path)
    bx, by, bw, bh = st.get("rect", [1800, 130, 1900, 1900])
    wx, wy, ww, wh = fit_rect(crop[2], crop[3], bw, bh, "fit", "center")
    win = [(bx + wx) * s, (by + wy) * s, ww * s, wh * s]
    W2, H2 = int(round(win[2] / 2) * 2), int(round(win[3] / 2) * 2); win[2], win[3] = W2, H2
    X, Y = int(round(win[0])), int(round(win[1])); win[0], win[1] = X, Y
    R2 = dict(R, profile=dict(R["profile"], w=W2, h=H2, canvas=[W2 / s, H2 / s]))
    inner = dict(item, stage=None, pip="none", align="center", fit="fit")
    flat = render_base(g, R2, sc, inner, k0, k1, tl, cam_full)
    # backdrop (animated, HLG like every graphic)
    bgp = A.graphic(st.get("backdrop", "StageBackdrop"), st.get("backdrop_props", {}), item["f1"] - item["f0"], R, alpha=False)
    bgi = g.inp(["-ss", f"{k0 / FPS:.4f}", "-i", bgp]); bg = g.lab("sbg")
    g.add(f"[{bgi}]setpts=PTS-STARTPTS,fps={FPS},trim=end_frame={n},scale={ow}:{oh}:flags=lanczos,{W10},setsar=1[{bg}]")
    # perspective expressions: a flat sum of linear pieces (ffmpeg's expression parser fails past ~80 terms -> at most 60)
    step = max(2, -(-(k1 - k0) // 60)); ks = list(range(k0, k1 + step, step)); cs = [stage_corners(stage_pose(st, k / FPS, (item["f0"] + k) / FPS), win, (ow, oh)) for k in ks]
    def expr(ci, cj):
        terms = []
        for (ka, a), (kb, b) in zip(zip(ks, cs), zip(ks[1:], cs[1:])):
            va, vb = float(a[ci][cj]), float(b[ci][cj]); fa, fb = ka - k0, kb - k0
            terms.append(f"gte(on,{fa})*lt(on,{fb})*({va:.2f}+{(vb - va) / (fb - fa):.4f}*(on-{fa}))")
        return "+".join(terms) or f"{float(cs[0][ci][cj]):.2f}"
    pers = "perspective=" + ":".join(f"{k}='{expr(i, j)}'" for (i, j), k in zip([(c, d) for c in range(4) for d in range(2)],
                                     ["x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"])) + ":interpolation=cubic:eval=frame"
    # motion blur where the window moves fast (corner speed > ~4 px/frame at 4K): blend 3 frames 1:2:1
    vel = [float(np.abs(b_ - a_).max()) / step for a_, b_ in zip(cs[:-1], cs[1:])]
    fast = [ks[i] - k0 for i, v_ in enumerate(vel) if v_ > 4 * s]
    mblur = ""
    if fast and st.get("motion_blur", True):
        spans, a_ = [], fast[0]; prev = a_
        for f_ in fast[1:]:
            if f_ - prev > step: spans.append((a_, prev + step)); a_ = f_
            prev = f_
        spans.append((a_, prev + step))
        en_mb = "+".join(f"between(n,{x0},{x1})" for x0, x1 in spans[:20])
        mblur = f",tmix=frames=3:weights='1 2 1':enable='{en_mb}'"
    rad = st.get("radius", 36) * s
    mp = A.rounded_mask(W2, H2, rad)
    mi = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.1:.3f}", "-i", mp])
    o = g.lab("stg")
    sh_off, sh_blur = min(int(50 * s), oh - Y - H2), max(4, int(60 * s))
    g.add(f"[{mi}]trim=end_frame={n},setpts=PTS-STARTPTS,format=gray,split=2[{o}m1][{o}m2];"
          f"[{flat}]format=yuva444p10le[{o}f];[{o}f][{o}m1]alphamerge,pad={ow}:{oh}:{X}:{Y}:color=black@0,{pers}{mblur}[{o}w];"
          f"[{o}m2]pad={ow}:{oh}:{X}:{Y + sh_off}:color=black,gblur=sigma={sh_blur},lut=y='val*0.62',{pers}[{o}sa];"   # shadow warped as one grey plane (memory)
          f"color=c=black:s={ow}x{oh}:r={FPS}:d={n / FPS + 0.1:.3f},format=yuva444p10le,trim=end_frame={n}[{o}sk];"
          f"[{o}sk][{o}sa]alphamerge[{o}s];"
          f"[{bg}][{o}s]overlay=0:0:format=yuv444p10[{o}b];[{o}b][{o}w]overlay=0:0:format=yuv444p10,{W10},setsar=1[{o}]")
    return o


def retype_overlay(g, R, sc, tl, item, lab, path, crop, rt, k0, k1, tmap, white):
    """"retype": [{"at": item seconds, "box": [x,y,w,h] source px | {"ocr": "first words", "to": "last words"},
    "done_at": source seconds when the full text is on screen (default: the source time at "at" + 0.4),
    "cps": 28, "fast": 3 (long text speeds up in the middle)}]. The box is covered with the app's background colour and
    the text is typed in, in its own colour, line by line where OCR found it; then the real recording takes over."""
    import numpy as np
    from . import ocr as OCR, frames as F
    ow, oh = _out_size(R); cw, ch = _canvas(R); s = ow / cw
    at = float(rt.get("at", 0.0)); f_at = int(round(at * FPS))
    t_done = float(rt.get("done_at", tmap(at) + 0.4))
    box = rt["box"]
    if isinstance(box, dict):
        box = OCR.find_box(path, t_done, box["ocr"], box.get("to"), half=box.get("half"), pad=box.get("pad", 10))
    bx, by, bw, bh = [int(v) for v in box]
    lines = [l for l in OCR.lines_at(path, t_done) if l[0] >= bx - 4 and l[1] >= by - 4 and l[0] + l[2] <= bx + bw + 4 and l[1] + l[3] <= by + bh + 4]
    if not lines: return lab
    # reading order: rows top to bottom (lines whose centres are within half a line height are one row), then left to right
    hmed = float(np.median([l[3] for l in lines]))
    lines.sort(key=lambda l: l[1] + l[3] / 2)
    rows, cur = [], [lines[0]]
    for l in lines[1:]:
        if abs((l[1] + l[3] / 2) - (cur[-1][1] + cur[-1][3] / 2)) < hmed * 0.5: cur.append(l)
        else: rows.append(cur); cur = [l]
    rows.append(cur)
    lines = [l for r in rows for l in sorted(r, key=lambda l: l[0])]
    # the app's colours: background = the box border, text = the pixels furthest from it
    rgb = F.read_rgb(path, t_done, 1, crop=[bx, by, bw, bh], matrix="bt709")[0]
    edge = np.concatenate([rgb[:3].reshape(-1, 3), rgb[-3:].reshape(-1, 3), rgb[:, :3].reshape(-1, 3), rgb[:, -3:].reshape(-1, 3)])
    bg = np.median(edge, 0); dist = np.abs(rgb - bg).sum(-1); fg = np.median(rgb[dist > np.percentile(dist, 97)], 0)
    to255 = lambda c: [int(round(float(v) * 255)) for v in c]
    props = dict(lines=[dict(text=l[4], x=round(l[0] - bx, 1), y=round(l[1] + l[3] / 2 - hmed / 2 - by, 1), h=round(hmed, 1)) for l in lines],   # one text size
                 bg=to255(bg), fg=to255(fg), at=0.0, cps=rt.get("cps", 28), fast=rt.get("fast", 3), _alpha=False)
    total = sum(len(l[4]) + 1 for l in lines); cps = rt.get("cps", 28); fast = rt.get("fast", 3)
    edge_c = min(60, total / 3); dur = 2 * edge_c / cps + max(0, total - 2 * edge_c) / (cps * fast) + rt.get("hold", 0.25)
    n_all = int(round(dur * FPS))
    a, b = max(k0, f_at), min(k1, f_at + n_all)
    if b <= a: return lab
    # where the box sits on the canvas at that moment (follows the shot's zoom at the start of the typing)
    m = map_box(item, crop, (cw, ch), at + 0.05, A.pip_rect(R, sc, tl, item) if item.get("pip", "none") != "none" else None)
    X, Y, Wd, Hd = [v * s for v in m([bx, by, bw, bh])]
    Wd, Hd = max(2, int(round(Wd / 2) * 2)), max(2, int(round(Hd / 2) * 2))
    R2 = dict(R, profile=dict(R["profile"], w=Wd, h=Hd), kit=dict(R["kit"], graphics_white=white))     # same dimming as the screen
    gp = A.graphic("TypeOn", props, n_all, R2, alpha=True, design=bw)
    v = g.inp(["-ss", f"{(a - f_at) / FPS:.4f}", "-i", gp]); o = g.lab("rty")
    st = a - k0
    g.add(f"[{v}]setpts=PTS-STARTPTS+{st / FPS:.4f}/TB,format=yuva444p10le[{o}i];"
          f"[{lab}][{o}i]overlay={int(round(X))}:{int(round(Y))}:format=yuv444p10:eof_action=pass:enable='between(n,{st},{st + (b - a) - 1})'[{o}]")
    return o


def render_base(g, R, sc, item, k0, k1, tl, cam_full):
    """Returns the label of frames k0..k1 (item time) of a base item, on the canvas, yuv444p10 HLG."""
    kind = item["kind"]; n = k1 - k0
    cw, ch = _canvas(R)
    ow, oh = _out_size(R); s = ow / cw
    if kind == "camera":
        return cam_full(item["f0"] + k0, item["f0"] + k1)
    if kind in ("slowmo", "hold"):
        from . import interp
        sp_ = src_path(tl, item["source"]) if "source" in item else os.path.expanduser(item["path"])
        D = (item["f1"] - item["f0"]) / FPS
        clip = (interp.slowmo(sp_, item["from"], item["from"] + D / item.get("factor", 2.0), item.get("factor", 2.0)) if kind == "slowmo"
                else interp.extend(sp_, item.get("at_src", item.get("from", 0.0)), D + 0.2, push=item.get("push", 0.02)))
        inner = {k: v for k, v in item.items() if k not in ("source", "from", "to", "factor", "kind")}
        return render_base(g, R, sc, dict(inner, kind="broll", path=clip, **{"from": 0.0}), k0, k1, tl, cam_full)
    if kind in ("broll", "screen") and item.get("stabilize") == "vidstab" and A.FFMPEG_FULL:
        # two-pass vid.stab on just the stretch this shot uses (cached), then the shot plays the steady copy
        sp_ = src_path(tl, item["source"]) if "source" in item else os.path.expanduser(item["path"])
        D = (item["f1"] - item["f0"]) / FPS * item.get("speed", 1.0)
        stab = A.stabilized(sp_, item.get("from", 0.0), D + 0.5, item.get("smooth", 15))
        inner = {k: v for k, v in item.items() if k not in ("source", "stabilize")}
        return render_base(g, R, sc, dict(inner, path=stab, **{"from": 0.0}), k0, k1, tl, cam_full)
    if kind in ("screen", "angle") and item.get("stage"):
        return render_stage(g, R, sc, item, k0, k1, tl, cam_full)
    if kind in ("screen", "broll", "angle"):
        path = src_path(tl, item["source"]) if "source" in item else os.path.expanduser(item["path"])
        srcinfo = tl["sources"].get(item.get("source"), {}) if "source" in item else {}
        D = (item["f1"] - item["f0"]) / FPS
        if kind == "angle":
            # multicam: this recording follows the spine's own cuts (synced by sound: this time = spine time - offset)
            off = srcinfo.get("offset", 0.0) + item.get("nudge", 0.0)
            parts, f_a, f_b = [], item["f0"] + k0, item["f0"] + k1
            for pc in sc["pieces"]:
                a0, a1 = max(f_a, pc["f0"]), min(f_b, pc["f0"] + pc["n"])
                if a1 > a0: parts.append(_source_frames(g, path, pc["a"] - off, 1.0, a0 - pc["f0"], a1 - pc["f0"]))
            lb = g.lab("ag")
            g.add("".join(f"[{x}]" for x in parts) + f"concat=n={len(parts)}:v=1:a=0[{lb}]" if len(parts) > 1 else f"[{parts[0]}]null[{lb}]")
            def tmap(tau, f0_=item["f0"]):
                f = f0_ + int(round(tau * FPS))
                pc = next((q for q in sc["pieces"] if q["f0"] <= f < q["f0"] + q["n"]), sc["pieces"][-1])
                return pc["a"] - off + (f - pc["f0"]) / FPS
        elif item.get("ramp"):
            # speed ramp: normal speed at both ends, eases up to a fast middle and back (no hard cut through a wait)
            a = item.get("from", 0.0); segs = ramp_segments(item["ramp"], D, (item["to"] - a) if item.get("to") is not None else None)
            parts, t_out, t_src = [], 0.0, a
            for dur_o, sp_ in segs:
                f_a, f_b = int(round(t_out * FPS)), int(round((t_out + dur_o) * FPS))
                lo, hi = max(k0, f_a), min(k1, f_b)
                if hi > lo: parts.append(_source_frames(g, path, t_src - f_a / FPS * sp_, sp_, lo, hi))
                t_out += dur_o; t_src += dur_o * sp_
            lb = g.lab("rmp")
            g.add("".join(f"[{x}]" for x in parts) + f"concat=n={len(parts)}:v=1:a=0[{lb}]" if len(parts) > 1 else f"[{parts[0]}]null[{lb}]")
            def tmap(tau, segs=segs, a=a):
                t_o, t_s = 0.0, a
                for d_, sp_ in segs:
                    if tau <= t_o + d_: return t_s + (tau - t_o) * sp_
                    t_o += d_; t_s += d_ * sp_
                return t_s
        else:
            a = item.get("from", 0.0)
            speed = (item["to"] - a) / D if item.get("to") is not None else item.get("speed", 1.0)
            if item.get("reverse"):
                nall = item["f1"] - item["f0"]
                full = _source_frames(g, path, a, speed, 0, nall); lb = g.lab("rev")
                g.add(f"[{full}]reverse,trim=start_frame={k0}:end_frame={k1},setpts=PTS-STARTPTS[{lb}]")
                tmap = (lambda tau, a=a, sp_=speed, Dn=nall / FPS: a + (Dn - tau) * sp_)
            else:
                lb = _freeze(g, path, a, n) if item.get("freeze") else _source_frames(g, path, a, speed, k0, k1)
                tmap = (lambda tau, a=a: a) if item.get("freeze") else (lambda tau, a=a, sp_=speed: a + tau * sp_)
        return screen_post(g, R, sc, tl, item, lb, path, srcinfo, k0, k1, tmap)
    if kind == "graphic":
        props = dict(item.get("props", {}))
        if item.get("start_at"): props["_t0"] = item["start_at"]
        p = A.graphic(item["template"], props, item["f1"] - item["f0"], R, alpha=False, layout=item.get("layout"), design=item.get("design"))
        v = g.inp(["-ss", f"{k0 / FPS:.4f}", "-i", p])
        out = g.lab("gx")
        g.add(f"[{v}]setpts=PTS-STARTPTS,fps={FPS},trim=end_frame={n},scale={ow}:{oh}:flags=lanczos,{W10},setsar=1[{out}]")
        return out
    if kind == "still":
        p = A.still_hlg(os.path.expanduser(item["path"]), _out_size(R), R["kit"], fit=item.get("fit", "fit"))
        v = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.1:.3f}", "-i", p])
        out = g.lab("st")
        g.add(f"[{v}]trim=end_frame={n},setpts=PTS-STARTPTS,{A.png16_to_yuv()},setsar=1[{out}]")
        return out
    if kind == "split":
        # side by side / top-bottom / grid: each panel is any base item (screen, angle, graphic, still, broll, camera)
        rects = split_panels(item, ow, oh)
        bgi = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.1:.3f}", "-i", A.bg_still(R)])
        o = g.lab("spl"); last = f"{o}bg"
        g.add(f"[{bgi}]{A.png16_to_yuv()},trim=end_frame={n}[{last}]")
        for pi, (panel, (x, y, w, h)) in enumerate(zip(item["panels"], rects)):
            R2 = dict(R, profile=dict(R["profile"], w=w, h=h, canvas=(w, h)))
            inner = dict(panel, f0=item["f0"], f1=item["f1"], pip="none")
            if panel["kind"] == "camera":
                lab = cam_full(item["f0"] + k0, item["f0"] + k1)
                sinfo = tl["sources"][sc["source_id"]]
                cx, cy, cw2, ch2 = A.face_crop(sc["src"], sinfo, w / h)
                ow0, oh0 = ow, oh
                pl = g.lab("pc"); g.add(f"[{lab}]scale={A.size_of(sc['src'])[0]}:{A.size_of(sc['src'])[1]},crop={cw2}:{ch2}:{cx}:{cy},scale={w}:{h}:flags=lanczos[{pl}]")
                lab = pl
            else:
                lab = render_base(g, R2, sc, inner, k0, k1, tl, None)
            mk = A.rounded_mask(w, h, item.get("radius", 28) * ow / 3840 if ow > oh else item.get("radius", 28))
            mi = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.1:.3f}", "-i", mk])
            nl = g.lab("sp")
            g.add(f"[{lab}]format=yuva444p10le[{nl}f];[{mi}]format=gray10le[{nl}m];[{nl}f][{nl}m]alphamerge[{nl}a];[{last}][{nl}a]overlay={x}:{y}:format=yuv444p10[{nl}]")
            last = nl
            if item.get("labels") and pi < len(item["labels"]) and item["labels"][pi]:
                kd = ow / (1080 if oh > ow * 1.2 else 1920)
                lp = A.graphic("Pill", dict(text=item["labels"][pi], x=round((x + w / 2) / kd, 1), y=round((y + h - 60 * oh / 2160) / kd, 1), size=30, fade=False),
                               item["f1"] - item["f0"], R, alpha=True)
                v = g.inp(["-ss", f"{k0 / FPS:.4f}", "-i", lp]); nl2 = g.lab("spl")
                g.add(f"[{v}]setpts=PTS-STARTPTS,format=yuva444p10le[{nl2}i];[{last}][{nl2}i]overlay=0:0:format=yuv444p10:eof_action=pass[{nl2}]"); last = nl2
        g.add(f"[{last}]trim=end_frame={n},{W10},setsar=1[{o}]")
        return o
    if kind == "stack":
        # Shorts layout: content edge to edge on top, his camera full size below (the frame slides down, never shrinks).
        # band > 0: a solid black band between them for the captions (header, band and camera like the house Shorts);
        # band = 0: the camera starts right under the content with a soft seam.
        D = int(round(item.get("top", 0.45) * oh / 2) * 2)
        B = int(round(item.get("band", 0) * oh / 2) * 2)
        o = g.lab("sk")
        sinfo = tl["sources"][sc["source_id"]]; SW, SH = A.size_of(sc["src"])
        fr_ = sinfo.get("frame") or A.vertical_frame(sc["src"], sinfo)
        hx, hy0 = A.head_point(sc["src"], sinfo); PH = oh - D - B
        z = item.get("cam_zoom", 1.0)    # < 1: a wider view of him in the lower panel (still edge to edge, never a box)
        if z < 1.0:
            def crop_at(zz):
                sc_ = ow / fr_[2] * zz; cw, ch = int(ow / sc_) // 2 * 2, int(PH / sc_) // 2 * 2
                cx = int(min(max(hx - cw / 2, 0), SW - cw)) // 2 * 2; cy_ = int(min(max(hy0 - ch * item.get("face_at", 0.45), 0), SH - ch)) // 2 * 2
                return f"crop={cw}:{ch}:{cx}:{cy_},scale={ow}:{PH}:flags=lanczos"
            a0, a1 = item["f0"] + k0, item["f0"] + k1
            # close-ups (camera "close"): hard-cut punch-ins on alternate pieces, so jump cuts read as deliberate
            zc = (sc["raw"].get("camera") or {}).get("zoom", 1.1)
            cuts = sorted({a0, a1, *[x for c_ in sc["close"] for x in c_ if a0 < x < a1]})
            parts = [(x, y, any(c0 <= x < c1 for c0, c1 in sc["close"])) for x, y in zip(cuts[:-1], cuts[1:])]
            if len(parts) == 1:
                cam = cam_full(a0, a1, crop_at(z * zc if parts[0][2] else z))
            else:
                raw = cam_full(a0, a1, "null"); sl = [g.lab("pz") for _ in parts]
                g.add(f"[{raw}]split={len(parts)}" + "".join(f"[{x}]" for x in sl))
                cam = g.lab("pc")
                g.add("".join(f"[{l}]trim=start_frame={x - a0}:end_frame={y - a0},setpts=PTS-STARTPTS,{crop_at(z * zc if cl else z)},setsar=1[{l}o];"
                              for l, (x, y, cl) in zip(sl, parts)) + "".join(f"[{l}o]" for l in sl) + f"concat=n={len(parts)}:v=1:a=0,setpts=N/({FPS}*TB)[{cam}]")
            g.add(f"[{cam}]pad={ow}:{oh}:0:{D + B}:black[{o}c]")
        else:   # his face centred in the lower panel at full-frame size: pick the camera rows around his head
            cam = cam_full(item["f0"] + k0, item["f0"] + k1)
            hy = (hy0 - fr_[1]) * oh / fr_[3]
            Y = int(min(max(hy - PH * item.get("face_at", 0.45), 0), D + B) // 2 * 2)
            g.add(f"[{cam}]crop={ow}:{PH}:0:{Y},pad={ow}:{oh}:0:{D + B}:black[{o}c]")
        inner = dict(item["content"], f0=item["f0"], f1=item["f1"])
        if item.get("box"):   # a board: the content laid out in its own box (design units = the box width), e.g. 1040x940 at y 130
            dz = ow / 1080; bx, by, bw, bh = [int(round(v * dz / 2) * 2) for v in item["box"]]
            R2 = dict(R, profile=dict(R["profile"], w=bw, h=bh, canvas=(bw, bh)))
            if inner["kind"] == "graphic": inner.setdefault("design", item["box"][2])
            top = render_base(g, R2, sc, inner, k0, k1, tl, None)
            base = f"{o}c"
            if by > 0:   # the app header band above the box (Instagram/TikTok labels sit there): theme backdrop, nothing important
                bgi = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.1:.3f}", "-i", A.bg_still(dict(R, profile=dict(R["profile"], w=ow, h=by)))])
                g.add(f"[{bgi}]{A.png16_to_yuv()}[{o}hb];[{o}c][{o}hb]overlay=0:0:format=yuv444p10[{o}ch]"); base = f"{o}ch"
            g.add(f"[{base}][{top}]overlay={bx}:{by}:format=yuv444p10,trim=end_frame={n},{W10},setsar=1[{o}]")
            return o
        # the top ~17 % is Instagram's header (dimmed): content starts below it, the badge sits in that band
        cy = int(round(item.get("content_y", 0.17) * oh / 2) * 2)
        R2 = dict(R, profile=dict(R["profile"], w=ow, h=D - cy, canvas=(ow, D - cy)))
        top = render_base(g, R2, sc, inner, k0, k1, tl, None)
        if B:   # black header and band (the pad is already black): content on top, no seam
            g.add(f"[{o}c][{top}]overlay=0:{cy}:format=yuv444p10,trim=end_frame={n},{W10},setsar=1[{o}]")
            return o
        seam = A.seam_gradient(ow, D, R)
        si = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.1:.3f}", "-i", seam])
        bgi = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.1:.3f}", "-i", A.bg_still(dict(R, profile=dict(R["profile"], w=ow, h=cy)))])
        g.add(f"[{bgi}]{A.png16_to_yuv()}[{o}b];[{o}c][{o}b]overlay=0:0:format=yuv444p10[{o}cb];"
              f"[{o}cb][{top}]overlay=0:{cy}:format=yuv444p10[{o}t];[{si}]{A.png16_to_yuva()}[{o}g];[{o}t][{o}g]overlay=0:{D - 4}:format=yuv444p10,trim=end_frame={n},{W10},setsar=1[{o}]")
        return o
    raise ValueError(f"unknown base kind {kind}")


# ------------------------------------------------------------------ camera
def camera_segments(sc):
    """Scene frames as segments: piece bodies, and (spine "morph": n) RIFE morph bridges over each jump cut. A morph
    replaces the last n/2 frames of one piece and the first n/2 of the next, so the frame count (and sync) is unchanged."""
    n = int((sc["spine"] or {}).get("morph", 0) or 0); h = n // 2
    pcs = sc["pieces"]; segs = []
    for i, p in enumerate(pcs):
        if p["hold"]:   # voice is off here: freeze his face on its first frame, so no lips move without sound
            segs.append(dict(kind="freeze", p=p, f0=p["f0"], n=p["n"], t=p["a"])); continue
        tail = p.get("tail", 0)    # scene "tail": silent frames after the last word, frozen on the last spoken frame
        cut_in = h if (h and i > 0 and not pcs[i - 1]["hold"]) else 0
        cut_out = h if (h and i + 1 < len(pcs) and not pcs[i + 1]["hold"]) else 0
        if p["n"] - tail <= cut_in + cut_out + 2: cut_in = cut_out = 0
        segs.append(dict(kind="piece", p=p, f0=p["f0"] + cut_in, n=p["n"] - tail - cut_in - cut_out, k_off=cut_in))
        if tail: segs.append(dict(kind="freeze", p=p, f0=p["f0"] + p["n"] - tail, n=tail, t=p["a"] + (p["n"] - tail - 1) / FPS))
        if cut_out:
            q = pcs[i + 1]
            segs.append(dict(kind="morph", f0=p["f0"] + p["n"] - cut_out, n=2 * h,
                             a_end=p["a"] + (p["n"] - cut_out - 1) / FPS, b_start=q["a"] + h / FPS))
    return segs


def camera_stream(g, R, sc, tl, f0, f1):
    """Raw camera frames (scene frames f0..f1): pieces cut on the grid (+ morph bridges), touch-up, grade, paint-outs."""
    src = sc["src"]; parts = []
    sinfo = tl["sources"][sc["source_id"]]
    look = A.touchup_look(sinfo)
    for sg in camera_segments(sc):
        a0, a1 = max(f0, sg["f0"]), min(f1, sg["f0"] + sg["n"])
        if a1 <= a0: continue
        if sg["kind"] == "morph":
            from . import interp
            mp = interp.morph(src, sg["a_end"], sg["b_start"], n=sg["n"])
            v = g.inp(["-ss", f"{(a0 - sg['f0']) / FPS:.4f}", "-i", mp]); o = g.lab("mo")
            g.add(f"[{v}]setpts=PTS-STARTPTS,trim=end_frame={a1 - a0},{W10}[{o}]"); lb = o
        elif sg["kind"] == "freeze":
            lb = _freeze(g, src, sg["t"], a1 - a0)
            if look is not None:   # the touch-up patch, frozen on the same frame
                ptch, (px, py) = A.touchup_patch(src, sg["t"], 0.2, look)
                v = g.inp(["-i", ptch]); o = g.lab("tu")
                g.add(f"[{v}]setpts=PTS-STARTPTS,trim=end_frame=1,loop=loop={a1 - a0}:size=1,setpts=N/{FPS}/TB,trim=end_frame={a1 - a0}[{o}p];"
                      f"[{lb}]{W10}[{o}b];[{o}b][{o}p]overlay={px}:{py}:format=yuv444p10[{o}]")
            else:
                o = g.lab("cf"); g.add(f"[{lb}]{W10}[{o}]")
            lb = o
        else:
            p = sg["p"]; k0, k1 = a0 - sg["f0"] + sg["k_off"], a1 - sg["f0"] + sg["k_off"]
            lb = _source_frames(g, src, p["a"], 1.0, k0, k1)
            if look is not None:
                ptch, (px, py) = A.touchup_patch(src, p["a"], p["n"] / FPS, look)
                v = g.inp(["-ss", f"{k0 / FPS:.4f}", "-i", ptch])
                o = g.lab("tu")
                g.add(f"[{v}]setpts=PTS-STARTPTS,trim=end_frame={k1 - k0}[{o}p];[{lb}]{W10}[{o}b];[{o}b][{o}p]overlay={px}:{py}:format=yuv444p10:eof_action=pass[{o}]")
                lb = o
            else:
                o = g.lab("cf"); g.add(f"[{lb}]{W10}[{o}]"); lb = o
        if sinfo.get("grade"):
            o = g.lab("gr"); g.add(f"[{lb}]{C.grade_chain(sinfo['grade'])}[{o}]"); lb = o
        for fx_ in A.source_fixes(sinfo):   # e.g. socket paint-out: static patches given as filters
            o = g.lab("fx"); g.add(f"[{lb}]{fx_}[{o}]"); lb = o
        parts.append(lb)
    out = g.lab("cam")
    if len(parts) == 1: g.add(f"[{parts[0]}]null[{out}]")
    else: g.add("".join(f"[{p}]" for p in parts) + f"concat=n={len(parts)}:v=1:a=0,settb=1/{FPS},setpts=N[{out}]")    # one clock for all pieces
    return out


def camera_full_filter(R, sc, tl, f0, f1):
    """Static frame for the canvas + close-ups (hard cut punch-in) and slow drift as one perspective expression."""
    cw, ch = _canvas(R); ow, oh = _out_size(R)
    sinfo = tl["sources"][sc["source_id"]]
    SW, SH = A.size_of(sc["src"])
    frame = sinfo.get("frame") or (A.vertical_frame(sc["src"], sinfo) if ch > cw else [0, 0, SW, SH])
    fx, fy, fw, fh = frame
    head = sinfo.get("head") or A.head_point(sc["src"], sinfo)
    cam = sc["raw"].get("camera") or {}
    z, drift = cam.get("zoom", 1.14), cam.get("drift", 0.0)     # no slow push-in unless the scene asks ("drift": 0.03)
    pre = f"crop={fw}:{fh}:{fx}:{fy},scale={ow}:{oh}:flags=lanczos"
    if ch > cw and (sinfo.get("reframe") or cam.get("reframe")) == "follow" and not sinfo.get("frame"):
        # Auto Reframe: the 9:16 window follows his head (smoothed track), keyframed every 10 frames
        xs = A.head_track(sc["src"], sc["pieces"])
        SW_ = A.size_of(sc["src"])[0]
        keys = [(f, min(max(xs[min(f, len(xs) - 1)] - fw / 2, 0), SW_ - fw)) for f in range(f0, f1 + 10, 10)]
        e = f"{keys[-1][1]:.1f}"
        for (fa, xa), (fb, xb) in reversed(list(zip(keys[:-1], keys[1:]))):
            e = f"if(lt(n+{f0},{fb}),{xa:.1f}+({xb - xa:.1f})*(n+{f0}-{fa})/{fb - fa},{e})"
        pre = f"crop={fw}:{fh}:'{e}':{fy},scale={ow}:{oh}:flags=lanczos"
        fx = int(sum(k[1] for k in keys) / len(keys))
    hx, hy = (head[0] - fx) * ow / fw, (head[1] - fy) * oh / fh
    segs = []
    for a, b in sc["close"]:
        if b > f0 and a < f1: segs.append((a, b, z, z))
    if drift:
        closed = sc["close"]
        for p in sc["pieces"]:
            a, b = p["f0"], p["f0"] + p["n"]
            if b - a >= 6 * FPS and not any(x <= a < y for x, y in closed) and b > f0 and a < f1: segs.append((a, b, 1.0, 1.0 + drift))
    if not segs: return pre
    def win(zz):
        w, h = ow / zz, oh / zz
        x = min(max(hx - w / 2, 0), ow - w); y = min(max(hy - h / 2, 0), oh - h); return x, y, w, h
    f = f"(on+{f0})"
    def expr(i):
        e = ["0", "0", str(ow), str(oh)][i]
        for a, b, za, zb in segs:
            if za == zb: v = f"{win(za)[i]:.3f}"
            else:
                u = f"(({f}-{a})/{b - a})"
                zz = f"({za}+({zb - za})*{u})"
                w_ = f"({ow}/{zz})"; h_ = f"({oh}/{zz})"
                v = {0: f"min(max({hx:.3f}-{w_}/2,0),{ow}-{w_})", 1: f"min(max({hy:.3f}-{h_}/2,0),{oh}-{h_})", 2: w_, 3: h_}[i]
            e = f"if(between({f},{a},{b - 1}),{v},{e})"
        return e
    X, Y, Wd, Hd = (expr(i) for i in range(4))
    ex = [X, Y, f"({X}+{Wd})", Y, X, f"({Y}+{Hd})", f"({X}+{Wd})", f"({Y}+{Hd})"]
    ks = ["x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"]
    return pre + ",perspective=" + ":".join(f"{k}='{e}'" for k, e in zip(ks, ex)) + ":interpolation=cubic:eval=frame"


def _pip_at_edge(s, first):
    """Whether scene s shows the face box at its first (or last) frame."""
    if not s.get("pieces"): return False
    its = sorted(s["base"], key=lambda b: b["f0"])
    if not its: return False
    b = its[0] if first else its[-1]
    return b["kind"] not in ("camera", "stack") and b.get("pip", s["raw"].get("pip", "none")) != "none"


def facebox_fade_expr(R, sc, items, pos, f0, d):
    """Opacity expression (geq time T = seconds into this render window) that fades the face box in and out at the
    edges of where it shows; an edge where it simply carries on (the next/previous scene shows it too) is not faded."""
    iv = []
    for b in sorted(items, key=lambda b: b["f0"]):
        if iv and b["f0"] <= iv[-1][1]: iv[-1][1] = max(iv[-1][1], b["f1"])
        else: iv.append([b["f0"], b["f1"]])
    scenes = sorted(R["scenes"], key=lambda s: s["index"])
    i = next(k for k, s in enumerate(scenes) if s["index"] == sc["index"])
    prev_on = i > 0 and _pip_at_edge(scenes[i - 1], first=False)
    next_on = i + 1 < len(scenes) and _pip_at_edge(scenes[i + 1], first=True)
    parts = []
    for a, b in iv:
        s_, e_ = (a - f0) / FPS, (b - f0) / FPS
        fin = not (a == 0 and prev_on); fout = not (b >= sc["nf"] and next_on)
        up = f"clip((T-{s_:.4f})/{d},0,1)" if fin else "1"
        dn = f"clip(({e_:.4f}-T)/{d},0,1)" if fout else "1"
        parts.append(f"between(T,{s_ - 0.001:.4f},{e_:.4f})*{up}*{dn}")
    return "+".join(parts) if parts else None


def pip_layer(g, R, sc, tl, L, f0, f1, last):
    """A video or image in a box on top of the picture: {"kind": "video"|"image", "source"|"path", "from", "speed",
    "rect": [x, y, w, h] (output px), "fit": "fill"|"fit", "radius": 28, "border": "accent"|null, "enter": "fade"|"slide-left"|
    "slide-up"|"pop", "exit": "fade"}. Picture-in-picture, inset screenshots, reaction boxes."""
    ow, oh = _out_size(R); n_all = L["f1"] - L["f0"]
    a, b = max(f0, L["f0"]), min(f1, L["f1"]); k0, k1 = a - L["f0"], b - L["f0"]; n = k1 - k0; start = a - f0
    x, y, w, h = [int(v) // 2 * 2 for v in L["rect"]]
    o = g.lab("pip")
    if L["kind"] == "video" and L.get("key"):
        # green screen: key the colour out on the SDR source, keep that alpha through the HLG conversion
        path = src_path(tl, L["source"]) if "source" in L else os.path.expanduser(L["path"])
        kc = L["key"]; col = kc.get("color", "0x00FF00") if isinstance(kc, dict) else "0x00FF00"
        sim, bl = (kc.get("similarity", 0.12), kc.get("blend", 0.08)) if isinstance(kc, dict) else (0.12, 0.08)
        lb = _source_frames(g, path, L.get("from", 0.0), L.get("speed", 1.0), k0, k1)
        conv = A.sdr_to_hlg_chain(A.white_of(R["kit"]), A.matrix_of(path), R["kit"]) if not A.is_hlg(path) else W10
        g.add(f"[{lb}]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,format=yuva444p,chromakey=color={col}:similarity={sim}:blend={bl},"
              f"despill=type=green,format=yuva444p10le,split[{o}k1][{o}k2];[{o}k1]alphaextract[{o}al];[{o}k2]{conv}[{o}rgb];[{o}rgb][{o}al]alphamerge[{o}a]")
        X, Y = str(x), str(y); start_ = start
        g.add(f"[{o}a]setpts=PTS-STARTPTS+{start_ / FPS:.4f}/TB[{o}s];[{last}][{o}s]overlay=x='{X}':y='{Y}':format=yuv444p10:eof_action=pass:enable='between(n,{start_},{start_ + n - 1})'[{o}]")
        return o
    if L["kind"] == "video" and L.get("alpha"):
        # a clip with its own alpha (ProRes 4444 made outside Cutroom): keep that alpha through the HLG conversion
        path = src_path(tl, L["source"]) if "source" in L else os.path.expanduser(L["path"])
        lb = _source_frames(g, path, L.get("from", 0.0), L.get("speed", 1.0), k0, k1, hw=False)
        conv = A.sdr_to_hlg_chain(A.white_of(R["kit"]), A.matrix_of(path), R["kit"]) if not A.is_hlg(path) else W10
        g.add(f"[{lb}]scale={w}:{h}:flags=lanczos,format=yuva444p10le,split[{o}k1][{o}k2];[{o}k1]alphaextract[{o}al];"
              f"[{o}k2]{conv}[{o}rgb];[{o}rgb][{o}al]alphamerge[{o}a]")
        g.add(f"[{o}a]setpts=PTS-STARTPTS+{start / FPS:.4f}/TB[{o}s];[{last}][{o}s]overlay=x={x}:y={y}:format=yuv444p10:eof_action=pass:enable='between(n,{start},{start + n - 1})'[{o}]")
        return o
    if L["kind"] == "image":
        p = A.still_hlg(os.path.expanduser(L["path"]), (w, h), R["kit"], fit=L.get("fit", "fit"), alpha=True)
        v = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.1:.3f}", "-i", p])
        g.add(f"[{v}]{A.png16_to_yuva()},trim=end_frame={n}[{o}c]")
    else:
        item = dict(L, kind="screen", f0=L["f0"], f1=L["f1"], pip="none")
        R2 = dict(R, profile=dict(R["profile"], w=w, h=h, canvas=(w, h)))
        lab = render_base(g, R2, sc, item, k0, k1, tl, None)
        g.add(f"[{lab}]format=yuva444p10le[{o}c]")
    mk = A.rounded_mask(w, h, L.get("radius", 28) * ow / (3840 if ow > oh else 1080))
    mi = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.1:.3f}", "-i", mk])
    # entrance / exit (item time), 0.35 s
    T = 0.35; ent, ex = L.get("enter", "fade"), L.get("exit", "fade")
    t_ = f"(t+{k0 / FPS:.4f})"; tg = f"(T+{k0 / FPS:.4f})"; Dn = n_all / FPS        # geq calls time T
    fade = f"min(1,{tg}/{T})" if ent in ("fade", "pop") else "1"
    if ex == "fade": fade = f"min({fade},max(0,({Dn:.4f}-{tg})/{T}))"
    if L["kind"] == "image":   # keep the picture's own alpha: mask x alpha (alphamerge alone replaced it, so see-through parts went black)
        g.add(f"[{o}c]split[{o}c1][{o}c2];[{o}c2]alphaextract,format=gray10le[{o}ia];[{mi}]format=gray10le[{o}mk];"
              f"[{o}ia][{o}mk]blend=all_mode=multiply[{o}m]")
        src = f"[{o}c1]"
    else:
        g.add(f"[{mi}]format=gray10le[{o}m]"); src = f"[{o}c]"
    g.add(f"{src}[{o}m]alphamerge,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='alpha(X,Y)*{fade}'[{o}a]" if fade != "1"
          else f"{src}[{o}m]alphamerge[{o}a]")
    e = f"(1-pow(1-min(1,{t_}/{T}),3))"
    X = {"slide-left": f"{ow}-({ow}-{x})*{e}", "slide-right": f"-{w}+({x}+{w})*{e}"}.get(ent, str(x))
    Y = {"slide-up": f"{oh}-({oh}-{y})*{e}"}.get(ent, str(y))
    if L.get("border"):
        bw_ = max(2, int(6 * ow / 3840))
        bm = A.ring_mask(w + 2 * bw_, h + 2 * bw_, L.get("radius", 28) * ow / (3840 if ow > oh else 1080) + bw_, bw_, A.theme(R["kit"]).get(L["border"], A.theme(R["kit"])["accent"]) if isinstance(L["border"], str) else tuple(L["border"]), R)
        bi = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.1:.3f}", "-i", bm])
        g.add(f"[{bi}]{A.png16_to_yuva()}[{o}r];[{last}][{o}r]overlay=x='{X}-{bw_}':y='{Y}-{bw_}':format=yuv444p10:enable='between(n,{start},{start + n - 1})'[{o}rb]")
        last = f"{o}rb"
    g.add(f"[{o}a]setpts=PTS-STARTPTS+{start / FPS:.4f}/TB[{o}s];[{last}][{o}s]overlay=x='{X}':y='{Y}':format=yuv444p10:eof_action=pass:enable='between(n,{start},{start + n - 1})'[{o}]")
    return o


def mask_stream(g, sc, f0, f1):
    """His mask (SAM 2) for scene frames f0..f1, cut on the same pieces as the camera."""
    from . import masks
    parts = []
    for p in sc["pieces"]:
        a0, a1 = max(f0, p["f0"]), min(f1, p["f0"] + p["n"])
        if a1 <= a0: continue
        mp = masks.person_masks(sc["src"], p["a"], p["n"], point=(sc["raw"].get("subject_point")))
        v = g.inp(["-ss", f"{(a0 - p['f0']) / FPS:.4f}", "-i", mp]); o = g.lab("mp")
        g.add(f"[{v}]setpts=PTS-STARTPTS,trim=end_frame={a1 - a0},format=yuv444p10le[{o}]"); parts.append(o)
    out = g.lab("mks")
    g.add("".join(f"[{x}]" for x in parts) + f"concat=n={len(parts)}:v=1:a=0[{out}]" if len(parts) > 1 else f"[{parts[0]}]null[{out}]")
    return out


def subject_effects(g, R, sc, tl, cam, mask, a, b, fxs):
    """Effects that know where the subject is (mask): behind (a graphic between the background and them), blur_bg,
    spotlight, outline, relight ({"subject": +0.12, "background": 0.25}). Each fx: {"effect", "at", "until", "graphic": {"template", "props"}, "amount"} in scene seconds; "behind" also takes
    "video": path (a full-frame clip with its own alpha, e.g. ProRes 4444 made outside Cutroom) instead of "graphic"."""
    from .model import anchor
    n = b - a; ws = sc["words"]; T = sc["nf"] / FPS
    cur = cam
    for i, fx in enumerate(fxs):
        t0 = anchor(fx.get("at", 0), ws, T); t1 = anchor(fx.get("until", {"end": 0}), ws, T, at=t0)
        fa, fb = max(a, int(round(t0 * FPS))), min(b, int(round(t1 * FPS)))
        if fb <= fa: continue
        en = f"between(n,{fa - a},{fb - a - 1})"
        o = g.lab("sfx")
        g.add(f"[{cur}]split[{o}c1][{o}c2];[{mask}]split[{o}m1][{o}m2]"); mask = f"{o}m2"
        g.add(f"[{o}c2]format=yuva444p10le[{o}ca];[{o}ca][{o}m1]alphamerge[{o}p]")            # him, cut out
        e = fx["effect"]; subj = f"{o}p"
        if e == "relight":      # face/subject a touch brighter, background darker (soft mask edge from SAM 2)
            up, dn = fx.get("subject", 0.06), fx.get("background", 0.22)
            g.add(f"[{o}c1]split[{o}k][{o}q];[{o}q]colorlevels=romax={1 - dn}:gomax={1 - dn}:bomax={1 - dn}[{o}dk];"
                  f"[{o}k][{o}dk]overlay=0:0:enable='{en}'[{o}b];[{o}p]lutyuv=y='clip(val*{1 + up:.3f},minval,maxval)'[{o}p2]"); subj = f"{o}p2"
        elif e == "behind":
            f0g = int(round(t0 * FPS)); st = max(0, f0g - a)
            if "video" in fx:     # a clip with its own alpha made outside Cutroom (ProRes 4444): alpha kept through the HLG conversion
                path = os.path.expanduser(fx["video"]); ow, oh = _out_size(R)
                v = g.inp(["-ss", f"{max(0, a - f0g) / FPS:.4f}", "-i", path])
                conv = A.sdr_to_hlg_chain(A.white_of(R["kit"]), A.matrix_of(path), R["kit"]) if not A.is_hlg(path) else W10
                g.add(f"[{v}]scale={ow}:{oh}:flags=lanczos,format=yuva444p10le,split[{o}v1][{o}v2];[{o}v1]alphaextract[{o}al];"
                      f"[{o}v2]{conv}[{o}rgb];[{o}rgb][{o}al]alphamerge,setpts=PTS-STARTPTS+{st / FPS:.4f}/TB[{o}g]")
            else:
                gp = A.graphic(fx["graphic"]["template"], fx["graphic"].get("props", {}), int(round(t1 * FPS)) - f0g, R, alpha=True)
                v = g.inp(["-ss", f"{max(0, a - f0g) / FPS:.4f}", "-i", gp])
                g.add(f"[{v}]setpts=PTS-STARTPTS+{st / FPS:.4f}/TB,format=yuva444p10le[{o}g]")
            g.add(f"[{o}c1][{o}g]overlay=0:0:format=yuv444p10:eof_action=pass:enable='{en}'[{o}b]")
        elif e == "blur_bg":
            g.add(f"[{o}c1]split[{o}k][{o}q];[{o}q]gblur=sigma={fx.get('amount', 24)}[{o}bl];[{o}k][{o}bl]overlay=0:0:enable='{en}'[{o}b]")
        elif e == "spotlight":
            g.add(f"[{o}c1]split[{o}k][{o}q];[{o}q]colorlevels=romax={1 - fx.get('amount', 0.45)}:gomax={1 - fx.get('amount', 0.45)}:bomax={1 - fx.get('amount', 0.45)}[{o}dk];"
                  f"[{o}k][{o}dk]overlay=0:0:enable='{en}'[{o}b]")
        elif e == "outline":
            th = A.theme(R["kit"])["accent"]
            col = "0x%02x%02x%02x" % tuple(th)
            g.add(f"[{mask}]split[{o}mm][{o}mn];[{o}mm]gblur=sigma=14,lut=y='min(maxval,val*3)'[{o}gl];"
                  f"color=c={col}:s={R['profile']['w']}x{R['profile']['h']}:r={FPS},format=yuva444p10le,trim=end_frame={n}[{o}cc];"
                  f"[{o}cc][{o}gl]alphamerge[{o}ring];[{o}c1][{o}ring]overlay=0:0:format=yuv444p10:enable='{en}'[{o}b]"); mask = f"{o}mn"
        else:
            raise ValueError(f"unknown subject effect {e}")
        g.add(f"[{o}b][{subj}]overlay=0:0:format=yuv444p10:enable='{en}'[{o}]")
        cur = o
    g.add(f"[{mask}]nullsink")      # the last unused copy of the mask
    return cur


# ------------------------------------------------------------------ scene window
def scene_window(g, R, sc, f0, f1, tl):
    """Frames f0..f1 (scene frames) of one scene -> label (output size, yuv444p10 HLG)."""
    ow, oh = _out_size(R); n = f1 - f0
    base_items = [b for b in sc["base"] if b["f1"] > f0 and b["f0"] < f1]
    need_cam = bool(sc["pieces"])
    cam_users = []
    if need_cam:
        n_full = sum(1 for b in base_items if b["kind"] in ("camera", "stack")) + sum(1 for b in base_items if b["kind"] == "split" for q in b["panels"] if q["kind"] == "camera")
        pip_on = [b for b in base_items if b["kind"] not in ("camera", "stack") and b.get("pip", sc["raw"].get("pip", "none")) != "none"
                  and not (b["kind"] == "split" and any(q["kind"] == "camera" for q in b["panels"]))]
        need_cam = n_full + (1 if pip_on else 0) > 0
        if not need_cam: pip_on = []
    if need_cam:
        cam = camera_stream(g, R, sc, tl, f0, f1)
        outs = [g.lab("cu") for _ in range(n_full + (1 if pip_on else 0))]
        if len(outs) == 1: g.add(f"[{cam}]null[{outs[0]}]")
        elif outs: g.add(f"[{cam}]split={len(outs)}" + "".join(f"[{o}]" for o in outs))
        full_filter = camera_full_filter(R, sc, tl, f0, f1)
        full_srcs = outs[:n_full]
        fxs = [x for x in (sc["raw"].get("subject_fx") or [])]
        mask_srcs = []
        if fxs and n_full:
            mk = mask_stream(g, sc, f0, f1)
            mask_srcs = [g.lab("mq") for _ in range(n_full)]
            g.add(f"[{mk}]split={n_full}" + "".join(f"[{m}]" for m in mask_srcs) if n_full > 1 else f"[{mk}]null[{mask_srcs[0]}]")
        def cam_full(a, b, filt=None):    # filt: another framing of the raw camera (e.g. a wider Shorts panel)
            lb = full_srcs.pop(0); o = g.lab("cv")
            g.add(f"[{lb}]{filt or full_filter},trim=start_frame={a - f0}:end_frame={b - f0},setpts=N/({FPS}*TB),{W10},setsar=1[{o}]")    # exact frame times (morph clips have their own clock)
            if mask_srcs:
                m = mask_srcs.pop(0); mo = g.lab("mk")
                g.add(f"[{m}]{full_filter},trim=start_frame={a - f0}:end_frame={b - f0},setpts=PTS-STARTPTS,format=gray10le,setsar=1[{mo}]")
                o = subject_effects(g, R, sc, tl, o, mo, a, b, fxs)
            return o
        pip_src = outs[n_full] if pip_on else None
    else:
        cam_full = None; pip_on = [] if not sc["pieces"] or not need_cam else pip_on; pip_src = None
    labels = []
    for b in base_items:
        k0, k1 = max(f0, b["f0"]) - b["f0"], min(f1, b["f1"]) - b["f0"]
        labels.append(render_base(g, R, sc, b, k0, k1, tl, cam_full))
    base = g.lab("base")
    # one exact 1/30 clock for the base: base pieces come from different time bases (images, clips, recordings), and a
    # microsecond-off timestamp makes the overlays below pair the face box with the previous camera frame (stutter)
    if len(labels) == 1: g.add(f"[{labels[0]}]settb=1/{FPS},setpts=N[{base}]")
    else: g.add("".join(f"[{l}]" for l in labels) + f"concat=n={len(labels)}:v=1:a=0,settb=1/{FPS},setpts=N[{base}]")
    last = base
    # face box
    if pip_src:
        fb = A.facebox(R, sc, tl)          # dict(mask=path, shadow=path, crop=(x,y,w,h), size=(w,h), pos={name: (x,y)}, label=...)
        mi = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.2:.3f}", "-i", fb["mask"]])
        si = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.2:.3f}", "-i", fb["shadow"]])
        cx, cy, cw_, ch_ = fb["crop"]; bw, bh = fb["size"]
        o = g.lab("fb")
        g.add(f"[{pip_src}]crop={cw_}:{ch_}:{cx}:{cy},scale={bw}:{bh}:flags=lanczos,format=yuva444p10le[{o}f];[{mi}]format=gray10le,scale={bw}:{bh}[{o}m];"
              f"[{o}f][{o}m]alphamerge[{o}a];[{si}]{A.png16_to_yuva()}[{o}s]")
        by_pos = {}
        for b in pip_on:
            by_pos.setdefault(b.get("pip", sc["raw"].get("pip", "none")), []).append(b)
        splits = [g.lab("fq") for _ in by_pos]; ss_ = [g.lab("fr") for _ in by_pos]
        g.add(f"[{o}a]split={len(splits)}" + "".join(f"[{x}]" for x in splits) if len(splits) > 1 else f"[{o}a]null[{splits[0]}]")
        g.add(f"[{o}s]split={len(ss_)}" + "".join(f"[{x}]" for x in ss_) if len(ss_) > 1 else f"[{o}s]null[{ss_[0]}]")
        for (pos, items), fa, sa in zip(by_pos.items(), splits, ss_):
            en = "+".join(f"between(t,{(max(f0, b['f0']) - f0) / FPS:.4f},{(min(f1, b['f1']) - f0) / FPS - 0.001:.4f})" for b in items)
            px, py = fb["pos"][pos]; sx, sy = fb["shadow_off"]
            fd = fb.get("fade", 0)
            if fd:   # the box fades in and out (kit facebox "fade": seconds) instead of popping; no fade where it simply continues
                ex = facebox_fade_expr(R, sc, items, pos, f0, fd)
                if ex:
                    gq = f"geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='alpha(X,Y)*({ex})'"
                    fa2, sa2 = g.lab("fx"), g.lab("fy")
                    g.add(f"[{fa}]{gq}[{fa2}];[{sa}]{gq}[{sa2}]"); fa, sa = fa2, sa2
            o2 = g.lab("fo")
            g.add(f"[{last}][{sa}]overlay={px + sx}:{py + sy}:format=yuv444p10:enable='{en}'[{o2}s];[{o2}s][{fa}]overlay={px}:{py}:format=yuv444p10:enable='{en}'[{o2}]")
            last = o2
            if fb.get("border"):         # thin border around the box (kit facebox "border": [r, g, b], "border_w": px at 4K)
                bwid, col = fb["border"]
                bm = A.ring_mask(bw + 2 * bwid, bh + 2 * bwid, fb["radius"] + bwid, bwid, tuple(col), R)
                bi = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{n / FPS + 0.2:.3f}", "-i", bm]); o3 = g.lab("fbb")
                fx_ = (f",geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='alpha(X,Y)*({ex})'" if fd and ex else "")
                g.add(f"[{bi}]{A.png16_to_yuva()}{fx_}[{o3}r];[{last}][{o3}r]overlay={px - bwid}:{py - bwid}:format=yuv444p10:enable='{en}'[{o3}]")
                last = o3
        if sc["raw"].get("pip_label"):
            for pos, items in by_pos.items():
                px, py = fb["pos"][pos]
                lp = A.pip_label(R, sc["raw"]["pip_label"], (px + bw // 2, py + bh - int(46 * ow / 3840)), n_total=sc["nf"])
                v = g.inp(["-ss", f"{f0 / FPS:.4f}", "-i", lp])
                en = "+".join(f"between(t,{(max(f0, b['f0']) - f0) / FPS:.4f},{(min(f1, b['f1']) - f0) / FPS - 0.001:.4f})" for b in items)
                o3 = g.lab("pl")
                g.add(f"[{v}]setpts=PTS-STARTPTS,format=yuva444p10le[{o3}i];[{last}][{o3}i]overlay=0:0:format=yuv444p10:eof_action=pass:enable='{en}'[{o3}]")
                last = o3
    # layers
    for L in sc["layers"]:
        if L["f1"] <= f0 or L["f0"] >= f1: continue
        if L["kind"] in ("video", "image"):
            last = pip_layer(g, R, sc, tl, L, f0, f1, last)
            continue
        if L["kind"] == "pin":
            last = pin_layer(g, R, sc, tl, L, f0, f1, last)
            continue
        if L["kind"] == "matte":
            last = matte_layer(g, R, sc, tl, L, f0, f1, last)
            continue
        p, xy = A.layer_asset(L, R, sc, tl)
        k0 = max(0, f0 - L["f0"]); start = max(0, L["f0"] - f0)
        o = g.lab("ly")
        end = min(f1, L["f1"]) - f0
        if p.endswith(".png"):
            v = g.inp(["-loop", "1", "-framerate", str(FPS), "-t", f"{(f1 - f0) / FPS + 0.1:.3f}", "-i", p])
            g.add(f"[{v}]{A.png16_to_yuva()}[{o}i];")
            g.chains[-1] = g.chains[-1].rstrip(";")
            g.add(f"[{last}][{o}i]overlay={xy[0]}:{xy[1]}:format=yuv444p10:enable='between(n,{start},{end - 1})'[{o}]")
            last = o
            continue
        v = g.inp(["-ss", f"{k0 / FPS:.4f}", "-i", p])
        if L.get("anim"):          # keyframes: move / scale / rotate / fade over time (After Effects style)
            v = anim_layer(g, R, L, v, xy, k0, start, min(f1, L["f1"]) - max(f0, L["f0"])); xy = (0, 0)
        if L.get("blend") and L["blend"] != "normal":
            last = blend_layer(g, last, v, L["blend"], xy, start, end, ow, oh, o, L.get("opacity", 1.0)); continue
        g.add(f"[{v}]setpts=PTS-STARTPTS+{start / FPS:.4f}/TB,format=yuva444p10le[{o}i];"
              f"[{last}][{o}i]overlay={xy[0]}:{xy[1]}:format=yuv444p10:eof_action=pass:enable='between(n,{start},{end - 1})'[{o}]")
        last = o
    last = adjust_layers(g, R, sc, last, f0, f1)
    o = g.lab("sw")
    g.add(f"[{last}]trim=end_frame={n},setpts=PTS-STARTPTS,{W10},setsar=1[{o}]")
    return o


def _ease(u, fn):
    u = min(1.0, max(0.0, u))
    if fn == "linear": return u
    if fn == "inout": return u * u * (3 - 2 * u)
    if fn == "cubic": return 1 - (1 - u) ** 3
    if fn == "back": c = 1.70158; return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2      # overshoot
    return min(1.0, (1 - (1 + 7.5 * u) * math.exp(-7.5 * u)) / 0.9953)                      # spring (default)


def anim_value(keys, t):
    """Keyframes [{"t", "x", "y", "s", "r", "o", "ease"}] -> pose at t (layer seconds). Missing values carry over."""
    pose = dict(x=0.0, y=0.0, s=1.0, r=0.0, o=1.0); prev = dict(pose)
    ks = sorted(keys, key=lambda k: k["t"])
    for i, k in enumerate(ks):
        tgt = dict(prev, **{q: float(k[q]) for q in "xysro" if q in k})
        if i == 0 or t >= k["t"]:
            if i + 1 < len(ks) and t < ks[i + 1]["t"]:
                nk = ks[i + 1]; nxt = dict(tgt, **{q: float(nk[q]) for q in "xysro" if q in nk})
                u = _ease((t - k["t"]) / max(1e-6, nk["t"] - k["t"]), nk.get("ease", "spring"))
                return {q: tgt[q] + (nxt[q] - tgt[q]) * u for q in pose}
            prev = tgt; pose = tgt
        else: break
    return pose


def anim_layer(g, R, L, v, xy, k0, start, n):
    """Pad the layer clip onto the canvas and move it by sampled keyframes (one perspective filter; fades by alpha)."""
    import numpy as np, cv2
    ow, oh = _out_size(R); cw, ch = _canvas(R); s = ow / cw
    o = g.lab("an")
    # the clip's own size is the rect (graphic in a box) or the full canvas
    if L.get("rect"): x, y, w, h = [v_ * s for v_ in L["rect"]]
    else: x, y, w, h = 0, 0, ow, oh
    cx, cy = x + w / 2, y + h / 2
    step = max(2, -(-n // 60)); ks = list(range(0, n + step, step))
    def corners(f):
        p = anim_value(L["anim"], (k0 + f) / FPS)
        a = math.radians(p["r"]); ca, sa = math.cos(a) * p["s"], math.sin(a) * p["s"]
        src = np.float32([[x, y], [x + w, y], [x, y + h], [x + w, y + h]])
        dst = np.float32([[cx + p["x"] * s + ca * (px - cx) - sa * (py - cy), cy + p["y"] * s + sa * (px - cx) + ca * (py - cy)] for px, py in src])
        H = cv2.getPerspectiveTransform(dst, src)
        return cv2.perspectiveTransform(np.float32([[[0, 0], [ow, 0], [0, oh], [ow, oh]]]), H)[0], p["o"]
    cs = [corners(f) for f in ks]
    def expr(ci, cj):
        return "+".join(f"gte(on,{fa})*lt(on,{fb})*({float(a[0][ci][cj]):.2f}+{(float(b[0][ci][cj]) - float(a[0][ci][cj])) / (fb - fa):.4f}*(on-{fa}))"
                        for (fa, a), (fb, b) in zip(zip(ks, cs), zip(ks[1:], cs[1:])))
    pers = "perspective=" + ":".join(f"{k}='{expr(i, j)}'" for (i, j), k in zip([(c, d) for c in range(4) for d in range(2)],
                                     ["x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"])) + ":interpolation=cubic:eval=frame"
    fades = ""
    os_ = [c[1] for c in cs]
    if min(os_) < 0.999:    # opacity keys -> one alpha fade in (first rise) and one fade out (last fall)
        up = [i for i in range(1, len(os_)) if os_[i] > os_[i - 1] + 1e-3]; dn = [i for i in range(1, len(os_)) if os_[i] < os_[i - 1] - 1e-3]
        if up: fa, fb = ks[up[0] - 1], ks[up[-1]]; fades += f",fade=t=in:st={(start + fa) / FPS:.4f}:d={max(1, fb - fa) / FPS:.4f}:alpha=1"
        if dn: fa, fb = ks[dn[0] - 1], ks[dn[-1]]; fades += f",fade=t=out:st={(start + fa) / FPS:.4f}:d={max(1, fb - fa) / FPS:.4f}:alpha=1"
    g.add(f"[{v}]format=yuva444p10le,pad={ow}:{oh}:{int(xy[0])}:{int(xy[1])}:color=black@0,{pers}[{o}]")
    if fades:
        o2 = g.lab("anf"); g.add(f"[{o}]setpts=PTS-STARTPTS+{start / FPS:.4f}/TB{fades},setpts=PTS-STARTPTS[{o2}]"); o = o2
    return o


BLENDS = {"screen": "screen", "add": "addition", "lighten": "lighten", "multiply": "multiply", "overlay": "overlay", "softlight": "softlight", "darken": "darken"}


def pin_layer(g, R, sc, tl, L, f0, f1, last):
    """Corner pin: put a picture ("content": screen / still / graphic / broll item) onto a flat surface in the shot under
    it (phone, monitor, sign). "quad": 4 corners TL,TR,BR,BL in source px of that shot at the layer's start; "track": true
    follows the surface (planar tracking). The shot under it must be a broll/screen item without zoom."""
    import numpy as np, cv2
    from . import analyze
    ow, oh = _out_size(R); cw, ch = _canvas(R); s = ow / cw
    a, b = max(f0, L["f0"]), min(f1, L["f1"]); k0, k1 = a - L["f0"], b - L["f0"]; n = k1 - k0; start = a - f0
    under = next((x for x in sc["base"] if x["f0"] <= L["f0"] < x["f1"]), None)
    path = src_path(tl, under["source"]) if under and "source" in under else os.path.expanduser(under["path"])
    crop = (under.get("crop") or tl["sources"].get(under.get("source"), {}).get("crop") or A.full_crop(path))
    fx, fy, fw, fh = fit_rect(crop[2], crop[3], cw, ch, under.get("fit", "fit"), under.get("align", "center")); kk = fw / crop[2]
    t_src0 = under.get("from", 0.0) + (L["f0"] - under["f0"]) / FPS * under.get("speed", 1.0)
    N = L["f1"] - L["f0"]
    quads = analyze.track_quad(path, t_src0, N, L["quad"]) if L.get("track", True) else [L["quad"]] * N
    item = dict(L["content"], f0=L["f0"], f1=L["f1"], pip="none")
    flat = render_base(g, R, sc, item, k0, k1, tl, None)
    src = np.float32([[0, 0], [ow, 0], [ow, oh], [0, oh]])
    step = max(2, -(-n // 60)); ks = list(range(k0, k1 + step, step))
    def corners(k):
        q = np.float32(quads[min(k, len(quads) - 1)])
        dst = np.float32([[(fx + (x - crop[0]) * kk) * s, (fy + (y - crop[1]) * kk) * s] for x, y in q])
        Hm = cv2.getPerspectiveTransform(dst, src)
        return cv2.perspectiveTransform(np.float32([[[0, 0], [ow, 0], [0, oh], [ow, oh]]]), Hm)[0]
    cs = [corners(k) for k in ks]
    def expr(ci, cj):
        return "+".join(f"gte(on,{ka - k0})*lt(on,{kb - k0})*({float(A_[ci][cj]):.2f}+{(float(B_[ci][cj]) - float(A_[ci][cj])) / (kb - ka):.4f}*(on-{ka - k0}))"
                        for (ka, A_), (kb, B_) in zip(zip(ks, cs), zip(ks[1:], cs[1:])))
    pers = "perspective=" + ":".join(f"{k}='{expr(i, j)}'" for (i, j), k in zip([(c, d) for c in range(4) for d in range(2)],
                                     ["x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"])) + ":interpolation=cubic:eval=frame"
    o = g.lab("pin")
    g.add(f"[{flat}]format=yuva444p10le,pad={ow + 4}:{oh + 4}:2:2:color=black@0,scale={ow}:{oh},{pers},setpts=PTS-STARTPTS+{start / FPS:.4f}/TB[{o}a];"
          f"[{last}][{o}a]overlay=0:0:format=yuv444p10:eof_action=pass:enable='between(n,{start},{start + n - 1})'[{o}]")
    return o


def matte_layer(g, R, sc, tl, L, f0, f1, last):
    """Track matte: a picture (screen / broll / still / graphic item in "content") shown only through the white parts
    of a matte graphic ("matte": {"template": "Matte", "props": {"text": "AI"}} or any template with alpha).
    "invert": true shows it everywhere except the shape. Video inside big text, circle reveals, shaped windows."""
    ow, oh = _out_size(R)
    a, b = max(f0, L["f0"]), min(f1, L["f1"]); k0, k1 = a - L["f0"], b - L["f0"]; n = k1 - k0; start = a - f0
    item = dict(L["content"], f0=L["f0"], f1=L["f1"], pip="none")
    lab = render_base(g, R, sc, item, k0, k1, tl, None)
    m = L.get("matte") or {"template": "Matte", "props": {"text": L.get("text", "")}}
    mp = A.graphic(m.get("template", "Matte"), m.get("props", {}), L["f1"] - L["f0"], R, alpha=True)
    mi = g.inp(["-ss", f"{k0 / FPS:.4f}", "-i", mp]); o = g.lab("mat")
    inv = ",negate" if L.get("invert") else ""
    g.add(f"[{mi}]setpts=PTS-STARTPTS,fps={FPS},trim=end_frame={n},scale={ow}:{oh},format=yuva444p10le,alphaextract{inv}[{o}m];"
          f"[{lab}]format=yuva444p10le[{o}c];[{o}c][{o}m]alphamerge,setpts=PTS-STARTPTS+{start / FPS:.4f}/TB[{o}a];"
          f"[{last}][{o}a]overlay=0:0:format=yuv444p10:eof_action=pass:enable='between(n,{start},{start + n - 1})'[{o}]")
    return o


def blend_layer(g, last, v, mode, xy, start, end, ow, oh, o, opacity=1.0):
    """Graphic layer combined with a blend mode (glows, light leaks, film burns: "screen" / "add"; shadows: "multiply").
    Done in R'G'B' on the HLG values; transparent parts of the layer leave the picture unchanged."""
    md = BLENDS.get(mode, mode)
    neutral = "white" if md in ("multiply", "darken") else "black"
    g.add(f"[{v}]setpts=PTS-STARTPTS+{start / FPS:.4f}/TB,format=yuva444p10le[{o}i];"
          f"color=c={neutral}:s={ow}x{oh}:r={FPS},format=yuv444p10le[{o}n];[{o}n][{o}i]overlay={xy[0]}:{xy[1]}:format=yuv444p10:eof_action=pass:shortest=0,"
          f"scale=in_color_matrix=bt2020:in_range=tv:out_range=full,format=gbrp10le[{o}g];"
          f"[{last}]scale=in_color_matrix=bt2020:in_range=tv:out_range=full,format=gbrp10le[{o}b];"
          f"[{o}b][{o}g]blend=all_mode={md}:all_opacity={opacity}:shortest=0:repeatlast=1:enable='between(n,{start},{end - 1})',"
          f"scale=in_range=full:out_color_matrix=bt2020:out_range=tv,{W10}[{o}]")
    return o


def adjust_layers(g, R, sc, last, f0, f1):
    """Adjustment layers: one look over everything under it for a time range (scene time, words allowed):
    "adjust": [{"at", "until", "grade": look|{...}, "blur": sigma, "vignette": 0-1, "glow": 0-1, "bright": -1..1,
                "grain": 0-1, "fringe": px, "sharpen": 0-1, "shake": 0-1}]."""
    for J in sc.get("adjust", []):
        a, b = J["f0"] - f0, J["f1"] - f0
        if b <= 0 or a >= f1 - f0: continue
        en = f"enable='between(n,{max(0, a)},{b - 1})'"; o = g.lab("adj"); ow, oh = _out_size(R)
        parts = []
        if J.get("grade"):
            parts.append(f"lut3d=file='{C.grade_lut(J['grade'])}':interp=tetrahedral:{en}")
        if J.get("blur"): parts.append(f"gblur=sigma={J['blur'] * ow / 1920:.2f}:{en}")
        if J.get("vignette"): parts.append(f"vignette=angle={0.3 + 0.5 * J['vignette']:.3f}:eval=init:{en}")
        if J.get("bright"): parts.append(f"eq=brightness={0.12 * J['bright']:.3f}:{en}")
        if J.get("grain"): parts.append(f"noise=alls={int(6 + 14 * J['grain'])}:allf=t:{en}")                 # film grain (moves every frame)
        if J.get("fringe"): k_ = max(1, int(J["fringe"] * ow / 1920)); parts.append(f"rgbashift=rh=-{k_}:bh={k_}:edge=smear:{en}")   # colour fringing
        if J.get("sharpen"): parts.append(f"unsharp=5:5:{0.6 * J['sharpen']:.2f}:5:5:0:{en}")
        if J.get("shake"): a_ = J["shake"] * ow / 1920 * 6; parts.append(f"crop=w=iw-{2 * int(a_ + 2)}:h=ih-{2 * int(a_ + 2)}:x='{int(a_ + 2)}+between(n\\,{max(0, a)}\\,{b - 1})*{a_:.1f}*sin(n*1.7)':y='{int(a_ + 2)}+between(n\\,{max(0, a)}\\,{b - 1})*{a_:.1f}*cos(n*2.3)',scale={ow}:{oh}")   # camera shake (hits), only in its range
        if parts: g.add(f"[{last}]" + ",".join(parts) + f",{W10}[{o}]"); last = o
        if J.get("glow"):     # bloom: blurred highlights screened back on
            o2 = g.lab("glw"); k = J["glow"]
            g.add(f"[{last}]split[{o2}a][{o2}b];[{o2}b]scale=in_color_matrix=bt2020:in_range=tv:out_range=full,format=gbrp10le,"
                  f"curves=all='0/0 0.55/0 1/1',gblur=sigma={30 * ow / 1920:.1f}[{o2}h];"
                  f"[{o2}a]scale=in_color_matrix=bt2020:in_range=tv:out_range=full,format=gbrp10le[{o2}c];"
                  f"[{o2}c][{o2}h]blend=all_mode=screen:all_opacity={k}:enable='between(n,{max(0, a)},{b - 1})',"
                  f"scale=in_range=full:out_color_matrix=bt2020:out_range=tv,{W10}[{o2}]"); last = o2
    return last


TRANSITIONS = {   # friendly names -> ffmpeg xfade (any other xfade name works too)
    "dissolve": "fade", "fade": "fade", "wipe-left": "wipeleft", "wipe-right": "wiperight", "wipe-up": "wipeup", "wipe-down": "wipedown",
    "slide-left": "slideleft", "slide-right": "slideright", "slide-up": "slideup", "slide-down": "slidedown",
    "push-left": "coverleft", "reveal-left": "revealleft", "zoom": "zoomin", "circle": "circleopen", "circle-close": "circleclose",
    "whip": "hblur", "smooth-left": "smoothleft", "smooth-up": "smoothup", "radial": "radial", "pixel": "pixelize",
    "squeeze": "squeezeh", "dip-black": "fadeblack", "dip-white": "fadewhite", "slice": "hlslice", "diagonal": "diagtl",
}


DESIGNED = {   # name: (xfade base, light leak variant or None, blur radius in 1080p px or 0)
    "leak": ("fade", "leak", 0), "burn": ("fade", "burn", 0), "flare": ("fade", "flare", 0),
    "zoom-blur": ("zoomin", None, 18), "whip-blur": ("hblur", None, 10), "flash": ("fadewhite", "flare", 0),
    "leak-slide": ("slideleft", "leak", 6),
}


def window(R, f0, f1, tl):
    """Graph for timeline frames [f0, f1). Returns (Graph, out_label)."""
    g, o = _window(R, f0, f1, tl)
    for L in R.get("overlays", []):
        if L["f1"] <= f0 or L["f0"] >= f1: continue
        p, xy = A.layer_asset(L, R, None, tl)
        k0 = max(0, f0 - L["f0"]); start = max(0, L["f0"] - f0); end = min(f1, L["f1"]) - f0
        v = g.inp(["-ss", f"{k0 / FPS:.4f}", "-i", p])
        o2 = g.lab("tw")
        g.add(f"[{v}]setpts=PTS-STARTPTS+{start / FPS:.4f}/TB,format=yuva444p10le[{o2}i];"
              f"[{o}][{o2}i]overlay={xy[0]}:{xy[1]}:format=yuv444p10:eof_action=pass:enable='between(n,{start},{end - 1})'[{o2}]")
        o = o2
    return g, o


def _window(R, f0, f1, tl):
    g = Graph()
    scs = [s for s in R["scenes"] if s["start"] < f1 and s["start"] + s["nf"] > f0]
    outs = []
    for s in scs:
        a, b = max(f0, s["start"]) - s["start"], min(f1, s["start"] + s["nf"]) - s["start"]
        outs.append((s, scene_window(g, R, s, a, b, tl), max(f0, s["start"]), min(f1, s["start"] + s["nf"])))
    if len(outs) == 1:
        return g, outs[0][1]
    if len(outs) == 2:   # a dissolve window: both scenes cover the same frames
        (s1, l1, a1, b1), (s2, l2, a2, b2) = outs
        if not (a1 == a2 == f0 and b1 == b2 == f1):
            raise ValueError(f"window {f0}-{f1} mixes a cut and a dissolve: chunk planner bug")
        d = (f1 - f0) / FPS
        o = g.lab("xf")
        tr = (s2["raw"].get("transition") or tl.get("default_transition") or {}); typ = tr.get("type", "dissolve")
        if typ in DESIGNED:      # designed transitions: a base move + a light/blur pass on top (light leak, burn, flare, zoom blur)
            base, leak, blur = DESIGNED[typ]
            g.add(f"[{l1}][{l2}]xfade=transition={base}:duration={d:.4f}:offset=0,trim=end_frame={f1 - f0}[{o}x]")
            cur = f"{o}x"
            if blur:
                ow, oh = _out_size(R)
                g.add(f"[{cur}]boxblur=luma_radius={max(1, int(blur * ow / 1920))}:luma_power=2:chroma_radius=2[{o}b]")      # blur through the move
                cur = f"{o}b"
            if leak:
                ow, oh = _out_size(R)
                p = A.graphic("LightLeak", dict(variant=leak, at=0.0, dur=d, color=tr.get("color", "warm"), **({"from": tr["from"]} if tr.get("from") else {})), f1 - f0, R, alpha=True)
                v = g.inp(["-i", p])
                cur = blend_layer(g, cur, v, "screen", (0, 0), 0, f1 - f0, ow, oh, g.lab("trl"), tr.get("strength", 1.0))
            g.add(f"[{cur}]null[{o}]")
            return g, o
        g.add(f"[{l1}][{l2}]xfade=transition={TRANSITIONS.get(typ, typ)}:duration={d:.4f}:offset=0,trim=end_frame={f1 - f0}[{o}]")
        return g, o
    raise ValueError("window spans more than two scenes")
