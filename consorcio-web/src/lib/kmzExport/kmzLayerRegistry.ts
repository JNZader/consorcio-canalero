/**
 * kmzLayerRegistry
 *
 * Source-of-truth for the KMZ export allowlist/denylist and per-layer
 * color/label/geometry metadata. Consumed by:
 *   - Phase 2 (styles) — dispatches KML `<Style>` blocks by `geometryHint`
 *     using the entry's `color` (fill/point) and optional `strokeColor`.
 *   - Phase 3 (builder) — iterates the registry, filters by user-visibility
 *     + `KMZ_EXCLUDED_LAYER_KEYS`, emits one `<Folder>` per allowed +
 *     visible entry.
 *
 * Allowlist vs. denylist
 * ----------------------
 * The registry intentionally includes ONLY the 13 layers in
 * `KMZ_LAYER_REGISTRY`. Any other layer key (including the three in
 * `KMZ_EXCLUDED_LAYER_KEYS`) must NEVER appear:
 *   - `puntos_conflicto` — derived analysis overlay, not raw map data
 *   - `approved_zones`   — draft/editorial zones with PII-shaped metadata
 *   - `basins`           — heavy MVT tiles, not meant for client export
 *
 * Key alignment with the store
 * ----------------------------
 * Each `key` matches the identically-named entry in
 * `defaultVisibleVectors` (see `stores/mapLayerSyncStore.ts`) with ONE
 * exception:
 *   - `ypf-estacion-bombeo` — this layer is ALWAYS-ON with no visibility
 *     toggle. Its key matches `YPF_ESTACION_BOMBEO_SOURCE_ID` so the
 *     exported metadata follows the same convention (source id = registry
 *     key) as the togglable layers.
 *
 * Color source-of-truth
 * ---------------------
 * Colors are imported from the MapLibre paint files whenever those files
 * export a named constant. Three layers paint inline in their sync helpers
 * and do NOT export a named constant — those colors are pinned here with
 * an inline comment pointing at the paint site. If any of the three gets
 * reused outside the export, PROMOTE it to a named export in the paint
 * module and import it here (single-source-of-truth invariant).
 */

import {
  CANALES_COLORS,
} from '../../components/map2d/canalesLayers';
import {
  PILAR_VERDE_COLORS,
} from '../../components/map2d/pilarVerdeLayers';
import {
  YPF_ESTACION_BOMBEO_COLOR,
  YPF_ESTACION_BOMBEO_LABEL,
} from '../../components/map2d/ypfEstacionBombeoLayer';
import { WATERWAY_DEFS } from '../../hooks/useWaterways';
import { SOIL_CAPABILITY_COLORS } from '../../hooks/useSoilMap';

/** Geometry dispatch hint used by Phase 2 style builders. */
export type KmzLayerGeometry = 'point' | 'line' | 'polygon';

/**
 * Describes ONE layer exportable to KMZ.
 *   - `key`           — matches the store visibility key (or the source id
 *                       for always-on layers like `ypf-estacion-bombeo`).
 *   - `label`         — human-readable name used for the KML `<Folder>`.
 *                       Mirrors the labels rendered by the in-app layer
 *                       controls panel (see `map2dDerived.buildVectorLayerItems`).
 *   - `geometryHint`  — primary OGC geometry family for dispatch.
 *   - `color`         — representative fill / point / line hex. For layers
 *                       with gradients (`pilar_verde_*`) we use the MIDDLE
 *                       tier as the one color KML can show at folder level.
 *   - `strokeColor`   — optional outline color. Only present when the
 *                       MapLibre paint uses a distinct outline hex.
 */
export interface KmzLayerEntry {
  key: string;
  label: string;
  geometryHint: KmzLayerGeometry;
  color: string;
  strokeColor?: string;
}

/**
 * Layer keys that MUST NEVER appear in the exported KMZ, even if the user
 * has them flipped on at export time. Phase 3 re-validates against this
 * tuple as a defense-in-depth check — the registry already doesn't include
 * them, but the denylist makes the intent explicit.
 */
export const KMZ_EXCLUDED_LAYER_KEYS = [
  'puntos_conflicto',
  'approved_zones',
  'basins',
] as const;

/**
 * Primary waterway representative = Río Tercero (biggest / most prominent
 * of the 5 waterways). The export uses one color per layer — the rest of
 * the per-feature palette is re-derived at feature emission time in Phase 3.
 */
const RIO_TERCERO_WATERWAY = WATERWAY_DEFS.find((def) => def.id === 'rio_tercero');
if (!RIO_TERCERO_WATERWAY) {
  throw new Error(
    'kmzLayerRegistry: `rio_tercero` missing from WATERWAY_DEFS — waterway ' +
      'representative color cannot be resolved. Update the fallback before ' +
      'editing WATERWAY_DEFS.',
  );
}

/**
 * The exported 13-layer registry.
 *
 * Order matches the user-facing layer controls panel (see
 * `map2dDerived.buildVectorLayerItems`) so the exported KMZ folders read
 * in the same order the user toggles them — less surprise on import.
 */
