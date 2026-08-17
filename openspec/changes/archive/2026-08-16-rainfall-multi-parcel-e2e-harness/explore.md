# Exploration: rainfall-multi-parcel-e2e-harness

## Executive Summary

The smallest production-honest path is a **test/harness-only variant of candidate A**: seed an
isolated PostGIS database with two deterministic parcel polygons plus one covering soil polygon,
publish those parcels through the real Martin `parcelas_catastro` source, open parcel A through the
real map, create real sheet-body scroll with a wheel gesture, and plain-click parcel B while the
`Lluvia` tab remains selected. The click positions must be derived from the committed fixture's
longitude/latitude, the declared camera center/zoom, and the live canvas bounds using Web Mercator
projection. No scale-label expectation, store mutation, test-only production hook, force-click, or
fixed pixel target is needed.

Candidate A as literally phrased around an arbitrary `fitBounds` call is not available through the
public UI: the app exposes a supported `?lat=&lng=&zoom=` camera path, while the MapLibre instance is
private to `MapaMapLibre`. The viable adaptation is therefore **A-prime: supported URL camera plus
derived projection**. Candidate B has no parcel search/list selection surface. Candidate C loses the
map route on login/logout and therefore cannot preserve the sheet. Candidate D is not configured and,
even if added, would test prop rerendering rather than the real map-to-ficha transition.

The browser can honestly prove that both semantic inputs to the private composite key changed (the
tab stayed `Lluvia`, while the real ficha request and rendered parcel identity changed A to B) and
that the keyed effect produced its observable result (`scrollTop === 0`). It cannot literally inspect
the private React prop value without adding a forbidden hook. Any proposal claiming literal key
inspection under the stated constraints would be fake.

## Current State

- The parent closeout already proves the initial 390×844 geometry: 10/10 scenarios, zero skips,
  `medio`, `scrollTop=0`, and a 15.921875 px card bottom margin.
- The sheet body is the real scrolling element and resets in a layout effect whenever
  `scrollResetKey` changes.
- The current composite key is tab + stable ficha selection identity + rainfall-priority state.
- `fichaSelectionKey` is derived from the request, and a plain parcel click immediately replaces the
  single-parcel request. The selected dataset tab deliberately survives selection changes.
- Rainfall detail is staff-only and single-parcel-only. A ctrl/meta click that creates
  `tipo=parcelas` is therefore the wrong transition for this proof; the second click must be a plain
  click that replaces parcel A with parcel B.
- The map's MapLibre instance is held in a component ref and is not published on `window` or through
  a context. The supported public camera path is `?lat=&lng=&zoom=`, which calls `flyTo` and places a
  marker.
- Existing rainfall E2E tests mock only rainfall APIs. The ficha request, MapLibre tile request,
  selection, panel loading, and sheet layout remain real.
- The repository has Playwright E2E configuration only. It does not install or configure
  `@playwright/experimental-ct-react`, which the installed Playwright generation requires for React
  component testing.
- A fresh migrated database creates `parcelas_catastro`, but no migration creates
  `vt_parcelas_catastro`. Martin explicitly reads that view, so an isolated harness must create and
  validate it instead of assuming migrations did.

## Affected Areas

- `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts` — add one transition scenario and make the
  rainfall mock return identity-specific scopes, revisions, and facts.
- `consorcio-web/tests/e2e/helpers/catastroFixture.ts` or a new sibling helper — keep the existing
  single-parcel helper stable; add deterministic two-parcel camera/projection/click logic in a
  separate helper if that keeps responsibilities clearer.
- `scripts/tests/fixtures/catastro_rural_cu.json` — an existing six-feature synthetic catastro fixture
  already contains simple polygons suitable as the source for a deterministic pair; do not silently
  copy coordinates into multiple files.
- A new test-only isolated-environment seed/run helper under `scripts/tests/` or
  `consorcio-web/tests/e2e/fixtures/` — migrate, seed exactly the fixture parcels/soil, create the
  missing Martin view, expose Martin to the host, preflight all prerequisites, run the named suite,
  and tear down only its own isolated resources.
- `consorcio-web/tsconfig.tests.json` — only if a new TypeScript rainfall helper/spec file is created;
  the current hand-maintained enrolment rule requires new rainfall contract test files to be listed.
