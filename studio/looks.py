"""Looks: named, tested design bundles (optional: nothing uses a look unless the timeline picks one).

A look = one palette (accent + green/red tuned to the background), one type pairing and one structure (panel surface,
corners, motion, how a key word is marked, number marks, timer, pill, backdrop, title/cover/Short layouts). Every
graphic element below is drawn from it by one Remotion template, `Look` (graphics/src/looks.tsx, prop `el`):
  title contents list panel pill timer number plan logo term source madeby versus end short shortend cover
so a video that picks a look gets a title card, list pop-ups, stopwatch, number hit, plan card... that all match.

Looks are generated: FAMILIES (the structure + allowed fonts/backgrounds/backdrops) x 7 accents each, rotated so any two
looks in a family differ in at least two of accent / background / font / backdrop. Families differ in structure, not
only colour. Fonts are macOS system fonts (fallback stacks for other machines); nothing is bundled.

  cutroom looks list [--family F]          the library
  cutroom looks preview NAME... --out DIR  one labelled photo board per look (every element on stand-in or real frames)
  cutroom looks contact NAME... --out F    numbered contact board (title card + panel + cover per look) to pick from
  cutroom looks apply TIMELINE NAME        writes the look into the timeline's kit (old templates follow its colours)
In an edit: layer(el, at, end, **props) gives a graphic layer, e.g. layer("list", 3.0, 9.0, title=..., items=[...])."""
import colorsys, json, os

# ------------------------------------------------------------------ colour maths (sRGB, WCAG 2)

def _lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb): return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a, b, t): return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def hue(rgb):
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb)); return h * 360, s


def hue_gap(a, b):
    d = abs(hue(a)[0] - hue(b)[0]) % 360; return min(d, 360 - d)


def fit(c, bg, need):
    """c moved toward white (dark bg) or black (light bg) until it reaches `need` contrast on bg."""
    to = (255, 255, 255) if luminance(bg) < 0.2 else (0, 0, 0)
    for i in range(41):
        x = mix(c, to, i / 40)
        if contrast(x, bg) >= need: return x
    return to


def on(c):
    """Text colour on a fill of colour c: white or near-black, whichever reads better."""
    return (255, 255, 255) if contrast((255, 255, 255), c) >= contrast((20, 20, 22), c) else (20, 20, 22)


# ------------------------------------------------------------------ ingredients

ACCENTS = {   # name: sRGB as it looks on white; on dark backgrounds it is lightened until it reads (fit)
    "cobalt": (35, 80, 216), "blue": (0, 113, 227), "sky": (20, 140, 210), "indigo": (88, 86, 214),
    "violet": (124, 77, 200), "plum": (142, 58, 160), "magenta": (190, 50, 120), "coral": (240, 100, 60),
    "tangerine": (232, 118, 20), "amber": (214, 150, 20), "gold": (176, 132, 50), "ochre": (176, 110, 30),
    "copper": (184, 100, 60), "teal": (0, 128, 128), "lagoon": (0, 145, 165), "slate": (74, 96, 128),
    "graphite": (44, 44, 48),
}
GOOD = {"light": (24, 150, 80), "dark": (52, 199, 110)}
BAD = {"light": (214, 40, 66), "dark": (255, 90, 105)}

BGS = {
    "white": (255, 255, 255), "mist": (245, 245, 247), "cloud": (236, 240, 246), "paper": (246, 241, 232),
    "sand": (239, 233, 222), "graphite": (28, 28, 30), "onyx": (12, 12, 14), "charcoal": (22, 24, 27),
    "warm-dark": (30, 26, 23),
    "tint": None, "deep-tint": None,     # made from the accent: 8% over white / 14% into near-black
}

