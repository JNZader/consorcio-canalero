# Tasks: Deterministic Multi-Parcel Rainfall E2E Harness

> Change: `rainfall-multi-parcel-e2e-harness` · Project: `consorcio-canalero` · Artifact store: hybrid (OpenSpec + Engram topic `sdd/rainfall-multi-parcel-e2e-harness/tasks`, `capture_prompt:false`).
> Authoritative inputs: `proposal.md`, `specs/rainfall-multi-parcel-e2e-harness/spec.md` (RMEH-001..014, 46 scenarios), `design.md` (Judgment APPROVED; warnings info only), `review-ledger.md`.
> Phase scope: tasks ONLY. No apply / verify / archive. No code, test, runtime, commit, push, PR, or build.

## Review Workload Forecast

| Surface | Est. added | Est. deleted | Est. total | Review focus |
|---|---:|---:|---:|---|
| Production code | **0** | 0 | **0** | Any non-zero line is a design failure / escalation (RMEH-014-B). Forbidden surfaces: `consorcio-web/src/**`, `gee-backend/app/**`, migrations, production Compose, parent artifacts. |
| Playwright fixture / helper / spec / Vitest | ~590 | 0 | ~590–840 | Projection, plain click, state machines, freshness, exact bearer, forbidden-seam denylist. |
| Python runner + Pytest | ~420 | 0 | ~420–590 | P0 write boundary, lifecycle, signals, cleanup, accounting, failure taxonomy, redaction. |
| Test Compose / Martin / config / workflow | ~190 | 0 | ~190–280 | Isolation, ports, service scope, manual-only CI, cancellation, no fixed shared names. |
| Docs | ~60 | 0 | ~60–90 | Operator contract, evidence, parent boundary, rollback. |
| **TOTAL non-production** | **~1,260** | 0 | **~1,260–1,800** | Design-authoritative aggregate ceiling = 1,800 (per-file high-water ≈1,802, bounded to 1,800). |

| Budget / decision field | Value | Basis |
|---|---|---|
| 800-PRODUCTION-line budget (owner-set) | **0 / 800 used** → risk **Low** | Forecast production additions = 0, deletions = 0. Constraint: ANY production line = escalation + STOP (not a budget to spend). |
| 400-line review budget risk | **High** | Aggregate ~1,260–1,800 non-production lines >> 400; design mandates full-4R review tier. |
| Tests/docs cognitive burden (excluded from the 800 by owner choice, but real) | **~1,260–1,800 lines** of test/harness/docs/config must be read. This is the substantive reviewer burden — destructive Python lifecycle + destructive-process risk + projection correctness. | Honest disclosure: the 800-prod budget is untouched, but the non-production reading load is the real cost. |
| Chained PRs recommended | **No** | Design D14: no useful independent slice — "the test without safety is dangerous, and the runner without the browser journey proves nothing." |
| Chain strategy | **size-exception** | One owner-approved focused PR carrying a large test-only diff (closest fit among the four skill options; not stacked, not feature-chain). |
| Delivery strategy | **ask-always** | Opening the eventual PR requires a fresh explicit owner approval (RMEH-014-C, design §Review Workload Forecast). |
| Decision needed before apply | **Yes** | Driven by ask-always (owner must approve PR opening) AND ceiling-proximity (aggregate high-water sits at the 1,800 continuation gate). |
| One-PR rationale | The fixture, fail-closed safety runner, deterministic bootstrap, projection helper, dual-viewport state machine, exact accounting, workflow, and JDA handoff form ONE reviewable invariant: every gate depends on every other gate, and no slice is safe or evidentially useful alone (D14, BP-1/BP-5/BP-7). |
| STOP recommendation for owner | **No — conditional proceed.** The orchestrator's STOP trigger fires only if forecast EXCEEDS 1,800 non-production lines OR any production path is required. Forecast is ≤1,800 (design-committed ceiling) and production is 0; trigger does not fire. PROCEED only with (a) owner approval and (b) a hard implementation cap: merged non-production diff ≤1,800 lines and 0 production lines. If apply-phase line count creeps above 1,800, or ANY line touches a forbidden production surface, STOP and re-adjudicate slicing/scope (design BP-7 / RMEH-014-B). |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units (one PR, eleven reviewable commits)

