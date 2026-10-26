# Cutroom

**A video editor with no buttons. You record; Claude edits.**

Cutroom is a command-line video editor built for [Claude Code](https://claude.com/claude-code) to drive. Drop your raw
recordings in a folder and ask Claude to edit them. Claude reads the transcript, cuts mistakes and retakes, syncs your
camera with your screen recording, adds captions, colour and sound, renders the video, and then checks its own work
(bad cuts, words chopped in half, captions that are hard to read, text over your face) before you see it.
Every edit is a plain JSON file, so each change is easy to read and undo.

**Mac only.** Needs a Mac with Apple Silicon (M1 or newer). It does not run on Windows or Linux: it uses Apple's own
Vision (reading on-screen text, person cut-outs), ScreenCaptureKit (screen takes) and VideoToolbox (fast encoding).

## Install

You need [Homebrew](https://brew.sh) and Apple's command line tools (`xcode-select --install`). Then:

```bash
git clone https://github.com/ndna-innovations/cutroom.git
cd cutroom
./setup.sh
```

`setup.sh` installs the tools (uv, node, ffmpeg, whisper.cpp), the Python environment, the graphics packages and the
macOS helper, downloads the models (about 2.3 GB; `./setup.sh --minimal` gets only the 1.6 GB every edit needs), writes
a starter config and runs `cutroom doctor`, which lists anything still missing with the command that fixes it.
Run it again any time; it skips what is already there.

| Model | What it does | Licence |
|---|---|---|
| Whisper large-v3-turbo (whisper.cpp) | speech to text | MIT |
| MediaPipe face landmarker | face position, face checks | Apache-2.0 |
| SAM 2.1 small (optional) | masks around a person | Apache-2.0 |
| DeepFilterNet (optional) | voice clean-up | MIT / Apache-2.0 |
| RIFE v4.6 (optional) | slow motion, smooth jump cuts | MIT |
| SigLIP 2, BiRefNet, Depth Anything V2 Small, LaMa | picture search, cut-outs, depth (download themselves on first use) | Apache-2.0 / MIT |

**Teach Claude to use it:**
```bash
mkdir -p ~/.claude/skills/cutroom && cp claude-skill/SKILL.md ~/.claude/skills/cutroom/
claude mcp add cutroom -- "$PWD/.venv/bin/python" -m studio.mcp_server     # optional: Cutroom tools inside Claude
```
Then open Claude Code and say: *"Edit the recording in ~/Downloads/today with Cutroom."*

**Make it yours (optional):**
```bash
.venv/bin/cutroom init --profile yourname --force
```
This writes `~/.config/cutroom/profiles/yourname.json`. Fill in what you like: `name, first_name, role_line, handle,
signoff, end_line, whoosh, theme, word_fixes, caption_fixes, styles {style: overrides}, rules`. `rules` is the path to
your own editing-rules file: Claude reads it before every edit and adds to it when you give feedback.
Machine paths (models, sound library, cache) live in `~/.config/cutroom/config.json`.

## Licences
- **Cutroom** is free and open source under the [MIT licence](LICENSE).
- **Graphics use [Remotion](https://www.remotion.dev/license)**, which is free for individuals and for companies with up
  to 3 employees. Bigger companies need a Remotion Company License.
- **Models** listed above are all free for commercial use. You download them yourself; they are not in this repo.
- **Music and sound effects:** bring your own; each library keeps its own licence. The optional Freesound downloader
  (`studio/freesound.py`) fetches CC0 sounds only, with your own API key, under
  [Freesound's API terms](https://freesound.org/help/tos_api/) (commercial use of their API is agreed with Freesound).
- **AI video clips** (optional) use Google Veo with your own paid Gemini API key, or FastWan 2.2 locally (Apache-2.0).

## Using it
Run everything as `cutroom <command>` (inside the activated `.venv`, or `.venv/bin/cutroom`) (same as `.venv/bin/python -m studio <command>`). Temp + cache: `~/VideoWork/studio-cache` (safe to delete; it rebuilds). It is kept under a size limit: after every
render the least recently used files go (nothing used in the last 24 h), limit = config `"cache_limit_gb"` (default 80);
`cutroom cache` shows the size, `cutroom cache --prune [--limit-gb N]` cleans now.

**Neutral by default.** The engine has no house style: no close-ups or zoom on the face, no face box, no dimming, no
music, sound effects, captions, end cards or calls to action, no look or theme colours (plain black/white) unless the
timeline, a look or a profile style asks for them. Editing rules belong to the creator (profile `styles`, their notes).

## The loop (raw footage -> finished video)
1. **Ingest**: `ingest ~/Downloads/today --out media.json`: every file's kind (camera / screen / music / image / broll),
   HDR, variable frame rate, transcript as sentences with times, slips ("cut", "action"), lines said twice (retakes),
   and the sound-sync offset between camera and screen recordings. Read it, then plan.
2. **Build the timeline** with the editing API (`studio/edit.py`) or by writing JSON (schema below):
   ```python
   from studio.edit import Timeline
   tl = Timeline.new("launch-x", profile="yt4k", kit={"theme": "studio"}, folder="~/VideoWork/launch-x")
   tl.source("cam", "~/Downloads/today/cam.mov", role="camera", enhance={"model": "deepfilter"})
   tl.source("scr", ".../display.mp4", role="screen", sync_to="cam", auto_blur=True)        # offset found from the sound
   tl.scene_say("hook", "cam", "Google just launched", "Let's go.")   # best take (last clean one) of that line
   tl.cut_fillers("hook"); tl.cut("hook", "To be flat", "Action.")
   tl.show("hook", {"word": "Gemini"}, "angle", source="scr", auto_zoom=True, cursor=True)  # screen follows the speaker's cuts
   tl.layer("hook", "captions", style="phrase", phrases=[...]); tl.transition("hook", "slide-left", 0.3)
   print(tl.lint()); tl.save()
   ```
3. **Look before rendering**: `describe TL`, `words TL SCENE`, `frame TL 24.0` (one frame as the viewer sees it), `lint TL`.
4. **Render**: `render TL --out X.mp4` (`--only 30 45` = just a stretch). Draft first (`"profile": "draft"`), 4K last.
5. **Check**: `check X.mp4 --timeline TL [--srt S] [--deny Name]`, `sheet x --video X.mp4`, look at the sheet.
6. **Deliver**: `srt TL --out X.srt`, `export X.mp4 --as review` (phone copy with timecode), `--as sdr` (platforms that
   mishandle HDR), `--as master` (ProRes), `stills X.mp4 3 9 15` (slideshow / carousel images), `otio TL --out X.otio`
   (open the edit in Resolve / Premiere / Final Cut). Nothing is final until the creator says so.
7. **Shorts**: `studio.shorts.build(main_tl, spec, version)` -> two timelines (-youtube, -insta-tiktok) + `shorts.cover()`.

## What it can do (feature map, modelled on Premiere / Resolve / Final Cut / CapCut / Descript / Opus Clip / Screen Studio)
| Area | Feature | How |
|---|---|---|
| Text-based editing | cut by words, best take of a line, filler removal, retake detection | `edit.scene_say/takes/cut/cut_fillers`, `ingest` |
| Pauses | tighten pauses > 0.35 s on the audio, never mid-word | `spine.gap/pad` |
| Multicam | sync camera + screen by sound; `angle` shots follow the camera's cuts | `ingest.audio_offset`, base kind `angle` |
| Layouts | full face, face box (auto-placed, avoids zoomed content), split screens (`lr`, `tb`, `3`, `grid`, `main-side`), picture-in-picture video/image layers (rounded, border, slide/fade), Shorts stack | base kinds + layers |
| Keyframes | any graphic layer moves/scales/turns/fades on keys: `"anim": [{"t", "x", "y", "s", "r", "o", "ease": spring|back|cubic|inout|linear}]`, key times can be words | `compile.anim_layer` |
| Text animation | `TextFX` (cascade, typewriter, blur, slam, wave, weight, split; highlighted words + drawn underline) | `graphics/src/motion.tsx` |
| Diagrams | `FlowDiagram`: nodes pop in, arrows draw themselves with a travelling glow, focus dims the rest | `motion.tsx` |
| Blend + light | graphic layers `"blend": screen|add|multiply|overlay|softlight`; `LightLeak` (leak, burn, flare) | `compile.blend_layer` |
| Adjustment layers | scene `"adjust": [{"at", "until", "grade", "blur", "vignette", "glow", "bright", "grain", "fringe", "sharpen", "shake"}]` | `compile.adjust_layers` |
| Track mattes | layer `"kind": "matte"`: a screen/broll/still shown inside text or a shape (`Matte` template), `"invert"` | `compile.matte_layer` |
| Designed transitions | `leak`, `burn`, `flare`, `flash`, `zoom-blur`, `whip-blur`, `leak-slide` | `compile.DESIGNED` |
| Colour page | `cutroom color VIDEO T --scope x.png` (levels, cast, clipping, skin tone vs the skin line, waveform + vectorscope), `cutroom match A TA B TB` (grade that matches shots) | `scopes.py` |
| Relight | subject effect `relight` (subject brighter, background darker, SAM 2 mask) | `compile.subject_effects` |
| Stabilise | `"stabilize": "vidstab"` on broll/screen (two-pass vid.stab via ffmpeg-full, cached); `true` = quick deshake | `assets.stabilized` |
| Corner pin | layer `"kind": "pin"`: content onto 4 corners in the shot, `"track": true` follows it (optical flow + homography) | `compile.pin_layer`, `analyze.track_quad` |
| 3D | `Device3D` (three.js laptop/phone playing a clip: `{"$clip": {source, from, dur}}`), `Parallax` (photo split by depth: `depth.layers`, LaMa fill), `LottieClip` | `media3d.tsx`, `depth.py` |
| Cinematic scenes | `BookReveal` (three.js: old book in a lamp-lit library, your line lights up word by word and lifts off the page) — Veo-style b-roll with real text, free. `DataCity` (numbers as glowing towers, camera sweep), `NodeNetwork` (core wired to labelled nodes, pulses), `CardTunnel` (fly through floating cards to a hero card), `ParticleWord` (particles lock into a word, optional burst), `GlobeArcs` (dotted globe, arcs between places) | `graphics/src/cinematic.tsx`, `scenes3d.tsx` |
| Generate b-roll | `cutroom generate "PROMPT" --engine veo|local|scene --secs 8 --aspect 16:9 --topic T` files the clip + its prompt in the b-roll library (`paths.broll_library`, by topic). veo = Gemini API (paid ~US$0.40/s: shows the price, needs `--yes`; key in `paths.gemini_key`); local = mlx-video + FastWan 2.2 TI2V-5B (free, Apache-2.0, 3-step DMD via `studio/wan_fast.py`; ~2.6 min per 5 s at 832x480, upscaled to 1080p; `--image STILL` = picture-to-clip, the still becomes the first frame; say "unbranded" in prompts, it draws logos; weights in `paths.local_video_model` = lBroth/FastWan2.2-TI2V-5B-MLX `model.safetensors` + `config.json`, with the Wan 2.2 TI2V-5B `t5_encoder` + `vae`); scene = Cutroom templates. `cutroom broll "QUERY" [--pictures]` finds clips by words or by picture | `generate.py` |
| Typing | screen item `"retype": [{"at", "box": {"ocr": "first words", "to": "last words"}, "done_at", "cps", "fast"}]` types pasted text in on the recording; `cutroom type "TEXT"` really types at a human pace while you record | `compile.retype_overlay`, `typer.py` |
| Auto screen take | `cutroom autotake TAKE.json [--dry]` — **the creator starts it** (a launcher in Terminal; Claude never starts it). Opens fresh windows in any apps (a Claude session in a fresh `{stamp}` folder, Chrome on any URL; placed fill/left/right), records ONE window or the whole screen with Terminal left out (ScreenCaptureKit, HEVC, cursor, ~60 fps, optional app sound), types or pastes each prompt, `prompt_all` sends the same prompt to several apps and waits for all (fair side-by-side tests), clicks by words or by window spot, scrolls, drags, waits until windows stop changing (8×8-block diff ignoring idle animations + OCR for busy/ask words), never types unless the target window is in front, stops safely on a timeout or an ask (unless `"approve": true`). Never signs in. Output in `~/VideoWork/autotake/<name>-<time>/`: `take.mov`, `log.json` (step times on the recording clock + window rects), `snaps/`, `run.txt`. Take-file schema in the module docstring. Terminal needs Screen Recording + Accessibility permission | `autotake.py`, `native/autotake.swift` (`studio/bin/studio-autotake`: windows / screen / record / click / scroll / drag) |
| Nested clips | a source whose path is another timeline `.json` renders (cached) and plays like a video | `model.nested` |
| Sound effects | library index (Freesound CC0 by category + Sonniss), audition reels, kits, `sfx.place(tl, rules)` (opt-in; nothing placed without rules) varied per moment, category-checked, peak-normalised; voice levelling per sentence; true-peak-safe limiter | `sfx.py`, `freesound.py`, `audio.py` |
| Floating screens | screen/angle item `"stage": {"rect", "ry", "rx", "moves": [{"t", "ry", "s"}], "backdrop"}`: the recording becomes a rounded window with a soft shadow on an animated backdrop (StageBackdrop), swings in on a spring, floats, tilts in 3D; zooms + pointer still work inside | `compile.render_stage` |
| Drawn scenes | illustrations that act out an idea: ModelLadder, SafetySwitch, CloudTrap (`graphics/src/scenes.tsx`); any graphic layer can sit in a box: `"rect": [x,y,w,h]` + `"design": 1150` (smaller = drawn bigger) | `scenes.tsx`, layer `rect`/`design` |
| Screen recordings | auto zoom on click clusters (eased, follows clicks), smoothed pointer + click rings, OCR-placed zoom boxes and rings, idle-stretch finder, auto privacy blur, bright-page dimming | `auto_zoom`, `cursor`, `view.box.ocr`, `analyze.idle`, `auto_blur`, `dim` |
| Camera | punch-in close-ups (opt-in: `"close": "auto"` + `"every"`, or listed times), slow drift (opt-in `"drift"`), socket paint-out, optional face/hair touch-up, Shorts reframe that follows his face | `camera`, `paint`, `touchup`, `reframe: follow` |
| Graphics | 36 Remotion templates (cards, scores, charts, captions, kinetic type, frames, news cards, lists…), motion blur, themes, word-timed props | `graphics/src`, `catalog.py` |
| Transitions | dissolve, wipes, slides, push, zoom, circle, whip, smooth, radial, pixel, squeeze, dips, slice, diagonal | `transition.type` (any ffmpeg xfade name too) |
| Sound | DeepFilterNet voice clean-up, voice chain, music only from the library (seamless loops), per-scene levels, ducking, stings, sfx, −14.4 LUFS | `audio.py` |
| Music-led edits | beats + downbeats; anchors `{"beat": 8}` / `{"downbeat": 2}` | `analyze.beats` |
| Colour | HLG BT.2020 end to end, exact sRGB↔HLG, SDR export with a soft roll-off, "legacy" warm look | `color.py`, `export.sdr` |
| B-roll | shot-change detection, stabilisation (`stabilize: true`) | `analyze.shots`, ffmpeg deshake |
| Search | where a phrase is said (`analyze.search`), and moments by what's in the picture (`search "a file open dialog" FILES`, SigLIP 2, Apache; screen recordings also searched in 2x2 tiles) | `analyze.py`, `ai_vision.py` |
| Cut-outs | Apple Vision (keeps fine hair strands, default) or BiRefNet (MIT; solid clean edge for busy backgrounds): `cutout SRC T --matte birefnet` | `shorts.cutout`, `ai_vision.cutout_birefnet` |
| Shorts picking | candidate stretches (15-60 s, sentence-bounded) with a hook score + reasons; Claude makes the call | `candidates TL` |
| Callouts | rings that follow moving content (template matching on the recording) | ring layer `"track": true` |
| Camera moves | spring-physics easing (Screen Studio feel) for zooms; also cubic / inout / linear | `view.ease_fn` |
| Looks | 112 named designs in 16 families (Keynote, Air, Editorial, Swiss, Technical, Soft, Block, Aurora, Product, Paper, Data, Frame, Split, Graphite, Gallery, Stack) x 7 accents: palette (accent + yes/no colours, contrast-checked), type pairing and structure (panels, corners, motion, key-word marking, number marks, timer, pill, backdrop, title/cover/Short layouts). One template `Look` draws every say-it/show-it graphic in the chosen look; `cutroom looks list / preview / contact / apply` | `looks.py`, `graphics/src/looks.tsx` |
| Styles | none built in: a creator's own style lives in their profile (`"styles": {"name": {...}}`) and `presets.apply(tl, "name", title=...)` applies only what it names (title card, end slate, captions on chosen roles, name tag, music levels, whooshes at joins, close-up rhythm, screen defaults; keys in `presets.py`); `presets.story(...)` for no-face daily slideshows cut on the beat | `presets.py` |
| Jump cuts | morph cuts (RIFE, MIT): `"spine": {"morph": 4}` replaces 2+2 frames at every cut with a flow-based bridge (sync unchanged) | `interp.morph` |
| Speed | speed ramps through waits (`"ramp": {"hold", "ease", "speed"}` or solved from `to`), real slow motion (base kind `slowmo`, RIFE), reverse (`"reverse": true`), shot holds with a slow push (base kind `hold`) | `compile.ramp_segments`, `interp` |
| Colour grading | exposure, white balance, contrast, saturation, lift/gamma/gain, split toning, looks (`clean`, `warm`, `cool`, `punchy`, `film`, `teal-orange`, `bright`, `moody`) on sources or items: `"grade": "warm"` or `{...}` (done in HDR, 3D LUT) | `color.grade` |
| Masks | SAM 2 subject masks per frame: scene `"subject_fx"`: text **behind** him, `blur_bg`, `spotlight`, `outline` glow | `masks.py`, `compile.subject_effects` |
| Green screen | video layers with `"key": {"color", "similarity", "blend"}` (chroma key + despill, alpha kept through HDR) | `pip_layer` |
| Clean sound | mouth-click / mic-knock repair in pauses only (never inside speech), DeepFilterNet room-noise removal, music fitted to an exact length ending on its real ending (`cues[].fit`) | `audio.declick`, `audio.fit_music` |
| Captions in other languages | `captions.export_for_translation` -> Claude translates -> `write_translated` (.srt) / `translated_layer` (burned) | `captions.py` |
| 3D titles | `Text3D` template (extruded letters, spring swing-in) | `graphics/src/cards.tsx` |
| Thumbnails | face cut out from the HDR frame with a natural tone map, 2-3 big words, badge, icons/proof, face-left/right/centre options + a sheet; no face (profile `"thumbnail_face": false` or `--no-face`, no camera needed): huge auto-fit words left, big tool tiles stacked right (`--icon-sep +`) | `thumbs [CAM T] --words ...` |
| Speed | chunked smart render: small fixes re-render seconds, not the video; VideoToolbox with watchdog | `render.py` |
| Checks | colour tags, loudness, slips, frozen/black frames, white glare, face-box stutter, privacy OCR, caption match, .srt vs burned captions; caption contrast on the real pixels, no text on a face, frame strips at every cut, every word whole at every cut, no footage reused in a Short | `checks.py`, `review.py` |
| Cut review page | `cutreview TL --video X.mp4`: one small HTML page, a kept/cut bar per source and every voice cut with the removed words and the raw vs edited sound around it (publishable as a review page) | `review.py` |
| Interchange | OpenTimelineIO export | `interchange.py` |
| Agent access | CLI + MCP server (background jobs) | `cli.py`, `mcp_server.py` |

Tests: `tests/test_features.py` (styles, neutral defaults, ghost mouth, word-safe cuts, cache limit, grading, click repair, music fit, ramps, keying, subject effects, translation,
3D text, candidates, OTIO), `tests/test_interp.py` (slow motion, morph, hold) and `.venv/bin/python tests/test_engine.py` builds synthetic footage (speech via `say`, an HDR test camera clip, a
screen recording with delayed sound) and checks ingest, editing API, every layout, transitions, render exactness,
encoder-setting consistency across chunks, cache hits, checks, exports and a Short (8 tests).

## Timeline JSON
```jsonc
{
 "name": "argon", "profile": "yt4k",            // yt4k 3840x2160 | draft 1920x1080 | short 1080x1920 | short-draft
 "kit": {"theme": "plain",                       // plain (default: black/white) | midnight | ink | studio | sunrise | mint (+ "colors": {"accent": [r,g,b]})
         "graphics_white": 0.75,                 // HLG level of graphics white (BT.2408 = 0.75); "dim": "auto" on a screen dims bright pages below it
         "graphics_mode": "hlg",                 // "legacy" = sRGB values played as HLG (an old warm/orange look)
         "graphics": {"motion_blur": 8, "font": "'Avenir Next'"},
         "facebox": {"w": 780, "h": 900, "radius": 44, "margin": 40}},
 "sources": {
   "cam": {"path": "~/Downloads/today/cam.mov", "role": "camera",
           "paint": [{"clone": [836,1630,110,190], "to": [836,1832], "feather": 14}],   // wall socket paint-out
           "touchup": false,                       // or {"hair": true, "skin": 0.45, "shine": 0.5, "eyes": 0.06} (optional, slow)
           "face": [x,y,w,h], "head": [x,y], "frame": [x,y,w,h]},   // all optional: found from face landmarks
   "hay": {"path": ".../display.mp4", "role": "screen", "crop": [0,64,3456,2170], "blur": [[x,y,w,h]]},
   "bed": {"path": "music/morning-logic_warm-background-bed_61s.m4a", "role": "music"}   // relative to the sound library
 },
 "word_fixes": {"Smart but worth it": "Smarter, but worth it"},    // checked word list (captions use it)
 "scenes": [
  {"id": "cold",
   "spine": {"source": "cam", "ranges": [[37.25, 46.39]], "gap": 0.35, "pad": 0.12,
             "cuts": [["To be flat", "Action."]],   // remove a stretch by its words (cut points placed in the quietest 10 ms)
             "holds": {"1": 5.0}},                  // 5 s silent beat before range 1: voice off, his face frozen (no lips moving without sound)
   "camera": {"close": "auto", "every": 8.0, "zoom": 1.14, "drift": 0.03, "close_on": ["zero"], "close_last": true},   // all off unless set
   "transition": {"type": "dissolve", "d": 0.2},    // into this scene; "cut" for none
   "pip": "bottom-left", "pip_label": "TEST 2 · NEEDLES",   // face box over non-camera shots (off unless set) + step label
   "base": [ {"at": 0, "kind": "camera"},
             {"at": {"word": "Gemini"}, "kind": "screen", "source": "hay", "from": 52.0, "to": 72.0},       // 20 s of screen fitted to the shot
             {"at": {"word": "nothing"}, "kind": "screen", "source": "hay", "from": 58.0, "freeze": true,
              "view": {"box": {"ocr": "There are actually", "to": "Chapter IX", "half": "L", "at": 58.0}, "hold": 0.4, "ease": 0.7},
              "dim": "auto", "pip": "bottom-right"},
             {"at": 12.0, "kind": "graphic", "template": "ScoreCard", "props": {...}},
             {"at": 20.0, "kind": "still", "path": "x.png"}, {"at": 0, "kind": "broll", "path": "...mp4", "from": 1.0, "speed": 0.8},
             {"at": 0, "kind": "stack", "top": 0.5, "content": {"kind": "screen", ...}} ],   // Shorts: content on top, him below
   "layers": [ {"kind": "ring", "at": {"word": "nothing", "offset": 1.2}, "box": {"ocr": "There are actually", "half": "L", "at": 58.0}},
               {"kind": "graphic", "template": "StatPanel", "at": 0, "until": {"end": 0},
                "props": {"items": [{"at": {"$word": "million"}, "big": "1M tokens"}]}},       // "$word" = seconds from the graphic start
               {"kind": "captions", "style": "phrase", "phrases": ["Google says it can read", "..."]},
               {"kind": "cutout", "source": "cam", "src_at": 785.4, "rect": [x,y,w,h]} ],      // his face, kept in HLG
   "music": 0.17,                                    // bed level under this scene; null = no music (screen walkthroughs)
   "sfx": [{"at": -0.25, "path": ".../whoosh.wav", "gain": 1.6}]}
 ],
 "overlays": [ {"kind": "graphic", "template": "Progress", "at": 0, "until": 30.0} ],    // timeline-wide, plain seconds
 "audio": {"bed": "bed", "loudness": -14.4, "limit": 0.85,
           "cues": [{"path": "music/the-opening-move_tech-intro_105s.m4a", "at": 7.9, "from": 2.0, "dur": 9.0, "gain": 0.55}]}
}
```
Anchors (`at`, `until`): seconds, `{"word": "phrase", "n": 2, "after": 3.0, "offset": -0.1}`, `{"word_end": ...}`,
`{"end": -1.0}` (from the scene end), `{"after": 5.0}` (until only). Words = the scene's own cut voice track, transcribed
(what the viewer hears), with `word_fixes` applied. Bad anchors fail with the words that *were* heard.
Coordinates: boxes on screen items are **source px** of that recording (OCR gives them); graphics props are design
units (1920 wide for 16:9, 1080 wide for 9:16).

## How it renders (why it is fast and safe)
- `model.resolve` -> concrete frames. `compile.window(R, f0, f1)` -> **one ffmpeg graph** for any window of the
  timeline (yuv444p10, HLG BT.2020, 30 fps). Sources are put on the 30 fps grid by timestamp (`-copyts` + `fps`), so
  VFR screen recordings can't stutter the face box, and chunks join frame-exactly (tested: 450/450 frames identical).
- `render.plan_chunks` cuts the video into ~8 s windows (scene/transition/shot boundaries). Each chunk's cache key =
  hash(graph, input fingerprints, profile, engine version). Chunks are encoded once (HEVC Main10, VideoToolbox) and
  joined **without re-encoding**. A small fix re-renders only its chunks (ring moved: 2/8 chunks, 43 s).
- Assets are content-addressed and built before the chunks: Remotion graphics in one batch, touch-up patches, stills.
- `media.ff` = ffmpeg with a progress watchdog: a stalled encode is killed after 90-180 s without progress and retried
  on the software encoder; errors raise with the command + stderr. VideoToolbox use is capped by a machine-wide
  2-slot lock (`STUDIO_VT_SLOTS`). Three parallel 4K VT encodes were tested fine on 2026-10-17.

## Colour (HDR) — never guess
- Footage is iPhone HLG BT.2020 10-bit; the whole pipeline stays HLG. `studio/color.py` holds the maths (BT.2100 +
  BT.2408: sRGB white -> 203 nits -> HLG 75 %), and a 65^3 LUT for ffmpeg `lut3d` (verified against the maths within 1
  code value: `tests/test_color.py`). Every RGB<->YUV step names the BT.2020 matrix explicitly (ffmpeg defaults to BT.601).
- Screens (bt709 Cap recordings) and graphics go through the same conversion; bright pages dim only when asked (`dim: "auto"`).
- Previews/stills for people (thumbnails, covers, contact sheets) use `color.hlg_to_srgb`. Faces inside graphics come
  from the HLG frame directly (`cutout` layer) — no sRGB round trip, no red face.

## Graphics (Remotion, graphics/src)
36 templates (`python -m studio templates`): TitleCard, TestCard, LogoHit, VersusCard, EndCard, ShortEnd, Cover,
ScoreCard, Scoreboard, WordRace, ClaimBoard, BigNumber, VerdictTable, Captions (kinetic / phrase / karaoke), Kinetic,
LowerThird, Pill, Chips, ListReveal, StatPanel, Highlight (ring / box / spotlight / underline), Callout, Timer, Progress, Cursor (his pointer + click rings: `"cursor": true` on a screen item).
- Time inside templates is **seconds** (`useT()`), springs via `sp()`. Shared look in `lib.tsx` (Panel, Glow, Stamp,
  Sparks, Shockwave, Sweep, Backdrop variants, themes). Every template has a tall (9:16) layout.
- Motion blur: pass 1 renders every frame at 30 fps (JPEG if solid, PNG if it has alpha); frames that move are found
  automatically and re-rendered at 240 fps, averaged 5/8 per frame (225° shutter), premultiplied. ~4x faster than
  supersampling everything.
- New template: add a component, register it in `src/index.tsx`, add a line to `studio/catalog.py`, preview with
  `python -m studio gfx NAME props.json [--tall]` (returns a frame sheet). Editing any template file invalidates its
  cached renders automatically (source hash).
- Images in props: `"file:///abs/path.png"` (copied next to the bundle, served by URL; never inline data URIs).
- Licence: Remotion is free for individuals and companies with up to 3 employees; larger companies need a Remotion Company License.

## Looks (`studio/looks.py`, `graphics/src/looks.tsx`)
A look is a whole design for one video, so no two videos look the same and every graphic in a video matches.
`FAMILIES` fix the structure (surface glass/solid/elevated/outline/flat/editorial/block/stack/none, corner radius, motion
pop/scale/rise/slide/wipe/mask/fade/type, key word colour/underline/marker/block/weight/gradient, marks, timer
ring/digital/bar/dial/flip, pill, title, cover, Short caption + header); each family has 7 variants that rotate accent,
background, font and backdrop (any two differ in 2+ of them; any two families differ in 4+ structural choices). Colours
are fitted: text 7:1, secondary 4.5:1, accent 3:1 on page and card, text on accent 4.5:1, accent hue 18+ degrees from
the yes/no green and red. No glow anywhere (neutral shadows only). Fonts are macOS system fonts; nothing is bundled.
```bash
cutroom looks list [--family paper]                          # 112 looks
cutroom looks preview air-indigo paper-copper --out DIR --frames cam.jpg screen.jpg   # labelled photo board per look
cutroom looks contact --pick 20 --out board.jpg --frames cam.jpg screen.jpg           # numbered board to pick from
cutroom looks apply timeline.json paper-copper              # kit.look + colours + fonts (older templates follow it)
```
In an edit: `looks.layer(el, at, end, **props)` (overlays) / `looks.base(el, at, **props)` (full-screen) with
`el` = title, contents, list, panel, pill, timer, number, plan, logo, term, source, madeby, versus, end, short,
shortend, cover (props in `catalog.py` -> Look). Looks are optional: nothing uses one unless the timeline picks it (the `Look` template refuses to draw without one).
One video can tweak a look: `"look": {"base": "data-amber", "accent": [r, g, b]}`. Tests: `tests/test_looks.py`.

## Sound
`studio/audio.py`: voice chain per scene (high-pass, de-noise, warmth, de-ess, presence compressor) with 4 ms fades at
every join; bed only from the sound library (`music_path` refuses anything else), looped seamlessly after a silent-tail
check, per-scene levels with 0.5 s ramps, sidechain ducking; stings/cues; sfx; final = one fixed gain to the target
(-14.4 LUFS) + limiter (never dynamic loudnorm). No pop sounds on text (by design).

## Shorts (`studio/shorts.py`)
Spec: `{"name", "hook", "badge", "keys": [...], "photo_at": cam_seconds, "look": "band"|"board"|"seam", "speed": 1.0,
"pieces": [{"scene", "from", "to", "layout": "face"|"stack"|"board", "look", "views": [view per part]}], "end": {"title", "kicker", "icons"}}`.
**Every Short gets its own look**: pick one per Short (or per piece), never one template for all. `shorts.LOOKS`:
- `band`: black header with the badge (white text, blue edge) and the hook (white rounded pill, first
  2.6 s) / the screen or graphic edge to edge (y 380-1000) / a solid black band with the kinetic captions (y 1000-1200) /
  him edge to edge in a wider view (y 1200-1920).
- `board`: a tall board fills the top half (box 1040x940 at y 130). Graphics are drawn in their board
  layout (big rows, 60 px claims, 40 px notes, long lines shrink to fit; `ClaimBoard`, `VerdictTable` with a big
  score row). Black band y 1080-1200 with captions at y 1140, him from y 1200. The badge hides while a board is up.
  Screen recordings fall back to `band`.
- `seam`: camera right under the content, soft seam, captions on the seam.
Piece keys `top`, `band`, `box`, `cam_zoom`, `face_at`, `content_y` fine-tune any look (fractions of the frame height;
box in 1080-wide px). New looks are new entries in `LOOKS`.
Layout rules for every look: boards readable at phone size, no wasted space at the top. Cuts between words: a piece
edge inside a word moves to just before it (most of the word kept) or just after it (most of it cut), so no first or last
word is lost; an end still inside sound runs on to the first quiet moment (`"snap": False` turns this off). Each piece
gets a 40 ms fade-in (`"fade_in"`). Jump cuts are plain hard cuts (`"jump": "hard"` default; `"punch"`: every other
piece 1.1x closer, set by `"punch"`; `"morph"` = RIFE morph cuts, which can melt hair on bigger moves). `"speed": 1.1` plays the whole Short faster with the pitch kept (timeline `speed`, applied
at the mux; chunks reused). Also built in: never shrink him, captions from the checked words, tool-only moments
dropped, versions that share all chunks but the end card, cover JPEG (sRGB). Opt-in only: music bed (`"music"`),
progress bar (`"progress": true`), end card (`"end"`, with its own `"cta"` per version; no call-to-action text is built in).

## Checks (`python -m studio check`)
streams (HLG/BT.2020/10-bit/30 fps, A/V length) · loudness · slips (re-transcribe: cut/action/retake/repeats) · frozen +
black frames (stills allowed) · bright-white share · face-box stutter · privacy OCR every 0.5 s (emails, IPs, phones,
cards, keys, `--deny` names) · .srt never overlapping burned captions · caption contrast ≥ 4.5:1 measured behind each caption
(re-measured 0.3 s either side so fades don't count) · no text on a face (every frame of a Short's first 2.5 s) · frame
strips at every cut (`strips TL --video X`, one-frame flashes + a sheet to look at) · every word whole at every voice cut (the
source must be silent at both edges; the two words either side must be heard) · no footage moment twice in a Short. Each
was added with a test that fails on a broken example first (`tests/test_review.py`).

## Face / hair touch-up (optional, `studio/touchup.py`)
Only when a video asks for it (not every time). SAM 2 masks on keyframes + MediaPipe landmarks;
the hair outline is kept in head coordinates and smoothed over time (no wobble), clumps/flyaways replaced by a wall
plate from the shot; gentle skin smoothing, shine removal, eye lift inside landmark masks. Patch = head region with an
alpha that is 0 wherever nothing changed (no rectangle edge -> no seam). Slow (~20x real time on an M5 Pro), cached.

## MCP (optional)
`claude mcp add cutroom -- "$PWD/.venv/bin/python" -m studio.mcp_server` (run in the repo folder) gives tools: describe, words,
transcribe, ocr, frame, render_start / check_start / job_status (background jobs), contact_sheet, templates,
gfx_preview, short_build. The CLI does the same.

## Built-in guarantees (engine behaviour, not style)
no cut-offs (range edges, cuts and removed pauses never land in a word's sound: a cut just inside a stretch of sound
goes to its edge, deeper inside it goes to the nearer word edge, 60 ms pad into the pause; word times are checked against
the audio because the speech model's are rough) · no lips moving
without sound (holds and tails freeze the face) · constant 30 fps, no unplanned frozen frames (checked) · no .srt over
burned captions (checked) · music only from the sound library (known licences) · HLG kept end to end · privacy check
after every render (OCR: emails, IPs, keys, the profile's `privacy_deny` list; blurring itself where `auto_blur` is set) ·
render cache kept under its size limit.

## Known gaps / next
- Lottie icon pack: LottieFiles downloads need the creator's own free account (no direct links); any .json plays.
- Proxies left out on purpose: drafts are graphics-bound, and proxies would change every source-px box (risk > gain).
- Voice clone / dubbing: waiting on the creator's decision (YouTube asks to label realistic synthetic voice).
- Not used on purpose: REA ("reverse engineer anything", decompiles apps): editors' licences forbid decompiling and the
  features are documented publicly anyway (decided 2026-10-17).
- Never use: CoTracker, MatAnyone, madmom, Demucs weights, InsightFace, Ultralytics (licences).
