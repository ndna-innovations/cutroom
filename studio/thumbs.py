"""Thumbnail options: several wordings x layouts, rendered as 1920x1080 sRGB JPEGs + one contact sheet to choose from
(the creator picks; nothing is final until they do). With a face: one photo cut out from the HDR camera frame (proper
colour). Without (face=False, or profile "thumbnail_face": false): layout "noface" = huge words left, tool tiles right.

    options(cam_path, at=785.4, wordings=[["ARGON", "FOUND ZERO."], ...], badge="GEMINI vs CLAUDE", icons=[...],
            layouts=["face-right", "face-left"], out_dir=...)
    options(None, None, wordings=[["ONE APP", "TWO TOOLS"]], icons=[a.png, b.png], icon_sep="+", face=False, out_dir=...)"""
import os
from PIL import Image, ImageDraw, ImageFont
from . import gfx, shorts, assets as A


def use_face(face=None):
    """Whether thumbnails show a face: the call's choice, else the profile's "thumbnail_face" (default: yes)."""
    if face is not None: return bool(face)
    from .config import profile
    return bool(profile().get("thumbnail_face", True))


def options(cam_path, at, wordings, out_dir, badge=None, icons=None, proof=None, layouts=("face-right",), kit=None, photo=None, matte="vision", icon_sep="vs", style=None, hero=None, stamp=None, bg=None, face=None):
    os.makedirs(out_dir, exist_ok=True)
    if use_face(face):
        if not (photo or cam_path): raise ValueError("a face thumbnail needs a camera file + time (or photo); for none: face=False / --no-face")
        photo = photo or _tight(shorts.cutout(cam_path, at, matte=matte))
    else:
        photo = None
        if not style: layouts = ["noface"]
    th = {k: list(v) for k, v in A.theme(kit or {}).items()}
    outs = []
    for wi, lines in enumerate(wordings):
        for lay in layouts:
            props = dict(lines=lines, badge=badge, layout=lay, photo="file://" + photo if photo else None, _theme=th,
                         icons=["file://" + os.path.expanduser(i) for i in icons] if icons else None, proof="file://" + os.path.expanduser(proof) if proof else None, icon_sep=icon_sep)
            if style:      # other designs: poster | split | warning | repo (ThumbnailStyle)
                props.update(style=style, hero=hero, stamp=stamp, bg=bg)
                p = os.path.join(out_dir, f"thumb_{wi + 1}_{style}.jpg")
                gfx.still_srgb("ThumbnailStyle", props, (1920, 1080), p); outs.append(p); continue
            p = os.path.join(out_dir, f"thumb_{wi + 1}_{lay}.jpg")
            gfx.still_srgb("Thumbnail", props, (1920, 1080), p); outs.append(p)
    # sheet (with the phone-size view: thumbnails are judged small)
    tiles = [Image.open(p).resize((640, 360)) for p in outs]
    cols = min(3, len(tiles)); rows = -(-len(tiles) // cols)
    sheet = Image.new("RGB", (cols * 640, rows * 400), (20, 20, 24)); d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype("/System/Library/Fonts/Avenir Next.ttc", 22, index=5)
    for i, (t, p) in enumerate(zip(tiles, outs)):
        x, y = (i % cols) * 640, (i // cols) * 400; sheet.paste(t, (x, y)); d.text((x + 8, y + 366), os.path.basename(p), fill=(220, 220, 220), font=f)
    sp = os.path.join(out_dir, "thumbnail-options.jpg"); sheet.save(sp, quality=90)
    return outs, sp


def _tight(p, ratio=0.8):
    """Head-and-shoulders crop of a cut-out: width = height x ratio, centred on the head (alpha mass of the top rows)."""
    import numpy as np
    im = Image.open(p).convert("RGBA"); a = np.asarray(im)[..., 3].astype(float)
    top = a[: max(1, a.shape[0] * 2 // 5)]
    cx = int((top.sum(0) * np.arange(a.shape[1])).sum() / max(1, top.sum()))
    w = min(im.width, int(im.height * ratio)); x0 = max(0, min(im.width - w, cx - w // 2))
    c = np.asarray(im.crop((x0, 0, x0 + w, im.height))).copy()
    f = max(8, w // 10); ramp = np.ones(w); ramp[:f] = np.linspace(0, 1, f); ramp[-f:] = np.linspace(1, 0, f)   # soft sides
    if x0 == 0: ramp[:f] = 1
    if x0 + w >= im.width: ramp[-f:] = 1
    c[..., 3] = (c[..., 3] * ramp[None, :]).astype(np.uint8)
    out = p.replace(".png", "_tight.png"); Image.fromarray(c).save(out); return out
