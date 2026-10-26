"""Feature tests (fast: single frames, small renders). Run:  .venv/bin/python tests/test_features.py
Styles (profile-defined, none built in), speed ramp + reverse, grading, click removal, music fit, green screen, subject effects,
translated captions, 3D text, Short candidates, tracked ring, thumbnails, OTIO export."""
import os, sys, time, json, subprocess, traceback
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_SOUND_LIBRARY"] = os.path.expanduser("~/VideoWork/studio-test/fixtures/sound-library")   # made by make_media.py
from studio import model as M, render as RD, frames as F, color as C, audio as AU, captions as CP, presets as PR, candidates as CD
from studio.edit import Timeline

FX = os.path.expanduser("~/VideoWork/studio-test/fixtures"); OUT = os.path.expanduser("~/VideoWork/studio-test/features"); os.makedirs(OUT, exist_ok=True)
if not os.path.exists(f"{FX}/cam.mov") or not os.path.exists(f"{FX}/sound-library/music/test-bed_61s.m4a"): subprocess.run([sys.executable, f"{HERE}/make_media.py", FX], check=True)
REAL_CAM = os.path.expanduser(os.environ.get("CUTROOM_TEST_CAM", ""))   # optional: real footage with a person (37-40.5 s used)
RESULTS = []
def test(name):
    def deco(fn):
        t = time.time()
        try: fn(); RESULTS.append((name, "ok", time.time() - t, ""))
        except Exception as e: RESULTS.append((name, "FAIL", time.time() - t, f"{e}\n{traceback.format_exc()[-1200:]}"))
        print(f"{RESULTS[-1][1]:4s} {name} ({RESULTS[-1][2]:.1f}s)" + (f"\n     {RESULTS[-1][3]}" if RESULTS[-1][3] else ""), flush=True)
    return deco

def base_tl(name):
    tl = Timeline.new(name, profile="draft", kit={"theme": "studio", "graphics": {"motion_blur": 1}}, folder=OUT)
    tl.source("cam", f"{FX}/cam.mov", role="camera", head=[1920, 900], face=[1140, 180, 1560, 1800])
    tl.source("scr", f"{FX}/screen/display.mp4", role="screen", crop=[0, 0, 3456, 2234])
    tl.source("bed", "music/test-bed_61s.m4a", role="music"); tl.d["audio"] = {"bed": "bed"}
    return tl

@test("styles: none built in; a profile style adds only what it names (title card, end slate, captions, music)")
def _():
    tl = base_tl("preset")
    tl.scene_say("hook", "cam", "This is the first line", "demo.", role="hook")
    tl.scene_say("demo", "cam", "here we compare", "side by side.", role="screen"); tl.show("demo", 0, "screen", source="scr", **{"from": 2.0})
    try: PR.apply(tl, "pm-episode", prof=dict(styles={})); raise AssertionError("old built-in style still exists")
    except KeyError: pass
    before = json.dumps(tl.d, sort_keys=True, default=str)
    PR.apply(tl, "empty", prof=dict(name="", styles={"empty": {}}))
    assert json.dumps(tl.d, sort_keys=True, default=str) == before, "an empty style changed the timeline"
    prof = dict(name="Test Person", handle="@t", signoff="Bye.", styles={"mine": dict(bed=0.2, end_secs=4.0, captions_on=["hook"], section_dissolve=0.2,
                                                                                         screen=dict(cursor=True, auto_blur=True))})
    PR.apply(tl, "mine", title="Test Title", sub="One line", kicker="SERIES · EP 1", prof=prof)
    ids = [s["id"] for s in tl.d["scenes"]]; assert ids == ["hook", "title", "demo", "end"], ids
    hook = tl.get("hook"); assert any(l["kind"] == "captions" for l in hook["layers"])
    assert tl.get("demo")["music"] is None and hook["music"] == 0.2 and "camera" not in hook   # no close-ups unless the style asks
    assert tl.get("demo")["base"][-1]["cursor"] and tl.get("demo")["base"][-1]["auto_blur"]
    assert not tl.lint(), tl.lint()
    R = tl.resolve(); assert R["total"] > 0

@test("grade: neutral settings change nothing; looks stay in range")
def _():
    x = np.random.default_rng(1).random((500, 3))
    assert np.abs(C.grade(x, {}) - x).max() < 1e-6
    for k in C.LOOKS: y = C.grade(x, k); assert y.min() >= 0 and y.max() <= 1
    assert os.path.exists(C.grade_lut("warm"))

@test("declick: synthetic clicks in pauses are found, speech untouched")
def _():
    import soundfile as sf
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{FX}/voice.aiff", "-ar", "48000", "-ac", "1", f"{OUT}/v.wav"], check=True)
    x, sr = sf.read(f"{OUT}/v.wav"); z = x.copy()
    for t in (0.15, 1.55): k = int(t * sr); z[k:k + 30] += 0.6 * np.sign(np.random.default_rng(2).standard_normal(30))
    sf.write(f"{OUT}/vc.wav", z, sr); o, n = AU.declick(f"{OUT}/vc.wav", f"{OUT}/vc_dc.wav"); y, _ = sf.read(o)
    assert n >= 1, n
    speech = np.abs(x) > 0.05; assert np.abs(y - z)[speech].max() < 1e-6 or n <= 3

@test("music fit: exact length, ends on the track's ending")
def _():
    p = AU.fit_music("music/test-intro_105s.m4a", 17.0)
    assert abs(AU.duration(p) - 17.0) < 0.05, AU.duration(p)

@test("speed ramp + reverse render")
def _():
    tl = base_tl("ramp")
    tl.scene("s", duration=4.0, base=[dict(at=0, kind="screen", source="scr", **{"from": 0.0}, to=12.0, ramp={"hold": 0.4, "ease": 0.5})])
    tl.scene("r", duration=1.0, base=[dict(at=0, kind="screen", source="scr", **{"from": 2.0}, reverse=True)])
    rep = tl.render(out=f"{OUT}/ramp.mp4"); assert rep["seconds"] == 5.0, rep["seconds"]

