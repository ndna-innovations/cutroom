// More cinematic 3D scenes (three.js), all driven by props so they fit any video:
//   DataCity     numbers rise as glowing towers on a grid while the camera sweeps round
//   NodeNetwork  a glowing core wired to labelled nodes; beams draw in and pulses run along them
//   CardTunnel   the camera flies through a spiral of floating cards and lands on a hero card
//   ParticleWord thousands of particles swirl in and lock into a word (optional burst at the end)
//   GlobeArcs    a dotted globe turns while arcs fly between labelled places
import React, { useMemo } from "react";
import { AbsoluteFill, Easing, interpolate, useVideoConfig } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import { Base, RGB, colorOf, ease, fonts, rgb, sp, useT, useTheme } from "./lib";

const rand = (seed: number) => { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };
const hex = (c: RGB) => new THREE.Color().setRGB(c[0] / 255, c[1] / 255, c[2] / 255, THREE.SRGBColorSpace);

function canvasTex(w: number, h: number, draw: (c: CanvasRenderingContext2D) => void) {
  const cv = document.createElement("canvas"); cv.width = Math.max(2, Math.ceil(w)); cv.height = Math.max(2, Math.ceil(h));
  const c = cv.getContext("2d")!; draw(c);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}

/** a text label as a texture; returns it with its aspect (w/h) */
function labelTex(text: string, o: { size?: number; color?: string; weight?: number; font?: string; glow?: string; bg?: string; border?: string } = {}) {
  const size = o.size ?? 72, font = `${o.weight ?? 800} ${size}px ${o.font || "'Avenir Next', sans-serif"}`;
  const m = document.createElement("canvas").getContext("2d")!; m.font = font;
  const pad = size * (o.bg ? 0.7 : 0.35), w = m.measureText(text).width + pad * 2, h = size * (o.bg ? 1.9 : 1.5);
  const tex = canvasTex(w, h, (c) => {
    if (o.bg) { c.fillStyle = o.bg; c.beginPath(); (c as any).roundRect(4, 4, w - 8, h - 8, h * 0.28); c.fill();
      if (o.border) { c.strokeStyle = o.border; c.lineWidth = 5; c.stroke(); } }
    c.font = font; c.textAlign = "center"; c.textBaseline = "middle";
    if (o.glow) { c.shadowColor = o.glow; c.shadowBlur = size * 0.45; }
    c.fillStyle = o.color || "#fff"; c.fillText(text, w / 2, h / 2 + size * 0.04);
  });
  return { tex, aspect: w / h };
}

let _glow: THREE.Texture | null = null;
const glowTex = () => _glow || (_glow = canvasTex(256, 256, (c) => {
  const g = c.createRadialGradient(128, 128, 0, 128, 128, 128);
  g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.25, "rgba(255,255,255,0.45)"); g.addColorStop(1, "rgba(255,255,255,0)");
  c.fillStyle = g; c.fillRect(0, 0, 256, 256);
}));

const Glow: React.FC<{ pos: [number, number, number]; size: number; color: RGB; opacity?: number }> = ({ pos, size, color, opacity = 1 }) => (
  <sprite position={pos} scale={[size, size, 1]}>
    <spriteMaterial map={glowTex()} color={hex(color)} transparent opacity={opacity} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
  </sprite>
);

const Label: React.FC<{ text: string; pos: [number, number, number]; h: number; opacity?: number; color?: string; glow?: string; bg?: string; border?: string; size?: number }> =
  ({ text, pos, h, opacity = 1, ...o }) => {
    const L = useMemo(() => labelTex(text, o), [text, o.color, o.glow, o.bg, o.border]);
    return <sprite position={pos} scale={[h * L.aspect, h, 1]}>
      <spriteMaterial map={L.tex} transparent opacity={opacity} depthWrite={false} toneMapped={false} />
    </sprite>;
  };

const Cam: React.FC<{ pos: [number, number, number]; look: [number, number, number] }> = ({ pos, look }) => {
  const { camera } = useThree(); camera.position.set(...pos); camera.lookAt(...look); return null;
};

