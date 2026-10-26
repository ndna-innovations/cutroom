"""RIFE slow motion + morph cut on real iPhone HLG footage: frame counts, HLG tags, timings, and a contact sheet of
the morph frames (~/VideoWork/studio-test/interp/morph_sheet.jpg) to judge hands and hair by eye.
Run: .venv/bin/python tests/test_interp.py SRC.mov"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image
from studio import interp, color as C
from studio.frames import read_rgb

if len(sys.argv) < 2: sys.exit("usage: tests/test_interp.py SRC.mov  (an iPhone HLG camera clip)")
SRC = os.path.expanduser(sys.argv[1])
OUT = os.path.expanduser("~/VideoWork/studio-test/interp"); os.makedirs(OUT, exist_ok=True)


def info(p):
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                                   "stream=codec_name,profile,pix_fmt,width,height,r_frame_rate,nb_read_frames,color_primaries,color_transfer,color_space",
                                   "-of", "json", p], capture_output=True, text=True, check=True).stdout)["streams"][0]
    return s


def check(p, frames):
    s = info(p)
    print("   ", {k: s[k] for k in ("codec_name", "profile", "pix_fmt", "width", "height", "r_frame_rate", "nb_read_frames")},
          s["color_primaries"], s["color_transfer"], s["color_space"])
    assert int(s["nb_read_frames"]) == frames, (s["nb_read_frames"], frames)
    assert s["r_frame_rate"] == "30/1" and s["pix_fmt"].startswith("yuv422p10")
    assert (s["color_primaries"], s["color_transfer"], s["color_space"]) == ("bt2020", "arib-std-b67", "bt2020nc")


def timed(label, fn, *a, **kw):
    t0 = time.time(); p = fn(*a, **kw); dt = time.time() - t0
    print(f"{label}: {dt:.1f}s  {p}"); return p, dt


def sheet(paths_frames, path, w=960):
    tiles = []
    for lab, rgb in paths_frames:
        s = C.hlg_to_sdr(rgb.astype(np.float64), 0.9, 0.95)
        im = Image.fromarray((np.clip(s, 0, 1) * 255 + 0.5).astype(np.uint8))
        tiles.append(im.resize((w, int(im.height * w / im.width)), Image.LANCZOS))
    cols = 3; rows = (len(tiles) + cols - 1) // cols; th = tiles[0].height
    out = Image.new("RGB", (cols * w, rows * th), (20, 20, 20))
    for i, t in enumerate(tiles): out.paste(t, ((i % cols) * w, (i // cols) * th))
    out.save(path, quality=90); return path


def test_interp():
    assert interp.available(), "install rife-ncnn-vulkan (see studio/interp.py)"
    for f in (2, 4):
        p, dt = timed(f"slowmo 1s x{f}", interp.slowmo, SRC, 300.0, 301.0, f)
        check(p, 30 * f)
        print(f"    {30 * (f - 1)} new 4K frames, {30 * (f - 1) / dt:.1f} new frames/s (first run; cached runs are instant)")
    a_end, b_start, n = 240.9, 241.6, 4
    p, dt = timed("morph 4 frames", interp.morph, SRC, a_end, b_start, n)
    check(p, n)
    fr = [("A (a_end)", read_rgb(SRC, a_end)[0])]
    mid = read_rgb(p, 0, n=n, matrix="bt2020")
    fr += [(f"morph {i + 1}", m) for i, m in enumerate(mid)]
    fr += [("B (b_start)", read_rgb(SRC, b_start)[0])]
    print("sheet:", sheet(fr, os.path.join(OUT, "morph_sheet.jpg")))
    p, dt = timed("extend 2s", interp.extend, SRC, 300.0, 2.0)
    check(p, 60)


if __name__ == "__main__": test_interp()
