// Drawn explainer scenes (illustrations that act out an idea) + the backdrop behind floating screen windows.
// StageBackdrop, ModelLadder, SafetySwitch, CloudTrap. All lay out from W/H, so they work full-frame or inside a box.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import { Base, Glow, PALETTE, RGB, ease, fonts, mix, rgb, sp, useT, useTheme, outFade } from "./lib";

/** Animated backdrop for screen recordings shown as floating windows: aurora glows drifting, a dot grid, a perspective
 * floor and a slow light sweep. {variant: aurora|calm} */
export const StageBackdrop: React.FC<Base & { variant?: string }> = (p) => {
  const { t, W, H } = useT(); const th = useTheme(p);
  const a = th.accent, b: RGB = [86, 110, 255], c: RGB = [40, 190, 200];
  const sweep = ((t * 0.06) % 1.4) - 0.2;
  return (
    <AbsoluteFill style={{ background: `linear-gradient(160deg, ${rgb(mix(th.bg, b, 0.16))} 0%, ${rgb(th.bg)} 55%, ${rgb(mix(th.bg, a, 0.1))} 100%)`, overflow: "hidden" }}>
      <Glow color={b} size={W * 0.9} x={W * (0.22 + 0.06 * Math.sin(t * 0.21))} y={H * (0.18 + 0.05 * Math.cos(t * 0.17))} alpha={0.26} />
      <Glow color={a} size={W * 0.8} x={W * (0.86 + 0.05 * Math.cos(t * 0.19))} y={H * (0.92 + 0.04 * Math.sin(t * 0.23))} alpha={0.22} />
      <Glow color={c} size={W * 0.5} x={W * (0.55 + 0.1 * Math.sin(t * 0.13 + 1))} y={H * (0.5 + 0.08 * Math.cos(t * 0.11))} alpha={0.1} />
      <AbsoluteFill style={{ backgroundImage: `radial-gradient(${rgb([255, 255, 255], 0.07)} 1.6px, transparent 2px)`, backgroundSize: "44px 44px",
        backgroundPosition: `${(t * 6) % 44}px ${(t * 3) % 44}px`, maskImage: "radial-gradient(ellipse at 50% 40%, black 20%, transparent 75%)" }} />
      <div style={{ position: "absolute", left: -W * 0.25, right: -W * 0.25, top: H * 0.72, height: H * 0.6, transform: "perspective(900px) rotateX(62deg)", transformOrigin: "50% 0%",
        backgroundImage: `linear-gradient(${rgb(a, 0.16)} 2px, transparent 2px), linear-gradient(90deg, ${rgb(a, 0.16)} 2px, transparent 2px)`,
        backgroundSize: "110px 110px", backgroundPosition: `0px ${(t * 30) % 110}px`, maskImage: "linear-gradient(transparent, black 30%, transparent)" }} />
      <div style={{ position: "absolute", top: 0, bottom: 0, left: `${sweep * 100}%`, width: W * 0.18, transform: "skewX(-18deg)",
        background: `linear-gradient(90deg, transparent, ${rgb([255, 255, 255], 0.035)}, transparent)` }} />
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ icons (drawn, no emoji)
const Ico: React.FC<{ kind: string; size: number; color: RGB }> = ({ kind, size, color }) => {
  const c = rgb(color); const s = { width: size, height: size };
  if (kind === "crown") return <svg viewBox="0 0 64 64" style={s}><path d="M8 46 L12 18 L24 32 L32 12 L40 32 L52 18 L56 46 Z" fill={c} /><rect x="8" y="49" width="48" height="7" rx="3" fill={c} /></svg>;
  if (kind === "brain") return <svg viewBox="0 0 64 64" style={s}><path d="M26 10c-6 0-10 4-10 9-5 1-8 5-8 10 0 3 1 6 4 8-1 6 3 11 9 11 2 4 6 6 10 6V10h-5zm12 0c6 0 10 4 10 9 5 1 8 5 8 10 0 3-1 6-4 8 1 6-3 11-9 11-2 4-6 6-10 6V10h5z" fill={c} /></svg>;
  if (kind === "bolt") return <svg viewBox="0 0 64 64" style={s}><path d="M36 4 L12 36 H30 L26 60 L52 26 H34 Z" fill={c} /></svg>;
  if (kind === "feather") return <svg viewBox="0 0 64 64" style={s}><path d="M54 8C34 8 16 24 14 46l-6 10 4 2 6-10c22-2 36-20 36-40zM20 44c4-12 12-22 24-28-8 8-14 18-18 30z" fill={c} /></svg>;
  if (kind === "shield") return <svg viewBox="0 0 64 64" style={s}><path d="M32 4 L54 12 V30 C54 44 44 54 32 60 C20 54 10 44 10 30 V12 Z" fill={c} /><path d="M22 32 L29 39 L43 24" stroke={rgb(PALETTE.ink)} strokeWidth="6" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>;
  if (kind === "file") return <svg viewBox="0 0 48 60" style={{ width: size * 0.8, height: size }}><path d="M4 4h26l14 14v38H4z" fill={c} /><path d="M30 4v14h14" fill={rgb([255, 255, 255], 0.35)} />
    <rect x="11" y="28" width="26" height="4" rx="2" fill={rgb(PALETTE.ink, 0.35)} /><rect x="11" y="37" width="20" height="4" rx="2" fill={rgb(PALETTE.ink, 0.35)} /></svg>;
  if (kind === "cloud") return <svg viewBox="0 0 96 64" style={{ width: size * 1.5, height: size }}><path d="M26 58C13 58 4 50 4 39s9-18 19-18c3-11 13-18 25-18 15 0 26 11 27 25 9 1 17 8 17 16 0 8-7 14-16 14z" fill={c} /></svg>;
  return null;
};

const Folder: React.FC<{ w: number; color: RGB; glow?: number; label?: string; dashed?: boolean; F: any }> = ({ w, color, glow = 0, label, dashed, F }) => (
  <div style={{ position: "relative", width: w, height: w * 0.74 }}>
    <svg viewBox="0 0 100 74" style={{ width: w, height: w * 0.74, filter: glow ? `drop-shadow(0 0 ${30 * glow}px ${rgb(color, 0.8)})` : undefined }}>
      <path d="M4 10 Q4 4 10 4 H38 L46 12 H90 Q96 12 96 18 V66 Q96 72 90 72 H10 Q4 72 4 66 Z" fill={dashed ? "none" : rgb(mix(color, [0, 0, 0], 0.25))}
        stroke={rgb(color)} strokeWidth={dashed ? 2.5 : 0} strokeDasharray={dashed ? "6 5" : undefined} />
      {!dashed && <path d="M4 24 Q4 20 10 20 H90 Q96 20 96 26 V66 Q96 72 90 72 H10 Q4 72 4 66 Z" fill={rgb(color)} />}
    </svg>
    {label && <div style={{ position: "absolute", left: 0, right: 0, top: w * 0.36, textAlign: "center", color: rgb(PALETTE.ink), fontFamily: F.display, fontWeight: 900, fontSize: w * 0.1 }}>{label}</div>}
  </div>
);

/** Which model when: a power ladder. Each model lands on its cue; the current one glows, the others step back.
 * {title, items:[{name, sub, icon: crown|brain|bolt|feather, power 0-1, at}]} */
export const ModelLadder: React.FC<Base & { title?: string; items: { name: string; sub?: string; icon?: string; power?: number; at: number }[]; transparent?: boolean }> = (p) => {
  const { t, fps, W, H, D } = useT(); const th = useTheme(p); const F = fonts(p);
  const n = p.items.length; const top = p.title ? H * 0.17 : H * 0.05; const gap = H * 0.025;
  const rowH = (H - top - H * 0.04 - gap * (n - 1)) / n;
  const cur = p.items.reduce((k, it, i) => (t >= it.at ? i : k), -1);
  const cols: RGB[] = [PALETTE.gold, PALETTE.claude, PALETTE.blue, PALETTE.green];
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade(p, t, D) }}>
      {p.title && <div style={{ position: "absolute", top: H * 0.03, left: W * 0.05, color: rgb(th.accent), fontSize: H * 0.075, fontWeight: 900, letterSpacing: 5,
        opacity: ease(t, 0, 0.4), transform: `translateY(${(1 - ease(t, 0, 0.5)) * -30}px)` }}>{p.title}</div>}
      {p.items.map((it, i) => {
        const k = sp(t, it.at, fps, { damping: 13, stiffness: 170 }); const on = i === cur; const past = i < cur;
        const col = cols[i % cols.length]; const focus = sp(t, it.at, fps, { damping: 20 }) * (on ? 1 : 0);
        const fill = interpolate(t, [it.at + 0.15, it.at + 0.9], [0, it.power ?? 1 - i * 0.22], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
        const indent = W * 0.05 + i * W * 0.035;
        return <div key={i} style={{ position: "absolute", left: indent, right: W * 0.05, top: top + i * (rowH + gap), height: rowH, opacity: k * (past ? 0.5 : 1),
          transform: `translateX(${(1 - k) * W * 0.25}px) scale(${1 + 0.035 * focus})`, transformOrigin: "left center",
          borderRadius: rowH * 0.28, background: `linear-gradient(90deg, ${rgb(mix(PALETTE.ink, col, on ? 0.28 : 0.12), 0.95)}, ${rgb(PALETTE.ink, 0.88)})`,
          border: `${on ? 4 : 2}px solid ${rgb(col, on ? 0.95 : 0.3)}`, boxShadow: on ? `0 0 ${50 * focus}px ${rgb(col, 0.55)}` : "none",
          display: "flex", alignItems: "center", gap: rowH * 0.28, padding: `0 ${rowH * 0.3}px` }}>
          <div style={{ transform: `rotate(${(1 - k) * -40}deg) scale(${0.6 + 0.4 * k})` }}><Ico kind={it.icon || "bolt"} size={rowH * 0.56} color={col} /></div>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: rowH * 0.2 }}>
              <div style={{ color: rgb(PALETTE.white), fontSize: rowH * 0.36, fontWeight: 900 }}>{it.name}</div>
              {it.sub && <div style={{ color: rgb(PALETTE.dim), fontSize: rowH * 0.2, fontWeight: 700 }}>{it.sub}</div>}
            </div>
            <div style={{ marginTop: rowH * 0.08, height: rowH * 0.1, borderRadius: rowH, background: rgb([255, 255, 255], 0.08), overflow: "hidden" }}>
              <div style={{ width: `${fill * 100}%`, height: "100%", borderRadius: rowH, background: `linear-gradient(90deg, ${rgb(col, 0.6)}, ${rgb(col)})`, boxShadow: `0 0 20px ${rgb(col, 0.8)}` }} />
            </div>
          </div>
        </div>;
      })}
    </AbsoluteFill>
  );
};

