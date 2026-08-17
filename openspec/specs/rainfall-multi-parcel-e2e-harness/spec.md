# Rainfall Multi-Parcel E2E Harness Specification

## Purpose

This capability defines a deterministic, operator-only Chromium browser harness that proves same-tab rainfall continuity and fact freshness while selecting three distinct parcels through the production interaction path. It provides isolated follow-up evidence for `lluvia-ux-tarjeta` without changing that capability or production behavior.

## Normative Language

The terms **MUST**, **MUST NOT**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as RFC 2119 requirement levels.

## Requirements

### Requirement RMEH-001: Disposable Environment Identity and Write Safety

Before any bootstrap write, the harness **MUST** establish that every mutable target belongs to the current run, is isolated from shared or real environments, and carries an explicit disposable-environment marker. A marker that is absent, unknown, inconsistent with the target identity, or associated with a shared database **MUST** cause an abort before any write. The harness **MUST NOT** mutate shared data even when repair would otherwise be possible.

#### Scenario RMEH-001-A: Owned disposable stack is accepted

- **GIVEN** the database and related mutable resources are isolated for the current run
- **AND** their target identities match an explicit disposable-environment marker
- **WHEN** the bootstrap safety gate executes
- **THEN** the gate permits prerequisite inspection and repair within those owned resources
- **AND** records the validated ownership boundary in the run diagnostics

#### Scenario RMEH-001-B: Unknown or shared database marker aborts before writes

- **GIVEN** the target database marker is absent, unknown, or denotes a shared or real environment
- **WHEN** bootstrap is requested
- **THEN** the run aborts before migrations, schema changes, fixture writes, or service reconfiguration
- **AND** diagnostics name the unsafe database target and marker condition

#### Scenario RMEH-001-C: Marker and resource identity disagree

- **GIVEN** a disposable marker is present
- **BUT** the marked identity does not match one or more mutable target resources for the current run
- **WHEN** the safety gate validates the ownership boundary
- **THEN** the run aborts before writes
- **AND** no mismatched or shared resource is mutated

### Requirement RMEH-002: Self-Healing Prerequisites With Post-Repair Validation

Within a validated disposable boundary, bootstrap **MUST** inspect and, when absent or invalid, repair the required tables and migrations, `vt_parcelas_catastro`, exactly three fixture parcels, `suelos_catastro`, the Martin catalog/source/tile path, the backend rainfall feature flag, and frontend/backend reachability. Every prerequisite **MUST** be independently validated after any repair and before browser steps begin. Repair success **MUST NOT** be inferred solely from a successful command or service start.

#### Scenario RMEH-002-A: Missing disposable prerequisites are repaired and validated

- **GIVEN** the disposable boundary has been validated
- **AND** one or more required tables, migrations, views, parcels, soils, Martin resources, or feature settings are missing
- **WHEN** bootstrap repairs the missing prerequisites
- **THEN** each repaired prerequisite is re-read or otherwise independently validated
- **AND** browser execution starts only after all prerequisite validations pass

#### Scenario RMEH-002-B: Complete prerequisites remain idempotent

- **GIVEN** all prerequisites already satisfy the harness contract in the owned disposable stack
- **WHEN** bootstrap runs again
- **THEN** it preserves the same three fixture identities and facts
- **AND** it does not duplicate rows, sources, catalog entries, tiles, soils, or aliases

#### Scenario RMEH-002-C: Missing or empty Martin source fails closed

- **GIVEN** the Martin source, catalog entry, or required tile is missing or returns no usable parcel features after attempted repair
- **WHEN** post-repair validation runs
- **THEN** the harness aborts before browser steps
- **AND** diagnostics identify the failing Martin prerequisite as missing, empty, or unusable

#### Scenario RMEH-002-D: Reachability or feature readiness remains invalid

- **GIVEN** the frontend or backend is unreachable, or the rainfall feature flag is not effective after attempted repair
- **WHEN** post-repair validation runs
- **THEN** the harness aborts before browser steps
- **AND** diagnostics identify each unreachable endpoint or ineffective feature prerequisite

