import { useEffect, useMemo, useState } from "react";
import { data, pct } from "../lib/data";
import { riskOf } from "../lib/risk";
import type { GaugeFile, Geometry, Horizon, Manifest, Risk, StatusFile } from "../lib/types";
import BasinSidebar from "./BasinSidebar";
import BasinMap from "./BasinMap";
import ForecastPanel from "./ForecastPanel";

/**
 * FloodPulse: Historical Backtest Replay Engine (2024).
 *
 * Replays REAL held-out 2024 model output, using rain forecasts exactly as they were issued.
 * Data: public/data/*.json from eval_harness/floodpulse_stress.py → export_dashboard.py
 *   manifest.json                 gauges, thresholds, audited headline metrics
 *   status_2024_deployed.json     per replay time × gauge: current level, predicted peak, hours to alert line
 *   gauge_<slug>.json             observed levels + baseline / FloodPulse trajectories + band
 *   geometry_<slug>.json          river channels traced from terrain
 * No live feed and no synthetic data.
 */
const START = "2024-12-04 18:00:00+00:00";      // opens on a real moment: Calder normal now, alert line crossed ~23 h later
const PLAY_MS = 1000;                           // one 3-hour step per second
const TIER: Record<Risk, number> = { crit: 0, warn: 1, ok: 2, none: 3 };

export default function FloodPulseDashboard() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [status, setStatus] = useState<StatusFile | null>(null);
  const [geometry, setGeometry] = useState<Record<string, Geometry>>({});
  const [selected, setSelected] = useState("calder_mytholmroyd");
  const [gaugeFile, setGaugeFile] = useState<GaugeFile | null>(null);
  const [horizon, setHorizon] = useState<Horizon>(24);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    data.manifest().then((mf) => {
      setManifest(mf);
      Promise.all(mf.gauges.map((g) => data.geometry(g.slug).then((geo) => [g.slug, geo] as const)))
        .then((pairs) => setGeometry(Object.fromEntries(pairs.filter(([, geo]) => geo)) as Record<string, Geometry>));
    }).catch((e) => setErr(String(e)));
    data.status("2024", "deployed").then((s) => { setStatus(s); setT(Math.max(0, s.times.indexOf(START))); })
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    data.gauge(selected).then(setGaugeFile).catch((e) => setErr(String(e)));
  }, [selected]);

  useEffect(() => {
    if (!playing || !status) return;
    const id = setInterval(() => setT((x) => (x + 1) % status.times.length), PLAY_MS);
    return () => clearInterval(id);
  }, [playing, status]);

  const time = status?.times[t] ?? null;
  const row = status?.rows[t];
  // most at risk first; stable order within each status so cards don't jump around during playback
  const ranked = useMemo(() => !manifest ? [] : manifest.gauges
    .filter((g) => g.sets["2024"])
    .map((g, order) => ({ g, order, ...riskOf(g, row?.[g.slug], horizon) }))
    .sort((a, b) => TIER[a.risk] - TIER[b.risk] || a.order - b.order), [manifest, row, horizon]);

  if (err) return <div className="flex h-full items-center justify-center text-crit">{err}</div>;
  if (!manifest || !status) return <div className="h-full bg-slate-900" />;

  const h = manifest.headline;
  const lo = Math.min(...Object.values(h.error_reduction_day2));
  const hi = Math.max(...Object.values(h.error_reduction_day1));
  const gaugeMeta = manifest.gauges.find((g) => g.slug === selected) ?? null;

  return (
    <div className="grid h-full grid-cols-[340px_1fr] grid-rows-[60px_1fr_300px] bg-slate-900 text-slate-200">
      <header className="col-span-full flex items-center gap-6 border-b border-slate-800 px-6">
        <div>
          <div className="font-mono text-[15px] font-medium tracking-[0.2em] text-slate-100">
            FLOODPULSE <span className="text-slate-600">//</span> <span className="text-slate-400">HISTORICAL BACKTEST REPLAY</span>
          </div>
          <div className="text-[11px] text-slate-500">Historical Backtest Replay Engine (2024) · not live monitoring</div>
        </div>
        <div className="ml-auto rounded-lg border border-slate-800 bg-slate-800/40 px-4 py-2 text-[13px] text-slate-300">
          Error Reduction: <span className="font-mono font-medium text-s-fp">−{pct(lo)} to −{pct(hi)}</span> vs. Baseline across {h.gauges_phase1} Gauges
        </div>
      </header>

      <aside className="min-h-0 border-r border-slate-800">
        <BasinSidebar ranked={ranked} selected={selected} onSelect={setSelected} />
      </aside>

      <main className="relative min-h-0">
        <BasinMap gauges={ranked} geometry={geometry} selected={selected} onSelect={setSelected} />
      </main>

      <section className="col-span-full min-h-0 border-t border-slate-800">
        <ForecastPanel gauge={gaugeMeta} file={gaugeFile?.slug === selected ? gaugeFile : null} time={time}
                       horizon={horizon} onHorizon={setHorizon}
                       times={status.times} t={t} onT={(i) => { setPlaying(false); setT(i); }}
                       playing={playing} onPlay={() => setPlaying((p) => !p)} />
      </section>
    </div>
  );
}
