# canales-admin-superposicion

## Objective
Staff can tell KMZ, APRHI SR PA, and old existentes apart when their traces share the same alignment, and can pick which one a click meant.

## Problem
Admin `/canales` stacks SR PA (orange dashed) under existentes (violet dashed) under KMZ (green solid). Geometries often coincide. Color + dash is not enough on imagery. Three independent layer click handlers fire on the same point; the last one wins. Overlay labels collide with KMZ labels.

## Why
The owner uses this screen to choose what to publish from every inventory. If the map does not show three traces, the comparison is unusable.

## Scope
- Admin map + sidebar only (`CanalesPublicacionMap`, `CanalesPublicacionPanel`).
- Visual: KMZ casing; overlay `line-offset` + dim when KMZ is visible; hide overlay labels while KMZ is on.
- Interaction: one padded `queryRenderedFeatures` across the three line layers; sidebar picker when 2+ hits.
- Pure helpers in `consorcio-web/src/lib/canalesPublicacionOverlap.ts` so tests do not need MapLibre.

## Out of scope
- Public citizen map.
- Backend / Alembic / publication rules.
- Auto-unpublish of relevadas.

## Constraints
- Isolated worktree `feat/canales-admin-superposicion` from `origin/main` (`d260b155`).
- Artifacts in English; UI copy in Spanish matching the existing panel.
- Do not rely on color alone: offset + dash + casing.
- Do not run `npm run build` / Vite.
- `rg`/`fd`/`sd`/`eza`/`bat`, never grep/find/sed/ls/cat.
- React 19: no `useMemo`/`useCallback`. TypeScript: const objects, no `any`.

## Route
Delegated writer (2+ non-trivial files). TDD unknown → ordinary vitest checks, not RED/GREEN ceremony.

## Tasks
- [x] T1 Overlap helpers + unit tests
- [x] T2 Admin map: casing, offset/dim, overlay-label gate, unified bbox click
- [x] T3 Panel picker + legend copy + panel tests

## Acceptance
- When KMZ is on and an overlay is on, overlay lines offset (SR PA left, existentes right) and dim unless selected.
- Overlay labels hidden while any KMZ group is visible; they return when KMZ groups are off.
- Click with 2+ line hits shows a sidebar list; choosing a row selects that canal.
- Click with 1 hit selects it and does not show the picker.
- Existing publish/switch tests still pass.

## Checks
```bash
cd consorcio-web
./node_modules/.bin/vitest run tests/unit/canalesPublicacionOverlap.test.ts tests/unit/canalesPublicacionMap.test.ts tests/unit/CanalesPublicacionPanel.test.tsx tests/unit/aprhiSrPa.test.ts
```

## Progress
- T1–T3 implemented on `feat/canales-admin-superposicion`.
- Parent vitest spot-check: 4 files, 35 passed, EXIT=0.
- Runtime map harness: N/A (MapLibre canvas; no local Vite).
- Rollback: revert this branch; public `map2d` untouched.

## Next
Open a PR when asked. One work-unit commit — splitting T1/T2/T3 would separate helpers from the map that consumes them.
