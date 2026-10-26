"""ffmpeg chain (lut3d + bt2020 matrix) must match the exact numpy maths to within 2 code values (10-bit)."""
import subprocess, numpy as np, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from studio import color as C

def test_chain():
    cols = [(255, 255, 255), (128, 128, 128), (255, 0, 0), (0, 255, 0), (0, 0, 255), (245, 158, 11), (10, 12, 26), (232, 128, 90), (0, 0, 0)]
    im = Image.new("RGBA", (16 * len(cols), 16))
    for i, c in enumerate(cols): im.paste(c + (255,), (16 * i, 0, 16 * i + 16, 16))
    p = os.path.expanduser("~/VideoWork/studio-test/patch.png"); os.makedirs(os.path.dirname(p), exist_ok=True); im.save(p)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-vf", C.overlay_chain(), "-f", "rawvideo", "-pix_fmt", "yuva444p10le", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint16).reshape(4, 16, 16 * len(cols))
    worst = 0
    for i, c in enumerate(cols):
        got = a[:3, 8, 16 * i + 8].astype(float)
        exp = C.to_limited10(C.rgb_to_ycbcr(C.srgb_to_hlg(np.array(c) / 255)))
        worst = max(worst, np.abs(got - exp).max())
        print(c, got, exp.round(1))
    assert a[3].min() == 1023, "alpha lost"
    assert worst <= 2.0, worst
    print("worst", worst)

if __name__ == "__main__": test_chain()
