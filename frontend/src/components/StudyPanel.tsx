import { ShieldCheck } from "lucide-react";
import type { StudyResponse } from "../lib/types";

const n = (v: number | null | undefined, d = 2) => (v == null ? "—" : v.toFixed(d));
const MODELS: [string, string][] = [["urbanpulse", "URBANPULSE"], ["no_denoise", "NO DENOISE"], ["persistence", "PERSIST"], ["hist_mean", "HIST MEAN"]];
const FEAT: Record<string, string> = { transit_proximity: "transit nodes", pedestrian_m: "pedestrian network", buildings: "buildings" };

export default function StudyPanel({ data }: { data: StudyResponse | null }) {
  const body = (() => {
    if (!data || data.status === "pending" || data.status === "running")
      return <div className="text-term-dim blink">▸ running dev → holdout study…</div>;
    if (data.status === "error" || !data.result) return <div className="text-term-red">study failed: {data.error}</div>;
    const r = data.result;
    const { forecast: f, spatial_persistence: sp, osm } = r.holdout;
    return (
      <>
        <div className="text-[10px] leading-4 text-term-dim">
          holdout = final {r.protocol.holdout_hours} h, untouched during selection. Scale chosen on dev:
          <span className="text-term-text"> H3 res {r.selected.res} · {r.selected.window_min / 60} h window</span> ({r.selected.label}, {r.selected.cells} zones)
        </div>

        <div className="text-[10px] font-bold text-term-cyan">A · FORECAST (holdout, {f.windows} windows)</div>
        <table className="w-full text-[10px] tabular-nums">
          <thead><tr className="text-term-dim"><th className="text-left font-normal">MODEL</th><th className="text-right font-normal" title="Pearson on log1p">r(log)↑</th><th className="text-right font-normal" title="Spearman over cells seen in training">ρ↑</th><th className="text-right font-normal">WAPE↓</th></tr></thead>
          <tbody>
            {MODELS.filter(([m]) => f.summary[m]).map(([m, label]) => (
              <tr key={m} className={m === "urbanpulse" ? "text-term-amber" : ""}>
                <td>{label}</td><td className="text-right">{n(f.summary[m].pearson_log)}</td>
                <td className="text-right">{n(f.summary[m].spearman_active)}</td><td className="text-right">{n(f.summary[m].wape)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="text-[10px] font-bold text-term-cyan">B · SPATIAL PERSISTENCE (dev → holdout)</div>
        <div className="grid grid-cols-3 gap-1 text-[10px]">
          <Stat k="r(log)" v={n(sp.pearson_log)} /><Stat k="ρ" v={n(sp.spearman_active)} /><Stat k="top-10% kept" v={sp.top_decile_retention == null ? "—" : `${Math.round(sp.top_decile_retention * 100)}%`} />
        </div>

        <div className="text-[10px] font-bold text-term-cyan">C · OSM INFRASTRUCTURE → ACTIVITY</div>
        {osm.available ? (
          <>
            <table className="w-full text-[10px] tabular-nums">
              <thead><tr className="text-term-dim"><th className="text-left font-normal">FEATURE (log)</th><th className="text-right font-normal">r dev</th><th className="text-right font-normal">r holdout</th></tr></thead>
              <tbody>
                {Object.entries(osm.per_feature).map(([k, v]) => (
                  <tr key={k}><td>{FEAT[k] ?? k}</td><td className="text-right">{n(v.pearson_dev)}</td><td className="text-right">{n(v.pearson_holdout)}</td></tr>
                ))}
              </tbody>
            </table>
            <div className="grid grid-cols-3 gap-1 text-[10px]">
              <Stat k="R² dev" v={n(osm.ols.r2_dev_in_sample)} /><Stat k={`R² block-CV`} v={n(osm.ols.r2_dev_spatial_block_cv)} /><Stat k="R² holdout" v={n(osm.ols.r2_holdout)} />
            </div>
            <div className="text-[10px] text-term-dim">{osm.covered_cells}/{osm.total_cells} zones fully inside OSM coverage</div>
          </>
        ) : <div className="text-[10px] text-term-dim">unavailable: {osm.reason}</div>}
      </>
    );
  })();
  return (
    <section className="border border-term-line bg-term-panel p-2.5">
      <h2 className="mb-2 flex items-center gap-1.5 text-[10px] font-bold tracking-[0.2em] text-term-amber"><ShieldCheck size={12} /> HOLDOUT CORRELATION STUDY</h2>
      <div className="flex flex-col gap-2">{body}</div>
    </section>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return <div className="border border-term-line px-1.5 py-1"><div className="text-term-dim">{k}</div><div className="text-sm font-bold">{v}</div></div>;
}
