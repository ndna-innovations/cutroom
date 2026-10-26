// YouTube thumbnails (1280x720 design at scale 1.5 = 1920x1080 still). Layouts: face-right | face-left | center (face on
// one side or none, 2-3 big words, a badge, one proof visual) | noface (huge words left, big tool tiles stacked right).
import React from "react";
import { AbsoluteFill, Img } from "remotion";
import { Base, Glow, Icon, PALETTE, colorOf, fonts, mix, rgb, useT, useTheme } from "./lib";

export const Thumbnail: React.FC<Base & { photo?: string; lines: string[]; accent_line?: number; badge?: string; proof?: string; proof_caption?: string;
  icons?: string[]; icon_sep?: string; layout?: string; bg?: string; strike?: string; size?: number; face_scale?: number }> = (p) => {
  const { W, H } = useT(); const th = useTheme(p); const F = fonts(p);
  const right = (p.layout || "face-right") !== "face-left"; const center = p.layout === "center";
  const acc = p.accent_line ?? p.lines.length - 1; const fs = p.size ?? (p.lines.join("").length > 18 ? 128 : 156);
  const textX = center ? W * 0.06 : right ? W * 0.045 : W * 0.5;
  if (p.layout === "noface") {
    // no face: 2-3 huge words on the left (auto-fit to ~64% of the width), the tool tiles big and stacked on the right
    // (icon_sep between them), or the proof picture there; faint grid on the theme background
    const longest = Math.max(...p.lines.map((l) => l.length), 1);
    const nfs = p.size ?? Math.min(H * 0.8 / Math.max(p.lines.length, 1), (W * 0.6) / (longest * 0.8));      // heavy caps run ~0.8 em per letter
    const ic = p.icons || []; const tile = Math.min(H * 0.34, (H * 0.84) / Math.max(ic.length, 1) - 40);
    return (
      <AbsoluteFill style={{ fontFamily: F.display, background: p.bg === "light" ? "#f4f1ea" : `linear-gradient(rgba(255,255,255,0.05) 2px, transparent 2px) 0 0 / 80px 80px, linear-gradient(90deg, rgba(255,255,255,0.05) 2px, transparent 2px) 0 0 / 80px 80px, radial-gradient(ellipse at 30% 45%, ${rgb(mix(th.bg, th.accent, 0.25))} 0%, ${rgb(th.bg)} 65%)` }}>
        {p.badge && <div style={{ position: "absolute", left: W * 0.045, top: H * 0.06, padding: "10px 22px", borderRadius: 14, background: rgb(th.accent), color: rgb(PALETTE.ink),
          fontSize: 34, fontWeight: 900, letterSpacing: 2 }}>{p.badge}</div>}
        <div style={{ position: "absolute", left: W * 0.045, top: 0, height: H, width: W * 0.64, display: "flex", flexDirection: "column", justifyContent: "center",
          paddingTop: p.badge ? H * 0.08 : 0 }}>
          {p.lines.map((l, i) => <div key={i} style={{ fontSize: nfs, fontWeight: 900, lineHeight: 0.98, whiteSpace: "nowrap", color: i === acc ? rgb(th.accent) : (p.bg === "light" ? "#111" : "#fff"),
            WebkitTextStroke: p.bg === "light" ? undefined : "12px black", paintOrder: "stroke fill", textTransform: "uppercase", letterSpacing: -2,
            textDecoration: p.strike && l === p.strike ? "line-through" : undefined, textDecorationColor: rgb(PALETTE.red), textDecorationThickness: 14 }}>{l}</div>)}
        </div>
        {ic.length > 0 && <div style={{ position: "absolute", right: W * 0.05, top: 0, height: H, width: W * 0.26, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 18 }}>
          {ic.map((s, i) => <React.Fragment key={i}>{i > 0 && (p.icon_sep ?? "+") !== "" && <div style={{ color: "#fff", fontSize: tile * 0.3, lineHeight: 1, fontWeight: 900, WebkitTextStroke: "6px black", paintOrder: "stroke fill" }}>{p.icon_sep ?? "+"}</div>}
            <div style={{ width: tile, height: tile, borderRadius: tile * 0.22, background: "rgba(255,255,255,0.96)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 16px 50px rgba(0,0,0,0.55)" }}>
              <Icon src={s} size={tile * 0.72} /></div></React.Fragment>)}</div>}
        {ic.length === 0 && p.proof && <Img src={p.proof} style={{ position: "absolute", right: W * 0.04, top: H * 0.15, width: W * 0.3, borderRadius: 18, border: `6px solid ${rgb(th.accent)}`,
          boxShadow: "0 20px 60px rgba(0,0,0,0.6)", transform: "rotate(2deg)" }} />}
      </AbsoluteFill>);
  }
  return (
    <AbsoluteFill style={{ fontFamily: F.display, background: p.bg === "light" ? "#f4f1ea" : `radial-gradient(ellipse at ${right ? "75%" : "25%"} 40%, ${rgb(mix(th.bg, th.accent, 0.35))} 0%, ${rgb(th.bg)} 60%)` }}>
      <Glow color={th.accent} size={W * 0.7} x={right ? W * 0.78 : W * 0.22} y={H * 0.45} alpha={0.35} />
      {p.photo && !center && <Img src={p.photo} style={{ position: "absolute", top: H * 0.07, [right ? "right" : "left"]: -W * 0.01, height: H * (p.face_scale ?? 1.15), filter: "drop-shadow(0 0 40px rgba(0,0,0,0.6))" } as any} />}
      {p.badge && <div style={{ position: "absolute", left: textX, top: H * 0.06, padding: "10px 22px", borderRadius: 14, background: rgb(th.accent), color: rgb(PALETTE.ink),
        fontSize: 34, fontWeight: 900, letterSpacing: 2 }}>{p.badge}</div>}
      <div style={{ position: "absolute", left: textX, top: H * (p.badge ? 0.2 : 0.12), width: center ? W * 0.88 : right ? W * 0.56 : W * 0.47 }}>
        {p.lines.map((l, i) => <div key={i} style={{ fontSize: fs, fontWeight: 900, lineHeight: 0.98, color: i === acc ? rgb(th.accent) : (p.bg === "light" ? "#111" : "#fff"),
          WebkitTextStroke: p.bg === "light" ? undefined : "10px black", paintOrder: "stroke fill", textTransform: "uppercase", letterSpacing: -2,
          textDecoration: p.strike && l === p.strike ? "line-through" : undefined, textDecorationColor: rgb(PALETTE.red), textDecorationThickness: 14 }}>{l}</div>)}
      </div>
      {p.icons && <div style={{ position: "absolute", left: textX, bottom: H * 0.07, display: "flex", gap: 28, alignItems: "center" }}>
        {p.icons.map((s, i) => <React.Fragment key={i}>{i > 0 && (p.icon_sep ?? "vs") !== "" && <div style={{ color: "#fff", fontSize: 54, fontWeight: 900, WebkitTextStroke: "6px black", paintOrder: "stroke fill" }}>{p.icon_sep ?? "vs"}</div>}
          <div style={{ width: 150, height: 150, borderRadius: 34, background: "rgba(255,255,255,0.95)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 10px 40px rgba(0,0,0,0.5)" }}>
            <Icon src={s} size={110} /></div></React.Fragment>)}</div>}
      {p.proof && <div style={{ position: "absolute", left: textX, bottom: H * 0.06, width: center ? W * 0.5 : W * 0.5, transform: "rotate(-2deg)" }}>
        <Img src={p.proof} style={{ width: "100%", borderRadius: 18, border: `6px solid ${rgb(th.accent)}`, boxShadow: "0 20px 60px rgba(0,0,0,0.6)" }} />
        {p.proof_caption && <div style={{ marginTop: 10, color: "#fff", fontSize: 40, fontWeight: 800, WebkitTextStroke: "5px black", paintOrder: "stroke fill" }}>{p.proof_caption}</div>}</div>}
    </AbsoluteFill>
  );
};