SF = "-apple-system, 'SF Pro Display', system-ui, 'Helvetica Neue', sans-serif"
FONTS = {   # name: label, head stack, body stack, head weight, case, tracking (em), number font
    "sf": dict(label="SF Pro", head=SF, w=700, track=-0.02),
    "sf-light": dict(label="SF Pro Light", head=SF, w=300, track=-0.03),
    "sf-rounded": dict(label="SF Pro Rounded", head="ui-rounded, 'SF Pro Rounded', " + SF, w=700, track=-0.01),
    "avenir": dict(label="Avenir Next", head="'Avenir Next', Avenir, sans-serif", w=700, track=-0.01),
    "avenir-heavy": dict(label="Avenir Next Heavy caps", head="'Avenir Next', Avenir, sans-serif", w=800, case="upper", track=0.02),
    "avenir-light": dict(label="Avenir Next Ultra Light", head="'Avenir Next', Avenir, sans-serif", w=200, track=-0.01),
    "avenir-cond": dict(label="Avenir Next Condensed caps", head="'Avenir Next Condensed', 'Avenir Next', sans-serif", w=700, case="upper", track=0.01),
    "helvetica": dict(label="Helvetica Neue Bold", head="'Helvetica Neue', Helvetica, Arial, sans-serif", w=700, track=-0.03),
    "helvetica-light": dict(label="Helvetica Neue Light", head="'Helvetica Neue', Helvetica, Arial, sans-serif", w=300, track=-0.03),
    "futura": dict(label="Futura caps", head="Futura, 'Avenir Next', sans-serif", w=700, case="upper", track=0.03),
    "gill": dict(label="Gill Sans", head="'Gill Sans', 'Gill Sans MT', sans-serif", w=600, track=0.0),
    "din": dict(label="DIN Alternate", head="'DIN Alternate', 'Helvetica Neue', sans-serif", w=700, track=0.0, num="'DIN Alternate', 'Helvetica Neue', sans-serif"),
    "din-cond": dict(label="DIN Condensed caps", head="'DIN Condensed', 'Avenir Next Condensed', sans-serif", w=700, case="upper", track=0.02, num="'DIN Condensed', 'Avenir Next Condensed', sans-serif"),
    "seravek": dict(label="Seravek", head="Seravek, 'Avenir Next', sans-serif", w=600, track=-0.01),
    "optima": dict(label="Optima", head="Optima, 'Avenir Next', sans-serif", w=700, track=0.0),
    "new-york": dict(label="New York + SF", head="ui-serif, 'New York', Georgia, serif", w=600, track=-0.02),
    "charter": dict(label="Charter + SF", head="Charter, 'Iowan Old Style', Georgia, serif", w=700, track=-0.01),
    "iowan": dict(label="Iowan Old Style + SF", head="'Iowan Old Style', Charter, Georgia, serif", w=600, track=-0.01),
    "athelas": dict(label="Athelas + SF", head="Athelas, Charter, Georgia, serif", w=700, track=-0.01),
    "didot": dict(label="Didot + SF", head="Didot, 'Bodoni 72', Georgia, serif", w=700, track=-0.01),
    "mono": dict(label="SF Mono + SF", head="ui-monospace, 'SF Mono', Menlo, monospace", w=600, track=-0.02, num="ui-monospace, 'SF Mono', Menlo, monospace"),
}
MONO = "ui-monospace, 'SF Mono', Menlo, monospace"

