"""
OpenStreetMap geometry + amenity loaders.

Two responsibilities:
  * OSMInfrastructureLoader — pedestrian paths, transit nodes and building
    footprints for the target bbox (feature layer for the tensor).
  * OSMAmenityLoader        — amenity POIs with their real last-edit timestamps
    (`out meta`) as a StandardSpatialEvent stream. Used for DATASET_MODE="osm"
    and as the graceful fallback for the Pokémon loader (PokéStops are largely
    seeded from the same public POIs).

Sources, in order: local GeoJSON in /data/raw  ->  live Overpass API (cached).
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from config import MAX_OVERPASS_AREA, OVERPASS_URL, RAW_DIR
from loaders.base import BaseDataLoader, LoaderError
from loaders.http import cached_request

log = logging.getLogger(__name__)

BBox = tuple[float, float, float, float]  # south, west, north, east

TRANSIT_TAGS = {
    ("highway", "bus_stop"), ("public_transport", "platform"),
    ("public_transport", "stop_position"), ("public_transport", "station"),
    ("railway", "station"), ("railway", "halt"), ("railway", "tram_stop"),
    ("railway", "subway_entrance"),
}
FOOTWAY_VALUES = {"footway", "pedestrian", "path", "steps", "living_street"}


def clamp_bbox(bbox: BBox, max_area: float = MAX_OVERPASS_AREA) -> tuple[BBox, bool]:
    """Shrink a bbox around its centre so Overpass doesn't reject the query."""
    s, w, n, e = bbox
    area = (n - s) * (e - w)
    if area <= max_area:
        return bbox, False
    scale = math.sqrt(max_area / area)
    cy, cx = (s + n) / 2, (w + e) / 2
    hh, hw = (n - s) * scale / 2, (e - w) * scale / 2
    return (cy - hh, cx - hw, cy + hh, cx + hw), True


def _bbox_str(b: BBox) -> str:
    return f"{b[0]:.5f},{b[1]:.5f},{b[2]:.5f},{b[3]:.5f}"


def overpass(query: str, namespace: str) -> tuple[dict, bool]:
    return cached_request(namespace, "POST", OVERPASS_URL, data={"data": query})


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------- #
# Infrastructure
# --------------------------------------------------------------------------- #
@dataclass
class OSMInfrastructure:
    transit: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["latitude", "longitude", "kind", "name"]))
    # one row per footway segment midpoint, carrying segment length in metres
    footways: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["latitude", "longitude", "length_m"]))
    buildings: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["latitude", "longitude"]))
    paths: list[list[list[float]]] = field(default_factory=list)  # [[lon,lat],...] polylines for UI
    source: str = "none"
    online: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def node_count(self) -> int:
        return len(self.transit) + len(self.footways) + len(self.buildings)


class OSMInfrastructureLoader:
    local_file = "osm_infrastructure.geojson"

    def __init__(self, bbox: BBox) -> None:
        self.bbox, clamped = clamp_bbox(bbox)
        self.result = OSMInfrastructure()
        if clamped:
            self.result.notes.append("bbox clamped to Overpass-safe area around data centroid")

    def load(self) -> OSMInfrastructure:
        local = RAW_DIR / self.local_file
        try:
            if local.exists():
                self._from_geojson(local)
                self.result.source = f"local:{local.name}"
            else:
                self._from_overpass()
            self.result.online = self.result.node_count > 0
        except Exception as exc:  # network or parse failure: report, don't fabricate
            log.exception("OSM infrastructure load failed")
            self.result.notes.append(f"load failed: {exc}")
        return self.result

    def _from_overpass(self) -> None:
        b = _bbox_str(self.bbox)
        q = f"""
        [out:json][timeout:90];
        (
          node["highway"="bus_stop"]({b});
          node["public_transport"~"^(platform|stop_position|station)$"]({b});
          node["railway"~"^(station|halt|tram_stop|subway_entrance)$"]({b});
        );
        out body;
        way["highway"~"^(footway|pedestrian|path|steps|living_street)$"]({b});
        out geom;
        way["building"]({b});
        out center;
        """
        payload, cached = overpass(q, "overpass_infra")
        self.result.source = "overpass:cache" if cached else "overpass:live"
        self._ingest_elements(payload.get("elements", []))

    def _ingest_elements(self, elements: list[dict]) -> None:
        transit, foot, bld = [], [], []
        for el in elements:
            tags = el.get("tags", {}) or {}
            if el.get("type") == "node" and any((k, tags.get(k)) in TRANSIT_TAGS for k in tags):
                kind = next(f"{k}={tags[k]}" for k in tags if (k, tags.get(k)) in TRANSIT_TAGS)
                transit.append((el["lat"], el["lon"], kind, tags.get("name", "")))
            elif el.get("type") == "way" and tags.get("highway") in FOOTWAY_VALUES and el.get("geometry"):
                geom = el["geometry"]
                self.result.paths.append([[p["lon"], p["lat"]] for p in geom])
                for a, c in zip(geom, geom[1:]):
                    foot.append(((a["lat"] + c["lat"]) / 2, (a["lon"] + c["lon"]) / 2,
                                 haversine_m(a["lat"], a["lon"], c["lat"], c["lon"])))
            elif el.get("type") == "way" and "building" in tags and el.get("center"):
                bld.append((el["center"]["lat"], el["center"]["lon"]))
        self.result.transit = pd.DataFrame(transit, columns=["latitude", "longitude", "kind", "name"])
        self.result.footways = pd.DataFrame(foot, columns=["latitude", "longitude", "length_m"])
        self.result.buildings = pd.DataFrame(bld, columns=["latitude", "longitude"])

    def _from_geojson(self, path: Path) -> None:
        """Accepts an Overpass-Turbo GeoJSON export of the same query."""
        gj = json.loads(path.read_text())
        transit, foot, bld = [], [], []
        for feat in gj.get("features", []):
            props = feat.get("properties", {}) or {}
            tags = props.get("tags", props)
            geom = feat.get("geometry") or {}
            gtype, coords = geom.get("type"), geom.get("coordinates")
            if not coords:
                continue
            if gtype == "Point" and any((k, tags.get(k)) in TRANSIT_TAGS for k in tags):
                kind = next(f"{k}={tags[k]}" for k in tags if (k, tags.get(k)) in TRANSIT_TAGS)
                transit.append((coords[1], coords[0], kind, tags.get("name", "")))
            elif gtype == "LineString" and tags.get("highway") in FOOTWAY_VALUES:
                self.result.paths.append(coords)
                for a, c in zip(coords, coords[1:]):
                    foot.append(((a[1] + c[1]) / 2, (a[0] + c[0]) / 2, haversine_m(a[1], a[0], c[1], c[0])))
            elif gtype in ("Polygon", "MultiPolygon") and "building" in tags:
                ring = coords[0] if gtype == "Polygon" else coords[0][0]
                lon = sum(p[0] for p in ring) / len(ring)
                lat = sum(p[1] for p in ring) / len(ring)
                bld.append((lat, lon))
        self.result.transit = pd.DataFrame(transit, columns=["latitude", "longitude", "kind", "name"])
        self.result.footways = pd.DataFrame(foot, columns=["latitude", "longitude", "length_m"])
        self.result.buildings = pd.DataFrame(bld, columns=["latitude", "longitude"])


