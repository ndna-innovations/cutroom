"""Auto-typer for recordings: really types a prompt into the focused app at a human pace while the screen records,
so the footage shows typing instead of a paste. macOS only (System Events; the app running it needs Accessibility
permission the first time: System Settings > Privacy & Security > Accessibility).

    cutroom type "Your prompt" [--cps 22] [--countdown 3] [--newline shift|enter|space] [--app "Claude"]
    cutroom type --file prompt.txt

Timing feels human: a little random per key, a short pause after spaces, a longer one after . , ! ?
Long prompts can type their middle faster (--fast 3) so viewers see the start and the end typed."""
import random, subprocess, sys, time

PUNCT_PAUSE = {".": 0.18, ",": 0.08, "!": 0.18, "?": 0.18, ":": 0.1, ";": 0.1, "\n": 0.25}


def plan(text, cps=22.0, jitter=0.35, fast=1.0, seed=1):
    """[(chunk, delay_after)] — keystrokes with human timing (deterministic for a seed)."""
    rnd = random.Random(seed); out = []
    n = len(text); edge = min(60, n / 3)
    for i, ch in enumerate(text):
        speed = cps * (fast if edge <= i < n - edge else 1.0)
        d = (1.0 / speed) * (1 + rnd.uniform(-jitter, jitter))
        if ch == " ": d += 0.03
        d += PUNCT_PAUSE.get(ch, 0.0)
        out.append((ch, round(max(0.008, d), 4)))
    return out


def _esc(ch):
    return ch.replace("\\", "\\\\").replace('"', '\\"')


def applescript(text, cps=22.0, jitter=0.35, fast=1.0, newline="shift", seed=1):
    """One AppleScript that types the whole text with its delays (one process: no per-key start-up lag)."""
    lines = ['tell application "System Events"']
    for ch, d in plan(text, cps, jitter, fast, seed):
        if ch == "\n":
            if newline == "shift": lines.append("key code 36 using shift down")
            elif newline == "enter": lines.append("key code 36")
            else: lines.append('keystroke " "')
        elif ch == "\t": lines.append("key code 48")
        else: lines.append(f'keystroke "{_esc(ch)}"')
        lines.append(f"delay {d}")
    lines.append("end tell")
    return "\n".join(lines)


def type_text(text, cps=22.0, jitter=0.35, fast=1.0, newline="shift", countdown=3, app=None, seed=1, dry=False):
    """Type `text` into the frontmost app (or bring `app` to the front first). Returns seconds it took (or the script if dry)."""
    script = applescript(text, cps, jitter, fast, newline, seed)
    if dry: return script
    if app: subprocess.run(["osascript", "-e", f'tell application "{app}" to activate'], check=True)
    for k in range(countdown, 0, -1):
        print(f"typing in {k}…", file=sys.stderr, flush=True); time.sleep(1)
    t0 = time.time()
    r = subprocess.run(["osascript", "-"], input=script, text=True, capture_output=True)
    if r.returncode:
        raise RuntimeError("typing failed (does this app have Accessibility permission? System Settings > Privacy & Security > "
                           f"Accessibility): {r.stderr.strip()[:300]}")
    return round(time.time() - t0, 2)
