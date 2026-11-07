import { useEffect, useMemo } from "react";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import type { TimelineFrame } from "../lib/types";

interface Props {
  frames: TimelineFrame[];
  index: number;
  onChange: (i: number) => void;
  playing: boolean;
  onTogglePlay: () => void;
  horizonLabel?: string;
}

const fmtTs = (iso: string, regime: string) => {
  const d = new Date(iso);
  return regime === "longrange"
    ? d.toLocaleDateString("en-US", { year: "numeric", month: "short", timeZone: "UTC" })
    : d.toISOString().replace("T", " ").slice(0, 16) + "Z";
};

export default function TimelineScrubber({ frames, index, onChange, playing, onTogglePlay, horizonLabel }: Props) {
  const n = frames.length;
  const cur = frames[index];
  const firstForecast = useMemo(() => frames.findIndex((f) => f.kind === "forecast"), [frames]);
  const firstNowcast = useMemo(() => frames.findIndex((f) => f.regime === "nowcast"), [frames]);
  const lastNowcast = useMemo(() => frames.map((f) => f.regime).lastIndexOf("nowcast"), [frames]);

  // year ticks for the long-range axis
  const ticks = useMemo(() => {
    const seen = new Set<number>();
    return frames.flatMap((f, i) => {
      const y = new Date(f.timestamp).getUTCFullYear();
      if (seen.has(y) || f.regime !== "longrange") return [];
      seen.add(y);
      return [{ i, y }];
    });
  }, [frames]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement && e.target.type !== "range") return;
      if (e.key === "ArrowRight") onChange(Math.min(n - 1, index + 1));
      if (e.key === "ArrowLeft") onChange(Math.max(0, index - 1));
      if (e.key === " ") { e.preventDefault(); onTogglePlay(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, n, onChange, onTogglePlay]);

  if (!cur) return null;
  const pct = (i: number) => `${(i / Math.max(n - 1, 1)) * 100}%`;

  return (
    <div className="border-t border-term-line bg-term-panel px-4 pb-3 pt-2">
      <div className="mb-1 flex items-center gap-3 text-[11px]">
        <button className="text-term-dim hover:text-term-amber" onClick={() => onChange(0)} aria-label="Start"><SkipBack size={14} /></button>
        <button className="text-term-amber hover:brightness-125" onClick={onTogglePlay} aria-label={playing ? "Pause" : "Play"}>
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <button className="text-term-dim hover:text-term-amber" onClick={() => onChange(firstForecast)} aria-label="Jump to forecast"><SkipForward size={14} /></button>
        <span className="text-base font-bold tabular-nums text-term-text">{fmtTs(cur.timestamp, cur.regime)}</span>
        <span className={`px-1.5 py-0.5 text-[10px] font-bold ${cur.kind === "forecast" ? "bg-term-amber text-black" : "bg-term-cyan/20 text-term-cyan"}`}>
          {cur.kind === "forecast" ? `FORECAST ${horizonLabel ?? ""}` : "REALIZED"}
        </span>
        <span className="text-term-dim">{cur.regime === "nowcast" ? "NOWCAST REGIME" : "MULTI-YEAR REGIME"}</span>
        <span className="ml-auto text-term-dim">frame {index + 1}/{n} · ←/→ step · space play</span>
      </div>
      <div className="relative h-8">
        {/* regime bands */}
        <div className="absolute inset-y-2 left-0 right-0 bg-term-line/60" />
        {firstNowcast >= 0 && (
          <div className="absolute inset-y-2 bg-term-cyan/25" style={{ left: pct(firstNowcast), width: `calc(${pct(lastNowcast)} - ${pct(firstNowcast)})` }} />
        )}
        {firstForecast >= 0 && (
          <div className="absolute inset-y-2 right-0 bg-term-amber/20" style={{ left: pct(firstForecast) }}>
            <div className="h-full border-l border-dashed border-term-amber" />
          </div>
        )}
        <div className="absolute inset-y-2 left-0 bg-term-amber/40" style={{ width: pct(index) }} />
        <input type="range" className="scrub absolute inset-0" min={0} max={n - 1} value={index}
               onChange={(e) => onChange(Number(e.target.value))} aria-label="Timeline" />
      </div>
      <div className="relative h-3 text-[9px] text-term-dim">
        {ticks.filter((_, k) => ticks.length < 14 || k % 2 === 0).map((t) => (
          <span key={t.y} className="absolute -translate-x-1/2" style={{ left: pct(t.i) }}>{t.y}</span>
        ))}
      </div>
    </div>
  );
}
