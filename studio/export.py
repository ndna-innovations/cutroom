"""Exports from a finished HLG render.
  sdr     1080p (or 4K) H.264 SDR BT.709: HLG -> SDR with the exact inverse of the graphics mapping and a soft
          highlight roll-off above graphics white (no hard clipping) — for Instagram/TikTok/stories that mishandle HDR.
  review  SDR 1080p, small file, burned timecode + "REVIEW" label: the copy the creator watches on a phone.
  master  ProRes 422 HQ, HLG, for archiving / other editors.
  stills  sRGB JPEGs at given times (slideshow posts, carousels, thumbnails from a frame)."""
import os
import numpy as np
from . import cache, color as C
from .media import ff, log


def sdr_lut(white=0.85, knee=0.92, n=65):
    """HLG BT.2020 R'G'B' -> sRGB BT.709 with a soft roll-off: values up to `knee` of white map 1:1, brighter ones
    compress smoothly into the last bit of headroom instead of clipping."""
    path = os.path.expanduser(f"~/VideoWork/studio-cache/luts/hlg_to_sdr_w{white:.3f}_k{knee:.2f}_{n}.cube")
    if os.path.exists(path): return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    g = np.linspace(0, 1, n); b, gg, r = np.meshgrid(g, g, g, indexing="ij")
    rgb = np.stack([r, gg, b], -1).reshape(-1, 3)
    scene = C.hlg_inv_oetf(rgb); ys = scene @ C.Y2020
    disp = scene * np.power(np.maximum(ys, 1e-12), C.GAMMA - 1)[..., None]
    lin = disp * C.LW / C.ref_nits_for(white) @ C.M2020_709.T            # 1.0 = graphics white, linear 709
    lin = np.clip(lin, 0, None)
    mx = lin.max(-1, keepdims=True)
    k = knee; peak = C.LW / C.ref_nits_for(white)                          # brightest possible value (~4.9)
    # Reinhard-style shoulder on the max channel above the knee (hue kept)
    over = np.maximum(mx - k, 0); room = 1 - k
    comp = np.where(mx > k, k + room * (over / (over + room)) * (1 + over / (peak - k) ** 2) ** 0, mx)
    lin = lin * (comp / np.maximum(mx, 1e-9))
    out = C.srgb_oetf(np.clip(lin, 0, 1))
    with open(path + ".tmp", "w") as f:
        f.write(f"LUT_3D_SIZE {n}\n"); np.savetxt(f, out, fmt="%.6f")
    os.replace(path + ".tmp", path); return path


def _sdr_chain(w, white=0.85):
    return (f"scale=in_color_matrix=bt2020:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb48le,lut3d=file='{sdr_lut(white)}':interp=tetrahedral,"
            f"scale={w}:-2:flags=lanczos,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
            f"setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")   # else the frames keep the HLG tags -> players show red faces


def sdr(video, out=None, width=1920, white=0.85, crf=18):
    out = out or os.path.splitext(video)[0] + f"-SDR-{width}.mp4"
    ff(["-i", video, "-vf", _sdr_chain(width, white), "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], label="sdr")
    return out


def review(video, out=None, width=1280, label="REVIEW"):
    """Small SDR copy with a timecode in the corner (one label image per second; this ffmpeg has no text filter)."""
    from PIL import Image, ImageDraw, ImageFont
    from .media import duration
    import tempfile, shutil
    out = out or os.path.splitext(video)[0] + "-review.mp4"
    D = duration(video); fs = max(18, width // 42)
    tmp = tempfile.mkdtemp(dir=os.path.expanduser("~/VideoWork"), prefix="tc_")
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", fs)
        for i in range(int(D) + 2):
            txt = f"{label}  {i // 60}:{i % 60:02d}"
            w_ = int(font.getlength(txt)) + 24
            im = Image.new("RGBA", (w_, fs + 16), (0, 0, 0, 150)); ImageDraw.Draw(im).text((12, 6), txt, font=font, fill=(255, 255, 255, 255))
            im.save(f"{tmp}/{i:05d}.png")
        ff(["-i", video, "-framerate", "1", "-i", f"{tmp}/%05d.png", "-filter_complex",
            f"[0:v]{_sdr_chain(width)}[b];[1:v]format=rgba,fps=30[t];[b][t]overlay=W-w-16:16:shortest=1:eof_action=repeat,format=yuv420p[v]",
            "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out], label="review")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def master(video, out=None):
    out = out or os.path.splitext(video)[0] + "-master.mov"
    ff(["-i", video, "-c:v", "prores_videotoolbox", "-profile:v", "hq", "-pix_fmt", "p210le", *C.ENC_TAGS, "-c:a", "pcm_s24le", out], label="master")
    return out


def stills(video, times, folder=None, width=1080):
    """sRGB JPEGs (viewer's view) at the given seconds."""
    from . import frames as F
    folder = folder or os.path.splitext(video)[0] + "-stills"; os.makedirs(folder, exist_ok=True)
    from PIL import Image
    out = []
    for i, t in enumerate(times):
        f = F.read_rgb(video, float(t))[0]
        lut_img = C.hlg_to_sdr(np.clip(f.astype(np.float64), 0, 1), 0.9, 0.95)
        im = Image.fromarray((np.clip(lut_img, 0, 1) * 255 + 0.5).astype(np.uint8))
        if width and im.width != width: im = im.resize((width, int(width * im.height / im.width)), Image.LANCZOS)
        p = os.path.join(folder, f"{i + 1:02d}_{t:07.2f}.jpg"); im.save(p, quality=93); out.append(p)
    return out
