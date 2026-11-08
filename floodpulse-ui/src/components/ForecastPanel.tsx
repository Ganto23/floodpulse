import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { HOUR, m, pct } from "../lib/data";
import type { GaugeFile, GaugeMeta, Horizon, Manifest, SetName, Variant } from "../lib/types";

const HORIZONS: Horizon[] = [6, 12, 18, 24];
const SET_SHORT: Record<string, string> = { "2024": "2024", ciara_dennis: "STORM CIARA · 2020", babet: "STORM BABET · 2023" };
const VARIANT_SHORT: Record<Variant, string> = { deployed: "REAL RAIN FORECASTS", oracle: "PERFECT RAIN (BEST CASE)", past: "NO RAIN FORECAST" };
const BACK = 72;                                   // hours of history shown left of "now"
const C = { obs: "#3987e5", base: "#d95926", fp: "#199e70", grid: "#27272a", axis: "#71717a", warn: "#fab219", crit: "#d03b3b" };
const parse = (s: string) => new Date(s.replace(" ", "T")).getTime();
const fmtShort = (ms: number) => new Date(ms).toISOString().slice(5, 16).replace("T", " ");

interface Props {
  manifest: Manifest; gauge: GaugeMeta | null; file: GaugeFile | null; setName: SetName; variant: Variant;
  time: string | null; horizon: Horizon; onHorizon: (h: Horizon) => void; onSet: (s: SetName) => void;
  onVariant: (v: Variant) => void; times: string[]; t: number; onT: (i: number) => void; playing: boolean; onPlay: () => void;
  advanced: boolean;
}

export default function ForecastPanel(p: Props) {
  const { manifest, gauge, file, setName, variant, time, horizon } = p;
  const stats = gauge?.sets[setName]?.[variant];
  return (
    <div className="flex h-full flex-col">
      {/* controls row (filters in one row above the chart) */}
      <div className="flex flex-wrap items-center gap-3 border-b border-zinc-800 px-3 py-1.5 text-[10px]">
        <span className="font-bold tracking-[0.2em] text-accent">{gauge ? gauge.name.toUpperCase() : "FORECAST"}</span>
        <Seg value={setName} options={Object.keys(manifest.sets).map((k) => [k, SET_SHORT[k] ?? k])}
             onChange={(v) => p.onSet(v as SetName)} />
        <Seg value={variant} options={manifest.sets[setName].variants.map((v) => [v, VARIANT_SHORT[v]])}
             onChange={(v) => p.onVariant(v as Variant)} />
        {p.advanced && <Seg value={String(horizon)} options={HORIZONS.map((h) => [String(h), `+${h}H`])} onChange={(v) => p.onHorizon(Number(v) as Horizon)} />}
        {p.advanced && stats && (
          <span className="ml-auto text-zinc-400">
            {gauge?.name} · MAE <span className="text-zinc-100">{stats.mae_mm.booster.toFixed(0)}</span> mm vs TimesFM{" "}
            <span className="text-zinc-100">{stats.mae_mm.timesfm.toFixed(0)}</span> · surge MAE{" "}
            <span className="text-zinc-100">{stats.surge_mae_mm.booster?.toFixed(0) ?? "—"}</span> vs{" "}
            <span className="text-zinc-100">{stats.surge_mae_mm.timesfm?.toFixed(0) ?? "—"}</span> · warnings caught{" "}
            <span className="text-zinc-100">{pct(stats.warning.booster.hit_rate)}</span> of {stats.events}
          </span>
        )}
      </div>

      <div className="min-h-0 flex-1">
        {gauge && file && time ? <Chart gauge={gauge} file={file} setName={setName} variant={variant} time={time} horizon={horizon} />
          : <div className="flex h-full items-center justify-center text-zinc-600">select a gauge</div>}
      </div>

      {/* storm replay scrubber */}
      <div className="flex items-center gap-3 border-t border-zinc-800 px-3 py-1.5">
        <button onClick={() => p.onT(Math.max(0, p.t - 1))} className="border border-zinc-700 p-0.5 text-zinc-300 hover:border-accent hover:text-accent" aria-label="Step back"><ChevronLeft size={14} /></button>
        <button onClick={p.onPlay} className="border border-zinc-700 p-0.5 text-accent hover:border-accent" aria-label={p.playing ? "Pause replay" : "Play replay"}>
          {p.playing ? <Pause size={14} /> : <Play size={14} />}
        </button>
        <button onClick={() => p.onT(Math.min(p.times.length - 1, p.t + 1))} className="border border-zinc-700 p-0.5 text-zinc-300 hover:border-accent hover:text-accent" aria-label="Step forward"><ChevronRight size={14} /></button>
        <span className="w-36 shrink-0 tabular-nums text-zinc-200">{time ? fmtShort(parse(time)) + "Z" : "—"}</span>
        <input type="range" className="scrub" min={0} max={p.times.length - 1} value={p.t}
               onChange={(e) => p.onT(Number(e.target.value))} aria-label="Replay time" />
        <span className="shrink-0 text-[10px] text-zinc-500">drag to move through time · {setName === "2024" ? "3 h" : "1 h"} per step</span>
      </div>
    </div>
  );
}

