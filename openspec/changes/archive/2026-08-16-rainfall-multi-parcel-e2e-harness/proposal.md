# Proposal: Deterministic Multi-Parcel Rainfall E2E Harness

## Intent

Units and O.1 prove wiring and geometry, not a same-tab transition through the real map, ficha request, browser scroller, and fresh answer. JDA-001 remains browser-unverified. Stakeholders: maintainers/reviewers; indirectly, mobile operators.

## Scope and Accepted Decisions

- Complete bounded operator-only Chromium suite: **A → B → C → A**, stable real-derived geometries, controlled synthetic identities/responses, every parcel ready, and distinct identity, scope, percentile, accumulation, and revision.
- Mobile 390×844/`medio`: before each transition create real non-zero scroll; afterwards require `Lluvia`, fresh identity/facts, `scrollTop === 0`, and the complete card inside the visible body.
- Desktop: same sequence, `Lluvia` persistence, fresh identity/facts, stable focus; no sheet-geometry assertion.
- A-prime: supported `?lat=&lng=&zoom=` camera, derived Web Mercator/canvas coordinates, and plain `tipo=parcela` clicks. No scale waits, arbitrary pixels, force-click, reload, store mutation, or production hooks/routes/props.
- Local runner plus optional GitHub `workflow_dispatch`; not a required check.

## Capabilities

### New Capabilities
- `rainfall-multi-parcel-e2e-harness`: isolated transition-continuity/freshness evidence.

### Modified Capabilities
- None; `rainfall-analysis` is unchanged.

## Safety and Relationship

Bootstrap auto-creates tables, view, source, and soils only in an explicitly marked disposable isolated database. Other targets abort before mutation; shared/real environments remain untouched.

This change depends on/validates `lluvia-ux-tarjeta`. Evidence may close JDA-001 in a separate review transaction; it cannot extend exhausted Judgment Day rounds or declare the parent APPROVED. Failure requires a separate remediation decision, not production scope creep.

## Non-Goals

No production behavior, auth redesign, real rainfall/GEE, generic all-state suite, required CI, component tests, or browser matrix.

## Success Criteria

- [ ] Both viewports complete A → B → C → A with distinct identities/facts and no stale facts, failures, or skips.
- [ ] Mobile proves each pre-transition scroll and reset/visibility contract; desktop proves focus stability.
- [ ] Interactions remain `tipo=parcela`; forbidden seams remain absent.
- [ ] Bootstrap/teardown fail closed outside owned resources.
- [ ] Full rainfall run reports **11 passed, 0 failed, 0 skipped**; production-code churn is zero.

## Affected Areas and Rollback

Affected: `consorcio-web/tests/e2e/`, `scripts/tests/`, conditional test config, runbook/manual workflow. Rollback removes only harness artifacts; no production/schema rollback.

## Risks and Tradeoffs

Projection drift, occlusion, cache aliasing, or weak isolation risk flakes, false greens, or damage. Preflight geometry, A/B/C facts, cache identities, and disposable ownership. If projection is nondeterministic, stop rather than expose MapLibre. Chromium-only trades breadth for reproducibility.

## Review Workload Forecast

| Surface | Forecast |
|---|---:|
| Production | **0** |
| Tests/harness | ~340–580 lines |
| Docs | ~50–90 lines |
| Config | ~0–5 conditional lines, included above |

Total: ~390–670 non-production lines; production budget: 800. **Decision: one focused PR**, accepted under ask-always; revisit only if task forecasting changes sliceability. Unresolved questions: none.
