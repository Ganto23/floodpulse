import { useEffect, useMemo, useRef, useState } from "react";
import { HOUR } from "../lib/data";
import type { GaugeFile, GaugeMeta, Horizon, SetName, Variant } from "../lib/types";
import { displayName } from "./names";

const HORIZONS: Horizon[] = [6, 12, 24];
const BACK = 24;                                                    // hours of history left of NOW (forecast gets half the width)
const C = { truth: "#8fb8c4", obs: "#cbd5e1", base: "#64748b", fp: "#06b6d4", grid: "#1e293b", axis: "#64748b", label: "#94a3b8", flood: "#f87171" };
const parse = (s: string) => new Date(s.replace(" ", "T")).getTime();

/** Forecast chart (observed, historical baseline, FloodPulse + band) with horizon toggles. Playback lives in PlaybackBar. */
export default function ForecastPanel(p: {
  gauge: GaugeMeta | null; file: GaugeFile | null; time: string | null; horizon: Horizon; onHorizon: (h: Horizon) => void;
  setName: SetName; variant: Variant;
}) {
  const [showBase, setShowBase] = useState(false);       // historical baseline: hidden by default to keep the chart clean
  return (
    <div className="flex h-full flex-col px-5 pt-4">
      <div className="flex items-center gap-6">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">Forecast</div>
          <div className="text-[15px] text-slate-100">{p.gauge ? displayName(p.gauge.slug, p.gauge.name) : ""}</div>
        </div>
        <div className="flex items-center gap-5 text-[12px] text-slate-400">
          <Key c={C.obs} k="Observed (past)" />
          <Key c={C.fp} k={p.variant === "oracle" ? "FloodPulse forecast (perfect-rain upper bound)" : "FloodPulse forecast"} />
          <span className="flex items-center gap-2"><svg width="22" height="6"><line x1="0" x2="22" y1="3" y2="3" stroke={C.truth} strokeWidth="1.5" strokeDasharray="4 3" opacity="0.6" /></svg>Actual ground truth</span>
          <Key c={C.flood} k="Alert threshold (P99)" dashed />
          {showBase && <Key c={C.base} k="Historical baseline" dotted />}
          <span className="flex items-center gap-2"><span className="h-3 w-5 rounded-sm" style={{ background: C.fp, opacity: 0.25 }} />80% band</span>
        </div>
        <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-[11px] text-slate-500 hover:text-slate-300">
          <input type="checkbox" checked={showBase} onChange={(e) => setShowBase(e.target.checked)} className="accent-slate-500" /> baseline
        </label>
        <div className="flex rounded-md bg-slate-800/60 p-0.5">
          {HORIZONS.map((h) => (
            <button key={h} onClick={() => p.onHorizon(h)}
                    className={`rounded px-3 py-1 font-mono text-[12px] ${h === p.horizon ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:text-slate-200"}`}>
              +{h}h
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 py-2">
        {p.gauge && p.file && p.time ? <Chart file={p.file} time={p.time} horizon={p.horizon} setName={p.setName} variant={p.variant} threshold={p.gauge.p99_mm} showBase={showBase} /> : null}
      </div>

    </div>
  );
}

function Key({ c, k, dotted, dashed }: { c: string; k: string; dotted?: boolean; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <svg width="22" height="6"><line x1="0" x2="22" y1="3" y2="3" stroke={c} strokeWidth="2.5" strokeDasharray={dotted ? "2 3" : dashed ? "5 3" : undefined} strokeLinecap="round" /></svg>
      {k}
    </span>
  );
}

function Chart({ file, time, horizon, setName, variant, threshold, showBase }: { file: GaugeFile; time: string; horizon: Horizon; setName: SetName; variant: Variant; threshold: number; showBase: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 200 });
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
    const t0 = parse(time), obsStart = parse(set.obs_start);
    const k = fc.origins.indexOf(time);
    const rows = Array.from({ length: BACK + 25 }, (_, i) => {
      const step = i - BACK;
      const obs = set.obs[Math.round((t0 + step * HOUR - obsStart) / HOUR)] ?? null;
      const at = (arr: (number | null)[][]) => (k >= 0 && step >= 1 && step <= horizon ? arr[k]?.[step - 1] ?? null : null);
      return { obs, base: at(fc.baseline), fp: at(fc.floodpulse), lo: at(fc.band_lo), hi: at(fc.band_hi) };
    });
    const vals = rows.flatMap((r) => [r.obs, showBase ? r.base : null, r.fp, r.lo, r.hi]).filter((v): v is number => v != null);
    vals.push(threshold);                                      // the flood alert line is always on screen
    const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.1 || 50;
    return { rows, ymin: lo - pad, ymax: hi + pad, hasFc: k >= 0 };
  }, [set, fc, time, horizon, threshold, showBase]);

  if (!model) return <div ref={ref} className="h-full" />;

  const M = { l: 52, r: 16, t: 24, b: 22 };
  const W = Math.max(size.w, 300), H = Math.max(size.h, 100);
  const iw = W - M.l - M.r, ih = H - M.t - M.b;
  const x = (i: number) => M.l + (i / (model.rows.length - 1)) * iw;
  const y = (v: number) => M.t + (1 - (v - model.ymin) / (model.ymax - model.ymin)) * ih;
  const nowObs = model.rows[BACK].obs;
  const series = (key: "obs" | "base" | "fp", from: number, to: number, anchor = false) => {
    let d = anchor && nowObs != null ? `M${x(BACK)},${y(nowObs)}` : "", pen = d !== "";
    for (let i = from; i <= to; i++) {
      const v = model.rows[i][key];
      if (v == null) { pen = false; continue; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true;
    }
    return d;
  };
  const band = (() => {
    const pts = model.rows.map((r, i) => (r.lo != null && r.hi != null ? { i, lo: r.lo, hi: r.hi } : null)).filter(Boolean) as { i: number; lo: number; hi: number }[];
    return pts.length ? `M${pts.map((q) => `${x(q.i)},${y(q.hi)}`).join("L")}L${[...pts].reverse().map((q) => `${x(q.i)},${y(q.lo)}`).join("L")}Z` : "";
  })();
  const ticks = [0, 1, 2, 3].map((i) => model.ymin + ((model.ymax - model.ymin) * (i + 0.5)) / 4);

  return (
    <div ref={ref} className="h-full w-full">
      <svg width={W} height={H} role="img" aria-label="Observed river level, historical baseline and FloodPulse forecast">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={M.l} x2={M.l + iw} y1={y(v)} y2={y(v)} stroke={C.grid} />
            <text x={M.l - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill={C.axis} fontFamily="JetBrains Mono">{(v / 1000).toFixed(1)} m</text>
          </g>
        ))}
        {[-24, -12, 0, 12, 24].map((s) => (
          <text key={s} x={x(s + BACK)} y={H - 4} textAnchor="middle" fontSize={11} fill={s === 0 ? C.label : C.axis} fontFamily="JetBrains Mono">
            {s === 0 ? "" : `${s > 0 ? "+" : ""}${s}h`}
          </text>
        ))}
        {/* future side is lightly shaded so past vs future reads at a glance */}
        <rect x={x(BACK)} y={M.t} width={x(model.rows.length - 1) - x(BACK)} height={ih} fill="#1e293b" opacity={0.45} />
        <text x={x(BACK) - 10} y={M.t + 16} textAnchor="end" fontSize={11} fill={C.axis} letterSpacing="0.1em">◄ PAST · OBSERVED</text>
        <text x={x(BACK) + 10} y={M.t + 16} fontSize={11} fill={C.fp} letterSpacing="0.1em">FUTURE · FORECAST ►</text>
        {/* flood alert threshold */}
        <line x1={M.l} x2={M.l + iw} y1={y(threshold)} y2={y(threshold)} stroke={C.flood} strokeWidth={1.5} strokeDasharray="6 4" opacity={0.85} />
        <text x={M.l + 8} y={y(threshold) - 6} fontSize={11} fill={C.flood}>Flood alert threshold (P99) · {(threshold / 1000).toFixed(2)}m</text>
        {band && <path d={band} fill={C.fp} opacity={0.22} />}
        <path d={series("obs", 0, BACK)} fill="none" stroke={C.obs} strokeWidth={2.5} />
        {/* actual ground truth after NOW: thin, muted, dashed */}
        <path d={series("obs", BACK, model.rows.length - 1)} fill="none" stroke={C.truth} strokeWidth={1.5} strokeDasharray="4 3" opacity={0.4} />
        {showBase && <path d={series("base", BACK + 1, BACK + horizon, true)} fill="none" stroke={C.base} strokeWidth={2.5} strokeDasharray="1 5" strokeLinecap="round" />}
        <path d={series("fp", BACK + 1, BACK + horizon, true)} fill="none" stroke={C.fp} strokeWidth={3} />
        {/* NOW divider */}
        <line x1={x(BACK)} x2={x(BACK)} y1={M.t - 2} y2={M.t + ih} stroke="#cbd5e1" strokeWidth={1.25} strokeDasharray="4 4" />
        <rect x={x(BACK) - 66} y={M.t - 20} width={132} height={18} rx={4} fill="#0f172a" stroke="#475569" />
        <text x={x(BACK)} y={M.t - 7} textAnchor="middle" fontSize={11} fill="#e2e8f0" fontFamily="JetBrains Mono">NOW (Forecast Line)</text>
        {!model.hasFc && <text x={x(BACK) + 10} y={M.t + 16} fontSize={12} fill={C.axis}>no forecast at this time (gauge data gap)</text>}
      </svg>
    </div>
  );
}
