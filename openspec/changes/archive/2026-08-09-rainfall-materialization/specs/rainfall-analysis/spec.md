# Delta for rainfall-analysis

## ADDED Requirements

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

## MODIFIED Requirements

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
