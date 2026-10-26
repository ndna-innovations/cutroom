// Marks on top of footage: Highlight (ring / box / spotlight / underline), Callout arrow, Timer.
import React from "react";
import { AbsoluteFill, Easing, Img, interpolate } from "remotion";
import { Base, PALETTE, colorOf, ease, fonts, life, rgb, sp, useT, useTheme } from "./lib";
import { outFade } from "./lib";

/** Draws attention to a box (design px). style: ring (rounded outline drawn on + glow), box (soft fill + outline),
 * spotlight (everything else dims), underline (marker stroke). {box:[x,y,w,h], style, color, delay, label} */
export const Highlight: React.FC<Base & { box: [number, number, number, number]; track?: [number, number, number, number, number][] | null; style?: string; color?: string; delay?: number; label?: string; pulse?: boolean }> = (p) => {
  const { t, fps, W, H, D } = useT(); const th = useTheme(p); const F = fonts(p); const c = colorOf(p.color, th);
  const tb = p.track && p.track.length ? p.track[Math.min(p.track.length - 1, Math.max(0, Math.round(t * 30)))] : null;   // follows moving content
  const [x, y, w, h] = tb ? [tb[1], tb[2], tb[3], tb[4]] : p.box; const at = p.delay ?? 0.0; const style = p.style || "ring";
  const k = ease(t - at, 0, 0.45, Easing.out(Easing.cubic));
  const out = outFade(p, t, D, 0.2);
  if (t < at) return null;
  const r = Math.min(24, h / 3);
  const per = 2 * (w + h);
  const pulse = p.pulse === false ? 0 : 0.5 + 0.5 * Math.sin((t - at) * 4);
  if (style === "spotlight") {
    return <AbsoluteFill style={{ opacity: out }}>
      <svg width={W} height={H} style={{ position: "absolute" }}><defs><mask id="m"><rect width={W} height={H} fill="white" />
        <rect x={x - 12} y={y - 12} width={w + 24} height={h + 24} rx={r} fill="black" /></mask></defs>
        <rect width={W} height={H} fill={`rgba(0,0,0,${0.55 * k})`} mask="url(#m)" /></svg>
      <div style={{ position: "absolute", left: x - 12, top: y - 12, width: w + 24, height: h + 24, borderRadius: r, border: `4px solid ${rgb(c, k)}`, boxShadow: `0 0 40px ${rgb(c, 0.6 * k)}` }} />
    </AbsoluteFill>;
  }
  if (style === "underline") {
    const uw = w * k;
    return <AbsoluteFill style={{ opacity: out }}><div style={{ position: "absolute", left: x, top: y + h + 4, width: uw, height: Math.max(8, h * 0.12), borderRadius: 6,
      background: rgb(c), boxShadow: `0 0 20px ${rgb(c, 0.7)}` }} /></AbsoluteFill>;
  }
  return (
    <AbsoluteFill style={{ opacity: out }}>
      {style === "box" && <div style={{ position: "absolute", left: x - 10, top: y - 10, width: w + 20, height: h + 20, borderRadius: r, background: rgb(c, 0.16 * k) }} />}
      <svg width={W} height={H} style={{ position: "absolute", overflow: "visible" }}>
        <rect x={x - 10} y={y - 10} width={w + 20} height={h + 20} rx={r} fill="none" stroke={rgb(c, 0.35 + 0.15 * pulse)} strokeWidth={22} style={{ filter: "blur(10px)" }}
          strokeDasharray={per + 200} strokeDashoffset={(per + 200) * (1 - k)} />
        <rect x={x - 10} y={y - 10} width={w + 20} height={h + 20} rx={r} fill="none" stroke={rgb([255, 255, 255], 0.95)} strokeWidth={9}
          strokeDasharray={per + 200} strokeDashoffset={(per + 200) * (1 - k)} />
        <rect x={x - 10} y={y - 10} width={w + 20} height={h + 20} rx={r} fill="none" stroke={rgb(c)} strokeWidth={5}
          strokeDasharray={per + 200} strokeDashoffset={(per + 200) * (1 - k)} />
      </svg>
      {p.label && <div style={{ position: "absolute", left: x + w / 2, top: y - 24, transform: `translate(-50%,-100%) scale(${sp(t, at + 0.3, fps, { damping: 12 })})`, padding: "10px 24px",
        borderRadius: 30, background: rgb(c), color: rgb(PALETTE.ink), fontFamily: F.body, fontWeight: 800, fontSize: 32, whiteSpace: "nowrap" }}>{p.label}</div>}
    </AbsoluteFill>
  );
};

