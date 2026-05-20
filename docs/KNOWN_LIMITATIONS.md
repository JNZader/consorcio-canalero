# Known limitations — consorcio-canalero

> Items the team has SHIPPED knowing the trade-off — not bugs, but
> things a future engineer should know about before "fixing" them. Each
> entry carries the expected fix milestone so this list is a roadmap
> backlog, not a static inventory.

Linked from `docs/RUNBOOK.md § 1.6`.

---

## Observability

### Boot logs duplicated under 2 uvicorn workers

`uvicorn` runs with `--workers 2` since Phase 3 / F3-J. Every
module-level log line in `app/main.py` (rate-limiter init, GEE
pre-init, cache-warming queued) fires once per worker, so
``Starting Consorcio Canalero Backend v2...`` appears twice on a
fresh deploy.

**Mitigation today**: Sentry/BetterStack dedup rule on identical
message within 1 s.

**Expected fix** (Phase 4): add a `worker_id` field to the structured
logger context so duplicated messages are trivially distinguishable
and dedup-friendly.

---

## Frontend / PWA

### PWA icons are a green "CC" placeholder

Phase 3 / F3-F generated three programmatic PNGs (192, 512,
512-maskable). The maskable is RGB, not RGBA — some Android launchers
(MIUI, One UI) render minor artifacts on the outer mask.

**Mitigation today**: replace the three files under
`consorcio-web/public/icons/icon-{192,512,512-maskable}.png` with a
real design. The manifest paths stay stable.

**Expected fix** (Phase 4 — design budget): commission a real logo.

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

### Refresh-token timing equicost has a constant-fold residual

Phase 2.3's `rotate()` uses `literal(true())` vs `literal(false())`
as the burn-vs-no-op gate, intending equicost SQL execution. The
PostgreSQL planner constant-folds `WHERE ... AND false` into a
"One-Time Filter" that returns 0 rows without an index scan, so the
no-op branch is measurably faster than the burn branch by hundreds
of microseconds.

**Mitigation today**: the attacker would need (a) co-location or
thousands of samples AND (b) a stolen cookie already in hand —
strictly stronger pre-conditions than what the leak grants.

**Expected fix** (Phase 4 backlog: simplify refresh-token design).
The whole CAS+family-burn+race-window machinery would be replaced
by short refresh tokens + frequent re-auth, eliminating the
constant-fold concern alongside the rest of the complexity.

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

**Expected fix** (Phase 4+): re-evaluate when Mantine v9 ships its
rumoured CSS-tree-shaking story.
