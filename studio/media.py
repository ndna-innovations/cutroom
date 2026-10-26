"""ffmpeg/ffprobe helpers that never hang silently.

`ff(...)` runs ffmpeg with `-progress` and a watchdog: if no new frame/progress arrives for `stall` seconds the process
is killed and the call either retries with the software encoder (for VideoToolbox encodes) or raises `RenderError`
with the command, the last progress line and the end of stderr. There is no overall timeout to guess: long renders
are fine while they move. Hardware encodes take a cross-process slot (`~/VideoWork/studio-cache/locks/vt*.lock`,
default 2 slots, `STUDIO_VT_SLOTS`) so many sessions can't pile onto the media engine at once."""
import fcntl, json, os, re, shlex, subprocess, threading, time, hashlib
from contextlib import contextmanager

from .config import path as _cfg_path
CACHE = _cfg_path("cache")
LOG = os.path.join(CACHE, "logs"); os.makedirs(LOG, exist_ok=True)
VERBOSE = bool(os.environ.get("STUDIO_VERBOSE"))


class RenderError(RuntimeError):
    pass


def log(*a):
    msg = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(msg, flush=True)
    with open(os.path.join(LOG, "studio.log"), "a") as f: f.write(msg + "\n")


@contextmanager
def vt_slot():
    """Hold one of N machine-wide VideoToolbox slots (flock on a file, released automatically if we die)."""
    n = int(os.environ.get("STUDIO_VT_SLOTS", "2"))
    d = os.path.join(CACHE, "locks"); os.makedirs(d, exist_ok=True)
    while True:
        for i in range(n):
            f = open(os.path.join(d, f"vt{i}.lock"), "w")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close(); continue
            try: yield i
            finally: fcntl.flock(f, fcntl.LOCK_UN); f.close()
            return
        time.sleep(0.5)


def _uses_vt(cmd):
    return any("videotoolbox" in str(x) for x in cmd)


def _software_fallback(cmd):
    """Swap VideoToolbox encoders for software ones (same container, same tags)."""
    out, i = [], 0
    cmd = list(map(str, cmd))
    while i < len(cmd):
        x = cmd[i]
        if x == "hevc_videotoolbox": out += ["libx265"]; out += ["-x265-params", "log-level=error"]
        elif x == "h264_videotoolbox": out += ["libx264"]
        elif x == "prores_videotoolbox": out += ["prores_ks"]
        elif x in ("-q:v",) and i + 1 < len(cmd) and _uses_vt(cmd):   # VT quality -> crf
            out += ["-crf", "16"]; i += 2; continue
        elif x in ("-allow_sw", "-realtime", "-prio_speed"):
            i += 2; continue
        else: out.append(x)
        i += 1
    return out


def ff(args, stall=90, label="", total=None, retry_sw=True, input_bytes=None):
    """Run ffmpeg. args = everything after 'ffmpeg'. Returns CompletedProcess-like (stdout bytes only when piping)."""
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-v", "error", "-progress", "pipe:2", "-stats_period", "2"] + list(map(str, args))
    if VERBOSE: log("$", " ".join(shlex.quote(c) for c in cmd)[:3000])
    vt = _uses_vt(cmd)
    ctx = vt_slot() if vt else _null()
    with ctx:
        ok, err, prog = _watch(cmd, stall, label, total)
    if ok: return True
    graph_err = any(x in err for x in ("Error binding filtergraph", "Invalid argument", "No such filter", "Error parsing", "unconnected", "Error opening input"))
    if vt and retry_sw and not graph_err:
        log(f"[{label}] hardware encode failed/stalled -> software encoder", prog)
        ok, err, prog = _watch(_software_fallback(cmd), stall * 2, label, total)
        if ok: return True
    if not err.strip():   # say why: re-run briefly with warnings on (the quiet log level hides filter errors)
        try:
            d = subprocess.run([c if c != "error" else "warning" for c in cmd[:cmd.index("-progress")] + cmd[cmd.index("-stats_period") + 2:]][:-1] + ["-frames:v", "1", "-f", "null", "-"],
                               capture_output=True, text=True, timeout=120).stderr
            err = "\n".join(l for l in d.splitlines() if "deprecated" not in l)[-3000:]
        except Exception: pass
    raise RenderError(f"ffmpeg failed [{label}]\nlast progress: {prog}\ncmd: {' '.join(shlex.quote(c) for c in cmd)[:4000]}\nstderr:\n{err[-4000:]}")


@contextmanager
def _null():
    yield None


def _watch(cmd, stall, label, total):
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1)
    last = [time.time()]; tail = []; prog = {}
    def reader():
        for line in p.stderr:
            line = line.rstrip()
            m = re.match(r"(\w+)=(.*)", line)
            if m and m.group(1) in ("frame", "out_time", "progress", "speed", "fps", "total_size", "out_time_us"):
                if m.group(1) in ("out_time_us", "frame", "total_size") and prog.get(m.group(1)) != m.group(2): last[0] = time.time()
                prog[m.group(1)] = m.group(2)
            else:
                tail.append(line); del tail[:-80]; last[0] = time.time()
    th = threading.Thread(target=reader, daemon=True); th.start()
    t0 = time.time(); shown = 0; tick = time.time()
    while p.poll() is None:
        time.sleep(0.5)
        now = time.time()
        if now - tick > 10: last[0] = now            # the Mac was asleep: that pause is not a stall
        tick = now
        if time.time() - last[0] > stall:
            p.kill(); p.wait(); th.join(2)
            log(f"[{label}] STALLED for {stall}s (no progress) at {prog.get('out_time')} - killed")
            return False, "\n".join(tail) + f"\nSTALLED {stall}s", dict(prog)
        if label and time.time() - shown > 30:
            shown = time.time(); log(f"[{label}] {prog.get('out_time', '?')} speed={prog.get('speed', '?')} ({time.time() - t0:.0f}s)")
    th.join(5)
    return p.returncode == 0, "\n".join(tail), dict(prog)


def run(cmd, check=True, **kw):
    r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, **kw)
    if check and r.returncode: raise RenderError(f"failed: {' '.join(map(str, cmd))[:2000]}\n{r.stderr[-3000:]}")
    return r


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path])
    return json.loads(r.stdout)


def duration(path):
    return float(probe(path)["format"]["duration"])


def vstream(path):
    return next(s for s in probe(path)["streams"] if s["codec_type"] == "video")


def is_complete(path):
    """A finished media file (a killed render leaves a file without an index)."""
    if not (os.path.exists(path) and os.path.getsize(path) > 0): return False
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() not in ("", "N/A")


def fingerprint(path):
    """Cheap content identity for cache keys: size + mtime + hash of the first/last 1 MB."""
    st = os.stat(path); h = hashlib.sha1(f"{st.st_size}:{int(st.st_mtime)}".encode())
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
        if st.st_size > 2 << 20: f.seek(-(1 << 20), 2); h.update(f.read(1 << 20))
    return h.hexdigest()[:16]


def frames(t, fps=30):
    return int(round(t * fps))


def snap(t, fps=30):
    return round(t * fps) / fps
