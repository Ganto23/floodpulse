import { useEffect, useMemo, useRef, useState } from "react";
import { HOUR } from "../lib/data";
import type { GaugeFile, GaugeMeta, Horizon, SetName, Variant } from "../lib/types";
import { displayName } from "./names";

const HORIZONS: Horizon[] = [6, 12, 24];
const BACK = 24;                                                    // hours of history left of NOW (forecast gets half the width)
const C = { obs: "#e2e8f0", base: "#64748b", fp: "#22c3dc", grid: "#1e293b", axis: "#64748b", label: "#94a3b8" };
const parse = (s: string) => new Date(s.replace(" ", "T")).getTime();

/** Forecast chart (observed, historical baseline, FloodPulse + band) with horizon toggles. Playback lives in PlaybackBar. */
export default function ForecastPanel(p: {
  gauge: GaugeMeta | null; file: GaugeFile | null; time: string | null; horizon: Horizon; onHorizon: (h: Horizon) => void;
  setName: SetName; variant: Variant;
}) {
  return (
    <div className="flex h-full flex-col px-5 pt-4">
      <div className="flex items-center gap-6">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">Forecast</div>
          <div className="text-[15px] text-slate-100">{p.gauge ? displayName(p.gauge.slug, p.gauge.name) : ""}</div>
        </div>
        <div className="flex items-center gap-5 text-[12px] text-slate-400">
          <Key c={C.obs} k="Observed" />
          <Key c={C.base} k="Historical baseline" dotted />
          <Key c={C.fp} k={p.variant === "oracle" ? "FloodPulse (perfect-rain upper bound)" : "FloodPulse (rain-augmented)"} />
          <span className="flex items-center gap-2"><span className="h-3 w-5 rounded-sm" style={{ background: C.fp, opacity: 0.25 }} />80% band</span>
        </div>
        <div className="ml-auto flex rounded-md bg-slate-800/60 p-0.5">
          {HORIZONS.map((h) => (
            <button key={h} onClick={() => p.onHorizon(h)}
                    className={`rounded px-3 py-1 font-mono text-[12px] ${h === p.horizon ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:text-slate-200"}`}>
              +{h}h
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 py-2">
        {p.gauge && p.file && p.time ? <Chart file={p.file} time={p.time} horizon={p.horizon} setName={p.setName} variant={p.variant} /> : null}
      </div>

    </div>
  );
}

function Key({ c, k, dotted }: { c: string; k: string; dotted?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <svg width="22" height="6"><line x1="0" x2="22" y1="3" y2="3" stroke={c} strokeWidth="2.5" strokeDasharray={dotted ? "2 3" : undefined} strokeLinecap="round" /></svg>
      {k}
    </span>
  );
}

function Chart({ file, time, horizon, setName, variant }: { file: GaugeFile; time: string; horizon: Horizon; setName: SetName; variant: Variant }) {
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
    const vals = rows.flatMap((r) => [r.obs, r.base, r.fp, r.lo, r.hi]).filter((v): v is number => v != null);
    const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.1 || 50;
    return { rows, ymin: lo - pad, ymax: hi + pad, hasFc: k >= 0 };
  }, [set, fc, time, horizon]);

  if (!model) return <div ref={ref} className="h-full" />;

  const M = { l: 52, r: 16, t: 8, b: 22 };
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
            {s === 0 ? "NOW" : `${s > 0 ? "+" : ""}${s}h`}
          </text>
        ))}
        <rect x={x(BACK)} y={M.t} width={x(BACK + horizon) - x(BACK)} height={ih} fill="#1e293b" opacity={0.35} />
        <line x1={x(BACK)} x2={x(BACK)} y1={M.t} y2={M.t + ih} stroke="#334155" />
        {band && <path d={band} fill={C.fp} opacity={0.2} />}
        <path d={series("obs", 0, BACK)} fill="none" stroke={C.obs} strokeWidth={2} />
        {/* what the river actually did after NOW: faint, for comparison */}
        <path d={series("obs", BACK, model.rows.length - 1)} fill="none" stroke={C.obs} strokeWidth={1.5} opacity={0.35} />
        <path d={series("base", BACK + 1, BACK + horizon, true)} fill="none" stroke={C.base} strokeWidth={2.5} strokeDasharray="1 5" strokeLinecap="round" />
        <path d={series("fp", BACK + 1, BACK + horizon, true)} fill="none" stroke={C.fp} strokeWidth={2.5} />
        {!model.hasFc && <text x={x(BACK) + 10} y={M.t + 16} fontSize={12} fill={C.axis}>no forecast at this time (gauge data gap)</text>}
      </svg>
    </div>
  );
}
