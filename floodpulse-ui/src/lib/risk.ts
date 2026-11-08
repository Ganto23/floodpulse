import type { GaugeMeta, Horizon, Risk, StatusCell } from "./types";

/** Risk state from REAL backtest outputs at the replay time. Thresholds: training-period P95 / P99. */
export interface RiskRow { risk: Risk; obs: number | null; peak: number | null; breach: number | null; index: number }

export function riskOf(g: GaugeMeta, c: StatusCell | undefined, hz: Horizon): RiskRow {
  if (!c || c.obs == null) return { risk: "none", obs: null, peak: null, breach: null, index: -Infinity };
  const peak = c.peak[String(hz) as "6"] ?? null;
  const breach = c.breach_h != null && c.breach_h <= hz ? c.breach_h : null;
  const level = Math.max(c.obs, peak ?? -Infinity);
  const index = (level - g.p95_mm) / Math.max(g.p99_mm - g.p95_mm, 1);   // 0 = P95, 1 = P99
  let risk: Risk = "ok";
  if (c.obs >= g.p99_mm || breach != null) risk = "crit";
  else if (level >= g.p95_mm) risk = "warn";
  return { risk, obs: c.obs, peak, breach, index };
}

export const RISK_STYLE: Record<Risk, { label: string; text: string; dot: string; rgb: [number, number, number] }> = {
  crit: { label: "BREACH", text: "text-crit", dot: "bg-crit", rgb: [208, 59, 59] },
  warn: { label: "ELEVATED", text: "text-warn", dot: "bg-warn", rgb: [250, 178, 25] },
  ok: { label: "NORMAL", text: "text-ok", dot: "bg-ok", rgb: [12, 163, 12] },
  none: { label: "NO DATA", text: "text-zinc-500", dot: "bg-zinc-600", rgb: [82, 82, 91] },
};
