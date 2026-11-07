import { AlertTriangle, ArrowDownRight, Send, Zap } from "lucide-react";
import type { Signal, SignalType } from "../lib/types";
import { SIGNAL_RGB } from "../lib/colors";

const ICON: Record<SignalType, typeof Zap> = {
  VELOCITY_SURGE: Zap, MOMENTUM_DECAY: ArrowDownRight, ANOMALY: AlertTriangle, DISPATCH: Send,
};

export default function SignalsPanel({ signals, label }: { signals: Signal[]; label: string }) {
  const counts = signals.reduce<Record<string, number>>((a, s) => ({ ...a, [s.type]: (a[s.type] ?? 0) + 1 }), {});
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-term-line px-3 py-2">
        <div className="text-[10px] font-bold tracking-[0.2em] text-term-amber">AUTOMATED QUANT SIGNALS</div>
        <div className="mt-1 flex flex-wrap gap-2 text-[10px]">
          <span className="text-term-dim">{label}</span>
          {Object.entries(counts).map(([k, v]) => (
            <span key={k} style={{ color: `rgb(${SIGNAL_RGB[k].join(",")})` }}>{k} {v}</span>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-2 scrollbar-thin">
        {signals.length === 0 && <div className="p-2 text-term-dim">no signals breach thresholds at this frame</div>}
        {signals.map((s) => {
          const Icon = ICON[s.type];
          const c = `rgb(${SIGNAL_RGB[s.type].join(",")})`;
          return (
            <div key={s.id} className="mb-2 border border-term-line bg-term-panel p-2" style={{ borderLeft: `3px solid ${c}` }}>
              <div className="flex items-center gap-1.5 text-[11px] font-bold" style={{ color: c }}>
                <Icon size={12} /> {s.type}
                <span className="ml-auto text-[10px] font-normal uppercase text-term-dim">{s.severity} · {s.z.toFixed(1)}σ</span>
              </div>
              <div className="mt-1 text-[11px] leading-4">{s.message}</div>
              <div className="mt-1 text-[10px] leading-4 text-term-green">» {s.action}</div>
              <div className="mt-1 text-[9px] text-term-dim">{s.h3} · {s.latitude.toFixed(4)}, {s.longitude.toFixed(4)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
