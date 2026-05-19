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

## Builds / bundles

### Mantine CSS imports stay monolithic

Phase 3 / F3-D evaluated swapping `@mantine/core/styles.css` for 43
per-component imports. The uncompressed 228 KB compresses to ~30 KB
gzipped + SW cache for a year. The migration is mechanically safe but
the surface for "forgot to import the CSS of a Tooltip" bugs is
large.

**Expected fix** (Phase 4+): re-evaluate when Mantine v9 ships its
rumoured CSS-tree-shaking story.