- A concise harness runbook beside the runner or in the existing rainfall E2E documentation surface
  — document hard prerequisites and zero-skip acceptance. Do not edit the parent change artifacts.

## Candidate Comparison

| Candidate | Feasibility from current code | Determinism | Production honesty | Setup / runtime cost | Main failure modes | Production changes |
|---|---|---|---|---|---|---|
| **A. Two parcels + derived map click** | **High as A-prime** with the public URL camera; literal arbitrary `fitBounds` is unavailable without private-map access | High when fixture geometry, camera and clicks are derived and preflighted | Highest: real MapLibre tiles, click handler, ficha request, React query transition, sheet, and browser geometry | Medium setup; medium runtime due isolated PostGIS/backend/Martin/frontend | Camera not settled; target under sheet/control; missing Martin view; fixture drift; stale rainfall scope cache | **No** |
| **B. Existing search/list/navigation selection** | **Not feasible**: no user-facing parcel search/list opens a ficha; URL coordinates only move/mark the map | N/A | Would be high if such a path existed | Low if it existed | Inventing a deep link or test route would test new production plumbing, not current behavior | Would require a new production feature, therefore reject |
| **C. Public auth hydration/role transition in-place** | **Not feasible for continuity**: login navigates to `/admin`; logout hard-replaces `/`; expiry redirects to `/login` | Low for the required same-sheet state | Public auth itself is real, but the required retained map/sheet state is not supported | High runtime and credential/seed cost | Route destruction, sheet unmount, cross-tab sessionStorage isolation, role not changing on token refresh | Would require production continuity behavior, therefore reject |
| **D. Playwright component test** | **Not currently supported/configured**; React CT package/config/template are absent | Medium after substantial setup | Insufficient: mounting/rerendering components bypasses real MapLibre click, ficha request, and selection identity | Medium-high setup; low runtime | Provider/mock drift, false confidence from direct props, separate Vite/CT configuration | Dependency/config additions; still does not satisfy objective |

## Detailed Assessment

### A — Deterministic two-parcel map journey

**Feasible adaptation.** Use the existing supported `?lat=&lng=&zoom=` path to establish a declared
camera. Choose two simple, non-overlapping fixture polygons whose interior points project inside the
uncovered canvas at 390×844 while the sheet is `medio`. Compute each click at runtime from:

1. committed parcel lng/lat interior points;
2. committed camera center/zoom generated from the pair bounds and safe insets;
3. live `.maplibregl-canvas` bounding box; and
4. Web Mercator world coordinates at that zoom.

The resulting `position` is derived, not guessed. Before clicking, hard-assert that it lies inside the
canvas and outside the live sheet rectangle and map-control rectangles. Wait on a successful
`parcelas_catastro` tile and then on the expected real `/api/v2/geo/analisis-zona` payload and rendered
identity; do not wait on scale text or a fixed sleep.

**Why plain click, not multi-select.** Ctrl/meta or the sticky `Varias` control changes the request to
`tipo=parcelas`; current rainfall detail intentionally renders only for `tipo=parcela`. A plain click
on B is still a genuine multi-parcel *journey* (two distinct parcels in sequence) and preserves the
`Lluvia` tab while changing the stable ficha identity.

**Fixture strategy.** Reuse one source of truth for both database seed and browser projection. The
existing synthetic catastro fixture already has large simple polygons, but apply must verify and
record the selected pair's interior margin, non-overlap, projected separation, and safe click region.
If that file's semantics are too coupled to Pilar Verde tests, copy the minimum pair into a new
rainfall-specific GeoJSON once, not into both SQL and TypeScript. Generate SQL from the GeoJSON in the
test runner rather than maintaining duplicate coordinates.

**Fresh-target facts.** The rainfall route mock must branch on the `scopes:resolve` request's
`nomenclature`, return distinct scope IDs for A and B, then return distinct B revision/metric facts.
Using the same scope ID would let TanStack's stale cache show A's answer and would make the scenario
incapable of proving freshness.

### B — Search/list/navigation selection

Rejected. The map route has no parcel-selection search state. The only coordinate navigation path
flies to a point and adds a marker; ficha selection remains local React state driven by real map
clicks. The visible `Selección múltiple` toolbar changes click accumulation semantics but does not
select or navigate to a parcel. Adding a parcel deep link, list, route prop, or postMessage channel
would violate the no-test-hook/no-production-change constraint and would broaden the product for one
test.