| Unit | Goal / phase | Commit (conventional) | Reqs | Notes |
|---|---|---|---|---|
| W1 | Disposable ownership, preflight, negative safety tests | `feat(rainfall-harness): add disposable ownership/preflight contracts and negative safety tests` | RMEH-001, RMEH-009-A, RMEH-012-B/C | Pure Python identity/lease/evidence + pytest negatives with fakes; zero DB writes. |
| W2 | TS fixture + pure projection/occlusion/cache helper + Vitest | `test(rainfall-harness): add A/B/C fixture, pure Web Mercator/occlusion helper and unit tests` | RMEH-003, RMEH-004, RMEH-005, RMEH-006-A/B, RMEH-013-A | DPR1/DPR2 invariance, canvas offsets, exactly-one-click contract, forbidden-seam denylist. |
| W3 | Python lifecycle + ResourceLease/signal cleanup + manifest/failure taxonomy | `feat(rainfall-harness): add lifecycle runner, signal-safe cleanup, manifest and failure taxonomy` | RMEH-010, RMEH-012 | Builds on W1 pure components; cleanup-before-OwnedBoundary. |
| W4 | Test infra config (Compose/Martin/Playwright/tsconfig/package.json) | `chore(rainfall-harness): add isolated compose stack, martin catalog and harness playwright config` | RMEH-001, RMEH-002-C, RMEH-009-C, RMEH-010, RMEH-014-A | No fixed shared names; 127.0.0.1 only; canary command byte-identical. |
| W5 | Idempotent bootstrap integration (migrations, geometry/data/soils, view provenance, Martin, health, postconditions) | `feat(rainfall-harness): add idempotent disposable bootstrap and postconditions` | RMEH-002, RMEH-003-A/D, RMEH-006-A, JDA-001, JDB-004 | Two-pass bootstrap; bounded rebuild; migration-owned soil view postconditions. |
| W6 | Operator auth + distinct cache identity + strict silent-refresh bearer | `test(rainfall-harness): add distinct rainfall cache identity and exact silent-refresh bearer handling` | RMEH-006, RMEH-013, D10 | Reuses existing addInitScript seam; no store writes; no production login backdoor. |
| W7 | Playwright mobile A→B→C→A state machine | `test(rainfall-harness): add mobile A→B→C→A continuity state machine` | RMEH-007, RMEH-005-A/B | One new `test()` (mobile context); real wheel pre-scroll; scrollTop=0; containment. |
| W8 | Playwright desktop A→B→C→A state machine | `test(rainfall-harness): add desktop A→B→C→A focus continuity state machine` | RMEH-008, RMEH-005 | Same `test()`, second context; focus allowlist; no mobile geometry assertions. |
| W9 | Fail-closed exact accounting + failure classification | `feat(rainfall-harness): add exact 11/0/0 accounting and bootstrap/browser/product classification` | RMEH-009 | Collection gate exactly 11; result gate 11/0/0; zero-skip; 8 one-click records. |
| W10 | Optional `workflow_dispatch` | `ci(rainfall-harness): add optional manual workflow_dispatch with isolation and cleanup` | RMEH-010 | workflow_dispatch only; `permissions: contents: read`; concurrency cancel-in-progress:false; no secrets. |
| W11 | Runbook + JDA-001 handoff + cleanup/rollback proof | `docs(rainfall-harness): add operator runbook, JDA-001 handoff boundary and rollback proof` | RMEH-010-A, RMEH-011, RMEH-012 | `jda-001-handoff.json` only on pass; parent record never mutated; rollback = remove 13 files + 2 enrolments. |

Tests and docs are kept with the behavior they verify (work-unit-commits skill). No commit is useful alone, so all eleven ship in one PR.

## Dependency Graph / Waves

Single-writer serial execution (no parallel worktrees approved). Waves are logical dependency layers; an earlier wave must land before a later wave's GREEN can pass.

```text
Wave 1 (independent):  W1 (Python safety)   W2 (TS fixture+helper)   W4 (infra config)
                          |                      |                         |
Wave 2:                   `-> W3 (lifecycle) ----'                         |
                                |                                            |
Wave 3:                         `-> W5 (bootstrap) <- W2 fixture <- W4 infra-'
                                          |
Wave 4:                                   `-> W6 (auth/cache/bearer)
                                                  |
Wave 5:                                           `-> W7 (mobile) -> W8 (desktop)
                                                                |
Wave 6 (parallel):                                              `-> W9 (accounting)   W10 (workflow)
                                                                          \            /
Wave 7:                                                                   `-> W11 (runbook/handoff/cleanup proof)
```

Critical edges: W2 fixture JSON feeds W5 seed AND W6 cache identity; W4 Compose/Martin feeds W5 integration; W5 bootstrapped stack feeds W6/W7; W7's new `test()` is extended by W8 (one test(), two contexts); W9 needs the final 11-count to exist (post W7/W8); W10 runner invocation needs W3/W5; W11 needs all evidence artifacts.

## Exact Likely Files Added / Modified

| File | Action | Forecast | Owner work unit | Cap rule |
|---|---|---:|---|---|
| `consorcio-web/tests/e2e/fixtures/rainfall-multi-parcel.fixture.json` | create | 100–140 | W2 | F2 sole source for Python seed + TS browser; drift = diagnostic, never auto-rewrite. |
| `consorcio-web/tests/e2e/helpers/rainfallMultiParcelHarness.ts` | create | 220–300 | W2/W6/W7/W8 | If F2 > 300 lines, split a second pure module before continuing (escalate, do not silently exceed). |
| `consorcio-web/tests/unit/rainfallMultiParcelHarness.test.ts` | create | 150–220 | W2/W6 | Vitest pure; no Playwright runtime. |
| `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts` | modify | 120–180 | W7/W8 | ONE new `test()`; existing 10 tests untouched; total = 11. |
| `consorcio-web/tests/e2e/playwright.rainfall-harness.config.ts` | create | 25–40 | W4 | Chromium, one worker, retries 0, JSON reporter, file selection. |
| `consorcio-web/tsconfig.tests.json` | modify | 2–4 | W4 | Enrol new TS helper/unit surfaces in this commit (repo hand-list include rule, per archived precedent). |
| `consorcio-web/package.json` | modify | 1–3 | W4 | One named harness command; canary command byte-identical. |
| `scripts/rainfall_e2e_harness.py` | create | 240–330 | W1/W3/W5/W9/W11 | If F8 > 330 lines, split runner modules before continuing. |
| `scripts/tests/test_rainfall_e2e_harness.py` | create | 180–260 | W1/W3/W5/W9/W11 | Pytest; fakes for unit, real-stack for integration markers. |
| `scripts/tests/rainfall-e2e.compose.yml` | create | 85–120 | W4 | No fixed shared names; 127.0.0.1 only; generated project/volume/network. |
| `scripts/tests/fixtures/martin-rainfall-e2e.yaml` | create | 20–30 | W4 | Publish only `vt_parcelas_catastro` under source `parcelas_catastro`, seven properties. |
| `docs/testing/rainfall-multi-parcel-e2e.md` | create | 60–90 | W11 | Operator prerequisites, command, statuses, evidence, cleanup, JDA boundary, rollback. |
| `.github/workflows/rainfall-multi-parcel-e2e.yml` | create | 60–85 | W10 | workflow_dispatch only; isolated; serialized; cleanup step; artifact retention. |

