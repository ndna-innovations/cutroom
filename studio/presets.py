"""Styles: apply a creator's own editing style to a timeline in one call, so Claude only adds what is special about
this video. Nothing is built in: a style is defined in the active profile (config.profile(), e.g.
~/.config/cutroom/profiles/<name>.json, "styles": {"my-style": {...}}) and every step below runs only when the style
asks for it. Names, sign-off, handle and whoosh come from the profile too.

Give scenes a "role" and call apply(tl, "my-style"):
  roles: cold | hook | who | title | screen | camera | card | lesson | wrap | end
  style keys (all optional):
    theme, graphics_white, motion_blur, loudness        kit/audio settings
    default_transition: {"type": "dissolve", "d": 0.2}  timeline default
    section_dissolve: 0.2      hard cuts between camera scenes of one section, a dissolve of this length between sections
    bed / card_bed: 0.2        music level under camera scenes / under cards (title, end, card)
    whoosh_joins: true         the profile's whoosh at camera <-> screen/card joins
    close_every: 8.0           close-ups ("camera": {"close": "auto"}) every N s; close_last_cold: true = last piece of "cold"
    captions_on: ["cold"]      burned captions (captions_style, default "phrase") on scenes with these roles
    name_tag: true             LowerThird the first time the creator says their first name (hook / who scenes)
    end_secs: 10.0             end slate with the profile's sign-off and handle
    screen: {"cursor": true, "dim": "auto", "auto_blur": true}   defaults for screen/angle items (pointer, dimming, privacy blur)
  title=... adds a title card after the hook.
  story(...)    daily slideshows (no face): news cards, varied transitions and looks, cuts on the beat.
apply() never overwrites what the timeline already sets."""
import copy, os, random
from . import model as M
from .config import profile as _profile

CAMERA_ROLES = ("cold", "hook", "who", "camera", "lesson", "wrap")


def style(name, prof=None):
    """A style from the active profile, plus the profile's name tag text, sign-off, handle and whoosh."""
    pr = prof or _profile()
    styles = pr.get("styles") or {}
    if name not in styles: raise KeyError(f"no style '{name}' in the profile (styles: {', '.join(styles) or 'none yet'})")
    st = dict(styles[name])
    st.setdefault("name", pr.get("name", "")); st.setdefault("first_name", pr.get("first_name") or (pr.get("name", "").split() or [""])[0])
    st.setdefault("role_line", pr.get("role_line", "")); st.setdefault("signoff", pr.get("signoff") or pr.get("end_line") or "")
    st.setdefault("handle", pr.get("handle", "")); st.setdefault("whoosh", pr.get("whoosh"))
    return st


def _set(d, k, v):
    if k not in d or d[k] is None: d[k] = v


