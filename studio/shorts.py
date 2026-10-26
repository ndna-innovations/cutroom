"""Shorts from a finished main timeline.

A Short is just another timeline (profile "short", 1080x1920) whose scenes are pieces of the main video's scenes,
so it reuses the same renderer, cache and checks. Every Short can have its own look (spec "look", or per piece):
- "band" (default): black header (badge, white pill hook) / the screen or graphic edge to edge / a solid black caption
  band / him edge to edge below; "board": a tall board fills the top half (graphics re-laid out big for a phone), black
  band y 1080-1200, him from y 1200, badge hidden while the board is up; "seam": camera right under the content.
  Piece keys top / band / box / cam_zoom / face_at / content_y fine-tune any look; layout "board" on a piece = that look.
- quality rules for every look: readable at phone size, no wasted space at the top, cuts only at real silences (the
  loudness is measured at each cut; a cut inside sound moves to the next clean word or the first quiet moment; spec
  "snap": False turns it off), a 40 ms fade-in on each piece ("fade_in"), jump cuts as plain hard cuts ("jump": "hard" (default) | "punch" | "morph"; "punch": 1.1 = the closer shot's zoom),
  whole-Short speed with the pitch kept ("speed": 1.1);
- never shrink him: 'face' = his face full-bleed (9:16 window on his head);
- captions come from the main timeline's CHECKED words (never a fresh transcription), kinetic, key words in the accent;
- tool-only moments (his voice off: 'holds') are dropped, so no lips moving without sound;
- start ON the first word (pieces start at the first word of the chosen stretch);
- badge and hook below y=270 (Instagram header), bottom-right kept clear, progress bar on top;
- opt-in by spec (nothing is added unless asked): a music bed ("music": 0.16, ducked, from the sound library), a progress
  bar ("progress": true), an end card ("end": {..., "cta": {"youtube": [cta, sub], "insta-tiktok": [cta, sub]}});
- versions per Short (e.g. "youtube", "insta-tiktok") share every chunk except the end card; a cover JPEG (sRGB) per Short.

spec "clean": path of a render of the main timeline without the face box (pip "none"); pieces with "clean": True
(or spec "clean_all") take their top from it at the same main-video moment, so the main edit's highlights/labels come along.

spec = {"name": "argon-short1", "hook": "I hid 3 sentences in War and Peace", "badge": "GEMINI 4 ARGON vs CLAUDE",
        "keys": ["zero", "three"], "photo_at": 785.4,                          # camera time for the cover / end-card face
        "pieces": [{"scene": "cold", "from": 0, "to": 7.87, "layout": "face"},
                   {"scene": "t2b", "from": 0, "to": 12.6, "layout": "stack", "top": 0.45}],
        "end": {"title": "7 REAL TESTS", "kicker": "GEMINI vs CLAUDE", "icons": ["file://..."]}}"""
import copy, json, os
import numpy as np
from . import model as M, cache
from .model import FPS


def _source_ranges(sc, t0, t1):
    """Main-scene time [t0, t1) -> source ranges of the spine (holds dropped), plus their scene-time offsets."""
    out = []
    for p in sc["pieces"]:
        a, b = p["f0"] / FPS, (p["f0"] + p["n"]) / FPS
        lo, hi = max(a, t0), min(b, t1)
        if hi - lo < 1 / FPS or p["hold"]: continue
        out.append(([round(p["a"] + lo - a, 4), round(p["a"] + hi - a, 4)], lo))
    return out


def _content_at(sc, t, tl):
    """The main scene's base item at scene time t, re-timed so it can start at t (for the top of a stacked piece)."""
    b = next((x for x in sc["base"] if x["f0"] / FPS <= t + 1e-6 < x["f1"] / FPS), None)
    if not b or b["kind"] == "camera": return None
    it = {k: v for k, v in b.items() if k not in ("f0", "f1", "at", "pip")}
    off = t - b["f0"] / FPS
    if it["kind"] in ("screen", "broll") and not it.get("freeze"):
        D = (b["f1"] - b["f0"]) / FPS
        sp = (it["to"] - it.get("from", 0)) / D if it.get("to") is not None else it.get("speed", 1.0)
        it["from"] = it.get("from", 0) + off * sp
        if it.get("to") is not None: it.pop("to"); it["speed"] = sp
        if isinstance(it.get("view"), dict) and "box" in it["view"]:
            v = dict(it["view"]); v["hold"] = max(0, v.get("hold", 0.4) - off); it["view"] = v
    if it["kind"] == "graphic":
        it["start_at"] = round(off + b.get("start_at", 0), 3)
    if it["kind"] in ("screen", "broll"):
        it["fit"] = "fit"
        it.setdefault("view", "fit")
    return it