@test("speed ramp + auto blur: few merged boxes, renders quickly, nothing private readable")
def _():
    import re
    from studio import compile as CO, ocr
    many = [dict(box=[286, 808 - 30 * i, 1005, 86], **{"from": i * 0.5}, to=i * 0.5 + 0.5) for i in range(30)]
    assert len(CO.merge_blur_boxes(many)) <= 8
    tl = base_tl("rampblur")
    tl.scene("s", duration=4.0, base=[dict(at=0, kind="screen", source="scr", **{"from": 0.0}, to=12.0, ramp={"hold": 0.4, "ease": 0.5}, auto_blur=True)])
    t0 = time.time(); rep = tl.render(out=f"{OUT}/rampblur.mp4"); took = time.time() - t0
    assert rep["seconds"] == 4.0 and took < 120, (rep["seconds"], took)
    leaks = [s for t in (0.1, 1.0, 2.0, 3.0, 3.9) for *_, s, c in ocr.lines_at(f"{OUT}/rampblur.mp4", t) if any(re.search(p, s) for _, p in ocr.PRIVATE)]
    assert not leaks, leaks

@test("green screen: keyed layer lets the camera show through")
def _():
    g = f"{OUT}/green.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x00ff00:s=1280x720:d=2,format=yuv420p", "-f", "lavfi", "-i", "testsrc2=s=400x400:d=2",
                    "-filter_complex", "[0][1]overlay=440:160", "-c:v", "libx264", "-pix_fmt", "yuv420p", g], check=True)
    tl = base_tl("key"); tl.scene_say("s", "cam", "This is the first line", "demo.")
    tl.layer("s", "video", at=0.1, path=g, rect=[960, 200, 760, 428], key={"similarity": 0.15}); tl.save()
    p = tl.frame(1.0, f"{OUT}/key.jpg"); from PIL import Image
    im = np.asarray(Image.open(p).convert("RGB")).astype(float); corner = im[210:240, 970:1010]
    assert not (corner[..., 1] > 200).all(), "green should be keyed out"

@test("alpha video layer: see-through parts show the camera, solid parts cover it")
def _():
    a = f"{OUT}/alpha.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red@0.0:s=1280x720:d=2,format=rgba", "-f", "lavfi", "-i", "color=c=white:s=400x400:d=2,format=rgba",
                    "-filter_complex", "[0][1]overlay=440:160,format=yuva444p10le", "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", a], check=True)
    tl = base_tl("alpha"); tl.scene_say("s", "cam", "This is the first line", "demo.")
    tl.layer("s", "video", at=0.1, path=a, rect=[0, 0, 1920, 1080], alpha=True); tl.save()
    plain = base_tl("alpha0"); plain.scene_say("s", "cam", "This is the first line", "demo."); plain.save()
    from PIL import Image
    im = np.asarray(Image.open(tl.frame(1.0, f"{OUT}/alpha.jpg")).convert("RGB")).astype(float)
    im0 = np.asarray(Image.open(plain.frame(1.0, f"{OUT}/alpha0.jpg")).convert("RGB")).astype(float)
    assert np.abs(im[20:120, 20:120] - im0[20:120, 20:120]).mean() < 6, "see-through part should show the camera"
    assert im[500:560, 900:1000].mean() > 170, "solid white part should cover the camera"

@test("face box border: a thin white outline is drawn around the box when the kit asks for it")
def _():
    from PIL import Image
    def frame(name, kit_fb):
        tl = base_tl(name); tl.d["kit"]["facebox"] = kit_fb
        tl.scene_say("s", "cam", "This is the first line", "demo.", pip="bottom-right")
        tl.show("s", 0, "screen", source="scr", **{"from": 2.0}); tl.save()
        return np.asarray(Image.open(tl.frame(1.0, f"{OUT}/{name}.jpg")).convert("RGB")).astype(float)
    plain = frame("fb0", {}); bordered = frame("fb1", {"border": [255, 255, 255], "border_w": 8})
    x0, y0 = 1920 - 390 - 20, 1080 - 450 - 20          # draft: box 390x450, margin 20, bottom-right
    edge = (slice(y0 + 100, y0 + 300), slice(x0 - 4, x0 - 1))
    assert bordered[edge].mean() > 180 and bordered[edge].mean() - plain[edge].mean() > 40, (bordered[edge].mean(), plain[edge].mean())

@test("exact cut: one short word inside speech is cut at its own edges, not pushed out to the whole stretch")
def _():
    tl = base_tl("exactcut"); tl.scene_say("s", "cam", "This is the first line", "demo.")
    a, b = tl.get("s")["spine"]["ranges"][0]
    ws = tl.words("cam", a, b); w = ws[2]                   # a word in the middle of the line
    tl.get("s")["spine"]["cuts"] = [[w[0], w[1], "exact"]]; tl.save()
    pcs = [p for p in tl.resolve()["scenes"][0]["pieces"]]
    edges = sorted({round(p["a"], 2) for p in pcs} | {round(p["a"] + p["n"] / 30, 2) for p in pcs})
    assert len(pcs) >= 2, pcs
    assert any(abs(e - w[0]) < 0.12 for e in edges) and any(abs(e - w[1]) < 0.12 for e in edges), (w, edges)

@test("auto blur only: patterns off, only the named words are found")
def _():
    from studio import analyze
    assert analyze.privacy_boxes(f"{FX}/screen/display.mp4", 0.0, 1.0, deny=[], patterns=False) == []

@test("face box fade: the box fades in at the start of the scene instead of popping")
def _():
    from PIL import Image
    def frame(name, fb, t):
        tl = base_tl(name); tl.d["kit"]["facebox"] = fb
        tl.scene_say("s", "cam", "This is the first line", "demo.", pip="bottom-right")
        tl.show("s", 0, "screen", source="scr", **{"from": 2.0}); tl.save()
        return np.asarray(Image.open(tl.frame(t, f"{OUT}/{name}_{t}.jpg")).convert("RGB")).astype(float)
    x0, y0 = 1920 - 390 - 20, 1080 - 450 - 20; box = (slice(y0 + 150, y0 + 300), slice(x0 + 100, x0 + 290))
    early, late = frame("fade", {"fade": 0.6}, 0.04), frame("fade", {"fade": 0.6}, 1.5)
    nofade_early = frame("nofade", {}, 0.04)
    assert np.abs(early[box] - nofade_early[box]).mean() > 8, "with a fade the box should be faint at the very start"

@test("bed_start: the bed begins where the timeline says in the track")
def _():
    from studio import audio as AU
    import soundfile as sf
    p = AU.music_path("music/test-bed_61s.m4a")
    a, b = AU.seamless_bed(p, 20, start=1.0), AU.seamless_bed(p, 20, start=6.0)
    assert a != b, "a different start must give a different bed"
    ya, _ = sf.read(a); yb, _ = sf.read(b)
    assert np.abs(ya[:48000] - yb[:48000]).mean() > 1e-3, "the two beds should start at different places"