/** The safety switch: a big toggle slides from AUTO to MANUAL, a shield lands, then an "Allow?" request pops up.
 * {title, switch_at, sub, sub_at, ask, ask_at} */
export const SafetySwitch: React.FC<Base & { title?: string; switch_at?: number; sub?: string; sub_at?: number; ask?: string; ask_at?: number }> = (p) => {
  const { t, fps, W, H, D } = useT(); const th = useTheme(p); const F = fonts(p);
  const sw = sp(t, p.switch_at ?? 0.6, fps, { damping: 12, stiffness: 200 });
  const tw = Math.min(W * 0.62, H * 1.1), thh = tw * 0.3; const tx = W * 0.07, ty = H * 0.22;
  const col = mix(PALETTE.dim, PALETTE.green, sw);
  const sk = sp(t, (p.switch_at ?? 0.6) + 0.15, fps, { damping: 9, stiffness: 220 });
  const ask = sp(t, p.ask_at ?? 99, fps, { damping: 14 });
  const nSub = Math.floor(Math.max(0, t - (p.sub_at ?? 1.4)) * 38);
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade(p, t, D) }}>
      {p.title && <div style={{ position: "absolute", top: H * 0.03, left: W * 0.07, color: rgb(th.accent), fontSize: H * 0.075, fontWeight: 900, letterSpacing: 5, opacity: ease(t, 0, 0.4) }}>{p.title}</div>}
      <div style={{ position: "absolute", left: tx, top: ty, width: tw, height: thh, borderRadius: thh, background: rgb(mix(PALETTE.ink, col, 0.35)),
        border: `4px solid ${rgb(col)}`, boxShadow: `0 0 ${60 * sw}px ${rgb(PALETTE.green, 0.5)}, inset 0 4px 20px rgba(0,0,0,0.5)`, opacity: ease(t, 0, 0.3) }}>
        <div style={{ position: "absolute", right: thh * 0.4, top: 0, bottom: 0, display: "flex", alignItems: "center", color: rgb(PALETTE.dim, Math.max(0, 1 - 2 * sw)), fontSize: thh * 0.34, fontWeight: 900 }}>AUTO</div>
        <div style={{ position: "absolute", left: thh * 0.4, top: 0, bottom: 0, display: "flex", alignItems: "center", color: rgb(PALETTE.white, Math.max(0, 2 * sw - 1)), fontSize: thh * 0.34, fontWeight: 900, letterSpacing: 3 }}>MANUAL</div>
        <div style={{ position: "absolute", top: thh * 0.08, left: thh * 0.08 + sw * (tw - thh * 1.0), width: thh * 0.84 - 8, height: thh * 0.84 - 8, borderRadius: thh,
          background: `radial-gradient(circle at 35% 30%, #fff, ${rgb(mix(PALETTE.white, col, 0.4))})`, boxShadow: "0 6px 18px rgba(0,0,0,0.5)" }} />
      </div>
      <div style={{ position: "absolute", left: tx + tw + W * 0.04, top: ty - thh * 0.15, transform: `scale(${sk}) rotate(${(1 - sk) * 30}deg)`, filter: `drop-shadow(0 0 30px ${rgb(PALETTE.green, 0.7)})` }}>
        <Ico kind="shield" size={thh * 1.3} color={PALETTE.green} /></div>
      {p.sub && <div style={{ position: "absolute", left: tx, top: ty + thh + H * 0.06, color: rgb(PALETTE.white), fontSize: H * 0.07, fontWeight: 800 }}>
        {p.sub.slice(0, nSub)}<span style={{ opacity: nSub < p.sub.length && t > (p.sub_at ?? 1.4) ? 1 : 0, color: rgb(th.accent) }}>▍</span></div>}
      {p.ask && <div style={{ position: "absolute", left: tx, top: ty + thh + H * 0.2, width: W * 0.84, padding: `${H * 0.03}px ${W * 0.03}px`, borderRadius: 26,
        background: rgb([24, 28, 52], 0.96), border: `2px solid ${rgb(th.accent, 0.6)}`, boxShadow: `0 20px 60px rgba(0,0,0,0.6)`, display: "flex", alignItems: "center", gap: W * 0.03,
        opacity: ask, transform: `translateY(${(1 - ask) * 60}px) scale(${0.9 + 0.1 * ask})` }}>
        <div style={{ flex: 1, color: rgb(PALETTE.white), fontSize: H * 0.05, fontWeight: 700 }}>{p.ask}</div>
        <div style={{ padding: `${H * 0.012}px ${W * 0.025}px`, borderRadius: 14, background: rgb(PALETTE.green), color: rgb(PALETTE.ink), fontSize: H * 0.045, fontWeight: 900 }}>Allow</div>
        <div style={{ padding: `${H * 0.012}px ${W * 0.02}px`, borderRadius: 14, border: `2px solid ${rgb(PALETTE.dim)}`, color: rgb(PALETTE.dim), fontSize: H * 0.045, fontWeight: 800 }}>Deny</div>
      </div>}
    </AbsoluteFill>
  );
};

