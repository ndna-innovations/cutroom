"""Generate b-roll clips from a prompt, into the b-roll library (by topic), with the prompt saved next to each clip.

Engines:
  veo    Google Veo through the Gemini API (best, photo-real; PAID per second). Key: config paths.gemini_key.
         Every paid run needs confirm=True (CLI: --yes) after the estimate is shown: money is never spent silently.
  local  a free open model on this Mac via mlx-video: FastWan 2.2 TI2V-5B (Apache-2.0, 3-step DMD), text or text+image
         (image= becomes the first frame: picture-to-clip). ~2.6 min for 5 s at 832x480 (22 s of that is the 3 steps, the rest decoding) -> 1080p; below Veo, no cost per clip.
  scene  Cutroom's own 3D/animated scenes (template + props): free, instant, any text.

    clip = generate("A typewriter typing by itself...", engine="veo", secs=8, aspect="16:9", topic="writing", confirm=True)
    find("typewriter")      -> clips in the library whose name/prompt match, best first
Library layout: <broll_library>/<topic>/<slug>_<aspect>_<res>.mp4 + .json (prompt, engine, model, date, cost)."""
import datetime, json, os, re, shutil, subprocess, time, urllib.request
from .config import path as _cfg_path, load as _cfg
from .media import log

VEO_MODEL = "veo-3.1-generate-preview"
VEO_PRICE = {"720p": 0.40, "1080p": 0.40, "4k": 0.60}       # US$ per second (Gemini API list price, Sept 2026; check before big batches)
API = "https://generativelanguage.googleapis.com/v1beta"


def library():
    return _cfg_path("broll_library")


def slug(s, n=60):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n].strip("-") or "clip"


def estimate(engine, secs, res="1080p"):
    """Cost in US$ of one generation (0 for local/scene)."""
    return round(VEO_PRICE.get(res.lower(), 0.40) * secs, 2) if engine == "veo" else 0.0


def _save(src, prompt, engine, topic, aspect, res, meta):
    d = os.path.join(library(), slug(topic or "general", 40)); os.makedirs(d, exist_ok=True)
    base = f"{slug(prompt)}_{aspect.replace(':', 'x')}_{res}"
    out = os.path.join(d, base + ".mp4"); k = 2
    while os.path.exists(out): out = os.path.join(d, f"{base}-{k}.mp4"); k += 1
    shutil.move(src, out)
    json.dump(dict(prompt=prompt, engine=engine, aspect=aspect, resolution=res, made=datetime.datetime.now().isoformat(timespec="seconds"), **meta),
              open(os.path.splitext(out)[0] + ".json", "w"), indent=1)
    return out


# ------------------------------------------------------------------ veo (Gemini API)
def _key():
    p = _cfg_path("gemini_key")
    if not os.path.exists(p): raise RuntimeError(f"no Gemini API key at {p} (aistudio.google.com -> Get API key; paste it into that file)")
    return open(p).read().strip()