### Requirement RMEH-003: Deterministic Three-Parcel Fixture

The fixture **MUST** contain exactly three parcels identified as A, B, and C. Their geometries **MUST** be stable and derived from real parcel geometry while their operator identities and rainfall facts remain synthetic and controlled. At both target viewports, each parcel **MUST** provide a non-overlapping clickable point and clickable area. A, B, and C **MUST** each be rainfall-ready and pairwise distinct in semantic identity, rainfall scope, percentile, accumulation, and revision.

#### Scenario RMEH-003-A: Fixture cardinality and identities are stable

- **GIVEN** bootstrap has completed
- **WHEN** the fixture is inspected before browser launch
- **THEN** exactly one A, one B, and one C parcel exist
- **AND** their synthetic semantic identities match the declared deterministic fixture

#### Scenario RMEH-003-B: Facts are ready and pairwise distinct

- **GIVEN** A, B, and C are present
- **WHEN** their rainfall facts are validated
- **THEN** each parcel reports a ready answer
- **AND** identity, scope, percentile, accumulation, and revision are pairwise distinct across all three parcels

#### Scenario RMEH-003-C: Click targets do not overlap

- **GIVEN** the target mobile and desktop camera states
- **WHEN** parcel geometries are projected into each viewport
- **THEN** each declared click point lies within exactly one intended parcel clickable area
- **AND** no declared click point or clickable area is ambiguous with another fixture parcel

#### Scenario RMEH-003-D: Repeated bootstrap reproduces the same fixture

- **GIVEN** a successful bootstrap has already created the fixture
- **WHEN** bootstrap is repeated in the same disposable environment
- **THEN** A, B, and C retain the same identities, geometries, ready facts, and distinct scopes
- **AND** fixture cardinalities remain unchanged without row accumulation or alias creation

### Requirement RMEH-004: Projection and Target Integrity

The harness **MUST** enter the map through the supported `?lat=&lng=&zoom=` camera contract and derive click coordinates from the configured camera, current viewport, and Web Mercator/canvas projection. It **MUST** verify that each derived target is visible, unobstructed, and resolves uniquely to its intended parcel before relying on the click. Projection drift, clipping, occlusion, or target ambiguity **MUST** fail with diagnostics rather than be bypassed through production hooks or map internals.

#### Scenario RMEH-004-A: Supported camera yields valid parcel targets

- **GIVEN** the supported latitude, longitude, and zoom parameters and a target viewport
- **WHEN** the camera settles and A, B, and C targets are derived
- **THEN** every target maps to the intended projected parcel geometry
- **AND** every target is visible and unobstructed within the canvas interaction area

#### Scenario RMEH-004-B: Projection drift or occlusion aborts interaction

- **GIVEN** a derived point falls outside its intended parcel, inside another parcel, outside the interactive canvas, or beneath an occluding element
- **WHEN** target integrity is validated
- **THEN** the affected browser sequence fails before that click
- **AND** diagnostics identify the parcel, viewport, camera state, and failed integrity condition

#### Scenario RMEH-004-C: No production map seam is introduced

- **GIVEN** deterministic projection cannot be established through the supported camera and canvas contract
- **WHEN** the harness evaluates whether to continue
- **THEN** it stops with a projection diagnostic
- **AND** it **MUST NOT** require a production MapLibre exposure, route, property, or test hook to proceed

### Requirement RMEH-005: Production-Honest Parcel Interaction

Every transition **MUST** use a plain, unforced, single-parcel click that produces the supported `tipo=parcela` flow. The harness **MUST NOT** mutate application stores directly, force clicks, reload between selections, wait on a scale label, depend on arbitrary fixed pixels, use production test hooks, or use multi-select behavior. Browser success **MUST** be attributable to the same user-visible interaction and request path available to an operator.

#### Scenario RMEH-005-A: Plain click drives the parcel request path

