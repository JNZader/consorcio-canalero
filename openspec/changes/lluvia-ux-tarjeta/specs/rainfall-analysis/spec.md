# Delta for rainfall-analysis

Presentation-only delta for change `lluvia-ux-tarjeta`. No data, state, export, metric-content, policy or route requirement changes. "Intensity, Peak, and Duration Outcomes" (`specs/rainfall-analysis/spec.md:607`) is untouched — only its dead display chrome is pruned. Proposal constraints R1–R7 are the acceptance floor.

## MODIFIED Requirements

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

## ADDED Requirements

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