# looks: how a stacked part is laid out (every Short can pick its own; pieces can override). All keep the quality rules:
# boards readable at phone size, no wasted space at the top, cuts only at real silences.
LOOKS = {
    # Short 1: black header (badge + white pill hook), content edge to edge (y 380-1000), black caption band, him below
    "band": dict(top=0.52, band=0.104, content_y=0.198, cam_zoom=0.6, face_at=0.44, badge=True),
    # Short 4: a tall board fills the top half (1040x940 at y 130; graphics re-laid out big), black band y 1080-1200, him below;
    # the badge hides while the board is up (screen recordings fall back to "band")
    "board": dict(top=0.5625, band=0.0625, box=[20, 320, 1040, 750], cam_zoom=0.5625, face_at=0.44, badge=False),
    # fill: the content fills the whole top half edge to edge (no empty header; screens zoomed with views, pictures
    # cropped to fill), black caption band y 1080-1200, him from y 1200 with headroom; badge + hook sit over the content
    # the top 320 px stay the app's header band (Instagram/TikTok/YouTube labels sit there; theme backdrop + badge only)
    "fill": dict(top=0.5625, band=0.0625, box=[0, 320, 1080, 760], cam_zoom=0.5625, face_at=0.44, badge=True, fit="fill"),
    # older: camera right under the content with a soft seam, captions on the seam
    "seam": dict(top=0.45, band=0, content_y=0.17, cam_zoom=1.0, face_at=0.45, badge=True),
}


def _envelope(src):
    """Speech loudness of a source, 10 ms steps, in dBFS (cached); plus its quiet floor."""
    import subprocess
    k = cache.key("env1", src); p = cache.path("audio", "env_" + k, "npy")
    if os.path.exists(p): e = np.load(p)
    else:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"], capture_output=True).stdout
        x = np.frombuffer(raw, np.float32); n = len(x) // 80
        e = 10 * np.log10(np.mean(x[:n * 80].reshape(n, 80) ** 2, axis=1) + 1e-10); np.save(p, e)
    return e, float(np.percentile(e, 10))


def _loud(env, floor, a, b):
    i0, i1 = max(0, int(a * 100)), max(int(a * 100) + 1, int(b * 100))
    return float(np.max(env[i0:i1])) > max(floor + 14, -50) if i0 < len(env) else False


def _snap(r2, src_words, env, floor):
    """Cuts between words, never inside one: a piece edge that falls inside a word moves to just before it (most of the
    word is kept) or just after it (most of it is cut), so no first or last word is clipped or dropped (only where there
    is sound: a cut in a real pause stays put, whatever the speech model's word times say). A piece that
    still ends inside sound runs on to the first quiet moment (up to 0.25 s). src_words = [[start, end, text]] in source s."""
    from . import words as W
    out = []
    for (s0, s1), lo in r2:
        a = W.snap_start(src_words, s0) if _loud(env, floor, s0 - 0.01, s0 + 0.03) else s0     # cuts in a real pause stay put
        e1 = W.snap_end(src_words, s1) if _loud(env, floor, s1 - 0.03, s1 + 0.01) else s1
        if _loud(env, floor, e1 - 0.03, e1 + 0.01):
            e1 = next((e1 + k / 100 for k in range(1, 26) if not _loud(env, floor, e1 + k / 100 - 0.02, e1 + k / 100 + 0.02)), e1)
        out.append(([round(a, 4), round(e1, 4)], lo + a - s0))
    return out


def _merge(spans):
    out = []
    for a, b in spans:
        if out and a - out[-1][1] < 0.05: out[-1][1] = b
        else: out.append([a, b])
    return out


