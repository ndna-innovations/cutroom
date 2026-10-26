// Data + story graphics: BarChart, LineChart, Donut, QuoteCard, CodeBlock, NewsCard, Frame (browser/phone), TopList, SubscribeHit.
import React from "react";
import { AbsoluteFill, Easing, Img, interpolate } from "remotion";
import { evolvePath } from "@remotion/paths";
import { Backdrop, Base, Glow, Icon, PALETTE, Panel, RGB, Shockwave, Sparks, colorOf, count, ease, fmt, fonts, mix, outFade, rgb, sp, useT, useTheme } from "./lib";

type Bar = { label: string; value: number; color?: string; icon?: string; note?: string };

/** Animated bar chart (horizontal by default). {title, unit, bars:[{label, value, color, icon}], at, stagger, max, vertical, decimals, highlight} */
export const BarChart: React.FC<Base & { title?: string; unit?: string; bars: Bar[]; at?: number; stagger?: number; max?: number; vertical?: boolean; decimals?: number; highlight?: number; transparent?: boolean }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const at = p.at ?? 0.3, st = p.stagger ?? 0.18; const mx = p.max ?? Math.max(...p.bars.map((b) => b.value)) * 1.1;
  const n = p.bars.length; const vert = p.vertical ?? false;
  const x0 = tall ? 70 : 220, x1 = W - (tall ? 70 : 220), y0 = tall ? 330 : 210, y1 = H - (tall ? 260 : 140);
  const labW = vert ? 0 : (tall ? 300 : 420);
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade(p, t, D) }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      {p.title && <div style={{ position: "absolute", top: y0 - (tall ? 170 : 140), left: 0, right: 0, textAlign: "center", color: rgb(th.text), fontSize: tall ? 64 : 58, fontWeight: 900, opacity: ease(t, 0, 0.3) }}>{p.title}</div>}
      {p.bars.map((b, i) => {
        const k = ease(t, at + i * st, at + i * st + 0.9, Easing.out(Easing.cubic));
        const c = colorOf(b.color || (p.highlight === i ? "accent" : "blue"), th);
        const hi = p.highlight === undefined || p.highlight === i;
        if (!vert) {
          const bh = Math.min(110, (y1 - y0) / n - 26), y = y0 + i * ((y1 - y0) / n);
          const len = (x1 - x0 - labW - 220) * (b.value / mx) * k;
          return <div key={i} style={{ opacity: Math.min(1, k * 3) * (hi ? 1 : 0.55) }}>
            <div style={{ position: "absolute", left: x0, top: y, width: labW - 30, height: bh, display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 14,
              color: rgb(th.text), fontSize: Math.min(44, bh * 0.42), fontWeight: 700, textAlign: "right" }}><Icon src={b.icon} size={bh * 0.6} />{b.label}</div>
            <div style={{ position: "absolute", left: x0 + labW, top: y, width: Math.max(bh * 0.3, len), height: bh, borderRadius: bh / 2,
              background: `linear-gradient(90deg, ${rgb(mix(c, [0, 0, 0], 0.35))}, ${rgb(c)})`, boxShadow: `0 0 ${hi ? 34 : 0}px ${rgb(c, 0.55)}` }} />
            <div style={{ position: "absolute", left: x0 + labW + Math.max(bh * 0.3, len) + 22, top: y, height: bh, display: "flex", alignItems: "center", color: rgb(th.text),
              fontSize: Math.min(56, bh * 0.55), fontWeight: 900 }}>{fmt(b.value * k, p.decimals || 0)}<span style={{ fontSize: Math.min(30, bh * 0.3), color: rgb(PALETTE.dim), marginLeft: 8 }}>{p.unit || ""}</span></div>
          </div>;
        }
        const bw = Math.min(220, (x1 - x0) / n - 40), x = x0 + i * ((x1 - x0) / n) + ((x1 - x0) / n - bw) / 2;
        const hgt = (y1 - y0 - 160) * (b.value / mx) * k;
        return <div key={i} style={{ opacity: Math.min(1, k * 3) * (hi ? 1 : 0.55) }}>
          <div style={{ position: "absolute", left: x, top: y1 - 80 - hgt, width: bw, height: hgt, borderRadius: 18, background: `linear-gradient(0deg, ${rgb(mix(c, [0, 0, 0], 0.35))}, ${rgb(c)})`,
            boxShadow: `0 0 ${hi ? 34 : 0}px ${rgb(c, 0.55)}` }} />
          <div style={{ position: "absolute", left: x - 40, width: bw + 80, top: y1 - 80 - hgt - 76, textAlign: "center", color: rgb(th.text), fontSize: 54, fontWeight: 900 }}>{fmt(b.value * k, p.decimals || 0)}{p.unit || ""}</div>
          <div style={{ position: "absolute", left: x - 40, width: bw + 80, top: y1 - 60, textAlign: "center", color: rgb(PALETTE.dim), fontSize: 34, fontWeight: 700 }}>{b.label}</div>
        </div>;
      })}
    </AbsoluteFill>
  );
};

