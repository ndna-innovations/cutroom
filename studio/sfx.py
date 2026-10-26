"""Sound effects from the library (never generated): index, audition reels, per-video kits, rule-based placement.

Nothing is placed unless asked: place() takes rules (which moments get a sound) from the call or from a profile style's
"sfx" key; nothing is built in. Unless a kit is set, placement picks different library sounds per moment.

    index()                          -> [{path, kind, secs, peak_db, name}] for everything under sound-library/sfx-*
    audition(kind, n=12, out)        -> numbered MP3 reel + .txt list, so he can pick by ear ("whoosh 3, hit 7")
    kit(whoosh=..., hit=..., riser=...) -> {"whoosh": path, ...} for tl["audio"]["kit"]
    place(tl, rules)                 -> adds scene sfx by the rules (returns what it placed)"""
import os, re, json, hashlib, subprocess
import numpy as np
from . import cache

from .config import path as _cfg_path
LIB = _cfg_path("sound_library")
KINDS = {   # first match wins (order matters)
    "riser": r"riser|rise|swell|build.?up|uplifter|reverse",
    "whoosh": r"whoosh|swoosh|swish|woosh|swipe|whip|sweep|pass.?by|fly.?by",
    "hit": r"impact|hit|boom|thud|slam|punch|braam|stinger|cinematic.?hit",
    "click": r"click|tick|button|ui|interface|keyboard|typing|mouse",
    "chime": r"ding|chime|notification|bell|success|confirm",
    "glitch": r"glitch|digital|static|data",
    "shutter": r"shutter|camera",
}


def _kind(name):
    if name.startswith("sfx-freesound-cc0/"): return name.split("/")[1]      # downloaded by category
    n = name.lower()
    for k, pat in KINDS.items():
        if re.search(pat, n): return k
    return "other"


def index(refresh=False):
    """Scan sound-library/sfx-* once (cached by file list): kind, length, peak."""
    files = []
    for root, _, fs in os.walk(LIB):
        if "/sfx-" not in root + "/": continue
        files += [os.path.join(root, f) for f in fs if f.lower().endswith((".wav", ".flac", ".aif", ".aiff"))]
    files.sort()
    key = hashlib.sha1(("v2\n" + "\n".join(files)).encode()).hexdigest()[:12]
    p = cache.path("probe", "sfxindex_" + key, "json")
    if os.path.exists(p) and not refresh: return json.load(open(p))
    import soundfile as sf
    out = []
    mp = os.path.join(LIB, "sfx-freesound-cc0", "manifest.json")
    man = json.load(open(mp)) if os.path.exists(mp) else {}
    for f in files:
        try:
            info = sf.info(f); secs = info.frames / info.samplerate
            if secs > 20: continue                                   # ambiences / loops: not effects
            x, sr = sf.read(f, frames=min(info.frames, int(sr_ := info.samplerate) * 20), always_2d=True)
            peak = float(20 * np.log10(np.abs(x).max() + 1e-9))
            rel = os.path.relpath(f, LIB)
            out.append(dict(path=f, rel=rel, name=os.path.basename(f), kind=_kind(rel), secs=round(secs, 2), peak_db=round(peak, 1),
                            rating=man.get(os.path.basename(f).split("_")[0], {}).get("rating")))
        except Exception:
            continue
    json.dump(out, open(p, "w")); return out


EXCLUDE = {   # names that land in a category by search drift but don't do its job in an edit
    "hit": r"small|metal|bell|church|glass|door|knock|wood|plastic|ball|hammer|stone|kick|drum hit|rim",
    "whoosh": r"page|paper|water|sword|stick|rope|whip crack", "riser": r"hit$|impact", "click": r"tongue|mouth|lighter|pen",
}


def _fits(s, kind):
    """A downloaded sound's own name must agree with its category (search results drift: a church bell under 'hit')."""
    if "/sfx-freesound-cc0/" not in s["path"]: return True
    n = s["name"].lower()
    if kind in EXCLUDE and re.search(EXCLUDE[kind], n): return False
    if kind in KINDS: return bool(re.search(KINDS[kind], n))
    try: from .freesound import QUERIES
    except Exception: return True
    nouns = {q.split()[-1][:5] for q in QUERIES.get(kind, ([kind], None))[0]} | {kind.split("-")[0][:5]}
    return any(w in n for w in nouns)


def find(kind, max_secs=None, words=None):
    xs = [s for s in index() if s["kind"] == kind and (max_secs is None or s["secs"] <= max_secs) and _fits(s, kind)]
    if words: xs = [s for s in xs if re.search(words, s["rel"], re.I)]
    return xs


