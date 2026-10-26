// Looks (studio/looks.py): one template, `Look`, draws every "say it -> show it" element in a look's palette, type and
// structure, so a video's title card, list pop-ups, timer, number hit, panels, end slate, Short frame and cover all match.
// Props: {el, ...content}; the look comes from props.look / props._look (the engine resolves the timeline's kit.look).
// House rules built in: no glow (shadows are neutral and soft), animated in and out, readable on phones, bottom-right
// corner left free (watermark), Short text inside the 3:4 grid crop.
// LookBoard / LookMini: labelled photo boards of every element for picking a look.
import React from "react";
import { AbsoluteFill, Img, Easing } from "remotion";
import { RGB, rgb, mix, ease, sp, useT, count, fmt } from "./lib";

export type Look = {
  name: string; label: string; statement: string; mode: "light" | "dark"; family: string; font_name: string;
  bg: RGB; card: RGB; ink: RGB; sub: RGB; line: RGB; accent: RGB; accent2: RGB; accent_ink: RGB; good: RGB; bad: RGB; tint: RGB;
  head: string; body: string; num: string; mono: string; head_w: number; case: string; track: number;
  surface: string; radius: number; motion: string; emph: string; mark: string; timer: string; pill: string;
  title: string; cover: string; caption: string; header: string; backdrop: string;
};

const DEFAULT: Look = {
  name: "air-blue", label: "Air", statement: "", mode: "light", family: "air", font_name: "sf",
  bg: [255, 255, 255], card: [247, 247, 249], ink: [29, 29, 31], sub: [96, 96, 102], line: [222, 222, 224], accent: [0, 113, 227],
  accent2: [88, 86, 214], accent_ink: [255, 255, 255], good: [24, 150, 80], bad: [214, 40, 66], tint: [219, 234, 251],
  head: "-apple-system, 'SF Pro Display', sans-serif", body: "-apple-system, 'SF Pro Display', sans-serif", num: "-apple-system, sans-serif",
  mono: "ui-monospace, Menlo, monospace", head_w: 700, case: "none", track: -0.02,
  surface: "glass", radius: 32, motion: "rise", emph: "color", mark: "dot", timer: "ring", pill: "soft", title: "center", cover: "proof",
  caption: "card", header: "badge", backdrop: "gradient",
};

type C = { L: Look; t: number; fps: number; W: number; H: number; D: number; tall: boolean; board?: boolean };
type P = Record<string, any>;

// ------------------------------------------------------------------ primitives

const caseOf = (L: Look, s: string) => (L.case === "upper" ? s.toUpperCase() : s);
const dark = (L: Look) => L.mode === "dark";
const shadow = (L: Look, k = 1) => dark(L) ? `0 ${18 * k}px ${50 * k}px rgba(0,0,0,${0.45 * Math.min(1, k)})` : `0 ${16 * k}px ${44 * k}px rgba(20,20,30,${0.13 * Math.min(1.4, k)}), 0 2px 6px rgba(20,20,30,0.06)`;

/** motion in at `at` (and out at the end of the graphic) in the look's own way */
const enter = (c: C, at: number, outAt?: number): React.CSSProperties => {
  const { L, t, fps, D } = c;
  const k = (L.motion === "pop" || L.motion === "scale") ? sp(t, at, fps, { damping: 16, stiffness: 170 }) : ease(t, at, at + 0.5, Easing.out(Easing.cubic));
  const end = outAt ?? D;
  const o = 1 - ease(t, end - 0.35, end, Easing.in(Easing.cubic));
  if (t < at) return { opacity: 0 };
  switch (L.motion) {
    case "pop": return { opacity: Math.min(1, k * 1.8) * o, transform: `scale(${0.88 + 0.12 * k})` };
    case "scale": return { opacity: Math.min(1, k * 1.5) * o, transform: `scale(${1.07 - 0.07 * k})` };
    case "rise": return { opacity: k * o, transform: `translateY(${(1 - k) * 40}px)` };
    case "slide": return { opacity: Math.min(1, k * 2) * o, transform: `translateX(${(1 - k) * -80}px)` };
    case "wipe": return { opacity: o, clipPath: `inset(-20px ${(1 - k) * 100}% -20px -20px)` };
    case "mask": return { opacity: o, clipPath: `inset(${(1 - k) * 100}% -20px -20px -20px)`, transform: `translateY(${(1 - k) * 24}px)` };
    case "fade": return { opacity: k * o, filter: k < 1 ? `blur(${(1 - k) * 12}px)` : undefined };
    default: return { opacity: Math.min(1, k * 3) * o };   // type: the text itself types on
  }
};

/** panel surface in the look's style */
const surf = (L: Look, kind?: string): React.CSSProperties => {
  const s = kind || L.surface, r = L.radius;
  switch (s) {
    case "glass": return { borderRadius: r, background: rgb(L.card, dark(L) ? 0.78 : 0.86), backdropFilter: "blur(28px)", border: `1.5px solid ${rgb(L.ink, 0.08)}`, boxShadow: shadow(L) };
    case "solid": return { borderRadius: r, background: rgb(L.card), boxShadow: shadow(L, 0.6) };
    case "elevated": case "stack": return { borderRadius: r, background: rgb(L.card), boxShadow: shadow(L, 1.4) };
    case "outline": return { borderRadius: r, background: rgb(L.bg, 0.95), border: `2.5px solid ${rgb(L.ink, dark(L) ? 0.32 : 0.22)}` };
    case "flat": return { borderRadius: r, background: rgb(L.card) };
    case "editorial": return { borderRadius: 0, background: rgb(L.bg, 0.97), borderTop: `7px solid ${rgb(L.ink)}` };
    case "block": return { borderRadius: r, background: rgb(L.accent), color: rgb(L.accent_ink) };
    default: return { borderRadius: 0, background: rgb(L.bg, 0.92) };   // none (gallery): just the page colour
  }
};

const Box: React.FC<{ L: Look; style?: React.CSSProperties; kind?: string; children?: React.ReactNode }> = ({ L, style, kind, children }) => {
  const k = kind || L.surface;
  return (
    <div style={{ position: "absolute", boxSizing: "border-box", ...surf(L, k), ...style }}>
      {k === "stack" ? <div style={{ position: "absolute", left: 26, right: 26, bottom: -22, height: 40, borderRadius: L.radius, background: rgb(mix(L.card, L.bg, 0.45)), zIndex: -1, boxShadow: shadow(L, 0.4) }} /> : null}
      {children}
    </div>
  );
};

const onBlock = (L: Look, kind?: string) => (kind || L.surface) === "block";
const inkOn = (L: Look, kind?: string) => onBlock(L, kind) ? L.accent_ink : L.ink;
const subOn = (L: Look, kind?: string) => onBlock(L, kind) ? mix(L.accent_ink, L.accent, 0.25) : L.sub;

/** head text style */
const headS = (L: Look, size: number, extra: React.CSSProperties = {}): React.CSSProperties => ({
  fontFamily: L.head, fontWeight: L.head_w, fontSize: size, letterSpacing: `${L.track}em`, lineHeight: 1.08,
  textTransform: L.case === "upper" ? "uppercase" : "none", ...extra,
});
const bodyS = (L: Look, size: number, extra: React.CSSProperties = {}): React.CSSProperties => ({ fontFamily: L.body, fontWeight: 500, fontSize: size, lineHeight: 1.25, ...extra });
const kickS = (L: Look, size: number, color: RGB): React.CSSProperties => ({
  fontFamily: L.surface === "outline" && L.family === "technical" ? L.mono : L.body, fontWeight: 700, fontSize: size, letterSpacing: "0.14em",
  textTransform: "uppercase", color: rgb(color),
});

