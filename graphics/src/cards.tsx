// Full-screen cards: TitleCard, TestCard, LogoHit, VersusCard, EndCard.
import React from "react";
import { AbsoluteFill, Easing, Img, OffthreadVideo, interpolate } from "remotion";
import { Backdrop, Base, Glow, Icon, PALETTE, Panel, RGB, Shockwave, Sparks, Sweep, colorOf, ease, fonts, life, mix, rgb, sp, useT, useTheme } from "./lib";
import { outFade } from "./lib";

/** Episode / video title card. {kicker, title, sub, variant} */
export const TitleCard: React.FC<Base & { kicker?: string; title: string; sub?: string; variant?: string }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const a = sp(t, 0.05, fps, { damping: 16 }), b = sp(t, 0.22, fps, { damping: 18 }), c = ease(t, 0.5, 0.9);
  const out = outFade(p, t, D, 0.25);
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <Backdrop th={th} t={t} W={W} H={H} variant={p.variant || "grid"} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", fontFamily: F.display, textAlign: "center", padding: tall ? 70 : 140 }}>
        {p.kicker && <div style={{ color: rgb(th.accent), fontSize: tall ? 34 : 30, fontWeight: 700, letterSpacing: 8, opacity: a,
          transform: `translateY(${(1 - a) * 30}px)` }}>{p.kicker}</div>}
        <div style={{ color: rgb(th.text), fontSize: tall ? 92 : 110, fontWeight: 800, lineHeight: 1.05, marginTop: 22,
          transform: `scale(${interpolate(b, [0, 1], [1.12, 1])})`, opacity: b, textShadow: `0 10px 50px rgba(0,0,0,0.6)` }}>{p.title}</div>
        <div style={{ width: interpolate(c, [0, 1], [0, tall ? 500 : 640]), height: 6, borderRadius: 3, background: rgb(th.accent), marginTop: 34,
          boxShadow: `0 0 30px ${rgb(th.accent, 0.8)}` }} />
        {p.sub && <div style={{ color: rgb(PALETTE.dim), fontSize: tall ? 40 : 38, fontWeight: 500, marginTop: 30, opacity: c }}>{p.sub}</div>}
      </AbsoluteFill>
      <Sweep t={t} at={0.35} />
    </AbsoluteFill>
  );
};

/** Big numbered test card with a claim chip. {num, total, title, claim, label} */
export const TestCard: React.FC<Base & { num: number; total?: number; title: string; claim?: string; label?: string; broll?: string; broll_from?: number; claim_label?: string }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const slam = sp(t, 0.0, fps, { damping: 11, stiffness: 240 });
  const tl = sp(t, 0.18, fps, { damping: 17 }), cl = sp(t, 0.42, fps, { damping: 15 });
  const out = outFade(p, t, D, 0.22);
  const cx = tall ? W / 2 : W * 0.3, cy = tall ? H * 0.34 : H / 2;
  return (
    <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
      <Backdrop th={th} t={t} W={W} H={H} />
      {p.broll && <AbsoluteFill style={{ opacity: 0.55 }}><OffthreadVideo src={p.broll} startFrom={Math.round((p.broll_from || 0) * 30)} muted
        style={{ width: W, height: H, objectFit: "cover", transform: `scale(${1.04 + 0.03 * t / Math.max(1, D)})` }} /></AbsoluteFill>}
      {p.broll && <AbsoluteFill style={{ background: `linear-gradient(90deg, ${rgb(th.bg, 0.25)}, ${rgb(th.bg, 0.75)})` }} />}
      <Glow color={th.accent} size={900} x={cx} y={cy} alpha={0.35 * slam} />
      <Shockwave x={cx} y={cy} t={t} at={0.08} color={th.accent} size={1100} />
      <Sparks x={cx} y={cy} t={t} at={0.08} color={th.accent} />
      <div style={{ position: "absolute", left: cx, top: cy, transform: `translate(-50%,-50%) scale(${interpolate(slam, [0, 1], [3, 1])})`,
        opacity: Math.min(1, slam * 2), textAlign: "center" }}>
        <div style={{ color: rgb(th.accent), fontSize: 34, fontWeight: 800, letterSpacing: 10 }}>{p.label || "TEST"}</div>
        <div style={{ color: rgb(th.text), fontSize: 300, fontWeight: 900, lineHeight: 0.9, textShadow: `0 0 80px ${rgb(th.accent, 0.6)}` }}>
          {p.num}{p.total ? <span style={{ fontSize: 90, color: rgb(PALETTE.dim) }}>/{p.total}</span> : null}</div>
      </div>
      <div style={{ position: "absolute", left: tall ? 70 : W * 0.52, right: tall ? 70 : 120, top: tall ? H * 0.56 : H * 0.36,
        textAlign: tall ? "center" : "left" }}>
        <div style={{ color: rgb(th.text), fontSize: tall ? 78 : 84, fontWeight: 800, lineHeight: 1.08, opacity: tl,
          transform: `translateX(${tall ? 0 : (1 - tl) * 80}px) translateY(${tall ? (1 - tl) * 40 : 0}px)` }}>{p.title}</div>
        {p.claim && (
          <div style={{ display: "inline-flex", alignItems: "center", gap: 16, marginTop: 40, opacity: cl, transform: `translateY(${(1 - cl) * 30}px)`,
            padding: "16px 30px", borderRadius: 50, border: `3px solid ${rgb(th.accent, 0.9)}`, background: rgb(th.accent, 0.12),
            color: rgb(th.text), fontSize: 38, fontWeight: 600 }}>
            <span style={{ color: rgb(th.accent), fontWeight: 800, fontSize: 30, letterSpacing: 3 }}>{p.claim_label || "CLAIM"}</span>{p.claim}</div>
        )}
        {p.total && <div style={{ display: "flex", gap: 14, marginTop: 40, justifyContent: tall ? "center" : "flex-start", opacity: cl }}>
          {Array.from({ length: p.total }).map((_, i) => <div key={i} style={{ width: i + 1 === p.num ? 34 : 14, height: 14, borderRadius: 7,
            background: i + 1 === p.num ? rgb(th.accent) : i + 1 < p.num ? rgb(th.text, 0.7) : rgb(th.text, 0.25), boxShadow: i + 1 === p.num ? `0 0 16px ${rgb(th.accent)}` : "none" }} />)}</div>}
      </div>
      <Sweep t={t} at={0.25} />
    </AbsoluteFill>
  );
};

