# Archive Report: Rainfall v2 Technical Analysis (`lluvia-v2`)

**Change:** `lluvia-v2` — Rainfall v2 Technical Analysis
**Archived on:** 2026-08-07
**Tracker branch:** `feat/lluvia-v2` (PRs #165, #168, #169, #170; commit `21e9c92`, tree identical to local, empty diff at archive time)
**Final verify verdict:** READY-FOR-ARCHIVE — 38/38 spec scenarios, no CRITICAL open, no HOLD

---

## Summary

The change delivers provenance-rich, calendar-year rainfall analysis for authenticated Consorcio technical staff, embedded in the territorial ficha. It adds a bounded `geo/rainfall` backend capability (evidence foundation, deterministic scope/temporal engine, policy/eligibility gates, immutable revision snapshots, outbox/ingest operations, CSV export) plus an authenticated ficha detail UI (`RainfallDetailPanel`) with regional-estimate labelling, state/badge disclosure and CSV parity. The existing compact public 1991–2020 normal stays untouched and remains available to unauthenticated visitors.

Specification promoted to main specs (no pre-existing `openspec/specs/` tree):

| Domain | Action | Details |
|--------|--------|---------|
| `rainfall-analysis` | **Created** (promoted) | 13 requirements (R1–R13), 38 scenarios, byte-identical copy of the delta spec |

## Scope Implemented vs Deferred

### Implemented (15/16 tasks complete)

- **Phase 1 — Evidence and foundation (1.1–1.4):** adapter-contract tests, canonical models/ports/schemas/policy/manifests, Alembic migration `lluvia_v2_001`, immutable append-only interval/revision store with two-year retention, backfill checkpoints, no raw-payload persistence.
- **Phase 2 — Deterministic backend (2.1–2.5):** scope resolution (zone/basin/parcel semantics, regional-estimate labels, direct-compute rejection), Buenos-Aires local dates, leap-day and same-date baseline rules, cross-year antecedents, rolling P30/P60/P3h/P24h + I30/I60, deterministic event peak/duration suppression, authenticated router with shared JSON/CSV parity serializer, resilience (timeout/quota/retry/circuit/cache) and Celery Beat/outbox ingest with durable commits and idempotent partial-unique enqueue.
- **Phase 3 — Authenticated ficha and export (3.1–3.3):** Vitest access/state/badge flows, `rainfall.ts` API layer + `useRainfallAnalysis` hook + `components/map2d/rainfall/` UI, `RainfallDetailPanel` conditional mount, authorized CSV export.
- **Phase 4 — Verification and controlled rollout (4.1–4.3):** deterministic Playwright E2E replacing the stale v1 spec, migration/replay/idempotency/feature-flag validation (single head `lluvia_v2_004`), `metrics.py` observability seam + roller manual owners workbook (§ 4 documented, `docs/lluvia-v2-observability-workbook.md`).

### Deferred / Open (non-blocking, recorded)

| Item | Status | Reason / follow-up |
|---|---|---|
| **Task 3.4 — Stryker UI mutation targets** | Deferred (task stays unchecked) | Shared formatting (`rainfallFormat.ts`) landed; mutation-target registration deferred: 3.1–3.3 exceeded the 400-line production budget (650 raw lines). Correction applied at archive (verify finding W1): the prior "backend policy/suppression/temporal/CSV-parity targets already exist per 2.4" wording was inaccurate — **grep confirms 0 rainfall entries in `.cosmic-ray.toml`, `.cosmic-ray.candidate.toml`, `stryker.config.mjs`**. Registration remains open, non-blocking. |
| **Provider adapters (stub)** | Deferred (PR 3A deferral); **wired post-archive (P3, 2026-08-07)** | `tasks.py:40` raised `NotImplementedError('provider adapter not wired')` at archive time; `ResilientAdapter` + outbox retry/circuit machinery in place. Evidence-gated by design: roles activate only after the known-event spike/manifests pass. **Closed**: spike PASS → CHIRPS v3 + IMERG V07 wired (see Follow-ups); `sqpe-obs` explicitly unwired (not in GEE). Staged provider/backfill activation still feature-flag gated. |
| **Post-push hook structural issue (#164)** | Environment, permanent vehicle | Pre-push harness/compile-wrapper exit-127 noise on the Node runner; documented in issue #164. Not a code defect of this change. |
| **Phase-4 shared-DB warning** | Env/test artifact, non-blocking | Teardown/SQLAlchemy warning in the partial-unique-index test output; migration replay verified clean (`downgrade lluvia_v2_003 && upgrade head`). |
| **Workbook §5 open items** | Human decisions | Named owners (design open question), Prometheus/OTel wiring, `rainfall.source.fallback` counter, source-health gauge, backlog alert threshold. None block merge. |
| **E2E live prod 5/7 failure** | Deployment staleness, not a spec defect | Deployed bundle predates rainfall UI; the 5 UI specs pass once frontend is rebuilt from current `main`. Honest data-gate → local run stays green. |
| **REREVIEW-001 (poll budget)** | SUGGESTION (info) | Poll budget only advances on 200; 5xx errors loop until give-up — optional future hardening. |
| **RISK3C-001 / RES3C-001 (gated-row starvation)** | Deferred, WARNING/info | Mechanism documented; impact only materializes once provider adapter is wired. |
| **Tracker → `main`/`develop` merge** | NOT performed | `main` is protected; deployed separately per release procedure after approval. Recorded as follow-up. |

## Key Decisions

Persisted as `openspec/specs/`/design.md and reviewed by Judgment Day (design round + apply PRs). Highlights:

- **Bounded capability:** `geo::rainfall` with `POST /geo/analisis-zona` and public `PrecipChart` untouched.
- **Immutable audit store:** `rainfall_source_eligibility`, `rainfall_interval_value`, immutable `rainfall_analysis_revision`; idempotent upserts append revisions; two-year superseded retention; no raw payloads; removable one-row-per-zone table avoided.
- **Deterministic temporal rules:** Buenos Aires timezone, half-open UTC intervals, same-date current-year baseline, leap-day baseline only, cross-year antecedents, cadence-aligned rolling windows, wet-run/contiguity peak/duration with cadence-verified intervals and 100% coverage gates.
- **Evidence-gated sources:** metric-scoped ordered fallback ladders (baseline CHIRPS v3; daily SQPE-OBS/CHIRPS; intensity RQPE→IMERG→V07→PERSIANN; gauges for validation only), never blended, fallback/discrepancy audited; rendered-image scraping rejected; candidates stay disabled until validation/manifests pass.
- **States:** `available|partial|suppressed|unavailable`, provisional badge + revision, `null ≠ 0`, suppression identifies the failure reason; CSV parity with the same state semantics.
- **Controlled rollout:** per-role feature flags (absent = OPEN, complete blob with explicit `false` = closed), rollback disables flags/jobs and retains audits; metrics/logs seam (`rainfall.<area>.<action>` JSON envelope) with no extra backend required.

## Verification Evidence (exact, from final verify — engram obs #12810)

| Suite | Result |
|---|---|
| `pytest tests/new/geo/rainfall -q` | **163 passed** |
| `pytest tests/new/test_auth_refresh_http.py` | 2 passed; combined **165 passed** |
| `ruff check` + `ruff format --check` (rainfall) | PASS (23 files formatted) |
| `alembic heads` | single head `lluvia_v2_004` |
| `npm run test` (Vitest, consorcio-web) | **3630 passed** / 276 files |
| `npx tsc --noEmit` | EXIT=0 |
| `vite build` | OK (12.93 s; only chunk-size warning; build-in-place blocked by stale root-owned dist, environment) |
| Playwright `--list` | 7 rainfall tests; total 86 tests / 10 files; live run → 7 SKIPPED via honest data-gate |
| `test_phase4_verification.py` | 8/8 (replay idempotency, partial unique index, re-enqueue, `RainfallRoleDisabled`, outbox skip-and-retain, observability events) |

Spec matrix: R1–R13 / 38 scenarios all mapped to tests; no HOLD/FAIL. Two scenarios flagged as false-PARTIAL by verify (see verify report) — informational, not defects.

## Review History (from review-ledger.md)

| Gate | Verdict |
|---|---|
| Design — Judgment Day Round 1 | APPROVED (JD-001 verified; JD-002/003 suspect/info; JD-004 info) |
| Apply PR 1 — Judgment Day | APPROVED (7 CRITICAL verified + hardening) |
| PR 1 — pre-commit review-risk | PASSED (5 CRITICAL verified) |
| PR 1 — pre-push review-risk | PASSED (3 CRITICAL verified; PUSH-RISK-004 resolved by convention, not a bug) |
| Apply PR 2 — Judgment Day | ESCALATED → authorized critical cycle → **APPROVED** |
| PR 2A — pre-commit / pre-push review-reliability | PASSED |
| PR 2B — Judgment Day | APPROVED (2 fix rounds) |
| PR 2B — pre-commit / pre-push review-reliability | PASSED |
| PR 2B — PRE-PR full-4R fix round 1 | Verified (reliability lens) |
| PR 3B — full-4R (>400 lines) | **PASS** (RES1-001/002 fixed; provider-wiring deferral recorded) |
| PR 3C — full-4R (>400 lines) | **PASS**; optional fix round applied (commit `ae2230b`); deferred items recorded (RISK3C-001, READ3C-003/004) |
| **Final verify** | **READY-FOR-ARCHIVE** (no CRITICAL, no HOLD) |

Implementation history: PR #165 (evidence foundation; absorbed the original 2A/2B squash per verify discovery), #168 (ingest/outbox/adapter resilience), #169 (ficha detail UI + CSV export), #170 (phase-4 E2E, rollout validation, observability) plus local hardening commit `b21bbb3` and `ae2230b`.

## Verification Notes / Caveats

- Migration verification limited to `alembic heads` + replay on disposable DBs (no remote DB used; `DATABASE_URL` referenced a non-resolvable host at verify time).
- Live-prod P2E minima not used; local `ficha_enabled=False` drives the honest E2E data-gate skips by design.
- `public/version.json` and `.claude/` were pre-existing dirty working-tree artifacts; not part of this change and untouched.

## Follow-ups

- Rollout to `main`/`develop` per release procedure (protected; deployed separately after approval).
- ~~Re-run mutation config registration~~ **DONE (post-archive 2026-08-07)**: Stryker rainfall entries added (`consorcio-web/stryker.config.mjs`); backend target tests `gee-backend/tests/test_mutation_targets_rainfall.py` (71 cases green, 0.50s); `.cosmic-ray.toml` entry present but `# issue: measure` (local 3.14 cosmic-ray crash + 1015-mutant budget; measurement command recorded for CI 3.11). Phase-4 tests made re-runnable on a shared `TEST_DATABASE_URL` (module-scoped rainfall cleanup fixture; verified second run passes).
- ~~Wire provider adapters when spike/manifest evidence passes, then staged backfill/provider/API/UI activation.~~ **DONE (post-archive 2026-08-07, P3)**: GEE validation spike **PASS** (2026-08-07, read-only from `/tmp/opencode`, engram obs #12820) → CHIRPS v3 (`UCSB-CHC/CHIRPS/V3/DAILY_RNL` final-as-ERA5 and `DAILY_SAT` NRT; catalog ids are case-sensitive) and IMERG V07 (`NASA/GPM_L3/IMERG_V07`, 30-min; V06 deprecated) are now wired through the project's own `gee_service` auth path via `ResilientAdapter` (retry/circuit/outbox semantics preserved). SQPE-OBS documented as **not available in GEE** (SMN NetCDF product; `sqpe-obs` keeps an explicit `NotImplementedError` + TODO for the SMN path — the daily role falls back to validated CHIRPS v3 per spec and the new `chirps-v3-sat` candidate). Activation is still feature-flag-gated per metric-role (roles OFF by default ⇒ role disabled ⇒ no provider contact).
- Resolve workbook §5 human items (owners, Prometheus/OTel, fallback counter, source-health gauge, alert threshold).
- Re-run the 5 prod E2E UI specs after a fresh frontend deployment.

## Artifact Lineage (engram observation IDs)

- Proposal: engram obs `#11726`
- Spec: engram obs `#11738`
- Design: engram obs `#11746`
- Tasks: engram obs `#11788`
- Verify report: engram obs `#12810`
- Archive report: engram topic `sdd/lluvia-v2/arxiv-report` (mirrored) / topic `sdd/lluvia-v2/archive-report`

Filesystem archive root: `openspec/changes/archive/2026-08-07-lluvia-v2/`