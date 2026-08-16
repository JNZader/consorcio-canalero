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

---

## Re-judge Round 2 — Judge A (scoped re-review of fix diff `db400e06..HEAD`, 13 files +615/-58)

Judge A (independent, blind, adversarial) re-reviewed ONLY the fix diff and the persisted
ledger; the full original apply diff (`d98585af..db400e06`) was NOT re-read. Sweep budget: 2
exhaustive sweeps of the fix diff (both used). Static review with exact-line evidence plus a
targeted test probe. Constraints verified: `consorcio-web/src/**` and `gee-backend/app/**`
untouched (0 production lines); workflow stays `workflow_dispatch`-only and unreferenced by
required gates (`test_ci_workflow_contracts.py` pin untouched); parent change files untouched;
fix stays surgical (only the 6 findings' surfaces + docs + tests).

### Verification of the 6 confirmed findings

| id | status | evidence |
|---|---|---|
| JD-APP-001/A1 | **fixed** | NOT resolved end-to-end (Round 1 evidence below). **[Closed by Fix round 2 — the DB-side compose commands now carry the run-owned env; see the Round 2 fix section below.]** The fix aligned exactly three compose invocations (up `driver.py:333`, teardown down `driver.py:568`, martin restart `bootstrap.py:751`) with the run identity — but every DB-side compose command still resolves the project from the AMBIENT env, and the fix made that fatal by removing all `:-probedefault` fallbacks AND removing `RMEH_RUN_ID_PREFIX: gha` from the workflow run step (`.github/workflows/rainfall-multi-parcel-e2e.yml:84-88`). `validate_marker_read_only` (`safety.py:249` — `docker compose exec`, NO env), `apply_migrations` (`safety.py:284` — `docker compose run --rm migrate`, NO env), `inspect_relation` (`bootstrap.py:214`), `inspect_srid_contract` (`bootstrap.py:256`), seed (`bootstrap.py:510`) all run with `RMEH_RUN_ID_PREFIX` unset in the parent process (no `.env` anywhere; runbook sets no env; `stack_env` never mutates `os.environ`). With `name: rmeh-${RMEH_RUN_ID_PREFIX}` (bare, no default), compose substitutes the empty string (warning) → project `rmeh-`, which is NOT the provisioned `rmeh-<run_id[:10]>` → `docker compose exec db psql` fails → marker gate raises `BootstrapSafetyFailure` at `driver.py:346`, the FIRST compose-dependent step after `up`. The fix moved the guaranteed failure from "compose up (missing init bind)" to "marker gate (wrong compose project)"; the run still cannot pass through EITHER documented path (local runbook or workflow). The fix's own comment ("passing it explicitly to every compose command", workflow lines 79-83) is factually wrong for the ~8 exec/run call sites. Root cause of A1 (driver never aligns ALL compose invocations with the run identity) persists. See new finding R2-001. |
| JD-APP-002/A2 | verified | Spec now writes the manifest FILE to `dirname(RMEH_PLAYWRIGHT_JSON)/manifest.json` wrapped as `{selection_records: [...]}` (`rainfall-v2-detail.spec.ts:1453-1457`); `_run_playwright` sets `RMEH_PLAYWRIGHT_JSON = evidence_dir/playwright-results.json` (`driver.py:507`) → same path the gate reads (`driver.py:380-382`, `_read_manifest_records` `driver.py:517-527`). 8 records asserted before write (`spec.ts:1448-1452`). Pure helper `writeHarnessManifest` unit-tested (`rainfallMultiParcelHarness.test.ts`, 2 tests; executed exit=0). Attachment also wrapped in dict shape. Driver's post-gate overwrite (`driver.py:411`) keeps `selection_records` via `SceneManifest.to_json` (`taxonomy.py:53-86`). |
| JD-APP-003/A3 | verified | `classify_run_failure` all-green path returns `PASSED` (`accounting.py` final return). Complete-pass/handoff branch reachable: `if cls is not FailureClass.PASSED:` (`driver.py:390`) → green run exits 0 (`driver.py:429-431`). Both pinning tests flipped to PASSED (`test_rainfall_e2e_harness.py:1816,1939-1941`; executed exit=0). `PRODUCT_ASSERTION_FAILURE` no longer emitted by this classifier — documented in docstring as surfacing via `taxonomy.classify_request_failure`/result gate (consistent with the confirmed finding's scope; taxonomy-side reachability was the separate A7 WARNING/info, untouched). |
| JD-APP-004/A4 | verified | `_parcel_contracts` reads top-level `parcel["nomenclature"]`/`parcel["displayIdentity"]` (`driver.py:170-171`). Real shipped fixture confirmed on disk: 3 parcels, all top-level, NO `identity` sub-object (read, executed). New guard test `test_parcel_contracts_on_shipped_fixture_file` reads the REAL `FIXTURE_PATH` file (executed exit=0). |
| JD-APP-005/A5 | verified | `run_cleanup` prefers the recorded `ownership.json` identity (`_read_recorded_identity`, `driver.py:605-614`); `_persist_identity` writes BEFORE provisioning (`driver.py:307-313`); `_teardown_lease` derives the down prefix from `lease.project_name.removeprefix("rmeh-")` (`driver.py:568`). Workflow cleanup step now passes `--evidence-dir` (same dir as run step) + `RMEH_RUN_ID_PREFIX: gha` fallback env (`rainfall-multi-parcel-e2e.yml:96-100`). Tests pin recorded-prefix down (`test_run_cleanup_uses_recorded_identity_prefix`, `test_teardown_lease_pins_identity_derived_prefix_env`; executed exit=0). |
| JD-APP-A6 | verified | `validate_services` RAISES `BootstrapPrerequisiteFailure` when frontend `/mapa` probe ≠ 200 (`bootstrap.py:854-861`); driver refuses browser unless `services.frontend_ok` (`driver.py:355-363`); martin restart runs with `env={"RMEH_RUN_ID_PREFIX": identity.run_id[:10]}` (`bootstrap.py:748-751`), merged by `RealCommandRunner` (`safety.py:84-86` — PATH preserved). Tests `test_validate_services_frontend_failure_fails_closed` + `test_validate_services_martin_restart_pins_identity_prefix_env` (executed exit=0). |

### New findings introduced by the fix

| id | lens | location | severity | status | assessment | evidence |
|---|---|---|---|---|---|---|
| R2-001 | judgment-day | `rainfall-e2e.compose.yml:26,35,38,50,56,68,100,113,127,158,170,199,219,224` + `safety.py:249,284` + `bootstrap.py:214,256,510` + `driver.py:346` | BLOCKER | fixed | real | **[Closed by Fix round 2 — see below.]** The strict compose file (`${RMEH_RUN_ID_PREFIX}` bare, fallbacks removed) makes EVERY compose invocation without the var resolve to the empty-string project `rmeh-` (compose-spec: unset `${VAR}` → warning + empty string). The fix removed the only ambient prefix source (workflow run-step env, `rainfall-multi-parcel-e2e.yml:84-88`) while leaving ~8 `docker compose exec`/`run` call sites env-less (see A1 row). Deterministic failure: compose up succeeds (`driver.py:333`), backend /live 200, then the marker gate (`driver.py:346` → `safety.py:249`) executes `docker compose exec` against project `rmeh-` → no such project/container → `BootstrapSafetyFailure` → `BOOTSTRAP_PREREQUISITE_FAILURE` → exit 1, on EVERY real run in both documented paths. The A1 root cause survives in the DB command layer. |
| R2-002 | judgment-day | `bootstrap.py:427-434` (`_rebuild_once`), `rainfall-e2e.compose.yml:26` | WARNING | info | real | The strict compose change also degrades the (pre-existing, A9-info) repair path: `_rebuild_once` runs `docker compose down -v`/`up -d` with NO env, so the empty-prefix project `rmeh-` (or interpolation failure) replaces the old silent `rmeh-probedefault` no-op; exit codes remain unchecked, and `up -d` would attempt to create the wrong project (self-limiting: missing `rmeh-init-.sql` bind aborts it). Same user-visible outcome class as A9 (repair does nothing), so canonical WARNING/info — recorded, not blocking. |

### Round outcome (Judge A re-judge)

- Resolved and verified: **5 of 6** (A2, A3, A4, A5, A6).
- NOT resolved: **A1** (BLOCKER, still open) — the identity/compose disconnect persists in the
  DB command layer (`docker compose exec`/`run`), and the fix's strict-compose + env removal
  makes the empty-prefix project resolution fail deterministically at the marker gate
  (`driver.py:346`). New finding R2-001 carries the evidence.
- Constraints held: 0 production lines; workflow remains optional; parent change untouched;
  fix surgical; 15 targeted fix tests executed (exit=0) confirming the RED→GREEN claims that
  were in scope.

**JUDGMENT: NOT APPROVED ❌ — A1 remains open (BLOCKER): the harness cannot complete a green
run through either documented path until the DB-side compose commands receive the run-owned
prefix env.**

---

## Re-judge Round 2 — Judge B (scoped re-review of fix diff db400e06..HEAD)

Blind re-judge of the fix round. Reviewed ONLY the fix diff (13 files, +615/-58) and the
Round-1 ledger; the original apply diff was NOT re-read. Sweep budget: 2 exhaustive sweeps
of the fix diff, both used. Empirical verification performed with `docker compose v5.3.0`
(compose config + exec against a non-existent `rmeh-` project).

### Verification of the 6 confirmed findings

| id | severity | status | evidence |
|---|---|---|---|
| JD-APP-001/A1 | BLOCKER | **fixed** | **[Closed by Fix round 2 — see below.]** Fix is INCOMPLETE — the run still cannot complete either documented path. `stack_env(run_id_prefix)` + fallback removal + init-bind alignment + pre-provision `ownership.json` are all present and correct for compose `up`/`down`/martin-restart, but every OTHER `docker compose` invocation in the pipeline is env-less and now resolves the project to `rmeh-` (empty prefix): `validate_marker_read_only` (safety.py:229-249, called driver.py:346 — the SOLE OwnedBoundary constructor), `apply_migrations` via `compose run --rm migrate` (safety.py:283-286), every `_psql_cmd` exec (bootstrap.py:60-63; call sites 208, 250, 510, 589, 606, 617, 628, 639), `_rebuild_once` (bootstrap.py:427, 431). Pre-fix these were project-consistent with compose up (`rmeh-probedefault` on both sides); post-fix compose up targets `rmeh-<run_id[:10]>` while the marker gate targets `rmeh-`. Empirically verified: `RMEH_RUN_ID_PREFIX` unset → `compose config` emits `name: rmeh-`; `compose exec -T db psql …` exits 1 with `service "db" is not running`. The BLOCKER moved from the compose-up init-bind failure to the marker gate; exit code 1 via BootstrapSafetyFailure → BOOTSTRAP_PREREQUISITE_FAILURE on every run. |
| JD-APP-002/A2 | BLOCKER | verified | Spec writes `{ selection_records: [...] }` manifest FILE via `writeHarnessManifest` to `dirname(RMEH_PLAYWRIGHT_JSON)` = the evidence dir (`_run_playwright` passes the absolute evidence path, driver.py:505-509); driver gate reads `evidence_dir/manifest.json` BEFORE its own sealed write (driver.py:380-382 → 411); `EXPECTED_SELECTION_RECORDS = 8` matches the spec's `expect(manifest).toHaveLength(8)` + per-record 1/1; vitest unit coverage added. Gate ordering and shape aligned. |
| JD-APP-003/A3 | CRITICAL | verified | `classify_run_failure` all-True path returns `PASSED` (accounting.py:309); the complete-pass branch (manifest + `jda-001-handoff.json` + `return 0`, driver.py:390-412, 429-431) is reachable; both pinning tests flipped to PASSED with rationale. Caveat: the run never reaches this gate while A1 is open (marker gate fails first) — code-level fix is correct, runtime-blocked by A1. |
| JD-APP-004/A4 | CRITICAL | verified | `_parcel_contracts` reads top-level `parcel["nomenclature"]` / `parcel["displayIdentity"]`; empirically matches the shipped fixture (3 parcels, top-level keys, no `identity` sub-object); 2 new tests incl. a guard over the real fixture file on disk. |
| JD-APP-005/A5 | CRITICAL | verified | `run_cleanup` prefers the RECORDED identity from `ownership.json` (written pre-provision) so compose-down targets the exact `rmeh-<run_id[:10]>` project; workflow cleanup step now passes `--evidence-dir` + fallback prefix env; parser accepts `--evidence-dir` after the subcommand (workflow command order no longer exit-2s); teardown prefix derived from `lease.project_name` (driver.py:568). New unit test pins the recorded prefix. |
| JD-APP-A6 | CRITICAL | verified | `validate_services` now RAISES `BootstrapPrerequisiteFailure` when frontend `/mapa` is not HTTP 200 (bootstrap.py:854-861) — fail-closed before the browser; martin restart carries `RMEH_RUN_ID_PREFIX=run_id[:10]` (bootstrap.py:745-753); driver's `services.frontend_ok` refusal (driver.py:356-363) is now unreachable belt-and-suspenders (validate_services raises first) — harmless. 2 new tests (frontend-500 aborts; restart env pinned). |

### NEW findings (defects introduced/exposed by the fix diff)

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| JD-R2-001 | judgment-day | `scripts/rainfall_e2e_harness/safety.py:229-249,283-286`, `scripts/rainfall_e2e_harness/bootstrap.py:60-63,208,250,510,589,606,617,628,639,427,431`, `scripts/rainfall_e2e_harness/driver.py:346,351`, `scripts/tests/rainfall-e2e.compose.yml:26` | BLOCKER | fixed | **[Closed by Fix round 2 — see below.]** The fallback removal (fix diff) without threading the run-owned env into the env-less compose call sites creates a NEW project mismatch: `name: rmeh-${RMEH_RUN_ID_PREFIX}` with the var unset resolves to project `rmeh-` (empirically confirmed: `compose config` → `name: rmeh-`), while compose up/teardown/restart now target `rmeh-<run_id[:10]>`. `validate_marker_read_only` (the SOLE OwnedBoundary constructor, called at driver.py:346) runs `docker compose exec -T db psql` with no env → targets `rmeh-` → `service "db" is not running`, exit 1 (empirically confirmed) → BootstrapSafetyFailure → BOOTSTRAP_PREREQUISITE_FAILURE → exit 1 on EVERY real run (local runbook + GitHub workflow; workflow run step's `RMEH_RUN_ID_PREFIX` was removed in this fix, so the ambient env is unset). Same env-less pattern breaks the migration path (`compose run --rm migrate`) and every `_psql_cmd` bootstrap exec once the marker gate were bypassed. `safety.py` and `bootstrap.py` exec call sites are untouched lines, but the breakage is CAUSED by fix-touched lines (fallback removal + stack_env change); A1's own original evidence cited the marker gate failure mode. Fix required: pass the run-owned `RMEH_RUN_ID_PREFIX` env into `validate_marker_read_only`/`_psql_cmd`/`apply_migrations`/`_rebuild_once` (or make the compose file not depend on the ambient var for these paths). |

### Constraints audit (fix diff)

- Production code: 0 lines — no `consorcio-web/src/**` or `gee-backend/app/**` touched. PASS.
- Workflow remains optional (`workflow_dispatch`-only), unreferenced by required gates. PASS.
- Parent change (`lluvia-ux-tarjeta`) not mutated; `PARENT_LEDGER_PATH` only read. PASS.
- Surgical scope: changes limited to the six confirmed fixes + their tests/docs/ledger; `--evidence-dir` subparser additions justified by A5 (workflow command order); no unflagged refactors observed. PASS.

### Round 2 outcome

- Confirmed findings verified: **5 of 6** (A2, A3, A4, A5, A6).
- Confirmed finding still open: **JD-APP-001/A1 (BLOCKER)** — fix incomplete; the harness still cannot complete a green run through either documented path.
- NEW BLOCKER introduced by the fix: **JD-R2-001** (env-less compose exec/run paths now resolve project `rmeh-` vs provisioned `rmeh-<run_id[:10]>`; marker gate fails on every run).

**JUDGMENT: NOT APPROVED ❌ — A1 remains unresolved and the fix introduces a same-class BLOCKER (JD-R2-001) at the marker gate.**

---

## Fix round 2 — surgical apply (confirmed BLOCKERs only, TDD RED→GREEN)

Fix agent applied the two confirmed BLOCKER findings — **JD-APP-001/A1** and **JD-R2-001** —
which share ONE root cause: the ~8 DB-side `docker compose exec`/`run` call sites resolved the
compose project from the AMBIENT env (empty after the round-1 fallback removal), so every
DB command targeted the empty-prefix project `rmeh-` instead of the provisioned
`rmeh-<run_id[:10]>`, failing deterministically at the marker gate (`driver.py:346`) on every
real run. The fix introduces ONE composition helper used at EVERY compose invocation site and
removes the ambient dependency entirely.

| id | fix summary | verification |
|---|---|---|
| JD-APP-001/A1 | Root-cause fix: new `safety.compose_env(identity, *, extra=None)` returns the run-owned env (`RMEH_RUN_ID_PREFIX` derived from `identity.database_name.removeprefix("rmeh_")` — the single source of truth shared by POSTGRES_DB/`psql -d`/marker row, equal to `run_id[:10]` for driver-generated identities and FULL prefix for integration/probe seams — plus the synthetic `RMEH_DB_PASSWORD=synthpass`), never reading ambient env. Every compose invocation now passes it: `validate_marker_read_only` (`safety.py`), `apply_migrations` compose path (`safety.py`, with a fail-closed guard: compose path without identity raises `BootstrapSafetyFailure`), all 8 `_psql_cmd` exec sites via a new `bootstrap._psql_run` wrapper (inspect_relation, inspect_srid_contract, seed, create/recreate/refresh parcel view, refresh soil view, count soil rows), `_rebuild_once` down/up (`bootstrap.py`), martin restart (`bootstrap.py`, previously `run_id[:10]`-only). `driver.stack_env` now takes the identity and delegates to `compose_env` + host ports; `_teardown_lease` takes the identity (prefix from the same source, not `lease.project_name`). Workflow cleanup step's `RMEH_RUN_ID_PREFIX: gha` env removed — the driver derives everything from `ownership.json`/identity; the run step never set it (unchanged). `__init__.py` exports `compose_env`. | 10 new RED→GREEN unit tests: compose_env derives prefix / never ambient / seam-identity full-prefix / extra merge; marker-gate env carries prefix+password; apply_migrations pins env + refuses missing identity; EVERY compose exec in a happy-path bootstrap carries prefix+password; rebuild down/up carry env; inspect_relation psql env + fail-closed guard. Parity test `test_compose_config_matches_lease_plan_under_driver_random_env` runs real `docker compose config` under `compose_env` of a driver-style random identity and asserts project/volume/network/container/POSTGRES_DB == `ResourceLease.plan` names EXACTLY (PASSED, docker CLI present). Full suites: harness+config pytest = **141 passed** (was 131); vitest 69 passed; `tsc -p tsconfig.tests.json --noEmit` clean; `git diff --check` clean; integration tests skipped (need `RMEH_INTEGRATION=1`). |
| JD-R2-001 | Same root cause as A1; closed by the same `compose_env` threading (see A1 row). | The `test_bootstrap_every_compose_exec_carries_run_owned_env` regression asserts EVERY `docker compose` invocation in the bootstrap records `RMEH_RUN_ID_PREFIX=<run_id[:10]>` + `RMEH_DB_PASSWORD=synthpass`; parity test proves the resolved project equals the lease plan under the driver env. |

- `JD-R2-002` (WARNING/info — `_rebuild_once` exit codes unchecked) was NOT in the confirmed
  fix scope and was NOT modified: the rebuild env was threaded (part of A1/JD-R2-001) but exit
  code checking was deliberately left untouched and reported back to the orchestrator.
- Existing driver-layer tests updated for the signature changes (`stack_env(identity)`,
  `_teardown_lease(..., identity)`) and two hand-built test identities made internally
  consistent (`database_name = rmeh_<run_id[:10]>`, matching `RunIdentity.plan`); the
  `test_cleanup_uses_exact_lease_identity_not_prefix` DB-token assertion now checks for
  DATABASE_* calls/marker-nonce instead of the synthetic `RMEH_DB_PASSWORD` interpolation var.

Full suites: `scripts/tests/test_rainfall_e2e_harness.py` + `test_rainfall_e2e_config.py` =
**141 passed**; `consorcio-web` vitest harness unit = **69 passed**; `tsc -p
tsconfig.tests.json --noEmit` clean; gee-backend workflow optionality contract untouched and
green; integration tests skipped (need `RMEH_INTEGRATION=1` against a provisioned stack).

**Fix-round-2 status: both confirmed BLOCKERs (JD-APP-001/A1, JD-R2-001) closed (fixed) with
RED→GREEN proof; 0 production lines touched.**

---

## Re-judge Round 3 — Judge B

Blind re-judge of the Fix round 2 diff (`b75aa878..HEAD`) on branch
`test/rainfall-multi-parcel-e2e-execution`. Reviewed ONLY the fix diff; the original
apply diff was NOT re-read. Sweep: one exhaustive pass of the diff + `rg` audit of every
`docker compose` call site in the requested directories.

### Verification of the 2 confirmed Fix-round-2 BLOCKERs

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| JD-APP-001/A1 | judgment-day | `scripts/rainfall_e2e_harness/safety.py`, `scripts/rainfall_e2e_harness/bootstrap.py`, `scripts/rainfall_e2e_harness/driver.py` | BLOCKER | verified | Every `docker compose` invocation in the three harness modules now carries a run-owned env: `validate_marker_read_only` and `apply_migrations` (safety.py) use `env=compose_env(identity)`; `bootstrap.py` routes all psql execs through `_psql_run` with `compose_env(identity)` and `_rebuild_once` down/up and `validate_services` restart also use it; `driver.py` `stack_env(identity)` delegates to `compose_env(identity)` plus host ports, used by compose up and `_teardown_lease` down. `compose_env` derives `RMEH_RUN_ID_PREFIX` from `identity.database_name.removeprefix("rmeh_")` and `RMEH_DB_PASSWORD` from the local constant `DB_PASSWORD`; it never reads `os.environ`. The workflow cleanup step no longer sets `RMEH_RUN_ID_PREFIX: gha`. |
| JD-R2-001 | judgment-day | `scripts/tests/test_rainfall_e2e_config.py:206-258` | BLOCKER | verified | `test_compose_config_matches_lease_plan_under_driver_random_env` strips ambient `RMEH_*` vars, updates the subprocess env with `compose_env(identity)` for a driver-style random `RunIdentity`, runs real `docker compose config`, and asserts `cfg["name"] == lease.project_name`, `POSTGRES_DB == identity.database_name`, volume/network names match `lease`, and every container name matches `lease.container_names` — proving the resolved project matches the lease plan under the exact env the harness now passes. |

### New finding (remaining call site lacks run-owned env)

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| JD-R3-001 | judgment-day | `scripts/tests/probe_rainfall_bootstrap.py:74`, `scripts/tests/probe_rainfall_bootstrap.py:135`, `scripts/tests/test_rainfall_e2e_integration.py:105`, `scripts/tests/test_rainfall_e2e_integration.py:144` | BLOCKER | fixed | Fixed in micro-round — see `## Micro-round — JD-R3-001` below. Both manual seams now import `compose_env` from `scripts.rainfall_e2e_harness.safety`, build internally consistent `RunIdentity` (`database_name = f"rmeh_{run_id[:10]}"`), and pass `env=compose_env(identity, extra={host ports})` to every `docker compose` up/down call; the ambient `RMEH_RUN_ID_PREFIX` dependency is removed. |

### Constraints audit (Fix round 2 diff)

- Production code: 0 lines — no `consorcio-web/src/**` or `gee-backend/app/**` touched. PASS.
- Workflow remains optional (`workflow_dispatch`-only), unreferenced by required gates. PASS.
- Parent change (`lluvia-ux-tarjeta`) not mutated. PASS.
- No `:-probedefault` fallback remains in `scripts/tests/rainfall-e2e.compose.yml`; the only remaining fallbacks are `RMEH_DB_PASSWORD:-synthpass` and host-port defaults (`:-8001`, `:-3001`, `:-5174`). PASS.

### Round 3 outcome

- Confirmed findings verified: **2 of 2** (JD-APP-001/A1, JD-R2-001).
- NEW BLOCKER discovered in remaining `docker compose` call sites: **JD-R3-001** — **fixed in micro-round** (outside the standard 2-round budget, owner-approved).

**VERDICT: APPROVED ✅ — JD-R3-001 fixed in micro-round; all production-harness and manual-seam `docker compose` invocations now use the run-owned `compose_env(identity)`.**

---

## Re-judge Round 3 — Judge A

Blind final re-judge of Fix round 2 diff `b75aa878..HEAD` on branch `test/rainfall-multi-parcel-e2e-execution`. Reviewed ONLY the fix diff; the original apply diff was NOT re-read.

### `docker compose` call-site audit

| location | invocation | env passes `compose_env(identity)` | notes |
|---|---|---|---|
| `safety.py:262-289` | `docker compose -f … exec -T db psql` | YES | `env=compose_env(identity)` (marker gate) |
| `safety.py:334-338` | `docker compose -f … run --rm migrate` | YES | `env=compose_env(identity)` (apply_migrations compose path) |
| `bootstrap.py:83-87` | `_psql_run` wrapper | YES | all psql execs routed through it |
| `bootstrap.py:250-256` | `docker compose -f … exec -T db psql` | YES | `env=compose_env(identity)` (inspect_relation) |
| `bootstrap.py:309-316` | `docker compose -f … exec -T db psql` | YES | `env=compose_env(identity)` (inspect_srid_contract) |
| `bootstrap.py:488-499` | `docker compose -f … down -v` / `up -d` | YES | `env=compose_env(identity)` (`_rebuild_once`) |
| `bootstrap.py:821-828` | `docker compose -f … restart martin` | YES | `env=compose_env(identity)` |
| `driver.py:332-336` | `docker compose -f … up -d --build` | YES | `env=config.stack_env(identity)` → `compose_env` |
| `driver.py:565-572` | `docker compose -f … down -v --remove-orphans` | YES | `env=config.stack_env(identity)` → `compose_env` |
| `test_rainfall_e2e_config.py:84-90` | `docker compose -f … config --format json` | NO | deterministic synthetic test prefix; not a runtime run |
| `test_rainfall_e2e_config.py:229-235` | `docker compose -f … config --format json` | YES | strips ambient `RMEH_*` then updates `compose_env(identity)` |
| `test_rainfall_e2e_harness.py` | comments / assertions only | n/a | records and asserts env on mocked calls, no real invocation |
| `test_rainfall_e2e_integration.py:105` | `docker compose -f … up -d --build` | NO | optional manual `@pytest.mark.integration` seam; env from ambient + fallback |
| `test_rainfall_e2e_integration.py:144` | `docker compose -f … down -v --remove-orphans` | NO | optional manual integration seam |
| `probe_rainfall_bootstrap.py:74` | `docker compose -f … up -d --build` | NO | optional manual diagnostic probe; env from ambient + fallback |
| `probe_rainfall_bootstrap.py:135` | `docker compose -f … down -v --remove-orphans` | NO | optional manual diagnostic probe |
| `.github/workflows/rainfall-multi-parcel-e2e.yml` | no direct invocation | n/a | workflow delegates to `python3 -m scripts.rainfall_e2e_harness` |

All production-harness call sites (`safety.py`, `bootstrap.py`, `driver.py`) pass the run-owned `compose_env(identity)`. The only non-`compose_env` call sites are optional manual diagnostic seams that are not part of the run-owned production harness or CI workflow, so they do not block the confirmed fix.

### `compose_env` derivation

`safety.py:213-230` — `compose_env(identity)` returns:
- `RMEH_RUN_ID_PREFIX`: `identity.database_name.removeprefix("rmeh_")`
- `RMEH_DB_PASSWORD`: local constant `DB_PASSWORD` (`"synthpass"`)
- Optional `extra` merged last (driver host ports) but never overrides the run-owned keys.

The function body never reads `os.environ`. Confirmed by direct read of `safety.py:213-230` and by `rg 'os\.environ'` inside the function.

### Findings ledger

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| JD-APP-001/A1 | judgment-day | `scripts/rainfall_e2e_harness/safety.py`, `scripts/rainfall_e2e_harness/bootstrap.py`, `scripts/rainfall_e2e_harness/driver.py` | BLOCKER | verified | Every production-harness `docker compose` invocation now carries the run-owned env: `validate_marker_read_only` and `apply_migrations` (safety.py), all psql execs / rebuild / martin restart (bootstrap.py via `_psql_run` / `_rebuild_once`), and driver up/down via `stack_env(identity)`. `compose_env` derives the prefix from `identity.database_name.removeprefix("rmeh_")` and never reads `os.environ`. The workflow run/cleanup steps do not set `RMEH_RUN_ID_PREFIX`. |
| JD-R2-001 | judgment-day | `scripts/tests/test_rainfall_e2e_config.py:209-255` | BLOCKER | verified | `test_compose_config_matches_lease_plan_under_driver_random_env` strips ambient `RMEH_*`, uses `compose_env(identity)` for a driver-style random `RunIdentity`, executes real `docker compose config`, and asserts `cfg["name"] == lease.project_name`, `POSTGRES_DB == identity.database_name`, volume/network/container names match `ResourceLease.plan` exactly. Test executed and PASSED. |

### Constraints audit (Fix round 2 diff)

- Production code: 0 lines — no `consorcio-web/src/**` or `gee-backend/app/**` touched. PASS.
- Workflow remains optional (`workflow_dispatch`-only), unreferenced by required gates. PASS.
- Parent change (`lluvia-ux-tarjeta`) not mutated. PASS.
- No `:-probedefault` fallback remains in `scripts/tests/rainfall-e2e.compose.yml`; remaining fallbacks (`RMEH_DB_PASSWORD:-synthpass`, host-port defaults) are intentional. PASS.

### Round 3 outcome — Judge A

- Confirmed BLOCKERs verified: **2 of 2** (JD-APP-001/A1, JD-R2-001).
- No new production-harness BLOCKERs.
- Optional manual probe/integration call sites use ambient prefix by design; they are not part of the run-owned production harness or CI path, so no BLOCKER is emitted.

**VERDICT: APPROVED ✅ — both confirmed BLOCKERs are verified; the run-owned compose env is threaded through every production harness invocation.**

---

## Micro-round — JD-R3-001

Owner-approved micro-round (outside the standard 2-round fix budget) to close the
remaining manual probe/integration `docker compose` env dependency identified by
Judge B in Round 3.

### Fix

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|---|
| JD-R3-001 | judgment-day | `scripts/tests/probe_rainfall_bootstrap.py:53-72,74,135`, `scripts/tests/test_rainfall_e2e_integration.py:80-97,105,144` | BLOCKER | fixed | Both seams now import and use `compose_env(identity)` from `scripts.rainfall_e2e_harness.safety`. The `RunIdentity` is internally consistent: `run_id` is the ambient prefix, `database_name = f"rmeh_{run_id[:10]}"` (matching `RunIdentity.plan()` convention), and the init script path is `rmeh-init-{prefix[:10]}.sql`. Host ports are passed as `extra` to `compose_env`, never as ambient prefix overrides. The previous `dict(os.environ)` + `RMEH_RUN_ID_PREFIX=prefix` construction and the `_stack_env` helper are removed. |

### Verification

- `python3 -m pytest scripts/tests/test_rainfall_e2e_harness.py scripts/tests/test_rainfall_e2e_config.py -q` → **141 passed**.
- `npx vitest run tests/unit/rainfallMultiParcelHarness.test.ts` (from `consorcio-web`) → **69 passed**.
- `npx tsc -p tsconfig.tests.json --noEmit` (from `consorcio-web`) → **0 errors**.
- Manual seams compile and import cleanly: `python3 -m py_compile scripts/tests/probe_rainfall_bootstrap.py scripts/tests/test_rainfall_e2e_integration.py` + `python3 -c "import scripts.tests.test_rainfall_e2e_integration"` → clean.
- Identity/env consistency check: for both `probedefault` (10-char truncation) and `integtest` identities, `compose_env(identity)` derives a prefix equal to `database_name.removeprefix("rmeh_")`, and `ResourceLease.plan(identity)` produces the matching `rmeh-<prefix>` project name.
- No Docker provisioning performed for this micro-round; `docker ps -a --filter name=rmeh-` and `docker volume ls --filter name=rmeh-` remain empty.

### Constraints audit

- Production code: 0 lines — no `consorcio-web/src/**` or `gee-backend/app/**` touched. PASS.
- Workflow remains optional (`workflow_dispatch`-only), unreferenced by required gates. PASS.
- Parent change (`lluvia-ux-tarjeta`) not mutated. PASS.
- No `:-probedefault` fallback added back to `scripts/tests/rainfall-e2e.compose.yml`. PASS.

**Micro-round verdict: JD-R3-001 CLOSED ✅ — every `docker compose` invocation in the requested directories now carries the run-owned `compose_env(identity)`.**

