# Review Ledger: Rainfall v2

**Target:** `openspec/changes/lluvia-v2/design.md`
**Review:** Judgment Day — Round 1 scoped re-judge complete
**Date:** 2026-08-06
**Artifact store:** hybrid

## Summary

| Bucket | Count |
|---|---:|
| Confirmed BLOCKER/CRITICAL | 1 |
| Suspect BLOCKER/CRITICAL | 2 |
| Contradictions | 0 |
| WARNING/SUGGESTION info | 1 |

## Findings

| id | lens | location | severity | status | convergence | evidence |
|---|---|---|---|---|---|---|
| JD-001 | judgment-day | `openspec/changes/lluvia-v2/design.md:20-30` | CRITICAL | verified | confirmed; both scoped re-judges approved | Round 1 design correction adds an explicit local half-open event window, no-auto-selection rule, cadence-aligned expected intervals, wet-run/contiguity semantics, 100% coverage and quality gate, deterministic duration and earliest-tie peak, plus suppression reasons. |
| JD-002 | judgment-day | `openspec/changes/lluvia-v2/design.md:30` | CRITICAL | info | suspect | One judge found that ending current-year comparison at `available_through` can hide missing days before the current date instead of representing the requested current-date period as partial. The other judge did not report this finding. |
| JD-003 | judgment-day | `openspec/changes/lluvia-v2/design.md:22,31,35` | CRITICAL | info | suspect | One judge found that parcel-origin context may collide in the cache with direct zone/basin requests, allowing a cached snapshot to omit the mandatory regional-estimate label. The other judge did not report this finding. |
| JD-004 | judgment-day | `openspec/changes/lluvia-v2/design.md:19-24` | WARNING | info | single-judge theoretical | `ScopeRef` permits caller geometry while the new POST endpoints do not explicitly reuse the existing pre-parse body-size guard; an oversized authorized request could be buffered before direct geometry execution is rejected. |

## Round State

- Round 1 scoped re-judge: independent Judge A approved `JD-001`; it is verified.
- Round 1 scoped re-judge: independent Judge B approved `JD-001`; it is verified.
- Only confirmed finding `JD-001` entered the fix/re-judge loop.
- Suspect findings `JD-002` and `JD-003` require manual triage and are not auto-fix inputs.
- `JD-004` is informational and never enters the fix loop.

**Judgment:** APPROVED

## Apply PR 1 — Judgment Day first pass

**Target:** `feat/lluvia-v2-01-evidence-foundation`
**Review:** Judgment Day — first pass
**Artifact store:** hybrid

### Summary

| Bucket | Count |
|---|---:|
| Confirmed CRITICAL/verified | 7 |
| Suspect CRITICAL/info | 1 |
| Contradictions | 0 |
| WARNING/info | 1 |

### Findings

| id | lens | location | severity | status | convergence | evidence |
|---|---|---|---|---|---|---|
| PR1-JD-001 | judgment-day | `gee-backend/app/db/migrations/versions/lluvia_v2_001_evidence_foundation.py` | CRITICAL | verified | both scoped re-judges approved | Migration/ORM drift: migration omits `RainfallSourceEligibility.created_at` and `RainfallBackfillCheckpoint.completed_at`. |
| PR1-JD-002 | judgment-day | `gee-backend/app/domains/geo/rainfall/schemas.py` | CRITICAL | verified | both scoped re-judges approved | `MetricResult` omits coverage, completeness, quality, discrepancies and Pydantic can discard them. |
| PR1-JD-003 | judgment-day | `gee-backend/app/domains/geo/rainfall/policy.py` | CRITICAL | verified | both scoped re-judges approved | Source selection ignores `CandidateManifest.enabled` and role, so disabled/wrong-role sources can be selected. |
| PR1-JD-004 | judgment-day | `gee-backend/app/domains/geo/rainfall/models.py` | CRITICAL | verified | both scoped re-judges approved | Interval and analysis revision immutability is claimed but UPDATE/DELETE is not prevented. |
| PR1-JD-005 | judgment-day | `gee-backend/app/domains/geo/rainfall/ports.py`, `gee-backend/tests/new/geo/rainfall/` | CRITICAL | verified | both scoped re-judges approved | Adapter protocol/golden evidence contract is insufficient: unconstrained object, missing SourceBatch dimensions and scientific golden checks; task 1.1 is overstated. |
| PR1-JD-006 | judgment-day | `gee-backend/app/domains/geo/rainfall/models.py` | CRITICAL | verified | both scoped re-judges approved | Backfill uniqueness omits scope_kind and scope_version, causing cross-kind/version collisions. |
| PR1-JD-007 | judgment-day | `gee-backend/.gitignore:10`, `gee-backend/tests/new/geo/rainfall/fixtures/approval-audit.json` | CRITICAL | verified | hardening validation | A single exact `.gitignore` negation makes the fixture visible to Git; it does not unignore any other JSON path. |
| PR1-JD-008 | judgment-day | `gee-backend/tests/new/geo/rainfall/test_evidence_foundation.py` | CRITICAL | info | suspect; single judge | Raw-payload prohibition test only checks a literal `raw_payload` column and may permit unrestricted JSON snapshots. |
| PR1-JD-009 | judgment-day | `gee-backend/app/domains/geo/rainfall/models.py`, `gee-backend/app/db/migrations/versions/lluvia_v2_001_evidence_foundation.py` | WARNING | info | severity mismatch; assessment real | Two-year retention is only nullable unconstrained timestamps/index; Judge A rated CRITICAL and Judge B WARNING, so canonical severity is WARNING. |

### Round State

- Counts: confirmed=7, suspect critical=1, contradictions=0, warnings=1.
- Scoped re-judge Judge A approved `PR1-JD-001` through `PR1-JD-006`; all are verified.
- Scoped re-judge Judge B approved `PR1-JD-001` through `PR1-JD-006`; all are verified.
- `PR1-JD-007` was verified during PR hardening by an exact fixture-path ignore exception; `PR1-JD-008` remains suspect informational and is not a fix-loop input.
- `PR1-JD-009` is WARNING/info and never a fix-loop input.
- Hardening evidence: 7 focused rainfall tests, Ruff lint/format, and compileall passed. A disposable CI-equivalent `pgrouting/pgrouting:16-3.4-3.6.1` Testcontainers database completed upgrade head and downgrade to `0020_add_canal_consorcio`, asserting rainfall tables, triggers, function cleanup, and revision stamps. No production/persistent database was used.
- The earlier Design judgment remains **APPROVED**.

**Judgment for Apply PR1:** APPROVED


## PR1 pre-commit review-risk

**Target:** `feat/lluvia-v2-01-evidence-foundation`
**Review:** fresh pre-commit review-risk sweep
**Status:** **pre-commit review-risk: PASSED**

| Bucket | Count |
|---|---:|
| CRITICAL/verified | 5 |
| WARNING/info | 3 |