def build(main_tl, spec, version="youtube"):
    """Short timeline (dict) for one spec + version. Save it with model.save and render with render.render."""
    R = M.resolve(main_tl)
    scenes = {s["id"]: s for s in R["scenes"]}
    cam_id = next(k for k, v in main_tl["sources"].items() if v.get("role") == "camera")
    tl = dict(name=f"{spec['name']}-{version}", profile=spec.get("profile", "short"), kit=copy.deepcopy(main_tl.get("kit", {})),
              sources=copy.deepcopy(main_tl["sources"]), word_fixes=main_tl.get("word_fixes", {}), scenes=[],
              audio=dict(bed=spec.get("bed", main_tl.get("audio", {}).get("bed")), loudness=-14.0), _dir=main_tl.get("_dir"))
    if spec.get("speed"): tl["speed"] = float(spec["speed"])
    tl["kit"].setdefault("graphics", {})
    words_all, t_short, y_at, badge_on = [], 0.0, [], []
    look0 = spec.get("look", "band" if spec.get("band", 0.104) else "seam")
    snap = spec.get("snap", True)
    for i, pc in enumerate(spec["pieces"]):
        sc = scenes[pc["scene"]]
        env = _envelope(sc["src"]) if snap else None      # each piece is measured on its own camera file (Shorts can mix takes)
        rng = _source_ranges(sc, pc["from"], pc["to"])
        if not rng: continue
        # split a piece wherever the main scene's base item changes (each part keeps its own content on top)
        cuts = sorted({pc["from"], pc["to"], *[b["f0"] / FPS for b in sc["base"] if pc["from"] < b["f0"] / FPS < pc["to"]]})
        if pc.get("content"): cuts = [pc["from"], pc["to"]]       # its own top: one part, so word cues see the whole piece
        for part, (a, b) in enumerate(zip(cuts[:-1], cuts[1:])):
            r2 = _source_ranges(sc, a, b)
            if not r2: continue
            if env is not None:   # scene words in source time, then move cuts that land inside sound
                sw = sorted([sr[0] + (w[0] - lo), sr[0] + (w[1] - lo), w[2]] for w in sc["words"] for sr, lo in r2 if w[0] < lo + sr[1] - sr[0] and w[1] > lo)
                r2 = [x for x in _snap(r2, sw, *env) if x[0][1] - x[0][0] > 1 / FPS]
                if not r2: continue
            nid = f"{pc['scene']}_{i}_{int(a * 100)}"
            # jump cuts: "hard" (default) = plain cuts; "punch" = every other piece a little closer;
            # "morph" = RIFE morph cuts (can melt hair on bigger moves)
            jump = spec.get("jump", "hard")
            s2 = dict(id=nid, spine=dict(source=sc["source_id"], ranges=[x[0] for x in r2], tighten=False, snap_words=False, morph=spec.get("morph", 6) if jump == "morph" else 0,
                                         fade_in=spec.get("fade_in", 0.04)), music=spec.get("music"),
                      camera=dict(close="auto" if jump == "punch" else None, every=0, zoom=spec.get("punch", 1.1), drift=0, reframe=spec.get("reframe", "follow")))
            layout = pc.get("layout", "face")
            if layout == "board": layout, pc = "stack", dict(pc, look="board")
            content = _content_at(sc, a + 0.001, main_tl) if layout == "stack" else None
            if layout == "stack" and pc.get("clean", spec.get("clean_all")) and spec.get("clean"):
                # top = the same moment of a clean render of the main video (no face box): every highlight, label and pill
                # of the main edit comes along, in sync with his words (main time = scene start + the kept piece's scene time)
                content = dict(kind="broll", path=spec["clean"], fit="fit", view="fit", **{"from": round(sc["start"] / FPS + r2[0][1], 3)})
            if layout == "stack" and pc.get("content"):      # the piece names its own top (a board graphic, a picture, a clip)
                content = copy.deepcopy(pc["content"]); content.setdefault("fit", "fit")
                if content["kind"] in ("screen", "broll"): content.setdefault("view", "fit")
            v_ = (pc.get("views") or [None] * 99)[part] if pc.get("views") else pc.get("view")
            if content and v_: content["view"] = v_      # Shorts: zoom to what he talks about (readable on a phone)
            L = None
            if content:
                name = pc.get("look", look0)
                if name == "board" and content["kind"] != "graphic": name = "band"     # boards are for graphics; recordings use the band
                L = dict(LOOKS[name]); L.update({k: pc[k] for k in ("top", "band", "cam_zoom", "face_at", "box", "content_y") if k in pc})
                if L.get("fit") and content["kind"] in ("screen", "broll", "still"): content["fit"] = pc.get("fit", L["fit"])
                if name == "fill" and content["kind"] == "graphic":
                    L["badge"] = False      # a board fills the top: the badge would cover its first line
                    content.setdefault("design", pc.get("design", 760))   # smaller design box = bigger text on a phone
                if name == "fill" and content["kind"] == "split": L["badge"] = False   # a screen + step text: the badge would sit on the screen
                if "badge" in pc: L["badge"] = pc["badge"]
                if name in ("band", "seam") and "band" in spec and "band" not in pc and spec["band"] != L["band"]: L["band"] = spec["band"]
                if spec.get("cam_zoom") and "cam_zoom" not in pc: L["cam_zoom"] = spec["cam_zoom"]
                s2["base"] = [dict(at=0, kind="stack", content=content, **{k: v for k, v in L.items() if k not in ("badge", "fit")})]
            tl["scenes"].append(s2)
            # words for captions: main scene's checked words inside [a, b), mapped to short time through the kept pieces
            ws = [w for w in sc["words"] if a - 0.05 <= w[0] < b]
            # piece mapping: scene time -> short time (pieces in order, gaps removed)
            mp, acc = [], t_short
            for sr, lo in r2:
                mp.append((lo, lo + sr[1] - sr[0], acc)); acc += sr[1] - sr[0]
            for w in ws:
                for lo, hi, st in mp:
                    if lo - 0.05 <= w[0] < hi:
                        words_all.append([round(st + max(0, w[0] - lo), 3), round(st + min(hi, w[1]) - lo, 3), w[2]]); break
            y_at.append([round(t_short, 3), (L["top"] + L["band"] / 2) if L and L["band"] else (L["top"] if L else 0.74)])
            if not L or L.get("badge", True): badge_on.append([round(t_short, 3), round(acc, 3)])
            t_short = acc
    T = t_short
    # Short-wide layers (timeline time): progress bar, badge, hook, captions
    tl["overlays"] = [
        dict(kind="graphic", template="Progress", at=0, until=T, props=dict(y=0, height=10)) if spec.get("progress") else None,
        *([dict(kind="graphic", template="Pill", at=a_, until=b_, props=dict(text=spec.get("badge", ""), x=540, y=283, size=30, color="text",
             border=spec.get("badge_border", [70, 110, 210]), icon=spec.get("badge_icon"), fade=False)) for a_, b_ in _merge(badge_on)] if spec.get("badge") else [None]),
        dict(kind="graphic", template="Pill", at=0, until=min(T, spec.get("hook_secs", 2.6)),   # the hook: white rounded pill, dark text
             props=dict(text=spec["hook"], x=540, y=392, size=spec.get("hook_size", 46), bg="white", max_w=1000, fade=False)) if spec.get("hook") else None,
        dict(kind="captions", at=0, until=T, style="kinetic", keys=spec.get("keys", []), words=words_all,
             y_at=[[t, round(v * 1920)] for t, v in y_at]),
    ]
    tl["overlays"] = [o for o in tl["overlays"] if o]
    # end card: only when the spec asks for one; its call to action (per version) comes from the spec, never built in
    if "end" not in spec: return tl
    e = spec["end"] or {}
    cta, sub = "", ""
    if e.get("cta"):
        c = e["cta"].get(version) or e["cta"].get("youtube") or ["", ""] if isinstance(e["cta"], dict) else e["cta"]; cta, sub = c[0], c[1]
    end = dict(id="end", duration=e.get("secs", 2.6), transition=dict(type="dissolve", d=0.2), music=e.get("music", spec.get("music")),
               base=[dict(at=0, kind="graphic", template="ShortEnd", props=dict(cta=cta, sub=sub, title=e.get("title"), kicker=e.get("kicker"), icons=e.get("icons")))])
    if spec.get("photo_at") is not None and e.get("face") == "cutout":   # old look: his cut-out at the bottom
        end["layers"] = [dict(kind="cutout", source=cam_id, src_at=spec["photo_at"], rect=[0, 1000, 1080, 920], at=0)]
    elif spec.get("photo_at") is not None:   # default: the speaker's face as a soft blurred background, never at the bottom
        import subprocess, hashlib
        src_path = main_tl["sources"][cam_id]["path"]
        fp = cache.path("assets", "endface-" + hashlib.sha1(f"{src_path}{spec['photo_at']}".encode()).hexdigest()[:12], "png")
        if not os.path.exists(fp):   # raw ffmpeg frame: graphics inside the HDR video keep his colour (editing rules)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(spec["photo_at"]), "-i", src_path, "-frames:v", "1", fp], check=True)
        mode = e.get("face", "background")   # background | side | none ; an "image" (proof/b-roll still) can sit behind instead
        if mode != "none": end["base"][0]["props"].update(face="file://" + fp, face_mode=mode)
    if e.get("image"): end["base"][0]["props"]["image"] = "file://" + os.path.expanduser(e["image"])
    tl["scenes"].append(end)
    return tl