/** Arrow + label pointing at a point. {point:[x,y], text, from:[x,y], color} */
export const Callout: React.FC<Base & { point: [number, number]; text: string; from?: [number, number]; color?: string }> = (p) => {
  const { t, fps, W, H, D } = useT(); const th = useTheme(p); const F = fonts(p); const c = colorOf(p.color, th);
  const [px, py] = p.point; const [fx, fy] = p.from || [px + 260, py - 200];
  const k = ease(t, 0, 0.5); const lk = sp(t, 0.35, fps, { damping: 13 }); const out = outFade(p, t, D, 0.2);
  const ex = fx + (px - fx) * k, ey = fy + (py - fy) * k; const ang = Math.atan2(py - fy, px - fx);
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <svg width={W} height={H} style={{ position: "absolute" }}>
        <line x1={fx} y1={fy} x2={ex} y2={ey} stroke={rgb(c)} strokeWidth={8} strokeLinecap="round" />
        {k > 0.95 && <polygon points={`${px},${py} ${px - 34 * Math.cos(ang - 0.45)},${py - 34 * Math.sin(ang - 0.45)} ${px - 34 * Math.cos(ang + 0.45)},${py - 34 * Math.sin(ang + 0.45)}`} fill={rgb(c)} />}
      </svg>
      <div style={{ position: "absolute", left: fx, top: fy, transform: `translate(-50%,-120%) scale(${lk})`, padding: "14px 30px", borderRadius: 36, background: rgb(c),
        color: rgb(PALETTE.ink), fontFamily: F.body, fontSize: 38, fontWeight: 800, whiteSpace: "nowrap" }}>{p.text}</div>
    </AbsoluteFill>
  );
};

/** Stopwatches that run and freeze on a done label. {timers:[{x, y, label, color, from, until, rate, done}]} (seconds of the clip) */
export const Timer: React.FC<Base & { timers: { x: number; y: number; label?: string; color?: string; from?: number; until: number; rate?: number; done?: string }[] }> = (p) => {
  const { t, fps } = useT(); const th = useTheme(p); const F = fonts(p);
  return (
    <AbsoluteFill style={{ fontFamily: F.mono }}>
      {p.timers.map((m, i) => { const c = colorOf(m.color, th); const run = Math.max(0, Math.min(t, m.until) - (m.from || 0)) * (m.rate || 1);
        const fin = t >= m.until; const mm = Math.floor(run / 60), ss = Math.floor(run % 60);
        return <div key={i} style={{ position: "absolute", left: m.x, top: m.y, transform: `translate(-50%,-50%) scale(${fin ? 1 + 0.08 * (1 - ease(t, m.until, m.until + 0.4)) : 1})`,
          padding: "12px 28px", borderRadius: 18, background: "rgba(8,10,24,0.88)", border: `3px solid ${rgb(c)}`, color: rgb(fin ? c : th.text), fontSize: 46, fontWeight: 800,
          boxShadow: fin ? `0 0 34px ${rgb(c, 0.7)}` : "none", whiteSpace: "nowrap" }}>
          {m.label ? <span style={{ fontFamily: F.body, fontSize: 28, marginRight: 14, color: rgb(c) }}>{m.label}</span> : null}
          {fin && m.done ? m.done : `${mm}:${String(ss).padStart(2, "0")}`}</div>; })}
    </AbsoluteFill>
  );
};

/** Thin progress bar along the top of a Short. {y, height, color} */
export const Progress: React.FC<Base & { y?: number; height?: number; color?: string }> = (p) => {
  const { t, W, D } = useT(); const th = useTheme(p); const c = colorOf(p.color, th);
  const k = Math.min(1, t / Math.max(0.01, D));
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 0, top: p.y ?? 0, width: W, height: p.height ?? 10, background: "rgba(255,255,255,0.12)" }} />
      <div style={{ position: "absolute", left: 0, top: p.y ?? 0, width: W * k, height: p.height ?? 10, background: rgb(c), boxShadow: `0 0 16px ${rgb(c, 0.8)}` }} />
    </AbsoluteFill>
  );
};

/** His mouse pointer + click rings from a recorded track (Cap's cursor.json, mapped to the screen view by the engine).
 * {track: [[t, x, y, id]...] at 30 fps, clicks: [[t, x, y]...], images: {id: url}, size, color} */
export const Cursor: React.FC<Base & { track: [number, number, number, string][]; clicks?: [number, number, number][]; images: Record<string, string>; size?: number; color?: string }> = (p) => {
  const { t } = useT(); const th = useTheme(p); const c = colorOf(p.color, th);
  const tr = p.track || []; if (!tr.length) return null;
  const i = Math.min(tr.length - 1, Math.max(0, Math.round(t * 30)));
  const [, x, y, id] = tr[i]; const size = p.size ?? 44;
  return (
    <AbsoluteFill>
      {(p.clicks || []).map(([ct, cx, cy], k) => { const u = t - ct; if (u < 0 || u > 0.8) return null; const e = ease(u, 0, 0.8);
        return <div key={k} style={{ position: "absolute", left: cx - 30 - 40 * e, top: cy - 30 - 40 * e, width: 60 + 80 * e, height: 60 + 80 * e, borderRadius: "50%",
          border: `5px solid rgba(255,255,255,${0.9 * (1 - e)})`, background: rgb(c, 0.35 * (1 - e)), boxShadow: `0 0 20px ${rgb(c, 0.6 * (1 - e))}` }} />; })}
      {p.images[id] && <Img src={p.images[id]} style={{ position: "absolute", left: x, top: y, height: size, filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.6))" }} />}
    </AbsoluteFill>
  );
};