# Structure per family. Lists are rotated across the family's variants; scalars are fixed (they ARE the family).
# surface: glass|solid|elevated|outline|flat|editorial|block|stack|none     radius: px at 1920 design width
# motion: pop|scale|rise|slide|wipe|mask|fade|type   emph: color|underline|marker|block|weight|gradient
# mark: circle|square|numeral|mono|dot|bar           timer: ring|digital|bar|dial|flip
# pill: solid|soft|outline|tag|bar|ink               title: center|left|split|corner|stack
# cover: stack|proof|poster|split|band               caption (Shorts): band|pill|clean|block|card   header: badge|bar|tab
FAMILIES = {
    "keynote": dict(label="Keynote", statement="Stage keynote: rich dark room, big confident type, cards that lift in.",
                    accents=["cobalt", "coral", "amber", "violet", "teal", "magenta", "sky"], bgs=["onyx", "graphite", "deep-tint", "charcoal"],
                    fonts=["sf", "avenir", "helvetica", "seravek"], backdrops=["gradient", "plain"],
                    surface="elevated", radius=28, motion="scale", emph="color", mark="circle", timer="ring", pill="solid", title="center",
                    cover="stack", caption="pill", header="badge"),
    "air": dict(label="Air", statement="Light and airy like a product page: frosted glass, soft rise, lots of white.",
                accents=["blue", "indigo", "coral", "lagoon", "plum", "tangerine", "slate"], bgs=["white", "mist", "cloud"],
                fonts=["sf", "sf-rounded", "avenir", "seravek"], backdrops=["gradient", "plain", "dots"],
                surface="glass", radius=32, motion="rise", emph="color", mark="dot", timer="ring", pill="soft", title="center",
                cover="proof", caption="card", header="badge"),
    "editorial": dict(label="Editorial", statement="A magazine feature: serif headlines, hairline rules, words underlined as said.",
                      accents=["coral", "cobalt", "plum", "teal", "ochre", "copper", "graphite"], bgs=["paper", "white", "sand"],
                      fonts=["new-york", "charter", "iowan", "athelas", "didot"], backdrops=["plain", "lines"],
                      surface="editorial", radius=0, motion="mask", emph="underline", mark="numeral", timer="digital", pill="outline", title="left",
                      cover="poster", caption="clean", header="bar"),
    "swiss": dict(label="Swiss", statement="International style: strict grid, flush-left bold sans, square corners, one strong colour.",
                  accents=["cobalt", "tangerine", "graphite", "indigo", "teal", "magenta", "amber"], bgs=["white", "mist", "onyx"],
                  fonts=["helvetica", "sf", "din", "avenir"], backdrops=["grid", "plain"],
                  surface="flat", radius=0, motion="wipe", emph="block", mark="mono", timer="bar", pill="bar", title="left",
                  cover="band", caption="block", header="bar"),
    "technical": dict(label="Technical", statement="Engineer's notebook: mono labels, hairline outlines, a fine grid, text that types on.",
                      accents=["lagoon", "amber", "violet", "blue", "coral", "teal", "sky"], bgs=["charcoal", "onyx", "white", "graphite"],
                      fonts=["mono", "din", "sf"], backdrops=["grid", "dots", "lines"],
                      surface="outline", radius=8, motion="type", emph="marker", mark="mono", timer="digital", pill="tag", title="left",
                      cover="stack", caption="band", header="tab"),
    "soft": dict(label="Soft", statement="Calm studio tint: the whole frame washed in the accent, big rounded white cards.",
                 accents=["indigo", "coral", "teal", "plum", "sky", "amber", "magenta"], bgs=["tint", "cloud"],
                 fonts=["sf-rounded", "avenir", "seravek", "sf"], backdrops=["shape", "plain"],
                 surface="solid", radius=44, motion="pop", emph="color", mark="circle", timer="ring", pill="soft", title="center",
                 cover="proof", caption="pill", header="badge"),
    "block": dict(label="Block", statement="Poster blocks: solid colour fields, heavy caps, panels that slide in like signs.",
                  accents=["cobalt", "tangerine", "violet", "teal", "magenta", "blue", "copper"], bgs=["white", "mist", "paper"],
                  fonts=["futura", "avenir-heavy", "helvetica", "din-cond"], backdrops=["band", "plain", "split"],
                  surface="block", radius=0, motion="slide", emph="block", mark="square", timer="flip", pill="solid", title="split",
                  cover="band", caption="block", header="bar"),
    "aurora": dict(label="Aurora", statement="Dark glass over a slow colour wash: premium, quiet, gentle blur-in.",
                   accents=["violet", "sky", "coral", "indigo", "lagoon", "magenta", "amber"], bgs=["deep-tint", "onyx"],
                   fonts=["sf", "avenir", "seravek", "optima"], backdrops=["mesh"],
                   surface="glass", radius=24, motion="fade", emph="gradient", mark="circle", timer="ring", pill="soft", title="center",
                   cover="poster", caption="pill", header="badge"),
    "product": dict(label="Product", statement="Apple product page: light grey stage, white cards, headline words in a colour gradient.",
                    accents=["blue", "plum", "tangerine", "teal", "indigo", "coral", "cobalt"], bgs=["mist", "white"],
                    fonts=["sf", "helvetica", "avenir"], backdrops=["plain", "gradient"],
                    surface="elevated", radius=24, motion="rise", emph="gradient", mark="numeral", timer="dial", pill="ink", title="center",
                    cover="proof", caption="card", header="badge"),
    "paper": dict(label="Paper", statement="Printed page: warm paper grain, book serifs, key words marked with a highlighter.",
                  accents=["copper", "teal", "cobalt", "plum", "ochre", "slate", "magenta"], bgs=["paper", "sand"],
                  fonts=["charter", "iowan", "gill", "optima"], backdrops=["paper", "lines"],
                  surface="outline", radius=6, motion="fade", emph="marker", mark="numeral", timer="digital", pill="outline", title="left",
                  cover="stack", caption="clean", header="tab"),
    "data": dict(label="Data", statement="Scoreboard energy: condensed caps, huge numbers, bars that race.",
                 accents=["amber", "sky", "coral", "lagoon", "violet", "cobalt", "tangerine"], bgs=["onyx", "white", "graphite", "mist"],
                 fonts=["din-cond", "avenir-cond", "din"], backdrops=["band", "grid"],
                 surface="solid", radius=4, motion="slide", emph="block", mark="bar", timer="bar", pill="bar", title="left",
                 cover="band", caption="band", header="bar"),
    "frame": dict(label="Frame", statement="Gallery frame: a thin border round the picture, text pinned to its corners.",
                  accents=["slate", "coral", "gold", "teal", "indigo", "plum", "blue"], bgs=["white", "paper", "onyx", "charcoal"],
                  fonts=["gill", "avenir", "optima", "futura"], backdrops=["frame"],
                  surface="outline", radius=0, motion="wipe", emph="underline", mark="numeral", timer="dial", pill="outline", title="corner",
                  cover="poster", caption="clean", header="tab"),
    "split": dict(label="Split", statement="Two-tone stage: a colour field on one side, the story on the other.",
                  accents=["coral", "cobalt", "teal", "violet", "amber", "magenta", "sky"], bgs=["white", "mist", "graphite"],
                  fonts=["sf", "futura", "avenir", "helvetica"], backdrops=["split"],
                  surface="solid", radius=16, motion="slide", emph="color", mark="circle", timer="ring", pill="solid", title="split",
                  cover="split", caption="card", header="badge"),
    "graphite": dict(label="Graphite", statement="Night-mode pro app: graphite cards, crisp SF, quick springy pops.",
                     accents=["tangerine", "blue", "lagoon", "violet", "coral", "amber", "indigo"], bgs=["graphite", "charcoal"],
                     fonts=["sf", "sf-rounded", "helvetica", "seravek"], backdrops=["plain", "dots"],
                     surface="solid", radius=20, motion="pop", emph="color", mark="dot", timer="digital", pill="soft", title="left",
                     cover="stack", caption="pill", header="badge"),
    "gallery": dict(label="Gallery", statement="Big quiet type: thin display weights, the key word goes bold, almost nothing else.",
                    accents=["graphite", "cobalt", "coral", "plum", "teal", "gold", "indigo"], bgs=["white", "onyx", "paper"],
                    fonts=["helvetica-light", "sf-light", "didot", "avenir-light"], backdrops=["plain"],
                    surface="none", radius=0, motion="fade", emph="weight", mark="numeral", timer="digital", pill="outline", title="center",
                    cover="poster", caption="clean", header="tab"),
    "stack": dict(label="Stack", statement="iOS widgets: layered rounded cards with a second card peeking behind.",
                  accents=["sky", "violet", "coral", "teal", "blue", "magenta", "amber"], bgs=["cloud", "mist", "graphite", "tint"],
                  fonts=["sf", "sf-rounded", "seravek", "avenir"], backdrops=["dots", "gradient", "plain"],
                  surface="stack", radius=36, motion="pop", emph="color", mark="circle", timer="ring", pill="solid", title="stack",
                  cover="proof", caption="card", header="badge"),
}
VARIANTS = 7
STRUCTURE = ("surface", "radius", "motion", "emph", "mark", "timer", "pill", "title", "cover", "caption", "header")
ELEMENTS = ("title", "contents", "list", "panel", "pill", "timer", "number", "plan", "logo", "term", "source", "madeby",
            "versus", "end", "short", "shortend", "cover")


