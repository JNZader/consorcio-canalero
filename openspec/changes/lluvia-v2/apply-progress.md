# Apply Progress: Lluvia v2 — PR 1 Evidence Foundation

## Branch strategy
- Feature-branch chain: `feat/lluvia-v2-01-evidence-foundation` targets tracker `feat/lluvia-v2`.
- Scope is tasks 1.1–1.4 only. No provider is validated or enabled.

## Completed tasks
- [x] 1.1 Adapter-contract evidence tests cover failed criterion, scrape rejection, no-blending fallback, immutable model contract, and approval fixture.
- [x] 1.2 Canonical models, ports, schemas, policy, manifests, Alembic registration, and migration added.
- [x] 1.3 Versioned disabled manifests and pending approval/audit fixture added.
- [x] 1.4 Immutable interval/revision uniqueness, lookup/retention indexes, two-year retention field, backfill checkpoint, and no raw-payload model contract added.

## TDD evidence
| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 1.1–1.4 | 4 focused tests failed with missing rainfall module | 7 focused evidence-contract tests pass after the approved Round 1 fixes | Ruff formatting and lint cleanup pass |

## Verification
- `venv/bin/python -m alembic heads` → `lluvia_v2_001 (head)`
- `venv/bin/pytest tests/new/geo/rainfall/test_evidence_foundation.py --confcutdir=.` → 7 passed
- `venv/bin/ruff check app/domains/geo/rainfall tests/new/geo/rainfall app/db/migrations/versions/lluvia_v2_001_evidence_foundation.py` → passed
- `venv/bin/python -m compileall -q app/domains/geo/rainfall app/db/migrations/versions/lluvia_v2_001_evidence_foundation.py` → passed

## Judgment Day Round 1 fix evidence
- PR1-JD-001: Migration includes eligibility `created_at` and nullable checkpoint `completed_at`; model/schema alignment is tested by migration/import checks.
- PR1-JD-002: `MetricResult` requires and bounds coverage/completeness, requires quality/discrepancies, and forbids unknown inputs.
- PR1-JD-003: Selection now requires a manifest that is enabled and has the policy role in addition to evidence eligibility; it still chooses one deterministic ladder member.
- PR1-JD-004: ORM `before_flush` rejects interval/revision updates and deletes; the migration adds reversible PostgreSQL triggers for direct SQL writes.
- PR1-JD-005: `SourceBatch`/`SourceInterval` are typed and validate UTC half-open cadence, units, revisions, coverage/completeness, discrepancies, checksum, and deterministic known-event fixture values. All provider manifests remain disabled.
- PR1-JD-006: Checkpoint identity and migration uniqueness include `scope_kind` and `scope_version`.
- Hardening validation: a disposable Testcontainers `pgrouting/pgrouting:16-3.4-3.6.1` PostgreSQL instance completed `alembic upgrade head` and downgrade to `0020_add_canal_consorcio`; the four rainfall tables, two immutability triggers, function cleanup, and Alembic stamps were asserted. No production or persistent local database was touched.
- `gee-backend/.gitignore` now has one explicit exception for `tests/new/geo/rainfall/fixtures/approval-audit.json`, so the non-sensitive fixture is visible to Git without allowing other JSON files.

## Judgment Day terminal approval
- Both independent scoped re-judges approved `PR1-JD-001` through `PR1-JD-006`; all six findings are verified.
- `PR1-JD-007` and `PR1-JD-008` remain suspect/info; `PR1-JD-009` remains WARNING/info.
- **Judgment for Apply PR1: APPROVED.**
- The previous compose-only migration blocker is superseded by the successful disposable Testcontainers validation. The project compose command still requires root-level `REDIS_PASSWORD`; it was not used for this check.