- **GIVEN** a validated, unobstructed target for the next parcel
- **WHEN** the harness performs a normal single click
- **THEN** the resulting selection uses the supported parcel interaction with `tipo=parcela`
- **AND** the application updates through its production request and rendering path

#### Scenario RMEH-005-B: Sequence remains in one page session

- **GIVEN** A is selected in the rainfall tab
- **WHEN** the harness transitions A to B to C to A
- **THEN** all transitions occur without page reload or direct state replacement
- **AND** no multi-select state is used

#### Scenario RMEH-005-C: Forbidden interaction seam invalidates conformance

- **GIVEN** a harness implementation uses force-click, direct store mutation, an arbitrary fixed click pixel, a scale-label wait, a production hook, or a production-only test route or property
- **WHEN** conformance is assessed
- **THEN** the harness does not satisfy this specification
- **AND** its browser result **MUST NOT** be accepted as transition evidence

### Requirement RMEH-006: Ready Rainfall Contract and Fact Matching

Before browser steps, the harness **MUST** validate that each fixture parcel can produce a ready rainfall answer whose semantic identity, scope, percentile, accumulation, and revision exactly match that parcel's declared fixture facts. During browser execution, the displayed answer **MUST** match the most recently selected parcel's validated ready contract. A missing field, queued/error answer, mismatched identity, or non-ready response **MUST** fail rather than be normalized into a ready result.

#### Scenario RMEH-006-A: Pre-browser rainfall contracts match

- **GIVEN** the backend is reachable and the feature flag is effective
- **WHEN** A, B, and C rainfall contracts are validated
- **THEN** each contract is ready and complete
- **AND** each identity, scope, percentile, accumulation, and revision matches the declared parcel fixture

#### Scenario RMEH-006-B: Missing or non-ready fact aborts before browser steps

- **GIVEN** one parcel returns a missing field, queued state, error state, or other non-ready answer
- **WHEN** pre-browser rainfall validation runs
- **THEN** browser execution does not start
- **AND** diagnostics name the parcel and missing or non-ready contract element

#### Scenario RMEH-006-C: Displayed facts must match the latest target

- **GIVEN** a parcel transition has produced a new ready response
- **WHEN** the answer card is asserted
- **THEN** all five semantic identity and rainfall fact dimensions match the newly selected parcel
- **AND** no field from the previously selected parcel remains displayed as the current answer

### Requirement RMEH-007: Mobile A-to-B-to-C-to-A Continuity

At a 390×844 viewport and `medio` rainfall mode, the harness **MUST** establish A as the initial ready selection and then execute A → B → C → A. Immediately before each of the three transitions, the page body's active scrolling element **MUST** have a true, measurable scroll range and a scroll position greater than zero. After each transition, the selected tab **MUST** remain `Lluvia`; the semantic identity and all target rainfall facts **MUST** change from the prior parcel and match the target parcel; body scroll position **MUST** equal zero; and the complete ready answer card **MUST** be contained within the visible body viewport. Freshness **MUST** be established from the latest target response and rendered values, not merely from eventual text presence.

#### Scenario RMEH-007-A: Mobile sequence starts from ready A

- **GIVEN** the 390×844 viewport, `medio` mode, and validated A target
- **WHEN** A is selected through the normal parcel click path
- **THEN** the `Lluvia` tab is active
- **AND** the complete visible answer card matches A's ready identity and facts

#### Scenario RMEH-007-B: Mobile transition A to B resets and refreshes

- **GIVEN** A is current and the body has both a non-zero scroll range and a scroll position greater than zero
- **WHEN** B is selected through a normal parcel click
- **THEN** `Lluvia` remains active and B's identity, scope, percentile, accumulation, and revision replace A's values
- **AND** body scroll position is zero
- **AND** B's complete ready answer card is contained within the visible body viewport

#### Scenario RMEH-007-C: Mobile transition B to C resets and refreshes

