# audit-2026-10-nuc-requestid-photothread

Fixes two verified audit WARNINGs in `gee-backend/app/main.py`: NUC-2
(request_id missing from access / rate-limit / CSRF logs) and NUC-5
(`get_denuncia_photo` runs its DB lookup on the event loop).

## In

- NUC-2: `RequestIdMiddleware` was added FIRST → innermost (Starlette
  reverses add order; last added = outermost). The `request_id`
  contextvar is bound inside its `__call__`, but every
  `BaseHTTPMiddleware` further out (RequestLogging, CSRF, rate limit)
  logs from the parent context while `call_next` runs the inner stack in
  a spawned child task — contextvar writes in the child never propagate
  back. "Request started/completed/failed", "Rate limit exceeded",
  "CSRF: Invalid origin" carried no request_id and could not be joined
  to the `X-Request-Id` header the client received.
- NUC-5: `get_denuncia_photo` called `next(db_gen)` + `db.get(Denuncia,
  id)` directly on the event loop; only the file read was offloaded.
  Gallery pages hit this once per photo; same failure class as the
  21-161 s tail-latency incident documented on `_run_blocking`
  (`router_gee_support.py`).

## Out

- NUC-2 fix: `app.add_middleware(RequestIdMiddleware)` moved to
  SECOND-OUTERMOST — after `CORSMiddleware`, immediately before
  `RequestMetricsMiddleware` (which stays outermost per OBS-02: metrics
  must keep timing everything the inner stack, rate limiter included,
  turns into a status code). Binding outside every logging middleware
  means all of them inherit the contextvar; rejection responses minted
  by the rate limiter / CSRF still exit through
  `RequestIdMiddleware.send_wrapper`, so a 429/403 and its log line
  carry the same id the `X-Request-Id` header shows. The ordering
  rationale is commented at the add site in `main.py`.
- NUC-5 fix: the row fetch (session open + `db.get` + session close)
  moved into `_fetch_denuncia_row(denuncia_id)` and runs via
  `await asyncio.to_thread(...)`, matching the file's existing offload
  idiom (`asyncio.to_thread` for the file read) and the documented
  `_run_blocking` pattern. Ownership/404 semantics unchanged: same
  checks in the same order (404 on missing/soft-deleted, 404 for
  non-owner/non-operator, 404 on stale pointer), filesystem IO still
  only after authorization. Column attributes are fully loaded by
  `db.get`, so they remain readable on the detached row after the
  session closes in the thread.
- Tests (`tests/new/test_request_id_logging.py`, full-app TestClient +
  caplog-on-structlog-event-dict idiom):
  - access log "Request started"/"Request completed" event dicts carry
    the same request_id as the response `X-Request-Id` header (RED on
    unfixed code: `KeyError: 'request_id'`).
  - rate-limit rejection log "Rate limit exceeded" carries the id of the
    429's `X-Request-Id` (`rate_limited` marker; `rate_limit_disabled`
    pinned False; singleton limiter `check` stubbed to refuse for
    determinism — the limiter arithmetic stays pinned by
    `test_global_rate_limit_contract.py`).
  - CSRF rejection log "CSRF: Invalid origin" carries the id of the
    403's `X-Request-Id`.
- Tests (`tests/unit/test_denuncia_photo_path.py`):
  - new `test_db_lookup_runs_off_the_event_loop`: records the thread id
    inside `db.get` and asserts it differs from the caller's (event
    loop) thread (RED on unfixed code: identical thread ids).
  - all pre-existing behavior pins (owner 200, auth-before-IO 404,
    stale/deleted 404, parser, confined reader) still pass unchanged.

## Validation

- RED (unfixed `main.py`, `git checkout` of the fix): 4/4 new tests
  fail — 3x `KeyError: 'request_id'`, 1x "db.get ran on the caller's
  (event-loop) thread" with identical thread ids.
- GREEN (fixed): `tests/new/test_request_id_logging.py` 3 passed;
  `tests/unit/test_denuncia_photo_path.py` 16 passed;
  `tests/unit/test_denuncia_photo_pointer.py` 5 passed (needs
  `UPLOADS_ROOT` set — pre-existing collection artifact, see below);
  task's `-k` selection over `tests/new/`: 52 passed, 4857 deselected.
- `ruff check` + `ruff format --check` clean on all three touched files.

## Pre-existing, NOT caused by this change (verified by re-running on
stashed/unfixed code)

- `pytest tests/unit` as a whole directory fails collection:
  `PermissionError: '/app'` (a module that imports `app.main` before the
  denuncia modules set `UPLOADS_ROOT` hits the Docker-default
  `/app/uploads`). Standalone module runs work.
- `test_csrf_cookie_origin.py` fails when `test_denuncia_photo_path.py`
  runs first in the same process (env pollution:
  `CORS_ORIGINS=http://localhost:5173` excludes the `localhost:3000`
  origin that test asserts). Passes standalone.
