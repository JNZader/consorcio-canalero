# ficha-frontend Specification

## Purpose

Map entry points that select an area of interest, and a `FichaTerritorialCard` that
renders the ficha response — tables per dataset plus a monthly precipitation bar chart —
with honest loading, error, no-coverage and low-confidence states.

## Requirements

### Requirement: Ficha data is fetched by a container, never by InfoPanel

`InfoPanel` MUST remain pure: it MUST NOT perform data fetching for the ficha and MUST
NOT call any data hook itself. A container component (map UI panels / workspace layer)
MUST own the request and pass state down to `FichaTerritorialCard` as props.

#### Scenario: Parcel click routes through the container

- GIVEN the user clicks a catastro parcel on the map
- WHEN the click handler resolves the parcel feature
- THEN the container issues the `analisis-zona` request
- AND `InfoPanel` receives the resulting state as props and performs no fetch

#### Scenario: InfoPanel purity is enforced

- GIVEN the change is applied
- WHEN `InfoPanel` is rendered in a unit test with no data provider
- THEN it renders without throwing and without issuing any network request

### Requirement: Three interaction modes

The map MUST offer three ways to define the area of interest: (a) clicking a catastro
parcel, (b) drawing a free polygon through the existing `DrawControl`, (c) selecting a
canal and choosing buffer or catchment. Each mode MUST produce the corresponding
discriminated-union request body and render into the same card.

> **Delta (post-JD) — one interaction-mode machine, and parcel click is the default (JDB-012,
> JDB-014, JD-A-013).** There MUST NOT be a second mode machine alongside the existing
> `measurementMode`: two independent machines can both be non-idle and both bind map clicks with no
> invariant preventing it. The existing union is widened instead
> (`'idle' | 'measuring-distance' | 'measuring-area' | 'ficha-dibujo' | 'ficha-canal'`), so mutual
> exclusion is structural.
>
> Clicking a catastro parcel is NOT a mode: in the default `'idle'` state the existing click routing
> and Pilar Verde click precedence are unchanged, and a click that resolves a `parcelas_catastro`
> feature additionally issues a `tipo: "parcela"` request. The ficha panel MUST NOT be gated behind
> a non-idle mode — that would hide the entire phase-1 deliverable. The drawing and canal modes are
> entered from explicit toolbar buttons alongside the existing measurement buttons.
>
> **Delta (post-JD) — canal clicks need an id-bearing layer (JDB-013).** The currently clickable
> canal layers come from static sources and carry no `canal_network` identifier, so no `canal_id`
> can be produced from them. The canal mode MUST render `vt_canal_network` (already published by
> Martin with `id_column: id`) as a clickable line layer and use the clicked feature's `id` as
> `canal_id`. The phase MUST verify that `vt_canal_network` is populated in the target environment;
> an empty view is a deployment blocker for the canal modes.
>
> **Delta (post-JD) — BPA membership is a client-side join [R1].** The ficha response carries no
> BPA/forestación block. `PilarVerdeBadges` joins the existing public
> `/data/pilar-verde/bpa_enriched.json` (already loaded by `usePilarVerde`) against the clicked
> feature's `nro_cuenta` tile property. A parcel whose tile has no `nro_cuenta` renders
> "sin vinculación"; for `poligono` and `canal_*` areas there is no single account, so the section
> is omitted entirely rather than rendered empty.

#### Scenario: Free polygon drawn

- GIVEN the user activates polygon drawing
- WHEN a polygon is completed
- THEN a `tipo: "poligono"` request is issued with the drawn geometry
- AND the drawing is clearable without leaving a stale ficha on screen

#### Scenario: Canal selection

- GIVEN the user selects a canal
- WHEN they choose the buffer option and a buffer distance
- THEN a `tipo: "canal_buffer"` request is issued with `canal_id` and `buffer_m`

#### Scenario: Switching modes discards previous result