- **GIVEN** B is current and the body has both a non-zero scroll range and a scroll position greater than zero
- **WHEN** C is selected through a normal parcel click
- **THEN** `Lluvia` remains active and C's identity, scope, percentile, accumulation, and revision replace B's values
- **AND** body scroll position is zero
- **AND** C's complete ready answer card is contained within the visible body viewport

#### Scenario RMEH-007-D: Mobile transition C back to A is fresh

- **GIVEN** C is current and the body has both a non-zero scroll range and a scroll position greater than zero
- **WHEN** A is selected again through a normal parcel click
- **THEN** `Lluvia` remains active and A's identity, scope, percentile, accumulation, and revision replace C's values
- **AND** the latest response and displayed card match the declared A fixture rather than a stale C or aliased cached answer
- **AND** body scroll position is zero and A's complete ready answer card is contained within the visible body viewport

### Requirement RMEH-008: Desktop A-to-B-to-C-to-A Continuity

At the declared desktop viewport and `medio` rainfall mode, the harness **MUST** execute A → B → C → A through the same production interaction path. After every transition, `Lluvia` **MUST** remain selected and all displayed identity and fact dimensions **MUST** match the latest target without stale values. Browser focus **MUST** remain in the map interaction context—either the body or the same map interaction surface—and **MUST NOT** jump to a hidden, off-screen, mobile-only, or unrelated control. Desktop conformance **MUST NOT** depend on mobile sheet geometry or body scroll-reset assertions.

#### Scenario RMEH-008-A: Desktop sequence preserves rainfall state and fresh facts

- **GIVEN** the desktop viewport, `medio` mode, and A as the initial ready selection
- **WHEN** the harness performs A → B → C → A with normal parcel clicks
- **THEN** `Lluvia` remains active after every transition
- **AND** each transition replaces all five identity and rainfall fact dimensions with the latest target's validated values

#### Scenario RMEH-008-B: Desktop focus remains stable without mobile geometry assertions

- **GIVEN** the desktop sequence is executing in the map interaction context
- **WHEN** each parcel response and answer card completes
- **THEN** focus remains on the body or the same map interaction surface and does not move to a hidden, off-screen, mobile-only, or unrelated control
- **AND** no mobile sheet-height, visible-body containment, or body scroll-reset condition is required for desktop success

### Requirement RMEH-009: Fail-Closed Execution and Honest Result Accounting

The harness **MUST** validate prerequisite cardinalities, A/B/C pairwise distinctness, ready fact completeness, and click-target integrity before browser steps. Missing prerequisites **MUST** produce explicit diagnostics naming the prerequisite. The complete rainfall harness run **MUST** report exactly 11 passed, 0 failed, and 0 skipped tests. A run with zero discovered tests, any skipped test, any soft skip, or an empty selected suite **MUST** fail and **MUST NOT** be reported as green.

#### Scenario RMEH-009-A: Preflight rejects invalid cardinality or distinctness

- **GIVEN** parcel, soil, source, tile, fact, or cache-scope cardinality is wrong, or any required A/B/C dimension is not pairwise distinct
- **WHEN** preflight runs
- **THEN** browser steps do not begin
- **AND** diagnostics name the failing cardinality or distinctness contract and observed values

#### Scenario RMEH-009-B: Missing prerequisite cannot become a soft skip

- **GIVEN** a required prerequisite is unavailable
- **WHEN** the suite attempts to skip, conditionally omit, or mark the affected test pending
- **THEN** the run fails
- **AND** diagnostics name the missing prerequisite instead of recording a skipped test

#### Scenario RMEH-009-C: Empty discovery fails

- **GIVEN** test filtering, configuration, or discovery selects zero rainfall harness tests
- **WHEN** the local or manual runner finishes discovery
- **THEN** the run exits unsuccessfully
- **AND** it reports that no harness tests were executed

#### Scenario RMEH-009-D: Successful complete run has exact accounting

- **GIVEN** all prerequisites and both browser sequences pass
- **WHEN** the complete rainfall harness run finishes
- **THEN** its summary reports exactly 11 passed, 0 failed, and 0 skipped
- **AND** useful execution evidence is retained

