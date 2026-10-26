"""Remotion bridge: render queued graphics jobs in one batch, then turn each PNG sequence into an HLG clip.

- Design units: 1920x1080 (16:9) or 1080x1920 (9:16); rendered with --scale so 4K stays sharp.
- Motion blur: kit.graphics.motion_blur = S (default 8) re-renders only MOVING frames at 30*S fps and averages 5/8 of every
  group (a 225-degree film shutter), premultiplied so edges stay clean. S=1 turns it off.
- Colour: PNG (sRGB, straight alpha) -> lut3d (sRGB -> HLG BT.2408, or the 'legacy' look) -> BT.2020 YUV.
  Output: ProRes 4444 with alpha (overlays) or ProRes 422 HQ (opaque full-screen graphics).
- Props: any string starting with "file://" is copied next to the bundle and passed as a URL (icons, logos, photos);
  keys listed in "_px" are output
  pixels and get divided by the render scale (ring boxes)."""
import base64, json, mimetypes, os, shutil, subprocess, tempfile, time
from . import cache
from . import color as C
from .media import ff, log, RenderError

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = "3"   # bump when this file changes how graphics are rendered (invalidates cached graphics)
GFX = os.path.join(os.path.dirname(HERE), "graphics")


def _datauri(v):
    p = os.path.expanduser(v[len("file://"):])
    mt = mimetypes.guess_type(p)[0] or "image/png"
    return f"data:{mt};base64," + base64.b64encode(open(p, "rb").read()).decode()


def _prep_props(props, scale):
    def walk(x):
        if isinstance(x, dict): return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list): return [walk(v) for v in x]
        if isinstance(x, str) and x.startswith("file://"): return "file://" + os.path.expanduser(x[7:])   # render.mjs serves it
        if isinstance(x, str) and x.startswith("tool:"):                                                 # drawn tool tiles
            from .tool_icons import tool_png
            return "file://" + tool_png(x[5:])
        return x
    out = walk(props)
    for k in out.pop("_px", []) if isinstance(out, dict) else []:
        v = out.get(k)
        if isinstance(v, list): out[k] = [round(x / scale, 2) for x in v]
        elif isinstance(v, (int, float)): out[k] = round(v / scale, 2)
    return out


def design_of(w, h, design=None):
    """Design units: 1920 wide for landscape-ish pictures, 1080 wide for tall ones; height keeps the aspect.
    design = an explicit design width (smaller = everything drawn bigger inside a box)."""
    dw = design or (1080 if h > w * 1.2 else 1920)        # same threshold as the templates' "tall" layout
    return (dw, int(round(dw * h / w / 2) * 2))


def _node(batch, tmp, tag):
    jf = os.path.join(tmp, f"jobs_{tag}.json"); json.dump(batch, open(jf, "w"))
    p = subprocess.run(["node", os.path.join(GFX, "render.mjs"), jf], cwd=GFX, capture_output=True, text=True)
    if p.returncode: raise RenderError("Remotion render failed:\n" + p.stderr[-4000:] + p.stdout[-2000:])


def _seq(d):
    files = sorted(f for f in os.listdir(d) if f.rsplit(".", 1)[-1] in ("png", "jpeg", "jpg"))
    if not files: raise RenderError(f"no frames in {d}")
    stem, rest = files[0].rsplit("-", 1)
    num, ext = rest.split(".")
    return os.path.join(d, f"{stem}-%0{len(num)}d.{ext}"), int(num), len(files)


def motion_spans(d, n, thr=0.9, pad=2):
    """Frame spans that move (mean abs change > thr of 255 at low res), padded; [(a, b)] inclusive-exclusive."""
    pat, start, cnt = _seq(d)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-start_number", str(start), "-i", pat, "-vf", "scale=240:-2:flags=area,format=rgba",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    import numpy as np
    a = np.frombuffer(raw, np.uint8)
    fr = a.reshape(cnt, -1, 4).astype(np.float32)
    rgb = fr[..., :3] * (fr[..., 3:] / 255)
    m = np.abs(np.diff(rgb, axis=0)).mean(axis=(1, 2)) if cnt > 1 else np.zeros(0)
    mov = np.zeros(n, bool)
    for i, v in enumerate(m):
        if v > thr: mov[max(0, i - pad): min(n, i + 2 + pad)] = True
    spans, i = [], 0
    while i < n:
        if mov[i]:
            j = i
            while j < n and mov[j]: j += 1
            spans.append((i, j)); i = j
        else: i += 1
    return spans


