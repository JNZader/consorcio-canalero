# Archive Report — lluvia-ux-tarjeta

**Archived**: 2026-08-22
**Archived to**: `openspec/changes/archive/2026-08-22-lluvia-ux-tarjeta/`
**Artifact store**: hybrid (OpenSpec files + Engram topics)
**Status at close**: complete — delivered, verified, and merged to `main`.

## 1. Final state

| Fact | Value | Source |
|---|---|---|
| Tasks | 46 checked / 0 unchecked in the archived `tasks.md` | persisted tasks artifact (rank 2) |
| Verify verdict | PASS-with-notes (2026-08-12) | `verify-report.md`, Engram obs #14815 |
| Open findings at close | **none** — V-001 closed 2026-08-22 (see §2) | executed E2E evidence + launch-prompt final-state facts (rank 3) |
| Delivery | squash-merged to `main` as `5e4c56a0` via PR #206, `fix(rainfall): per-parcel cache freshness and desktop card click-through`, merged 2026-08-22T15:04:31Z | repository (`git log`) |
| Review gate | `reviewGate` structurally ABSENT — receipt-driven development kill switch is OFF for this repository, so no review lifecycle ever ran for this candidate. Archive proceeds under ordinary repository policy. | Native Review Receipt Gate |

## 2. V-001 is CLOSED (supersedes the verify-report snapshot)

Per `verify-report.md` (2026-08-12), finding **V-001 (CRITICAL)** was OPEN: the declared local
E2E run (task O.1 / design D13) had never been EXECUTED, so the zero-scroll criterion was
asserted by nobody. That is an intermediate snapshot and describes 2026-08-12 only.

**On 2026-08-22 the gate was executed against a live stack on the integrated head and passed.**
Sealed evidence, verified in this archive phase directly from the artifact bundle rather than
taken on assertion:

- Evidence bundle: `.artifacts/rainfall-multi-parcel/` (`manifest.json`, `playwright-results.json`,
  `events.jsonl`, `ownership.json`, `jda-001-handoff.json`)
- `manifest.json`: `failure_class: PASSED`, `counts` = **11 passed / 0 failed / 0 skipped**
- `playwright-results.json` stats: `expected: 11`, `unexpected: 0`, `flaky: 0`, `skipped: 0`
- `evidence_sha256`: `ff30ebb6d56c878ed59a5e90600f7d1364b20d8f76634c4b7add470f9671f680`
- `repo_sha`: `bd6fe3e5e2bc88eee32a971fdf4c3e7b62bcfd37`
- `run_id`: `ff6f72a92ba5d2c0487b04153d799ea9`, `compose_project`: `rmeh-ff6f72a92b`
- `selection_records` cover the full `A→B→C→A` journey in both `mobile` and `desktop` contexts,
  every transition at `attemptCount: 1` (no retries)

The verify-report's owner-runway instruction — "if V-001 is still open at that point, record IN
the archive that the zero-scroll criterion ships unasserted" — does **not** apply: the criterion
is asserted by an executed run. It ships measured, not declared.

## 3. Accessibility spec-lag fix (a11y fade harness)

Commit `61bdc090` — `test(a11y): mount the card fade harness on .panelCardBody` — fixed the
`consorcio-web/tests/accessibility/mapPanelFade.spec.ts` harness. The 16 a11y-matrix failures
were **spec-lag, not a product regression**: the harness mounted the desktop card as a single
scroll box on the panel root, but the R3-001 `pointer-events` refactor (sibling change
`rainfall-analysis-cache-freshness`) moved scroll and the `::after` fade to `.panelCardBody`, so
the harness' background poll never converged and timed out. The fix's protective intent was
verified by mutation; the full a11y matrix then passed **88/88**.

`61bdc090` is not an ancestor of `main` because PR #206 was squash-merged, but its content is in
`main`: `git diff 61bdc090 HEAD -- consorcio-web/tests/accessibility/mapPanelFade.spec.ts` is
empty, and `5e4c56a0` carries the same `mapPanelFade.spec.ts` and
`mapPanelFadeClearance.test.ts` changes.

## 4. Verify-phase figures (attributed, per `verify-report.md` 2026-08-12)

At verification time, the read/measured evidence was: the 3810-test figure claimed by the apply
record reproduced digit-for-digit; all 26 delta-spec scenarios traced to a named test; the review
ledger closed with zero open findings across four review rounds (full-4R slice 1, full-4R slice 2,
two Judgment Days); commit hygiene clean over 26 commits (no `Claude-Session`, no
`Co-Authored-By`, no `Generated with`, `version.json` in no commit); bundle 910207 B gz vs the
slice-2 base 908422 B → +1785 B against the 3072 B budget (PASS, 1287 B headroom). Findings
V-002…V-010 were closed by the commit that carried the verify report.

## 5. Specs synced

| Domain | Action | Details |
|---|---|---|
| `rainfall-analysis` | Updated | 2 MODIFIED requirements replaced, 3 ADDED requirements appended |

- MODIFIED → `Metric Provenance and State Metadata` (enumerated rendering floor, one-disclosure
  reachability, consolidation for homogeneous sets, suppression ≠ absence of evidence; 6 new
  scenarios, 1 scenario rewritten)
- MODIFIED → `Authenticated Technical Rainfall Detail` (public normal readable with no disclosure
  control operated; 1 new scenario)
- ADDED → `Answer-First Rainfall Presentation Hierarchy`
- ADDED → `Derived Interpretive Rainfall Label`
- ADDED → `Progressive Disclosure Without Data Loss`

Every requirement not named by the delta was preserved verbatim. Requirement blocks were spliced
byte-for-byte from the delta file by script; no spec content was retyped.

Source of truth: `openspec/specs/rainfall-analysis/spec.md`.

## 6. Engram observation IDs (traceability)

| Artifact | Topic | Observation |
|---|---|---|
| proposal | `sdd/lluvia-ux-tarjeta/proposal` | `#13730` |
| spec (delta) | `sdd/lluvia-ux-tarjeta/spec` | `#13731` |
| design | `sdd/lluvia-ux-tarjeta/design` | `#13738` |
| tasks | `sdd/lluvia-ux-tarjeta/tasks` | `#13872` |
| apply-progress | `sdd/lluvia-ux-tarjeta/apply-progress` | `#14779` |
| verify-report | `sdd/lluvia-ux-tarjeta/verify-report` | `#14815` |
| a11y fade fix | (bugfix) `Fix a11y fade spec: spec-lag del refactor R3-001` | `#18184` |
| archive-report | `sdd/lluvia-ux-tarjeta/archive-report` | this file (saved on archive) |

Retrieval note: the Engram MCP tools (`mem_search` / `mem_get_observation`) were not exposed in
this executor context. Observation IDs were resolved with the `engram` CLI (`engram search`), and
full artifact bodies were read from their on-disk hybrid mirrors in this change folder, which are
the same artifacts.

## 7. Archive verification

- `diff -r` (pre-move `cp -R` snapshot vs. archived folder): **empty, exit 0** — byte-identical.
- Active changes directory no longer contains `lluvia-ux-tarjeta`.
- Archived folder contains: `proposal.md`, `design.md`, `tasks.md`, `specs/rainfall-analysis/spec.md`,
  `apply-progress.md`, `review-ledger.md`, `verify-report.md`, and this report (additive).
- Archived `tasks.md`: 0 unchecked implementation tasks.
