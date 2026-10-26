"""Content-hash cache. Every render step is keyed by (step name, version, resolved inputs, file fingerprints);
the output lives at ~/VideoWork/studio-cache/<step>/<key>.<ext>. Change one overlay -> only its segment re-renders.
Write to a temp name, rename when complete: a killed render never looks finished.
Size limit: after every render, prune() removes the least recently used files until the cache is under its limit
(config "cache_limit_gb", default 80 GB), e.g. old graphics versions no timeline asks for any more."""
import hashlib, json, os, time
from .media import CACHE, fingerprint, is_complete, log


def _norm(x):
    if isinstance(x, dict): return {k: _norm(v) for k, v in sorted(x.items())}
    if isinstance(x, (list, tuple)): return [_norm(v) for v in x]
    if isinstance(x, float): return round(x, 4)
    if isinstance(x, str) and os.path.isabs(x):
        if x.startswith(CACHE): return x                 # cache files are named by their content hash already
        if os.path.isfile(x): return {"file": x, "fp": fingerprint(x)}
    elif isinstance(x, str) and "/" not in x[:1] and os.path.isfile(x):   # a relative path: same file, same fingerprint (a replaced file never reuses old results)
        a = os.path.abspath(x); return {"file": a, "fp": fingerprint(a)}
    return x


def key(*parts):
    return hashlib.sha1(json.dumps(_norm(parts), sort_keys=True, default=str).encode()).hexdigest()[:14]


def path(step, k, ext):
    d = os.path.join(CACHE, step); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{k}.{ext}")
    try: os.utime(p, (time.time(), os.stat(p).st_mtime))     # mark as used (access time; the file itself is unchanged)
    except OSError: pass
    return p


def limit_bytes():
    from .config import load
    return int(float(load().get("cache_limit_gb", 80)) * 1024 ** 3)


def prune(limit=None, keep_hours=24.0, dry=False):
    """Bring the cache under `limit` bytes (default: limit_bytes()): least recently used files go first; nothing used in
    the last `keep_hours` is removed (a render in progress keeps its files). Leftover .part files older than a day go
    too. Returns dict(before, after, removed, freed) in bytes / files."""
    limit = limit_bytes() if limit is None else limit
    now, files = time.time(), []
    for root, dirs, names in os.walk(CACHE):
        if os.path.relpath(root, CACHE).split(os.sep)[0] == "locks": continue
        for n in names:
            f = os.path.join(root, n)
            try: st = os.stat(f)
            except OSError: continue
            files.append((max(st.st_atime, st.st_mtime), st.st_size, f, ".part" in n))
    before = total = sum(x[1] for x in files); removed = 0
    files.sort()
    for used, size, f, part in files:
        old = now - used > keep_hours * 3600
        if not old: break
        if total <= limit and not (part and now - used > 86400): continue
        if not dry:
            try: os.remove(f)
            except OSError: continue
        total -= size; removed += 1
    if total > limit: log(f"cache: {total / 1024 ** 3:.1f} GB is over the {limit / 1024 ** 3:.0f} GB limit, but all of it was used in the last {keep_hours:g} h")
    return dict(before=before, after=total, removed=removed, freed=before - total)


def tmp(p):
    base, ext = os.path.splitext(p)
    return f"{base}.part{ext}"


def done(p, media=True):
    if not os.path.exists(p): return False
    return is_complete(p) if media else os.path.getsize(p) > 0


def commit(p):
    os.replace(tmp(p), p); return p
