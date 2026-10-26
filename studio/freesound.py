"""Freesound CC0 sound effects -> sound-library/sfx-freesound-cc0/<kind>/ (+ manifest.json with id, author, link).
Uses your Freesound API key (config paths.freesound_key, never printed). Token access gives the high-quality
previews (OGG ~192 kbps), converted to 48 kHz WAV. Only CC0 (no credit needed); best rated / most downloaded first.

    fetch(kinds=None, per=60)   -> {kind: n downloaded}  (about 40 categories)"""
import os, json, re, subprocess, urllib.parse, urllib.request

from .config import path as _cfg_path
KEYF = _cfg_path("freesound_key")
OUT = os.path.join(_cfg_path("sound_library"), "sfx-freesound-cc0")
QUERIES = {   # kind: ([queries], (min s, max s)) — a broad library: many categories, many options each
    "whoosh": (["whoosh", "swoosh", "transition whoosh", "fast whoosh", "air whoosh", "cinematic whoosh"], (0.3, 3.0)),
    "whoosh-heavy": (["heavy whoosh", "deep swoosh", "sub whoosh"], (0.5, 4.0)),
    "riser": (["riser", "uplifter", "tension riser", "sweep up"], (1.0, 10.0)),
    "downlifter": (["downlifter", "sweep down", "power down"], (0.5, 6.0)),
    "hit": (["cinematic hit", "trailer impact", "boom impact", "braam", "epic hit"], (0.4, 6.0)),
    "impact-soft": (["soft impact", "thud", "low thump", "punch"], (0.1, 2.5)),
    "sub-drop": (["sub drop", "bass drop", "808 drop"], (0.5, 5.0)),
    "click": (["ui click", "mouse click", "button click", "interface tick"], (0.02, 1.0)),
    "ui-beep": (["ui beep", "interface beep", "hud beep", "menu select"], (0.05, 1.5)),
    "notification": (["notification", "message notification", "phone notification", "ping"], (0.1, 3.0)),
    "success": (["success chime", "ui confirm", "correct answer", "level up", "achievement"], (0.2, 4.0)),
    "error": (["error buzzer", "wrong answer", "ui error", "denied"], (0.1, 3.0)),
    "pop": (["pop", "bubble pop", "cork pop"], (0.02, 1.0)),
    "swipe": (["swipe", "paper swipe", "slide transition", "card slide"], (0.1, 1.5)),
    "glitch": (["glitch transition", "digital glitch", "data glitch", "static burst"], (0.1, 2.5)),
    "typing": (["keyboard typing", "mechanical keyboard", "laptop typing"], (0.5, 10.0)),
    "typewriter": (["typewriter", "typewriter bell"], (0.2, 6.0)),
    "shutter": (["camera shutter", "camera flash", "photo snap"], (0.1, 1.5)),
    "paper": (["page turn", "paper rustle", "paper flip"], (0.2, 3.0)),
    "sparkle": (["sparkle", "magic chime", "shimmer", "twinkle"], (0.2, 4.0)),
    "cash": (["cash register", "coins", "ka-ching", "money"], (0.2, 3.0)),
    "applause": (["applause", "small crowd cheer", "crowd clapping"], (1.0, 12.0)),
    "laugh": (["audience laugh", "crowd laugh"], (0.5, 8.0)),
    "drumroll": (["drum roll", "snare roll"], (1.0, 10.0)),
    "ding": (["ding", "bell ding", "service bell", "glass ding"], (0.1, 3.0)),
    "record-scratch": (["record scratch", "vinyl scratch"], (0.1, 2.0)),
    "tick": (["clock ticking", "tick tock", "stopwatch"], (0.5, 10.0)),
    "heartbeat": (["heartbeat"], (0.5, 10.0)),
    "tension": (["suspense sting", "tension hit", "dramatic sting"], (0.5, 6.0)),
    "stinger": (["stinger", "logo sting", "intro sting"], (0.5, 6.0)),
    "magic": (["magic spell", "fairy dust", "transform"], (0.3, 5.0)),
    "zoom": (["zoom in", "zoom out", "camera zoom"], (0.2, 3.0)),
    "scroll": (["scroll", "mouse wheel"], (0.1, 3.0)),
    "phone": (["phone vibrate", "phone tap", "smartphone unlock", "message sent"], (0.1, 3.0)),
    "printer": (["printer", "fax"], (0.5, 8.0)),
    "rocket": (["rocket launch", "launch whoosh"], (1.0, 10.0)),
    "wind": (["wind transition", "wind gust"], (0.5, 6.0)),
    "water": (["water drop", "splash"], (0.1, 3.0)),
    "glass": (["glass clink", "glass tap"], (0.1, 2.0)),
    "door": (["door open", "door close", "knock knock"], (0.2, 4.0)),
    "footsteps": (["footsteps"], (0.5, 8.0)),
    "bass-hit": (["bass hit", "deep boom"], (0.3, 5.0)),
}


def _key():
    return open(KEYF).read().strip()


def _get(path, **q):
    q["token"] = _key()
    url = "https://freesound.org/apiv2/" + path + "?" + urllib.parse.urlencode(q)
    import time; time.sleep(1.1)        # API limit: 60 requests a minute
    with urllib.request.urlopen(url, timeout=60) as r: return json.load(r)


def fetch(kinds=None, per=60, page_size=100):
    man_p = os.path.join(OUT, "manifest.json"); os.makedirs(OUT, exist_ok=True)
    man = json.load(open(man_p)) if os.path.exists(man_p) else {}
    got = {}
    for kind, (qs, (lo, hi)) in QUERIES.items():
        if kinds and kind not in kinds: continue
        seen, picks = set(), []
        for q in qs:
            d = _get("search/text/", query=q, filter=f'license:"Creative Commons 0" duration:[{lo} TO {hi}]',
                     sort="rating_desc", fields="id,name,username,duration,avg_rating,num_ratings,num_downloads,previews,url,license",
                     page_size=page_size)
            for r in d.get("results", []):
                if r["id"] in seen or r.get("num_ratings", 0) < 3: continue
                seen.add(r["id"]); picks.append(r)
        picks.sort(key=lambda r: (-(r.get("avg_rating") or 0), -(r.get("num_downloads") or 0)))
        n = 0
        os.makedirs(os.path.join(OUT, kind), exist_ok=True)
        for r in picks[:per]:
            name = re.sub(r"[^A-Za-z0-9._ -]+", "", r["name"])[:60].strip() or str(r["id"])
            dst = os.path.join(OUT, kind, f"{r['id']}_{os.path.splitext(name)[0]}.wav")
            if not os.path.exists(dst):
                src = r["previews"].get("preview-hq-ogg") or r["previews"]["preview-hq-mp3"]
                tmp = dst + ".dl"
                urllib.request.urlretrieve(src, tmp)
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-ar", "48000", "-ac", "2", dst], check=True); os.remove(tmp)
            man[str(r["id"])] = dict(kind=kind, file=os.path.relpath(dst, OUT), name=r["name"], author=r["username"], url=r["url"],
                                    license=r["license"], rating=r.get("avg_rating"), secs=r["duration"])
            n += 1
        got[kind] = n
        json.dump(man, open(man_p, "w"), indent=1)
    return got