/** Line chart that draws itself; optional second series and point callouts. {title, x:[labels], series:[{name, values, color}], at, dur, unit, callouts:[{i, text}]} */
export const LineChart: React.FC<Base & { title?: string; x: string[]; series: { name: string; values: number[]; color?: string }[]; at?: number; dur?: number; unit?: string; callouts?: { i: number; s?: number; text: string }[]; min?: number; max?: number; transparent?: boolean }> = (p) => {
  const { t, W, H, D, tall, fps } = useT(); const th = useTheme(p); const F = fonts(p);
  const at = p.at ?? 0.3, dur = p.dur ?? 1.6;
  const all = p.series.flatMap((s) => s.values); const lo = p.min ?? Math.min(0, ...all), hi = p.max ?? Math.max(...all) * 1.1;
  const x0 = tall ? 110 : 220, x1 = W - (tall ? 60 : 160), y0 = tall ? 420 : 230, y1 = H - (tall ? 420 : 170);
  const px = (i: number) => x0 + (x1 - x0) * (i / Math.max(1, p.x.length - 1)); const py = (v: number) => y1 - (y1 - y0) * ((v - lo) / (hi - lo));
  const k = ease(t, at, at + dur, Easing.inOut(Easing.cubic));
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade(p, t, D) }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} variant="dots" />}
      {p.title && <div style={{ position: "absolute", top: y0 - (tall ? 200 : 150), left: 0, right: 0, textAlign: "center", color: rgb(th.text), fontSize: 58, fontWeight: 900 }}>{p.title}</div>}
      <svg width={W} height={H} style={{ position: "absolute" }}>
        {[0, 0.25, 0.5, 0.75, 1].map((g, i) => <line key={i} x1={x0} x2={x1} y1={y0 + (y1 - y0) * g} y2={y0 + (y1 - y0) * g} stroke="rgba(255,255,255,0.08)" strokeWidth={2} />)}
        {p.series.map((s, si) => {
          const c = colorOf(s.color || (si ? "claude" : "accent"), th);
          const d = s.values.map((v, i) => `${i ? "L" : "M"} ${px(i).toFixed(1)} ${py(v).toFixed(1)}`).join(" ");
          const ev = evolvePath(k, d);
          const area = d + ` L ${px(s.values.length - 1)} ${y1} L ${x0} ${y1} Z`;
          return <g key={si}>
            <path d={area} fill={rgb(c, 0.12 * k)} />
            <path d={d} fill="none" stroke={rgb(c)} strokeWidth={8} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={ev.strokeDasharray} strokeDashoffset={ev.strokeDashoffset}
              style={{ filter: `drop-shadow(0 0 10px ${rgb(c, 0.7)})` }} />
            {s.values.map((v, i) => (i / Math.max(1, s.values.length - 1)) <= k + 1e-6 && <circle key={i} cx={px(i)} cy={py(v)} r={10} fill={rgb(th.bg)} stroke={rgb(c)} strokeWidth={5} />)}
          </g>;
        })}
      </svg>
      {p.x.map((l, i) => <div key={i} style={{ position: "absolute", left: px(i) - 80, width: 160, top: y1 + 20, textAlign: "center", color: rgb(PALETTE.dim), fontSize: 28, fontWeight: 600 }}>{l}</div>)}
      {p.series.length > 1 && <div style={{ position: "absolute", top: y0 - 70, left: x0, display: "flex", gap: 40 }}>{p.series.map((s, si) => <div key={si} style={{ display: "flex", alignItems: "center", gap: 12, color: rgb(th.text), fontSize: 32, fontWeight: 700 }}>
        <div style={{ width: 30, height: 8, borderRadius: 4, background: rgb(colorOf(s.color || (si ? "claude" : "accent"), th)) }} />{s.name}</div>)}</div>}
      {(p.callouts || []).map((c, ci) => { const s = p.series[c.s || 0]; const v = s.values[c.i]; const show = (c.i / Math.max(1, s.values.length - 1)) <= k;
        const kk = show ? sp(t, at + dur * (c.i / Math.max(1, s.values.length - 1)), fps, { damping: 12 }) : 0;
        return <div key={ci} style={{ position: "absolute", left: px(c.i), top: py(v) - 40, transform: `translate(-50%,-100%) scale(${kk})`, padding: "12px 24px", borderRadius: 24,
          background: rgb(th.accent), color: rgb(PALETTE.ink), fontSize: 32, fontWeight: 900, whiteSpace: "nowrap" }}>{c.text}</div>; })}
    </AbsoluteFill>
  );
};