**13 files total: 10 created, 3 modified.** Zero files under `consorcio-web/src/`, `gee-backend/app/`, migrations, production Compose, or parent change artifacts. Per-unit line apportionment below sums to the design's committed 1,260–1,800 aggregate (shared runner/helper/test files accrue across commits, so per-unit figures are an apportionment, not independent file counts):

| WU | Approx. lines | WU | Approx. lines |
|---|---:|---|---:|
| W1 | ~200–280 | W6 | ~50–100 |
| W2 | ~470–660 | W7 | ~90–130 |
| W3 | ~90–140 | W8 | ~35–60 |
| W4 | ~133–197 | W9 | ~70–110 |
| W5 | ~90–150 | W10 | ~60–85 |
| | | W11 | ~80–130 |

## Phase 1 — W1: Disposable Ownership, Preflight & Negative Safety Tests

- [x] 1.1 RED `scripts/tests/test_rainfall_e2e_harness.py` — unknown/shared DB marker, marker-query error, mismatched marker/target identity, external `DATABASE_URL`, non-loopback host (`0.0.0.0`), pre-existing volume, wrong/fixed Compose project → `BOOTSTRAP_SAFETY_FAILURE` before migrations/fixture writes; recording command adapter proves zero database-mutating commands. GREEN: pure identity/planning/evidence components in `scripts/rainfall_e2e_harness.py` (run_id, compose_project, db_name, marker_nonce, `ResourceLease.plan`, `ownership.json` writer). Accept: `pytest scripts/tests/test_rainfall_e2e_harness.py -k safety -q`. Rollback: delete both new files. Reqs: RMEH-001-A/B/C.
- [x] 1.2 RED cleanup-before-marker + exact-ID/label-cleanup refusal + residual leased resource → `CLEANUP_FAILURE` overrides an otherwise passing run; teardown never searches by prefix, never uses the DB token for Docker teardown, never global-prunes. GREEN: `ResourceLease` reconcile/teardown by recorded immutable ID + cryptographic lease/run/Compose labels. Accept: `pytest ... -k cleanup -q`. Reqs: RMEH-001-B, RMEH-012-B/C.
- [x] 1.3 RED preflight cardinality/distinctness negatives (parcels ≠ 3, soil/source/tile/fact/cache-scope wrong, any A/B/C dimension not pairwise distinct) → abort before browser with diagnostics naming the failing contract and observed values. GREEN: Python-side preflight reading DB + fixture JSON (not the TS validator). Accept: `pytest ... -k preflight -q`. Reqs: RMEH-009-A, RMEH-013-A.

## Phase 2 — W2: TS Fixture + Pure Projection/Occlusion/Cache Helper + Vitest

- [x] 2.1 Create `consorcio-web/tests/e2e/fixtures/rainfall-multi-parcel.fixture.json` — three real-derived polygon rings extracted once from `consorcio-web/public/data/catastro_rural_cu.geojson` + source feature id + canonical geometry SHA-256 `derivation: exact-ring-extraction`; covering soil/zone `MULTIPOLYGON`; committed mobile+desktop camera `{lat,lng,zoom}`; synthetic identity/scope/percentile/accumulation/revision/effectiveCacheKey per design table. Accept: `python -c 'import json;json.load(open(...))'` parses. Rollback: delete file. Reqs: RMEH-003-A/B, RMEH-013-A.
- [x] 2.2 RED `consorcio-web/tests/unit/rainfallMultiParcelHarness.test.ts` — strict `unknown` parsing (no `any`, no direct union), cardinality exactly 3 (one A/B/C), pairwise distinct identity/scope/percentile/accumulation/revision/cache key; missing field / non-ready / unknown scope → throw (no A fallback). GREEN pure fixture validator in `consorcio-web/tests/e2e/helpers/rainfallMultiParcelHarness.ts`. Accept: `pnpm --filter consorcio-web exec vitest run tests/unit/rainfallMultiParcelHarness.test.ts`. Reqs: RMEH-003-A/B, RMEH-006-A/B, RMEH-013-A.
- [x] 2.3 RED projection/geometry: Web Mercator known points; `getBoundingClientRect()` with non-zero `left/top` offsets; DPR 1 vs DPR 2 byte-identical local/page CSS coordinates AND identical integrity outcome (DPR/backing-store diagnostic-only); polygon point-in-polygon; ≥12 CSS px edge clearance; 6 CSS px clickable disk; pairwise non-overlap (disk-vs-disk, disk-vs-other-parcel); clipping; occlusion denylist (ficha sheet, marker/popup, nav/fullscreen/scale controls, pointer-intercepting elements). GREEN pure projection/geometry/occlusion in the helper. Accept: same vitest. Reqs: RMEH-003-C, RMEH-004-A/B.
- [x] 2.4 RED exactly-one-click contract + forbidden-seam denylist: `force:true`, direct store mutation, arbitrary fixed click pixel, scale-label wait, production hook/route/property, reload between selections, multi-select, `queryRenderedFeatures`, helper retry > 0, Playwright retry > 0 → invalid; conformance MUST NOT accept such a browser result. GREEN interaction contract constants + zero-retry policy in the helper. Accept: same vitest. Reqs: RMEH-005-A/B/C.

