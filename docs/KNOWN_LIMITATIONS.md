# Known limitations — consorcio-canalero

> Items the team has SHIPPED knowing the trade-off — not bugs, but
> things a future engineer should know about before "fixing" them. Each
> entry carries the expected fix milestone so this list is a roadmap
> backlog, not a static inventory.

Linked from `docs/RUNBOOK.md § 1.6`.

---

## Observability

### ~~Boot logs duplicated under 2 uvicorn workers~~ — RESOLVED in F5-N

Originally documented: `uvicorn` runs with `--workers 2` since
Phase 3 / F3-J. Every module-level log line in `app/main.py` fires
once per worker, so ``Starting Consorcio Canalero Backend v2...``
appears twice on a fresh deploy. Sentry/BetterStack would dedup by
message hash and silently hide the second worker's events.

**Resolved**: ``add_app_context`` in ``app/core/logging.py`` now
emits a per-process ``worker_id`` field (PID of the importing
process, computed once at module load) on every event. The dedup
grouping becomes ``(message, worker_id)`` so both workers' boot
lines stay visible. The same mechanism applies to celery prefork
workers naturally — each fork is a separate process with its own
PID.

This section is kept for historical context; remove on the next
KNOWN_LIMITATIONS sweep.

---

## Frontend / PWA

### ~~PWA icons are a green "CC" placeholder~~ — RESOLVED in F5-M

Originally documented: the 3 PWA PNGs in
``consorcio-web/public/icons/icon-{192,512,512-maskable}.png`` were
programmatically-generated placeholders (green "CC" text) from
Phase 3 / F3-F. The maskable variant was RGB instead of RGBA,
producing visual artifacts on Android adaptive-icon launchers
(One UI, MIUI).

**Resolved** in F5-M: regenerated all three icons from
``public/favicon.ico`` (256×256 RGBA, the existing real favicon
of the SPA). The pipeline:

  - ``icon-192.png`` — direct LANCZOS downscale 256→192.
  - ``icon-512.png`` — LANCZOS upscale 256→512 (some softness vs
    a native 512 asset, but acceptable; the favicon is the only
    source of truth available without commissioning a logo).
  - ``icon-512-maskable.png`` — 80% safe area: the favicon is
    inset to 409×409 centered on a 512×512 transparent canvas
    with 51px of RGBA-transparent padding on each side. This is
    the spec-compliant safe-area mask that lets Android launchers
    crop into any shape (circle, squircle, teardrop) without
    losing critical content.

All three files are now RGBA, fixing the RGB artifact bug on
adaptive-icon launchers.

This is still a placeholder in spirit (the favicon is a simple
mark, not a full institutional logo), but it's a placeholder
that **(a) matches the rest of the SPA's brand mark**, **(b)**
fixes the technical RGBA bug, and **(c)** doesn't need a design
budget to ship.

If the consorcio eventually commissions a proper logo, the
manifest paths stay stable — drop in the new PNGs and the PWA
picks them up on next install.

### React Compiler opted-out on two ref-heavy files

Phase 3 / F3-E activated `babel-plugin-react-compiler`. Two files
(`LocationSection.tsx`, `TerrainViewer3D.tsx`) mutate refs during
render and earned a `'use no memo'` directive in Phase 3.1 to keep
the compiler from skipping renders.

**Trade-off**: the map + 3D terrain views — the most-renderable
surfaces — miss the compiler's auto-memoisation wins.

**Expected fix** (Phase 4): wrap each `ref.current = value` in a
`useEffect(() => { ref.current = value; })` and remove the directive.
Ticket: `consorcio-web/TODO_REFS.md` (TBD).

---

## Backend / DB

### Celery DB pool intentionally smaller than backend

`app/db/session.py` detects whether the process is a Celery worker
(by basename of `sys.argv[0]`) and shrinks the pool from 20+20 to
5+5. Celery tasks are I/O-light and hold one connection per task,
not per-worker-idle.

**Mitigation today**: this IS the mitigation. The alternative was
160 connections vs a typical 100 `max_connections` budget on the
shared postgres.

**Expected fix** (none — this is the steady state). Re-evaluate if
the workload becomes I/O-heavy or if we move to a per-deployment
postgres.

### celery-beat is a singleton

`docker compose up -d --scale celery-beat=2` corrupts the schedule
db because both replicas write to the shared
`celery-beat-schedule` volume. `deploy.replicas: 1` is a
Swarm-only directive; on plain Compose the `container_name`
constraint is the operational guard.

