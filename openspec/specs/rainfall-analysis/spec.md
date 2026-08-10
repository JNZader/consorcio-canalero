# Rainfall Analysis Specification

## Purpose

Provide authenticated Consorcio technical staff with provenance-rich, calendar-year rainfall analysis from the territorial ficha. The capability delivers auditable regional results for stable operational zones and basins while preserving the existing compact public 1991–2020 normal.

## Requirements

### Requirement: Authenticated Technical Rainfall Detail

The system MUST make detailed Rainfall v2 analysis available only to authenticated Consorcio technical staff from the territorial ficha. The system MUST NOT create a dedicated Rainfall v2 page in this release. The existing compact public 1991–2020 monthly normal MUST remain available without requiring this technical detail.

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

### Requirement: Metric Provenance and State Metadata

Every displayed metric and every exported metric MUST include source class and identifier, method, nominal resolution, spatial scope, interval start and end, freshness, `available_through`, coverage, completeness, quality, provisional or final state, revision, chosen source, fallback use, and relevant source discrepancies. The system MUST preserve at least `observed_station`, `estimated_radar`, and `estimated_satellite` as distinct source classes. Nominal grid resolution MUST NOT be represented as parcel-level accuracy.

#### Scenario: Displayed metric exposes complete provenance

- GIVEN a rainfall metric is displayed to staff
- WHEN staff inspect its metadata
- THEN the system exposes all required provenance and state fields for that metric
- AND states the metric's spatial scope and nominal resolution separately

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

### Requirement: GEE Quota Guards on Request-Path Re-enqueue and Poll

This requirement governs the **request path only**. `queue_missing_analysis` — the enqueue path reached from `POST /api/v2/geo/rainfall/analyses` — MUST NOT enqueue new work when a recent `done` row already exists for the same key. A poll for a key that already has a materialized `rainfall_analysis_revision` MUST be served from that stored revision with no new GEE fetch.

The scheduled sweeps ("Current-Year Re-materialization Cadence" and "Year-Rollover Finalization") enqueue through a distinct mechanism that does not pass through `queue_missing_analysis`, and their deliberate re-enqueue of an already-`done` key MUST NOT be read as a violation of this requirement. Their quota is bounded by their own cadence and per-key limits, stated in their own requirements: at most one work item and one provider fetch per key per scheduled run.

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
- THEN the stored revision is returned and no new GEE fetch is triggered

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
