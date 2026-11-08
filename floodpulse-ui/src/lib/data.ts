import type { GaugeFile, Geometry, Manifest, SetName, StatusFile, Variant } from "./types";

const cache = new Map<string, Promise<unknown>>();
function load<T>(file: string): Promise<T> {
  if (!cache.has(file)) {
    cache.set(file, fetch(`${import.meta.env.BASE_URL}data/${file}`).then((r) => {
      if (!r.ok) throw new Error(`${file}: HTTP ${r.status} — run \`npm run data\``);
      return r.json();
    }));
  }
  return cache.get(file) as Promise<T>;
}

export const data = {
  manifest: () => load<Manifest>("manifest.json"),
  status: (s: SetName, v: Variant) => load<StatusFile>(`status_${s}_${v}.json`),
  gauge: (slug: string) => load<GaugeFile>(`gauge_${slug}.json`),
  geometry: (slug: string) => load<Geometry>(`geometry_${slug}.json`).catch(() => null),
};

export const HOUR = 3_600_000;
export const m = (mmv: number | null | undefined, d = 2) => (mmv == null ? "—" : (mmv / 1000).toFixed(d));
export const pct = (x: number | null | undefined, d = 0) => (x == null ? "—" : `${(x * 100).toFixed(d)}%`);
export const fmtTime = (iso: string) => new Date(iso).toISOString().replace("T", " ").slice(0, 16) + "Z";
