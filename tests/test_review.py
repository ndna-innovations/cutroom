"""Tests for studio/review.py (contrast, face, strips, every word whole, reuse, cut review page). Each check is run on a
broken example first (it must fail) and on a clean one (it must pass). Run:  .venv/bin/python tests/test_review.py"""
import os, sys, time, shutil, subprocess, traceback, tempfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from studio import review as RV, words as W

FX = os.path.expanduser("~/VideoWork/studio-test/fixtures"); OUT = os.path.expanduser("~/VideoWork/studio-test/review"); os.makedirs(OUT, exist_ok=True)
if not os.path.exists(f"{FX}/cam.mov"): subprocess.run([sys.executable, f"{HERE}/make_media.py", FX], check=True)
RESULTS = []
def test(name):
    def deco(fn):
        t = time.time()
        try: fn(); RESULTS.append((name, "ok", time.time() - t, ""))
        except Exception as e: RESULTS.append((name, "FAIL", time.time() - t, f"{e}\n{traceback.format_exc()[-1200:]}"))
        print(f"{RESULTS[-1][1]:4s} {name} ({RESULTS[-1][2]:.1f}s)" + (f"\n     {RESULTS[-1][3]}" if RESULTS[-1][3] else ""), flush=True)
    return deco

def card(fg, bg, text="SHIP IT TODAY"):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (1080, 400), bg); d = ImageDraw.Draw(im)
    d.text((80, 140), text, font=ImageFont.truetype("/System/Library/Fonts/Avenir Next.ttc", 96, index=5), fill=fg)
    return im

def video_from(frames, path, fps=30):
    h, w = frames[0].shape[:2]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", path],
                         stdin=subprocess.PIPE)
    p.communicate(np.stack(frames).astype(np.uint8).tobytes()); return path

@test("contrast: white on near-white fails, white on dark passes (measured on OCR boxes)")
def _():
    d = tempfile.mkdtemp(dir=OUT)
    card((255, 255, 255), (20, 22, 28)).save(f"{d}/a.png"); card((90, 90, 96), (20, 22, 28)).save(f"{d}/b.png")
    found = RV._ocr([f"{d}/a.png", f"{d}/b.png"])
    from PIL import Image
    good = [RV.text_contrast(np.asarray(Image.open(f"{d}/a.png")) / 255, l) for l in found[f"{d}/a.png"]]
    assert good and min(good) >= 4.5, f"white on dark measured {good}"
    low = [RV.text_contrast(np.asarray(Image.open(f"{d}/b.png")) / 255, l) for l in found.get(f"{d}/b.png", [])]
    assert low and max(low) < 4.5, f"grey on dark measured {low}"
    im = np.asarray(card((255, 255, 255), (238, 238, 236))) / 255           # white on white: OCR may not even see it
    assert RV.text_contrast(im, [60, 120, 900, 160]) < 4.5

@test("face: text over the face box is caught, text below it is not; a real face is found")
def _():
    fb = [400, 300, 280, 360]
    assert RV.overlaps(fb, [380, 560, 400, 70, "CAPTION", 1])                # over the mouth
    assert not RV.overlaps(fb, [380, 700, 400, 70, "CAPTION", 1])            # on the chest
    src = os.path.expanduser(os.environ.get("CUTROOM_TEST_FACE", ""))   # optional: a photo of one face
    if not os.path.exists(f"{FX}/face.jpg") and src and os.path.exists(src): shutil.copy(src, f"{FX}/face.jpg")
    if not os.path.exists(f"{FX}/face.jpg"): print("     (no face still: detector part skipped)"); return
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    from PIL import Image
    det = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=os.path.expanduser("~/models/studio/face_landmarker.task")), num_faces=2))
    boxes = RV.face_boxes(np.asarray(Image.open(f"{FX}/face.jpg").convert("RGB")), det); det.close()
    assert len(boxes) == 1 and boxes[0][2] > 40, boxes

@test("face (whole video): a caption burned over the face fails, the same caption on the chest passes")
def _():
    if not os.path.exists(f"{FX}/face.jpg"): print("     (no face still: skipped)"); return
    from PIL import Image, ImageDraw, ImageFont
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    base = Image.new("RGB", (540, 960), (40, 42, 48)); base.paste(Image.open(f"{FX}/face.jpg").convert("RGB").resize((300, 300)), (120, 180))
    det = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=os.path.expanduser("~/models/studio/face_landmarker.task"))))
    x, y, w, h = RV.face_boxes(np.asarray(base), det)[0]; det.close()
    f = ImageFont.truetype("/System/Library/Fonts/Avenir Next.ttc", 44, index=5)
    def with_cap(cy):
        im = base.copy(); d = ImageDraw.Draw(im); d.rectangle([40, cy - 8, 500, cy + 56], fill=(15, 17, 22)); d.text((60, cy), "SHIP IT TODAY", font=f, fill=(255, 255, 255))
        return np.asarray(im)
    bad = video_from([with_cap(int(y + h * 0.6))] * 30, f"{OUT}/face-bad.mp4")
    ok = video_from([with_cap(int(y + h * 1.6))] * 30, f"{OUT}/face-ok.mp4")
    assert not RV.face(bad, every=0.5, first=0.5)["ok"], "caption over the mouth passed"
    r = RV.face(ok, every=0.5, first=0.5); assert r["ok"], r

