# Consorcio Canalero

Operational contract for this repository. `CLAUDE.md` is the local developer
setup. Where the two disagree about the Hetzner box, this file wins.

This is Consorcio Canalero 10 de Mayo. It is not biogas-platform. Both stacks
run on the same VPS. Consorcio commands stay in the consorcio checkout and
only name containers that start with `consorcio-`.

## Box deploy

The box is updated by `scripts/deploy-box.sh`, run on the box. The laptop does
not build or push these images.

The script builds `backend`, `worker`, `celery-beat`, and `geo-worker` locally.
It does not publish to GHCR, does not set `ENABLE_PRODUCTION_DEPLOY`, and does
not deploy the frontend. It saves the box `docker-compose.yml` and restores it
after `git reset --hard origin/main`. The compose on `origin/main` is the
development file.

It does not run Alembic. Schema changes are a separate, explicit step.

On 2026-10-24 the live database stamp was `0033_one_way_profile`. The image
running there reports that revision as `(head)` because the image predates
`conocimiento_008`. On current `main`, `conocimiento_008` revises
`0033_one_way_profile` and is the only Alembic head. `alembic upgrade head`
from a current checkout against that database would apply `conocimiento_008`.
Do not add that command to the deploy script.

`geo-worker` bind-mounts `gee-backend/app` and runs as uid 100. The checkout
inside the script uses `umask 022`. A tree left at mode `600` makes the worker
fail to import (`PermissionError` on `config.py` was the observed case). The
public tile proxy turns a worker status `>= 400` into `204`. MapLibre then
draws flat terrain. The health probe is `python -m app.healthcheck` inside
`consorcio-backend`. A curl to `127.0.0.1:8000/health` returns `400` because
the host header is rejected.

## Map stack

One map engine, one tile stack, no proprietary mapping platforms. The reasons
are part of the rule; a ban without them rots.

- **MapLibre GL only** for every map. No Leaflet, no OpenLayers. The app leans
  on the style spec's data-driven expressions, `setFeatureState` (selection
  highlighting), and the 3D terrain built from our own terrain-RGB tiles
  (`tile_service_support.py`). A second engine would duplicate interaction
  logic and double the bug surface; client-side reprojection (OpenLayers'
  strength) is useless here because measurement runs server-side in
  EPSG:32720.
- **Martin (PostGIS MVT via the `vt_*` views) + PMTiles on the CDN + the
  geo-worker raster tile service.** No self-hosted GeoServer: a JVM on a
  single compose box adds ops burden and attack surface with zero capability
  this stack lacks.
- **No ArcGIS platform or SDK.** Per-credit licensing and data lock-in are
  disqualifying for a public consortium.
- **Esri basemap imagery is allowed ONLY as the interactive map's basemap,
  with attribution** (`TILE_LAYERS.satellite` in
  `consorcio-web/src/constants/mapStyles.ts` — Maxar/Earthstar aerial,
  sub-meter). This is a deliberate, documented exception: sub-meter aerial
  beats a 10 m Sentinel-2 basemap for parcel-level orientation, and no
  provincial replacement is verified yet.
- **Esri imagery is banned in derived products** (report PDFs, KMZ exports,
  offline field packages). Esri terms restrict bulk caching/redistribution,
  and the reports' contract is dated provenance — a 2025-09-05 water mask
  cannot sit on an aerial mosaic of unknown date. Derived products use our
  own dated Sentinel-2/Landsat imagery via GEE.

## Live-contract testing rule

Mocked tests prove internal logic; they CANNOT prove an external API's
contract (keyword names, asset loading patterns, band validation, projection
handling, error shapes). Seven layers of mock-passed bugs shipped to
production in one feature before this rule existed (the GEE thumbnail onion,
PRs #753-#760, 2026-11-20). The same lesson was already paid with IDECOR
WFS/WCS (the `IDECOR_LIVE=1` test exists for that reason).

For EVERY integration with an external API (GEE, IDECOR, any third-party
service), there MUST be at least one opt-in live test that exercises the
real API surface. The test:

- lives in `tests/unit/` (no DB fixture dependency) or a dedicated file
- is skipped by default (`GEE_LIVE=1`, `IDECOR_LIVE=1`, etc. — opt-in)
- calls the REAL service with REAL credentials (the box's or dev .env)
- asserts on the REAL response (bytes, structure, format — not just "no
  exception")
- runs at least once before the first production deploy of the feature,
  and after any change to the integration code

The mocked tests stay — they are fast and catch internal regressions. But
green mocks + no live test = UNTESTED against reality.

## Flags

`conocimiento_normas_enabled` defaults to false in `gee-backend/app/config.py`.
Leave it off. Do not ingest the production corpus as part of unrelated work.
