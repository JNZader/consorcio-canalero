# Design: Lluvia Insights — Rainfall v2 Product Layer

## Technical Approach

Additive wiring over the shipped materialization pipeline. No new table, no migration, no
breaking route. Four seams move: (1) a **provider-asset-keyed baseline** in the existing
`rainfall_interval_value` store, (2) `build_snapshot` grows sibling metrics from intervals
handed to it by `tasks.py`, (3) a **series contract** served from the interval store — pinned
to the revision it claims to illustrate — feeds both the chart and the xlsx daily sheet,
(4) the frontend activates renderers that already exist. Boundary rule from the archived design holds: adapters own providers, `compute.py`
stays pure, `repository.py` owns SQL, `tasks.py` owns the Session.

## Architecture Decisions

### D1 — Baseline persistence keying (the load-bearing one)

Every zone id collapses to one asset (`adapters/gee_client.py:33-46`, `DEFAULT_ZONE_ASSET`
at :24), but intervals are keyed by `(source_id, scope_kind, scope_id, scope_version, …)`
(`models.py:48-59`) and read with that exact filter (`repository.py:213-246`).

| Option | Tradeoff |
|---|---|
| (a) One canonical **asset-level key**: `scope_kind="provider_asset"`, `scope_id=<asset>`, `scope_version="v1"`; zone→asset resolved at read time | 30 reductions total; zoning republication cannot orphan it (key carries no zoning version); read path needs one resolution call |
| (b) Duplicate baseline rows per zone key | Uniform reads, but N×30 GEE reductions, N×11k rows of **byte-identical numbers**, and re-backfill on every `scope_version` bump. Worse: it fabricates per-zone baselines the provider never produced |
| (c) New `rainfall_baseline_*` table | Migration + a second store with its own supersession/anti-join semantics to re-derive |

**Choice: (a).** Rejects (b) because scope_version churn would silently orphan 30 years of
evidence (`intervals_in_window` filters on it) and because differentiated storage of
undifferentiated data is misrepresentation, which this spec exists to prevent. Rejects (c)
because supersession, checkpoints and idempotency already exist here. `String(16)` fits
`provider_asset` (no CHECK constraint on `scope_kind` — `lluvia_v2_001:51`), and
`executable_scope` rejects any kind outside `zone|basin` (`scope.py:36-42`), so **the
baseline key is unreachable as a request scope** — storage only.

Read path: `tasks._persist_analysis_revision` resolves `asset_name_for(scope.kind, scope.id)`
(adapters own provider knowledge) and calls a new
`repository.baseline_cumulatives(db, *, source_id="chirps-v3-final", asset key, dates)` that
aggregates per-baseline-year cumulative-through-same-date **in SQL** (window `SUM` over the
same supersession anti-join), returning `{year: (total_mm, matched_days, expected_days)}`.
`compute.build_snapshot` receives that dict — it never touches SQL. A basin whose id has no
asset (`gee_client.py:42-45`, `repository.py:132` emits UUIDs) raises `UnknownProviderScope`;
`tasks.py` catches it and passes `baseline=None` → normal/percentile suppressed with reason
`baseline_scope_unmapped`. The pre-existing basin gap must not become a build crash.

### D2 — Backfill orchestration

Reuse `backfill_missing` verbatim (`tasks.py:947-972`): per-key checkpoint, `already_complete`
short-circuit, single transaction, `persist_intervals` append-only + `ON CONFLICT DO NOTHING`.
New thin orchestrator `tasks.backfill_baseline_range(asset, years=range(1991,2021))` loops
years, sleeps `RAINFALL_BACKFILL_PACE_SECONDS` (default 5) between years, emits
`record_event("rainfall.backfill.year", …)`, and **stops on `(AdapterError, CircuitOpen)`**
instead of burning quota against an open circuit.

**Both exception types, explicitly (Judgment Day round 1, LIA-004 — corrects an earlier
"stops on `AdapterError`" that would not actually stop cleanly).** `CircuitOpen` and
`AdapterError` are *sibling* `RuntimeError` subclasses (`resilience.py:25-30`), and
`ResilientAdapter.fetch` raises `CircuitOpen` from `state.can_attempt()`
(`resilience.py:80`, called at `resilience.py:262`) **before** the retry loop that converts
provider failures into `AdapterError` (`resilience.py:264-290`). So `CircuitOpen` never
passes through `ingest_source_scope`'s `except AdapterError` (`tasks.py:172-173`) and would
escape the orchestrator raw on exactly the realistic rerun. Catching bare `RuntimeError`
instead is rejected: too broad — it would relabel genuine bugs (a `RuntimeError` from the
session, from `_run_with_timeout`, or from Celery itself) as a clean "quota stop" and hide
them behind the operator message meant for a provider outage. The orchestrator catches the
two named classes, emits `record_event("rainfall.backfill.stopped", reason=…)` with
`adapter_error` / `circuit_open` as the reason, and returns a stop result instead of raising.

**Runbook consequence.** The circuit is Redis-backed and keyed by *role*
(`RedisCircuitStore`, `tasks.py:153-159`; "so separate workers see the same breaker",
`resilience.py:101-102`), and stays open for `recovery_seconds` (300s default,
`resilience.py:52`) **across processes** — a fresh `python -m …backfill_cli` inherits the
open breaker of the run that just failed. The runbook step therefore reads: on a labelled
stop, wait out the ~5-minute recovery window before rerunning; a rerun inside the window is
expected to stop again immediately with the same labelled event — never a raw traceback and
never a provider call. Operationally it is a one-shot module with
`__main__`, mirroring the existing hand-run ETL precedent
(`geo/etl/generate_chirps_normals.py`), not a Beat schedule — a 1991-2020 baseline is
computed once. Dedupe is structural: the key *is* the asset, so N zones cost 30 reductions,
not 30N. Re-run is idempotent by checkpoint; an interrupted run resumes at the first
year without `completed_at`. Precondition: `historical` role flag enabled
(`feature_flags.py:6-17`, `tasks._role_enabled`).

### D3 — Envelope, data_revision, and the chart's data

Metric groups already exist (`service.py:19`), root `summary` is already allow-listed
(`service.py:142-155`), `normalize_snapshot` iterates generically (`service.py:429-448`).
So the envelope grows `annual.{normal,percentile}` + `antecedents.{d7,d30,d90}` + root
`summary` with **zero structural change** to the metric machinery.

