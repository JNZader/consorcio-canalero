# Archive Report: Multi-Hazard Viewer

## Change Metadata

| Field | Value |
|-------|-------|
| **Change** | `multi-hazard-viewer` |
| **Project** | `consorcio-canalero` |
| **Artifact store** | hybrid (Engram + OpenSpec) |
| **Archived on** | 2026-08-17 |
| **Archive path** | `openspec/changes/archive/2026-08-17-multi-hazard-viewer/` |
| **Archive reason** | Implementation and verification complete on local stacked branches; user chose to keep work local and upload later. |

## Source Artifact Observation IDs (Engram)

| Artifact | Engram Topic Key | Observation ID | Notes |
|----------|------------------|----------------|-------|
| Proposal | `sdd/multi-hazard-viewer/proposal` | `#15437` | Full proposal content preserved. |
| Spec | `sdd/multi-hazard-viewer/spec` | `#15438` | Stored as a structured mem_save summary pointing to `openspec/changes/multi-hazard-viewer/spec.md`; no OpenSpec file copy exists. |
| Design | `sdd/multi-hazard-viewer/design` | `#15439` | Stored as a structured mem_save summary pointing to `openspec/changes/multi-hazard-viewer/design.md`; no OpenSpec file copy exists. |
| Tasks | `sdd/multi-hazard-viewer/tasks` | `#15440` | Reconciled to all `[x]` at archive time; see reconciliation note below. |
| Apply Progress | `sdd/multi-hazard-viewer/apply-progress` | `#15441` | Stale snapshot after PR-A/PR-B1; superseded by `apply-progress.md` and `verify-report.md`. |
| Verify Report | — | — | OpenSpec only (`openspec/changes/multi-hazard-viewer/verify-report.md`). Not persisted to Engram. |

## OpenSpec Files Archived

| File | Status |
|------|--------|
| `archive-report.md` | ✅ |
| `apply-progress.md` | ✅ |
| `explore.md` | ✅ |
| `verify-report.md` | ✅ |
| `proposal.md` | ❌ missing in OpenSpec (Engram only) |
| `design.md` | ❌ missing in OpenSpec (Engram only) |
| `spec.md` / `specs/` | ❌ missing in OpenSpec (Engram only) |
| `tasks.md` | ❌ missing in OpenSpec (Engram only) |

## Summary

The Multi-Hazard Viewer introduces a feature-flagged hazard mode inside the existing 2D map. It overlays flood risk, drainage need, soil capability, surveyed channels, basins, and CHIRPS 1991-2020 precipitation normals, with shareable URL state and role-gated access for `admin` / `operador`.

Implementation was delivered as a local stacked branch chain:

| Branch | Scope | Tip Commit |
|--------|-------|------------|
| `feature/multi-hazard-viewer/pr-a` | Backend tile catalog + colormap | Backend `precip_normal` publication + tests |
| `feature/multi-hazard-viewer/pr-b1` | Frontend foundation | URL state, store, gate, registry, legend, unit tests |
| `feature/multi-hazard-viewer/pr-b2` | Hazard UI components | `HazardControls`, `HazardControlsMobile`, basin filter helper |
| `feature/multi-hazard-viewer/pr-b3` | Map integration + basin filter + legend wiring | Map wiring, layout, legend extension, integration test |
| `feature/multi-hazard-viewer/pr-b4` | Tests + final lint fix | Playwright E2E spec + Biome complexity fix |

Final branch tip for the chain is `feature/multi-hazard-viewer/pr-b4` at `8a8d0761`.

## Spec Sync to Main Specs

**Action**: None.

No canonical main spec exists for the Multi-Hazard Viewer domain. The OpenSpec `openspec/specs/` tree currently contains:

- `knowledge-corpus-ingestion/spec.md`
- `knowledge-hybrid-retrieval/spec.md`
- `rainfall-analysis/spec.md`

The Multi-Hazard Viewer spec lives only as a delta artifact (Engram `#15438` and the referenced but absent `openspec/changes/multi-hazard-viewer/spec.md`). Because there is no matching `openspec/specs/{domain}/spec.md` to merge into, the delta remains with the archived change. The archive report preserves the observation ID for traceability.

## Verification Results

Final verification executed against branch `feature/multi-hazard-viewer/pr-b4`:

