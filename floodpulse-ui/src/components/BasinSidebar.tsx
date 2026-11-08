import { AlertOctagon, AlertTriangle, CheckCircle2, CircleDashed } from "lucide-react";
import { m } from "../lib/data";
import { RISK_STYLE, type RiskRow } from "../lib/risk";
import type { GaugeMeta, Horizon } from "../lib/types";

const ICON = { crit: AlertOctagon, warn: AlertTriangle, ok: CheckCircle2, none: CircleDashed };

type Row = RiskRow & { g: GaugeMeta };

export default function BasinSidebar({ ranked, selected, onSelect, horizon, time }: {
  ranked: Row[]; selected: string | null; onSelect: (s: string) => void; horizon: Horizon; time: string;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-zinc-800 px-3 py-2">
        <div className="text-[10px] font-bold tracking-[0.2em] text-accent">RIVERS · CLICK ONE TO SEE ITS FORECAST</div>
        <div className="mt-0.5 text-[10px] text-zinc-500">{time} · looking {horizon} h ahead · most at risk first</div>
      </div>
      <div className="grid grid-cols-[1fr_52px_52px_44px] gap-x-2 border-b border-zinc-900 px-3 py-1 text-[9px] tracking-widest text-zinc-500">
        <span>RIVER GAUGE</span><span className="text-right">NOW m</span><span className="text-right">MAX m</span><span className="text-right">ALERT IN</span>
      </div>
      <ol className="thin-scroll flex-1 overflow-y-auto">
        {ranked.map(({ g, risk, obs, peak, breach }) => {
          const st = RISK_STYLE[risk];
          const Icon = ICON[risk];
          return (
            <li key={g.slug}>
              <button onClick={() => onSelect(g.slug)}
                      className={`grid w-full grid-cols-[1fr_52px_52px_44px] items-center gap-x-2 border-b border-zinc-900 px-3 py-2 text-left hover:bg-zinc-900 ${selected === g.slug ? "bg-zinc-900 shadow-[inset_2px_0_0_#22d3ee]" : ""}`}>
                <span className="min-w-0">
                  <span className="block truncate text-[11px] text-zinc-100">{g.name}</span>
                  <span className={`flex items-center gap-1 text-[9px] font-bold ${st.text}`}><Icon size={10} /> {st.label}</span>
                </span>
                <span className="text-right tabular-nums text-zinc-200">{m(obs)}</span>
                <span className="text-right tabular-nums text-zinc-200">{m(peak)}</span>
                <span className={`text-right tabular-nums ${breach ? "font-bold text-crit" : "text-zinc-600"}`}>{breach ? `+${breach}h` : "—"}</span>
              </button>
            </li>
          );
        })}
      </ol>
      <div className="border-t border-zinc-800 px-3 py-2 text-[9px] leading-4 text-zinc-500">
        <b className="text-zinc-400">ALERT</b> = FloodPulse expects the river to pass its alert line (the level it
        only exceeds 1% of the time; our proxy, not an official EA flood warning). <b className="text-zinc-400">WATCH</b> =
        above the 5% line. NOW = measured level; MAX = highest forecast level ahead.
      </div>
    </div>
  );
}