/** Why not iCloud: the memory folder sits on the Mac, a cloud drifts in and lifts its files away (Claude can't read it),
 * then the folder moves to a local place and the files come home. {title, cloud_at, steal_at, local_at, local_label, bad, good} */
export const CloudTrap: React.FC<Base & { title?: string; cloud_at?: number; steal_at?: number; local_at?: number; local_label?: string; bad?: string; good?: string }> = (p) => {
  const { t, fps, W, H, D } = useT(); const th = useTheme(p); const F = fonts(p);
  const cA = p.cloud_at ?? 0.5, sA = p.steal_at ?? 1.6, lA = p.local_at ?? 99;
  const fw = Math.min(W * 0.3, H * 0.55); const fx = W * 0.12, fy = H * 0.42;
  const cloudIn = sp(t, cA, fps, { damping: 16 }) * (1 - ease(t, lA, lA + 0.6));
  const local = sp(t, lA, fps, { damping: 14 });
  const fileCol = mix(PALETTE.dim, PALETTE.white, 0.6);
  const cx = W * 0.62, cy = H * 0.16;
  const bad = sp(t, sA + 1.1, fps, { damping: 12 }) * (1 - ease(t, lA, lA + 0.3));
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade(p, t, D), overflow: "hidden" }}>
      {p.title && <div style={{ position: "absolute", top: H * 0.03, left: W * 0.06, color: rgb(th.accent), fontSize: H * 0.075, fontWeight: 900, letterSpacing: 5, opacity: ease(t, 0, 0.4) }}>{p.title}</div>}
      {/* the Mac */}
      <div style={{ position: "absolute", left: fx - fw * 0.25, top: fy - fw * 0.12, width: fw * 1.5, height: fw * 0.95, borderRadius: 22, border: `4px solid ${rgb(mix(PALETTE.dim, PALETTE.green, local), 0.8)}`,
        background: rgb(PALETTE.ink, 0.7), boxShadow: local ? `0 0 ${60 * local}px ${rgb(PALETTE.green, 0.45)}` : "none" }} />
      <div style={{ position: "absolute", left: fx - fw * 0.42, top: fy + fw * 0.83, width: fw * 1.84, height: fw * 0.07, borderRadius: 10, background: rgb(PALETTE.dim, 0.5) }} />
      <div style={{ position: "absolute", left: fx, top: fy, opacity: ease(t, 0, 0.3) }}>
        <Folder w={fw} color={mix(th.accent, PALETTE.green, local)} label="Product-Brain" F={F} glow={local} /></div>
      {/* files: leave for the cloud, come back when local */}
      {[0, 1, 2].map((i) => {
        const go = ease(t, sA + i * 0.18, sA + 0.9 + i * 0.18, Easing.inOut(Easing.cubic)) * (1 - ease(t, lA + 0.2 + i * 0.12, lA + 1.0 + i * 0.12, Easing.inOut(Easing.cubic)));
        const hx = fx + fw * (0.22 + i * 0.22), hy = fy - fw * 0.18;
        const x = hx + (cx + fw * 0.2 * (i - 1) - hx) * go, y = hy + (cy + fw * 0.15 - hy) * go - Math.sin(go * Math.PI) * H * 0.12;
        return <div key={i} style={{ position: "absolute", left: x, top: y, opacity: 1 - 0.85 * go * (1 - local), transform: `rotate(${go * (i - 1) * 25}deg) scale(${1 - 0.4 * go})` }}>
          <Ico kind="file" size={fw * 0.22} color={fileCol} /></div>;
      })}
      {/* the cloud */}
      <div style={{ position: "absolute", left: cx - fw * 0.45 + (1 - cloudIn) * W * 0.5, top: cy - fw * 0.05, opacity: cloudIn, filter: `drop-shadow(0 0 30px ${rgb(PALETTE.blue, 0.6)})` }}>
        <Ico kind="cloud" size={fw * 0.62} color={mix(PALETTE.blue, PALETTE.white, 0.35)} />
        <div style={{ textAlign: "center", color: rgb(PALETTE.white), fontSize: H * 0.05, fontWeight: 900, marginTop: -fw * 0.42, position: "relative" }}>iCloud</div></div>
      {/* verdicts */}
      <div style={{ position: "absolute", left: W * 0.52, top: H * 0.66, width: W * 0.44, padding: `${H * 0.02}px ${W * 0.025}px`, borderRadius: 20, background: rgb(PALETTE.red, 0.16),
        border: `3px solid ${rgb(PALETTE.red)}`, color: rgb(PALETTE.white), fontSize: H * 0.05, fontWeight: 800, opacity: bad, transform: `scale(${0.8 + 0.2 * bad})` }}>
        <span style={{ color: rgb(PALETTE.red), fontWeight: 900 }}>✕ </span>{p.bad || "Files moved off the Mac. Claude can't read its memory."}</div>
      <div style={{ position: "absolute", left: W * 0.52, top: H * 0.6, width: W * 0.44, padding: `${H * 0.02}px ${W * 0.025}px`, borderRadius: 20, background: rgb(PALETTE.green, 0.16),
        border: `3px solid ${rgb(PALETTE.green)}`, color: rgb(PALETTE.white), fontSize: H * 0.055, fontWeight: 800, opacity: local, transform: `translateY(${(1 - local) * 40}px)` }}>
        <span style={{ color: rgb(PALETTE.green), fontWeight: 900 }}>✓ </span>{p.good || "A local folder: Developer"}
        <div style={{ color: rgb(PALETTE.dim), fontSize: H * 0.04, fontWeight: 700, marginTop: 6 }}>{p.local_label || "on this Mac · always readable"}</div></div>
    </AbsoluteFill>
  );
};