### C — Public auth transition while retaining the sheet

Rejected. Successful login performs a hard navigation to `/admin`; logout performs a hard replace to
`/`; expiry redirects to `/login`. Token refresh changes the token only, not the cached user role.
Cross-tab login is also not a valid substitute: credentials are persisted in per-tab sessionStorage,
and the existing durable cross-tab listener is for logout. The application therefore does not support
the required in-place anonymous-to-staff or staff-to-anonymous transition while the same map sheet
remains mounted.

An initial auth-hydration race is also invalid: controlling it would require storage or store
instrumentation rather than a public UI action, and it would not prove a supported user journey.

### D — Browser/component testing

Rejected for this objective. The current project has `@playwright/test` E2E configuration only.
Playwright React component testing for this dependency generation requires a separate experimental CT
package, CT config, mount template, and provider setup. More importantly, mounting
`FichaTerritorialPanel` and updating `resetKey` would merely repeat the existing unit-level prop
transition in a browser engine. It would not exercise MapLibre feature resolution, the real ficha
request, selection-key derivation, tab persistence, or the production container hierarchy from map
click to sheet.

## Recommendation

Adopt **A-prime: isolated two-parcel fixture + supported URL camera + runtime-derived Web Mercator
clicks + one real plain parcel transition**.

This is the only option that meets all constraints with zero production code. It directly targets the
missing evidence rather than creating a general map test framework. Keep the first slice narrow: one
pair, one viewport, one transition, one hard-gated isolated run.

The test must not claim direct visibility into the private composite key. Instead it should prove the
key's semantic change and behavior as follows:

- `Lluvia` remains the active tab;
- the real ficha POST changes from parcel A to parcel B;
- the rendered parcel identity and identity-specific rainfall scope/facts change to B;
- source inspection/unit coverage establishes that request identity feeds `fichaSelectionKey`, which
  feeds the composite reset key; and
- the real sheet body returns from a measured non-zero value to exactly zero before B's complete card
  is accepted.

That is stronger and more honest than exposing the key string just so a test can read it.

## Implementable First Slice

1. **Fixture and projection helper**
   - Select two fixture polygons and generate interior points plus a camera that keeps both click
     points in the uncovered canvas at 390×844 / `medio`.
   - Derive runtime CSS coordinates via Web Mercator and the live canvas box.
   - Assert safe-region membership before each click; no force-click and no scale label.
2. **Isolated data/service harness**
   - Use a unique Compose project, ports, network, and volume.
   - Run migrations; seed only the deterministic parcels and a soil polygon covering both.
   - Create/replace `vt_parcelas_catastro` with the exact property projection Martin config expects.
   - Start backend with `FICHA_ENABLED=true`; expose Martin to the browser host; start the frontend
     with matching API/Martin URLs.
   - Preflight counts, fixture nomenclatures, soil intersections, Martin catalog/source, app URL, and
     API URL. In harness mode, any missing prerequisite is a hard failure, never a skip.
3. **One Playwright scenario in the existing rainfall spec**
   - Seed staff auth using the existing offline seam.
   - Register identity-aware rainfall routes before navigation.
   - Open A through a real projected canvas click and activate `Lluvia`.
   - Assert initial A card and `data-stage="medio"`.
   - Produce real non-zero body scroll with a wheel gesture whose delta is derived from
     `scrollHeight - clientHeight`; assert `scrollHeight > clientHeight` and `scrollTop > 0`.
   - Plain-click B at its derived point.
   - Wait for the real ficha payload/identity B, then B-specific rainfall scope and facts.
   - Assert tab continuity, `scrollTop === 0`, `medio`, and the entire B card inside the visible sheet
     body.
4. **Runbook/diagnostics**
   - Print/attach camera, derived click points, safe rectangles, A/B ficha payloads, A/B rainfall
     scopes, pre/post scroll geometry, and final card/body bounds.
   - Run the full rainfall file and require 11/11, zero skipped.

## Exact Acceptance Criteria

1. At viewport **390×844**, the ficha sheet reports `data-stage="medio"`, `Lluvia` is selected, and
   parcel A's complete answer card is wholly inside the visible sheet body.
