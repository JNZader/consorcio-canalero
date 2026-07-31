# soils-etl Specification

## Purpose

Populate the currently empty `suelos_catastro` table from `suelos_cu.geojson`, remove the
dead `canales_geo` / `mv_canales_por_zona` twins, and define the refresh strategy for
`mv_suelos_por_zona`.

## Requirements

### Requirement: Idempotent soils load

The ETL MUST load every feature of `suelos_cu.geojson` into `suelos_catastro` as
MULTIPOLYGON EPSG:4326 with `simbolo`, `cap` and `ip` attributes. Re-running the ETL on an
already-loaded database MUST converge to the same row set — it MUST NOT duplicate rows and
MUST NOT require a manual truncate.

#### Scenario: First run populates the table

- GIVEN `suelos_catastro` is empty
- WHEN the ETL runs against `suelos_cu.geojson`
- THEN the table row count equals the source feature count
- AND the total area in EPSG:32720 matches the source total within 1%

#### Scenario: Re-run is idempotent

- GIVEN the ETL has already run successfully
- WHEN it runs a second time with the same source file
- THEN the row count is unchanged
- AND no duplicate rows exist for any source feature identity

### Requirement: Load-time assertions

The ETL MUST assert, and fail loudly, on: (a) row count equal to the source feature
count, (b) every stored geometry valid under `ST_IsValid`, (c) every geometry SRID 4326.
A failing assertion MUST abort the load transaction, leaving the table in its prior state.

> **Delta (post-JD)** — two further load-time obligations, plus the runnability contract:
> (d) total hectares in EPSG:32720 within 1 % of the source total; (e) the source `ip` attribute is
> an **integer** in `suelos_cu.geojson` while `suelos_catastro.ip` is `String(50)` — the loader MUST
> coerce it explicitly rather than relying on driver behavior; (f) a NULL `cap` is valid source data
> (2 of 45 features) and MUST NOT abort the load.
>
> **Runnability**: the loader MUST be executable in the deployed environment. `gee-backend/Dockerfile`
> copies only `app/` and `alembic.ini` into the runtime image, so neither `gee-backend/scripts/` nor
> the repo-root `scripts/` exists in the container. The loader MUST therefore live under `app/` and
> be invoked as a module (`python -m app.domains.geo.etl.load_suelos_catastro`, run via
> `docker compose exec backend`), with its source geojson shipped as package data (overridable with
> `--source`) and a test asserting the packaged copy matches the frontend artifact byte-for-byte.
> Rationale: design §3.3 (JDB-002).

#### Scenario: Loader runs inside the deployed container

- GIVEN a deployment where only the backend image is available
- WHEN the operator runs the documented module invocation inside the backend container
- THEN the load completes without requiring any file outside the image
- AND `/data/geo` is reachable because the backend container mounts that volume

#### Scenario: Invalid source geometry aborts the load

- GIVEN the source file contains a self-intersecting polygon that cannot be repaired
- WHEN the ETL runs
- THEN the process exits non-zero naming the offending feature
- AND `suelos_catastro` is unchanged (transaction rolled back)

#### Scenario: Row-count mismatch aborts the load

- GIVEN the inserted row count differs from the source feature count
- WHEN the assertion runs before commit
- THEN the load is rolled back and reported as failed

### Requirement: Dead twin removal

A migration MUST DROP `mv_canales_por_zona` and then `canales_geo`. Both are unreferenced
outside their creating migration; `canal_network` remains the canonical canal table.
Downgrade MUST be documented as unsupported, following the `rainfall_records` precedent.

#### Scenario: Twins are gone after upgrade

- GIVEN the migration is applied to a database created by migration 0015
- WHEN the schema is inspected
- THEN neither `canales_geo` nor `mv_canales_por_zona` exists
- AND `canal_network` and `mv_suelos_por_zona` still exist

#### Scenario: Downgrade is explicit

- GIVEN an operator attempts the downgrade
- WHEN the downgrade function runs
- THEN it raises an explicit "downgrade unsupported" error rather than silently passing

### Requirement: Materialized view refresh strategy

`mv_suelos_por_zona` MUST be refreshable on demand by an operator-triggered admin action,
and the ETL MUST refresh it as its final step. The view MUST be created/refreshed such
that reads are not blocked for the whole refresh (concurrent refresh where a unique index
permits it). The chosen cadence MUST be documented alongside the migration.

> **Delta (post-JD)** — the "concurrent refresh where a unique index permits it" clause is not
> satisfiable as the view stands: migration 0015 creates only two non-unique indexes
> (`ix_mv_suelos_cuenca`, `ix_mv_suelos_zona`), and `(zona_id, simbolo)` is not unique because the
> same symbol can intersect one zone as two disjoint polygons. The phase-0 migration MUST therefore
> recreate `mv_suelos_por_zona` with a surrogate key `row_number() over (order by z.id, s.id) AS
> mv_id` and add a unique index on it, so `REFRESH MATERIALIZED VIEW CONCURRENTLY` is legal.
>
> The refresh MUST run **outside** the load transaction (PostgreSQL forbids `REFRESH … CONCURRENTLY`
> inside a transaction block): the ETL commits the load, then refreshes in autocommit. Consequence,
> which MUST be documented: the "assertions roll the load back" guarantee covers the load only; a
> failed refresh leaves data loaded and the view stale, and the operator admin action
> (`POST /api/v2/admin/geo/suelos/refresh-mv`, admin-only) is the recovery path.
>
> The ficha endpoint itself does NOT read this view — it runs the same SQL parameterized by the
> request geometry — so a stale view never affects ficha correctness, only the existing zone
> dashboards. Rationale: design §3.4 (JD-A-004, JDB-016).

#### Scenario: ETL refreshes the view

- GIVEN the ETL has inserted soil polygons
- WHEN the ETL completes
- THEN `mv_suelos_por_zona` returns non-zero rows for zones intersecting soils

#### Scenario: Stale view is recoverable

- GIVEN soils were reloaded without refreshing the view
- WHEN the operator triggers the refresh action
- THEN the view reflects the current `suelos_catastro` contents

### Requirement: Prerequisite verification of parcelas_catastro

The phase MUST verify and report whether `parcelas_catastro` is populated in the target
environment, since the parcel ficha depends on it.

#### Scenario: Empty catastro reported

- GIVEN `parcelas_catastro` has zero rows in the target environment
- WHEN the phase verification runs
- THEN the emptiness is reported as a deployment blocker for `tipo=parcela`
- AND it does NOT silently pass as success
