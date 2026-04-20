/**
 * pilarVerde.ts
 *
 * Frozen TypeScript mirrors of the static Pilar Verde data assets shipped under:
 *   - consorcio-web/public/capas/pilar-verde/*.geojson  (six GeoJSON layers)
 *   - consorcio-web/public/data/pilar-verde/*.json      (three flat JSON files)
 *
 * Schemas (verified against real ETL outputs on 2026-04-20):
 *   - bpa_enriched.json     : schema_version "1.2"  (+años_bpa + años_lista)
 *   - bpa_history.json      : schema_version "1.0"
 *   - aggregates.json       : schema_version "1.2"  (−3 ranking fields)
 *   - bpa_historico.geojson : Phase 7 unified historical BPA layer
 *                              (feature per parcel with años_bpa >= 1)
 *
 * Real-data quirks documented inline:
 *   - `bpa_2025.bpa_total` is emitted as a STRING (e.g. "2") in bpa_enriched.json,
 *     because the IDECor source publishes it as a string.
 *   - `bpa_2025.activa` is `boolean` in bpa_enriched.json (ETL normalizes "1"/"0")
 *     but stays as the raw string `"1"`/`"0"` inside the GeoJSON `bpa_2025.geojson`
 *     properties — normalize at the consumer hook layer if needed.
 *   - GeoJSON `bpa_2025` properties are FLAT (`eje_persona`, `eje_planeta`, …),
 *     they are NOT nested under an `ejes` object the way bpa_enriched.json is.
 *   - `valuacion`, `superficie_ha`, `nomenclatura`, `pedania` may be `null` in
 *     bpa_enriched.json (catastro source rows occasionally lack these).
 *   - `agro_aceptada.geojson` features can have `geometry.type === 'Polygon'` OR
 *     `'MultiPolygon'` — the same is true for `agro_presentada.geojson`.
 *
 * These types are NOT runtime-validated (no Zod). The ETL is the single source of
 * truth for shape correctness; the test `tests/unit/pilarVerdeTypes.test.ts`
 * pins the expected literals against the real samples.
 */

import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson';

// ---------------------------------------------------------------------------
// Shared atomic types
// ---------------------------------------------------------------------------

/** IDECor publishes BPA practice / eje flags as the literal Spanish strings. */
export type BpaPracticeFlag = 'Si' | 'No';

/** The 4 ejes of the BPA framework. */
export type BpaEjeKey = 'persona' | 'planeta' | 'prosperidad' | 'alianza';

/** All 21 BPA practice keys, mirroring the IDECor `bpa_2025` WFS schema verbatim. */
export type PilarVerdePracticaKey =
  | 'capacitacion'
  | 'tranqueras_abiertas'
  | 'polinizacion'
  | 'integ_comunidad'
  | 'nutricion_suelo'
  | 'rotacion_gramineas'
  | 'pasturas_implantadas'
  | 'sistema_terraza'
  | 'bioinsumos'
  | 'manejo_de_cultivo_int'
  | 'trazabilidad'
  | 'tecn_pecuaria'
  | 'agricultura_de_precision'
  | 'economia_circular'
  | 'participacion_grup_asociativo'
  | 'indiacagro'
  | 'caminos_rurales'
  | 'ag_tech'
  | 'bpa_tutor'
  | 'corredores_bio'
  | 'riego_precision';

/** The 7 historical years tracked by `aggregates.bpa.evolucion_anual`. */
export type BpaYear = '2019' | '2020' | '2021' | '2022' | '2023' | '2024' | '2025';

/** Possible `ley_forestal` resolutions for an enriched parcel. */
export type LeyForestalStatus = 'aceptada' | 'presentada' | 'no_inscripta';

// ---------------------------------------------------------------------------
// Runtime constants — readonly arrays the consumer can iterate at runtime.
// Kept here (not in `constants/`) so they live next to the literal unions.
// ---------------------------------------------------------------------------

export const PILAR_VERDE_BPA_YEARS: readonly BpaYear[] = [
  '2019',
  '2020',
  '2021',
  '2022',
  '2023',
  '2024',
  '2025',
] as const;

/**
 * Canonical 21-key list of practica keys, in the IDECor source declaration order.
 * Components MAY re-sort (alphabetically, or by adoption rank) — but this is the
 * authoritative source list.
 */
export const PILAR_VERDE_PRACTICA_KEYS: readonly PilarVerdePracticaKey[] = [
  'capacitacion',
  'tranqueras_abiertas',
  'polinizacion',
  'integ_comunidad',
  'nutricion_suelo',
  'rotacion_gramineas',
  'pasturas_implantadas',
  'sistema_terraza',
  'bioinsumos',
  'manejo_de_cultivo_int',
  'trazabilidad',
  'tecn_pecuaria',
  'agricultura_de_precision',
  'economia_circular',
  'participacion_grup_asociativo',
  'indiacagro',
  'caminos_rurales',
  'ag_tech',
  'bpa_tutor',
  'corredores_bio',
  'riego_precision',
] as const;