## Phase 3 — W3: Python Lifecycle Runner + ResourceLease/Signal Cleanup + Manifest/Failure Taxonomy

- [x] 3.1 RED lifecycle phase enum `CREATED→LEASE_PLANNED→PROVISIONING→DATABASE_OWNED→BOOTSTRAPPED→PREFLIGHT_PASSED→TESTS_FINISHED→EVIDENCE_SEALED` (+ `LEASE_CLEANUP→CLEANED`); top-level `try/finally`; `OwnedBoundary` sole constructor = successful marker gate; cleanup valid when `owned=None`. GREEN lifecycle in `scripts/rainfall_e2e_harness.py`. Accept: `pytest ... -k lifecycle -q`. Reqs: RMEH-010-A, RMEH-012-A/B.
- [x] 3.2 RED SIGINT/SIGTERM → cancellation phase + forward termination to active child process group; second signal shortens waits, never changes cleanup target; pre-ownership `ResourceLease` cleanup executes on interruption between Docker creation and manifest append. GREEN signal handling. Accept: `pytest ... -k signal -q`. Reqs: RMEH-010-D, RMEH-012-B.
- [x] 3.3 RED failure taxonomy: the seven `manifest.json` classes (`BOOTSTRAP_SAFETY_FAILURE`, `BOOTSTRAP_PREREQUISITE_FAILURE`, `HARNESS_ACCOUNTING_FAILURE`, `BROWSER_INTEGRITY_FAILURE`, `PRODUCT_ASSERTION_FAILURE`, `CLEANUP_FAILURE`, `PASSED`) are mutually exclusive; redactor removes password/token values and Authorization/Cookie headers; evidence SHA-256 + repository SHA + run/lease identity recorded. GREEN taxonomy + redaction + manifest writer. Accept: `pytest ... -k taxonomy -q`. Reqs: RMEH-009, RMEH-012-B.
- [x] 3.4 GREEN events.jsonl append-only + flushed-after-each-phase (cancellation still leaves an explanation); evidence dir `.artifacts/rainfall-multi-parcel/<run-id>/`. Accept: `pytest ... -k events -q`. Reqs: RMEH-010, RMEH-012.

## Phase 4 — W4: Test Infra Config

- [x] 4.1 Create `scripts/tests/rainfall-e2e.compose.yml` — Postgres+PostGIS/Redis/migrate/backend/Martin/frontend; generated project `rmeh-<run_id-prefix>`, volume, network; every port `127.0.0.1`; no fixed shared names; reject `0.0.0.0`/non-loopback/default `consorcio` DB. Accept: `docker compose -f scripts/tests/rainfall-e2e.compose.yml config` resolves with loopback-only ports (specify; do not execute). Reqs: RMEH-001, RMEH-010.
- [x] 4.2 Create `scripts/tests/fixtures/martin-rainfall-e2e.yaml` — publish only `public.vt_parcelas_catastro` under source `parcelas_catastro` with the seven whitelisted properties. Reqs: RMEH-002-C, RMEH-003.
- [x] 4.3 Create `consorcio-web/tests/e2e/playwright.rainfall-harness.config.ts` — select only `rainfall-v2-detail.spec.ts`, Chromium channel, one worker, `retries: 0`, JSON reporter, evidence dir. Reqs: RMEH-009-C/D, RMEH-014-A.
- [x] 4.4 Modify `consorcio-web/tsconfig.tests.json` (enrol new TS helper + unit test) and `consorcio-web/package.json` (one named harness Playwright command; canary command byte-identical). Accept: `pnpm --filter consorcio-web exec tsc -p tsconfig.tests.json --noEmit`. Reqs: RMEH-010-A, RMEH-014-A. _(committed 5c35d8ba, W4: 67 pytest + 31 vitest green)_

## Phase 5 — W5: Idempotent Bootstrap Integration

- [x] 5.1 GREEN bootstrap ordering in `scripts/rainfall_e2e_harness/bootstrap.py`: re-read `rmeh_ownership`; `alembic upgrade head`; validate head + `parcelas_catastro`/`suelos_catastro`/`zonas_operativas`/PostGIS/geometry types/SRID 4326/indexes; classify both materialized-view slots (absent/present with provenance). Inspect `pg_namespace`/`pg_class.relkind`/owner/comment/columns/indexes/definition digest before any drop/recreate. Accept: integration test against real owned stack. Reqs: RMEH-002-A, RMEH-001.
- [ ] 5.2 GREEN one bounded disposable rebuild (budget = 1): if migration state / migration-owned table / migration-owned `mv_suelos_por_zona` absent-incompatible OR existing migration/unknown `vt_parcelas_catastro` incompatible → recreate run-owned DB, reinstall marker, rerun migrations once, repeat inspection; remaining mismatch aborts (never hand-create migration objects). Reqs: RMEH-002-A, JDA-001, JDB-004. _(unit-covered; real-stack rebuild negative pending 5.7)_
- [x] 5.3 GREEN fixture seed transaction: validate fixture first, then replace run-owned `parcelas_catastro`/`suelos_catastro`/`zonas_operativas` with deterministic rows (stable UUIDs/nomenclatures); one synthetic fixture zone `MULTIPOLYGON` covering A/B/C. Reqs: RMEH-003-A/D.
- [x] 5.4 GREEN `vt_parcelas_catastro` provenance gate (create as materialized view w/ `geometria` + 7 properties + harness run/lease ownership comment IF absent; if exact marker present → drop/recreate/refresh; if migration-owned/unknown → require compatible kind/schema/cols/definition/row behavior, use/refresh, never relabel) + migration-owned `mv_suelos_por_zona` postconditions (`relkind='m'`, exact cols, unique `mv_id`, definition digest, preserved owner/comment, refresh succeeds, exactly one fixture zone/soil row with positive `ha_suelo`). Reqs: RMEH-002-A, JDA-001, JDB-004.
- [x] 5.5 GREEN Martin (health + exactly `parcelas_catastro` source + 200 + non-empty vector-tile body for every declared click target z/x/y; HTTP 204 → `BOOTSTRAP_PREREQUISITE_FAILURE`) + backend `/live` + real ficha POST A/B/C succeeding as `tipo=parcela` (flag effective, not just env-dumped) + frontend `/mapa?lat&lng&zoom` 200 from loopback. Reqs: RMEH-002-C/D, RMEH-006-A.
- [x] 5.6 RED idempotency probe (integration, real stack, marker `@pytest.mark.integration`): run seed + view refresh + all validations a second time in same owned DB; require byte-for-byte/cardinality stable IDs/facts/geometry digests/source catalog/aliases. Reqs: RMEH-002-B, RMEH-003-D. _(test_rainfall_e2e_integration.py, 2 passed on real stack)_
- [ ] 5.7 RED relation-drift negatives (integration): migration-owned incompatible `vt_parcelas_catastro` consumes the one rebuild then fails explicitly; missing/incompatible `mv_suelos_por_zona` → migration-only repair, no ad hoc DDL; Martin empty/204 source → abort before browser. Reqs: RMEH-002-A/C, JDA-001, JDB-004. _(unit-covered incl. bounded martin restart; real-stack negatives pending)_

