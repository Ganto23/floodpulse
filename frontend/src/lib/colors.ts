// Inferno-like ramp tuned for dark terminals. t in [0,1].
const STOPS: [number, [number, number, number]][] = [
  [0.0, [20, 11, 52]],
  [0.25, [101, 21, 110]],
  [0.5, [188, 55, 84]],
  [0.75, [249, 142, 9]],
  [1.0, [252, 255, 164]],
];

export function ramp(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t));
  for (let i = 1; i < STOPS.length; i++) {
    const [t1, c1] = STOPS[i];
    const [t0, c0] = STOPS[i - 1];
    if (x <= t1) {
      const f = (x - t0) / (t1 - t0);
      return [0, 1, 2].map((k) => Math.round(c0[k] + f * (c1[k] - c0[k]))) as [number, number, number];
    }
  }
  return STOPS[STOPS.length - 1][1];
}

export const SIGNAL_RGB: Record<string, [number, number, number]> = {
  VELOCITY_SURGE: [25, 226, 138],
  MOMENTUM_DECAY: [255, 77, 94],
  ANOMALY: [255, 79, 216],
  DISPATCH: [255, 176, 0],
};

export const fmt = (v: number | null | undefined, d = 3) =>
  v == null ? "—" : Math.abs(v) >= 1000 ? v.toExponential(2) : v.toPrecision(d);
