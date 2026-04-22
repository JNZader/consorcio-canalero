/**
 * escuelas.ts
 *
 * Frozen TypeScript mirrors of the static Escuelas rurales data asset
 * shipped under `consorcio-web/public/capas/escuelas/`:
 *
 *   - `escuelas_rurales.geojson` : FeatureCollection<Point, EscuelaFeatureProperties>
 *
 * Schema is FROZEN at the Python ETL side (`scripts/etl_escuelas/`). The
 * ETL's `build.py::build_geojson` whitelists EXACTLY 4 property keys in a
 * locked order — any drift between these TypeScript types and the runtime
 * shape is a bug in the ETL. Tests in `tests/hooks/useEscuelas.test.ts`
 * pin the expected literals against a hand-picked fixture.
 *
 * Real-data quirks (verified against the Batch B ETL run on 2026-04-21):
 *   - `id` lives at the TOP LEVEL of each Feature (GeoJSON spec-idiomatic),
 *     NOT inside `properties`. This matches the real geojson shape and the
 *     design §4.2 contract. The 4-prop whitelist deliberately excludes `id`
 *     to avoid duplicating it.
 *   - `nombre` is RAW from the KMZ (still prefixed `Esc. …`). Humanization
 *     to `Escuela …` lives in `EscuelaCard.tsx` at render time (Batch E),
 *     NOT in the hook.
 *   - The GeoJSON file carries a sibling `metadata: { generated_at }`
 *     object at the FeatureCollection root — non-standard but deterministic.
 *     Not surfaced by the hook (internal ETL detail).
 *
 * These types are NOT runtime-validated (no Zod). The ETL is the single
 * source of truth for shape correctness.
 */

import type { Feature, FeatureCollection, Point } from 'geojson';

// ---------------------------------------------------------------------------
// Atomic enums
// ---------------------------------------------------------------------------

/**
 * The 2 ámbito categories the KMZ source carries. Frozen by the KMZ
 * (`<Ámbito>` CDATA label) — spec REQ-ESC-2.
 */
export type Ambito = 'Rural Aglomerado' | 'Rural Disperso';

// ---------------------------------------------------------------------------
// GeoJSON property + Feature types
// ---------------------------------------------------------------------------

/**
 * Every Escuela Feature carries EXACTLY these 4 keys in this order
 * (enforced by `scripts/etl_escuelas/build.py::serialize_feature_collection`
 * via an explicit `OrderedDict`). Any additional key is a PII leak — the
 * Batch 0.8 tests assert the 4-key whitelist is exclusive.
 *
 * See design `sdd/escuelas-rurales/design` §4.2 ETL output GeoJSON shape.
 */
export interface EscuelaFeatureProperties {
  /** Raw name from KMZ `<name>` — still carries the `Esc. ` prefix. */
  readonly nombre: string;
  /** Township / locality from KMZ `<b>Localidad:</b>`. */
  readonly localidad: string;
  /** Rural setting classification from KMZ `<b>Ámbito:</b>`. */
  readonly ambito: Ambito;
  /** Education levels offered from KMZ `<b>Nivel:</b>` — preserves `·`. */
  readonly nivel: string;
}

/** One point feature. `id` lives at the top level (GeoJSON-spec idiomatic). */
export type EscuelaFeature = Feature<Point, EscuelaFeatureProperties>;

/** FeatureCollection shape returned by `useEscuelas()`. */
export type EscuelaFeatureCollection = FeatureCollection<Point, EscuelaFeatureProperties>;

// ---------------------------------------------------------------------------
// Composite shape returned by `useEscuelas()`
// Single slot — `null` when the fetch failed (graceful degradation per spec
// scenario "Missing file graceful degradation").
// ---------------------------------------------------------------------------

export interface EscuelasData {
  readonly collection: EscuelaFeatureCollection | null;
}