> **Delta (post-JD)** — stated mechanism: the query key includes the area reference, and the hook
> MUST NOT use `placeholderData: keepPreviousData`. Changing mode, clicking a different parcel, or
> clearing the drawing changes the key, so the card falls back to its loading state instead of
> presenting the previous area's numbers. Leaving a ficha mode clears the selection and unmounts the
> panel. Rationale: design §6.5.

- GIVEN a parcel ficha is displayed
- WHEN the user starts drawing a polygon
- THEN the previous ficha is cleared or visibly marked stale before the new result arrives

### Requirement: Card rendering — tables plus monthly chart

`FichaTerritorialCard` MUST render one table per dataset with columns clase / ha / % and
the total hectares, plus a 12-bar monthly precipitation chart using the existing charting
library. Percentages MUST be displayed with a fixed precision and MUST NOT be
recalculated client-side from hectares.

> **Delta (post-JD) — tables are the contract, charts are the complement (JD-A-012).** Stacked bars
> and bin bars are permitted only *in addition to* the per-dataset table, never instead of it. The
> soils table MUST include the `sin dato` residual row and the `sin clasificar` row, with the full
> `cap` subclass shown as a tooltip on the grouped class. The precipitation block MUST render the
> 12-bar chart **and** a mes/mm table plus `anual_mm`, because its payload is a typed mm series, not
> clase/ha/pct rows.

#### Scenario: Full ficha rendered

- GIVEN a successful response with all datasets covered
- WHEN the card renders
- THEN one table per dataset is shown with clase / ha / % rows and the total hectares
- AND a 12-bar monthly precipitation chart is shown in calendar order

### Requirement: Loading, error and no-coverage states

The card MUST distinguish four states per render: loading, error, no coverage, and
result. A `sin_cobertura` dataset MUST display an explicit "sin cobertura" message — it
MUST NOT be rendered as `0%` rows or as an empty table. Errors MUST surface the server's
actionable message (404 unknown parcel, 422 caps exceeded, 429 rate limited, 503 dataset
not loaded) rather than a generic failure.

#### Scenario: No coverage is not zero

- GIVEN a dataset returns `cobertura: "sin_cobertura"`
- WHEN the card renders that dataset
- THEN it shows "sin cobertura" text
- AND it does NOT render a class row with `0%`

#### Scenario: Rate limited

- GIVEN the API responds 429
- WHEN the card renders the error state
- THEN it tells the user the request limit was reached and that they can retry shortly

#### Scenario: Caps exceeded on a drawn polygon

- GIVEN the API responds 422 for an oversized polygon
- WHEN the card renders the error state
- THEN it names the exceeded cap and its limit so the user can redraw smaller

#### Scenario: Soils dataset not loaded

- GIVEN the API responds 503 because `suelos_catastro` is empty
- WHEN the card renders
- THEN it states the soils dataset is unavailable in this deployment
- AND it does NOT display a soils table of zeros

#### Scenario: Loading state

- GIVEN a request is in flight
- WHEN the card renders
- THEN a loading indicator is shown and no stale previous result is presented as current

### Requirement: Low-confidence badge

When a dataset reports `low_confidence: true`, the card MUST display a visible badge next
to that dataset explaining that the area is small relative to the 30 m raster resolution
and the percentages are approximate.

#### Scenario: Small parcel badge

- GIVEN a parcel ficha where `flood_risk.low_confidence` is `true`
- WHEN the card renders
- THEN a low-confidence badge is shown on the flood-risk table
- AND the badge text mentions the limited pixel count

#### Scenario: No badge on large areas

- GIVEN all datasets report `low_confidence: false`
- WHEN the card renders
- THEN no low-confidence badge is present

### Requirement: No personal data in the ficha UI

The card MUST NOT display consorcista names or identifiers. BPA/forestación membership
MUST be shown as an aggregate/status only, and a parcel with a null `nro_cuenta` MUST
render as "sin vinculación" rather than as an error or a blank section.

#### Scenario: Parcel with null nro_cuenta

- GIVEN the response reports `sin_vinculacion`
- WHEN the card renders
- THEN the membership section reads "sin vinculación"
- AND the rest of the ficha renders normally
