"""Render a timeline: plan chunks -> build missing assets -> render changed chunks in parallel -> join -> mix -> mux.

- Chunks are ~8 s windows (cut at scene, transition and shot boundaries). Each chunk's cache key is the hash of its
  compiled ffmpeg graph + input fingerprints + profile + engine version, so a small fix re-renders only the chunks it
  touches. Chunks are encoded once (HEVC Main10 HLG on the media engine) and joined without re-encoding.
- `frame(tl, t)` renders one frame (or a few) straight from the graph: Claude checks layouts without a full render.
- Every run writes a report (timings, cache hits, checks) next to the output."""
import concurrent.futures as cf, json, os, shutil, time
from . import assets as A, cache, compile as K, model as M, audio
from . import color as C
from .media import ff, log, RenderError, probe

ENGINE_VERSION = "2"
FPS = M.FPS


def plan_chunks(R, target=8.0, minimum=1.5):
    """[(f0, f1)] covering the timeline; dissolve overlaps get their own window; never more than two scenes."""
    T = R["total"]; t = int(target * FPS); mn = int(minimum * FPS)
    hard = {0, T}
    for s in R["scenes"]:
        hard.add(s["start"]); hard.add(s["start"] + s["nf"])
        if s["trans"]: hard.add(s["start"] + s["trans"])
    soft = set()
    for s in R["scenes"]:
        for b in s["base"]: soft.add(s["start"] + b["f0"])
    hard = sorted(x for x in hard if 0 <= x <= T)
    out = []
    for a, b in zip(hard[:-1], hard[1:]):
        if b - a <= t: out.append((a, b)); continue
        cur = a
        while b - cur > t + mn:
            want = cur + t
            cands = [x for x in soft if cur + mn <= x <= min(b - mn, cur + t * 1.4)]
            nxt = min(cands, key=lambda x: abs(x - want)) if cands else want
            out.append((cur, nxt)); cur = nxt
        out.append((cur, b))
    return [(a, b) for a, b in out if b > a]


def encoder(R, draft=False):
    q = R["profile"]["q"]
    return ["-c:v", "hevc_videotoolbox", "-profile:v", "main10", "-q:v", str(q), "-tag:v", "hvc1", "-pix_fmt", "p010le",
            "-allow_sw", "1", *C.ENC_TAGS]


def compile_chunks(R, tl, chunks):
    jobs = []
    for f0, f1 in chunks:
        g, out = K.window(R, f0, f1, tl)
        # identical frame tags on every chunk: VideoToolbox picks its stream settings (e.g. chroma QP offsets) from them,
        # and chunks joined without re-encoding must share one set (found 2026-10-17: a red-channel shift after joining)
        script = g.script() + f";\n[{out}]format=yuv420p10le,{C.HLG_TAGS}[vout]"
        k = cache.key("chunk", ENGINE_VERSION, R["profile"], g.inputs, script)
        jobs.append(dict(f0=f0, f1=f1, inputs=g.inputs, script=script, key=k, path=cache.path("chunks", k, "mov")))
    return jobs


def build_assets():
    """Everything queued in assets.PENDING: Remotion graphics in one batch, touch-up patches in turn."""
    from . import gfx
    pend = dict(A.PENDING); A.PENDING.clear()
    rem = {p: j for p, j in pend.items() if j["kind"] == "remotion"}
    tu = {p: j for p, j in pend.items() if j["kind"] == "touchup"}
    t0 = time.time()
    if rem: gfx.render_jobs(rem)
    for p, j in tu.items():
        from . import touchup as T
        T.patch(j["src"], j["a"], j["d"], j["look"])
    return dict(graphics=len(rem), touchups=len(tu), seconds=round(time.time() - t0, 1))