def _veo(prompt, secs, aspect, res, negative=None, image=None, model=None, timeout=900):
    model = model or (_cfg().get("veo_model") or VEO_MODEL); key = _key()
    params = {"aspectRatio": aspect, "durationSeconds": int(secs), "resolution": res}
    if negative: params["negativePrompt"] = negative
    inst = {"prompt": prompt}
    if image:
        import base64, mimetypes
        inst["image"] = {"bytesBase64Encoded": base64.b64encode(open(image, "rb").read()).decode(), "mimeType": mimetypes.guess_type(image)[0] or "image/png"}
    req = urllib.request.Request(f"{API}/models/{model}:predictLongRunning", data=json.dumps({"instances": [inst], "parameters": params}).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    op = json.load(urllib.request.urlopen(req, timeout=60))["name"]
    t0 = time.time()
    while True:
        time.sleep(10)
        st = json.load(urllib.request.urlopen(urllib.request.Request(f"{API}/{op}", headers={"x-goog-api-key": key}), timeout=60))
        if st.get("done"): break
        if time.time() - t0 > timeout: raise RuntimeError(f"Veo still running after {timeout}s: {op}")
        log(f"veo: generating… {time.time() - t0:.0f}s")
    if "error" in st: raise RuntimeError(f"Veo error: {st['error']}")
    samples = (st.get("response", {}).get("generateVideoResponse", {}) or {}).get("generatedSamples") or []
    if not samples: raise RuntimeError(f"Veo returned no video (maybe filtered): {json.dumps(st)[:400]}")
    uri = samples[0]["video"]["uri"]
    tmp = os.path.join(os.path.expanduser("~/VideoWork"), f"veo_{int(time.time())}.mp4")
    with urllib.request.urlopen(urllib.request.Request(uri, headers={"x-goog-api-key": key}), timeout=300) as r, open(tmp, "wb") as f: shutil.copyfileobj(r, f)
    return tmp, dict(model=model)


# ------------------------------------------------------------------ local (mlx-video)
def local_available():
    import importlib.util
    return importlib.util.find_spec("mlx_video") is not None and os.path.isdir(_cfg_path("local_video_model"))


def _local(prompt, secs, aspect, res, negative=None, seed=42, image=None):
    if not local_available():
        raise RuntimeError("local video model not installed: pip install git+https://github.com/Blaizzy/mlx-video.git, then put FastWan2.2 "
                           f"TI2V-5B MLX weights in {_cfg_path('local_video_model')} (see README 'Generate')")
    import sys
    mdir = _cfg_path("local_video_model")
    fast = "fastwan_dmd" in json.load(open(os.path.join(mdir, "config.json")))
    # 832x480 fits in memory on a 64 GB Mac; the result is upscaled to 1080p. Prompts: say "unbranded" (it draws logos). 720p ("hq") needs far more memory.
    w, h = {"16:9": (832, 480), "9:16": (480, 832), "1:1": (640, 640)}.get(aspect, (832, 480))
    if res in ("720p", "hq"): w, h = {"16:9": (1280, 704), "9:16": (704, 1280)}.get(aspect, (1280, 704))
    frames = int(secs * 24) // 4 * 4 + 1
    tmp = os.path.join(os.path.expanduser("~/VideoWork"), f"local_{int(time.time())}.mp4")
    if fast:   # FastWan (DMD): 3 steps, no CFG
        cmd = [sys.executable, "-m", "studio.wan_fast", "--model-dir", mdir, "--prompt", prompt, "--width", str(w), "--height", str(h),
               "--num-frames", str(frames), "--seed", str(seed), "--output-path", tmp]
    else:      # plain Wan 2.2: 25 UniPC steps with CFG (about 8x slower)
        cmd = [sys.executable, "-m", "mlx_video.models.wan_2.generate", "--model-dir", mdir, "--prompt", prompt,
               "--width", str(w), "--height", str(h), "--num-frames", str(frames), "--seed", str(seed), "--output-path", tmp,
               "--steps", "25", "--scheduler", "unipc", "--tiling", "auto"]
        if negative: cmd += ["--negative-prompt", negative]
    if image: cmd += ["--image", os.path.expanduser(image)]
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode: raise RuntimeError(f"local generation failed: {(r.stderr or r.stdout)[-800:]}")
    up = tmp.replace(".mp4", "_1080.mp4")             # upscale to 1080p (lanczos) so it sits well in 4K edits
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-vf", f"scale=-2:{1080 if aspect != '9:16' else 1920}:flags=lanczos,format=yuv420p",
                    "-c:v", "libx264", "-crf", "16", up], check=True); os.remove(tmp)
    return up, dict(model=("fastwan2.2-ti2v-5b (DMD 3-step)" if fast else "wan2.2-ti2v-5b-q8") + " (mlx-video)", generated=f"{w}x{h}",
                    seed=seed, seconds_to_make=round(time.time() - t0), **({"image": os.path.basename(image)} if image else {}))


