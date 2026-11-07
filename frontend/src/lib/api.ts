import type { BacktestResponse, StudyResponse, Infrastructure, SpatialFrame, StatusResponse, TimelineResponse } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { signal });
  if (!res.ok) throw new Error(`${path} → HTTP ${res.status}`);
  return (await res.json()) as T;
}

export const api = {
  status: () => get<StatusResponse>("/api/status"),
  timeline: () => get<TimelineResponse>("/api/timeline"),
  backtest: () => get<BacktestResponse>("/api/backtest"),
  evaluation: () => get<StudyResponse>("/api/evaluation"),
  infrastructure: () => get<Infrastructure>("/api/infrastructure"),
  frame: (ts: string, signal?: AbortSignal) =>
    get<SpatialFrame>(`/api/spatial-frame?timestamp=${encodeURIComponent(ts)}`, signal),
};