function Chart({ gauge, file, setName, variant, time, horizon }: {
  gauge: GaugeMeta; file: GaugeFile; setName: SetName; variant: Variant; time: string; horizon: Horizon;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 200 });
  const [hx, setHx] = useState<number | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const set = file.sets[setName];
  const fc = set?.variants[variant];
  const model = useMemo(() => {
    if (!set || !fc) return null;
    const t0 = parse(time);
    const obsStart = parse(set.obs_start);
    const k = fc.origins.indexOf(time);
    const hours: number[] = [];
    for (let i = -BACK; i <= 24; i++) hours.push(t0 + i * HOUR);
    const obsAt = (ms: number) => set.obs[Math.round((ms - obsStart) / HOUR)] ?? null;
    const fcAt = (arr: (number | null)[][], step: number) => (k >= 0 && step >= 1 && step <= horizon ? arr[k]?.[step - 1] ?? null : null);
    const rows = hours.map((ms, i) => {
      const step = i - BACK;
      return { ms, step, obs: obsAt(ms), base: fcAt(fc.baseline, step), fp: fcAt(fc.floodpulse, step),
               lo: fcAt(fc.band_lo, step), hi: fcAt(fc.band_hi, step) };
    });
    const vals = rows.flatMap((r) => [r.obs, r.fp, r.base, r.lo, r.hi]).filter((v): v is number => v != null);
    vals.push(gauge.p95_mm, gauge.p99_mm);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo) * 0.08 || 50;
    return { rows, ymin: lo - pad, ymax: hi + pad, hasFc: k >= 0 };
  }, [set, fc, time, horizon, gauge]);

  if (!model) return <div ref={ref} className="flex h-full items-center justify-center text-zinc-600">no forecasts for this gauge in this replay set</div>;

  const M = { l: 48, r: 112, t: 26, b: 20 };
  const W = Math.max(size.w, 300), Hh = Math.max(size.h, 120);
  const iw = W - M.l - M.r, ih = Hh - M.t - M.b;
  const x = (i: number) => M.l + (i / (model.rows.length - 1)) * iw;
  const y = (v: number) => M.t + (1 - (v - model.ymin) / (model.ymax - model.ymin)) * ih;
  const path = (key: "obs" | "base" | "fp", from = 0, to = model.rows.length - 1) => {
    let d = "", pen = false;
    for (let i = from; i <= to; i++) {
      const v = model.rows[i][key];
      if (v == null) { pen = false; continue; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true;
    }
    return d;
  };
  const nowI = BACK;
  const band = (() => {
    const pts = model.rows.map((r, i) => (r.lo != null && r.hi != null ? { i, lo: r.lo, hi: r.hi } : null)).filter(Boolean) as { i: number; lo: number; hi: number }[];
    if (!pts.length) return "";
    return `M${pts.map((p) => `${x(p.i)},${y(p.hi)}`).join("L")}L${pts.reverse().map((p) => `${x(p.i)},${y(p.lo)}`).join("L")}Z`;
  })();
  const ticks = Array.from({ length: 5 }, (_, i) => model.ymin + ((model.ymax - model.ymin) * i) / 4);
  const hover = hx != null ? model.rows[hx] : null;
  const last = (key: "base" | "fp") => { for (let i = model.rows.length - 1; i >= 0; i--) if (model.rows[i][key] != null) return i; return -1; };

  const rightLabels = (() => {
    const ls: { k: string; text: string; ly: number; fill: string }[] = [
      { k: "p99", text: `alert ${(gauge.p99_mm / 1000).toFixed(2)} m`, ly: y(gauge.p99_mm), fill: "#a1a1aa" },
      { k: "p95", text: `watch ${(gauge.p95_mm / 1000).toFixed(2)} m`, ly: y(gauge.p95_mm), fill: "#a1a1aa" },
    ];
    for (const [k, text] of [["fp", "FloodPulse"], ["base", "old model"]] as const) {
      const i = last(k);
      const v = i >= 0 ? model.rows[i][k] : null;
      if (v != null) ls.push({ k, text, ly: y(v), fill: "#e4e4e7" });
    }
    ls.sort((a, b) => a.ly - b.ly);
    for (let i = 1; i < ls.length; i++) ls[i].ly = Math.max(ls[i].ly, ls[i - 1].ly + 11);
    const over = ls.length ? ls[ls.length - 1].ly - (M.t + ih) : 0;   // keep inside the plot vertically
    if (over > 0) for (let i = ls.length - 1; i >= 0; i--) { ls[i].ly -= over; if (i > 0) ls[i - 1].ly = Math.min(ls[i - 1].ly, ls[i].ly - 11); }
    return ls;
  })();

  return (
    <div ref={ref} className="relative h-full w-full">
      <svg width={W} height={Hh} role="img" aria-label={`Forecast envelope for ${gauge.name}`}
           onMouseMove={(e) => {
             const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
             const i = Math.round(((e.clientX - r.left - M.l) / iw) * (model.rows.length - 1));
             setHx(i >= 0 && i < model.rows.length ? i : null);
           }} onMouseLeave={() => setHx(null)}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={M.l} x2={M.l + iw} y1={y(v)} y2={y(v)} stroke={C.grid} strokeWidth={1} />
            <text x={M.l - 6} y={y(v) + 3} textAnchor="end" fontSize={10} fill={C.axis}>{(v / 1000).toFixed(2)}</text>
          </g>
        ))}
        {[-72, -48, -24, 0, 12, 24].map((s) => (
          <text key={s} x={x(s + BACK)} y={Hh - 5} textAnchor="middle" fontSize={10} fill={C.axis}>{s === 0 ? "NOW" : `${s > 0 ? "+" : ""}${s}h`}</text>
        ))}
        {/* alert levels */}
        {([["P99", gauge.p99_mm, C.crit], ["P95", gauge.p95_mm, C.warn]] as const).map(([lab, v, col]) => (
          <line key={lab} x1={M.l} x2={M.l + iw} y1={y(v)} y2={y(v)} stroke={col} strokeWidth={1} strokeDasharray="2 4" opacity={0.8} />
        ))}
        {/* horizon window */}
        <rect x={x(nowI)} y={M.t} width={x(nowI + horizon) - x(nowI)} height={ih} fill="#22d3ee" opacity={0.04} />
        <line x1={x(nowI)} x2={x(nowI)} y1={M.t} y2={M.t + ih} stroke="#a1a1aa" strokeWidth={1} />
        {band && <path d={band} fill={C.fp} opacity={0.16} />}
        <path d={path("obs", 0, nowI)} fill="none" stroke={C.obs} strokeWidth={2} />
        <path d={path("obs", nowI, model.rows.length - 1)} fill="none" stroke={C.obs} strokeWidth={1.5} strokeDasharray="1 3" opacity={0.75} />
        <path d={path("base")} fill="none" stroke={C.base} strokeWidth={2} strokeDasharray="6 4" />
        <path d={path("fp")} fill="none" stroke={C.fp} strokeWidth={2} />
        {/* right-margin labels (line ends + alert levels), de-collided so none overlap */}
        {rightLabels.map((l) => <text key={l.k} x={M.l + iw + 6} y={l.ly + 3} fontSize={10} fill={l.fill}>{l.text}</text>)}
        <text x={x(nowI) - 6} y={M.t + 10} textAnchor="end" fontSize={10} fill="#a1a1aa">← what happened before</text>
        <text x={x(nowI) + 6} y={M.t + 10} fontSize={10} fill="#a1a1aa">forecast made here → (dotted blue = what really happened)</text>
        {hover && <line x1={x(hx!)} x2={x(hx!)} y1={M.t} y2={M.t + ih} stroke="#e4e4e7" strokeWidth={1} opacity={0.4} />}
        {!model.hasFc && <text x={M.l + iw / 2} y={M.t + ih / 2} textAnchor="middle" fontSize={11} fill={C.axis}>no forecast issued for this gauge at this time</text>}
      </svg>
      {hover && (
        <div className="pointer-events-none absolute top-7 border border-zinc-700 bg-zinc-950/95 px-2 py-1.5 text-[10px] leading-4"
             style={{ left: Math.min(x(hx!) + 10, W - 190) }}>
          <div className="text-zinc-300">{fmtShort(hover.ms)}Z · {hover.step > 0 ? `+${hover.step}h` : hover.step === 0 ? "now" : `${hover.step}h`}</div>
          <Row c={C.obs} k={hover.step > 0 ? "really happened" : "measured"} v={m(hover.obs)} />
          {hover.step > 0 && <Row c={C.base} k="old model" v={m(hover.base)} dashed />}
          {hover.step > 0 && <Row c={C.fp} k="FloodPulse" v={m(hover.fp)} />}
          {hover.step > 0 && hover.lo != null && <Row c={C.fp} k="likely range" v={`${m(hover.lo)}–${m(hover.hi)}`} faint />}
        </div>
      )}
      <div className="absolute left-12 top-1 flex flex-wrap gap-x-4 text-[10px] text-zinc-400">
        <Legend c={C.obs} k="River level (measured)" />
        <Legend c={C.base} k="Old model (river history only)" dashed />
        <Legend c={C.fp} k="FloodPulse (adds rain)" />
        <Legend c={C.fp} k="Likely range*" faint />
      </div>
      <div className="absolute right-2 top-1 text-[9px] text-zinc-600">*approximate 80% range</div>
    </div>
  );
}

