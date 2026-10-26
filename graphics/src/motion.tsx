// Motion design: TextFX (After Effects style text animators) and FlowDiagram (a diagram that draws itself on cue).
// Everything lays out from W/H, so both work full-frame, tall or inside a box.
import React from "react";
import { AbsoluteFill, Easing, Img, interpolate } from "remotion";
import { Base, Glow, RGB, colorOf, ease, fonts, mix, rgb, sp, useT, useTheme, outFade } from "./lib";

const clean = (s: string) => s.toLowerCase().replace(/[^a-z0-9%#']/g, "");
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

// ------------------------------------------------------------------ TextFX
type FXLine = { text: string; at?: number; color?: string; size?: number; weight?: number; out?: number };

/** Text animators. Each unit (char or word) animates on its own time: at + index * stagger.
 * cascade: rises with a 3D flip and overshoot · typewriter: types with a caret · blur: sharpens from blur + scale ·
 * slam: drops from big with a shake · wave: lands then keeps a gentle wave · weight: 300 -> 900 · split: grows out of the centre.
 * {lines:[{text, at, color, size, weight, out}], style, per: char|word, stagger, align, x, y, highlight:[words], underline_at, out} */
export const TextFX: React.FC<Base & { lines: FXLine[]; style?: string; per?: string; stagger?: number; align?: string; x?: number; y?: number;
  highlight?: string[]; underline_at?: number; out?: number }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const style = p.style || "cascade";
  const per = p.per || (["typewriter", "wave", "split", "weight"].includes(style) ? "char" : "word");
  const stagger = p.stagger ?? (per === "char" ? (style === "typewriter" ? 0.045 : 0.03) : style === "slam" ? 0.16 : 0.09);
  const align = p.align || "center";
  const hl = new Set((p.highlight || []).map(clean));
  const base = tall ? W * 0.11 : H * 0.11;
  const boxW = W * 0.88;
  const x = p.x ?? (align === "left" ? 0.06 : align === "right" ? 0.94 : 0.5);
  const left = x * W - boxW * (align === "left" ? 0 : align === "right" ? 1 : 0.5);
  const family = style === "weight" && !p._kit?.display ? `-apple-system, 'SF Pro Display', ${F.display}` : F.display;

  // line start times: given, or right after the previous line finishes
  let next = 0.1;
  const lines = p.lines.map((l) => {
    const words = l.text.split(/\s+/).filter(Boolean);
    const n = per === "char" ? words.join("").length : words.length;
    const at = l.at ?? next; next = at + n * stagger + 0.3;
    return { ...l, words, n, at };
  });
  const active = lines.reduce((k, l, i) => (t >= l.at ? i : k), -1);

  return (
    <AbsoluteFill style={{ fontFamily: family, opacity: outFade(p, t, D) }}>
      <div style={{ position: "absolute", left, width: boxW, top: (p.y ?? 0.5) * H, transform: "translateY(-50%)", display: "flex", flexDirection: "column",
        gap: base * 0.12, textAlign: align as any }}>
        {lines.map((l, li) => {
          const size = l.size ?? base; const col = l.color ? colorOf(l.color, th) : th.text;
          const out = l.out ?? p.out; const total = l.words.join(" ").length;
          let ui = 0, ci = 0;
          // slam: the whole line shakes a little as each unit lands
          let sx = 0, sy = 0;
          if (style === "slam") for (let i = 0; i < l.n; i++) {
            const u = t - (l.at + i * stagger + 0.09);
            if (u > 0 && u < 0.5) { const a = size * (per === "char" ? 0.012 : 0.04) * Math.exp(-u * 11); sx += a * Math.sin(u * 95); sy += a * Math.cos(u * 77); }
          }
          const typing = style === "typewriter" && li === active;
          const lastTyped = Math.floor((t - l.at) / stagger);
          const caretOn = typing && (lastTyped < l.n || Math.floor(t * 2.4) % 2 === 0);
          const rule = style === "split" ? ease(t, l.at - 0.05, l.at + 0.35, Easing.out(Easing.cubic)) * (1 - ease(t, l.at + 0.7, l.at + 1.3)) : 0;
          const open = style === "split" ? ease(t, l.at + 0.1, l.at + 0.75, Easing.out(Easing.cubic)) : 1;
          return (
            <div key={li} style={{ fontSize: size, lineHeight: 1.12, fontWeight: l.weight ?? 800, color: rgb(col), transform: `translate(${sx}px, ${sy}px)` }}>
              <span style={{ position: "relative", display: "inline-block", clipPath: style === "split" ? `inset(-40% ${50 * (1 - open)}% -40% ${50 * (1 - open)}%)` : undefined }}>
                {l.words.map((w, wi) => {
                  const isHl = hl.has(clean(w));
                  const units = per === "char" ? w.split("") : [w];
                  const wStart = ci; ci += w.length + 1;
                  const firstU = ui; ui += units.length;
                  const landed = l.at + (ui - 1) * stagger + 0.25;
                  const ua = p.underline_at ?? landed;
                  const mk = isHl ? ease(t, ua, ua + 0.45, Easing.inOut(Easing.cubic)) : 0;
                  const caretHere = caretOn && Math.min(lastTyped, l.n - 1) >= firstU && Math.min(lastTyped, l.n - 1) < ui;
                  return (
                    <React.Fragment key={wi}>
                      {wi > 0 && " "}
                      <span style={{ position: "relative", display: "inline-block", whiteSpace: "nowrap", color: isHl ? rgb(th.accent) : undefined }}>
                        {isHl && <svg viewBox="0 0 100 20" preserveAspectRatio="none" style={{ position: "absolute", left: "-4%", width: "108%", bottom: -size * 0.04, height: size * 0.22, overflow: "visible" }}>
                          <path d="M2 13 Q 28 7 52 11 T 98 8" pathLength={100} fill="none" stroke={rgb(th.accent, 0.9)} strokeWidth={10} strokeLinecap="round"
                            strokeDasharray="100" strokeDashoffset={100 * (1 - mk)} opacity={mk > 0 ? 1 : 0} /></svg>}
                        {units.map((u, k) => {
                          const i = firstU + k;
                          const rel = wStart + k + (per === "char" ? 0.5 : w.length / 2) - total / 2;    // chars from the line centre
                          const ta = style === "split" ? l.at + 0.15 + Math.abs(rel) * stagger * 0.4 : l.at + i * stagger;
                          let tf = "", op = 1, blur = 0, wt: number | undefined, glow = 0;
                          if (style === "typewriter") op = t >= ta ? 1 : 0;
                          else if (style === "cascade" || style === "wave") {
                            const s = sp(t, ta, fps, { damping: 9, stiffness: 190 });
                            op = clamp01(s * 2.2);
                            tf = `perspective(${size * 6}px) translateY(${(1 - s) * size * 0.7}px) rotateX(${(1 - s) * -75}deg)`;
                            if (style === "wave") tf += ` translateY(${Math.sin(t * 4.2 - i * 0.42) * size * 0.07 * ease(t, ta + 0.35, ta + 0.9)}px)`;
                          } else if (style === "blur") {
                            const e = ease(t, ta, ta + 0.6, Easing.out(Easing.cubic));
                            op = e; blur = (1 - e) * size * 0.2; tf = `scale(${1.4 - 0.4 * e})`;
                          } else if (style === "slam") {
                            const s = sp(t, ta, fps, { damping: 16, stiffness: 420, mass: 0.7 });
                            op = clamp01(s * 4); tf = `translateY(${-(1 - s) * size * 0.35}px) scale(${s < 1 ? interpolate(s, [0, 1], [tall ? 1.9 : 2.6, 1]) : 1 - (s - 1) * 0.4})`;
                            blur = (1 - clamp01(s)) * size * 0.04; glow = t > ta ? Math.exp(-(t - ta - 0.08) * 5) : 0;
                          } else if (style === "weight") {
                            const e = ease(t, ta, ta + 0.55, Easing.inOut(Easing.cubic));
                            op = (0.15 + 0.85 * clamp01(e * 3)) * ease(t, lines[0].at - 0.3, lines[0].at); wt = 300 + ((l.weight ?? 900) - 300) * e; tf = `scale(${0.94 + 0.06 * e})`;
                          } else if (style === "split") {
                            const s = sp(t, ta, fps, { damping: 15, stiffness: 170 });
                            tf = `translateX(${-rel * size * 0.05 * (1 - s)}px) scaleX(${0.7 + 0.3 * Math.min(1, s)})`;
                          }
                          if (out !== undefined) {
                            const e = ease(t, out + i * 0.012, out + 0.3 + i * 0.012, Easing.in(Easing.cubic));
                            op *= 1 - e; blur += e * size * 0.08; tf += ` translateY(${-e * size * 0.35}px)`;
                          }
                          const c = isHl ? th.accent : col;
                          return <span key={k} style={{ position: "relative", display: "inline-block", opacity: op, transform: tf || undefined, transformOrigin: "50% 100%",
                            filter: blur > 0.3 ? `blur(${blur}px)` : undefined, fontWeight: wt,
                            textShadow: `0 ${size * 0.06}px ${size * 0.3}px rgba(0,0,0,0.6)${glow > 0.02 ? `, 0 0 ${size * 0.5}px ${rgb(mix(c, [255, 255, 255], 0.3), glow)}` : ""}` }}>
                            {u}{caretHere && i === Math.min(lastTyped, l.n - 1) && <Caret size={size} color={th.accent} />}</span>;
                        })}
                      </span>
                    </React.Fragment>
                  );
                })}
                {style === "typewriter" && caretOn && lastTyped < 0 && <Caret size={size} color={th.accent} />}
                {rule > 0 && <div style={{ position: "absolute", left: "50%", bottom: -size * 0.06, height: Math.max(3, size * 0.045), width: `${rule * 104}%`, transform: "translateX(-50%)",
                  borderRadius: size, background: rgb(th.accent), boxShadow: `0 0 ${size * 0.3}px ${rgb(th.accent, 0.6)}` }} />}
              </span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const Caret: React.FC<{ size: number; color: RGB }> = ({ size, color }) => (
  <span style={{ position: "absolute", left: "100%", marginLeft: size * 0.05, top: "12%", height: "80%", width: Math.max(3, size * 0.06), borderRadius: 2,
    background: rgb(color), boxShadow: `0 0 ${size * 0.25}px ${rgb(color, 0.8)}` }} />
);

// ------------------------------------------------------------------ FlowDiagram
type FNode = { id: string; text: string; sub?: string; icon?: string; x?: number; y?: number; color?: string; at?: number; shape?: string };
type FEdge = { from: string; to: string; at?: number; label?: string; dashed?: boolean; color?: string };
type Pt = [number, number];

const bez = (P: Pt[], s: number): Pt => {
  const u = 1 - s;
  return [0, 1].map((k) => u * u * u * P[0][k] + 3 * u * u * s * P[1][k] + 3 * u * s * s * P[2][k] + s * s * s * P[3][k]) as Pt;
};
/** sub-curve from 0 to s (de Casteljau), so a dashed edge can draw on too */
const bezTo = (P: Pt[], s: number): Pt[] => {
  const l = (a: Pt, b: Pt): Pt => [a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s];
  const a = l(P[0], P[1]), b = l(P[1], P[2]), c = l(P[2], P[3]), d = l(a, b), e = l(b, c);
  return [P[0], a, d, l(d, e)];
};
/** arc-length table: param s for a fraction of the length */
const arcParam = (P: Pt[]) => {
  const N = 48; const acc = [0]; let prev = P[0];
  for (let i = 1; i <= N; i++) { const q = bez(P, i / N); acc.push(acc[i - 1] + Math.hypot(q[0] - prev[0], q[1] - prev[1])); prev = q; }
  const L = acc[N];
  return { L, at: (f: number) => { const g = clamp01(f) * L; let i = 1; while (i < N && acc[i] < g) i++; return (i - 1 + (g - acc[i - 1]) / Math.max(1e-6, acc[i] - acc[i - 1])) / N; } };
};

const NodeIcon: React.FC<{ src: string; size: number }> = ({ src, size }) =>
  /^(https?:|file:|data:)/.test(src) ? <Img src={src} style={{ width: size, height: size, objectFit: "contain" }} />
    : <span style={{ fontSize: size * 0.86, lineHeight: 1 }}>{src}</span>;

/** A diagram that draws itself: nodes pop in on cue, edges draw as curved arrows, then a glow dot keeps travelling along
 * them; focus makes one node pulse while the rest dim. {title, nodes:[{id, text, sub, icon, x, y, color, at, shape: box|pill|circle}],
 * edges:[{from, to, at, label, dashed, color}], focus:[{id, at}], layout: free|row|column} (x/y = 0-1 of the box, node centre) */
export const FlowDiagram: React.FC<Base & { title?: string; nodes: FNode[]; edges?: FEdge[]; focus?: { id?: string | null; at: number }[]; layout?: string }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const n = p.nodes.length;
  let layout = p.layout || "free";
  const auto = p.nodes.some((nd) => nd.x === undefined || nd.y === undefined);
  if (layout === "free" && auto) layout = tall ? "column" : "row";
  if (layout === "row" && tall && auto) layout = "column";
  const x0 = W * 0.05, x1 = W * 0.95, y0 = p.title ? H * (tall ? 0.12 : 0.17) : H * 0.06, y1 = H * 0.95;
  let nw: number, nh: number;
  if (layout === "row") { const slot = (x1 - x0) / n; nw = Math.min(slot * 0.7, (x1 - x0) * 0.3); nh = Math.min(nw * 0.86, (y1 - y0) * 0.6); }
  else if (layout === "column") { const slot = (y1 - y0) / n; nh = Math.min(slot * 0.66, (y1 - y0) * 0.3); nw = Math.min(W * 0.62, nh * 2.8); }
  else { nw = tall || W / H < 1.3 ? W * 0.3 : W * 0.17; nh = Math.min(nw * 0.66, H * 0.22); }   // squarer boxes (split panels) get bigger nodes
  const size = (nd: FNode): Pt => (nd.shape === "circle" ? [Math.min(nw, nh) * 1.15, Math.min(nw, nh) * 1.15] : [nw, nh]);
  const pos: Record<string, Pt> = {};
  p.nodes.forEach((nd, i) => {
    const ax = layout === "row" ? x0 + (x1 - x0) * (i + 0.5) / n : W / 2, ay = layout === "column" ? y0 + (y1 - y0) * (i + 0.5) / n : (y0 + y1) / 2;
    pos[nd.id] = [nd.x !== undefined && !(auto && layout !== "free") ? nd.x * W : ax, nd.y !== undefined && !(auto && layout !== "free") ? nd.y * H : ay];
  });
  p.nodes.forEach((nd) => { const [w, h] = size(nd); const q = pos[nd.id];
    pos[nd.id] = [Math.max(x0 + w / 2, Math.min(x1 - w / 2, q[0])), Math.max(y0 + h / 2, Math.min(y1 - h / 2, q[1]))]; });
  const atOf: Record<string, number> = {};
  p.nodes.forEach((nd, i) => (atOf[nd.id] = nd.at ?? 0.2 + i * 0.4));

  // focus level per node: +1 focused, -1 dimmed, 0 normal (each cue blends from the previous state)
  const focus = [...(p.focus || [])].sort((a, b) => a.at - b.at);
  const lvl = (id: string) => {
    let v = 0;
    for (const f of focus) if (t >= f.at) v += ((f.id ? (f.id === id ? 1 : -1) : 0) - v) * ease(t, f.at, f.at + 0.35);
    return v;
  };
  const byId: Record<string, FNode> = {}; p.nodes.forEach((nd) => (byId[nd.id] = nd));

  const edges = (p.edges || []).filter((e) => byId[e.from] && byId[e.to]).map((e) => {
    const [ax, ay] = pos[e.from], [bx, by] = pos[e.to]; const [aw, ah] = size(byId[e.from]), [bw, bh] = size(byId[e.to]);
    const dx = bx - ax, dy = by - ay; const gap = Math.min(nw, nh) * 0.06;
    let P: Pt[];
    if (Math.abs(dx) * nh >= Math.abs(dy) * nw) {
      const sx = Math.sign(dx) || 1;
      if (Math.abs(dy) < nh * 0.5 && Math.abs(dx) > nw * 2.2) {   // same row, far apart: arc over the top
        const top = Math.min(ay - ah / 2, by - bh / 2) - nh * 0.7;
        P = [[ax, ay - ah / 2 - gap], [ax, top], [bx, top], [bx, by - bh / 2 - gap * 2.5]];
      } else {
        const a: Pt = [ax + sx * (aw / 2 + gap), ay], b: Pt = [bx - sx * (bw / 2 + gap * 2.5), by]; const m = (b[0] - a[0]) * 0.5;
        P = [a, [a[0] + m, a[1]], [b[0] - m, b[1]], b];
      }
    } else {
      const sy = Math.sign(dy) || 1;
      if (Math.abs(dx) < nw * 0.5 && Math.abs(dy) > nh * 2.2) {   // same column, far apart: arc round the side
        const side = Math.min(W * 0.975, Math.max(ax + aw / 2, bx + bw / 2) + nw * 0.25);
        P = [[ax + aw / 2 + gap, ay], [side, ay], [side, by], [bx + bw / 2 + gap * 2.5, by]];
      } else {
        const a: Pt = [ax, ay + sy * (ah / 2 + gap)], b: Pt = [bx, by - sy * (bh / 2 + gap * 2.5)]; const m = (b[1] - a[1]) * 0.5;
        P = [a, [a[0], a[1] + m], [b[0], b[1] - m], b];
      }
    }
    const at = e.at ?? Math.max(atOf[e.from], atOf[e.to]) + 0.3;
    return { ...e, P, at, arc: arcParam(P), col: e.color ? colorOf(e.color, th) : mix(th.accent, [255, 255, 255], 0.15) };
  });
  const sw = Math.max(2.5, Math.min(nw, nh) * 0.03);
  const fsz = layout === "column" ? nh * 0.2 : Math.min(nh * 0.2, nw * 0.125);
  const across = nw / nh > 1.8;

  return (
    <AbsoluteFill style={{ fontFamily: F.display, opacity: outFade(p, t, D), overflow: "hidden" }}>
      {p.title && <div style={{ position: "absolute", top: H * 0.035, left: W * 0.05, right: W * 0.05, color: rgb(th.accent), fontSize: Math.min(H * 0.07, W * 0.06), fontWeight: 900,
        letterSpacing: 4, opacity: ease(t, 0, 0.4), transform: `translateY(${(1 - ease(t, 0, 0.5)) * 20}px)`, textAlign: tall ? "center" : "left" }}>{p.title}</div>}
      <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
        {edges.map((e, i) => {
          const draw = ease(t, e.at, e.at + 0.65, Easing.inOut(Easing.cubic));
          if (draw <= 0) return null;
          const s = e.arc.at(draw); const Q = bezTo(e.P, s);
          const d = `M${Q[0][0]},${Q[0][1]} C${Q[1][0]},${Q[1][1]} ${Q[2][0]},${Q[2][1]} ${Q[3][0]},${Q[3][1]}`;
          const tip = Q[3]; const dir = Math.atan2(Q[3][1] - Q[2][1], Q[3][0] - Q[2][0]) || Math.atan2(e.P[3][1] - e.P[0][1], e.P[3][0] - e.P[0][0]);
          const ah = sw * 4.2; const dim = 1 - 0.7 * Math.max(0, -Math.max(lvl(e.from), lvl(e.to)));
          const pts = [[tip[0] + Math.cos(dir) * ah * 0.5, tip[1] + Math.sin(dir) * ah * 0.5], [tip[0] + Math.cos(dir + 2.5) * ah, tip[1] + Math.sin(dir + 2.5) * ah],
            [tip[0] + Math.cos(dir - 2.5) * ah, tip[1] + Math.sin(dir - 2.5) * ah]].map((q) => q.join(",")).join(" ");
          const travel = t - e.at - 0.65; const ph = travel > 0 ? (travel / 1.6) % 1 : -1; const dot = ph >= 0 ? bez(e.P, e.arc.at(ph)) : null;
          const dotA = ph >= 0 ? Math.sin(ph * Math.PI) * ease(t, e.at + 0.65, e.at + 0.9) : 0;
          return (
            <g key={i} opacity={dim}>
              <path d={d} fill="none" stroke={rgb(e.col, 0.18)} strokeWidth={sw * 4} strokeLinecap="round" />
              <path d={d} fill="none" stroke={rgb(e.col)} strokeWidth={sw} strokeLinecap="round" strokeDasharray={e.dashed ? `${sw * 3} ${sw * 2.6}` : undefined} />
              <polygon points={pts} fill={rgb(e.col)} />
              {dot && <><circle cx={dot[0]} cy={dot[1]} r={sw * 5} fill={rgb(e.col, 0.25 * dotA)} /><circle cx={dot[0]} cy={dot[1]} r={sw * 1.6} fill={rgb([255, 255, 255], dotA)} /></>}
            </g>
          );
        })}
      </svg>
      {edges.filter((e) => e.label).map((e, i) => {
        const k = sp(t, e.at + 0.35, fps, { damping: 14 }); if (k <= 0) return null;
        const m = bez(e.P, 0.5); const q = bez(e.P, 0.55); const flat = Math.abs(q[0] - m[0]) >= Math.abs(q[1] - m[1]); const arc = e.P[1][1] !== e.P[0][1] && flat;
        const ly = flat && !arc ? Math.min(e.P[0][1], e.P[3][1]) - nh * 0.5 - fsz * 0.25 : m[1]; const dim = 1 - 0.7 * Math.max(0, -Math.max(lvl(e.from), lvl(e.to)));
        return <div key={i} style={{ position: "absolute", left: m[0], top: ly, transform: `translate(${flat ? -50 : m[0] > W * 0.7 ? -112 : 12}%, ${flat ? (arc ? -135 : -100) : -50}%) scale(${0.6 + 0.4 * k})`, opacity: clamp01(k * 1.5) * dim,
          padding: `${fsz * 0.18}px ${fsz * 0.5}px`, borderRadius: fsz, background: rgb(mix(th.bg, [30, 34, 70], 0.5), 0.95), border: `2px solid ${rgb(e.col, 0.7)}`,
          color: rgb(th.text), fontSize: fsz * 0.62, fontWeight: 800, whiteSpace: "nowrap", boxShadow: "0 10px 30px rgba(0,0,0,0.5)" }}>{e.label}</div>;
      })}
      {p.nodes.map((nd) => {
        const k = sp(t, atOf[nd.id], fps, { damping: 12, stiffness: 220 }); if (k <= 0) return null;
        const [cx, cy] = pos[nd.id]; const [w, h] = size(nd); const c = colorOf(nd.color, th);
        const v = lvl(nd.id); const fo = Math.max(0, v), dm = Math.max(0, -v);
        const pulse = fo * (0.05 + 0.025 * Math.sin((t - atOf[nd.id]) * 6));
        const r = nd.shape === "pill" || nd.shape === "circle" ? h / 2 : h * 0.18;
        return (
          <div key={nd.id} style={{ position: "absolute", left: cx - w / 2, top: cy - h / 2, width: w, height: h, borderRadius: r, padding: 3,
            opacity: clamp01(k * 2) * (1 - 0.65 * dm), transform: `scale(${interpolate(k, [0, 1], [0.4, 1]) * (1 + pulse) * (1 - 0.06 * dm)})`,
            background: `linear-gradient(135deg, ${rgb(c, 0.95)}, ${rgb(c, 0.25)} 50%, ${rgb([255, 255, 255], 0.2)})`,
            boxShadow: `0 24px 60px rgba(0,0,0,0.55), 0 0 ${h * (0.25 + 0.6 * fo)}px ${rgb(c, 0.22 + 0.5 * fo)}` }}>
            {fo > 0.05 && <Glow color={c} size={w * 1.5} x={w / 2} y={h / 2} alpha={0.2 * fo} />}
            <div style={{ position: "relative", width: "100%", height: "100%", borderRadius: r - 3, overflow: "hidden", display: "flex", flexDirection: across ? "row" : "column",
              alignItems: "center", justifyContent: "center", gap: fsz * 0.4, padding: `0 ${fsz * 0.6}px`, boxSizing: "border-box",
              background: `linear-gradient(160deg, ${rgb(mix(th.bg, mix(c, [40, 46, 90], 0.6), 0.45))}, ${rgb(th.bg)})` }}>
              {nd.icon && <NodeIcon src={nd.icon} size={across ? h * 0.42 : h * (nd.sub ? 0.26 : 0.32)} />}
              <div style={{ textAlign: across ? "left" : "center", minWidth: 0 }}>
                <div style={{ color: rgb(th.text), fontSize: fsz, fontWeight: 900, lineHeight: 1.1 }}>{nd.text}</div>
                {nd.sub && <div style={{ color: rgb(mix(c, [255, 255, 255], 0.35)), fontSize: fsz * 0.62, fontWeight: 700, marginTop: fsz * 0.15, lineHeight: 1.15 }}>{nd.sub}</div>}
              </div>
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/** Re-type: covers pasted text on a screen recording and types it in, letter by letter, in the app's own colours.
 * Coordinates are design px of the box (the engine passes the box in source px and design = box width).
 * {lines:[{text, x, y, h}], bg:[r,g,b], fg:[r,g,b], font, weight, at, cps, fast (middle speed-up x), caret, total} */
export const TypeOn: React.FC<Base & { lines: { text: string; x: number; y: number; h: number }[]; bg: RGB; fg: RGB; font?: string; weight?: number;
  at?: number; cps?: number; fast?: number; caret?: RGB; hold?: number }> = (p) => {
  const { t, W, H } = useT();
  const total = p.lines.reduce((a, l) => a + l.text.length + 1, 0);
  const cps = p.cps ?? 28, fast = p.fast ?? 1, at = p.at ?? 0;
  // characters typed by time: normal speed for the first and last ~60 characters, `fast` x in between (long prompts)
  const edge = Math.min(60, total / 3);
  const tEdge = edge / cps, tMid = Math.max(0, total - 2 * edge) / (cps * fast);
  const u = Math.max(0, t - at);
  const n = u < tEdge ? u * cps : u < tEdge + tMid ? edge + (u - tEdge) * cps * fast : Math.min(total, total - edge + (u - tEdge - tMid) * cps);
  let left = Math.floor(n);
  const blink = Math.floor(t * 2) % 2 === 0;
  let caretAt: { x: number; y: number; h: number } | null = null;
  return (
    <AbsoluteFill style={{ background: rgb(p.bg) }}>
      {p.lines.map((l, i) => {
        const k = Math.max(0, Math.min(l.text.length, left)); left -= l.text.length + 1;
        const shown = l.text.slice(0, k);
        if (k < l.text.length && !caretAt) caretAt = { x: l.x, y: l.y, h: l.h };
        return <div key={i} style={{ position: "absolute", left: l.x, top: l.y, height: l.h, lineHeight: `${l.h}px`, whiteSpace: "pre",
          fontFamily: p.font || "-apple-system, 'SF Pro Text', 'Helvetica Neue', sans-serif", fontWeight: p.weight ?? 400, fontSize: l.h * 0.78, color: rgb(p.fg) }}>
          {shown}{k < l.text.length && k >= 0 && (n < total) && caretAt && caretAt.y === l.y ? <span style={{ display: "inline-block", width: Math.max(2, l.h * 0.08), height: l.h * 0.9,
            verticalAlign: "middle", background: rgb(p.caret || p.fg, blink ? 0.9 : 0), marginLeft: 1 }} /> : null}</div>;
      })}
    </AbsoluteFill>
  );
};