2. The harness observes `sheetBody.scrollHeight > sheetBody.clientHeight`; a real wheel gesture makes
   `scrollTop > 0`. Direct assignment to `scrollTop` is forbidden.
3. The second interaction is an ordinary user canvas click at a point derived from fixture geometry,
   camera, projection, and live canvas bounds. It is not forced and is outside the sheet/controls.
4. The unmocked ficha endpoint records `tipo=parcela, nomenclatura=A` followed by
   `tipo=parcela, nomenclatura=B`; the panel renders B's nomenclature. No `tipo=parcelas` request is
   accepted for this scenario.
5. The `Lluvia` tab remains selected through the transition. The two request identities are distinct,
   therefore the stable ficha selection identity — and the composite reset-key input — changes while
   the tab does not.
6. Rainfall scope resolution records A then B nomenclature and returns distinct scope IDs. The final
   card contains at least two B-only facts (for example B percentile and B accumulated amount) and no
   A-only fact; its revision/series route is also B-specific.
7. After B is ready, the real sheet body's `scrollTop` is exactly `0`; no reload, stage toggle,
   direct DOM scroll assignment, store mutation, or assertion tolerance is used to obtain it.
8. The final B answer-card box is fully inside the visible sheet-body box with the same ±1 px geometry
   tolerance used by O.1, and the measured element is the complete card, not a child.
9. The declared harness preflight proves: `FICHA_ENABLED=true`; both fixture parcels exist; at least one
   covering `suelos_catastro` row exists; `vt_parcelas_catastro` exists with the required public
   columns; Martin is host-reachable and advertises/serves `parcelas_catastro`; `E2E_APP_URL` and
   `E2E_API_BASE` match the isolated services.
10. The named full rainfall run exits 0 with **11 passed, 0 failed, 0 skipped**. A skipped transition
    or missing prerequisite is a failed gate.
11. Production-code diff is **0 lines**. No app route, component prop, store export, test ID, or
    environment-only production branch is added.

## Prerequisite and Runbook Corrections

The parent runbook's six prerequisites remain necessary but are not sufficient for a repeatable fresh
stack. Add these corrections in the follow-up harness:

1. **Create and validate `vt_parcelas_catastro`.** Migrations do not create it, while every Martin
   config reads it. The harness must create the view after migrations and before Martin starts, with
   `geometria` plus the seven public parcel properties expected by Martin.
2. **Seed parcels explicitly.** A migrated database has the table but no parcel rows. Seed the exact
   deterministic pair from one committed GeoJSON source; verify both nomenclatures and geometry
   validity.
3. **Seed soils explicitly.** The soils ETL depends on a larger packaged source and is unnecessary for
   this narrow harness. A single deterministic soil polygon covering both parcels is sufficient to
   exercise the real ficha path, provided the harness labels it clearly as isolated test data.
4. **Use host-reachable Martin by construction.** A Compose override must publish a unique loopback
   port, and the frontend must receive that exact `VITE_MARTIN_URL` before startup. Merely starting the
   stock `martin` service is insufficient because it only uses `expose`.
5. **Bind all URLs explicitly.** Set matching `E2E_APP_URL`, `E2E_API_BASE`, frontend `VITE_API_URL`,
   and `VITE_MARTIN_URL`. Do not rely on localhost defaults.
6. **Promote deterministic prerequisites to hard gates.** The general suite may soft-skip absent data;
   this dedicated harness owns its data and must fail when its own seed/view/catalog is absent.
7. **Isolate and tear down.** Unique project name, ports, network, and volume; teardown must address
   only those names. Never reuse or truncate a developer's existing database.

## Rollback

- Remove the single transition test, pair/projection helper, isolated seed/run helper, and its concise
  runbook entry.
- Remove any new `tsconfig.tests.json` enrolment line and package script added solely for the harness.
- No production rollback or database migration rollback is required because the harness operates only
  on disposable isolated resources and introduces no production schema/code.
- Preserve the parent JDA-001 state as `fixed` unless and until a successful 11/11 zero-skip run is
  recorded; a failed or reverted harness must not rewrite parent closeout evidence.

## Review Workload Forecast