/** title + subtitle over the scene (HTML, crisp at any size) */
const Title: React.FC<{ p: Base; title?: string; sub?: string; accent: RGB; t: number; top?: boolean }> = ({ p, title, sub, accent, t, top = true }) => {
  const { height } = useVideoConfig(); const F = fonts(p);
  if (!title && !sub) return null;
  return <AbsoluteFill style={{ justifyContent: top ? "flex-start" : "flex-end", alignItems: "center", padding: `${height * 0.08}px 6%`, textAlign: "center" }}>
    {title && <div style={{ fontFamily: F.display, fontWeight: 900, fontSize: height * 0.085, color: "#fff", lineHeight: 1.05, textShadow: "0 6px 30px rgba(0,0,0,0.85)",
      opacity: ease(t, 0.2, 0.8), transform: `translateY(${(1 - ease(t, 0.2, 0.9)) * 30}px)` }}>{title}</div>}
    {sub && <div style={{ fontFamily: F.body, fontWeight: 700, fontSize: height * 0.036, color: rgb(accent), marginTop: 10, opacity: ease(t, 0.5, 1.1),
      textShadow: "0 4px 18px rgba(0,0,0,0.8)" }}>{sub}</div>}
  </AbsoluteFill>;
};

const Vignette = () => <AbsoluteFill style={{ pointerEvents: "none", background: "radial-gradient(ellipse at 50% 50%, transparent 50%, rgba(0,0,0,0.7) 100%)" }} />;

