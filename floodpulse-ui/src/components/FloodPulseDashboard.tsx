import { useEffect, useMemo, useState } from "react";
import { Activity, ShieldAlert, Waves } from "lucide-react";
import { data, fmtTime, pct } from "../lib/data";
import { riskOf } from "../lib/risk";
import type { GaugeFile, Geometry, Horizon, Manifest, SetName, StatusFile, Variant } from "../lib/types";
import BasinSidebar from "./BasinSidebar";
import BasinMap from "./BasinMap";
import ForecastPanel from "./ForecastPanel";
import AuditPanel from "./AuditPanel";

/**
 * FloodPulse terminal. Everything rendered here is a REPLAY of real, held-out backtest output
 * (eval_harness/floodpulse_stress.py → export_dashboard.py). There is no live feed and no synthetic data.
 */
export default function FloodPulseDashboard() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [setName, setSetName] = useState<SetName>("2024");
  const [variant, setVariant] = useState<Variant>("deployed");
  const [status, setStatus] = useState<StatusFile | null>(null);
  const [t, setT] = useState(0);
  const [horizon, setHorizon] = useState<Horizon>(24);
  const [selected, setSelected] = useState<string | null>(null);
  const [gaugeFile, setGaugeFile] = useState<GaugeFile | null>(null);
  const [geometry, setGeometry] = useState<Record<string, Geometry>>({});
  const [mesh, setMesh] = useState(true);
  const [audit, setAudit] = useState(false);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    data.manifest().then((mf) => {
      setManifest(mf);
      Promise.all(mf.gauges.map((g) => data.geometry(g.slug).then((geo) => [g.slug, geo] as const)))
        .then((pairs) => setGeometry(Object.fromEntries(pairs.filter(([, geo]) => geo)) as Record<string, Geometry>));
    }).catch((e) => setErr(String(e)));
  }, []);

  // status file for the replay set/variant; open on the moment with the most predicted breaches
  useEffect(() => {
    if (!manifest) return;
    const allowed = manifest.sets[setName].variants;
    const v = allowed.includes(variant) ? variant : allowed[0];
    if (v !== variant) { setVariant(v); return; }
    data.status(setName, v).then((s) => {
      setStatus(s);
      let best = 0, bestScore = -Infinity;
      s.rows.forEach((row, i) => {
        const score = Object.values(row).filter((c) => c.breach_h != null).length;
        if (score > bestScore) { bestScore = score; best = i; }
      });
      setT(best);
    }).catch((e) => setErr(String(e)));
  }, [manifest, setName, variant]);

  useEffect(() => {
    if (!selected) return;
    setGaugeFile(null);
    data.gauge(selected).then(setGaugeFile).catch((e) => setErr(String(e)));
  }, [selected]);

  useEffect(() => {
    if (!playing || !status) return;
    const id = setInterval(() => setT((x) => (x + 1) % status.times.length), 250);
    return () => clearInterval(id);
  }, [playing, status]);

  const time = status?.times[t];
  const row = status?.rows[t];
  const ranked = useMemo(() => {
    if (!manifest) return [];
    return manifest.gauges
      .filter((g) => g.sets[setName])
      .map((g) => ({ g, ...riskOf(g, row?.[g.slug], horizon) }))
      .sort((a, b) => b.index - a.index);
  }, [manifest, row, horizon, setName]);

  useEffect(() => {
    if (ranked.length && (!selected || !ranked.some((r) => r.g.slug === selected))) setSelected(ranked[0].g.slug);
  }, [ranked, selected]);

  if (err) return <Center><span className="text-crit">{err}</span></Center>;
  if (!manifest || !status) return <Center><span className="blink text-zinc-500">loading backtest replay…</span></Center>;

  const h = manifest.headline;
  const w = h.warnings_2024_deployed;
  const selectedMeta = manifest.gauges.find((g) => g.slug === selected) ?? null;
  const counts = ranked.reduce((a, r) => ({ ...a, [r.risk]: (a[r.risk] ?? 0) + 1 }), {} as Record<string, number>);
  const rangeLo = Math.min(...Object.values(h.error_reduction_day2));
  const rangeHi = Math.max(...Object.values(h.error_reduction_day1));

  return (
    <div className="grid h-full grid-cols-[320px_1fr] grid-rows-[44px_1fr_300px] bg-zinc-950 max-lg:grid-cols-1 max-lg:grid-rows-[auto_50vh_auto_auto]">
      {/* ── top bar ─────────────────────────────────────────────── */}
      <header className="col-span-full flex items-center gap-5 overflow-x-auto border-b border-zinc-800 px-4 whitespace-nowrap">
        <span className="flex items-center gap-2 font-bold tracking-[0.25em] text-accent"><Waves size={16} /> FLOODPULSE</span>
        <span className="flex items-center gap-1.5 border border-warn/50 px-2 py-0.5 text-[10px] font-bold text-warn">
          <Activity size={11} /> BACKTEST REPLAY · {manifest.sets[setName].label.toUpperCase()}
        </span>
        <Stat k="GAUGES" v={`${ranked.length}`} />
        <Stat k="BREACH / ELEV / NORM" v={`${counts.crit ?? 0} / ${counts.warn ?? 0} / ${counts.ok ?? 0}`} />
        <Stat k="FORECAST ERROR vs RIVER-HISTORY BASELINE (6–24 h)" v={`−${pct(rangeLo)} to −${pct(rangeHi)}`} accent />
        <Stat k={`WARNINGS · REAL FORECASTS · ${w.events} EVENTS`} v={`${pct(w.booster.hit_rate)} caught · ${w.booster.mean_lead_h?.toFixed(1)} h lead`} />
        <button onClick={() => setAudit(true)}
                className="ml-auto flex items-center gap-1.5 border border-zinc-700 px-2 py-1 text-[10px] text-zinc-300 hover:border-accent hover:text-accent">
          <ShieldAlert size={12} /> MODEL AUDIT &amp; LIMITATIONS
        </button>
      </header>

      <aside className="row-span-2 min-h-0 border-r border-zinc-800 max-lg:row-span-1 max-lg:border-r-0">
        <BasinSidebar ranked={ranked} selected={selected} onSelect={setSelected} horizon={horizon} time={time ? fmtTime(time) : ""} />
      </aside>

      <main className="relative min-h-0">
        <BasinMap gauges={ranked} geometry={geometry} selected={selectedMeta} mesh={mesh} onSelect={setSelected} />
        <label className="absolute right-3 top-3 flex cursor-pointer items-center gap-2 border border-zinc-800 bg-zinc-950/90 px-2 py-1 text-[10px] text-zinc-300">
          <input type="checkbox" checked={mesh} onChange={(e) => setMesh(e.target.checked)} className="accent-cyan-400" />
          DEM CATCHMENT MESH + D8 FLOW PATHS
        </label>
      </main>

      <section className="min-h-0 border-t border-zinc-800">
        <ForecastPanel manifest={manifest} gauge={selectedMeta} file={gaugeFile} setName={setName} variant={variant}
                       time={time ?? null} horizon={horizon} onHorizon={setHorizon}
                       onSet={(s) => { setSetName(s); setPlaying(false); }} onVariant={setVariant}
                       times={status.times} t={t} onT={setT} playing={playing} onPlay={() => setPlaying((p) => !p)} />
      </section>

      {audit && <AuditPanel manifest={manifest} onClose={() => setAudit(false)} />}
    </div>
  );
}

function Stat({ k, v, accent }: { k: string; v: string; accent?: boolean }) {
  return (
    <span className="flex flex-col leading-tight">
      <span className="text-[9px] tracking-widest text-zinc-500">{k}</span>
      <span className={`text-[12px] font-bold tabular-nums ${accent ? "text-accent" : "text-zinc-100"}`}>{v}</span>
    </span>
  );
}

function Center({ children }: { children: React.ReactNode }) {
  return <div className="flex h-full items-center justify-center bg-zinc-950">{children}</div>;
}