### Requirement RMEH-010: Local Runner and Optional Manual GitHub Execution

The capability **MUST** provide a local operator runner as the primary execution path. It **MAY** provide a GitHub `workflow_dispatch` path, but that workflow **MUST NOT** become a required pull-request check or run automatically for ordinary pull requests. If supplied, every manual run **MUST** use isolated disposable resources, prevent concurrent runs from sharing mutable resources, clean up after success, failure, or cancellation, and publish useful diagnostic evidence without exposing secrets.

#### Scenario RMEH-010-A: Operator runs the harness locally

- **GIVEN** an operator has the declared local prerequisites
- **WHEN** the local runner is invoked
- **THEN** it performs the same safety gate, bootstrap validation, browser suite, result accounting, evidence retention, and cleanup contract defined here

#### Scenario RMEH-010-B: Manual workflow is not PR-required CI

- **GIVEN** the optional manual workflow exists
- **WHEN** a pull request is opened or updated without an explicit manual dispatch
- **THEN** this harness is not automatically required or executed as a pull-request check

#### Scenario RMEH-010-C: Concurrent manual dispatches remain isolated

- **GIVEN** two manual runs overlap in time
- **WHEN** they acquire mutable resources
- **THEN** each run uses a distinct disposable ownership boundary or execution is serialized before mutation
- **AND** neither run can read, overwrite, or clean up the other run's mutable resources or temporary secrets

#### Scenario RMEH-010-D: Canceled manual run retains safe evidence

- **GIVEN** a manually dispatched run is canceled after resources have been created
- **WHEN** cancellation handling executes
- **THEN** owned services, resources, and temporary secrets are removed
- **AND** non-secret diagnostics and available browser evidence are published or retained

### Requirement RMEH-011: Parent Evidence and Remediation Boundary

A passing harness result **MAY** be submitted as separate follow-up evidence for parent finding JDA-001. It **MUST NOT** rewrite the exhausted parent Judgment Day record, automatically mark that record `APPROVED`, or extend its review rounds. If the harness demonstrates that the production fix still fails, the result **MUST** trigger a separate remediation decision and **MUST NOT** authorize production changes within this harness change.

#### Scenario RMEH-011-A: Passing evidence remains a separate transaction

- **GIVEN** the complete harness run passes with valid evidence
- **WHEN** maintainers evaluate JDA-001
- **THEN** they may cite the harness evidence in a separate follow-up review transaction
- **AND** the parent Judgment Day status is not automatically rewritten or approved

#### Scenario RMEH-011-B: Failing production behavior requires separate remediation

- **GIVEN** the deterministic fixture and harness prerequisites pass
- **BUT** a required mobile or desktop production behavior fails
- **WHEN** the result is reviewed
- **THEN** the failure is preserved as evidence for a separate remediation decision
- **AND** the harness change does not expand itself to modify production behavior

### Requirement RMEH-012: Cleanup, Rollback, and Diagnostic Preservation

After every attempted run, the harness **MUST** remove only the isolated services, mutable resources, and temporary secrets owned by that run. Cleanup **MUST** execute after success, setup failure, browser failure, and cancellation. It **MUST NOT** mutate or remove shared data or resources. Non-secret diagnostics needed to explain a failure **MUST** survive cleanup. Rollback of this capability **MUST** consist only of removing harness, conditional test configuration, runbook, and optional manual-workflow artifacts; it **MUST NOT** require a production or shared-schema rollback.

#### Scenario RMEH-012-A: Successful run cleans owned resources

- **GIVEN** the complete harness run succeeds
- **WHEN** teardown executes
- **THEN** all run-owned services, resources, and temporary secrets are removed
- **AND** shared resources remain unchanged

#### Scenario RMEH-012-B: Failed run still cleans owned resources

- **GIVEN** bootstrap, preflight, or a browser assertion fails after owned resources were created
- **WHEN** failure handling executes
- **THEN** all run-owned services, resources, and temporary secrets are removed
- **AND** diagnostics sufficient to identify the failure are retained without secrets

