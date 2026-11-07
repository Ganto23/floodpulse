# data/raw — drop real datasets here

UrbanPulse never generates synthetic rows. Every loader reads a real file from this
folder or a real public API, and `/api/status` reports which source was used.

## Pokémon GO (`DATASET_MODE=pokemon`, default)

### Recommended: Kaggle "Predict'em All" (real 2016 spawn telemetry)

```bash
./scripts/fetch_kaggle_predictemall.sh     # -> data/raw/kaggle_predictemall/300k.csv
```

[`semioniy/predictemall`](https://www.kaggle.com/datasets/semioniy/predictemall) contains 296,021 wild-spawn
sightings from 2016-09-02 to 2016-09-08 across about 40 timezone regions. Kaggle lists its license as "Unknown",
so cite it and don't redistribute it. The loader auto-detects the file and handles these quirks:

- **`city` is a timezone region, not a city.** `New_York` covers the whole US East Coast, and its densest
  cluster is in Vermont. `FOCUS_CITY` (default `Prague`) filters by that label, and the pipeline then takes the
  densest metro inside it. Prague is the densest true city cluster, with about 9.3k sightings. Paris (about 5k)
  is a good second choice: `URBANPULSE_FOCUS_CITY=Paris`.
- **`appearedLocalTime` is one global clock, not local time.** It sits exactly 2 h behind `appearedHour` in every
  region. It's treated as UTC; adjust with `URBANPULSE_KAGGLE_TS_UTC_OFFSET_HOURS`.
- **There are no lures**, so the highlight layer is **rare spawns** instead. These are species whose combined
  sightings make up the rarest 5% of the dataset, measured from the data itself.
- **Collection effort isn't constant.** Daily volume peaks on Sep 5–6 and drops sharply on Sep 7–8. Part of the
  late "momentum decay" reflects fewer scans, not fewer players.

### Other sources

The first file found wins:

| File | Format |
|---|---|
| `pokemon_telemetry.csv` | Flat rows, e.g. a RocketMap / PokemonGo-Map `pokestop` or `gym` table export |
| `pokemon_telemetry.json` | A list of records, or `{"pokestops": [...], "gyms": [...]}` |
| `pokestops.geojson` | Point FeatureCollection (community PokéStop maps); properties carry the timestamp |

Columns are matched case-insensitively against these aliases:

- **lat**: `latitude`, `lat` · **lon**: `longitude`, `lon`, `lng`, `long`
- **timestamp** (required): `timestamp`, `last_modified`, `last_updated`, `updated_at`, `date`, `seen_at`, … (ISO strings or epoch s/ms)
- **lure**: `lure_expiration` (lured if it is still active at the observation time), or `lured` / `is_lured` / `active_fort_modifier` (any truthy value)
- **type**: `type` / `kind` / `fort_type` (values containing "gym" become Gyms). Gym-only columns such as `team_id` or `gym_points` also work.
- **value** (optional, defaults to 1): `value`, `count`, `weight`

**If no file is present**, the loader falls back to the real **OpenStreetMap POI layer** for
`TARGET_BBOX` (default: downtown San Francisco) via Overpass. Most PokéStops and Gyms were
originally seeded from these POIs. Each event's timestamp is the POI's real last-edit time.
The status panel then shows the stream as `[DEGRADED] fallback_osm(...)`, so the fallback
is never passed off as scanner telemetry.

## OpenStreetMap infrastructure (optional; otherwise fetched live)

- `osm_infrastructure.geojson`: an Overpass-Turbo GeoJSON export of bus stops, stations and platforms, footways and pedestrian ways, and buildings
- `osm_amenities.geojson`: for `DATASET_MODE=osm`. Point features need a `timestamp` (export with `out meta`)

## Housing (`DATASET_MODE=housing`)

`housing_transactions.csv` needs `lat`/`long` + `date` columns, plus an optional `price` and a
new-build flag (`old_new`, `new_build`, or `yr_built`). This works as-is with King County `kc_house_data.csv`.

## Weather

Nothing to place here. Open-Meteo archive data (ERA5) is pulled for the dataset's bounding box
and cached in `data/cache/`.
