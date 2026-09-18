# Conducción paralela (cuneta de hecho)

## Objective

Surface D8 flow that runs **alongside** a road as a first-class unranked kind
(`conduccion`), drawn as along-road arrows, with the nearest downhill canal
crossing on the same segment as optional sink. Do **not** put these rows in
the `flujo_natural` ranking.

## Problem

O.1 ranked crossings drop θ < 22.5° as `flujo_paralelo`. On zona_principal
that discarded 162 events (vs 361 ranked crossings). Those events are the
road conveying water in the ditch — the operational dynamics, not a failed
crossing.

## Why

Operators (APRHI / T269-03) need to see water running WITH the road toward a
canal. Mixing that into the ranked crossing list would treat conveyance as a
culvert candidate.

## Scope

- Persist `tipo='conduccion'` on `cruce_camino` (unranked).
- Assign `canal_ref` when a canal crossing on the **same tramo** lies in the
  along-road direction of the D8 pointer.
- Map: terracotta arrows (line + ▲) on the same `road_flow` toggle.
- Panel: independent switch "Cuneta (paralelo)", default on; ranked list
  unchanged; companion unranked section.
- GLO-30 honesty: this is regional along-road drainage, not a 1 m ditch
  section.

## Out of scope

- Walking connected tramos / road-network topology.
- 5 m IGN/drone DEM.
- Mixing conduccion into `orden_ranking`.
- Enabling RAG. Deploy to the box (after merge).

## Constraints

- Isolated worktree `feat/conduccion-paralela` off `origin/main` `912ad9c2`.
- No vite/`npm run build`.
- Alembic head is `lluvia_ext_002`; new revision revises that.
- `ck_cruce_flujo_sin_canal` stays: only `flujo_natural` cannot carry
  `canal_ref`. `conduccion` may.
- Arrow distinction must not be hue-only (imagery + CVD).

## Tasks

- [x] T1 Migration `0024_add_cruce_conduccion` + ORM CHECKs
- [x] T2 Detector: store conduccion instead of excluding; canal sink
- [x] T3 API totals + schema
- [x] T4 Frontend kinds, arrows, filter switch, list section
- [x] T5 Tests (pytest detector + 0024; vitest layers/arrows/list)

## Acceptance

- Parallel D8 (θ < 22.5°) produces `tipo=conduccion`, `orden_ranking` NULL.
- Perpendicular D8 is still ranked `flujo_natural`.
- Same-tramo canal in the along-road direction is `canal_ref`; opposite
  direction is not.
- Rank denominator `total_flujo_natural` ignores conduccion.
- Map arrows hidden when the cuneta switch is off; crossings stay.
- `flujo_paralelo` no longer emitted as an exclusion for stored rows.

## Checks

- `pytest gee-backend/tests/new/test_detectar_cruces_camino_flujo.py gee-backend/tests/new/test_cruce_conduccion_migration.py -q`
- `cd consorcio-web && npx vitest run tests/unit/roadFlowLayers.test.ts tests/unit/roadFlowArrows.test.ts tests/unit/RoadFlowRankedList.test.tsx tests/unit/layerRenderRegistry.test.ts`

## TDD

Unknown at project level; this change uses tests-first on the detector
predicate and the arrow azimuth helper.
