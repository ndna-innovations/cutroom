"""Editing API: build and change timelines by what is said, not by hand-typed numbers.

    from studio.edit import Timeline
    tl = Timeline.new("launch-x", profile="yt4k", kit={"theme": "studio"}, folder="~/VideoWork/launch-x")
    tl.source("cam", "~/Downloads/today/cam.mov", role="camera")
    tl.source("scr", "~/Library/.../display.mp4", role="screen", sync_to="cam")     # offset found from the sound
    tl.scene_say("hook", "cam", "Google just launched", "Let's go.")                 # best (last clean) take of that line
    tl.cut_fillers("hook")
    tl.show("hook", {"word": "launched"}, kind="graphic", template="LogoHit", props={...})
    tl.layer("hook", "captions", at=0, style="phrase")
    tl.transition("hook", "dissolve", 0.2)
    print(tl.lint()); tl.save(); tl.render()

Everything writes the same JSON the renderer reads (see README), so Claude can mix API calls and direct edits."""
import copy, json, os, re
from . import model as M, words as W, cache
from .media import probe, duration

FILLERS = ("um", "uh", "erm", "uhm", "hmm", "ah")


class Timeline:
    def __init__(self, d, path):
        self.d, self.path = d, os.path.abspath(os.path.expanduser(path))
        self.d["_path"], self.d["_dir"] = self.path, os.path.dirname(self.path)

    # ------------------------------------------------------------------ files
    @classmethod
    def new(cls, name, profile="yt4k", kit=None, folder=None):
        folder = os.path.expanduser(folder or f"~/VideoWork/{name}")
        os.makedirs(folder, exist_ok=True)
        return cls(dict(name=name, profile=profile, kit=kit or {}, sources={}, scenes=[], overlays=[], audio={}),
                   os.path.join(folder, f"{name}.json"))

    @classmethod
    def load(cls, path):
        return cls(M.load(os.path.expanduser(path)), path)

    def save(self, path=None):
        if path: self.path = os.path.abspath(os.path.expanduser(path)); self.d["_path"] = self.path; self.d["_dir"] = os.path.dirname(self.path)
        M.save(self.d, self.path); return self.path

    def copy(self, name, profile=None):
        d = copy.deepcopy({k: v for k, v in self.d.items() if not k.startswith("_")}); d["name"] = name
        if profile: d["profile"] = profile
        return Timeline(d, os.path.join(self.d["_dir"], f"{name}.json"))

    # ------------------------------------------------------------------ sources
    def source(self, sid, path, role, sync_to=None, **opts):
        """Add a source. role: camera | screen | broll | music | sfx | image. sync_to: another source id -> the time
        offset between the two recordings is found from their sound and stored as "offset" (this = other + offset)."""
        p = os.path.expanduser(path)
        if role not in ("music",) and not os.path.exists(p): raise FileNotFoundError(p)
        s = dict(path=path, role=role, **opts)
        if sync_to:
            from .ingest import audio_offset
            s["offset"] = round(audio_offset(M.src_path(self.d, sync_to), p), 3); s["sync_to"] = sync_to
        self.d["sources"][sid] = s
        return s

    def src_time(self, sid, t_other):
        """Time in source sid that matches time t_other in the source it is synced to."""
        s = self.d["sources"][sid]
        return t_other - s.get("offset", 0.0)

    # ------------------------------------------------------------------ words / takes
    def words(self, sid, a=None, b=None):
        return W.transcribe(M.src_path(self.d, sid), a, b)

    def takes(self, sid, first, last=None, a=None, b=None):
        """Every take of a line in a source: [(start, end, text, clean)] — clean = no filler or slip inside.
        `first`/`last` are the first and last words of the line ("Google says", "found zero.")."""
        ws = self.words(sid, a, b); out = []
        i = 0
        while i < len(ws):
            try: k = W.find(ws, first, start=i)
            except KeyError: break
            j = k
            if last:
                try: j = W.find(ws, last, start=k) + len(last.split()) - 1
                except KeyError: break
            seg = ws[k:j + 1]
            clean = not any(W.norm(w[2]) in FILLERS for w in seg) and not W.slips(seg)
            out.append((seg[0][0], seg[-1][1], " ".join(w[2] for w in seg), clean))
            i = k + 1
        return out

    def scene_say(self, sid_scene, source, first, last=None, take="last-clean", a=None, b=None, **opts):
        """Add a scene whose spine is the line from `first` to `last` (best take). take: last-clean | first | last | N."""
        tk = self.takes(source, first, last, a, b)
        if not tk: raise KeyError(f"line not found in {source}: {first!r} .. {last!r}")
        if take == "last-clean": pick = next((t for t in reversed(tk) if t[3]), tk[-1])
        elif take == "first": pick = tk[0]
        elif take == "last": pick = tk[-1]
        else: pick = tk[int(take)]
        src = M.src_path(self.d, source)
        a0 = min(W.quiet_point(src, pick[0] - 0.05, 0.15), pick[0] - 0.03)     # never after his first word starts
        b0 = W.extend_end(src, pick[1])              # never clip his last word
        return self.scene(sid_scene, source=source, ranges=[[round(a0, 3), round(b0 + 0.05, 3)]], **opts)

    def scene(self, sid, source=None, ranges=None, duration=None, index=None, **opts):
        sc = dict(id=sid, **opts)
        if source: sc["spine"] = dict(source=source, ranges=ranges)
        elif duration: sc["duration"] = duration
        else: raise ValueError("a scene needs a spine (source + ranges) or a duration")
        if any(s["id"] == sid for s in self.d["scenes"]): raise ValueError(f"scene {sid} exists")
        if index is None: self.d["scenes"].append(sc)
        else: self.d["scenes"].insert(index, sc)
        return sc

    def get(self, sid):
        return next(s for s in self.d["scenes"] if s["id"] == sid)

    def remove(self, sid):
        self.d["scenes"] = [s for s in self.d["scenes"] if s["id"] != sid]

    def move(self, sid, index):
        sc = self.get(sid); self.remove(sid); self.d["scenes"].insert(index, sc)

    # ------------------------------------------------------------------ cuts
    def cut(self, sid, first, last=None):
        """Remove a stretch of a scene's voice by its words (both ends included)."""
        sp = self.get(sid)["spine"]; sp.setdefault("cuts", []).append([first] + ([last] if last else []))

    def cut_fillers(self, sid, fillers=FILLERS):
        """Cut every filler word (um, uh, ...) heard in the scene's ranges."""
        sp = self.get(sid)["spine"]; n = 0
        for a, b in sp["ranges"]:
            for w in W.transcribe(M.src_path(self.d, sp["source"]), a, b):
                if W.norm(w[2]) in fillers: sp.setdefault("cuts", []).append([round(w[0], 3), round(w[1], 3)]); n += 1
        return n

    def hold(self, sid, before_range, seconds):
        """Silent face (video runs, voice muted) before range k: tool moments, waits."""
        self.get(sid)["spine"].setdefault("holds", {})[str(before_range)] = seconds

    # ------------------------------------------------------------------ picture
    def show(self, sid, at, kind, **fields):
        """Put something on screen from `at` until the next base item: camera | screen | graphic | still | broll | split | stack."""
        sc = self.get(sid); sc.setdefault("base", [{"at": 0, "kind": "camera"}] if "spine" in sc else [])
        sc["base"].append(dict(at=at, kind=kind, **fields)); return sc["base"][-1]

    def layer(self, sid, kind, at=0, until=None, **fields):
        """On top of the base: graphic | ring | captions | cutout | video | image | blur."""
        L = dict(kind=kind, at=at, **fields)
        if until is not None: L["until"] = until
        self.get(sid).setdefault("layers", []).append(L); return L

    def overlay(self, kind, at=0, until=None, **fields):
        """Timeline-wide layer (seconds of the whole video): progress bar, badge, watermark-safe labels."""
        L = dict(kind=kind, at=at, **fields)
        if until is not None: L["until"] = until
        self.d.setdefault("overlays", []).append(L); return L

    def transition(self, sid, type="dissolve", d=0.2):
        self.get(sid)["transition"] = dict(type=type, d=d)

    def music(self, sid, level):
        self.get(sid)["music"] = level

    # ------------------------------------------------------------------ check / render
    def resolve(self): return M.resolve(self.d)
    def describe(self): return M.describe(self.resolve())

    def lint(self):
        return lint(self.d)

    def render(self, out=None, **kw):
        from .render import render
        self.save(); return render(self.d, out=out, **kw)

    def frame(self, t, out=None):
        from .render import frame
        self.save(); return frame(self.d, t, out)