**Retraction (Judgment Day round 1, LIA-001+LIB-002).** This decision previously claimed
"and no new root key", while also promising the UI could "detect drift from the snapshot it
drew" from an echoed `data_revision`. Both cannot be true: `data_revision` is a *column* on
`rainfall_analysis_revision` (`models.py:96`, part of `uq_rainfall_analysis_snapshot`,
`models.py:86-92`) and is disclosed nowhere — it is absent from `SNAPSHOT_ROOT_KEYS`
(`service.py:142-155`), from `build_snapshot`'s returned envelope (`compute.py:176-189`) and
from the TS contract (`rainfall.ts:74-86`). The "no new root key" framing is **retracted**,
not silently rewritten: **one** new root key is added, `data_revision`, and the consistency
loop is closed at both ends — server-side pinning (authoritative) and the client echo
(cross-check).

**The `data_revision` hash does not move on its own** — it hashes source/family/scope/year/
comparison_end/intervals only (`compute.py:192-222`). For a key whose intervals and
comparison_end have not moved, `persist_revision` would hit `ON CONFLICT DO NOTHING` and the
enriched envelope would **never land** (`repository.py:385-398`). The
`RAINFALL_METRIC_POLICY_REVISION` bump is therefore load-bearing, not cosmetic: it is the
second of the three columns of `uq_rainfall_analysis_snapshot` (`models.py:86-92`), so
bumping it makes the enriched snapshot a distinct row rather than a discarded duplicate. Old rows stay self-consistent (the router passes the *row's*
`policy_revision`, `router.py:145-147`), so no migration and no backfill of snapshots.
Past-year keys already `done` are never revisited by either sweep, so `router.read_analysis`
gains: when the served snapshot's `metric_policy.revision` differs from the current constant,
serve it **and** enqueue a refresh labelled `policy_revision_stale`; `recent_done`'s cooldown
(`service.py:238-248`) bounds the resulting GEE cost. Rejected: a bulk requeue command
(unbounded fetches for keys nobody views) and doing nothing (stale envelope forever).

**Cooldown ladder amendment (slice 2b resilience round, LI2B-001 + LI2B-003).** The
sentence above — "`recent_done`'s cooldown bounds the resulting GEE cost" — was only true
for one of the three terminal states a key's own outbox history can be in, and the code
matched the sentence rather than the intent. A key whose newest row is terminal `failed`
matched neither `recent_done` (it has no `completed_at`) nor the `pending` pre-check, so
every poll started a fresh `MAX_RETRIES` cycle; for a *deterministic* compute-time failure
that never terminates, because ingest succeeds and the adapter's circuit breaker therefore
never trips — each attempt is a real full-year GEE fetch. A key whose newest row is `done`
but whose build **refused to write** (`latched`/`gate_refused`, `compute.revision_write_decision`)
was equally unbounded in a different way: it stayed permanently stale *and* was re-enqueued
every 10 minutes forever, with no progress possible until upstream published adequate data.

The bound is therefore stated per terminal state, all three applied by
`service._requeue_cooldown` over `repository.latest_terminal_attempt` (the key's NEWEST
`done`/`failed` row, so a key that has since been healed is never suppressed by its own
history):

| newest terminal row | window | constant |
|---|---|---|
| `done`, productive | 10 min | `RAINFALL_RECOMPUTE_COOLDOWN` (decision 6, unchanged) |
| `done`, build refused to write | 24 h | `RAINFALL_REFUSED_REQUEUE_COOLDOWN` |
| `failed` (terminal) | 6 h | `RAINFALL_FAILED_REQUEUE_COOLDOWN` |

6 hours is chosen against both failure shapes at once: a transient failure heals on the
first read after the cooldown lapses (well inside one working day), while a deterministic
one is capped at ≤ 4 retry cycles per day. A shorter window buys nothing for the transient
case — nothing that fails deterministically becomes fixable in minutes — and multiplies the
deterministic burn. 24 h for a refusal aligns the retry cadence with the write gate's own
daily sweep, which is the only thing that can actually change the answer. A refusal is
recorded on the row itself as an `outcome:` label in `work_labels` (`RainfallOutbox` has no
result/note column), stripped by `service.carryover_labels` whenever either sweep copies
labels onto a fresh `pending` row so a marker can never outlive the build it describes.

**The refresh is best-effort, and says so (LI2B-002).** The snapshot is already in memory
when the stale-policy enqueue runs, so `router._requeue_stale_revision` wraps it in a
SAVEPOINT and degrades to `rainfall.analysis.requeue_failed` + a normal 200. A bare
`try/except` would not do: a statement that fails mid-transaction leaves the session aborted
(SQLSTATE 25P02) and poisons everything that touches it afterwards. The savepoint is driven
manually rather than with `with db.begin_nested():` because `queue_missing_analysis` owns
its own transaction boundary (it commits, and rolls back to recover the `IntegrityError`
race of decision 8) — inside the context-manager form that inner rollback closes the block
and the race recovery's own re-read raises `InvalidRequestError`, verified empirically
before choosing the shape.

*Caveat (LIA-003, info):* that cooldown is **per key**, not a global rate limit —
`RAINFALL_RECOMPUTE_COOLDOWN` is 10 minutes (`service.py:71`) and `recent_done` filters
source/role/scope/year (`service.py:238-248`), so it bounds re-enqueue *per key*, not the
size of the post-bump backlog. The backlog is bounded elsewhere and is self-limiting: only
keys somebody actually views enter it, and `process_outbox` drains at most
`MAX_OUTBOX_BATCH = 50` rows per run (`tasks.py:16`) on a `crontab(minute="*")` schedule
(`celery_app.py:154-158`) → ≤50 keys/minute. This assumes the scope population stays small
(the proposal counts it with SQL at apply time); a large zoning would make the drain rate,
not the cooldown, the thing to watch.

