import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, ArrowLeft, ArrowRight, Compass, ShieldAlert, Waves, X } from "lucide-react";
import { data, fmtTime, pct } from "../lib/data";
import { riskOf } from "../lib/risk";
import { TOUR } from "../lib/tour";
import type { GaugeFile, Geometry, Horizon, Manifest, Risk, SetName, StatusFile, Variant } from "../lib/types";
import BasinSidebar from "./BasinSidebar";
import BasinMap from "./BasinMap";
import ForecastPanel from "./ForecastPanel";
import AuditPanel from "./AuditPanel";

const PLAY_MS = 1000;                                       // one replay step per second: slow enough to read
const TIER: Record<Risk, number> = { crit: 0, warn: 1, ok: 2, none: 3 };

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
  const [target, setTarget] = useState<string | null>(null);   // replay time requested by the tour
  const [horizon, setHorizon] = useState<Horizon>(24);
  const [selected, setSelected] = useState<string | null>(null);
  const [gaugeFile, setGaugeFile] = useState<GaugeFile | null>(null);
  const [geometry, setGeometry] = useState<Record<string, Geometry>>({});
  const [mesh, setMesh] = useState(true);
  const [audit, setAudit] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [tour, setTour] = useState<number | null>(0);
  const curTime = useRef<string | null>(null);              // keep the same moment when switching rain scenario

  useEffect(() => {
    data.manifest().then((mf) => {
      setManifest(mf);
      Promise.all(mf.gauges.map((g) => data.geometry(g.slug).then((geo) => [g.slug, geo] as const)))
        .then((pairs) => setGeometry(Object.fromEntries(pairs.filter(([, geo]) => geo)) as Record<string, Geometry>));
    }).catch((e) => setErr(String(e)));
  }, []);

  // status file for the replay set/variant; without a tour target, open on the moment with the most alerts
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
      const want = target ?? curTime.current;
      setT(want && s.times.includes(want) ? s.times.indexOf(want) : best);
    }).catch((e) => setErr(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifest, setName, variant]);

  useEffect(() => {
    if (status && target) { const i = status.times.indexOf(target); if (i >= 0) setT(i); }
  }, [status, target]);

  useEffect(() => {
    if (!selected) return;
    setGaugeFile(null);
    data.gauge(selected).then(setGaugeFile).catch((e) => setErr(String(e)));
  }, [selected]);

  useEffect(() => {
    if (!playing || !status) return;
    const id = setInterval(() => setT((x) => (x + 1) % status.times.length), PLAY_MS);
    return () => clearInterval(id);
  }, [playing, status]);

  // tour: jump to the step's real moment
  useEffect(() => {
    const at = tour != null ? TOUR[tour].at : undefined;
    if (!at) return;
    setPlaying(false);
    setSetName(at.set); setVariant(at.variant); setSelected(at.gauge); setHorizon(24); setTarget(at.time);
  }, [tour]);

  const time = status?.times[t];
  curTime.current = time ?? null;
  const row = status?.rows[t];
  // most-at-risk first, but stable inside each tier so the list doesn't reshuffle every step
  const ranked = useMemo(() => {
    if (!manifest) return [];
    return manifest.gauges
      .filter((g) => g.sets[setName])
      .map((g, order) => ({ g, order, ...riskOf(g, row?.[g.slug], horizon) }))
      .sort((a, b) => TIER[a.risk] - TIER[b.risk] || a.order - b.order);
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
  const step = tour != null ? TOUR[tour] : null;

  return (
    <div className="grid h-full grid-cols-[320px_1fr] grid-rows-[44px_1fr_300px] bg-zinc-950 max-lg:grid-cols-1 max-lg:grid-rows-[auto_50vh_auto_auto]">
      {/* ── top bar ─────────────────────────────────────────────── */}
      <header className="col-span-full flex items-center gap-5 overflow-x-auto border-b border-zinc-800 px-4 whitespace-nowrap">
        <span className="flex items-center gap-2 font-bold tracking-[0.25em] text-accent"><Waves size={16} /> FLOODPULSE</span>
        <span className="flex items-center gap-1.5 border border-warn/50 px-2 py-0.5 text-[10px] font-bold text-warn">
          <Activity size={11} /> REPLAY OF PAST DATA · NOT LIVE
        </span>
        <Stat k="RESULT" v={`Forecast error cut ${pct(rangeLo)}–${pct(rangeHi)} vs river-history-only model`} accent />
        <Stat k="RIGHT NOW IN THIS REPLAY" v={`${counts.crit ?? 0} alert · ${counts.warn ?? 0} watch · ${counts.ok ?? 0} normal`} />
        {advanced && <Stat k={`WARNINGS · REAL FORECASTS · ${w.events} EVENTS`} v={`${pct(w.booster.hit_rate)} caught · ${w.booster.mean_lead_h?.toFixed(1)} h lead`} />}
        <span className="ml-auto flex items-center gap-2">
          <button onClick={() => setTour(0)} className="flex items-center gap-1.5 border border-accent/60 px-2 py-1 text-[10px] text-accent hover:bg-accent/10">
            <Compass size={12} /> GUIDED TOUR
          </button>
          <label className="flex cursor-pointer items-center gap-1.5 border border-zinc-700 px-2 py-1 text-[10px] text-zinc-300">
            <input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} className="accent-cyan-400" /> ADVANCED
          </label>
          <button onClick={() => setAudit(true)}
                  className="flex items-center gap-1.5 border border-zinc-700 px-2 py-1 text-[10px] text-zinc-300 hover:border-accent hover:text-accent">
            <ShieldAlert size={12} /> LIMITATIONS
          </button>
        </span>
      </header>

      <aside className="row-span-2 min-h-0 border-r border-zinc-800 max-lg:row-span-1 max-lg:border-r-0">
        <BasinSidebar ranked={ranked} selected={selected} onSelect={setSelected} horizon={horizon} time={time ? fmtTime(time) : ""} />
      </aside>

      <main className="relative min-h-0">
        <BasinMap gauges={ranked} geometry={geometry} selected={selectedMeta} mesh={mesh} onSelect={setSelected} />
        {advanced && (
          <label className="absolute right-3 top-3 flex cursor-pointer items-center gap-2 border border-zinc-800 bg-zinc-950/90 px-2 py-1 text-[10px] text-zinc-300">
            <input type="checkbox" checked={mesh} onChange={(e) => setMesh(e.target.checked)} className="accent-cyan-400" />
            SHOW TERRAIN MESH
          </label>
        )}
        {step && (
          <div className="absolute left-3 top-3 flex min-h-[270px] w-[420px] max-w-[calc(100%-24px)] flex-col border border-accent/50 bg-zinc-950/95 p-4 shadow-2xl">
            <div className="mb-1 flex items-center justify-between text-[10px] tracking-widest text-zinc-500">
              <span>GUIDED TOUR · {tour! + 1} / {TOUR.length}</span>
              <button onClick={() => setTour(null)} aria-label="Close tour" className="text-zinc-500 hover:text-zinc-200"><X size={14} /></button>
            </div>
            <div className="mb-2 text-[14px] font-bold text-zinc-100">{step.title}</div>
            <p className="text-[12px] leading-5 text-zinc-300">{step.body}</p>
            {step.look && <p className="mt-2 text-[11px] text-accent">👀 {step.look}</p>}
            <div className="mt-auto flex items-center gap-2 pt-3">
              <button disabled={tour === 0} onClick={() => setTour(tour! - 1)}
                      className="flex items-center gap-1 border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 disabled:opacity-30">
                <ArrowLeft size={12} /> Back
              </button>
              {tour! < TOUR.length - 1 ? (
                <button onClick={() => setTour(tour! + 1)}
                        className="flex items-center gap-1 bg-accent px-3 py-1 text-[11px] font-bold text-zinc-950">
                  Next <ArrowRight size={12} />
                </button>
              ) : (
                <button onClick={() => setTour(null)} className="bg-accent px-3 py-1 text-[11px] font-bold text-zinc-950">Start exploring</button>
              )}
              <span className="ml-auto flex gap-1">
                {TOUR.map((_, i) => <span key={i} className={`h-1.5 w-1.5 rounded-full ${i === tour ? "bg-accent" : "bg-zinc-700"}`} />)}
              </span>
            </div>
          </div>
        )}
      </main>

      <section className="min-h-0 border-t border-zinc-800">
        <ForecastPanel manifest={manifest} gauge={selectedMeta} file={gaugeFile} setName={setName} variant={variant}
                       time={time ?? null} horizon={horizon} onHorizon={setHorizon} advanced={advanced}
                       onSet={(s) => { setTarget(null); curTime.current = null; setSetName(s); setPlaying(false); }}
                       onVariant={(v) => { setVariant(v); setPlaying(false); }}
                       times={status.times} t={t} onT={(i) => { setPlaying(false); setTarget(null); setT(i); }}
                       playing={playing} onPlay={() => setPlaying((p) => !p)} />
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
