---
name: cutroom
description: Cutroom is Claude's own backend video editor (installed on this machine). Use it for ANY video work — editing a recording, a launch video, an episode, Shorts/Reels/TikToks, thumbnails, covers, captions/.srt, daily story slideshows, re-edits, exports or checks. Never write one-off ffmpeg/Remotion scripts for a video.
---

# Cutroom

Engine: the Cutroom repo (wherever it is installed; `cutroom doctor` checks the setup). Read its `README.md` first — schema, features, recipes). CLI: `cutroom <command>`
(`cutroom -h`). Python: `from studio.edit import Timeline` (the repo's own Python environment). MCP server `cutroom` has the same tools (long jobs run in the background).
House rules: the active profile's `rules` file (see `~/.config/cutroom/profiles/`) if it has one. Nothing is final until the creator approves it.

## Recipe
0. The engine is neutral: no zoom, face box, music, captions, end card, look or colours unless the edit asks for them.
   The creator's rules decide what to add. Looks (optional, 112 named): `cutroom looks contact --pick 20 --out board.jpg
   --frames CAM.jpg SCREEN.jpg` / `cutroom looks preview NAME...`; once one is approved, `looks.apply(tl, NAME)` and
   `looks.layer(el, at, end, ...)` (list, timer, number, plan, logo, term, panel, pill, source, madeby, versus).
1. `cutroom ingest <folder> --out media.json` — kinds, HDR/VFR, transcripts, slips, retakes, camera/screen sync.
2. Build the timeline: `Timeline.new(...)`, `source(...)`, `scene_say(...)` (best take by words), `cut_fillers`, `show`
   (camera / screen / angle / split / stack / graphic / slowmo / hold), `layer` (captions, rings, graphics, video/image PiP,
   cutout), `transition`; a style saved in the profile (`"styles"`) can be applied with `presets.apply(tl, NAME, title=...)`
   (none are built in).
   Daily no-face posts: `presets.story(name, cards, bed)`.
3. `cutroom lint TL`, `cutroom describe TL`, `cutroom frame TL <t>` (look at frames before rendering).
4. `cutroom render TL --out X.mp4` (profile "draft" first, then "yt4k"); small fixes re-render only changed chunks.
5. `cutroom check X.mp4 --timeline TL`, `cutroom sheet x --video X.mp4` — look at the sheet and at every cut strip sheet
   (`X-cuts-N.jpg`, also `cutroom strips TL --video X.mp4`). Before the first draft goes out, `cutroom cutreview TL --video X.mp4`
   makes the cut review page (publish it as a review page).
6. Deliver: `cutroom srt`, `cutroom export X.mp4 --as review` (phone copy), Shorts via `studio.shorts.build`
   (+ `cutroom candidates TL` to pick), `cutroom thumbs CAM T --words "A/B" ...`, `cutroom otio` if asked.
7. Missing a feature: add it to the engine with a test, run `tests/test_engine.py` + `tests/test_features.py` + `tests/test_review.py`, commit.
   A new editing note from the creator: fix the edit, write the rule in their rules file, and where it can be measured add a
   check whose test fails on a broken example first.