| Surface | Estimated churn | Review focus |
|---|---:|---|
| Production code | **0 lines** target; hard ceiling 0 for first slice | Reject any production hook/route/prop/store exposure |
| Playwright spec/helper | ~180–280 changed lines | Projection math, safe click region, identity-aware mocks, no soft assertions |
| Isolated seed/runner | ~100–180 changed lines | Destructive-operation guards, view shape, ports, teardown ownership, hard preflight |
| Tests for pure projection/fixture logic | ~60–120 changed lines | Pair drift, bounds, non-overlap, Web Mercator calculation |
| Docs/runbook | ~50–90 changed lines | Exact prerequisites, zero-skip gate, no misleading defaults |

**Forecast:** approximately 390–670 test/harness/docs lines, **0 production lines**. This is below the
800 production-line budget by design. A chained PR is **not recommended**: fixture, runner, and one
scenario form one inseparable review unit, and production churn is zero. Under `ask-always`, the owner
must choose the delivery strategy before apply; recommend one focused PR after that decision.

## Risks

- **Private-map boundary:** actual `map.project()` / `queryRenderedFeatures()` cannot be called from
  Playwright without exposing or intercepting the private instance. The Web Mercator adaptation must
  be validated against the observed A/B identities, not trusted from math alone.
- **Camera settlement:** a click derived from the final camera is wrong during `flyTo`. Gate on target
  catastro tile success and expected identity; do not add a sleep.
- **Sheet occlusion:** the second target can be geometrically valid but covered by the `medio` sheet.
  Safe-region assertions must hard-fail before click.
- **Rainfall cache aliasing:** returning the same scope ID for A and B can preserve A's cached card.
  Distinct identity-specific scopes/revisions are mandatory.
- **View drift:** Martin's config and the test-created view can diverge. Preflight the advertised
  source and required property names, not only relation existence.
- **False green through skips:** existing helpers soft-skip missing data. Dedicated harness mode must
  turn owned prerequisites into failures and assert zero skips in the full result.

## Explicit Non-Goals

- No production parcel search, deep link, map-instance export, test hook, route, prop, or store API.
- No generic multi-parcel selection E2E suite and no `tipo=parcelas` rainfall feature.
- No real rainfall/GEE analysis; rainfall remains mocked at its existing network boundary.
- No auth/login/logout redesign or cross-tab auth synchronization.
- No Playwright component-testing adoption.
- No CI service-stack rollout, canary allowlist change, build, or production deployment.
- No changes to `lluvia-ux-tarjeta` artifacts or terminal ledger in this exploration.

## Stress-Test Report

### Breaking Points

| # | What breaks | Threshold / condition | Failure cascade | Detection | Priority |
|---|---|---|---|---|---|
| BP-1 | Derived click misses B | Camera has not reached declared center/zoom, or projection drifts | Empty/wrong feature → ficha identity unchanged → reset never exercised | Expected B ficha payload and rendered nomenclature never arrive | P1 |
| BP-2 | B is not actionable | Projected point intersects sheet/control rectangle | Browser clicks overlay → no map event → timeout misdiagnosed as data failure | Pre-click safe-rectangle assertion | P1 |
| BP-3 | Fresh stack lacks Martin source | `vt_parcelas_catastro` absent or host port not published | No 200 tile → current helper soft-skips → green-empty suite | Hard harness preflight + 11/11 zero-skip result | P1 |
| BP-4 | B shows A's cached rainfall | A and B resolve to identical query key | Identity changes but old answer survives → false freshness proof | Distinct recorded scope IDs and B-only card facts | P1 |
| BP-5 | Runner damages a live stack | Non-isolated DB/project name accepted | Seed/truncate affects developer data | Refuse non-allowlisted DB/project naming; unique volume/network | P0 |

### Required Mitigations

- BP-1: pair the mathematical projection with outcome validation; no identity B means hard failure.
- BP-2: derive and attach live safe rectangles before the click.
- BP-3: create/validate the view and host route before Playwright; missing owned data is never skippable.
- BP-4: branch scopes and snapshots on nomenclature and assert B-only values.
- BP-5: runner must require an unmistakable disposable database/project name and tear down only exact
  resources it created.

**Stress verdict:** Adequate after these mitigations; fragile without the isolated preflight and
safe-region checks.

