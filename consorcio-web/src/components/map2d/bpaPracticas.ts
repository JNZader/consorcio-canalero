/**
 * bpaPracticas.ts
 *
 * Pure helpers that underpin the Pilar Verde InfoPanel BpaCard (Phase 3).
 *
 * Everything in this module is:
 *   - PURE    — no I/O, no React, no globals
 *   - STABLE  — the 21 practice keys mirror the IDECor BPA 2025 WFS schema verbatim
 *   - TYPED   — consumer-facing types live in `src/types/pilarVerde.ts`; we reuse
 *               them here so the module is one import deep
 *   - STRYKER-TARGET — mutation score ≥85% (tasks.md 3.7). Tests are tight enough
 *               to catch arithmetic / boundary / equality mutations.
 *
 * Layout decisions (per spec §"InfoPanel BPA Branch" — option B, no eje grouping):
 *   - `PRACTICAS_SORTED` is alphabetical so UI rendering is deterministic
 *   - `sortPracticasByAdopcion` (Task 3.8) offers an optional ranking mode:
 *     adopted practices (Si) first, then non-adopted (No), each group alphabetical
 *
 * Shape adapters (GeoJSON → enriched):
 *   - `normalizeBpaFlat` converts the FLAT `bpa_2025.geojson` feature-properties
 *     shape (`eje_persona`, `capacitacion`, `activa: "1"`) into the NESTED
 *     `Bpa2025EnrichedRecord` shape (`ejes.persona`, `practicas.capacitacion`,
 *     `activa: true`) used by `<BpaCard>`. One adapter, one source of truth.
 *
 * Defensive defaults:
 *   - Missing practice / eje keys default to `'No'` (never `undefined`) so the UI
 *     never renders `undefined`/`null` chips even if IDECor ships a malformed row.
 *
 * @see spec `sdd/pilar-verde-bpa-agroforestal/spec` § "InfoPanel BPA Branch"
 * @see design `sdd/pilar-verde-bpa-agroforestal/design` § 4 Frontend Architecture
 */

import {
  type Bpa2025EnrichedRecord,
  type BpaEjeKey,
  type BpaEjesRecord,
  type BpaPracticeFlag,
  type BpaPracticesRecord,
  PILAR_VERDE_EJE_KEYS,
  PILAR_VERDE_PRACTICA_KEYS,
  type PilarVerdePracticaKey,
} from '../../types/pilarVerde';

// ---------------------------------------------------------------------------
// PRACTICAS_SORTED
// ---------------------------------------------------------------------------

/**
 * All 21 practice keys, sorted ASCENDING via locale-independent `localeCompare`.
 *
 * Order is frozen by the test `PRACTICAS_SORTED first key is "ag_tech"` — any
 * change to sort key or direction MUST break that test FIRST.
 *
 * Underscores sort BEFORE letters in `localeCompare` (in default en-US collation),
 * which is why `ag_tech` comes before `agricultura_de_precision`.
 */
export const PRACTICAS_SORTED: readonly PilarVerdePracticaKey[] = [
  ...PILAR_VERDE_PRACTICA_KEYS,
].sort((a, b) => a.localeCompare(b)) as readonly PilarVerdePracticaKey[];

// ---------------------------------------------------------------------------
// humanizePractica
// ---------------------------------------------------------------------------

/**
 * Rioplatense Spanish labels for every IDECor BPA practice key.
 *
 * Labels picked to mirror the IDECor public BPA communication pieces. All
 * punctuation (accents, "ó", "í") is UTF-8 — Biome / tsc accept these as-is.
 *
 * If IDECor adds or renames a key, THIS object must be updated — TypeScript
 * won't catch a new enum member because `PilarVerdePracticaKey` is a literal
 * union frozen at the type layer.
 */
const HUMANIZED: Record<PilarVerdePracticaKey, string> = {
  capacitacion: 'Capacitación',
  tranqueras_abiertas: 'Tranqueras abiertas',
  polinizacion: 'Polinización',
  integ_comunidad: 'Integración con la comunidad',
  nutricion_suelo: 'Nutrición del suelo',
  rotacion_gramineas: 'Rotación de gramíneas',
  pasturas_implantadas: 'Pasturas implantadas',
  sistema_terraza: 'Sistema de terrazas',
  bioinsumos: 'Bioinsumos',
  manejo_de_cultivo_int: 'Manejo integrado de cultivos',
  trazabilidad: 'Trazabilidad',
  tecn_pecuaria: 'Tecnología pecuaria',
  agricultura_de_precision: 'Agricultura de precisión',
  economia_circular: 'Economía circular',
  participacion_grup_asociativo: 'Participación en grupo asociativo',
  indiacagro: 'IndicAgro',
  caminos_rurales: 'Caminos rurales',
  ag_tech: 'AgTech',
  bpa_tutor: 'Tutor BPA',
  corredores_bio: 'Corredores biológicos',
  riego_precision: 'Riego de precisión',
};

