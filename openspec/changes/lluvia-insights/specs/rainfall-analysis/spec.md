# Delta for rainfall-analysis

## MODIFIED Requirements

### Requirement: GEE Quota Guards on Request-Path Re-enqueue and Poll

This requirement governs the **request path only**. `queue_missing_analysis` — the enqueue path reached from `POST /api/v2/geo/rainfall/analyses` — MUST NOT enqueue new work when a recent `done` row already exists for the same key. A poll for a key that already has a materialized `rainfall_analysis_revision` MUST be served from that stored revision.

A poll MAY additionally trigger **one asynchronous refresh** for that key when the stored revision's `policy_revision` no longer matches the current approved metric policy. The poll itself MUST still be served from the stored revision, normalized under that revision's own `policy_revision`; the refresh is background work and MUST NOT change, delay or fail the served response. This is the only request-path exception to "no new GEE fetch" and exists because neither scheduled sweep revisits a past-year key that is already `done`, so the request path is the only place a superseded policy revision is ever noticed.

That refresh MUST be bounded per key by the terminal state of the key's own most recent outbox row, so that repeated polling can never cost more than one refresh per key per window:

- a productive `done` row within the recompute cooldown (10 minutes) suppresses it;
- a `done` row whose build refused to write (a latched or gate-refused decision) suppresses it for a daily window, because such a refusal cannot be resolved by retrying sooner;
- a terminal `failed` row suppresses it for a six-hour window, because a key that exhausted its retries would otherwise begin a fresh retry cycle on every poll;
- a `pending` row for the same key is reused rather than duplicated.

A failure to enqueue that refresh MUST NOT fail the poll: the stored revision MUST still be served, and the failure MUST be recorded as an observable event.

#### Scenario: Repeated POST skips re-enqueue after recent done
- GIVEN a recent `done` outbox row exists for a key
- WHEN the same key is POSTed again through the request path
- THEN no new outbox row is enqueued and no new GEE fetch occurs

#### Scenario: A scheduled sweep is not bound by the request-path cooldown
- GIVEN a `done` outbox row exists for a key that a scheduled sweep is due to re-enqueue
- WHEN that sweep runs
- THEN it enqueues its work item under its own per-run per-key bound
- AND the request-path cooldown does not suppress it

#### Scenario: Repeated poll serves the stored revision
- GIVEN a `rainfall_analysis_revision` already exists for a key
- WHEN that key is polled again
- THEN the stored revision is returned
- AND no new GEE fetch is triggered, unless the stored revision's `policy_revision` is superseded and no cooldown for that key is in force

#### Scenario: Poll of a key whose stored revision is on a superseded policy revision
- GIVEN a stored revision for a key was written under a superseded `policy_revision`
- AND no cooldown is in force for that key
- WHEN that key is polled
- THEN the stored revision is served, normalized under its own `policy_revision`
- AND exactly one refresh is enqueued for that key

#### Scenario: Poll of a key whose last attempt failed terminally
- GIVEN the most recent outbox row for a key is terminal `failed` within the failed-requeue cooldown
- WHEN that key is polled, with or without a superseded stored revision
- THEN no new outbox row is enqueued and no new GEE fetch occurs
- AND the stored revision, if any, is still served

#### Scenario: Poll of a key whose last build refused to write
- GIVEN the most recent outbox row for a key is `done` and its build refused to write
- AND that row completed within the daily refused-requeue cooldown
- WHEN that key is polled
- THEN no new outbox row is enqueued and no new GEE fetch occurs

#### Scenario: The refresh enqueue fails
- GIVEN a stored revision on a superseded `policy_revision` is being served
- WHEN enqueueing its refresh raises a database error
- THEN the stored revision is still returned to the caller
- AND the enqueue failure is recorded as an observable event

## ADDED Requirements

### Requirement: Historical Baseline Backfill

The system MUST backfill 1991–2020 daily intervals for every provider-reachable zone scope, one ingest call per (scope, year), resumable via checkpoint with no duplication on rerun. The system MUST dedupe by provider asset so scopes sharing one asset are bounded at 30 year-reductions total, not per scope.

#### Scenario: Interrupted backfill resumes

- GIVEN a backfill was interrupted mid-run
- WHEN it resumes
- THEN it continues from the checkpoint without re-fetching completed years

#### Scenario: Shared asset fetched once per year

- GIVEN two zone scopes resolve to one provider asset
- WHEN backfill runs
- THEN the provider is fetched once per year for that asset

### Requirement: Policy Thresholds for New Metrics

