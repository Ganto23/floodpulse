import { useEffect, useMemo, useRef, useState } from "react";
import { data, pct } from "../lib/data";
import { riskOf } from "../lib/risk";
import type { GaugeFile, Geometry, Horizon, Manifest, Risk, SetName, StatusFile, Variant } from "../lib/types";
import BasinSidebar from "./BasinSidebar";
import BasinMap from "./BasinMap";
import ForecastPanel from "./ForecastPanel";
import PlaybackBar, { type FloodEvent, type Preset } from "./PlaybackBar";

/**
 * FloodPulse: Historical Backtest Replay Engine.
 *
 * Replays REAL held-out model output. Data: public/data/*.json from eval_harness/floodpulse_stress.py → export_dashboard.py
 *   manifest.json             gauges, alert thresholds (training-period P99), audited headline metrics
 *   status_<set>_<var>.json   per replay step × gauge: current level, predicted peak, hours to alert line
 *   gauge_<slug>.json         observed levels + baseline / FloodPulse trajectories + band
 *   geometry_<slug>.json      river channels traced from terrain
 * 2024 uses rain forecasts exactly as issued. No forecasts were archived before 2024, so the storm replays
 * (Ciara 2020, Babet 2023) use the rain that actually fell: a perfect-rain UPPER BOUND, labelled as such.
 */
const REPLAY: Record<SetName, { variant: Variant; title: string; note: string }> = {
  "2024": { variant: "deployed", title: "Historical Backtest Replay Engine (2024)", note: "real rain forecasts as issued · not live monitoring" },
  babet: { variant: "oracle", title: "Storm Babet replay (Oct 2023)", note: "perfect-rain upper bound: no archived rain forecasts before 2024" },
  ciara_dennis: { variant: "oracle", title: "Storm Ciara replay (Feb 2020)", note: "perfect-rain upper bound: no archived rain forecasts before 2024" },
};
// Babet / Dec 2024: the moment FloodPulse first called the Calder crossing its alert line ahead of time (river still below it).
// Ciara: the moment with the most gauges forecast to cross (Calder·Mytholmroyd is not in the Ciara replay).
const PRESETS: Preset[] = [
  { id: "babet", label: "Storm Babet", set: "babet", time: "2023-10-19 05:00:00+00:00", gauge: "calder_mytholmroyd", note: "perfect rain" },
  { id: "ciara", label: "Storm Ciara", set: "ciara_dennis", time: "2020-02-09 14:00:00+00:00", gauge: "eden_sheepmount", note: "perfect rain" },
  { id: "dec24", label: "Dec 2024 Surge", set: "2024", time: "2024-12-04 18:00:00+00:00", gauge: "calder_mytholmroyd" },
];
const START = "2024-12-04 18:00:00+00:00";      // opens on a real moment: Calder normal now, alert line crossed ~23 h later
const PLAY_MS = 1000;                           // one replay step per second
const MERGE_H = 24;                             // flagged steps closer than this belong to the same event
const TIER: Record<Risk, number> = { crit: 0, warn: 1, ok: 2, none: 3 };
const parse = (s: string) => new Date(s.replace(" ", "T")).getTime();

