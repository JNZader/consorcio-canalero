# Review ledger — `rainfall-multi-parcel-e2e-harness`

Artifact store: hybrid (this file + Engram topic
`sdd/rainfall-multi-parcel-e2e-harness/review-ledger`).

## Design phase — Judgment Day round 1 (2026-08-15)

Two blind judges reviewed `proposal.md`, the RMEH-001..014 specification, and `design.md`.
Their convergence supplies adversarial verification; no review-refuter tasks were used.

### Convergence map

| Judge A | Judge B | Resolution |
|---|---|---|
| JDA-002 | JDB-001 | Confirmed CRITICAL — DPR projection mixes backing-store and CSS pixels |
| JDA-003 | JDB-002 | Confirmed CRITICAL — helper click retries can produce false-green single-click evidence |
| JDA-004 | JDB-003 | Confirmed CRITICAL — cleanup authority is unavailable after early marker failure |
| JDA-001 | JDB-005 | Same ownership-drift risk; A=CRITICAL, B=WARNING — owner promoted JDA-001 for fix; warning counterpart remains info |
| — | JDB-004 | B-only CRITICAL — owner promoted for fix; missing migration-owned soil view must use migration repair and postconditions |
| JDA-005 | — | A-only WARNING — integrity-stage failure classification is undefined |

### Findings

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| JD-DES-001 | judgment-day | `design.md:330-356` | CRITICAL | verified | Both scoped judges verified CSS projection from live `getBoundingClientRect()` dimensions/offsets, diagnostic-only DPR/backing dimensions, and DPR 1/2 invariance probes. |
| JD-DES-002 | judgment-day | `design.md:75-78,377-393,500-508` | CRITICAL | verified | Both scoped judges verified pre-interaction integrity sampling, exactly one unforced click/attempt per selection, zero helper/Playwright retries, and immediate failure on missing/wrong request or identity. |
| JD-DES-003 | judgment-day | `design.md:135-173,529-554` | CRITICAL | verified | Both scoped judges verified that pre-provision `ResourceLease` owns exact Docker cleanup independently of post-marker DB-write `OwnedBoundary`. |
| JDA-001 | judgment-day | `design.md:73,182-214,240` | CRITICAL | verified | Both scoped judges verified pre-mutation relation provenance inspection, exact harness-marker replacement only, preservation of compatible migration/unknown objects, and one bounded rebuild then explicit failure for incompatible drift. |
| JDB-004 | judgment-day | `design.md:182-214,232-247` | CRITICAL | verified | Both scoped judges verified migration-only soil-view repair and mandatory kind/schema/definition/index/refresh/ownership/row postconditions. |
| JDB-005 | judgment-day | `design.md:199-207,772` | WARNING | info | assessment=theoretical. Warning counterpart remains canonical WARNING/info and was not independently fixed or re-reviewed; the owner-approved CRITICAL JDA-001 drove the relation-provenance design change. |
| JDA-005 | judgment-day | `design.md:370-393,510-524` | WARNING | info | assessment=real. Warning remains canonical WARNING/info and was not independently fixed or re-reviewed. The exhaustive failure taxonomy now places pre-click camera/projection/occlusion failures under `BROWSER_INTEGRITY_FAILURE` only as mechanically necessary for the five approved fixes. |

### Round outcome

- Confirmed BLOCKER/CRITICAL: **3**
- Suspect single-judge CRITICAL: **2**
- INFO warnings: **2**
- Fixes applied: **0**

**Initial judgment: ESCALATED ⚠️ — owner authorization was required before fix round 1.**

## Design fix round 1 (2026-08-15)

Owner authorization: `Corregir los cinco`.

- Fixed `JD-DES-001`: projection is entirely in Playwright CSS coordinates from the live canvas
  rectangle; DPR/backing dimensions are diagnostic only, with deterministic DPR 1/2 probes.
- Fixed `JD-DES-002`: bounded probes remain pre-interaction; every intended selection has exactly
  one plain click, one helper attempt, zero helper retries, and zero Playwright retries.