| id | lens | location | severity | status | convergence/refutation | evidence |
|---|---|---|---|---|---|
| RISK-001 | risk | `gee-backend/app/domains/geo/rainfall/models.py:63-64,106-117`; `gee-backend/app/db/migrations/versions/lluvia_v2_001_evidence_foundation.py:49-50,102-106` | CRITICAL | verified | scoped re-review PASS | The append-only ORM hook and database triggers reject every UPDATE/DELETE of interval rows, including the documented `superseded_at` / `expires_at` lifecycle updates required for supersession and retention. |
| RISK-002 | risk | `gee-backend/app/domains/geo/rainfall/models.py:22-37,106-117`; `gee-backend/app/db/migrations/versions/lluvia_v2_001_evidence_foundation.py:18-36,102-106` | CRITICAL | verified | scoped re-review PASS | `RainfallSourceEligibility` is an audit/evidence record but is excluded from both ORM immutability and database triggers, so its eligibility criteria and approval history can be rewritten or deleted. |
| RISK-003 | risk | `gee-backend/app/domains/geo/rainfall/policy.py:64-78` | CRITICAL | verified | scoped re-review PASS | `select_source` accepts `dict[str, bool]`; this collapses source role and evidence revision into a boolean, allowing approval evidence from a different role or revision to authorize selection. |
| RISK-004 | risk | `gee-backend/app/domains/geo/rainfall/schemas.py:21-45` | CRITICAL | verified | scoped re-review PASS | `MetricResult` allows every state with either value and either reason; it does not require a numeric value for available/partial, nor suppress it and require a reason for suppressed/unavailable. |
| RISK-005 | risk | `gee-backend/app/domains/geo/rainfall/ports.py:32-59` | CRITICAL | verified | scoped re-review PASS | `SourceBatch` and `RainfallSourceAdapter.fetch` carry only `scope_id`, omitting `scope_kind` and `scope_version`; identical IDs across scope types/versions cannot be isolated. |
| RISK-006 | risk | `openspec/changes/lluvia-v2/tasks.md:29-32`; `openspec/changes/lluvia-v2/apply-progress.md:60-64,77-85` | WARNING | info | not applicable | Planning/progress claim provider-spike golden evidence and completed retention/provider requirements, while the slice contains disabled manifests and synthetic contract tests only; no provider or scientific golden evidence exists. |
| RISK-007 | risk | `gee-backend/app/domains/geo/rainfall/models.py:16,33-34,80`; `gee-backend/app/db/migrations/versions/lluvia_v2_001_evidence_foundation.py:25-26,68,107-117` | WARNING | info | not applicable | ORM uses PostgreSQL `JSON` while migration uses `JSONB`; index definitions exist only in migration, leaving schema/index metadata drift that can make later autogeneration or model inspection misleading. |
| RISK-008 | risk | `openspec/changes/lluvia-v2/tasks.md:7-17`; `openspec/changes/lluvia-v2/apply-progress.md:56-58`; branch `feat/lluvia-v2-01-evidence-foundation` | WARNING | info | not applicable | Tasks retain `ask-on-risk` and chain strategy `pending`, while apply progress claims a feature-branch chain and the branch does not follow the repository `type/description` convention. |

### Round state
- Fresh review found five CRITICAL candidates and three WARNING informational findings.
- General refuter verdict: RISK-001 through RISK-005 stood; scoped re-review PASS verified all five with no new fix-line BLOCKER/CRITICAL findings.
- RISK-006 through RISK-008 remain WARNING/info and do not enter the fix loop.
- **pre-commit review-risk: PASSED**


## PR1 pre-push review-risk

**Target:** `feat/lluvia-v2-01-evidence-foundation`
**Review:** fresh pre-push review-risk sweep
**Status:** **pre-push review-risk: PASSED**

| Bucket | Count |
|---|---:|
| BLOCKER/open | 1 |
| CRITICAL/open | 3 |
| WARNING/info | 2 |

| id | lens | location | severity | status | convergence/refutation | evidence |
|---|---|---|---|---|---|
| PUSH-RISK-001 | risk | `gee-backend/app/db/migrations/versions/lluvia_v2_001_evidence_foundation.py:117-148` | CRITICAL | verified | scoped re-review PASS | The controlled purge relies on a transaction-local GUC which any DELETE-capable role can set; the purge function has unrestricted default EXECUTE, so direct deletion protection can be bypassed. |
| PUSH-RISK-002 | risk | `gee-backend/app/domains/geo/rainfall/policy.py`; `adapters/manifests.py` | CRITICAL | verified | scoped re-review PASS | Typed eligibility binds source, role, and evidence revision but not manifest version, provider revision, or checksum, permitting stale manifest evidence. |
| PUSH-RISK-003 | risk | `gee-backend/app/domains/geo/rainfall/schemas.py:21-52`; `ports.py:8-29` | CRITICAL | verified | scoped re-review PASS | Metric and source interval floats accept NaN/non-finite values, which serialize as JSON null and break audit consistency. |
| PUSH-RISK-004 | risk | commits `b001b0d`, `b71b8ee`; `openspec/changes/lluvia-v2/tasks.md:7-17` | BLOCKER | wont-fix | maintainer convention; no size exception | Maintainer convention: 400 behavioral production lines plus 2 package docstrings; tests 330; migrations 167; OpenSpec 666; config 1. No size exception required. |
| PUSH-RISK-005 | risk | `openspec/changes/lluvia-v2/{apply-progress,review-ledger,tasks}.md` | WARNING | info | not applicable | SDD evidence/test counts and the retained old RISK-008 chain metadata are inconsistent. |
| PUSH-RISK-006 | risk | `gee-backend/app/domains/geo/rainfall/models.py:16,34-35,92`; migration index declarations | WARNING | info | not applicable | ORM JSON versus migration JSONB and index metadata remain divergent. |

### Round state
- Fresh review found one BLOCKER, three CRITICAL candidates, and two WARNING informational findings.
- General refuter verdict: PUSH-RISK-001 through PUSH-RISK-004 **stand** (4 surviving, 0 refuted).
- PUSH-RISK-005 and PUSH-RISK-006 remain WARNING/info.
- **fix round 1 required for PUSH-RISK-001..003; maintainer decision required for PUSH-RISK-004 (split vs size:exception); pre-push blocked**

## PR1 pre-push resilience incident

**Issue:** #164

| id | lens | severity | status | evidence |
|---|---|---|---|---|
| RES-001 | resilience | CRITICAL | open | javi-forge Node runner lacks Docker/Make/Python, so required checks cannot execute. |
| RES-002 | resilience | CRITICAL | open | Compile stage masks build exit 127 via `|| true`. |
| RES-003 | resilience | WARNING | info | Hook suggests no-verify without proving equivalent checks. |

- Current push blocked. `--no-verify` is allowed only after equivalent full checks pass on exact HEAD, with no later code commit.

## PR1 backend gate invocation reliability incident

**Issue:** #164

| id | lens | severity | status | evidence |
|---|---|---|---|---|
| REL-001 | reliability | WARNING | info | The full-suite subprocess test is cwd-sensitive: repository-root invocation causes `ModuleNotFoundError`, while backend-cwd invocation passes. |
| REL-002 | reliability | WARNING | info | Local `Makefile` / `scripts/test-local.sh` use a 70% coverage floor that drifts from the authoritative CI/package 60% threshold. |

