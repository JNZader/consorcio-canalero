import type { Feature, FeatureCollection, GeoJsonProperties, Geometry, Position } from 'geojson';
import type {
  CorridorAlternative,
  CorridorFeature,
  CorridorFeatureCollection,
  CorridorRoutingResponse,
  RoutingMode,
  RoutingProfile,
} from '../../../lib/api';

export const ROUTING_PROFILE_PRESETS: Record<
  RoutingProfile,
  {
    label: string;
    description: string;
    corridorWidthM: number;
    alternativeCount: number;
  }
> = {
  balanceado: {
    label: 'Balanceado',
    description: 'Perfil general con corredor medio y alternativas moderadas.',
    corridorWidthM: 50,
    alternativeCount: 2,
  },
  hidraulico: {
    label: 'Hidráulico',
    description: 'Favorece un corredor más ancho y menos alternativas.',
    corridorWidthM: 80,
    alternativeCount: 1,
  },
  evitar_propiedad: {
    label: 'Evitar propiedad',
    description: 'Explora más desvíos y un corredor más acotado.',
    corridorWidthM: 40,
    alternativeCount: 3,
  },
};

export const ROUTING_MODE_PRESETS: Record<
  RoutingMode,
  {
    label: string;
    description: string;
  }
> = {
  network: {
    label: 'Red existente',
    description: 'Usa la red de canales/pgRouting y aplica perfiles sobre los tramos existentes.',
  },
  raster: {
    label: 'Raster multi-criterio',
    description: 'Calcula un least-cost path real sobre raster combinando pendiente, hidrología y propiedad.',
  },
};

export function formatCorridorDistance(totalDistanceM: number): string {
  if (totalDistanceM >= 1000) {
    return `${(totalDistanceM / 1000).toFixed(2)} km`;
  }
  return `${Math.round(totalDistanceM)} m`;
}

export function buildCorridorSummary(result: CorridorRoutingResponse | null) {
  if (!result) return null;

  return {
    totalDistance: formatCorridorDistance(result.summary.total_distance_m),
    mode: ROUTING_MODE_PRESETS[result.summary.mode ?? 'network']?.label ?? result.summary.mode ?? 'network',
    profile: ROUTING_PROFILE_PRESETS[result.summary.profile]?.label ?? result.summary.profile,
    edges: result.summary.edges,
    width: `${Math.round(result.summary.corridor_width_m)} m`,
    alternativeCount: result.alternatives.length,
    penaltyFactor: result.summary.penalty_factor ?? null,
    costBreakdown: result.summary.cost_breakdown ?? null,
  };
}

function isGeometry(value: unknown): value is Geometry {
  return !!value && typeof value === 'object' && 'type' in value;
}

function normalizeFeature(
  feature: Record<string, unknown>,
  extraProperties: GeoJsonProperties,
): Feature | null {
  if (feature.type !== 'Feature' || !isGeometry(feature.geometry)) {
    return null;
  }

  return {
    type: 'Feature',
    geometry: feature.geometry,
    properties: {
      ...(typeof feature.properties === 'object' && feature.properties ? feature.properties : {}),
      ...extraProperties,
    },
  };
}

function normalizeFeatureCollection(
  collection: CorridorFeatureCollection,
  extraProperties: GeoJsonProperties,
): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: collection.features
      .map((feature) => normalizeFeature(feature, extraProperties))
      .filter((feature): feature is Feature => feature !== null),
  };
}

function normalizeCorridorFeature(feature: CorridorFeature | null): FeatureCollection | null {
  if (!feature?.geometry || !isGeometry(feature.geometry)) {
    return null;
  }

  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: feature.geometry,
        properties: {
          ...(typeof feature.properties === 'object' && feature.properties ? feature.properties : {}),
          role: 'corridor',
        },
      },
    ],
  };
}

export function buildCorridorMapCollections(result: CorridorRoutingResponse | null): {
  centerline: FeatureCollection | null;
  corridor: FeatureCollection | null;
  alternatives: FeatureCollection | null;
} {
  if (!result) {
    return { centerline: null, corridor: null, alternatives: null };
  }

  return {
    centerline: normalizeFeatureCollection(result.centerline, { role: 'centerline' }),
    corridor: normalizeCorridorFeature(result.corridor),
    alternatives: buildCorridorAlternativesCollection(result.alternatives),
  };
}

function buildCorridorAlternativesCollection(
  alternatives: CorridorAlternative[],
): FeatureCollection | null {
  const features = alternatives.flatMap((alternative) =>
    normalizeFeatureCollection(alternative.geojson, {
      role: 'alternative',
      rank: alternative.rank,
      total_distance_m: alternative.total_distance_m,
    }).features,
  );

  return features.length > 0 ? { type: 'FeatureCollection', features } : null;
}

function collectGeometryCoordinates(geometry: Geometry): Position[] {
  switch (geometry.type) {
    case 'Point':
      return [geometry.coordinates];
    case 'MultiPoint':
    case 'LineString':
      return geometry.coordinates;
    case 'MultiLineString':
    case 'Polygon':
      return geometry.coordinates.flat();
    case 'MultiPolygon':
      return geometry.coordinates.flat(2);
    case 'GeometryCollection':
      return geometry.geometries.flatMap(collectGeometryCoordinates);
    default:
      return [];
  }
}

export function collectCorridorBounds(result: CorridorRoutingResponse | null): Position[] {
  if (!result) return [];

  const { centerline, corridor, alternatives } = buildCorridorMapCollections(result);
  return [centerline, corridor, alternatives]
    .filter((collection): collection is FeatureCollection => collection !== null)
    .flatMap((collection) => collection.features)
    .flatMap((feature) => (feature.geometry ? collectGeometryCoordinates(feature.geometry) : []));
}

export function buildCorridorAnchorCollection(form: {
  fromLon: number | '';
  fromLat: number | '';
  toLon: number | '';
  toLat: number | '';
}): FeatureCollection | null {
  const features: Feature[] = [];

  if (form.fromLon !== '' && form.fromLat !== '') {
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [form.fromLon, form.fromLat] },
      properties: { role: 'from', label: 'Origen', color: '#2f9e44' },
    });
  }

  if (form.toLon !== '' && form.toLat !== '') {
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [form.toLon, form.toLat] },
      properties: { role: 'to', label: 'Destino', color: '#e03131' },
    });
  }

  return features.length > 0 ? { type: 'FeatureCollection', features } : null;
}