export const PILAR_VERDE_EJE_KEYS: readonly BpaEjeKey[] = [
  'persona',
  'planeta',
  'prosperidad',
  'alianza',
] as const;

// ---------------------------------------------------------------------------
// `bpa_enriched.json` (schema 1.0)
// ---------------------------------------------------------------------------

/** Practice flag map nested inside `bpa_2025` of an enriched parcel. */
export type BpaPracticesRecord = Record<PilarVerdePracticaKey, BpaPracticeFlag>;

/** Eje flag map nested inside `bpa_2025` of an enriched parcel. */
export type BpaEjesRecord = Record<BpaEjeKey, BpaPracticeFlag>;

/**
 * The `bpa_2025` block in `bpa_enriched.json`.
 * NOTE: `bpa_total` is a string because the IDECor source publishes it that way.
 * NOTE: `activa` is a boolean because the ETL normalizes the IDECor "1"/"0" → bool.
 */
export interface Bpa2025EnrichedRecord {
  n_explotacion: string;
  superficie_bpa: number;
  bpa_total: string;
  id_explotacion: string;
  activa: boolean;
  ejes: BpaEjesRecord;
  practicas: BpaPracticesRecord;
}

/**
 * One row of `bpa_enriched.json::parcels[]`.
 * `bpa_2025` is `null` exactly when no BPA 2025 record matched the parcel.
 */
export interface ParcelEnriched {
  nro_cuenta: string;
  nomenclatura: string | null;
  departamento: string | null;
  pedania: string | null;
  superficie_ha: number | null;
  valuacion: number | null;
  ley_forestal: LeyForestalStatus;
  bpa_2025: Bpa2025EnrichedRecord | null;
  /** Map of year → `n_explotacion`. Empty object if no historical record exists. */
  bpa_historico: Record<string, string>;
  // ── Phase 7 — commitment-depth (schema 1.2) ──
  /** Count of BPA years (2019..2025) the parcel participated in. 0..7. */
  años_bpa: number;
  /** Sorted ASC list of BPA year strings present for this parcel. */
  años_lista: string[];
}

export interface BpaEnrichedFile {
  schema_version: '1.2';
  generated_at: string;
  source: string;
  parcels: ParcelEnriched[];
}

// ---------------------------------------------------------------------------
// `bpa_history.json` (schema 1.0)
// ---------------------------------------------------------------------------

export interface BpaHistoryFile {
  schema_version: '1.0';
  generated_at: string;
  /** key = nro_cuenta, value = { yyyy: n_explotacion } */
  history: Record<string, Record<string, string>>;
}

// ---------------------------------------------------------------------------
// `aggregates.json` (schema 1.2 — subtractive over 1.1)
//
// Phase 7 dropped the 3 ranking-driven fields (not actionable for the widget).
// `AggregatesBpaPracticaRanking` stays exported — it may still show up in
// legacy v1.1 payloads during a transition and downstream consumers (AI
// sessions, PDF exports) can keep using it if they compute rankings client-
// side.
// ---------------------------------------------------------------------------

export interface AggregatesLeyForestal {
  aceptada_count: number;
  presentada_count: number;
  no_inscripta_count: number;
  aceptada_superficie_ha: number;
  presentada_superficie_ha: number;
  cumplimiento_pct_parcelas: number;
  cumplimiento_pct_superficie: number;
}

export interface AggregatesBpaPracticaRanking {
  nombre: PilarVerdePracticaKey;
  adopcion_pct: number;
}

export interface AggregatesBpa {
  explotaciones_activas: number;
  superficie_total_ha: number;
  cobertura_pct_zona: number;
  // ── Historical-coverage KPIs (carried over from 1.1) ──
  cobertura_historica_count: number;
  cobertura_historica_pct: number;
  abandonaron_count: number;
  abandonaron_pct: number;
  nunca_count: number;
  nunca_pct: number;
  /** Always contains all 7 keys 2019..2025 (zero-filled if no records). */
  evolucion_anual: Record<BpaYear, number>;
  ejes_distribucion: Record<BpaEjeKey, number>;
}

export interface AggregatesGrilla {
  altura_med_mean: number;
  pend_media_mean: number;
  forest_mean_pct: number;
  categoria_distribution: Record<string, number>;
  drenaje_distribution: Record<string, number>;
}

export interface AggregatesZonaAgroforestal {
  leyenda: string;
  superficie_ha_en_zona: number;
}

export interface AggregatesFile {
  schema_version: '1.2';
  generated_at: string;
  zona: { nombre: string; superficie_ha: number };
  ley_forestal: AggregatesLeyForestal;
  bpa: AggregatesBpa;
  grilla_aggregates: AggregatesGrilla;
  zonas_agroforestales: AggregatesZonaAgroforestal[];
}

// ---------------------------------------------------------------------------
// GeoJSON layer property types
// (Geometries are taken from `geojson` package — no schema_version in GeoJSONs.)
// ---------------------------------------------------------------------------