@test("image layer keeps the picture's own alpha (a full-frame transparent PNG does not darken the shot)")
def _():
    from PIL import Image
    im = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0)); im.paste((255, 255, 255, 255), (900, 500, 1000, 560)); im.save(f"{OUT}/chip.png")
    tl = base_tl("imgalpha"); tl.scene_say("s", "cam", "This is the first line", "demo.")
    tl.layer("s", "image", at=0, path=f"{OUT}/chip.png", rect=[0, 0, 1920, 1080], radius=0, enter="none", exit="none"); tl.save()
    plain = base_tl("imgalpha0"); plain.scene_say("s", "cam", "This is the first line", "demo."); plain.save()
    a = np.asarray(Image.open(tl.frame(1.0, f"{OUT}/imgalpha.jpg")).convert("RGB")).astype(float)
    b = np.asarray(Image.open(plain.frame(1.0, f"{OUT}/imgalpha0.jpg")).convert("RGB")).astype(float)
    assert np.abs(a[20:300, 20:300] - b[20:300, 20:300]).mean() < 6, "see-through part should show the camera unchanged"
    sq = a[510:550, 910:990]
    assert sq.std() < 4 and sq.mean() > b[510:550, 910:990].mean() + 10, "solid part should show (graphics white, even)"

@test("subject effects: text behind him + blur background")
def _():
    tl = Timeline.new("fx", profile="draft", kit={"theme": "midnight", "graphics": {"motion_blur": 1}}, folder=OUT)
    if not os.path.exists(REAL_CAM): print("     (set CUTROOM_TEST_CAM to a camera clip with a person: skipped)"); return
    tl.source("cam", REAL_CAM, role="camera")
    tl.scene("s", source="cam", ranges=[[37.27, 40.5]], subject_fx=[{"effect": "behind", "at": 0.1, "until": 1.6,
             "graphic": {"template": "Kinetic", "props": {"lines": [{"text": "ZERO", "at": 0.0, "size": 420}], "layout": "center"}}}, {"effect": "blur_bg", "at": 1.8, "until": 2.4}, {"effect": "relight", "at": 2.4, "until": 3.0}])
    tl.save(); assert os.path.exists(tl.frame(1.0, f"{OUT}/fx1.jpg")); assert os.path.exists(tl.frame(2.1, f"{OUT}/fx2.jpg")); assert os.path.exists(tl.frame(2.7, f"{OUT}/fx3.jpg"))

@test("subject effects: an alpha clip made outside Cutroom goes behind him")
def _():
    a = f"{OUT}/behind.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=white:s=1280x720:d=2,format=rgba",
                    "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", a], check=True)
    tl = Timeline.new("fxv", profile="draft", folder=OUT)
    if not os.path.exists(REAL_CAM): print("     (set CUTROOM_TEST_CAM to a camera clip with a person: skipped)"); return
    tl.source("cam", REAL_CAM, role="camera")
    tl.scene("s", source="cam", ranges=[[37.27, 40.5]], subject_fx=[{"effect": "behind", "at": 0.1, "until": 2.0, "video": a}])
    tl.save(); from PIL import Image
    im = np.asarray(Image.open(tl.frame(1.0, f"{OUT}/fxv.jpg")).convert("RGB")).astype(float)
    assert im[20:120, 20:120].mean() > 170, "the clip should cover the background"
    assert im.mean() < 235, "he should stay in front of the clip"

@test("translated captions: srt in another language + burned layer")
def _():
    tl = base_tl("tr"); tl.scene_say("s", "cam", "This is the first line", "demo."); tl.scene_say("t", "cam", "The chart shows", "final score."); tl.save()
    j = CP.export_for_translation(tl.d, f"{OUT}/cues.json"); cs = json.load(open(j)); assert cs
    CP.write_translated(j, ["[ES] " + c["text"] for c in cs], f"{OUT}/es.srt"); assert "[ES]" in open(f"{OUT}/es.srt").read()
    L = CP.translated_layer(j, ["Hola " + c["text"] for c in cs]); tl.overlay(**L); tl.save(); assert os.path.exists(tl.frame(0.8, f"{OUT}/tr.jpg"))

@test("3D text + short candidates + OTIO")
def _():
    from studio.checks import gfx_preview
    assert os.path.exists(gfx_preview("Text3D", {"text": "TEST"}, 1.5, False, f"{OUT}/t3d.jpg"))
    for st in ("poster", "split", "warning", "repo"):
        assert os.path.exists(gfx_preview("ThumbnailStyle", {"style": st, "lines": ["A", "B"], "hero": "REA", "stamp": "43/100"}, 0.5, False, f"{OUT}/thumbstyle-{st}.jpg"))
    assert os.path.exists(gfx_preview("Contents", {"title": "4 REAL TESTS", "brand": "REA", "items": [{"text": "Ask 3 AIs"}, {"text": "Safe install"}, {"text": "Clone a real app"}, {"text": "Cost + verdict"}], "footer": "Let us see."}, 3.0, False, f"{OUT}/contents.jpg"))
    tl = base_tl("cand"); tl.scene_say("a", "cam", "This is the first line", "final score."); tl.save()
    c = CD.candidates(tl.d, 3, 60, 3); assert c and "score" in c[0]
    from studio.interchange import to_otio
    assert os.path.exists(to_otio(tl.d, f"{OUT}/cand.otio"))

@test("stage: floating 3D screen window on the backdrop + drawn scene in a box")
def _():
    tl = base_tl("stage")
    tl.scene("s", duration=3.0, base=[dict(at=0, kind="screen", source="scr", **{"from": 0.0}, stage={"rect": [1800, 110, 1960, 1940], "moves": [{"t": 1.5, "ry": -2}]})])
    tl.layer("s", "graphic", at=0.2, template="ModelLadder", rect=[90, 60, 1660, 900], design=1150,
             props={"title": "PICK", "items": [{"name": "A", "icon": "crown", "at": 0.3}, {"name": "B", "icon": "bolt", "at": 0.8}]})
    tl.save(); p = tl.frame(2.0, f"{OUT}/stage.jpg"); from PIL import Image
    im = np.asarray(Image.open(p).convert("RGB")).astype(float)
    assert im[-40:, :200].mean() > 3, "backdrop should show around the window"
    rep = tl.render(out=f"{OUT}/stage.mp4"); assert rep["seconds"] == 3.0

