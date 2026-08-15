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