/** Light leak / film burn for "blend": "screen" layers: warm glowing streaks that sweep across and fade.
 * {variant: leak|burn|flare, color, at, dur, from: left|right} */
export const LightLeak: React.FC<Base & { variant?: string; color?: string; at?: number; dur?: number; from?: string }> = (p) => {
  const { t, W, H } = useT(); const th = useTheme(p);
  const at = p.at ?? 0, dur = p.dur ?? 1.2; const u = Math.max(0, Math.min(1, (t - at) / dur));
  const env = Math.sin(Math.PI * u); const dir = p.from === "right" ? -1 : 1;
  const warm: RGB = p.color === "cool" ? [120, 170, 255] : p.color === "accent" ? th.accent : [255, 150, 60];
  const hot: RGB = mix(warm, [255, 240, 210], 0.6);
  const x = W * (dir > 0 ? -0.3 + 1.6 * u : 1.3 - 1.6 * u);
  if (p.variant === "flare") return (
    <AbsoluteFill style={{ opacity: env }}>
      <div style={{ position: "absolute", left: x - W * 0.6, top: H * 0.35, width: W * 1.2, height: H * 0.08, borderRadius: H,
        background: `radial-gradient(ellipse, ${rgb(hot, 0.9)} 0%, ${rgb(warm, 0.35)} 35%, transparent 70%)`, filter: `blur(${H * 0.01}px)` }} />
      <div style={{ position: "absolute", left: x - H * 0.25, top: H * 0.39 - H * 0.25, width: H * 0.5, height: H * 0.5, borderRadius: H,
        background: `radial-gradient(circle, ${rgb([255, 255, 255], 0.9)} 0%, ${rgb(hot, 0.5)} 20%, transparent 60%)` }} />
    </AbsoluteFill>);
  if (p.variant === "burn") return (
    <AbsoluteFill style={{ opacity: env, background: `radial-gradient(ellipse at ${dir > 0 ? 10 + 80 * u : 90 - 80 * u}% ${60 - 20 * u}%, ${rgb(hot, 0.95)} 0%, ${rgb(warm, 0.7)} 25%, ${rgb([200, 40, 20], 0.35)} 50%, transparent 75%)`,
      filter: `blur(${H * 0.02}px)` }} />);
  return (
    <AbsoluteFill style={{ opacity: env }}>
      {[0, 1, 2].map((i) => (
        <div key={i} style={{ position: "absolute", left: x - W * (0.25 + i * 0.12), top: -H * 0.2, width: W * (0.18 + i * 0.1), height: H * 1.4,
          transform: `rotate(${18 + i * 7}deg)`, background: `linear-gradient(90deg, transparent, ${rgb(i === 1 ? hot : warm, 0.55 - i * 0.12)}, transparent)`,
          filter: `blur(${H * (0.03 + i * 0.02)}px)` }} />))}
    </AbsoluteFill>
  );
};