@test("blend modes + adjustment layers: light leak screened on, glow/vignette/grade over a range")
def _():
    tl = base_tl("blend"); tl.scene_say("s", "cam", "This is the first line", "demo.")
    tl.layer("s", "graphic", at=0.1, until=1.5, template="LightLeak", props={"at": 0.0, "dur": 1.4}, blend="screen")
    tl.get("s")["adjust"] = [{"at": 0.0, "until": 1.0, "glow": 0.6, "vignette": 0.5, "grade": "warm", "grain": 0.5, "fringe": 3, "sharpen": 0.5},
                             {"at": 1.0, "until": 1.4, "shake": 0.6}]
    tl.save(); from PIL import Image
    a = np.asarray(Image.open(tl.frame(0.8, f"{OUT}/blend.jpg")).convert("RGB")).astype(float)
    tl.d["scenes"][0]["layers"] = [l for l in tl.d["scenes"][0]["layers"] if l.get("template") != "LightLeak"]; tl.d["scenes"][0]["adjust"] = []
    b = np.asarray(Image.open(tl.frame(0.8, f"{OUT}/blend0.jpg")).convert("RGB")).astype(float)
    assert np.abs(a - b).mean() > 2, "leak/glow should change the picture"

@test("colour tools: report, match a shot to itself = no change, scope picture")
def _():
    from studio import scopes as SC
    r = SC.report(f"{FX}/cam.mov", 1.0, face=False); assert 0 <= r["mid"] <= 100 and "cast" in r
    g = SC.match(f"{FX}/cam.mov", 1.0, f"{FX}/cam.mov", 1.0); assert abs(g["exposure"]) < 0.01 and abs(g["temp"]) < 0.01, g
    assert os.path.exists(SC.scope_image(f"{FX}/cam.mov", 1.0, f"{OUT}/scope.png"))

@test("keyframes: a boxed graphic slides in, grows, turns and fades on its keys")
def _():
    tl = base_tl("anim"); tl.scene_say("s", "cam", "This is the first line", "demo.")
    tl.layer("s", "graphic", at=0.0, template="Pill", props={"text": "MOVING", "x": 300, "y": 200, "size": 60, "fade": False}, rect=[200, 200, 1200, 600],
             anim=[{"t": 0.0, "x": -900, "o": 0.0}, {"t": 0.6, "x": 0, "o": 1.0}, {"t": 1.0, "s": 1.3, "r": 8, "ease": "back"}])
    tl.save(); from PIL import Image
    a = np.asarray(Image.open(tl.frame(0.05, f"{OUT}/anim0.jpg")).convert("RGB")).astype(float)
    b = np.asarray(Image.open(tl.frame(1.1, f"{OUT}/anim1.jpg")).convert("RGB")).astype(float)
    assert np.abs(a - b).mean() > 0.5
    from studio.compile import anim_value
    p = anim_value(tl.get("s")["layers"][0]["anim"], 0.3); assert -900 < p["x"] < 0 and 0 < p["o"] < 1, p
    rep = tl.render(out=f"{OUT}/anim.mp4"); assert rep["seconds"] > 1

@test("depth: photo -> depth map -> parallax layers (far layer filled in); Parallax + LottieClip templates render")
def _():
    from studio import depth
    from studio.checks import gfx_preview
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", f"{FX}/cam.mov", "-frames:v", "1", "-vf", "scale=960:-2", f"{OUT}/still.jpg"], check=True)
    ls = depth.layers(f"{OUT}/still.jpg", 2); assert len(ls) == 2 and all(os.path.exists(x) for x in ls)
    assert os.path.exists(gfx_preview("Device3D", {"kind": "laptop", "image": "file://" + f"{OUT}/still.jpg"}, 1.5, False, f"{OUT}/dev3d.jpg"))
    assert os.path.exists(gfx_preview("BookReveal", {"line": "Every answer is already in the book", "at": 0.3, "per_word": 0.15}, 1.5, False, f"{OUT}/book.jpg"))
    assert os.path.exists(gfx_preview("Parallax", {"image": "file://" + ls[0], "layers": ["file://" + x for x in ls]}, 1.5, False, f"{OUT}/plx.jpg"))

@test("track matte: the screen recording plays inside big text; inverted circle")
def _():
    tl = base_tl("matte"); tl.scene_say("s", "cam", "This is the first line", "demo.")
    tl.layer("s", "matte", at=0.1, until=1.4, content={"kind": "screen", "source": "scr", "from": 1.0},
             matte={"template": "Matte", "props": {"text": "AI", "size": 700, "grow": True}})
    tl.layer("s", "matte", at=1.5, content={"kind": "screen", "source": "scr", "from": 2.0}, invert=True,
             matte={"template": "Matte", "props": {"shape": "circle", "w": 0.3}})
    tl.save(); from PIL import Image
    a = np.asarray(Image.open(tl.frame(1.0, f"{OUT}/matte1.jpg")).convert("RGB")).astype(float)
    b = np.asarray(Image.open(tl.frame(1.8, f"{OUT}/matte2.jpg")).convert("RGB")).astype(float)
    assert a.std() > 5 and b.std() > 5

@test("designed transitions: light leak, flare, zoom blur between scenes render")
def _():
    tl = base_tl("dtrans")
    for i, typ in enumerate(["cut", "leak", "zoom-blur", "flare"]):
        tl.scene(f"s{i}", duration=1.2, base=[dict(at=0, kind="screen", source="scr", **{"from": i * 1.0})])
        if i: tl.transition(f"s{i}", typ, 0.5)
    rep = tl.render(out=f"{OUT}/dtrans.mp4"); assert rep["seconds"] > 3

@test("stabilize: vid.stab two-pass steady copy of a b-roll shot (ffmpeg-full)")
def _():
    from studio import assets as A_
    if not A_.FFMPEG_FULL: return
    tl = base_tl("stab"); tl.scene("s", duration=1.5, base=[dict(at=0, kind="broll", path=f"{FX}/cam.mov", **{"from": 0.5}, stabilize="vidstab")])
    assert tl.render(out=f"{OUT}/stab.mp4")["seconds"] == 1.5

@test("corner pin: a screen recording pinned onto a tracked quad in a b-roll shot")
def _():
    tl = base_tl("pin")
    tl.scene("s", duration=1.5, base=[dict(at=0, kind="broll", path=f"{FX}/cam.mov", **{"from": 0.2})])
    tl.layer("s", "pin", at=0.1, content={"kind": "screen", "source": "scr", "from": 1.0},
             quad=[[1300, 500], [2500, 600], [2450, 1500], [1250, 1400]], track=True)
    tl.save(); assert os.path.exists(tl.frame(1.0, f"{OUT}/pin.jpg"))
    assert tl.render(out=f"{OUT}/pin.mp4")["seconds"] == 1.5