- The previous repository-root command is invalid full-gate evidence. The authoritative backend command must run from `gee-backend/`:
  `./venv/bin/python -m pytest tests/new/ --cov=app --cov-config=.coveragerc --cov-report=term --cov-fail-under=60 -q --no-header --tb=short`.
- #164 remains the permanent correction vehicle for the pre-push harness and compile-wrapper failure masking.

## Apply PR 2 — Judgment Day first pass

**Target:** `feat/lluvia-v2-02-backend-api` uncommitted diff
**Review:** Judgment Day — first pass
**Artifact store:** hybrid

### Summary

| Bucket | Count |
|---|---:|
| Confirmed CRITICAL/open | 1 |
| Suspect CRITICAL/info | 4 |
| Contradictions | 0 |
| WARNING/info | 1 |

### Findings

| id | lens | location | severity | status | convergence | evidence |
|---|---|---|---|---|---|---|
| PR2-JD-001 | judgment-day | `gee-backend/app/domains/geo/rainfall/repository.py:RainfallRepository._validate_active_zoning` | CRITICAL | verified | model-diverse scoped re-judge approved | Active zoning validation now rejects malformed collections, missing/duplicate identities, invalid/empty geometries, and truthy non-object `feature.properties` with controlled `ScopeConfigurationError`; missing/null/empty properties preserve feature-ID fallback. |
| PR2-JD-002 | judgment-day | `gee-backend/app/domains/geo/rainfall/temporal.py:41-62` | CRITICAL | info | suspect; single judge | Event peak/duration truncates `rolling_window / cadence` without requiring exact divisibility, so unsupported cadence can silently change scientific window semantics. |
| PR2-JD-003 | judgment-day | `gee-backend/app/domains/geo/rainfall/router.py:32-38`; `gee-backend/app/domains/geo/router.py:243` | CRITICAL | info | suspect; single judge | The production-registered scope body accepts an unbounded geometry object; authorization, CSRF and generic rate limiting do not impose a pre-parse byte limit. |
| PR2-JD-004 | judgment-day | `gee-backend/app/domains/geo/rainfall/repository.py:43-49` | CRITICAL | info | suspect; single judge | Zone identity uses `zone_id + zoning.version`, while zoning versions may be per-cuenca and generic IDs may repeat across active cuencas, potentially producing indistinguishable scope choices. |
| PR2-JD-005 | judgment-day | `gee-backend/app/domains/geo/rainfall/temporal.py:75-80` | CRITICAL | info | suspect; single judge | Rolling totals build a dictionary before completeness validation, so duplicate timestamps can collapse last-write-wins and pass cadence checks with an incorrect total. |
| PR2-JD-006 | judgment-day | `gee-backend/app/domains/geo/rainfall/temporal.py:10-11` | WARNING | info | single judge; partial-stage assessment | `comparison_end` does not itself clamp current or historical comparisons to a source `available_through`; an upstream caller can compensate while task 2.4 remains incomplete. |

### Round state

- `PR2-JD-001` is the only confirmed fix-loop input and requires Round 1 correction plus scoped dual re-judgment.
- `PR2-JD-002` through `PR2-JD-005` are suspect informational findings and are not automatic fix inputs.
- `PR2-JD-006` is WARNING/info and never enters the fix loop.
- Focused evidence before Judgment Day: 30 non-DB rainfall tests plus 3 real PostgreSQL resolver tests passed; focused Ruff check/format passed.
- Production behavioral scope is 340 lines under the maintainer's 400-line convention.

**Judgment for Apply PR2:** ESCALATED — Round 1 fix approval required

### Apply PR 2 — Judgment Day Round 2 scoped re-judge

| Judge | Model | Verdict for PR2-JD-001 | Evidence |
|---|---|---|---|
| A | `gpt-5.6-sol` | verified | Confirmed active FeatureCollection, identity, PostGIS validity/non-empty checks and basin-masking regressions close the original malformed-zoning path. |
| B | `gpt-5.6-terra` | open | Found a residual fix-line path: truthy non-object `feature.properties` reaches `.get("zone_id")` and raises uncontrolled `AttributeError` rather than `ScopeConfigurationError`. |

- Round 1 verification exposed empty geometries accepted by `ST_IsValid`; Round 2 added explicit `ST_IsEmpty` rejection.
- Round 2 focused evidence: 39 Rainfall tests passed; focused Ruff check/format passed; production behavioral diff is 387 lines.
- The model-diverse judges contradicted on the remaining fix-line behavior.
- The two-fix-round convergence budget is exhausted. No further automatic fix is permitted in this Judgment Day run.
- `PR2-JD-001` remains open pending manual decision or a new explicitly authorized review cycle.

**Judgment for Apply PR2:** ESCALATED — contradictory Round 2 verdicts

### Apply PR 2 — New authorized critical cycle terminal re-judge

| Judge | Model | Verdict for PR2-JD-001 |
|---|---|---|
| A | `gpt-5.6-sol` | verified |
| B | `gpt-5.6-terra` | verified |

- The residual truthy non-object `feature.properties` path now raises controlled `ScopeConfigurationError` before mapping access.
- Missing, null, and empty-object properties retain the intended feature-level ID fallback.
- Regression evidence: resolver suite 14 passed; full focused Rainfall suite 44 passed; focused Ruff check/format and `git diff --check` passed.
- Both model-diverse scoped judges found no new BLOCKER/CRITICAL on fix-touched lines.
- `PR2-JD-001` is verified. Suspect/info findings `PR2-JD-002` through `PR2-JD-006` retain their original non-blocking statuses.

**Judgment for Apply PR2 critical cycle:** APPROVED

## PR2A pre-commit review-reliability

**Target:** `feat/lluvia-v2-02-backend-api` uncommitted deterministic-core diff
**Review:** fresh pre-commit review-reliability — Round 1
**Status:** **PASSED**

| id | lens | location | severity | status | convergence/refutation | evidence |
|---|---|---|---|---|---|---|
| RELIABILITY-001 | reliability | `gee-backend/app/domains/geo/rainfall/temporal.py:event_peak_and_duration` | CRITICAL | verified | general refuter: stands; GREEN | A positive rolling window must divide exactly by the source cadence; non-divisible windows now suppress via the existing `EventSuppressed` path instead of flooring to a shorter scientific window. |
| RELIABILITY-002 | reliability | `gee-backend/app/domains/geo/rainfall/temporal.py:rolling_total` | CRITICAL | verified | general refuter: stands; GREEN | Duplicate interval starts are rejected before construction of the timestamp-to-value mapping, preventing last-write-wins totals from passing coverage validation. |

### Round state

- Focused temporal regressions: 2 passed.
- Focused Rainfall suite: 44 passed.
- Focused Ruff check/format and `git diff --check`: passed.
- Production behavioral scope: 399 lines, within the 400-line PR2A cap.

### PR2A pre-commit reliability scoped re-review