**Curve points**: rejected embedding ~730 points per revision in the snapshot JSONB — that
inflates an immutable *audit* table ~15× with display data the interval store already holds
verbatim, and expands the contract at `archive/2026-08-07-lluvia-v2/design.md:22`. Chosen:
`GET /rainfall/analyses/{revision}/series`, resolved **from the revision id** so it inherits
the CSV route's auth and 404 semantics, echoing `data_revision`, `comparison_end` and
`available_through` so the UI can detect drift from the snapshot it drew. It is **strictly
read-only** — no enqueue, no write, no side effect (unlike `read_analysis`, which owns the
stale-policy refresh) — so the cooldown ladder above has nothing to bound here: a chart
polling this route cannot create GEE work at all. The displayed window is the analysis'
own clipped disclosure window (`annual.selected`'s `available_through`), not the calendar
`comparison_end`, so under provider lag the series stops where the evidence does instead of
trailing empty days a chart would read as a dry spell (D5/D6 amendments). One series builder,
two consumers: this endpoint and the xlsx "Serie diaria" sheet. The normal curve is averaged
across exactly the eligible-year set used by `annual.normal`, keyed by `(month, day)` (not
day-of-year, which misaligns leap years); Feb-29 is omitted from the curve. Acceptance: the
normal curve's last point equals `annual.normal.value`.

**Normal-curve integrity amendment (slice 3a fix round, LI3A-001).** That acceptance rule is
now enforced at **runtime**, not only by a test on one fixture, and the response says which
of three states the curve is in: **`normal_curve_state: "available" | "suppressed" |
"integrity_refused"`**. The reason is that the two sides of the rule age differently —
`annual.normal.value` is computed once at build time and is immutable, while the curve is
read live, and nothing rebuilds a finalized past year, so a divergence introduced after the
build is permanent and invisible. Two guards:

- *Sibling guard.* `repository.baseline_curve_rows` reads through the same supersession
  anti-join as `baseline_cumulatives` and therefore inherits its "at most one non-superseded
  row per `interval_start`" invariant. `baseline_cumulatives` raises
  `DuplicateBaselineSlotError` on a breach (LI2A-005/LI2B-004) precisely because a duplicate
  inflates the total while hiding itself; the curve simply summed duplicates, so the same
  broken data the build path refuses to total was being drawn. It now refuses too — detected
  per slot in the bucketing loop, which costs no extra round trip and sees every row consumed.
- *Acceptance cross-check.* The curve's last point is compared against the STORED
  `annual.normal.value` (`math.isclose`, `rel_tol=1e-9` — one side is summed by PostgreSQL and
  the other in Python, so bit-exact equality would be a flaky gate). Any drift refuses the
  whole curve.

A refused curve emits `rainfall.series.normal_curve_refused` and renders every
`normal_accumulated` as `null` — which is also what a structurally absent curve renders, and
is exactly why the state field exists: without it the response cannot distinguish an honest
absence from a curve that was computed and thrown away. Note that `consistent_with_snapshot`
does **not** cover this: the pin hashes the SELECTED scope's intervals and the baseline store
is not in that hash, so a true pin never vouched for the baseline.

**Series/snapshot consistency — server-side pinning (authoritative).** The revision row is
immutable and forever servable, while the series builder reads the interval store **live**
through the same supersession anti-join (`repository.intervals_in_window`,
`repository.py:213-246`). An NRT correction that supersedes a slot inside the analysis window
moves the series without moving the revision id, so the same revision id can serve a card
whose total disagrees with its own chart and xlsx sheet. Divergence is routine, not
theoretical, for current-year keys. The builder therefore **pins**:

1. Recompute `compute.data_revision_for(...)` (`compute.py:192-222`) over *exactly* the keys
   and window the build read — `(source_id, scope.kind, scope.id, scope.version)` and
   `[year_start - 90d, year_end)` (`tasks.py:248-256` as widened by D6), which is the
   **build's read window, not the displayed calendar-year window**; a display-window
   recompute would hash a different interval set and mismatch every time.
2. Take its inputs from the served revision alone, with no provider call: `scope`, `year`
   and `comparison_end` from the snapshot root (`compute.py:176-181`), `source_id` from
   `annual.selected.provenance.source_id` (`compute.py:147-148`), and the
   `provider_revision_family` from the read rows themselves — `revision_family(...)`
   (`compute.py:30-38`) over `RainfallIntervalValue.provider_revision` (`models.py:66`).
   `intervals_in_window` deliberately does not filter by revision family
   (`repository.py:227-229`), so the rule is: the read rows MUST map to exactly one family.

   *Asymmetry note (LIB-101 fold, slice 3a).* The two sides derive that family
   differently and cannot be made identical: at **build** time it comes from the adapter
   batch's single reported `provider_revision` (`tasks.py`, `revision_family(batch[...])`)
   — one value, available even when the read returned no rows; at **pin** time there is no
   batch, so it is derived per row from the persisted
   `RainfallIntervalValue.provider_revision` across possibly-many rows. The asymmetry is
   bounded to the conservative direction by the exactly-one rule: "not exactly one" —
   **two or more** families live in the window, or **zero** because nothing is left to read
   — reports `interval_family_ambiguous` and never attempts a comparison, so the failure
   mode is a false *inconsistent*, never a false consistent. The same bound covers the
   other input the two sides share by convention rather than by construction: `rows` are
   handed to `data_revision_for` exactly as the read returned them, with no normalization,
   because any transformation applied at pin time and not at build time would flip a
   healthy pin (this includes datetime rendering — `psycopg2` renders a `timestamptz` in
   the session's `TimeZone`, so parity, not normalization, is what keeps the two digests
   comparable).
3. Compare the recomputed digest with the row's stored `data_revision`
   (`models.py:96`; `RainfallRepository.get_revision` returns the ORM row,
   `repository.py:41-42`, so both the `/series` and the `.xlsx` route have it).

The response carries two deterministic fields: **`consistent_with_snapshot: bool`** and
**`consistency_reason: str | null`** ∈ {`null`, `"data_revision_moved"`,
`"interval_family_ambiguous"`}. Errors are one-directional by construction: an ambiguous
family or a moved digest reports *inconsistent*; nothing reports consistent unless the
digests are equal. Silent divergence is impossible.

*Wire normalization amendment (JD round 1 re-judge, JDB-101 — the LI3A-005 class).* The
echoed **`available_through` is served UTC-normalized**, not as the raw stored string. Under
provider lag the stored value is `max(interval_end)`, a `timestamptz` `psycopg2` renders in
the database session's own `TimeZone` — which nothing in this repository pins — so the same
instant can be stored as `2024-03-02T21:00:00-03:00` and every consumer reading a calendar
day off its first ten characters lands a day early. `build_series` therefore serves
`_as_utc(...)`'s rendering of the identical instant (the window is unchanged; only its
rendering is), which is what allows BOTH display consumers — the chart footer and the xlsx
Resumen cell — to keep a plain day operation. `export._last_evidence_day` applies
`temporal.as_utc`/`utc_day` anyway, as a second, independently-failing layer: its parameter
is a bare `str` and nothing in the type system says where it came from.

