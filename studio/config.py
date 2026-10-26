"""Settings: where things live on this machine + the creator's profile (brand). Nothing about one person is baked in.

~/.config/cutroom/config.json (or $CUTROOM_CONFIG):
  {"profile": "yourname",                                  # profiles/<name>.json next to config.json (or built-in "default")
   "paths": {"sound_library": "~/Music/sfx", "models": "~/models/studio", "whisper": "...ggml-large-v3-turbo.bin",
             "deepfilter": ".../deep-filter", "rife_bin": "...", "rife_model": "...", "hf": "~/models/studio/hf",
             "freesound_key": "~/.config/cutroom/freesound_key.txt", "cache": "~/VideoWork/studio-cache"}}
A profile (brand) is optional; every field has a neutral default:
  {"name": "", "first_name": "", "role_line": "", "handle": "", "signoff": "", "end_line": "Thanks for watching.",
   "whoosh": null, "theme": "plain", "word_fixes": {"heard": "right"}, "caption_fixes": [["heard", "shown"]],
   "styles": {"my-style": {...}} (see presets.py), "privacy_deny": ["text to blur"], "thumbnail_face": true}
Environment variables (STUDIO_SOUND_LIBRARY, STUDIO_MODELS, STUDIO_WHISPER, ...) still win, for one-off runs."""
import json, os

HOME = os.path.expanduser("~")
CFG_PATH = os.path.expanduser(os.environ.get("CUTROOM_CONFIG", "~/.config/cutroom/config.json"))
DEFAULT_PATHS = dict(
    sound_library="~/Music/cutroom-sound-library", models="~/models/studio", whisper="~/models/whisper/ggml-large-v3-turbo.bin",
    deepfilter="~/models/studio/bin/deep-filter", rife_bin="~/models/studio/bin/rife-ncnn-vulkan", rife_model="~/models/studio/rife/rife-v4.6",
    hf="~/models/studio/hf", freesound_key="~/.config/cutroom/freesound_key.txt", cache="~/VideoWork/studio-cache",
    broll_library="~/Movies/cutroom-broll-library", gemini_key="~/.config/cutroom/gemini_key.txt", local_video_model="~/models/studio/fastwan2.2-ti2v-5b-mlx")
ENV = dict(sound_library="STUDIO_SOUND_LIBRARY", models="STUDIO_MODELS", whisper="STUDIO_WHISPER", deepfilter="STUDIO_DEEPFILTER",
           rife_bin="STUDIO_RIFE_BIN", rife_model="STUDIO_RIFE_MODEL", hf="STUDIO_HF", cache="STUDIO_CACHE", broll_library="STUDIO_BROLL")
DEFAULT_PROFILE = dict(name="", first_name="", role_line="", handle="", signoff="", end_line="Thanks for watching.", whoosh=None,
                       theme="plain", word_fixes={}, caption_fixes=[], styles={})
_C = None


def load():
    global _C
    if _C is None:
        _C = json.load(open(CFG_PATH)) if os.path.exists(CFG_PATH) else {}
    return _C


def path(key):
    if ENV.get(key) and os.environ.get(ENV[key]): return os.path.expanduser(os.environ[ENV[key]])
    return os.path.expanduser((load().get("paths") or {}).get(key) or DEFAULT_PATHS[key])


def profile(name=None):
    """The active creator profile merged over neutral defaults."""
    name = name or os.environ.get("CUTROOM_PROFILE") or load().get("profile") or "default"
    p = dict(DEFAULT_PROFILE)
    if name != "default":
        f = os.path.join(os.path.dirname(CFG_PATH), "profiles", f"{name}.json")
        if os.path.exists(f): p.update(json.load(open(f)))
        else: raise FileNotFoundError(f"cutroom profile '{name}' not found at {f}")
    for k in ("whoosh",):
        if p.get(k): p[k] = os.path.expanduser(p[k])
    return p


def init(profile_name=None, sound_library=None, force=False):
    """Write a starter config (and an empty profile) for a new machine/user. Returns the config path."""
    os.makedirs(os.path.join(os.path.dirname(CFG_PATH), "profiles"), exist_ok=True)
    if os.path.exists(CFG_PATH) and not force: return CFG_PATH
    cfg = dict(profile=profile_name or "default", paths=dict(DEFAULT_PATHS, **({"sound_library": sound_library} if sound_library else {})))
    json.dump(cfg, open(CFG_PATH, "w"), indent=1)
    if profile_name:
        pf = os.path.join(os.path.dirname(CFG_PATH), "profiles", f"{profile_name}.json")
        if not os.path.exists(pf): json.dump(dict(DEFAULT_PROFILE), open(pf, "w"), indent=1)
    global _C; _C = None
    return CFG_PATH


def doctor():
    """What this machine has and lacks, with the fix for each. [(ok, item, detail)]"""
    import shutil, subprocess
    out = []
    def chk(ok, item, fix): out.append((bool(ok), item, "" if ok else fix))
    ff = shutil.which("ffmpeg")
    chk(ff, "ffmpeg", "brew install ffmpeg")
    if ff:
        v = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        chk("hevc_videotoolbox" in v or "libx265" in v, "ffmpeg HEVC encoder", "install an ffmpeg build with VideoToolbox or x265")
    chk(shutil.which("node"), "node (graphics)", "brew install node; then: cd graphics && npm install")
    chk(os.path.exists(os.path.join(os.path.dirname(__file__), "..", "graphics", "node_modules")), "graphics packages", "cd graphics && npm install")
    chk(os.path.exists(path("whisper")), "speech model (whisper.cpp)", f"download ggml-large-v3-turbo.bin to {path('whisper')}")
    chk(shutil.which("whisper-cli") or shutil.which("whisper-cpp"), "whisper.cpp binary", "brew install whisper-cpp")
    chk(os.path.exists(path("deepfilter")), "voice clean-up (DeepFilterNet, optional)", f"see README setup -> {path('deepfilter')}")
    chk(os.path.exists(path("rife_bin")), "frame interpolation (RIFE, optional)", f"see README setup -> {path('rife_bin')}")
    chk(os.path.exists(os.path.join(path("models"), "sam2.1_hiera_small.pt")), "subject masks (SAM 2, optional)", "see README setup")
    chk(os.path.exists(os.path.join(path("models"), "face_landmarker.task")), "face model (MediaPipe, face checks)", "./setup.sh (or see README setup)")
    chk(os.path.isdir(path("sound_library")), "sound library folder", f"mkdir -p {path('sound_library')}/music (put licensed music + sfx there)")
    vis = os.path.join(os.path.dirname(__file__), "bin", "studio-vision")
    chk(os.path.exists(vis), "macOS Vision helper (OCR, cut-outs)", "swiftc -O studio/native/vision.swift -o studio/bin/studio-vision")
    try: p = profile(); chk(True, f"profile: {load().get('profile', 'default')}" + (f" ({p['name']})" if p.get("name") else ""), "")
    except Exception as e: chk(False, "profile", str(e))
    return out
