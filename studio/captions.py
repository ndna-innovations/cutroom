"""Closed captions (.srt) and chapters from the timeline's CHECKED words.
- Cues: up to 2 lines x 42 characters, 1-6 s, broken at sentence ends / pauses.
- Stretches with burned-in captions are left out (viewers with CC on would see captions twice).
- Optional text fixes from the profile ("caption_fixes": [[heard, shown], ...]); none are built in."""
import re
from . import model as M
from .model import FPS

from .config import profile as _profile
FIX = [(r"\b" + re.escape(a) + r"\b\.?", b) for a, b in (_profile().get("caption_fixes") or [])]     # e.g. a sign-off the speech model shortens


def timeline_words(R):
    out = []
    for s in R["scenes"]:
        t0 = s["start"] / FPS
        for a, b, w in s["words"]: out.append([t0 + a, t0 + b, w])
    return out


def burned(R):
    rs = [((s["start"] + l["f0"]) / FPS, (s["start"] + l["f1"]) / FPS) for s in R["scenes"] for l in s["layers"] if l["kind"] == "captions"]
    rs += [(l["f0"] / FPS, l["f1"] / FPS) for l in R.get("overlays", []) if l["kind"] == "captions"]
    return rs


def cues(R, max_chars=42, max_secs=6.0):
    ws = [w for w in timeline_words(R) if not any(a - 0.05 <= w[0] < b for a, b in burned(R))]
    out, cur = [], []
    def flush():
        if cur: out.append([cur[0][0], cur[-1][1], " ".join(x[2] for x in cur)]); cur.clear()
    for i, w in enumerate(ws):
        if cur and (len(" ".join(x[2] for x in cur + [w])) > 2 * max_chars or w[1] - cur[0][0] > max_secs or w[0] - cur[-1][1] > 0.7): flush()
        cur.append(w)
        if re.search(r"[.!?]$", w[2]) and len(" ".join(x[2] for x in cur)) > 18: flush()
    flush()
    for c in out:
        for pat, rep in FIX: c[2] = re.sub(pat, rep, c[2])
    for i in range(len(out) - 1): out[i][1] = min(out[i][1] + 0.3, out[i + 1][0] - 0.02)
    return out


def _wrap(t, n=42):
    if len(t) <= n: return t
    words, best = t.split(), None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        sc = max(len(a), len(b))
        if best is None or sc < best[0]: best = (sc, a + "\n" + b)
    return best[1]


def ts(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)) % 1000:03d}"


def write_srt(tl, path):
    R = M.resolve(tl)
    cs = cues(R)
    with open(path, "w") as f:
        for i, (a, b, t) in enumerate(cs, 1): f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{_wrap(t)}\n\n")
    return path, len(cs)


def chapters(tl, marks):
    """marks: [(scene_id, "Title")] -> 'MM:SS Title' lines (first must be 0:00)."""
    R = M.resolve(tl); st = {s["id"]: s["start"] / FPS for s in R["scenes"]}
    lines = []
    for sid, title in marks:
        t = st[sid]; lines.append(f"{int(t // 60)}:{int(t % 60):02d} {title}")
    if lines and not lines[0].startswith("0:00"): lines[0] = "0:00 " + lines[0].split(" ", 1)[1]
    return "\n".join(lines)


# ---------------------------------------------------------------------- translation
def export_for_translation(tl, path, include_burned=True):
    """Cues as JSON for translating ([{i, start, end, text}]). Claude translates the texts (best quality, any
    language) and calls write_translated(). include_burned=True also lists burned-caption stretches (for a fully
    translated burned version)."""
    import json
    R = M.resolve(tl)
    if include_burned:
        ws = timeline_words(R); out, cur = [], []
        for w in ws:
            if cur and (len(" ".join(x[2] for x in cur + [w])) > 84 or w[0] - cur[-1][1] > 0.7): out.append(cur); cur = []
            cur.append(w)
            if re.search(r"[.!?]$", w[2]): out.append(cur); cur = []
        if cur: out.append(cur)
        cs = [[c[0][0], c[-1][1], " ".join(x[2] for x in c)] for c in out]
    else:
        cs = cues(R)
    data = [dict(i=i, start=round(a, 3), end=round(b, 3), text=t) for i, (a, b, t) in enumerate(cs)]
    json.dump(data, open(path, "w"), indent=1, ensure_ascii=False)
    return path


def write_translated(cues_json, translations, path, skip_burned_tl=None):
    """translations: list of strings in the same order as the exported cues -> .srt in that language.
    skip_burned_tl: a timeline whose burned-caption stretches should be left out (CC only)."""
    import json
    cs = json.load(open(cues_json))
    burned_r = burned(M.resolve(skip_burned_tl)) if skip_burned_tl else []
    with open(path, "w") as f:
        k = 0
        for c, t in zip(cs, translations):
            if any(a - 0.05 <= c["start"] < b for a, b in burned_r): continue
            k += 1; f.write(f"{k}\n{ts(c['start'])} --> {ts(c['end'] + 0.25)}\n{_wrap(t)}\n\n")
    return path


def translated_layer(cues_json, translations, scene_start=0.0):
    """A burned 'captions' layer (timeline overlay) showing the translated cues at the original times."""
    import json
    cs = json.load(open(cues_json))
    return dict(kind="captions", style="phrase", at=0, cues=[[round(c["start"] - scene_start, 3), round(c["end"] + 0.2 - scene_start, 3), t] for c, t in zip(cs, translations)])