export default function FloodPulseDashboard() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [setName, setSetName] = useState<SetName>("2024");
  const [status, setStatus] = useState<StatusFile | null>(null);
  const [geometry, setGeometry] = useState<Record<string, Geometry>>({});
  const [selected, setSelected] = useState("calder_mytholmroyd");
  const [gaugeFile, setGaugeFile] = useState<GaugeFile | null>(null);
  const [horizon, setHorizon] = useState<Horizon>(24);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const target = useRef<string | null>(START);  // time to land on once a replay's status file loads
  const variant = REPLAY[setName].variant;

  useEffect(() => {
    data.manifest().then((mf) => {
      setManifest(mf);
      Promise.all(mf.gauges.map((g) => data.geometry(g.slug).then((geo) => [g.slug, geo] as const)))
        .then((pairs) => setGeometry(Object.fromEntries(pairs.filter(([, geo]) => geo)) as Record<string, Geometry>));
    }).catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    data.status(setName, variant).then((s) => {
      setStatus(s);
      const i = target.current ? s.times.indexOf(target.current) : -1;
      setT(i >= 0 ? i : 0);              // target is kept (not cleared) so a double-run effect lands on the same step
    }).catch((e) => setErr(String(e)));
  }, [setName, variant]);

  useEffect(() => {
    data.gauge(selected).then(setGaugeFile).catch((e) => setErr(String(e)));
  }, [selected]);

  useEffect(() => {
    if (!playing || !status) return;
    const id = setInterval(() => setT((x) => (x + 1) % status.times.length), PLAY_MS);
    return () => clearInterval(id);
  }, [playing, status]);

  // flood events in this replay: merged runs of steps where any gauge is forecast to cross, or is above, its alert line
  const events = useMemo<FloodEvent[]>(() => {
    if (!status || !manifest) return [];
    const p99 = Object.fromEntries(manifest.gauges.map((g) => [g.slug, g.p99_mm]));
    const out: FloodEvent[] = [];
    status.rows.forEach((row, i) => {
      const cells = Object.entries(row);
      const pred = cells.filter(([, c]) => c.breach_h != null).length;
      const actual = cells.some(([k, c]) => c.obs != null && c.obs >= p99[k]);
      if (!pred && !actual) return;
      const last = out[out.length - 1];
      if (last && parse(status.times[i]) - parse(status.times[last.end]) <= MERGE_H * 3_600_000) {
        last.end = i; last.actual ||= actual;
        if (pred > Object.values(status.rows[last.peak]).filter((c) => c.breach_h != null).length) last.peak = i;
      } else out.push({ start: i, end: i, peak: i, actual });
    });
    return out;
  }, [status, manifest]);

  const time = status?.times[t] ?? null;
  const row = status?.rows[t];
  // most at risk first; stable order within each status so cards don't jump around during playback
  const ranked = useMemo(() => !manifest ? [] : manifest.gauges
    .filter((g) => g.sets[setName])
    .map((g, order) => ({ g, order, ...riskOf(g, row?.[g.slug], horizon) }))
    .sort((a, b) => TIER[a.risk] - TIER[b.risk] || a.order - b.order), [manifest, row, horizon, setName]);

  useEffect(() => {   // keep a valid gauge selected when a replay doesn't include it
    if (ranked.length && !ranked.some((r) => r.g.slug === selected)) setSelected(ranked[0].g.slug);
  }, [ranked, selected]);

  if (err) return <div className="flex h-full items-center justify-center text-crit">{err}</div>;
  if (!manifest || !status) return <div className="h-full bg-slate-900" />;

  const h = manifest.headline;
  const lo = Math.min(...Object.values(h.error_reduction_day2));
  const hi = Math.max(...Object.values(h.error_reduction_day1));
  const gaugeMeta = manifest.gauges.find((g) => g.slug === selected) ?? null;
  const replay = REPLAY[setName];

  const jump = (i: number) => { setPlaying(false); setT(i); };
  const goPreset = (pr: Preset) => {
    setPlaying(false);
    setSelected(pr.gauge);
    if (pr.set === setName) { const i = status.times.indexOf(pr.time); if (i >= 0) setT(i); }
    else { target.current = pr.time; setSetName(pr.set); }
  };
  const nextEvent = () => { const e = events.find((ev) => ev.start > t) ?? events[0]; if (e) jump(e.start); };
  const prevEvent = () => {
    const cur = events.findIndex((ev) => t >= ev.start && t <= ev.end);
    const before = events.filter((ev) => ev.start < (cur >= 0 ? events[cur].start : t));
    const e = before[before.length - 1] ?? events[events.length - 1];
    if (e) jump(e.start);
  };
  const activePreset = PRESETS.find((pr) => {
    if (pr.set !== setName) return false;
    const i = status.times.indexOf(pr.time);
    const ev = events.find((e) => i >= e.start && i <= e.end);
    return ev ? t >= ev.start && t <= ev.end : t === i;
  })?.id ?? null;

  return (
    <div className="grid h-full grid-cols-[340px_1fr] grid-rows-[60px_1fr_360px] bg-slate-900 text-slate-200">
      <header className="col-span-full flex items-center gap-6 border-b border-slate-800 px-6">
        <div>
          <div className="font-mono text-[15px] font-medium tracking-[0.2em] text-slate-100">
            FLOODPULSE <span className="text-slate-600">//</span> <span className="text-slate-400">HISTORICAL BACKTEST REPLAY</span>
          </div>
          <div className="text-[11px] text-slate-500">
            {replay.title} · <span className={variant === "oracle" ? "text-warn/80" : ""}>{replay.note}</span>
          </div>
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

      <section className="col-span-full flex min-h-0 flex-col border-t border-slate-800">
        <div className="min-h-0 flex-1">
          <ForecastPanel gauge={gaugeMeta} file={gaugeFile?.slug === selected ? gaugeFile : null} time={time}
                         horizon={horizon} onHorizon={setHorizon} setName={setName} variant={variant} />
        </div>
        <PlaybackBar presets={PRESETS} activePreset={activePreset} onPreset={goPreset}
                     times={status.times} t={t} onT={jump} playing={playing} onPlay={() => setPlaying((x) => !x)}
                     events={events} onPrev={prevEvent} onNext={nextEvent} />
      </section>
    </div>
  );
}
