import { useEffect, useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import { FlyToInterpolator, type PickingInfo } from "@deck.gl/core";
import { LineLayer, ScatterplotLayer, SolidPolygonLayer, TextLayer } from "@deck.gl/layers";
import Map from "react-map-gl/maplibre";
import { m } from "../lib/data";
import { RISK_STYLE, type RiskRow } from "../lib/risk";
import type { GaugeMeta, Geometry } from "../lib/types";

// Free dark basemap (MapLibre-compatible; swap for a Mapbox style URL + token if preferred)
const BASEMAP = "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json";
type Row = RiskRow & { g: GaugeMeta };
type Cell = { poly: [number, number][]; z: number; slug: string };
type Seg = { a: [number, number]; b: [number, number]; w: number; slug: string };

export default function BasinMap({ gauges, geometry, selected, mesh, onSelect }: {
  gauges: Row[]; geometry: Record<string, Geometry>; selected: GaugeMeta | null; mesh: boolean; onSelect: (s: string) => void;
}) {
  const [view, setView] = useState<Record<string, unknown>>({ latitude: 54.25, longitude: -2.45, zoom: 7.3, pitch: 35, bearing: 0 });
  const [hover, setHover] = useState<PickingInfo<Row> | null>(null);

  useEffect(() => {
    if (selected) setView((v) => ({ ...v, latitude: selected.lat, longitude: selected.lon, zoom: 9.3,
                                    transitionDuration: 900, transitionInterpolator: new FlyToInterpolator() }));
  }, [selected]);

  const { cells, segs, zmax } = useMemo(() => {
    const cells: Cell[] = [], segs: Seg[] = [];
    let zmax = 1;
    for (const [slug, geo] of Object.entries(geometry)) {
      const [dlat, dlon] = geo.cell_deg;
      // snap to an exact grid so neighbouring cells share edges (exported coords are rounded → seams)
      const [lon0, lat0] = geo.cells.length ? geo.cells[0] : [0, 0];
      for (const [lon, lat, z] of geo.cells) {
        const i = Math.round((lon - lon0) / dlon), j = Math.round((lat - lat0) / dlat);
        const x0 = lon0 + (i - 0.5) * dlon, x1 = lon0 + (i + 0.5) * dlon, y0 = lat0 + (j - 0.5) * dlat, y1 = lat0 + (j + 0.5) * dlat;
        cells.push({ slug, z, poly: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]] });
        zmax = Math.max(zmax, z);
      }
      for (const [x0, y0, x1, y1, la] of geo.channels) segs.push({ a: [x0, y0], b: [x1, y1], w: la, slug });
    }
    return { cells, segs, zmax };
  }, [geometry]);

  const sel = selected?.slug;
  const selCells = useMemo(() => cells.filter((c) => c.slug === sel), [cells, sel]);
  const layers = [
    mesh && new SolidPolygonLayer<Cell>({
      // selected catchment only: nested catchments (Ribble ⊃ Calder·Whalley) on different grids would moiré
      id: "dem-mesh", data: selCells, getPolygon: (d) => d.poly,
      // sequential single hue (blue ramp) by elevation
      getFillColor: (d) => { const t = d.z / zmax; return [28 + 60 * t, 92 + 90 * t, 171 + 70 * t, 60]; },
      updateTriggers: { getFillColor: [zmax] },
    }),
    new LineLayer<Seg>({
      id: "channels-glow", data: segs, getSourcePosition: (d) => d.a, getTargetPosition: (d) => d.b,
      getColor: (d) => [34, 211, 238, d.slug === sel ? 70 : 30], getWidth: (d) => 2 + d.w * 2.2, widthUnits: "pixels",
      updateTriggers: { getColor: [sel] },
    }),
    new LineLayer<Seg>({
      id: "channels", data: segs, getSourcePosition: (d) => d.a, getTargetPosition: (d) => d.b,
      getColor: (d) => [165, 243, 252, d.slug === sel ? 230 : 120], getWidth: (d) => 0.6 + d.w * 0.6, widthUnits: "pixels",
      updateTriggers: { getColor: [sel] },
    }),
    new ScatterplotLayer<Row>({
      id: "gauge-halo", data: gauges.filter((r) => r.risk === "crit" || r.risk === "warn"),
      getPosition: (r) => [r.g.lon, r.g.lat], getRadius: 18, radiusUnits: "pixels",
      getFillColor: (r) => [...RISK_STYLE[r.risk].rgb, 60] as [number, number, number, number],
    }),
    new ScatterplotLayer<Row>({
      id: "gauges", data: gauges, pickable: true, getPosition: (r) => [r.g.lon, r.g.lat],
      getRadius: (r) => (r.g.slug === sel ? 9 : 6), radiusUnits: "pixels", stroked: true, lineWidthUnits: "pixels",
      getFillColor: (r) => [...RISK_STYLE[r.risk].rgb, 255] as [number, number, number, number],
      getLineColor: (r) => (r.g.slug === sel ? [34, 211, 238, 255] : [9, 9, 11, 255]), getLineWidth: 2,
      onClick: (info) => info.object && onSelect(info.object.g.slug), onHover: setHover,
      updateTriggers: { getRadius: [sel], getLineColor: [sel] },
    }),
    new TextLayer<Row>({
      id: "labels", data: gauges, getPosition: (r) => [r.g.lon, r.g.lat], getText: (r) => r.g.name.split(" · ")[0],
      getSize: 11, getColor: [212, 212, 216, 220], getPixelOffset: [18, 0], getTextAnchor: "start",
      fontFamily: "JetBrains Mono, monospace", characterSet: "auto",
    }),
  ].filter(Boolean);

  const o = hover?.object;
  return (
    <div className="relative h-full w-full">
      <DeckGL viewState={view} onViewStateChange={({ viewState }) => setView(viewState as Record<string, unknown>)}
              controller layers={layers} getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}>
        <Map mapStyle={BASEMAP} reuseMaps />
      </DeckGL>
      {o && hover && (
        <div className="pointer-events-none absolute z-10 border border-zinc-700 bg-zinc-950/95 px-3 py-2 text-[11px] leading-5"
             style={{ left: hover.x + 12, top: hover.y + 12 }}>
          <div className="text-accent">{o.g.name}</div>
          <div className={RISK_STYLE[o.risk].text}>{RISK_STYLE[o.risk].label}</div>
          <div className="text-zinc-400">level <span className="text-zinc-100">{m(o.obs)} m</span> · peak <span className="text-zinc-100">{m(o.peak)} m</span></div>
          <div className="text-zinc-400">P95 {m(o.g.p95_mm)} · P99 {m(o.g.p99_mm)} m · DEM lag {o.g.dem_tc_h.toFixed(1)} h</div>
        </div>
      )}
      <div className="pointer-events-none absolute bottom-3 left-3 border border-zinc-800 bg-zinc-950/90 px-3 py-2 text-[10px] text-zinc-400">
        {(["crit", "warn", "ok"] as const).map((k) => (
          <span key={k} className="mr-3"><span className={`mr-1 inline-block h-2 w-2 rounded-full ${RISK_STYLE[k].dot}`} />{RISK_STYLE[k].label}</span>
        ))}
        <span className="mr-3 text-cyan-300">━ D8 channel (≥1% catchment area)</span>
        {mesh && <span>▦ DEM mesh · selected catchment</span>}
      </div>
    </div>
  );
}