/** Logo hit: icon slams in with shockwave + sparks, title under it. {icon, title, sub, color} */
export const LogoHit: React.FC<Base & { icon?: string; title?: string; sub?: string; color?: string; transparent?: boolean }> = (p) => {
  const { t, fps, W, H, D } = useT(); const th = useTheme(p); const F = fonts(p); const c = colorOf(p.color, th);
  const s = sp(t, 0.0, fps, { damping: 10, stiffness: 220 }); const ti = sp(t, 0.3, fps, { damping: 16 });
  const out = outFade(p, t, D, 0.3);
  return (
    <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} variant="dots" />}
      <Glow color={c} size={1000} x={W / 2} y={H * 0.42} alpha={0.45 * s} />
      <Shockwave x={W / 2} y={H * 0.42} t={t} at={0.1} color={c} size={1300} />
      <Shockwave x={W / 2} y={H * 0.42} t={t} at={0.22} color={PALETTE.white} size={800} />
      <Sparks x={W / 2} y={H * 0.42} t={t} at={0.1} color={c} n={34} reach={560} />
      <div style={{ position: "absolute", left: W / 2, top: H * 0.42, transform: `translate(-50%,-50%) scale(${interpolate(s, [0, 1], [0.2, 1])}) rotate(${(1 - s) * -25}deg)` }}>
        <Icon src={p.icon} size={260} style={{ filter: `drop-shadow(0 0 40px ${rgb(c, 0.8)})` }} />
      </div>
      {p.title && <div style={{ position: "absolute", left: 0, right: 0, top: H * 0.62, textAlign: "center", color: rgb(th.text), fontSize: 90, fontWeight: 900,
        opacity: ti, letterSpacing: interpolate(ti, [0, 1], [30, 4]) }}>{p.title}</div>}
      {p.sub && <div style={{ position: "absolute", left: 0, right: 0, top: H * 0.62 + 120, textAlign: "center", color: rgb(PALETTE.dim), fontSize: 40, opacity: ease(t, 0.5, 0.8) }}>{p.sub}</div>}
    </AbsoluteFill>
  );
};