#### Scenario RMEH-012-C: Cleanup failure cannot produce a green run

- **GIVEN** one or more owned resources cannot be removed
- **WHEN** teardown completes
- **THEN** the run is unsuccessful
- **AND** diagnostics identify the residual owned resource without attempting cleanup of shared resources

#### Scenario RMEH-012-D: Capability rollback does not touch production state

- **GIVEN** maintainers decide to remove this capability
- **WHEN** rollback is performed
- **THEN** only harness-specific tests, scripts, conditional test configuration, documentation, and optional manual-workflow artifacts are removed
- **AND** no production behavior, production schema, or shared data rollback is performed

### Requirement RMEH-013: Scope and Cache Isolation

A, B, and C **MUST** use pairwise distinct rainfall scopes and effective cache identities. Each selected parcel **MUST** resolve to its own ready facts even after earlier parcels have populated caches. Duplicate or aliased scope/cache identities **MUST** fail preflight, and any response or rendered card carrying a prior parcel's facts **MUST** fail the browser sequence.

#### Scenario RMEH-013-A: Scope and cache identities are pairwise distinct

- **GIVEN** the A/B/C fixture has been bootstrapped
- **WHEN** scope and effective cache identities are validated
- **THEN** all three are pairwise distinct
- **AND** each maps to exactly one declared parcel fact set

#### Scenario RMEH-013-B: Stale A facts after B or C selection fail

- **GIVEN** A has populated a rainfall result before B or C is selected
- **WHEN** the latest target response or displayed card is evaluated
- **THEN** any A identity, scope, percentile, accumulation, or revision remaining as the current B or C answer fails the run
- **AND** diagnostics identify the expected target and stale observed dimensions

#### Scenario RMEH-013-C: Cache aliasing fails before or during browser execution

- **GIVEN** two parcels share an effective cache identity or one parcel receives another parcel's cached response
- **WHEN** preflight or transition freshness validation detects the alias
- **THEN** the run fails closed
- **AND** the aliased parcel identities, scopes, revisions, and observed response are named in diagnostics

### Requirement RMEH-014: Bounded First Delivery and Production Isolation

The first delivery **MUST** be operator-only, Chromium-only, and ready-state-only. It **MUST** target zero production-code changes and **MUST NOT** add production routes, properties, hooks, or behavior. The implementation **MUST** remain within the proposal's single focused pull-request plan unless later task forecasting demonstrates that the reviewable slice exceeds the accepted workload; delivery remains ask-always and requires owner approval before any pull request is opened.

#### Scenario RMEH-014-A: First delivery uses the bounded browser scope

- **GIVEN** the harness is executed for first delivery
- **WHEN** browser projects and answer states are selected
- **THEN** only Chromium operator flows and ready rainfall answers are in scope
- **AND** no browser matrix, generic state matrix, or queued/error-state suite is required

#### Scenario RMEH-014-B: Harness requires no production seam

- **GIVEN** the capability implementation is reviewed
- **WHEN** changed production surfaces are assessed
- **THEN** production-code churn is zero
- **AND** no production route, property, hook, auth redesign, or behavior exists solely for the harness

#### Scenario RMEH-014-C: Delivery remains owner-gated and focused

- **GIVEN** design and task forecasting remain within the accepted focused-change workload
- **WHEN** delivery packaging is proposed
- **THEN** one focused pull request is recommended
- **AND** opening that pull request still requires explicit owner approval

## Traceability Index