# --------------------------------------------------------------------------- #
# Amenity event stream
# --------------------------------------------------------------------------- #
class OSMAmenityLoader(BaseDataLoader):
    """Real OSM POIs; timestamp = real last-edit time from OSM metadata."""

    name = "osm_amenities"
    local_file = "osm_amenities.geojson"

    def __init__(self, bbox: BBox) -> None:
        super().__init__()
        self.bbox, clamped = clamp_bbox(bbox)
        if clamped:
            self.report.notes.append("bbox clamped to Overpass-safe area")

    def load_data(self) -> pd.DataFrame:
        local = RAW_DIR / self.local_file
        if local.exists():
            df = self._from_geojson(local)
            self.report.source, self.report.path = "local_geojson", str(local)
        else:
            b = _bbox_str(self.bbox)
            q = f"""
            [out:json][timeout:90];
            (
              node["amenity"]({b});
              node["tourism"~"^(artwork|attraction|museum|viewpoint|gallery)$"]({b});
              node["historic"]({b});
              node["leisure"~"^(park|playground|fitness_station)$"]({b});
            );
            out meta;
            """
            try:
                payload, cached = overpass(q, "overpass_amenity")
            except Exception as exc:
                raise LoaderError(f"Overpass amenity query failed and no local {self.local_file}: {exc}") from exc
            self.report.source = "overpass:cache" if cached else "overpass:live"
            df = self._from_elements(payload.get("elements", []))
        self.report.online = True
        return self.standardize(df)

    @staticmethod
    def _category(tags: dict) -> str:
        for k in ("amenity", "tourism", "historic", "leisure"):
            if k in tags:
                return f"{k}:{tags[k]}"
        return "poi"

    def _from_elements(self, elements: list[dict]) -> pd.DataFrame:
        rows = [
            {
                "latitude": el.get("lat"), "longitude": el.get("lon"),
                "timestamp": el.get("timestamp"), "value": 1.0,
                "category": self._category(el.get("tags", {}) or {}),
            }
            for el in elements if el.get("type") == "node"
        ]
        if not rows:
            raise LoaderError("Overpass returned zero amenity nodes for bbox")
        return pd.DataFrame(rows)

    def _from_geojson(self, path: Path) -> pd.DataFrame:
        gj = json.loads(path.read_text())
        rows = []
        for feat in gj.get("features", []):
            geom = feat.get("geometry") or {}
            if geom.get("type") != "Point":
                continue
            props = feat.get("properties", {}) or {}
            meta = props.get("meta", {}) or {}
            ts = props.get("timestamp") or meta.get("timestamp") or props.get("@timestamp")
            rows.append({
                "latitude": geom["coordinates"][1], "longitude": geom["coordinates"][0],
                "timestamp": ts, "value": 1.0,
                "category": self._category(props.get("tags", props)),
            })
        if not rows:
            raise LoaderError(f"{path.name} contains no Point features with timestamps")
        return pd.DataFrame(rows)
