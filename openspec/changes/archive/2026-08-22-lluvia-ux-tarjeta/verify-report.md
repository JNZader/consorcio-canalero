# Verify report — `lluvia-ux-tarjeta`

**Verdict: PASS-with-notes.**
Date: 2026-08-12 · Branch: `feat/lluvia-ux-02-disclosure` (stacked on `feat/lluvia-ux-01-jerarquia`)
Artifact store: hybrid (this file + `review-ledger.md` + Engram topic `sdd/lluvia-ux-tarjeta/apply-progress`)

> **Provenance of this file.** The verify pass was executed by a READ-ONLY agent, which could
> not write to disk and could not run a build in its sandbox. This file was written by the
> single writer that closed the findings, from that agent's report, with its findings table,
> executed-evidence table and owner runway kept intact. The one figure the read-only pass
> could not produce — the bundle — was MEASURED here and is marked as such. Nothing was
> carried over as an assertion where a run was available.

---

## 1. Verdict in one paragraph

The code is verified. The 3810-test figure the apply record claims reproduces digit-for-digit,
all 26 delta-spec scenarios trace to a named test, the review ledger closes with zero open
findings across four review rounds (full-4R slice 1, full-4R slice 2, two Judgment Days), and
the commit hygiene is clean — 26 commits, zero AI attribution, `consorcio-web/public/version.json`
in no commit. **What the verify phase found was the RECORD, not the code**: nine of its ten
findings are figures in the artifacts that disagree with the runs that produced them. That is
not filed as trivia. This change's entire argument is that a measured number beats an asserted
one — an apply record whose own arithmetic drifts is the same failure class one level up. All
nine are now corrected against the run, never against the other document. The tenth, V-001, is
a gate that has never been executed, and it stays open.

## 2. Executed evidence

Every row below was RUN in this phase on the branch head. Nothing is inherited.

| gate | command | result |
|---|---|---|
| unit suite | `npx vitest run` (full) | **279 files / 3810 tests passed**, exit 0 |
| typecheck | `npm run typecheck` | exit 0 (both tsconfigs) |
| lint | `npm run lint` | exit 0, **3 warnings**, all pre-existing, none added |
| e2e collection | `npx playwright test -c tests/e2e/playwright.config.ts --list` | **89 tests in 10 files**; **10** in `rainfall-v2-detail.spec.ts`, the zero-scroll case included. COLLECTED, NOT EXECUTED |
| bundle (D12) | `rm -rf dist` → `npm run build` → `find dist/assets -name '*.js' -exec sh -c 'gzip -9 -c "$1" \| wc -c' _ {} \; \| paste -sd+ - \| bc` | **910207** vs slice-2 base `908422` → **+1785 against the 3072 budget — PASS**, 1287 B headroom. **Reproduced the recorded figure byte for byte.** |
| hygiene | `git log` over the 26 commits; `git log --stat` grep for `version.json` | no `Claude-Session`, no `Co-Authored-By`, no `Generated with`; `version.json` in no commit |

**Method trap, recorded so the next person does not misread it:** `npx playwright test --list`
WITHOUT `-c tests/e2e/playwright.config.ts` collects **zero** tests and exits 1 — from
`consorcio-web/` it sweeps the vitest suites too and dies on `vi.mock` outside a vitest runner.
The bare invocation looks like a broken e2e suite and is not one.

## 3. Findings

| id | severity | status | summary |
|---|---|---|---|
| V-001 | CRITICAL | **OPEN** | The declared local e2e run (task O.1 / design D13) has never been executed; the zero-scroll criterion is asserted by nobody |
| V-002 | WARNING | closed | `36/36` recorded for `RainfallAnswerCard.test.tsx`; measured 35 |
| V-003 | WARNING | closed | Task O.2 unchecked pending an owner decision that had already been made |
| V-004 | WARNING | closed | Bundle unmeasured by the read-only pass — measured here, reproduces |
| V-005 | WARNING | closed | Slice-2 head test count 3807 vs the ledger's 3806 |
| V-006 | WARNING | closed | The three pre-existing lint warnings mis-attributed |
| V-007 | WARNING | closed | `design.md:385` still said NINE hoisted fields after the eight-field amendment |
| V-008 | WARNING | closed | Delta-spec preamble cited base spec `:596`; the requirement is at `:607` (bequest UXJA-206) |
| V-009 | WARNING | closed | UXJA-201, the sole open item at budget end, resolved in prose with no ledger row |
| V-010 | SUGGESTION | closed | `version.json` confirmed out of every commit, this one included |

