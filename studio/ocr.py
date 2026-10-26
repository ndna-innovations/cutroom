"""OCR with macOS Vision (studio/bin/studio-vision): find on-screen text boxes for zooms and rings, and scan for
private information (emails, IP addresses, phone numbers, names on a deny list)."""
import json, os, re, subprocess, tempfile
from . import cache
from .media import ff

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "studio-vision")


def ensure_bin():
    if not os.path.exists(BIN):
        src = os.path.join(os.path.dirname(BIN), "..", "native", "vision.swift")
        subprocess.run(["swiftc", "-O", src, "-o", BIN], check=True)
    return BIN


def lines_at(path, t, crop=None):
    """[[x, y, w, h, text, conf], ...] in source px at time t (cached)."""
    k = cache.key("ocr1", path, round(t, 3), crop)
    jp = cache.path("ocr", k, "json")
    if os.path.exists(jp): return json.load(open(jp))
    png = cache.path("ocr", k, "png")
    vf = ["-vf", f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}"] if crop else []
    ff(["-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", *vf, png], label="ocr frame")
    r = subprocess.run([ensure_bin(), "ocr", png], capture_output=True, text=True, check=True)
    L = json.loads(r.stdout.strip().splitlines()[-1])["lines"]
    if crop: L = [[x + crop[0], y + crop[1], w, h, s, c] for x, y, w, h, s, c in L]
    json.dump(L, open(jp, "w")); os.remove(png)
    return L


def find_box(path, t, text, to=None, half=None, pad=14, nth=1):
    """Box around the line containing `text` (down to the line containing `to`), optionally only the left/right half."""
    L = sorted(lines_at(path, t), key=lambda r: (r[1], r[0]))
    W = max((r[0] + r[2] for r in L), default=3456)
    mid = W / 2
    if half == "L": L = [r for r in L if r[0] + r[2] / 2 < mid]
    if half == "R": L = [r for r in L if r[0] + r[2] / 2 > mid]
    hits = [k for k, r in enumerate(L) if text.lower() in r[4].lower()]
    if len(hits) < nth: raise KeyError(f"OCR: {text!r} not found at {t}s in {os.path.basename(path)} (half={half}). Seen: " + " | ".join(r[4] for r in L)[:800])
    i = hits[nth - 1]
    j = i if not to else next((k for k in range(i, len(L)) if to.lower() in L[k][4].lower()), None)
    if j is None: raise KeyError(f"OCR: {to!r} not found after {text!r}")
    y0, y1 = L[i][1] - 2, L[j][1] + 2
    sel = [r for r in L if y0 <= r[1] <= y1]
    x0 = min(r[0] for r in sel); ya = min(r[1] for r in sel); x1 = max(r[0] + r[2] for r in sel); yb = max(r[1] + r[3] for r in sel)
    return [round(x0 - pad, 1), round(ya - pad, 1), round(x1 - x0 + 2 * pad, 1), round(yb - ya + 2 * pad, 1)]


PRIVATE = [
    ("email", r"[\w.+-]+@[\w-]+\.[A-Za-z][\w.-]*"),
    ("ip", r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    ("phone", r"(?:\+?1[ -.]?)?\(?\d{3}\)?[ -.]\d{3}[ -.]\d{4}"),
    ("card", r"\b(?:\d[ -]?){13,16}\b"),
    ("key", r"\b(sk|pk|ghp|xox[abp])[-_][A-Za-z0-9]{10,}"),
]


def scan_dir(d, deny=()):
    """OCR every frame image in d; returns [(file, kind, text, box)]."""
    r = subprocess.run([ensure_bin(), "ocrdir", d], capture_output=True, text=True, check=True)
    hits = []
    for line in r.stdout.splitlines():
        try: o = json.loads(line)
        except ValueError: continue
        for x, y, w, h, s, c in o.get("lines", []):
            for kind, pat in PRIVATE:
                if re.search(pat, s): hits.append((os.path.basename(o["file"]), kind, s, [x, y, w, h]))
            for word in deny:
                if word.lower() in s.lower(): hits.append((os.path.basename(o["file"]), "deny:" + word, s, [x, y, w, h]))
    return hits
