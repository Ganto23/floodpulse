import { useEffect, useId, useMemo, useRef, useState } from "react";
import { HOUR, m } from "../lib/data";
import type { GaugeFile, GaugeMeta, Horizon, SetName, Variant } from "../lib/types";
import { displayName } from "./names";

const HORIZONS: Horizon[] = [6, 12, 24];
const BACK = 24;                                                    // hours of history left of NOW (forecast gets half the width)
const C = { truth: "#8fb8c4", obs: "#cbd5e1", fp: "#06b6d4", grid: "#1e293b", axis: "#64748b", label: "#94a3b8", flood: "#f87171" };
const parse = (s: string) => new Date(s.replace(" ", "T")).getTime();

type Pt = { obs: number | null; fp: number | null; lo: number | null; hi: number | null };
interface Model { rows: Pt[]; hasFc: boolean; actualPeak: number | null; fcPeak: number | null; nowObs: number | null }

/** One place that reads the replay data for the chart AND the outcome badge, so they can never disagree. */
function useForecast(file: GaugeFile | null, time: string | null, horizon: Horizon, setName: SetName, variant: Variant): Model | null {
  return useMemo(() => {
    const set = file?.sets[setName];
    const fc = set?.variants[variant];
    if (!set || !fc || !time) return null;
    const t0 = parse(time), obsStart = parse(set.obs_start);
    const k = fc.origins.indexOf(time);
    const rows: Pt[] = Array.from({ length: BACK + 25 }, (_, i) => {
      const step = i - BACK;
      const obs = set.obs[Math.round((t0 + step * HOUR - obsStart) / HOUR)] ?? null;
      const at = (arr: (number | null)[][]) => (k >= 0 && step >= 1 && step <= horizon ? arr[k]?.[step - 1] ?? null : null);
      return { obs, fp: at(fc.floodpulse), lo: at(fc.band_lo), hi: at(fc.band_hi) };
    });
    const peak = (key: "obs" | "fp") => {
      const v = rows.slice(BACK + 1, BACK + horizon + 1).map((r) => r[key]).filter((x): x is number => x != null);
      return v.length ? Math.max(...v) : null;
    };
    return { rows, hasFc: k >= 0, actualPeak: peak("obs"), fcPeak: peak("fp"), nowObs: rows[BACK].obs };
  }, [file, time, horizon, setName, variant]);
}

/** Forecast chart (observed, FloodPulse forecast + band, actual ground truth, alert threshold) with an explicit "what actually happened" outcome badge. Playback lives in PlaybackBar. */
export default function ForecastPanel(p: {
  gauge: GaugeMeta | null; file: GaugeFile | null; time: string | null; horizon: Horizon; onHorizon: (h: Horizon) => void;
  setName: SetName; variant: Variant;
}) {
  const model = useForecast(p.file, p.time, p.horizon, p.setName, p.variant);
  return (
    <div className="flex h-full flex-col px-5 pt-3">
      <div className="flex items-center gap-4">
        <div className="min-w-0">
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">Forecast</div>
          <div className="truncate text-[15px] text-slate-100">{p.gauge ? displayName(p.gauge.slug, p.gauge.name) : ""}</div>
        </div>
        {p.gauge && model && <Outcome model={model} threshold={p.gauge.p99_mm} horizon={p.horizon} />}
        <div className="ml-auto flex rounded-md bg-slate-800/60 p-0.5">
          {HORIZONS.map((h) => (
            <button key={h} onClick={() => p.onHorizon(h)}
                    className={`rounded px-3 py-1 font-mono text-[12px] ${h === p.horizon ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:text-slate-200"}`}>
              +{h}h
            </button>
          ))}
        </div>
      </div>
      <div className="mt-1.5 flex items-center gap-5 text-[12px] text-slate-400">
        <Key c={C.obs} k="Observed (past)" />
        <Key c={C.fp} k="FloodPulse Forecast" />
        <span className="flex items-center gap-2"><svg width="22" height="6"><line x1="0" x2="22" y1="3" y2="3" stroke={C.truth} strokeWidth="1.5" strokeDasharray="4 3" opacity="0.6" /></svg>Actual Ground Truth</span>
        <Key c={C.flood} k="Alert Threshold (P99)" dashed />
        <span className="flex items-center gap-2"><span className="h-3 w-5 rounded-sm" style={{ background: C.flood, opacity: 0.25 }} />Above threshold</span>
        <span className="flex items-center gap-2"><span className="h-3 w-5 rounded-sm" style={{ background: C.fp, opacity: 0.25 }} />80% Confidence Band</span>
      </div>

      <div className="min-h-0 flex-1 py-1.5">
        {p.gauge && model ? <Chart model={model} horizon={p.horizon} threshold={p.gauge.p99_mm} /> : null}
      </div>
    </div>
  );
}