const clean = (w: string) => w.toLowerCase().replace(/[^a-z0-9%$.]/g, "").replace(/\.$/, "");

/** a line of text with its key words marked the look's way (colour, underline, highlighter, block, weight, gradient) */
const Rich: React.FC<{ c: C; text: string; keys?: string[]; at?: number; style: React.CSSProperties; color?: RGB; type?: boolean }> = ({ c, text, keys = [], at = 0, style, color, type }) => {
  const { L, t } = c;
  const ks = keys.map(clean);
  const words = text.split(" ");
  const shown = type || L.motion === "type" ? Math.floor(Math.max(0, t - at) * 38) : 1e9;   // typing: ~38 chars a second
  let used = 0;
  const base = color || L.ink;
  const k = ease(t, at + 0.25, at + 0.75);
  return (
    <span style={{ ...style, color: rgb(base) }}>
      {words.map((w, i) => {
        const vis = Math.max(0, Math.min(w.length, shown - used)); used += w.length + 1;
        const txt = shown >= 1e9 ? w : w.slice(0, vis);
        const hit = ks.includes(clean(w));
        const sp_ = i < words.length - 1 ? " " : "";
        if (!hit) return <React.Fragment key={i}>{txt}{sp_}</React.Fragment>;
        const em: React.CSSProperties = { position: "relative", display: "inline-block" };
        let deco = null;
        switch (L.emph) {
          case "color": em.color = rgb(L.accent); break;
          case "underline": em.color = rgb(base); deco = <span style={{ position: "absolute", left: 0, bottom: "0.02em", height: "0.09em", width: `${k * 100}%`, background: rgb(L.accent), borderRadius: 2 }} />; break;
          case "marker": em.backgroundImage = `linear-gradient(${rgb(L.accent, dark(L) ? 0.42 : 0.3)}, ${rgb(L.accent, dark(L) ? 0.42 : 0.3)})`; em.backgroundRepeat = "no-repeat";
            em.backgroundSize = `${k * 100}% 0.42em`; em.backgroundPosition = "0 88%"; break;
          case "block": em.background = rgb(L.accent); em.color = rgb(L.accent_ink); em.padding = "0 0.16em"; em.borderRadius = Math.min(10, L.radius * 0.4); break;
          case "weight": em.fontWeight = 800; break;
          case "gradient": em.backgroundImage = `linear-gradient(90deg, ${rgb(L.accent)}, ${rgb(L.accent2)})`; em.WebkitBackgroundClip = "text"; em.color = "transparent"; break;
        }
        return <React.Fragment key={i}><span style={em}>{txt}{deco}</span>{sp_}</React.Fragment>;
      })}
    </span>
  );
};

/** list / step number in the look's mark style */
const Mark: React.FC<{ L: Look; i: number; size: number; state?: "done" | "now" | "todo" | "plain"; kind?: string }> = ({ L, i, size, state = "plain", kind }) => {
  const blk = onBlock(L, kind);
  const fillC = state === "done" ? L.good : blk ? L.accent_ink : L.accent;
  const txtC = state === "done" ? [255, 255, 255] as RGB : blk ? L.accent : L.accent_ink;
  const check = <svg width={size * 0.56} height={size * 0.56} viewBox="0 0 24 24"><path d="M4 12.5l5 5L20 6.5" fill="none" stroke={rgb(txtC)} strokeWidth={3.4} strokeLinecap="round" strokeLinejoin="round" /></svg>;
  const n = state === "done" ? check : String(i + 1);
  const todo = state === "todo";
  const box = (r: number | string): React.CSSProperties => ({ width: size, height: size, borderRadius: r, flex: "none", display: "flex", alignItems: "center", justifyContent: "center",
    background: todo ? "transparent" : rgb(fillC), border: todo ? `3px solid ${rgb(blk ? L.accent_ink : L.line)}` : undefined, color: rgb(todo ? L.sub : txtC),
    fontFamily: L.num, fontWeight: 700, fontSize: size * 0.5, boxSizing: "border-box" });
  switch (L.mark) {
    case "circle": return <div style={box("50%")}>{n}</div>;
    case "square": return <div style={box(Math.min(6, L.radius))}>{n}</div>;
    case "dot": return state === "plain" ? <div style={{ width: size * 0.34, height: size * 0.34, margin: size * 0.33, borderRadius: "50%", background: rgb(fillC), flex: "none" }} /> : <div style={box("50%")}>{n}</div>;
    case "mono": return state === "plain" || state === "now" ? <div style={{ width: size * 1.25, flex: "none", fontFamily: L.mono, fontWeight: 600, fontSize: size * 0.62, color: rgb(blk ? L.accent_ink : L.accent) }}>{String(i + 1).padStart(2, "0")}</div> : <div style={box(4)}>{n}</div>;
    case "bar": return <div style={{ width: 8, height: size, background: rgb(fillC), flex: "none", borderRadius: 2 }} />;
    default: return state === "plain" || state === "now" ? <div style={{ width: size * 1.05, flex: "none", fontFamily: L.head, fontWeight: L.head_w < 500 ? 300 : 700, fontSize: size * 0.95, lineHeight: 1, color: rgb(blk ? L.accent_ink : L.accent) }}>{i + 1}</div> : <div style={box("50%")}>{n}</div>;
  }
};

/** a drawn tile for a tool/site when no logo file is given: rounded square in the tool's colour with its letter */
const Tile: React.FC<{ icon?: string; color?: RGB; letter?: string; size: number; r?: number }> = ({ icon, color = [90, 90, 96], letter = "?", size, r }) =>
  icon ? <Img src={icon} style={{ width: size, height: size, objectFit: "contain", flex: "none" }} /> :
    <div style={{ width: size, height: size, borderRadius: r ?? size * 0.24, background: rgb(color), color: "#fff", flex: "none", display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: "-apple-system, sans-serif", fontWeight: 700, fontSize: size * 0.52 }}>{letter}</div>;

// ------------------------------------------------------------------ backdrops (full-screen elements)