def _bg(name, accent):
    if name == "tint": return mix((255, 255, 255), accent, 0.09)
    if name == "deep-tint": return mix((13, 14, 17), accent, 0.16)
    return BGS[name]


_COMBOS = {}
def _combos(family):
    """(background, font, backdrop) per variant: picked greedily so each new variant is as far as possible from the ones
    before it (most ingredients different); no two variants of a family share all three."""
    if family not in _COMBOS:
        import itertools
        F = FAMILIES[family]; pool = list(itertools.product(F["bgs"], F["fonts"], F["backdrops"])); out = [pool.pop(0)]
        while len(out) < VARIANTS:
            score = lambda c: (min(sum(x != y for x, y in zip(c, o)) for o in out), -sum(c[0] == o[0] for o in out), -sum(c[1] == o[1] for o in out))
            best = max(pool, key=score); pool.remove(best); out.append(best)
        _COMBOS[family] = out
    return _COMBOS[family]


def build(family, i):
    F = FAMILIES[family]
    an = F["accents"][i % len(F["accents"])]
    bgn, fn, bd = _combos(family)[i]
    a0 = ACCENTS[an]; bg = _bg(bgn, a0)
    dark = luminance(bg) < 0.2; mode = "dark" if dark else "light"
    warm = bgn in ("paper", "sand", "warm-dark")
    ink = (245, 245, 247) if dark else ((36, 30, 26) if warm else (29, 29, 31))
    sub = (168, 168, 175) if dark else ((96, 88, 80) if warm else (96, 96, 102))
    if F["surface"] in ("glass", "solid", "elevated", "stack") and not dark: surface = (255, 255, 255) if bgn != "white" else (247, 247, 249)
    elif dark: surface = mix(bg, (255, 255, 255), 0.075)
    else: surface = mix(bg, (255, 255, 255), 0.5) if bgn != "white" else (244, 244, 246)
    accent = fit(a0, bg, 3.2)
    if contrast(accent, surface) < 3.0: accent = fit(accent, surface, 3.0)
    while contrast(on(accent), accent) < 4.5:   # text on an accent fill must read too: push the accent a little further
        accent = mix(accent, (0, 0, 0) if not dark else (255, 255, 255), 0.04)
    accent2 = fit(tuple(round(c * 255) for c in colorsys.hls_to_rgb(((hue(a0)[0] + 38) % 360) / 360, *colorsys.rgb_to_hls(*(c / 255 for c in a0))[1:])), bg, 3.0)
    good, bad = fit(GOOD[mode], surface, 3.0), fit(BAD[mode], surface, 3.0)
    f = FONTS[fn]
    name = f"{family}-{an}"
    return dict(
        name=name, family=family, n=i + 1, label=f"{F['label']} · {an.capitalize()} · {f['label']}", statement=F["statement"],
        mode=mode, accent_name=an, bg_name=bgn, font_name=fn, backdrop=bd,
        bg=list(bg), card=list(surface), ink=list(ink), sub=list(sub), line=list(mix(bg, ink, 0.16)),
        accent=list(accent), accent2=list(accent2), accent_ink=list(on(accent)), good=list(good), bad=list(bad),
        tint=list(mix(bg, accent, 0.14)),
        head=f["head"], body=(SF if family != "gallery" else f["head"]), num=f.get("num", f["head"]), mono=MONO,
        head_w=f["w"], case=f.get("case", "none"), track=f.get("track", 0.0),
        **{k: F[k] for k in STRUCTURE})


