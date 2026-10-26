"""Auto screen take: runs a screen recording with nobody at the Mac. The creator starts it (a launcher in Terminal);
it opens fresh windows (a Claude session, a browser on Gemini, …), records one window or the whole screen, types
each prompt at a human pace, waits until the apps have finished, and logs every step's time so the edit can cut
the waits. It follows the take file exactly; anything unexpected stops it safely.

    cutroom autotake TAKE.json [--dry] [--out DIR]

Take file (JSON):
{
  "name": "argon-vs-claude",
  "windows": [                                   # opened in this order; the first is the default for steps
    {"name": "claude", "app": "Claude", "new_window": ["File", "New Session in New Window"], "folder": "~/Demo/fresh-1",
     "place": "left"},                           # fill | left | right | keep
    {"name": "gemini", "app": "Google Chrome", "new_window": ["File", "New Window"], "url": "https://gemini.google.com",
     "place": "right", "focus_text": "Ask Gemini"}   # focus_text: clicked before each prompt (a web page's text box);
                                                 # focus_at: [x, y] window fractions instead (boxes with changing hint
                                                 # text); ignore: [[x0, y0, x1, y1], …] areas that never count as "busy"
                                                 # After typing, the prompt must be readable on screen or the run stops
                                                 # ("check": false on a step turns that off)
  ],                                             # folder paths may contain {stamp} (date-time) for a new folder each run
  "record": {"mode": "screen", "audio": false},  # mode: window (records "win", default the first) | screen (whole display,
                                                 #   Terminal left out) | manual (a {"do": "record"} step starts it)
                                                 # default: window for one window, screen for several
  "busy_words": ["Thinking", "Working", "Running", "Stop"],   # OCR words that mean "not done yet"
  "ask_words": ["Allow", "Deny", "Approve"],                   # OCR words that mean "the app is asking"
  "steps": [
    {"id": "1", "do": "prompt_all", "wins": ["claude", "gemini"], "text": "…", "paste": true},  # same prompt to both,
                                                 #   sent back to back, then waits until BOTH are done (fair comparisons)
    {"id": "2", "do": "prompt", "win": "claude", "text": "…", "quiet": 8, "max": 900},  # type + Enter + wait
    {"id": "3", "do": "type", "text": "…", "enter": false},
    {"id": "4", "do": "keys", "keys": "cmd+shift+g"},
    {"id": "5", "do": "menu", "path": ["View", "Show Browser"]},
    {"id": "6", "do": "open_url", "win": "gemini", "url": "https://…"},
    {"id": "7", "do": "open_folder", "win": "claude", "path": "~/Demo/fresh-2"},
    {"id": "8", "do": "click_text", "text": "Allow once", "optional": true},
    {"id": "8b", "do": "click_at", "at": [0.5, 0.4]},             # a spot on a canvas: fractions of the window (x, y)
    {"id": "8c", "do": "scroll", "at": [0.5, 0.5], "lines": -8},  # negative = down
    {"id": "8d", "do": "drag", "from": [0.3, 0.5], "to": [0.6, 0.5], "secs": 0.8},   # a point may also be {"text": "Logo"}
    {"id": "9", "do": "wait", "wins": ["claude", "gemini"], "quiet": 6, "max": 120, "until_text": "Done"},
    {"id": "10", "do": "pause", "secs": 2},
    {"id": "11", "do": "snap"}
  ]
}
Old single-window files still work: top-level "app", "new_window", "fill" (true = place fill) and "record":
"after_window" | "manual". A folder must be empty unless the window/step says "allow_nonempty": true (a fresh
folder means the session cannot read old notes). Sign-ins are never typed: be signed in before the run.
A prompt/wait step may set "approve": true to click Allow when the app asks; otherwise an ask stops the run safely
("needs_you" in the log). Before typing, the target window must be in front (it is raised; if that fails the run
stops instead of typing anywhere else). Ctrl-C (or closing Terminal) stops the recording cleanly and keeps the log.
Output folder: take.mov (the recording; app sound when "audio"), log.json (steps with times in seconds on the
recording's clock, window rects for cropping a screen recording), snaps/, run.txt."""
import json, os, signal, subprocess, time

