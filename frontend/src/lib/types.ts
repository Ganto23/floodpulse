// Mirrors backend/schemas.py — keep in sync.

export type SourceState = "ONLINE" | "DEGRADED" | "OFFLINE" | "LOADING";
export type FrameKind = "historical" | "forecast";
export type Regime = "nowcast" | "longrange";
export type SignalType = "VELOCITY_SURGE" | "MOMENTUM_DECAY" | "ANOMALY" | "DISPATCH";

export interface SourceStatus {
  key: string;
  label: string;
  state: SourceState;
  detail: string;
  metrics: Record<string, unknown>;
}

export interface ModeDescriptor {
  key: string;
  label: string;
  value_label: string;
  event_noun: string;
  highlight_label: string;
}

export interface TensorStats {
  shape: number[];
  freq: string;
  ranks: number[];
  activity_rel_error: number;
  temporal_explained: number[];
  horizon_steps: number;
  history: [string, string];
  notes: string[];
}

export interface StatusResponse {
  pipeline: "idle" | "loading" | "ready" | "error";
  stage: string;
  error: string | null;
  mode: ModeDescriptor;
  sources: SourceStatus[];
  tensor: Partial<Record<Regime, TensorStats>>;
  notes: string[];
  elapsed_s: number | null;
}

export interface TimelineFrame {
  timestamp: string;
  kind: FrameKind;
  regime: Regime;
}

export interface TimelineResponse {
  start: string;
  end: string;
  history_end: string;
  forecast_end: string;
  frames: TimelineFrame[];
  bbox: [number, number, number, number];
  center: [number, number];
}

export interface CellProperties {
  h3: string;
  realized: number | null;
  denoised: number | null;
  forecast: number | null;
  forecast_lo: number | null;
  forecast_hi: number | null;
  momentum: number;
  signal: SignalType | null;
}

export interface CellFeature {
  type: "Feature";
  geometry: { type: "Polygon"; coordinates: number[][][] };
  properties: CellProperties;
}

export interface Signal {
  id: string;
  type: SignalType;
  severity: "critical" | "high" | "medium";
  h3: string;
  latitude: number;
  longitude: number;
  z: number;
  message: string;
  action: string;
}

export interface MomentumVector {
  from: [number, number];
  to: [number, number];
  magnitude: number;
}

export interface Catchment {
  h3: string;
  type: string;
  rings: { k: number; walk_minutes: number; coordinates: number[][][][] }[];
}

export interface FrameMeta {
  timestamp: string;
  kind: FrameKind;
  regime: Regime;
  freq: string;
  horizon_label: string;
  value_label: string;
  momentum_unit: string;
  max_surface: number;
  weather: { temperature: number | null; precipitation: number | null; wind_speed: number | null } | null;
}

export interface SpatialFrame {
  type: "FeatureCollection";
  features: CellFeature[];
  meta: FrameMeta;
  highlights: { latitude: number; longitude: number; category: string; timestamp: string }[];
  vectors: MomentumVector[];
  catchments: Catchment[];
  signals: Signal[];
}

export interface Infrastructure {
  transit: { latitude: number; longitude: number; kind: string; name: string }[];
  paths: [number, number][][];
  source: string;
}

export type BacktestModel = "urbanpulse" | "no_denoise" | "persistence" | "hist_mean" | "seasonal" | "zero";

export interface BacktestMetrics {
  wape: number;
  share_err: number | null;
  mae: number | null;
  rmse: number | null;
  spearman: number | null;
  precision_k: number | null;
  volume_err: number | null;
  origins: number;
}

export interface BacktestResult {
  freq: string;
  horizon_steps: number;
  horizon_minutes: number;
  top_k: number;
  cells: number;
  origins: number;
  excluded_origins: number;
  min_window_events: number;
  window: [string, string];
  forecaster: string;
  labels: Record<BacktestModel, string>;
  summary: Partial<Record<BacktestModel, BacktestMetrics>>;
  skill: Record<string, number | null>;
  elapsed_s: number;
}

export interface BacktestResponse {
  status: "pending" | "running" | "ready" | "error";
  error: string | null;
  result: BacktestResult | null;
}