**Behavior when `consistent_with_snapshot` is false (defined, not left to the caller).**
- Chart: `RainfallAccumulationChart` **still renders** the series — the data is the fresher
  evidence, not garbage — above a Mantine `Alert` stating the daily data was corrected after
  this analysis. **Disclosure only, no remedy** (amended by Judgment Day round 1,
  JDA-003 ≡ JDB-003; the paragraph originally specified "plus a re-request action that
  re-POSTs `/analyses` for the same scope/year", returning either the newer revision (200)
  or a labelled 202 the panel already knows how to poll, `rainfall.ts:88-99`). That control
  was **removed as structurally inert**: the only path that enqueues a rebuild is a
  superseded *policy* revision (`router.read_analysis` → `_requeue_stale_revision`), never a
  moved `data_revision`, and revisions are immutable — so the re-POST returned the same
  revision every time and the labelled-202 branch was unreachable from this flow. A control
  that reliably does nothing turns an accurate disclosure into an instruction the reader
  follows and blames themselves for. No new backend enqueue path was added (owner decision,
  explicitly out of scope). A silent redraw remains prohibited; the panel's own poll is what
  eventually moves a tab to a newer analysis.
- xlsx: the **Resumen** sheet stamps the flag (`Serie diaria consistente con el análisis:
  sí | no — <motivo>`), because the workbook outlives the screen that showed the notice.

**Client-side contract, made real.** `data_revision` is added to `SNAPSHOT_ROOT_KEYS`
(`service.py:142-155`) and injected at disclosure time from the served row, exactly as
`analysis_revision_id` already is (`router.py:148-156`: `build_snapshot` cannot set it —
`data_revision` is computed *after* the snapshot exists, at `tasks.py:285-294`, from the
adapter batch's revision family; `normalize_snapshot` copies the envelope with
`dict(snapshot)` (`service.py:434`) and validates the root-key set on input only
(`service.py:431`), so post-normalize injection is safe). The TS
`RainfallAnalysisSnapshot` gains `data_revision: string` (`rainfall.ts:74-86`), so the
promised client check finally exists: the series echo compared against the snapshot the tab
is holding. The server flag is authoritative; the client comparison is the cheap cross-check
that also catches a stale snapshot held open in a tab.

### D4 — Policy thresholds

`apply_metric_policy` looks up `metric["metric"]`, not the group key (`service.py:413-419`),
and an absent entry force-suppresses as `policy_threshold_unset` (`policy.py:160-165`).

| group key | `metric` name | min coverage | min quality | rationale |
|---|---|---|---|---|
| `annual.selected` | `annual` | 0.8 | 0.8 | **unchanged** — renaming would break `served_state`, `revision_write_decision` (`compute.py:318`) and the raw JSON path in `repository.py:586-590` |
| `annual.normal` | `annual_normal` | 20/30 | 20/30 | see the threshold note below. `completeness` = eligible years used / years `baseline_years_for` yields; `coverage` = worst used year's day-completeness |
| `annual.percentile` | `annual_percentile` | 20/30 | 20/30 | same sample, same evidence |
| `antecedents.d7/d30/d90` | `d7`/`d30`/`d90` | 0.9 | 0.8 | `rolling_total` already refuses an incomplete window (`temporal.py:78-88`), so this is a floor, not the gate |

`quality["score"]` is set to the metric's own completeness (same convention as
`compute.py:137`).

**Threshold note — the baseline metrics' two thresholds are `20/30` (slice 2b fix
round, LI2A-003).** They were `0.9`/`0.8`, which made `MIN_BASELINE_YEARS = 20` dead
code at disclosure time. `annual_normal`/`annual_percentile` carry
`completeness = eligible baseline years / 30`, and their `quality["score"]` is *that same
number* (the convention above), so a 0.9 coverage threshold moved the effective floor to
**27** eligible years, and every sample in the reachable 20-26 band was suppressed as
`coverage_below_threshold` — a sample-size shortfall wearing a coverage label, which is
exactly the misattribution D5's two-layer suppression exists to prevent. Both entries are
now `MIN_BASELINE_YEARS / 30`, written as that literal division so the boundary case
compares *equal* (a hand-rounded `0.6667` would suppress a 20-year sample, since
`20/30 = 0.666…`). Consequence, and the point: the compute-level floor — the layer that
owns the distinct `baseline_years_below_minimum` reason — is the binding gate, and the
policy entries are the structural backstop they were meant to be (an absent entry still
force-suppresses as `policy_threshold_unset`). **Both** thresholds moved, not only
coverage: with `quality["score"] == completeness`, leaving quality at 0.8 re-suppressed
the identical band under `quality_below_threshold` (verified by probe during the fix).
Every other metric's thresholds are untouched.

`summary` is a **root-level Spanish string**, not a metric: the frontend
renderer already keys on `typeof snapshot.summary === 'string'`
(`RainfallMetricList.tsx:95-99`) and spec.md:92 asks it to *distinguish states*, which a
`MetricResult` with no value/unit/interval cannot honestly do. It therefore has no
`RAINFALL_METRIC_POLICY` entry and can never be `policy_threshold_unset`.

That contradicted the delta spec's literal threshold list. **Owner decision 2026-08-10: the
spec cedes** — the delta drops `summary` from the threshold list and gains the coherence rule
below instead (recorded in "Owner Decisions and Risks", which is also what the earlier
dangling "see Risks" pointer meant to reference; no such section existed).

**Coherence invariant (Judgment Day round 1, LIB-001+LIA-002).** Exempting `summary` from
policy is only honest if the narrative cannot contradict the badges printed beside it. The
invariant: **the summary MUST be derived from the same post-`apply_metric_policy` states
`normalize_snapshot` serves, and never from build-time completeness.**

Mechanism — the summary is assembled at **disclosure** time, not build time.
`compute.build_snapshot` does not emit `summary` at all; a pure module-level
`service.rainfall_summary(normalized_groups)` runs at the end of `normalize_snapshot`, after
the per-group `_normalize_metric` loop (`service.py:435-448`), reading only each normalized
metric's `state` / `reason` / `value`. Three reasons this is the only coherent seam:

