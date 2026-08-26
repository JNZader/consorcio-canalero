# Rainfall Extreme Events Specification

## Purpose

Persist and serve a catalog of extreme-rainfall events for the consorcio zone, detected by
ranking rolling windows of the persisted 1991-2025 CHIRPS daily baseline against their own
climatology, so the historic-flood picker stops being three hand-written literals and becomes
an auditable, append-only record of what the record actually holds. The catalog spends zero
provider quota, keeps every curated anchor institutional memory already knows, and declares
its own limits: zone-only coverage, imagery candidacy per event, and the CHIRPS disclosure
that this is a relative ranking rather than a millimetre measurement.

A NEW capability rather than a `rainfall-analysis` extension -- the catalog is persisted,
append-only, scope-wide and serves the historic-floods consumers, while `rainfall-analysis`
governs the per-request snapshot card; only the shared window-percentile mode contract is
touched there.

## Requirements

### Requirement: Extreme Event Detection by Absolute-Mode Window Percentile

Detection MUST rank each rolling window against the FULL persisted 1991–2025 daily baseline
using the **absolute window percentile** mode (`climatology.absolute_window_percentile`), for
window lengths `d1`, `d3` and `d7`, each against the climatology of its own length. Fixed
millimetre thresholds are an explicit **non-requirement**: CHIRPS daily fields are
pentad-disaggregated and underestimate Argentine extremes, so a constant mm threshold measures
dataset bias, not weather. The threshold percentiles are named constants — **p99.75 =
`extrema`, p98.8 = `alta`** — each carrying a pinned rationale in the code (the measured
percentile→count table over the all-window population; ratified 2026-08-26 to select the
~30/~150 volumes the proposal described — the earlier p99/p95 wording predated the
population-arithmetic correction), and the effective threshold MUST be sealed into every
persisted row alongside a versioned `detector_revision`.

The catalog MUST record which window(s) fired for each event, so `d1`-only events read as
flash and `d7` events as accumulation.

#### Scenario: A window is ranked, not measured

- GIVEN a persisted baseline of ~12.7k daily rows for the scope
- WHEN the detector evaluates a 3-day window
- THEN the window is ranked against all rolling 3-day baseline windows
- AND no fixed millimetre threshold participates in the qualifying decision

#### Scenario: Both tiers are persisted, and the firing windows are recorded

- GIVEN an event whose `d3` window reaches p99 and whose `d7` window reaches only p95
- WHEN the event is persisted
- THEN the row carries its severity tier and the set of windows that fired with their percentiles
- AND the sealed threshold values and `detector_revision` are stored on the row

#### Scenario: An incomplete window never qualifies

- GIVEN a candidate window missing one interior day
- WHEN the detector evaluates it
- THEN the window is skipped, never partially summed
- AND the resulting failure mode is a false negative, never a fabricated event

### Requirement: Append-Only Catalog Persisted Without Provider Calls

The catalog MUST live in its own table (`rainfall_extreme_event`); the existing
`flood_events` / `flood_labels` pair MUST NOT be reused — verified 2026-08-25, those model
per-zone calibration labels, have no writer, and carry foreign semantics.

The detector MUST be runnable as an idempotent **full-span** backfill over the whole persisted
span, MUST read only persisted rows (**zero GEE / zero provider fetches**), and MUST be
reproducible: the same persisted rows plus the same `detector_revision` yield the same catalog.
Re-running MUST NOT duplicate or mutate existing rows under the same identity key.

*(Amended at the B2a spec merge, 2026-08-26: the change delta still required the detector to
be runnable "incrementally", which design.md D6 CUT — the climatology span is frozen to whole
calendar years, so every run ranks against the same distribution and reads the same rows, and
advancing the span requires a revision bump that regenerates the whole generation anyway. The
incremental path had no reachable use case and cost two of the review's hardest findings.
Merging the original sentence would have put a MUST on `main` that nothing implements and
nothing can implement without reopening D6. The runbook's own parser asserts the ABSENCE of a
`--since` flag, so this amendment is what the code actually does.)*

#### Scenario: Re-running the backfill is a no-op

- GIVEN the detector has already been run over the full span at revision R
- WHEN it is run again at revision R over the same persisted rows
- THEN no row is inserted, updated or deleted
- AND the served catalog is byte-identical in its event set

#### Scenario: A revision bump appends rather than rewrites

- GIVEN a catalog written at revision R
- WHEN the detector runs at revision R+1 with a different threshold
- THEN new rows are appended under R+1
- AND the R rows are retained, still readable with their own sealed threshold

#### Scenario: Detection spends no provider quota