# ---------------------------------------------------------------------- lint
def lint(tl):
    """Problems a render would hit or a viewer would notice, before rendering. [] = clean."""
    from .catalog import TEMPLATES
    from . import audio as AU
    P = []
    for sid, s in tl.get("sources", {}).items():
        p = M.src_path(tl, sid) if s.get("role") != "music" else None
        if s.get("role") == "music":
            try: AU.music_path(s["path"])
            except Exception as e: P.append(f"source {sid}: {e}")
        elif not os.path.exists(p): P.append(f"source {sid}: missing file {p}")
    ids = set()
    for sc in tl.get("scenes", []):
        w = f"scene {sc.get('id')}"
        if sc.get("id") in ids: P.append(f"{w}: duplicate id")
        ids.add(sc.get("id"))
        if "spine" not in sc and "duration" not in sc: P.append(f"{w}: needs a spine or a duration")
        if "spine" in sc and sc["spine"].get("source") not in tl.get("sources", {}): P.append(f"{w}: unknown source {sc['spine'].get('source')}")
        for it in (sc.get("base") or []) + (sc.get("layers") or []):
            t = it.get("template") or (it.get("content") or {}).get("template")
            if t and t not in TEMPLATES: P.append(f"{w}: unknown template {t}")
            src = it.get("source") or (it.get("content") or {}).get("source")
            if src and src not in tl.get("sources", {}): P.append(f"{w}: unknown source {src}")
            props = it.get("props") or {}
            if isinstance(props.get("x"), (int, float)) and isinstance(props.get("y"), (int, float)) and props["x"] > 1630 and props["y"] > 860 and tl.get("profile", "yt4k") != "short":
                P.append(f"{w}: {t} at ({props['x']}, {props['y']}) sits in the bottom-right corner (YouTube watermark)")
            r_ = it.get("rect")
            if r_ and tl.get("profile", "yt4k") not in ("short", "short-draft"):     # boxed graphics: 4K canvas px
                x_, y_, w_, h_ = r_
                if x_ + w_ > 3840 * 0.85 and y_ + h_ > 2160 * 0.82:
                    P.append(f"{w}: {t or it.get('kind')} box {r_} reaches the bottom-right corner (YouTube watermark)")
                if x_ < 0 or y_ < 0 or x_ + w_ > 3840 or y_ + h_ > 2160:
                    P.append(f"{w}: {t or it.get('kind')} box {r_} goes off the frame")
            if tl.get("profile", "").startswith("short") and r_ and r_[1] < 270:
                P.append(f"{w}: {t or it.get('kind')} box starts above y=270 (Instagram's dimmed top band)")
        if sc.get("music") is not None and not tl.get("audio", {}).get("bed"): P.append(f"{w}: music level set but no audio.bed")
    if not P:
        try:
            R = M.resolve(tl)
            for s in R["scenes"]:
                if s["trans"] and s["trans"] >= s["nf"]: P.append(f"scene {s['id']}: transition longer than the scene")
                for L in s["layers"]:
                    if L["kind"] == "ring" and L["f1"] - L["f0"] < 15: P.append(f"scene {s['id']}: ring shown under 0.5 s")
                if s["nf"] < 15: P.append(f"scene {s['id']}: only {s['nf'] / 30:.2f}s long")
        except Exception as e:
            P.append(f"resolve failed: {e}")
    return P