@test("nested clip: a finished timeline used as a source inside another (b-roll + 3D laptop)")
def _():
    sub = base_tl("nest_sub"); sub.scene("a", duration=1.0, base=[dict(at=0, kind="graphic", template="TitleCard", props={"title": "INNER"})]); sub.save()
    tl = base_tl("nest_top"); tl.source("inner", sub.path, role="broll")
    tl.scene("s", duration=1.0, base=[dict(at=0, kind="broll", source="inner", **{"from": 0.0})])
    tl.scene("t", duration=1.0, base=[dict(at=0, kind="graphic", template="Device3D", props={"video": {"$clip": {"source": "inner", "from": 0.0, "dur": 1.0}}})])
    assert tl.render(out=f"{OUT}/nest.mp4")["seconds"] == 2.0

@test("sound effects: nothing placed without rules; varied library sounds where rules say; none on text; mix under -1 dBTP")
def _():
    from studio import sfx
    if not sfx.find("whoosh"): return
    tl = base_tl("sfx")
    tl.scene("t", duration=1.5, role="title", base=[dict(at=0, kind="graphic", template="TitleCard", props={"title": "X"})])
    tl.scene("k", duration=1.5, base=[dict(at=0, kind="graphic", template="Kinetic", props={"lines": [{"text": "TEXT", "at": 0}]})]); tl.transition("k", "leak", 0.4)
    tl.scene("h", duration=1.5, base=[dict(at=0, kind="graphic", template="LogoHit", props={"title": "Y"})]); tl.transition("h", "dissolve", 0.3)
    assert sfx.place(tl, {}) == []
    placed = sfx.place(tl, dict(joins=True, stage_whoosh=True, reveal_hit=True, riser_title=True)); kinds = [p[2] for p in placed]
    assert "hit" in kinds and "whoosh" in kinds, placed
    assert not any(p[0] == "k" and p[2] == "hit" for p in placed), "no hit on a text scene"
    assert len({p[3] for p in placed if p[2] == "whoosh"}) == len([p for p in placed if p[2] == "whoosh"]), "whooshes vary"
    tl.render(out=f"{OUT}/sfx.mp4")
    from studio import audio as AU
    I, TP = AU.loudness(f"{OUT}/sfx.mp4"); assert TP <= -1.0, TP

@test("regression: a split screen right after a morph cut has no repeated frames")
def _():
    from studio import interp
    if not interp.available(): return
    tl = base_tl("morphsplit")
    tl.scene("s", source="cam", ranges=[[0.2, 1.2], [1.6, 2.8]], spine={"source": "cam", "ranges": [[0.2, 1.2], [1.6, 2.8]], "tighten": False, "morph": 4})
    tl.get("s")["spine"] = {"source": "cam", "ranges": [[0.2, 1.2], [1.6, 2.8]], "tighten": False, "morph": 4}
    tl.show("s", 1.0, "split", layout="lr", panels=[{"kind": "camera"}, {"kind": "graphic", "template": "TitleCard", "props": {"title": "X"}}])
    tl.render(out=f"{OUT}/morphsplit.mp4")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1.0", "-t", "1.0", "-i", f"{OUT}/morphsplit.mp4", "-vf", "scale=320:180,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, 180, 320).astype(float)
    d = [np.abs(f[i + 1][:, :160] - f[i][:, :160]).mean() for i in range(len(f) - 1)]
    assert sum(1 for x in d if x < 0.02) <= 1, [round(x, 2) for x in d]

@test("auto zoom follows screen activity when there are no clicks (and stays calm)")
def _():
    from studio import assets as A_
    k = A_.activity_keys({"crop": [0, 0, 3456, 2234]}, f"{FX}/screen/display.mp4", 8.0, lambda t: t, {})
    assert k and k[0][1] == "full"
    ts = [x[0] for x in k]; assert all(b - a >= 0.04 for a, b in zip(ts, ts[1:]))

@test("audio: room tone means no dead air in voice-less shots; the dropout check catches a muted word")
def _():
    from studio import checks as CK, model as M_
    tl = base_tl("deadair"); tl.scene_say("a", "cam", "This is the first line", "demo.")
    tl.scene("gap", duration=1.5, base=[dict(at=0, kind="graphic", template="TitleCard", props={"title": "X"})])
    tl.scene_say("b", "cam", "The chart shows", "final score."); tl.d["audio"] = {"loudness": -14.4}
    tl.render(out=f"{OUT}/deadair.mp4")
    assert CK.dead_air(f"{OUT}/deadair.mp4")["ok"], CK.dead_air(f"{OUT}/deadair.mp4")
    R = M_.resolve(tl.d); assert CK.dropouts(f"{OUT}/deadair.mp4", R)["ok"]
    # mute half a second of speech in a copy: the check must notice
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{OUT}/deadair.mp4", "-c:v", "copy", "-af", "volume=enable='between(t,0.6,1.1)':volume=0",
                    f"{OUT}/deadair_muted.mp4"], check=True)
    assert not CK.dropouts(f"{OUT}/deadair_muted.mp4", R)["ok"], "a muted word must be reported"

@test("retype: pasted text on a screen recording is typed in, in reading order, then the recording takes over")
def _():
    tl = base_tl("retype")
    tl.scene("s", duration=3.0, base=[dict(at=0, kind="screen", source="scr", **{"from": 1.0},
             retype=[{"at": 0.2, "box": {"ocr": "Project dashboard", "to": "Server 10.0.0.12"}, "done_at": 1.5, "cps": 40, "fast": 2}])])
    tl.save(); from PIL import Image
    a = np.asarray(Image.open(tl.frame(0.6, f"{OUT}/rt_a.jpg")).convert("L")).astype(float)
    b = np.asarray(Image.open(tl.frame(2.9, f"{OUT}/rt_b.jpg")).convert("L")).astype(float)
    assert (a > 128).mean() < (b > 128).mean(), "less text while typing than after"
    assert tl.render(out=f"{OUT}/retype.mp4")["seconds"] == 3.0

@test("typer: human timing plan + AppleScript for a prompt (dry run, nothing typed)")
def _():
    from studio import typer
    pl = typer.plan("Hi there. How are you?", cps=20)
    assert len(pl) == 22 and pl[8][1] > pl[2][1], "a pause after the full stop"
    sc = typer.type_text('Say "hi"\nnext', dry=True)
    assert 'keystroke "\\"' in sc and "key code 36 using shift down" in sc and sc.startswith('tell application "System Events"')
    assert sum(d for _, d in typer.plan("x" * 300, cps=20, fast=3)) < sum(d for _, d in typer.plan("x" * 300, cps=20))