/** `zona_ampliada.geojson` — single Polygon, no business-relevant properties. */
export interface ZonaAmpliadaProperties {
  name?: string | null;
}
export type ZonaAmpliadaFeature = Feature<Polygon, ZonaAmpliadaProperties>;
export type ZonaAmpliadaFeatureCollection = FeatureCollection<Polygon, ZonaAmpliadaProperties>;

/**
 * `bpa_2025.geojson` properties — FLAT (no nested `ejes`/`practicas`).
 * `activa` and `bpa_total` are STRINGS in the GeoJSON (vs. boolean/string in
 * the enriched JSON). Consumer is responsible for any normalization.
 */
export type Bpa2025FeatureProperties = {
  n_explotacion: string;
  cuenta: string;
  superficie: number;
  superficie_bpa: number;
  bpa_total: string;
  id_explotacion: string;
  activa: string;
  eje_persona: BpaPracticeFlag;
  eje_planeta: BpaPracticeFlag;
  eje_prosperidad: BpaPracticeFlag;
  eje_alianza: BpaPracticeFlag;
} & Record<PilarVerdePracticaKey, BpaPracticeFlag>;

export type Bpa2025Feature = Feature<MultiPolygon | Polygon, Bpa2025FeatureProperties>;
export type Bpa2025FeatureCollection = FeatureCollection<
  MultiPolygon | Polygon,
  Bpa2025FeatureProperties
>;

/** `agro_aceptada.geojson` / `agro_presentada.geojson` share the same properties. */
export interface AgroParcelFeatureProperties {
  estado: 'Aceptada' | 'Presentada' | string;
  lista_cuenta: string;
}
export type AgroParcelFeature = Feature<MultiPolygon | Polygon, AgroParcelFeatureProperties>;
export type AgroParcelFeatureCollection = FeatureCollection<
  MultiPolygon | Polygon,
  AgroParcelFeatureProperties
>;
export type AgroAceptadaFeatureCollection = AgroParcelFeatureCollection;
export type AgroPresentadaFeatureCollection = AgroParcelFeatureCollection;

/** `agro_zonas.geojson` */
export interface AgroZonasFeatureProperties {
  leyenda: string;
}
export type AgroZonasFeature = Feature<MultiPolygon | Polygon, AgroZonasFeatureProperties>;
export type AgroZonasFeatureCollection = FeatureCollection<
  MultiPolygon | Polygon,
  AgroZonasFeatureProperties
>;

/** `porcentaje_forestacion.geojson` */
export interface PorcentajeForestacionFeatureProperties {
  nro_cuenta: string;
  forest_obligatoria: number;
}
export type PorcentajeForestacionFeature = Feature<
  MultiPolygon | Polygon,
  PorcentajeForestacionFeatureProperties
>;
export type PorcentajeForestacionFeatureCollection = FeatureCollection<
  MultiPolygon | Polygon,
  PorcentajeForestacionFeatureProperties
>;

/**
 * `bpa_historico.geojson` (Phase 7 — unified historical BPA layer).
 *
 * One feature per parcel that has EVER been in the BPA program
 * (`años_bpa >= 1`). The map colors the fill by `años_bpa` using a MapLibre
 * `interpolate` expression — gradient from pale green (1 año) to dark green
 * (7 años) signaling commitment depth at a glance.
 */
export interface BpaHistoricoFeatureProperties {
  nro_cuenta: string;
  /** Count of BPA years (2019..2025) the parcel participated in. 1..7. */
  años_bpa: number;
  /** Sorted ASC list of BPA year strings present for this parcel. */
  años_lista: string[];
  /** Most recent ``n_explotacion`` (2025 name if active, else last historical). */
  n_explotacion_ultima: string;
  /** True iff the parcel appears in `bpa_2025`. */
  bpa_activa_2025: boolean;
}
export type BpaHistoricoFeature = Feature<
  MultiPolygon | Polygon,
  BpaHistoricoFeatureProperties
>;
export type BpaHistoricoFeatureCollection = FeatureCollection<
  MultiPolygon | Polygon,
  BpaHistoricoFeatureProperties
>;

// ---------------------------------------------------------------------------
// Composite shape returned by the `usePilarVerde()` hook.
// Each slot is `null` when the corresponding fetch failed (graceful degradation
// per spec: "UI shows 'Datos no disponibles' if missing").
// ---------------------------------------------------------------------------

export interface PilarVerdeData {
  zonaAmpliada: ZonaAmpliadaFeatureCollection | null;
  bpa2025: Bpa2025FeatureCollection | null;
  /** Phase 7 — unified historical BPA layer (replaces bpa_2025 on the map). */
  bpaHistorico: BpaHistoricoFeatureCollection | null;
  agroAceptada: AgroAceptadaFeatureCollection | null;
  agroPresentada: AgroPresentadaFeatureCollection | null;
  agroZonas: AgroZonasFeatureCollection | null;
  porcentajeForestacion: PorcentajeForestacionFeatureCollection | null;
  bpaEnriched: BpaEnrichedFile | null;
  bpaHistory: BpaHistoryFile | null;
  aggregates: AggregatesFile | null;
}
