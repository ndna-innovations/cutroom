"""Read/write frames as float arrays in the HLG BT.2020 R'G'B' domain (no tone change: just the BT.2020 matrix),
and make sRGB previews of HLG frames that look like QuickTime (via color.hlg_to_srgb)."""
import subprocess
import numpy as np
from . import color as C


def read_rgb(src, t=None, n=1, crop=None, ss_accurate=True, fps=30, matrix="bt2020", step=1):
    """n frames from src starting at t as float32 (n, h, w, 3) in 0..1 (code values, full range)."""
    vf = []
    if crop:     # even position and size (4:2:0 video: odd crops get rounded by ffmpeg and the frame size no longer matches)
        crop = [int(v) // 2 * 2 for v in crop]; x, y, w, h = crop; vf.append(f"crop={w}:{h}:{x}:{y}")
    if step > 1: vf.append(f"select='not(mod(n\\,{step}))'")
    vf.append(f"scale=in_color_matrix={matrix}:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb48le")
    meta = probe_wh(src) if not crop else (crop[2], crop[3])
    w, h = meta
    a = (["-ss", f"{t:.4f}"] if t is not None else [])
    cmd = ["ffmpeg", "-v", "error", "-nostdin", *a, "-i", src, "-vf", ",".join(vf), "-frames:v", str(n), "-fps_mode", "passthrough",
           "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    arr = np.frombuffer(raw, np.uint16).reshape(-1, h, w, 3)
    return arr.astype(np.float32) / 65535


def probe_wh(src):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", src],
                       capture_output=True, text=True, check=True).stdout.strip().split(",")
    return int(o[0]), int(o[1])


def preview(rgb_hlg, path, white=0.75, scale=None):
    """Save an sRGB JPEG/PNG of an HLG frame (what a viewer sees, with graphics white = sRGB white)."""
    from PIL import Image
    s = C.hlg_to_srgb(np.clip(rgb_hlg.astype(np.float64), 0, 1), white)
    im = Image.fromarray((np.clip(s, 0, 1) * 255 + 0.5).astype(np.uint8))
    if scale: im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    im.save(path, quality=92)
    return path