**Mitigation today**: a ⚠️ comment block in `docker-compose.prod.yml`
warning operators not to scale it.

**Expected fix** (Phase 4): migrate to `celery-redbeat` (Redis-backed
schedule store with leader election). Beat processes self-coordinate
so multiple replicas become safe.

---

## Auth / sessions

### `logout-all` has a ≤15 min residual access-token window

`POST /auth/jwt/logout-all` revokes every refresh token immediately,
but JWT access tokens issued in the previous 15 minutes remain valid
until natural expiry (JWT is stateless by design).

**Mitigation today**: communicate the 15-min cap to security-sensitive
operators who use the endpoint.

**Expected fix** (Phase 4): add a per-user `revocation_epoch` column
and check it in `get_jwt_strategy`. Cost: one DB read per request,
worth it only if a real threat model demands it.

### SMTP body logging carries reset / verify tokens

Phase 2 / F2-J sends password-reset and email-verification tokens
inside the message body. Most SMTP providers (Brevo, Resend, SES)
log message bodies for 30+ days for support purposes.

**Mitigation today**: documented in RUNBOOK § 1.5 — operators
configure their provider to disable body logging OR use the
provider's transactional API rather than SMTP.

**Expected fix** (Phase 4): switch to a one-time code that the SPA
exchanges for the long token, so the SMTP body never carries the
credential itself.

### Refresh-token timing equicost has a constant-fold residual (F5-G skipped)

Phase 2.3's `rotate()` uses `literal(true())` vs `literal(false())`
as the burn-vs-no-op gate, intending equicost SQL execution. The
PostgreSQL planner constant-folds `WHERE ... AND false` into a
"One-Time Filter" that returns 0 rows without an index scan, so the
no-op branch is measurably faster than the burn branch by hundreds
of microseconds.

**Mitigation today**: the attacker would need (a) co-location or
thousands of samples AND (b) a stolen cookie already in hand —
strictly stronger pre-conditions than what the leak grants.

**Phase 5 / F5-G investigation outcome (skip-with-justification)**:
F5-G was originally scoped as "swap the ``true()/false()`` literals
for a predicate the planner can't constant-fold". The investigation
landed on the conclusion that ANY shape the planner can statically
determine to be empty (``id == sentinel_uuid``, ``revoked_at <=
1970-01-01``, ``token_hash == 'never_a_hash'``) is still subject to
fast path optimisation — index lookup returning 0 rows is roughly
as fast as the One-Time Filter. The only honest equicost shapes
either:

  - Force a real row-by-row scan (e.g. ``position()`` calls on every
    row) which is itself a measurable cost spike and visible as a
    different timing signature; or
  - Execute the same UPDATE in both branches and rely on the WHERE
    not mutating anything in no-op mode — that requires the burn
    semantics to be a SUPERSET of the no-op semantics, which they
    are not (legitimate race-loss must NOT burn the family).

The real fix is what this section already pointed at: rip out the
CAS + family-burn + race-window machinery in favour of short
refresh tokens + frequent re-auth. That removes the burn-vs-no-op
decision and the leak vanishes with it. That refactor was deferred
to Phase 6+ because it's a multi-day rewrite of a load-bearing
auth path, while the threat model accepts the current residual.

**Expected fix** (Phase 6+ refresh-token redesign): see above.

---

## Architecture

### Dependency Injection is pragmatic, not formal IoC (F4-I skipped)