- Fixed `JD-DES-003`: pre-provision `ResourceLease` controls exact Docker teardown independently
  from post-marker `OwnedBoundary`, so marker failure still cleans without enabling DB writes.
- Fixed promoted `JDA-001`: parcel-view kind/schema/owner/comment/definition are inspected before
  mutation; only exact harness ownership permits replacement, while future migration drift is
  preserved, rebuilt once, or failed explicitly.
- Fixed promoted `JDB-004`: the migration-owned soil view is repaired only by one bounded database
  rebuild/migration pass and is mandatory in the postcondition matrix, including row behavior.
- `JDB-005` and `JDA-005` remain `WARNING`/`info`; neither was independently fixed or re-reviewed.
- Production-code forecast remains **0 lines**; RMEH-001..014 and all 46 scenarios remain mapped.

Fixes applied: **5 CRITICAL findings**. Status is `fixed`, not `verified`; scoped dual re-judgment
has not run in this fix-only round, so no terminal approval is recorded.

## Design fix round 1 — scoped re-judge

Both blind judges reviewed only the persisted ledger and fix-touched design sections. All five
CRITICAL resolutions were independently verified; no contradiction survived. Warning rows stayed
`info` and were not re-reviewed.

**JUDGMENT: APPROVED ✅ — 5 CRITICAL findings fixed and verified in round 1 of 2.**

## Apply phase — Judgment Day (execution half, W4–W11, commits 5c35d8ba..db400e06)

Judge B (adversarial, blind) reviewed the apply diff — the runner (`scripts/rainfall_e2e_harness/*`),
the compose stack, the workflow, and the browser helper/spec. Static code review with exact-line
evidence; no harness execution. Sweep budget: 2 sweeps (1 used, exhaustive).

### Findings (Judge B)