| Requirement | Scenario IDs | Contract covered |
|---|---|---|
| RMEH-001 | RMEH-001-A..C | Disposable identity, ownership, unsafe-marker abort before writes |
| RMEH-002 | RMEH-002-A..D | Self-healing tables/migrations, view, three parcels, soils, Martin, flag, reachability, post-repair validation |
| RMEH-003 | RMEH-003-A..D | Stable real-derived geometry, synthetic deterministic A/B/C identities and distinct ready facts, idempotency |
| RMEH-004 | RMEH-004-A..C | Supported camera, Web Mercator/canvas derivation, drift and occlusion failure |
| RMEH-005 | RMEH-005-A..C | Plain production parcel clicks and forbidden-seam exclusions |
| RMEH-006 | RMEH-006-A..C | Ready API/fact contract and latest-target matching |
| RMEH-007 | RMEH-007-A..D | Mobile 390×844/`medio` A → B → C → A, real pre-scroll, reset, visibility, freshness |
| RMEH-008 | RMEH-008-A..B | Desktop continuity, freshness, focus stability, no mobile geometry contract |
| RMEH-009 | RMEH-009-A..D | Fail-closed preflight, no skips/green-empty, exact 11/0/0 accounting |
| RMEH-010 | RMEH-010-A..D | Local runner, optional manual dispatch, isolated concurrency, cancellation evidence |
| RMEH-011 | RMEH-011-A..B | Separate JDA-001 evidence and remediation boundary |
| RMEH-012 | RMEH-012-A..D | Cleanup on every outcome, diagnostic preservation, rollback boundary |
| RMEH-013 | RMEH-013-A..C | Distinct scope/cache identities, stale-fact and aliasing failures |
| RMEH-014 | RMEH-014-A..C | Operator/Chromium/ready-only scope, zero production churn, ask-always focused delivery |

**Coverage total:** 14 requirements and 46 scenarios. All normative requirements have at least one objectively testable happy, boundary, or negative scenario.

## Assumptions

1. The application already supports the `?lat=&lng=&zoom=` camera contract and ordinary `tipo=parcela` selection; the harness validates rather than extends these production contracts.
2. An operator-capable session can be provided to local and optional manual execution without changing production authentication.
3. Stable, legally usable real-derived parcel geometries can be retained as deterministic test fixtures while all operator identities and rainfall facts remain synthetic.
4. The existing ready answer exposes semantic identity, scope, percentile, accumulation, and revision in contracts observable by preflight and browser assertions.
5. A complete mobile answer card means the existing ready-state answer required by `lluvia-ux-tarjeta`; this capability adds no new product fields or layout behavior.
6. Desktop focus stability is satisfied when focus remains on the body or the same map interaction surface and never jumps to hidden, off-screen, mobile-only, or unrelated controls.
7. Disposable databases and companion resources expose enough identity and ownership metadata to prove isolation before writes; the design may choose the mechanism but may not weaken the fail-closed outcome.

## Non-Goals

- Changing production rainfall behavior or the parent `lluvia-ux-tarjeta` or `rainfall-analysis` specifications.
- Performing real GEE rainfall computation or introducing real operator rainfall data.
- Redesigning authentication or production environment provisioning.
- Covering queued, loading, unavailable, or generic error-state matrices.
- Requiring this harness in pull-request CI.
- Adding component-test adoption or replacing existing unit/integration coverage.
- Supporting a browser matrix beyond Chromium in first delivery.
- Adding multi-select behavior, production test hooks, production routes, MapLibre exposure, or test-only production properties.
- Repairing a production defect discovered by the harness inside this change.

## Unresolved Questions

None. The proposal's accepted decisions are sufficient for specification; implementation mechanisms remain design-phase work.

## Excavation Appendix

### Load-Bearing Assumptions

| Assumption | Category | Load-bearing | If wrong | Required validation |
|---|---|---:|---|---|
| URL camera parameters deterministically establish the intended map state | Dependency | Yes | Derived click targets cannot be production-honest | Validate camera and projected targets at both declared viewports before interaction |
| Real-derived fixtures remain uniquely clickable at both viewports | Technical | Yes | Clicks become ambiguous, occluded, or flaky | Prove each point is visible, unobstructed, and inside exactly one projected parcel |
| Ownership metadata distinguishes disposable from shared resources before writes | Environmental | Yes | Self-healing could damage shared data | Validate marker, target identity, run ownership, and mismatch behavior with a no-write negative path |
| All five ready fact dimensions are independently observable | Knowledge | Yes | A stale or aliased answer could look fresh | Cross-check declared fixture, backend ready contract, latest response, and rendered card |
| Desktop focus context can be identified consistently | Technical | Yes | Focus regression evidence becomes ambiguous | Record the allowed pre-transition context and assert no jump to forbidden controls |

