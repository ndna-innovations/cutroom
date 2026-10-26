"""Interchange: export a timeline as OpenTimelineIO (.otio) so it opens in DaVinci Resolve, Premiere (via adapters)
or Final Cut (FCPXML adapter) for a manual look. Video track 1 = his camera spine (each kept piece a clip, dissolves
as transitions); track 2 = base shots that aren't the camera (screens, angles, graphics as named gaps); markers for
layers (rings, captions, graphics) so nothing is lost. Graphics/effects are engine-only and appear as markers."""
import os
import opentimelineio as otio
from . import model as M
from .model import FPS


def to_otio(tl, path):
    R = M.resolve(tl)
    T = otio.schema.Timeline(name=R["name"])
    v1 = otio.schema.Track(name="camera", kind=otio.schema.TrackKind.Video)
    v2 = otio.schema.Track(name="shots", kind=otio.schema.TrackKind.Video)
    a1 = otio.schema.Track(name="voice", kind=otio.schema.TrackKind.Audio)
    rt = lambda f: otio.opentime.RationalTime(f, FPS)
    cur1 = cur2 = 0
    for s in R["scenes"]:
        if s["start"] > cur1: v1.append(otio.schema.Gap(source_range=otio.opentime.TimeRange(rt(0), rt(s["start"] - cur1)))); cur1 = s["start"]
        if s["trans"] and len(v1):
            for tr in (v1, a1, v2):       # the overlap: shorten what came before by the dissolve length
                if len(tr) and isinstance(tr[-1], (otio.schema.Clip, otio.schema.Gap)):
                    r = tr[-1].source_range; tr[-1].source_range = otio.opentime.TimeRange(r.start_time, rt(max(1, r.duration.value - s["trans"])))
            cur2 -= s["trans"]
            v1.append(otio.schema.Transition(transition_type=otio.schema.TransitionTypes.SMPTE_Dissolve, in_offset=rt(s["trans"] / 2), out_offset=rt(s["trans"] / 2)))
        if s["pieces"]:
            ref = otio.schema.ExternalReference(target_url="file://" + s["src"])
            for p in s["pieces"]:
                c = otio.schema.Clip(name=f"{s['id']}", media_reference=ref, source_range=otio.opentime.TimeRange(rt(round(p["a"] * FPS)), rt(p["n"])))
                v1.append(c); a1.append(c.clone())
        else:
            v1.append(otio.schema.Gap(source_range=otio.opentime.TimeRange(rt(0), rt(s["nf"]))))
            a1.append(otio.schema.Gap(source_range=otio.opentime.TimeRange(rt(0), rt(s["nf"]))))
        cur1 = s["start"] + s["nf"]
        for b in s["base"]:
            st = s["start"] + b["f0"]; n = b["f1"] - b["f0"]
            if st > cur2: v2.append(otio.schema.Gap(source_range=otio.opentime.TimeRange(rt(0), rt(st - cur2)))); cur2 = st
            if b["kind"] in ("screen", "broll") and ("source" in b or "path" in b):
                p_ = M.src_path(tl, b["source"]) if "source" in b else os.path.expanduser(b["path"])
                v2.append(otio.schema.Clip(name=f"{s['id']}:{b['kind']}", media_reference=otio.schema.ExternalReference(target_url="file://" + p_),
                                           source_range=otio.opentime.TimeRange(rt(round(b.get("from", 0) * FPS)), rt(n))))
            else:
                v2.append(otio.schema.Gap(name=f"{s['id']}:{b['kind']}:{b.get('template', '')}", source_range=otio.opentime.TimeRange(rt(0), rt(n))))
            cur2 = st + n
        for L in s["layers"]:
            T.tracks.markers.append(otio.schema.Marker(name=f"{s['id']}: {L['kind']} {L.get('template', '')}",
                                                         marked_range=otio.opentime.TimeRange(rt(s["start"] + L["f0"]), rt(L["f1"] - L["f0"]))))
    T.tracks.extend([v1, v2, a1])
    otio.adapters.write_to_file(T, path)
    return path
