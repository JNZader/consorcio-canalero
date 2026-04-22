import type { Feature, FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';
import type maplibregl from 'maplibre-gl';

import { GEE_LAYER_COLORS } from '../../hooks/useGEELayers';
import { getSoilColor } from '../../hooks/useSoilMap';
import {
  PILAR_AZUL_DEFAULT_VISIBILITY,
  PILAR_VERDE_DEFAULT_VISIBILITY,
} from '../../stores/mapLayerSyncStore';

/**
 * Base vector toggle defaults that the terrain viewer renders directly via
 * `syncTerrainVectorLayers`. The Pilar Verde / Pilar Azul defaults are merged
 * from the SHARED constants in `mapLayerSyncStore` to avoid drift — when the
 * store evolves a default (e.g. flipping `canales_propuestos` to ON), the 3D
 * viewer follows automatically without a literal duplication update here.
 *
 * NOTE: `zona` was removed from this record because the 3D mesh IS the
 * consorcio area — rendering a red perimeter outline in 3D was visual noise.
 * 2D keeps its own independent `zona` visibility via `mapLayerSyncStore`'s
 * shared `visibleVectors` (keyed per-view), so removing it here does not
 * affect the 2D viewer.
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

export const TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY = {
  ...TERRAIN_BASE_VECTOR_LAYER_VISIBILITY,
  ...PILAR_VERDE_DEFAULT_VISIBILITY,
  ...PILAR_AZUL_DEFAULT_VISIBILITY,
} as const;

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
 *   - Canales line layers BEFORE `catastro-fill` so line-over-parcel clicks
 *     resolve to the canal (user feedback — hydraulic context wins).
 *   - Agro aceptada/presentada are clickable too (legacy BPA-lite branch).
 *   - Agro zonas / porcentaje_forestacion are context-only (NOT clickable).
 *
 * Per Batch F design decision, the ids ARE the 2D ids (no `terrain_` prefix)
 * because the two map instances never coexist in one MapLibre
 * context — reusing ids simplifies sharing paint factories + filter
 * builders between 2D and 3D.
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
    // Pilar Verde — BPA topmost on overlap
    'pilar_verde_bpa_historico-fill',
    'pilar_verde_agro_aceptada-fill',
    'pilar_verde_agro_presentada-fill',
    // Canales (Pilar Azul) — above parcels for hydraulic context
    'canales-propuestos-line',
    'canales-relevados-line',
    // Base vectors (generic whitelist branch via InfoPanel)
    'soil-fill',
    'catastro-fill',
    'roads-line',
    'waterways-line',
    'basins-fill',
    'approved-zones-fill',
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
