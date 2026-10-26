"""Synthetic test footage (no real recordings needed):
  cam.mov     4K HLG BT.2020 10-bit HEVC, 30 fps, with speech (macOS `say`): a retake, a filler "um", pauses
  screen/     a Cap-style folder: display.mp4 (3456x2234 bt709, 60 fps, scrolling text page) + audio-input.m4a (same
              speech, 1.25 s later -> tests sync)
  shot.png    a screenshot-like image
  sound-library/music/   two made-up music tracks (61 s, 105 s)
Usage: python tests/make_media.py OUTDIR"""
import os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/VideoWork/studio-test/fixtures"); os.makedirs(OUT + "/screen", exist_ok=True)
SCRIPT = ("[[slnc 400]] This is the first line of the demo. [[slnc 900]] This is the first line of the demo. [[slnc 700]] "
          "Um, [[slnc 200]] here we compare two tools side by side. [[slnc 800]] The chart shows the final score. [[slnc 600]] "
          "See you next sprint. Ship smarter. [[slnc 600]]")
def run(c): subprocess.run(c, check=True)
if not os.path.exists(f"{OUT}/voice.aiff"):
    run(["say", "-v", "Samantha", "-r", "175", "-o", f"{OUT}/voice.aiff", SCRIPT])
D = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f"{OUT}/voice.aiff"], capture_output=True, text=True).stdout)
if not os.path.exists(f"{OUT}/cam.mov"):
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=3840x2160:r=30:d={D:.3f}", "-i", f"{OUT}/voice.aiff",
         "-vf", "format=yuv420p10le,setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc:range=tv",
         "-c:v", "hevc_videotoolbox", "-profile:v", "main10", "-q:v", "60", "-tag:v", "hvc1",
         "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc", "-c:a", "aac", "-ar", "48000", "-shortest", f"{OUT}/cam.mov"])
# fake app page with text (for OCR) scrolled slowly
page = Image.new("RGB", (3456, 4400), (24, 25, 30)); d = ImageDraw.Draw(page)
f = ImageFont.truetype("/System/Library/Fonts/Avenir Next.ttc", 64, index=5)
lines = ["Project dashboard", "Weekly active users rose 12 percent", "Checkout conversion is down in Canada", "contact: someone@example.com",
         "Release 4.2 shipped on Tuesday", "Three bugs are still open", "Server 10.0.0.12 responded slowly"] * 3
for i, l in enumerate(lines): d.text((300, 200 + i * 200), l, font=f, fill=(235, 235, 240))
page.save(f"{OUT}/page.png")
page.crop((0, 0, 3456, 2234)).resize((1728, 1117)).save(f"{OUT}/shot.png")
if not os.path.exists(f"{OUT}/screen/display.mp4"):
    run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "60", "-t", f"{D + 1.25:.3f}", "-i", f"{OUT}/page.png",
         "-vf", f"crop=3456:2234:0:'min(2166,t*60)',format=yuv420p", "-c:v", "h264_videotoolbox", "-q:v", "70", "-colorspace", "bt709",
         "-color_primaries", "bt709", "-color_trc", "bt709", f"{OUT}/screen/display.mp4"])
    run(["ffmpeg", "-v", "error", "-y", "-i", f"{OUT}/voice.aiff", "-af", "adelay=1250:all=1", "-c:a", "aac", f"{OUT}/screen/audio-input.m4a"])
# two music tracks (a chord with a beat every 0.5 s and a real ending) for the sound-library tests
os.makedirs(f"{OUT}/sound-library/music", exist_ok=True)
for name, secs in (("test-bed", 61), ("test-intro", 105)):
    f = f"{OUT}/sound-library/music/{name}_{secs}s.m4a"
    if not os.path.exists(f):
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
             f"aevalsrc=0.12*sin(2*PI*220*t)+0.09*sin(2*PI*277.2*t)+0.09*sin(2*PI*329.6*t)+0.5*sin(2*PI*60*t)*exp(-25*mod(t\\,0.5)):s=48000:d={secs}",
             "-af", f"afade=t=out:st={secs - 3}:d=3", "-ac", "2", "-c:a", "aac", "-b:a", "192k", f])
print(OUT, f"{D:.2f}s")