/** Donut / share chart. {title, value (0-100), label, color, at} */
export const Donut: React.FC<Base & { title?: string; value: number; label?: string; color?: string; at?: number; transparent?: boolean }> = (p) => {
  const { t, W, H, D } = useT(); const th = useTheme(p); const F = fonts(p); const c = colorOf(p.color, th);
  const at = p.at ?? 0.2; const k = ease(t, at, at + 1.2, Easing.out(Easing.cubic)); const r = Math.min(W, H) * 0.26; const cx = W / 2, cy = H / 2 + 30;
  const circ = 2 * Math.PI * r;
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade(p, t, D) }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      {p.title && <div style={{ position: "absolute", top: cy - r - 170, left: 0, right: 0, textAlign: "center", color: rgb(th.text), fontSize: 56, fontWeight: 900 }}>{p.title}</div>}
      <svg width={W} height={H} style={{ position: "absolute" }}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={r * 0.22} />
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={rgb(c)} strokeWidth={r * 0.22} strokeLinecap="round" strokeDasharray={`${circ * p.value / 100 * k} ${circ}`}
          transform={`rotate(-90 ${cx} ${cy})`} style={{ filter: `drop-shadow(0 0 20px ${rgb(c, 0.7)})` }} />
      </svg>
      <div style={{ position: "absolute", left: 0, right: 0, top: cy - 90, textAlign: "center", color: rgb(th.text), fontSize: 160, fontWeight: 900 }}>{Math.round(p.value * k)}<span style={{ fontSize: 70, color: rgb(c) }}>%</span></div>
      {p.label && <div style={{ position: "absolute", left: 0, right: 0, top: cy + r + 60, textAlign: "center", color: rgb(PALETTE.dim), fontSize: 42, fontWeight: 700 }}>{p.label}</div>}
    </AbsoluteFill>
  );
};

