import { Activity, CloudRain, Cpu, Network, Radio } from "lucide-react";
import type { BacktestResponse, FrameMeta, SourceState, StatusResponse } from "../lib/types";
import BacktestPanel from "./BacktestPanel";

const ICONS: Record<string, typeof Activity> = { telemetry: Radio, weather: CloudRain, osm: Network, forecast: Cpu };
const STATE_CLS: Record<SourceState, string> = {
  ONLINE: "text-term-green",
  DEGRADED: "text-term-amber",
  OFFLINE: "text-term-red",
  LOADING: "text-term-dim blink",
};

export default function TelemetrySidebar({ status, meta, backtest }: { status: StatusResponse | null; meta: FrameMeta | null; backtest: BacktestResponse | null }) {
  if (!status) return <div className="p-3 text-term-dim blink">connecting to backend…</div>;
  const nowcast = status.tensor.nowcast;
  const longrange = status.tensor.longrange;
  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3 scrollbar-thin">
      <Section title="ALT-DATA TELEMETRY">
        {status.sources.map((s) => {
          const Icon = ICONS[s.key] ?? Activity;
          return (
            <div key={s.key} className="border-l-2 border-term-line pl-2" title={JSON.stringify(s.metrics, null, 1)}>
              <div className="flex items-start gap-1.5">
                <span className={`font-bold ${STATE_CLS[s.state]}`}>[{s.state}]</span>
                <Icon size={13} className="mt-0.5 shrink-0 text-term-dim" />
                <span className="leading-4">{s.label}</span>
              </div>
              <div className="mt-0.5 text-[10px] leading-4 text-term-dim">{s.detail}</div>
            </div>
          );
        })}
        {status.pipeline !== "ready" && (
          <div className={status.pipeline === "error" ? "text-term-red" : "text-term-amber blink"}>
            ▸ {status.pipeline.toUpperCase()}: {status.error ?? status.stage}
          </div>
        )}
      </Section>

      {status.pipeline === "ready" && <BacktestPanel data={backtest} />}

      {meta?.weather && (
        <Section title="WEATHER @ FRAME (OPEN-METEO ERA5)">
          <Grid rows={[["TEMP", `${meta.weather.temperature ?? "—"} °C`], ["PRECIP", `${meta.weather.precipitation ?? "—"} mm`],
                       ["WIND", `${meta.weather.wind_speed ?? "—"} km/h`]]} />
        </Section>
      )}

      {nowcast && (
        <Section title="TUCKER DENOISER">
          <Grid rows={[
            ["TENSOR", nowcast.shape.join(" × ")],
            ["RANKS", nowcast.ranks.join(" / ")],
            ["BIN", nowcast.freq],
            ["RESID ‖E‖/‖X‖", nowcast.activity_rel_error.toFixed(3)],
            ...(longrange ? [["LR TENSOR", longrange.shape.join(" × ")] as [string, string], ["LR HORIZON", `${longrange.horizon_steps} mo`] as [string, string]] : []),
          ]} />
          <div className="mt-2 text-[10px] text-term-dim">LATENT TEMPORAL ENERGY</div>
          <div className="mt-1 flex h-10 items-end gap-0.5">
            {nowcast.temporal_explained.map((v, i) => (
              <div key={i} className="flex-1 bg-term-cyan/70" style={{ height: `${Math.max(4, v * 100)}%` }} title={`U_t[${i}] ${(v * 100).toFixed(1)}%`} />
            ))}
          </div>
        </Section>
      )}

      {status.notes.length > 0 && (
        <Section title="PIPELINE LOG">
          {status.notes.map((n, i) => <div key={i} className="text-[10px] leading-4 text-term-dim">› {n}</div>)}
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border border-term-line bg-term-panel p-2.5">
      <h2 className="mb-2 text-[10px] font-bold tracking-[0.2em] text-term-amber">{title}</h2>
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  );
}

function Grid({ rows }: { rows: [string, string][] }) {
  return (
    <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[11px]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <span className="text-term-dim">{k}</span>
          <span className="text-right tabular-nums">{v}</span>
        </div>
      ))}
    </div>
  );
}