from . import typer

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "bin", "studio-autotake")
SRC = os.path.join(HERE, "native", "autotake.swift")
DEFAULT_BUSY = ["Thinking", "Working", "Running", "Generating", "Stop"]
DEFAULT_ASK = ["Allow", "Deny", "Approve"]
KEYCODES = {"enter": 36, "return": 36, "tab": 48, "space": 49, "delete": 51, "escape": 53, "esc": 53,
            "left": 123, "right": 124, "down": 125, "up": 126}
MODS = {"cmd": "command down", "command": "command down", "shift": "shift down", "alt": "option down",
        "option": "option down", "ctrl": "control down", "control": "control down"}
VALID = {"prompt", "prompt_all", "type", "keys", "menu", "click_text", "click_at", "scroll", "drag", "wait", "pause", "snap",
         "record", "open_url", "open_folder"}
POINT_KEYS = {"click_at": ["at"], "scroll": ["at"], "drag": ["from", "to"]}
PLACES = {"fill", "left", "right", "keep"}


def ensure_bin():
    if not os.path.exists(BIN) or os.path.getmtime(BIN) < os.path.getmtime(SRC):
        subprocess.run(["swiftc", "-O", SRC, "-o", BIN], check=True)
    return BIN


# ---------- take file ----------
def load(path):
    take = json.load(open(os.path.expanduser(path)))
    problems = validate(take)
    if problems: raise ValueError("take file problems:\n- " + "\n- ".join(problems))
    return take


def window_specs(take):
    """The take's windows, upgrading the old single-window keys."""
    if take.get("windows"): return take["windows"]
    return [{"name": "main", "app": take.get("app", "Claude"),
             "new_window": take.get("new_window", ["File", "New Session in New Window"]),
             "place": "fill" if take.get("fill", True) else "keep", "folder": take.get("folder")}]


def record_spec(take):
    r = take.get("record", "after_window")
    if isinstance(r, str): r = {"mode": "manual" if r == "manual" else None}
    r = dict(r)
    if not r.get("mode"): r["mode"] = "window" if len(window_specs(take)) == 1 else "screen"
    return r


def valid_point(p):
    if isinstance(p, dict): return bool(p.get("text"))
    return isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in p)


def frac_point(win, at):
    """Window fractions -> global screen points."""
    return (win["x"] + at[0] * win["w"], win["y"] + at[1] * win["h"])


def validate(take):
    out = []
    if not take.get("steps"): out.append("no steps")
    wins = window_specs(take)
    names = [w.get("name") for w in wins]
    if len(set(names)) != len(names) or None in names: out.append("every window needs a unique name")
    for w in wins:
        if w.get("place", "fill") not in PLACES: out.append(f"window {w.get('name')}: place must be one of {sorted(PLACES)}")
    rec = record_spec(take)
    if rec["mode"] not in ("window", "screen", "manual"): out.append(f"record mode {rec['mode']!r}: use window, screen or manual")
    if rec.get("win") and rec["win"] not in names: out.append(f"record win {rec['win']!r} is not a window")
    seen = set()
    for i, s in enumerate(take.get("steps", [])):
        sid = s.get("id", f"#{i + 1}")
        if sid in seen: out.append(f"{sid}: duplicate id")
        seen.add(sid)
        do = s.get("do")
        if do not in VALID: out.append(f"{sid}: unknown do={do!r} (use {sorted(VALID)})")
        if do in ("prompt", "prompt_all", "type") and not s.get("text"): out.append(f"{sid}: needs text")
        if do == "menu" and not s.get("path"): out.append(f"{sid}: needs path")
        if do == "keys" and not s.get("keys"): out.append(f"{sid}: needs keys")
        if do == "click_text" and not s.get("text"): out.append(f"{sid}: needs text")
        if do == "open_url" and not s.get("url"): out.append(f"{sid}: needs url")
        if do == "open_folder" and not s.get("path"): out.append(f"{sid}: needs path")
        for key in POINT_KEYS.get(do, []):
            if not valid_point(s.get(key)): out.append(f'{sid}: {key} must be [x, y] fractions 0–1 of the window or {{"text": …}}')
        if do == "scroll" and not isinstance(s.get("lines"), int): out.append(f"{sid}: scroll needs whole-number lines")
        if do == "record" and rec["mode"] != "manual": out.append(f"{sid}: record step needs \"record\": \"manual\"")
        for n in ([s["win"]] if s.get("win") else []) + s.get("wins", []):
            if n not in names: out.append(f"{sid}: unknown window {n!r}")
        if do == "prompt_all" and len(s.get("wins", [])) < 2: out.append(f"{sid}: prompt_all needs 2+ wins")
    return out