export const Back: React.FC<{ L: Look; W: number; H: number; t: number }> = ({ L, W, H, t }) => {
  const bg = L.bg, a = L.accent, s = Math.min(W, H);
  const lineC = rgb(L.ink, dark(L) ? 0.07 : 0.06);
  let layer: React.ReactNode = null;
  switch (L.backdrop) {
    case "gradient": layer = <AbsoluteFill style={{ background: `linear-gradient(160deg, ${rgb(mix(bg, a, dark(L) ? 0.16 : 0.08))} 0%, ${rgb(bg)} 55%, ${rgb(mix(bg, dark(L) ? [0, 0, 0] : [255, 255, 255], 0.3))} 100%)` }} />; break;
    case "grid": layer = <AbsoluteFill style={{ backgroundImage: `linear-gradient(${lineC} 1.5px, transparent 1.5px), linear-gradient(90deg, ${lineC} 1.5px, transparent 1.5px)`, backgroundSize: `${s / 12}px ${s / 12}px`, backgroundPosition: `${(t * 6) % (s / 12)}px 0` }} />; break;
    case "dots": layer = <AbsoluteFill style={{ backgroundImage: `radial-gradient(${rgb(L.ink, dark(L) ? 0.12 : 0.1)} 2px, transparent 2.6px)`, backgroundSize: `${s / 22}px ${s / 22}px`, backgroundPosition: `${(t * 5) % (s / 22)}px 0` }} />; break;
    case "lines": layer = <AbsoluteFill style={{ backgroundImage: `linear-gradient(${lineC} 1.5px, transparent 1.5px)`, backgroundSize: `100% ${s / 14}px` }} />; break;
    case "paper": layer = <AbsoluteFill><svg width={W} height={H} style={{ position: "absolute", opacity: 0.32, mixBlendMode: "multiply" }}><filter id="pg"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={4} /><feColorMatrix values="0 0 0 0 0.45  0 0 0 0 0.38  0 0 0 0 0.3  0 0 0 0.35 0" /></filter><rect width={W} height={H} filter="url(#pg)" /></svg></AbsoluteFill>; break;
    case "mesh": layer = <AbsoluteFill style={{ background: `linear-gradient(${125 + 8 * Math.sin(t * 0.3)}deg, ${rgb(mix(bg, a, 0.34))} 0%, ${rgb(bg)} 42%, ${rgb(bg)} 58%, ${rgb(mix(bg, L.accent2, 0.3))} 100%)` }} />; break;
    case "shape": layer = <div style={{ position: "absolute", width: s * 1.1, height: s * 1.1, right: -s * 0.35, top: -s * 0.4, borderRadius: "50%", background: rgb(mix(bg, a, 0.12)) }} />; break;
    case "band": layer = <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: H * 0.075, background: rgb(a) }} />; break;
    case "split": layer = <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: W > H ? W * 0.36 : W, height: W > H ? H : H * 0.3, background: rgb(a) }} />; break;
    case "frame": layer = <div style={{ position: "absolute", inset: s * 0.035, border: `3px solid ${rgb(L.ink, 0.85)}` }} />; break;
  }
  return <AbsoluteFill style={{ background: rgb(bg), overflow: "hidden" }}>{layer}</AbsoluteFill>;
};
const splitW = (L: Look, W: number, H: number) => L.backdrop === "split" && W > H ? W * 0.36 : 0;

// ------------------------------------------------------------------ elements

const Title: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, W, H, tall } = c;
  const big = tall ? 118 : 132;
  const sw = splitW(L, W, H);
  const layout = tall ? (L.title === "split" ? "stack" : L.title === "corner" ? "corner" : L.title) : L.title;
  const left = layout === "left" || layout === "split" || layout === "corner" || layout === "stack";
  const x0 = layout === "split" ? sw + W * 0.06 : W * 0.08;
  const kickColor = L.backdrop === "band" || L.backdrop === "split" ? L.ink : L.accent;
  const title = caseOf(L, p.title || "");
  const st: React.CSSProperties = left
    ? { position: "absolute", left: x0, right: W * 0.08, top: layout === "corner" ? H * 0.12 : undefined, bottom: layout === "corner" ? undefined : H * (tall ? 0.36 : 0.2) }
    : { position: "absolute", left: W * 0.08, right: W * 0.08, top: 0, bottom: 0, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center" };
  return (
    <AbsoluteFill>
      <Back L={L} W={W} H={H} t={c.t} />
      {layout === "split" && sw > 0 && !tall && p.mark !== false ? <div style={{ position: "absolute", left: sw * 0.18, top: H * 0.16, ...headS(L, 300, { color: rgb(L.accent_ink, 0.9), lineHeight: 1 }), ...enter(c, 0.1) }}>{p.num || "01"}</div> : null}
      <div style={st}>
        {p.kicker ? <div style={{ ...kickS(L, 38, kickColor), marginBottom: 26, ...enter(c, 0.1) }}>{p.kicker}</div> : null}
        <div style={{ ...headS(L, big, { maxWidth: tall ? W * 0.84 : W * (layout === "split" && sw > 0 ? 0.52 : layout === "stack" ? 0.5 : 0.8) }), ...enter(c, 0.25) }}>
          <Rich c={c} text={title} keys={p.keys} at={0.25} style={{}} />
        </div>
        {p.sub ? <div style={{ ...bodyS(L, 40, { color: rgb(L.sub), marginTop: 30 }), ...enter(c, 0.55) }}>{p.sub}</div> : null}
      </div>
      {layout === "stack" && !tall ? <Box L={L} style={{ right: W * 0.08, top: H * 0.18, width: W * 0.24, height: H * 0.5, overflow: "hidden", ...enter(c, 0.5) }}>
        {p.image ? <Img src={p.image} style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: L.radius }} /> : null}</Box> : null}
    </AbsoluteFill>
  );
};

const Contents: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, W, H, tall } = c;
  const items: string[] = (p.items || []).map((x: any) => (typeof x === "string" ? x : x.text));
  const per = p.per ?? 0.45, at0 = p.at ?? 0.5;
  const sw = splitW(L, W, H);
  const x0 = sw ? sw + W * 0.05 : W * 0.08;
  const cols = tall ? 1 : items.length > 3 ? 2 : 1;
  const cw = ((W - x0 - W * 0.08) - (cols - 1) * 40) / cols;
  return (
    <AbsoluteFill>
      <Back L={L} W={W} H={H} t={c.t} />
      <div style={{ position: "absolute", left: x0, top: tall ? H * 0.2 : H * 0.17, ...headS(L, tall ? 96 : 92), color: rgb(sw && false ? L.accent_ink : L.ink), ...enter(c, 0.1) }}>{caseOf(L, p.title || "")}</div>
      {items.map((it, i) => {
        const col = i % cols, row = Math.floor(i / cols);
        return (
          <Box key={i} L={L} style={{ left: x0 + col * (cw + 40), top: (tall ? H * 0.34 : H * 0.42) + row * (tall ? 210 : 190), width: cw, height: tall ? 170 : 150,
            display: "flex", alignItems: "center", gap: 28, padding: "0 36px", ...enter(c, at0 + i * per) }}>
            <Mark L={L} i={i} size={64} />
            <div style={{ ...bodyS(L, tall ? 50 : 46, { fontWeight: 650, color: rgb(inkOn(L)) }) }}>{it}</div>
          </Box>
        );
      })}
    </AbsoluteFill>
  );
};

/** side panel (right): list pop-ups and the key-word text panel share it; the face/screen stays visible on the left */
const sideRect = (c: C) => c.tall ? { left: 60, top: 300, width: c.W - 120 } : { left: c.W * 0.585, top: c.H * 0.14, width: c.W * 0.36 };

const List: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L } = c;
  const r = sideRect(c);
  const items: any[] = (p.items || []).map((x: any, i: number) => (typeof x === "string" ? { text: x, at: 0.3 + i * 0.6 } : x));
  const kind = L.surface;
  return (
    <AbsoluteFill>
      <Box L={L} style={{ ...r, padding: "44px 46px 38px", ...enter(c, 0) }}>
        {p.title ? <div style={{ ...kickS(L, 32, onBlock(L) ? L.accent_ink : L.accent), marginBottom: 26 }}>{p.title}</div> : null}
        {items.map((it, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 24, marginTop: i ? 26 : 0, ...enter(c, it.at ?? 0.3 + i * 0.6) }}>
            <Mark L={L} i={i} size={60} kind={kind} />
            <div style={{ ...bodyS(L, 44, { fontWeight: 650, color: rgb(inkOn(L)) }) }}>{it.text}</div>
          </div>
        ))}
      </Box>
    </AbsoluteFill>
  );
};

