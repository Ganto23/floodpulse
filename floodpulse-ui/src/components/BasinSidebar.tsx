import { m } from "../lib/data";
import type { RiskRow } from "../lib/risk";
import type { GaugeMeta } from "../lib/types";
import { nameParts } from "./names";

type Row = RiskRow & { g: GaugeMeta };

/** Badge text + style. Alert = FloodPulse forecasts the gauge's flood alert threshold (P99) within the horizon. */
function badge({ risk, obs, breach, g }: Row) {
  if (risk === "crit" && obs != null && obs >= g.p99_mm)
    return { text: "ABOVE FLOOD ALERT", cls: "bg-crit/20 text-red-200 ring-crit/60", dot: "bg-crit flood-dot" };
  if (risk === "crit") return { text: `FLOOD ALERT IN +${breach}H`, cls: "bg-crit/20 text-red-200 ring-crit/60", dot: "bg-crit flood-dot" };
  if (risk === "warn") return { text: "WATCH", cls: "bg-warn/15 text-amber-200 ring-warn/50", dot: "bg-warn" };
  if (risk === "ok") return { text: "NORMAL", cls: "bg-ok/10 text-green-200 ring-ok/40", dot: "bg-ok" };
  return { text: "NO DATA", cls: "bg-slate-800 text-slate-400 ring-slate-700", dot: "bg-slate-500" };
}

/** Active Gauge Telemetry: name, status, and current / peak levels in the context of the flood alert threshold. */
export default function BasinSidebar({ ranked, selected, onSelect }: {
  ranked: Row[]; selected: string | null; onSelect: (s: string) => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <h2 className="px-5 pb-3 pt-5 text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">Active Gauge Telemetry</h2>
      <ol className="thin-scroll flex-1 space-y-2.5 overflow-y-auto px-4 pb-4">
        {ranked.map((r) => {
          const { g, obs, peak } = r;
          const [river, place] = nameParts(g.slug, g.name);
          const b = badge(r);
          const active = selected === g.slug;
          const over = peak != null && peak >= g.p99_mm;
          return (
            <li key={g.slug}>
              <button onClick={() => onSelect(g.slug)}
                      className={`w-full rounded-lg border px-4 py-3 text-left transition-colors ${active ? "border-s-fp/50 bg-slate-800/80" : "border-slate-800 bg-slate-800/30 hover:bg-slate-800/60"}`}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-[14px] font-medium text-slate-100">{river}</span>
                  <span className="truncate text-[11px] text-slate-500">{place}</span>
                </div>
                <span className={`mt-2 inline-flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[11px] font-semibold ring-1 ${b.cls}`}>
                  <span className={`h-2 w-2 rounded-full ${b.dot}`} />{b.text}
                </span>
                <div className="mt-2 font-mono text-[13px] tabular-nums text-slate-300">
                  Current: <span className="text-slate-100">{m(obs)}m</span>
                  <span className="mx-1.5 text-slate-600">|</span>
                  Peak: <span className={over ? "font-semibold text-crit" : "text-slate-100"}>{m(peak)}m</span>
                </div>
                <div className="font-mono text-[11px] text-slate-500">Flood alert threshold: {m(g.p99_mm)}m</div>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