| Check | Command | Result |
|-------|---------|--------|
| Backend geo tests | `pytest tests/new/test_geo_public_layers.py tests/new/test_imagery_tile_service.py` | **PASS** — 34/34 tests passed |
| Frontend typecheck | `npm run typecheck` | **PASS** — no errors |
| Frontend unit tests | `npm run test:run` | **PASS** — 282 test files, 3,719 tests passed |
| Frontend lint | `npm run lint` | **PASS** — 4 Biome warnings total (3 pre-existing, 1 new warning fixed in final commit) |
| Playwright E2E | `multi-hazard.spec.ts` | **PASS** — 6/6 tests passed |

The final lint-fix commit `8a8d0761` refactored `stringifyHazardSearch` in `src/main.tsx` into `appendHazardParam`, `appendArrayParam`, and `appendStringParam` helpers, eliminating the new Biome cognitive-complexity warning while preserving exact URL output.

## Known Warnings / Notes

- **OpenSpec artifact gap**: `proposal.md`, `design.md`, `spec.md`, and `tasks.md` were not written to the OpenSpec active change folder during earlier phases; they exist only in Engram. This does not block archive, but future changes should write all required artifacts to both stores when in hybrid mode.
- **Biome warnings**: 3 pre-existing warnings remain unrelated to this change.
- **E2E canary**: The `verify-report.md` recommends running the full `test:e2e:local` canary/prod suite before merging to ensure the router serializer change does not regress other routes.
- **No PRs created**: The user chose to keep the work local and upload later; no branches were pushed and no PRs were opened.

## Task Completion Reconciliation

The original Engram `tasks` observation (`#15440`) showed PR-A and PR-B1 tasks as checked, but PR-B2, PR-B3, PR-B4 tasks remained unchecked because later apply waves did not sweep checkboxes. At archive time the tasks were mechanically reconciled to all `[x]` because:

- `verify-report.md` documents completion and passing tests for all phases.
- `apply-progress.md` records the final lint fix and full verification pass.
- The git history on `feature/multi-hazard-viewer/pr-b4` contains commits covering PR-B2 (`cb783fad`), PR-B3 (`191bdd1f`), and PR-B4 (`4e3294f7`, `8a8d0761`).

Reconciliation reason: stale checkboxes after delegated PR-B2/PR-B3/PR-B4 apply waves; completion proven by `verify-report.md` and final `apply-progress.md`.

## Next Steps (Push / PR)

1. Push the stacked branch chain to the remote when convenient:
   - `feature/multi-hazard-viewer/pr-a`
   - `feature/multi-hazard-viewer/pr-b1`
   - `feature/multi-hazard-viewer/pr-b2`
   - `feature/multi-hazard-viewer/pr-b3`
   - `feature/multi-hazard-viewer/pr-b4`
2. Open stacked PRs against `main` in order (PR-A first; each subsequent PR targets the previous PR branch or retarget after merge).
3. Before merge, run the full `test:e2e:local` canary/prod Playwright suite to validate route-search-param serialization has no regressions.
4. Add a dedicated Playwright project for `multi-hazard.spec.ts` in `playwright.local.config.ts` so future runs do not need a temporary config file.
5. Consider adding a backend integration test for the `precip_normal` catalog deduplication key change to prevent regression.

## Deferred Work

The following items were intentionally deferred out of this change per the proposal:

- A separate `/visor-multi-riesgo` route or public/executive dashboard.
- Daily, event, or configurable precipitation rasters.
- Risk threshold numeric slider or cross-dataset terrain-class thresholds.
- Multi-select basin filtering or basin comparison mode.
- Persisting hazard-mode settings to `localStorage` or user preferences.

The contracts (layer registry, tile-catalog descriptor, URL params, state slice, legend config) were designed to support the future precipitation overlay without rewriting the hazard-mode shell.

## Archive Checklist

- [x] Main specs reviewed — no matching main spec to update.
- [x] Change folder moved to `openspec/changes/archive/2026-08-17-multi-hazard-viewer/`.
- [x] Archive contains all OpenSpec artifacts that existed (`apply-progress.md`, `explore.md`, `verify-report.md`, `archive-report.md`).
- [x] Tasks artifact reconciled to all `[x]` with documented reason.
- [x] Active changes directory no longer contains `multi-hazard-viewer`.
- [x] Engram archive report persisted to `sdd/multi-hazard-viewer/archive-report`.

## SDD Cycle Status

The Multi-Hazard Viewer has been planned, implemented, verified, and archived. The change is ready for the next cycle.