/** Quote card (a line someone said, a review, a claim). {quote, who, role, icon, accent_words:[...]} */
export const QuoteCard: React.FC<Base & { quote: string; who?: string; role?: string; icon?: string; accent_words?: string[]; transparent?: boolean }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const words = p.quote.split(" "); const acc = new Set((p.accent_words || []).map((w) => w.toLowerCase()));
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade(p, t, D) }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      <div style={{ position: "absolute", left: tall ? 70 : 240, right: tall ? 70 : 240, top: tall ? H * 0.22 : H * 0.2 }}>
        <div style={{ color: rgb(th.accent), fontSize: 220, lineHeight: 0.6, fontWeight: 900, opacity: ease(t, 0, 0.3), transform: `scale(${sp(t, 0, fps, { damping: 10 })})`, transformOrigin: "left" }}>“</div>
        <div style={{ color: rgb(th.text), fontSize: tall ? 72 : 76, fontWeight: 800, lineHeight: 1.18, marginTop: 20 }}>
          {words.map((w, i) => { const a = 0.2 + i * 0.045; const k = ease(t, a, a + 0.3);
            return <span key={i} style={{ opacity: k, display: "inline-block", transform: `translateY(${(1 - k) * 20}px)`, marginRight: "0.28em",
              color: acc.has(w.toLowerCase().replace(/[^a-z0-9%#']/g, "")) ? rgb(th.accent) : rgb(th.text) }}>{w}</span>; })}</div>
        {p.who && <div style={{ display: "flex", alignItems: "center", gap: 22, marginTop: 50, opacity: ease(t, 0.3 + words.length * 0.045, 0.6 + words.length * 0.045) }}>
          <Icon src={p.icon} size={80} /><div><div style={{ color: rgb(th.text), fontSize: 42, fontWeight: 800 }}>{p.who}</div>
          {p.role && <div style={{ color: rgb(PALETTE.dim), fontSize: 30, fontWeight: 600 }}>{p.role}</div>}</div></div>}
      </div>
    </AbsoluteFill>
  );
};

/** Code / prompt block typing itself out. {title, code, lang, at, cps (chars per second), highlight_lines:[n]} */
export const CodeBlock: React.FC<Base & { title?: string; code: string; at?: number; cps?: number; highlight_lines?: number[]; transparent?: boolean; size?: number }> = (p) => {
  const { t, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const at = p.at ?? 0.2, cps = p.cps ?? 60; const shown = Math.max(0, Math.floor((t - at) * cps));
  const text = p.code.slice(0, shown); const lines = text.split("\n"); const all = p.code.split("\n");
  const pw = tall ? W - 80 : Math.min(1500, W - 60), ph = Math.min(H - 200, 140 + all.length * (p.size ?? 40) * 1.5), x = (W - pw) / 2, y = (H - ph) / 2;
  return (
    <AbsoluteFill style={{ opacity: outFade(p, t, D) }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      <Panel x={x} y={y} w={pw} h={ph} th={th} r={24}>
        <div style={{ position: "absolute", top: 24, left: 30, display: "flex", gap: 12 }}>{["#ff5f57", "#febc2e", "#28c840"].map((c) => <div key={c} style={{ width: 20, height: 20, borderRadius: 10, background: c }} />)}</div>
        {p.title && <div style={{ position: "absolute", top: 18, left: 0, right: 0, textAlign: "center", color: rgb(PALETTE.dim), fontFamily: F.body, fontSize: 28, fontWeight: 700 }}>{p.title}</div>}
        <div style={{ position: "absolute", top: 84, left: 40, right: 40, fontFamily: F.mono, fontSize: p.size ?? 40, lineHeight: 1.5, color: rgb([220, 225, 245]), whiteSpace: "pre-wrap" }}>
          {lines.map((l, i) => <div key={i} style={{ background: (p.highlight_lines || []).includes(i + 1) ? rgb(th.accent, 0.16) : "transparent", borderRadius: 8 }}>{l}{i === lines.length - 1 && shown < p.code.length ? <span style={{ background: rgb(th.accent), color: "transparent" }}>_</span> : null}</div>)}
        </div>
      </Panel>
    </AbsoluteFill>
  );
};

/** News card for daily stories ("AI in 30 seconds"). {kicker, headline, body, source, logo, date, image} */
export const NewsCard: React.FC<Base & { kicker?: string; headline: string; body?: string; source?: string; logo?: string; date?: string; image?: string; transparent?: boolean }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const a = sp(t, 0, fps, { damping: 16 }), b = ease(t, 0.25, 0.6), c = ease(t, 0.5, 0.9);
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade(p, t, D) }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} variant="dots" />}
      {p.image && <Img src={p.image} style={{ position: "absolute", left: tall ? 60 : W * 0.55, top: tall ? 260 : 140, width: tall ? W - 120 : W * 0.4, height: tall ? H * 0.32 : H - 280, objectFit: "cover",
        borderRadius: 30, opacity: c, transform: `scale(${0.95 + 0.05 * c})`, boxShadow: "0 30px 80px rgba(0,0,0,0.6)" }} />}
      <div style={{ position: "absolute", left: tall ? 60 : 140, right: tall ? 60 : W * 0.5, top: tall ? (p.image ? H * 0.47 : H * 0.25) : H * 0.22 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18, opacity: a }}>
          <Icon src={p.logo} size={64} />
          {p.kicker && <span style={{ padding: "8px 20px", borderRadius: 24, background: rgb(th.accent), color: rgb(PALETTE.ink), fontSize: 30, fontWeight: 900, letterSpacing: 3 }}>{p.kicker}</span>}
          {p.date && <span style={{ color: rgb(PALETTE.dim), fontSize: 30, fontWeight: 600 }}>{p.date}</span>}
        </div>
        <div style={{ color: rgb(th.text), fontSize: tall ? 84 : 80, fontWeight: 900, lineHeight: 1.05, marginTop: 30, opacity: a, transform: `translateY(${(1 - a) * 40}px)` }}>{p.headline}</div>
        {p.body && <div style={{ color: rgb([210, 215, 235]), fontSize: tall ? 44 : 40, fontWeight: 500, lineHeight: 1.3, marginTop: 30, opacity: b }}>{p.body}</div>}
        {p.source && <div style={{ color: rgb(PALETTE.dim), fontSize: 28, fontWeight: 600, marginTop: 30, opacity: c }}>Source: {p.source}</div>}
      </div>
    </AbsoluteFill>
  );
};

/** A screenshot / image inside a browser window or phone frame, gently scrolling. {image, kind: browser|phone, url, scroll (0-1), at} */
export const Frame: React.FC<Base & { image: string; kind?: string; url?: string; scroll?: number; at?: number; transparent?: boolean; title?: string }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const k = sp(t, p.at ?? 0, fps, { damping: 16 }); const sc = ease(t, 0.8, Math.max(1.5, D - 0.5), Easing.inOut(Easing.cubic)) * (p.scroll ?? 0);
  const phone = (p.kind || "browser") === "phone";
  const fw = phone ? Math.min(W * 0.42, H * 0.42) * (tall ? 1.9 : 1) : (tall ? W - 80 : W * 0.78), fh = phone ? fw * 2.05 : (tall ? H * 0.5 : H * 0.78);
  const x = (W - fw) / 2, y = (H - fh) / 2 + (p.title ? 40 : 0);
  return (
    <AbsoluteFill style={{ fontFamily: F.body, opacity: outFade(p, t, D) }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      {p.title && <div style={{ position: "absolute", top: y - 110, left: 0, right: 0, textAlign: "center", color: rgb(th.text), fontSize: 52, fontWeight: 900, fontFamily: F.display }}>{p.title}</div>}
      <div style={{ position: "absolute", left: x, top: y, width: fw, height: fh, borderRadius: phone ? fw * 0.13 : 22, overflow: "hidden", background: "#111",
        border: phone ? `${fw * 0.03}px solid #1c1c22` : "2px solid rgba(255,255,255,0.12)", boxShadow: "0 40px 120px rgba(0,0,0,0.65)",
        transform: `translateY(${(1 - k) * 120}px) scale(${0.92 + 0.08 * k})`, opacity: Math.min(1, k * 1.5) }}>
        {!phone && <div style={{ height: 64, background: "#1e1f26", display: "flex", alignItems: "center", gap: 12, padding: "0 22px" }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => <div key={c} style={{ width: 18, height: 18, borderRadius: 9, background: c }} />)}
          <div style={{ marginLeft: 20, flex: 1, height: 38, borderRadius: 19, background: "#2a2c35", color: "#aab", fontSize: 24, display: "flex", alignItems: "center", padding: "0 20px" }}>{p.url || ""}</div></div>}
        <div style={{ position: "absolute", top: phone ? 0 : 64, left: 0, right: 0, bottom: 0, overflow: "hidden" }}>
          <Img src={p.image} style={{ width: "100%", transform: `translateY(${-sc * 100}%)` }} /></div>
      </div>
    </AbsoluteFill>
  );
};

/** Numbered top-N list counting down / up, one item per cue. {title, items:[{text, sub, icon, at}], order: down|up} */
export const TopList: React.FC<Base & { title?: string; items: { text: string; sub?: string; icon?: string; at: number }[]; order?: string; transparent?: boolean }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const n = p.items.length; const narrow = !tall && W < 1400;   // drawn inside a box (layer "rect")
  const top0 = tall ? 380 : narrow ? 110 : 190, gap = narrow ? 14 : 20;
  const rowH = tall ? 190 : Math.min(150, (H - top0 - 30) / n - gap); const fs = narrow ? 0.42 : 0.3;
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade(p, t, D) }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      {p.title && <div style={{ position: "absolute", top: tall ? 200 : narrow ? 20 : 70, left: 0, right: 0, textAlign: "center", color: rgb(th.text), fontSize: tall ? 72 : narrow ? 56 : 62, fontWeight: 900 }}>{p.title}</div>}
      {p.items.map((it, i) => { const k = sp(t, it.at, fps, { damping: 14 }); if (t < it.at) return null; const num = p.order === "down" ? n - i : i + 1;
        const y = top0 + i * (rowH + gap);
        return <div key={i} style={{ position: "absolute", left: tall ? 50 : narrow ? 40 : 300, right: tall ? 50 : narrow ? 40 : 300, top: y, height: rowH, opacity: k, transform: `translateX(${(1 - k) * 120}px)`,
          display: "flex", alignItems: "center", gap: 30, padding: "0 36px", borderRadius: 26, background: rgb([24, 28, 52], 0.9), border: `2px solid ${rgb(th.accent, 0.35)}` }}>
          <div style={{ color: rgb(th.accent), fontSize: rowH * 0.6, fontWeight: 900, width: rowH * 0.8, textAlign: "center", textShadow: `0 0 30px ${rgb(th.accent, 0.6)}` }}>{num}</div>
          <Icon src={it.icon} size={rowH * 0.5} />
          <div><div style={{ color: rgb(th.text), fontSize: rowH * fs, fontWeight: 800 }}>{it.text}</div>
            {it.sub && <div style={{ color: rgb(PALETTE.dim), fontSize: rowH * fs * 0.62, fontWeight: 600 }}>{it.sub}</div>}</div>
        </div>; })}
    </AbsoluteFill>
  );
};

/** Subscribe / follow hit (overlay): button slams in, gets "clicked", bell rings. {text, at, x, y} */
export const SubscribeHit: React.FC<Base & { text?: string; at?: number; x?: number; y?: number }> = (p) => {
  const { t, fps, W, H, D } = useT(); const th = useTheme(p); const F = fonts(p);
  const at = p.at ?? 0.1; const k = sp(t, at, fps, { damping: 11, stiffness: 240 }); const click = t > at + 0.9; const press = click ? 1 - 0.08 * (1 - ease(t, at + 0.9, at + 1.15)) : 1;
  const x = p.x ?? W / 2, y = p.y ?? H * 0.82;
  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade({ _alpha: true }, t, D) }}>
      <div style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,-50%) scale(${k * press})`, display: "flex", alignItems: "center", gap: 18,
        padding: "22px 46px", borderRadius: 50, background: click ? "#2b2b33" : "#ff0033", color: "white", fontSize: 48, fontWeight: 800, boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>
        {click ? "✓ " : ""}{click ? "Subscribed" : (p.text || "Subscribe")}</div>
      <Sparks x={x} y={y} t={t} at={at + 0.95} color={th.accent} n={20} reach={260} />
    </AbsoluteFill>
  );
};
