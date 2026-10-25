# audit-2026-10-fe-admin-ux

Three audit WARNINGs in the admin panels, same root family as the merged C5/PR #589
finanzas fix (error toasts + `submitting` guards). One PR onto `origin/main`.

## In

- [x] FE-3: wire `QueryError` end to end. `api/core.ts` throws
      `new QueryError(getApiErrorMessage(...), response.status)` for every non-2xx
      (including the 401-expired branch), `queryRetry.ts` reads `statusCode` via
      `instanceof` before the `API Error: NNN` regex fallback (kept). String-detail
      4xx (FastAPI `HTTPException(detail="...")`) are no longer retried 3x with
      backoff. `QueryError` moved to leaf `src/lib/queryError.ts` to avoid the
      core.ts → query.ts → api/index.ts → core.ts cycle; `query.ts` re-exports it
      so existing imports keep working. Red-check: 5 new tests fail on unfixed
      src, pass after.
- [x] FE-5: double-submit guards following the #589 finanzas pattern
      (`submitting` state + `loading={submitting}` + red/green toasts):
      TramitesPanel create, ReunionCreateModal submit (state in
      `useReunionesController`, prop through `ReunionesPanel`). Failed create
      keeps the modal open.
- [x] FE-6: TramitesPanel load failures render a persistent `Alert` +
      "Reintentar" (AdminDashboard `cargarDashboard` idiom, new
      `erroresUi.cargarTramites` entry) instead of an empty table; failed detail
      fetch shows a red toast and no longer opens an empty history modal;
      create failure shows a red toast (#589 shape).
- [x] Tests: queryRetry (QueryError 4xx/5xx/no-status), apiCoreHelpers
      (string-detail 404/403/409 → QueryError with status; integration
      core+retry: 404 not retried, 503 still retried), TramitesPanel +
      ReunionesPanel harnesses extended (load-error Alert + retry recovery,
      detail-failure toast, double-submit disable + failure keeps modal open).

## Out (not this PR)

- Finanzas list load failure is still console-only (verified: `fetchFinanzas`
  catch logs only — #589 covered create/update toasts, not the list). Same
  FE-6 shape, milder; separate slice if it gets prioritized.
- ReunionesPanel list/agenda load failures are also console-only
  (`fetchReuniones`/`fetchAgenda` swallow errors) — same family, not in scope.
- SugerenciasPanel load failures (toast only, no persistent state) — same
  family, not in scope.
- Retry-policy change for mutations (still `retry: false` globally; unchanged).
- `QueryError.endpoint` is still never populated by the core (kept optional;
  nothing consumes it today).