## Phase 6 — W6: Operator Auth + Distinct Cache Identity + Silent-Refresh Bearer

- [x] 6.1 GREEN fixture-aware `page.route` rainfall boundary + deterministic silent-refresh `/auth/jwt/refresh` rotated synthetic token in `rainfallMultiParcelHarness.ts` (reuses existing `addInitScript` sessionStorage seam; no application store writes; no production login backdoor; no real credential/cookie/secret). Reqs: RMEH-006-A, D10, RMEH-013-A. _(pure contracts: TokenLifecycle, activeToken/observeRefresh, refreshRouteContract, classifyRainfallRequest, assertExactBearer, resolveParcelByIdentity, readyResponseFor, assertResponseMatchesTarget; page.route wiring lands in W7/W8 importing these)_
- [x] 6.2 RED exact-bearer: every rainfall scope/analysis/series/CSV/XLSX request carries `Authorization: Bearer <active synthetic token>`; token never in URL; rotated token after refresh; unknown identity → fail route (no A fallback); bodies ready with matching scope/percentile/accumulation/analysis+data+metric revision; no queued/error normalization. Files: `rainfallMultiParcelHarness.test.ts` + request observers in `rainfall-v2-detail.spec.ts`. Reqs: RMEH-006-A/B/C, RMEH-013-A, D10. _(vitest 9 tests; spec observers deferred to W7/W8)_
- [x] 6.3 RED cache-aliasing negative: two parcels share an effective cache key, or one parcel receives another parcel's cached response, or any A-only value remains current after B/C → preflight or transition freshness fails closed with diagnostics naming aliased identities/scopes/revisions/observed response. Files: `rainfallMultiParcelHarness.test.ts`. Reqs: RMEH-013-B/C. _(vitest 5 tests: assertCacheKeysDistinct + assertFreshResponse + stale-dimension negatives)_

## Phase 7 — W7: Playwright Mobile A→B→C→A

- [ ] 7.1 GREEN mobile state-machine helper in `rainfallMultiParcelHarness.ts`: NEW CONTEXT → navigate supported `?lat&lng&zoom` → plain-click A (exactly one `canvas.click({position})`, no `force`) → activate `Lluvia` once → READY_A (Lluvia label, ficha identity = A, target scope/percentile/accumulation, technical revision) + complete-card containment inside visible body + stage `medio`. Reqs: RMEH-007-A, RMEH-005-A.
- [ ] 7.2 GREEN mobile transitions: before EACH transition prove `scrollHeight > clientHeight` AND wheel over the real sheet body until `scrollTop > 0` (delta = `scrollHeight - clientHeight`; forbid direct `scrollTop` assignment / `scrollIntoView` / keyboard); attach `{range, beforeScrollTop, afterWheelScrollTop}`; then plain-click B / C → READY_B / READY_C + Lluvia + exact B/C facts replace prior + `scrollTop === 0` + complete ready card inside visible body (±1 CSS px). Reqs: RMEH-007-B/C, RMEH-005-B.
- [ ] 7.3 GREEN mobile C→A fresh: require a NEW A scope/analysis request + ready response sequence newer than C's; A exact revision/facts; absence of every C-only fact from current surfaces (no stale C / aliased A cache); `scrollTop=0` + containment. Reqs: RMEH-007-D, RMEH-013-B.
- [ ] 7.4 RED add exactly ONE new `test()` (mobile context) in `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts` exercising 7.1–7.3; attach `projection-mobile.json`, `request-trace.json`, screenshots/trace on failure. Accept: `pnpm --filter consorcio-web exec playwright test --config=tests/e2e/playwright.rainfall-harness.config.ts --list` reports the count INCREASED BY EXACTLY 1. Reqs: RMEH-007, RMEH-005-A/B.

## Phase 8 — W8: Playwright Desktop A→B→C→A (same `test()`, second context)

