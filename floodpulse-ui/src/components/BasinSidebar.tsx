import { AlertOctagon, AlertTriangle, Check, CircleDashed } from "lucide-react";
import { m } from "../lib/data";
import type { RiskRow } from "../lib/risk";
import type { GaugeMeta } from "../lib/types";
import { displayName } from "./names";

type Row = RiskRow & { g: GaugeMeta };
const STATE = {
  crit: { Icon: AlertOctagon, cls: "text-crit" },
  warn: { Icon: AlertTriangle, cls: "text-warn" },
  ok: { Icon: Check, cls: "text-ok" },
  none: { Icon: CircleDashed, cls: "text-dim" },
} as const;

/** ACTIVE GAUGES: name, then "now → forecast max (alert in N h)". */
export default function BasinSidebar({ ranked, selected, onSelect }: {
  ranked: Row[]; selected: string | null; onSelect: (s: string) => void;
}) {
  return (
    <div className="flex h-full flex-col bg-panel">
      <div className="border-b border-line px-4 py-3 text-[11px] tracking-[0.2em] text-dim">ACTIVE GAUGES</div>
      <ol className="thin-scroll flex-1 overflow-y-auto">
        {ranked.map(({ g, risk, obs, peak, breach }) => {
          const { Icon, cls } = STATE[risk];
          return (
            <li key={g.slug}>
              <button onClick={() => onSelect(g.slug)}
                      className={`flex w-full items-start gap-3 border-b border-line/60 px-4 py-3 text-left hover:bg-line/40 ${selected === g.slug ? "bg-line/50" : ""}`}>
                <Icon size={14} className={`mt-0.5 shrink-0 ${cls}`} aria-label={risk} />
                <span className="min-w-0">
                  <span className="block truncate text-[12px] text-ink">{displayName(g.slug, g.name)}</span>
                  <span className="mt-1 block tabular-nums text-[12px] text-dim">
                    {m(obs)}m → <span className="text-ink">{m(peak)}m</span>
                    {breach != null && <span className={`ml-2 ${cls}`}>(+{breach}h)</span>}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