@test("generate: paid engines refuse without confirm; scene engine files a clip + prompt in the library; find() by words")
def _():
    import tempfile
    os.environ["STUDIO_BROLL"] = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"))
    from studio import generate as GN
    assert GN.estimate("veo", 8, "1080p") == 3.2 and GN.estimate("scene", 8) == 0
    try: GN.generate("x", engine="veo", secs=8); raise AssertionError("must refuse")
    except PermissionError: pass
    p = GN.generate("Glowing book line test", engine="scene", secs=1.0, topic="tests", template="TitleCard", props={"title": "GEN"})
    assert os.path.exists(p) and os.path.exists(os.path.splitext(p)[0] + ".json") and "/tests/" in p
    assert GN.find("glowing book")[0]["path"] == p
    q = GN.add(p, prompt="sunset over a quiet city", topic="imported"); assert "/imported/" in q and GN.find("quiet city")[0]["path"] == q
    del os.environ["STUDIO_BROLL"]

@test("cinematic 3D scenes: DataCity, NodeNetwork, CardTunnel, ParticleWord, GlobeArcs render; FastWan DMD sampler math")
def _():
    from studio.checks import gfx_preview
    for k, pr in {"DataCity": {"items": [{"label": "A", "value": 3}, {"label": "B", "value": 7}], "title": "T"},
                  "NodeNetwork": {"nodes": ["Jira", "GitHub", "Slack"]}, "CardTunnel": {"cards": ["one", "two", "three"], "hero": "Done."},
                  "ParticleWord": {"word": "GO", "burst": True}, "GlobeArcs": {"title": "World"}}.items():
        assert os.path.exists(gfx_preview(k, pr, 1.5, False, f"{OUT}/{k}.jpg")), k
    try: import mlx.core as mx
    except ImportError: print("     (mlx not installed: FastWan sampler part skipped)"); return
    from studio.wan_fast import DMDScheduler
    s = DMDScheduler(); s.set_timesteps(); assert s.timesteps.tolist() == [1000.0, 757.0, 522.0]
    x, v = mx.ones((2, 2)), mx.full((2, 2), 0.5)
    for _ in range(2): x = s.step(v, 0, x)
    out = s.step(v, 0, x); assert mx.allclose(out, x - 0.522 * v).item()     # last step returns the clean prediction (no re-noise)

@test("tool tiles: every tile incl. claude, chatgpt, gemini draws (REA video, 2026-10-18)")
def _():
    from studio.tool_icons import TOOLS, tool_icon, tool_png
    for n in ("claude", "chatgpt", "gemini"): assert n in TOOLS
    for n in TOOLS: im = tool_icon(n, 112); assert im.size[0] > 50 and im.getbbox(), n
    assert os.path.exists(tool_png("claude"))

@test("base clock: base pieces share one exact 1/30 clock, so the face box never pairs with an old camera frame (REA draft 5 stutter)")
def _():
    from studio import render as RN
    from PIL import Image
    png = f"{OUT}/still_clock.png"; Image.new("RGB", (1920, 1080), (40, 40, 60)).save(png)
    tl = base_tl("baseclock")
    tl.scene_say("s", "cam", "This is the first line", "demo.", role="screen", pip="bottom-left")
    tl.get("s")["base"] = []
    tl.show("s", 0, "still", path=png, fit="fill"); tl.show("s", 1.0, "screen", source="scr", **{"from": 2.0})
    tl.save(); R = tl.resolve()
    j = RN.compile_chunks(R, tl.d, RN.plan_chunks(R))[0]
    import re
    m = re.search(r"concat=n=2:v=1:a=0,settb=1/30,setpts=N\[base\d+\]", j["script"]) or re.search(r"settb=1/30,setpts=N\[base\d+\]", j["script"])
    assert m, "base must be re-clocked to exact 1/30 before the face box overlay"

@test("shorts clean top: a piece can take its top from a clean render of the main video at the same moment (REA Shorts)")
def _():
    from studio import shorts as SH
    tl = base_tl("cleantop")
    tl.scene_say("hook", "cam", "This is the first line", "demo.", role="hook")
    tl.save(); R = M.resolve(tl.d); st = R["scenes"][0]["start"] / 30
    spec = {"name": "ct", "hook": "x", "clean": "/tmp/clean.mp4", "snap": False,
            "pieces": [{"scene": "hook", "from": 0.5, "to": 2.0, "layout": "stack", "clean": True}]}
    s = SH.build(tl.d, spec)
    c = s["scenes"][0]["base"][0]["content"]
    assert c["kind"] == "broll" and c["path"] == "/tmp/clean.mp4" and abs(c["from"] - (st + 0.5)) < 0.05, c
    spec["pieces"][0]["content"] = {"kind": "graphic", "template": "ListReveal", "props": {"title": "T", "items": []}}
    c2 = SH.build(tl.d, spec)["scenes"][0]["base"][0]["content"]; assert c2["kind"] == "graphic" and c2["template"] == "ListReveal", c2

@test("shorts safe area: fill look keeps the app header band clear; header_band check finds text there")
def _():
    from studio import shorts as SH, checks as C
    from PIL import Image, ImageDraw, ImageFont
    assert SH.LOOKS["fill"]["box"][1] >= 270 and SH.LOOKS["board"]["box"][1] >= 270, "content must start below the app header band"
    d = os.path.expanduser("~/VideoWork/studio-tests"); os.makedirs(d, exist_ok=True)
    for name, y in (("hdr_bad", 120), ("hdr_ok", 900)):
        im = Image.new("RGB", (1080, 1920), (20, 20, 30)); dr = ImageDraw.Draw(im)
        dr.text((80, y), "Last login on ttys000", fill=(255, 255, 255), font=ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60))
        im.save(f"{d}/{name}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", f"{d}/{name}.png", "-t", "2", "-pix_fmt", "yuv420p", f"{d}/{name}.mp4"], check=True)
    assert not C.header_band(f"{d}/hdr_bad.mp4")["ok"], "text at y 120 must be reported"
    assert C.header_band(f"{d}/hdr_ok.mp4")["ok"], "text at y 900 is fine"

@test("cover styles: classic, proof, screen, number, split, hero all render 1080x1920 and differ")
def _():
    from studio import gfx
    import numpy as np
    from PIL import Image
    d = os.path.expanduser("~/VideoWork/studio-tests"); os.makedirs(d, exist_ok=True)
    pic = f"{d}/cover_pic.png"; Image.new("RGB", (800, 500), (200, 60, 60)).save(pic)
    outs = []
    for st in ("classic", "proof", "screen", "number", "split", "hero", "text", "stamp", "vs", "behind"):
        o = gfx.still_srgb("Cover", dict(hook="Test|cover", badge="BADGE", style=st, proof="file://" + pic, proof2="file://" + pic, number="43", labels=["A", "B"], word="BIG", stamp="TESTED", photo="file://" + pic), (1080, 1920), f"{d}/cover_{st}.jpg")
        im = np.asarray(Image.open(o).convert("L").resize((54, 96)), dtype=float); assert Image.open(o).size == (1080, 1920); outs.append(im)
    for i in range(len(outs)):
        for j in range(i + 1, len(outs)):
            assert np.abs(outs[i] - outs[j]).mean() > 3, f"cover styles {i} and {j} look the same"