1. `compute.py` is pure and never applies policy — policy is applied at disclosure with the
   *row's* `policy_revision` (`router.py:145-147` → `service.py:413-425`), so any build-time
   narrative describes states that may never be the ones served.
2. `_normalize_metric` downgrades metrics for reasons structurally invisible at build time:
   `metric_contract_invalid` (`service.py:391-398`), `policy_revision_mismatch`
   (`service.py:399-400`), `policy_unavailable` (`service.py:403-404`),
   `metric_quality_invalid` (`service.py:405-412`), plus every threshold outcome
   (`service.py:413-426`).
3. `normalize_snapshot` is the single funnel every disclosure passes through — JSON
   (`router.py:145-147`), audit CSV (`router.py:176-183`) and the xlsx Resumen sheet (D7) —
   so one assembly point keeps the narrative identical across them with no duplication.
   **Precisely (LIA-102 fold):** the two disclosures that actually *carry* `summary` are the
   JSON body and the xlsx Resumen sheet. The audit CSV route serializes
   `metric_rows(normalized)` (`service.py:451-459`), which iterates
   `METRIC_GROUPS = ("annual", "antecedents", "intensity")` and never reads a root key, so
   `summary` is structurally outside its row projection — the CSV's byte contract is
   unchanged by this decision, which is what D7's regression test pins.

Contract safety: writing `normalized["summary"]` after the loop is safe for the same reason
the router injects `analysis_revision_id` post-normalize (`router.py:148-156`) —
`normalize_snapshot` copies the envelope via `dict(snapshot)` (`service.py:434`) and
validates the root-key set on *input* (`service.py:431`), and `summary` is already
allow-listed (`service.py:152`). Immutability is preserved: the audit row keeps evidence
only, and the narrative stays a deterministic function of that row plus its own policy
revision, re-derivable at any time. Rollback for the summary is therefore a `service.py`
revert with no snapshot rewrite. Rejected: passing post-policy states down into
`build_snapshot` — it would drag `apply_metric_policy` into `compute.py`, breaking the purity
boundary this design opens with, and would still miss the disclosure-time downgrades in (2).

### D5 — Percentile mechanics

Empirical Weibull, in `compute.py` (pure, already imports `temporal`) — **not** `temporal.py`,
whose contract is calendar/event-window rules, not statistics. Sample = the eligible baseline
cumulatives **plus** the selected-year cumulative (N = n+1); `p = 100·i/(N+1)` with `i` the
1-based ascending position, ties taking mean position. Including the year avoids degenerate
0/100 and keeps the range 3.1–96.9 at n=30. Rejected: exceedance-only `count(b<x)/n` (emits a
literal 0 or 100) and any fitted distribution (the proposal already rejected Gumbel for v1).

Two-layer suppression, because `apply_metric_policy` only speaks fractions and cannot see
absolute n: (1) per-year day-completeness < 0.95 drops that year from the sample; (2)
`MIN_BASELINE_YEARS = 20` in `compute.py` → below it, normal and percentile are emitted
`state="suppressed"`, `reason="baseline_years_below_minimum"` (a compute-level suppression
survives normalization untouched, `service.py:401-402`). **Feb-29 therefore suppresses**:
`baseline_years_for` yields 8 leap years (`temporal.py:20-26`), whose percentile resolution is
~11 points — misleading precision. Rejected: imputing Feb-28 (contradicts the shipped
no-imputation rule) and lowering the floor to 8 (publishes the misleading rank the proposal's
risk row exists to prevent). Unit for percentile is `"percentil"`, not `"%"`, which would be
misread as "% of normal".

Other contract details: `annual.normal.interval_*` = the baseline envelope (1991-01-01 →
last baseline comparison_end + 1d) with per-year windows disclosed in `quality`;
`temporal_state` of percentile follows its weakest input (provisional if the selected year is);
normal/percentile carry `provenance.source_id = "chirps-v3-final"` per spec.md:435 while
`annual.selected` keeps its own — role assignment, not blending.

**Same-date anchor amendment (slice 2b fix round, LI2A-101).** "Same date" above means
the date the *selected year actually reaches*, not the calendar `comparison_end`. The
baseline windows are cut at `baseline_cutoff_for(...)` — the last day covered by
`window_end = min(comparison_end_exclusive, last_interval_end)`, the same clip
`annual.selected` applies (`compute.py`) and the same one D6's anchor amendment adopted
for the antecedents. Provider lag is the documented steady state, and under lag the old
calendar cut compared unlike things: `annual.selected` totalled through
`comparison_end − lag` while every baseline year totalled through `comparison_end`, so the
selected year entered its own rank sample short by the lag and the percentile was biased
low — a violation of this decision's own premise, not merely of D6's. With a 3-day lag and
a baseline whose tail days are large, the reproduction moved the rank from the 50th
percentile to the 3rd. `annual.normal`'s disclosed `interval_end`/`available_through` now
end at that same effective cutoff, so the envelope tells the same truth `available_through`
already told for the selected year after the D6 fix. With no lag the two dates are
provably identical (`window_end == comparison_end_exclusive`), so the no-lag path is
unchanged. Mechanism: one derivation, `compute._disclosure_window`, called by
`build_snapshot` for its own window and by `tasks._persist_analysis_revision` (through
`baseline_cutoff_for`) to pick `temporal.baseline_dates(...)` *before* the build — the same
"computed once ahead, recomputed identically inside" shape the caller already uses for
`comparison_end`, never a second independent derivation. Note the Feb-29 interaction is
resolved consistently rather than special-cased: under lag the effective cutoff is not
Feb 29, so the 30-year family applies and the rank is honest; without lag the 8-leap-year
family still trips `MIN_BASELINE_YEARS`.