const Panel: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L } = c;
  const r = sideRect(c);
  const lines: string[] = p.lines || [];
  return (
    <AbsoluteFill>
      <Box L={L} style={{ ...r, padding: "46px 48px 44px", ...enter(c, 0) }}>
        {p.title ? <div style={{ ...headS(L, 58), color: rgb(inkOn(L)), marginBottom: 22 }}>{caseOf(L, p.title)}</div> : null}
        <div style={{ height: 4, width: 90, background: rgb(onBlock(L) ? L.accent_ink : L.accent), marginBottom: 26, borderRadius: 2 }} />
        {lines.map((ln, i) => (
          <div key={i} style={{ ...bodyS(L, 46, { fontWeight: 600, marginTop: i ? 18 : 0 }), ...enter(c, 0.35 + i * 0.5) }}>
            <Rich c={c} text={ln} keys={p.keys} at={0.35 + i * 0.5} style={{}} color={inkOn(L)} />
          </div>
        ))}
      </Box>
    </AbsoluteFill>
  );
};

const Pill: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, W, H, tall } = c;
  const size = tall ? 56 : 56;
  const st: Record<string, React.CSSProperties> = {
    solid: { background: rgb(L.accent), borderRadius: 999, color: rgb(L.accent_ink) },
    soft: { background: rgb(L.card, 0.94), borderRadius: 999, boxShadow: shadow(L, 0.8), border: `1.5px solid ${rgb(L.ink, 0.07)}` },
    outline: { background: rgb(L.bg, 0.94), borderRadius: Math.min(999, L.radius * 4 || 0), border: `3px solid ${rgb(L.ink)}` },
    tag: { background: rgb(L.bg, 0.96), borderRadius: 8, border: `2px solid ${rgb(L.accent)}`, fontFamily: L.mono },
    bar: { background: rgb(L.card), borderRadius: 0, borderLeft: `12px solid ${rgb(L.accent)}` },
    ink: { background: rgb(L.ink), borderRadius: 999, color: rgb(L.bg) },
  };
  const s = st[L.pill] || st.soft;
  const txtC: RGB = L.pill === "solid" ? L.accent_ink : L.pill === "ink" ? L.bg : L.ink;
  const keys = L.pill === "solid" || L.pill === "ink" ? [] : p.keys;
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, top: p.y ?? (tall ? H * 0.6 : H * 0.8), display: "flex", justifyContent: "center", ...enter(c, 0) }}>
        <div style={{ padding: `${size * 0.42}px ${size * 0.85}px`, maxWidth: W * 0.8, textAlign: "center", ...s }}>
          <Rich c={c} text={p.text || ""} keys={keys} at={0} style={{ ...bodyS(L, size, { fontWeight: 700, fontFamily: L.pill === "tag" ? L.mono : L.head === L.body ? L.body : L.head }) }} color={txtC} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

const clock = (s: number, tenths = true) => {
  const m = Math.floor(s / 60), ss = s % 60;
  return `${m}:${(tenths ? ss.toFixed(1) : Math.floor(ss).toString()).padStart(tenths ? 4 : 2, "0")}`;
};

const Timer: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, t, W, tall } = c;
  const from = p.from ?? 0.2, until = p.until ?? 2.5, rate = p.rate ?? 1;
  const run = Math.max(0, Math.min(t, until) - from) * rate;
  const fin = t >= until; const kf = fin ? ease(t, until, until + 0.4) : 0;
  const prog = Math.min(1, Math.max(0, (Math.min(t, until) - from) / Math.max(0.01, until - from)));
  const shown = fin && p.done ? p.done : clock(run, run < 600);
  const col = fin ? L.good : L.accent;
  const x = p.x ?? (tall ? W / 2 : W * 0.8), y = p.y ?? (tall ? 520 : 250);
  const lab = p.label ? <div style={{ ...kickS(L, 26, L.sub), marginBottom: 8 }}>{p.label}</div> : null;
  let body: React.ReactNode;
  switch (L.timer) {
    case "ring": {
      const R = 120, C_ = 2 * Math.PI * R;
      body = <Box L={L} style={{ left: -170, top: -190, width: 340, height: 380, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }} kind={L.surface === "block" ? "solid" : undefined}>
        <svg width={280} height={280} style={{ position: "absolute", top: 22 }}><circle cx={140} cy={140} r={R} fill="none" stroke={rgb(L.line)} strokeWidth={12} />
          <circle cx={140} cy={140} r={R} fill="none" stroke={rgb(col)} strokeWidth={12} strokeLinecap="round" strokeDasharray={`${C_ * prog} ${C_}`} transform="rotate(-90 140 140)" /></svg>
        <div style={{ position: "absolute", top: 22, width: 280, height: 280, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: L.num, fontWeight: 700, fontSize: fin && p.done ? 64 : 54, color: rgb(fin ? L.good : L.ink), fontVariantNumeric: "tabular-nums", transform: `scale(${1 + 0.08 * Math.sin(kf * Math.PI)})` }}>{shown}</div>
        <div style={{ position: "absolute", bottom: 26, ...kickS(L, 26, L.sub) }}>{p.label}</div>
      </Box>; break;
    }
    case "dial": {
      const ang = (run % 60) / 60 * 360;
      body = <Box L={L} style={{ left: -170, top: -200, width: 340, height: 400, display: "flex", flexDirection: "column", alignItems: "center" }} kind={L.surface === "block" ? "solid" : undefined}>
        <svg width={250} height={250} style={{ marginTop: 26 }}>
          <circle cx={125} cy={125} r={112} fill="none" stroke={rgb(L.ink, 0.85)} strokeWidth={4} />
          {Array.from({ length: 60 }, (_, i) => { const a = i / 60 * Math.PI * 2, l = i % 5 ? 8 : 18; return <line key={i} x1={125 + Math.sin(a) * 100} y1={125 - Math.cos(a) * 100} x2={125 + Math.sin(a) * (100 - l)} y2={125 - Math.cos(a) * (100 - l)} stroke={rgb(L.ink, i % 5 ? 0.35 : 0.8)} strokeWidth={i % 5 ? 2 : 4} />; })}
          <line x1={125} y1={125} x2={125 + Math.sin(ang * Math.PI / 180) * 92} y2={125 - Math.cos(ang * Math.PI / 180) * 92} stroke={rgb(col)} strokeWidth={6} strokeLinecap="round" />
          <circle cx={125} cy={125} r={9} fill={rgb(col)} /></svg>
        <div style={{ fontFamily: L.num, fontWeight: 700, fontSize: 52, color: rgb(fin ? L.good : L.ink), fontVariantNumeric: "tabular-nums", marginTop: 6 }}>{shown}</div>
        <div style={{ ...kickS(L, 20, L.sub), marginTop: 2 }}>{p.label}</div>
      </Box>; break;
    }
    case "bar":
      body = <Box L={L} style={{ left: -260, top: -80, width: 520, height: 160, padding: "22px 30px" }} kind={L.surface === "block" ? "solid" : undefined}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ ...kickS(L, 26, L.sub) }}>{p.label}</span>
          <span style={{ fontFamily: L.num, fontWeight: 700, fontSize: 58, color: rgb(fin ? L.good : L.ink), fontVariantNumeric: "tabular-nums" }}>{shown}</span></div>
        <div style={{ height: 14, background: rgb(L.line), marginTop: 12, borderRadius: Math.min(7, L.radius) }}><div style={{ height: 14, width: `${prog * 100}%`, background: rgb(col), borderRadius: Math.min(7, L.radius) }} /></div>
      </Box>; break;
    case "flip": {
      const chars = shown.split("");
      body = <div style={{ position: "absolute", left: -260, top: -110, width: 520, display: "flex", flexDirection: "column", alignItems: "center" }}>
        <div style={{ ...kickS(L, 22, L.ink), marginBottom: 12, background: rgb(L.bg, 0.9), padding: "4px 12px" }}>{p.label}</div>
        <div style={{ display: "flex", gap: 8 }}>{chars.map((ch, i) => /[0-9]/.test(ch)
          ? <div key={i} style={{ width: 74, height: 112, background: rgb(fin ? L.good : L.accent), color: rgb(fin ? [255, 255, 255] : L.accent_ink), fontFamily: L.num, fontWeight: 800, fontSize: 84, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: Math.min(8, L.radius) }}>{ch}</div>
          : <div key={i} style={{ fontFamily: L.num, fontWeight: 800, fontSize: 70, color: rgb(fin && p.done ? L.bg : L.ink), background: fin && p.done ? rgb(L.good) : undefined, padding: fin && p.done ? "14px 10px" : 0, alignSelf: "center" }}>{ch}</div>)}</div>
      </div>; break;
    }
    default:   // digital
      body = <Box L={L} style={{ left: -230, top: -95, width: 460, height: 190, display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 36px" }} kind={L.surface === "block" ? "solid" : undefined}>
        {lab}<div style={{ fontFamily: L.family === "technical" ? L.mono : L.num, fontWeight: L.head_w < 400 ? 300 : 700, fontSize: 86, lineHeight: 1, color: rgb(fin ? L.good : L.ink), fontVariantNumeric: "tabular-nums" }}>{shown}</div>
      </Box>;
  }
  // the wrapper has a real size so wipe/mask motions (clip-path) have something to reveal
  return <AbsoluteFill><div style={{ position: "absolute", left: x - 300, top: y - 240, width: 600, height: 480, ...enter(c, 0) }}>
    <div style={{ position: "absolute", left: 300, top: 240 }}>{body}</div></div></AbsoluteFill>;
};