@test("strips: a one-frame white flash next to a cut is found; a clean cut is not")
def _():
    a = [np.full((180, 320, 3), 70, np.uint8)] * 30; b = [np.full((180, 320, 3), 150, np.uint8)] * 30
    clean = video_from(a + b, f"{OUT}/strip-clean.mp4")
    fl = list(a); fl[25] = np.full((180, 320, 3), 255, np.uint8)
    flash = video_from(fl + b, f"{OUT}/strip-flash.mp4")
    R = dict(scenes=[dict(id="s", start=0, pieces=[], src=None, base=[dict(kind="camera", f0=0, f1=30), dict(kind="screen", f0=30, f1=60)], layers=[])])
    r = RV.strips(flash, R, out=f"{OUT}/strip-flash"); assert not r["ok"] and "0.83s" in r["problems"][0], r
    assert os.path.exists(r["sheets"][0])
    r = RV.strips(clean, R, out=f"{OUT}/strip-clean"); assert r["ok"], r

@test("cuts: a cut in the middle of a word fails, a cut in a pause passes; a missing word is reported")
def _():
    src = f"{FX}/cam.mov"; ws = W.transcribe(src)
    from studio.checks import _env
    e = _env(src); mid = float(np.argmax(e[:100])) * 0.02            # the loudest moment of the first line: mid-word (Whisper's times drift)
    gaps = [(a[1], b[0]) for a, b in zip(ws, ws[1:]) if b[0] - a[1] > 0.5]
    g0, g1 = gaps[0]; pause = (g0 + g1) / 2
    def R_(end, resume):
        n1 = int(round(end * 30)); return dict(scenes=[dict(id="s", start=0, src=src, base=[dict(kind="camera", f0=0, f1=999)], layers=[],
                 pieces=[dict(a=0.0, n=n1, f0=0, hold=False), dict(a=resume, n=60, f0=n1, hold=False)])])
    bad = RV.cuts(src, R_(mid, mid + 0.6), heard=ws)
    assert any("still speaking" in p for p in bad["problems"]), bad
    ok = RV.cuts(src, R_(pause - 0.05, g1 - 0.15), heard=ws)
    assert not any("still speaking" in p for p in ok["problems"]), ok
    assert RV.missing_words(["First", "what", "um", "it"], ["first", "it"]) == ["what"]

@test("reuse: the same screen moment twice fails; two different moments pass")
def _():
    def R_(f2):
        return dict(scenes=[dict(id="s", start=0, src="/x/cam.mov", pieces=[], layers=[], base=[
            dict(kind="screen", source="/x/screen.mp4", f0=0, f1=60, **{"from": 10.0}),
            dict(kind="screen", source="/x/screen.mp4", f0=60, f1=120, **{"from": f2})])])
    r = RV.reuse(R_(11.0), {}); assert not r["ok"] and "same" in r["problems"][0], r
    r = RV.reuse(R_(30.0), {}); assert r["ok"], r

@test("cutreview: one page with every voice cut, what was removed, and playable raw + edited sound")
def _():
    src = f"{FX}/cam.mov"; ws = W.transcribe(src)
    gaps = [(a[1], b[0]) for a, b in zip(ws, ws[1:]) if b[0] - a[1] > 0.5]
    (g0, g1), (h0, h1) = gaps[0], gaps[1]
    n1 = int(round(g0 * 30)); n2 = int(round((h0 - g1) * 30))
    R = dict(scenes=[dict(id="s", start=0, src=src, base=[dict(kind="camera", f0=0, f1=999)], layers=[],
                          pieces=[dict(a=0.0, n=n1, f0=0, hold=False), dict(a=h1, n=60, f0=n1, hold=False)])])
    L = RV.cut_list(R); assert len(L) == 1 and L[0]["words"], L
    p = RV.cutreview({"name": "Test"}, src, out=f"{OUT}/cuts.html", R=R)
    s = open(p).read()
    assert s.count("<audio") == 2 and "data:audio/mpeg;base64," in s and L[0]["words"].split()[0] in s
    assert os.path.getsize(p) < 2_000_000

print(f"\n{sum(r[1] == 'ok' for r in RESULTS)}/{len(RESULTS)} passed")
sys.exit(0 if all(r[1] == "ok" for r in RESULTS) else 1)
