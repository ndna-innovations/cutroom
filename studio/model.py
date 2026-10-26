"""The timeline: one JSON document per video (or Short). Claude edits this; the engine renders it.

Shape (every time is in seconds; "scene time" = time inside a scene after its cuts):

{
  "name": "argon",
  "profile": "yt4k" | "short" | "draft",
  "kit": {"theme": "plain", "graphics_white": 0.75, "graphics_mode": "hlg" | "legacy"},
  "sources": {"cam": {"path": "...", "role": "camera", "face": [x, y, w, h], "touchup": false | {...Look}},
              "hay": {"path": "...", "role": "screen", "crop": [x, y, w, h]},
              "bed": {"path": "...", "role": "music"}},
  "word_fixes": {"heard words": "right words"},
  "scenes": [
    {"id": "cold",
     "spine": {"source": "cam", "ranges": [[37.25, 48.1], ...], "gap": 0.35, "pad": 0.12,
               "cuts": [["from words", "to words"], ...],      # remove a stretch (word-accurate, by text)
               "holds": {"2": 5.0}},                            # silent beat before range 2: voice off, picture frozen (no moving lips)
     "duration": 2.4,                                           # only for scenes without a spine
     "transition": {"type": "dissolve", "d": 0.2},            # into this scene (overlap with the previous one)
     "camera": {"close": "auto" | [[t0, t1], ...], "zoom": 1.14, "every": 8.0, "drift": 0.03, "close_on": ["words"...]},   # all off unless set
     "base": [ {"at": 0, "kind": "camera"},
               {"at": {"word": "Gemini"}, "kind": "screen", "source": "hay", "from": 52.0, "to": 72.0,
                "view": "fit" | {"box": [x, y, w, h], "ease": 0.8, "hold": 0.4} | {"ocr": "text", "to_text": "...", "half": "L"},
                "freeze": false, "dim": "auto" | 0.65, "blur": [[x, y, w, h]], "pip": "none" (default) | "bottom-left" | "bottom-right"},
               {"at": 12.0, "kind": "graphic", "template": "ScoreCard", "props": {...}},
               {"at": 20.0, "kind": "still", "path": "x.png"}, {"at": 0, "kind": "broll", "path": "...", "from": 0.5}],
     "layers": [ {"kind": "graphic", "template": "LowerThird", "props": {...}, "at": {"word": "Alex"}, "until": {"after": 5.0}},
                 {"kind": "ring", "on": 1, "box": [x, y, w, h] | {"ocr": "text"}, "at": ..., "until": ...},
                 {"kind": "captions", "style": "kinetic", "words": "spine" | [...]} ],
     "music": 0.17 | null,                                      # bed level under this scene (null = off)
     "sfx": [{"at": 0.0, "path": "...", "gain": 1.0}]}
  ],
  "audio": {"bed": "bed", "loudness": -14.4, "peak": -1.0, "intro": {...}, "outro": {...}}
}

Anchors ("at"/"until"): a number, {"word": "phrase", "n": 1, "after": 3.0, "offset": -0.1}, {"word_end": ...},
{"end": -1.0} (from the scene end), {"after": 5.0} (for "until": seconds after "at").
`resolve(timeline)` turns all of this into concrete frame numbers (see `Resolved`)."""
import copy, json, os
from . import words as W
from . import cache

FPS = 30
PROFILES = {
    "yt4k": dict(w=3840, h=2160, scale=1.0, codec="hevc", q=75),
    "draft": dict(w=1920, h=1080, scale=0.5, codec="hevc", q=60),
    "short": dict(w=1080, h=1920, scale=1.0, codec="hevc", q=72),
    "short-draft": dict(w=540, h=960, scale=0.5, codec="hevc", q=60),
}


def load(path):
    tl = json.load(open(path))
    tl["_path"] = os.path.abspath(path)
    tl["_dir"] = os.path.dirname(tl["_path"])
    return tl