### Root Cause Chain

```text
Stated problem: JDA-001 lacks browser evidence for same-tab multi-parcel rainfall continuity
    ^ caused by
Existing proof covers wiring and geometry but not the complete map/request/scroller/render transition
    ^ caused by
An uncontrolled environment cannot guarantee distinct parcels, facts, projection targets, or cache identities
    ^ caused by
Shared or weakly identified resources make self-healing unsafe and results non-repeatable
    ^ caused by
ROOT CAUSE: trustworthy browser evidence requires a deterministic fixture inside a provably disposable ownership boundary
```

### Second-Order Effects

| Effect | Category | Likelihood | Severity | Contract response |
|---|---|---:|---:|---|
| Fixture geometry drifts relative to map rendering over time | Maintenance | Medium | High | Fail projection integrity explicitly; do not bypass with production seams |
| Optional manual workflow leaves resources after cancellation | Operational | Medium | High | Require cancellation-safe cleanup and per-run isolation |
| Exact result accounting silently stops discovering tests | Maintenance | Medium | High | Fail green-empty and require exact 11 passed, 0 failed, 0 skipped |
| Evidence is mistaken for authority to rewrite parent review history | Governance | Low | High | Require a separate follow-up transaction and remediation decision |

### Real Problem

The missing artifact is not merely another browser test. It is trustworthy evidence that a real operator interaction produces fresh, parcel-specific rainfall answers across repeated same-tab transitions, which is only credible when environment ownership, fixture distinctness, projection integrity, cache isolation, and result accounting all fail closed.

## Stress-Test Appendix

### Breaking Points

| ID | Breaking point | Dimension | Threshold | Failure cascade | Detection | Priority | Contract mitigation |
|---|---|---|---|---|---|---|---|
| BP-1 | Disposable ownership cannot be proven | Adversarial | Any absent, unknown, shared, or mismatched marker/target identity | Repair writes → shared mutation → data damage | Safety-gate diagnostic before first write | P0 | RMEH-001 and RMEH-012 require abort-before-write and owned-only cleanup |
| BP-2 | Projected target is not uniquely clickable | Temporal | Any target outside its intended geometry, inside another geometry, clipped, or occluded | Wrong click → wrong parcel response → false freshness evidence | Per-viewport target-integrity diagnostic | P1 | RMEH-003 and RMEH-004 require unique visible targets or fail closed |
| BP-3 | Scope or cache identity aliases across parcels | Scale | Any duplicate effective scope/cache identity among A, B, and C or any target response carrying prior facts | Cache hit → stale card → false green transition | Preflight distinctness plus latest-response/render comparison | P1 | RMEH-006, RMEH-009, and RMEH-013 require pairwise distinctness and stale-fact failure |
| BP-4 | Test discovery or prerequisite handling produces no executed assertions | Adversarial | Zero discovered tests or one or more soft skips | Missing coverage → green-empty run → invalid JDA evidence | Exact summary and discovery diagnostics | P1 | RMEH-009 requires exactly 11/0/0 and rejects skips or empty runs |
| BP-5 | Cancellation interrupts teardown | Temporal | Any cancellation after resource creation | Residual service/secret → later collision or exposure | Teardown and residual-resource diagnostics | P1 | RMEH-010 and RMEH-012 require cancellation-safe cleanup and retained non-secret evidence |

### Stress Verdict

**Adequate if all fail-closed contracts are preserved.** The specification blocks the P0 ownership failure before mutation and converts the principal false-green risks—projection drift, cache aliasing, skips, and empty discovery—into explicit failures. Weakening any ownership, distinctness, or accounting gate would make the evidence untrustworthy.