| id | lens | location | severity | status | assessment | evidence |
|---|---|---|---|---|---|---|
| JD-APP-001 | judgment-day | `safety.py:189-194`, `driver.py:259,274`, `driver.py:123,136`, `rainfall-e2e.compose.yml:26,35,38,50,56,68,100,113,127,158,170,199,219,224` | BLOCKER | fixed | real | Identity/compose naming disconnect. `RunIdentity.plan` generates random `run_id=token_hex(16)`, `database_name=rmeh_<run_id[:10]>`, init file `rmeh-init-<run_id[:10]>.sql` (driver.py:274). Compose derives ALL names from `${RMEH_RUN_ID_PREFIX:-probedefault}` and mounts `./rmeh-init-${RMEH_RUN_ID_PREFIX:-probedefault}.sql`. `stack_env()` sets `RMEH_RUN_ID_PREFIX=self.run_id_prefix` = env or `""` → resolves `probedefault`. Local runbook: bind source `rmeh-init-probedefault.sql` missing → `compose up` fails → BROWSER_INTEGRITY_FAILURE; even if mounted, marker gate queries `rmeh_<random>` but DB is `rmeh_probedefault` → BootstrapSafetyFailure. Workflow (`RMEH_RUN_ID_PREFIX: gha`): compose expects `rmeh-init-gha.sql`/`rmeh_gha`, driver writes random names → same failure. Integration tests pass ONLY because they manually construct `RunIdentity(run_id=prefix, database_name=f"rmeh_{prefix}")` aligned to env (test_rainfall_e2e_integration.py, probe_rainfall_bootstrap.py). The driver never aligns. Both documented execution paths (local runbook + GitHub workflow) cannot work as shipped. |
| JD-APP-002 | judgment-day | `rainfall-v2-detail.spec.ts:1452-1454`, `driver.py:455-465,318-320,349` | BLOCKER | fixed | real | Manifest gate can never pass. Spec only `testInfo.attach('manifest.json', { body })` → embedded base64 inside `playwright-results.json` (JSON reporter); nothing writes `evidence_dir/manifest.json`. `_read_manifest_records` reads `evidence_dir/manifest.json` → missing → `[]` → `assert_manifest_contract([])` raises HarnessAccountingFailure → HARNESS_ACCOUNTING_FAILURE. Double mismatch: spec writes a bare ARRAY; driver expects dict with `selection_records` (line 465). Driver writes its own manifest.json only at line 349, AFTER the gate (line 320). HARNESS_ACCOUNTING_FAILURE guaranteed on every real run. |
| JD-APP-003 | judgment-day | `accounting.py:287-309`, `driver.py:321-331`, `test_rainfall_e2e_harness.py:1717-1722` | CRITICAL | fixed | real | `classify_run_failure` NEVER returns PASSED: all-True flags return PRODUCT_ASSERTION_FAILURE (accounting.py:309). `run_driver` hardcodes `pre_click_ok, click_occurred = True, True` and passes `collection_ok=True, result_ok=result.ok` → fully green run classifies PRODUCT_ASSERTION_FAILURE → `if cls is not FailureClass.PASSED:` always fires → complete-pass/handoff branch (driver.py:331-350) is unreachable → exit 1 on every run. Unit test pins all-True → PRODUCT_ASSERTION_FAILURE. |
| JD-APP-004 | judgment-day | `driver.py:165-166`, `fixtures/rainfall-multi-parcel.fixture.json` (parcels top-level `nomenclature`/`displayIdentity`, no `identity` sub-object), `test_rainfall_e2e_harness.py` `_fixture()` | CRITICAL | fixed | real | `_parcel_contracts` reads `parcel["identity"]["nomenclature"]` / `parcel["identity"]["displayIdentity"]` but shipped fixture AND unit-test `_fixture()` have top-level keys, NO `identity` sub-object → `KeyError: 'identity'` on every real run → generic except → BROWSER_INTEGRITY_FAILURE. `_parcel_contracts` is never unit-tested (only called inside `run_driver`, which has no end-to-end tests). |
| JD-APP-005 | judgment-day | `.github/workflows/rainfall-multi-parcel-e2e.yml:72-84`, `driver.py:526-546` | CRITICAL | fixed | real | Workflow cleanup step is a no-op. Cleanup step runs `cleanup --run-id gha` WITHOUT `RMEH_RUN_ID_PREFIX: gha` env (only run step line 75 sets it) → compose resolves `rmeh-probedefault` → `down` targets wrong project; real resources are `rmeh-gha-*`. `run_cleanup` builds synthetic identity (run_id "gha", marker_nonce "", database_name "rmeh_gha") + fresh empty lease → per-resource reconcile no-op → relies solely on `docker compose down -v` against the wrong project. RMEH-010-D cancellation-safety violated. |
| JD-APP-006 | judgment-day | `driver.py:372-385`, `driver.py:449-452` | WARNING | info | real | Failure-classification mislabels: BootstrapSafetyFailure AND BootstrapPrerequisiteFailure both → BOOTSTRAP_PREREQUISITE_FAILURE (BOOTSTRAP_SAFETY_FAILURE unreachable from driver); default → BROWSER_INTEGRITY_FAILURE for ANY exception incl. `_wait_for_liveness` RuntimeError (RMEH-002-D reachability) and compose-up failure; genuine product assertion failures → `_run_playwright` raises HarnessAccountingFailure on non-zero exit → HARNESS_ACCOUNTING_FAILURE, never PRODUCT_ASSERTION_FAILURE (RMEH-009/011 remediation boundary broken). |
| JD-APP-007 | judgment-day | `driver.py:491-518`, `driver.py:347`, `safety.py:397-404` | WARNING | info | real | Lease never records created resources: no `record_created` call in driver.py → `_teardown_lease` per-resource immutable-ID reconciliation iterates empty list; teardown relies solely on `docker compose down -v`; RMEH-012-B/C not implemented; `cleanup_result=""` hardcoded; RMEH-012-C (cleanup failure → red) unimplemented — exceptions swallowed (try/except pass), residuals never affect exit code. |
| JD-APP-008 | judgment-day | `driver.py:509-518` | WARNING | info | real | Residual detection inverted: `exists = _resource_exists(...)` computed BEFORE removal, then `if exists: lease.residual_resources.append(...)` → every successfully-removed resource marked residual. Dead code in real runs (created_resources empty), but wrong. |
| JD-APP-009 | judgment-day | `bootstrap.py:427-434` | WARNING | info | real | `_rebuild_once` runs `docker compose down -v`/`up -d` WITHOUT `env=stack_env()` → RMEH_RUN_ID_PREFIX unset → rebuild targets `rmeh-probedefault` project while the actual stack is `rmeh-gha` (workflow) — rebuild repairs nothing / wrong project; exit codes unchecked. |