- [ ] 8.1 GREEN desktop context inside the SAME `test()` from 7.4: committed desktop viewport + camera; plain-click A → B → C → A; `assertTargetReady` after each (all five dimensions replaced, no prior-only value current). Reqs: RMEH-008-A, RMEH-005.
- [ ] 8.2 GREEN desktop focus continuity: capture active element before each click; after readiness focus must be `body`, the canvas, or the same visible map interaction ancestor; a non-body active element must intersect the viewport and must NOT be hidden/inert/disabled/mobile-only/unrelated. NO sheet-height, visible-body containment, body scroll-range, or scroll-reset assertion on desktop. Reqs: RMEH-008-B.
- [ ] 8.3 Accept: total discovered test count stays EXACTLY 11 (one `test()`, two contexts); manifest records EIGHT one-attempt selection records (4 mobile + 4 desktop), attempt count `1` and click count `1` in each; helper retry count `0`, Playwright retry count `0`. Reqs: RMEH-005, RMEH-009-D.

## Phase 9 — W9: Fail-Closed Exact Accounting + Failure Classification

- [ ] 9.1 GREEN collection gate in `scripts/rainfall_e2e_harness.py`: run Playwright collection with JSON output BEFORE browser execution; require EXACTLY 11 discovered tests; zero/ten/twelve/omitted file/`.only`/collection-error → `HARNESS_ACCOUNTING_FAILURE`. Reqs: RMEH-009-C.
- [ ] 9.2 GREEN result gate: parse JSON reporter + interaction evidence; require 11 passed / 0 failed / 0 skipped / 0 interrupted / 0 flaky / 0 Playwright-retried; helper retry count `0`; exactly 8 selection records; attempt `1` / click `1` each; expected project/file identity. Reqs: RMEH-009-D.
- [ ] 9.3 RED zero-skip gate: existing soft-gate helpers may still express environmental skips for ordinary runs, but the owned preflight makes prerequisites mandatory and any residual soft skip turns the run red (a missing prerequisite is never translated into a test annotation). Files: `scripts/tests/test_rainfall_e2e_harness.py`. Reqs: RMEH-009-B.
- [ ] 9.4 GREEN failure classification: bootstrap (safety/prerequisite) vs `BROWSER_INTEGRITY_FAILURE` (camera/projection/occlusion/tile before pointer) vs `PRODUCT_ASSERTION_FAILURE` (post-click request/identity/continuity/freshness/scroll/geometry/focus) — exclusive classes from pre-click evidence + request/render trace; diagnostic evidence retained without secrets. Reqs: RMEH-009-A/D, RMEH-006-B.

## Phase 10 — W10: Optional `workflow_dispatch`

- [ ] 10.1 Create `.github/workflows/rainfall-multi-parcel-e2e.yml` — `workflow_dispatch` only; `permissions: { contents: read }`; ONE global concurrency group with `cancel-in-progress: false` (dispatches serialize, do not share mutable resources, do not cancel an older cleanup); 45-minute job timeout; checkout + pinned major setup actions + Node 22 + lockfile install + locked Chromium + the same Python runner used locally; NO repository/environment secrets (all DB/auth values synthetic run values). Reqs: RMEH-010-B/C.
- [ ] 10.2 RED/contract `gee-backend/tests/test_ci_workflow_contracts.py` — assert this workflow is NOT referenced by the required `Frontend`/`Backend`/`Deploy` gates and is NOT in the production canary three-spec read-only allowlist. Reqs: RMEH-010-B, RMEH-014-A.
- [ ] 10.3 GREEN `if: always()` artifact upload with 14-day retention and `if-no-files-found: error` (ownership.json exists before provisioning); explicit cleanup step calling the runner's idempotent cleanup command if the main process was externally killed before its trap completed. Reqs: RMEH-010-D, RMEH-012-A/B.

## Phase 11 — W11: Runbook + JDA-001 Handoff + Cleanup/Rollback Proof

- [ ] 11.1 GREEN `jda-001-handoff.json` emitted ONLY on a complete pass: source change `rainfall-multi-parcel-e2e-harness`; fixture + evidence digests; exact 11/0/0 result; mobile/desktop transition evidence references; `parent_record_mutated: false`; proposed action "open a separate follow-up review transaction for JDA-001". Reqs: RMEH-011-A.
- [ ] 11.2 RED parent-boundary: runner + workflow NEVER write `openspec/changes/lluvia-ux-tarjeta/review-ledger.md`, never update an Engram parent topic, never extend Judgment Day rounds, never declare the parent APPROVED; a `PRODUCT_ASSERTION_FAILURE` emits evidence requesting a separate remediation decision and this change stays test-only. Files: `scripts/tests/test_rainfall_e2e_harness.py`. Reqs: RMEH-011-A/B.
- [ ] 11.3 RED rollback proof: rollback = remove only the 13 file-architecture artifacts + the 2 test-config enrolments; NO production/schema/shared-data/parent rollback; any residual disposable resource cleaned only via exact recorded lease identity + immutable Docker labels before removing the runner. Files: `scripts/tests/test_rainfall_e2e_harness.py`. Reqs: RMEH-012-D, RMEH-001.
- [ ] 11.4 Create `docs/testing/rainfall-multi-parcel-e2e.md` — operator prerequisites, local command, statuses (PASSED + six failure classes), evidence layout, cleanup contract, JDA-001 boundary, rollback procedure, "not a required CI check" notice. Reqs: RMEH-010-A, RMEH-011, RMEH-012.

## Task → RMEH Scenario Matrix (46 scenarios; coverage must total 46)

