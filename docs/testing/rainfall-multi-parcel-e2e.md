# Runbook — Rainfall Multi-Parcel E2E Harness

> Operator contract for the deterministic multi-parcel rainfall A→B→C→A E2E
> harness (change `rainfall-multi-parcel-e2e-harness`, RMEH-010/011/012).
> This is an OPTIONAL, operator-invoked harness — **it is NOT a required CI
> check on any PR**, and it is NOT part of the production canary's read-only
> allowlist. Read this before running it, diagnosing a failure, or rolling it
> back.

## Purpose

The harness proves the rainfall detail flow is deterministic across three real
parcels (A/B/C) and two form factors (mobile 390×844, desktop 1280×720), with
exactly one plain click per selection, zero helper/Playwright retries, and a
fail-closed 11/0/0/0 accounting gate. It provisions a fully disposable Docker
stack (Postgres+PostGIS, Redis, migrate, backend, Martin, frontend) owned by a
cryptographic run identity, seeds it from the committed fixture, and tears it
down to the exact recorded lease identity — even on failure or external kill.

## Prerequisites

- **Docker** with Compose v2 (the runner shells out to `docker compose`).
- **Python 3.11+** (the runner is a stdlib-only `python -m` driver).
- **Node 20/22 + npm** (Playwright run via `npx` from `consorcio-web/`).
- Lockfile deps installed: `npm ci` in `consorcio-web/` and a locked Chromium:
  `npx playwright install --with-deps chromium`.
- ~2–3 GB free disk/memory for the disposable stack.

No database credentials, no real secrets, and no admin account are required:
all DB/auth values are generated synthetic run values by the runner.

## One command (local)

```bash
# From the repo root (this is the SAME runner the GitHub workflow uses):
python3 -m scripts.rainfall_e2e_harness run
```

That single command does the whole owned lifecycle:

1. generates a fresh run identity + lease (never caller-supplied);
2. refuses any resource collision and any non-loopback port binding;
3. provisions the disposable compose stack (init script carves the ownership
   marker on the brand-new volume); the compose project prefix derives from the
   generated identity's `run_id[:10]` and is passed explicitly to every compose
   command — no env default, so `up`, the martin restart, and `down` always
   target the SAME project;
4. waits for backend liveness, then the read-only marker gate (the ONLY
   `OwnedBoundary` constructor — no mutation before it); the run/lease identity
   is recorded (`ownership.json`) BEFORE provisioning so a cancelled run can
   still be cleaned;
5. bootstraps migrations + geometry/soil seed + view provenance, validates
   Martin/backend/frontend services, and the Python parcel preflight;
6. runs the Playwright collection gate (exactly 11 tests) BEFORE any browser;
7. runs the browser journey (mobile + desktop A→B→C→A);
8. applies the exact 11/0/0/0 result gate + 8 one-click manifest gate;
9. on a **complete pass only**, emits `manifest.json` AND `jda-001-handoff.json`;
10. tears down the exact leased resources in a top-level `finally` (RMEH-012).

The exit code is `0` only on a complete `PASSED` pass; any failure class returns
non-zero but STILL cleans up the disposable resources.

## Statuses

The manifest records exactly one failure class (`manifest.json` →
`failure_class`), mutually exclusive (RMEH-009):

| Class | Meaning | Who acts |
|---|---|---|
| `PASSED` | Complete pass: 11/0/0/0, 8 one-click records, handoff emitted | — |
| `BOOTSTRAP_SAFETY_FAILURE` | Marker/collision/identity safety boundary refused before writes | Operator: re-run with a fresh identity; never adopt a shared DB |
| `BOOTSTRAP_PREREQUISITE_FAILURE` | Migration/geometry/Martin/backend/service prerequisite missing/incompatible | Operator: see "Diagnosing" |
| `HARNESS_ACCOUNTING_FAILURE` | Collection ≠ 11, result ≠ 11/0/0/0, manifest ≠ 8×1 click, or a soft skip | Operator: harness/spec drift — see "Diagnosing" |
| `BROWSER_INTEGRITY_FAILURE` | Pre-click camera/projection/occlusion/tile integrity failed or no click | Investigate projection/occlusion, not product behavior |
| `PRODUCT_ASSERTION_FAILURE` | Integrity passed + real click happened, but request/identity/continuity/freshness/scroll/geometry/focus failed | **Separate remediation decision** — see "JDA-001 boundary" |
| `CLEANUP_FAILURE` | A residual leased resource remained after teardown | Operator: exact-lease cleanup, then re-check |

## Reading the evidence

Every run writes into `.artifacts/rainfall-multi-parcel/<run-id>/`:

```text
.artifacts/rainfall-multi-parcel/<run-id>/
├── ownership.json            # run/lease identity + marker
├── events.jsonl              # append-only phase log (cancellation included)
├── bootstrap.json            # bootstrap report (seed digest, soil rows, SRID)
├── projection-mobile.json    # per-click projection/occlusion evidence
├── projection-desktop.json
├── request-trace.json        # per-selection request/identity/token trace
├── playwright-results.json   # JSON reporter (11 tests)
├── test-results/             # screenshots/trace only when produced
├── manifest.json             # final status, counts, digests, cleanup result
└── jda-001-handoff.json      # emitted ONLY on a complete pass
```

