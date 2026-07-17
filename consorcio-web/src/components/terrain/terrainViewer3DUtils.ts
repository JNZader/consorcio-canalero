import type { Feature, FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';
import type maplibregl from 'maplibre-gl';

import { GEE_LAYER_COLORS } from '../../hooks/useGEELayers';
import { getSoilColor } from '../../hooks/useSoilMap';
import { MAP3D_DEFAULT_VISIBLE_VECTORS } from '../../stores/mapLayerSyncStore';

/**
 * Shape (key set) of the vector toggles the terrain viewer renders directly
 * via `syncTerrainVectorLayers`. Values here are only a last-resort fallback:
 * the REAL startup visibility comes from `mapLayerSyncStore`'s `map3d` slice
 * (defaults below merge `MAP3D_DEFAULT_VISIBLE_VECTORS`, and the viewer seeds
 * its local state from the live — possibly persisted — store on mount). The
 * historical "lightweight 3D" hidden-by-default policy died in acb1d23 when
 * 3D defaults were unified with 2D; keeping a second value-bearing copy here
 * caused a divergent first frame.
 *
 * NOTE: `zona` is excluded because the 3D mesh IS the consorcio area —
 * rendering a red perimeter outline in 3D was visual noise. `cuencas` is
 * forced off in 3D (the GEE sub-cuencas builds replace it).
 */
const TERRAIN_BASE_VECTOR_LAYER_VISIBILITY = {
  approved_zones: false,
  cuencas: false,
  basins: false,
  roads: false,
  waterways: false,
  soil: false,
  catastro: false,
} as const;

const { zona: _zonaExcluded, ...map3dDefaultsWithoutZona } = MAP3D_DEFAULT_VISIBLE_VECTORS;

export const TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY: Record<string, boolean> = {
  ...TERRAIN_BASE_VECTOR_LAYER_VISIBILITY,
  ...map3dDefaultsWithoutZona,
  cuencas: false,
};

export type TerrainVectorLayerVisibility = Record<
  keyof typeof TERRAIN_BASE_VECTOR_LAYER_VISIBILITY,
  boolean
>;

interface GeeLayerLike {
  features: Feature[];
}

interface GeeLayerMapLike {
  candil?: GeeLayerLike | null;
  ml?: GeeLayerLike | null;
  noroeste?: GeeLayerLike | null;
  norte?: GeeLayerLike | null;
}

interface WaterwayLike {
  nombre: string;
  style: { color?: string | null };
  data: FeatureCollection;
}

export function asFeatureCollection(features: Feature[]): FeatureCollection {
  return { type: 'FeatureCollection', features };
}

export function decorateFeature(
  feature: Feature<Geometry, GeoJsonProperties>,
  properties: GeoJsonProperties
): Feature<Geometry, GeoJsonProperties> {
  return {
    ...feature,
    properties: {
      ...(feature.properties ?? {}),
      ...properties,
    },
  };
}

export function buildCuencasCollection(geeLayers: GeeLayerMapLike): FeatureCollection | null {
  const defs = [
    { key: 'candil', color: GEE_LAYER_COLORS.candil, label: 'Candil' },
    { key: 'ml', color: GEE_LAYER_COLORS.ml, label: 'ML' },
    { key: 'noroeste', color: GEE_LAYER_COLORS.noroeste, label: 'Noroeste' },
    { key: 'norte', color: GEE_LAYER_COLORS.norte, label: 'Norte' },
  ] as const;

  const features = defs.flatMap(({ key, color, label }) =>
    (geeLayers[key]?.features ?? []).map((feature) =>
      decorateFeature(feature, {
        __color: color,
        __label: label,
      })
    )
  );

  return features.length > 0 ? asFeatureCollection(features) : null;
}

export function buildSoilCollection(
  soilMap: FeatureCollection | null | undefined
): FeatureCollection | null {
  if (!soilMap) return null;

  return asFeatureCollection(
    soilMap.features.map((feature) =>
      decorateFeature(feature, {
        __color: getSoilColor((feature.properties as { cap?: string | null } | null)?.cap),
      })
    )
  );
}

export function buildWaterwaysCollection(waterways: WaterwayLike[]): FeatureCollection | null {
  const features = waterways.flatMap((layer) =>
    layer.data.features.map((feature) =>
      decorateFeature(feature, {
        __color: layer.style.color ?? '#1565C0',
        __label: layer.nombre,
      })
    )
  );

  return features.length > 0 ? asFeatureCollection(features) : null;
}

/**
 * Ordered list of layer ids that are clickable in the 3D viewer.
 *
 * MUST mirror the 2D `buildClickableLayers()` z-order invariant:
 *   - Pilar Verde BPA-fill FIRST so it wins on overlap (BpaCard branch).
 *   - Canales line layers BEFORE catastro so line-over-parcel clicks resolve
 *     to the canal (user feedback — hydraulic context wins).
 *   - Agro aceptada/presentada are clickable too (legacy BPA-lite branch).
 *   - Agro zonas / porcentaje_forestacion are context-only (NOT clickable).
 *
 * IDs come from TWO different sources:
 *   - Pilar Verde + Canales: registered via SHARED `mapLayerEffectHelpers`
 *     (used by both 2D and 3D), so they keep the bare id from
 *     `SOURCE_IDS.PILAR_VERDE_*` / `SOURCE_IDS.CANALES_*` (no prefix).
 *   - Base vectors (basins / soil / roads / waterways / approved-zones /
 *     catastro): registered via `terrainVectorLayerEffects.ts` with the
 *     `terrain-vector-*` prefix from `TERRAIN_SOURCE_IDS`. The 2D viewer
 *     uses `map2d-*` prefixed ids for the same data — DIFFERENT prefix.
 *
 * IMPORTANT: an earlier version of this list used 2D-style bare ids
 * (`'soil-fill'`, `'basins-fill'`, …) which DO NOT EXIST on the 3D map.
 * `filterExistingLayers` would silently drop them and clicks on basins,
 * soil, roads, waterways, approved-zones, catastro produced an empty
 * `queryRenderedFeatures` result → the InfoPanel never opened. The fix is
 * to import the actual ids from the registration module — no more bare-id
 * guesses, no more silent drops.
 *
 * Consumers MUST filter the result with `map.getLayer(id)` before passing
 * to `queryRenderedFeatures` — MapLibre throws if any id in the `layers`
 * list does not exist on the map.
 *
 * @returns the ordered id list (stable across renders, no allocation per
 *          call beyond the top-level array literal)
 */
export function buildClickableLayers3D(): string[] {
  return [
    // Pilar Verde — BPA topmost on overlap. Bare ids (shared sync helpers).
    'pilar_verde_bpa_historico-fill',
    'pilar_verde_agro_aceptada-fill',
    'pilar_verde_agro_presentada-fill',
    // Canales (Pilar Azul) — above parcels for hydraulic context. Bare ids
    // come from `SOURCE_IDS.CANALES_{PROPUESTOS,RELEVADOS}` which use
    // underscore separators (`canales_propuestos`, NOT `canales-propuestos`).
    'canales_propuestos-line',
    'canales_relevados-line',
    // Base vectors — registered with the `terrain-vector-*` prefix in
    // `terrainVectorLayerEffects.ts`. Catastro in 3D is line-only (no fill);
    // soil + basins + approved-zones are fill-clickable. The strings are
    // duplicated from `TERRAIN_SOURCE_IDS` to avoid a circular import
    // (terrainVectorLayerEffects.ts already imports from this module).
    'terrain-vector-soil-fill',
    'terrain-vector-catastro-line',
    'terrain-vector-roads-line',
    'terrain-vector-waterways-line',
    'terrain-vector-basins-fill',
    'terrain-vector-approved-zones-fill',
    // NOTE: `zona-fill` was removed — the 3D viewer no longer registers any
    // zona layer (the 3D mesh IS the consorcio area). The click-target
    // whitelist tracks reality, so there is nothing to click against.
  ];
}

/**
 * Filter the full clickable-layer id list down to the ids that actually
 * exist on the given MapLibre instance. Non-existent ids throw from
 * `queryRenderedFeatures`, so the click handler MUST filter first.
 */
export function filterExistingLayers(
  map: Pick<maplibregl.Map, 'getLayer'>,
  ids: readonly string[]
): string[] {
  return ids.filter((id) => Boolean(map.getLayer(id)));
}
