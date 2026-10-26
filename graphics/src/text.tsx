// Text graphics: Captions (kinetic / phrase / karaoke), Kinetic (hype words), LowerThird, Pill, Chips, ListReveal, StatPanel.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import { Backdrop, Base, Glow, Icon, PALETTE, Panel, RGB, Stamp, colorOf, ease, fonts, life, mix, rgb, sp, useT, useTheme } from "./lib";
import { outFade } from "./lib";

type Word = [number, number, string];
const clean = (s: string) => s.toLowerCase().replace(/[^a-z0-9%#.']/g, "").replace(/\.$/, "");

/** Burned captions from CHECKED words (never re-transcribed).
 * style "kinetic": 1-4 word groups, each word springs in, key words bigger in the accent colour (Shorts).
 * style "phrase": given phrases shown whole, white with a black outline (hook / cold open of long videos).
 * style "karaoke": a line at a time, the spoken word lights up. {words, phrases?, keys?, y?, size?} */
export const Captions: React.FC<Base & { words: Word[]; phrases?: string[]; cues?: [number, number, string][]; style?: string; keys?: string[]; y?: number | null; y_at?: [number, number][]; size?: number; max?: number }> = (p) => {
  const { t, fps, W, H, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const style = p.style || "kinetic";
  const keys = new Set((p.keys || []).map(clean));
  let y = p.y ?? (tall ? H * 0.62 : H * 0.84);
  if (p.y_at) for (const [ta, ya] of p.y_at) if (t >= ta) y = ya;     // captions sit at the seam in stacked parts
  const size = p.size ?? (tall ? 84 : 64);
  const ws = p.words || [];
  // groups
  let groups: { a: number; b: number; ws: Word[] }[] = [];
  if (p.cues?.length) {   // whole cues (e.g. a translation): each shown for its own time
    groups = p.cues.map(([a, b, txt]) => ({ a, b, ws: txt.split(" ").map((w) => [a, b, w] as Word) }));
  } else if (style === "phrase" && p.phrases?.length) {
    let i = 0;
    for (const ph of p.phrases) {
      const n = ph.split(/[\s-]+/).filter((x) => clean(x)).length; const g = ws.slice(i, i + n); i += n;
      if (g.length) groups.push({ a: g[0][0], b: g[g.length - 1][1], ws: ph.split(" ").map((w, k) => [g[Math.min(k, g.length - 1)][0], g[Math.min(k, g.length - 1)][1], w] as Word) });
    }
  } else {
    const max = p.max ?? (style === "karaoke" ? 6 : 3);
    let cur: Word[] = [];
    ws.forEach((w, i) => {
      cur.push(w);
      const gap = i + 1 < ws.length ? ws[i + 1][0] - w[1] : 9;
      const lone = cur.length === 1 && clean(w[2]).length <= 3 && !/[.,!?]$/.test(w[2]);   // never flash a lone "a" / "to": keep it with the next words
      if (cur.length >= max || ((gap > 0.35 || /[.,!?]$/.test(w[2])) && !lone)) { groups.push({ a: cur[0][0], b: cur[cur.length - 1][1], ws: cur }); cur = []; }
    });
    if (cur.length) groups.push({ a: cur[0][0], b: cur[cur.length - 1][1], ws: cur });
  }
  // each group stays until the next starts (no flicker in short gaps)
  const gi = groups.findIndex((g, i) => t >= g.a - 0.05 && t < (i + 1 < groups.length ? groups[i + 1].a - 0.05 : g.b + 0.6));
  if (gi < 0) return null;
  const g = groups[gi];
  const outline = `${size * 0.09}px`;
  return (
    <AbsoluteFill style={{ fontFamily: F.display }}>
      <div style={{ position: "absolute", left: tall ? 50 : 160, right: tall ? 50 : 160, top: y, transform: "translateY(-50%)", display: "flex", flexWrap: "wrap",
        justifyContent: "center", gap: `${size * 0.12}px ${size * 0.26}px`, textAlign: "center" }}>
        {g.ws.map((w, k) => {
          const isKey = keys.has(clean(w[2]));
          const on = style === "phrase" ? 1 : sp(t, w[0] - 0.04, fps, { damping: 13, stiffness: 300 });
          const lit = style === "karaoke" ? t >= w[0] - 0.03 : true;
          const col = isKey ? th.accent : th.text;
          if (style !== "phrase" && t < w[0] - 0.06 && style === "kinetic") return <span key={k} style={{ opacity: 0, fontSize: size * (isKey ? 1.25 : 1), fontWeight: 900 }}>{w[2]}</span>;
          return (
            <span key={k} style={{ display: "inline-block", fontSize: size * (isKey && style !== "phrase" ? 1.25 : 1), fontWeight: 900, lineHeight: 1.1,
              color: rgb(lit ? col : [200, 200, 210]), opacity: style === "karaoke" ? (lit ? 1 : 0.55) : 1,
              transform: `scale(${style === "kinetic" ? interpolate(on, [0, 1], [0.6, 1]) : 1}) translateY(${style === "kinetic" ? (1 - on) * 18 : 0}px)`,
              WebkitTextStroke: `${outline} black`, paintOrder: "stroke fill",
              textShadow: isKey ? `0 0 ${size * 0.4}px ${rgb(th.accent, 0.7)}, 0 6px 18px rgba(0,0,0,0.7)` : "0 6px 18px rgba(0,0,0,0.7)" }}>{w[2]}</span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/** Kinetic type: big words hit one after another (hype / claims / key line). {lines:[{text, at, color, size}], layout: center|stack, bg} */
export const Kinetic: React.FC<Base & { lines: { text: string; at: number; color?: string; size?: number; out?: number }[]; layout?: string; dark?: number; y?: number }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const stack = (p.layout || "stack") === "stack";
  const vis = p.lines.filter((l) => t >= l.at && (l.out === undefined || t < l.out));
  const shown = stack ? vis : vis.slice(-1);
  const total = shown.length;
  return (
    <AbsoluteFill style={{ fontFamily: F.display, background: p.dark ? `rgba(0,0,0,${p.dark * life(t, D, 0, 0.2, 0.25)})` : undefined }}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: p.y !== undefined ? "flex-start" : "center", paddingTop: p.y ?? 0, flexDirection: "column", gap: 10 }}>
        {shown.map((l, i) => {
          const k = sp(t, l.at, fps, { damping: 11, stiffness: 260 }); const c = colorOf(l.color || (i === total - 1 ? "accent" : "text"), th);
          return <div key={l.text + l.at} style={{ fontSize: l.size || (tall ? 110 : 130), fontWeight: 900, color: rgb(c), letterSpacing: interpolate(k, [0, 1], [18, 1]),
            transform: `scale(${interpolate(k, [0, 1], [1.8, 1])})`, opacity: Math.min(1, k * 2), textShadow: `0 0 50px ${rgb(c, 0.5)}, 0 10px 40px rgba(0,0,0,0.8)`, textAlign: "center",
            padding: "0 60px", lineHeight: 1.05 }}>{l.text}</div>;
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** Name tag sliding in. {name, role, x, y, icon} */
export const LowerThird: React.FC<Base & { name: string; role?: string; x?: number; y?: number; icon?: string }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const k = sp(t, 0, fps, { damping: 18 }); const k2 = sp(t, 0.15, fps, { damping: 18 });
  const out = ease(t, D - 0.35, D, Easing.in(Easing.cubic));
  const x = p.x ?? (tall ? 60 : 70), y = p.y ?? (tall ? H * 0.70 : H * 0.70);
  return (
    <AbsoluteFill style={{ fontFamily: F.display }}>
      <div style={{ position: "absolute", left: x, top: y, transform: `translateX(${(1 - k) * -700 - out * 700}px)`, display: "flex", alignItems: "stretch" }}>
        <div style={{ width: 12, borderRadius: 6, background: rgb(th.accent), boxShadow: `0 0 24px ${rgb(th.accent, 0.8)}` }} />
        <div style={{ marginLeft: 18, padding: "18px 34px", borderRadius: 18, background: rgb(mix(th.bg, [30, 34, 70], 0.4), 0.92), boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>
          <div style={{ color: rgb(th.text), fontSize: 54, fontWeight: 800, whiteSpace: "nowrap" }}>{p.name}</div>
          {p.role && <div style={{ color: rgb(th.accent), fontSize: 30, fontWeight: 600, marginTop: 4, opacity: k2, letterSpacing: 2, whiteSpace: "nowrap" }}>{p.role}</div>}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Small text pill (step label, source note, "SPED UP"). {text, x, y, anchor: center|left|right, size, color, icon, border} */
/** {text, x, y, anchor, size, color, icon, border, fade, bg ("white" = white pill with dark text, the Shorts hook), max_w (shrinks to fit)} */
export const Pill: React.FC<Base & { text: string; x?: number; y?: number; anchor?: string; size?: number; color?: string; icon?: string; border?: string; fade?: boolean; bg?: string | RGB; max_w?: number }> = (p) => {
  const { t, fps, W, H, D } = useT(); const th = useTheme(p); const F = fonts(p);
  const k = p.fade === false ? 1 : life(t, D, 0, 0.25, 0.25);
  const maxW = p.max_w ?? W * 0.92, est = (p.text.length * 0.56 + 1.6) * (p.size ?? 34);   // rough width of the pill at that size
  const size = (p.size ?? 34) * Math.min(1, maxW / est); const x = p.x ?? W / 2, y = p.y ?? H * 0.92;
  const white = p.bg === "white", bgc: RGB = white ? [255, 255, 255] : p.bg ? colorOf(p.bg as any, th) : [10, 16, 30];
  const tr = p.anchor === "left" ? "translate(0,-50%)" : p.anchor === "right" ? "translate(-100%,-50%)" : "translate(-50%,-50%)";
  return (
    <AbsoluteFill style={{ fontFamily: F.body }}>
      <div style={{ position: "absolute", left: x, top: y, transform: `${tr} scale(${0.9 + 0.1 * k})`, opacity: k, display: "flex", alignItems: "center", gap: size * 0.4,
        padding: `${size * 0.35}px ${size * 0.8}px`, borderRadius: white ? size * 0.55 : size, background: rgb(bgc, white ? 1 : 0.88), whiteSpace: "nowrap",
        border: p.border ? `3px solid ${rgb(colorOf(p.border, th))}` : white ? "none" : `2px solid ${rgb([255, 255, 255], 0.12)}`,
        color: rgb(p.color ? colorOf(p.color, th) : white ? [12, 14, 24] : th.text), fontSize: size, fontWeight: white ? 800 : 700,
        boxShadow: white ? "0 8px 30px rgba(0,0,0,0.35)" : undefined }}>
        <Icon src={p.icon} size={size * 1.2} />{p.text}</div>
    </AbsoluteFill>
  );
};

/** Feature chips popping in on cues. {items:[{text, at}], y, title} */
export const Chips: React.FC<Base & { items: { text: string; at: number; icon?: string }[]; y?: number; title?: string }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const out = outFade(p, t, D, 0.25);
  return (
    <AbsoluteFill style={{ fontFamily: F.body, opacity: out }}>
      <div style={{ position: "absolute", left: 80, right: 80, top: p.y ?? (tall ? H * 0.12 : 80), display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 18 }}>
        {p.items.map((it, i) => { const k = sp(t, it.at, fps, { damping: 10, stiffness: 280 }); if (t < it.at) return null;
          return <div key={i} style={{ transform: `scale(${k})`, display: "flex", alignItems: "center", gap: 12, padding: "14px 30px", borderRadius: 40,
            background: rgb(mix(th.bg, th.accent, 0.18), 0.94), border: `3px solid ${rgb(th.accent)}`, color: rgb(th.text), fontSize: tall ? 40 : 38, fontWeight: 800,
            boxShadow: `0 0 30px ${rgb(th.accent, 0.35)}` }}><Icon src={it.icon} size={40} />{it.text}</div>; })}
      </div>
    </AbsoluteFill>
  );
};

/** List that builds item by item with ticks/crosses. {title, items:[{text, at, mark: check|cross|dot, icon}], x, side,
 * enter/exit: false = no fade in/out (a board that carries on across cuts)} */
export const ListReveal: React.FC<Base & { title?: string; items: { text: string; at: number; mark?: string; icon?: string }[]; side?: string; transparent?: boolean; backdrop?: boolean; enter?: boolean; exit?: boolean }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const out = p.exit === false ? 1 : outFade(p, t, D, 0.25);
  const pw = tall ? W - 100 : Math.min(1000, W - 80), ph = tall ? 160 + p.items.length * 150 : 140 + p.items.length * 110;
  const x = tall ? 50 : W < pw + 240 ? (W - pw) / 2 : p.side === "left" ? 120 : W - pw - 120, y = tall ? H * 0.08 : (H - ph) / 2;   // narrow box: centred
  return (
    <AbsoluteFill style={{ fontFamily: F.body, opacity: out }}>
      {p.backdrop && <Backdrop th={th} t={t} W={W} H={H} />}
      <div style={{ opacity: p.enter === false ? 1 : sp(t, 0, fps, { damping: 18 }) }}>
        <Panel x={x} y={y} w={pw} h={ph} th={th}>
          {p.title && <div style={{ position: "absolute", top: 34, left: 50, color: rgb(th.accent), fontSize: 40, fontWeight: 900, letterSpacing: 4 }}>{p.title}</div>}
          {p.items.map((it, i) => { const k = sp(t, it.at, fps, { damping: 16 }); const c = it.mark === "cross" ? PALETTE.red : it.mark === "check" ? PALETTE.green : th.accent;
            return <div key={i} style={{ position: "absolute", left: 50, right: 40, top: (p.title ? 120 : 50) + i * (tall ? 150 : 110), height: tall ? 120 : 90, display: "flex", alignItems: "center",
              gap: 26, opacity: k, transform: `translateX(${(1 - k) * 60}px)` }}>
              <div style={{ width: 56, height: 56, borderRadius: 28, background: rgb(c, 0.2), border: `3px solid ${rgb(c)}`, display: "flex", alignItems: "center", justifyContent: "center",
                color: rgb(c), fontSize: 34, fontWeight: 900, transform: `scale(${sp(t, it.at + 0.12, fps, { damping: 8, stiffness: 300 })})` }}>
                {it.mark === "cross" ? "✕" : it.mark === "check" ? "✓" : String(i + 1)}</div>
              <Icon src={it.icon} size={56} />
              <div style={{ color: rgb(th.text), fontSize: tall ? 50 : 44, fontWeight: 700 }}>{it.text}</div></div>; })}
        </Panel>
      </div>
    </AbsoluteFill>
  );
};

/** Side panel of claims/stats that stack up on cues. {title, items:[{at, big, label, tag}], side: right|left, note} */
export const StatPanel: React.FC<Base & { title?: string; items: { at: number; big: string; label?: string; tag?: string }[]; side?: string; note?: string }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const out = outFade(p, t, D, 0.25);
  const pw = tall ? W - 100 : 640, x = tall ? 50 : p.side === "left" ? 80 : W - pw - 70, y0 = tall ? 120 : 100;
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: out }}>
      {p.title && <div style={{ position: "absolute", left: x, width: pw, top: y0, color: rgb(th.accent), fontSize: 30, fontWeight: 900, letterSpacing: 6, opacity: ease(t, 0, 0.3) }}>{p.title}</div>}
      {p.items.map((it, i) => { if (t < it.at) return null; const k = sp(t, it.at, fps, { damping: 15 }); const y = y0 + 60 + i * (tall ? 220 : 200);
        return <div key={i} style={{ position: "absolute", left: x, top: y, width: pw, opacity: k, transform: `translateX(${(1 - k) * (p.side === "left" ? -120 : 120)}px)` }}>
          <Panel x={0} y={0} w={pw} h={tall ? 190 : 175} th={th} r={24}>
            <div style={{ position: "absolute", left: 34, top: 20, color: rgb(th.text), fontSize: 76, fontWeight: 900 }}>{it.big}
              {it.tag && <span style={{ marginLeft: 18, fontSize: 30, padding: "4px 14px", borderRadius: 12, background: rgb(th.accent), color: rgb(PALETTE.ink), verticalAlign: "middle" }}>{it.tag}</span>}</div>
            {it.label && <div style={{ position: "absolute", left: 36, top: 112, color: rgb(PALETTE.dim), fontSize: 32, fontWeight: 600 }}>{it.label}</div>}
          </Panel></div>; })}
      {p.note && <div style={{ position: "absolute", left: x, width: pw, bottom: 50, color: rgb(PALETTE.dim), fontSize: 22, opacity: 0.8 }}>{p.note}</div>}
    </AbsoluteFill>
  );
};

/** A chat thread that plays out: bubbles slide in on cues (AI replies get typing dots first); optionally the chat is
 * wiped ("NEW CHAT") and a stamp lands. {title, messages:[{who: "you"|"ai", text, at}], clear_at, clear_label, stamp:{text, at, color}} */
export const ChatThread: React.FC<Base & { title?: string; messages: { who: string; text: string; at: number }[]; clear_at?: number; clear_label?: string;
  stamp?: { text: string; at: number; color?: string }; transparent?: boolean }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const pw = Math.min(W - 120, tall ? W - 80 : 1300), ph = Math.min(H - 160, tall ? H * 0.7 : 900), x = (W - pw) / 2, y = (H - ph) / 2;
  const cleared = p.clear_at !== undefined && t >= p.clear_at; const ck = p.clear_at !== undefined ? ease(t, p.clear_at, p.clear_at + 0.35) : 0;
  const k0 = sp(t, 0, fps, { damping: 18 });
  const shown = p.messages.filter((m) => t >= m.at - (m.who === "ai" ? 0.7 : 0));
  return (
    <AbsoluteFill style={{ fontFamily: F.body, opacity: outFade(p, t, D) }}>
      {!p.transparent && <AbsoluteFill style={{ background: rgb(th.bg) }} />}
      <div style={{ opacity: k0, transform: `translateY(${(1 - k0) * 60}px)` }}>
        <Panel x={x} y={y} w={pw} h={ph} th={th} r={30}>
          <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 90, display: "flex", alignItems: "center", gap: 14, padding: "0 34px",
            borderBottom: "2px solid rgba(255,255,255,0.08)", color: rgb(th.text), fontSize: 34, fontWeight: 800 }}>
            {["#ff5f57", "#febc2e", "#28c840"].map((c) => <div key={c} style={{ width: 18, height: 18, borderRadius: 9, background: c }} />)}
            <span style={{ marginLeft: 16 }}>{cleared ? (p.clear_label || "New chat") : (p.title || "Chat")}</span></div>
          <div style={{ position: "absolute", left: 36, right: 36, top: 120, bottom: 30, display: "flex", flexDirection: "column", gap: 22,
            opacity: 1 - ck, transform: `translateY(${-ck * 40}px)`, filter: `blur(${ck * 10}px)` }}>
            {shown.map((m, i) => {
              const ai = m.who === "ai"; const typing = ai && t < m.at; const k = sp(t, m.at - (ai ? 0.7 : 0), fps, { damping: 16 });
              return <div key={i} style={{ alignSelf: ai ? "flex-start" : "flex-end", maxWidth: "78%", padding: "20px 28px", borderRadius: 28,
                borderBottomRightRadius: ai ? 28 : 8, borderBottomLeftRadius: ai ? 8 : 28, fontSize: tall ? 40 : 36, lineHeight: 1.3, fontWeight: 600,
                background: ai ? "rgba(255,255,255,0.08)" : rgb(th.accent), color: ai ? rgb(th.text) : rgb(PALETTE.ink),
                transform: `translateX(${(1 - k) * (ai ? -80 : 80)}px) scale(${0.9 + 0.1 * k})`, opacity: Math.min(1, k * 1.5) }}>
                {typing ? <span style={{ letterSpacing: 8 }}>{[0, 1, 2].map((d) => <span key={d} style={{ opacity: 0.35 + 0.65 * Math.abs(Math.sin((t * 6) + d)) }}>●</span>)}</span> : m.text}</div>;
            })}
          </div>
          {cleared && <div style={{ position: "absolute", left: 0, right: 0, top: ph * 0.42, textAlign: "center", color: rgb(PALETTE.dim), fontSize: 40, fontWeight: 700,
            opacity: ease(t, p.clear_at! + 0.3, p.clear_at! + 0.7) }}>Hi! How can I help you today?</div>}
        </Panel>
      </div>
      {p.stamp && <Stamp text={p.stamp.text} color={colorOf(p.stamp.color || "red", th)} t={t} at={p.stamp.at} fps={fps} x={W / 2} y={y + ph * 0.72} size={tall ? 70 : 64} font={F.display} />}
    </AbsoluteFill>
  );
};
