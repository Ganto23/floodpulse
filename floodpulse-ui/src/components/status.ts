import type { RiskRow } from "../lib/risk";
import type { GaugeMeta } from "../lib/types";

export type Row = RiskRow & { g: GaugeMeta };

/** Status badge for a gauge at the replay time. Alert = FloodPulse forecasts the P99 alert threshold within the horizon. */
export function statusBadge({ risk, obs, breach, g }: Row, long = false) {
  const red = { cls: "bg-crit/20 text-red-200 ring-crit/60", dot: "bg-crit flood-dot" };
  if (risk === "crit" && obs != null && obs >= g.p99_mm) return { text: "ABOVE FLOOD ALERT", ...red };
  if (risk === "crit") return { text: `FLOOD ALERT IN +${breach}H`, ...red };
  const tail = long ? " (No Breach Predicted)" : "";
  if (risk === "warn") return { text: `WATCH${tail}`, cls: "bg-warn/15 text-amber-200 ring-warn/50", dot: "bg-warn" };
  if (risk === "ok") return { text: `NORMAL${tail}`, cls: "bg-ok/10 text-green-200 ring-ok/40", dot: "bg-ok" };
  return { text: "NO DATA", cls: "bg-slate-800 text-slate-400 ring-slate-700", dot: "bg-slate-500" };
}
