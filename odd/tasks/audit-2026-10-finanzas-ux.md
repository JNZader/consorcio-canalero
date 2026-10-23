# audit-2026-10-finanzas-ux

Finanzas admin panel UX hardening on `feature/audit-c5-finanzas-ux` (from `main` `14256df5`). The 2026-10-23 audit rated CRITICAL: all four mutation handlers in `useFinanzasController` (create/update gasto, create/update ingreso) caught errors with `logger.error` only — no toast, no error state — so a failed POST/PATCH left the user with no feedback, and the four modal submit buttons had no loading/disabled state, so a second click while a request was in flight could duplicate a financial record.

## In

- [x] `useFinanzasController.ts`: red `notifications.show` error toast in each of the four catches, mirroring `handleDownloadSummaryPdf`'s pattern (title + `error.message` fallback). New `submitting` state: set true before the request, released in `finally`; set after the `editingGasto`/`editingIngreso` guards so an early return cannot strand it. Exposed as `submitting`.
- [x] `GastoFormModal`, `IngresoFormModal`, `EditGastoModal`, `EditIngresoModal`: new required `submitting` prop, `loading={submitting}` on the submit button only (Mantine disables a loading button) — close/cancel paths untouched. `FinanzasPanel.tsx` passes `controller.submitting` to all four.
- [x] `src/lib/api/core.ts` `getApiErrorMessage`: INCLUDED — FastAPI 422 `detail` arrays (`ValidationError[].msg`, per `HTTPValidationError` in `src/types/schema.d.ts`) are now joined with `; ` into the thrown Error's message, so the new toasts surface field errors instead of a bare `API Error: 422`. String `detail` / `message` / `error.message` precedence unchanged; arrays without usable `msg` entries still fall back to the status.
- [x] UI strings follow main's accented Spanish ("No se pudo actualizar la categoría", "Intentá nuevamente en unos minutos.") — the replayed diff carried two unaccented strings from the stale develop base, fixed during rebase validation.
- [x] Tests extended in the three existing covering files: `tests/hooks/useFinanzasController.test.tsx` (error toasts on all four failure paths, no green toast on failure, `submitting` toggles true in-flight / false on settle and on guard early-return), `tests/components/FinanzasPanel.test.tsx` (submit button disabled while the POST hangs, green toast + dialog close after settle), `tests/unit/apiCoreHelpers.test.ts` (422 detail-array join + unusable-array fallback). 57/57 passed; `npm run typecheck` (src + tests) and `biome check` clean on touched files.

## Out

React Query migration for the finanzas panel (server-cache invalidation, per-mutation `isPending`) — separate future unit; this fix stays on local state. Mapping 422 `loc` entries back to individual form fields (we surface the joined messages in the toast). The initial-load failure path (`fetchFinanzas`) still logs only — the panel keeps its `LoadingState`/empty rendering and that path creates no duplicate-write risk. Blocking modal close (Escape/backdrop) while a submit is in flight — only the submit path is guarded, per unit scope.