## PR hardening readiness
- Focused rainfall tests: 7 passed; Ruff lint and formatting checks passed; Python compile check passed.
- The fixture is not ignored and appears in `git ls-files --others --exclude-standard`; no sensitive/unrelated candidate file was found by the staging-safety scan.
- Publication remains blocked pending a fresh pre-commit review and an approved GitHub issue: no rainfall/lluvia issue or open tracker PR exists, and no open `status:approved` issue is available.

## Pre-commit Round 1 fixes
- RISK-001: immutable interval facts now use append-only lifecycle records; a reversible PostgreSQL expiry-purge function is the sole controlled deletion path.
- RISK-002: source eligibility rows join ORM and database append-only enforcement.
- RISK-003: selection requires typed source/role/evidence-revision eligibility records.
- RISK-004: metric state/value/reason invariants are validated, preserving partial zero/null semantics.
- RISK-005: adapter batches and fetch requests carry scope kind and version.
- RED: 6 focused regressions failed; GREEN: 18 rainfall tests passed. Ruff, compileall, Alembic single head, and disposable pgrouting/PostGIS upgrade+downgrade passed.
- Scoped pre-commit re-review PASS verified RISK-001 through RISK-005 with no new fix-line BLOCKER/CRITICAL findings; pre-commit review-risk passed.

## Risks and rollback
- Provider access/licence and scientific evidence remain pending; manifests stay disabled.
- Rollback: disable/remove the PR-1 migration and domain foundation; no provider data or raw payloads were persisted.

## Remaining tasks
- [ ] 2.1–4.3

## Pre-push Round 1 fixes
- PUSH-RISK-001..003 fixed pending scoped re-review; durable expiry facts authorize deletion, manifest identity is bound, and non-finite numbers are rejected.
- PUSH-RISK-004 resolved by maintainer convention: 400 behavioral production + 2 package docstrings; tests 330; migrations 167; OpenSpec 666; config 1; no size exception required.

- Migration harness initially failed because REVOKE preceded function creation; removed only premature REVOKE. Disposable pgrouting/PostGIS upgrade-head/downgrade-0020 then passed.
- PUSH-RISK-002 Round 2 removed authoritative defaults; exact manifest identity is mandatory. Focused suite: 19 passed.
- Pre-push scoped re-reviews verified PUSH-RISK-001..003; PUSH-RISK-004 remains resolved under maintainer code-only budget convention; pre-push review-risk passed.

## Pre-push harness incident
- Linked permanent bug #164. Push blocked: Node runner lacks Docker/Make/Python and compile masks exit 127; no-verify only after equivalent full checks pass on exact HEAD without later code commits.

## Backend gate invocation reliability incident
- REL-001 (WARNING/info): the subprocess contract test is cwd-sensitive; a repository-root invocation causes `ModuleNotFoundError`, while running from `gee-backend/` passes.
- REL-002 (WARNING/info): local `Makefile` / `scripts/test-local.sh` impose 70% coverage, which drifts from the authoritative CI/package 60% threshold.
- The earlier repository-root result is invalid full-gate evidence. Authoritative command, from `gee-backend/`:
  `./venv/bin/python -m pytest tests/new/ --cov=app --cov-config=.coveragerc --cov-report=term --cov-fail-under=60 -q --no-header --tb=short`.
- Linked #164 for the permanent pre-push harness and compile-wrapper correction.


