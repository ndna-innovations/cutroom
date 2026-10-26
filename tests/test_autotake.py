"""Auto take: take-file checks, key combos, menu paths, change detection and a dry run (nothing touches the Mac)."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from studio import autotake as AT


def test_validate():
    assert AT.validate({"steps": [{"id": "1", "do": "prompt", "text": "hi"}]}) == []
    bad = AT.validate({"steps": [{"id": "1", "do": "prompt"}, {"id": "1", "do": "fly"}, {"id": "2", "do": "record"}]})
    assert any("needs text" in p for p in bad) and any("duplicate" in p for p in bad)
    assert any("unknown do" in p for p in bad) and any("manual" in p for p in bad)
    assert AT.validate({"steps": []}) == ["no steps"]


def test_keys():
    assert AT.keys_script("enter").endswith("key code 36")
    assert AT.keys_script("cmd+shift+g") == 'tell application "System Events" to keystroke "g" using {command down, shift down}'
    assert "key code 53" in AT.keys_script("esc")


def test_menu_ref():
    seen, real = [], AT.osa
    AT.osa = lambda s: seen.append(s) or ""
    try:
        AT.menu("Claude", ["File", "New Session in New Window"])
        AT.menu("Claude", ["View", "Sub", "Item"])
    finally:
        AT.osa = real
    assert seen[0].endswith('click menu item "New Session in New Window" of menu 1 of menu bar item "File" of menu bar 1')
    assert 'menu item "Item" of menu 1 of menu item "Sub" of menu 1 of menu bar item "View"' in seen[1]


def test_changed_cells():
    a = np.zeros((100, 100), np.uint8); b = a.copy()
    assert AT.changed_cells(a, b) == 0
    b[0, 0] = 255                       # a blinking caret: one cell
    assert AT.changed_cells(a, b) == 1
    b[10:20, :] = 200                   # a new line of text streaming in
    assert AT.changed_cells(a, b) > 2
    assert AT.changed_cells(None, b) > 2


def test_idle_animation_is_not_busy():
    cells = 271 * 432                     # a full-screen Claude window at 1/8 scale
    assert not AT.is_busy_change(6, cells)      # idle mascot/ring (measured 18 Oct)
    assert AT.is_busy_change(2404, cells)       # answer streaming in (measured 18 Oct)
    a = np.zeros((271, 432), np.uint8); b = np.zeros((277, 432), np.uint8)
    assert AT.changed_cells(a, b) == 0          # window moved/resized: same picture, not a change


def test_front_guard():
    run = AT.Run({"steps": [{"id": "1", "do": "type", "text": "x"}]}, tempfile.mkdtemp())
    run.win = {"id": 7, "x": 0, "y": 0, "w": 10, "h": 10}
    real_w, real_a, real_o = AT.windows, AT.activate, AT.osa
    big = {"w": 1728, "h": 1084}
    strip = {"id": 5, "owner": "Claude", "w": 1728, "h": 32}
    assert AT.frontmost([strip, {"id": 7, **big}])["id"] == 7          # the thin bar is not "in front"
    AT.windows = lambda: [strip, {"id": 99, "owner": "Claude", **big}, {"id": 7, "owner": "Claude", **big}]   # someone clicked another window
    AT.activate = lambda app: None; AT.osa = lambda s: "2"
    typed = []
    real_t = AT.typer.type_text; AT.typer.type_text = lambda *a, **k: typed.append(a) or 0
    try:
        st = run.step({"id": "1", "do": "type", "text": "x"})
    finally:
        AT.windows, AT.activate, AT.osa, AT.typer.type_text = real_w, real_a, real_o, real_t
    assert st.startswith("needs_you") and typed == []   # never types into the wrong window


PAIR = {"name": "pair", "windows": [
    {"name": "claude", "app": "Claude", "new_window": ["File", "New Session in New Window"], "place": "left"},
    {"name": "gemini", "app": "Google Chrome", "new_window": ["File", "New Window"], "url": "https://gemini.google.com", "place": "right"}],
    "steps": [{"id": "1", "do": "prompt_all", "wins": ["claude", "gemini"], "text": "hi", "paste": True},
              {"id": "2", "do": "prompt", "win": "gemini", "text": "more"}], "gap": 0, "tail": 0}


def test_multi_window_take():
    assert AT.validate(PAIR) == []
    assert AT.record_spec(PAIR)["mode"] == "screen"                       # several windows -> whole screen
    assert AT.record_spec({"steps": [1]})["mode"] == "window"             # old single-window file
    assert AT.record_spec({"record": "manual", "steps": [1]})["mode"] == "manual"
    bad = dict(PAIR, steps=[{"id": "1", "do": "prompt_all", "wins": ["claude"], "text": "x"},
                            {"id": "2", "do": "prompt", "win": "chatgpt", "text": "x"}])
    probs = AT.validate(bad)
    assert any("2+ wins" in p for p in probs) and any("unknown window 'chatgpt'" in p for p in probs)
    assert AT.window_specs({"app": "Claude", "fill": False, "steps": [1]})[0]["place"] == "keep"


def test_place_rect():
    scr = {"x": 0, "y": 33, "w": 1728, "h": 1084}
    assert AT.place_rect("left", scr) == (0, 33, 864, 1084)
    assert AT.place_rect("right", scr) == (864, 33, 864, 1084)
    assert AT.place_rect("fill", scr) == (0, 33, 1728, 1084)


def test_fresh_folder():
    d = os.path.join(tempfile.mkdtemp(), "new")
    assert AT.fresh_folder(d) == d and os.path.isdir(d)                  # made if missing
    open(os.path.join(d, "notes.md"), "w").write("old")
    try: AT.fresh_folder(d); raise AssertionError("non-empty folder accepted")
    except RuntimeError: pass
    assert AT.fresh_folder(d, allow_nonempty=True) == d
    s = AT.fresh_folder(os.path.join(os.path.dirname(d), "run-{stamp}"))
    assert "{stamp}" not in s and os.path.isdir(s)                     # a new folder every run


def test_dry_pair_run():
    d = tempfile.mkdtemp(); take = os.path.join(d, "pair.json"); json.dump(PAIR, open(take, "w"))
    r, out = AT.run(take, os.path.join(d, "out"), dry=True)
    log = json.load(open(os.path.join(out, "log.json")))
    assert r == "finished" and set(log["windows"]) == {"claude", "gemini"} and log["record"]["mode"] == "screen"
    assert log["events"][0]["win"] == ["claude", "gemini"] and log["events"][1]["win"] == "gemini"


def test_mouse_steps():
    base = {"steps": [{"id": "1", "do": "click_at", "at": [0.5, 0.4]},
                      {"id": "2", "do": "scroll", "at": {"text": "Pricing"}, "lines": -5},
                      {"id": "3", "do": "drag", "from": [0.2, 0.5], "to": [0.7, 0.5], "secs": 0.8}]}
    assert AT.validate(base) == []
    bad = AT.validate({"steps": [{"id": "1", "do": "click_at", "at": [1.5, 0]}, {"id": "2", "do": "scroll", "at": [0.5, 0.5]},
                                 {"id": "3", "do": "drag", "from": [0.1, 0.1]}]})
    assert sum("must be [x, y]" in p for p in bad) == 2 and any("whole-number lines" in p for p in bad)
    win = {"x": 0, "y": 33, "w": 1728, "h": 1084}
    assert AT.frac_point(win, [0.5, 0.5]) == (864.0, 575.0)
    run = AT.Run({"steps": [1]}, tempfile.mkdtemp()); run.win = dict(win, id=7)
    calls, real = [], (AT.windows, AT.subprocess.run)
    AT.windows = lambda: [dict(win, id=7, owner="Claude")]
    AT.subprocess.run = lambda cmd, **k: calls.append(cmd[1:])
    try:
        assert run.step({"id": "3", "do": "drag", "from": [0.25, 0.5], "to": [0.75, 0.5], "secs": 0.5}) == "ok"
    finally:
        AT.windows, AT.subprocess.run = real
    assert calls == [["drag", "432.0", "575.0", "1296.0", "575.0", "0.5"]]


def test_text_landed():
    p = "Design a mobile home screen for a habit tracker app: calm green colours."
    assert AT.text_landed(p, [[0, 0, 1, 1, "Design a mobile home", 1.0]])
    assert AT.text_landed(p, [[0, 0, 1, 1, "…tracker app: calm green colours.", 1.0]])   # long prompt scrolled in its box
    assert not AT.text_landed(p, [[0, 0, 1, 1, "Attach a file, link your design syste", 1.0]])   # practice run 4: box empty


def test_ignore_areas():
    from PIL import Image
    d = tempfile.mkdtemp(); a, b = os.path.join(d, "a.png"), os.path.join(d, "b.png")
    Image.new("L", (800, 800), 0).save(a)
    im = Image.new("L", (800, 800), 0); im.paste(255, (300, 180, 500, 220)); im.save(b)   # moving hint text
    box = [[0.3, 0.2, 0.65, 0.3]]
    assert AT.changed_cells(AT.small_gray(a, box), AT.small_gray(b, box)) == 0
    assert AT.changed_cells(AT.small_gray(a), AT.small_gray(b)) > 0


def test_prompt_stops_when_text_does_not_land():
    run = AT.Run({"steps": [1]}, tempfile.mkdtemp()); run.win = {"id": 7, "x": 0, "y": 0, "w": 100, "h": 100}
    real = (AT.windows, AT.typer.type_text, AT.ocr, AT.snap, AT.press)
    sent = []
    AT.windows = lambda: [{"id": 7, "owner": "Claude", "x": 0, "y": 0, "w": 300, "h": 300}]
    AT.typer.type_text = lambda *a, **k: 1.0
    AT.snap = lambda wid, path: open(path, "w").close() or True
    AT.ocr = lambda p: [[0, 0, 1, 1, "Attach a file", 1.0]]
    AT.press = lambda k: sent.append(k)
    try:
        st = run.step({"id": "3", "do": "prompt", "text": "Design a habit tracker"})
    finally:
        AT.windows, AT.typer.type_text, AT.ocr, AT.snap, AT.press = real
    assert st.startswith("needs_you(the prompt did not appear") and "enter" not in sent


def test_has_word():
    L = [[0, 0, 1, 1, "Thinking…", 1.0], [0, 0, 1, 1, "Allow once", 1.0]]
    assert AT.has_word(L, ["thinking"]) == "thinking"
    assert AT.has_word(L, ["Deny"]) is None


def test_dry_run():
    d = tempfile.mkdtemp()
    take = os.path.join(d, "t.json")
    json.dump({"name": "t", "steps": [{"id": "1", "do": "prompt", "text": "hi"}, {"id": "2", "do": "pause", "secs": 0}], "gap": 0, "tail": 0}, open(take, "w"))
    r, out = AT.run(take, os.path.join(d, "out"), dry=True)
    assert r == "finished"
    log = json.load(open(os.path.join(out, "log.json")))
    assert [e["id"] for e in log["events"]] == ["1", "2"] and all(e["status"] == "ok" for e in log["events"])


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for n, f in tests: f(); print("ok", n)
    print(f"{len(tests)}/{len(tests)} passed")