### Round outcome (apply phase)

- BLOCKER: **2** (JD-APP-001, JD-APP-002) — both independently make the harness unable to complete a run.
- CRITICAL: **3** (JD-APP-003, JD-APP-004, JD-APP-005).
- WARNING (info): **4** (JD-APP-006..009).
- Verified-correct (no finding): workflow optionality pin (`test_ci_workflow_contracts.py:1816` — workflow_dispatch-only, unreferenced by required gates); collection gate exactly 11 / forbidOnly / one worker / retries 0; result gate 11/0/0/0; `ROLLBACK_ARTIFACTS` contains no production/migration files; helper never writes manifest.json to disk.

**Initial judgment: REJECTED ❌ — the primary execution paths cannot pass as shipped.** 2 BLOCKER + 3 CRITICAL,
each code-evidence-backed; the runner unit tests never exercise `run_driver` end-to-end, so all five are masked.

---

## Apply phase — Judgment Day, Judge A (execution half, W4–W11, base d98585af..HEAD db400e06)

Judge A (independent, blind, adversarial) reviewed the same apply diff — runner (`scripts/rainfall_e2e_harness/*`),
compose stack, workflow, browser helper/spec, unit/integration tests. Static review with exact-line evidence;
no harness execution. Sweep budget: 2 sweeps, both used (exhaustive first pass + targeted verification of
identity/compose env flow, manifest evidence path, Playwright JSON reporter attachment handling v1.60.0,
workflow cleanup env, `_rebuild_once` env, `frontend_ok` enforcement).

### Findings (Judge A)