- `RELIABILITY-001`: verified; non-divisible event windows suppress before integer width calculation, and divisible-window semantics remain covered.
- `RELIABILITY-002`: verified; duplicate starts are rejected before dictionary construction, while unique cadence and null-versus-zero behavior remain covered.
- No new BLOCKER/CRITICAL finding was found on fix-touched lines.
- Evidence: 2 targeted regressions passed; 44 focused Rainfall tests passed; Ruff check/format and diff check passed.
- Production behavioral diff: 399 lines.

**PR2A pre-commit review-reliability:** PASSED

## PR2A pre-push review-reliability — RELIABILITY-003

| id | lens | location | severity | status | convergence/refutation | evidence |
|---|---|---|---|---|---|---|
| RELIABILITY-003 | reliability | `gee-backend/app/domains/geo/rainfall/repository.py:_validate_active_zoning` | CRITICAL | verified | pre-push candidate; general refuter: stands; GREEN; scoped re-review PASS | The validation now rejects every non-object `properties` value whenever the key is present and non-null, including falsey `[]`, `""`, `0`, and `false`; only missing, null, and `{}` retain feature-ID fallback. |

### Round state

- RED: the four falsey invalid-properties cases failed before the validation change.
- GREEN: targeted repository regressions passed (9 passed), covering falsey invalid values and missing/null/empty-object feature-ID fallback.
- Scoped verification: PASS; targeted regressions 9 passed, focused Rainfall suite 48 passed, Ruff and restricted diff checks passed, and the PR2A production behavioral range remains 399 lines.


## PR2A pre-push review-reliability — RELIABILITY-004

| id | lens | location | severity | status | convergence/refutation | evidence |
|---|---|---|---|---|---|---|
| RELIABILITY-004 | reliability | gee-backend/app/domains/geo/rainfall/repository.py:_validate_active_zoning | CRITICAL | verified | candidate; general refuter: stands; GREEN; scoped re-review PASS | Fail closed unless the active zoning is a FeatureCollection, every member is a Feature, and each geometry is a Polygon or MultiPolygon; existing PostGIS validity and emptiness checks remain required. |

### Round state

- RED: top-level missing/wrong type and Point geometry regressions failed before the validation change; malformed member type cases were already rejected through a later geometry guard.
- GREEN: targeted new regressions passed (6 passed); complete scope repository suite passed (25 passed), including valid Polygon/MultiPolygon coverage.
- Focused Rainfall suite: 55 passed. Ruff format/check and git diff --check passed.
- Production behavioral range: exactly 400 raw added lines and 0 deletions across the six production files, within the PR2A cap without exclusions.
- RELIABILITY-004 is verified; targeted structural/property tests passed (16), the focused Rainfall suite passed (55), Ruff and diff checks passed, and no new BLOCKER/CRITICAL was found on fix-touched lines.

## PR2A final pre-push review-reliability

**Target:** `277c7cc2588c40b60dd8e0ac46ecef67ea47a218..af14e395afbe8597c69d258dd207eb1a202a4b8b`
**Verdict:** PASS

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| — | reliability | — | — | — | Empty ledger; no defensible user-impacting defects found. |

- Exact production range: 400 additions and 0 deletions across six production files.
- Focused Rainfall suite: 55 passed; Ruff and diff checks passed.
- RELIABILITY-001 through RELIABILITY-004 remain verified.

## PR2A pre-PR full 4R review — fix round 1

**Target:** `277c7cc2588c40b60dd8e0ac46ecef67ea47a218..ad2468986784f274468924817e29f16a6d9c1d42`

### Merged lens ledger

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| RELIABILITY-005 | reliability | `gee-backend/app/domains/geo/rainfall/repository.py:_validate_active_zoning,resolve_parcel_scopes` | CRITICAL | verified | Validation previously fell back on falsey non-null `zone_id`, while SQL used null-only fallback, allowing validated and emitted identities to disagree. |
| RELIABILITY-006 | reliability | `gee-backend/app/domains/geo/rainfall/repository.py:_validate_active_zoning` | CRITICAL | verified | Topology and SRID tagging previously accepted out-of-range WGS84 coordinates, allowing malformed active zoning to degrade to basin-only choices. |

- `review-risk`: empty ledger.
- `review-resilience`: empty ledger.
- `review-readability`: empty ledger.
- `review-reliability`: RELIABILITY-005 and RELIABILITY-006.

### Full-4R adversarial verification

| id | correctness | exploitability/impact | reproducibility | vote |
|---|---|---|---|---|
| RELIABILITY-005 | stands | refuted | stands | stands (2 of 3) |
| RELIABILITY-006 | stands | refuted | stands | stands (2 of 3) |

### Fix round 1 state

- RELIABILITY-005 now falls back to `feature.id` only when `zone_id` is missing or null; every present value must be a non-empty string, aligning validation with SQL identity emission.
- RELIABILITY-006 now requires the parsed Polygon/MultiPolygon envelope to be contained by the WGS84 bounds before scope resolution.
- RED/GREEN regressions cover falsey non-null zone IDs, missing/null fallback, valid boundary coordinates, and out-of-range longitude/latitude.
- Scope repository suite: 36 passed. Focused Rainfall suite: 66 passed. Ruff and `git diff --check`: passed.
- Exact six-file production range remains 400 additions and 0 deletions.
- Scoped fix re-review: PASS. RELIABILITY-005 and RELIABILITY-006 are verified; 11 targeted regressions, 36 scope tests, and 66 focused Rainfall tests passed; Ruff and diff checks passed; no new BLOCKER/CRITICAL was found on fix-touched lines.

## PR2B apply Judgment Day — round 1

**Target:** uncommitted `feat/lluvia-v2-02b-api-policy-contract` diff against `d6d6b2914a95b0360b4004c1cc2745e6f0d3965a`
**Judges:** two blind model-diverse reviews
**State:** APPROVED after fix round 2

| id | lens | location | severity | status | convergence | evidence |
|---|---|---|---|---|---|---|
| PR2B-JD-001 | judgment-day | `gee-backend/app/domains/geo/rainfall/router.py:79-94`; `gee-backend/app/domains/geo/rainfall/service.py`; `gee-backend/app/domains/geo/rainfall/policy.py` | CRITICAL | verified | final fix round 2 GREEN; dual scoped re-judgment PASS | JSON and CSV derive from the same fail-closed normalized metric representation; malformed metric-like mappings, invalid threshold domains, and below-duration-threshold values cannot disclose numeric values. |
| PR2B-JD-002 | judgment-day | `gee-backend/app/domains/geo/rainfall/router.py:29-41,65-80` | CRITICAL | info | suspect; Judge A only | FastAPI buffers the typed body before route dependencies, so the route-level 16 KiB check does not prevent allocation for chunked bodies without Content-Length. |
| PR2B-JD-003 | judgment-day | `gee-backend/app/domains/geo/rainfall/router.py:58-86` | CRITICAL | info | suspect; Judge A only | The POST body currently exposes internal snapshot lookup keys rather than the specified public `{scope, year, event_window?}` analysis request contract. |
| PR2B-JD-004 | judgment-day | `consorcio-web/public/version.json` | WARNING | info | Judge A only; known unrelated dirt | Generated local version drift must remain excluded from PR2B. |

