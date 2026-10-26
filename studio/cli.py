"""studio CLI (python -m studio ...). Commands:
  render  TIMELINE [--out F] [--only T0 T1]      render (cached chunks; prints the report)
  frame   TIMELINE T [--out F.jpg]                one frame at T seconds, as a viewer sees it
  sheet   TIMELINE [--every 2] [--out F.jpg]      contact sheet of frames across the timeline
  describe TIMELINE                               plain outline: scenes, shots, layers, what he says
  words   TIMELINE SCENE                          checked words of a scene with times (for cue anchors)
  check   VIDEO [--timeline TL] [--srt F]         all checks (privacy, slips, loudness, freezes, white, face box, captions)
  gfx     TEMPLATE PROPS.json [--secs 3] [--tall] render one graphic alone + a preview sheet
  templates                                       list graphics templates
  lint    TIMELINE                                problems a render would hit (missing files, bad anchors, templates, corners)
  ingest  FOLDER|FILES [--out media.json]         what's in the raw footage: kinds, HDR/VFR, transcripts, slips, retakes, sync
  export  VIDEO --as sdr|review|master            SDR copy (tone-mapped), phone review copy with timecode, ProRes master
  stills  VIDEO T1 T2 ...                         sRGB JPEGs at those seconds (slideshows, carousels)
  candidates TIMELINE [--min 15 --max 60]        Short candidates with a hook score (Claude picks; then shorts.build)
  thumbs  [CAMERA T] --words "FOUND/ZERO." ... --out DIR   thumbnail options (face from the HDR frame) + a sheet;
          --no-face / --face override the profile's "thumbnail_face" (no face: huge words + big tool tiles, no camera needed)
  search  "QUERY" FILES...                        find moments by what's in the picture (SigLIP 2); transcripts: analyze.search
  cutout  SOURCE T [--matte vision|birefnet]      person cut-out PNG (sRGB) from a frame
  otio    TIMELINE --out F.otio                   OpenTimelineIO export (open the edit in Resolve / Premiere / FCP)
  srt     TIMELINE --out F.srt                    closed captions from checked words (skips burned-caption stretches)
  init    [--profile NAME] [--sound-library DIR]  first-time setup: writes ~/.config/cutroom/config.json (+ an empty profile)
  doctor                                          what this machine has and lacks, with the fix for each
  cache [--prune] [--limit-gb N]                  render cache size; --prune removes least recently used files over the limit
  generate "PROMPT" [--engine veo|local|scene --secs 8 --aspect 16:9 --res 1080p --topic T --yes]   make a b-roll clip into the library (veo is paid: shows the price, needs --yes)
  broll   "QUERY" [--pictures]                    find clips in the b-roll library by words (and by what's in the picture)
  broll   add FILE --topic T --prompt "..." [--move]   file a clip made elsewhere (Gemini app download) into the library
  type    "TEXT" | --file F [--cps 22 --fast 1 --countdown 3 --newline shift --app NAME]   really types it into the focused app (record typing, not a paste)
  color   VIDEO T [--scope F.png]                 colour numbers for a frame: levels, cast, saturation, skin-tone check (+ waveform/vectorscope picture)
  match   A TA B TB                               grade that makes shot A (at TA) look like shot B (at TB): put it in "grade"
  looks   list [--family F] | show NAME | preview NAME... [--out DIR] [--frames CAM SCREEN TALL] | contact [NAME...] [--pick 20] --out F.jpg | apply TIMELINE NAME
                                                  the look library (100+ named designs: palette, type, every say-it/show-it graphic, covers, Shorts)
  short   TIMELINE ...                            (Shorts: a timeline with profile 'short'; see README)"""
import argparse, json, os, sys