| id | lens | location | severity | status | assessment | evidence |
|---|---|---|---|---|---|---|
| JD-APP-A1 | judgment-day | `safety.py:189-196,360`, `driver.py:259,274,123,133-136`, `rainfall-e2e.compose.yml:26,35,38,50,56,68,100`, `driver.py:279` | BLOCKER | fixed | real | Identity/compose naming disconnect (converges with JD-APP-001). `RunIdentity.plan()`: `run_id = secrets.token_hex(16)`, `database_name = f"rmeh_{run_id[:10]}"`; `ResourceLease.plan()`: `project_name = f"rmeh-{identity.run_id[:10]}"`; driver writes init `rmeh-init-{identity.run_id[:10]}.sql` (driver.py:274). Compose derives ALL names from `RMEH_RUN_ID_PREFIX:-probedefault` (project `rmeh-<prefix>`, `POSTGRES_DB rmeh_<prefix>`, bind `./rmeh-init-<prefix>.sql:ro`). `stack_env()` (driver.py:133-136) sets `RMEH_RUN_ID_PREFIX = run_id_prefix` = env value or `""` (driver.py:123). Local: bind source `rmeh-init-probedefault.sql` missing (driver wrote random hex name) → compose fails or mounts nothing; marker gate queries `rmeh_<random>` vs DB `rmeh_probedefault` → BootstrapSafetyFailure. Workflow `RMEH_RUN_ID_PREFIX: gha`: compose expects `rmeh-init-gha.sql`/`rmeh_gha`; driver writes random-hex init and queries `rmeh_<random>` → same failure. Tests pass ONLY because integration test/probe construct `RunIdentity(run_id=prefix, database_name=f"rmeh_{prefix}")` aligned to env, bypassing the driver. Both documented execution paths cannot work. |
| JD-APP-A2 | judgment-day | `rainfall-v2-detail.spec.ts:1452-1454`, `driver.py:455-465,318-320,349`, `playwright.rainfall-harness.config.ts` (JSON reporter outputFile) | BLOCKER | fixed | real | Manifest gate can never pass (converges with JD-APP-002). Spec only `testInfo.attach('manifest.json', { body })` → attachment file lands in Playwright `test-results/` output dir and body is embedded base64 inside `playwright-results.json` (verified JSONReporter v1.60.0 source: `attachments: result.attachments.map(a => ({name, contentType, path, body: a.body?.toString('base64')}))`). NOTHING writes `evidence_dir/manifest.json`. `_read_manifest_records` (driver.py:455-465) reads `evidence_dir/manifest.json` → missing → `[]` → `assert_manifest_contract([])` raises (expected 8) → HARNESS_ACCOUNTING_FAILURE on every real run. Bonus mismatch: spec attaches a bare ARRAY; driver expects dict with `selection_records` key (driver.py:465). Driver's own manifest write (driver.py:349) happens AFTER the gate (driver.py:320) — unreachable. |
| JD-APP-A3 | judgment-day | `accounting.py:287-309`, `driver.py:321-331` | BLOCKER | fixed | real | `classify_run_failure` NEVER returns PASSED: all-True flags → `PRODUCT_ASSERTION_FAILURE` (accounting.py:309, final return). Driver hardcodes `pre_click_ok, click_occurred = True, True` (driver.py:321) and passes `collection_ok=True, result_ok=result.ok` → fully green run classifies PRODUCT_ASSERTION_FAILURE → `if cls is not FailureClass.PASSED:` always true → complete-pass/handoff branch (driver.py:331-350) unreachable → every run exits failure. Converges with JD-APP-003. |
| JD-APP-A4 | judgment-day | `driver.py:165-166`, `fixtures/rainfall-multi-parcel.fixture.json` (top-level `nomenclature`/`displayIdentity`, lines 115-116/177-178/231-232; NO `identity` sub-object) | CRITICAL | fixed | real | `_parcel_contracts` reads `parcel["identity"]["nomenclature"]` / `parcel["identity"]["displayIdentity"]` → `KeyError: 'identity'` on every fixture. `build_seed_sql` reads top-level `p['nomenclature']` (correct). Preflight call driver.py:300 → generic except → BROWSER_INTEGRITY_FAILURE. Masked by A1 in real flow; fires as soon as identity issue is fixed. Converges with JD-APP-004. |
| JD-APP-A5 | judgment-day | `.github/workflows/rainfall-multi-parcel-e2e.yml:72-84` (cleanup step no env), `driver.py:123,133-136,503` | CRITICAL | fixed | real | Workflow cleanup step runs WITHOUT `RMEH_RUN_ID_PREFIX: gha` (only run step line 75 sets it) → compose project `rmeh-probedefault` → `down -v` targets wrong project; `rmeh-gha-*` stack left running. `run_cleanup` builds synthetic identity run_id="gha"/db `rmeh_gha` but teardown is compose-down driven by env, not identity. RMEH-010-D cancellation-safety violated. Converges with JD-APP-005. |
| JD-APP-A6 | judgment-day | `bootstrap.py:854-859` (`frontend_ok` computed, never raised), `driver.py:301` (ServiceReport discarded) | CRITICAL | fixed | real | `validate_services` computes `frontend_ok = _http_code(mapa.stdout) == 200` but NEVER raises when false; driver discards the ServiceReport entirely. Browser steps then run against a dead/500 frontend → misclassified HARNESS_ACCOUNTING_FAILURE (via `_run_playwright` non-zero exit). RMEH-002-D (service validation before browser) violated. `backend_live` also unenforced but harmless (ficha POST probe raises first). |
| JD-APP-A7 | judgment-day | `driver.py:372-385`, `driver.py:449-452`, `accounting.py:287-309` | WARNING | info | real | Classification reachability: `_classify_exception` maps (BootstrapSafetyFailure, BootstrapPrerequisiteFailure) → BOOTSTRAP_PREREQUISITE_FAILURE → BOOTSTRAP_SAFETY_FAILURE unreachable from driver; default → BROWSER_INTEGRITY_FAILURE for ANY exception (incl. compose-up failure, `_wait_for_liveness` RuntimeError); `_run_playwright` raises HarnessAccountingFailure on ANY non-zero playwright exit → genuine PRODUCT_ASSERTION_FAILURE never emitted (JDA-001 remediation trigger dead). RMEH-009-A/D taxonomy unreachable. |
| JD-APP-A8 | judgment-day | `driver.py:491-518`, `driver.py:347`, `safety.py:397-404` | WARNING | info | real | Cleanup accounting not implemented: no `record_created` call anywhere in driver → `created_resources` empty in real path → residual reconciliation dead; `residual_resources` never checked (no `assert_no_residual_resources()` call); `_teardown_lease` best-effort `try/except pass`; `cleanup_result=""` hardcoded in manifest; exit 0 decided before teardown → failed teardown still PASSED+exit 0. RMEH-012-C violated. Converges with JD-APP-007. |
| JD-APP-A9 | judgment-day | `bootstrap.py:426-434` (`_rebuild_once` no `env=`), `driver.py:279` (stack_env pattern) | WARNING | info | real | `_rebuild_once` runs `compose down -v`/`up -d` WITHOUT `env=stack_env()` → RMEH_RUN_ID_PREFIX unset → targets `rmeh-probedefault` project while actual stack is `rmeh-gha` (workflow) — rebuild repairs nothing; exit codes unchecked. Converges with JD-APP-009. |
| JD-APP-A10 | judgment-day | `bootstrap.py:854` (`camera_zoom` default), `fixtures/rainfall-multi-parcel.fixture.json` cameras zoom 13 (mobile+desktop) | WARNING | info | theoretical | Tile-probe zoom mismatch: `validate_services` probes A/B/C tiles at default `camera_zoom=14` (camera params from fixture only for `/mapa` query); fixture cameras are zoom 13. Legacy probe uses declared zoom 16 (correct). Probe validates different-zoom tiles than the browser journey will request — a zoom-sensitive tile failure could pass probe and fail in browser. |
| JD-APP-A11 | judgment-day | `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts` `waitForTargetAnalysis` (≤15s poll, strict newer-sequence), `helpers/rainfallMultiParcelHarness.ts:969-971` (assertTargetReady strict `>`), `apply-progress.md:565-569` | WARNING | info | theoretical | A2 (repeat-A) freshness gate depends on unverified real-stack behavior: fixture router serves repeat A from the 60s React Query cache with NO new request → `analysisSequence` never increments → journey test fails closed on fixture router BY DESIGN (documented). Real stack passes ONLY IF A1's queued analysis (202 + 5s poll) leaves A2's cache stale → refetch. If the owned backend completes analyses <60s (or cache remains fresh), the A2 leg fails and W9's 11/0/0/0 gate is unreachable. Documented accepted risk; runtime-pending at W9 — flagged as the single largest unknown that gates the whole green path. |