/** VS split: two sides slam in, VS hit in the middle. {left:{name,icon,color}, right:{...}, title} */
export const VersusCard: React.FC<Base & { left: { name: string; icon?: string; color?: string; sub?: string }; right: { name: string; icon?: string; color?: string; sub?: string }; title?: string }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const L = sp(t, 0.0, fps, { damping: 15 }), R = sp(t, 0.12, fps, { damping: 15 }), V = sp(t, 0.35, fps, { damping: 8, stiffness: 300 });
  const cl = colorOf(p.left.color || "blue", th), cr = colorOf(p.right.color || "claude", th);
  const out = outFade(p, t, D, 0.25);
  const side = (s: typeof p.left, c: RGB, k: number, dir: number, x: number, y: number) => (
    <div style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,-50%) translateX(${dir * (1 - k) * W * 0.4}px)`, textAlign: "center", opacity: Math.min(1, k * 1.5) }}>
      <Icon src={s.icon} size={tall ? 200 : 230} style={{ filter: `drop-shadow(0 0 30px ${rgb(c, 0.7)})` }} />
      <div style={{ color: rgb(th.text), fontSize: tall ? 70 : 76, fontWeight: 900, marginTop: 20 }}>{s.name}</div>
      {s.sub && <div style={{ color: rgb(c), fontSize: 34, fontWeight: 700, marginTop: 8, letterSpacing: 3 }}>{s.sub}</div>}
    </div>
  );
  return (
    <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
      <AbsoluteFill style={{ background: tall ? `linear-gradient(180deg, ${rgb(mix(th.bg, cl, 0.3))} 0%, ${rgb(th.bg)} 50%, ${rgb(mix(th.bg, cr, 0.3))} 100%)`
        : `linear-gradient(100deg, ${rgb(mix(th.bg, cl, 0.32))} 0%, ${rgb(th.bg)} 50%, ${rgb(mix(th.bg, cr, 0.32))} 100%)` }} />
      {side(p.left, cl, L, -1, tall ? W / 2 : W * 0.25, tall ? H * 0.25 : H / 2)}
      {side(p.right, cr, R, 1, tall ? W / 2 : W * 0.75, tall ? H * 0.73 : H / 2)}
      <Shockwave x={W / 2} y={H / 2} t={t} at={0.4} color={PALETTE.white} size={700} />
      <div style={{ position: "absolute", left: W / 2, top: H / 2, transform: `translate(-50%,-50%) scale(${interpolate(V, [0, 1], [3.5, 1])})`, opacity: Math.min(1, V * 2),
        color: rgb(th.accent), fontSize: 150, fontWeight: 900, fontStyle: "italic", textShadow: `0 0 60px ${rgb(th.accent, 0.9)}` }}>VS</div>
      {p.title && <div style={{ position: "absolute", left: 0, right: 0, top: tall ? H * 0.06 : H * 0.08, textAlign: "center", color: rgb(PALETTE.dim), fontSize: 40,
        fontWeight: 700, letterSpacing: 6, opacity: ease(t, 0.5, 0.8) }}>{p.title}</div>}
    </AbsoluteFill>
  );
};

/** End slate with room for YouTube end-screen elements (video box left, subscribe right). {line, handle, icon} */
export const EndCard: React.FC<Base & { line?: string; handle?: string; icon?: string; boxes?: boolean; pos?: "middle" | "bottom" }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  // pos "bottom": sign-off low, so YouTube's end-screen boxes (left: next video/series, right: subscribe) have the middle
  const Y = p.pos === "bottom" ? H * 0.8 : H * 0.45;
  const hit = sp(t, 0.15, fps, { damping: 10, stiffness: 220 });
  const l1 = ease(t, 0.45, 0.85);
  return (
    <AbsoluteFill style={{ fontFamily: F.display }}>
      <Backdrop th={th} t={t} W={W} H={H} />
      <Glow color={th.accent} size={1100} x={W / 2} y={Y} alpha={0.4 * hit} />
      <Shockwave x={W / 2} y={Y} t={t} at={0.2} color={th.accent} size={1400} />
      <Sparks x={W / 2} y={Y} t={t} at={0.2} color={th.accent} n={36} reach={620} />
      <div style={{ position: "absolute", left: 0, right: 0, top: Y, transform: `translateY(-50%) scale(${interpolate(hit, [0, 1], [2.2, 1])})`, opacity: Math.min(1, hit * 2),
        textAlign: "center", color: rgb(th.text), fontSize: tall ? 74 : 72, fontWeight: 800, lineHeight: 1.15, padding: "0 80px", textShadow: `0 0 40px ${rgb(th.accent, 0.5)}` }}>
        {(p.line || "Thanks for watching.").split(". ").map((s, i, a) => <div key={i} style={{ color: i === a.length - 1 ? rgb(th.accent) : rgb(th.text) }}>{s}{i < a.length - 1 ? "." : ""}</div>)}
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, top: Y + (p.pos === "bottom" ? 110 : (tall ? 200 : 150)), textAlign: "center", color: rgb(PALETTE.dim), fontSize: 38, fontWeight: 600, opacity: l1, letterSpacing: 2 }}>
        {p.handle || ""}</div>
    </AbsoluteFill>
  );
};

/** Short end card / call to action (tall). {kicker, title, cta, sub, photo, icons:[..], handle} */
export const ShortEnd: React.FC<Base & { kicker?: string; title?: string; cta: string; sub?: string; photo?: string; icons?: string[]; handle?: string; face?: string; face_mode?: string; image?: string }> = (p) => {
  const { t, fps, W, H } = useT(); const th = useTheme(p); const F = fonts(p);
  const a = sp(t, 0.05, fps, { damping: 13 }), b = sp(t, 0.25, fps, { damping: 12 }), c = sp(t, 0.5, fps, { damping: 10, stiffness: 240 });
  return (
    <AbsoluteFill style={{ fontFamily: F.display }}>
      <Backdrop th={th} t={t} W={W} H={H} />
      {p.image && <Img src={p.image} style={{ position: "absolute", inset: 0, width: W, height: H, objectFit: "cover", opacity: 0.5, filter: "blur(6px)", transform: `scale(${1.04 + 0.03 * a})` }} />}
      {p.face && p.face_mode !== "side" && <Img src={p.face} style={{ position: "absolute", left: -W * 0.45, top: 0, width: W * 1.9, height: H, objectFit: "cover", opacity: 0.42,
        filter: "blur(22px) saturate(0.8)", transform: `scale(${1.04 + 0.03 * a})` }} />}
      {p.face && p.face_mode === "side" && <Img src={p.face} style={{ position: "absolute", left: W * 0.42, top: H * 0.38, width: W * 1.05, height: H * 0.62, objectFit: "cover", objectPosition: "50% 25%",
        opacity: 0.9, maskImage: "linear-gradient(90deg, transparent 0%, black 35%)", WebkitMaskImage: "linear-gradient(90deg, transparent 0%, black 35%)" }} />}
      {(p.face || p.image) && <AbsoluteFill style={{ background: `linear-gradient(180deg, ${rgb(th.bg, 0.55)} 0%, ${rgb(th.bg, 0.25)} 45%, ${rgb(th.bg, 0.7)} 100%)` }} />}
      {p.photo && <Img src={p.photo} style={{ position: "absolute", left: 0, right: 0, bottom: 0, width: W, height: H * 0.56, objectFit: "contain", objectPosition: "bottom",
        transform: `translateY(${(1 - a) * 200}px)`, filter: "drop-shadow(0 -10px 60px rgba(0,0,0,0.5))" }} />}
      <Glow color={th.accent} size={900} x={W / 2} y={H * 0.2} alpha={0.35 * a} />
      <div style={{ position: "absolute", top: 300, left: 60, right: 60, textAlign: "center" }}>
        {p.icons && <div style={{ display: "flex", justifyContent: "center", gap: 50, opacity: a, transform: `scale(${0.7 + 0.3 * a})` }}>{p.icons.map((s, i) => <Icon key={i} src={s} size={130} />)}</div>}
        {p.kicker && <div style={{ color: rgb(th.accent), fontSize: 46, fontWeight: 900, letterSpacing: 6, marginTop: 30, opacity: a }}>{p.kicker}</div>}
        {p.title && <div style={{ color: rgb(th.text), fontSize: 92, fontWeight: 900, lineHeight: 1.05, marginTop: 14, opacity: b, transform: `translateY(${(1 - b) * 40}px)`,
          WebkitTextStroke: "6px black", paintOrder: "stroke fill" }}>{p.title}</div>}
        <div style={{ display: "inline-block", marginTop: 46, padding: "26px 54px", borderRadius: 40, background: "white", transform: `scale(${c})`, boxShadow: `0 0 60px ${rgb(th.accent, 0.6)}` }}>
          <div style={{ color: rgb(PALETTE.ink), fontSize: 58, fontWeight: 900 }}>{p.cta}</div>
          {p.sub && <div style={{ color: "rgb(60,64,90)", fontSize: 38, fontWeight: 600, marginTop: 6 }}>{p.sub}</div>}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Cover image for a Short (a still; sRGB). {badge, hook, photo} */
/** Short cover (1080x1920). Every cover should look different on a profile grid, so it has several layouts (`style`):
 * classic (face bottom, text top) | proof (proof picture card on top, text, face bottom-right) | screen (proof fills the frame,
 * text over a dark band, face bottom-left) | number (giant number on a colour, no face) | split (two proof pictures with labels, no face)
 * | hero (picture fills the top, text below, no face) | blur (his face big + blurred behind the text) | crop (giant face crop off the right edge,
 * text left) | behind (giant word behind his cut-out) | corner (proof card, small face circle bottom-right) | vs (two logos, winner glows)
 * | text (colour field + editorial type, light: true = cream) | stamp (a video still + a stamp). All text stays inside the 3:4 profile-grid crop (y 240-1680) and clear of
 * the top-right reel icon. {badge, hook ("|" = line breaks), photo, style, bg [r,g,b], proof, proof2, labels [a,b], number, accent_last} */
export const Cover: React.FC<Base & { badge?: string; hook: string; photo?: string; accent_last?: boolean; style?: string; bg?: number[];
  proof?: string; proof2?: string; labels?: string[]; number?: string; face?: string; word?: string; stamp?: string; light?: boolean; look?: string }> = (p) => {
  const { W, H } = useT(); const th = useTheme(p); const F = fonts(p);
  const style = p.style || "classic";
  // modern looks (no saturated colour fields, no black outlines on text)
  const LOOKS: Record<string, any> = {
    glass: { bg: [10, 10, 16], text: [245, 245, 247], accent: [245, 181, 68], sub: [170, 170, 185],
      css: "radial-gradient(900px 700px at 15% 20%, rgba(110,86,207,0.55) 0%, rgba(110,86,207,0) 70%), radial-gradient(800px 800px at 90% 85%, rgba(43,179,163,0.35) 0%, rgba(43,179,163,0) 70%), radial-gradient(600px 500px at 80% 10%, rgba(245,181,68,0.18) 0%, rgba(245,181,68,0) 70%), #0A0A10",
      badge: { background: "rgba(255,255,255,0.08)", border: "1.5px solid rgba(255,255,255,0.22)", color: "rgb(245,245,247)" },
      card: { border: "1.5px solid rgba(255,255,255,0.28)", boxShadow: "0 40px 120px rgba(0,0,0,0.65), 0 0 0 10px rgba(255,255,255,0.04)" }, font: undefined },
    editorial: { bg: [243, 239, 231], text: [18, 18, 20], accent: [79, 70, 229], sub: [90, 90, 96],
      css: "radial-gradient(1000px 700px at 85% 10%, rgba(79,70,229,0.10) 0%, rgba(79,70,229,0) 70%), #F3EFE7",
      badge: { background: "transparent", border: "2px solid rgb(18,18,20)", color: "rgb(18,18,20)" },
      card: { border: "2px solid rgb(18,18,20)", boxShadow: "18px 18px 0 rgba(18,18,20,0.9)" }, font: "'New York', 'Iowan Old Style', Georgia, serif" },
    "editorial-peach": { bg: [250, 236, 225], text: [18, 18, 20], accent: [226, 92, 60], sub: [90, 90, 96],
      css: "radial-gradient(900px 800px at 90% 5%, rgba(255,150,110,0.45) 0%, rgba(255,150,110,0) 70%), radial-gradient(800px 700px at 0% 100%, rgba(255,205,150,0.5) 0%, rgba(255,205,150,0) 70%), #FAECE1",
      badge: { background: "rgba(255,255,255,0.55)", border: "2px solid rgb(18,18,20)", color: "rgb(18,18,20)" },
      card: { border: "2px solid rgb(18,18,20)", boxShadow: "18px 18px 0 rgba(226,92,60,0.85)" }, font: "'New York', 'Iowan Old Style', Georgia, serif", editorial: true },
    "editorial-sage": { bg: [232, 240, 232], text: [18, 18, 20], accent: [30, 122, 90], sub: [90, 90, 96],
      css: "radial-gradient(900px 800px at 95% 0%, rgba(120,190,150,0.45) 0%, rgba(120,190,150,0) 70%), radial-gradient(700px 700px at 0% 100%, rgba(200,230,180,0.6) 0%, rgba(200,230,180,0) 70%), #E8F0E8",
      badge: { background: "rgba(255,255,255,0.55)", border: "2px solid rgb(18,18,20)", color: "rgb(18,18,20)" },
      card: { border: "2px solid rgb(18,18,20)", boxShadow: "18px 18px 0 rgba(30,122,90,0.85)" }, font: "'New York', 'Iowan Old Style', Georgia, serif", editorial: true },
    "editorial-lavender": { bg: [238, 234, 250], text: [18, 18, 20], accent: [110, 72, 220], sub: [90, 90, 96],
      css: "radial-gradient(900px 800px at 90% 5%, rgba(170,140,255,0.45) 0%, rgba(170,140,255,0) 70%), radial-gradient(800px 700px at 0% 95%, rgba(255,180,220,0.4) 0%, rgba(255,180,220,0) 70%), #EEEAFA",
      badge: { background: "rgba(255,255,255,0.55)", border: "2px solid rgb(18,18,20)", color: "rgb(18,18,20)" },
      card: { border: "2px solid rgb(18,18,20)", boxShadow: "18px 18px 0 rgba(110,72,220,0.85)" }, font: "'New York', 'Iowan Old Style', Georgia, serif", editorial: true },
    "editorial-sky": { bg: [230, 240, 250], text: [18, 18, 20], accent: [30, 100, 210], sub: [90, 90, 96],
      css: "radial-gradient(900px 800px at 90% 0%, rgba(120,180,255,0.5) 0%, rgba(120,180,255,0) 70%), radial-gradient(800px 700px at 0% 100%, rgba(170,230,240,0.55) 0%, rgba(170,230,240,0) 70%), #E6F0FA",
      badge: { background: "rgba(255,255,255,0.55)", border: "2px solid rgb(18,18,20)", color: "rgb(18,18,20)" },
      card: { border: "2px solid rgb(18,18,20)", boxShadow: "18px 18px 0 rgba(30,100,210,0.85)" }, font: "'New York', 'Iowan Old Style', Georgia, serif", editorial: true },
    "editorial-sunset": { bg: [252, 238, 232], text: [18, 18, 20], accent: [200, 60, 120], sub: [90, 90, 96],
      css: "linear-gradient(160deg, #FFE3D3 0%, #FCEEE8 45%, #F3E6FF 100%)",
      badge: { background: "rgba(255,255,255,0.55)", border: "2px solid rgb(18,18,20)", color: "rgb(18,18,20)" },
      card: { border: "2px solid rgb(18,18,20)", boxShadow: "18px 18px 0 rgba(200,60,120,0.85)" }, font: "'New York', 'Iowan Old Style', Georgia, serif", editorial: true },
    storymic: { bg: [236, 92, 112], text: [255, 255, 255], accent: [255, 232, 214], sub: [255, 236, 226],
      css: "linear-gradient(160deg, #F8966E 0%, #EE6E7E 50%, #E84676 100%)",
      badge: { background: "rgba(255,255,255,0.92)", border: "none", color: "rgb(214,60,100)" },
      card: { border: "none", boxShadow: "0 40px 100px rgba(120,20,50,0.45)" }, font: undefined },
    "rea-indigo": { bg: [30, 18, 62], text: [255, 255, 255], accent: [245, 158, 11], sub: [200, 190, 230],
      css: "linear-gradient(rgba(255,255,255,0.06) 2px, transparent 2px) 0 0 / 90px 90px, linear-gradient(90deg, rgba(255,255,255,0.06) 2px, transparent 2px) 0 0 / 90px 90px, radial-gradient(ellipse at 30% 20%, rgb(64,40,70) 0%, rgb(30,18,62) 60%), rgb(30,18,62)",
      badge: { background: "rgba(10,8,24,0.75)", border: "2px solid rgb(245,158,11)", color: "rgb(255,255,255)" },
      card: { border: "4px solid rgb(245,158,11)", boxShadow: "0 40px 100px rgba(0,0,0,0.55)" }, font: undefined },
    graphite: { bg: [17, 18, 20], text: [237, 237, 237], accent: [200, 242, 92], sub: [150, 150, 150],
      css: "linear-gradient(180deg, #1C1D21 0%, #111214 55%), #111214",
      badge: { background: "transparent", border: "2px solid rgb(200,242,92)", color: "rgb(200,242,92)" },
      card: { border: "1.5px solid rgba(255,255,255,0.18)", boxShadow: "0 40px 100px rgba(0,0,0,0.7)" }, font: undefined },
  };
  const LK = p.look ? LOOKS[p.look] : null;
  const bg = LK ? LK.bg : ((p.bg as any) || th.bg);
  const TXT = LK ? LK.text : th.text; const ACC = LK ? LK.accent : th.accent;
  const FONT = LK && LK.font ? LK.font : F.display;
  const stroke = (px: number) => LK ? { textShadow: (LK && (LK === LOOKS.editorial || LK.editorial)) ? "none" : "0 8px 40px rgba(0,0,0,0.45)" } : { WebkitTextStroke: `${px}px black`, paintOrder: "stroke fill" };
  let lines: string[] = [];
  const wrap = style === "screen" || style === "number" ? 14 : 16;
  if (p.hook.includes("|")) lines = p.hook.toUpperCase().split("|").map((l) => l.trim());
  else { const words = p.hook.toUpperCase().split(" "); let cur = "";
    for (const w of words) { if ((cur + " " + w).trim().length > wrap) { lines.push(cur.trim()); cur = w; } else cur += " " + w; } lines.push(cur.trim()); }
  const Lines = ({ top, size, align = "center", left = 50, right = 50 }: { top: number; size: number; align?: any; left?: number; right?: number }) => (
    <div style={{ position: "absolute", top, left, right, textAlign: align }}>
      {lines.map((l, i) => <div key={i} style={{ fontSize: size, fontWeight: 900, lineHeight: 1.06, color: i === lines.length - 1 && p.accent_last !== false ? rgb(ACC) : rgb(TXT),
        letterSpacing: LK ? -2 : 0, ...stroke(Math.round(size / 13)) }}>{l}</div>)}
    </div>);
  const Badge = ({ top, align = "center", left = 0 }: { top: number; align?: any; left?: number }) => p.badge ? (
    <div style={{ position: "absolute", top, left, right: align === "center" ? 0 : undefined, textAlign: align }}><span style={{ padding: "12px 28px", borderRadius: 30,
      background: rgb(th.accent), color: rgb(PALETTE.ink), fontSize: 30, fontWeight: 900, letterSpacing: 3, ...(LK ? { ...LK.badge, fontWeight: 700, fontFamily: F.display } : {}) }}>{p.badge}</span></div>) : null;
  const Card = ({ src, x, y, w, h, tilt = 0, label }: { src: string; x: number; y: number; w: number; h: number; tilt?: number; label?: string }) => (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, transform: `rotate(${tilt}deg)`, borderRadius: 26, overflow: "hidden",
      border: `6px solid ${rgb(th.accent)}`, boxShadow: "0 30px 80px rgba(0,0,0,0.6)", background: "#000", ...(LK ? LK.card : {}) }}>
      <Img src={src} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      {label && <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: "10px 0", textAlign: "center", background: "rgba(0,0,0,0.75)",
        color: rgb(th.text), fontSize: 34, fontWeight: 900, letterSpacing: 2 }}>{label}</div>}
    </div>);
  const radial = LK ? LK.css : `radial-gradient(ellipse at 50% 30%, ${rgb(mix(bg, th.accent, 0.25))} 0%, ${rgb(bg)} 65%)`;
  const flat = LK ? LK.css : rgb(bg);
  if (style === "proof") return (
    <AbsoluteFill style={{ fontFamily: FONT, background: radial }}>
      <Badge top={300} />
      {p.proof && <Card src={p.proof} x={70} y={340} w={940} h={560} tilt={-2.5} />}
      {p.photo && <Img src={p.photo} style={{ position: "absolute", right: -60, bottom: 0, width: W * 0.75, height: H * 0.42, objectFit: "contain", objectPosition: "right bottom" }} />}
      <Lines top={960} size={86} align="left" left={60} right={400} />
    </AbsoluteFill>);
  if (style === "screen") return (
    <AbsoluteFill style={{ fontFamily: FONT, background: flat }}>
      {p.proof && <Img src={p.proof} style={{ position: "absolute", left: 0, top: 0, width: W, height: H, objectFit: "cover", filter: "brightness(0.75)" }} />}
      <div style={{ position: "absolute", left: 0, right: 0, top: 560, height: 820, background: "linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.85) 22%, rgba(0,0,0,0.85) 78%, rgba(0,0,0,0) 100%)" }} />
      <Badge top={300} align="left" left={60} />
      {p.photo && <Img src={p.photo} style={{ position: "absolute", left: -40, bottom: 0, width: W * 0.7, height: H * 0.36, objectFit: "contain", objectPosition: "left bottom" }} />}
      <Lines top={720} size={112} align="left" left={60} right={60} />
    </AbsoluteFill>);
  if (style === "number") return (
    <AbsoluteFill style={{ fontFamily: FONT, background: LK ? LK.css : `linear-gradient(160deg, ${rgb(mix(bg, [255, 255, 255], 0.1))} 0%, ${rgb(bg)} 75%)`, overflow: "hidden" }}>
      <div style={{ position: "absolute", top: 380, left: -120, right: -120, textAlign: "center", fontSize: 640, fontWeight: 900, lineHeight: 1, color: (LK && (LK === LOOKS.editorial || LK.editorial)) ? "rgba(18,18,20,0.06)" : rgb([255, 255, 255], 0.06), letterSpacing: -20 }}>{p.number}</div>
      <Badge top={300} />
      <div style={{ position: "absolute", top: 520, left: 0, right: 0, textAlign: "center", fontSize: 320, fontWeight: 900, lineHeight: 1, color: rgb(ACC),
        ...stroke(14), letterSpacing: -6 }}>{p.number}</div>
      <div style={{ position: "absolute", top: 900, left: 340, right: 340, height: 10, borderRadius: 5, background: rgb(ACC) }} />
      <Lines top={980} size={104} />
    </AbsoluteFill>);
  if (style === "split") return (
    <AbsoluteFill style={{ fontFamily: FONT, background: radial }}>
      <Badge top={300} />
      {p.proof && <Card src={p.proof} x={40} y={380} w={490} h={760} tilt={-3} label={p.labels?.[0]} />}
      {p.proof2 && <Card src={p.proof2} x={550} y={380} w={490} h={760} tilt={3} label={p.labels?.[1]} />}
      <Lines top={1230} size={96} />
    </AbsoluteFill>);
  // ---- face as the background
  if (style === "blur") return (
    <AbsoluteFill style={{ fontFamily: FONT, background: flat }}>
      {p.face && <Img src={p.face} style={{ position: "absolute", left: -W * 0.4, top: 0, width: W * 1.8, height: H, objectFit: "cover", filter: "blur(26px) brightness(0.45) saturate(0.8)" }} />}
      <div style={{ position: "absolute", inset: 0, background: `linear-gradient(180deg, ${rgb(bg, 0.35)} 0%, ${rgb(mix(bg, th.accent, 0.15), 0.35)} 100%)` }} />
      <Badge top={300} />
      <Lines top={640} size={150} />
    </AbsoluteFill>);
  if (style === "crop") return (
    <AbsoluteFill style={{ fontFamily: FONT, background: flat }}>
      {p.face && <Img src={p.face} style={{ position: "absolute", left: 420, top: 160, width: 1100, height: 1600, objectFit: "cover", objectPosition: "50% 22%" }} />}
      <div style={{ position: "absolute", inset: 0, background: `linear-gradient(90deg, ${rgb(bg)} 0%, ${rgb(bg)} 42%, ${rgb(bg, 0.85)} 52%, ${rgb(bg, 0)} 72%)` }} />
      <Badge top={300} align="left" left={60} />
      <Lines top={560} size={LK && (LK === LOOKS.editorial || LK.editorial) ? 84 : 104} align="left" left={60} right={540} />
    </AbsoluteFill>);
  if (style === "behind") return (
    <AbsoluteFill style={{ fontFamily: FONT, background: radial }}>
      <Badge top={300} />
      <Lines top={390} size={76} />
      <div style={{ position: "absolute", top: 600, left: 0, right: 0, textAlign: "center", fontSize: (LK && (LK === LOOKS.editorial || LK.editorial)) ? 250 : 320, fontWeight: 900, lineHeight: 1, color: rgb(ACC), letterSpacing: -8 }}>{p.word}</div>
      {p.photo && <Img src={p.photo} style={{ position: "absolute", left: 0, bottom: 0, width: W, height: H * 0.74, objectFit: "contain", objectPosition: "bottom" }} />}
    </AbsoluteFill>);
  // ---- small face
  if (style === "corner") return (
    <AbsoluteFill style={{ fontFamily: FONT, background: flat }}>
      <Badge top={300} align="left" left={60} />
      <Lines top={380} size={92} align="left" left={60} right={140} />
      {p.proof && <Card src={p.proof} x={60} y={720} w={960} h={600} tilt={2} />}
      {p.face && <div style={{ position: "absolute", left: 740, top: 1330, width: 290, height: 290, borderRadius: 145, overflow: "hidden", border: `8px solid ${rgb(ACC)}`,
        boxShadow: "0 20px 60px rgba(0,0,0,0.6)" }}><Img src={p.face} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "50% 30%", transform: "scale(1.6)" }} /></div>}
    </AbsoluteFill>);
  // ---- no face
  if (style === "vs") return (
    <AbsoluteFill style={{ fontFamily: FONT, background: LK ? LK.css : `linear-gradient(90deg, ${rgb(bg)} 50%, ${rgb(mix(bg, th.accent, 0.3))} 50%)` }}>
      <Badge top={300} />
      {p.proof && <Img src={p.proof} style={{ position: "absolute", left: 90, top: 560, width: 360, height: 360, objectFit: "contain", filter: "grayscale(0.85) brightness(0.8)" }} />}
      {p.proof2 && <Img src={p.proof2} style={{ position: "absolute", right: 90, top: 560, width: 360, height: 360, objectFit: "contain", filter: `drop-shadow(0 0 40px ${rgb(th.accent)})` }} />}
      <div style={{ position: "absolute", top: 640, left: 0, right: 0, textAlign: "center", fontSize: 150, fontWeight: 900, color: rgb(TXT), ...stroke(10) }}>VS</div>
      {p.labels && <div style={{ position: "absolute", top: 950, left: 60, right: 60, display: "flex", justifyContent: "space-between", color: rgb(th.text), fontSize: 46, fontWeight: 900 }}>
        <span>{p.labels[0]}</span><span>{p.labels[1]}</span></div>}
      <Lines top={1150} size={96} />
    </AbsoluteFill>);
  if (style === "text") {
    const ink = p.light ? [24, 20, 40] : th.text; const field = p.light ? [246, 240, 228] : bg;
    return (
    <AbsoluteFill style={{ fontFamily: FONT, background: rgb(field as any) }}>
      <div style={{ position: "absolute", top: 300, left: 80, color: rgb(th.accent), fontSize: 34, fontWeight: 900, letterSpacing: 4 }}>{p.badge}</div>
      <div style={{ position: "absolute", top: 560, left: 80, right: 120 }}>
        {lines.map((l, i) => <div key={i} style={{ fontSize: 150, fontWeight: 900, lineHeight: 1.02, letterSpacing: -3, color: rgb(ink as any) }}>
          {i === lines.length - 1 ? <span style={{ background: rgb(th.accent), color: rgb(PALETTE.ink), padding: "0 18px" }}>{l}</span> : l}</div>)}
      </div>
    </AbsoluteFill>); }
  if (style === "stamp") return (
    <AbsoluteFill style={{ fontFamily: FONT, background: "#000" }}>
      {p.proof && <Img src={p.proof} style={{ position: "absolute", inset: 0, width: W, height: H, objectFit: "cover", filter: "contrast(1.08) saturate(1.1)" }} />}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 40%, rgba(0,0,0,0.55) 100%)" }} />
      <div style={{ position: "absolute", top: 290, left: 60, transform: "rotate(-6deg)", padding: "14px 34px", border: `8px solid ${rgb(th.accent)}`, color: rgb(th.accent),
        fontSize: 84, fontWeight: 900, letterSpacing: 6, background: "rgba(0,0,0,0.35)" }}>{p.stamp}</div>
      <Lines top={1280} size={96} align="left" left={60} right={140} />
    </AbsoluteFill>);
  if (style === "hero") return (
    <AbsoluteFill style={{ fontFamily: FONT, background: flat }}>
      {p.proof && <Img src={p.proof} style={{ position: "absolute", left: 0, top: 0, width: W, height: H * 0.66, objectFit: "cover" }} />}
      <div style={{ position: "absolute", left: 0, right: 0, top: H * 0.46, height: H * 0.22, background: `linear-gradient(180deg, rgba(0,0,0,0) 0%, ${rgb(bg)} 100%)` }} />
      <Badge top={300} />
      <Lines top={1180} size={100} />
    </AbsoluteFill>);
  return (
    <AbsoluteFill style={{ fontFamily: FONT, background: radial }}>
      {p.photo && <Img src={p.photo} style={{ position: "absolute", left: 0, bottom: 0, width: W, height: H * 0.58, objectFit: "contain", objectPosition: "bottom" }} />}
      <Badge top={290} />
      <Lines top={400} size={108} />
    </AbsoluteFill>
  );
};

/** 3D title: extruded letters that swing in on a spring and slowly turn (CSS 3D, layered depth). {text, sub, color, depth, turn} */
export const Text3D: React.FC<Base & { text: string; sub?: string; color?: string; depth?: number; turn?: number; transparent?: boolean; size?: number }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p); const c = colorOf(p.color, th);
  const k = sp(t, 0.05, fps, { damping: 12, stiffness: 140 });
  const ry = interpolate(k, [0, 1], [-75, 0]) + Math.sin(t * 0.9) * (p.turn ?? 16);
  const rx = interpolate(k, [0, 1], [30, 0]) + Math.cos(t * 0.7) * 4;
  const depth = p.depth ?? 24; const size = p.size ?? (tall ? 170 : 210);
  const layers = Array.from({ length: depth }, (_, i) => i);
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade(p, t, D) }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} variant="dots" />}
      <Glow color={c} size={W * 0.8} x={W / 2} y={H / 2} alpha={0.3 * k} />
      <AbsoluteFill style={{ perspective: 1400, alignItems: "center", justifyContent: "center" }}>
        <div style={{ transformStyle: "preserve-3d", transform: `rotateX(${rx}deg) rotateY(${ry}deg) scale(${interpolate(k, [0, 1], [0.6, 1])})`, position: "relative" }}>
          {layers.map((i) => <div key={i} style={{ position: i ? "absolute" : "relative", left: 0, top: 0, transform: `translateZ(${-i * 4}px)`, fontSize: size, fontWeight: 900,
            whiteSpace: "nowrap", letterSpacing: -2, color: i ? rgb(mix(c, [0, 0, 0], 0.35 + 0.5 * i / depth)) : rgb(th.text),
            textShadow: i ? "none" : `0 0 40px ${rgb(c, 0.6)}` }}>{p.text}</div>)}
        </div>
      </AbsoluteFill>
      {p.sub && <div style={{ position: "absolute", left: 0, right: 0, top: H * 0.7, textAlign: "center", color: rgb(PALETTE.dim), fontSize: 44, fontWeight: 700, opacity: ease(t, 0.6, 1.0) }}>{p.sub}</div>}
    </AbsoluteFill>
  );
};

/** "What we cover" page: logo + title, numbered colour tiles popping in one by one, a footer line.
 * {title, icon, brand, items:[{text, color?, icon?}], footer, at, per, cols} */
const TILE_COLORS: RGB[] = [[60, 120, 240], [40, 170, 110], [140, 90, 230], [235, 110, 50], [220, 70, 150], [220, 60, 60], [30, 150, 200], [230, 160, 30]];
export const Contents: React.FC<Base & { title: string; icon?: string; brand?: string; items: { text: string; color?: string | RGB; icon?: string }[];
  footer?: string; at?: number; per?: number; cols?: number }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const out = outFade(p, t, D, 0.25); const at = p.at ?? 0.35, per = p.per ?? 0.18;
  const n = p.items.length, cols = p.cols || (tall ? 2 : Math.min(4, Math.ceil(n / 2))), rows = Math.ceil(n / cols);
  const tw = tall ? 440 : 360, thh = tall ? 230 : 200, gap = 30;
  const gw = cols * tw + (cols - 1) * gap, gh = rows * thh + (rows - 1) * gap;
  const x0 = (W - gw) / 2, y0 = tall ? H * 0.28 : (H - gh) / 2 + 30;
  const hd = sp(t, 0.05, fps, { damping: 18 }); const ft = ease(t, at + n * per + 0.2, at + n * per + 0.7);
  return (
    <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
      <Backdrop th={th} t={t} W={W} H={H} variant="grid" />
      {(p.icon || p.brand) && <div style={{ position: "absolute", left: 50, top: 36, display: "flex", alignItems: "center", gap: 18, opacity: hd }}>
        <Icon src={p.icon} size={72} /><div style={{ color: rgb(th.text), fontSize: 38, fontWeight: 800 }}>{p.brand}</div></div>}
      <div style={{ position: "absolute", left: 0, right: 0, top: tall ? H * 0.14 : y0 - 150, textAlign: "center", color: rgb(th.text), fontSize: tall ? 70 : 64,
        fontWeight: 900, letterSpacing: 2, opacity: hd, transform: `translateY(${(1 - hd) * 24}px)` }}>{p.title}</div>
      {p.items.map((it, i) => {
        const k = sp(t, at + i * per, fps, { damping: 12, stiffness: 220 }); if (t < at + i * per) return null;
        const c = it.color ? colorOf(it.color, th) : TILE_COLORS[i % TILE_COLORS.length];
        const x = x0 + (i % cols) * (tw + gap), y = y0 + Math.floor(i / cols) * (thh + gap);
        return <div key={i} style={{ position: "absolute", left: x, top: y, width: tw, height: thh, borderRadius: 26, padding: "24px 28px", boxSizing: "border-box",
          background: `linear-gradient(150deg, ${rgb(c)}, ${rgb(mix(c, [0, 0, 0], 0.35))})`, boxShadow: `0 18px 50px ${rgb(c, 0.35)}`,
          transform: `scale(${k}) translateY(${(1 - k) * 30}px)`, opacity: Math.min(1, k * 1.4) }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ color: "white", fontSize: 54, fontWeight: 900, lineHeight: 1 }}>{i + 1}</div><Icon src={it.icon} size={46} /></div>
          <div style={{ color: "white", fontSize: tall ? 40 : 34, fontWeight: 700, lineHeight: 1.15, marginTop: 16 }}>{it.text}</div></div>; })}
      {p.footer && <div style={{ position: "absolute", left: 0, right: 0, top: y0 + gh + 60, textAlign: "center", color: rgb(th.text), fontSize: tall ? 46 : 42,
        fontWeight: 800, opacity: ft }}>{p.footer}</div>}
      <Sweep t={t} at={0.2} />
    </AbsoluteFill>
  );
};