def main():
    ap = argparse.ArgumentParser(prog="cutroom", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render"); r.add_argument("timeline"); r.add_argument("--out"); r.add_argument("--only", nargs=2, type=float); r.add_argument("--parallel", type=int)
    f = sub.add_parser("frame"); f.add_argument("timeline"); f.add_argument("t", type=float); f.add_argument("--out")
    s = sub.add_parser("sheet"); s.add_argument("timeline"); s.add_argument("--every", type=float, default=2.0); s.add_argument("--out"); s.add_argument("--video")
    d = sub.add_parser("describe"); d.add_argument("timeline")
    w = sub.add_parser("words"); w.add_argument("timeline"); w.add_argument("scene")
    c = sub.add_parser("check"); c.add_argument("video"); c.add_argument("--timeline"); c.add_argument("--srt"); c.add_argument("--deny", nargs="*", default=[])
    sp = sub.add_parser("strips"); sp.add_argument("timeline"); sp.add_argument("--video", required=True); sp.add_argument("--out")
    cr = sub.add_parser("cutreview"); cr.add_argument("timeline"); cr.add_argument("--video", required=True); cr.add_argument("--out"); cr.add_argument("--title")
    g = sub.add_parser("gfx"); g.add_argument("template"); g.add_argument("props"); g.add_argument("--secs", type=float, default=3.0); g.add_argument("--tall", action="store_true"); g.add_argument("--out")
    sub.add_parser("templates")
    ex = sub.add_parser("export"); ex.add_argument("video"); ex.add_argument("--as", dest="kind", choices=["sdr", "review", "master"], required=True); ex.add_argument("--out"); ex.add_argument("--width", type=int)
    stl = sub.add_parser("stills"); stl.add_argument("video"); stl.add_argument("times", nargs="+", type=float); stl.add_argument("--folder")
    li = sub.add_parser("lint"); li.add_argument("timeline")
    ing = sub.add_parser("ingest"); ing.add_argument("paths", nargs="+"); ing.add_argument("--out"); ing.add_argument("--no-words", action="store_true")
    cd = sub.add_parser("candidates"); cd.add_argument("timeline"); cd.add_argument("--min", type=float, default=15); cd.add_argument("--max", type=float, default=60); cd.add_argument("--top", type=int, default=10)
    tb = sub.add_parser("thumbs"); tb.add_argument("camera", nargs="?"); tb.add_argument("at", type=float, nargs="?")
    tb.add_argument("--face", dest="face", action="store_true", default=None); tb.add_argument("--theme", help="colours: plain (default) | midnight | ink | studio | sunrise | mint"); tb.add_argument("--no-face", dest="face", action="store_false"); tb.add_argument("--words", nargs="+", required=True, help='lines split by "/", e.g. "FOUND/ZERO." "I TESTED/ARGON."')
    tb.add_argument("--badge"); tb.add_argument("--icons", nargs="*"); tb.add_argument("--proof"); tb.add_argument("--layouts", nargs="*", default=["face-right", "face-left"]); tb.add_argument("--out", required=True)
    tb.add_argument("--icon-sep", default="vs", help='word between icons ("vs" for head-to-heads, "" for a plain row)')
    tb.add_argument("--style", choices=["poster", "split", "warning", "repo"], help="another design instead of the classic layout")
    tb.add_argument("--hero"); tb.add_argument("--stamp"); tb.add_argument("--bg", choices=["dark", "light", "indigo"])
    se = sub.add_parser("search"); se.add_argument("query"); se.add_argument("paths", nargs="+"); se.add_argument("--top", type=int, default=10)
    cu = sub.add_parser("cutout"); cu.add_argument("source"); cu.add_argument("t", type=float); cu.add_argument("--matte", choices=["vision", "birefnet"], default="vision"); cu.add_argument("--out")
    ot = sub.add_parser("otio"); ot.add_argument("timeline"); ot.add_argument("--out", required=True)
    ini = sub.add_parser("init"); ini.add_argument("--profile"); ini.add_argument("--sound-library"); ini.add_argument("--force", action="store_true")
    sub.add_parser("doctor")
    ca = sub.add_parser("cache"); ca.add_argument("--prune", action="store_true"); ca.add_argument("--limit-gb", type=float)
    lk = sub.add_parser("looks"); lk.add_argument("action", choices=["list", "show", "preview", "contact", "apply"]); lk.add_argument("names", nargs="*")
    lk.add_argument("--family"); lk.add_argument("--out"); lk.add_argument("--frames", nargs="*", help="real stills behind overlays: CAMERA SCREEN [TALL]")
    lk.add_argument("--pick", type=int, default=20); lk.add_argument("--cols", type=int, default=2); lk.add_argument("--title")
    gn = sub.add_parser("generate"); gn.add_argument("prompt"); gn.add_argument("--engine", default="veo"); gn.add_argument("--secs", type=float, default=8)
    gn.add_argument("--aspect", default="16:9"); gn.add_argument("--res", default="1080p"); gn.add_argument("--topic"); gn.add_argument("--negative")
    gn.add_argument("--image"); gn.add_argument("--template"); gn.add_argument("--props"); gn.add_argument("--yes", action="store_true")
    br = sub.add_parser("broll"); br.add_argument("query"); br.add_argument("file", nargs="?"); br.add_argument("--pictures", action="store_true")
    br.add_argument("--top", type=int, default=10); br.add_argument("--topic"); br.add_argument("--prompt", default=""); br.add_argument("--move", action="store_true")
    ty = sub.add_parser("type"); ty.add_argument("text", nargs="?"); ty.add_argument("--file"); ty.add_argument("--cps", type=float, default=22.0)
    ty.add_argument("--fast", type=float, default=1.0); ty.add_argument("--countdown", type=int, default=3); ty.add_argument("--newline", default="shift")
    ty.add_argument("--app"); ty.add_argument("--dry", action="store_true")
    co = sub.add_parser("color"); co.add_argument("video"); co.add_argument("t", type=float); co.add_argument("--scope")
    ma = sub.add_parser("match"); ma.add_argument("a"); ma.add_argument("ta", type=float); ma.add_argument("b"); ma.add_argument("tb", type=float)
    sr = sub.add_parser("srt"); sr.add_argument("timeline"); sr.add_argument("--out", required=True)
    at = sub.add_parser("autotake", help="unattended screen take from a take file (the creator starts it)"); at.add_argument("take"); at.add_argument("--out"); at.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    from . import model as M
    if a.cmd in ("generate", "broll"):
        from . import generate as GN
        if a.cmd == "broll":
            if a.query == "add" and a.file: print(GN.add(a.file, a.prompt, a.topic, move=a.move)); return
            for r in GN.find(a.query, a.top, a.pictures): print(json.dumps(r))
            return
        if GN.estimate(a.engine, a.secs, a.res) and not a.yes:
            print(f"{a.engine}: about US${GN.estimate(a.engine, a.secs, a.res):.2f} for {a.secs:g}s at {a.res}. Run again with --yes to spend it."); return
        props = json.loads(open(a.props).read()) if a.props else None
        print(GN.generate(a.prompt, a.engine, a.secs, a.aspect, a.res, a.topic, a.negative, a.image, a.template, props, confirm=a.yes))
        return
    if a.cmd == "autotake":
        from . import autotake as AT
        r, out = AT.run(a.take, a.out, a.dry)
        raise SystemExit(0 if r == "finished" else 1)
    if a.cmd == "type":
        from . import typer
        text = open(os.path.expanduser(a.file)).read().rstrip("\n") if a.file else a.text
        if not text: raise SystemExit("give the text or --file")
        r = typer.type_text(text, a.cps, fast=a.fast, newline=a.newline, countdown=a.countdown, app=a.app, dry=a.dry)
        print(r if a.dry else f"typed {len(text)} characters in {r}s")
        return
    if a.cmd == "looks":
        from . import looks as LK
        return LK.cli(a)
    if a.cmd in ("init", "doctor"):
        from . import config as CF
        if a.cmd == "init": print(CF.init(a.profile, a.sound_library, a.force))
        else:
            for ok, item, fix in CF.doctor(): print(("ok   " if ok else "MISS ") + item + (f"  ->  {fix}" if fix else ""))
        return
    if a.cmd in ("color", "match"):
        from . import scopes as SC
        if a.cmd == "color":
            print(json.dumps(SC.report(a.video, a.t), indent=1))
            if a.scope: print(SC.scope_image(a.video, a.t, a.scope))
        else: print(json.dumps(SC.match(a.a, a.ta, a.b, a.tb)))
        return
    if a.cmd == "render":
        from .render import render
        rep = render(M.load(a.timeline), out=a.out, only=a.only, parallel=a.parallel)
        print(json.dumps(rep, indent=1))
    elif a.cmd == "frame":
        from .render import frame
        print(frame(M.load(a.timeline), a.t, a.out))
    elif a.cmd == "sheet":
        from .checks import contact_sheet
        print(contact_sheet(a.video, every=a.every, out=a.out) if a.video else contact_sheet(None, M.load(a.timeline), a.every, a.out))
    elif a.cmd == "cache":
        from . import cache as CA
        lim = int(a.limit_gb * 1024 ** 3) if a.limit_gb is not None else None
        r = CA.prune(lim, dry=not a.prune)
        print(f"cache {CA.CACHE}: {r['before'] / 1024 ** 3:.1f} GB, limit {(lim or CA.limit_bytes()) / 1024 ** 3:.0f} GB"
              + (f"; removed {r['removed']} files ({r['freed'] / 1024 ** 3:.1f} GB)" if a.prune else f"; --prune would remove {r['removed']} files ({r['freed'] / 1024 ** 3:.1f} GB)"))
    elif a.cmd == "describe":
        print(M.describe(M.resolve(M.load(a.timeline))))
    elif a.cmd == "words":
        R = M.resolve(M.load(a.timeline)); sc = next(x for x in R["scenes"] if x["id"] == a.scene)
        for w_ in sc["words"]: print(f"{w_[0]:7.2f} {w_[1]:7.2f}  {w_[2]}")
    elif a.cmd == "check":
        from .checks import check_all
        rep = check_all(a.video, timeline=M.load(a.timeline) if a.timeline else None, srt=a.srt, deny=a.deny)
        print(json.dumps(rep, indent=1))
    elif a.cmd == "strips":
        from .review import strips
        print(json.dumps(strips(a.video, M.resolve(M.load(a.timeline)), a.out), indent=1))
    elif a.cmd == "cutreview":
        from .review import cutreview
        print(cutreview(M.load(a.timeline), a.video, a.out, a.title))
    elif a.cmd == "gfx":
        from .checks import gfx_preview
        print(gfx_preview(a.template, json.load(open(a.props)), a.secs, a.tall, a.out))
    elif a.cmd == "export":
        from . import export as E
        kw = {"out": a.out}
        if a.width: kw["width"] = a.width
        print({"sdr": E.sdr, "review": E.review, "master": E.master}[a.kind](a.video, **kw))
    elif a.cmd == "stills":
        from .export import stills
        print("\n".join(stills(a.video, a.times, a.folder)))
    elif a.cmd == "lint":
        from .edit import lint
        P = lint(M.load(a.timeline)); print("\n".join(P) if P else "clean")
    elif a.cmd == "ingest":
        from .ingest import ingest
        rep = ingest(a.paths, transcribe=not a.no_words)
        s_ = json.dumps(rep, indent=1)
        if a.out: open(a.out, "w").write(s_); print(a.out)
        else: print(s_)
    elif a.cmd == "candidates":
        from .candidates import candidates
        for c in candidates(M.load(a.timeline), a.min, a.max, a.top):
            print(f"{c['score']:3d}  {c['scene']} {c['from']:.2f}-{c['to']:.2f} ({c['secs']}s)  {', '.join(c['why'])}\n     {c['text'][:220]}")
    elif a.cmd == "thumbs":
        from .thumbs import options
        outs, sheet = options(a.camera, a.at, [w.split("/") for w in a.words], a.out, badge=a.badge, icons=a.icons, proof=a.proof, layouts=a.layouts, icon_sep=a.icon_sep, style=a.style, hero=a.hero, stamp=a.stamp, bg=a.bg, face=a.face, kit={"theme": a.theme} if a.theme else None)
        print(sheet)
    elif a.cmd == "search":
        from .ai_vision import search
        for h in search(a.paths, a.query, top=a.top): print(f"{h['score']:.3f}  {h['t']:8.2f}s  {h['path']}")
    elif a.cmd == "cutout":
        from .shorts import cutout
        print(cutout(a.source, a.t, a.out, matte=a.matte))
    elif a.cmd == "otio":
        from .interchange import to_otio
        print(to_otio(M.load(a.timeline), a.out))
    elif a.cmd == "srt":
        from .captions import write_srt
        print(write_srt(M.load(a.timeline), a.out))
    elif a.cmd == "templates":
        from .catalog import TEMPLATES
        for k, v in TEMPLATES.items(): print(f"{k:14s} {v}")


if __name__ == "__main__":
    main()