/** Mattes: white shapes/text on transparent, used as the alpha of a "matte" layer (video inside text or a shape).
 * {text, size, font_weight, shape: circle|rect|rounded|none, x, y (0-1), w, h (0-1 of height for circle radius), grow: seconds} */
export const Matte: React.FC<Base & { text?: string; size?: number; weight?: number; shape?: string; x?: number; y?: number; w?: number; h?: number; grow?: number; at?: number; letter?: number }> = (p) => {
  const { t, fps, W, H } = useT(); const F = fonts(p);
  const k = p.grow ? sp(t, p.at ?? 0, fps, { damping: 18, stiffness: 110 }) : 1;
  const cx = (p.x ?? 0.5) * W, cy = (p.y ?? 0.5) * H;
  return (
    <AbsoluteFill>
      {p.shape === "circle" && <div style={{ position: "absolute", left: cx - (p.w ?? 0.35) * H * k, top: cy - (p.w ?? 0.35) * H * k,
        width: 2 * (p.w ?? 0.35) * H * k, height: 2 * (p.w ?? 0.35) * H * k, borderRadius: "50%", background: "#fff" }} />}
      {(p.shape === "rect" || p.shape === "rounded") && <div style={{ position: "absolute", left: cx - (p.w ?? 0.6) * W * k / 2, top: cy - (p.h ?? 0.6) * H * k / 2,
        width: (p.w ?? 0.6) * W * k, height: (p.h ?? 0.6) * H * k, borderRadius: p.shape === "rounded" ? H * 0.05 : 0, background: "#fff" }} />}
      {p.text && <div style={{ position: "absolute", left: 0, right: 0, top: cy, transform: `translateY(-50%) scale(${0.85 + 0.15 * k})`, textAlign: "center",
        fontFamily: F.display, fontWeight: p.weight ?? 900, fontSize: p.size ?? H * 0.32, letterSpacing: p.letter ?? -4, lineHeight: 0.9, color: "#fff" }}>{p.text}</div>}
    </AbsoluteFill>
  );
};