const NumberHit: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, t, W, H, tall } = c;
  const v = count(t, p.at ?? 0.3, p.dur ?? 1.1, p.value ?? 0, p.from ?? 0);
  const col = p.good === true ? L.good : p.good === false ? L.bad : L.accent;
  const full = p.full;
  const r = full ? { left: 0, top: 0, width: W, height: H } : tall ? { left: 80, top: 320, width: W - 160, height: 560 } : { left: W * 0.58, top: H * 0.2, width: W * 0.36, height: H * 0.58 };
  const inner = (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: L.title === "center" || full ? "center" : "flex-start", padding: "0 54px", textAlign: L.title === "center" || full ? "center" : "left" }}>
      <div style={{ fontFamily: L.num, fontWeight: L.head_w < 400 ? 200 : 800, fontSize: full ? 300 : 210, lineHeight: 0.95, color: rgb(onBlock(L) ? L.accent_ink : col), letterSpacing: "-0.03em", fontVariantNumeric: "tabular-nums" }}>
        {p.prefix || ""}{fmt(v, p.decimals || 0)}{p.suffix || ""}</div>
      <div style={{ ...bodyS(L, 46, { fontWeight: 650, color: rgb(inkOn(L)), marginTop: 14 }) }}>{p.label}</div>
      {p.sub ? <div style={{ ...bodyS(L, 32, { color: rgb(subOn(L)), marginTop: 10 }) }}>{p.sub}</div> : null}
    </div>
  );
  return <AbsoluteFill>{full ? <><Back L={L} W={W} H={H} t={t} /><div style={{ ...enter(c, 0), position: "absolute", inset: 0 }}>{inner}</div></> :
    <Box L={L} style={{ ...r, ...enter(c, 0) }}>{inner}</Box>}</AbsoluteFill>;
};

const Plan: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, t } = c;
  const r = sideRect(c);
  const steps: any[] = p.steps || [];
  const kind = L.surface;
  return (
    <AbsoluteFill>
      <Box L={L} style={{ ...r, padding: "44px 46px 40px", ...enter(c, 0) }}>
        <div style={{ ...headS(L, 54), color: rgb(inkOn(L)), marginBottom: 30 }}>{caseOf(L, p.title || "Today")}</div>
        {steps.map((s, i) => {
          const done = s.done_at != null && t >= s.done_at;
          const now = !done && (i === 0 || (steps[i - 1].done_at != null && t >= steps[i - 1].done_at));
          const k = done ? ease(t, s.done_at, s.done_at + 0.3) : 0;
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 24, marginTop: i ? 24 : 0, ...enter(c, s.at ?? 0.2 + i * 0.25) }}>
              <div style={{ transform: `scale(${1 + 0.15 * Math.sin(k * Math.PI)})` }}><Mark L={L} i={i} size={58} state={done ? "done" : now ? "now" : "todo"} kind={kind} /></div>
              <div style={{ ...bodyS(L, 42, { fontWeight: 650, color: rgb(done ? subOn(L) : inkOn(L)), textDecoration: done && p.strike ? "line-through" : "none" }) }}>{s.text}</div>
            </div>
          );
        })}
      </Box>
    </AbsoluteFill>
  );
};

const Chip: React.FC<{ c: C; style: React.CSSProperties; children: React.ReactNode; at?: number }> = ({ c, style, children, at = 0 }) => {
  const { L } = c;
  return <div style={{ position: "absolute", display: "flex", alignItems: "center", gap: 20, padding: "18px 30px 18px 18px", ...surf(L, L.surface === "block" || L.surface === "none" ? "solid" : L.surface === "editorial" ? "flat" : L.surface === "stack" ? "elevated" : undefined),
    borderRadius: L.radius ? Math.min(999, L.radius * 1.4) : 0, ...enter(c, at), ...style }}>{children}</div>;
};

const Logo: React.FC<{ c: C; p: P }> = ({ c, p }) => (
  <AbsoluteFill>
    <Chip c={c} style={{ left: p.x ?? 90, top: p.y ?? 90 }}>
      <Tile icon={p.icon} color={p.color} letter={p.letter || (p.name || "?")[0]} size={84} />
      <div style={{ ...headS(c.L, 50, { textTransform: "none" }), color: rgb(c.L.ink) }}>{p.name}</div>
    </Chip>
  </AbsoluteFill>
);

const Term: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, H, tall } = c;
  return (
    <AbsoluteFill>
      <Chip c={c} style={{ left: p.x ?? 90, top: p.y ?? (tall ? 1150 : H * 0.7), padding: "22px 36px" }}>
        <div style={{ ...headS(L, 64), color: rgb(L.accent), lineHeight: 1 }}>{p.short}</div>
        <div style={{ width: 3, height: 54, background: rgb(L.line) }} />
        <div style={{ ...bodyS(L, 42, { fontWeight: 600, color: rgb(L.ink) }) }}>{p.full}</div>
      </Chip>
    </AbsoluteFill>
  );
};

const Source: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L } = c;
  return (
    <AbsoluteFill>
      <Chip c={c} style={{ left: p.x ?? 90, top: p.y ?? 90, padding: "14px 26px 14px 14px", gap: 16 }}>
        <Tile icon={p.icon} color={p.color} letter={p.letter || (p.name || "?")[0]} size={52} />
        <div><div style={{ ...kickS(L, 20, L.sub) }}>{p.kicker || "Source"}</div>
          <div style={{ ...bodyS(L, 32, { fontWeight: 650, color: rgb(L.ink) }) }}>{p.name}</div></div>
      </Chip>
    </AbsoluteFill>
  );
};

const MadeBy: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, W } = c;
  const tc: RGB = p.color || L.accent;
  const r = L.radius ? Math.min(999, L.radius * 1.4) : 0;
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, top: p.y ?? 60, display: "flex", justifyContent: "center", ...enter(c, 0) }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18, padding: "16px 34px", background: rgb(tc), color: rgb(on(tc)), borderRadius: r, boxShadow: shadow(L, 0.7), maxWidth: W * 0.8 }}>
          {p.icon ? <Tile icon={p.icon} size={46} /> : null}
          <span style={{ fontFamily: L.body, fontWeight: 600, fontSize: 30, letterSpacing: "0.16em", opacity: 0.85 }}>MADE BY</span>
          <span style={{ ...headS(L, 44, { textTransform: "none" }) }}>{p.tool}</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