// ----------------------------------------------------------------------------------------------- DataCity
type Item = { label: string; value: number; color?: string };
/** {items:[{label,value,color?}], highlight (index, default the biggest), unit ("%", "h"...), prefix ("$"), decimals, title, sub, at, accent} */
export const DataCity: React.FC<Base & { items?: Item[]; highlight?: number; unit?: string; prefix?: string; decimals?: number; title?: string; sub?: string; at?: number; accent?: string | RGB }> = (p) => {
  const { width, height } = useVideoConfig(); const { t, fps, D } = useT(); const th = useTheme(p);
  const acc = colorOf(p.accent, th);
  const items = p.items?.length ? p.items : [{ label: "Mon", value: 3 }, { label: "Tue", value: 5 }, { label: "Wed", value: 4 }, { label: "Thu", value: 9 }, { label: "Fri", value: 6 }];
  const max = Math.max(...items.map((i) => i.value), 1e-6);
  const hi = p.highlight ?? items.reduce((b, it, i) => (it.value > items[b].value ? i : b), 0);
  const at = p.at ?? 0.5, gap = 1.25, x0 = -((items.length - 1) * gap) / 2;
  const u = interpolate(t, [0, D], [0, 1], { extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  const ang = -0.75 + 0.75 * u, rad = 11.5 - 2.3 * u, span = Math.max(1, items.length / 5);
  const fmtV = (v: number) => `${p.prefix || ""}${v.toLocaleString("en-US", { maximumFractionDigits: p.decimals ?? 0, minimumFractionDigits: p.decimals ?? 0 })}${p.unit || ""}`;
  const grid = useMemo(() => { const g = new THREE.GridHelper(40, 40, hex(acc), hex([40, 50, 90])); (g.material as THREE.Material).transparent = true; (g.material as THREE.Material).opacity = 0.35; return g; }, [acc.join()]);
  const bg = th.bg;
  return (
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 70%, ${rgb([bg[0] + 18, bg[1] + 22, bg[2] + 40])} 0%, ${rgb(bg)} 70%)` }}>
      <ThreeCanvas width={width} height={height} camera={{ fov: 34, position: [0, 3, 10] }} gl={{ antialias: true }}>
        <Cam pos={[Math.sin(ang) * rad * span, 2.4 + 1.4 * u, Math.cos(ang) * rad * span]} look={[0, 1.75, 0]} />
        <fog attach="fog" args={[hex(bg), 9 * span, 26 * span]} />
        <ambientLight intensity={0.35} />
        <directionalLight position={[4, 8, 6]} intensity={1.6} />
        <pointLight position={[0, 5, 3]} intensity={18} distance={14} color={hex(acc)} />
        <primitive object={grid} />
        {items.map((it, i) => {
          const h = 0.15 + 2.7 * (it.value / max), grow = sp(t, at + i * 0.13, fps, { damping: 15, stiffness: 70 });
          const isHi = i === hi, col = it.color ? colorOf(it.color, th) : isHi ? acc : [70, 90, 150] as RGB;
          const hh = Math.max(0.001, h * grow), x = x0 + i * gap, done = ease(t, at + i * 0.13 + 0.45, at + i * 0.13 + 0.8);
          return <group key={i}>
            <mesh position={[x, hh / 2, 0]}><boxGeometry args={[0.78, hh, 0.78]} />
              <meshStandardMaterial color={hex(col)} emissive={hex(col)} emissiveIntensity={isHi ? 0.9 : 0.25} roughness={0.35} metalness={0.4} /></mesh>
            <mesh position={[x, hh + 0.005, 0]} rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[0.78, 0.78]} />
              <meshBasicMaterial color={hex(isHi ? [255, 255, 255] : col)} transparent opacity={0.85} toneMapped={false} /></mesh>
            {isHi && <Glow pos={[x, hh, 0]} size={2.6} color={acc} opacity={0.8 * grow} />}
            <Label text={fmtV(it.value)} pos={[x, hh + 0.45, 0]} h={isHi ? 0.5 : 0.36} opacity={done} glow={isHi ? rgb(acc) : undefined} />
            <Label text={it.label} pos={[x, -0.32, 0.6]} h={0.3} opacity={ease(t, 0.2, 0.7)} color="rgba(220,228,255,0.9)" />
          </group>;
        })}
      </ThreeCanvas>
      <Vignette />
      <Title p={p} title={p.title} sub={p.sub} accent={acc} t={t} />
    </AbsoluteFill>
  );
};

// ----------------------------------------------------------------------------------------------- NodeNetwork
/** {center ("Claude"), nodes: ["Jira","GitHub",...] (2-12), title, sub, at, per (s between beams), accent} */
export const NodeNetwork: React.FC<Base & { center?: string; nodes?: string[]; title?: string; sub?: string; at?: number; per?: number; accent?: string | RGB }> = (p) => {
  const { width, height } = useVideoConfig(); const { t, fps } = useT(); const th = useTheme(p);
  const acc = colorOf(p.accent, th);
  const nodes = p.nodes?.length ? p.nodes : ["Jira", "GitHub", "Database", "Slack", "Gmail", "Mixpanel"];
  const at = p.at ?? 0.6, per = p.per ?? 0.3, R = 3.1;
  const pos = nodes.map((_, i) => { const a = (i / nodes.length) * Math.PI * 2; return new THREE.Vector3(Math.cos(a) * R, (i % 2 ? 0.55 : -0.55) * (nodes.length > 4 ? 1 : 0.4), Math.sin(a) * R); });
  const core = sp(t, 0.1, fps, { damping: 12, stiffness: 90 }), beat = 1 + 0.06 * Math.sin(t * 5);
  const r = rand(5); const stars = useMemo(() => Array.from({ length: 180 }, () => [(r() - 0.5) * 30, (r() - 0.5) * 16, -6 - r() * 14, r()]), []);
  const orbit = 0.25 * t;
  return (
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 50%, ${rgb([th.bg[0] + 14, th.bg[1] + 16, th.bg[2] + 36])} 0%, ${rgb(th.bg)} 75%)` }}>
      <ThreeCanvas width={width} height={height} camera={{ fov: 40, position: [0, 2.2, 7.5] }} gl={{ antialias: true }}>
        <Cam pos={[Math.sin(orbit) * 8.6, 2.6 - 0.6 * ease(t, 0, 3), Math.cos(orbit) * 8.6]} look={[0, 0.2, 0]} />
        <ambientLight intensity={0.4} /><pointLight position={[0, 0, 0]} intensity={30 * core} distance={9} color={hex(acc)} />
        {stars.map(([x, y, z, s], i) => <mesh key={i} position={[x, y, z]}><sphereGeometry args={[0.015 + 0.03 * s, 6, 6]} /><meshBasicMaterial color="#9fb0ff" transparent opacity={0.3 + 0.5 * s} /></mesh>)}
        <mesh scale={0.42 * core * beat}><icosahedronGeometry args={[1, 3]} /><meshStandardMaterial color={hex(acc)} emissive={hex(acc)} emissiveIntensity={1.2} roughness={0.2} metalness={0.3} flatShading /></mesh>
        <Glow pos={[0, 0, 0]} size={2.6 * core * beat} color={acc} opacity={0.7} />
        {p.center !== "" && <Label text={p.center || "Claude"} pos={[0, -0.78, 0]} h={0.42} opacity={ease(t, 0.3, 0.8)} glow={rgb(acc)} />}
        {nodes.map((n, i) => {
          const v = pos[i], ta = at + i * per, draw = ease(t, ta, ta + 0.45, Easing.inOut(Easing.cubic)), pop = sp(t, ta + 0.35, fps, { damping: 11, stiffness: 160 });
          const len = v.length(), mid = v.clone().multiplyScalar(0.5 * draw);
          const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), v.clone().normalize());
          const k = ((t - ta - 0.6) * 0.7) % 1, pulse = t > ta + 0.6 ? v.clone().multiplyScalar(1 - k) : null;   // pulses run node -> core
          return <group key={i}>
            <mesh position={mid} quaternion={q}><cylinderGeometry args={[0.018, 0.018, Math.max(0.001, len * draw), 6]} />
              <meshBasicMaterial color={hex(acc)} transparent opacity={0.7} toneMapped={false} /></mesh>
            {pulse && <Glow pos={[pulse.x, pulse.y, pulse.z]} size={0.55} color={[255, 255, 255]} opacity={0.9} />}
            <mesh position={v} scale={0.13 * pop}><sphereGeometry args={[1, 24, 24]} /><meshBasicMaterial color="#ffffff" toneMapped={false} /></mesh>
            <Glow pos={[v.x, v.y, v.z]} size={0.9 * pop} color={acc} opacity={0.55} />
            <Label text={n} pos={[v.x, v.y + 0.42, v.z]} h={0.36} opacity={pop} bg="rgba(12,16,34,0.82)" border={rgb(acc, 0.8)} size={60} />
          </group>;
        })}
      </ThreeCanvas>
      <Vignette />
      <Title p={p} title={p.title} sub={p.sub} accent={acc} t={t} />
    </AbsoluteFill>
  );
};

