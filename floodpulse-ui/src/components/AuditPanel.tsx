import { X } from "lucide-react";
import { pct } from "../lib/data";
import type { Manifest } from "../lib/types";

/** Wilson 95% interval: sample-size honesty for small storm counts. */
function wilson(p: number, n: number): [number, number] {
  if (!n) return [0, 1];
  const z = 1.96, d = 1 + (z * z) / n, c = (p + (z * z) / (2 * n)) / d, h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [Math.max(0, c - h), Math.min(1, c + h)];
}

export default function AuditPanel({ manifest, onClose }: { manifest: Manifest; onClose: () => void }) {
  const h = manifest.headline;
  const d1 = h.error_reduction_day1, d2 = h.error_reduction_day2;
  const wd = h.warnings_2024_deployed, wo = h.warnings_2024_oracle;
  const derwent = manifest.gauges.find((g) => g.slug === "derwent_ouse_bridge");
  const babet = h.storms["babet_oracle"]?.booster;
  const bab = babet?.capture_12h != null ? wilson(babet.capture_12h, babet.n_12h) : null;
  const wci = wd.booster.hit_rate != null ? wilson(wd.booster.hit_rate, wd.events) : null;

  const items: [string, React.ReactNode][] = [
    ["Forecast timing", <>Rain forecasts are archived <b>issued</b> NWP runs (Open-Meteo Previous-Runs), used to both fit and score. With 24 h-old forecasts the error reduction is −{pct(d1["6"])} / −{pct(d1["12"])} / −{pct(d1["24"])} at 6/12/24 h. Publication latency is undocumented, so with strictly-public <b>48 h-old</b> forecasts it is −{pct(d2["6"])} / −{pct(d2["12"])} / −{pct(d2["24"])}. At 24 h that's <b>−{pct(d2["24"])} to −{pct(d1["24"])}</b>; median of {h.gauges_phase1} gauges, positive at all.</>],
    ["What the baseline is", <>Error reduction is measured against a model using <b>river-level history only</b>. It is <b>not</b> a comparison with Environment Agency operational flood forecasts, which aren't publicly archived.</>],
    ["Warnings: the bottleneck", <>With real issued forecasts (2024 backtest, {wd.events} threshold crossings): <b>{pct(wd.booster.hit_rate)} caught</b> (95% CI {wci ? `${pct(wci[0])}–${pct(wci[1])}` : "—"}), mean lead <b>{wd.booster.mean_lead_h?.toFixed(1)} h</b>, false-alarm ratio {wd.booster.far?.toFixed(2)}. With a perfect rain forecast: {pct(wo.booster.hit_rate)} caught, {wo.booster.mean_lead_h?.toFixed(1)} h; held-out storms ~{h.warnings_ciara_oracle?.booster.mean_lead_h?.toFixed(0)}–{h.warnings_babet_oracle?.booster.mean_lead_h?.toFixed(0)} h. <b>Rain-forecast quality, not the river model, limits lead time.</b></>],
    ["Topographic lag", <>DEM (priority-flood + D8) Kirpich travel time vs measured rain→peak lag: Spearman <b>ρ = {h.dem_lag.spearman.toFixed(2)}, p = {h.dem_lag.spearman_p.toFixed(3)}</b> (n = {h.dem_lag.n}): not significant. It matches 8 rivers within ~3 h but <b>misses the lake-fed Derwent</b> ({derwent?.dem_tc_h.toFixed(1)} h predicted vs {derwent?.empirical_lag_h} h measured): lake storage isn't modelled. That was diagnosed after the fact, not flagged by the model.</>],
    ["Storm sample size", <>Mega-storms predate the forecast archive, so they're bracketed by past-rain-only and perfect-rain variants. Babet crest capture (±20%, ±3 h, 12 h lead, perfect rain) = {babet?.capture_12h != null ? `${pct(babet.capture_12h)} of ${babet.n_12h} rivers` : "—"} (95% CI {bab ? `${pct(bab[0])}–${pct(bab[1])}` : "—"}): <b>indicative only</b>. Crests are under-predicted by every model.</>],
    ["Chronology", <>Storm windows (±7 days) and all of 2024 are held out, but storm tests use models fit on 2019–2023, i.e. including years <b>after</b> Ciara. That's no test-data leakage, but it isn't a strict forward test either.</>],
    ["Known data issues", <>7 tipping-bucket rain artifacts (33–74 mm/h with ERA5 ≈ 0 and no river response) pass QC, 1 inside 2024; measured impact ≤ 0.11 m, no false warning. Up to 13% of hours fall back from gauge rain to ERA5. ERA5 isn't real-time, so a live system needs NWP-analysis soil moisture.</>],
    ["Definitions", <>“Breach” = the forecast reaches the training-period <b>P99</b> level: a high-level alert proxy, not an EA flood threshold. False alarms are counted per hourly forecast. 9 <b>gauges</b>, not 9 independent basins (e.g. the Ribble at Samlesbury is downstream of the Calder at Whalley).</>],
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="audit-title"
           className="thin-scroll max-h-[85vh] w-full max-w-3xl overflow-y-auto border border-zinc-700 bg-zinc-950 p-5"
           onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 id="audit-title" className="text-[11px] font-bold tracking-[0.25em] text-accent">MODEL AUDIT &amp; LIMITATIONS</h2>
          <button onClick={onClose} aria-label="Close" className="text-zinc-500 hover:text-zinc-200"><X size={16} /></button>
        </div>
        <p className="mb-4 text-[11px] leading-5 text-zinc-400">
          {manifest.mode}. Every figure is computed from held-out results in <code>eval_harness/</code>; full evidence with file:line
          references is in <code>AUDIT_FLOODPULSE.md</code>.
        </p>
        <dl className="grid grid-cols-[150px_1fr] gap-x-4 gap-y-3 text-[11px] leading-5">
          {items.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="font-bold text-zinc-300">{k}</dt>
              <dd className="text-zinc-400 [&_b]:text-zinc-100">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