/** More thumbnail designs (pick per video; the classic layout above stays the default).
 * style: poster (one giant hero word on top, face big at the bottom-right, a line under the word)
 *      | split (proof picture fills the left 62%, a tilted score stamp on it, face on the right)
 *      | warning (yellow/black hazard band with the line, red accent, face right)
 *      | repo (the proof card big and centred at the top, face bottom-right, line bottom-left)
 * {photo, lines, hero, stamp, proof, badge, bg: dark|light|indigo, face_scale} */
export const ThumbnailStyle: React.FC<Base & { style: string; photo?: string; lines: string[]; hero?: string; stamp?: string; proof?: string; badge?: string;
  bg?: string; face_scale?: number; accent_line?: number }> = (p) => {
  const { W, H } = useT(); const th = useTheme(p); const F = fonts(p);
  const light = p.bg === "light"; const ink = light ? "#111" : "#fff";
  const bgc = light ? "#f4f1ea" : p.bg === "indigo" ? "radial-gradient(ellipse at 70% 40%, #4a2c8a 0%, #1e123e 55%, #0d0820 100%)"
    : `radial-gradient(ellipse at 70% 40%, ${rgb(mix(th.bg, th.accent, 0.35))} 0%, ${rgb(th.bg)} 60%)`;
  const acc = p.accent_line ?? p.lines.length - 1;
  const stroke = light ? undefined : "10px black";
  const Line = ({ l, i, fs }: { l: string; i: number; fs: number }) => <div style={{ fontSize: fs, fontWeight: 900, lineHeight: 0.98, letterSpacing: -2, textTransform: "uppercase",
    color: i === acc ? rgb(th.accent) : ink, WebkitTextStroke: stroke, paintOrder: "stroke fill" }}>{l}</div>;
  const Face = ({ scale, x }: { scale: number; x: number }) => p.photo ? <Img src={p.photo} style={{ position: "absolute", bottom: 0, right: x, height: H * scale,
    filter: "drop-shadow(0 0 40px rgba(0,0,0,0.6))" }} /> : null;
  const Badge = () => p.badge ? <div style={{ position: "absolute", left: W * 0.045, top: H * 0.06, padding: "10px 22px", borderRadius: 14, background: rgb(th.accent),
    color: rgb(PALETTE.ink), fontSize: 34, fontWeight: 900, letterSpacing: 2 }}>{p.badge}</div> : null;
  const Stamp = ({ x, y }: { x: number; y: number }) => p.stamp ? <div style={{ position: "absolute", left: x, top: y, transform: "rotate(-8deg)", padding: "14px 34px",
    border: `12px solid ${rgb(PALETTE.red)}`, borderRadius: 22, color: rgb(PALETTE.red), background: "rgba(255,255,255,0.92)", fontSize: 150, fontWeight: 900,
    letterSpacing: -3, boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>{p.stamp}</div> : null;
  if (p.style === "poster") return (
    <AbsoluteFill style={{ fontFamily: F.display, background: bgc }}>
      <Glow color={th.accent} size={W * 0.8} x={W * 0.3} y={H * 0.3} alpha={0.35} />
      <div style={{ position: "absolute", left: W * 0.04, top: H * 0.0, fontSize: H * 0.62, fontWeight: 900, lineHeight: 1, letterSpacing: -12, color: rgb(th.accent),
        WebkitTextStroke: light ? undefined : "16px black", paintOrder: "stroke fill", textShadow: "0 20px 80px rgba(0,0,0,0.5)" }}>{p.hero || "REA"}</div>
      <div style={{ position: "absolute", left: W * 0.05, bottom: H * 0.07, width: W * 0.55 }}>{p.lines.map((l, i) => <Line key={i} l={l} i={-5} fs={92} />)}</div>
      <Face scale={p.face_scale ?? 0.95} x={-W * 0.01} />
    </AbsoluteFill>);
  if (p.style === "split") return (
    <AbsoluteFill style={{ fontFamily: F.display, background: bgc }}>
      {p.proof && <Img src={p.proof} style={{ position: "absolute", left: 0, top: 0, width: W * 0.62, height: H, objectFit: "cover" }} />}
      <div style={{ position: "absolute", left: 0, top: 0, width: W * 0.62, height: H * 0.42, background: "linear-gradient(180deg, rgba(8,10,24,0.92) 0%, rgba(8,10,24,0.75) 60%, rgba(8,10,24,0) 100%)" }} />
      <div style={{ position: "absolute", left: W * 0.62 - 8, top: 0, width: 16, height: H, background: rgb(th.accent) }} />
      <div style={{ position: "absolute", left: W * 0.03, top: H * 0.05, width: W * 0.58 }}>{p.lines.map((l, i) => <Line key={i} l={l} i={i} fs={104} />)}</div>
      <Stamp x={W * 0.12} y={H * 0.52} />
      <Face scale={p.face_scale ?? 1.0} x={-W * 0.04} />
    </AbsoluteFill>);
  if (p.style === "warning") return (
    <AbsoluteFill style={{ fontFamily: F.display, background: bgc }}>
      <Glow color={PALETTE.red} size={W * 0.7} x={W * 0.75} y={H * 0.5} alpha={0.3} />
      <div style={{ position: "absolute", left: 0, top: H * 0.06, width: W, height: H * 0.075, background: "repeating-linear-gradient(-45deg, #ffcc00 0 40px, #111 40px 80px)" }} />
      <div style={{ position: "absolute", left: W * 0.045, top: H * 0.2, width: W * 0.58 }}>
        <div style={{ fontSize: 70, fontWeight: 900, color: "#ffcc00", WebkitTextStroke: "8px black", paintOrder: "stroke fill" }}>⚠ {p.hero || "WARNING"}</div>
        {p.lines.map((l, i) => <Line key={i} l={l} i={i} fs={132} />)}</div>
      {p.proof && <Img src={p.proof} style={{ position: "absolute", left: W * 0.045, bottom: H * 0.06, width: W * 0.42, borderRadius: 18, border: "6px solid #ffcc00", transform: "rotate(-2deg)" }} />}
      <Face scale={p.face_scale ?? 1.05} x={-W * 0.02} />
      <div style={{ position: "absolute", left: 0, bottom: 0, width: W, height: H * 0.03, background: "repeating-linear-gradient(-45deg, #ffcc00 0 40px, #111 40px 80px)" }} />
    </AbsoluteFill>);
  // repo: proof card big at the top centre-left, line below it, face right
  return (
    <AbsoluteFill style={{ fontFamily: F.display, background: bgc }}>
      <Glow color={th.accent} size={W * 0.7} x={W * 0.35} y={H * 0.3} alpha={0.3} />
      <Badge />
      {p.proof && <Img src={p.proof} style={{ position: "absolute", left: W * 0.04, top: H * (p.badge ? 0.17 : 0.07), width: W * 0.6, borderRadius: 22,
        boxShadow: "0 24px 70px rgba(0,0,0,0.6)", transform: "rotate(-2deg)" }} />}
      <div style={{ position: "absolute", left: W * 0.045, bottom: H * 0.07, width: W * 0.6 }}>{p.lines.map((l, i) => <Line key={i} l={l} i={i} fs={104} />)}</div>
      <Face scale={p.face_scale ?? 1.0} x={-W * 0.03} />
    </AbsoluteFill>);
};