### Evidence

- Apply RED: 4 focused contract failures; GREEN: API 15 passed, Rainfall 70 passed, auth HTTP 2 passed.
- Production diff: 66 additions and 7 deletions, within the 400-line budget.
- Confirmed fix round 1 requires explicit user approval before implementation.

### PR2B Judgment Day fix round 1 re-judgment

**Result:** ESCALATED; PR2B-JD-001 remains open.

- Judge A: malformed metric dictionaries missing the `metric` key bypass normalization, retain numeric JSON values, and diverge from empty CSV output.
- Judge B: negative coverage/quality thresholds are accepted and `duration_threshold` is present but not evaluated, allowing below-threshold numeric values.
- Both judges classified these as residual paths of PR2B-JD-001, with no separate new BLOCKER/CRITICAL findings.
- Positive evidence: JSON and CSV both invoke `normalize_snapshot`; targeted API 17 passed; focused Rainfall 72 passed; auth checks passed; Ruff lint and diff checks passed.
- Ruff format remains failing for `service.py` and `test_backend_api.py` and must be corrected in fix round 2.
- Fix round 2 is the final allowed convergence round.


### PR2B Judgment Day fix round 2 evidence

- `PR2B-JD-001` is **fixed** after the final authorized convergence round: mappings with a metric-like numeric `value` but no `metric` normalize to an unavailable `unknown` metric, so JSON and CSV consume the same fail-closed representation.
- Coverage and quality thresholds must be finite fractions in `[0, 1]`; duration thresholds must be finite and nonnegative. Any invalid threshold configuration suppresses disclosure.
- `duration_threshold` is applied only to the `duration` metric: below suppresses with `duration_below_threshold`; equal and above disclose when all other gates pass. Existing valid complete metric disclosure and per-metric isolation remain covered.
- TDD evidence: RED 5 targeted regressions failed before implementation; GREEN targeted API 24 passed, full Rainfall 79 passed, auth/API 53 passed.
- Verification: `./venv/bin/python -m ruff check --config ruff.toml ...` passed; required Ruff format applied to `service.py` and `test_backend_api.py`, then `ruff format --check` passed; `git diff --check` passed.
- PR2B production raw diff relative to `d6d6b2914a95b0360b4004c1cc2745e6f0d3965a`: 198 additions, 10 deletions across `policy.py`, `router.py`, and `service.py` (under the 400-addition cap).
- `PR2B-JD-002` and `PR2B-JD-003` remain suspect/info; `PR2B-JD-004` remains WARNING/info. No other ledger status changed.


### PR2B Judgment Day fix round 2 re-judgment

- Both blind model-diverse judges verified PR2B-JD-001.
- Missing-metric numeric mappings fail closed; JSON and CSV share normalized output; invalid threshold domains suppress; duration boundaries are enforced; valid complete metrics remain available.
- Targeted API: 24 passed. Focused Rainfall: 79 passed. Auth/API: 53 passed. Ruff check/format and diff check passed.
- Production diff: 198 additions and 10 deletions, within the 400-addition cap.
- No new BLOCKER/CRITICAL finding was found on round-2 fix-touched lines.
- PR2B-JD-002, PR2B-JD-003 and PR2B-JD-004 remain informational.

**JUDGMENT: APPROVED**

## PR2B pre-commit review-reliability — RELIABILITY-PR2B-001

| id | lens | location | severity | status | convergence/refutation | evidence |
|---|---|---|---|---|---|---|
| RELIABILITY-PR2B-001 | reliability | `gee-backend/app/domains/geo/rainfall/service.py:_normalize_metric` | CRITICAL | verified | candidate; general refuter: stands; GREEN; scoped re-review PASS | Raw validation precedes Pydantic: boolean, string, and non-finite values fail closed; finite integers/floats and null semantics are preserved across aligned JSON/CSV output. |

### Fix state

- RED: focused persisted-value contract failed for `true`, `false`, and numeric string values because Pydantic coerced them to floats.
- GREEN: focused parametrized contract passed for booleans, numeric string, finite integer, finite float, and null/unavailable value.
- Scoped re-review PASS: focused 6, API 30, Rainfall 85, auth/API 59, Ruff check/format, and `git diff --check` passed; no new BLOCKER/CRITICAL finding was found on fix-touched lines.
- `RELIABILITY-PR2B-002` and `PR2B-JD-002` through `PR2B-JD-004` remain unchanged.

## PR2B pre-push review-reliability — RELIABILITY-001

| id | lens | location | severity | status | convergence/refutation | evidence |
|---|---|---|---|---|---|---|
| RELIABILITY-001 | reliability | `gee-backend/app/domains/geo/rainfall/service.py:_normalize_metric` | CRITICAL | verified | general refuter: stands; GREEN; scoped re-review PASS | The 2-addition raw guard runs before Pydantic coercion: boolean, numeric-string and non-finite `coverage`/`completeness` fail closed as `metric_contract_invalid`; finite `0.0`/`1.0` boundaries and null/unavailable semantics are preserved; JSON and CSV remain aligned. Targeted 18, Ruff check/format and `git diff --check` passed, with no new BLOCKER/CRITICAL on fix-touched lines. |

### Fix state

- Safety net: targeted Rainfall API suite passed before edits (30 passed).
- RED: focused raw-evidence regression produced 4 expected failures for boolean/numeric-string coverage/completeness; six non-finite cases already failed closed.
- GREEN/TRIANGULATE: 18 focused cases passed across both fields, malformed types, finite boundaries, null values, and JSON/CSV parity.
- Verification evidence: targeted API 48 passed; full focused Rainfall 103 passed; bounded auth/API 77 passed; Ruff check/format and `git diff --check` passed.
- Production delta for this fix: 2 additions and 0 deletions. PR2B production range: 207 additions and 10 deletions, below the 400-addition cap.
- Scoped re-review PASS: `RELIABILITY-001` is verified; the 2-addition guard runs before Pydantic, targeted 18 and Ruff/format/diff checks passed, and no new BLOCKER/CRITICAL was found on fix-touched lines.
- Existing WARNING/info entries remain unchanged.

## PR2B PRE-PR full-4R — fix round 1

**Target:** `d6d6b2914a95b0360b4004c1cc2745e6f0d3965a..87fdc3d659b060a506dfea14dc465756dd45e1fa`
**Vote rule:** each CRITICAL survives unless at least two of three independent refuters reject it.
**State:** all ten candidates survived 2-of-3; fix round 1 verified by scoped reliability re-review.