def apply(tl, style_name, title=None, sub=None, kicker=None, prof=None):
    st = style_name if isinstance(style_name, dict) else style(style_name, prof)
    tl = tl.d if hasattr(tl, "d") else tl
    kit = tl.setdefault("kit", {})
    for k in ("theme", "graphics_white"):
        if k in st: _set(kit, k, st[k])
    if "motion_blur" in st: kit.setdefault("graphics", {}).setdefault("motion_blur", st["motion_blur"])
    if "loudness" in st: tl.setdefault("audio", {}); _set(tl["audio"], "loudness", st["loudness"])
    if st.get("default_transition"): _set(tl, "default_transition", st["default_transition"])
    scenes = tl["scenes"]
    # title card right after the hook
    if title and not any(s.get("role") == "title" for s in scenes):
        hi = next((i for i, s in enumerate(scenes) if s.get("role") == "hook"), None)
        if hi is not None:
            scenes.insert(hi + 1, dict(id="title", role="title", duration=2.4, base=[dict(at=0, kind="graphic", template="TitleCard",
                                       props=dict(kicker=kicker, title=title, sub=sub))]))
    # end slate
    if st.get("end_secs") and not any(s.get("role") == "end" for s in scenes):
        scenes.append(dict(id="end", role="end", duration=st["end_secs"], base=[dict(at=0, kind="graphic", template="EndCard",
                                                                             props=dict(line=st["signoff"], handle=st["handle"]))]))
    whoosh = st.get("whoosh") if st.get("whoosh_joins") else None
    named = False
    prev_kind = None
    for i, s in enumerate(scenes):
        role = s.get("role") or ("camera" if "spine" in s else "card")
        is_cam = role in CAMERA_ROLES
        # transitions: hard cuts between camera pieces of the same section, dissolves between sections
        if st.get("section_dissolve") and i > 0 and "transition" not in s:
            s["transition"] = {"type": "cut"} if (is_cam and prev_kind == "cam" and role not in ("lesson", "wrap")) else {"type": "dissolve", "d": st["section_dissolve"]}
        # music levels by role
        if "music" not in s and ("bed" in st or "card_bed" in st):
            s["music"] = st.get("bed") if is_cam else (st.get("card_bed") if role in ("card", "title", "end") else None)
        # whoosh at section joins (camera <-> screen/card)
        kind = "cam" if is_cam else "other"
        if whoosh and i > 0 and prev_kind and kind != prev_kind and os.path.exists(whoosh):
            s.setdefault("sfx", [])
            if not any(x.get("path") == whoosh for x in s["sfx"]): s["sfx"].append(dict(at=-0.25, path=whoosh, gain=1.6))
        prev_kind = kind
        # close-up rhythm
        if "spine" in s and st.get("close_every"):
            cam = s.setdefault("camera", {}); _set(cam, "close", "auto"); _set(cam, "every", st["close_every"])
            if role == "cold" and st.get("close_last_cold"): _set(cam, "close_last", True)
        # burned captions on the chosen roles (the .srt skips them automatically)
        if role in (st.get("captions_on") or ()) and "spine" in s and not any(l.get("kind") == "captions" for l in s.get("layers", [])):
            s.setdefault("layers", []).append(dict(kind="captions", style=st.get("captions_style", "phrase"), at=0))
        # name tag the first time the creator says their first name (profile)
        if st.get("name_tag") and not named and st["first_name"] and "spine" in s and role in ("hook", "who"):
            s.setdefault("layers", []).append(dict(kind="graphic", template="LowerThird", at={"word": st["first_name"], "offset": -0.3},
                                                   until={"after": 5.0}, props=dict(name=st["name"], role=st["role_line"]), optional=True))
            named = True
        # screen recordings: the style's defaults (pointer, click rings, dimming, privacy blur ...)
        for b in s.get("base", []):
            if b.get("kind") in ("screen", "angle"):
                for k, v in (st.get("screen") or {}).items(): _set(b, k, v)
    return tl


# ---------------------------------------------------------------------- daily stories
STORY_THEMES = ["sunrise", "mint", "studio", "ink", "midnight"]
STORY_TRANSITIONS = ["slide-left", "zoom", "push-left", "circle", "wipe-up", "smooth-left", "radial", "squeeze"]


def story(name, cards, bed, folder=None, seconds=4.0, seed=None, on_beat=True, profile="short"):
    """A no-face slideshow timeline: one NewsCard per item ({kicker, headline, body, source, logo, image, date}),
    a different look and transition each day (seeded), card lengths snapped to the music's downbeats."""
    from .edit import Timeline
    rnd = random.Random(seed if seed is not None else name)
    tl = Timeline.new(name, profile=profile, kit={"theme": rnd.choice(STORY_THEMES), "graphics": {"motion_blur": 8}}, folder=folder)
    tl.source("bed", bed, role="music")
    tl.d["audio"] = {"bed": "bed", "loudness": -14.0}
    lens = [seconds] * len(cards)
    if on_beat:
        from . import analyze, audio
        b = analyze.beats(audio.music_path(bed))
        db = b["downbeats"] or b["beats"]
        t, lens = 0.0, []
        for _ in cards:
            target = t + seconds
            nxt = min((x for x in db if x > t + seconds * 0.6), key=lambda x: abs(x - target), default=target)
            lens.append(round(nxt - t, 3)); t = nxt
    trs = STORY_TRANSITIONS[:]; rnd.shuffle(trs)
    for i, (c, L) in enumerate(zip(cards, lens)):
        sc = tl.scene(f"card{i + 1}", duration=L, base=[dict(at=0, kind="graphic", template=c.get("template", "NewsCard"),
                                                             props={k: v for k, v in c.items() if k != "template"})], music=0.5)
        if i: tl.transition(sc["id"], trs[i % len(trs)], 0.35)
    tl.overlay("graphic", at=0, template="Progress", props=dict(y=0, height=10))
    return tl