def cutout(src, t, out=None, matte="vision"):
    """sRGB PNG of him cut out (person mask) from the camera at time t: for covers and end cards (no red faces:
    it is converted from HLG properly, then back to HLG by the graphics pipeline)."""
    from . import frames as F, color as C
    src = os.path.expanduser(src)
    if matte == "birefnet":     # solid, clean edge (busy backgrounds); Vision keeps finer see-through hair strands
        from .ai_vision import cutout_birefnet
        return cutout_birefnet(src, t, out)
    k = cache.key("cutout4", src, round(t, 3))
    p = out or cache.path("assets", "cutout_" + k, "png")
    if os.path.exists(p): return p
    import subprocess, tempfile, cv2
    f = F.read_rgb(src, t)[0]
    srgb = (np.clip(C.hlg_to_sdr(np.clip(f.astype(np.float64), 0, 1), 0.9, 0.95), 0, 1) * 255 + 0.5).astype(np.uint8)
    d = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork")); cv2.imwrite(f"{d}/f.png", srgb[..., ::-1])
    from .ocr import ensure_bin
    subprocess.run([ensure_bin(), "person", d, d + "/m"], check=True)
    m = cv2.imread(f"{d}/m/f.png", 0)
    m = cv2.GaussianBlur(m, (0, 0), 2)
    ys, xs = np.nonzero(m > 20)
    y0, y1, x0, x1 = max(0, ys.min() - 20), srgb.shape[0], max(0, xs.min() - 20), min(srgb.shape[1], xs.max() + 20)
    rgba = np.dstack([srgb, m])[y0:y1, x0:x1]
    cv2.imwrite(p, cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)); subprocess.run(["rm", "-rf", d])
    return p


