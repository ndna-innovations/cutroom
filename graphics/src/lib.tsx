// Shared design system for every template: time in SECONDS (so supersampled motion blur works at any fps),
// springs, easing, theme colours from the engine, glow, stamps, panels, particles.
import React from "react";
import { AbsoluteFill, Img, interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { noise2D } from "@remotion/noise";

export type RGB = [number, number, number];
export type Theme = { bg: RGB; accent: RGB; text: RGB; [k: string]: RGB };
export type Base = { _theme?: Theme; _kit?: { font?: string; display?: string; mono?: string; style?: string } };

export const rgb = (c: RGB, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
export const mix = (a: RGB, b: RGB, t: number): RGB => [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * t)) as RGB;

export const PALETTE = {
  green: [60, 214, 135] as RGB,
  red: [240, 84, 84] as RGB,
  gold: [255, 196, 64] as RGB,
  blue: [90, 155, 255] as RGB,
  claude: [232, 128, 90] as RGB,
  white: [255, 255, 255] as RGB,
  dim: [160, 170, 210] as RGB,
  ink: [10, 12, 26] as RGB,
};

export const useTheme = (p: Base): Theme =>
  (p._theme as Theme) || { bg: [8, 10, 24], accent: [245, 158, 11], text: [255, 255, 255] };

export const colorOf = (c: string | RGB | undefined, th: Theme): RGB => {
  if (!c) return th.accent;
  if (Array.isArray(c)) return c as RGB;
  if (c === "accent") return th.accent;
  if (c === "text") return th.text;
  return (PALETTE as any)[c] || th[c] || th.accent;
};

export const fonts = (p: Base) => ({
  body: p._kit?.font || "'Avenir Next', 'SF Pro Display', 'Helvetica Neue', sans-serif",
  display: p._kit?.display || "'Avenir Next', 'SF Pro Display', 'Helvetica Neue', sans-serif",
  mono: p._kit?.mono || "'SF Mono', Menlo, monospace",
});

/** current time in seconds and the canvas in design units */
export const useT = () => {
  const f = useCurrentFrame();
  const { fps, width, height, durationInFrames, props } = useVideoConfig() as any;
  const t0 = (props && props._t0) || 0;      // start part-way through (a Short that picks up mid-graphic)
  // board: a near-square box in a phone frame (a Short's top half, ~1040x940 design units): templates lay out big rows that fill it
  return { t: f / fps + t0, fps, W: width, H: height, D: durationInFrames / fps + t0, tall: height > width * 1.2, board: !(height > width * 1.2) && width <= 1300 };
};

/** spring that starts at `at` seconds (0 -> 1), fps independent */
export const sp = (t: number, at: number, fps: number, cfg: { damping?: number; stiffness?: number; mass?: number } = {}) =>
  t < at ? 0 : spring({ frame: (t - at) * fps, fps, config: { damping: 14, stiffness: 160, mass: 0.9, ...cfg } });

export const ease = (t: number, a: number, b: number, fn: (x: number) => number = Easing.out(Easing.cubic)) =>
  interpolate(t, [a, b], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: fn });

/** fade in at `a`, out before the end (`out` seconds), smooth */
export const life = (t: number, D: number, a = 0, inD = 0.25, out = 0.3) =>
  Math.min(ease(t, a, a + inD), 1 - ease(t, D - out, D, Easing.in(Easing.cubic)));

export const Glow: React.FC<{ color: RGB; size: number; x: number; y: number; alpha?: number }> = ({ color, size, x, y, alpha = 0.55 }) => (
  <div style={{ position: "absolute", left: x - size / 2, top: y - size / 2, width: size, height: size, borderRadius: "50%",
    background: `radial-gradient(circle, ${rgb(color, alpha)} 0%, ${rgb(color, alpha * 0.35)} 35%, rgba(0,0,0,0) 70%)` }} />
);