| id | lens | severity | correctness | impact | reproducibility | status | consolidated fix |
|---|---|---|---|---|---|---|---|
| READABILITY-003 | readability | CRITICAL | stands | stands | stands | verified | A — typed-body pre-buffering removed; shared streamed bounded JSON runs first. |
| RISK-001 | risk | CRITICAL | stands | stands | stands | verified | A — chunked bodies abort at 16 KiB before parsing or snapshot lookup. |
| RESILIENCE-001 | resilience | CRITICAL | stands | stands | stands | verified | A — malformed, oversized and disconnected streams map deterministically to 422/413/400. |
| READABILITY-002 | readability | CRITICAL | stands | stands | stands | verified | B — public request is `{scope,year,event_window?}`; fingerprint/revisions are server-owned. |
| RISK-002 | risk | CRITICAL | stands | refuted | stands | verified | B — newest immutable snapshot resolves by server-derived fingerprint and persisted creation time; historical CSV remains revision-addressed. |
| READABILITY-001 | readability | CRITICAL | stands | stands | stands | verified | C — rainfall wet cutoff is no longer compared with duration hours; unset cutoff suppresses peak and duration. |
| RELIABILITY-001 | reliability | CRITICAL | stands | stands | stands | verified | D — canonical root/direct metric-group nesting is validated before normalization. |
| RESILIENCE-002 | resilience | CRITICAL | stands | stands | stands | verified | D — JSON and CSV consume the same accepted direct metric traversal; invalid envelopes fail closed. |
| RELIABILITY-002 | reliability | CRITICAL | stands | stands | stands | verified | E — mixed naive/aware metric bounds become `metric_contract_invalid`, not an uncaught TypeError. |
| RELIABILITY-003 | reliability | CRITICAL | stands | stands | stands | verified | F — raw quality score must be finite numeric, non-boolean, and within `[0,1]`. |

### Fix evidence

- Safety net: existing Rainfall API suite passed before edits (48 passed).
- RED: 20 focused cases produced 13 expected failures and 7 already-passing boundary cases (the 20th case is the final OpenAPI publication TDD addition).
- GREEN/TRIANGULATE: focused 20 passed; combined prior/new API regressions 68 passed.
- Production range: 382 additions / 48 deletions relative to PR2A, excluding tests/docs/migrations/generated files; below the 400-addition cap.
- Warning/info entries are unchanged. Fresh scoped re-review and terminal verification are still required before any candidate becomes verified.

### Scoped re-review (reliability lens) — fix round 1 verdicts

- `READABILITY-003` — **verified**: `router.py` replaces typed bodies with `Depends(parse_scope_request)`/`Depends(parse_analysis_request)` and `openapi_extra` schemas, so FastAPI no longer pre-buffers the typed body.
- `RISK-001` — **verified**: `cache_bounded_request_body` enforces Content-Length first and aborts the stream at 16 KiB with 413 before JSON parsing or snapshot lookup; chunked-no-length regression proves rejection pre-parse.
- `RESILIENCE-001` — **verified**: oversized/invalid Content-Length, malformed JSON, non-object payload and client disconnect map deterministically to 413/422/422/400 via shared `parse_bounded_json_object`.
- `READABILITY-002` — **verified**: `AnalysisRequest` is `{scope, year, event_window?}` with `extra=forbid`; internal fingerprint/revision keys are rejected and absent from the published OpenAPI body.
- `RISK-002` — **verified**: server derives the sha256 fingerprint; `get_snapshot` orders by `created_at DESC, id DESC`; untracked migration `lluvia_v2_002_analysis_created_at.py` adds the column and index; CSV remains addressed by revision UUID.
- `READABILITY-001` — **verified**: `apply_metric_policy` never compares duration hours with the cutoff; unset `duration_threshold` suppresses `duration`/`peak` via `policy_threshold_unset`; boundary test shows 0.9/1.0/1.1 all available.
- `RELIABILITY-001` — **verified**: `normalize_snapshot` validates root keys against `SNAPSHOT_ROOT_KEYS` and requires metric-like dict members per group before any normalization; invalid envelopes raise `SnapshotContractError`.
- `RESILIENCE-002` — **verified**: JSON and CSV routes both call `normalize_snapshot` and `metric_rows` traverses only `METRIC_GROUPS`, so both representations consume the identical accepted traversal and fail closed as 503.
- `RELIABILITY-002` — **verified**: `MetricResult` rejects mixed naive/aware interval bounds before the ordering comparison and `_normalize_metric` catches `(TypeError, ValidationError)` as `metric_contract_invalid` in both JSON and CSV.
- `RELIABILITY-003` — **verified**: raw quality score must be non-boolean `int/float`, finite, and within `[0,1]`; violations become `metric_quality_invalid` and valid 0.0/1.0 boundaries remain available.
- Spot-check evidence: focused contract file `test_prepr_contract_fixes.py` re-run — 20 passed; `ScopeRef` fields exactly match `ScopeRequest`, so the parcel path cannot raise an uncaught `TypeError`.
- Info-level signals (no new round): the `duration_below_threshold` reason no longer exists — deliberate contract change of fix C superseding PR2B-JD round-2 semantics; a pre-cached `request._body` skips the streaming bound, unreachable in this router because the parse dependency is the first body consumer.
- No new BLOCKER/CRITICAL finding was found on fix-touched lines.

**PR2B PRE-PR full-4R fix round 1 scoped re-review:** PASS — all ten candidates verified.

## PR 3B — Full-4R (pre-PR, >400 lines)

**Target:** `feat/lluvia-v2-03b-ficha-ui` vs `feat/lluvia-v2` (12 files, 1533 insertions; frontend-only)
**Review:** Full-4R (risk, resilience, readability, reliability) — first pass
**Date:** 2026-08-07
**Artifact store:** hybrid

### Lens ledgers (merged)

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| RISK-3B-001 | risk | (all rainfall endpoints) | — | open | Empty ledger — no findings. Server-side role enforcement verified at router level (require_operator on all endpoints); bearer confined to Authorization header, never URL; React default escaping only (no raw HTML sinks); ORM parameterization; no hardcoded secrets. |
| RESILIENCE-001 | resilience | `consorcio-web/src/hooks/useRainfallAnalysis.ts:79` | CRITICAL | open | 202-queued polling unbounded: `refetchInterval` polls every 5 s forever while queued — no max poll count, no backoff, no terminal/timeout state. Server never exposes a terminal failure: `read_analysis` re-calls `queue_missing_analysis` when snapshot absent, and it matches only `status='pending'`, so a `failed` outbox row causes a NEW pending row on next poll. Every open staff ficha on missing analysis issues ~12 POST/min indefinitely; backend re-enqueues/re-fails in a closed loop; pending state can never resolve or fail. |
| RESILIENCE-002 | resilience | `gee-backend/app/domains/geo/rainfall/tasks.py:40` | CRITICAL | open | Ingest pipeline behind every queued (202) analysis is a stub: lambda throws `NotImplementedError('provider adapter not wired')`. ResilientAdapter retries it as transient (2 retries + sleeps) then raises AdapterError; process_outbox burns retries and marks row `failed` — but `failed` is never surfaced (RESILIENCE-001 re-enqueues and answers 202). `RainfallDetailPanel.tsx:164-174` therefore shows "Análisis en preparación…" permanently for terminally failed work; degraded backend state surfaces as misleading labelled-pending, never labelled-failure. |
| RESILIENCE-003 | resilience | `gee-backend/app/domains/geo/rainfall/tasks.py:97-113` | WARNING | info | process_outbox calls ingest synchronously per row; on failure ResilientAdapter sleeps inside the call (5 s + 10 s, plus up to 60 s timeout per attempt). MAX_OUTBOX_BATCH=50 → single failing batch can take ≥12.5 min while celery beat fires every 1 minute; no soft_time_limit/time_limit, no single-instance guard → overlapping runs pile up and can starve unrelated tasks. |
| RESILIENCE-004 | resilience | `gee-backend/app/domains/geo/rainfall/service.py:121-155` | WARNING | info | `queue_missing_analysis` does check-then-insert without IntegrityError handling; partial unique index means two concurrent requests for same scope/year race → loser raises IntegrityError → 500 instead of 202. On frontend, error stops polling entirely (retry:false), leaving user stuck on error text until year/scope change. |
| RESILIENCE-005 | resilience | `gee-backend/app/domains/geo/rainfall/tasks.py:96-113` | WARNING | info | Outbox failure path silent: broad `except Exception` writes error only to `row.last_error` — no logging, no metric, no alert on retry or terminal `failed` transition; permanently broken provider produces endless 202/fail/re-enqueue with zero production visibility. |
| READABILITY-3B-001 | readability | — | — | open | Empty ledger — lens agent returned empty response; orchestrator inline check found no critical vocabulary/state-label divergences vs spec or backend state vocabulary. |
| RELIABILITY-3B-001 | reliability | — | — | open | Empty ledger — lens agent returned empty response; orchestrator inline parity check passed: `MetricResult`/`Provenance` fields match backend schemas.py exactly; 202 queued body (`status/outbox_id/scope/year/labels`) matches `queue_missing_analysis`; snapshot fields defensive (optional). Behavioral risks are captured by RESILIENCE-001/002. |