export const KMZ_LAYER_REGISTRY: readonly KmzLayerEntry[] = [
  // ── Pilar Azul — Canales ────────────────────────────────────────────
  {
    key: 'canales_relevados',
    label: 'Canales relevados',
    geometryHint: 'line',
    // Primary blue-700 used by the `match` fallback on source_style.
    color: CANALES_COLORS.relevadoSinObra,
    strokeColor: CANALES_COLORS.outlineRelevado,
  },
  {
    key: 'canales_propuestos',
    label: 'Canales propuestos',
    geometryHint: 'line',
    // High-priority representative (red-600) — matches the Etapa 1 paint.
    color: CANALES_COLORS.propuestoAlta,
    strokeColor: CANALES_COLORS.outlinePropuesto,
  },
  // ── Pilar Azul — Escuelas + YPF ─────────────────────────────────────
  {
    key: 'escuelas',
    label: 'Escuelas rurales',
    geometryHint: 'point',
    // mirrors escuelas MapLibre `circle-color` (escuelasLayers.ts::
    // buildEscuelasCirclePaint). Promote to a named export if reused.
    color: '#1976d2',
    strokeColor: '#ffffff',
  },
  // ── Pilar Verde ─────────────────────────────────────────────────────
  {
    key: 'pilar_verde_bpa_historico',
    label: 'BPA histórico (por años)',
    geometryHint: 'polygon',
    // Middle gradient stop (green-600 @ 5 años). The 1/3/5/7 gradient
    // collapses to a single representative color in KML.
    color: PILAR_VERDE_COLORS.bpaHistoricoStop5,
    strokeColor: PILAR_VERDE_COLORS.bpaHistoricoLine,
  },
  {
    key: 'pilar_verde_agro_aceptada',
    label: 'Agroforestal: Cumplen',
    geometryHint: 'polygon',
    color: PILAR_VERDE_COLORS.agroAceptadaFill,
    strokeColor: PILAR_VERDE_COLORS.agroAceptadaLine,
  },
  {
    key: 'pilar_verde_agro_presentada',
    label: 'Agroforestal: Presentaron',
    geometryHint: 'polygon',
    color: PILAR_VERDE_COLORS.agroPresentadaFill,
    strokeColor: PILAR_VERDE_COLORS.agroPresentadaLine,
  },
  {
    key: 'pilar_verde_agro_zonas',
    label: 'Zonas Agroforestales',
    geometryHint: 'polygon',
    // Fallback / warm anchor. Per-zone hues exist in the paint but the
    // registry ships one representative for the KML folder.
    color: PILAR_VERDE_COLORS.agroZonasFill,
    strokeColor: PILAR_VERDE_COLORS.agroZonasLine,
  },
  {
    key: 'pilar_verde_porcentaje_forestacion',
    label: '% Forestación obligatoria',
    geometryHint: 'polygon',
    // Middle tier (violet-500 @ 2.31–2.60%). Three-step tier gradient
    // collapses to one color in KML.
    color: PILAR_VERDE_COLORS.porcentajeForestacionMedia,
  },
  // ── Base context layers ─────────────────────────────────────────────
  {
    key: 'waterways',
    label: 'Hidrografía',
    geometryHint: 'line',
    // Río Tercero — the anchor waterway. Each individual waterway has its
    // own per-file color (canal_desviador, arroyos…) resolved in Phase 3
    // at placemark time; the folder-level color uses this representative.
    color: RIO_TERCERO_WATERWAY.style.color,
  },
  {
    key: 'roads',
    label: 'Red vial',
    geometryHint: 'line',
    // mirrors roads MapLibre `line-color` coalesce fallback
    // (mapLayerEffectHelpers.ts::syncRoadLayers — `'line-color': ['coalesce',
    // ['get', 'color'], '#FFEB3B']`). Promote to a named export if reused.
    color: '#FFEB3B',
  },
  {
    key: 'catastro',
    label: 'Catastro rural',
    geometryHint: 'polygon',
    // mirrors catastro MapLibre `fill-color` / `line-color`
    // (mapLayerEffectHelpers.ts::syncCatastroLayers — fill `#8d6e63` @ 0.08,
    // line `#FFFFFF`). Promote to named exports if reused elsewhere.
    color: '#8d6e63',
    strokeColor: '#FFFFFF',
  },
  {
    key: 'soil',
    label: 'Suelos IDECOR',
    geometryHint: 'polygon',
    // Class IV — mid-point of the I–VIII capability palette. Per-feature
    // coloring by `cap` property happens in Phase 3 at placemark time;
    // the folder-level color uses this representative.
    color: SOIL_CAPABILITY_COLORS.IV,
  },
  // ── Always-on landmark (no store toggle) ────────────────────────────
  {
    key: 'ypf-estacion-bombeo',
    label: YPF_ESTACION_BOMBEO_LABEL,
    geometryHint: 'point',
    color: YPF_ESTACION_BOMBEO_COLOR,
    strokeColor: '#ffffff',
  },
] as const;