/** glassy panel with a gradient border */
export const Panel: React.FC<{ x: number; y: number; w: number; h: number; th: Theme; children?: React.ReactNode; r?: number; tint?: RGB; style?: React.CSSProperties }> = ({ x, y, w, h, th, children, r = 28, tint, style }) => {
  const c = tint || th.accent;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, borderRadius: r, padding: 2,
      background: `linear-gradient(135deg, ${rgb(c, 0.85)}, ${rgb(c, 0.15)} 45%, ${rgb([255, 255, 255], 0.18)})`,
      boxShadow: `0 30px 80px rgba(0,0,0,0.55), 0 0 60px ${rgb(c, 0.18)}`, ...style }}>
      <div style={{ width: "100%", height: "100%", borderRadius: r - 2, overflow: "hidden", position: "relative",
        background: `linear-gradient(160deg, ${rgb(mix(th.bg, [40, 46, 90], 0.55), 0.96)}, ${rgb(th.bg, 0.97)})` }}>{children}</div>
    </div>
  );
};

export const Stamp: React.FC<{ text: string; color: RGB; t: number; at: number; fps: number; x: number; y: number; size?: number; rot?: number; font: string }> =
  ({ text, color, t, at, fps, x, y, size = 64, rot = -8, font }) => {
    if (t < at) return null;
    const s = sp(t, at, fps, { damping: 9, stiffness: 260 });
    const scale = interpolate(s, [0, 1], [2.6, 1]);
    const op = ease(t, at, at + 0.06);
    return (
      <div style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,-50%) rotate(${rot}deg) scale(${scale})`, opacity: op,
        border: `${size * 0.09}px solid ${rgb(color)}`, borderRadius: size * 0.22, padding: `${size * 0.1}px ${size * 0.35}px`,
        color: rgb(color), fontFamily: font, fontWeight: 900, fontSize: size, letterSpacing: size * 0.06, whiteSpace: "nowrap",
        boxShadow: `0 0 ${size * 0.6}px ${rgb(color, 0.45)}, inset 0 0 ${size * 0.3}px ${rgb(color, 0.25)}`,
        textShadow: `0 0 ${size * 0.3}px ${rgb(color, 0.6)}`, background: rgb([0, 0, 0], 0.25) }}>{text}</div>
    );
  };

/** sparks bursting from a point (deterministic) */
export const Sparks: React.FC<{ x: number; y: number; t: number; at: number; color: RGB; n?: number; reach?: number; seed?: string }> =
  ({ x, y, t, at, color, n = 26, reach = 420, seed = "s" }) => {
    const u = t - at;
    if (u < 0 || u > 1.2) return null;
    const items = [];
    for (let i = 0; i < n; i++) {
      const ang = (i / n) * Math.PI * 2 + noise2D(seed, i, 0.3) * 0.6;
      const sp_ = 0.55 + 0.45 * (noise2D(seed, i, 1.7) * 0.5 + 0.5);
      const d = reach * sp_ * (1 - Math.pow(1 - Math.min(u / 0.9, 1), 3));
      const len = 40 * (1 - u) + 6;
      const op = Math.max(0, 1 - u / 1.0);
      items.push(<div key={i} style={{ position: "absolute", left: x + Math.cos(ang) * d, top: y + Math.sin(ang) * d, width: len, height: 4,
        borderRadius: 2, background: rgb(color, op), transform: `translate(-50%,-50%) rotate(${ang}rad)`, boxShadow: `0 0 12px ${rgb(color, op)}` }} />);
    }
    return <>{items}</>;
  };

export const Shockwave: React.FC<{ x: number; y: number; t: number; at: number; color: RGB; size?: number }> = ({ x, y, t, at, color, size = 900 }) => {
  const u = t - at;
  if (u < 0 || u > 0.9) return null;
  const k = ease(u, 0, 0.9);
  const s = size * k;
  return <div style={{ position: "absolute", left: x - s / 2, top: y - s / 2, width: s, height: s, borderRadius: "50%",
    border: `${10 * (1 - k) + 1}px solid ${rgb(color, 1 - k)}`, boxShadow: `0 0 40px ${rgb(color, 0.6 * (1 - k))}` }} />;
};

/** diagonal light sweep across a box */
export const Sweep: React.FC<{ t: number; at: number; dur?: number }> = ({ t, at, dur = 0.7 }) => {
  const k = ease(t, at, at + dur, Easing.inOut(Easing.cubic));
  if (k <= 0 || k >= 1) return null;
  return <AbsoluteFill style={{ background: `linear-gradient(105deg, rgba(255,255,255,0) ${k * 140 - 40}%, rgba(255,255,255,0.22) ${k * 140 - 25}%, rgba(255,255,255,0) ${k * 140 - 10}%)` }} />;
};

export const Icon: React.FC<{ src?: string; size: number; style?: React.CSSProperties }> = ({ src, size, style }) =>
  src ? <Img src={src} style={{ width: size, height: size, objectFit: "contain", ...style }} /> : null;

/** animated background: deep gradient + drifting grid + soft glows; `style` picks the variant */
export const Backdrop: React.FC<{ th: Theme; t: number; variant?: string; W: number; H: number }> = ({ th, t, variant = "grid", W, H }) => {
  const c = th.accent;
  const drift = (t * 18) % 90;
  return (
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 30% 20%, ${rgb(mix(th.bg, c, 0.16))} 0%, ${rgb(th.bg)} 60%)` }}>
      {variant === "grid" && (
        <AbsoluteFill style={{ backgroundImage: `linear-gradient(${rgb([255, 255, 255], 0.06)} 2px, transparent 2px), linear-gradient(90deg, ${rgb([255, 255, 255], 0.06)} 2px, transparent 2px)`,
          backgroundSize: "90px 90px", backgroundPosition: `${drift}px ${drift}px` }} />
      )}
      {variant === "grid" && Array.from({ length: Math.round(W * H / 90000) }, (_, i) => {
        // a few grid squares light up and fade, slowly and out of step: alive, never pulling focus
        const r = (k: number) => { const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); };
        const cols = Math.ceil(W / 90) + 1, rows = Math.ceil(H / 90) + 1;
        const cx = Math.floor(r(1) * cols), cy = Math.floor(r(2) * rows);
        const ph = r(3) * Math.PI * 2, sp_ = 0.35 + r(4) * 0.35;
        const a = Math.pow(Math.max(0, Math.sin(t * sp_ + ph)), 3) * 0.16;
        if (a < 0.004) return null;
        return <div key={i} style={{ position: "absolute", left: cx * 90 + drift - 90, top: cy * 90 + drift - 90, width: 88, height: 88,
          background: rgb(mix(c, [255, 255, 255], 0.35), a), boxShadow: `0 0 40px ${rgb(c, a * 1.6)}`, borderRadius: 4 }} />;
      })}
      {variant === "dots" && (
        <AbsoluteFill style={{ backgroundImage: `radial-gradient(${rgb([255, 255, 255], 0.08)} 2px, transparent 2.5px)`, backgroundSize: "48px 48px", backgroundPosition: `${drift / 2}px 0px` }} />
      )}
      <Glow color={c} size={W * 0.9} x={W * (0.8 + 0.04 * Math.sin(t * 0.7))} y={H * 0.9} alpha={0.22} />
      <Glow color={mix(c, [90, 120, 255], 0.6)} size={W * 0.7} x={W * 0.1} y={H * (0.15 + 0.03 * Math.cos(t * 0.5))} alpha={0.16} />
    </AbsoluteFill>
  );
};

/** number that counts up with an ease */
export const count = (t: number, at: number, dur: number, to: number, from = 0) => from + (to - from) * ease(t, at, at + dur, Easing.out(Easing.quad));

export const fmt = (v: number, decimals = 0) => v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

/** end fade: only for overlays (props._alpha); solid full-screen cards never fade to black (house rule) */
export const outFade = (p: any, t: number, D: number, d = 0.25) => (p && p._alpha ? 1 - ease(t, D - d, D, Easing.in(Easing.cubic)) : 1);

/** font size that fits `text` in `maxW` px (estimate: 0.56 em per character for bold sans), between min and size */
export const fit = (text: string, maxW: number, size: number, min = size * 0.6) => Math.max(min, Math.min(size, maxW / Math.max(1, text.length * 0.56)));

/** the rounded dark card a board template draws on (its own background, readable over anything) */
export const BoardCard: React.FC<{ W: number; H: number }> = ({ W, H }) => (
  <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, borderRadius: 40, background: "rgba(10,12,30,0.94)", border: "3px solid rgba(70,80,140,1)", boxSizing: "border-box" }} />
);
