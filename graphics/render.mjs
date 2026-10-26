// Batch renderer: node render.mjs jobs.json
// jobs: [{id, template, props, frames, fps, design:[w,h], scale, outDir, format: png|jpeg, range: [a,b]}]
// Bundles once (cached by source hash in BUNDLE_DIR), renders each job as a PNG sequence (transparent when alpha).
import { bundle } from "@remotion/bundler";
import { renderFrames, selectComposition, ensureBrowser } from "@remotion/renderer";
import fs from "node:fs"; import path from "node:path"; import crypto from "node:crypto"; import os from "node:os";

const here = path.dirname(new URL(import.meta.url).pathname);
const jobs = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const h = crypto.createHash("sha1");
for (const f of fs.readdirSync(path.join(here, "src")).sort()) h.update(f + fs.readFileSync(path.join(here, "src", f)));
const cacheRoot = process.env.BUNDLE_DIR || path.join(os.homedir(), "VideoWork/studio-cache/remotion");
const serve = path.join(cacheRoot, "bundle-" + h.digest("hex").slice(0, 12));
if (!fs.existsSync(path.join(serve, "index.html"))) {
  fs.mkdirSync(cacheRoot, { recursive: true });
  const tmp = serve + ".tmp-" + process.pid;
  await bundle({ entryPoint: path.join(here, "src/index.tsx"), outDir: tmp });
  fs.rmSync(serve, { recursive: true, force: true }); fs.renameSync(tmp, serve);
}
// keep the 3 newest bundles
for (const d of fs.readdirSync(cacheRoot).filter(x => x.startsWith("bundle-") && !x.includes("tmp")).map(x => path.join(cacheRoot, x))
  .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs).slice(3)) if (d !== serve) fs.rmSync(d, { recursive: true, force: true });
fs.utimesSync(serve, new Date(), new Date());
// file:// props -> copied next to the bundle and passed as a short URL (big images as data: URIs stall Chrome)
const pub = path.join(serve, "public", "sa"); fs.mkdirSync(pub, { recursive: true });
const files = (x) => {
  if (Array.isArray(x)) return x.map(files);
  if (x && typeof x === "object") return Object.fromEntries(Object.entries(x).map(([k, v]) => [k, files(v)]));
  if (typeof x === "string" && x.startsWith("file://")) {
    const src = x.slice(7); const ext = path.extname(src) || ".png";
    const name = crypto.createHash("sha1").update(src + fs.statSync(src).mtimeMs).digest("hex").slice(0, 16) + ext;
    const dst = path.join(pub, name); if (!fs.existsSync(dst)) fs.copyFileSync(src, dst);
    return "/public/sa/" + name;
  }
  return x;
};
await ensureBrowser();
const conc = Number(process.env.REMOTION_CONCURRENCY || Math.max(2, Math.floor(os.cpus().length * 0.6)));
for (const j of jobs) {
  const t0 = Date.now();
  const inputProps = { ...files(j.props), _w: j.design[0], _h: j.design[1], _frames: j.frames, _fps: j.fps };
  const comp = await selectComposition({ serveUrl: serve, id: j.template, inputProps });
  fs.mkdirSync(j.outDir, { recursive: true });
  await renderFrames({ composition: comp, serveUrl: serve, inputProps, outputDir: j.outDir, imageFormat: j.format || "png", jpegQuality: j.format === "jpeg" ? (j.quality || 94) : undefined,
    scale: j.scale, concurrency: conc, frameRange: j.range || null,
    onStart: () => {}, onFrameUpdate: () => {}, chromiumOptions: { gl: "angle" }, logLevel: "error" });
  console.log(JSON.stringify({ id: j.id, ok: true, seconds: (Date.now() - t0) / 1000 }));
}
