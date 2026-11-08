import { m } from "../lib/data";
import type { Horizon } from "../lib/types";
import { nameParts } from "./names";
import { statusBadge, type Row } from "./status";

/** Telemetry spotlight for the selected gauge, floating over the map. Re-keyed on selection so it flashes on change. */
export default function GaugeHUD({ row, horizon }: { row: Row | undefined; horizon: Horizon }) {
  if (!row) return null;
  const { g, obs, peak } = row;
  const [river, place] = nameParts(g.slug, g.name);
  const b = statusBadge(row, true);
  const over = peak != null && peak >= g.p99_mm;
  return (
    <div key={g.slug} className="hud-flash pointer-events-none absolute left-4 top-4 z-10 w-[340px] rounded-xl border border-slate-700 bg-slate-900/92 p-4 shadow-2xl backdrop-blur">
      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">Selected gauge</div>
      <div className="mt-1 text-[22px] font-semibold leading-tight text-slate-50">{place || river}</div>
      <div className="text-[13px] text-slate-400">{place ? river : ""}</div>
      <div className="mt-3 grid grid-cols-3 gap-3">
        <Metric k="Current" v={m(obs)} />
        <Metric k={`Peak (+${horizon}h)`} v={m(peak)} accent={over ? "text-crit" : undefined} />
        <Metric k="P99 alert" v={m(g.p99_mm)} accent="text-red-300/80" />
      </div>
      <span className={`mt-3 inline-flex items-center gap-2 rounded-md px-2.5 py-1 font-mono text-[12px] font-semibold ring-1 ${b.cls}`}>
        <span className={`h-2.5 w-2.5 rounded-full ${b.dot}`} />{b.text}
      </span>
    </div>
  );
}

function Metric({ k, v, accent }: { k: string; v: string; accent?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{k}</div>
      <div className={`font-mono text-[22px] font-semibold tabular-nums ${accent ?? "text-slate-100"}`}>{v}<span className="ml-0.5 text-[13px] font-normal text-slate-500">m</span></div>
    </div>
  );
}