const on = (c: RGB): RGB => (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] > 150 ? [20, 20, 22] : [255, 255, 255]);

const Versus: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, W, H, tall } = c;
  const side = (s: any, x: number, at: number) => (
    <Chip c={c} at={at} style={{ left: x, top: tall ? 60 : 40, transform: `translateX(-50%) ${(enter(c, at).transform as string) || ""}`, padding: "14px 30px 14px 14px" }}>
      <Tile icon={s.icon} color={s.color} letter={s.letter || (s.name || "?")[0]} size={56} />
      <span style={{ ...headS(L, 42, { textTransform: "none" }), color: rgb(L.ink) }}>{s.name}</span>
    </Chip>
  );
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: W / 2 - 2, top: 0, width: 4, height: H, background: rgb(L.bg), opacity: enter(c, 0).opacity as number }} />
      {side(p.left || {}, W * 0.25, 0.05)}{side(p.right || {}, W * 0.75, 0.2)}
      <div style={{ position: "absolute", left: W / 2 - 46, top: H / 2 - 46, width: 92, height: 92, borderRadius: L.radius ? "50%" : 0, background: rgb(L.accent), color: rgb(L.accent_ink),
        display: "flex", alignItems: "center", justifyContent: "center", ...headS(L, 38), ...enter(c, 0.3) }}>vs</div>
    </AbsoluteFill>
  );
};

const End: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, W, H, board } = c;
  return (
    <AbsoluteFill>
      <Back L={L} W={W} H={H} t={c.t} />
      {board ? <>   {/* where YouTube puts its end-screen elements: kept free */}
        <div style={{ position: "absolute", left: W * 0.07, top: H * 0.2, width: W * 0.36, height: W * 0.36 * 9 / 16, border: `4px dashed ${rgb(L.sub, 0.6)}`, borderRadius: 16 }} />
        <div style={{ position: "absolute", right: W * 0.1, top: H * 0.22, width: W * 0.17, height: W * 0.17, border: `4px dashed ${rgb(L.sub, 0.6)}`, borderRadius: "50%" }} /></> : null}
      <div style={{ position: "absolute", left: W * 0.1, right: W * 0.1, bottom: H * 0.1, textAlign: "center", ...enter(c, 0.2) }}>
        <div style={{ ...headS(L, 72), color: rgb(L.ink) }}><Rich c={c} text={caseOf(L, p.line || "")} keys={p.keys || (p.line || "").split(" ").slice(-1)} at={0.2} style={{}} /></div>
        {p.handle ? <div style={{ ...bodyS(L, 34, { color: rgb(L.sub), marginTop: 16, fontWeight: 600 }) }}>{p.handle}</div> : null}
      </div>
    </AbsoluteFill>
  );
};

/** Short frame parts: header (badge), the caption band style; content (top) and face (below) show through */
const ShortFrame: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, W, H } = c;
  const capY = p.cap_y ?? 1020;
  const capTxt = <Rich c={c} text={caseOf(L, p.caption || "")} keys={p.keys} at={0} style={{ ...headS(L, 64, { lineHeight: 1.1 }) }}
    color={L.caption === "block" ? L.accent_ink : L.caption === "clean" ? [255, 255, 255] : L.ink} />;
  const capBox: Record<string, React.CSSProperties> = {
    band: { left: 0, right: 0, top: capY, height: 150, background: rgb(L.bg), display: "flex", alignItems: "center", justifyContent: "center", padding: "0 50px" },
    pill: { left: 60, right: 60, top: capY + 10, padding: "24px 36px", background: rgb(L.card, 0.96), borderRadius: 999, textAlign: "center", boxShadow: shadow(L, 0.6) },
    card: { left: 60, right: 60, top: capY, padding: "28px 40px", background: rgb(L.card, 0.96), borderRadius: Math.max(18, L.radius), textAlign: "center", boxShadow: shadow(L, 0.8) },
    block: { left: 60, right: 60, top: capY + 10, padding: "20px 34px", background: rgb(L.accent), borderRadius: Math.min(8, L.radius), textAlign: "center" },
    clean: { left: 60, right: 60, top: capY + 20, textAlign: "center", filter: "drop-shadow(0 3px 10px rgba(0,0,0,0.55))" },
  };
  const hdr = L.header;
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 270, overflow: "hidden" }}><Back L={L} W={W} H={270} t={c.t} /></div>
      <div style={{ position: "absolute", left: 0, right: 0, top: 120, display: "flex", justifyContent: hdr === "tab" ? "flex-start" : "center", paddingLeft: hdr === "tab" ? 60 : 0, ...enter(c, 0) }}>
        {hdr === "badge" ? <div style={{ padding: "14px 30px", borderRadius: 999, background: rgb(L.accent), color: rgb(L.accent_ink), ...kickS(L, 28, L.accent_ink) }}>{p.badge}</div>
          : hdr === "bar" ? <div style={{ padding: "12px 28px", borderLeft: `10px solid ${rgb(L.accent)}`, background: rgb(L.card), ...kickS(L, 30, L.ink) }}>{p.badge}</div>
            : <div style={{ ...kickS(L, 30, L.accent), borderBottom: `4px solid ${rgb(L.accent)}`, paddingBottom: 8 }}>{p.badge}</div>}
      </div>
      <div style={{ position: "absolute", ...capBox[L.caption] || capBox.card, ...enter(c, 0.1) }}>{capTxt}</div>
    </AbsoluteFill>
  );
};