- GIVEN the persisted baseline is present
- WHEN the detector runs over the whole span
- THEN it issues zero provider/GEE requests

### Requirement: Catalog-Backed Historic Floods Through the Existing Contract

`get_historic_floods_impl` MUST serve catalog rows in the SAME dict shape the current literals
use (`id`, `name`, `date`, `description`, `severity`, and optional `sensor` / `max_cloud` /
`days_buffer`), so the picker, `get_historic_flood_tiles_impl` and the `analyze_flood` bridge
keep working with **zero frontend changes**. The epoch-dependent `days_buffer` default
(30 before 2020, else 15) MUST keep applying to catalog events that do not override it.

The DEFAULT response MUST serve the `extrema` tier (~30 events at the ratified p99.75
threshold); the `alta` tier MUST be reachable through an explicit filter parameter and
MUST NOT be the default.

#### Scenario: Default response is the short list

- GIVEN a catalog holding both `extrema` and `alta` rows
- WHEN `GET /historic-floods` is called without filters
- THEN only `extrema` events are served
- AND requesting the `alta` tier explicitly returns the wider set

#### Scenario: The imagery bridge resolves a catalog event

- GIVEN a served catalog event dated before 2020 with no `days_buffer` override
- WHEN its tiles are requested by id
- THEN the event resolves by id exactly as a literal did
- AND a 30-day buffer is applied

### Requirement: Provenance, Confirmation State and Curated Events Are Never Dropped

Every served event MUST carry a machine-readable provenance and confirmation state. A curated
event that the detector does NOT confirm MUST still be served, flagged
`curated, not detector-confirmed`, and MUST NEVER be silently dropped nor served unflagged.
The three known anchors (`mar_2015`, `feb_2017`, `sep_2025`) are validation anchors: each is
either detector-confirmed — recorded with its firing window(s) and tier — or carried as curated.

Confirmation is derived at read with a **±3-day tolerance**: a curated anchor counts as
detector-confirmed when a detected event's span falls within 3 days of the anchor date, and
the served confirmation names the confirming event. The anchor KEEPS its curated date — the
impact date institutional memory knows. *(Ratified 2026-08-26 from the real calibration:
`feb_2017`'s rain — 54.57mm on 2017-02-18, fired at p99.68 — precedes the curated 02-20 by
two days, plausibly the downstream-flooding peak date; a strict same-date rule would hide a
real confirmation behind a dating technicality. `mar_2015`'s nearest event is 8 days away
and correctly stays unconfirmed.)*

#### Scenario: A confirmed anchor is served as detected

- GIVEN a detected event's span falls within ±3 days of the anchor date 2017-02-20
- WHEN the catalog is served
- THEN that anchor's confirmation names the detected event with its window(s) and tier
- AND the anchor keeps its curated date in the served record

#### Scenario: A non-detection surfaces instead of vanishing

- GIVEN an anchor date falls inside no detected span
- WHEN the catalog is built and served
- THEN the non-detection is surfaced as an explicit finding (failing anchor test and a served
  `curated, not detector-confirmed` flag)
- AND the event remains in the served list

### Requirement: Declared Coverage, Imagery Candidacy and CHIRPS Disclosure

The served contract MUST declare, explicitly and machine-readably, that catalog coverage is
`zone` only (`zona_cc_ampliada`) and not basin-wide. Every event MUST carry a first-class
`imagery_candidate` field: post-2015 events are candidates, pre-2015 events MUST carry an
explicit no-useful-imagery label, and the golden window 2017–2021 MUST be stated in the
response metadata. Each event MUST carry the CHIRPS disclosure: the catalog ranks relatively
and bounds satellite search windows; it is not a millimetre measurement.

#### Scenario: A pre-2015 event discloses its imagery limit

- GIVEN a detected event dated 1994
- WHEN it is served
- THEN `imagery_candidate` is false with an explicit no-useful-imagery label
- AND the event is still served, not filtered out

#### Scenario: Scope is never overstated

- GIVEN any catalog response
- WHEN it is read by a client
- THEN the zone-only coverage is machine-readably declared
- AND no basin or parcel coverage is implied

### Requirement: No Invented Events

The catalog MUST contain only events derived from persisted baseline rows or explicitly flagged
curated entries. Absence MUST be served with a reason (no qualifying window, incomplete
evidence, or scope unsupported) rather than as an empty success or a placeholder event.

#### Scenario: A year with no qualifying window serves an absence, not a filler

- GIVEN a requested year in which no window reaches the served tier
- WHEN the catalog is served for that year
- THEN the empty result is accompanied by its reason
- AND no synthetic or interpolated event is produced
