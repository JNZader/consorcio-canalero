# Rainfall Analysis Specification

## Purpose

Provide authenticated Consorcio technical staff with provenance-rich, calendar-year rainfall analysis from the territorial ficha. The capability delivers auditable regional results for stable operational zones and basins while preserving the existing compact public 1991–2020 normal. A materialized 1991–2020 baseline lets the capability serve the selected year against its normal, its historical percentile and its 7/30/90-day antecedents in one view, with a narrative summary and staff-gated CSV and xlsx exports that carry the same states as the screen.

## Requirements

### Requirement: Authenticated Technical Rainfall Detail

The system MUST make detailed Rainfall v2 analysis available only to authenticated Consorcio technical staff from the territorial ficha. The system MUST NOT create a dedicated Rainfall v2 page in this release. The existing compact public 1991–2020 monthly normal MUST remain available without requiring this technical detail.

When the public 1991–2020 normal is the only rainfall content available to a reader, it MUST be readable without that reader first operating a disclosure control.

(Previously: silent on whether the public normal could be placed behind a collapsed disclosure.)

#### Scenario: Authorized staff opens technical detail

- GIVEN an authenticated user authorized as Consorcio technical staff is viewing a territorial ficha
- WHEN the user opens Rainfall v2 detail
- THEN the system displays the technical rainfall analysis controls and results in that ficha

#### Scenario: Unauthenticated visitor views public rainfall content

- GIVEN an unauthenticated visitor is viewing public territorial content
- WHEN the visitor accesses the rainfall area
- THEN the system displays the existing compact public 1991–2020 normal when it is available
- AND the system does not expose Rainfall v2 technical detail or its export

#### Scenario: Authenticated user without technical authorization requests detail

- GIVEN an authenticated user without authorization for Consorcio technical rainfall detail
- WHEN the user requests Rainfall v2 detail
- THEN the system denies the technical result
- AND the response does not reveal restricted metric values or export data

#### Scenario: Non-technical reader lands on the rainfall area

- GIVEN a reader without technical authorization, for whom the public normal is the only rainfall content
- WHEN the rainfall area renders
- THEN the public normal is already readable with no disclosure control operated
- AND no Rainfall v2 detail, control or export is presented

### Requirement: Supported Analysis Scope and Parcel Semantics

The Rainfall v2 contract MUST represent `zone`, `basin`, `parcel`, and `geometry` scopes. This release MUST execute detailed analysis for stable operational zones and basins only. A parcel request MUST resolve to its associated zone or basin and MUST allow the user to switch between the available resolved regional scopes. Every parcel-originated detailed result MUST be labelled as a regional estimate. The system MUST NOT execute direct parcel or arbitrary-geometry rainfall computation in this release.

#### Scenario: Zone analysis is selected

- GIVEN a stable operational zone is selected in a territorial ficha
- WHEN authorized staff request Rainfall v2 analysis
- THEN the system returns the zone's regional rainfall analysis
- AND identifies the spatial scope as `zone`

#### Scenario: Parcel resolves to a regional scope

- GIVEN a parcel has an associated zone and basin
- WHEN authorized staff open Rainfall v2 detail from that parcel's ficha
- THEN the system offers the resolved zone and basin as selectable analysis scopes
- AND labels the displayed result as a regional estimate

#### Scenario: Staff switch a parcel-originated result from zone to basin

- GIVEN Rainfall v2 detail was opened from a parcel and both resolved scopes are available
- WHEN staff select the basin scope
- THEN the system replaces the displayed result with the basin result
- AND retains the regional-estimate label

#### Scenario: Direct geometry execution is requested

- GIVEN a request identifies `parcel` or `geometry` as the direct computation target
- WHEN detailed Rainfall v2 analysis is requested
- THEN the system reports that direct computation for that target is unavailable in this release
- AND does not return a rainfall metric presented as a parcel or arbitrary-geometry measurement

### Requirement: Calendar-Year Comparison and Baseline

The system MUST support calendar-year selection only. It MUST compare the selected year against a fixed 1991–2020 normal and percentile baseline. The result MUST present selected-year cumulative rainfall and the corresponding normal in one view. For the current calendar year, it MUST also present a same-date comparison so the selected-year and normal periods end on the same calendar date. Agricultural and hydrological campaign periods MUST NOT be offered as analysis periods.

#### Scenario: Historical calendar year is compared with the normal

- GIVEN staff select a completed calendar year for a supported zone or basin
- WHEN the analysis is available
- THEN the result shows that year's cumulative rainfall and the 1991–2020 normal in one view
- AND identifies the selected calendar-year interval and baseline interval

#### Scenario: Current year uses a same-date comparison

- GIVEN staff select the current calendar year on a date before year end
- WHEN the analysis is available
- THEN the result compares rainfall accumulated through that date with the normal accumulated through the same month and day
- AND identifies the comparison end date

#### Scenario: Non-calendar campaign period is requested

- GIVEN staff attempt to select an agricultural or hydrological campaign period
- WHEN the request is submitted
- THEN the system rejects the period as unsupported
- AND does not substitute a calendar-year result without identifying it

### Requirement: Percentile Minimum Sample Size

The system MUST suppress `annual.percentile` when baseline years available for the comparison date fall below a defined minimum, disclosing an insufficient-sample reason distinct from coverage or quality suppression.

#### Scenario: February 29 rank on a small sample

