"""Short candidates (like Opus Clip's virality picker, but Claude makes the final call).

candidates(tl) scans the finished timeline's checked words and lists stretches of 15-60 s that start on a sentence,
end on a sentence, and stand alone. Each gets a hook score 0-100 from plain signals:
  + a strong first line (numbers, "I tested", "nobody", "never", "zero", questions, contrast words)
  + concrete numbers / results inside, a clear payoff near the end
  + energy: loudness swings in his voice (he gets animated)
  - starting on a pointing word ("it", "this", "that", "so") or mid-thought, too short / too long, long silences.
Claude reads the top ones (text included) and writes the Short spec."""
import re
import numpy as np
from . import model as M, words as W
from .model import FPS

HOOK = {"tested": 8, "test": 4, "nobody": 8, "never": 6, "zero": 8, "none": 6, "only": 4, "secret": 6, "mistake": 7, "wrong": 6,
        "better": 4, "faster": 5, "fastest": 7, "worst": 7, "best": 5, "won": 5, "beat": 5, "failed": 7, "free": 4, "hidden": 6,
        "found": 4, "why": 5, "how": 4, "what": 3, "stop": 6, "instead": 5, "vs": 6, "versus": 6, "claims": 5, "real": 3, "hid": 7, "hide": 6, "trick": 7, "tricked": 7, "#1": 7, "one": 1, "thousand": 3, "million": 4}
POINTING = {"it", "this", "that", "so", "and", "but", "then", "also", "which", "they", "these", "those"}
PAYOFF = {"so", "verdict", "winner", "result", "bottom", "lesson", "means", "that's", "zero", "all"}


def _sentences(ws):
    out, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        gap = ws[i + 1][0] - w[1] if i + 1 < len(ws) else 9
        if re.search(r"[.!?]$", w[2]) or gap > 1.0:
            out.append(cur); cur = []
    if cur: out.append(cur)
    return out


def score(sents, energy=None, min_s=15, max_s=50):
    first = " ".join(w[2] for w in sents[0]); toks = [W.norm(w[2]) for s in sents for w in s]
    ft = [W.norm(w[2]) for w in sents[0]]
    sc = 40.0; why = []
    h = sum(HOOK.get(t, 0) for t in ft); sc += min(24, h * 1.5)
    if h: why.append("strong first line")
    if any(re.search(r"\d", w[2]) for w in sents[0]): sc += 8; why.append("number in the hook")
    if first.strip().endswith("?"): sc += 6; why.append("question hook")
    if ft and ft[0] in POINTING: sc -= 18; why.append("starts on a pointing word")
    nums = sum(1 for w in (w for s in sents for w in s) if re.search(r"\d", w[2])); sc += min(10, nums * 2)
    last = [W.norm(w[2]) for w in sents[-1]]
    if any(t in PAYOFF for t in last) or any(re.search(r"\d", w[2]) for w in sents[-1]): sc += 6; why.append("ends on a payoff")
    D = sents[-1][-1][1] - sents[0][0][0]
    if D < min_s: sc -= (min_s - D) * 2
    if D > max_s: sc -= (D - max_s)
    gaps = [b[0][0] - a[-1][1] for a, b in zip(sents[:-1], sents[1:])]
    if gaps and max(gaps) > 2.5: sc -= 10; why.append("long pause inside")
    if energy is not None: sc += energy; why.append(f"energy {energy:+.0f}")
    return max(0, min(100, round(sc))), why


def candidates(tl, min_s=15, max_s=60, top=10):
    """[{scene, from, to, secs, score, why, text}] across all scenes (scene time), best first, non-overlapping."""
    R = M.resolve(tl); out = []
    for s in R["scenes"]:
        if not s["words"]: continue
        sents = _sentences(s["words"])
        env = None
        try:
            from .audio import scene_voice
            env_src = scene_voice(s)
            env, t0, hop = W.envelope(env_src)
        except Exception: pass
        for i in range(len(sents)):
            for j in range(i, len(sents)):
                a, b = sents[i][0][0], sents[j][-1][1]
                if b - a > max_s: break
                if b - a < min_s: continue
                e = None
                if env is not None:
                    seg = env[int(a / 0.01): int(b / 0.01)]; seg = seg[seg > -50]
                    if len(seg) > 50: e = float(np.clip((np.std(seg) - 6) * 2, -6, 8))
                sc, why = score(sents[i:j + 1], e, min_s, max_s)
                out.append(dict(scene=s["id"], **{"from": round(max(0, a - 0.05), 2)}, to=round(b + 0.25, 2), secs=round(b - a, 1), score=sc, why=why,
                                text=" ".join(w[2] for ss in sents[i:j + 1] for w in ss)))
    out.sort(key=lambda c: -c["score"])
    picked = []
    for c in out:
        if any(p["scene"] == c["scene"] and not (c["to"] <= p["from"] or c["from"] >= p["to"]) for p in picked): continue
        picked.append(c)
        if len(picked) >= top: break
    return picked