# ------------------------------------------------------------------ scene (Cutroom templates)
def _scene(template, props, secs, aspect):
    from .edit import Timeline
    d = os.path.expanduser("~/VideoWork/generate-scene"); os.makedirs(d, exist_ok=True)
    prof = "short" if aspect == "9:16" else "yt4k"
    tl = Timeline.new(f"scene-{int(time.time())}", profile=prof, folder=d, kit={"graphics": {"motion_blur": 8}})
    tl.scene("s", duration=float(secs), base=[dict(at=0, kind="graphic", template=template, props=props or {})])
    out = os.path.join(d, f"{tl.d['name']}.mp4"); tl.render(out=out)
    return out, dict(model=f"cutroom:{template}")


def generate(prompt, engine="veo", secs=8, aspect="16:9", res="1080p", topic=None, negative=None, image=None,
             template=None, props=None, confirm=False, model=None):
    """Make one clip and file it in the b-roll library. Returns its path. Paid engines need confirm=True."""
    cost = estimate(engine, secs, res)
    if cost and not confirm:
        raise PermissionError(f"{engine} costs about US${cost:.2f} for {secs}s at {res}: ask first, then call again with confirm=True (CLI --yes)")
    if engine == "veo": tmp, meta = _veo(prompt, secs, aspect, res, negative, image, model)
    elif engine == "local": tmp, meta = _local(prompt, secs, aspect, res, negative, image=image)
    elif engine == "scene": tmp, meta = _scene(template or "BookReveal", props, secs, aspect)
    else: raise ValueError(f"unknown engine {engine}")
    out = _save(tmp, prompt, engine, topic, aspect, res, dict(meta, cost_usd=cost, secs=secs))
    log(f"generate: {engine} -> {out}" + (f" (~US${cost:.2f})" if cost else ""))
    return out


def add(src, prompt="", topic=None, engine="veo-app", aspect=None, move=False):
    """File a clip made elsewhere (e.g. downloaded from the Gemini app) into the library with its prompt. Returns the new path."""
    import shutil as _sh
    from .media import probe
    v = next((s for s in probe(src)["streams"] if s["codec_type"] == "video"), {})
    w, h = int(v.get("width", 1920)), int(v.get("height", 1080))
    aspect = aspect or ("9:16" if h > w * 1.2 else "1:1" if abs(w - h) < 40 else "16:9")
    res = f"{min(w, h)}p"
    tmp = os.path.join(os.path.expanduser("~/VideoWork"), f"add_{int(time.time())}{os.path.splitext(src)[1]}")
    (_sh.move if move else _sh.copy2)(os.path.expanduser(src), tmp)
    return _save(tmp, prompt or os.path.splitext(os.path.basename(src))[0].replace("_", " "), engine, topic, aspect, res,
                 dict(source=os.path.basename(src), width=w, height=h))


def index():
    """Every clip in the library: [{path, topic, name, prompt, engine, secs, aspect}]."""
    out = []
    root = library()
    for dp, _, fs in os.walk(root):
        for f in fs:
            if not f.lower().endswith((".mp4", ".mov", ".m4v")): continue
            p = os.path.join(dp, f); side = os.path.splitext(p)[0] + ".json"
            meta = json.load(open(side)) if os.path.exists(side) else {}
            out.append(dict(path=p, topic=os.path.relpath(dp, root), name=f, prompt=meta.get("prompt", ""), engine=meta.get("engine", "?"),
                            aspect=meta.get("aspect") or ("9x16" if "9x16" in f else "16x9"), secs=meta.get("secs")))
    return out


def find(query, top=10, pictures=False):
    """Clips matching the words (file name, topic, saved prompt); pictures=True also ranks by what's in the frames (SigLIP 2)."""
    ws = set(re.findall(r"[a-z0-9]{3,}", query.lower()))
    rows = []
    for c in index():
        hay = f"{c['topic']} {c['name']} {c['prompt']}".lower()
        sc = sum(1 for w in ws if w in hay)
        if sc: rows.append((sc, c))
    rows.sort(key=lambda r: -r[0]); res = [dict(c, score=s) for s, c in rows[:top]]
    if pictures:
        from . import ai_vision
        hits = ai_vision.search([c["path"] for c in index()], query, top=top)
        seen = {r["path"] for r in res}
        res += [dict(path=h["path"], t=h["t"], score=h["score"], by="picture") for h in hits if h["path"] not in seen]
    return res
