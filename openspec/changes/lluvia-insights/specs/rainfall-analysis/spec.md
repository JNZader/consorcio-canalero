# Delta for rainfall-analysis

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

The year-vs-normal chart MUST visibly disclose both the comparison end date and `available_through` alongside the plotted series.

The daily series served for a stored analysis revision MUST either match that revision's data (`data_revision`) or disclose the inconsistency deterministically in the response, and the revision's own `data_revision` MUST be disclosed with the analysis so the mismatch is detectable by the consumer. A series that no longer matches its revision MUST NOT be presented as if it did, in the chart or in the exported file.

#### Scenario: Chart shows both dates

- GIVEN staff view the year-vs-normal chart for the current year
- WHEN it renders
- THEN it displays the comparison end date and `available_through` together with the plotted totals

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