## Antithesize Report

### Core Claim

A test-only two-parcel fixture with URL camera and derived projection is the smallest approach that
can produce production-honest browser evidence of the scroll reset with zero production changes.

### Strongest Counter-Argument

Because Playwright cannot access the live MapLibre instance, reproducing projection from declared
camera values risks testing a parallel model of the map. If camera animation, padding, bounds, device
pixel ratio, bearing, or pitch differs, the derived click can be wrong; a public parcel-search path or
actual `map.project()` call would be less brittle.

### Confidence Impact

**Level: Moderate.** The counter wins if the final camera cannot be observed strongly enough, or if no
fixture pair remains safely clickable under the live sheet without relying on timing. The
recommendation is modified accordingly: projection math is never accepted alone. The scenario must
hard-validate safe geometry and the real B ficha payload/identity, and the pair/camera derivation must
be a checked fixture artifact. If those checks cannot be made deterministic in one implementation
slice, stop; do not add a production map export to rescue the test.

### Verdict

**Modify, then proceed.** A-prime remains the only feasible option, but outcome validation and
safe-region preflight are part of the approach, not optional hardening.

## Evidence

<!-- evidence:begin -->
- [read] The sheet resets its real body scroller in a layout effect keyed by `scrollResetKey`. src=consorcio-web/src/components/map2d/MapPanelShell.tsx:139-149
- [read] The current composite key contains tab, reset identity, and priority state. src=consorcio-web/src/components/map2d/FichaTerritorialPanel.tsx:843-869
- [read] Selection identity derives from request type plus stable request reference. src=consorcio-web/src/hooks/useFichaTerritorial.ts:25-68
- [read] Dataset tab survives a selection-key change by explicit contract. src=consorcio-web/src/components/map2d/useFichaOverlayTabs.ts:81-93
- [read] A plain parcel click replaces the single selection immediately; accumulated two-parcel state produces `tipo=parcelas`. src=consorcio-web/src/components/map2d/useFichaInteraction.ts:421-490
- [read] The rainfall detail/priority predicate is restricted to staff plus `tipo=parcela`. src=consorcio-web/src/components/map2d/FichaTerritorialPanel.tsx:731-741
- [read] Map clicks query the real rendered layers and pass resolved parcel identity into the ficha coordinator. src=consorcio-web/src/components/map2d/useMapInteractionEffects.ts:273-315
- [read] The MapLibre instance remains in a private component ref, while the supported URL path performs `flyTo`. src=consorcio-web/src/components/MapaMapLibre.tsx:142-147
- [read] The supported URL camera path calls `flyTo` and adds a marker/popup. src=consorcio-web/src/components/map2d/useReportHighlight.ts:42-113
- [read] Successful login hard-navigates to `/admin`. src=consorcio-web/src/components/LoginForm.tsx:64-82
- [read] Public logout hard-replaces the current route with `/`. src=consorcio-web/src/components/UserMenu.tsx:274-282
- [read] Auth expiry redirects the page to `/login`. src=consorcio-web/src/components/AppProvider.tsx:63-77
- [read] Martin requires `vt_parcelas_catastro` as the source table. src=martin/config.yaml:16-41
- [read] The parcel-table migration creates `parcelas_catastro` but not the Martin view. src=gee-backend/app/db/migrations/versions/0013_add_parcelas_catastro.py:20-67
- [read] The existing isolated closeout run passed 10/10 with all six prerequisites and recorded the 15.921875 px margin. src=openspec/changes/lluvia-ux-tarjeta/apply-progress.md:489-500
- [read] The current Playwright dependency/config is E2E-only and no React CT package is installed. src=consorcio-web/package.json:67-90
- [inferred] There is no current production-supported way for a Playwright page to call the live map instance's `project` or `queryRenderedFeatures`; URL camera plus independently derived projection is the smallest no-production-change bridge. from=E8
<!-- evidence:end -->

## Ready for Proposal

**Yes, conditionally.** The exploration is sufficient for an owner decision. Before any later apply,
the owner should approve A-prime and the one-PR delivery recommendation. The next phase must preserve
the hard constraints: zero production code, disposable isolated services, derived clicks, and 11/11
with zero skips. This exploration does not start proposal/design/tasks/apply work.