def render_chunk(job, R):
    if cache.done(job["path"]): return job["path"], True
    sf = job["path"] + ".graph.txt"
    open(sf, "w").write(job["script"])
    ff([*job["inputs"], "-/filter_complex", sf, "-map", "[vout]", "-frames:v", str(job["f1"] - job["f0"]), "-an",
        *encoder(R), "-r", str(FPS), "-fps_mode", "cfr", cache.tmp(job["path"])], label=f"chunk {job['f0'] / FPS:.1f}-{job['f1'] / FPS:.1f}s", stall=180)
    os.remove(sf)
    return cache.commit(job["path"]), False


def param_sets(path):
    """Hash of the HEVC VPS/SPS/PPS a chunk was encoded with (chunks joined without re-encoding must all match)."""
    import hashlib, subprocess
    o = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:v", "-c", "copy", "-bsf:v", "hevc_mp4toannexb", "-frames:v", "1", "-f", "hevc", "-"],
                       capture_output=True).stdout
    nals = [n for n in o.split(b"\x00\x00\x01") if n]
    return hashlib.md5(b"".join(n.rstrip(b"\x00") for n in nals if ((n[0] >> 1) & 0x3F) in (32, 33, 34))).hexdigest()[:12]


def join(paths, out, R):
    """Join chunks without re-encoding when they share stream settings; otherwise re-encode once (safe fallback)."""
    lst = out + ".txt"
    open(lst, "w").write("".join(f"file '{p}'\n" for p in paths))
    sets = {param_sets(p) for p in paths}
    if len(sets) == 1:
        ff(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], label="join")
    else:
        log(f"join: chunks have {len(sets)} different stream settings -> re-encoding the join (slower, still exact)")
        ff(["-f", "concat", "-safe", "0", "-i", lst, "-vf", f"format=yuv420p10le,{C.HLG_TAGS}", *encoder(R), "-r", str(FPS), out], label="join-reencode", stall=300)
    os.remove(lst)
    return out


def render(tl, out=None, parallel=None, only=None, audio_only=False):
    """Full render. `only` = (t0, t1) seconds to render just that stretch (plus its own output file).
    Keeps the Mac awake while it runs (caffeinate), so a long render isn't paused by sleep."""
    import subprocess as _sp, sys as _sys
    awake = _sp.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())]) if _sys.platform == "darwin" and not os.environ.get("CUTROOM_NO_CAFFEINATE") else None
    try:
        return _render(tl, out, parallel, only, audio_only)
    finally:
        if awake: awake.terminate()