def save(tl, path=None):
    path = path or tl["_path"]
    out = {k: v for k, v in tl.items() if not k.startswith("_")}
    tmp = path + ".tmp"
    json.dump(out, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def src_path(tl, sid):
    s = tl["sources"][sid]
    p = os.path.expanduser(s["path"])
    p = p if os.path.isabs(p) else os.path.join(tl.get("_dir", "."), p)
    if p.endswith(".json") and s.get("role") != "music":
        return nested(p, tl.get("profile", "yt4k"))
    return p


_NESTED = {}
def nested(tl_path, profile):
    """Nested clip: a source that is another timeline (.json) is rendered (cached chunks) and used as a video file,
    e.g. a finished section shown on the 3D laptop, inside a matte, or as b-roll."""
    key = (os.path.realpath(tl_path), profile, os.path.getmtime(tl_path))
    if key in _NESTED: return _NESTED[key]
    from . import render as RD, cache
    sub = load(tl_path); sub["_path"] = tl_path; sub["_dir"] = os.path.dirname(tl_path); sub["profile"] = profile
    k = cache.key("nest1", open(tl_path).read(), profile)
    out = cache.path("nested", "nest_" + k, "mp4")
    if not os.path.exists(out): RD.render(sub, out=out)
    _NESTED[key] = out
    return out


def fr(t): return int(round(t * FPS))


# --------------------------------------------------------------------------- spine
def spine_pieces(tl, sc):
    """Kept source pieces of a scene: [(src_a, src_b, hold)] where hold=True = silent face (voice muted)."""
    sp = sc.get("spine")
    if not sp: return []
    src = src_path(tl, sp["source"])
    k = cache.key("pieces7", src, sp)
    p = cache.path("plan", "pieces_" + k, "json")
    if os.path.exists(p): return [tuple(x) for x in json.load(open(p))]
    out, cuts = [], []
    word_cuts = [c for c in sp.get("cuts", []) if not isinstance(c[0], (int, float))]
    ws = []
    if word_cuts:
        for a, b in sp["ranges"]: ws += W.transcribe(src, a, b)
    exact = []
    for c in sp.get("cuts", []):
        if isinstance(c[0], (int, float)) and len(c) > 2 and c[2] == "exact":
            # one short word inside continuous speech (a filler "so"): cut at the quietest point just around it and
            # skip word snapping, which would push the edges out to the whole stretch of sound
            exact.append((W.quiet_point(src, c[0], 0.05), W.quiet_point(src, c[1], 0.05))); continue
        if isinstance(c[0], (int, float)):          # [t0, t1] source seconds (e.g. a filler found by cut_fillers)
            cuts.append((W.quiet_point(src, c[0] - 0.02, 0.08), W.quiet_point(src, c[1] + 0.02, 0.08))); continue
        i = W.find(ws, c[0]); j = W.find(ws, c[1], after=ws[i][0]) if len(c) > 1 else i
        n1 = len(c[1].split()) if len(c) > 1 else len(c[0].split())
        a = W.quiet_point(src, ws[i][0] - 0.02, 0.15)
        b = W.quiet_point(src, ws[min(len(ws) - 1, j + n1 - 1)][1] + 0.05, 0.2)
        cuts.append((a, b))
    holds = {int(k_): v for k_, v in (sp.get("holds") or {}).items()}
    snap = sp.get("snap_words", True)     # every cut lands between words (with a small pad): no first or last word clipped
    for ri, (a, b) in enumerate(sp["ranges"]):
        if snap:
            lo_, hi_ = max(0.0, a - 2.0), b + 2.0      # a little either side, to see words and sound a range edge cuts into
            wn, rn = W.voiced(src, W.transcribe(src, lo_, hi_)), W.sound_runs(src, lo_, hi_)
            a, b = W.snap_start(wn, a, runs=rn), W.snap_end(wn, b, runs=rn)
            rc = [(W.snap_end(wn, ca, runs=rn), W.snap_start(wn, cb, runs=rn)) for ca, cb in cuts if cb > lo_ and ca < hi_]
        else: rc = list(cuts)
        rc += exact
        segs = [(a, b)]
        for ca, cb in rc:
            nxt = []
            for x, y in segs:
                if cb <= x or ca >= y: nxt.append((x, y)); continue
                if ca > x: nxt.append((x, ca))
                if cb < y: nxt.append((cb, y))
            segs = nxt
        pcs = []
        for x, y in segs:
            if sp.get("tighten", True):
                tp = W.speech_pieces(src, x, y, sp.get("gap", 0.35), sp.get("pad", 0.12))
                if snap:    # a removed pause never takes the soft start or fade of a word with it
                    ex_edges = [e for c_ in exact for e in c_]          # exact cut edges stay where they are
                    keep = lambda t_, v: any(abs(t_ - e) < 0.02 for e in ex_edges) and abs(t_ - v) < 0.02
                    tp = [(p0 if keep(p0, x) else max(x, W.snap_start(wn, p0, runs=rn)),
                           p1 if keep(p1, y) else min(y, W.snap_end(wn, p1, runs=rn))) for p0, p1 in tp]
                    tp = [(round(p0 * FPS) / FPS, round(p0 * FPS) / FPS + max(1, round((p1 - p0) * FPS)) / FPS) for p0, p1 in tp]
                    for q in tp:
                        if pcs and q[0] <= pcs[-1][1] + 1e-6: pcs[-1] = (pcs[-1][0], max(pcs[-1][1], q[1]))
                        else: pcs.append(q)
                else: pcs += tp
            else: pcs.append((round(x * FPS) / FPS, round(x * FPS) / FPS + round((y - x) * FPS) / FPS))
        if ri in holds and pcs:
            h = holds[ri]
            prev_end = out[-1][1] if out else max(0.0, pcs[0][0] - h)
            out.append((prev_end, prev_end + round(h * FPS) / FPS, True))
        out += [(x, y, False) for x, y in pcs]
    json.dump(out, open(p, "w"))
    return out


def scene_words(tl, sc, pieces):
    """Checked words of the scene's own voice, in scene time."""
    sp = sc.get("spine")
    if not sp: return []
    src = src_path(tl, sp["source"])
    ws = []
    for a, b in sp["ranges"]: ws += W.transcribe(src, a, b)
    ws = W.checked(ws, {**tl.get("word_fixes", {}), **sc.get("word_fixes", {})})
    voiced = [(a, b) if not h else (a, a) for a, b, h in pieces]
    out, t = [], 0.0
    for (a, b, h) in pieces:
        if not h:
            for w in ws:
                mid = (w[0] + w[1]) / 2
                if a <= mid < b: out.append([round(t + max(0, w[0] - a), 3), round(t + min(b, w[1]) - a, 3), w[2]])
        t += b - a
    return out


def scene_words_heard(tl, sc, fpieces, nf):
    """Words of the scene's own cut voice track (what the viewer hears), in scene time, with checked fixes applied.
    More reliable than mapping source word times through the cuts (Whisper's times drift into removed pauses)."""
    from . import audio
    src = src_path(tl, sc["spine"]["source"])
    wav = audio.scene_voice(dict(id=sc["id"], src=src, pieces=fpieces, nf=nf))
    ws = W.transcribe(wav)
    held = [(p["f0"] / FPS, (p["f0"] + p["n"]) / FPS) for p in fpieces if p["hold"]]
    ws = [w for w in ws if not any(a <= (w[0] + w[1]) / 2 < b for a, b in held)]
    return W.checked(ws, {**tl.get("word_fixes", {}), **sc.get("word_fixes", {})})


# --------------------------------------------------------------------------- anchors
class AnchorError(ValueError):
    pass


_CTX = {}


def anchor(v, ws, T, at=None):
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    if not isinstance(v, dict): raise AnchorError(f"bad anchor {v!r}")
    off = v.get("offset", 0.0)
    if "word" in v:
        try: return W.cue(ws, v["word"], v.get("n", 1), v.get("after", 0.0), v.get("lead", 0.08)) + off
        except KeyError as e: raise AnchorError(str(e))
    if "word_end" in v:
        try: return W.cue_end(ws, v["word_end"], v.get("n", 1), v.get("after", 0.0)) + off
        except KeyError as e: raise AnchorError(str(e))
    if "end" in v: return T + v["end"]
    if "beat" in v or "downbeat" in v:     # music-led edits: the n-th beat of the bed, in this scene's time
        from . import analyze, audio
        tl = _CTX["tl"]; bed = tl.get("audio", {}).get("bed")
        bp = audio.music_path(tl["sources"][bed]["path"] if bed in tl["sources"] else bed)
        b = analyze.beats(bp)
        lst = b["downbeats"] if "downbeat" in v else b["beats"]
        n = v.get("downbeat", v.get("beat"))
        return lst[min(int(n), len(lst) - 1)] - _CTX.get("scene_start", 0.0) + off
    if "after" in v:
        if at is None: raise AnchorError("'after' needs an 'at'")
        return at + v["after"]
    raise AnchorError(f"bad anchor {v!r}")


# --------------------------------------------------------------------------- resolve
def resolve(tl):
    """Concrete timeline: every scene with frames, pieces, base items and layers in frame numbers.
    Returns dict(scenes=[...], total=frames, profile=...)."""
    prof = dict(PROFILES[tl.get("profile", "yt4k")])
    out, start = [], 0
    _CTX["tl"] = tl
    for si, sc in enumerate(tl["scenes"]):
        pieces = spine_pieces(tl, sc)
        if pieces:
            fpieces, f = [], 0
            for a, b, h in pieces:
                n = max(1, fr(b - a)); fpieces.append(dict(a=a, n=n, f0=f, hold=h)); f += n
            nf = f + fr(sc.get("tail", 0.0))
            if sc.get("tail"): fpieces[-1]["n"] += fr(sc["tail"]); fpieces[-1]["tail"] = fr(sc["tail"])
        else:
            fpieces, nf = [], fr(sc["duration"])
        T = nf / FPS
        ws = scene_words_heard(tl, sc, fpieces, nf) if pieces else []
        tr = sc.get("transition") or tl.get("default_transition")
        dn = fr(tr["d"]) if (tr and si > 0 and tr.get("type", "dissolve") != "cut") else 0
        start -= dn
        _CTX["scene_start"] = start / FPS
        rs = dict(id=sc["id"], index=si, start=start, nf=nf, pieces=fpieces, words=ws, trans=dn, spine=sc.get("spine"),
                  music=sc.get("music"), sfx=sc.get("sfx", []), src=src_path(tl, sc["spine"]["source"]) if sc.get("spine") else None,
                  source_id=sc["spine"]["source"] if sc.get("spine") else None, raw=sc)
        # base items
        base = []
        for it in sc.get("base") or ([{"at": 0, "kind": "camera"}] if pieces else []):
            t0 = anchor(it.get("at", 0), ws, T)
            b_ = dict(it, f0=max(0, min(nf, fr(t0))))
            if "props" in b_: b_["props"] = resolve_props(b_["props"], ws, T, b_["f0"] / FPS)
            if isinstance(b_.get("stage"), dict): b_["stage"] = resolve_props(b_["stage"], ws, T, b_["f0"] / FPS)   # word-timed poses
            if isinstance(b_.get("content"), dict) and "props" in b_["content"]:     # Shorts stack: a board graphic on top, timed by words
                b_["content"] = dict(b_["content"], props=resolve_props(b_["content"]["props"], ws, T, b_["f0"] / FPS))
            if b_.get("panels"):   # split panels: word-timed props are seconds from the split's start
                b_["panels"] = [dict(p_, props=resolve_props(p_["props"], ws, T, b_["f0"] / FPS)) if "props" in p_ else p_ for p_ in b_["panels"]]
            if isinstance(b_.get("content"), dict) and b_["content"].get("panels"):   # Shorts stack with a split on top: same for its panels
                b_["content"] = dict(b_["content"], panels=[dict(p_, props=resolve_props(p_["props"], ws, T, b_["f0"] / FPS)) if "props" in p_ else p_
                                                            for p_ in b_["content"]["panels"]])
            for holder in (b_, b_.get("content")):
                v = holder.get("view") if holder else None
                if isinstance(v, dict) and isinstance(v.get("box"), dict):     # zoom target found by OCR
                    from . import ocr
                    bx = v["box"]; sp_ = src_path(tl, holder["source"])
                    holder["view"] = dict(v, box=ocr.find_box(sp_, bx.get("at", holder.get("from", 0.0)), bx["ocr"], bx.get("to"), bx.get("half"), bx.get("pad", 14)))
            base.append(b_)
        base.sort(key=lambda b: b["f0"])
        for i, b in enumerate(base): b["f1"] = base[i + 1]["f0"] if i + 1 < len(base) else nf
        base = [b for b in base if b["f1"] > b["f0"]]
        if not base: raise AnchorError(f"scene {sc['id']}: nothing on screen")
        if base[0]["f0"] > 0: base[0]["f0"] = 0
        rs["base"] = base
        # layers
        lay = []
        for it in sc.get("layers", []):
            try:
                t0 = anchor(it.get("at", 0), ws, T)
                t1 = anchor(it.get("until", {"end": 0}), ws, T, at=t0)
            except AnchorError:
                if it.get("optional"): continue      # e.g. the name tag when the name is not said here
                raise
            f0, f1 = max(0, fr(t0)), min(nf, fr(t1))
            if f1 > f0:
                l_ = dict(it, f0=f0, f1=f1)
                if "props" in l_: l_["props"] = resolve_props(l_["props"], ws, T, f0 / FPS)
                if "anim" in l_: l_["anim"] = resolve_props(l_["anim"], ws, T, f0 / FPS)     # keyframe times can be words
                if l_.get("kind") == "matte" and isinstance(l_.get("matte"), dict) and "props" in l_["matte"]:
                    l_["matte"] = dict(l_["matte"], props=resolve_props(l_["matte"]["props"], ws, T, f0 / FPS))
                if it.get("optional") and it["kind"] == "ring" and isinstance(it.get("box"), dict) and "ocr" in it["box"]:
                    # optional ring whose text isn't on screen at that moment: skip it instead of failing the render
                    under = next((b for b in base if b["f0"] <= f0 < b["f1"] and b.get("source")), None)
                    if under:
                        from . import ocr
                        bx = it["box"]
                        try: ocr.find_box(src_path(tl, under["source"]), bx.get("at", 0.0), bx["ocr"], bx.get("to"), half=bx.get("half"), pad=bx.get("pad", 14))
                        except Exception as e:
                            from .media import log; log(f"scene {sc['id']}: optional ring skipped ({str(e)[:80]})"); continue
                lay.append(l_)
        rs["layers"] = lay
        adj = []
        for it in sc.get("adjust", []):     # adjustment layers: a look over everything for a time range
            t0 = anchor(it.get("at", 0), ws, T); t1 = anchor(it.get("until", {"end": 0}), ws, T, at=t0)
            if fr(t1) > fr(t0): adj.append(dict(it, f0=max(0, fr(t0)), f1=min(nf, fr(t1))))
        rs["adjust"] = adj
        rs["close"] = closeups(sc, fpieces, ws, nf)
        out.append(rs); start += nf
    ovl = []
    for it in tl.get("overlays", []):          # timeline-wide layers, plain seconds of the whole timeline
        f0 = max(0, fr(anchor(it.get("at", 0), [], start / FPS)))
        f1 = min(start, fr(anchor(it.get("until", {"end": 0}), [], start / FPS, at=f0 / FPS)))
        if f1 > f0: ovl.append(dict(it, f0=f0, f1=f1))
    return dict(scenes=out, total=start, profile=prof, name=tl.get("name", "video"), kit=tl.get("kit", {}), tl=tl, overlays=ovl)


def resolve_props(x, ws, T, t0):
    """Inside graphics props, {"$word": "million"} / {"$word_end": ..} / {"$t": 4.2} (scene time) become seconds
    relative to the graphic's own start, so animations land on his words."""
    if isinstance(x, list): return [resolve_props(v, ws, T, t0) for v in x]
    if isinstance(x, dict):
        if "$word" in x or "$word_end" in x or "$t" in x:
            a = {k[1:]: v for k, v in x.items() if k.startswith("$")}
            a.update({k: v for k, v in x.items() if not k.startswith("$")})
            if "t" in a: return round(float(a["t"]) - t0 + a.get("offset", 0), 3)
            return round(anchor(a, ws, T) - t0, 3)
        return {k: resolve_props(v, ws, T, t0) for k, v in x.items()}
    return x


def closeups(sc, fpieces, ws, nf):
    """Frame ranges shown as a close-up (hard-cut punch-in), only on full-face camera. Off unless the scene asks:
    "close": 'auto' alternates every `every` s at piece boundaries, or a list of [t0, t1]; plus pieces that contain
    any 'close_on' words."""
    cam = sc.get("camera") or {}
    c = cam.get("close")
    if isinstance(c, list): return [(fr(a), fr(b)) for a, b in c]
    out, acc, on = [], 0, False
    every = fr(cam.get("every", 8.0))
    for p in (fpieces if c == "auto" else []):
        if acc >= every: on, acc = not on, 0
        if on: out.append((p["f0"], p["f0"] + p["n"]))
        acc += p["n"]
    for w_ in cam.get("close_on", []):
        try: t = W.cue(ws, w_)
        except KeyError: continue
        f = fr(t)
        p = next((p for p in fpieces if p["f0"] <= f < p["f0"] + p["n"]), None)
        if p: out.append((p["f0"], p["f0"] + p["n"]))
    if cam.get("close_last") and fpieces: p = fpieces[-1]; out.append((p["f0"], p["f0"] + p["n"]))
    return sorted(set(out))


def describe(R):
    """Plain outline of a resolved timeline (for Claude to read)."""
    L = [f"{R['name']}  {R['total'] / FPS:.2f}s  {R['profile']['w']}x{R['profile']['h']}"]
    for s in R["scenes"]:
        L.append(f"[{s['start'] / FPS:7.2f}-{(s['start'] + s['nf']) / FPS:7.2f}] {s['id']}  ({s['nf'] / FPS:.2f}s, {len(s['pieces'])} pieces"
                 + (f", dissolve {s['trans'] / FPS:.2f}" if s['trans'] else "") + ")")
        for b in s["base"]:
            what = b["kind"] + (f" {b.get('source', '')} {b.get('from', '')}" if b["kind"] == "screen" else "") + (f" {b.get('template')}" if b["kind"] == "graphic" else "")
            L.append(f"    base {b['f0'] / FPS:6.2f}-{b['f1'] / FPS:6.2f} {what}")
        for l in s["layers"]:
            L.append(f"    layer {l['f0'] / FPS:6.2f}-{l['f1'] / FPS:6.2f} {l['kind']} {l.get('template', '')}")
        if s["words"]:
            L.append("    says: " + " ".join(w[2] for w in s["words"]))
    return "\n".join(L)
