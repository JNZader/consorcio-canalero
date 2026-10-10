# explorer-probar-este

Worktree: `/home/javier/programacion/worktrees/consorcio-probar-este`
Branch: `feat/explorer-probar-este` from `origin/main` `da08e7d4`

## Goal

Operator Extreme Events cards show the persisted GEE shortlist and **Probar este** loads that scene (sensor + date + visualization), then **Usar esta imagen** still publishes. Keep **Buscar imagen** (historic-flood composite).

## Tasks

- [x] T1 — Cards render ranked Probar este; click calls try-shortlist. Tests first.
- [x] T2 — Controller fetches `/historic-floods/{id}/candidates` and loads the scene with explicit sensor/date (suppress day-fetch). Tests.
- [x] T3 — Focused vitest + work-unit commit.

## Non-goals

- Batch backend endpoint
- Auto-publish
- QGIS render / L7 gap-fill
- PgBouncer CLI fix