# ---------- the Mac ----------
def osa(script):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode: raise RuntimeError(f"AppleScript failed (Terminal needs Accessibility permission?): {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def windows():
    return json.loads(subprocess.run([ensure_bin(), "windows"], capture_output=True, text=True, check=True).stdout)


def screen():
    return json.loads(subprocess.run([ensure_bin(), "screen"], capture_output=True, text=True, check=True).stdout)


def app_windows(app):
    return [w for w in windows() if w["owner"] == app and w["h"] > 200]


def activate(app):
    osa(f'tell application "{app}" to activate'); time.sleep(0.4)


def menu(app, path):
    if len(path) < 2: raise ValueError(f"menu path needs at least 2 items: {path}")
    ref = f'menu bar item "{path[0]}" of menu bar 1'
    for item in path[1:]:
        ref = f'menu item "{item}" of menu 1 of {ref}'
    osa(f'tell application "System Events" to tell process "{app}" to click {ref}')


def keys_script(combo):
    parts = [p.strip().lower() for p in combo.split("+")]
    key, mods = parts[-1], [MODS[p] for p in parts[:-1]]
    using = f" using {{{', '.join(mods)}}}" if mods else ""
    if key in KEYCODES: return f'tell application "System Events" to key code {KEYCODES[key]}{using}'
    return f'tell application "System Events" to keystroke "{key}"{using}'


def press(combo):
    osa(keys_script(combo))


def paste_text(text):
    subprocess.run(["pbcopy"], input=text, text=True, check=True)
    press("cmd+v")


def place_rect(place, scr):
    """Window rect in points for a placement on the visible screen."""
    x, y, w, h = scr["x"], scr["y"], scr["w"], scr["h"]
    if place == "left": return (x, y, w // 2, h)
    if place == "right": return (x + w // 2, y, w - w // 2, h)
    return (x, y, w, h)


def set_front_window_rect(app, rect):
    x, y, w, h = (int(v) for v in rect)
    osa(f'tell application "System Events" to tell process "{app}" to tell window 1\n'
        f'set position to {{{x}, {y}}}\nset size to {{{w}, {h}}}\nend tell')


def fresh_folder(path, allow_nonempty=False):
    """Make/check the session folder. "{stamp}" in the path becomes the date and time, so every run gets a new one."""
    p = os.path.expanduser(path.replace("{stamp}", time.strftime("%Y%m%d-%H%M%S")))
    os.makedirs(p, exist_ok=True)
    left = [f for f in os.listdir(p) if not f.startswith(".")]
    if left and not allow_nonempty:
        raise RuntimeError(f"folder {p} is not empty ({len(left)} items): use a fresh folder, or set allow_nonempty")
    return p


def snap(win_id, path):
    r = subprocess.run(["screencapture", "-x", "-o", f"-l{win_id}", "-t", "png", path], capture_output=True)
    return r.returncode == 0 and os.path.exists(path)


def ocr(png):
    from .ocr import ensure_bin as vision
    r = subprocess.run([vision(), "ocr", png], capture_output=True, text=True)
    if r.returncode: return []
    return json.loads(r.stdout.strip().splitlines()[-1])["lines"]


def changed_cells(a, b, thresh=14):
    """How many 8x8 blocks differ between two stills (ignores a blinking caret, sees text streaming in).
    A window that was moved or resized is compared at the same size, not counted as a full change."""
    import numpy as np
    if a is None or b is None: return 10 ** 6
    if a.shape != b.shape:
        from PIL import Image
        b = np.asarray(Image.fromarray(b).resize((a.shape[1], a.shape[0])))
    return int((np.abs(a.astype(np.int16) - b.astype(np.int16)) > thresh).sum())


def is_busy_change(n, cells):
    """Real activity (text streaming, a new panel) vs idle animations: the Claude window's idle mascot/ring
    flips ~6 cells every few seconds (measured 18 Oct); streaming text changes thousands."""
    return n > max(40, cells // 1000)


def frontmost(wins):
    """The front real window (CGWindowList lists on-screen windows front to back). Thin strips are skipped: the Claude
    app keeps a 32-pt-high bar window above its main window (found on practice run 2, 18 Oct)."""
    return next((w for w in wins if w["h"] > 200 and w["w"] > 200), None)


def small_gray(png, ignore=()):
    """1/8-size grey still; `ignore` = [[x0, y0, x1, y1], …] window fractions blanked out (moving hint text, ads,
    animations that should not count as the app working)."""
    import numpy as np
    from PIL import Image
    im = Image.open(png).convert("L")
    a = np.array(im.resize((max(1, im.width // 8), max(1, im.height // 8))))
    H, W = a.shape
    for x0, y0, x1, y1 in ignore:
        a[int(y0 * H):int(y1 * H) + 1, int(x0 * W):int(x1 * W) + 1] = 0
    return a


def _words(t):
    import re
    return re.findall(r"[a-z0-9]+", t.lower())


def text_landed(text, lines, n=3):
    """Did the typed prompt reach the screen? True if its first or last few words show up in the OCR lines
    (a long prompt may scroll inside its box, so either end counts)."""
    w, seen = _words(text), " ".join(_words(" ".join(l[4] for l in lines)))
    if not w: return True
    n = min(n, len(w))
    return " ".join(w[:n]) in seen or " ".join(w[-n:]) in seen


def has_word(lines, words):
    txt = " ".join(l[4] for l in lines).lower()
    return next((w for w in words if w.lower() in txt), None)


# ---------- the run ----------
class Run:
    def __init__(self, take, out, dry=False):
        self.take, self.out, self.dry = take, out, dry
        self.specs = {w["name"]: w for w in window_specs(take)}
        self.order = [w["name"] for w in window_specs(take)]
        self.recspec = record_spec(take)
        self.events, self.rec, self.first_frame = [], None, None
        self.wins = {}                      # name -> live window {id, owner, x, y, w, h}
        self.busy = take.get("busy_words", DEFAULT_BUSY)
        self.ask = take.get("ask_words", DEFAULT_ASK)
        os.makedirs(os.path.join(out, "snaps"), exist_ok=True)
        self.last_still = 0.0
        self.notes = []

    # the first window, kept as .win for single-window callers
    @property
    def win(self): return self.wins.get(self.order[0])

    @win.setter
    def win(self, w): self.wins[self.order[0]] = w

    def t(self):
        return round(time.time() - self.first_frame, 3) if self.first_frame else None

    def say(self, msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True); self.notes.append(line)

    def app(self, name): return self.specs[name]["app"]

    # recording
    def start_recording(self):
        if self.dry or self.rec: return
        path = os.path.join(self.out, "take.mov")
        cmd = [ensure_bin(), "record", "--out", path]
        if self.recspec["mode"] == "screen":
            cmd += ["--display", "--exclude", ",".join(self.recspec.get("exclude", ["Terminal"]))]
        else:
            cmd += ["--window", str(self.wins[self.recspec.get("win", self.order[0])]["id"])]
        if self.recspec.get("audio"): cmd.append("--audio")
        self.rec = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        line = self.rec.stdout.readline().strip()
        if not line.startswith("first_frame"):
            err = self.rec.stderr.read()[:400]
            raise RuntimeError(f"recording did not start (Terminal needs Screen Recording permission?): {line} {err}")
        self.first_frame = float(line.split()[1])
        self.say(f"recording {self.recspec['mode']}{' + sound' if self.recspec.get('audio') else ''} -> {path}")

    def stop_recording(self):
        if not self.rec: return
        self.rec.send_signal(signal.SIGINT)
        try: out, _ = self.rec.communicate(timeout=20)
        except subprocess.TimeoutExpired: self.rec.kill(); out = "killed"
        self.say(f"recording stopped ({out.strip()})"); self.rec = None

    # windows
    def refresh(self, name):
        w = self.wins[name]
        self.wins[name] = next((x for x in windows() if x["id"] == w["id"]), w)
        return self.wins[name]

    def open_window(self, name):
        spec, app = self.specs[name], self.app(name)
        if self.dry: self.wins[name] = {"id": len(self.wins), "owner": app, "x": 0, "y": 0, "w": 1728, "h": 1084}; return
        activate(app)
        before = {w["id"] for w in app_windows(app)}
        how = spec.get("new_window")
        if how:
            if isinstance(how, list): menu(app, how)
            else: press(how)
            for _ in range(40):
                time.sleep(0.25)
                new = [w for w in app_windows(app) if w["id"] not in before]
                if new: self.wins[name] = new[0]; break
            if name not in self.wins: raise RuntimeError(f"no new {app} window appeared after {how}")
        else:
            ws = app_windows(app)
            if not ws: raise RuntimeError(f"{app} has no open window")
            self.wins[name] = ws[0]
        place = spec.get("place", "fill")
        if place != "keep":
            try:
                if place == "fill" and app == "Claude": menu(app, ["Window", "Fill"])
                else: set_front_window_rect(app, place_rect(place, screen()))
                time.sleep(0.8)
            except RuntimeError as e: self.say(f"could not place {name}: {e}")
            self.refresh(name)
        w = self.wins[name]
        self.say(f"window {name} ({app}) id {w['id']} at {w['x']},{w['y']} {w['w']}x{w['h']}")
        if spec.get("folder"): self.open_folder(name, spec["folder"], spec.get("allow_nonempty", False))
        if spec.get("url"): self.open_url(name, spec["url"])

    def open_url(self, name, url):
        if not self.ensure_front(name): raise RuntimeError(f"window {name} not in front")
        press("cmd+l"); time.sleep(0.3)
        typer.type_text(url, cps=40, countdown=0)
        press("enter"); time.sleep(2)
        self.say(f"{name}: opened {url}")

    def open_folder(self, name, path, allow_nonempty=False):
        """A Claude session working in a fresh folder: File > Open Folder…, Go to Folder, the path, open."""
        p = fresh_folder(path, allow_nonempty)
        if not self.ensure_front(name): raise RuntimeError(f"window {name} not in front")
        menu(self.app(name), ["File", "Open Folder…"]); time.sleep(1.2)
        press("cmd+shift+g"); time.sleep(0.8)
        typer.type_text(p, cps=60, countdown=0); time.sleep(0.4)
        press("enter"); time.sleep(1.0)
        press("enter"); time.sleep(2.0)
        self.refresh(name)
        self.still(f"folder-{name}")
        self.say(f"{name}: folder {p}")

    def is_front(self, name):
        f = frontmost(windows())
        return bool(f) and f["id"] == self.wins[name]["id"]

    def ensure_front(self, name):
        """Never type into the wrong window: bring this window to the front (raising each of the app's windows in turn
        until the front one is ours), or report False so the run stops."""
        if self.is_front(name): return True
        app = self.app(name)
        activate(app)
        if self.is_front(name): return True
        n = int(osa(f'tell application "System Events" to tell process "{app}" to count windows') or 0)
        for i in range(1, n + 1):
            try:
                osa(f'tell application "System Events" to tell process "{app}" to perform action "AXRaise" of window {i}')
            except RuntimeError: continue
            time.sleep(0.3)
            if self.is_front(name): self.say(f"brought {name} back to the front"); return True
        return False

    def still(self, tag, name=None):
        name = name or self.order[0]
        p = os.path.join(self.out, "snaps", f"{tag}.png")
        return p if (not self.dry and snap(self.wins[name]["id"], p)) else None

    def point(self, name, at):
        """A step's spot as global points: [x, y] window fractions, or {"text": "…"} found by reading the window."""
        win = self.refresh(name)
        if isinstance(at, dict):
            p = self.still("_point", name)
            L = [l for l in ocr(p) if at["text"].lower() in l[4].lower()] if p else []
            if len(L) < at.get("nth", 1): return None
            x, y, w, h = L[at.get("nth", 1) - 1][:4]
            from PIL import Image
            scale = Image.open(p).width / win["w"]
            return (win["x"] + (x + w / 2) / scale, win["y"] + (y + h / 2) / scale)
        return frac_point(win, at)

    def mouse(self, *args):
        subprocess.run([ensure_bin(), *[str(round(a, 1)) if isinstance(a, float) else str(a) for a in args]], check=True)

    def click_text(self, text, nth=1, name=None):
        name = name or self.order[0]
        p = self.still("_click", name)
        if not p: return False
        L = [l for l in ocr(p) if text.lower() in l[4].lower()]
        if len(L) < nth: return False
        x, y, w, h = L[nth - 1][:4]
        from PIL import Image
        win = self.refresh(name)
        scale = Image.open(p).width / win["w"]   # still px per point
        subprocess.run([ensure_bin(), "click", str(win["x"] + (x + w / 2) / scale), str(win["y"] + (y + h / 2) / scale)], check=True)
        return True

    def wait_done(self, s, names=None):
        """Until every window has not changed for `quiet` s (and shows no busy word), `until_text` appears in one,
        or `max` s pass. An app asking (Allow/Deny) stops the run unless the step says approve."""
        names = names or [s.get("win") or self.order[0]]
        quiet, mx, mn = s.get("quiet", 8), s.get("max", 900), s.get("min", 3)
        until = s.get("until_text")
        if self.dry: return "done(dry)"
        t0, n = time.time(), 0
        prev = {k: None for k in names}; since = {k: time.time() for k in names}; done = set()
        while True:
            el = time.time() - t0
            if el > mx: return "timeout" + (f"({', '.join(sorted(set(names) - done))})" if len(names) > 1 else "")
            n += 1
            for k in names:
                if k in done: continue
                tmp = os.path.join(self.out, "snaps", f"_wait-{k}.png")
                if not snap(self.wins[k]["id"], tmp): continue
                cur = small_gray(tmp, self.specs[k].get("ignore", ()))
                if is_busy_change(changed_cells(prev[k], cur), cur.size): since[k] = time.time()
                prev[k] = cur
                if time.time() - self.last_still >= 5:
                    import shutil
                    shutil.copy(tmp, os.path.join(self.out, "snaps", f"{self.t() or 0:08.1f}-{k}.png")); self.last_still = time.time()
                calm = el >= mn and time.time() - since[k] >= quiet
                if not (until or calm or n % 10 == 0): continue
                L = ocr(tmp)
                if until and has_word(L, [until]): return f"done(text in {k})"
                asked = has_word(L, self.ask)
                if asked:
                    if s.get("approve") and self.click_text(s.get("approve_text", "Allow"), name=k):
                        self.say(f"approved in {k} ({asked})"); since[k] = time.time(); continue
                    return f"needs_you({k} asks: {asked})"
                if not until and calm:
                    if has_word(L, self.busy): since[k] = time.time() - quiet / 2; continue
                    done.add(k)
            if not until and done >= set(names): return "done"
            time.sleep(1)

    def send_prompt(self, name, s, ev):
        """Click into the text box, type (or paste) the prompt, check it really landed, send it.
        Returns "ok", or a needs_you(...) status (window not in front / text not on screen)."""
        if not self.ensure_front(name): return f"needs_you({name} not in front: someone clicked another window)"
        spec = self.specs[name]
        f_at, f_text = s.get("focus_at", spec.get("focus_at")), s.get("focus_text", spec.get("focus_text"))   # step wins
        if f_at: self.mouse("click", *frac_point(self.refresh(name), f_at))   # a box with changing hint text
        elif f_text and not self.click_text(f_text, name=name):               # e.g. "Ask Gemini"
            self.say(f"{name}: '{f_text}' not seen, typing where the cursor is")
        time.sleep(0.3)
        if s.get("paste"): paste_text(s["text"])
        else: ev[f"typed_secs_{name}"] = typer.type_text(s["text"], cps=s.get("cps", 22.0), fast=s.get("fast", 1.0), countdown=0)
        time.sleep(0.4)
        if s.get("check", True) and not self.dry:
            p = self.still(f"_typed-{name}", name)
            if p and not text_landed(s["text"], ocr(p)):
                return f"needs_you(the prompt did not appear in {name}: the text box was not focused)"
        time.sleep(s.get("before_send", 0.6)); press("enter")
        ev[f"sent_{name}"] = self.t()
        return "ok"

    def step(self, s):
        do, sid = s["do"], s.get("id", "?")
        name = s.get("win") or self.order[0]
        ev = {"id": sid, "do": do, "win": s.get("wins") or name, "start": self.t()}
        status = "ok"
        blocked = "needs_you({} not in front: someone clicked another window)"
        if self.dry:
            self.say(f"(dry) {sid} {do} {s.get('text', s.get('path', s.get('keys', s.get('url', ''))))!s:.60}")
        elif do == "prompt_all":
            for k in s["wins"]:
                status = self.send_prompt(k, s, ev)
                if status != "ok": break
            else: status = self.wait_done(s, s["wins"])
        elif do in ("prompt", "type", "keys", "menu", *POINT_KEYS) and not self.ensure_front(name):
            status = blocked.format(name)
        elif do == "prompt":
            status = self.send_prompt(name, s, ev)
            if status == "ok": status = self.wait_done(s, [name])
        elif do == "type":
            if s.get("paste"): paste_text(s["text"])
            else: ev["typed_secs"] = typer.type_text(s["text"], cps=s.get("cps", 22.0), fast=s.get("fast", 1.0), countdown=0)
            if s.get("enter"): time.sleep(s.get("before_send", 0.6)); press("enter"); ev["sent"] = self.t()
        elif do == "keys": press(s["keys"])
        elif do == "menu": menu(self.app(name), s["path"])
        elif do == "open_url": self.open_url(name, s["url"])
        elif do == "open_folder": self.open_folder(name, s["path"], s.get("allow_nonempty", False))
        elif do == "click_text":
            ok = self.click_text(s["text"], s.get("nth", 1), name)
            status = "ok" if ok else ("skipped" if s.get("optional") else "not_found")
        elif do in POINT_KEYS:
            pts = [self.point(name, s[k]) for k in POINT_KEYS[do]]
            if None in pts: status = "skipped" if s.get("optional") else "not_found"
            elif do == "click_at": self.mouse("click", *pts[0])
            elif do == "scroll": self.mouse("scroll", *pts[0], s["lines"])
            else: self.mouse("drag", *pts[0], *pts[1], float(s.get("secs", 0.6)))
        elif do == "wait": status = self.wait_done(s, s.get("wins") or [name])
        elif do == "pause": time.sleep(s.get("secs", 1))
        elif do == "snap": ev["file"] = self.still(f"step-{sid}", name)
        elif do == "record": self.start_recording()
        ev.update(end=self.t(), status=status)
        self.events.append(ev)
        self.say(f"{sid} {do}: {status}")
        return status

    def save(self, result):
        log = {"take": self.take.get("name"), "result": result,
               "video": os.path.join(self.out, "take.mov") if self.first_frame else None,
               "record": self.recspec, "first_frame_unix": self.first_frame,
               "window": self.win, "windows": self.wins, "events": self.events}
        if self.recspec["mode"] == "screen" and not self.dry:
            try: log["screen"] = screen()
            except Exception: pass
        json.dump(log, open(os.path.join(self.out, "log.json"), "w"), indent=1)
        open(os.path.join(self.out, "run.txt"), "w").write("\n".join(self.notes) + "\n")

    def go(self):
        result = "finished"
        try:
            for name in self.order: self.open_window(name)
            if self.recspec["mode"] != "manual": self.start_recording()
            for s in self.take["steps"]:
                st = self.step(s)
                if st.startswith(("timeout", "not_found", "needs_you")):
                    result = f"stopped at {s.get('id')}: {st}"; self.say(result); break
                time.sleep(s.get("after", self.take.get("gap", 1.0)))
            time.sleep(self.take.get("tail", 3))
        except KeyboardInterrupt:
            result = "stopped by Ctrl-C"; self.say(result)
        except Exception as e:
            result = f"error: {e}"; self.say(result)
        finally:
            self.stop_recording()
            self.save(result)
        return result


def run(take_path, out=None, dry=False):
    take = load(take_path)
    out = os.path.expanduser(out or os.path.join("~/VideoWork/autotake", f"{take.get('name', 'take')}-{time.strftime('%Y%m%d-%H%M')}"))
    print(f"Auto take '{take.get('name')}': {len(take['steps'])} steps, {len(window_specs(take))} window(s) -> {out}")
    if not dry:
        for k in range(take.get("countdown", 10), 0, -1):
            print(f"  starting in {k}… hands off the keyboard and mouse (Ctrl-C to cancel)", end="\r", flush=True); time.sleep(1)
        print()

    def hangup(*_): raise KeyboardInterrupt   # Terminal window closed: still stop the recording cleanly and save the log
    signal.signal(signal.SIGHUP, hangup)
    r = Run(take, out, dry).go()
    print(f"\nResult: {r}\nFolder: {out}")
    return r, out