Full evidence for each row is in `review-ledger.md`, section **"Verify phase (2026-08-12)"`.
The nine closed rows were closed by the commit that carries this file.

### V-001 in full — the one that stays open

The case EXISTS and COLLECTS (10 tests in the spec, the zero-scroll case among them), which is
the only thing any record in this change claims. It has never RUN. All three blocking
preconditions were re-verified live in this phase rather than inherited from the design:

1. `gee-backend/app/config.py:124` — `ficha_enabled: bool = False`.
2. `rg FICHA_ENABLED` over the tree returns NOTHING outside `openspec/` — no compose file, no
   env file, no example sets it. Without it `probeFichaAvailability` returns `'off'` and every
   test in the spec soft-skips.
3. `docker-compose.yml:345-351` — the `martin` service publishes **no host port**, by
   deliberate design (its own comment: host 3000 is taken by another stack on this box), while
   the SPA resolves tiles from `VITE_MARTIN_URL || 'http://localhost:3000'`. Without a route,
   `clickFixtureParcela` never gets its `parcelas_catastro` 200 and the zero-scroll case skips.

**A skipped run is a failed gate, not a pass.** Archiving with V-001 closed would record a
zero-scroll criterion that no run has ever asserted — the third repetition of this gate's own
three-strikes history (canary → preview → local). It is owner-gated and not agent-closable.

## 4. Owner runway

What the owner has to do, in order:

1. **Execute O.1**, satisfying all five D13 preconditions — the three above plus `E2E_API_BASE`
   and `E2E_APP_URL`:

   ```
   FICHA_ENABLED=true docker compose up -d postgres backend
   docker compose up -d martin   # + a host route for 3000, or VITE_MARTIN_URL
   npm --prefix consorcio-web run dev
   E2E_APP_URL=http://localhost:5173 E2E_API_BASE=http://localhost:8000 npm --prefix consorcio-web run test:e2e:rainfall
   ```

   Acceptance: every test in the describe **RUNS** (not skips), the zero-scroll case among
   them. Then check O.1 and close V-001.
2. **Push** — every commit on both branches after `ead8c6dd` is LOCAL. The worktree's pre-push
   hook is broken and `--no-verify` was deliberately not used, so the push wants a full
   environment where Docker CI can run.
3. **Archive** — and if V-001 is still open at that point, record IN the archive that the
   zero-scroll criterion ships unasserted. Do not let it archive silently.

## 5. Non-blocking bequest carried forward

Recorded in `review-ledger.md`, none blocking, all `info`:

- `S2R3-005` — `lib/api/rainfall.ts:69` declares `provenance` REQUIRED while the backend serves
  stripped shapes without it; every test constructing that state needs an
  `as unknown as RainfallMetric` cast. A truthful `provenance?:` forces an audit of every
  reader of `.provenance` — which is the audit the current type is suppressing.
- `UXJA2R-002` — `coverage_below_threshold` is English snake_case in Spanish copy. Correct
  scope for the fix is ONE `RAINFALL_REASON_LABELS` inside `describeMetricState`, which fixes
  the card, the panel row and the aria-labels in a single edit.
- `UXJA2-002` / `UXJA2-003` / `UXJB2-001` / `UXJB2-002` / `UXJB2-003` / `UXJA2R-004` /
  `S2RR-001..004` — assessed real or theoretical, each with its evidence and its reason for not
  entering the fix loop.