### Round outcome (apply phase — Judge A)

- BLOCKER: **3** (A1, A2, A3) — A3 (classify never PASSED) is independent of the identity/manifest blockers and alone guarantees every run fails.
- CRITICAL: **3** (A4, A5, A6).
- WARNING (info): **5** (A7..A11).
- Verified-correct (no finding): workflow optionality pin (`test_ci_workflow_contracts.py:1816-1862` — workflow_dispatch-only, no secrets, serialized, unreferenced by required gates); collection gate exactly 11 / forbidOnly / one worker / retries 0; Playwright config env wiring (`process.env.RMEH_PLAYWRIGHT_JSON` confirmed at config line 34); `__main__.py` → driver.main; single harness package.json command; `.gitignore` covers `rmeh-init-*.sql` + `.artifacts/`.

**Judge A initial judgment: REJECTED ❌ — the harness cannot complete a green run through either documented path.** 3 BLOCKER + 3 CRITICAL, all code-evidence-backed; runner unit tests never exercise `run_driver` end-to-end, so all are masked. Blind convergence with Judge B on A1/A2/A3/A4/A5/A7/A8/A9 (8 of 11 findings) — cross-judge agreement strengthens confidence on the BLOCKER set.

---

## Fix round — surgical apply (confirmed issues only, TDD RED→GREEN)