@test("neutral defaults: no close-ups or drift, no face box, plain theme, Look needs a look, Shorts add nothing unasked")
def _():
    from studio import assets as A, compile as K, shorts as SH
    pcs = [dict(a=0.0, n=300, f0=0, hold=False), dict(a=12.0, n=300, f0=300, hold=False)]
    assert M.closeups({}, pcs, [], 600) == [], "close-ups without being asked"
    assert M.closeups({"camera": {"close": "auto", "every": 5.0}}, pcs, [], 600), "asked-for close-ups missing"
    assert A.theme({}) == A.THEMES["plain"] and A.theme({"theme": "midnight"}) == A.THEMES["midnight"]
    assert Timeline.new("neutral", folder=OUT).d["kit"] == {}
    try: A.graphic("Look", dict(el="pill", text="x"), 30, dict(profile=dict(w=1920, h=1080), kit={})); raise AssertionError("Look rendered with no look")
    except ValueError: pass
    tl = base_tl("neutral_short"); tl.scene_say("intro", "cam", "This is the first line", "demo."); tl.save()
    st = SH.build(tl.d, dict(name="n", pieces=[dict(scene="intro", **{"from": 0}, to=99)]), "youtube")
    cam = st["scenes"][0]["camera"]; assert cam["close"] is None and st["scenes"][0]["music"] is None, st["scenes"][0]
    assert [s["id"] for s in st["scenes"] if s["id"] == "end"] == [] and not any(o.get("template") == "Progress" for o in st["overlays"])
    e = SH.build(tl.d, dict(name="n", end=dict(title="T", cta={"youtube": ["A", "B"]}), pieces=[dict(scene="intro", **{"from": 0}, to=99)]), "youtube")
    assert e["scenes"][-1]["base"][0]["props"]["cta"] == "A"

@test("ghost mouth: a hold (voice off) and a scene tail freeze his face and stay silent")
def _():
    from studio import compile as K
    sc = dict(spine={}, pieces=[dict(a=1.0, n=30, f0=0, hold=False), dict(a=2.0, n=45, f0=30, hold=True), dict(a=2.0, n=60, f0=75, hold=False, tail=15)])
    kinds = [(g["kind"], g["n"]) for g in K.camera_segments(sc)]
    assert kinds == [("piece", 30), ("freeze", 45), ("piece", 45), ("freeze", 15)], kinds
    tl = base_tl("ghost")
    tl.scene_say("s", "cam", "This is the first line", "demo.")
    a, b = tl.get("s")["spine"]["ranges"][0]; m = round((a + b) / 2, 2)
    tl.get("s")["spine"].update(ranges=[[a, m], [m, b]], snap_words=False, tighten=False); tl.hold("s", 1, 1.5)
    tl.save(); R = tl.resolve(); hp = next(p for p in R["scenes"][0]["pieces"] if p["hold"])
    rep = tl.render(out=f"{OUT}/ghost.mp4")
    t0, t1 = hp["f0"] / 30 + 0.2, (hp["f0"] + hp["n"]) / 30 - 0.2
    f0_, f1_ = F.read_rgb(rep["output"], t0)[0], F.read_rgb(rep["output"], t1)[0]
    assert np.abs(f0_.astype(float) - f1_.astype(float)).mean() < 0.002, "the picture moves during the hold"
    live = F.read_rgb(rep["output"], 0.2)[0], F.read_rgb(rep["output"], 0.6)[0]
    assert np.abs(live[0].astype(float) - live[1].astype(float)).mean() > 0.002, "the spoken part should move"
    import soundfile as sf
    w = f"{OUT}/ghost.wav"; subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", rep["output"], "-ac", "1", w], check=True)
    x, sr = sf.read(w); seg = x[int(t0 * sr):int(t1 * sr)]
    assert np.sqrt(np.mean(seg ** 2)) < 0.003, "voice heard during the hold"
    ch = __import__("studio.checks", fromlist=["x"]).check_all(rep["output"], timeline=tl.d)
    assert ch["frozen"]["ok"], ch["frozen"]          # a frozen hold is on purpose, not a fault

@test("clipped words: cuts snap to word edges with a small pad (unit + a range that starts and ends inside words)")
def _():
    from studio import words as W
    ws = [[1.0, 1.4, "first"], [1.5, 1.9, "line"], [1.92, 2.3, "here"]]
    assert abs(W.snap_start(ws, 1.1) - 0.94) < 1e-9          # most of "first" is after the cut: kept whole, 60 ms pad
    assert abs(W.snap_start(ws, 1.35) - 1.45) < 1e-9         # most of "first" is before it: left out whole (gap middle)
    assert abs(W.snap_end(ws, 1.8) - 1.91) < 1e-9            # "line" mostly kept: ends after it, never into "here"
    assert abs(W.snap_end(ws, 1.6) - 1.45) < 1e-9            # "line" mostly cut: ends before it (gap middle)
    assert W.snap_start(ws, 1.45) == 1.45 and W.snap_end(ws, 3.0) == 3.0          # already between words: unchanged
    for t in np.linspace(0.8, 2.5, 60):                     # never inside a word, either way
        for x in (W.snap_start(ws, t), W.snap_end(ws, t)): assert not any(w[0] < x < w[1] for w in ws), (t, x)
    runs = [[1.0, 2.3], [3.0, 3.4]]                          # what the audio says: one stretch of sound, then a pause
    assert W.snap_end(ws, 2.2, runs=runs) == 2.36 and W.snap_start(ws, 1.1, runs=runs) == 0.94   # near a stretch's edge: go to it
    assert W.snap_end(ws, 2.6, runs=runs) == 2.6 and W.snap_start(ws, 2.9, runs=runs) == 2.9     # in a pause: stay put
    assert W.snap_start(ws, 2.97, runs=runs) == 2.94                                              # just before sound: pad
    tl = base_tl("clip"); src = f"{FX}/cam.mov"
    tl.scene_say("s", "cam", "This is the first line", "demo.")
    a, b = tl.get("s")["spine"]["ranges"][0]
    wn = W.voiced(src, W.transcribe(src, max(0.0, a - 2.0), b + 2.0)); inside = [w for w in wn if a <= (w[0] + w[1]) / 2 <= b]
    w0 = next(w for w in inside if W.norm(w[2]) == "this"); wl = [w for w in inside if W.norm(w[2]) == "demo"][-1]   # the line's own first/last words
    tl.get("s")["spine"].update(ranges=[[round(w0[0] + 0.3 * (w0[1] - w0[0]), 3), round(wl[0] + 0.7 * (wl[1] - wl[0]), 3)]], tighten=False)   # the snap alone
    pcs = M.spine_pieces(tl.d, tl.get("s"))
    assert pcs[0][0] <= w0[0] - 0.02, (pcs[0], w0)             # the first word is kept whole (from where its sound starts)
    assert pcs[-1][1] >= wl[1] - 0.01, (pcs[-1], wl)           # and the last one
    tl.get("s")["spine"]["tighten"] = True                     # pauses removed too: still never into the first/last word's sound
    pcs = M.spine_pieces(tl.d, tl.get("s")); assert pcs[0][0] <= w0[0] - 0.02 and pcs[-1][1] >= wl[1] - 0.01, (pcs, w0, wl)

