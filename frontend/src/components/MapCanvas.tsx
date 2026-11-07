import { useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import type { PickingInfo } from "@deck.gl/core";
import { GeoJsonLayer, LineLayer, PathLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import Map from "react-map-gl/maplibre";
import type { CellFeature, Infrastructure, SpatialFrame } from "../lib/types";
import { fmt, ramp, SIGNAL_RGB } from "../lib/colors";

export type Metric = "realized" | "denoised" | "forecast";
export interface LayerToggles {
  extrude: boolean;
  vectors: boolean;
  catchments: boolean;
  infra: boolean;
  highlights: boolean;
}

const BASEMAP = "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json";

function cellValue(p: CellFeature["properties"], metric: Metric): number {
  return (p[metric] ?? p.forecast ?? p.denoised ?? 0) as number;
}

interface Props {
  frame: SpatialFrame | null;
  infra: Infrastructure | null;
  center: [number, number];
  metric: Metric;
  toggles: LayerToggles;
  highlightLabel: string;
}

export default function MapCanvas({ frame, infra, center, metric, toggles, highlightLabel }: Props) {
  const [hover, setHover] = useState<PickingInfo<CellFeature> | null>(null);

  const max = useMemo(() => {
    if (!frame) return 1;
    return Math.max(1e-9, ...frame.features.map((f) => cellValue(f.properties, metric)));
  }, [frame, metric]);

  const layers = useMemo(() => {
    if (!frame) return [];
    const out = [];
    if (toggles.infra && infra) {
      out.push(
        new PathLayer<[number, number][]>({
          id: "footways", data: infra.paths, getPath: (d) => d,
          getColor: [58, 214, 255, 38], widthMinPixels: 1,
        }),
        new ScatterplotLayer<Infrastructure["transit"][number]>({
          id: "transit", data: infra.transit,
          getPosition: (d) => [d.longitude, d.latitude], getRadius: 14, radiusMinPixels: 1.5,
          getFillColor: [58, 214, 255, 160],
        }),
      );
    }
    out.push(
      new GeoJsonLayer<CellFeature["properties"]>({
        id: "h3-cells",
        data: frame as unknown as GeoJSON.FeatureCollection,
        pickable: true, stroked: true, filled: true,
        extruded: toggles.extrude, wireframe: false,
        getElevation: (f) => 900 * Math.sqrt(cellValue(f.properties, metric) / max),
        getFillColor: (f) => {
          const t = Math.sqrt(cellValue(f.properties, metric) / max);
          return [...ramp(t), 40 + Math.round(180 * t)] as [number, number, number, number];
        },
        getLineColor: (f) => (f.properties.signal ? [...SIGNAL_RGB[f.properties.signal], 255] : [255, 255, 255, 18]) as [number, number, number, number],
        getLineWidth: (f) => (f.properties.signal ? 3 : 1),
        lineWidthUnits: "pixels",
        updateTriggers: { getElevation: [metric, max], getFillColor: [metric, max] },
        onHover: (info) => setHover(info as PickingInfo<CellFeature>),
        transitions: { getElevation: 300, getFillColor: 300 },
      }),
    );
    if (toggles.catchments) {
      const rings = frame.catchments.flatMap((c) =>
        c.rings.flatMap((r) => r.coordinates.map((poly) => ({ poly, k: r.k, type: c.type }))),
      );
      out.push(
        new PolygonLayer<(typeof rings)[number]>({
          id: "catchments", data: rings, filled: false, stroked: true,
          getPolygon: (d) => d.poly,
          getLineColor: (d) => [...SIGNAL_RGB[d.type] ?? [255, 176, 0], 220 - d.k * 50] as [number, number, number, number],
          getLineWidth: 1.5, lineWidthUnits: "pixels",
        }),
      );
    }
    if (toggles.vectors) {
      out.push(
        new LineLayer<SpatialFrame["vectors"][number]>({
          id: "momentum", data: frame.vectors,
          getSourcePosition: (d) => d.from, getTargetPosition: (d) => d.to,
          getColor: (d) => [255, 255, 255, 60 + 180 * d.magnitude], getWidth: (d) => 1 + 2 * d.magnitude,
        }),
        new ScatterplotLayer<SpatialFrame["vectors"][number]>({
          id: "momentum-tips", data: frame.vectors, getPosition: (d) => d.to,
          getRadius: 6, radiusMinPixels: 1.5, getFillColor: [255, 255, 255, 200],
        }),
      );
    }
    if (toggles.highlights) {
      out.push(
        new ScatterplotLayer<SpatialFrame["highlights"][number]>({
          id: "highlights", data: frame.highlights,
          getPosition: (d) => [d.longitude, d.latitude], getRadius: 30, radiusMinPixels: 3,
          getFillColor: [255, 79, 216, 200], stroked: true, getLineColor: [255, 255, 255, 220], lineWidthMinPixels: 1,
        }),
      );
    }
    out.push(
      new ScatterplotLayer<SpatialFrame["signals"][number]>({
        id: "signal-pins", data: frame.signals,
        getPosition: (d) => [d.longitude, d.latitude], getRadius: 45, radiusMinPixels: 4,
        filled: false, stroked: true, lineWidthMinPixels: 2,
        getLineColor: (d) => [...SIGNAL_RGB[d.type], 255] as [number, number, number, number],
      }),
    );
    return out;
  }, [frame, infra, metric, max, toggles]);

  const p = hover?.object?.properties;
  return (
    <div className="relative h-full w-full">
      <DeckGL
        initialViewState={{ latitude: center[0], longitude: center[1], zoom: 13.4, pitch: 45, bearing: -12 }}
        controller layers={layers}
        getCursor={({ isHovering }) => (isHovering ? "crosshair" : "grab")}
      >
        <Map mapStyle={BASEMAP} reuseMaps />
      </DeckGL>

      {p && hover && (
        <div className="pointer-events-none absolute z-10 border border-term-line bg-term-panel/95 px-3 py-2 text-[11px] leading-5 shadow-xl"
             style={{ left: hover.x + 14, top: hover.y + 14 }}>
          <div className="text-term-amber">{p.h3}</div>
          <Row k="REALIZED" v={fmt(p.realized)} />
          <Row k="DENOISED" v={fmt(p.denoised)} />
          <Row k="FORECAST" v={p.forecast == null ? "—" : `${fmt(p.forecast)} [${fmt(p.forecast_lo, 2)}, ${fmt(p.forecast_hi, 2)}]`} />
          <Row k="ΔS/Δt" v={fmt(p.momentum)} />
          {p.signal && <div style={{ color: `rgb(${SIGNAL_RGB[p.signal].join(",")})` }}>▲ {p.signal}</div>}
        </div>
      )}

      <div className="pointer-events-none absolute bottom-3 left-3 border border-term-line bg-term-panel/90 px-3 py-2 text-[10px] text-term-dim">
        <div className="mb-1 uppercase tracking-widest">{frame?.meta.value_label ?? "activity"} · {metric}</div>
        <div className="h-2 w-48" style={{ background: `linear-gradient(90deg, ${[0, 0.25, 0.5, 0.75, 1].map((t) => `rgb(${ramp(t).join(",")})`).join(",")})` }} />
        <div className="mt-1 flex justify-between"><span>0</span><span>{fmt(max)}</span></div>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
          {Object.entries(SIGNAL_RGB).map(([k, c]) => (
            <span key={k}><span style={{ color: `rgb(${c.join(",")})` }}>■</span> {k}</span>
          ))}
          <span><span className="text-term-magenta">●</span> {highlightLabel}</span>
          <span><span className="text-term-cyan">●</span> transit</span>
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-6">
      <span className="text-term-dim">{k}</span>
      <span className="tabular-nums">{v}</span>
    </div>
  );
}