def _render(tl, out=None, parallel=None, only=None, audio_only=False):
    t_start = time.time()
    R = M.resolve(tl)
    name = tl.get("name", "video")
    out = out or os.path.join(tl.get("_dir", "."), f"{name}.mp4")
    chunks = plan_chunks(R)
    if only:
        a, b = int(only[0] * FPS), int(only[1] * FPS)
        chunks = [(max(a, x), min(b, y)) for x, y in chunks if y > a and x < b]
    log(f"render {name}: {R['total'] / FPS:.2f}s, {len(chunks)} chunks, profile {tl.get('profile', 'yt4k')}")
    jobs = compile_chunks(R, tl, chunks)
    t_assets = time.time(); ares = build_assets(); t_assets = time.time() - t_assets
    if A.PENDING: ares2 = build_assets()     # assets that only got named during the first build (rare)
    parallel = parallel or int(os.environ.get("STUDIO_PARALLEL", "4"))
    if R["profile"]["w"] >= 3840 and any(b.get("stage") for s_ in R["scenes"] for b in s_["base"]):
        parallel = min(parallel, 2)      # floating-window shots hold several 4K frames with alpha: fewer at once (memory)
    t_chunks = time.time(); hits = 0
    with cf.ThreadPoolExecutor(parallel) as ex:
        futs = [ex.submit(render_chunk, j, R) for j in jobs]
        for f in futs:
            p, hit = f.result(); hits += hit
    t_chunks = time.time() - t_chunks
    # join
    vid = join([j["path"] for j in jobs], out + ".video.mov", R)
    # sound
    t_audio = time.time()
    wav = out + ".audio.wav"
    if only:
        sub = dict(R); aud = audio.mix(R, wav)
        a0 = chunks[0][0] / FPS
        ff(["-i", vid, "-ss", f"{a0:.4f}", "-t", f"{(chunks[-1][1] - chunks[0][0]) / FPS:.4f}", "-i", wav, "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", cache.tmp(out)], label="mux")
    else:
        aud = audio.mix(R, wav)
        T = R["total"] / FPS
        spd = float(tl.get("speed") or 1.0)    # whole-video speed-up (e.g. a Short at 1.1x): picture re-timed, voice pitch kept
        vargs = ["-c:v", "copy"] if spd == 1.0 else ["-vf", f"setpts=PTS/{spd}", "-r", str(FPS), *encoder(R)]
        ff(["-i", vid, "-i", wav, "-map", "0:v", "-map", "1:a", *vargs,
            "-af", f"apad=whole_dur={T:.4f},atrim=0:{T:.4f}" + (f",atempo={spd}" if spd != 1.0 else ""),
            "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", cache.tmp(out)], label="mux")
    os.replace(cache.tmp(out), out)
    t_audio = time.time() - t_audio
    for f in (vid, wav):
        if os.path.exists(f): os.remove(f)
    rep = dict(output=out, seconds=round(R["total"] / FPS / (1.0 if only else float(tl.get("speed") or 1.0)), 2), chunks=len(jobs), cached_chunks=hits, rendered_chunks=len(jobs) - hits,
               assets=ares, time=dict(assets=round(t_assets, 1), chunks=round(t_chunks, 1), audio_and_mux=round(t_audio, 1),
                                      total=round(time.time() - t_start, 1)), audio=aud,
               timeline=[dict(id=s["id"], start=round(s["start"] / FPS, 3), dur=round(s["nf"] / FPS, 3)) for s in R["scenes"]])
    json.dump(rep, open(out + ".report.json", "w"), indent=1)
    log(f"done {out}: {rep['time']['total']}s total ({hits}/{len(jobs)} chunks from cache)")
    pr = cache.prune()
    if pr["removed"]: log(f"cache: removed {pr['removed']} old files ({pr['freed'] / 1024 ** 3:.1f} GB), now {pr['after'] / 1024 ** 3:.1f} GB")
    return rep


def frame(tl, t, path=None, n=1):
    """Render frame(s) at timeline time t straight from the graph (no chunk files) -> sRGB preview JPEG(s)."""
    from . import frames as F
    R = M.resolve(tl)
    f0 = min(int(round(t * FPS)), R["total"] - 1); f1 = min(R["total"], f0 + n)
    # the window must not cut a dissolve in half
    for s in R["scenes"]:
        if s["trans"] and s["start"] <= f0 < s["start"] + s["trans"]: f0, f1 = s["start"], s["start"] + s["trans"]; break
    g, out = K.window(R, f0, f1, tl)
    build_assets()
    tgt = int(round(t * FPS)) - f0
    raw = path or os.path.join(cache.CACHE if hasattr(cache, "CACHE") else os.path.expanduser("~/VideoWork"), f"frame_{t:.2f}.jpg")
    script = g.script() + f";\n[{out}]select='eq(n\\,{tgt})',scale=in_color_matrix=bt2020:in_range=tv,format=rgb48le[vout]"
    sf = raw + ".graph.txt"; open(sf, "w").write(script)
    w, h = R["profile"]["w"], R["profile"]["h"]
    import subprocess, numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *g.inputs, "-/filter_complex", sf, "-map", "[vout]", "-frames:v", "1",
                        "-f", "rawvideo", "-"], capture_output=True)
    os.remove(sf)
    if r.returncode or not r.stdout: raise RenderError("frame failed:\n" + r.stderr.decode()[-3000:])
    raw_yuv = r.stdout
    arr = np.frombuffer(raw_yuv, np.uint16).reshape(h, w, 3).astype(np.float32) / 65535
    F.preview(arr, raw, white=A.white_of(R["kit"]))
    return raw