export function humanizePractica(key: PilarVerdePracticaKey): string {
  return HUMANIZED[key];
}

// ---------------------------------------------------------------------------
// normalizeBpaFlat
// ---------------------------------------------------------------------------

/**
 * Narrow a flag-like unknown into the frozen `BpaPracticeFlag` literal union.
 * Anything that is NOT exactly the string `"Si"` falls back to `"No"` — this
 * is the defensive default that keeps the UI from rendering undefined chips.
 */
function asPracticeFlag(value: unknown): BpaPracticeFlag {
  return value === 'Si' ? 'Si' : 'No';
}

/**
 * Normalize the IDECor-esque `"1"`/`"0"`/`1`/`0` activa representation into a
 * boolean. Only the literal truthy representations produce `true`.
 */
function normalizeActiva(raw: unknown): boolean {
  return raw === '1' || raw === 1 || raw === true;
}

/**
 * Convert the FLAT GeoJSON feature-properties shape (exported by
 * `scripts/etl_pilar_verde/main.py` → `bpa_2025.geojson`) into the NESTED
 * `Bpa2025EnrichedRecord` shape consumed by `<BpaCard>`.
 *
 * Returns `null` if `bpa_total` is missing OR null/undefined — this is the
 * signal "this feature is not a BPA 2025 record" and callers MUST fall back
 * to the catastro-enriched lookup OR the generic InfoPanel branch.
 *
 * Extra properties on the input are IGNORED silently; the output shape is
 * always exactly `Bpa2025EnrichedRecord` (21 practicas + 4 ejes guaranteed).
 *
 * @example
 *   const bpa = normalizeBpaFlat(feature.properties)
 *   if (bpa) renderBpaCard(bpa)  // nested shape
 *   else     renderGeneric(feature.properties)
 */
export function normalizeBpaFlat(
  props: Record<string, unknown> | null | undefined,
): Bpa2025EnrichedRecord | null {
  if (!props) return null;
  const rawTotal = props.bpa_total;
  if (rawTotal === null || rawTotal === undefined) return null;

  const practicas = {} as BpaPracticesRecord;
  for (const key of PILAR_VERDE_PRACTICA_KEYS) {
    practicas[key] = asPracticeFlag(props[key]);
  }

  const ejes = {} as BpaEjesRecord;
  for (const key of PILAR_VERDE_EJE_KEYS) {
    ejes[key] = asPracticeFlag(props[`eje_${key}`]);
  }

  return {
    n_explotacion: String(props.n_explotacion ?? ''),
    superficie_bpa: typeof props.superficie_bpa === 'number' ? props.superficie_bpa : 0,
    bpa_total: String(rawTotal),
    id_explotacion: String(props.id_explotacion ?? ''),
    activa: normalizeActiva(props.activa),
    ejes,
    practicas,
  };
}

// ---------------------------------------------------------------------------
// adoptedCount
// ---------------------------------------------------------------------------

/** Count of practices flagged "Si" in the given record. 0..21. */
export function adoptedCount(practices: BpaPracticesRecord): number {
  let count = 0;
  for (const key of PILAR_VERDE_PRACTICA_KEYS) {
    if (practices[key] === 'Si') count += 1;
  }
  return count;
}

// ---------------------------------------------------------------------------
// sortPracticasByAdopcion  (Task 3.8 REFACTOR — optional ranking mode)
// ---------------------------------------------------------------------------

/**
 * Return practice keys sorted by adoption: "Si" first (alphabetical), then
 * "No" (alphabetical). Useful if a future InfoPanel variant wants
 * "show what they DO first" instead of strict alphabetical.
 *
 * `<BpaCard>` currently uses `PRACTICAS_SORTED` (pure alphabetical) per spec.
 * This helper is kept tested so the refactor path stays open.
 */
export function sortPracticasByAdopcion(
  practices: BpaPracticesRecord,
): PilarVerdePracticaKey[] {
  const si: PilarVerdePracticaKey[] = [];
  const no: PilarVerdePracticaKey[] = [];
  for (const key of PRACTICAS_SORTED) {
    (practices[key] === 'Si' ? si : no).push(key);
  }
  return [...si, ...no];
}

// ---------------------------------------------------------------------------
// Re-exports for convenience
// ---------------------------------------------------------------------------

export { PILAR_VERDE_EJE_KEYS, PILAR_VERDE_PRACTICA_KEYS };
export type { BpaEjeKey, BpaPracticeFlag, PilarVerdePracticaKey };