def render_jobs(jobs):
    """jobs: {out_path: job} from assets.PENDING (kind == 'remotion'). Renders all; raises on failure.
    Pass 1: every job at 30 fps (JPEG when solid, PNG when it has alpha). Pass 2: only the moving spans again at 30*S fps
    for motion blur. Then one ffmpeg graph per job joins still frames + blurred spans and converts to HLG."""
    if not jobs: return
    tmp = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"), prefix="gfx_")
    try:
        meta, b1 = {}, []
        for i, (out, j) in enumerate(jobs.items()):
            dw, dh = design_of(j["w"], j["h"], j.get("design")); scale = j["w"] / dw
            S = int(j["props"].get("_kit", {}).get("motion_blur", 8) or 1)
            props = _prep_props(dict(j["props"], _alpha=bool(j["alpha"])), scale)
            fmt = "png" if j["alpha"] else "jpeg"
            d1 = os.path.join(tmp, f"j{i}_a")
            b1.append(dict(id=str(i), template=j["template"], props=props, frames=j["frames"], fps=30, design=[dw, dh], scale=scale, outDir=d1, format=fmt))
            meta[str(i)] = dict(out=out, job=j, d1=d1, S=S, props=props, design=[dw, dh], scale=scale, fmt=fmt)
        t0 = time.time()
        log(f"graphics: pass 1, {len(b1)} job(s), {sum(x['frames'] for x in b1)} frames")
        _node(b1, tmp, "a")
        b2 = []
        for k, m in meta.items():
            m["spans"] = motion_spans(m["d1"], m["job"]["frames"]) if m["S"] > 1 else []
            for si, (a, b) in enumerate(m["spans"]):
                d2 = os.path.join(tmp, f"j{k}_b{si}")
                b2.append(dict(id=f"{k}.{si}", template=m["job"]["template"], props=m["props"], frames=m["job"]["frames"] * m["S"], fps=30 * m["S"],
                               design=m["design"], scale=m["scale"], outDir=d2, format=m["fmt"], range=[a * m["S"], b * m["S"] - 1]))
                m.setdefault("d2", []).append(d2)
        if b2:
            log(f"graphics: pass 2 (motion blur), {len(b2)} span(s), {sum((x['range'][1] - x['range'][0] + 1) for x in b2)} sub-frames")
            _node(b2, tmp, "b")
        log(f"graphics: Remotion done in {time.time() - t0:.0f}s")
        for k, m in meta.items(): _encode(m)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _encode(m):
    """Frames -> one HLG ProRes clip. Each piece (plain 30 fps frames, or a 240 fps motion-blur span averaged down to 30)
    is encoded on its own to an exact length (last frame cloned if a piece comes up short), then the pieces are joined with
    the concat demuxer. One ffmpeg per piece: a single graph with several image inputs + the concat filter stalled for
    ever when a blur span delivered a frame short (REA video, 2026-10-18)."""
    j, S, out = m["job"], m["S"], m["out"]
    n = j["frames"]
    lut = (C.hlg_lut(white=round(j["white"], 3)) if j.get("mode", "hlg") != "legacy" else __import__("studio.assets", fromlist=["x"]).legacy_lut())
    pat1, st1, _ = _seq(m["d1"])
    k = max(1, round(S * 0.625))
    pieces, cur = [], 0
    for si, (a, b) in enumerate(m.get("spans", [])):
        if a > cur: pieces.append(("still", cur, a, None))
        pieces.append(("blur", a, b, si)); cur = b
    if cur < n: pieces.append(("still", cur, n, None))
    conv = (f"lut3d=file='{lut}':interp=tetrahedral,scale=out_color_matrix=bt2020:out_range=tv:flags=accurate_rnd+full_chroma_int,"
            + ("format=yuva444p10le" if j["alpha"] else "format=yuv422p10le") + "," + C.HLG_TAGS)
    enc = (["-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits", "16"] if j["alpha"] else ["-c:v", "prores_ks", "-profile:v", "3"])
    work = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"), prefix="gfxenc_")
    try:
        parts = []
        for i, (kind, a, b, si) in enumerate(pieces):
            if kind == "still":
                inp = ["-framerate", "30", "-start_number", str(st1 + a), "-i", pat1]; f = "setpts=N/30/TB"
            else:
                pat2, st2, _ = _seq(m["d2"][si])
                inp = ["-framerate", str(30 * S), "-start_number", str(st2), "-i", pat2]
                f = (f"format=rgba64le,premultiply=inplace=1,tmix=frames={k},select='eq(mod(n\\,{S})\\,{k - 1})',"
                     "setpts=N/30/TB,unpremultiply=inplace=1")
            p = os.path.join(work, f"p{i:03d}.mov"); parts.append(p)
            ff([*inp, "-vf", f"{f},format=rgba64le,tpad=stop=-1:stop_mode=clone,trim=end_frame={b - a},{conv}",
                "-frames:v", str(b - a), *enc, *C.ENC_TAGS, "-r", "30", p], label=f"gfx {j['template']} {i + 1}/{len(pieces)}")
        if len(parts) == 1: shutil.copy(parts[0], cache.tmp(out))
        else:
            lst = os.path.join(work, "list.txt")
            with open(lst, "w") as fh: fh.write("".join(f"file '{p}'\n" for p in parts))
            ff(["-f", "concat", "-safe", "0", "-i", lst, "-map", "0:v", "-c", "copy", "-frames:v", str(n), cache.tmp(out)],
               label=f"gfx {j['template']} join")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    cache.commit(out)


def still_srgb(template, props, size, out):
    """One frame of a template as an sRGB JPEG (covers, thumbnails: pictures that are uploaded, not played as HLG)."""
    tmp = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"), prefix="still_")
    try:
        dw, dh = design_of(*size); scale = size[0] / dw
        _node([dict(id="0", template=template, props=_prep_props(dict(props), scale), frames=1, fps=30, design=[dw, dh], scale=scale,
                    outDir=tmp + "/f", format="jpeg", quality=95)], tmp, "s")
        pat, st, _ = _seq(tmp + "/f")
        shutil.copy(pat % st, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out