const ShortEnd: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, W, H } = c;
  const yt = (p.version || "youtube") === "youtube";
  const cta = p.cta || (yt ? "Full video · link below" : "Full video · link in bio");
  const btn = p.button || (yt ? "Subscribe" : "Follow");
  return (
    <AbsoluteFill>
      <Back L={L} W={W} H={H} t={c.t} />
      {p.face ? <Img src={p.face} style={{ position: "absolute", inset: 0, width: W, height: H, objectFit: "cover", opacity: 0.22, filter: "blur(18px)" }} /> : null}
      <div style={{ position: "absolute", left: 80, right: 80, top: 520, textAlign: L.title === "center" || L.title === "stack" ? "center" : "left" }}>
        {p.kicker ? <div style={{ ...kickS(L, 34, L.accent), marginBottom: 24, ...enter(c, 0.1) }}>{p.kicker}</div> : null}
        <div style={{ ...headS(L, 112), color: rgb(L.ink), ...enter(c, 0.2) }}>{caseOf(L, p.title || "")}</div>
        <Box L={L} kind={L.surface === "block" ? "flat" : undefined} style={{ position: "relative", marginTop: 70, padding: "34px 40px", ...enter(c, 0.45) }}>
          <div style={{ ...bodyS(L, 46, { fontWeight: 650, color: rgb(L.ink) }) }}>{cta}</div>
        </Box>
        <div style={{ display: "flex", justifyContent: L.title === "center" || L.title === "stack" ? "center" : "flex-start", marginTop: 46, ...enter(c, 0.7) }}>
          <div style={{ padding: "26px 64px", borderRadius: L.radius ? 999 : 0, background: rgb(L.accent), color: rgb(L.accent_ink), fontFamily: L.body, fontWeight: 700, fontSize: 48 }}>{btn}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Short cover (1080x1920 still): text inside the 3:4 grid crop (y 240-1680), proof visual, never a face at the bottom */
const Cover: React.FC<{ c: C; p: P }> = ({ c, p }) => {
  const { L, W, H } = c;
  const hook = caseOf(L, p.hook || "");
  const proof = (style: React.CSSProperties) => (
    <Box L={L} kind={L.surface === "block" || L.surface === "none" || L.surface === "editorial" ? "elevated" : undefined} style={{ overflow: "hidden", ...style }}>
      {p.proof ? <Img src={p.proof} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> :
        <div style={{ position: "absolute", inset: 0, background: `linear-gradient(135deg, ${rgb(L.tint)}, ${rgb(L.card)})`, display: "flex", alignItems: "center", justifyContent: "center", ...kickS(L, 28, L.sub) }}>proof</div>}
    </Box>
  );
  const badge = p.badge ? <div style={{ display: "inline-block", padding: "12px 26px", borderRadius: L.radius ? 999 : 0, background: rgb(L.accent), ...kickS(L, 28, L.accent_ink) }}>{p.badge}</div> : null;
  const big = (size: number, color?: RGB) => <div style={{ ...headS(L, size, { lineHeight: 1.02 }) }}><Rich c={c} text={hook} keys={p.keys} style={{}} color={color} /></div>;
  let body: React.ReactNode;
  switch (L.cover) {
    case "proof":
      body = <>{proof({ left: 70, right: 70, top: 280, height: 760 })}<div style={{ position: "absolute", left: 80, right: 80, top: 1110 }}>{badge}<div style={{ marginTop: 28 }}>{big(112)}</div></div></>; break;
    case "poster":
      body = <><div style={{ position: "absolute", left: 80, right: 80, top: 300 }}>{badge}<div style={{ marginTop: 40 }}>{big(156)}</div></div>{proof({ left: 300, right: 70, top: 1180, height: 480 })}</>; break;
    case "band":
      body = <><div style={{ position: "absolute", left: 0, right: 0, top: 260, height: 640, background: rgb(L.accent), padding: "60px 80px", boxSizing: "border-box" }}>
        <div style={{ ...kickS(L, 30, L.accent_ink), marginBottom: 30 }}>{p.badge}</div>{big(124, L.accent_ink)}</div>{proof({ left: 70, right: 70, top: 960, height: 700 })}</>; break;
    case "split":
      body = <><div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 960, background: rgb(L.accent) }} />
        <div style={{ position: "absolute", left: 80, right: 80, top: 320 }}><div style={{ ...kickS(L, 30, L.accent_ink), marginBottom: 30 }}>{p.badge}</div>{big(124, L.accent_ink)}</div>
        {proof({ left: 70, right: 70, top: 900, height: 760 })}</>; break;
    default:   // stack: text top, proof below
      body = <><div style={{ position: "absolute", left: 80, right: 80, top: 290 }}>{badge}<div style={{ marginTop: 34 }}>{big(124)}</div></div>{proof({ left: 70, right: 70, top: 900, height: 760 })}</>;
  }
  return <AbsoluteFill><Back L={L} W={W} H={H} t={c.t} />{body}</AbsoluteFill>;
};

const ELS: Record<string, React.FC<{ c: C; p: P }>> = {
  title: Title, contents: Contents, list: List, panel: Panel, pill: Pill, timer: Timer, number: NumberHit, plan: Plan,
  logo: Logo, term: Term, source: Source, madeby: MadeBy, versus: Versus, end: End, short: ShortFrame, shortend: ShortEnd, cover: Cover,
};

const lookOf = (p: P): Look => ({ ...DEFAULT, ...(p._look || (typeof p.look === "object" ? p.look : {})) });

/** the template: {el, ...content}; see studio/looks.py */
export const LookEl: React.FC<P> = (p) => {
  const { t, fps, W, H, D, tall } = useT();
  const E = ELS[p.el] || Title;
  return <AbsoluteFill style={{ fontFamily: lookOf(p).body }}><E c={{ L: lookOf(p), t, fps, W, H, D, tall }} p={p} /></AbsoluteFill>;
};

// ------------------------------------------------------------------ boards

/** one element drawn at its own design size, scaled into a cell, caught at time `t`, over a stand-in or real frame */
const Cell: React.FC<{ L: Look; el: string; p: P; t: number; x: number; y: number; w: number; tall?: boolean; under?: React.ReactNode; label: string; fps: number }> = ({ L, el, p, t, x, y, w, tall, under, label, fps }) => {
  const dw = tall ? 1080 : 1920, dh = tall ? 1920 : 1080, s = w / dw;
  const E = ELS[el];
  return (
    <div style={{ position: "absolute", left: x, top: y }}>
      <div style={{ fontFamily: "-apple-system, sans-serif", fontSize: 19, fontWeight: 600, color: "#55555c", marginBottom: 7, letterSpacing: "0.02em" }}>{label}</div>
      <div style={{ width: w, height: dh * s, overflow: "hidden", borderRadius: 10, position: "relative", boxShadow: "0 2px 10px rgba(0,0,0,0.12)", background: "#ddd" }}>
        <div style={{ width: dw, height: dh, transform: `scale(${s})`, transformOrigin: "0 0", position: "absolute", fontFamily: L.body }}>
          {under}
          <E c={{ L, t, fps, W: dw, H: dh, D: 1e4, tall: !!tall, board: true }} p={p} />
        </div>
      </div>
    </div>
  );
};

/** stand-in footage when no real frame is given: a neutral room with a person, or a light app window */
const StandIn: React.FC<{ kind: "camera" | "screen" | "tall"; img?: string; W: number; H: number }> = ({ kind, img, W, H }) => {
  if (img) return <Img src={img} style={{ position: "absolute", inset: 0, width: W, height: H, objectFit: "cover" }} />;
  if (kind === "screen") return <AbsoluteFill style={{ background: "#e9ebef" }}>
    <div style={{ position: "absolute", left: 60, top: 60, right: 60, bottom: 60, background: "#fff", borderRadius: 18, boxShadow: "0 4px 20px rgba(0,0,0,0.08)" }}>
      <div style={{ height: 64, borderBottom: "2px solid #eee", display: "flex", gap: 14, alignItems: "center", paddingLeft: 26 }}>{[0, 1, 2].map((i) => <div key={i} style={{ width: 18, height: 18, borderRadius: 9, background: "#d9d9de" }} />)}</div>
      {Array.from({ length: 9 }, (_, i) => <div key={i} style={{ height: 22, margin: "34px 60px 0", width: `${50 + ((i * 37) % 45)}%`, background: "#eceef2", borderRadius: 11 }} />)}
    </div></AbsoluteFill>;
  const cx = kind === "tall" ? W / 2 : W * 0.34;
  return <AbsoluteFill style={{ background: "linear-gradient(180deg, #8d8a86 0%, #6f6b67 100%)" }}>
    <div style={{ position: "absolute", left: cx - W * 0.06 * (kind === "tall" ? 2.6 : 1), top: H * (kind === "tall" ? 0.25 : 0.24), width: W * 0.12 * (kind === "tall" ? 2.6 : 1), height: W * 0.15 * (kind === "tall" ? 2.6 : 1), borderRadius: "50%", background: "#4c4744" }} />
    <div style={{ position: "absolute", left: cx - W * 0.17 * (kind === "tall" ? 2.6 : 1), top: H * (kind === "tall" ? 0.5 : 0.62), width: W * 0.34 * (kind === "tall" ? 2.6 : 1), height: H, borderRadius: "45% 45% 0 0", background: "#3f3b39" }} />
  </AbsoluteFill>;
};