def cover(spec, main_tl, out):
    """Cover JPEG (sRGB, 1080x1920): face cut-out + hook, badge in the Instagram-safe area. spec "cover_hook" (with "|" for
    line breaks) overrides the hook text; "cover_matte": "birefnet" gives a solid cut-out edge (a mic or prop never goes see-through)."""
    from . import gfx
    cam_id = next(k for k, v in main_tl["sources"].items() if v.get("role") == "camera")
    # the face is never at the bottom of a cover: only "blur"/"crop" use it, as the background
    photo = None if spec.get("cover_style") not in ("behind_face_ok",) else spec.get("photo") or cutout(main_tl["sources"][cam_id]["path"], spec["photo_at"], matte=spec.get("cover_matte", "vision"))
    face = None
    if spec.get("cover_style") in ("blur", "crop"):   # the full camera frame (not the cut-out) for face-as-background layouts
        from . import export as EX
        face = EX.stills(main_tl["sources"][cam_id]["path"], [spec.get("cover_face_at", spec["photo_at"])], folder=os.path.dirname(os.path.abspath(out)) + "/.cover-faces")[0]
    if "cover_look" not in spec:   # the creator's chosen cover look (profile), unless the spec names one
        try:
            from .config import profile as _prof
            if _prof().get("cover_look"): spec = dict(spec, cover_look=_prof()["cover_look"])
        except Exception: pass
    props = dict(hook=spec.get("cover_hook", spec["hook"]), badge=spec.get("badge"), photo="file://" + photo if photo else None,
                 face="file://" + face if face else None, **{k: spec[f"cover_{k}"] for k in ("word", "stamp", "light") if f"cover_{k}" in spec},
                 **{k: spec[f"cover_{k}"] for k in ("style", "bg", "number", "labels", "look") if f"cover_{k}" in spec},
                 **{k: "file://" + os.path.expanduser(spec[f"cover_{k}"]) for k in ("proof", "proof2") if spec.get(f"cover_{k}")},
                 _theme={k: list(v) for k, v in __import__("studio.assets", fromlist=["x"]).theme(main_tl.get("kit", {})).items()})
    return gfx.still_srgb("Cover", props, (1080, 1920), out)