| Req | Scenario | Task(s) | Verification layer |
|---|---|---|---|
| RMEH-001 | 001-A Owned disposable accepted | 1.1, 5.1 | Pytest safety positive + bootstrap ownership evidence |
| RMEH-001 | 001-B Unknown/shared marker aborts | 1.1 | Pytest negative (zero DB-mutating commands) |
| RMEH-001 | 001-C Marker/identity mismatch aborts | 1.1 | Pytest negative |
| RMEH-002 | 002-A Missing prereqs repaired + validated | 5.1, 5.4 | Bootstrap integration (post-repair validation) |
| RMEH-002 | 002-B Complete prereqs idempotent | 5.6 | Idempotency probe (two-pass) |
| RMEH-002 | 002-C Missing/empty Martin fails | 5.5, 5.7 | Martin 204/empty negative |
| RMEH-002 | 002-D Reachability/feature flag invalid | 5.5 | Backend `/live` + ficha POST negative |
| RMEH-003 | 003-A Cardinality & identities stable | 2.1, 2.2, 5.3 | DB count 3 + fixture validator |
| RMEH-003 | 003-B Facts ready & pairwise distinct | 2.2, 5.5 | Fixture validator + pre-browser contract |
| RMEH-003 | 003-C Click targets don't overlap | 2.3 | Vitest projection/geometry/disk overlap (both viewports) |
| RMEH-003 | 003-D Repeated bootstrap reproduces fixture | 5.6 | Idempotency probe byte-for-byte stable |
| RMEH-004 | 004-A Supported camera yields valid targets | 2.3, 7.1, 8.1 | Vitest DPR1/DPR2 + offset + Playwright pre-click integrity |
| RMEH-004 | 004-B Drift/occlusion aborts interaction | 2.3, 8.3 | Vitest occlusion/clipping + BROWSER_INTEGRITY_FAILURE |
| RMEH-004 | 004-C No production map seam | 2.4, 8.3, review | Forbidden-seam denylist + static production-diff gate (RMEH-014-B) |
| RMEH-005 | 005-A Plain click drives parcel request path | 7.4, 8.3 | Exactly-one-click + `tipo=parcela` request trace |
| RMEH-005 | 005-B Sequence stays in one page session | 7.4, 8.1 | No reload / no multi-select assertions |
| RMEH-005 | 005-C Forbidden seam invalidates conformance | 2.4, 8.3 | Forbidden-seam static test + manifest click count = 1 |
| RMEH-006 | 006-A Pre-browser contracts match | 2.2, 5.5 | Fixture validator + backend ficha POST |
| RMEH-006 | 006-B Missing/non-ready fact aborts | 2.2, 5.5 | Validator negative; aborts before browser |
| RMEH-006 | 006-C Displayed facts match latest target | 7.1–7.3, 8.1 | `assertTargetReady` latest-response/render matching |
| RMEH-007 | 007-A Mobile starts from ready A | 7.1, 7.4 | Playwright mobile READY_A + containment |
| RMEH-007 | 007-B Mobile A→B reset & refresh | 7.2, 7.4 | READY_B + scrollTop=0 + containment |
| RMEH-007 | 007-C Mobile B→C reset & refresh | 7.2, 7.4 | READY_C + scrollTop=0 + containment |
| RMEH-007 | 007-D Mobile C→A fresh | 7.3, 7.4 | READY_A2 newer response + no stale C |
| RMEH-008 | 008-A Desktop fresh facts | 8.1, 8.3 | Desktop READY_A/B/C/A2 |
| RMEH-008 | 008-B Desktop focus stable, no mobile geometry | 8.2 | Focus allowlist; no geometry assertions |
| RMEH-009 | 009-A Preflight rejects bad cardinality/distinctness | 1.3, 5.7 | Pytest preflight negative |
| RMEH-009 | 009-B Missing prereq can't be soft skip | 9.3 | Zero-skip gate (soft skip → red) |
| RMEH-009 | 009-C Empty discovery fails | 9.1 | Collection gate (zero discovered → HARNESS_ACCOUNTING_FAILURE) |
| RMEH-009 | 009-D Successful run exact 11/0/0 | 9.2, 8.3 | Result gate 11 passed/0 failed/0 skipped |
| RMEH-010 | 010-A Operator runs harness locally | 3.1, 5.5, 11.4 | Local lifecycle = same contract |
| RMEH-010 | 010-B Manual workflow not PR-required | 10.1, 10.2 | workflow_dispatch-only + workflow-contract test |
| RMEH-010 | 010-C Concurrent dispatches isolated | 3.1, 10.1 | Unique lease identity + concurrency cancel-in-progress:false |
| RMEH-010 | 010-D Canceled run retains safe evidence | 3.2, 10.3 | Signal cleanup + `if:always` artifact + residual check |
| RMEH-011 | 011-A Passing evidence separate transaction | 11.1, 11.2 | `jda-001-handoff.json` + no parent path write |
| RMEH-011 | 011-B Failing product → separate remediation | 11.2 | PRODUCT_ASSERTION_FAILURE evidence + no scope creep |
| RMEH-012 | 012-A Success cleans owned resources | 3.1, 10.3, 11.3 | Teardown success + shared unchanged |
| RMEH-012 | 012-B Failed run still cleans | 3.2, 11.3 | Failure-path cleanup + diagnostics retained |
| RMEH-012 | 012-C Cleanup failure not green | 1.2, 3.1 | Residual leased resource → CLEANUP_FAILURE overrides pass |
| RMEH-012 | 012-D Rollback no production state | 11.3 | Rollback = remove 13 files + 2 enrolments only |
| RMEH-013 | 013-A Scope/cache identities pairwise distinct | 2.2, 6.1 | Fixture validator cache-key distinctness |
| RMEH-013 | 013-B Stale A facts after B/C fail | 7.3, 8.1 | A-after-C freshness assertion |
| RMEH-013 | 013-C Cache aliasing fails preflight/browser | 6.3, 7.3 | Aliasing negative + stale-card failure |
| RMEH-014 | 014-A Bounded browser scope | 4.3, 9.2 | Chromium/ready-only config + accounting |
| RMEH-014 | 014-B No production seam | review + 2.4 | Static production-diff gate + forbidden-seam denylist |
| RMEH-014 | 014-C Owner-gated focused delivery | forecast + 11.4 | ask-always owner gate (this forecast) |

