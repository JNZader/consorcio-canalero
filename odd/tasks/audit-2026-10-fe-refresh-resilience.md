# Work Unit: audit-2026-10-fe-refresh-resilience

Frontend half of review finding **RES2-001** (SEG-2 4R lens review): the
silent-refresh boundary in `consorcio-web/src/lib/api/core.ts` treated ANY
failed refresh — 500/502/503/429 or a network throw — as session expiry:
`clearTokens()` + `auth:expired` → AppProvider hard-redirects to `/login`
after 1.5s, losing unsaved form state. With the owner-approved 60-minute
access tokens (SEG-2 decision), every active user depends on a successful
`/auth/jwt/refresh` ~8x/workday, so a 2-minute backend blip force-logged-out
~3% of active users and a 10-minute one ~17%.

Owner-endorsed design intent: only a REAL 401/403 from the refresh endpoint
means the session is dead (cookie rejected/rotated away). Transient failures
must fail only the triggering request while preserving the session, so the
next request retries the refresh naturally.

## In

- `src/lib/api/core.ts` — `attemptTokenRefresh` now returns a tri-state
  `RefreshOutcome` instead of `boolean`:
  - `{ kind: 'refreshed' }` — 200 + token persisted; original request
    retried once (`__alreadyRetried` loop guard unchanged).
  - `{ kind: 'session-dead' }` — refresh answered 401/403, the logout
    tombstone is set, or a 200 arrived without an access token (existing
    behavior preserved). The existing logout flow runs UNCHANGED:
    `clearTokens()` + `auth:expired` dispatch (10s `_handlingAuthExpiry`
    dedupe) + 'Tu sesión ha expirado...' error.
  - `{ kind: 'transient'; status? }` — any other non-ok (5xx, 429 from the
    rate limiter, and other 4xx) or a network/abort throw. The triggering
    request rejects with `QueryError` (statusCode = refresh HTTP status when
    known) and message 'No se pudo renovar la sesión (servidor ocupado).
    Volvé a intentar en unos segundos.'; tokens/cookie/cache untouched, no
    `auth:expired` dispatched. Note: the suggested copy said "Reintenta"
    (tuteo); adapted to voseo to match the house message style
    (`userFacingError.ts`, existing core.ts strings).
- Anti-spam guard: a plain timestamp (`_lastTransientRefreshAt`); a new
  refresh attempt within 2s of a transient failure fails fast with the same
  `QueryError` without hitting the network. No in-flight retry loops were
  added — single attempt per 401 boundary, the natural retry is the user's
  next request (TanStack Query's existing retry/backoff drives that).
- Single-flight semantics preserved and shared: concurrent 401s await the
  same in-flight promise and observe the SAME outcome object; each waiter
  re-checks the logout tombstone (tombstone wins → session-dead). Only the
  flight owner writes the backoff timestamp.
- `src/lib/queryError.ts` (new leaf module): `QueryError` moved here and
  re-exported from `src/lib/query.ts`. Rationale: `query.ts` imports the api
  index, so `core.ts → query.ts` would be a dependency cycle, and 14 test
  files use partial `vi.mock('src/lib/api/core')` factories that would break
  a re-export chain through core.
- `authenticatedFetchResponse`: the 401 branch now delegates to a new
  `retryAfterRefresh` helper (refresh → retry-once / transient QueryError /
  logout flow). Extracted because the added branch pushed the function over
  biome's cognitive-complexity limit (37 > 30); behavior of the genuine
  expiry path is byte-identical to before.
- `tests/unit/apiCore.test.ts` — new describe `refresh failure discrimination
  (RES2-001)` with RED-CHECK (all new-behavior tests failed on unfixed code,
  which instead logged 'Sesión expirada — redirigiendo a login' and cleared
  tokens): 503 → transient QueryError + session intact + fail-fast inside
  2s + refresh retried (and recovered) on the next request after the window;
  network throw → transient (no status); 429 → transient, NOT session-death;
  two concurrent 401s sharing one transient-failed flight → both get the
  QueryError, exactly one refresh call, session intact; refresh 401 → exact
  existing logout semantics (clearTokens + `auth:expired` once + no retry).
  Existing pins (refresh-once, tombstone, no-second-refresh, blob refresh)
  all keep passing unmodified.

## Out

- No automatic in-flight retry/backoff loop inside the refresh — deliberate:
  one attempt per 401 boundary; the user's next request (or TanStack Query's
  global retry) is the retry. The 2s fail-fast guard covers retry-spam.
- Backend cookie-rotation race (**RES2-002**) — related but separate backend
  unit; not touched here.
- `AppProvider.tsx` `auth:expired` handling (reset + toast + redirect) —
  unchanged by design; the fix is that transient failures no longer dispatch
  the event at all.
- No `returnTo`/form-state-preservation work for the genuine-expiry path —
  out of scope for RES2-001; the genuine path keeps its exact contract.
- A 200 from refresh without `access_token` stays session-dead (existing
  behavior) — it is a backend bug, not a blip; reclassifying it would change
  the genuine-expiry contract without evidence.
- `shouldRetryQuery`/`httpStatusFromError` interplay (QueryError carries
  `statusCode`, which the retry policy does not read — transient refresh
  failures therefore retry under the global default) — acceptable: retries
  are cheap thanks to the 2s fail-fast guard; changing the retry policy is a
  separate decision.