function Row({ c, k, v, dashed, faint }: { c: string; k: string; v: string; dashed?: boolean; faint?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="flex items-center gap-1 text-zinc-400"><Swatch c={c} dashed={dashed} faint={faint} />{k}</span>
      <span className="tabular-nums text-zinc-100">{v} m</span>
    </div>
  );
}
function Legend({ c, k, dashed, faint }: { c: string; k: string; dashed?: boolean; faint?: boolean }) {
  return <span className="flex items-center gap-1.5"><Swatch c={c} dashed={dashed} faint={faint} />{k}</span>;
}
function Swatch({ c, dashed, faint }: { c: string; dashed?: boolean; faint?: boolean }) {
  return faint ? <span className="inline-block h-2 w-4" style={{ background: c, opacity: 0.3 }} />
    : <span className="inline-block w-4 border-t-2" style={{ borderColor: c, borderStyle: dashed ? "dashed" : "solid" }} />;
}
function Seg({ value, options, onChange }: { value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <span className="flex border border-zinc-800">
      {options.map(([v, label]) => (
        <button key={v} onClick={() => onChange(v)}
                className={`px-1.5 py-0.5 ${v === value ? "bg-zinc-800 text-accent" : "text-zinc-500 hover:text-zinc-200"}`}>{label}</button>
      ))}
    </span>
  );
}