**Coverage total: 14 requirements × 46 scenarios = 46/46 covered.** Every scenario maps to at least one executable layer (Pytest unit / Vitest unit / Bootstrap integration / Playwright E2E / Manual workflow / static review) per the design's Scenario Traceability. None relies solely on documentation.

## Mutation Targets

`openspec/config.yaml` `rules.tasks`: "Small TDD-first tasks, add mutation targets and thresholds per module." This change touches **zero production modules** (RMEH-014-B; production churn = 0), so no cosmic-ray/mutation target is added to a production gate. The repo's `.cosmic-ray.toml` is Python-only and gates production surfaces; the new files are all test/harness/config/docs. The two candidate PURE-LOGIC surfaces (the TS Web Mercator/occlusion helper `rainfallMultiParcelHarness.ts` pure portion, and the Python safety/lease/manifest/taxonomy pure components) are the natural mutation targets IF a harness-mutation gate is later introduced — but adding such a gate is out of scope for this change (would itself be a production/CI surface change). Threshold: N/A. No uncommented production mutation enrollment is added.

## Rollback Boundary (summary)

Rolling back this capability removes ONLY: the 10 created files + the 3 modified file deltas (revert `rainfall-v2-detail.spec.ts` to its 10-test state, drop the 2 tsconfig/package.json enrolments). It requires NO database downgrade, NO shared cleanup, NO parent-artifact rewrite (JDA-001 ledger + Engram parent topic untouched), NO production/schema/behavior rollback. Any residual disposable resource is cleaned only through its exact recorded lease identity + immutable Docker labels BEFORE removing the runner. The current dirty parent closeout diff is preserved — tasks touch only new follow-up paths and the approved test/config surfaces listed in the file table above.

## Evidence

<!-- evidence:begin -->
- [read] The proposal requires A→B→C→A, URL camera projection, plain parcel clicks, exact 11/0/0, zero production churn, and one owner-approved focused PR. src=openspec/changes/rainfall-multi-parcel-e2e-harness/proposal.md:7-58
- [read] The specification defines 14 requirements and 46 scenarios (RMEH-001..014) and forbids production hooks/routes/props/store exports, force-click, reload, store mutation, scale waits, fixed pixels, component-test adoption, real GEE, auth redesign, and browser/role/state matrices beyond approved scope. src=openspec/changes/rainfall-multi-parcel-e2e-harness/specs/rainfall-multi-parcel-e2e-harness/spec.md:13-415
- [read] The design (Decision Register D1–D14, File Architecture, Bootstrap Postcondition Matrix, Projection, State Machines, Auth, Accounting, Workflow, JDA Handoff) commits production-code forecast 0 and a non-production aggregate of 1,260–1,800 lines, with 1,800 as the hard continuation gate and "stop and re-adjudicate slicing/scope" if exceeded or if any production line is required. src=openspec/changes/rainfall-multi-parcel-e2e-harness/design.md:85-104,707-727
- [read] The design fixes the five CRITICAL Judgment-Day findings (CSS projection from live canvas rect + DPR diagnostic-only; exactly one unforced click/attempt, zero retries; pre-provision ResourceLease independent of OwnedBoundary; parcel-view provenance inspection + bounded rebuild; migration-only soil-view repair + postconditions). src=openspec/changes/rainfall-multi-parcel-e2e-harness/design.md:330-393,135-214
- [read] The review ledger records design Judgment APPROVED after fix round 1 (5 CRITICAL fixed and verified); two WARNING rows remain `info` and are not independently fixed/re-reviewed. src=openspec/changes/rainfall-multi-parcel-e2e-harness/review-ledger.md:1-70
- [read] The OpenSpec config `rules.tasks` requires "Small TDD-first tasks, add mutation targets and thresholds per module"; the archived `lluvia-insights/tasks.md` establishes this repo's rich RED/GREEN + Coverage matrix + Workload Forecast convention. src=openspec/config.yaml:6-10, openspec/changes/archive/2026-08-11-lluvia-insights/tasks.md:1-180
- [inferred] The 800-PRODUCTION-line owner budget is untouched (forecast production = 0 added / 0 deleted) because every named file lives under test/harness/config/docs paths and the design's forbidden-surface list excludes `consorcio-web/src/**`, `gee-backend/app/**`, migrations, production Compose, and parent artifacts. from=E3
- [inferred] The forecast's aggregate upper bound (1,800) equals the design's continuation-gate ceiling exactly; naive per-file high-water sums reach ~1,802 (rounding), so the orchestrator's STOP trigger ("exceeds 1,800 OR any production path required") does NOT fire, but ceiling-proximity plus ask-always forces "Decision needed before apply: Yes" and a hard ≤1,800 / 0-production implementation cap. from=E3
- [assumed] Acceptance commands (`pytest`, `vitest`, `playwright --list`, `docker compose config`, `tsc --noEmit`) are SPECIFIED for the apply phase, not executed in this tasks-only phase (session contract: no build/test/runtime). unverified=apply phase must run each acceptance command in the correct cwd and observe the stated outcome before closing each task.
<!-- evidence:end -->