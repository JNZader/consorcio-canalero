# Tasks: Rainfall v2 Technical Analysis

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 2,000–3,200 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Approved split | evidence → deterministic core → API policy contract → UI/export/operations |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Delivery-boundary decision: Resolved — four slices approved
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Approved Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | Evidence gate, contracts, migration | PR 1 | Complete; providers disabled |
| 2A | Deterministic scope, PostGIS, temporal rules and API groundwork | PR 2A | Current; exactly 400 raw production lines |
| 2B | API policy contract | PR 2B | Planned; completes unchecked 2.3–2.4 |
| 3 | Ficha UI, export and operations | PR 3 | Planned; includes 2.5 and phases 3–4 |

## Phase 1: Evidence and foundation

- [x] 1.1 **RED**: Add adapter-contract and spike golden tests under `gee-backend/tests/new/geo/rainfall/` for access/licence, units, UTC boundaries, cadence, coverage, revision, discrepancy, known events and scrape-rejection.
- [x] 1.2 **GREEN**: Create `gee-backend/app/domains/geo/rainfall/{models,schemas,ports,adapters/,policy}.py` and Alembic migration for eligibility, immutable intervals and analysis revisions; enforce versioned source-role policy and no blending.
- [x] 1.3 **REFACTOR**: Add versioned manifests and approval/audit fixtures; keep every candidate disabled until role criteria pass, with metric-specific fallback ladders.
- [x] 1.4 Add source/scope/data/policy revision indexes, two-year superseded-revision retention, idempotent backfill checkpoints, and prohibit raw payload persistence/generic observation migration.

## Phase 2: Deterministic backend

- [x] 2.1 **RED**: Test `scope.py` for stable zone/basin identities, parcel intersection choices/regional labels, ambiguity/no-match, and parcel/geometry direct-compute rejection.
- [x] 2.2 **GREEN**: Implement `scope.py`, `repository.py`, `temporal.py` and `service.py`: Buenos Aires local dates, leap-day rule, same-date baseline, cross-year antecedents, cadence-aligned rolling P30/P60/P3h/P24h and deterministic event suppression/peak/duration.
- [x] 2.3 **REFACTOR**: Centralize versioned coverage/quality/duration thresholds; make null distinct from zero and isolate failed metrics. Implementation corrected in PRE-PR full-4R fix round 1; verified by scoped reliability re-review (all ten candidates verified).
- [x] 2.4 **RED/GREEN**: Add `router.py` and shared snapshot metric-row serializer with tests for admin/operator auth, CSRF/content-type/body limits/rate limit, JSON/CSV parity, revisions, states, provenance and denied disclosure. Implementation corrected in PRE-PR full-4R fix round 1; verified by scoped reliability re-review (all ten candidates verified).
- [x] 2.5 Add `tasks.py`, adapter timeout/quota/retry/circuit/cache behavior and Celery Beat/outbox ingest/revisit/backfill; requests read DB/Redis and queue labelled missing work. Fixed in PR 3A round 1-A: durable outbox commit, idempotent enqueue, partial unique index, `process_outbox` consumer with SKIP LOCKED/backoff/max retries, and source-role resolution. Fixed in PR 3A round 1-B: enforce `ResilientAdapter` timeout with func_timeout/SIGALRM fallback and share circuit-breaker state across workers via `CircuitStore` (`MemoryCircuitStore` for tests, `RedisCircuitStore` for production).

## Phase 3: Authenticated ficha and export

- [x] 3.1 **RED**: Add Vitest tests for access, resolve/switch, metric states/badges/reasons, live announcements and textual charts.
- [x] 3.2 **GREEN**: Create `consorcio-web/src/lib/api/rainfall.ts`, `hooks/useRainfallAnalysis.ts`, and `components/map2d/rainfall/`; use strict flat contracts, labelled controls and TanStack Query.
- [x] 3.3 Mount `RainfallDetailPanel` conditionally in `FichaTerritorialPanel.tsx`; preserve public `PrecipChart.tsx`, regional-estimate labels and authorized CSV download.
- [ ] 3.4 **REFACTOR**: Share displayed/exported state formatting without manual memoization; add mutation targets for policy, suppression, temporal windows and CSV parity. PARTIALLY DONE in PR 3B: shared formatting landed as `rainfallFormat.ts` (single formatter for display/export semantics, no manual memoization — React 19). DEFERRED: Stryker mutation-target registration for the rainfall UI slice. Correction (documented at archive, verify report): the earlier wording "backend policy/suppression/temporal/CSV-parity mutation targets already exist per 2.4" was inaccurate — there are NO rainfall entries in `gee-backend/.cosmic-ray.toml`, `gee-backend/.cosmic-ray.candidate.toml`, or `consorcio-web/stryker.config.mjs` (verified by grep, 0 matches). Deferred because 3.1–3.3 alone exceeded the 400-line production budget (650 raw lines); the deferral remains non-blocking and the mutation-target registration stays open for a follow-up.

## Phase 4: Verification and controlled rollout

- [x] 4.1 Replace stale rainfall E2E with Playwright ficha authorization, parcel scope switching, inaccessible detail/export, state disclosure and CSV parity flows with accessible selectors.
- [x] 4.2 Validate migration/replay/idempotency and feature flags; run provider spike before each metric-role activation, then staged backfill/provider/API/UI rollout with rollback disabling flags/jobs but retaining audits. Validation portion complete and verified in `test_phase4_verification.py` (replay no-op on double backfill, interrupted-checkpoint re-run, DB-level partial unique index on outbox pending (migration `lluvia_v2_004`), re-enqueue after terminal, disabled-role gate raising `RainfallRoleDisabled`, outbox skip-and-retain for gated roles, flag-off retains eligibility/interval/outbox audits). `alembic downgrade lluvia_v2_003 && upgrade head` executed clean; single head `lluvia_v2_004`. Rollback procedure documented in `docs/lluvia-v2-observability-workbook.md` §4. Provider adapters remain evidence-gated stubs by design (see review-ledger PR 3B deferral: `provider adapter not wired`); the staged provider/backfill activation runs once evidence/manifests pass — not executed in this apply batch.
- [x] 4.3 Add metrics/logs for latency, gaps, fallback, revisions and source health; document owners, leaving open roles/events/gauges human. `metrics.py` ships a dependency-free seam over the app's existing structlog foreign_pre_chain (JSON envelope, no extra backend required). Events wired at call sites: `rainfall.analysis.served` (latency_ms), `rainfall.csv.served`, `rainfall.outbox.{reused,queued,gated,done,failed,delayed}` — stable `rainfall.<area>.<action>` names verified by test. `docs/lluvia-v2-observability-workbook.md` created as the metric catalogue + owners + rollout/rollback contract; open items (Prometheus/OTel wiring, fallback counter, source-health gauge, backlog alert threshold, named owners) deliberately left for manual decision.
