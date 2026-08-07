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

### Requirement: Evidence-Gated Source Roles

The system MUST treat candidate source roles as evidence-gated rather than as unconditional provider guarantees. Historical normal and percentile metrics MUST use CHIRPS v3 Final only after validation, with validated alternatives permitted for continuity or benchmarking. Daily operational metrics MAY use SQPE-OBS only after validation and MAY use validated CHIRPS v3 or other satellite fallbacks. High-resolution zonal intensity MAY use validated SINARAME RQPE radar/Alejandro Roca and MUST use a validated fallback such as IMERG V07 when the preferred candidate is ineligible or unavailable; PERSIANN remains a secondary candidate. Accessible SMN, BCC, or INA gauges MAY be used for point validation or observation. The system MUST NOT use CHIRPS v2 as the future Rainfall v2 historical/climatology contract.

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
