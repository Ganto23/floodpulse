import { useEffect, useMemo, useRef, useState } from "react";
import { HOUR } from "../lib/data";
import type { GaugeFile, GaugeMeta, Horizon } from "../lib/types";
import { displayName } from "./names";

const HORIZONS: Horizon[] = [6, 12, 24];
const BACK = 72;                                                   // hours of history left of NOW
// validate_palette.js --mode dark --surface #1a1d23: all checks pass
const C = { obs: "#5687cf", base: "#c46e3a", fp: "#22a07f", grid: "#2c313a", axis: "#7c828d", label: "#aeb2ba" };
const parse = (s: string) => new Date(s.replace(" ", "T")).getTime();

/** FORECAST ENVELOPE: observed river level, historical-base forecast, FloodPulse forecast. Nothing else. */
export default function ForecastPanel({ gauge, file, time, horizon, onHorizon }: {
  gauge: GaugeMeta | null; file: GaugeFile | null; time: string | null; horizon: Horizon; onHorizon: (h: Horizon) => void;
}) {
  return (
    <div className="flex h-full flex-col bg-panel">
      <div className="flex items-center gap-4 border-b border-line px-4 py-2">
        <span className="text-[11px] tracking-[0.2em] text-dim">FORECAST ENVELOPE:</span>
        <span className="text-[13px] text-ink">{gauge ? displayName(gauge.slug, gauge.name) : ""}</span>
        <span className="ml-auto flex gap-1">
          {HORIZONS.map((h) => (
            <button key={h} onClick={() => onHorizon(h)}
                    className={`border px-2 py-0.5 text-[11px] ${h === horizon ? "border-dim text-ink" : "border-line text-dim hover:text-ink"}`}>
              +{h}h
            </button>
          ))}
        </span>
      </div>
      <div className="min-h-0 flex-1">
        {gauge && file && time ? <Chart file={file} time={time} horizon={horizon} /> : null}
      </div>
    </div>
  );
}

function Chart({ file, time, horizon }: { file: GaugeFile; time: string; horizon: Horizon }) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 220 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const set = file.sets["2024"];
  const fc = set?.variants.deployed;
  const model = useMemo(() => {
    if (!set || !fc) return null;
    const t0 = parse(time), obsStart = parse(set.obs_start);
    const k = fc.origins.indexOf(time);
    const rows = Array.from({ length: BACK + 25 }, (_, i) => {
      const step = i - BACK;
      const obs = set.obs[Math.round((t0 + step * HOUR - obsStart) / HOUR)] ?? null;
      const at = (arr: (number | null)[][]) => (k >= 0 && step >= 1 && step <= horizon ? arr[k]?.[step - 1] ?? null : null);
      return { step, obs, base: at(fc.baseline), fp: at(fc.floodpulse) };
    });
    const vals = rows.flatMap((r) => [r.obs, r.base, r.fp]).filter((v): v is number => v != null);
    const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.1 || 50;
    return { rows, ymin: lo - pad, ymax: hi + pad };
  }, [set, fc, time, horizon]);

  if (!model) return <div ref={ref} className="h-full" />;

  const M = { l: 56, r: 130, t: 16, b: 24 };
  const W = Math.max(size.w, 300), H = Math.max(size.h, 120);
  const iw = W - M.l - M.r, ih = H - M.t - M.b;
  const x = (i: number) => M.l + (i / (model.rows.length - 1)) * iw;
  const y = (v: number) => M.t + (1 - (v - model.ymin) / (model.ymax - model.ymin)) * ih;
  const path = (key: "obs" | "base" | "fp", from: number, to: number) => {
    let d = "", pen = false;
    for (let i = from; i <= to; i++) {
      const v = model.rows[i][key];
      if (v == null) { pen = false; continue; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true;
    }
    return d;
  };
  // forecasts are drawn from the river level at NOW, so they visibly start where the river was
  const nowObs = model.rows[BACK].obs;
  const fcPath = (key: "base" | "fp") => (nowObs == null ? "" : `M${x(BACK)},${y(nowObs)}`) + path(key, BACK + 1, BACK + horizon).replace(/^M/, "L");
  const end = (key: "base" | "fp") => model.rows[BACK + horizon][key];
  const ticks = [0, 1, 2].map((i) => model.ymin + ((model.ymax - model.ymin) * (i + 0.5)) / 3);

  // right-edge labels, nudged apart so they never overlap
  const labels = [{ k: "fp", text: "FloodPulse", v: end("fp"), c: C.fp }, { k: "base", text: "Historical base", v: end("base"), c: C.base }]
    .filter((l) => l.v != null).map((l) => ({ ...l, ly: y(l.v as number) })).sort((a, b) => a.ly - b.ly);
  for (let i = 1; i < labels.length; i++) labels[i].ly = Math.max(labels[i].ly, labels[i - 1].ly + 14);

  return (
    <div ref={ref} className="relative h-full w-full">
      <svg width={W} height={H} role="img" aria-label="Observed river level, historical base forecast and FloodPulse forecast">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={M.l} x2={M.l + iw} y1={y(v)} y2={y(v)} stroke={C.grid} />
            <text x={M.l - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill={C.axis}>{(v / 1000).toFixed(2)}m</text>
          </g>
        ))}
        {[-72, -24, 0, 12, 24].map((s) => (
          <text key={s} x={x(s + BACK)} y={H - 6} textAnchor="middle" fontSize={11} fill={s === 0 ? C.label : C.axis}>
            {s === 0 ? "NOW" : `${s > 0 ? "+" : ""}${s}h`}
          </text>
        ))}
        <rect x={x(BACK)} y={M.t} width={x(BACK + horizon) - x(BACK)} height={ih} fill="#ffffff" opacity={0.025} />
        <line x1={x(BACK)} x2={x(BACK)} y1={M.t} y2={M.t + ih} stroke={C.axis} strokeDasharray="2 3" />
        {/* observed: solid up to NOW, faint afterwards (what the river then actually did) */}
        <path d={path("obs", 0, BACK)} fill="none" stroke={C.obs} strokeWidth={2.5} />
        <path d={path("obs", BACK, model.rows.length - 1)} fill="none" stroke={C.obs} strokeWidth={2} opacity={0.45} />
        <path d={fcPath("base")} fill="none" stroke={C.base} strokeWidth={2} strokeDasharray="6 4" />
        <path d={fcPath("fp")} fill="none" stroke={C.fp} strokeWidth={2.5} />
        {labels.map((l) => (
          <g key={l.k}>
            <line x1={M.l + iw + 6} x2={M.l + iw + 18} y1={l.ly} y2={l.ly} stroke={l.c} strokeWidth={2.5} strokeDasharray={l.k === "base" ? "4 3" : undefined} />
            <text x={M.l + iw + 24} y={l.ly + 4} fontSize={11} fill={C.label}>{l.text}</text>
          </g>
        ))}
        <text x={x(BACK) - 8} y={M.t + 12} textAnchor="end" fontSize={11} fill={C.label}>Observed</text>
      </svg>
    </div>
  );
}
