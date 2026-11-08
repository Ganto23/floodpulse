import { useEffect, useMemo, useState } from "react";
import { data } from "../lib/data";
import { riskOf } from "../lib/risk";
import type { GaugeFile, Geometry, Horizon, Manifest, Risk, StatusFile } from "../lib/types";
import BasinSidebar from "./BasinSidebar";
import BasinMap from "./BasinMap";
import ForecastPanel from "./ForecastPanel";

/**
 * FloodPulse. A replay of REAL held-out 2024 backtest output (eval_harness/floodpulse_stress.py →
 * export_dashboard.py), using rain forecasts exactly as they were issued. No live feed, no synthetic data.
 * Pinned to one real moment so the screen can be presented without anyone driving it.
 */
const MOMENT = "2024-12-04 18:00:00+00:00";
const TIER: Record<Risk, number> = { crit: 0, warn: 1, ok: 2, none: 3 };

export default function FloodPulseDashboard() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [status, setStatus] = useState<StatusFile | null>(null);
  const [geometry, setGeometry] = useState<Record<string, Geometry>>({});
  const [selected, setSelected] = useState("calder_mytholmroyd");
  const [gaugeFile, setGaugeFile] = useState<GaugeFile | null>(null);
  const [horizon, setHorizon] = useState<Horizon>(24);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    data.manifest().then((mf) => {
      setManifest(mf);
      Promise.all(mf.gauges.map((g) => data.geometry(g.slug).then((geo) => [g.slug, geo] as const)))
        .then((pairs) => setGeometry(Object.fromEntries(pairs.filter(([, geo]) => geo)) as Record<string, Geometry>));
    }).catch((e) => setErr(String(e)));
    data.status("2024", "deployed").then(setStatus).catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    setGaugeFile(null);
    data.gauge(selected).then(setGaugeFile).catch((e) => setErr(String(e)));
  }, [selected]);

  const row = status?.rows[status.times.indexOf(MOMENT)];
  const ranked = useMemo(() => !manifest ? [] : manifest.gauges
    .filter((g) => g.sets["2024"])
    .map((g, order) => ({ g, order, ...riskOf(g, row?.[g.slug], horizon) }))
    .sort((a, b) => TIER[a.risk] - TIER[b.risk] || a.order - b.order), [manifest, row, horizon]);

  if (err) return <div className="flex h-full items-center justify-center text-crit">{err}</div>;
  if (!manifest || !status) return <div className="h-full bg-bg" />;

  const cut = manifest.headline.booster_deployed.mae_red_vs_timesfm_median;
  const selectedMeta = manifest.gauges.find((g) => g.slug === selected) ?? null;

  return (
    <div className="grid h-full grid-cols-[320px_1fr] grid-rows-[48px_1fr_280px] bg-bg">
      <header className="col-span-full flex items-center gap-4 border-b border-line bg-panel px-5">
        <span className="text-[14px] font-bold tracking-[0.25em] text-ink">FLOODPULSE</span>
        <span className="text-dim">//</span>
        <span className="text-[12px] tracking-[0.15em] text-dim">BACKTEST REPLAY</span>
        <span className="ml-auto border border-line px-3 py-1 text-[12px] text-ink">
          <span className="text-s-fp">−{Math.round(cut * 100)}%</span> error vs baseline
        </span>
        <span className="border border-line px-3 py-1 text-[12px] text-dim">2024</span>
      </header>

      <aside className="min-h-0 border-r border-line">
        <BasinSidebar ranked={ranked} selected={selected} onSelect={setSelected} />
      </aside>

      <main className="relative min-h-0">
        <BasinMap gauges={ranked} geometry={geometry} selected={selectedMeta} onSelect={setSelected} />
      </main>

      <section className="col-span-full min-h-0 border-t border-line">
        <ForecastPanel gauge={selectedMeta} file={gaugeFile} time={MOMENT} horizon={horizon} onHorizon={setHorizon} />
      </section>
    </div>
  );
}