LOOKS = {}
for _fam in FAMILIES:
    for _i in range(VARIANTS):
        _L = build(_fam, _i); LOOKS[_L["name"]] = _L


def names(family=None): return [k for k, v in LOOKS.items() if not family or v["family"] == family]


def get(name):
    if isinstance(name, dict): return name
    if name not in LOOKS:
        near = [k for k in LOOKS if name.split("-")[0] in k][:6]
        raise KeyError(f"no look '{name}'" + (f"; did you mean {', '.join(near)}?" if near else f" ({len(LOOKS)} looks: cutroom looks list)"))
    return LOOKS[name]


def resolve(look):
    """Look dict for a name, a dict, or a {"base": name, ...overrides} dict (e.g. a different accent for one video)."""
    if not look: return None
    if isinstance(look, str): return dict(get(look))
    if "base" in look: return {**get(look["base"]), **{k: v for k, v in look.items() if k != "base"}}
    return look


def kit(name, kit=None):
    """Kit settings for a look: `look` for the Look template + colours/font so the older templates follow it too."""
    L = get(name); k = dict(kit or {})
    k["look"] = L["name"]
    k["colors"] = dict(k.get("colors", {}), bg=L["bg"], accent=L["accent"], text=L["ink"])
    k.setdefault("graphics", {})
    k["graphics"] = dict(k["graphics"], font=L["body"], display=L["head"], mono=L["mono"])
    return k


