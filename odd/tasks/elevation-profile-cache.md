# Elevation profile cache (Postgres) + new-source contract

Persist the GLO-30 profile per geometry so a repeat view costs a DB read instead
of 1–3 s of rasterio/pyproj on the box, and freeze the invalidation contract so a
new altimetry source enters without silently serving stale numbers.

## Specs

- **S1** — Cache key = `sha256(canonical_geometry_json + "|" + source_identity)`,
  hex. Canonical JSON = `json.dumps(geometry, sort_keys=True, separators=(",",":"))`,
  so key order in the payload does not change the key. No rounding of
  coordinates: a different geometry must never hit.
- **S2** — `source_identity` is built from **the files that were actually
  sampled**, not from job bookkeeping:
  `series:v1|dem_filled:<size>:<mtime_ns>|mde_ar:<size>:<mtime_ns>` or
  `mde_ar:absent`. A DEM run that rewrites the raster, a re-mosaic of MDE-Ar, or
  a change in the sampling logic (`series:v1` → `v2`) all change the key.
- **S3** — Only the plain series (`compare_dems=False`) is cached. The operator
  GEE comparison (`compare_dems=True`) bypasses the cache entirely: AW3D30 /
  NASADEM must never be served from a stored GLO-30 payload.
- **S4** — A hit returns the stored payload without reopening any raster, plus
  an additive `cache: "hit" | "miss"` field for diagnosis. A miss computes,
  stores, and returns `cache: "miss"`.
- **S5** — New table `elevation_profile_cache` (additive, reversible):
  `cache_key text PK`, `source_identity text NOT NULL`, `payload jsonb NOT NULL`,
  `created_at timestamptz NOT NULL DEFAULT now()`, index on `created_at`.
  Migration `zz_elevation_profile_cache` chains from the single Alembic head
  `zz_audit_v6_db` (checked: `0028_add_canal_publicacion_sr_pa` is NOT the head in
  the current tree — it already has the `lluvia_ext_*` chain as a child).
- **S6** — Retention: on write, prune rows older than 90 days (one statement).
  Superseded DEM runs simply stop being requested; their rows age out.
- **S7** — Adding a new source is 3 documented steps (`docs/ALTIMETRIA-FUENTES.md`)
  and the key picks it up automatically; a new source that is *not* reflected in
  `source_identity` is a defect, not a preference.

## Tasks

- [ ] T1 Pure key + identity module (`elevation_profile_cache.py`), no sqlalchemy at import — `S1`,`S2`
- [ ] T2 Migration `elevation_profile_cache` from head `zz_audit_v6_db` — `S5`
- [ ] T3 Service wiring: read/write/prune, GEE bypass, `cache` flag — `S3`,`S4`,`S6`
- [ ] T4 Tests: pure key/identity (local) + DB round-trip + second call does not resample — `S1`–`S6`
- [ ] T5 Runbook `docs/ALTIMETRIA-FUENTES.md`: what to do when a new source arrives — `S7`
- [ ] T6 Evidence: measured before/after latency, verifier pass, commit ids

## Log

- **L1** (2026-10-14, owner): "no lo veo mal el sl2...digo pq ya no hay mejores o
  mas fuentes q tengqa disponibles...ahora bien...quiza abria que documentar que
  hacer si llega a entrar una fuente nueva" — slice 2 approved, with the
  new-source runbook as an explicit deliverable.
- **L2** (measured before the change, prod, client wall time): 0.27 km → 1.01 s;
  4.93 km → 1.44 s; 20.76 km (1384 points) → 2.5–3.0 s, 218 KB response, MDE-Ar
  sampled. ~1 s fixed cost + ~1.1 ms per point.