### Refutation — full-4R (3 batched tasks: correctness, exploitability/impact, reproducibility)

| id | correctness | exploitability/impact | reproducibility | verdict | status |
|---|---|---|---|---|---|
| RESILIENCE-001 | stands | stands | stands | stands | open |
| RESILIENCE-002 | stands | refuted | stands | stands | open |

- RESILIENCE-001: 3/3 stands — unbounded 5 s polling, no stop condition, server never exposes terminal failure; verified line-accurate on the 3B branch; the 202 path is the DEFAULT state today (nothing writes RainfallAnalysisRevision; feature flags dead code, zero callers); impact is UX-critical (panel promises auto-resolution that is impossible), load negligible at 1-5 staff scale.
- RESILIENCE-002: 1/3 refuted (exploitability/impact) but survives (2-of-3 rule). Impact refuter: stub is PR 3A deferral outside this frontend diff; its user-facing consequence is subsumed by RESILIENCE-001's UI fix. Verdict stands → both enter the fix loop; the honest terminal-state fix for 001 covers 002's UI consequence; backend adapter wiring remains a tracked PR 3A deferral.

### Fix round 1

- Fix target: bound the 202 polling (max polls / timeout → terminal state), add honest failure/unavailable label + manual retry in RainfallDetailPanel, stop promising "se actualiza automáticamente" after give-up; update tests (RED→GREEN).
- Fix scope: frontend only (useRainfallAnalysis.ts, RainfallDetailPanel.tsx, tests). Backend stub (tasks.py:40) NOT touched — recorded deferral.
- Status: in-progress.

### Fix round 1 result — commit ce466a1

- Applied `ce466a1` `fix(rainfall): bounded 202 polling and honest terminal state (RESILIENCE-001/002)` (local, +276/−20, 4 files). TDD RED→GREEN: 6 new tests failed then passed; full suite 3630 passed, lint zero new warnings, clean vite build verified to /tmp/opencode/consorcio-web-build-3bfix (standard build blocked by pre-existing root-owned dist/ EACCES — pre-PR environment issue, not code).
- Budget mechanics: `RAINFALL_MAX_QUEUED_POLLS=12` (~60 s); counter advances only on successful queued responses; resets on scope/year change, retry(), and ready; `refetchInterval` returns false at exhaustion; `gaveUp` terminal state + Reintentar button; aria-live announces both states; queued→ready transition does not stick gaveUp.

### Scoped re-review (reliability lens, fresh context) — fix round 1 verdicts

- `RESILIENCE-001` — **verified**: polling now bounded on the queued path per contract; no budget carryover; gaveUp reachable and exact; queued→ready transition clean; deterministic tests.
- `RESILIENCE-002` — **verified** (UI side): terminal state honest; "Se actualiza automáticamente" not shown after give-up; aria-live announces terminal state; retry re-runs query.
- New findings on fix-touched lines:
  - `REREVIEW-001` (WARNING, info) — `useRainfallAnalysis.ts:113-116`: the 12-poll budget only advances on SUCCESSFUL queued responses; on persistent endpoint failure (5xx/network/auth), TanStack retains `data` ('queued') across error refetches and the interval callback re-evaluates → loop keeps polling every 5 s forever against the failing endpoint, hidden behind the isError+Reintentar block. reported once; severity floor: never re-reviewed, never blocks.
  - `REREVIEW-002` (SUGGESTION, info) — no test covers the poll failure path (error between polls); the only netted case for REREVIEW-001-close would need one.
  - `REREVIEW-003` (SUGGESTION, info) — `vitest.config.ts` lacks `forbidOnly`; CI runs `vitest run`; existing tests don't use `.only` (non-blocking; untouched lines).

### PR 3B Full-4R verdict

- Fix round 1: PASS for BLOCKER/CRITICAL candidates (RESILIENCE-001/002 verified via fresh-context scoped re-review). Residual WARNING/SUGGESTION findings reported once with status `info`, never re-reviewed, never blocking. No round 2 required.
- **PR 3B review: PASS — eligible for PR creation.** Deferred/known: provider adapter wiring (PR 3A), error-path polling budget hardening (REREVIEW-001 — optional future work), standard build blocked by stale root-owned consorcio-web/dist/ artifacts (environment).

### Round State

- WARNING/SUGGESTION (RESILIENCE-003/004/005) reported once with status `info`; never re-reviewed; never block.
- CRITICAL candidates RESILIENCE-001 and RESILIENCE-002 survived 3-lens refutation → enter fix → re-review loop (max 2 rounds).
- NOTE: RESILIENCE-002 cites backend code (`tasks.py` stub adapter) merged in PR 3A and NOT part of this PR 3B diff; the stub is a recorded PR 3A deferral (concrete provider adapters not wired). UI consequence (misleading labelled-pending on terminal failure) is in 3B scope.

## PR 3C — Full-4R (pre-PR, >400 lines)

**Target:** `feat/lluvia-v2-03c-phase4` vs `feat/lluvia-v2` (commits d0c1f0f + 0e01942; 11 files, 1080+/83-)
**Review:** Full-4R (risk, resilience, readability, reliability) — first pass
**Date:** 2026-08-07
**Artifact store:** hybrid

