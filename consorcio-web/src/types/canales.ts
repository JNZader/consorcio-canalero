/**
 * canales.ts
 *
 * Frozen TypeScript mirrors of the static Pilar Azul (Canales) data assets
 * shipped under `consorcio-web/public/capas/canales/`:
 *
 *   - `relevados.geojson`    : FeatureCollection<LineString, CanalFeatureProperties>
 *   - `propuestas.geojson`   : FeatureCollection<LineString, CanalFeatureProperties>
 *   - `index.json`           : IndexFile (flat — schema + counts + per-canal meta)
 *
 * Schemas are FROZEN at `"1.0"` (see `sdd/canales-relevados-y-propuestas/spec`
 * observation #2039 — ETL owns the shape, frontend mirrors it verbatim).
 *
 * Real-data quirks (verified against the Batch 2 ETL run on 2026-04-20):
 *   - `prioridad` is ALWAYS `null` on relevados (they carry `source_style`
 *     categories `sin_obra|readec|asociada` instead). Propuestas MAY also be
 *     `null` — v1 keeps those always-visible (not filterable by etapa).
 *   - `longitud_declarada_m` is OPTIONAL: present when the KMZ `<name>`
 *     declared a length, `null` otherwise.
 *   - `tramo_folder` is nullable because root-level Placemarks exist.
 *   - `id` is the ETL-generated slug and is globally unique ACROSS both
 *     `relevados.geojson` and `propuestas.geojson`.
 *   - GeoJSON files carry a sibling `metadata: { schema_version, generated_at }`
 *     object at the FeatureCollection root (not standard, but deterministic).
 *   - `index.json` is FLAT — `schema_version` + `generated_at` + `counts` live
 *     at the root, NOT nested under `metadata`.
 *
 * These types are NOT runtime-validated (no Zod). The ETL is the single source
 * of truth for shape correctness; `tests/unit/canalesTypes.test.ts` pins the
 * expected literals against a hand-picked fixture.
 */

import type { Feature, FeatureCollection, LineString } from 'geojson';

// ---------------------------------------------------------------------------
// Atomic enums + runtime constants
// ---------------------------------------------------------------------------

/**
 * The 5 etapas for propuestos, in priority-descending order (spec-locked).
 * Relevados always have `prioridad: null` (they use `source_style` categories
 * instead).
 */
export type Etapa = 'Alta' | 'Media-Alta' | 'Media' | 'Opcional' | 'Largo plazo';

/**
 * Canonical list — iterate this, never hardcode the 5 strings elsewhere.
 * Order matches `Etapa` priority (highest → lowest).
 */
export const ALL_ETAPAS: readonly Etapa[] = [
  'Alta',
  'Media-Alta',
  'Media',
  'Opcional',
  'Largo plazo',
] as const;

/** Discriminant that tells the two FeatureCollections apart. */
export type CanalEstado = 'relevado' | 'propuesto';

// ---------------------------------------------------------------------------
// GeoJSON property + Feature types
// ---------------------------------------------------------------------------

/**
 * Every canal Feature in both `relevados.geojson` and `propuestas.geojson`
 * carries an IDENTICAL property shape. Geometry is ALWAYS LineString.
 *
 * See spec requirement "CanalFeature.properties Schema (FROZEN v1.0)".
 */
export interface CanalFeatureProperties {
  /** Deterministic slug — globally unique across both files. */
  id: string;
  /** KMZ code (`"N4"`, `"E9"`, `"S2"`, ...) — `null` when absent. */
  codigo: string | null;
  /** Short human-readable name parsed from KML `<name>`. */
  nombre: string;
  /** Free-form description chunk from KML `<name>` — `null` when absent. */
  descripcion: string | null;
  /** Discriminant — matches the filename (`"relevado"` / `"propuesto"`). */
  estado: CanalEstado;
  /** Geodesic length computed via `pyproj.Geod(ellps='WGS84')`, METERS, 1 decimal. */
  longitud_m: number;
  /** Human-declared length from KML `<name>` — `null` when absent. */
  longitud_declarada_m: number | null;
  /**
   * Etapa for propuestos. `null` for ALL relevados, and for the subset of
   * propuestos whose KMZ name didn't carry an etapa keyword.
   */
  prioridad: Etapa | null;
  /** `★` flag from KML `<name>` (user-tagged). */
  featured: boolean;
  /** Parent `<Folder>` name — `null` for root-level Placemarks. */
  tramo_folder: string | null;
  /**
   * KML `styleUrl` without the `#` prefix. For relevados this drives the
   * line color via the `source_style` category (`"sin_obra"`, `"readec"`,
   * `"asociada"`). For propuestos it mirrors the etapa (`"prio_Alta"`, ...).
   */
  source_style: string | null;
}

export type CanalFeature = Feature<LineString, CanalFeatureProperties>;
export type CanalesFeatureCollection = FeatureCollection<LineString, CanalFeatureProperties>;

// ---------------------------------------------------------------------------
// index.json — flat registry consumed by the store/bootstrap
// ---------------------------------------------------------------------------

/**
 * Per-canal metadata row in `index.json`. Same shape for relevados + propuestas.
 *
 * NOTE: `prioridad` is only present on propuestas (relevados omit this key —
 * TypeScript's optional marker makes the omission explicit). Real ETL output
 * also includes the `estado` discriminant at the root of each row — carried
 * here for completeness; the ETL emits it so consumers can skip the
 * containing-array lookup when they need to classify a single row.
 */
export interface CanalMetadata {
  id: string;
  nombre: string;
  codigo: string | null;
  /** Propuestas only — relevados omit the key entirely. */
  prioridad?: Etapa | null;
  longitud_m: number;
  featured: boolean;
  /** Discriminant duplicated from the source FeatureCollection for convenience. */
  estado?: CanalEstado;
}

/**
 * `index.json` top-level shape. FLAT — schema + counts + generated_at live at
 * root (no `metadata` wrapper, unlike the GeoJSON siblings).
 */
export interface IndexFile {
  schema_version: '1.0';
  generated_at: string;
  counts: {
    relevados: number;
    propuestas: number;
    total: number;
  };
  relevados: CanalMetadata[];
  propuestas: CanalMetadata[];
}

// ---------------------------------------------------------------------------
// Composite shape returned by `useCanales()`
// Each slot is `null` when the corresponding fetch failed (graceful
// degradation per spec scenario "Missing file graceful degradation").
// ---------------------------------------------------------------------------

export interface CanalesData {
  relevados: CanalesFeatureCollection | null;
  propuestas: CanalesFeatureCollection | null;
  index: IndexFile | null;
}
