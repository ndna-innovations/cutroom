"""MCP server: the studio engine as tools for Claude.  Run: .venv/bin/python -m studio.mcp_server  (stdio)
Register once:  claude mcp add cutroom -- /path/to/cutroom/.venv/bin/python -m studio.mcp_server
Long work (render, check) runs as a background job: start it, then poll job_status (no tool-call timeouts)."""
import json, os, subprocess, sys, time, uuid
from mcp.server.mcpserver import MCPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "bin", "python")
JOBS = os.path.expanduser("~/VideoWork/studio-cache/jobs"); os.makedirs(JOBS, exist_ok=True)
sys.path.insert(0, ROOT)
server = MCPServer("cutroom", instructions=open(os.path.join(ROOT, "README.md")).read()[:6000] if os.path.exists(os.path.join(ROOT, "README.md")) else "")


def _job(args):
    jid = time.strftime("%H%M%S-") + uuid.uuid4().hex[:6]
    log = os.path.join(JOBS, jid + ".log")
    p = subprocess.Popen([PY, "-m", "studio", *args], cwd=ROOT, stdout=open(log, "w"), stderr=subprocess.STDOUT, start_new_session=True)
    json.dump(dict(pid=p.pid, args=args, log=log, started=time.time()), open(os.path.join(JOBS, jid + ".json"), "w"))
    return jid


@server.tool()
def describe(timeline: str) -> str:
    """Plain outline of a timeline JSON: scenes, shots, layers, what he says in each scene. Fails loudly on bad anchors."""
    from studio import model as M
    return M.describe(M.resolve(M.load(timeline)))


@server.tool()
def words(timeline: str, scene: str) -> str:
    """Checked words of one scene with scene times (use them for {"word": ...} anchors)."""
    from studio import model as M
    R = M.resolve(M.load(timeline)); sc = next(x for x in R["scenes"] if x["id"] == scene)
    return "\n".join(f"{a:7.2f} {b:7.2f} {w}" for a, b, w in sc["words"])


@server.tool()
def transcribe(media: str, start: float = 0.0, end: float = -1.0) -> str:
    """Word timings of any media file stretch (absolute seconds). For finding takes, slips and cue words in raw footage."""
    from studio import words as W
    ws = W.transcribe(os.path.expanduser(media), start, None if end < 0 else end)
    return "\n".join(f"{a:8.2f} {b:8.2f} {w}" for a, b, w in ws)


@server.tool()
def ocr(media: str, t: float) -> str:
    """Text lines on screen at time t (x, y, w, h in source px) - for zoom boxes, rings and privacy blurs."""
    from studio import ocr as O
    return "\n".join(f"{x:.0f} {y:.0f} {w:.0f} {h:.0f}  {s}" for x, y, w, h, s, c in O.lines_at(os.path.expanduser(media), t))


@server.tool()
def frame(timeline: str, t: float, out: str = "") -> str:
    """Render one frame of the timeline at t seconds (as a viewer sees it) without a full render. Returns a JPEG path to look at."""
    from studio import model as M, render as RD
    return RD.frame(M.load(timeline), t, out or None)


@server.tool()
def render_start(timeline: str, out: str = "", only_from: float = -1, only_to: float = -1) -> str:
    """Start a render in the background (cached chunks: small fixes only re-render what changed). Returns a job id."""
    a = ["render", timeline] + (["--out", out] if out else []) + (["--only", str(only_from), str(only_to)] if only_from >= 0 else [])
    return _job(a)


@server.tool()
def check_start(video: str, timeline: str = "", srt: str = "", deny: str = "") -> str:
    """Start all checks on a finished video (colour tags, loudness, slips, frozen frames, white screens, privacy OCR, captions). Returns a job id."""
    a = ["check", video] + (["--timeline", timeline] if timeline else []) + (["--srt", srt] if srt else []) + (["--deny", *deny.split(",")] if deny else [])
    return _job(a)


@server.tool()
def job_status(job: str) -> str:
    """Progress (last log lines) or the final JSON report of a background job."""
    meta = json.load(open(os.path.join(JOBS, job + ".json")))
    alive = subprocess.run(["kill", "-0", str(meta["pid"])], capture_output=True).returncode == 0
    log = open(meta["log"]).read()
    return ("RUNNING\n" if alive else "FINISHED\n") + (log[-3000:] if alive else log[-12000:])


@server.tool()
def contact_sheet(video: str, every: float = 2.0) -> str:
    """Tile of frames every N seconds (as a viewer sees them). Returns a JPEG path."""
    from studio.checks import contact_sheet as cs
    return cs(os.path.expanduser(video), every=every)


@server.tool()
def search_picture(query: str, paths: str, top: int = 10) -> str:
    """Find moments in footage by what's in the picture (SigLIP 2). paths: comma-separated files. Describe the whole frame."""
    from studio.ai_vision import search
    return "\n".join(f"{h['score']:.3f} {h['t']:.2f}s {h['path']}" for h in search([os.path.expanduser(p.strip()) for p in paths.split(",")], query, top=top))


@server.tool()
def search_words(phrase: str, paths: str) -> str:
    """Where a phrase is said across footage (transcripts). paths: comma-separated files."""
    from studio.analyze import search
    return "\n".join(f"{h['t']:.2f}s {h['path']}: {h['text']}" for h in search([os.path.expanduser(p.strip()) for p in paths.split(",")], phrase))


@server.tool()
def templates() -> str:
    """Graphics templates and their props."""
    from studio.catalog import TEMPLATES, __doc__ as d
    return d + "\n\n" + "\n".join(f"{k}: {v}" for k, v in TEMPLATES.items())


@server.tool()
def gfx_preview(template: str, props_json: str, seconds: float = 3.0, tall: bool = False) -> str:
    """Render one graphic alone and return a sheet of 6 frames (to judge a design before using it)."""
    from studio.checks import gfx_preview as gp
    return gp(template, json.loads(props_json), seconds, tall)


@server.tool()
def short_build(main_timeline: str, spec_json: str, out_dir: str) -> str:
    """Build the two Short timelines (-youtube, -insta-tiktok) from a main timeline + spec (see studio/shorts.py). Returns their paths."""
    from studio import model as M, shorts as S
    main = M.load(main_timeline); spec = json.loads(spec_json); out = []
    os.makedirs(os.path.expanduser(out_dir), exist_ok=True)
    for v in ("youtube", "insta-tiktok"):
        tl = S.build(main, spec, v); p = os.path.join(os.path.expanduser(out_dir), tl["name"] + ".json"); M.save(dict(tl, _path=p)); out.append(p)
    if spec.get("photo_at") is not None or spec.get("photo"):
        out.append(S.cover(spec, main, os.path.join(os.path.expanduser(out_dir), spec["name"] + "-cover.jpg")))
    return "\n".join(out)


if __name__ == "__main__":
    server.run()