Every metric published under `annual.normal`, `annual.percentile`, and `antecedents.{d7,d30,d90}` MUST have a coverage and quality threshold in `RAINFALL_METRIC_POLICY` before being served; the revision MUST be bumped when thresholds are added.

#### Scenario: Complete analysis has no unthresholded metric

- GIVEN eligible data satisfies each new metric's threshold
- WHEN an analysis builds
- THEN no required outcome is suppressed as `policy_threshold_unset`

### Requirement: Summary Coheres with the Disclosed Metric States

The report summary is a narrative, not a measured metric, and therefore carries no coverage or quality threshold. It MUST be derived from the same disclosed metric states the system serves — the states produced after the approved metric policy is applied — and MUST NOT be derived from build-time completeness. The summary MUST NOT describe a metric in a state that contradicts the state disclosed for that metric alongside it.

#### Scenario: Policy suppresses a metric the raw data would have supported

- GIVEN a metric whose build-time completeness would read as available
- AND the approved policy suppresses that metric at disclosure
- WHEN the analysis is served as JSON, CSV or xlsx
- THEN the summary describes that metric as suppressed with its disclosed reason, and never as an available value

#### Scenario: Summary and badges cannot disagree

- GIVEN an analysis whose disclosed metrics include at least one non-available state
- WHEN staff read the summary next to the per-metric states
- THEN every state named in the summary matches the state disclosed for that same metric

### Requirement: Percentile Minimum Sample Size

The system MUST suppress `annual.percentile` when baseline years available for the comparison date fall below a defined minimum, disclosing an insufficient-sample reason distinct from coverage or quality suppression.

#### Scenario: February 29 rank on a small sample

- GIVEN the comparison date is February 29 with only ~7 contributing baseline years
- WHEN percentile is computed
- THEN the system suppresses it for insufficient sample size, not as a misleading rank

### Requirement: Campaign Display Preset

The system MAY offer a "campaign since September 1" display preset that reformats an existing calendar-year analysis for viewing. It MUST NOT be offered or accepted as an analysis period, and results MUST remain labelled as derived from the underlying calendar-year analysis.

#### Scenario: Preset does not change the analysis period

- GIVEN staff apply the campaign display preset to a calendar-year analysis
- WHEN it renders
- THEN values are reformatted from that analysis, not requested as a new period

### Requirement: Friendly Report Export (xlsx)

The system MUST provide a staff-gated xlsx export with a Resumen sheet and a Serie diaria sheet, under the same authorization boundary as the existing CSV export. Partial, suppressed, unavailable, and provisional states MUST carry the same meaning as displayed and CSV values. The existing audit CSV route and contract MUST remain unchanged.

#### Scenario: Authorized export includes both sheets

- GIVEN authorized staff view an analysis
- WHEN they request the xlsx export
- THEN the file contains Resumen and Serie diaria sheets with non-complete states shown by state and reason, not zero

#### Scenario: Unauthorized export is denied

- GIVEN a requester lacks Rainfall v2 technical authorization
- WHEN they request the xlsx export
- THEN the system denies it

### Requirement: Chart Discloses Comparison Date and Freshness

The year-vs-normal chart MUST visibly disclose both the comparison end date and the freshness of the evidence alongside the plotted series. Freshness MUST be disclosed as the **last day with evidence** — `available_through − 1 day` — because `available_through` is the EXCLUSIVE end of the disclosure window and no daily point is ever emitted on it; the raw exclusive value MUST NOT be presented as a day the analysis has evidence for.

The daily series served for a stored analysis revision MUST either match that revision's data (`data_revision`) or disclose the inconsistency deterministically in the response, and the revision's own `data_revision` MUST be disclosed with the analysis so the mismatch is detectable by the consumer. A series that no longer matches its revision MUST NOT be presented as if it did, in the chart or in the exported file.

#### Scenario: Chart shows both dates

- GIVEN staff view the year-vs-normal chart for the current year
- WHEN it renders
- THEN it displays the comparison end date and the last day with evidence (`available_through − 1 day`) together with the plotted totals
- AND the raw exclusive `available_through` value is not shown

#### Scenario: Daily data was corrected after the analysis was stored

- GIVEN a stored analysis revision for the current year
- AND the underlying daily values inside that analysis window were later corrected
- WHEN the daily series for that revision is served
- THEN the response reports that it is no longer consistent with the revision, with a reason
- AND the chart shows the series together with that disclosure, and the xlsx export records it

#### Scenario: Series still matches its revision

- GIVEN a stored analysis revision whose underlying daily values have not changed
- WHEN the daily series for that revision is served
- THEN the response reports it as consistent with the revision, with no inconsistency reason