## PR 2 deterministic scope and temporal progress (partial)
- Branch: `feat/lluvia-v2-02-backend-api`, based exactly on PR1 `277c7cc2588c40b60dd8e0ac46ecef67ea47a218`.
- [x] 2.1 RED: focused unit and real PostGIS tests cover stable identities, parcel zone/basin choices, regional labels, ambiguity/no-match, full-tuple selection, direct parcel/geometry rejection, boundary-only exclusion, inactive-zoning exclusion, missing stable IDs, malformed configuration fail-closed behavior.
- [x] 2.2 GREEN: `scope.py`, PostGIS JSON-lateral `repository.py`, and pure temporal helpers implement Buenos Aires conversion, leap-only Feb-29 baseline dates, same-date calendar comparison, cross-year antecedents, cadence-complete rolling totals, and deterministic event peak/duration suppression.
- TDD evidence: RED missing modules, kind-only selection, missing cadence coverage, missing provenance serialization, an ambiguous production SQL column, and missing local-date helpers; GREEN 30 non-DB focused rainfall tests plus 3 real-PostgreSQL resolver tests pass.
- API groundwork is uncommitted: authenticated router, snapshot reads, JSON/CSV parity serializer, and unauthenticated/CSRF/content-type focused contract tests. Task 2.4 remains unchecked pending revision, disclosure, and rate-limit coverage; 2.3 and 2.5 remain pending.
- Production behavior: 340 lines (338 new rainfall modules plus 2 Geo-router registration lines); tests/docs excluded.

## Approved delivery boundary after PR 2A critical cycle

The earlier PR 2 progress above remains historical evidence. The approved feature-branch chain now has four slices:

| Slice | Boundary | Status |
|---|---|---|
| PR 1 | Evidence gate, contracts and migration | Complete |
| PR 2A | Deterministic scope, PostGIS resolution, temporal rules and API groundwork | Current; tasks 2.1–2.2 complete at 400 production lines |
| PR 2B | API policy contract | Planned; tasks 2.3–2.4 remain unchecked |
| PR 3 | UI, export and operations | Planned; task 2.5 and phases 3–4 remain unchecked |

### PR 2A boundary evidence

- The user-approved convention counts production behavioral code only and caps each slice at 400 lines; tests, fixtures, migrations, documentation, generated files, package docstrings and operational configuration are excluded.
- PR 2A is frozen at exactly 400 raw production lines.
- Verification: 55 focused Rainfall tests passed; focused Ruff checks and the diff consistency check passed.
- The model-diverse critical review/fix cycle approved the PR 2A boundary.
- Only tasks 2.1–2.2 are complete; tasks 2.3–2.5 remain unchecked.


## PR 2B API policy contract progress
- Branch: `feat/lluvia-v2-02b-api-policy-contract`, based exactly on PR2A `d6d6b2914a95b0360b4004c1cc2745e6f0d3965a`.
- [x] 2.3: Added the versioned `MetricThresholdPolicy` evaluator with per-metric coverage, completeness, quality, and duration gates. Missing policy thresholds fail closed; `None` remains unavailable while a numeric `0.0` remains available; a failed metric does not affect independent metrics.
- [x] 2.4: Hardened authenticated snapshot routes with bounded JSON content, explicit request field limits, existing admin/operator authorization, existing CSRF middleware, global rate limiting, and the existing shared metric-row JSON/CSV provenance/state contract. Authorization denial continues to return no snapshot or CSV values.

### TDD evidence
| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 2.3–2.4 | Four focused tests failed: missing threshold-policy symbols, absent body limit, and empty policy revision accepted. | 15 API-contract tests passed after implementation; complete rainfall suite passed (70). | Ruff format/check passed for modified policy, router, and tests. |

### Verification
- `cd gee-backend && ./venv/bin/python -m pytest tests/new/geo/rainfall -q --no-header --tb=short` → 70 passed.
- `cd gee-backend && ./venv/bin/python -m pytest tests/new/test_auth_refresh_http.py -q --no-header --tb=short` → 2 passed.
- `cd gee-backend && ./venv/bin/python -m ruff check app/domains/geo/rainfall/policy.py app/domains/geo/rainfall/router.py tests/new/geo/rainfall/test_backend_api.py` → passed.
- `git diff --check d6d6b2914a95b0360b4004c1cc2745e6f0d3965a` → passed.
- PR2B production raw numstat relative to the PR2A base: `66 additions / 7 deletions` across `policy.py` and `router.py`; tests and OpenSpec artifacts excluded from the production budget.

## Remaining tasks
- [ ] 2.5–4.3