Fix agent applied the six CONFIRMED issues (JD-APP-001/A1, JD-APP-002/A2, JD-APP-003/A3,
JD-APP-004/A4, JD-APP-005/A5, JD-APP-A6). Each fix landed RED-first (a failing test pinned the
bug), then GREEN (implementation), then full-suite verification. Row statuses above flipped
`open → fixed` per fix. WARNING (info) findings JD-APP-006..009 / A7..A11 were NOT modified —
reported back to the orchestrator instead.

| id | fix summary | verification |
|---|---|---|
| JD-APP-001/A1 | `DriverConfig.stack_env()` now takes the prefix EXPLICITLY, derived from `identity.run_id[:10]` (compose up, teardown, martin restart); ambient `RMEH_RUN_ID_PREFIX` never leaks; compose dropped all `:-probedefault` fallbacks; `run_driver` persists `ownership.json` BEFORE provisioning; `--evidence-dir` accepted after the subcommand (the workflow's command order previously exit-2'd). | 4 new unit tests (stack_env derives prefix, teardown pins prefix env, ownership persisted, cleanup uses recorded identity) + compose config suite + workflow contract test green. |
| JD-APP-002/A2 | Spec now writes the manifest FILE `dirname(RMEH_PLAYWRIGHT_JSON)/manifest.json` as `{ selection_records: [...] }` via new pure helper `writeHarnessManifest` (unit-tested); attachment also wrapped in the dict shape. Driver gate reads the file it was always reading. | 2 new vitest tests; 69 vitest + tsc clean. |
| JD-APP-003/A3 | `classify_run_failure` all-green path now returns `PASSED` (the classifier receives no input that can signal a product-behavior failure); the complete-pass/handoff branch is reachable. | Both tests that pinned all-True → PRODUCT_ASSERTION_FAILURE updated to pin PASSED. |
| JD-APP-004/A4 | `_parcel_contracts` reads top-level `nomenclature`/`displayIdentity` (the shipped fixture + `_fixture()` shape). | 2 new tests incl. a guard against the REAL fixture file on disk. |
| JD-APP-005/A5 | `run_cleanup` prefers the RECORDED ownership identity (exact project the run created); workflow cleanup step now passes `--evidence-dir` + a `RMEH_RUN_ID_PREFIX` fallback env. | New unit test pins cleanup's compose-down prefix = recorded `run_id[:10]`. |
| JD-APP-A6 | `validate_services` RAISES `BootstrapPrerequisiteFailure` when the frontend `/mapa` probe is not 200 (fail-closed before the browser); martin restart now runs with the run-owned prefix env; `run_driver` refuses to launch unless the service report is green. | 2 new tests: frontend-500 aborts; restart env carries `run_id[:10]`. |

Full suites: `scripts/tests/test_rainfall_e2e_harness.py` + `test_rainfall_e2e_config.py` = **131 passed**;
`consorcio-web` vitest harness unit = **69 passed**; `tsc -p tsconfig.tests.json --noEmit` clean;
gee-backend workflow optionality contract green; integration tests skipped (need `RMEH_INTEGRATION=1`).

**Fix-round status: all six confirmed findings closed (fixed) with RED→GREEN proof.**