Every service in ``app/domains/*/service.py`` accepts its
repository through the constructor with a sensible default:

```python
class DenunciaService:
    def __init__(self, repository: DenunciaRepository | None = None) -> None:
        self.repo = repository or DenunciaRepository()
```

The pattern delivers what DI is supposed to deliver — services
are testable WITHOUT touching the database (verified across the
F4-B mutation suite where every Service is instantiated with a
``MagicMock()`` repo and the assertions still exercise real
business logic), and a future swap of the persistence backend
needs to change exactly one default per service rather than
hunt down every caller.

What this is NOT:
  - There is no formal ``RepositoryProtocol`` typed contract.
    Repos and services are coupled to each other's concrete
    classes at type-check time. Mocks work because Python's
    structural typing accepts ``MagicMock`` for anything.
  - There is no IoC container (no Punq, no ``dependency-injector``,
    no FastAPI ``Depends`` for repos). The wiring is just
    constructor-argument-with-default.

Why F4-I (a planned refactor to formal Protocol-based DI) was
skipped:
  - The 8 services that follow this pattern would each need a
    Protocol class declaring every method they depend on. ~400
    lines of new code, ~zero behaviour change.
  - The benefit (clearer contracts, mock-by-default in mypy
    strict mode) does NOT pay back at this codebase size. The
    F4-B mutation tests already cover the same surface without
    Protocols.
  - The harder part of "real DI" — letting a deploy swap
    PostgreSQL for SQLite, or instrument repo calls with OTel —
    requires runtime wiring at FastAPI ``Depends`` level, not
    just a type-only refactor. That is a Phase 5+ project once
    a use case actually motivates it.

**Expected fix** (Phase 5+, only if motivated by a real use case):
introduce a thin ``app/_shared/repository_protocols.py`` declaring
``DenunciaRepoProtocol``, ``MonitoringRepoProtocol``, etc., and
re-type the service constructors against the Protocol. Routers
move from ``Depends(get_service)`` to ``Depends(get_repo)`` +
explicit service construction. This is invasive and shouldn't
land until something concrete (e.g. a read-only replica repo for
analytics) makes it worth the churn.

---

### ~~Admin force-revoke endpoint missing~~ — RESOLVED in F5-F follow-up

Originally documented as a gap: the user-side ``/auth/jwt/logout-all``
existed since F5-F but had no admin-side counterpart for the "fire
an employee" / "compromise on user X" workflow.

**Resolved** (commit landed in this batch): ``POST /admin/users/{id}/force-revoke``
runs the same two-layer revocation as ``logout_all_sessions`` against
ANY ``user_id``, writes an ``audit_log`` row with
``action='user.force-revoke'`` + ``resource='user_id=<target>'`` so
the action is traceable, and refuses self-revoke with a 400 (the
admin must use ``/auth/jwt/logout-all`` for their own sessions —
otherwise they'd lock themselves out mid-incident).

This section is kept for historical context; remove on the next
KNOWN_LIMITATIONS sweep.

### Two endpoints still ``response_model=dict`` (F5-B leftover)

F5-B migrated 29 of 31 dict-typed endpoints to proper Pydantic
schemas. Two remain. Both have shapes that don't fit the standard
``PaginatedResponse[T]`` envelope or any other reusable schema:

1. **``GET /geo/basins``** — returns a raw GeoJSON ``FeatureCollection``
   (``{"type": "FeatureCollection", "features": [...]}``). The frontend
   feeds it directly into MapLibre's ``addSource()`` which already
   understands the shape. Adding a Pydantic ``FeatureCollection``
   wrapper would mean either (a) validating every geometry on the
   way out (expensive for a 500-polygon response) or (b) keeping
   ``features: list[dict]`` as a passthrough, which gains nothing
   over the current state.
2. **``GET /geo/intelligence/hci``** — returns one of TWO mutually-
   exclusive shapes depending on the ``use_mv`` query flag:
   ``IndiceHidricoResponse`` items when false, ``mv_hci_por_zona``
   raw dict rows when true. A proper migration is to split this
   into two endpoints (``/hci`` and ``/hci/by-zone``) so each has
   one shape. That's an API-breaking change and out of scope for
   F5-B's "fix the type contract without changing the URL".

**Expected fix** (Phase 5+):
  - ``/geo/basins``: only worth it if the frontend codegen pain
    surfaces. The MapLibre integration doesn't care.
  - ``/geo/intelligence/hci``: split into two URLs the next time
    the intelligence API gets a version bump or a documented
    breaking-change window.

---

## Builds / bundles

### Mantine CSS imports stay monolithic

Phase 3 / F3-D evaluated swapping `@mantine/core/styles.css` for 43
per-component imports. The uncompressed 228 KB compresses to ~30 KB
gzipped + SW cache for a year. The migration is mechanically safe but
the surface for "forgot to import the CSS of a Tooltip" bugs is
large.

**Status** (Phase 5 / F5-L, 2026-05-20): deferred indefinitely.
Mantine 9.x released (currently 9.2.1) did NOT bring the CSS
tree-shaking story we were waiting on — the maintainers confirmed in
discussion #500 that components stay ESM with monolithic CSS, and
`optimizePackageImports` continues to be the recommended JS-side
optimisation (which we already have). The patch upgrade
`8.3.14 → 8.3.18` was applied to capture the bug fixes within 8.x
without breaking changes; the major 8 → 9 jump (~2-4h, new TreeSelect
/ SankeyChart / RollingNumber) brings no concrete value for our
current screens, so we stay on 8.x.

**Trigger to revisit**: a 9.x-only component lands that we actually
need, OR Mantine ships real CSS tree-shaking in a future version.