- GIVEN the comparison date is February 29 with only ~7 contributing baseline years
- WHEN percentile is computed
- THEN the system suppresses it for insufficient sample size, not as a misleading rank

### Requirement: Percentile Requires the Selected Year's Own Evidence

The system MUST suppress `annual.percentile` when the selected year's evidence inside the disclosed comparison window is itself incomplete — the rank sums only the intervals that are present and places the selected year inside a sample whose baseline years each had to clear their own completeness floor to participate — and MUST disclose a reason distinct from the baseline sample-size and baseline-evidence reasons. Suppression MUST NOT depend on `annual.selected` remaining suppressed: a selected-year total that still clears its own disclosure threshold can be short by enough days to move the rank materially. `annual.normal` is unaffected, being a baseline average that ranks nothing.

#### Scenario: Selected year is missing days inside the comparison window

- GIVEN the selected year is missing days inside the disclosed comparison window
- WHEN the percentile is computed
- THEN the system suppresses it with a selected-evidence reason, even when the selected-year cumulative total is still presented
- AND still presents the 1991–2020 normal

### Requirement: Campaign Display Preset

The system MAY offer a "campaign since September 1" display preset that reformats an existing calendar-year analysis for viewing. It MUST NOT be offered or accepted as an analysis period, and results MUST remain labelled as derived from the underlying calendar-year analysis.

#### Scenario: Preset does not change the analysis period

- GIVEN staff apply the campaign display preset to a calendar-year analysis
- WHEN it renders
- THEN values are reformatted from that analysis, not requested as a new period

### Requirement: Required Rainfall Outcomes

For every supported analysis scope and selected calendar year, the system MUST expose, when available under the applicable quality policy: selected-year and normal cumulative totals, historical percentile, 7-day, 30-day, and 90-day antecedent rainfall, and a report-style summary. The summary MUST distinguish available, partial, suppressed, and unavailable outcomes rather than treating them as equivalent.

#### Scenario: Complete analysis returns required outcomes

- GIVEN a supported scope has complete eligible data for the selected year and antecedent windows
- WHEN staff request analysis
- THEN the result includes selected-year and normal cumulative totals, historical percentile, and 7-day, 30-day, and 90-day antecedent rainfall
- AND includes a report-style summary of those outcomes and their states

#### Scenario: Antecedent window crosses the year boundary

- GIVEN staff request a 30-day antecedent metric on an early calendar date
- WHEN eligible data covers the full 30-day window across the preceding year boundary
- THEN the system returns the 30-day antecedent rainfall for the full requested window
- AND identifies the interval start and end

#### Scenario: A required outcome is not available

- GIVEN a required rainfall outcome cannot be produced from an eligible source
- WHEN staff view the analysis
- THEN the system marks that outcome as unavailable with its reason
- AND continues to show independent eligible outcomes

### Requirement: Summary Coheres with the Disclosed Metric States

The report summary is a narrative, not a measured metric, and therefore carries no coverage or quality threshold. It MUST be derived from the same disclosed metric states the system serves — the states produced after the approved metric policy is applied — and MUST NOT be derived from build-time completeness. The summary MUST NOT describe a metric in a state that contradicts the state disclosed for that metric alongside it.

The audit CSV export projects metric rows only and structurally carries no summary. This requirement therefore governs the channels that do carry it — the JSON envelope and the xlsx Resumen sheet — and MUST NOT be read as requiring a summary in the CSV export, whose contract is fixed by "CSV Export Parity" and "Friendly Report Export (xlsx)".

#### Scenario: Policy suppresses a metric the raw data would have supported

- GIVEN a metric whose build-time completeness would read as available
- AND the approved policy suppresses that metric at disclosure
- WHEN the analysis is served as JSON or in the xlsx Resumen sheet
- THEN the summary describes that metric as suppressed with its disclosed reason, and never as an available value

#### Scenario: Summary and badges cannot disagree

- GIVEN an analysis whose disclosed metrics include at least one non-available state
- WHEN staff read the summary next to the per-metric states
- THEN every state named in the summary matches the state disclosed for that same metric

### Requirement: Metric Provenance and State Metadata

Every displayed metric and every exported metric MUST include source class and identifier, method, nominal resolution, spatial scope, interval start and end, freshness, `available_through`, coverage, completeness, quality, provisional or final state, revision, chosen source, fallback use, and relevant source discrepancies. The system MUST preserve at least `observed_station`, `estimated_radar`, and `estimated_satellite` as distinct source classes. Nominal grid resolution MUST NOT be represented as parcel-level accuracy.

The displayed view MUST render, reachable by operating at most one disclosure control — not necessarily the same control for every field — every field of this enumerated floor that the served snapshot carries: at the metric — source class, source identifier, method, nominal resolution, aggregation, spatial scope, interval start, interval end, freshness, `available_through`, coverage, completeness, quality, discrepancies, provisional or final state, revision and fallback use; and at the analysis — source health. Source health is a property of the analysis, not of a metric, and MUST be rendered once for the analysis rather than repeated per metric.

A field the served snapshot does not carry MUST NOT be fabricated, and MUST NOT be rendered as an empty or placeholder value; it is simply absent from the view. `available_through` MUST NOT be rendered as evidence for a metric that carries none, because the disclosure window has a value even when nothing was published. The enumerated floor's `available_through` entry is satisfied by the metric's evidence statement: where the metric's evidence cannot be established, the view renders NO date rather than the raw window bound, and that absence discharges the entry rather than violating it. A metric whose value is suppressed by policy is NOT a metric without evidence: its coverage and provenance are still served, and its `available_through` MUST still be rendered as its last day with evidence.