`manifest.json` carries the repository SHA, fixture digest, exact 11/0/0 counts,
8 one-click selection records, evidence SHA-256, failure class, and cleanup
result. The event stream is append-only and flushed after each phase, so a
cancellation still leaves an explanation.

## Diagnosing a failure

- **`HARNESS_ACCOUNTING_FAILURE`** — the collection/result gate is exact by
  design. If discovery ≠ 11, a spec was added/removed or a `.only` crept in; if
  the result ≠ 11/0/0/0, a soft skip or a retry slipped in. Fix the spec/accounting
  drift, never weaken the gate.
- **`BROWSER_INTEGRITY_FAILURE`** — read `projection-*.json` before anything
  else: a parcel target outside the visible body, an occluding element, or a
  projection drift fails here. This is NOT a product bug.
- **`PRODUCT_ASSERTION_FAILURE`** — the integrity gate passed and the click
  happened; the post-click request/identity/continuity/freshness/scroll/geometry/
  focus failed. Read `request-trace.json` for the exact request sequence and
  cache keys. This requests a **separate** remediation decision (below).
- **External kill / timeout** — re-run the idempotent cleanup command:

  ```bash
  python3 -m scripts.rainfall_e2e_harness cleanup --run-id <run_id>
  ```

  `cleanup` tears down exactly the recorded leased resources by immutable
  identity and is safe to re-run after an externally killed main process (the
  GitHub workflow calls it in an `if: always()` step for the same reason).
  `cleanup` first reads the run's `ownership.json` (recorded before
  provisioning) so it targets the exact project the run created; `--run-id` is
  only a fallback when no ownership record exists.

## Cleanup contract

The runner tears down the exact resources it created via its recorded lease
identity + cryptographic labels — never a prefix sweep, never the DB token,
never a global prune (RMEH-012). On success, teardown is a
`docker compose -f scripts/tests/rainfall-e2e.compose.yml down -v --remove-orphans`
plus per-resource reconciliation. Verify nothing leaked:

```bash
docker ps -a --filter name=rmeh-    # expect empty
docker volume ls --filter name=rmeh- # expect empty
```

## JDA-001 boundary (parent change)

The harness is the evidence-gathering side of JDA-001 (the parent
`lluvia-ux-tarjeta` change). It NEVER writes
`openspec/changes/lluvia-ux-tarjeta/review-ledger.md`, never updates an Engram
parent topic, never extends Judgment-Day rounds, and never declares the parent
approved. On a **complete pass** it emits `jda-001-handoff.json` carrying
`parent_record_mutated: false` and the proposed action:

> open a separate follow-up review transaction for JDA-001

A `PRODUCT_ASSERTION_FAILURE` emits evidence that requests a separate
remediation decision; this change stays test-only. Evaluate a passing handoff in
a separate JDA-001 review transaction — never by editing the parent's ledger.

## Rollback

Rolling back this harness removes ONLY the 13 file-architecture artifacts plus
the 2 test-config enrolments (the change's full delta). It requires **no**
database downgrade, **no** shared cleanup, **no** parent-artifact rewrite, and
**no** production/schema/behavior rollback (RMEH-012-D).

```bash
# Remove the harness's created files + revert the two enrolments, e.g.:
git rm \
  consorcio-web/tests/e2e/fixtures/rainfall-multi-parcel.fixture.json \
  consorcio-web/tests/e2e/helpers/rainfallMultiParcelHarness.ts \
  consorcio-web/tests/unit/rainfallMultiParcelHarness.test.ts \
  consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts \
  consorcio-web/tests/e2e/playwright.rainfall-harness.config.ts \
  consorcio-web/tsconfig.tests.json consorcio-web/package.json \
  scripts/rainfall_e2e_harness.py scripts/tests/test_rainfall_e2e_harness.py \
  scripts/tests/rainfall-e2e.compose.yml \
  scripts/tests/fixtures/martin-rainfall-e2e.yaml \
  docs/testing/rainfall-multi-parcel-e2e.md \
  .github/workflows/rainfall-multi-parcel-e2e.yml
git checkout -- consorcio-web/tsconfig.tests.json consorcio-web/package.json
```

Any residual disposable resource is cleaned only through its exact recorded
lease identity + immutable labels BEFORE removing the runner (see Cleanup
contract).

## Not a required CI check

This workflow is `workflow_dispatch`-only, serialized (`cancel-in-progress:
false`), runs with `contents: read` and no secrets, and is NOT referenced by the
required `Frontend`/`Backend`/`Deploy` gates nor by the production canary's
three-spec read-only allowlist. It cannot become a PR-required check unless
branch protection is separately and explicitly changed, which is outside this
change (RMEH-010-B, RMEH-014-A).