// ----------------------------------------------------------------------------------------------- CardTunnel
/** {cards: ["10 tabs", "5 tools", ...], hero: "One chat.", sub (under the hero), accent} — the camera flies past the cards to the hero */
export const CardTunnel: React.FC<Base & { cards?: string[]; hero?: string; sub?: string; title?: string; accent?: string | RGB }> = (p) => {
  const { width, height } = useVideoConfig(); const { t, D } = useT(); const th = useTheme(p);
  const acc = colorOf(p.accent, th);
  const cards = p.cards?.length ? p.cards : ["Jira", "Confluence", "Slack", "Gmail", "Sheets", "Mixpanel", "GitHub", "Figma"];
  const step = 2.4, zEnd = -cards.length * step - 3.5;
  const L = useMemo(() => cards.map((c) => labelTex(c, { size: 84, bg: "rgba(18,24,48,0.92)", border: "rgba(160,180,255,0.55)" })), [cards.join("|")]);
  const H = useMemo(() => labelTex(p.hero || "One place.", { size: 120, bg: rgb([20, 24, 46], 0.95), border: rgb(acc), glow: rgb(acc) }), [p.hero, acc.join()]);
  const fly = interpolate(t, [0.2, D * 0.82], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.45, 0, 0.15, 1) });
  const camZ = 5 + (zEnd + 4.6 - 5) * fly, sway = 0.25 * Math.sin(t * 0.9);
  const r = rand(11); const streaks = useMemo(() => Array.from({ length: 260 }, () => [(r() - 0.5) * 9, (r() - 0.5) * 6, 6 - r() * (cards.length * step + 14), r()]), [cards.length]);
  return (
    <AbsoluteFill style={{ background: rgb(th.bg) }}>
      <ThreeCanvas width={width} height={height} camera={{ fov: 50, position: [0, 0, 5] }} gl={{ antialias: true }}>
        <Cam pos={[sway, 0.15 * Math.cos(t * 0.7), camZ]} look={[sway * 0.3, 0, camZ - 6]} />
        <fog attach="fog" args={[hex(th.bg), 4, 16]} />
        {streaks.map(([x, y, z, s], i) => <mesh key={i} position={[x, y, z]}><boxGeometry args={[0.012, 0.012, 0.4 + 2.4 * s * (0.3 + fly)]} />
          <meshBasicMaterial color={hex(s > 0.85 ? acc : [140, 160, 255])} transparent opacity={0.25 + 0.5 * s} toneMapped={false} /></mesh>)}
        {cards.map((c, i) => {
          const a = i * 1.15, z = -i * step, x = Math.cos(a) * 1.9, y = Math.sin(a) * 1.05, h = 0.62;
          return <mesh key={i} position={[x, y, z]} rotation={[0, -x * 0.12, 0]}><planeGeometry args={[h * L[i].aspect, h]} />
            <meshBasicMaterial map={L[i].tex} transparent toneMapped={false} side={THREE.DoubleSide} /></mesh>;
        })}
        <group position={[0, 0, zEnd]}>
          <Glow pos={[0, 0, -0.2]} size={7} color={acc} opacity={0.35 + 0.35 * ease(t, D * 0.7, D * 0.9)} />
          <mesh><planeGeometry args={[1.25 * H.aspect, 1.25]} /><meshBasicMaterial map={H.tex} transparent toneMapped={false} /></mesh>
        </group>
      </ThreeCanvas>
      <Vignette />
      {p.sub && <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: height * 0.16 }}>
        <div style={{ fontFamily: fonts(p).body, fontWeight: 700, fontSize: height * 0.04, color: rgb(acc), opacity: ease(t, D * 0.82, D * 0.95), textShadow: "0 4px 18px rgba(0,0,0,0.8)" }}>{p.sub}</div>
      </AbsoluteFill>}
      <Title p={p} title={p.title} accent={acc} t={t} />
    </AbsoluteFill>
  );
};

