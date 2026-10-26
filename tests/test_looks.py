"""Look library tests. Run:  .venv/bin/python tests/test_looks.py
100+ distinct looks, readable colours (WCAG contrast), accent never confused with yes/no colours, families that differ
in structure (not only colour), no glow in the look graphics, kit/apply/layer wiring, and a real board render."""
import itertools, os, re, sys, time, traceback
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from studio import looks as K

OUT = os.path.expanduser("~/VideoWork/studio-test/looks"); os.makedirs(OUT, exist_ok=True)
RESULTS = []
def test(name):
    def deco(fn):
        t = time.time()
        try: fn(); RESULTS.append((name, "ok", time.time() - t, ""))
        except Exception as e: RESULTS.append((name, "FAIL", time.time() - t, f"{e}\n{traceback.format_exc()[-1200:]}"))
        print(f"{RESULTS[-1][1]:4s} {name} ({RESULTS[-1][2]:.1f}s)" + (f"\n     {RESULTS[-1][3]}" if RESULTS[-1][3] else ""), flush=True)
    return deco


@test("library: 100+ looks, unique names, every look complete")
def _():
    assert len(K.LOOKS) >= 100, len(K.LOOKS)
    need = {"name", "family", "label", "statement", "mode", "bg", "card", "ink", "sub", "accent", "accent_ink", "good", "bad",
            "head", "body", "num", "backdrop", *K.STRUCTURE}
    for L in K.LOOKS.values():
        miss = need - set(L); assert not miss, (L["name"], miss)
    assert len({L["label"] for L in K.LOOKS.values()}) == len(K.LOOKS), "two looks share a label"


@test("variety: inside a family any two looks differ in 2+ of accent/background/font/backdrop")
def _():
    for f in K.FAMILIES:
        for a, b in itertools.combinations([K.LOOKS[n] for n in K.names(f)], 2):
            d = sum(a[k] != b[k] for k in ("accent_name", "bg_name", "font_name", "backdrop"))
            assert d >= 2, (a["name"], b["name"])


@test("variety: any two families differ in 4+ structural choices (not just colour swaps)")
def _():
    F = K.FAMILIES
    for a, b in itertools.combinations(F, 2):
        d = sum(F[a][k] != F[b][k] for k in K.STRUCTURE)
        assert d >= 4, (a, b, d)
    assert len({L["mode"] for L in K.LOOKS.values()}) == 2
    assert len({L["font_name"] for L in K.LOOKS.values()}) >= 15


@test("readable: text 7:1, secondary 4.5:1, accent 3:1 on page and card, text on accent 4.5:1, yes/no 3:1")
def _():
    c = K.contrast
    for L in K.LOOKS.values():
        n = L["name"]
        assert c(L["ink"], L["bg"]) >= 7, n
        assert c(L["sub"], L["bg"]) >= 4.5 and c(L["sub"], L["card"]) >= 4.5, n
        assert c(L["accent"], L["bg"]) >= 3 and c(L["accent"], L["card"]) >= 3, n
        assert c(L["accent_ink"], L["accent"]) >= 4.5, n
        assert c(L["good"], L["card"]) >= 3 and c(L["bad"], L["card"]) >= 3, n


@test("accent never reads as yes/no: hue 18+ degrees from green and red")
def _():
    for L in K.LOOKS.values():
        if K.hue(L["accent"])[1] < 0.15: continue          # greys (graphite) have no hue
        assert K.hue_gap(L["accent"], L["bad"]) >= 18 and K.hue_gap(L["accent"], L["good"]) >= 18, L["name"]


@test("house rules in the look graphics: no glow, no text shadows, all elements drawn")
def _():
    src = open(os.path.join(os.path.dirname(HERE), "graphics/src/looks.tsx")).read()
    assert "textShadow" not in src and "Glow" not in src
    for m in re.findall(r"boxShadow[^,}]*", src):          # shadows are neutral (black/grey), never coloured light
        assert "rgb(L." not in m and "accent" not in m, m
    for el in K.ELEMENTS: assert re.search(rf"\b{el}: \w+", src), f"element {el} not registered"


@test("wiring: kit/apply set the look + colours, layer() makes a Look graphic, assets resolves _look")
def _():
    tl = {"kit": {"theme": "midnight"}, "scenes": []}
    K.apply(tl, "paper-teal")
    assert tl["kit"]["look"] == "paper-teal" and tl["kit"]["colors"]["accent"] == K.LOOKS["paper-teal"]["accent"]
    assert tl["kit"]["graphics"]["display"] == K.LOOKS["paper-teal"]["head"]
    ly = K.layer("timer", 3.0, 9.0, label="Build", until=4.0, done="9 min")
    assert ly["template"] == "Look" and ly["props"]["el"] == "timer" and ly["until"] == 9.0
    from studio import assets as A, catalog
    assert "Look" in catalog.TEMPLATES and "LookBoard" in catalog.TEMPLATES
    A.PENDING.clear()
    R = dict(profile=dict(w=1920, h=1080), kit=tl["kit"])
    A.graphic("Look", ly["props"], 30, R)
    job = next(iter(A.PENDING.values())); assert job["props"]["_look"]["name"] == "paper-teal"
    A.PENDING.clear()
    A.graphic("Look", dict(ly["props"], look={"base": "data-amber", "accent": [0, 0, 255]}), 30, R)
    job = next(iter(A.PENDING.values())); assert job["props"]["_look"]["family"] == "data" and job["props"]["_look"]["accent"] == [0, 0, 255]
    A.PENDING.clear()
    try: K.get("nope-look"); raise AssertionError("bad name accepted")
    except KeyError: pass


@test("render: a board and a contact strip come out as full, non-blank JPEGs")
def _():
    from PIL import Image
    outs = K.render_boards([("frame-slate", None), ("gallery-graphite", 3)], OUT)
    for o in outs:
        im = np.asarray(Image.open(o).convert("L")).astype(float)
        assert im.shape == (K.BOARD[1], K.BOARD[0]), im.shape
        # every cell has drawing in it (not a blank cell): check the 12 landscape cells' variance
        for i in range(12):
            x, y = 30 + (i % 3) * 606, 140 + 30 + (i // 3) * 384
            assert im[y:y + 320, x:x + 580].std() > 6, (o, i)
    c = K.contact(["air-blue", "block-cobalt", "editorial-coral"], os.path.join(OUT, "contact.jpg"), cols=3, title="test")
    assert Image.open(c).size[0] == 3 * K.MINI[0] + 4 * 30


print(f"\n{sum(r[1] == 'ok' for r in RESULTS)}/{len(RESULTS)} passed")
sys.exit(0 if all(r[1] == "ok" for r in RESULTS) else 1)
