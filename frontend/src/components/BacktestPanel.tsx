import { FlaskConical } from "lucide-react";
import type { BacktestMetrics, BacktestModel, BacktestResponse } from "../lib/types";

const ORDER: BacktestModel[] = ["urbanpulse", "no_denoise", "persistence", "hist_mean", "seasonal", "zero"];
const SHORT: Record<BacktestModel, string> = {
  urbanpulse: "URBANPULSE", no_denoise: "NO DENOISE", persistence: "PERSIST",
  hist_mean: "HIST MEAN", seasonal: "T−24H", zero: "ZERO",
};
type Col = { key: keyof BacktestMetrics; label: string; better: "low" | "high"; title: string };
const COLS: Col[] = [
  { key: "wape", label: "WAPE", better: "low", title: "Pooled Σ|err|/Σactual over cells × origins. Below 1.0 beats predicting zero." },
  { key: "share_err", label: "SHARE", better: "low", title: "Allocation error: distance between predicted and actual activity shares (0 = perfect). Ignores scan volume." },
  { key: "precision_k", label: "P@K", better: "high", title: "Share of predicted top-K cells that are actually top-K." },
];

const pct = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "−" : "+"}${Math.abs(v * 100).toFixed(0)}%`);

export default function BacktestPanel({ data }: { data: BacktestResponse | null }) {
  if (!data || data.status === "pending" || data.status === "running") {
    return <Shell><div className="text-term-dim blink">▸ running rolling-origin backtest…</div></Shell>;
  }
  if (data.status === "error" || !data.result) {
    return <Shell><div className="text-term-red">backtest failed: {data.error}</div></Shell>;
  }
  const r = data.result;
  const rows = ORDER.filter((m) => r.summary[m]);
  // best per column, excluding the zero floor (it isn't a forecaster)
  const best = Object.fromEntries(COLS.map((c) => {
    const vals = rows.filter((m) => m !== "zero").map((m) => [m, r.summary[m]![c.key] as number | null] as const)
      .filter(([, v]) => v != null) as [BacktestModel, number][];
    vals.sort((a, b) => (c.better === "low" ? a[1] - b[1] : b[1] - a[1]));
    return [c.key, vals[0]?.[0]];
  }));
  const s = r.skill;

  return (
    <Shell>
      <div className="text-[10px] leading-4 text-term-dim">
        {r.origins} out-of-sample origins · {r.horizon_minutes}-min horizon · {r.cells} cells · K={r.top_k}
        <br />refit on data before each origin · forecaster: <span className="text-term-text">{r.forecaster}</span>
      </div>
      <div className="grid grid-cols-2 gap-1 text-[10px]">
        <Kpi label="WAPE vs persistence" v={s.wape_vs_persistence} />
        <Kpi label="WAPE vs no-denoise" v={s.wape_vs_no_denoise} />
        <Kpi label="WAPE vs hist. mean" v={s.wape_vs_hist_mean} />
        <Kpi label="WAPE vs zero floor" v={s.wape_vs_zero} />
      </div>
      <table className="w-full text-[10px] tabular-nums">
        <thead>
          <tr className="text-term-dim">
            <th className="text-left font-normal">MODEL</th>
            {COLS.map((c) => <th key={c.key} className="text-right font-normal" title={c.title}>{c.label}{c.better === "low" ? "↓" : "↑"}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m} className={m === "urbanpulse" ? "text-term-amber" : m === "zero" ? "text-term-dim" : ""} title={r.labels[m]}>
              <td>{SHORT[m]}</td>
              {COLS.map((c) => {
                const v = r.summary[m]![c.key] as number | null;
                return (
                  <td key={c.key} className={`text-right ${best[c.key] === m ? "font-bold text-term-green" : ""}`}>
                    {v == null ? "—" : v.toFixed(3)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="text-[10px] leading-4 text-term-dim">
        › {r.excluded_origins} windows with &lt;{r.min_window_events} sightings excluded as scanner gaps.
        <br />› Green = best real forecaster per column. WAPE above 1.0 is worse than predicting zero — expected for sparse 15-min hex counts.
      </div>
    </Shell>
  );
}

function Kpi({ label, v }: { label: string; v: number | null | undefined }) {
  const good = v != null && v > 0;
  return (
    <div className="border border-term-line px-1.5 py-1">
      <div className="text-term-dim">{label}</div>
      <div className={`text-sm font-bold ${v == null ? "text-term-dim" : good ? "text-term-green" : "text-term-red"}`}>{pct(v)}</div>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <section className="border border-term-line bg-term-panel p-2.5">
      <h2 className="mb-2 flex items-center gap-1.5 text-[10px] font-bold tracking-[0.2em] text-term-amber">
        <FlaskConical size={12} /> OUT-OF-SAMPLE BACKTEST
      </h2>
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  );
}
