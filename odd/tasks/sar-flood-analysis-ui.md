# SAR / flood analysis UI (ImageExplorer)

Objective: operator can submit `POST /api/v2/geo/gee/analysis` (tipo flood), poll until done, and push before/after tiles into the existing `/mapa` comparison slider. Branch `feat/sar-flood-analysis-ui`. Delivery: ask-on-risk. Runner: vitest.

## Specs

- **S1** — From `/admin/images`, operator submits flood analysis with `tipo: "flood"` and `parametros: { start_date, end_date, method }` where `method` is exactly one of `fusion` | `sar_only` | `optical_only`.
- **S2** — Date semantics match backend `build_flood_analysis_result`: `start_date` = flood/crecida, `end_date` = normal/referencia. For `fusion` comparison tiles, require `(end_date - start_date) >= 1` day (day-to-day deltas are in scope).
- **S3** — Client polls `GET /api/v2/geo/gee/analysis/{id}` until `estado` is `completed` or `failed` (or timeout); does not invent `/analysis/flood-detection*` paths.
- **S4** — On `completed` with `resultado.comparison`, set comparison left = `normal_rgb`, right = `flood_detection` (fallback `flood_rgb`) via existing `setLeftImage`/`setRightImage` → `/mapa` slider.
- **S5** — On `completed` without comparison but with `resultado.sar` (or `optical`), set the flood side from that tile; for `sar_only` also sync-fetch Sentinel-1 `vv_flood` for `end_date` as the normal side when possible.
- **S6** — Focused unit tests cover date-span gate + tile picking from resultado; component test covers submit→poll→setLeft/setRight happy path with mocked `apiFetch`.

## Tasks

- [x] T1 API client + pure helpers (`geeFloodAnalysis.ts`) — S1 S2 S3 S4 S5 — inline
- [x] T2 `ImageExplorerFloodAnalysis` card + wire into `ImageExplorerPanel` — S1 S2 S3 S4 S5 — inline
- [x] T3 Vitest unit + component — S6 — inline — 10 passed

## Log

- **L1** (2026-11-09): User asked to productize SAR flood E2E after audit PARTIAL (API live, zero FE callers to `/gee/analysis`). Spike: form → poll → bind slider. No Lidar.
- **L2** (2026-11-09): Implemented. Vitest 10/10. Browser E2E GEE job deferred to operator (login + GEE quota).
- **L3** (2026-11-09): User: fusion span >5d too strict for marked day-to-day deltas → backend+FE gate lowered to >=1 day.
