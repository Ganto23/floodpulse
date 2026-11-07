import { useCallback, useEffect, useRef, useState } from "react";
import { Layers3 } from "lucide-react";
import MapCanvas, { type LayerToggles, type Metric } from "./components/MapCanvas";
import TimelineScrubber from "./components/TimelineScrubber";
import TelemetrySidebar from "./components/TelemetrySidebar";
import SignalsPanel from "./components/SignalsPanel";
import { api } from "./lib/api";
import type { BacktestResponse, Infrastructure, SpatialFrame, StatusResponse, TimelineResponse } from "./lib/types";

const PLAY_MS = 450;

export default function App() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [infra, setInfra] = useState<Infrastructure | null>(null);
  const [index, setIndex] = useState(0);
  const [frame, setFrame] = useState<SpatialFrame | null>(null);
  const [playing, setPlaying] = useState(false);
  const [metric, setMetric] = useState<Metric>("denoised");
  const [toggles, setToggles] = useState<LayerToggles>({ extrude: true, vectors: true, catchments: true, infra: true, highlights: true });
  const [err, setErr] = useState<string | null>(null);
  const [backtest, setBacktest] = useState<BacktestResponse | null>(null);
  const cache = useRef(new Map<string, SpatialFrame>());

  // poll status until the pipeline is ready, then every 15 s
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const s = await api.status();
        if (!alive) return;
        setStatus(s); setErr(null);
        timer = setTimeout(tick, s.pipeline === "ready" ? 15000 : 1500);
      } catch (e) {
        if (!alive) return;
        setErr(String(e)); timer = setTimeout(tick, 3000);
      }
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, []);

  const ready = status?.pipeline === "ready";
  useEffect(() => {
    if (!ready || timeline) return;
    api.timeline().then((t) => {
      setTimeline(t);
      const lastHist = t.frames.map((f) => f.kind).lastIndexOf("historical");
      setIndex(Math.max(0, lastHist));
    }).catch((e) => setErr(String(e)));
    api.infrastructure().then(setInfra).catch(() => setInfra(null));
  }, [ready, timeline]);

  // backtest runs after the map is live; poll until it settles
  useEffect(() => {
    if (!ready) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => api.backtest().then((b) => {
      if (!alive) return;
      setBacktest(b);
      if (b.status === "pending" || b.status === "running") timer = setTimeout(tick, 2000);
    }).catch(() => { if (alive) timer = setTimeout(tick, 4000); });
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [ready]);

  // fetch the frame for the current index (cached, abortable)
  useEffect(() => {
    const ts = timeline?.frames[index]?.timestamp;
    if (!ts) return;
    const hit = cache.current.get(ts);
    if (hit) { setFrame(hit); return; }
    const ctl = new AbortController();
    api.frame(ts, ctl.signal).then((f) => {
      cache.current.set(ts, f);
      setFrame(f);
    }).catch((e) => { if (e.name !== "AbortError") setErr(String(e)); });
    return () => ctl.abort();
  }, [timeline, index]);

  // playback
  useEffect(() => {
    if (!playing || !timeline) return;
    const id = setInterval(() => setIndex((i) => (i + 1 >= timeline.frames.length ? 0 : i + 1)), PLAY_MS);
    return () => clearInterval(id);
  }, [playing, timeline]);

  // forecast frames have no realized/denoised surface: follow the forecast automatically
  const effectiveMetric: Metric = frame?.meta.kind === "forecast" ? "forecast" : metric === "forecast" ? "denoised" : metric;
  const togglePlay = useCallback(() => setPlaying((p) => !p), []);

  return (
    <div className="grid h-full grid-cols-[300px_1fr_340px] grid-rows-[40px_1fr_auto] max-lg:grid-cols-1 max-lg:grid-rows-[40px_60vh_auto_auto_auto]">
      <header className="col-span-full flex items-center gap-4 border-b border-term-line bg-term-panel px-4">
        <span className="font-bold tracking-[0.25em] text-term-amber">URBANPULSE</span>
        <span className="text-term-dim">ALT-DATA SPATIAL MOMENTUM TERMINAL</span>
        <span className="border border-term-line px-1.5 text-[10px] text-term-cyan">MODE: {status?.mode.label ?? "…"}</span>
        <div className="ml-auto flex items-center gap-1 text-[10px]">
          {(["realized", "denoised"] as Metric[]).map((m) => (
            <button key={m} onClick={() => setMetric(m)}
                    className={`px-2 py-0.5 uppercase ${effectiveMetric === m ? "bg-term-amber text-black" : "text-term-dim hover:text-term-text"}`}>{m}</button>
          ))}
          <span className={`px-2 py-0.5 uppercase ${effectiveMetric === "forecast" ? "bg-term-amber text-black" : "text-term-line"}`}>forecast</span>
          <Layers3 size={13} className="ml-3 text-term-dim" />
          {(Object.keys(toggles) as (keyof LayerToggles)[]).map((k) => (
            <button key={k} onClick={() => setToggles((t) => ({ ...t, [k]: !t[k] }))}
                    className={`px-1.5 py-0.5 uppercase ${toggles[k] ? "text-term-cyan" : "text-term-line"}`}>{k}</button>
          ))}
        </div>
      </header>

      <aside className="border-r border-term-line max-lg:order-3 max-lg:border-r-0">
        <TelemetrySidebar status={status} meta={frame?.meta ?? null} backtest={backtest} />
      </aside>

      <main className="relative min-h-0">
        {timeline ? (
          <MapCanvas frame={frame} infra={infra} center={timeline.center} metric={effectiveMetric}
                     toggles={toggles} highlightLabel={status?.mode.highlight_label ?? "highlights"} />
        ) : (
          <div className="flex h-full items-center justify-center text-term-dim">
            <span className="blink">{err ? `backend unreachable — ${err}` : `▸ ${status?.stage || "booting pipeline"}…`}</span>
          </div>
        )}
      </main>

      <aside className="min-h-0 border-l border-term-line max-lg:order-4 max-lg:max-h-[50vh] max-lg:border-l-0">
        <SignalsPanel signals={frame?.signals ?? []} label={frame?.meta.horizon_label ?? ""} />
      </aside>

      <footer className="col-span-full max-lg:order-2">
        {timeline && (
          <TimelineScrubber frames={timeline.frames} index={index} onChange={setIndex}
                            playing={playing} onTogglePlay={togglePlay} horizonLabel={frame?.meta.horizon_label} />
        )}
      </footer>
    </div>
  );
}