def apply(tl, name):
    """Give a timeline (dict or edit.Timeline) a look. Returns the timeline dict."""
    d = tl.d if hasattr(tl, "d") else tl
    d["kit"] = kit(name, d.get("kit")); return d


def layer(el, at, end=None, **props):
    """A graphic layer drawn in the timeline's look, shown from `at` to `end` (the layer's anchors; `until` in props is the
    timer's own stop time). el: one of ELEMENTS. Full-screen elements (title, contents, end, shortend, cover) belong in
    "base" items instead: base(el, at, **props)."""
    assert el in ELEMENTS, f"unknown look element {el}: {ELEMENTS}"
    d = dict(kind="graphic", template="Look", at=at, props=dict(el=el, **props))
    if end is not None: d["until"] = end
    return d


def base(el, at, **props):
    assert el in ELEMENTS, f"unknown look element {el}: {ELEMENTS}"
    return dict(at=at, kind="graphic", template="Look", props=dict(el=el, **props))


# ------------------------------------------------------------------ boards (photo boards to pick from)

DEMO = {   # content + the moment each element is caught at on a board (seconds into the graphic)
    "title": (dict(kicker="HYPE VS REALITY", title="I tested it on real work", keys=["real"], sub="Seven tests. One score."), 2.2),
    "contents": (dict(title="What we cover", items=["The claim", "Setup on camera", "Seven real tests", "The score"]), 3.2),
    "list": (dict(title="Three things to check", items=[{"text": "Does it read the files?", "at": 0.3}, {"text": "Can it run the tests?", "at": 0.9},
                                                       {"text": "What does it cost?", "at": 1.5}]), 2.6),
    "panel": (dict(title="Why it matters", lines=["One place for every tool", "No copy and paste", "Answers in minutes"], keys=["minutes"]), 2.4),
    "pill": (dict(text="Test it on your real work", keys=["real", "work"]), 1.8),
    "timer": (dict(label="Build time", until=2.4, rate=230, done="9 min"), 3.2),
    "number": (dict(value=73, suffix="%", label="of answers were right", sub="27 of 37 checks", good=True), 2.6),
    "plan": (dict(title="Today we test", steps=[{"text": "Install it", "at": 0.2, "done_at": 0.9}, {"text": "Build an app", "at": 0.4, "done_at": 1.6},
                                                {"text": "Score it", "at": 0.6}]), 2.4),
    "logo": (dict(name="Claude Code", color=[217, 119, 87], letter="C"), 1.4),
    "term": (dict(short="REA", full="Reverse Engineer Anything"), 1.6),
    "source": (dict(name="anthropic.com", color=[217, 119, 87], letter="A"), 1.2),
    "madeby": (dict(tool="Claude Design", color=[217, 119, 87]), 1.4),
    "versus": (dict(left=dict(name="Claude", color=[217, 119, 87]), right=dict(name="Gemini", color=[66, 133, 244])), 1.6),
    "end": (dict(line="Thanks for watching.", handle="@yourhandle"), 2.0),
    "short": (dict(badge="HYPE VS REALITY", caption="It built the app in NINE minutes", keys=["NINE"]), 1.8),
    "shortend": (dict(kicker="Full test", title="Claude vs Gemini", version="youtube"), 1.8),
    "cover": (dict(badge="HYPE VS REALITY", hook="It built my app in 9 minutes", keys=["9"]), 1.0),
}
BOARD = (3180, 1660)
MINI = (1600, 470)


def _frames(frames):
    out = {}
    for k, v in (frames or {}).items():
        if v: out[k] = "file://" + os.path.abspath(os.path.expanduser(v))
    return out


def board_props(name, frames=None, demo=None, number=None, brand=None):
    L = get(name)
    cells = {el: dict(props=dict((demo or {}).get(el, DEMO[el][0])), t=DEMO[el][1]) for el in ELEMENTS}
    if brand:   # a creator's own handle / sign-off on the end slate
        cells["end"]["props"].update({k: v for k, v in brand.items() if v})
    return dict(_look=L, cells=cells, frames=_frames(frames), number=number)