/** Prediction vs reality over the selected horizon: did the river actually cross the P99 alert threshold, and did FloodPulse call it? */
function Outcome({ model, threshold, horizon }: { model: Model; threshold: number; horizon: Horizon }) {
  const { actualPeak, fcPeak, hasFc } = model;
  if (actualPeak == null) return <span className="text-[12px] text-slate-500">Actual outcome: not available (gauge data gap)</span>;
  const breached = actualPeak >= threshold;
  const called = hasFc && fcPeak != null && fcPeak >= threshold;
  const verdict = !hasFc ? null
    : breached ? (called ? { t: "✓ forecast called it", c: "text-green-300" } : { t: "✗ forecast missed it", c: "text-amber-300" })
    : (called ? { t: "✗ false alarm", c: "text-amber-300" } : { t: "✓ correctly safe", c: "text-green-300" });
  return (
    <span className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-[12px] ring-1 ${breached ? "bg-crit/15 ring-crit/50" : "bg-ok/10 ring-ok/30"}`}>
      <span className="text-slate-400">Actual outcome (+{horizon}h):</span>
      <b className={breached ? "text-red-200" : "text-green-200"}>{breached ? "THRESHOLD BREACHED" : "SAFE"}</b>
      <span className="font-mono text-slate-300">peak {m(actualPeak)}m vs {m(threshold)}m</span>
      {verdict && <span className={`font-medium ${verdict.c}`}>· {verdict.t}</span>}
    </span>
  );
}

function Key({ c, k, dashed }: { c: string; k: string; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <svg width="22" height="6"><line x1="0" x2="22" y1="3" y2="3" stroke={c} strokeWidth="2.5" strokeDasharray={dashed ? "5 3" : undefined} strokeLinecap="round" /></svg>
      {k}
    </span>
  );
}

function Chart({ model, horizon, threshold }: { model: Model; horizon: Horizon; threshold: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const clipId = "breach" + useId().replace(/:/g, "");
  const [size, setSize] = useState({ w: 800, h: 200 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { rows, nowObs } = model;
  const vals = rows.flatMap((r) => [r.obs, r.fp, r.lo, r.hi]).filter((v): v is number => v != null);
  vals.push(threshold);                                        // the alert threshold is always on screen
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.1 || 50;
  const ymin = lo - pad, ymax = hi + pad;

  const M = { l: 52, r: 16, t: 24, b: 22 };
  const W = Math.max(size.w, 300), H = Math.max(size.h, 100);
  const iw = W - M.l - M.r, ih = H - M.t - M.b;
  const x = (i: number) => M.l + (i / (rows.length - 1)) * iw;
  const y = (v: number) => M.t + (1 - (v - ymin) / (ymax - ymin)) * ih;
  const pts = (key: "obs" | "fp", from: number, to: number, anchor = false) => {
    const out: [number, number][] = anchor && nowObs != null ? [[BACK, nowObs]] : [];
    for (let i = from; i <= to; i++) { const v = rows[i][key]; if (v != null) out.push([i, v]); }
    return out;
  };
  const line = (p: [number, number][]) => p.map(([i, v], j) => `${j ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  // area between a line and the threshold; clipped to the region above the threshold, so only breaches are shaded
  const breachArea = (p: [number, number][]) => p.length < 2 ? "" :
    `${line(p)}L${x(p[p.length - 1][0])},${y(threshold)}L${x(p[0][0])},${y(threshold)}Z`;
  const band = (() => {
    const q = rows.map((r, i) => (r.lo != null && r.hi != null ? { i, lo: r.lo, hi: r.hi } : null)).filter(Boolean) as { i: number; lo: number; hi: number }[];
    return q.length ? `M${q.map((a) => `${x(a.i)},${y(a.hi)}`).join("L")}L${[...q].reverse().map((a) => `${x(a.i)},${y(a.lo)}`).join("L")}Z` : "";
  })();
  const ticks = [0, 1, 2, 3].map((i) => ymin + ((ymax - ymin) * (i + 0.5)) / 4);
  const fcPts = pts("fp", BACK + 1, BACK + horizon, true);
  const sideY = y(threshold) < M.t + 30 ? M.t + ih - 8 : M.t + 16;   // keep PAST/FUTURE labels clear of the threshold line
  const truthPts = pts("obs", BACK, rows.length - 1);

  return (
    <div ref={ref} className="h-full w-full">
      <svg width={W} height={H} role="img" aria-label="Observed river level, FloodPulse forecast, actual outcome and alert threshold">
        <defs>
          <clipPath id={clipId}><rect x={M.l} y={M.t} width={iw} height={Math.max(0, y(threshold) - M.t)} /></clipPath>
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={M.l} x2={M.l + iw} y1={y(v)} y2={y(v)} stroke={C.grid} />
            <text x={M.l - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill={C.axis} fontFamily="JetBrains Mono">{(v / 1000).toFixed(1)} m</text>
          </g>
        ))}
        {[-24, -12, 12, 24].map((s) => (
          <text key={s} x={x(s + BACK)} y={H - 4} textAnchor="middle" fontSize={11} fill={C.axis} fontFamily="JetBrains Mono">{`${s > 0 ? "+" : ""}${s}h`}</text>
        ))}
        {/* future side is lightly shaded so past vs future reads at a glance */}
        <rect x={x(BACK)} y={M.t} width={x(rows.length - 1) - x(BACK)} height={ih} fill="#1e293b" opacity={0.45} />
        <text x={x(BACK) - 10} y={sideY} textAnchor="end" fontSize={11} fill={C.axis} letterSpacing="0.1em">◄ PAST · OBSERVED</text>
        <text x={x(BACK) + 10} y={sideY} fontSize={11} fill={C.fp} letterSpacing="0.1em">FUTURE · FORECAST ►</text>
        {/* breach fills: soft red between a line and the threshold wherever the line is above it */}
        <g clipPath={`url(#${clipId})`}>
          <path d={breachArea(truthPts)} fill={C.flood} opacity={0.12} />
          <path d={breachArea(fcPts)} fill={C.flood} opacity={0.2} />
        </g>
        <line x1={M.l} x2={M.l + iw} y1={y(threshold)} y2={y(threshold)} stroke={C.flood} strokeWidth={1.5} strokeDasharray="6 4" opacity={0.85} />
        <text x={M.l + 8} y={y(threshold) - 6} fontSize={11} fill={C.flood}>Alert Threshold (P99) · {(threshold / 1000).toFixed(2)}m</text>
        {band && <path d={band} fill={C.fp} opacity={0.18} />}
        <path d={line(pts("obs", 0, BACK))} fill="none" stroke={C.obs} strokeWidth={2.5} />
        <path d={line(truthPts)} fill="none" stroke={C.truth} strokeWidth={1.5} strokeDasharray="4 3" opacity={0.4} />
        <path d={line(fcPts)} fill="none" stroke={C.fp} strokeWidth={3} />
        {/* NOW divider */}
        <line x1={x(BACK)} x2={x(BACK)} y1={M.t - 2} y2={M.t + ih} stroke="#cbd5e1" strokeWidth={1.25} strokeDasharray="4 4" />
        <rect x={x(BACK) - 66} y={M.t - 20} width={132} height={18} rx={4} fill="#0f172a" stroke="#475569" />
        <text x={x(BACK)} y={M.t - 7} textAnchor="middle" fontSize={11} fill="#e2e8f0" fontFamily="JetBrains Mono">NOW (Forecast Line)</text>
        {!model.hasFc && <text x={x(BACK) + 10} y={M.t + 34} fontSize={12} fill={C.axis}>no forecast at this time (gauge data gap)</text>}
      </svg>
    </div>
  );
}