Provenance MAY be presented once for a displayed set of metrics when source class, source identifier, nominal resolution and revision are identical across that set. Any metric whose source, resolution, revision, `fallback_used`, coverage or discrepancies diverge from that consolidated presentation MUST surface its own values at the metric.

When two rainfall normals of different spatial scope are displayed adjacently, each MUST be labelled with its own scope.

(Previously: required provenance per displayed metric, silent on consolidation for a homogeneous set, on adjacent normals of different scope, on whether a served field may go unrendered, and on whether policy suppression removes a metric's evidence. The rendering floor is now an enumerated list bound to what the snapshot serves, instead of an unbounded "a served field MUST NOT remain unrendered" that named no fields and so could be neither satisfied nor falsified; source health is placed at the analysis, where it is served; and suppression of a value is stated to be distinct from absence of evidence, because the served metric keeps its coverage and provenance.)

#### Scenario: Displayed metric exposes complete provenance

- GIVEN a rainfall metric is displayed to staff
- WHEN staff inspect its metadata, operating at most one disclosure control
- THEN the system exposes every enumerated field the snapshot carries for that metric, including interval start, interval end, freshness, `available_through`, completeness, quality and discrepancies
- AND states the metric's spatial scope and nominal resolution separately
- AND source health, when served, is rendered once for the analysis rather than once per metric

#### Scenario: An enumerated field is not served

- GIVEN the served snapshot carries no value for one of the enumerated fields
- WHEN the analysis renders with every disclosure control operated
- THEN that field is absent from the view
- AND no empty, placeholder or invented value is presented in its place

#### Scenario: The disclosure window has a value but nothing was published

- GIVEN a metric whose analysis published no interval, so its `available_through` carries the window's fallback bound
- WHEN its provenance renders
- THEN the view states that no day with published evidence exists for it
- AND does not present that bound as a day the metric has evidence for

#### Scenario: A policy-suppressed metric keeps its freshness

- GIVEN a metric suppressed for coverage below the served threshold, whose coverage and `available_through` are still served
- WHEN its provenance renders
- THEN the view states its last day with evidence
- AND does not state that no day with published evidence exists for it
- AND its value remains withheld with its suppression reason

#### Scenario: Gridded result is viewed from a parcel ficha

- GIVEN a parcel-originated view displays a gridded regional estimate
- WHEN staff inspect the displayed metric
- THEN the system labels it as a regional estimate
- AND does not describe nominal grid resolution as parcel-level accuracy

#### Scenario: Metadata cannot be established

- GIVEN a source returns a numeric value without one or more required provenance or state fields
- WHEN the metric would otherwise be displayed or exported
- THEN the system marks the metric unavailable or suppressed according to its applicable policy
- AND does not present the numeric value as a fully qualified result

#### Scenario: Homogeneous displayed set consolidates provenance once

- GIVEN every displayed metric shares source class, source identifier, nominal resolution and revision
- WHEN the analysis renders
- THEN that provenance is presented once for the set
- AND no required field of any metric in the set becomes unreachable

#### Scenario: Divergent metric keeps its own provenance

- GIVEN a displayed set where one metric used a fallback source, a different revision or a different coverage than the rest
- WHEN the analysis renders
- THEN that metric surfaces its own source, revision, `fallback_used`, coverage and discrepancies at the metric
- AND the consolidated presentation states only what is identical across the remaining set

#### Scenario: Two normals of different scope are shown together

- GIVEN a parcel-scope normal and a zone-scope normal are displayed adjacently
- WHEN they render
- THEN each is labelled with its own spatial scope
- AND neither is presented as the other's value

### Requirement: Partial, Suppressed, and Unavailable Data States

The system MUST visibly distinguish partial data, suppressed metrics, and unavailable metrics. A partial metric MUST expose its coverage and completeness state. A completeness-sensitive derived metric MUST be suppressed when its applicable coverage or quality policy is not satisfied. Suppression MUST identify the applicable failure reason and MUST NOT be rendered as zero or as an unavailable-source failure.

#### Scenario: Partial base metric remains visible

- GIVEN an eligible source provides a base rainfall metric with partial coverage
- WHEN the applicable policy permits its display
- THEN the system displays the metric as partial
- AND shows its coverage, completeness, quality, and interval metadata

#### Scenario: Completeness-sensitive metric is suppressed

- GIVEN the applicable policy requires complete data for a derived metric
- WHEN the source data fails that policy
- THEN the system suppresses the derived metric
- AND identifies the coverage or quality condition that caused suppression

#### Scenario: No eligible source exists

- GIVEN no eligible source can provide a requested metric
- WHEN staff view the analysis
- THEN the system marks the metric unavailable
- AND does not label the state as partial or suppressed

### Requirement: Policy Thresholds for New Metrics

Every metric published under `annual.normal`, `annual.percentile`, and `antecedents.{d7,d30,d90}` MUST have a coverage and quality threshold in `RAINFALL_METRIC_POLICY` before being served; the revision MUST be bumped when thresholds are added.

#### Scenario: Complete analysis has no unthresholded metric

- GIVEN eligible data satisfies each new metric's threshold
- WHEN an analysis builds
- THEN no required outcome is suppressed as `policy_threshold_unset`

### Requirement: Provisional Data and Revision Visibility

The system MAY display provisional data to authorized technical staff only when it has an explicit provisional badge and complete required metadata. When final or permanent data replaces provisional data, the system MUST make the later revision visible and MUST identify the revision and state of the result being viewed.

#### Scenario: Provisional result is displayed

- GIVEN an eligible source provides a provisional rainfall metric
- WHEN authorized staff view the metric
- THEN the system displays a provisional badge
- AND exposes its freshness, `available_through`, and revision metadata

#### Scenario: Final revision replaces provisional data

- GIVEN staff previously viewed a provisional result for a metric interval
- WHEN final or permanent data for that interval becomes available
- THEN subsequent retrieval identifies the result as final or permanent
- AND exposes the revision that replaced the provisional result

### Requirement: Deterministic Multi-Source Selection and Fallback

The system MUST use a validated, metric-specific source policy with an ordered fallback sequence. It MUST select at most one chosen source for each metric result and MUST NOT silently average, reconcile, or invent gap-filled values across sources. A preferred-source failure MUST NOT block independent valid metrics or a valid ordered fallback. The result MUST record `fallback_used` and relevant discrepancies for audit.

#### Scenario: Preferred source succeeds

- GIVEN the preferred eligible source returns a metric that passes its source policy
- WHEN the metric is requested
- THEN the system uses that source as the chosen source
- AND records `fallback_used` as false

#### Scenario: Preferred source fails and validated fallback succeeds

- GIVEN the preferred source is unavailable or fails its source policy for one metric
- AND an ordered validated fallback is available for that metric
- WHEN staff request analysis
- THEN the system returns the metric from that fallback
- AND records the chosen source, `fallback_used`, and the preferred-source failure
- AND continues to return independent valid metrics

#### Scenario: Sources disagree without a valid reconciliation policy

- GIVEN two eligible candidate sources produce materially discrepant values for the same metric interval
- WHEN the source policy selects one source
- THEN the system returns only the policy-selected source value
- AND exposes the relevant discrepancy
- AND does not average or otherwise merge the two values

### Requirement: Source Eligibility Validation Gate

Before a candidate source is eligible as a preferred source or fallback, the system MUST record a known-event source-resolution validation outcome for that source and role. The validation MUST cover access, licence, units, time-window boundaries, cadence, completeness, provisional-to-final revisions, corridor coverage, quality, and representative known events. It MUST evaluate available radar, SQPE/CHIRPS, IMERG, PERSIANN, and accessible gauges; it MUST NOT require scraping rendered images. A source that fails any required validation criterion for a role MUST NOT be eligible for that role.

#### Scenario: Candidate source passes validation

- GIVEN a candidate source has been evaluated for a metric role against representative known events
- WHEN the validation records passing results for all required criteria
- THEN the source may be marked eligible for that role
- AND its validation outcome is available for audit

#### Scenario: Candidate source fails an eligibility criterion

- GIVEN a candidate source fails access, licence, units, boundaries, cadence, completeness, revision, corridor coverage, or quality validation for a role
- WHEN source selection is performed for that role
- THEN the system excludes that source as a preferred source and fallback
- AND records the failed eligibility criterion

#### Scenario: Rendered imagery is the only candidate access path

- GIVEN a candidate source can only be obtained by scraping rendered imagery
- WHEN the validation gate is evaluated
- THEN the system marks the candidate ineligible
- AND does not use it for Rainfall v2 metrics

### Requirement: Interval Persistence on Ingest

The system MUST persist every `SourceInterval` fetched by `ingest_source_scope` into `rainfall_interval_value`, using `INSERT .. ON CONFLICT DO NOTHING` keyed on `uq_rainfall_interval_revision`. Re-running an identical ingest MUST NOT create duplicate rows and MUST NOT raise.

#### Scenario: Ingest persists fetched intervals
- GIVEN ingest fetches a `SourceBatch` for a scope/source/revision
- WHEN ingest completes
- THEN each interval is written to `rainfall_interval_value`

#### Scenario: Re-ingest is idempotent
- GIVEN intervals already exist for that scope/source/revision
- WHEN the identical ingest runs again
- THEN no duplicate rows are created and no error is raised

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

### Requirement: Analysis Materialization and Chained Resolution

After ingest reaches `done`, in the same processing cycle the system MUST run `build_analysis`, reading persisted intervals and writing exactly one `rainfall_analysis_revision` keyed by the outbox row's `request_fingerprint`. `rainfall_outbox` MUST gain a nullable `request_fingerprint` column, populated at enqueue time. The written snapshot MUST pass `normalize_snapshot`. A 202 from `POST /api/v2/geo/rainfall/analyses` MUST resolve to 200 with that snapshot within one processing cycle, without changing the existing 202/200 response envelope or the CSV export contract.

#### Scenario: Ingest done triggers materialization within one cycle
- GIVEN an outbox row reaches `done` with `request_fingerprint` set
- WHEN `build_analysis` runs
- THEN it writes a revision for that fingerprint and a later poll returns 200

#### Scenario: Invalid snapshot preserves the existing failure contract
- GIVEN a built snapshot fails `normalize_snapshot`
- WHEN the analysis is polled
- THEN the existing failure response is preserved unchanged, not silently served as 200

### Requirement: Current-Year Re-materialization Cadence

For the current calendar year the system MUST re-materialize every already-materialized analysis key on a recurring daily schedule, so that a stored snapshot never becomes the permanent answer for a year that is still accumulating. The scheduled sweep MUST re-enqueue outbox work for each current-year key that has already completed, MUST recompute the comparison end date at each build, and MUST write a new `rainfall_analysis_revision` whenever the resolved interval values or the disclosed comparison end differ from the stored revision. A later poll of the same request MUST be served the newest revision, without changing the request's fingerprint. Completed calendar years MUST NOT be re-materialized by this daily refresh, because re-running the same source over a fixed comparison end can produce no new information. This exemption covers freshness only; the one-off provisional-to-final transition owed to a completed year is specified separately under "Year-Rollover Finalization".

#### Scenario: Current-year snapshot is refreshed on the next day

- GIVEN a current-year key was materialized on day D and its snapshot reports comparison end D
- WHEN the daily re-materialization runs on day D+1 and the analysis is polled again
- THEN the poll returns a snapshot whose comparison end is D+1
- AND the earlier revision is retained rather than overwritten

#### Scenario: Newly published days enter the refreshed snapshot

- GIVEN the provider publishes intervals for days that did not exist at first materialization
- WHEN the current-year key is re-materialized
- THEN those intervals are persisted and included in the refreshed snapshot's totals and evidence

#### Scenario: Completed year is not refreshed for freshness

- GIVEN an analysis key for a completed calendar year
- WHEN the daily re-materialization runs
- THEN no daily-refresh work is enqueued for that key
- AND no provider fetch is spent on refreshing its comparison end

#### Scenario: In-flight refresh is not duplicated

- GIVEN a re-materialization for a key is still pending
- WHEN the daily sweep runs again
- THEN no second pending work item is created for that key

### Requirement: Year-Rollover Finalization

An analysis key first materialized while its calendar year was still running is served from a provisional satellite source. Once that year completes, the system MUST transition the key to the final historical source as soon as that source's data for the year is adequate under the applicable quality policy, so the stored answer stops being provisional. Because the request fingerprint does not encode the source or role, and a poll is served from any stored snapshot without re-resolving them, this transition MUST be performed by a scheduled sweep rather than by the request path.

The sweep MUST select completed-year keys by the temporal state and chosen source disclosed in the snapshot currently being served, not by the history of previously enqueued work, and MUST re-resolve the source and role for the enqueued transition rather than reusing the completed key's provisional source. The enqueued transition MUST preserve the request's fingerprint unchanged.

The system MUST NOT replace a served snapshot with a final-source snapshot that its own quality policy would suppress; while the final source's data is not yet adequate, the provisional snapshot MUST remain the served answer, and the sweep MUST keep attempting the transition on its recurring schedule rather than treating a refused attempt as completed. Once an adequate final-source revision has been written and is served, the sweep MUST stop enqueueing transitions for that key. The system MUST NOT write a provisional revision that would shadow an already-served final revision for the same request. While a transition is pending, the system MUST NOT spend more than one provider fetch per key per scheduled run.

#### Scenario: Transition is enqueued after the year completes

- GIVEN a key was materialized during its calendar year and its served snapshot reports a provisional state from the satellite source
- WHEN the scheduled sweep runs after that calendar year has completed
- THEN work is enqueued for that key against the final historical source
- AND the enqueued work carries the same request fingerprint as the served snapshot

#### Scenario: Final revision becomes the served answer

- GIVEN the final historical source publishes adequate data for that completed year
- WHEN the enqueued transition is processed and the analysis is polled again
- THEN the poll returns a snapshot identified as final and sourced from the final historical source
- AND the earlier provisional revision is retained rather than overwritten

#### Scenario: Inadequate final data does not replace the served snapshot

- GIVEN the final historical source's data for that year would be suppressed by the applicable quality policy
- WHEN the transition is processed
- THEN no new analysis revision is written
- AND a poll still returns the previously served provisional snapshot with its provisional state

#### Scenario: A refused transition is retried, not abandoned

- GIVEN a transition attempt was refused because the final source's data was inadequate
- WHEN the scheduled sweep runs again
- THEN work is enqueued for that key again
- AND the key keeps being selected until an adequate final revision is served

#### Scenario: An adequate final revision terminates the sweep for that key

- GIVEN a final-source revision is written and served for a completed-year key
- WHEN the scheduled sweep runs again
- THEN no transition work is enqueued for that key
- AND no provider fetch is spent on it

#### Scenario: A late provisional build does not shadow a finalized year

- GIVEN a final revision is being served for a completed-year request
- WHEN a provisional satellite build for that same request is processed afterwards
- THEN no new revision is written
- AND a poll still returns the final revision

#### Scenario: A pending transition is bounded to one fetch per run

- GIVEN a completed-year key whose transition is still pending
- WHEN the scheduled sweep runs
- THEN at most one transition work item exists for that key
- AND at most one provider fetch is spent on it for that run

### Requirement: Provider Correction Supersession Within a Revision

When a provider restates the value of an interval it has already published, without changing its provider revision identifier, the system MUST record the corrected value as new append-only evidence, MUST retain the superseded value, MUST record the supersession in `rainfall_interval_lifecycle` identifying the superseding row, and MUST resolve exactly one non-superseded value per interval slot when computing a snapshot. The system MUST NOT discard the correction, MUST NOT mutate or delete the superseded row, and MUST NOT include both values in the same computed total. A re-fetch whose value is unchanged MUST NOT create a new interval row or a lifecycle row.

#### Scenario: Restated value is stored without losing the original

- GIVEN an interval was persisted with a provisional value
- WHEN the same interval is re-fetched with a different value under the same provider revision identifier
- THEN the corrected value is persisted as a new interval row
- AND the original row is retained unchanged

#### Scenario: Supersession is recorded as evidence

- GIVEN a corrected interval row is persisted
- WHEN lifecycle evidence is inspected for the original row
- THEN it records the supersession and identifies the superseding row

#### Scenario: Computation resolves one value per interval

- GIVEN an interval slot has both an original and a corrected row
- WHEN a snapshot is computed for a window containing that interval
- THEN only the corrected value contributes to the result
- AND the total does not include both values

#### Scenario: Unchanged re-fetch writes nothing

- GIVEN an interval was persisted
- WHEN the same interval is re-fetched with an unchanged value
- THEN no new interval row and no lifecycle row are created

#### Scenario: Corrected value becomes visible as a later revision

- GIVEN staff previously viewed a snapshot built from the provisional value of an interval
- WHEN the correction is ingested and the analysis is re-materialized
- THEN a later analysis revision is written and served for that request
- AND it identifies the revision behind the result being viewed

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

### Requirement: GEE Quota Guards on Request-Path Re-enqueue and Poll

This requirement governs the **request path only**. `queue_missing_analysis` — the enqueue path reached from `POST /api/v2/geo/rainfall/analyses` — MUST NOT enqueue new work when a recent `done` row already exists for the same key. A poll for a key that already has a materialized `rainfall_analysis_revision` MUST be served from that stored revision.

The scheduled sweeps ("Current-Year Re-materialization Cadence" and "Year-Rollover Finalization") enqueue through a distinct mechanism that does not pass through `queue_missing_analysis`, and their deliberate re-enqueue of an already-`done` key MUST NOT be read as a violation of this requirement. Their quota is bounded by their own cadence and per-key limits, stated in their own requirements: at most one work item and one provider fetch per key per scheduled run.

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

### Requirement: Snapshot Evidence Computed at Build Time

`build_analysis` MUST compute coverage, completeness, and quality for each snapshot metric from the persisted `rainfall_interval_value` rows used in that build, so `apply_metric_policy` reads them from the snapshot per the existing provenance requirement (spec.md:117).

#### Scenario: Metric evidence reflects persisted rows
- GIVEN a metric is built from N persisted interval rows
- WHEN the snapshot is written
- THEN that metric's coverage, completeness, and quality reflect those rows

### Requirement: Operational Robustness of the Materialization Path

The validation-role source identifier MUST be `smn-gauge` consistently across the validation-role constant and source manifests. A race between two identical `POST /api/v2/geo/rainfall/analyses` requests MUST NOT surface an `IntegrityError` as a 500; both callers MUST receive the standard 202 envelope.

#### Scenario: Validation identifier matches its manifest
- GIVEN the validation-role constant and the source manifest are compared
- WHEN either is inspected
- THEN both identify the source as `smn-gauge`

#### Scenario: Concurrent identical POST does not surface a 500
- GIVEN two identical POST requests race on the same enqueue key
- WHEN both reach `queue_missing_analysis` concurrently
- THEN the resulting `IntegrityError` is caught and both callers receive a 202 response

### Requirement: Evidence-Gated Source Roles

The system MUST treat candidate source roles as evidence-gated rather than as unconditional provider guarantees. Historical normal and percentile metrics MUST use CHIRPS v3 Final only after validation, with validated alternatives permitted for continuity or benchmarking. Daily operational metrics MAY use SQPE-OBS only after validation and MAY use validated CHIRPS v3 or other satellite fallbacks. High-resolution zonal intensity MAY use validated SINARAME RQPE radar/Alejandro Roca and MUST use a validated fallback such as IMERG V07 when the preferred candidate is ineligible or unavailable; PERSIANN remains a secondary candidate. Accessible SMN, BCC, or INA gauges MAY be used for point validation or observation. The system MUST NOT use CHIRPS v2 as the future Rainfall v2 historical/climatology contract. As a deliberate, tracked deferral, the daily role MAY default to `chirps-v3-sat` under this MAY fallback clause even though no per-role eligibility outcome has yet been recorded for the daily role under "Source Eligibility Validation Gate"; this deferral MUST be recorded as outstanding technical debt, not treated as a completed validation.

(Previously: silent on what the daily role does while SQPE-OBS is unimplemented and no per-role eligibility record exists for the daily role.)

#### Scenario: Validated CHIRPS v3 Final supplies historical baseline

- GIVEN CHIRPS v3 Final passed validation for the historical role
- WHEN staff request a historical normal or percentile
- THEN the system may select CHIRPS v3 Final under the source policy
- AND identifies its final state and source metadata

#### Scenario: Operational candidate lacks validated access

- GIVEN SQPE-OBS has not passed validation for operational access or its requested window
- WHEN a daily operational metric is requested
- THEN the system does not select SQPE-OBS
- AND evaluates the ordered validated fallbacks

#### Scenario: High-resolution radar is unavailable

- GIVEN the high-resolution radar candidate is ineligible or unavailable for the requested intensity metric
- AND IMERG V07 has passed validation for the applicable fallback role
- WHEN staff request the metric
- THEN the system uses IMERG V07 as the fallback
- AND records fallback use and the radar candidate's state

#### Scenario: Daily role uses the documented default ahead of a per-role eligibility record
- GIVEN SQPE-OBS remains unimplemented and no per-role eligibility outcome has been recorded for the daily role
- WHEN a daily operational metric is requested
- THEN the system selects `chirps-v3-sat` as the documented interim default under the daily MAY fallback
- AND the selection is recorded as a tracked deviation from the Source Eligibility Validation Gate, not as a validated eligibility outcome

### Requirement: Intensity, Peak, and Duration Outcomes

When source cadence and coverage support the requested interval, the system MUST expose P30, P60, P3h, P24h, I30, I60, event duration, and peak window outcomes. Peak and duration outcomes MUST require every expected interval in the requested analysis window. When cadence, coverage, or quality policy does not support an intensity, peak, or duration outcome, the system MUST suppress that outcome with its reason while preserving independent available metrics.

#### Scenario: Complete sub-daily interval supports intensity metrics

- GIVEN an eligible source covers every expected interval needed for a requested P30 and I30 outcome
- WHEN staff request intensity analysis
- THEN the system returns the supported intensity outcomes with interval and source metadata

#### Scenario: Missing interval suppresses peak and duration

- GIVEN one or more expected intervals are missing from a requested peak or duration window
- WHEN staff request those outcomes
- THEN the system suppresses peak and duration outcomes
- AND identifies incomplete expected-interval coverage as the reason

#### Scenario: Daily-only source cannot support sub-daily intensity

- GIVEN the chosen source cadence cannot support P30, P60, P3h, I30, or I60
- WHEN staff request those outcomes
- THEN the system suppresses each unsupported outcome with a cadence reason
- AND may still return supported daily outcomes such as P24h

### Requirement: CSV Export Parity

The system MUST provide CSV export for authorized technical staff. CSV output MUST preserve the displayed metric values, state, spatial scope, interval, and all required provenance metadata. Exported partial, suppressed, unavailable, provisional, revised, and fallback states MUST have the same meaning as their displayed counterparts.

#### Scenario: Authorized staff export a complete analysis

- GIVEN authorized staff are viewing a complete Rainfall v2 analysis
- WHEN they export CSV
- THEN the CSV includes the displayed metrics and all required provenance and state metadata

#### Scenario: Export includes non-complete states

- GIVEN the displayed analysis includes partial, suppressed, unavailable, provisional, revised, or fallback metrics
- WHEN authorized staff export CSV
- THEN the CSV represents each metric's displayed state and reason where applicable
- AND does not replace suppressed or unavailable values with zero

#### Scenario: Unauthorized export is requested

- GIVEN a requester is not authorized for Rainfall v2 technical detail
- WHEN the requester requests its CSV export
- THEN the system denies the export
- AND does not disclose technical metric data

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

### Requirement: Explicit Exclusions and Reusable Outputs

Rainfall v2 MUST NOT provide surface-water or inundation mapping, Sentinel-1/2/Landsat analysis, SMAP soil moisture, NDVI/NDMI, flood prediction, return periods, rainfall event catalogues, entities, or polygons, before/after intervention analysis, SPI/ENSO, community-gauge deployment, groundwater analysis, agricultural campaigns, direct arbitrary-geometry execution, or a generic whole-database observation-model migration. It SHOULD produce provenance-rich rainfall time series that can be reused by later capabilities without defining those later capabilities in this specification.

#### Scenario: Excluded capability is requested from Rainfall v2

- GIVEN a user requests an excluded Rainfall v2 capability
- WHEN the request is evaluated
- THEN the system reports that the capability is outside Rainfall v2
- AND does not present a substituted analysis as if it were that capability

#### Scenario: Reusable time series is consumed by a future capability

- GIVEN a later capability is authorized to consume Rainfall v2 output
- WHEN it obtains a rainfall time series from Rainfall v2
- THEN the time series retains its provenance and state metadata
- AND this Rainfall v2 specification does not prescribe the later capability's behavior

### Requirement: Answer-First Rainfall Presentation Hierarchy

The rainfall view MUST present the contextualized answer for the selected year — historical percentile, selected-year accumulated total, normal accumulated to the same date, and freshness as the last day with evidence — before any historical or climatological context, and all four MUST be part of the always-visible answer surface rather than reachable only through a disclosure control.

The percentile MUST be the typographic headline and MUST NOT be repeated as a badged metric row on the same always-visible surface. Its restatement inside the chart's textual equivalent is NOT a duplication: "Progressive Disclosure Without Data Loss" requires that equivalent to remain rendered and complete, and the year's ranking against its baseline is one of the facts the plot conveys visually — a reader who cannot see the plot gets it only from the sentence, so removing it from there would leave a partial equivalent.

Freshness MUST be presented as the last day with evidence, using the same `available_through − 1 day` conversion "Chart Discloses Comparison Date and Freshness" defines. The view MUST NOT re-derive that conversion, and MUST derive it once per SUBJECT: the analysis' freshness, shown on the answer surface and in the per-metric disclosure, from the stored analysis; the plotted series' freshness, shown with the chart as that requirement demands, from the series response. Two derivations for the same subject are forbidden; one derivation per subject is required, because the analysis and the series it drew are different objects that can legitimately disagree — and when they do, that divergence MUST be disclosed rather than reconciled into a single number.

Whether a freshness claim may be made MUST be decided by the evidence the analysis carries, never by whether its value may be displayed. A metric whose value is suppressed by policy still has evidence and MUST show its freshness date. The statement that no day with published evidence exists MUST be reserved for an analysis whose disclosure window is genuinely empty, because that window carries a bound even when nothing was published. When the served analysis carries neither evidence nor proof of an empty window, the view MUST state that freshness is unavailable rather than assert either.

This delta MUST NOT introduce a dedicated Rainfall v2 page (the prohibition above stands), multi-year comparison, public exposure of Rainfall v2 detail, any backend or data-contract change, or a new runtime dependency.

#### Scenario: Answer is visible without scrolling on a phone

- GIVEN a staff reader on a 390×844 viewport with the ficha sheet at `medio`
- WHEN the rainfall view renders
- THEN the percentile headline and the selected-year accumulated total are inside the sheet's visible height with no scrolling
- AND the 1991–2020 climatological context is rendered after them

#### Scenario: Percentile is not duplicated

- GIVEN an analysis whose percentile is available
- WHEN the rainfall view renders
- THEN the percentile appears once as the typographic headline
- AND once inside the chart's textual equivalent, which must state the year's ranking to stay a complete equivalent
- AND no badged percentile metric row is present on the always-visible surface
- AND a suppressed or unavailable percentile is shown by state and reason, never as a number and never as zero

#### Scenario: Freshness is on the answer surface, derived once per subject

- GIVEN an analysis whose evidence ends before the comparison end date
- WHEN the rainfall view renders
- THEN the last day with evidence is stated on the always-visible answer surface, with no disclosure control operated
- AND it is the same conversion the chart requirement defines, applied once to the analysis
- AND the chart's own freshness statement, which describes the series it drew, is derived from the series response

#### Scenario: An analysis with no published evidence

- GIVEN an analysis that published no interval, whose disclosure window still carries a bound
- WHEN the rainfall view renders
- THEN the answer surface states that no day with published evidence exists for the analysis
- AND no date is presented as the analysis' last day with evidence

#### Scenario: The year's value is suppressed by policy but its evidence exists

- GIVEN an analysis whose selected-year total is suppressed with a coverage reason, and whose served coverage and `available_through` are present
- WHEN the rainfall view renders
- THEN the answer surface states that analysis' last day with evidence
- AND it does not state that no day with published evidence exists
- AND the suppressed total is shown by state and reason, never as a number and never as zero

#### Scenario: Freshness cannot be established

- GIVEN a served analysis whose selected-year metric carries neither evidence nor the reason that marks an empty disclosure window
- WHEN the rainfall view renders
- THEN the answer surface states that freshness is unavailable, with the served reason reachable
- AND it presents no date and does not state that no day with published evidence exists

### Requirement: Derived Interpretive Rainfall Label

Any interpretive label characterising the selected year (for example "año seco") MUST be derived solely from the served percentile, using cut-offs published with the label vocabulary, and MUST be presented as derived from that percentile. The view MUST NOT re-derive the label from raw totals, daily series or any other served value. When the percentile is suppressed or unavailable, no interpretive label MUST be presented.

#### Scenario: Label at a published cut-off boundary

- GIVEN a served percentile exactly at a published cut-off between two labels
- WHEN the label is derived
- THEN the label is the one the published cut-off assigns to that boundary value
- AND the same percentile always yields the same label

#### Scenario: Label is shown as derived

- GIVEN an available percentile
- WHEN the interpretive label renders
- THEN it is presented together with the percentile it was derived from

#### Scenario: Percentile is suppressed

- GIVEN the percentile is suppressed or unavailable with its reason
- WHEN the rainfall view renders
- THEN no interpretive label is presented
- AND the suppression reason is displayed

### Requirement: Progressive Disclosure Without Data Loss

Progressive disclosure MUST NOT remove information already served. A collapsed section MUST show its key values in the collapsed header. The textual equivalent of a visible chart MUST remain rendered while that chart is visible and MUST NOT be placed inside a collapsible region. It MUST also remain COMPLETE: it MUST state the facts the plot conveys visually — including the selected year's ranking against its baseline — so that a reader who cannot see the plot receives the same information rather than a subset of it. The system MUST render every metric group present in the served snapshot, including groups it does not recognise, with a visible fallback title rather than dropping them. The accessibility and honesty behaviour already required elsewhere is carried forward unchanged: state announcements for asynchronous updates, the chart's textual equivalent and its plotted-window description, the solid-versus-dashed distinction between evidenced and projected series, reuse of the last day with evidence per "Chart Discloses Comparison Date and Freshness", and never rendering a suppressed or unavailable value as zero per "Partial, Suppressed, and Unavailable Data States".

#### Scenario: Collapsed section still carries its numbers

- GIVEN the antecedent metrics (7-, 30- and 90-day) are in a collapsed section
- WHEN the rainfall view renders with that section closed
- THEN each antecedent's value or its non-available state is visible in the collapsed header
- AND expanding the section reveals the metrics' provenance and state metadata

#### Scenario: Visible chart keeps its textual equivalent

- GIVEN the year-versus-normal chart is visible
- WHEN the rainfall view renders in any disclosure state
- THEN the chart's textual equivalent is present in the accessibility tree
- AND it is not inside a region that unmounts when collapsed

#### Scenario: Unknown metric group is served

- GIVEN the served snapshot contains a metric group the view has no title for
- WHEN the rainfall view renders
- THEN that group's metrics are rendered under a visible fallback title
- AND no served metric is omitted from the displayed set

#### Scenario: Nothing served disappears

- GIVEN a snapshot fixture whose displayed metric set is known
- WHEN every disclosure control in the rainfall view is expanded
- THEN the rendered metric set matches the snapshot's displayed metric set
- AND each metric carries its state, reason and provenance