// ----------------------------------------------------------------------------------------------- ParticleWord
/** {word, sub, at (s when it locks), burst (true: blows apart at the end), color, accent} */
export const ParticleWord: React.FC<Base & { word?: string; sub?: string; at?: number; burst?: boolean; color?: string | RGB; accent?: string | RGB }> = (p) => {
  const { width, height } = useVideoConfig(); const { t, D } = useT(); const th = useTheme(p);
  const acc = colorOf(p.accent, th), col = p.color ? colorOf(p.color, th) : [255, 255, 255] as RGB;
  const word = p.word || "SHIP IT", lock = p.at ?? 1.8;
  const data = useMemo(() => {
    const cw = 1400, ch = 360, cv = document.createElement("canvas"); cv.width = cw; cv.height = ch; const c = cv.getContext("2d")!;
    let fs = 300; c.font = `900 ${fs}px 'Avenir Next', sans-serif`; while (c.measureText(word).width > cw * 0.94 && fs > 40) { fs -= 10; c.font = `900 ${fs}px 'Avenir Next', sans-serif`; }
    c.fillStyle = "#fff"; c.textAlign = "center"; c.textBaseline = "middle"; c.fillText(word, cw / 2, ch / 2);
    const px = c.getImageData(0, 0, cw, ch).data, pts: number[] = [];
    for (let y = 0; y < ch; y += 3) for (let x = 0; x < cw; x += 3) if (px[(y * cw + x) * 4 + 3] > 128) pts.push((x - cw / 2) / 160, -(y - ch / 2) / 160);
    const n = Math.min(9000, pts.length / 2), r = rand(3), stride = pts.length / 2 / n;
    const tgt = new Float32Array(n * 3), src = new Float32Array(n * 3), dly = new Float32Array(n), hot = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const j = Math.floor(i * stride) * 2; tgt[i * 3] = pts[j]; tgt[i * 3 + 1] = pts[j + 1]; tgt[i * 3 + 2] = 0;
      const th_ = r() * Math.PI * 2, ph = Math.acos(2 * r() - 1), rr = 5 + r() * 5;
      src[i * 3] = rr * Math.sin(ph) * Math.cos(th_); src[i * 3 + 1] = rr * Math.sin(ph) * Math.sin(th_) * 0.6; src[i * 3 + 2] = rr * Math.cos(ph) - 2;
      dly[i] = r() * 0.55; hot[i] = r();
    }
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    const cols = new Float32Array(n * 3); for (let i = 0; i < n; i++) { const c_ = hot[i] > 0.82 ? acc : col; cols[i * 3] = c_[0] / 255; cols[i * 3 + 1] = c_[1] / 255; cols[i * 3 + 2] = c_[2] / 255; }
    geo.setAttribute("color", new THREE.BufferAttribute(cols, 3));
    return { n, tgt, src, dly, geo };
  }, [word, acc.join(), col.join()]);
  const pos = data.geo.attributes.position.array as Float32Array;
  const boom = p.burst ? ease(t, D - 0.9, D - 0.1, Easing.in(Easing.cubic)) : 0;
  for (let i = 0; i < data.n; i++) {
    const k = ease(t, 0.15 + data.dly[i] * lock * 0.6, lock * (0.65 + data.dly[i] * 0.6), Easing.inOut(Easing.cubic));
    const sw = (1 - k) * 2.2, i3 = i * 3;
    const sx = data.src[i3], sz = data.src[i3 + 2], c = Math.cos(sw), s = Math.sin(sw);
    const ax = sx * c - sz * s, az = sx * s + sz * c;
    let x = ax + (data.tgt[i3] - ax) * k, y = data.src[i3 + 1] + (data.tgt[i3 + 1] - data.src[i3 + 1]) * k, z = az + (data.tgt[i3 + 2] - az) * k;
    const shim = k > 0.99 ? 0.012 * Math.sin(t * 6 + i) : 0; y += shim;
    if (boom) { x += (data.src[i3] - data.tgt[i3]) * boom * 1.6; y += (data.src[i3 + 1] - data.tgt[i3 + 1]) * boom * 1.6; z += (data.src[i3 + 2] + 4) * boom; }
    pos[i3] = x; pos[i3 + 1] = y; pos[i3 + 2] = z;
  }
  data.geo.attributes.position.needsUpdate = true;
  const settle = ease(t, lock * 0.8, lock * 1.3);
  return (
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 50%, ${rgb([th.bg[0] + 16, th.bg[1] + 18, th.bg[2] + 38])} 0%, ${rgb(th.bg)} 70%)` }}>
      <ThreeCanvas width={width} height={height} camera={{ fov: 40, position: [0, 0, 7] }} gl={{ antialias: true }}>
        <Cam pos={[0.4 * Math.sin(t * 0.4), 0.15 * Math.cos(t * 0.5), 7.6 - 0.8 * ease(t, 0, D)]} look={[0, 0, 0]} />
        <points geometry={data.geo}><pointsMaterial size={0.046} vertexColors transparent opacity={1} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} sizeAttenuation /></points>
        <Glow pos={[0, 0, -0.5]} size={11} color={acc} opacity={0.22 * settle * (1 - boom)} />
      </ThreeCanvas>
      <Vignette />
      {p.sub && <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: height * 0.2 }}>
        <div style={{ fontFamily: fonts(p).body, fontWeight: 700, fontSize: height * 0.042, color: rgb(acc), opacity: settle * (1 - boom), letterSpacing: 1 }}>{p.sub}</div>
      </AbsoluteFill>}
    </AbsoluteFill>
  );
};

// ----------------------------------------------------------------------------------------------- GlobeArcs
type Place = { label: string; lat: number; lon: number };
/** {places: [{label,lat,lon}], arcs: [[from,to],...] (indexes; default: first place to every other), title, sub, at, per, accent} */
export const GlobeArcs: React.FC<Base & { places?: Place[]; arcs?: [number, number][]; title?: string; sub?: string; at?: number; per?: number; accent?: string | RGB }> = (p) => {
  const { width, height } = useVideoConfig(); const { t } = useT(); const th = useTheme(p);
  const acc = colorOf(p.accent, th);
  const places = p.places?.length ? p.places : [{ label: "Toronto", lat: 43.7, lon: -79.4 }, { label: "London", lat: 51.5, lon: -0.1 }, { label: "Bengaluru", lat: 12.97, lon: 77.6 },
    { label: "San Francisco", lat: 37.8, lon: -122.4 }, { label: "Sydney", lat: -33.9, lon: 151.2 }];
  const arcs = p.arcs?.length ? p.arcs : places.slice(1).map((_, i) => [0, i + 1] as [number, number]);
  const R = 2, at = p.at ?? 0.8, per = p.per ?? 0.45, RAD = 8;
  const v3 = (lat: number, lon: number, r = R) => { const ph = (90 - lat) * Math.PI / 180, th_ = (lon + 180) * Math.PI / 180;
    return new THREE.Vector3(-r * Math.sin(ph) * Math.cos(th_), r * Math.cos(ph), r * Math.sin(ph) * Math.sin(th_)); };
  const dots = useMemo(() => { const n = 3200, g = new THREE.BufferGeometry(), a = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) { const y = 1 - (i / (n - 1)) * 2, rr = Math.sqrt(1 - y * y), phi = i * Math.PI * (3 - Math.sqrt(5));
      a[i * 3] = Math.cos(phi) * rr * R * 1.004; a[i * 3 + 1] = y * R * 1.004; a[i * 3 + 2] = Math.sin(phi) * rr * R * 1.004; }
    g.setAttribute("position", new THREE.BufferAttribute(a, 3)); return g; }, []);
  // arcs as glowing tubes (lines are 1 px at 4K); drawn in by growing the index range
  const tubes = useMemo(() => arcs.map(([a, b]) => {
    const A = v3(places[a].lat, places[a].lon), B = v3(places[b].lat, places[b].lon);
    const M = A.clone().add(B).multiplyScalar(0.5); M.setLength(R + 0.3 + A.distanceTo(B) * 0.3);
    const curve = new THREE.QuadraticBezierCurve3(A, M, B), segs = 96;
    return { geo: new THREE.TubeGeometry(curve, segs, 0.018, RAD, false), curve, segs };
  }), [JSON.stringify(arcs), JSON.stringify(places)]);
  // turn so the first place (the hub) faces the camera, then drift east
  const mlat = places.reduce((s_, q) => s_ + q.lat, 0) / places.length, mlon = places[0].lon;
  const spin = -((mlon + 90) * Math.PI) / 180 + 0.1 * t - 0.25, tilt = ((places[0].lat * 0.85 + mlat * 0.15) * Math.PI) / 180;
  const rim = useMemo(() => canvasTex(512, 512, (c) => {
    const g = c.createRadialGradient(256, 256, 170, 256, 256, 256);
    g.addColorStop(0, "rgba(255,255,255,0)"); g.addColorStop(0.62, "rgba(255,255,255,0.55)"); g.addColorStop(1, "rgba(255,255,255,0)");
    c.fillStyle = g; c.fillRect(0, 0, 512, 512);
  }), []);
  return (
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 60%, ${rgb([th.bg[0] + 10, th.bg[1] + 14, th.bg[2] + 34])} 0%, ${rgb(th.bg)} 70%)` }}>
      <ThreeCanvas width={width} height={height} camera={{ fov: 34, position: [0, 0.6, 7.4] }} gl={{ antialias: true }}>
        <Cam pos={[0, 0.1, 8.4 - 0.7 * ease(t, 0, 5)]} look={[0, 0.42, 0]} />
        <sprite position={[0, 0, -0.1]} scale={[R * 2.72, R * 2.72, 1]}>
          <spriteMaterial map={rim} color={hex(mix3(acc, [120, 150, 255], 0.6))} transparent opacity={0.55} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
        </sprite>
        <group rotation={[tilt, spin, 0]}>
          <mesh><sphereGeometry args={[R * 0.995, 64, 64]} /><meshBasicMaterial color={hex([th.bg[0] + 4, th.bg[1] + 8, th.bg[2] + 22])} /></mesh>
          <points geometry={dots}><pointsMaterial size={0.03} color={hex([120, 150, 230])} transparent opacity={0.85} sizeAttenuation toneMapped={false} /></points>
          {tubes.map(({ geo, curve, segs }, i) => {
            const k = ease(t, at + i * per, at + i * per + 0.9, Easing.inOut(Easing.cubic));
            geo.setDrawRange(0, Math.max(0, Math.round(k * segs)) * RAD * 6);
            const head = curve.getPoint(Math.max(0.001, k));
            return <group key={i}>
              <mesh geometry={geo}><meshBasicMaterial color={hex(acc)} toneMapped={false} /></mesh>
              {k > 0 && k < 1 && <Glow pos={[head.x, head.y, head.z]} size={0.55} color={[255, 255, 255]} />}
            </group>;
          })}
          {places.map((pl, i) => {
            const v = v3(pl.lat, pl.lon), vo = v3(pl.lat, pl.lon, R + 0.3);
            const ai = arcs.findIndex((a) => a[1] === i), on = i === 0 ? ease(t, 0.3, 0.7) : ai < 0 ? ease(t, 0.5, 0.9) : ease(t, at + ai * per + 0.8, at + ai * per + 1.1);
            return <group key={i}>
              <Glow pos={[v.x, v.y, v.z]} size={0.42 + 0.1 * Math.sin(t * 4 + i)} color={acc} opacity={on} />
              <Label text={pl.label} pos={[vo.x, vo.y, vo.z]} h={0.22} opacity={on} bg="rgba(12,16,34,0.85)" size={56} />
            </group>;
          })}
        </group>
      </ThreeCanvas>
      <Vignette />
      <Title p={p} title={p.title} sub={p.sub} accent={acc} t={t} />
    </AbsoluteFill>
  );
};

const mix3 = (a: RGB, b: RGB, k: number): RGB => [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * k)) as RGB;
