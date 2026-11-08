import { useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import type { PickingInfo } from "@deck.gl/core";
import { LineLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import Map from "react-map-gl/maplibre";
import { m } from "../lib/data";
import type { RiskRow } from "../lib/risk";
import type { GaugeMeta, Geometry, Risk } from "../lib/types";
import { displayName } from "./names";

// Free dark basemap (MapLibre-compatible; swap for a Mapbox style URL + token if preferred).
// It is softened with a CSS brightness filter in index.css so it isn't pure black.
const BASEMAP = "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json";
const PIN: Record<Risk, [number, number, number]> = { crit: [207, 100, 97], warn: [201, 162, 78], ok: [90, 160, 112], none: [124, 130, 141] };
type Row = RiskRow & { g: GaugeMeta };
type Seg = { a: [number, number]; b: [number, number]; w: number; slug: string };

/** Clean map: river channels traced from terrain (soft glow) + one pin per gauge. */
export default function BasinMap({ gauges, geometry, selected, onSelect }: {
  gauges: Row[]; geometry: Record<string, Geometry>; selected: GaugeMeta | null; onSelect: (s: string) => void;
}) {
  const [view, setView] = useState<Record<string, unknown>>({ latitude: 54.32, longitude: -2.45, zoom: 7.45, pitch: 0, bearing: 0 });
  const [hover, setHover] = useState<PickingInfo<Row> | null>(null);


  const segs = useMemo(() => {
    const out: Seg[] = [];
    for (const [slug, geo] of Object.entries(geometry))
      for (const [x0, y0, x1, y1, la] of geo.channels) out.push({ a: [x0, y0], b: [x1, y1], w: la, slug });
    return out;
  }, [geometry]);

  const sel = selected?.slug;
  const layers = [
    new LineLayer<Seg>({
      id: "river-glow", data: segs, getSourcePosition: (d) => d.a, getTargetPosition: (d) => d.b,
      getColor: [86, 135, 207, 45], getWidth: (d) => 3 + d.w * 2.4, widthUnits: "pixels",
    }),
    new LineLayer<Seg>({
      id: "rivers", data: segs, getSourcePosition: (d) => d.a, getTargetPosition: (d) => d.b,
      getColor: [140, 172, 214, 170], getWidth: (d) => 0.7 + d.w * 0.6, widthUnits: "pixels",
    }),
    new ScatterplotLayer<Row>({
      id: "pins", data: gauges, pickable: true, getPosition: (r) => [r.g.lon, r.g.lat],
      getRadius: (r) => (r.g.slug === sel ? 9 : 6), radiusUnits: "pixels", stroked: true, lineWidthUnits: "pixels",
      getFillColor: (r) => PIN[r.risk], getLineColor: (r) => (r.g.slug === sel ? [201, 204, 211, 255] : [26, 29, 35, 255]),
      getLineWidth: 2, onClick: (info) => info.object && onSelect(info.object.g.slug), onHover: setHover,
      updateTriggers: { getRadius: [sel], getLineColor: [sel] },
    }),
    new TextLayer<Row>({
      id: "labels", data: gauges, getPosition: (r) => [r.g.lon, r.g.lat],
      getText: (r) => displayName(r.g.slug, r.g.name).replace(/^River /, "").replace(/ \(.*\)$/, ""),
      getSize: 11, getColor: [170, 175, 185, 220], getPixelOffset: [14, 0], getTextAnchor: "start",
      fontFamily: "JetBrains Mono, monospace", characterSet: "auto",
    }),
  ];

  const o = hover?.object;
  return (
    <div className="relative h-full w-full">
      <DeckGL viewState={view} onViewStateChange={({ viewState }) => setView(viewState as Record<string, unknown>)}
              controller layers={layers} getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}>
        <Map mapStyle={BASEMAP} reuseMaps />
      </DeckGL>
      {o && hover && (
        <div className="pointer-events-none absolute z-10 border border-line bg-panel px-3 py-2 text-[11px] leading-5"
             style={{ left: hover.x + 12, top: hover.y + 12 }}>
          <div className="text-ink">{displayName(o.g.slug, o.g.name)}</div>
          <div className="text-dim">{m(o.obs)}m → {m(o.peak)}m</div>
        </div>
      )}
    </div>
  );
}