**Cross-source caveat (Judgment Day round 1, LIB-003, info).** That role assignment means a
current-year comparison ranks an NRT-sourced total against a Final-sourced baseline — a
methodological caveat the reader cannot infer from the numbers. It needs a *disclosure
channel*, and the baseline has none of its own: it comes from a SQL aggregate
(`repository.baseline_cumulatives`, D1), so there is no adapter batch and nothing to inherit
the way `annual.selected` inherits `batch["discrepancies"]` (`compute.py:169`). Chosen:
`build_snapshot` emits a **fixed entry into `annual.normal`'s and `annual.percentile`'s own
`discrepancies` list** (`schemas.py:36`, `tuple[str, ...]` — the same channel, already
carried through `_normalize_metric`'s `{**raw, …}` passthrough at `service.py:426`). Exact
shape, following the flat `key=value` convention already in use
(`adapters/zonal.py:99`), no spaces:

    f"cross_source_baseline=chirps-v3-final_vs_{selected_source_id}"

Emitted once per metric, and **only** when `annual.selected.provenance.source_id` differs
from the baseline `chirps-v3-final` — a completed year sourced from Final emits nothing, so
the caveat appears exactly where it is true. Rejected: a free-text note on the root summary
(the caveat belongs to the two metrics it biases, and must survive into CSV/xlsx rows, not
only the panel).

### D6 — Antecedents read window

d7/d30/d90 end at `comparison_end` and may cross the year boundary (spec.md:101-106). The
resolved-interval read in `tasks.py:246-256` widens from `[year_start, year_end)` to
`[year_start - 90d, year_end)`; `build_snapshot`'s own `in_window` filter
(`compute.py:113-117`) keeps `annual.selected` unchanged. Same `source_id` as the selected
year — never mixing final+sat rows, which would be blending. When the prior-year window is
missing, `rolling_total` raises `EventSuppressed` → suppressed with a specific reason, never a
short sum. Widening the read changes `data_revision_for`'s input, which is fine and expected:
one new revision per key on the next build.

**Anchor amendment (slice 2a fix round, LI2A-002).** The sentence above says the windows
"end at `comparison_end`". Corrected: they end at
`min(comparison_end_exclusive, last_interval_end)` — the *same* clip `annual.selected` already
applies (`compute.py:394`) — not at the raw calendar `comparison_end`. Provider lag is the
documented steady state: the owner's 2026-08-08 decision explicitly kept the calendar
`comparison_end` **plus** `available_through` disclosure rather than redesigning the semantics
(`openspec/changes/archive/2026-08-09-rainfall-materialization/review-ledger.md:86`), and that
decision only holds if `available_through` is honest. A rigid calendar anchor is not:
`temporal.rolling_total` demands an EXACT cadence-aligned slot set (`temporal.py:81-87` — it
compares the fetched slot tuple against the expected one, so a single absent slot suppresses),
so it would demand a slot for *today*, which a lagging provider has not published. With lag
≥ 1 day, all three of `antecedents.{d7,d30,d90}` therefore suppressed as
`antecedent_window_incomplete` on **every** current-year build — the feature was unrenderable
in exactly its steady state. `provenance.available_through` and `interval_end` now disclose the
clipped end, mirroring how `annual.selected` reports its own clipped `window_end`
(`compute.py:429`), instead of overstating availability up to a calendar date the provider has
not reached.

Suppression semantics are unchanged: a missing slot *inside* the clipped window still raises
`EventSuppressed` → `antecedent_window_incomplete`, never a short sum. Year-boundary lag
degrades naturally, with no special path: the clip reuses `in_window`'s own
`last_interval_end`, so when the lag reaches back past `year_start` there is no in-window
interval at all, the clip falls back to `comparison_end_exclusive`, and the windows suppress
because their current-year head slots do not exist (the last expected slot, `end - cadence`,
is never earlier than `year_start`, so it would have been in `in_window` had it been
published). Were the anchor ever to land before `year_start`, the window's head slots would
fall outside the D6 read window `[year_start - 90d, …)` and the same exact-set check would
suppress. Both are safe failures — suppression, never a wrong value.

### D7 — Export (xlsx)

`GET /rainfall/analyses/{revision}.xlsx` beside the CSV route, inheriting the router-level
`require_admin_or_operator` (`router.py:39-41`). Builder lives in a new
`rainfall/export.py` (routers stay thin; `service.py` is already 478 lines).
`openpyxl.Workbook(write_only=True)` → `BytesIO`; `Content-Disposition:
attachment; filename="lluvia_{revision}.xlsx"`. Sheet **Resumen** is built from the *same*
`metric_rows(normalize_snapshot(...))` the CSV uses, so parity is structural rather than
duplicated (spec.md:491-506); `None` writes an **empty cell**, never 0. Sheet **Serie diaria**
comes from the shared series builder (D3): fecha, mm, acumulado, normal acumulada, estado.
Because the workbook outlives the screen, **Resumen** also stamps the series pin from D3
(`Serie diaria consistente con el análisis: sí | no — <motivo>`), so a downloaded file can
never present a corrected daily series beside an uncorrected summary without saying so.
Audit CSV bytes are untouched and regression-tested.

### D8 — Frontend

`recharts` directly (`PrecipChart.tsx:43`), not `@mantine/charts`: the Lluvia tab already
loads the `vendor-charts` chunk and `vendor-mantine-charts` is currently admin-only
(`vite.config.ts:446-448`) — zero incremental vendor bytes on the ficha route.
New `components/map2d/rainfall/RainfallAccumulationChart.tsx` (two `Line`s: selected year vs
normal, `ReferenceLine` at `comparison_end`) fed by `useRainfallSeries(revisionId)`.
`rainfallFormat.ts:14-29` **already** labels `normal`/`percentile`/`d7`/`d30`/`d90`, and
`lib/api/rainfall.ts:81-83` types groups as `Record<string, RainfallMetric>` — so activation
costs no type or label churn. `AnnualText` (`RainfallMetricList.tsx:63-75`) gains the
percentile phrase and stays the chart's textual equivalent. Both dates are disclosed in the
chart footer (owner decision 4) — as the **last day with evidence**, i.e.
`available_through − 1 day`, because `available_through` is the EXCLUSIVE end of the
disclosure window (JD round 1, JDA-001 ≡ JDB-001; the raw value never reaches the reader).
The chart also owns the **staleness notice** defined in D3: when the series response reports
`consistent_with_snapshot: false` (or its echoed `data_revision` differs from the snapshot's
newly typed `data_revision`, `rainfall.ts:74-86`), it renders the curve *plus* an `Alert` —
never a silent redraw, and **never a re-request action** (removed in JD round 1 as
structurally inert, JDA-003 ≡ JDB-003 — see D3). The **campaign preset** is a display
`SegmentedControl` that
windows the x-axis of the same calendar-year series and **must not alter the request payload**
— asserted by a test that no `/analyses` call fires on toggle, which is what keeps spec.md:67
intact.

## Data Flow

    1991-2020 one-shot          per-request / sweep
    backfill_baseline_range     outbox -> ingest_source_scope
            |                            |
            v                            v
    persist_intervals            persist_intervals
    key: provider_asset          key: zone|basin
            \                          /
             \      intervals_in_window (anti-join)
              \    baseline_cumulatives (SQL window SUM)
               \        /
                v      v
              compute.build_snapshot  --> persist_revision (policy_revision bump lands it)
                                              |          (row carries data_revision)
                    router /analyses ---------+--> normalize_snapshot -> apply policy
                                              |    -> summary assembled here (D4)
                                              |    -> + data_revision injected -> JSON | .csv | .xlsx
                    router /series  ----------+--> series builder -> pin: recompute
                                                   data_revision_for over the build window
                                                   vs row.data_revision
                                                   -> consistent_with_snapshot
                                                   -> chart + "Serie diaria" + Resumen stamp

## File Changes

| File | Action | Description |
|---|---|---|
| `geo/rainfall/adapters/gee_client.py` | Modify | `asset_name_for` accepts `provider_asset`; export `BASELINE_ASSET_VERSION` |
| `geo/rainfall/repository.py` | Modify | `baseline_cumulatives` (anti-joined, TZ-pinned year key, + the duplicated-slot guard `build_snapshot` already applies — LI2A-005), `daily_series_rows`, `baseline_curve_rows` (all anti-joined) |
| `geo/rainfall/compute.py` | Modify | normal/percentile/antecedents in `build_snapshot` (**not** `summary` — D4 moves it to disclosure time); fixed `cross_source_baseline=…` discrepancy entry (D5); `weibull_percentile`, `MIN_BASELINE_YEARS` |
| `geo/rainfall/service.py` | Modify | `data_revision` added to `SNAPSHOT_ROOT_KEYS` (`service.py:142-155`); pure `rainfall_summary(...)` assembled at the end of `normalize_snapshot` from post-policy states (D4) |
| `geo/rainfall/policy.py` | Modify | 5 threshold entries (`annual_normal`, `annual_percentile`, `d7`, `d30`, `d90` — **no `summary` entry**, D4; the two baseline entries at `20/30`, D4 threshold note) + revision bump to `rainfall-v2-2026-08-insights` |
| `geo/rainfall/tasks.py` | Modify | widened interval read, baseline resolution + `UnknownProviderScope` guard, `backfill_baseline_range` with `except (AdapterError, CircuitOpen)` (D2) |
| `geo/rainfall/export.py` | Create | xlsx workbook + Spanish metric labels + series-consistency stamp in Resumen (D7) |
| `geo/rainfall/series.py` | Create | one series contract: points + echoed `data_revision` + `consistent_with_snapshot`/`consistency_reason` pin recomputed over the build's read window (D3) |
| `geo/rainfall/router.py` | Modify | `.xlsx` + `/series` routes; stale-policy requeue; inject `data_revision` post-normalize from the served row (mirrors `analysis_revision_id`, `router.py:148-156`) |
| `geo/rainfall/backfill_cli.py` | Create | `__main__` one-shot runner; labelled stop + recovery-window note in its `--help`/runbook text |
| `web/…/rainfall/RainfallAccumulationChart.tsx` | Create | year-vs-normal curve + campaign preset + staleness notice, **disclosure only — no re-request action** (JD round 1, JDA-003 ≡ JDB-003) (D3/D8) |
| `web/…/rainfall/RainfallMetricList.tsx` | Modify | percentile phrase in `AnnualText` |
| `web/src/lib/api/rainfall.ts`, `hooks/useRainfallAnalysis.ts` | Modify | `data_revision: string` on `RainfallAnalysisSnapshot` (`rainfall.ts:74-86`); series fetch/hook incl. consistency fields; xlsx download |
| `openspec/specs/rainfall-analysis/spec.md` | Delta | xlsx export requirement + campaign-display clarification + series/snapshot consistency scenario + summary-coherence requirement (`summary` dropped from the threshold list) |
| `temporal.py`, `PrecipChart.tsx`, `ficha_service.py`, `generate_chirps_normals.py` | Untouched | reused verbatim / public path unchanged |

## Testing Strategy and CI

| Layer | What | How |
|---|---|---|
| Unit (pure) | Weibull rank, min-n, per-year filtering, envelope shape | extend `tests/test_mutation_targets_rainfall.py` (no DB, branch-dense) |
| Unit (pure) | **summary coherence (D4)**: `rainfall_summary` fed the *post-policy* groups never describes as available a metric the policy suppressed; a metric downgraded to `unavailable`/`policy_revision_mismatch` at disclosure is narrated as such; `build_snapshot` emits **no** `summary` key | extend `tests/test_mutation_targets_rainfall.py` + a `normalize_snapshot` end-to-end case (thresholds set so build-time completeness and post-policy state disagree) |
| Unit (pure) | **cross-source caveat (D5)**: `cross_source_baseline=chirps-v3-final_vs_<src>` present on normal+percentile for an NRT selected year, absent when both sides are Final | extend `tests/test_mutation_targets_rainfall.py` |
| Integration (real PG) | baseline reachable from a zone analysis; **zoning republication does not orphan the baseline**; supersession respected on baseline reads | `tests/new/geo/rainfall/test_rainfall_baseline.py` (new) |
| Integration (real PG) | all new metrics `available`; **no metric has `reason == "policy_threshold_unset"`**; normal/percentile share `annual.selected`'s `comparison_end`; cross-year d90; d90 suppressed with reason when incomplete | `test_rainfall_insights_metrics.py` (new) |
| Integration (real PG) | **series pin (D3)**: untouched intervals → `consistent_with_snapshot: true` / `reason: null`; supersede one slot inside the build window → `false` + `data_revision_moved`; two revision families non-superseded in the window → `false` + `interval_family_ambiguous`; the pin recompute uses the D6-widened window (a display-window recompute would mismatch a consistent case) | `test_rainfall_series_consistency.py` (new) |
| Integration (real PG) | 30 checkpoints, re-run `already_complete` + 0 inserts, resume after interruption; **backfill stops labelled, not raw**: a pre-opened Redis circuit for the role yields a `circuit_open` stop result (no traceback, no provider call), an `AdapterError` yields `adapter_error` | `test_rainfall_backfill.py` (new), `FakeGeeClient` — CI never touches GEE (`gee_client.py:4-5`) |
| Integration (real PG) | xlsx sheets/states/blank-not-zero, 401/403, filename; **Resumen stamps the series-consistency flag in both directions**; `data_revision` present on the served snapshot JSON | `test_rainfall_export_xlsx.py` (new) |
| Vitest | chart renders both series, both dates disclosed (the second as the last day WITH evidence, JDA-001 ≡ JDB-001), campaign toggle fires no request; **staleness notice renders when `consistent_with_snapshot` is false and is absent when true — and offers NO re-request action** (the three absence tests replace the four 200/202 tests, JD round 1, JDA-003 ≡ JDB-003) | `tests/unit/RainfallAccumulationChart.test.tsx` (new, `ResponsiveContainer` mock recipe from `tests/unit/PrecipChart.test.tsx:41-42`); extend `RainfallDetailPanel.test.tsx`, `rainfallApi.test.ts` |
| E2E | xlsx download + chart visible | extend `tests/e2e/rainfall-v2-detail.spec.ts` |
| Mutation | new pure code lands in the rainfall target file; `policy.py`/`service.py`/`compute.py` stay **registered-commented** in `.cosmic-ray.toml:78-90` — including `rainfall_summary`, which D4 places in `service.py` (already in that same commented block) | repo rule: no wiring an unmeasured module into the gate (blocked on a Python-3.11 cosmic-ray, not on tests) |

No new CI job, no new dependency (`openpyxl`, `recharts` present).

## Delivery — chained PRs on `feat/lluvia-insights`

| # | Slice | Budget | Gate |
|---|---|---|---|
| 1 | provider-asset key + `baseline_cumulatives` + backfill orchestrator/CLI (`(AdapterError, CircuitOpen)` stop) + tests | ~380 | merge, then run 1991 alone (verify 365 intervals), then the remaining 29 |
| 2 | metrics + percentile + policy entries + revision bump + disclosure-time `summary` + cross-source caveat + stale-policy requeue | ~450 | with an empty baseline these suppress as `baseline_years_below_minimum` — never wrong numbers; summary coherence asserted against post-policy states |
| 3 | series module + pin/consistency fields + `data_revision` exposure (root key + router injection + TS) + `/series` + `.xlsx` (incl. Resumen stamp) + tests | ~450 | audit CSV regression; consistency true/false both asserted |
| 4 | chart + activation + preset + staleness notice + Vitest/E2E | ~350 | droppable last (dropping it leaves the server-side flag, which is the authoritative half) |

`Decision needed before apply: Yes` · `Chained PRs recommended: Yes` · `400-line budget risk: High`
(~1630 lines total — up from ~1400 after Judgment Day round 1 added the consistency pin, the
`data_revision` exposure and the disclosure-time summary; slices 2 and 3 now exceed the
400-line budget on their own and are the two to watch). GEE cost opens only in slice 1 and
only via the manual runbook step, so a paused backfill degrades to labelled suppression
rather than a wrong disclosure.

## Migration / Rollout

No schema migration. Order: deploy slice 1 → enable `historical` role flag → dry-run 1991 →
full backfill → deploy slice 2 (revision bump makes the new envelope land) → slices 3-4.

Backfill runbook step (D2): the CLI stops **labelled** on `AdapterError` or `CircuitOpen` and
exits non-zero with the reason; it never raises a bare traceback and never keeps hammering an
open breaker. On a `circuit_open` stop, **wait out the ~300s recovery window**
(`resilience.py:52`) before rerunning — the breaker is Redis-backed per role
(`tasks.py:153-159`, `resilience.py:101-102`), so a brand-new process inherits it and an
immediate rerun is expected to stop again at once. Re-running after the window resumes at the
first year without `completed_at`; nothing is re-fetched.

Rollback per proposal: drop the policy entries and bump the revision again; backfilled
intervals are append-only evidence and stay. The `summary` narrative and the series
consistency fields are computed at disclosure time, so rolling either back is a code revert
with no snapshot rewrite.

## Owner Decisions and Risks

| Item | Date | Decision / mitigation |
|---|---|---|
| `summary` vs the delta spec's literal threshold list (LIB-001+LIA-002) | 2026-08-10 | **The spec cedes.** `summary` is a root-level Spanish string, not a `MetricResult`, so it gets no `RAINFALL_METRIC_POLICY` entry and can never be `policy_threshold_unset`. The delta drops it from the threshold list and instead requires the coherence rule in D4. This is the section D4's earlier "see Risks" pointer meant to reference — it did not exist. |
| Summary contradicting the badges beside it | 2026-08-10 | Invariant + mechanism in D4: assembled at disclosure time from post-`apply_metric_policy` states, never from build-time completeness. Unit-tested with thresholds chosen so the two disagree. |
| Series ≠ snapshot after an NRT correction (LIA-001+LIB-002) | 2026-08-10 | Server-side pin + `consistent_with_snapshot`/`consistency_reason` (D3), a defined UI staleness path, and a Resumen stamp in the workbook. Residual risk: a false *inconsistent* when the read window legitimately holds two revision families — conservative by design, and disclosed with its own reason rather than hidden. |
| Backfill rerun inside the circuit recovery window (LIA-004) | 2026-08-10 | `except (AdapterError, CircuitOpen)` at the orchestrator + the runbook wait-out step (D2, Migration / Rollout). Bare `RuntimeError` rejected as too broad. |
| Post-bump requeue backlog (LIA-003, info) | 2026-08-10 | Per-key cooldown is not a global bound; the real bound is the 50-rows-per-minute outbox drain. Accepted under a small scope population, counted with SQL at apply time. |
| Cross-source (NRT year vs Final baseline) bias (LIB-003, info) | 2026-08-10 | Fixed `cross_source_baseline=…` entry in the two affected metrics' `discrepancies`, emitted only when the sources actually differ (D5). |

## Open Questions

- [ ] `RAINFALL_BACKFILL_PACE_SECONDS` default (5s) is a guess — one real 1991 run settles it.
- [ ] Should `annual.percentile` also suppress when `annual.selected` is `partial` (not only
      `unavailable`)? Recommendation: allow, and inherit `partial`.
