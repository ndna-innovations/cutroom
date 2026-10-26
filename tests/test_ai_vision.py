"""Runnable check of studio.ai_vision (no pytest): BiRefNet cut-out vs Apple Vision person mask (hair-edge crop
saved to ~/VideoWork/studio-test/ai_vision/cutout_compare.jpg) and SigLIP 2 picture search, with timings.
Run: .venv/bin/python tests/test_ai_vision.py CAMERA.mov SECONDS [SCREEN.mp4]"""
import os, sys, time, subprocess, tempfile
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from studio import ai_vision as V
from studio.ocr import ensure_bin

if len(sys.argv) < 3: sys.exit("usage: tests/test_ai_vision.py CAMERA.mov SECONDS [SCREEN.mp4]  (a camera clip with a person at SECONDS)")
CAM = os.path.expanduser(sys.argv[1])
T = float(sys.argv[2])
SCREEN = os.path.expanduser(sys.argv[3]) if len(sys.argv) > 3 else ""
OUT = os.path.expanduser("~/VideoWork/studio-test/ai_vision")


def timed(label, fn, *a, **k):
    t = time.time(); r = fn(*a, **k); print(f"  {label}: {time.time() - t:.2f} s"); return r


def vision_mask(rgb):
    d = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"))
    cv2.imwrite(f"{d}/f.png", rgb[..., ::-1])
    subprocess.run([ensure_bin(), "person", d, d + "/m"], check=True, capture_output=True)
    m = cv2.imread(f"{d}/m/f.png", 0); subprocess.run(["rm", "-rf", d])
    return cv2.resize(m, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255


def test_cutout():
    print("BiRefNet cut-out")
    rgb = timed("read + tone map frame", V.frame_srgb, CAM, T)
    timed("matte (first call, loads model)", V.matte_birefnet, rgb)
    a = timed("matte (warm, 4K)", V.matte_birefnet, rgb)
    raw = timed("matte (warm, no edge refine)", V.matte_birefnet, rgb, False)
    vm = timed("Apple Vision person mask", vision_mask, rgb)
    p = timed("cutout_birefnet (cached after first run)", V.cutout_birefnet, CAM, T)
    assert os.path.exists(p) and Image.open(p).mode == "RGBA"
    print("  cut-out:", p)
    # crop around the top of the head, where hair edges are
    ys, xs = np.nonzero(a > 0.5); top = ys.min()
    cx = int(np.mean(xs[ys < top + 250])); w, h = 900, 560
    x0, y0 = max(0, cx - w // 2), max(0, top - 160)
    sl = np.s_[y0:y0 + h, x0:x0 + w]
    bg = np.zeros_like(rgb[sl], np.float32) + np.array([20, 170, 160], np.float32)   # teal shows fringes well
    comp = lambda m: (rgb[sl] * m[sl][..., None] + bg * (1 - m[sl][..., None])).astype(np.uint8)
    gray = lambda m: np.repeat((m[sl][..., None] * 255).astype(np.uint8), 3, 2)
    rows = [[rgb[sl], comp(vm), comp(a)], [gray(raw), gray(vm), gray(a)]]
    labels = [["Original", "Apple Vision", "BiRefNet + guided filter"], ["BiRefNet alpha (raw)", "Vision alpha", "BiRefNet alpha (refined)"]]
    sheet = Image.new("RGB", (w * 3 + 40, h * 2 + 30), (30, 30, 30)); dr = ImageDraw.Draw(sheet)
    try: font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
    except OSError: font = None
    for r, row in enumerate(rows):
        for c, im in enumerate(row):
            x, y = 10 + c * (w + 10), 10 + r * (h + 10)
            sheet.paste(Image.fromarray(im), (x, y)); dr.text((x + 14, y + 10), labels[r][c], fill=(255, 255, 0), font=font)
    os.makedirs(OUT, exist_ok=True); dst = f"{OUT}/cutout_compare.jpg"; sheet.save(dst, quality=92)
    print("  comparison:", dst)


def test_search():
    print("Picture search (SigLIP 2)")
    paths = [CAM] + ([SCREEN] if os.path.exists(SCREEN) else [])
    for p in paths:
        timed(f"index {os.path.basename(p)} every 2 s", V.index, [p], 2.0)
    timed("index again (cache hit)", V.index, paths, 2.0)
    for q in ["a man talking to the camera", "a file open dialog", "a chat app with text",
              "a screenshot of a file selection dialog box", "a screenshot of a chat conversation with long text replies"]:
        res = timed(f"search '{q}'", V.search, paths, q, 5)
        for r in res: print(f"    {r['score']:.3f}  {os.path.basename(r['path']):<14} t={r['t']:.1f}")
    best = V.search(paths, "a man talking to the camera", 1)[0]
    assert best["path"] == CAM, best


if __name__ == "__main__":
    print("device:", V.device())
    test_cutout()
    test_search()
    print("ok")
