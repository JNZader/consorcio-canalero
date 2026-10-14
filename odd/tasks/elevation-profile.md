# Elevation profile (GLO-30) — public access

Google Earth-style distance vs elevation for a LineString. Public visitors see
published canal/road traces **and** a hand-drawn line; AW3D30/NASADEM stay
operator-only.

## Specs

- **S1** — `POST /api/v2/public/map/elevation-profile` is anonymous: same body
  as the operator route (`geometry` LineString EPSG:4326, optional `area_id`),
  no auth required.
- **S2** — The public route **never** samples GEE: `compare_dems` is forced
  `False`. AW3D30/NASADEM remain reachable only through the authenticated
  `POST /api/v2/geo/elevation-profile`.
- **S3** — Product series is unchanged: local `dem_filled.tif` (Copernicus
  GLO-30), plus MDE-Ar only when the sibling tif exists. Disclaimer stays
  "Perfil sobre Copernicus GLO-30 (~30 m). No es cota de proyecto ni sección de
  canal."
- **S4** — Caps stay as-is: 200 km max length, 2000 sampled points, nodata stays
  `null`. No new constant.
- **S5** — The chart is visible in `InfoPanel` for every visitor (canal,
  camino, or drawn trace). The operator-only "Comparar DEMs (GEE)" checkbox
  still appears after the first sample and still needs a session.

## Tasks

- [ ] T1 Public anonymous route + forced `compare_dems=False` — `S1`,`S2` — PR feat/public-elevation-profile
- [ ] T2 Frontend uses the public route when GEE is not requested — `S1`,`S2`,`S5`
- [ ] T3 Drop the `canSeeElevation` gate in `InfoPanel` — `S5`
- [ ] T4 Tests: anonymous 200, GEE never called, POST spends the generic rate budget — `S1`–`S4`
- [ ] T5 Docs: this file + `docs/ROADMAP.md` note - `S1`

## Log

- **L1** (original): elevation profile requested for operator use only — shipped
  as `POST /api/v2/geo/elevation-profile` behind `_require_operator`.
- **L2** (2026-10-14): "me interesa que se pueda ver de todo...osea canal/camino
  publicado y traza hecha a mano" — reverses the previous non-goal "public
  unauthenticated route". Public table therefore keeps GEE off and relies on the
  generic 100/60 per-IP rate limit (POST is not in `PUBLIC_MAP_GET_EXACT`).
