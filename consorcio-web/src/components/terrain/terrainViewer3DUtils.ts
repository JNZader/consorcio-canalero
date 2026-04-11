import type { Feature, FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';

import { GEE_LAYER_COLORS } from '../../hooks/useGEELayers';
import { getSoilColor } from '../../hooks/useSoilMap';

export const TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY = {
  approved_zones: false,
  zona: false,
  cuencas: false,
  basins: false,
  roads: false,
  waterways: false,
  soil: false,
  catastro: false,
} as const;

export type TerrainVectorLayerVisibility = Record<
  keyof typeof TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY,
  boolean
>;

interface GeeLayerLike {
  features: Feature[];
}

interface GeeLayerMapLike {
  zona?: FeatureCollection | null;
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
  properties: GeoJsonProperties,
): Feature<Geometry, GeoJsonProperties> {
  return {
    ...feature,
    properties: {
      ...(feature.properties ?? {}),
      ...properties,
    },
  };
}

export function buildCuencasCollection(
  geeLayers: GeeLayerMapLike,
): FeatureCollection | null {
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
      }),
    ),
  );

  return features.length > 0 ? asFeatureCollection(features) : null;
}

export function buildSoilCollection(
  soilMap: FeatureCollection | null | undefined,
): FeatureCollection | null {
  if (!soilMap) return null;

  return asFeatureCollection(
    soilMap.features.map((feature) =>
      decorateFeature(feature, {
        __color: getSoilColor((feature.properties as { cap?: string | null } | null)?.cap),
      }),
    ),
  );
}

export function buildWaterwaysCollection(
  waterways: WaterwayLike[],
): FeatureCollection | null {
  const features = waterways.flatMap((layer) =>
    layer.data.features.map((feature) =>
      decorateFeature(feature, {
        __color: layer.style.color ?? '#1565C0',
        __label: layer.nombre,
      }),
    ),
  );

  return features.length > 0 ? asFeatureCollection(features) : null;
}

