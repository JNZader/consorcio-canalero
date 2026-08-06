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