### Lens ledgers (merged)

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| RISK3C-001 | risk | `gee-backend/app/domains/geo/rainfall/tasks.py:167-195` | WARNING | info | Disable path starves the whole queue: gated rows stay pending with past next_attempt_at; beat re-selects them each minute (LIMIT 50, created_at ASC); a disabled role at FIFO head blocks all enabled roles forever and re-emits `outbox.gated` every sweep. |
| RISK3C-002 | risk | `docs/lluvia-v2-observability-workbook.md:97-99` vs `tasks.py:44-46`/`feature_flags.py` | WARNING | fixed | Workbook §4 rollback instructed "remove the key — strict default false" but `_role_enabled` treats an absent setting as OPEN (True), so the documented rollback would re-enable all roles. **Fixed in commit `ae2230b`**: workbook §4 now mandates setting a COMPLETE blob with every role explicitly `false` (omit nothing) and explicitly forbids removing the key; §3 states the unset semantics (absent setting = OPEN; configured blob = only listed `true` run; omitted role in a configured blob = false). Doc-only alignment — backend semantics unchanged. |
| RELI3C-001 | reliability | `docs/lluvia-v2-observability-workbook.md:68-73` | WARNING | fixed | Workbook §3 canonical blob had a non-existent role `data` and silently gated `daily` off. **Fixed in commit `ae2230b`**: §3 canonical blob now lists the exact role set (`historical`, `daily`, `intensity`, `validation`) with every role explicit (three `true`, one explicit `false` demo), consistent with the unset/configured semantics of Fix RISK3C-002. |
| RELI3C-003 | reliability | `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts:320-324` | WARNING | fixed | Scope-switch test waited on any analysisRequest (`length > 0`) and asserted the last one, letting the default zone POST satisfy the poll before the basin POST arrived. **Fixed in commit `ae2230b`**: `expect.poll` now waits until a RECORDED request carries `scope.kind === 'basin'` and asserts its id (`b-carcara-01`); also fixed the test-title typo `reconsultaa` → `reconsulta` on a touched line. |
| RELI3C-004 | reliability | `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts:305` | WARNING | fixed | E2E hardcoded `Año 2026` while the snapshot year comes from `new Date().getFullYear()`. **Fixed in commit `ae2230b`**: the expectation now derives the year the same way (``const currentYear = new Date().getFullYear()``, asserting `Año ${currentYear}`); CSV/interval date strings in the fixture are inert (never asserted) and left unchanged. Breaks on 2027-01-01 no longer possible. |
| RELI3C-005 | reliability | `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts:116-139, 342-366` | WARNING | fixed | "CSV parity" never asserted snapshot↔CSV equivalence (fixture encoded 98.2 vs 96.2 drift and only compared bytes to a static constant). **Fixed in commit `ae2230b`**: snapshot mock and CSV body now derive from a single `SNAPSHOT_METRICS` constant (single source of truth — 98.2/96.2 drift is structurally impossible); the download-bytes assertions were derived from the same constant AND extended with explicit parity assertions that the CSV contains the values the UI displays from the snapshot (`98.2`, `123.4`). No assertion weakened. |
| READ3C-001 / R2C-004 | readability | workbook §4 vs `tasks.py` `_role_enabled` | WARNING | info | Same as RISK3C-002 (rollback doc contradicting absent-key semantics). |
| READ3C-003 / R2C-005 | readability | `router.py` export vs workbook §2.2 | WARNING | info | `rainfall.csv.served` emits hard-coded `latency_ms=0`, a fabricated measurement; events from `_process_outbox_batch` never send `scope_version`/`labels` though catalogue promises them. |
| RES3C-001 | resilience | `tasks.py:185-195` | WARNING | info | Same mechanism as RISK3C-001: gated rows re-selected each beat, ≥50 gated rows starve enabled roles; re-emits gated events (up to ~72k/day) + settings SELECT per row per sweep — signal buried by noise. |
| RES3C-002 | resilience | `router.py:171-176` | WARNING | fixed | `latency_ms=0` hard-coded hides any real CSV rendering latency regression. **Fixed in commit `ae2230b`**: `export_analysis` now times the CSV rendering (`datetime.now()` before/after `metric_rows_csv(metric_rows(...))`, mirrors `read_analysis`) and emits the measured `latency_ms`; event name and fields unchanged. |
| READ3C-004 / R2C-006 | readability | workbook §1 cross-ref | SUGGESTION | info | Deliverables table links "Rollback → §5" but the procedure is in §4. |

### Refutation

No BLOCKER/CRITICAL candidates → no refutation fan-out (protocol: refutation evaluates only BLOCKER/CRITICAL candidates; a candidate list that is empty spawns no refuter tasks). All findings are WARNING/SUGGESTION reported once with status `info`; per severity floor they never re-review and never block.

### Fix round (optional pre-PR hardening of cheap, high-value warnings)

- Selected: fix the doc↔code rollback contradiction (RISK3C-002/RELI3C-002/READ3C-002), the workbook role/blob bug (RELI3C-001), the hardcoded 2026 E2E (RELI3C-004), the flaky scope-switch polling wait (RELI3C-003), the unexecuted CSV-parity assertion (RELI3C-005), and the fabricated `latency_ms=0` (RES3C-002/READ3C-002). Opting out (documented): gated-row starvation mechanism (RISK3C-001/RES3C-001) — logic is correct for the flag-retention contract, impact only materializes once the provider adapter is wired (PR 3A deferral); recorded as open in workbook §5.

### Fix round 1 result — commit ae2230b

- Applied `ae2230b` `fix(rainfall): hardening from full-4R review (rollback doc, e2e determinism, csv parity, latency)` (local, 4 files: workbook `docs/lluvia-v2-observability-workbook.md`, `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts`, `gee-backend/app/domains/geo/rainfall/router.py`, this ledger). No push, no PR.
- RISK3C-002 + RELI3C-001: workbook §3 canonical blob now lists the real four roles and §4 rollback mandates a complete all-false blob (never remove the key — absent = OPEN). Doc-only; backend flag semantics untouched.
- RELI3C-003: scope-switch E2E polls for a recorded request with `scope.kind === 'basin'` before asserting (plus `reconsultaa` → `reconsulta` in a touched title).
- RELI3C-004: `Año ${new Date().getFullYear()}` replaces hardcoded `Año 2026`; fixture date strings left inert.
- RELI3C-005: snapshot and CSV derive from one `SNAPSHOT_METRICS` constant; the parity test asserts the download bytes contain the UI-displayed values (98.2 / 123.4).
- RES3C-002: `export_analysis` emits measured CSV-rendering `latency_ms` instead of hard-coded 0.
- Verification: vitest (consorcio-web `npm run test`) all passed; Playwright `--list` enumerates the 7 rainfall tests (data-gate skips expected); `pytest tests/new/geo/rainfall -q` passed; Ruff check/format on `router.py` passed; `npx tsc --noEmit` clean.
- Unfixed (unchanged statuses by design): gated-row starvation RISK3C-001/RES3C-001 (deferred, no behavior change), READ3C-001/R2C-004 (doc alias of RISK3C-002 — covered by the same fix), READ3C-003/R2C-005 (outbox event fields — outside scope), READ3C-004/R2C-006 (workbook §1 cross-ref, SUGGESTION, left for the owner).
- Ownership: single writer sub-agent, commit on top of the two 3C commits.
