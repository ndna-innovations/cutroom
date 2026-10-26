"""Ingest: what is in a folder of raw footage, ready for planning an edit.

    python -m studio ingest ~/Downloads/today --out media.json
For every file: kind (camera = phone HDR take, screen = Cap/QuickTime recording, music, image, broll), duration,
size, frame rate (variable or not), HDR or not, has sound; for anything with speech: the transcript split into
sentences with times, slips ("cut", "action", "retake"), and lines said more than once (retakes: the last clean one is
usually the keeper). Camera and screen recordings of the same session are synced by their sound (offset stored).
The output is a plain JSON Claude reads to write the timeline."""
import json, os, re, subprocess
import numpy as np
from . import words as W, cache
from .media import probe, log

VIDEO = (".mov", ".mp4", ".m4v", ".mkv")
AUDIO = (".m4a", ".wav", ".mp3", ".aac", ".ogg", ".flac")
IMAGE = (".png", ".jpg", ".jpeg", ".heic", ".webp")


def companion_audio(path):
    """Cap keeps the mic in a separate file next to display.mp4."""
    d = os.path.dirname(path)
    for f in sorted(os.listdir(d)):
        if f.startswith(("audio-input", "microphone", "mic")) and f.endswith(AUDIO): return os.path.join(d, f)
    return None


def has_audio(path):
    return any(s["codec_type"] == "audio" for s in probe(path)["streams"])


def _pcm(path, secs=300, sr=8000):
    a = path if has_audio(path) else companion_audio(path)
    if not a: raise ValueError(f"no sound to sync with in {path}")
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", a, "-t", str(secs), "-vn", "-ac", "1", "-ar", str(sr),
                          "-af", "highpass=f=200,lowpass=f=3000", "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(out, np.float32).astype(np.float64); x -= x.mean(); return x / (x.std() + 1e-12)


def audio_offset(ref, other, max_offset=300, sr=8000):
    """Seconds such that  other_time = ref_time - offset  (cross-correlation of the two sound tracks)."""
    k_ = cache.key("sync3", ref, other, max_offset)
    p = cache.path("probe", "sync_" + k_, "json")
    if os.path.exists(p): return json.load(open(p))["offset"]
    a, b = _pcm(ref, max_offset + 240, sr), _pcm(other, max_offset + 240, sr)
    n = 1 << (len(a) + len(b)).bit_length()
    corr = np.fft.irfft(np.conj(np.fft.rfft(b, n)) * np.fft.rfft(a, n), n)
    lags = np.arange(-min(int(max_offset * sr), len(b) - 1), min(int(max_offset * sr), len(a) - 1) + 1)   # only real overlaps
    c = np.abs(corr[lags % n])
    k = int(np.argmax(c)); mask = np.abs(lags - lags[k]) > sr // 2
    conf = float(c[k] / (c[mask].max() + 1e-12)); off = float(lags[k] / sr)
    if conf < 1.5: log(f"sync {os.path.basename(other)}: low confidence {conf:.2f} (check by eye)")
    json.dump(dict(offset=off, confidence=conf), open(p, "w"))
    return off


def kind_of(path, info):
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE: return "image"
    if ext in AUDIO: return "music" if "sound-library" in path or "music" in path.lower() else "audio"
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not v: return "audio"
    if v.get("color_transfer") == "arib-std-b67": return "camera"
    if os.path.basename(path) == "display.mp4" or ".cap/" in path or "Screen Recording" in path: return "screen"
    return "broll"


def sentences(ws):
    out, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        gap = ws[i + 1][0] - w[1] if i + 1 < len(ws) else 9
        if re.search(r"[.!?]$", w[2]) or gap > 1.2:
            out.append(dict(start=round(cur[0][0], 2), end=round(cur[-1][1], 2), text=" ".join(x[2] for x in cur))); cur = []
    if cur: out.append(dict(start=round(cur[0][0], 2), end=round(cur[-1][1], 2), text=" ".join(x[2] for x in cur)))
    return out


def retakes(sents, min_words=4):
    """Sentences that start the same way as a later one (he said it again): keep the later one."""
    def key(s): return " ".join(W.norm(s["text"]).split()[:min_words])
    out = []
    for i, s in enumerate(sents):
        k = key(s)
        if len(k.split()) < min_words: continue
        later = [t for t in sents[i + 1:i + 8] if key(t) == k]
        if later: out.append(dict(said_at=s["start"], again_at=[t["start"] for t in later], text=s["text"][:80]))
    return out


def ingest(paths, transcribe=True, sync=True):
    files = []
    for p in paths:
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            for root, _, fs in os.walk(p):
                files += [os.path.join(root, f) for f in sorted(fs) if f.lower().endswith(VIDEO + AUDIO + IMAGE)]
        else: files.append(p)
    media = []
    for f in files:
        try: info = probe(f)
        except Exception as e: media.append(dict(path=f, error=str(e))); continue
        v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
        k = kind_of(f, info)
        m = dict(path=f, kind=k, duration=round(float(info["format"].get("duration", 0)), 2))
        if v:
            fr = v.get("avg_frame_rate", "0/1"); rf = v.get("r_frame_rate", "0/1")
            def q(x): a, b = x.split("/"); return float(a) / float(b) if float(b) else 0
            m.update(size=f"{v['width']}x{v['height']}", fps=round(q(fr), 3), variable_fps=abs(q(fr) - q(rf)) > 0.5,
                     hdr=v.get("color_transfer") in ("arib-std-b67", "smpte2084"), sound=has_audio(f) or bool(companion_audio(f)))
        if transcribe and k in ("camera", "audio") or (transcribe and k == "screen" and companion_audio(f)):
            src = f if has_audio(f) else companion_audio(f)
            ws = W.transcribe(src)
            ss = sentences(ws)
            m.update(sentences=ss, slips=[dict(t=round(t, 2), what=s) for t, s in W.slips(ws)], retakes=retakes(ss))
        media.append(m)
    if sync:
        cams = [m for m in media if m.get("kind") == "camera"]
        for m in media:
            if m.get("kind") == "screen" and cams and m.get("sound"):
                try: m["offset_to"] = dict(camera=cams[0]["path"], offset=round(audio_offset(cams[0]["path"], m["path"]), 3))
                except Exception as e: m["offset_to"] = dict(error=str(e))
    return media
