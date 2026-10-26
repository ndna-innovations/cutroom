// Results graphics: ScoreCard, Scoreboard, WordRace, ClaimBoard, BigNumber, VerdictTable.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import { Backdrop, Base, Glow, Icon, PALETTE, Panel, RGB, Shockwave, Sparks, Stamp, Sweep, colorOf, count, ease, fmt, fonts, life, mix, rgb, sp, useT, useTheme } from "./lib";
import { BoardCard, fit, outFade } from "./lib";

type Side = { name: string; icon?: string; color?: string; score?: string | number; note?: string };

/** Head-to-head result of one test. {title, left, right, winner: left|right|tie, stamp, t_stamp} */
export const ScoreCard: React.FC<Base & { title?: string; left: Side; right: Side; winner?: "left" | "right" | "tie"; stamp?: string; t_stamp?: number; transparent?: boolean }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const out = outFade(p, t, D, 0.25);
  const ts = p.t_stamp ?? 0.9;
  const sides: [Side, number, "left" | "right"][] = [[p.left, 0.1, "left"], [p.right, 0.22, "right"]];
  const pw = tall ? W - 120 : 760, ph = tall ? 560 : 640;
  return (
    <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      {p.title && <div style={{ position: "absolute", top: tall ? 120 : 70, left: 0, right: 0, textAlign: "center", color: rgb(PALETTE.dim), fontSize: 40, fontWeight: 800,
        letterSpacing: 8, opacity: ease(t, 0, 0.3) }}>{p.title}</div>}
      {sides.map(([s, at, key], i) => {
        const k = sp(t, at, fps, { damping: 16 });
        const c = colorOf(s.color || (key === "left" ? "blue" : "claude"), th);
        const won = p.winner === key, lost = p.winner && p.winner !== "tie" && !won;
        const x = tall ? 60 : (i === 0 ? W / 2 - pw - 40 : W / 2 + 40), y = tall ? (i === 0 ? 260 : 260 + ph + 60) : (H - ph) / 2 + 10;
        const fadeLost = lost ? interpolate(ease(t, ts, ts + 0.4), [0, 1], [1, 0.55]) : 1;
        return (
          <div key={key} style={{ opacity: Math.min(1, k * 1.4) * fadeLost, transform: `translateY(${(1 - k) * 80}px) scale(${won ? 1 + 0.04 * ease(t, ts, ts + 0.3) : 1})`,
            transformOrigin: "center" }}>
            <Panel x={x} y={y} w={pw} h={ph} th={th} tint={c}>
              <div style={{ position: "absolute", top: 50, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center" }}>
                <Icon src={s.icon} size={130} />
                <div style={{ color: rgb(th.text), fontSize: 58, fontWeight: 800, marginTop: 18 }}>{s.name}</div>
                {s.score !== undefined && <div style={{ color: rgb(c), fontSize: 150, fontWeight: 900, marginTop: 6, textShadow: `0 0 40px ${rgb(c, 0.6)}` }}>{s.score}</div>}
                {s.note && <div style={{ color: rgb(PALETTE.dim), fontSize: 36, fontWeight: 500, marginTop: 4, padding: "0 40px", textAlign: "center" }}>{s.note}</div>}
              </div>
              <Sweep t={t} at={at + 0.3} />
            </Panel>
            {won && p.stamp !== "" && <Stamp text={p.stamp || "WINNER"} color={PALETTE.green} t={t} at={ts} fps={fps} x={x + pw / 2} y={y - 6} size={50} rot={-3} font={F.display} />}
          </div>
        );
      })}
      {p.winner === "tie" && <Stamp text={p.stamp || "TIE"} color={PALETTE.gold} t={t} at={ts} fps={fps} x={W / 2} y={tall ? H * 0.52 : H * 0.55} size={80} font={F.display} />}
    </AbsoluteFill>
  );
};

/** Running tally. {title, left, right, rows:[{label, winner: left|right|tie, at}], total:true} */
export const Scoreboard: React.FC<Base & { title?: string; left: Side; right: Side; rows: { label: string; winner?: string; at?: number; note?: string }[]; transparent?: boolean }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const out = outFade(p, t, D, 0.25);
  const cl = colorOf(p.left.color || "blue", th), cr = colorOf(p.right.color || "claude", th);
  const n = p.rows.length; const rowH = tall ? 120 : Math.min(110, 640 / n);
  const pw = tall ? W - 100 : Math.min(1500, W - 60), x0 = (W - pw) / 2, y0 = tall ? 330 : 230;
  let L = 0, R = 0;
  const shown = p.rows.map((r, i) => { const at = r.at ?? 0.4 + i * 0.35; const on = t >= at + 0.25;
    if (on && (r.winner === "left" || r.winner === "tie")) L++; if (on && (r.winner === "right" || r.winner === "tie")) R++; return at; });
  return (
    <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      <div style={{ position: "absolute", top: tall ? 110 : 70, left: 0, right: 0, textAlign: "center", color: rgb(th.text), fontSize: 56, fontWeight: 900, letterSpacing: 4 }}>{p.title || "SCOREBOARD"}</div>
      <div style={{ position: "absolute", left: x0, width: pw, top: y0 - 110, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        {[[p.left, cl, L], [p.right, cr, R]].map(([s, c, v]: any, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 20, flexDirection: i ? "row-reverse" : "row" }}>
            <Icon src={s.icon} size={70} /><div style={{ color: rgb(th.text), fontSize: 44, fontWeight: 800 }}>{s.name}</div>
            <div style={{ color: rgb(c), fontSize: 80, fontWeight: 900, minWidth: 70, textAlign: "center", textShadow: `0 0 30px ${rgb(c, 0.7)}` }}>{v}</div>
          </div>))}
      </div>
      {p.rows.map((r, i) => {
        const at = shown[i]; const k = sp(t, at, fps, { damping: 18 }); const y = y0 + i * (rowH + 14);
        const c = r.winner === "left" ? cl : r.winner === "right" ? cr : PALETTE.gold;
        const mark = ease(t, at + 0.25, at + 0.45);
        return (
          <div key={i} style={{ position: "absolute", left: x0, top: y, width: pw, height: rowH, borderRadius: 18, opacity: k, transform: `translateX(${(1 - k) * -60}px)`,
            background: `linear-gradient(90deg, ${rgb(r.winner === "left" ? cl : [30, 34, 60], r.winner === "left" ? 0.28 * mark : 0.5)}, ${rgb([20, 24, 44], 0.85)} 50%, ${rgb(r.winner === "right" ? cr : [30, 34, 60], r.winner === "right" ? 0.28 * mark : 0.5)})`,
            border: `2px solid ${rgb(c, 0.25 + 0.5 * mark)}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <div style={{ color: rgb(th.text), fontSize: Math.min(44, rowH * 0.42), fontWeight: 700 }}>{r.label}</div>
            {r.winner && r.winner !== "tie" && <div style={{ position: "absolute", [r.winner === "left" ? "left" : "right"]: 28, width: rowH * 0.5, height: rowH * 0.5, borderRadius: "50%",
              background: rgb(c), transform: `scale(${sp(t, at + 0.25, fps, { damping: 9, stiffness: 300 })})`, boxShadow: `0 0 24px ${rgb(c)}` } as any} />}
            {r.winner === "tie" && <div style={{ position: "absolute", right: 28, color: rgb(PALETTE.gold), fontSize: 30, fontWeight: 900, opacity: mark, letterSpacing: 3 }}>TIE</div>}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/** Two bars racing to a value (words written, seconds, tokens). {title, unit, left:{name,icon,value}, right:{...}, at, dur, max} */
export const WordRace: React.FC<Base & { title?: string; unit?: string; left: Side & { value: number }; right: Side & { value: number }; at?: number; dur?: number; max?: number; transparent?: boolean; decimals?: number }> = (p) => {
  const { t, fps, W, H, D, tall } = useT(); const th = useTheme(p); const F = fonts(p);
  const out = outFade(p, t, D, 0.25); const at = p.at ?? 0.4, dur = p.dur ?? Math.max(1.2, D * 0.55);
  const mx = p.max ?? Math.max(p.left.value, p.right.value) * 1.08;
  const bw = tall ? W - 160 : Math.min(1400, W - 80), x0 = (W - bw) / 2;
  const sides: [Side & { value: number }, RGB][] = [[p.left, colorOf(p.left.color || "blue", th)], [p.right, colorOf(p.right.color || "claude", th)]];
  return (
    <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      {p.title && <div style={{ position: "absolute", top: tall ? 300 : 170, left: 0, right: 0, textAlign: "center", color: rgb(th.text), fontSize: 60, fontWeight: 900 }}>{p.title}</div>}
      {sides.map(([s, c], i) => {
        const v = count(t, at, dur * (s.value / Math.max(p.left.value, p.right.value)), s.value);
        const y = (tall ? H * 0.42 : H * 0.42) + i * (tall ? 330 : 240);
        const fin = t >= at + dur * (s.value / Math.max(p.left.value, p.right.value));
        return (
          <div key={i}>
            <div style={{ position: "absolute", left: x0, top: y - 80, display: "flex", alignItems: "center", gap: 18 }}>
              <Icon src={s.icon} size={60} /><div style={{ color: rgb(th.text), fontSize: 44, fontWeight: 800 }}>{s.name}</div></div>
            <div style={{ position: "absolute", left: x0, top: y, width: bw, height: 90, borderRadius: 45, background: rgb([255, 255, 255], 0.07) }} />
            <div style={{ position: "absolute", left: x0, top: y, width: Math.max(90, bw * v / mx), height: 90, borderRadius: 45,
              background: `linear-gradient(90deg, ${rgb(mix(c, [0, 0, 0], 0.3))}, ${rgb(c)})`, boxShadow: `0 0 ${fin ? 50 : 25}px ${rgb(c, 0.7)}` }} />
            <div style={{ position: "absolute", left: x0 + Math.max(90, bw * v / mx) + 24, top: y + 8, color: rgb(th.text), fontSize: 64, fontWeight: 900 }}>
              {fmt(v, p.decimals || 0)}<span style={{ fontSize: 34, color: rgb(PALETTE.dim), marginLeft: 10 }}>{p.unit || ""}</span></div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/** Claims vs reality: rows appear on cues, verdict stamps on cues. {title, rows:[{claim, verdict, note, at, at_verdict}]} */
export const ClaimBoard: React.FC<Base & { title?: string; rows: { claim: string; verdict: string; note?: string; at?: number; at_verdict?: number }[]; transparent?: boolean }> = (p) => {
  const { t, fps, W, H, D, tall, board } = useT(); const th = useTheme(p); const F = fonts(p);
  const out = outFade(p, t, D, 0.25);
  const VC0: Record<string, RGB> = { YES: PALETTE.green, NO: PALETTE.red, HALF: PALETTE.gold, TRUE: PALETTE.green, FALSE: PALETTE.red };
  if (board) {   // Shorts board: header split on " vs ", rows fill the box, big claim (60, shrinks to fit), note 40, solid verdict pill
    const n = p.rows.length, top = 112, gap = 12, rh = (H - top - 24 - gap * (n - 1)) / n;
    const [l, r_] = (p.title || "CLAIM vs REALITY").split(/\s+vs\.?\s+/i);
    return (
      <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
        <BoardCard W={W} H={H} />
        <div style={{ position: "absolute", left: 44, top: 36, fontSize: 44, fontWeight: 900, color: rgb(PALETTE.dim), letterSpacing: 1 }}>{l}</div>
        {r_ && <div style={{ position: "absolute", right: 44, top: 36, fontSize: 44, fontWeight: 900, color: rgb(PALETTE.dim), letterSpacing: 1 }}>{r_}</div>}
        {p.rows.map((r, i) => {
          const at = r.at ?? 0.3 + i * 0.5, av = r.at_verdict ?? at + 0.6, c = VC0[r.verdict.toUpperCase()] || th.accent;
          const k = ease(t, at - 0.15, at + 0.1), v = sp(t, av, fps, { damping: 11, stiffness: 260 }), y = top + i * (rh + gap);
          if (k <= 0) return null;
          const vt = r.verdict.toUpperCase(), vs = Math.min(56, rh * 0.38);
          return <div key={i} style={{ position: "absolute", left: 30 - (1 - k) * 60, top: y, width: W - 60, height: rh, opacity: k }}>
            <div style={{ position: "absolute", inset: 0, borderRadius: 28, background: "rgba(22,26,56,1)" }} />
            <div style={{ position: "absolute", left: 32, right: 300, top: 0, bottom: 0, display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <div style={{ color: rgb(th.text), fontSize: fit(r.claim, W - 390, Math.min(60, rh * 0.42), 40), fontWeight: 900, whiteSpace: "nowrap", lineHeight: 1.1 }}>{r.claim}</div>
              {r.note && t >= av && <div style={{ color: "rgb(200,205,232)", fontSize: fit(r.note, W - 140, Math.min(40, rh * 0.27), 28), fontWeight: 600, whiteSpace: "nowrap", marginTop: 4 }}>{r.note}</div>}
            </div>
            {t >= av && <div style={{ position: "absolute", right: 32, top: rh * 0.36, transform: `translateY(-50%) scale(${1 + 0.35 * (1 - v)})`, transformOrigin: "right center",
              padding: `${vs * 0.12}px ${vs * 0.45}px`, borderRadius: 18, background: rgb(c), color: "rgb(10,12,26)", fontSize: vs, fontWeight: 900 }}>{vt}</div>}
          </div>;
        })}
      </AbsoluteFill>
    );
  }
  const n = p.rows.length; const rowH = tall ? 210 : Math.min(150, 760 / n);
  const pw = tall ? W - 90 : Math.min(1640, W - 60), x0 = (W - pw) / 2, y0 = tall ? 320 : 210;
  const VC: Record<string, RGB> = { YES: PALETTE.green, NO: PALETTE.red, HALF: PALETTE.gold, TRUE: PALETTE.green, FALSE: PALETTE.red };
  return (
    <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      <div style={{ position: "absolute", top: tall ? 140 : 80, left: 0, right: 0, textAlign: "center", color: rgb(th.text), fontSize: tall ? 64 : 58, fontWeight: 900, letterSpacing: 3 }}>{p.title || "CLAIM vs REALITY"}</div>
      {p.rows.map((r, i) => {
        const at = r.at ?? 0.3 + i * 0.5, av = r.at_verdict ?? at + 0.6;
        const k = sp(t, at, fps, { damping: 18 }); const y = y0 + i * (rowH + 18); const c = VC[r.verdict.toUpperCase()] || th.accent;
        const v = ease(t, av, av + 0.3);
        return (
          <div key={i} style={{ position: "absolute", left: x0, top: y, width: pw, height: rowH, opacity: k, transform: `translateY(${(1 - k) * 40}px)` }}>
            <div style={{ position: "absolute", inset: 0, borderRadius: 22, background: `linear-gradient(90deg, ${rgb([24, 28, 52], 0.92)}, ${rgb(mix([24, 28, 52], c, 0.25 * v), 0.92)})`,
              border: `2px solid ${rgb(c, 0.15 + 0.6 * v)}` }} />
            <div style={{ position: "absolute", left: 36, top: 0, bottom: 0, right: tall ? 260 : 330, display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <div style={{ color: rgb(th.text), fontSize: tall ? 46 : Math.min(46, rowH * 0.34), fontWeight: 800 }}>{r.claim}</div>
              {r.note && <div style={{ color: rgb(PALETTE.dim), fontSize: tall ? 34 : Math.min(32, rowH * 0.22), fontWeight: 500, marginTop: 6, opacity: v }}>{r.note}</div>}
            </div>
            <Stamp text={r.verdict.toUpperCase()} color={c} t={t} at={av} fps={fps} x={pw - (tall ? 130 : 160)} y={rowH / 2} size={tall ? 56 : Math.min(58, rowH * 0.4)} rot={-6} font={F.display} />
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/** One big kinetic number. {value, decimals, prefix, suffix, label, from, at, dur, color} */
export const BigNumber: React.FC<Base & { value: number; decimals?: number; prefix?: string; suffix?: string; label?: string; from?: number; at?: number; dur?: number; color?: string; transparent?: boolean; x?: number; y?: number }> = (p) => {
  const { t, fps, W, H, D } = useT(); const th = useTheme(p); const F = fonts(p); const c = colorOf(p.color, th);
  const at = p.at ?? 0.1, dur = p.dur ?? 1.0;
  const v = count(t, at, dur, p.value, p.from ?? 0);
  const k = sp(t, at, fps, { damping: 12 }); const done = sp(t, at + dur, fps, { damping: 8, stiffness: 300 });
  const out = outFade(p, t, D, 0.25);
  const x = p.x ?? W / 2, y = p.y ?? H / 2;
  return (
    <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      <Glow color={c} size={800} x={x} y={y} alpha={0.3 * k} />
      <Shockwave x={x} y={y} t={t} at={at + dur} color={c} size={900} />
      <div style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,-55%) scale(${interpolate(k, [0, 1], [0.6, 1]) * (1 + 0.06 * done * (1 - ease(t, at + dur + 0.1, at + dur + 0.5)))})`,
        color: rgb(th.text), fontSize: 260, fontWeight: 900, whiteSpace: "nowrap", textShadow: `0 0 60px ${rgb(c, 0.7)}` }}>
        <span style={{ color: rgb(c) }}>{p.prefix || ""}</span>{fmt(v, p.decimals || 0)}<span style={{ fontSize: 120, color: rgb(c) }}>{p.suffix || ""}</span></div>
      {p.label && <div style={{ position: "absolute", left: 0, right: 0, top: y + 140, textAlign: "center", color: rgb(PALETTE.dim), fontSize: 46, fontWeight: 600, opacity: ease(t, at + 0.3, at + 0.7) }}>{p.label}</div>}
    </AbsoluteFill>
  );
};

/** Final verdict table: rows of criteria, columns per contender, cells reveal in order. {title, cols:[{name, icon, color}], rows:[{label, cells:[text|{text, good}]}], at, step} */
export const VerdictTable: React.FC<Base & { title?: string; cols: Side[]; rows: { label: string; cells: (string | { text: string; good?: boolean })[] }[]; at?: number; step?: number; transparent?: boolean }> = (p) => {
  const { t, fps, W, H, D, tall, board } = useT(); const th = useTheme(p); const F = fonts(p);
  const out = outFade(p, t, D, 0.25); const at = p.at ?? 0.3, step = p.step ?? 0.25;
  const nr = p.rows.length, nc = p.cols.length;
  if (board) {   // Shorts board: title, column heads (icon or name), rows with WIN / TIE pills; a last "Score" row becomes big numbers
    const last = p.rows[nr - 1], score = /^score$/i.test(last?.label || "") ? last : null, rows = score ? p.rows.slice(0, -1) : p.rows;
    const lab = W * 0.56, cw = (W - lab - 40) / nc, top = 170, bottom = score ? 150 : 30, rh = Math.min(84, (H - top - bottom) / rows.length);
    const cx = (j: number) => lab + cw * (j + 0.5);
    const pill = (txt: string, good?: boolean) => {
      const tie = /^tie$/i.test(txt), win = good === true || /^win$/i.test(txt);
      return { bg: win ? th.accent : tie ? [110, 116, 160] as RGB : good === false ? PALETTE.red : null, ink: [10, 12, 26] as RGB };
    };
    const ts = at + rows.length * step + 0.2, sk = sp(t, ts, fps, { damping: 10, stiffness: 220 });
    return (
      <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
        <BoardCard W={W} H={H} />
        {p.title && <div style={{ position: "absolute", top: 30, left: 0, right: 0, textAlign: "center", color: rgb(th.text), fontSize: fit(p.title, W - 80, 50, 36), fontWeight: 900 }}>{p.title}</div>}
        {p.cols.map((c, j) => <div key={j} style={{ position: "absolute", left: cx(j) - cw / 2, width: cw, top: 88, height: 76, display: "flex", alignItems: "center", justifyContent: "center", opacity: ease(t, 0, 0.3) }}>
          {c.icon ? <Icon src={c.icon} size={58} /> : <div style={{ color: rgb(colorOf(c.color, th)), fontSize: c.name.length > 10 ? 30 : 36, fontWeight: 900, textAlign: "center", lineHeight: 1.05, maxWidth: cw - 8 }}>{c.name}</div>}</div>)}
        {rows.map((r, i) => {
          const y = top + i * rh, k = ease(t, at + i * step, at + i * step + 0.2);
          if (k <= 0) return null;
          return <div key={i} style={{ opacity: k }}>
            <div style={{ position: "absolute", left: 44, top: y, height: rh, display: "flex", alignItems: "center", color: "rgb(225,228,245)", fontSize: fit(r.label, lab - 60, Math.min(42, rh * 0.55), 28), fontWeight: 700, whiteSpace: "nowrap" }}>{r.label}</div>
            {r.cells.map((cell, j) => { const c = typeof cell === "string" ? { text: cell } : cell; if (!c.text) return null; const pl = pill(c.text, c.good);
              const fs = Math.min(34, rh * 0.42);
              return <div key={j} style={{ position: "absolute", left: cx(j) - 62, width: 124, top: y + rh / 2 - fs * 0.75, height: fs * 1.5, borderRadius: fs, display: "flex", alignItems: "center", justifyContent: "center",
                background: pl.bg ? rgb(pl.bg) : "transparent", color: rgb(pl.bg ? pl.ink : th.text), fontSize: fs, fontWeight: 900 }}>{c.text}</div>; })}
          </div>;
        })}
        {score && t >= ts && <div>
          <div style={{ position: "absolute", left: 44, right: 44, top: H - 128, height: 2, background: "rgb(70,80,140)" }} />
          <div style={{ position: "absolute", left: 44, top: H - 92, transform: "translateY(-50%)", color: "rgb(200,205,232)", fontSize: 46, fontWeight: 900 }}>{score.label.toUpperCase()}</div>
          {score.cells.map((cell, j) => { const c = typeof cell === "string" ? { text: cell } : cell;
            return <div key={j} style={{ position: "absolute", left: cx(j) - cw / 2, width: cw, top: H - 92, transform: `translateY(-50%) scale(${1 + 0.4 * (1 - sk)})`, textAlign: "center",
              color: rgb(colorOf(p.cols[j]?.color, th)), fontSize: 96, fontWeight: 900, lineHeight: 1 }}>{c.text}</div>; })}
        </div>}
      </AbsoluteFill>
    );
  }
  const tw = tall ? W - 80 : Math.min(1700, W - 60), x0 = (W - tw) / 2, lab = tall ? 300 : 520, cw = (tw - lab) / nc;
  const rh = tall ? Math.min(150, 1300 / (nr + 1)) : Math.min(110, 760 / (nr + 1)), y0 = tall ? 300 : 170;
  return (
    <AbsoluteFill style={{ opacity: out, fontFamily: F.display }}>
      {!p.transparent && <Backdrop th={th} t={t} W={W} H={H} />}
      {p.title && <div style={{ position: "absolute", top: y0 - (tall ? 150 : 120), left: 0, right: 0, textAlign: "center", color: rgb(th.text), fontSize: 58, fontWeight: 900 }}>{p.title}</div>}
      {p.cols.map((c, j) => (
        <div key={j} style={{ position: "absolute", left: x0 + lab + j * cw, width: cw, top: y0, height: rh, display: "flex", alignItems: "center", justifyContent: "center", gap: 14,
          opacity: ease(t, 0, 0.3) }}><Icon src={c.icon} size={rh * 0.5} /><div style={{ color: rgb(colorOf(c.color, th)), fontSize: rh * 0.36, fontWeight: 900 }}>{c.name}</div></div>))}
      {p.rows.map((r, i) => {
        const y = y0 + (i + 1) * rh; const k = ease(t, at + i * step, at + i * step + 0.3);
        return (
          <div key={i} style={{ opacity: k }}>
            <div style={{ position: "absolute", left: x0, top: y, width: tw, height: rh - 8, borderRadius: 14, background: rgb([255, 255, 255], i % 2 ? 0.03 : 0.06) }} />
            <div style={{ position: "absolute", left: x0 + 26, top: y, height: rh - 8, display: "flex", alignItems: "center", color: rgb(th.text), fontSize: rh * 0.32, fontWeight: 700 }}>{r.label}</div>
            {r.cells.map((cell, j) => { const c = typeof cell === "string" ? { text: cell } : cell; const col = c.good === true ? PALETTE.green : c.good === false ? PALETTE.red : th.text;
              const ck = sp(t, at + i * step + 0.1 + j * 0.08, fps, { damping: 12 });
              return <div key={j} style={{ position: "absolute", left: x0 + lab + j * cw, width: cw, top: y, height: rh - 8, display: "flex", alignItems: "center", justifyContent: "center",
                color: rgb(col), fontSize: rh * 0.32, fontWeight: 800, transform: `scale(${ck})` }}>{c.text}</div>; })}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