def audition(kind, n=12, out=None, max_secs=4.0, words=None, seed=0):
    """Numbered reel to listen to: a spoken-free beep count is avoided; each sound is separated by 0.8 s of silence and
    listed in a .txt with its number, time and file. Picks a spread across the library (different sources)."""
    xs = find(kind, max_secs, words)
    if not xs: raise RuntimeError(f"no '{kind}' sounds in the library yet")
    rng = np.random.default_rng(seed)
    by_src = {}
    for s in xs: by_src.setdefault(s["rel"].split("/")[1] if "/" in s["rel"] else "", []).append(s)
    pick = []
    srcs = list(by_src); rng.shuffle(srcs)
    while len(pick) < min(n, len(xs)):
        for k in srcs:
            if by_src[k] and len(pick) < n: pick.append(by_src[k].pop(int(rng.integers(len(by_src[k])))))
    out = out or os.path.expanduser(f"~/VideoWork/sfx-audition-{kind}.mp3")
    ins, fc, t, lines = [], [], 0.0, []
    for i, s in enumerate(pick):
        ins += ["-i", s["path"]]
        fc.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-18:TP=-2,apad=pad_dur=0.8[a{i}]")
        lines.append(f"{i + 1:2d}  at {t:5.1f}s  {s['secs']:.1f}s  {s['rel']}"); t += s["secs"] + 0.8
    fc.append("".join(f"[a{i}]" for i in range(len(pick))) + f"concat=n={len(pick)}:v=0:a=1[o]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", "[o]", "-b:a", "192k", out], check=True)
    open(os.path.splitext(out)[0] + ".txt", "w").write("\n".join(lines) + "\n")
    json.dump(pick, open(os.path.splitext(out)[0] + ".json", "w"), indent=1)
    return out, lines


def from_audition(kind, number, reel=None):
    """The file behind 'whoosh 3' in an audition reel."""
    reel = reel or os.path.expanduser(f"~/VideoWork/sfx-audition-{kind}.mp3")
    return json.load(open(os.path.splitext(reel)[0] + ".json"))[number - 1]["path"]


RULE_KEYS = ("joins", "stage_whoosh", "reveal_hit", "riser_title")   # whoosh on dissolve joins, whoosh when a floating screen enters,
                                                                      # hit on a reveal graphic, riser before the title card
REVEALS = ("TitleCard", "LogoHit", "TestCard", "VersusCard", "ScoreCard", "BigNumber", "Text3D")


def pick(kind, seed, max_secs=None, avoid=()):
    """One sound of a kind, varied by seed (deterministic: same edit = same sounds), never one in `avoid`."""
    xs = [x for x in find(kind, max_secs) if x["path"] not in avoid] or find(kind, max_secs)
    curated = [x for x in xs if "/sfx-freesound-cc0/" in x["path"]]      # sorted by category, best rated: prefer them
    if curated:
        curated.sort(key=lambda x: -(x.get("rating") or 0)); xs = curated[: max(8, len(curated) // 2)]    # the better-rated half
    if not xs: return None
    h = int(hashlib.sha1(str(seed).encode()).hexdigest()[:8], 16)
    return xs[h % len(xs)]


def norm_gain(snd, gain=1.0, peak=-8.0):
    """Linear gain that brings a library sound's peak to `peak` dBFS, times the wanted level."""
    return round(gain * 10 ** ((peak - snd.get("peak_db", -8.0)) / 20), 3)


LENGTHS = {"whoosh": 2.5, "hit": 4.0, "riser": 6.0}


def place(tl, rules, vary=True):
    """Add sound effects where `rules` say (a dict of RULE_KEYS -> True, or the name of a profile style whose "sfx" key
    holds that dict). Sounds come from tl['audio']['kit'] when set (one chosen sound per kind), otherwise from the whole
    library, varied per moment. Never on text pops (Kinetic/TextFX/Captions/Pill/Chips). Levels are normalised from
    each sound's peak."""
    d = tl.d if hasattr(tl, "d") else tl
    if isinstance(rules, str):
        from .presets import style
        rules = style(rules).get("sfx") or {}
    r = {k: bool(rules.get(k)) for k in RULE_KEYS}
    kit = d.get("audio", {}).get("kit") or {}; placed = []; used = []
    def add(sc, at, kind, gain=1.0):
        if kit.get(kind): snd = dict(path=kit[kind], peak_db=-6.0)
        elif vary: snd = pick(kind, f"{d.get('name')}:{sc['id']}:{at}:{kind}", LENGTHS.get(kind), avoid=used[-6:])
        else: snd = None
        if not snd: return
        sc.setdefault("sfx", [])
        if any(abs(x.get("at", 0) - at) < 0.05 for x in sc["sfx"]): return
        sc["sfx"].append(dict(at=at, path=snd["path"], gain=norm_gain(snd, gain))); placed.append((sc["id"], at, kind, os.path.basename(snd["path"])))
        used.append(snd["path"])
    for i, sc in enumerate(d["scenes"]):
        base = sc.get("base") or []
        if r["joins"] and i > 0 and (sc.get("transition") or {}).get("type", "cut") != "cut": add(sc, -0.25, "whoosh", 0.8)
        for b in base:
            at = b.get("at", 0) if isinstance(b.get("at", 0), (int, float)) else None
            if at is None: continue
            if b.get("kind") == "graphic" and b.get("template") in REVEALS and r["reveal_hit"]: add(sc, at + 0.05, "hit", 0.9)
            if b.get("stage") and (b["stage"] or {}).get("enter", True) and r["stage_whoosh"]: add(sc, at, "whoosh", 0.6)
        if sc.get("role") == "title" and r["riser_title"]: add(sc, -1.2, "riser", 0.6)
    return placed