def _brand():
    try:
        from .config import profile
        p = profile(); return dict(line=p.get("signoff") or p.get("end_line"), handle=p.get("handle"))
    except Exception: return None


def render_boards(items, out_dir, frames=None, mini=False):
    """items: [(look name, number or None)]. One JPEG per look (sRGB), all rendered in one Remotion batch."""
    import shutil, tempfile
    from . import gfx
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"), prefix="looks_")
    size = MINI if mini else BOARD; brand = _brand(); outs = []
    try:
        jobs = []
        for i, (nm, num) in enumerate(items):
            props = gfx._prep_props(board_props(nm, frames, number=num, brand=brand), 1.0)
            jobs.append(dict(id=str(i), template="LookMini" if mini else "LookBoard", props=props, frames=1, fps=30, design=list(size), scale=1.0,
                             outDir=f"{tmp}/{i}", format="jpeg", quality=92))
        gfx._node(jobs, tmp, "looks")
        for i, (nm, num) in enumerate(items):
            pat, st, _ = gfx._seq(f"{tmp}/{i}")
            o = os.path.join(out_dir, (f"{num:03d}-" if num else "") + nm + ("-mini" if mini else "") + ".jpg")
            shutil.copy(pat % st, o); outs.append(o)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return outs


def contact(looks, out, frames=None, cols=2, title=None, start=1):
    """Numbered contact board: one mini strip (title card, panel over a frame, cover) per look, `cols` per row."""
    from PIL import Image, ImageDraw, ImageFont
    d = os.path.splitext(out)[0] + "-strips"
    strips = render_boards([(nm, i + start) for i, nm in enumerate(looks)], d, frames, mini=True)
    w, h = MINI; pad = 30; top = 110 if title else pad
    rows = (len(strips) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w + (cols + 1) * pad, top + rows * (h + pad)), (250, 250, 250))
    for i, p in enumerate(strips):
        sheet.paste(Image.open(p), (pad + (i % cols) * (w + pad), top + (i // cols) * (h + pad)))
    if title:
        try: f = ImageFont.truetype("/System/Library/Fonts/Avenir Next.ttc", 54, index=0)
        except Exception: f = ImageFont.load_default()
        ImageDraw.Draw(sheet).text((pad, 26), title, fill=(29, 29, 31), font=f)
    sheet.save(out, quality=90); return out


def pick(n=20):
    """A spread for a first board: every family once, then second variants; each pick takes the family's variant whose
    accent, mode and font are least used so far (a board that is not all blue or all dark)."""
    from collections import Counter
    used, out = Counter(), []
    fams = list(FAMILIES)
    for k in range(n):
        f = fams[k % len(fams)]
        cand = [nm for nm in names(f) if nm not in out]
        best = min(cand, key=lambda nm: (used[LOOKS[nm]["accent_name"]] * 3 + used[LOOKS[nm]["mode"] + str(k // len(fams))]
                                         + used[LOOKS[nm]["font_name"]], LOOKS[nm]["n"]))
        out.append(best); L = LOOKS[best]
        used.update([L["accent_name"], L["mode"] + str(k // len(fams)), L["font_name"]])
    return out


def cli(a):
    if a.action == "list":
        for nm in names(a.family):
            L = LOOKS[nm]; print(f"{nm:22s} {L['mode']:5s} {L['label']}")
        print(f"{len(names(a.family))} looks" + (f" in {a.family}" if a.family else f" in {len(FAMILIES)} families"))
    elif a.action == "show":
        for nm in a.names: print(json.dumps(get(nm), indent=1))
    elif a.action == "preview":
        frames = dict(zip(("camera", "screen", "tall"), a.frames or []))
        for p in render_boards([(nm, None) for nm in a.names], a.out or "looks-preview", frames): print(p)
    elif a.action == "contact":
        nms = a.names or pick(a.pick)
        frames = dict(zip(("camera", "screen", "tall"), a.frames or []))
        print(contact(nms, a.out or "looks-contact.jpg", frames, cols=a.cols, title=a.title))
    elif a.action == "apply":
        tl = json.load(open(a.names[0])); apply(tl, a.names[1])
        json.dump(tl, open(a.names[0], "w"), indent=1); print(f"{a.names[0]}: look {a.names[1]}")