const Swatch: React.FC<{ c: RGB; label: string }> = ({ c, label }) => (
  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
    <div style={{ width: 62, height: 62, borderRadius: 14, background: rgb(c), border: "2px solid rgba(0,0,0,0.12)" }} />
    <div style={{ fontFamily: "-apple-system, sans-serif", fontSize: 15, color: "#666" }}>{label}</div></div>
);

const cellsOf = (p: P) => p.cells || {};
const fr = (p: P) => p.frames || {};

export const LookBoard: React.FC<P> = (p) => {
  const { fps } = useT();
  const L = lookOf(p); const cells = cellsOf(p); const f = fr(p);
  const cw = 586, gx = 20, rowH = 330 + 32 + 22, x0 = 30, y0 = 140;
  const land: [string, string, string?][] = [
    ["title", "Title card / cold-open title"], ["contents", "Contents page"], ["end", "End slate (sides free for end screen)"],
    ["list", "List pop-ups", "camera"], ["panel", "Text panel (key words)", "camera"], ["pill", "Key-line pill", "camera"],
    ["timer", "Stopwatch → lands on the number", "screen"], ["number", "Number hit", "camera"], ["plan", "Plan card with ticks", "camera"],
    ["logo", "Logo pop-up + acronym", "camera"], ["madeby", "MADE BY <tool> + source tag", "screen"], ["versus", "Side-by-side labels", "screen"],
  ];
  const under = (k?: string, extra?: string) => k ? <><StandIn kind={k as any} img={f[k]} W={1920} H={1080} />
    {extra ? (() => { const E = ELS[extra]; const cc = cells[extra] || {}; return <E c={{ L, t: cc.t ?? 1.5, fps, W: 1920, H: 1080, D: 1e4, tall: false, board: true }} p={cc.props || {}} />; })() : null}</> : null;
  const tallX = x0 + 3 * cw + 2 * gx + 40, tw = 400, tg = 26;
  const ink = "#1d1d1f";
  return (
    <AbsoluteFill style={{ background: "#f4f4f6" }}>
      <div style={{ position: "absolute", left: x0, top: 26, right: 30, display: "flex", alignItems: "center", gap: 30 }}>
        {p.number ? <div style={{ fontFamily: "-apple-system, sans-serif", fontWeight: 800, fontSize: 64, color: ink }}>{p.number}</div> : null}
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: "-apple-system, sans-serif", fontWeight: 700, fontSize: 44, color: ink }}>{L.label} <span style={{ color: "#8a8a90", fontWeight: 500, fontSize: 30 }}>· {L.name}</span></div>
          <div style={{ fontFamily: "-apple-system, sans-serif", fontSize: 25, color: "#55555c", marginTop: 4 }}>{L.statement}</div>
        </div>
        {([[L.bg, "bg"], [L.card, "card"], [L.ink, "text"], [L.accent, "accent"], [L.good, "yes"], [L.bad, "no"]] as [RGB, string][]).map(([c, l]) => <Swatch key={l} c={c} label={l} />)}
      </div>
      {land.map(([el, label, k], i) => {
        const col = i % 3, row = Math.floor(i / 3);
        const cc = cells[el] || {};
        const extra = el === "logo" ? "term" : el === "madeby" ? "source" : undefined;
        return <Cell key={el} L={L} el={el} p={cc.props || {}} t={cc.t ?? 1.5} fps={fps} x={x0 + col * (cw + gx)} y={y0 + row * rowH} w={cw} label={label} under={under(k, extra)} />;
      })}
      {([["short", "Short frame", "tall"], ["shortend", "Short end card"], ["cover", "Short cover"]] as [string, string, string?][]).map(([el, label, k], i) => {
        const cc = cells[el] || {};
        const und = el === "short" ? <><div style={{ position: "absolute", left: 0, top: 270, width: 1080, height: 750, overflow: "hidden" }}><StandIn kind="screen" img={f.screen} W={1080} H={750} /></div>
          <div style={{ position: "absolute", left: 0, top: 1020, width: 1080, height: 900, overflow: "hidden" }}><StandIn kind="tall" img={f.tall || f.camera} W={1080} H={900} /></div></> : null;
        const pp = el === "cover" && f.screen ? { ...cc.props, proof: f.screen } : cc.props || {};
        return <Cell key={el} L={L} el={el} p={pp} t={cc.t ?? 1.5} fps={fps} x={tallX + i * (tw + tg)} y={y0} w={tw} tall label={label} under={und} />;
      })}
      <div style={{ position: "absolute", left: tallX, top: y0 + 711 + 60 + 20, width: 3 * tw + 2 * tg, height: 640, borderRadius: 16, background: rgb(L.bg), overflow: "hidden", boxShadow: "0 2px 10px rgba(0,0,0,0.12)" }}>
        <Back L={L} W={3 * tw + 2 * tg} H={640} t={1} />
        <div style={{ position: "absolute", left: 50, top: L.backdrop === "band" ? 80 : 40, right: 50 }}>
          <div style={{ ...kickS(L, 22, L.accent) }}>Type · {L.font_name}</div>
          <div style={{ ...headS(L, 112), color: rgb(L.ink), marginTop: 12 }}>{caseOf(L, "Aa Bb 0123")}</div>
          <div style={{ ...bodyS(L, 34, { color: rgb(L.ink), marginTop: 14 }) }}>Body text reads clearly on a phone screen.</div>
          <div style={{ display: "flex", gap: 14, marginTop: 34, flexWrap: "wrap" }}>
            {[["surface", L.surface], ["corners", `${L.radius}px`], ["motion", L.motion], ["key word", L.emph], ["marks", L.mark], ["timer", L.timer], ["backdrop", L.backdrop]].map(([k, v]) =>
              <div key={k} style={{ padding: "10px 18px", borderRadius: 999, background: rgb(L.card), border: `1.5px solid ${rgb(L.line)}`, fontFamily: L.body, fontSize: 22, color: rgb(L.ink) }}>
                <span style={{ color: rgb(L.sub) }}>{k} </span><b>{v}</b></div>)}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** compact strip for contact boards: number + name, title card, list pop-ups over a frame, cover */
export const LookMini: React.FC<P> = (p) => {
  const { fps } = useT();
  const L = lookOf(p); const cells = cellsOf(p); const f = fr(p);
  const c = (el: string) => cells[el] || {};
  return (
    <AbsoluteFill style={{ background: "#ffffff" }}>
      <div style={{ position: "absolute", left: 24, top: 6, right: 24, display: "flex", alignItems: "baseline", gap: 18, fontFamily: "-apple-system, sans-serif" }}>
        <span style={{ fontWeight: 800, fontSize: 40, color: "#1d1d1f" }}>{p.number}</span>
        <span style={{ fontWeight: 700, fontSize: 28, color: "#1d1d1f" }}>{L.label}</span>
        <span style={{ fontSize: 20, color: "#8a8a90" }}>{L.name}</span>
      </div>
      <Cell L={L} el="title" p={c("title").props || {}} t={c("title").t ?? 2} fps={fps} x={24} y={44} w={640} label="" />
      <Cell L={L} el="list" p={c("list").props || {}} t={c("list").t ?? 2} fps={fps} x={684} y={44} w={640} label="" under={<StandIn kind="camera" img={f.camera} W={1920} H={1080} />} />
      <Cell L={L} el="cover" p={f.screen ? { ...c("cover").props, proof: f.screen } : c("cover").props || {}} t={1} fps={fps} x={1350} y={44} w={222} tall label="" />
    </AbsoluteFill>
  );
};