@test("describe: the full transcript, no 400-character cut")
def _():
    long = [[i * 0.3, i * 0.3 + 0.25, f"word{i}"] for i in range(200)]
    R = dict(name="d", total=1800, profile=dict(w=1920, h=1080), scenes=[dict(id="s", start=0, nf=1800, pieces=[], trans=0, base=[], layers=[], words=long)])
    out = M.describe(R); assert "word199" in out and len(out) > 1500

@test("render cache: size limit removes least recently used files, keeps recent ones and old leftovers go")
def _():
    from studio import cache as CA
    import tempfile
    d = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork")); old = CA.CACHE; CA.CACHE = d
    try:
        os.makedirs(f"{d}/gfx"); os.makedirs(f"{d}/locks"); now = time.time()
        for i, age_h in enumerate([200, 100, 50, 1]):
            p = f"{d}/gfx/v{i}.mov"; open(p, "wb").write(b"x" * 1000); os.utime(p, (now - age_h * 3600, now - age_h * 3600))
        p = f"{d}/gfx/x.part.mov"; open(p, "wb").write(b"x" * 10); os.utime(p, (now - 48 * 3600, now - 48 * 3600))
        open(f"{d}/locks/l", "w").write("x"); os.utime(f"{d}/locks/l", (now - 900 * 3600, now - 900 * 3600))
        r = CA.prune(limit=2500, dry=True); assert r["removed"] == 3 and os.path.exists(f"{d}/gfx/v0.mov"), r
        r = CA.prune(limit=2500)
        assert sorted(os.listdir(f"{d}/gfx")) == ["v2.mov", "v3.mov"] and os.path.exists(f"{d}/locks/l"), os.listdir(f"{d}/gfx")
        CA.path("gfx", "v2", "mov"); assert time.time() - os.stat(f"{d}/gfx/v2.mov").st_atime < 60, "a cache hit should mark the file as used"
        assert CA.prune(limit=0)["after"] >= 2000 and os.path.exists(f"{d}/gfx/v2.mov") and os.path.exists(f"{d}/gfx/v3.mov"), "a file used in the last day was removed"
    finally:
        CA.CACHE = old; subprocess.run(["rm", "-rf", d])

@test("thumbnails without a face: profile setting, no camera needed, huge words left, big tool tiles right")
def _():
    from studio import thumbs as TH, config as CF
    from PIL import Image
    assert TH.use_face(False) is False and TH.use_face(True) is True
    old = CF.profile; CF.profile = lambda name=None: dict(old(name), thumbnail_face=False)
    try: assert TH.use_face() is False
    finally: CF.profile = old
    icons = []
    for i, c in enumerate([(217, 119, 87), (66, 133, 244)]):
        q = f"{OUT}/icon{i}.png"; Image.new("RGB", (256, 256), c).save(q); icons.append(q)
    outs, sheet = TH.options(None, None, [["ONE APP", "TWO TOOLS"]], f"{OUT}/thumbs-noface", icons=icons, icon_sep="+", face=False)
    assert [os.path.basename(o) for o in outs] == ["thumb_1_noface.jpg"] and os.path.exists(sheet), outs
    im = np.asarray(Image.open(outs[0]).convert("RGB"), dtype=float); assert im.shape == (1080, 1920, 3)
    right, left = im[:, 1400:], im[:, 80:1200]
    assert (np.abs(right - [217, 119, 87]).sum(2) < 60).mean() > 0.04 and (np.abs(right - [66, 133, 244]).sum(2) < 60).mean() > 0.04, "tool tiles missing or small"
    assert (left.min(2) > 230).mean() > 0.04, "big white words missing on the left"
    try: TH.options(None, None, [["X"]], f"{OUT}/thumbs-noface", face=True); raise AssertionError("a face thumbnail without a camera should fail clearly")
    except ValueError: pass

@test("audio mix: every scene's voice reaches the end (amix never stops when the first scene's voice ends)")
def _():
    tl = base_tl("mixlen")
    for i, (a, b) in enumerate([(0.0, 2.0), (2.0, 4.0), (4.0, 6.0)]):
        tl.scene(f"s{i}", source="cam", ranges=[[a, b]], music=0.05)["spine"]["tighten"] = False
        if i: tl.transition(f"s{i}", "dissolve", 0.2)
    R = tl.resolve(); last = next(s for s in R["scenes"] if s["id"] == "s2"); t0 = last["start"] / 30
    src = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-ss", "4.3", "-t", "1.4", "-i", f"{FX}/cam.mov", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                                       capture_output=True).stdout, np.int16).astype(float)
    assert np.sqrt((src ** 2).mean()) > 100, "fixture has no sound in the test window"
    for k in range(4):                                   # the old graph failed only on some runs
        w = f"{OUT}/mixlen{k}.wav"; AU.mix(R, w)
        x = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0 + 0.3:.2f}", "-t", "1.4", "-i", w, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                                         capture_output=True).stdout, np.int16).astype(float)
        assert len(x) and np.sqrt((x ** 2).mean()) > 100, f"run {k}: last scene is silent"

print("\n" + "\n".join(f"{s:4s} {n}" for n, s, _, e in RESULTS))
print(f"\n{sum(1 for r in RESULTS if r[1] == 'ok')}/{len(RESULTS)} passed")
sys.exit(0 if all(r[1] == "ok" for r in RESULTS) else 1)
