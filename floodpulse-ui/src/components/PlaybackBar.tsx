import { ChevronLeft, ChevronRight, Pause, Play, Zap } from "lucide-react";
import type { SetName } from "../lib/types";

export interface Preset { id: string; label: string; set: SetName; time: string; gauge: string; note?: string }
/** A flood event: a run of replay steps where any gauge is forecast to cross (or is above) its alert line. */
export interface FloodEvent { start: number; end: number; peak: number; actual: boolean }

const fmtDay = (s: string) => new Date(s.replace(" ", "T")).toLocaleString("en-GB", {
  day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC";

/** Event presets, event navigation, play/pause and a timeline track with event markers. */
export default function PlaybackBar(p: {
  presets: Preset[]; activePreset: string | null; onPreset: (pr: Preset) => void;
  times: string[]; t: number; onT: (i: number) => void; playing: boolean; onPlay: () => void;
  events: FloodEvent[]; onPrev: () => void; onNext: () => void;
}) {
  const n = Math.max(p.times.length - 1, 1);
  const current = p.events.findIndex((e) => p.t >= e.start && p.t <= e.end);
  return (
    <div className="px-5 pb-3 pt-2">
      {/* event presets */}
      <div className="mb-2.5 flex items-center gap-2">
        {p.presets.map((pr) => {
          const on = p.activePreset === pr.id;
          return (
            <button key={pr.id} onClick={() => p.onPreset(pr)}
                    className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] transition-colors ${on ? "border-s-fp/60 bg-s-fp/10 text-slate-100" : "border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200"}`}>
              <Zap size={12} className={on ? "text-s-fp" : "text-warn"} /> {pr.label}
              {pr.note && <span className="text-[10px] text-slate-500">· {pr.note}</span>}
            </button>
          );
        })}
        <span className="ml-auto text-[11px] text-slate-500">
          {current >= 0 ? `event ${current + 1} of ${p.events.length}` : `${p.events.length} events in this replay`}
        </span>
      </div>

      {/* transport + timeline */}
      <div className="flex items-center gap-3">
        <button onClick={p.onPrev} className="flex items-center gap-1 rounded-md bg-slate-800 px-2.5 py-1 text-[12px] text-slate-300 hover:bg-slate-700">
          <ChevronLeft size={13} /> Prev Event
        </button>
        <button onClick={p.onPlay} aria-label={p.playing ? "Pause" : "Play"}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-800 text-slate-200 hover:bg-slate-700">
          {p.playing ? <Pause size={13} /> : <Play size={13} className="ml-0.5" />}
        </button>
        <button onClick={p.onNext} className="flex items-center gap-1 rounded-md bg-slate-800 px-2.5 py-1 text-[12px] text-slate-300 hover:bg-slate-700">
          Next Event <ChevronRight size={13} />
        </button>

        <div className="relative flex-1">
          <input type="range" className="scrub relative z-10" min={0} max={n} value={p.t}
                 onChange={(e) => p.onT(Number(e.target.value))} aria-label="Replay time" />
          {/* event markers: red = a river actually went above its alert line, amber = forecast only */}
          <div className="pointer-events-none absolute inset-x-[7px] top-1/2 z-20">
            {p.events.map((e, i) => (
              <span key={i} title={fmtDay(p.times[e.start])}
                    className={`absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-slate-900 ${e.actual ? "bg-crit" : "bg-warn"}`}
                    style={{ left: `${(e.start / n) * 100}%` }} />
            ))}
          </div>
        </div>
        <span className="w-52 shrink-0 text-right font-mono text-[12px] text-slate-300">{p.times[p.t] ? fmtDay(p.times[p.t]) : ""}</span>
      </div>
    </div>
  );
}
