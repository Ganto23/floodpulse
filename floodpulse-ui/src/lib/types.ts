// Shapes produced by eval_harness/export_dashboard.py. Levels are integer millimetres.

export type SetName = "2024" | "ciara_dennis" | "babet";
export type Variant = "deployed" | "oracle" | "past";
export type Horizon = 6 | 12 | 18 | 24;
export type Risk = "crit" | "warn" | "ok" | "none";

export interface WarningStats {
  hit_rate: number | null;
  mean_lead_h: number | null;
  mean_lead_h_given_hit?: number | null;
  leads_h?: number[];
  warnings?: number;
  false_alarm_ratio?: number | null;
  far?: number | null;
}

export interface GaugeMeta {
  slug: string;
  name: string;
  river: string;
  lat: number;
  lon: number;
  p95_mm: number;
  p99_mm: number;
  dem_tc_h: number;
  empirical_lag_h: number;
  dem_area_km2: number;
  nrfa_area_km2: number | null;
  dem_unreliable: boolean;
  phase1: Record<"6" | "12" | "24", { day1: number; day2: number | null }> | null;
  sets: Partial<Record<SetName, Partial<Record<Variant, {
    mae_mm: Record<"persistence" | "timesfm" | "booster", number>;
    surge_mae_mm: Record<"persistence" | "timesfm" | "booster", number | null>;
    warning: Record<"timesfm" | "booster", WarningStats>;
    events: number;
  }>>>>;
}

export interface Manifest {
  generated: string;
  mode: string;
  sets: Record<SetName, { label: string; variants: Variant[] }>;
  variant_labels: Record<Variant, string>;
  headline: {
    error_reduction_day1: Record<"6" | "12" | "24", number>;
    error_reduction_day2: Record<"6" | "12" | "24", number>;
    booster_deployed: { n: number; mae_red_vs_timesfm_median: number; mae_red_vs_persistence_median: number; surge_mae_red_vs_timesfm_median: number };
    warnings_2024_deployed: { events: number; booster: WarningStats; timesfm: WarningStats };
    warnings_2024_oracle: { events: number; booster: WarningStats; timesfm: WarningStats };
    warnings_ciara_oracle: { events: number; booster: WarningStats } | null;
    warnings_babet_oracle: { events: number; booster: WarningStats } | null;
    dem_lag: { spearman: number; spearman_p: number; n: number; mae_h: number };
    storms: Record<string, Record<string, { capture_6h: number | null; capture_12h: number | null; n_12h: number; median_peak_err_pct: number | null }>>;
    gauges_phase1: number;
  };
  gauges: GaugeMeta[];
}

export interface StatusCell {
  obs: number | null;
  peak: Record<"6" | "12" | "18" | "24", number | null>;
  breach_h: number | null;
}
export interface StatusFile {
  times: string[];
  rows: Record<string, StatusCell>[];
}

export interface VariantForecasts {
  origins: string[];
  baseline: (number | null)[][];
  floodpulse: (number | null)[][];
  band_lo: (number | null)[][];
  band_hi: (number | null)[][];
}
export interface GaugeFile {
  slug: string;
  sets: Partial<Record<SetName, { obs_start: string; obs: (number | null)[]; variants: Partial<Record<Variant, VariantForecasts>> }>>;
}

export interface Geometry {
  cell_deg: [number, number];
  outlet: [number, number];
  cells: [number, number, number][];          // lon, lat, elevation m
  channels: [number, number, number, number, number][]; // lon0, lat0, lon1, lat1, log10(area km²)
}
