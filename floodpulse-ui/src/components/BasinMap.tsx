import { useEffect, useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import { FlyToInterpolator, type PickingInfo } from "@deck.gl/core";
import { LineLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import Map from "react-map-gl/maplibre";
import { m } from "../lib/data";
import type { RiskRow } from "../lib/risk";
import type { GaugeMeta, Geometry, Risk } from "../lib/types";
import { mapLabel, nameParts } from "./names";

// Dark vector basemap (MapLibre). To use Mapbox: swap in a mapbox:// style URL and pass mapboxAccessToken.
const BASEMAP = "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json";
const VIEW = { latitude: 54.32, longitude: -2.45, zoom: 7.45, pitch: 0, bearing: 0 };   // all gauges in frame
const PIN: Record<Risk, [number, number, number]> = { crit: [248, 113, 113], warn: [251, 191, 36], ok: [74, 222, 128], none: [100, 116, 139] };
type Row = RiskRow & { g: GaugeMeta };

/** Recolour the basemap to the slate theme: land slate-900, water slate-950, roads/borders muted. */
function slateBasemap(map: { getStyle: () => { layers?: { id: string; type: string }[] }; setPaintProperty: (id: string, k: string, v: unknown) => void }) {
  for (const l of map.getStyle().layers ?? []) {
    try {
      if (l.type === "background") map.setPaintProperty(l.id, "background-color", "#131c2e");
      else if (l.type === "fill" && /water/.test(l.id)) map.setPaintProperty(l.id, "fill-color", "#0b1220");
      else if (l.type === "fill") map.setPaintProperty(l.id, "fill-color", "#162036");
      else if (l.type === "line" && /water|river/.test(l.id)) map.setPaintProperty(l.id, "line-color", "#0b1220");
      else if (l.type === "line") map.setPaintProperty(l.id, "line-color", "#25314a");
    } catch { /* layer without that paint property */ }
  }
}
type Seg = { a: [number, number]; b: [number, number]; w: number; slug: string };

/**
 * River channels traced from terrain (D8 flow routing on SRTM) with a soft glow, plus one pin per gauge.
 * Selecting a gauge highlights its river network and gives its pin a pulsing ring (cyan, or red if forecast to flood).
 * `focus` changes (a card or preset click) fly the camera to that gauge; the page opens on the full overview.
 */
export default function BasinMap({ gauges, geometry, selected, onSelect, focus }: {
  gauges: Row[]; geometry: Record<string, Geometry>; selected: string | null; onSelect: (s: string) => void;
  focus: { slug: string; n: number } | null;
}) {
  const [view, setView] = useState<Record<string, unknown>>(VIEW);
  const fly = (to: Record<string, number>) => setView((v) => ({ ...v, ...to, transitionDuration: 1800,
    transitionInterpolator: new FlyToInterpolator({ speed: 0.8 }) }));
  useEffect(() => {
    const g = focus && gauges.find((r) => r.g.slug === focus.slug)?.g;
    if (g) fly({ latitude: g.lat, longitude: g.lon, zoom: 9.2 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.n]);
  const [hover, setHover] = useState<PickingInfo<Row> | null>(null);
  const flooding = useMemo(() => gauges.filter((r) => r.risk === "crit"), [gauges]);
  const sel = gauges.find((r) => r.g.slug === selected);
  const selFlood = sel?.risk === "crit";
  const [ms, setMs] = useState(0);                   // animation clock for the pulsing rings
  useEffect(() => {
    let raf = 0;
    const tick = (t: number) => { setMs(t); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  const phase = (ms % 1600) / 1600;                  // flood rings: 1.6 s
  const selPhase = (ms % (selFlood ? 900 : 1800)) / (selFlood ? 900 : 1800);   // selected ring: faster when flooding

  const segs = useMemo(() => {
    const out: Seg[] = [];
    for (const [slug, geo] of Object.entries(geometry))
      for (const [x0, y0, x1, y1, la] of geo.channels) out.push({ a: [x0, y0], b: [x1, y1], w: la, slug });
    return out;
  }, [geometry]);

  const layers = [
    new LineLayer<Seg>({
      id: "river-glow", data: segs, getSourcePosition: (d) => d.a, getTargetPosition: (d) => d.b,
      getColor: (d) => (d.slug === selected ? [34, 195, 220, 70] : [56, 189, 248, 22]), getWidth: (d) => 3 + d.w * 2.6, widthUnits: "pixels",
      updateTriggers: { getColor: [selected] },
    }),
    new LineLayer<Seg>({
      id: "rivers", data: segs, getSourcePosition: (d) => d.a, getTargetPosition: (d) => d.b,
      getColor: (d) => (d.slug === selected ? [165, 236, 246, 230] : [125, 165, 200, 120]), getWidth: (d) => 0.7 + d.w * 0.6, widthUnits: "pixels",
      updateTriggers: { getColor: [selected] },
    }),
    // pulsing red ring on gauges forecast to reach their flood alert threshold
    new ScatterplotLayer<Row>({
      id: "flood-pulse", data: flooding, getPosition: (r) => [r.g.lon, r.g.lat],
      filled: false, stroked: true, radiusUnits: "pixels", lineWidthUnits: "pixels",
      getRadius: 8 + 20 * phase, getLineWidth: 2.5, getLineColor: [248, 113, 113, Math.round(220 * (1 - phase))],
      updateTriggers: { getRadius: [phase], getLineColor: [phase] },
    }),
    // selected gauge: a larger double ring so a card click visibly connects to its pin
    new ScatterplotLayer<Row>({
      id: "selected-ring", data: sel ? [sel] : [], getPosition: (r) => [r.g.lon, r.g.lat],
      filled: false, stroked: true, radiusUnits: "pixels", lineWidthUnits: "pixels",
      getRadius: 12 + 26 * selPhase, getLineWidth: 3,
      getLineColor: [...(selFlood ? [248, 113, 113] : [6, 182, 212]), Math.round(255 * (1 - selPhase))] as [number, number, number, number],
      updateTriggers: { getRadius: [selPhase], getLineColor: [selPhase, selFlood] },
    }),
    new ScatterplotLayer<Row>({
      id: "selected-halo", data: sel ? [sel] : [], getPosition: (r) => [r.g.lon, r.g.lat],
      filled: false, stroked: true, radiusUnits: "pixels", lineWidthUnits: "pixels", getRadius: 13, getLineWidth: 2,
      getLineColor: selFlood ? [248, 113, 113, 255] : [6, 182, 212, 255], updateTriggers: { getLineColor: [selFlood] },
    }),
    new ScatterplotLayer<Row>({
      id: "pins", data: gauges, pickable: true, getPosition: (r) => [r.g.lon, r.g.lat],
      getRadius: (r) => (r.g.slug === selected ? 9 : 6), radiusUnits: "pixels", stroked: true, lineWidthUnits: "pixels",
      getFillColor: (r) => PIN[r.risk], getLineColor: (r) => (r.g.slug === selected ? [226, 232, 240, 255] : [15, 23, 42, 255]),
      getLineWidth: 2, onClick: (info) => info.object && onSelect(info.object.g.slug), onHover: setHover,
      updateTriggers: { getRadius: [selected], getLineColor: [selected] },
    }),
    new TextLayer<Row>({
      id: "labels", data: gauges, getPosition: (r) => [r.g.lon, r.g.lat],
      getText: (r) => mapLabel(r.g.slug, r.g.name),
      getSize: 12, getColor: (r) => (r.g.slug === selected ? [226, 232, 240, 255] : [148, 163, 184, 220]),
      getPixelOffset: (r) => (r.g.slug === "cragg_dauber_bridge" ? [14, 9] : r.g.slug === "calder_mytholmroyd" ? [14, -7] : [14, 0]), getTextAnchor: "start", fontFamily: "Inter, sans-serif", characterSet: "auto",
      updateTriggers: { getColor: [selected] },
    }),
  ];

  const o = hover?.object;
  return (
    <div className="relative h-full w-full">
      <DeckGL viewState={view} onViewStateChange={({ viewState }) => setView(viewState as Record<string, unknown>)}
              controller layers={layers} getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}>
        <Map mapStyle={BASEMAP} reuseMaps onLoad={(e) => slateBasemap(e.target)} />
      </DeckGL>
      <button onClick={() => fly(VIEW)}
              className="absolute right-3 top-3 rounded-md border border-slate-700 bg-slate-900/90 px-3 py-1.5 text-[12px] text-slate-300 hover:border-slate-500 hover:text-slate-100">
        All gauges
      </button>
      {o && hover && (
        <div className="pointer-events-none absolute z-10 rounded-md border border-slate-700 bg-slate-900/95 px-3 py-2 text-[12px]"
             style={{ left: hover.x + 12, top: hover.y + 12 }}>
          <div className="text-slate-100">{nameParts(o.g.slug, o.g.name).join(" · ")}</div>
          <div className="font-mono text-slate-400">{m(o.obs)} m → {m(o.peak)} m</div>
        </div>
      )}
    </div>
  );
}
