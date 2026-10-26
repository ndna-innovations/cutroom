// Cinematic 3D scenes (three.js): moods that would otherwise need generated b-roll, but with real, chosen text.
// BookReveal: an old open book in a dark library; one line lights up word by word and the words lift off the page.
import React, { useMemo } from "react";
import { AbsoluteFill, Easing, interpolate, useVideoConfig } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import { Base, RGB, ease, rgb, sp, useT } from "./lib";

const rand = (seed: number) => { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };

function canvasTex(w: number, h: number, draw: (c: CanvasRenderingContext2D) => void) {
  const cv = document.createElement("canvas"); cv.width = w; cv.height = h;
  const c = cv.getContext("2d")!; draw(c);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}

const WORDS = "the of and to in that was his he it with is for as had you not be her on at by which have or from this but all she they were my are me one their so an said them we who would been will no when there if more out up into do any your what has man could other than our some very time upon about may its only now like little then can should made did us such a great before must two these see know over much down after first mr good men own never most old shall day where those came come".split(" ");

/** {line, at (s, highlight starts), per_word (s), lift (s after a word lights up), title, sub, seed, accent: [r,g,b]} */
export const BookReveal: React.FC<Base & { line?: string; at?: number; per_word?: number; lift?: number; title?: string; sub?: string; seed?: number; accent?: RGB }> = (p) => {
  const { width, height } = useVideoConfig(); const { t, fps, D } = useT();
  const line = (p.line || "Every answer is already in the book").split(/\s+/);
  const at = p.at ?? 1.2, per = p.per_word ?? 0.28, lift = p.lift ?? 0.5;
  const gold: RGB = p.accent || [255, 196, 92];
  const pageTex = useMemo(() => [0, 1].map((side) => canvasTex(1024, 1400, (c) => {
    const r = rand((p.seed ?? 7) * 31 + side);
    const g = c.createLinearGradient(side ? 0 : 1024, 0, side ? 1024 : 0, 0);
    g.addColorStop(0, "#5a4630"); g.addColorStop(0.12, "#c9b48f"); g.addColorStop(1, "#d8c7a2"); c.fillStyle = g; c.fillRect(0, 0, 1024, 1400);
    for (let i = 0; i < 4000; i++) { c.fillStyle = `rgba(70,50,30,${r() * 0.08})`; c.fillRect(r() * 1024, r() * 1400, 2, 2); }
    c.fillStyle = "rgba(55,38,22,0.72)"; c.font = "italic 30px Georgia, 'Times New Roman', serif";
    for (let y = 140; y < 1300; y += 46) {
      if (side === 1 && Math.abs(y - 700) < 30) continue;            // the hero line lives here (as 3D words)
      let x = 110; while (x < 920) { const w = WORDS[Math.floor(r() * WORDS.length)]; c.fillText(w, x, y); x += c.measureText(w).width + 14; }
    }
  })), [p.seed]);
  const texW = line.map((w) => 90 + w.length * 46);                        // each tile is as wide as its word (+ glow room)
  const wordTex = useMemo(() => line.map((w, i) => [false, true].map((lit) => canvasTex(texW[i], 128, (c) => {
    c.font = "italic 600 76px Georgia, 'Times New Roman', serif"; c.textBaseline = "middle"; c.textAlign = "center";
    if (lit) { c.shadowColor = rgb(gold, 1); c.shadowBlur = 28; c.fillStyle = rgb([255, 236, 190]); }
    else c.fillStyle = "rgba(55,38,22,0.85)";
    c.fillText(w, texW[i] / 2, 64); if (lit) { c.shadowBlur = 50; c.fillText(w, texW[i] / 2, 64); }
  }))), [p.line]);
  const raw = line.map((w) => 0.03 + w.length * 0.05);
  const fitK = Math.min(1, 0.92 / (raw.reduce((a, b) => a + b, 0) + 0.04 * (line.length - 1)));   // the line fits on the right page
  const widths = raw.map((w) => w * fitK);
  const totalW = widths.reduce((a, b) => a + b, 0) + 0.04 * fitK * (line.length - 1);
  const u = interpolate(t, [0, D], [0, 1], { extrapolateRight: "clamp", easing: Easing.inOut(Easing.quad) });
  const Cam: React.FC = () => { const { camera } = useThree(); camera.position.set(0.25 - 0.35 * u, 2.1 - 0.5 * u, 3.4 - 1.1 * u); camera.lookAt(0.35, 0.05, 0); return null; };
  const r = rand(99);
  const dust = useMemo(() => Array.from({ length: 70 }, () => [r(), r(), r(), r()]), []);
  const flick = 1 + 0.05 * Math.sin(t * 7.3) + 0.03 * Math.sin(t * 13.1);
  return (
    <AbsoluteFill style={{ background: "radial-gradient(ellipse at 55% 45%, #2a1d12 0%, #0b0806 60%, #050403 100%)" }}>
      <ThreeCanvas width={width} height={height} camera={{ fov: 32, position: [0, 2, 3.4] }} gl={{ antialias: true }}>
        <Cam />
        <ambientLight intensity={0.45} />
        <pointLight position={[1.4, 1.6, 1.2]} intensity={14 * flick} distance={7} color="#ffb466" />
        <pointLight position={[-2, 1.2, -1.5]} intensity={2.5} distance={8} color="#5c7cff" />
        {/* table + book stack behind */}
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.06, 0]}><planeGeometry args={[12, 8]} /><meshStandardMaterial color="#1b120b" roughness={0.9} /></mesh>
        {[0, 1, 2, 3].map((i) => <mesh key={i} position={[-1.7 + i * 0.05, 0.12 + i * 0.24, -1.2]} rotation={[0, 0.2 * (i % 2 ? 1 : -1), 0]}>
          <boxGeometry args={[1.4, 0.22, 1.0]} /><meshStandardMaterial color={["#4a2a1a", "#2f3a24", "#5a1f1f", "#3a2a40"][i]} roughness={0.7} /></mesh>)}
        {/* the open book: covers + two slightly raised pages */}
        <mesh position={[0, -0.03, 0]}><boxGeometry args={[2.3, 0.05, 1.6]} /><meshStandardMaterial color="#3d2416" roughness={0.6} /></mesh>
        {[0, 1].map((side) => <mesh key={side} position={[side ? 0.55 : -0.55, 0.02, 0]} rotation={[-Math.PI / 2, side ? -0.05 : 0.05, 0]}>
          <planeGeometry args={[1.1, 1.5, 16, 1]} /><meshStandardMaterial map={pageTex[side]} roughness={0.95} /></mesh>)}
        {/* the hero line: each word lights up in turn, then lifts off the page and drifts toward the camera */}
        {line.map((w, i) => {
          const x0 = 0.55 - totalW / 2 + widths.slice(0, i).reduce((a, b) => a + b + 0.04 * fitK, 0) + widths[i] / 2;
          const ta = at + i * per; const litK = ease(t, ta, ta + 0.25); const up = sp(t, ta + lift, fps, { damping: 18, stiffness: 40 });
          // on the page: small, in its row; in the air: big and readable, laid out as one line above the book
          const big = Math.min(3.2, 1.7 / Math.max(0.3, totalW)), bw_ = widths.map((w_) => w_ * big), bt = bw_.reduce((a, b) => a + b, 0) + 0.05 * big * (line.length - 1);
          const xa = 0.35 - bt / 2 + bw_.slice(0, i).reduce((a, b) => a + b + 0.05 * big, 0) + bw_[i] / 2;
          const xb = x0 + (xa - x0) * up + 0.02 * Math.sin(t * 1.1 + i) * up;
          const y = 0.035 + up * (0.78 + 0.02 * Math.sin(t * 1.4 + i * 2.1)), z = up * 0.35;
          const rot = -Math.PI / 2 * (1 - up) + up * (-0.25 + 0.04 * Math.sin(t + i));
          const ww = widths[i] * (1 + (big - 1) * up);
          return <group key={i} position={[xb, y, z]} rotation={[rot, 0, 0]}>
            <mesh><planeGeometry args={[ww, ww * 128 / texW[i]]} /><meshBasicMaterial map={wordTex[i][0]} transparent opacity={1 - litK} depthWrite={false} /></mesh>
            <mesh><planeGeometry args={[ww, ww * 128 / texW[i]]} /><meshBasicMaterial map={wordTex[i][1]} transparent opacity={litK} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} /></mesh>
          </group>;
        })}
      </ThreeCanvas>
      {/* warm bokeh of distant lamps */}
      <AbsoluteFill style={{ pointerEvents: "none", mixBlendMode: "screen" }}>
        {[[0.12, 0.18, 0.09], [0.82, 0.12, 0.07], [0.66, 0.26, 0.05], [0.3, 0.08, 0.06], [0.93, 0.34, 0.08]].map(([x, y, s_], i) =>
          <div key={i} style={{ position: "absolute", left: x * width, top: y * height, width: s_ * height * 2, height: s_ * height * 2, borderRadius: "50%",
            background: rgb([255, 170, 90], 0.12 + 0.04 * Math.sin(t * 1.3 + i)), filter: `blur(${s_ * height * 0.25}px)` }} />)}
      </AbsoluteFill>
      {/* dust in the lamp light + a soft vignette */}
      <AbsoluteFill style={{ pointerEvents: "none" }}>
        {dust.map(([a, b, c, d], i) => { const x = (a * width + t * 12 * (c - 0.5)) % width, y = (b * height - t * 9 * d + height) % height;
          return <div key={i} style={{ position: "absolute", left: x, top: y, width: 2 + 3 * c, height: 2 + 3 * c, borderRadius: 9, background: rgb([255, 214, 160], 0.15 + 0.35 * d), filter: "blur(1px)" }} />; })}
        <AbsoluteFill style={{ background: "radial-gradient(ellipse at 52% 48%, transparent 45%, rgba(0,0,0,0.75) 100%)" }} />
      </AbsoluteFill>
      {p.title && <AbsoluteFill style={{ justifyContent: "flex-start", alignItems: "center", paddingTop: height * 0.09 }}>
        <div style={{ fontFamily: "'Avenir Next', sans-serif", fontWeight: 900, fontSize: height * 0.09, color: "#fff", textShadow: "0 6px 30px rgba(0,0,0,0.8)", opacity: ease(t, 0.3, 0.9) }}>{p.title}</div>
        {p.sub && <div style={{ fontFamily: "'Avenir Next', sans-serif", fontWeight: 700, fontSize: height * 0.035, color: rgb(gold), marginTop: 8, opacity: ease(t, 0.6, 1.2) }}>{p.sub}</div>}
      </AbsoluteFill>}
    </AbsoluteFill>
  );
};
