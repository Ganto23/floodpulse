import { m } from "../lib/data";
import type { RiskRow } from "../lib/risk";
import type { GaugeMeta, Risk } from "../lib/types";
import { nameParts } from "./names";

type Row = RiskRow & { g: GaugeMeta };

const BADGE: Record<Risk, { label: string; cls: string }> = {
  crit: { label: "CRITICAL", cls: "bg-crit/10 text-crit ring-crit/30" },
  warn: { label: "WATCH", cls: "bg-warn/10 text-warn ring-warn/30" },
  ok: { label: "NORMAL", cls: "bg-ok/10 text-ok ring-ok/25" },
  none: { label: "NO DATA", cls: "bg-slate-800 text-slate-500 ring-slate-700" },
};

/** Active Gauge Telemetry: one card per gauge — name, current level, predicted peak, status. */
export default function BasinSidebar({ ranked, selected, onSelect }: {
  ranked: Row[]; selected: string | null; onSelect: (s: string) => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <h2 className="px-5 pb-3 pt-5 text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">Active Gauge Telemetry</h2>
      <ol className="thin-scroll flex-1 space-y-2.5 overflow-y-auto px-4 pb-4">
        {ranked.map(({ g, risk, obs, peak, breach }) => {
          const [river, place] = nameParts(g.slug, g.name);
          const b = BADGE[risk];
          const active = selected === g.slug;
          return (
            <li key={g.slug}>
              <button onClick={() => onSelect(g.slug)}
                      className={`w-full rounded-lg border px-4 py-3 text-left transition-colors ${active ? "border-s-fp/50 bg-slate-800/80" : "border-slate-800 bg-slate-800/30 hover:bg-slate-800/60"}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-[14px] font-medium text-slate-100">{river}</div>
                    <div className="truncate text-[12px] text-slate-500">{place}</div>
                  </div>
                  <span className={`shrink-0 rounded px-2 py-0.5 font-mono text-[10px] font-medium ring-1 ${b.cls}`}>
                    {risk === "crit" && breach != null ? `+${breach}h ` : ""}{b.label}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <Metric k="Current" v={`${m(obs)} m`} />
                  <Metric k="Predicted peak" v={`${m(peak)} m`} />
                </div>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Metric({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{k}</div>
      <div className="font-mono text-[15px] tabular-nums text-slate-200">{v}</div>
    </div>
  );
}
