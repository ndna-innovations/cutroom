"""Drawn tool tiles for Shorts, cards and thumbnails: a tool word gets its tool tile,
never a generic emoji that means something else in everyday life (tickets ≠ 🎫, Slack ≠ 💬).
Plain shapes in the tool's colours, no official logos. Import: sys.path.insert(0, ".../recordings/tools"); from tool_icons import tool_icon
Usage: tool_icon("jira", 112) -> RGBA image about 112 px tall. Names: jira, confluence, slack, gmail, github, database, mixpanel, newrelic, claude, chatgpt, gemini.
"""
from PIL import Image, ImageDraw, ImageFont

AV = "/System/Library/Fonts/Avenir Next.ttc"
WHITE, GREEN, GREY = (255, 255, 255, 255), (52, 199, 89, 255), (180, 190, 205, 255)


def _tile(size, colour, r=0.18):
    w = int(size * 0.92); im = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w - 1, w - 1], int(w * r), fill=colour)
    return im, ImageDraw.Draw(im), w


def _glyph(d, w, text, scale=0.6, colour=WHITE, dy=0.0):
    f = ImageFont.truetype(AV, int(w * scale), index=8)
    d.text((w // 2, w // 2 + int(w * dy)), text, font=f, fill=colour, anchor="mm")


def jira(size):        # blue tile with ticket rows
    s = size / 112; w, h = int(100 * s), int(112 * s)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], int(16 * s), fill=(0, 101, 255, 255))
    for k in range(3):
        y = int((16 + k * 30) * s)
        d.rounded_rectangle([int(12 * s), y, w - int(12 * s), y + int(22 * s)], int(5 * s), fill=WHITE)
        d.rectangle([int(20 * s), y + int(8 * s), int(30 * s), y + int(14 * s)], fill=GREEN)
        d.rounded_rectangle([int(36 * s), y + int(8 * s), w - int(22 * s), y + int(14 * s)], int(3 * s), fill=GREY)
    return im


def confluence(size):  # navy tile with a white page
    im, d, w = _tile(size, (23, 43, 77, 255))
    d.rounded_rectangle([int(w * .2), int(w * .14), int(w * .8), int(w * .86)], int(w * .06), fill=WHITE)
    for k in range(4):
        y = int(w * (.3 + k * .13)); d.rounded_rectangle([int(w * .3), y, int(w * (.7 if k < 3 else .55)), y + int(w * .05)], 3, fill=GREY)
    return im


def slack(size):       # aubergine tile, white #
    im, d, w = _tile(size, (74, 21, 75, 255), r=0.2); _glyph(d, w, "#", 0.78, dy=0.03); return im


def gmail(size):       # white tile, red envelope
    im, d, w = _tile(size, (255, 255, 255, 255))
    x0, y0, x1, y1 = int(w * .14), int(w * .26), int(w * .86), int(w * .74)
    d.rectangle([x0, y0, x1, y1], outline=(234, 67, 53, 255), width=max(3, w // 14))
    d.line([x0, y0, w // 2, int(w * .52), x1, y0], fill=(234, 67, 53, 255), width=max(3, w // 14))
    return im


def github(size):      # near-black tile, white </> mark
    im, d, w = _tile(size, (36, 41, 47, 255)); _glyph(d, w, "</>", 0.36); return im


def database(size):    # blue cylinder
    w = int(size * 0.8); h = int(size * 0.95); im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    e = int(w * .32); col, edge = (59, 130, 246, 255), (191, 219, 254, 255)
    for k in range(3):
        top = k * (h - e) // 3
        d.rectangle([0, top + e // 2, w - 1, top + e // 2 + (h - e) // 3], fill=col)
        d.ellipse([0, top + (h - e) // 3, w - 1, top + (h - e) // 3 + e], fill=col, outline=edge, width=3)
    d.ellipse([0, 0, w - 1, e], fill=(96, 165, 250, 255), outline=edge, width=3)
    return im


def mixpanel(size):    # purple tile, bar chart
    im, d, w = _tile(size, (124, 58, 237, 255))
    for k, hgt in enumerate((.3, .5, .7)):
        x = int(w * (.2 + k * .22)); d.rounded_rectangle([x, int(w * (.8 - hgt)), x + int(w * .16), int(w * .8)], 3, fill=WHITE)
    return im


def newrelic(size):    # dark tile, green pulse line
    im, d, w = _tile(size, (16, 24, 32, 255))
    pts = [(.12, .55), (.35, .55), (.45, .3), (.55, .75), (.65, .5), (.88, .5)]
    d.line([(int(w * x), int(w * y)) for x, y in pts], fill=(28, 231, 131, 255), width=max(3, w // 16), joint="curve")
    return im


def claude(size):      # warm orange tile, white burst (plain shape, not the logo)
    im, d, w = _tile(size, (217, 119, 87, 255)); c = w / 2
    import math
    for k in range(12):
        a = k * math.pi / 6; r0, r1 = w * .08, w * (.36 if k % 2 == 0 else .28)
        d.line([(c + r0 * math.cos(a), c + r0 * math.sin(a)), (c + r1 * math.cos(a), c + r1 * math.sin(a))], fill=WHITE, width=max(3, w // 14))
    return im


def chatgpt(size):     # black tile, white ring of petals (plain shape, not the logo)
    im, d, w = _tile(size, (16, 16, 16, 255)); c = w / 2
    import math
    for k in range(6):
        a = k * math.pi / 3; x, y = c + w * .14 * math.cos(a), c + w * .14 * math.sin(a); r = w * .16
        d.ellipse([x - r, y - r, x + r, y + r], outline=WHITE, width=max(2, w // 22))
    return im


def gemini(size):      # dark tile, blue four-point sparkle (plain shape, not the logo)
    im, d, w = _tile(size, (24, 28, 48, 255)); c = w / 2; R, r = w * .36, w * .07
    pts = [(c, c - R), (c + r, c - r), (c + R, c), (c + r, c + r), (c, c + R), (c - r, c + r), (c - R, c), (c - r, c - r)]
    d.polygon(pts, fill=(96, 150, 255, 255)); return im


TOOLS = {"jira": jira, "confluence": confluence, "slack": slack, "gmail": gmail, "github": github,
         "database": database, "mixpanel": mixpanel, "newrelic": newrelic,
         "claude": claude, "chatgpt": chatgpt, "gemini": gemini}


def tool_icon(name, size=112):
    return TOOLS[name.lower()](size)


if __name__ == "__main__":   # preview sheet: python3 tool_icons.py OUT.png
    import sys
    sheet = Image.new("RGBA", (len(TOOLS) * 150 + 20, 190), (10, 16, 30, 255)); d = ImageDraw.Draw(sheet)
    for i, n in enumerate(TOOLS):
        im = tool_icon(n, 112); sheet.alpha_composite(im, (20 + i * 150, 20)); d.text((20 + i * 150, 150), n, fill=WHITE)
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "/tmp/tool_icons.png")


def tool_png(name, size=256):
    """Path of a cached PNG of the tool tile (used by graphics props as "tool:jira" etc.)."""
    import os
    d = os.path.expanduser("~/VideoWork/studio-cache/assets/tools"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{name}_{size}.png")
    if not os.path.exists(p): tool_icon(name, size).save(p)
    return p
