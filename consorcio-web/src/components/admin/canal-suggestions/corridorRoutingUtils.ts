import type { Feature, FeatureCollection, GeoJsonProperties, Geometry, Position } from 'geojson';
import type {
  AutoAnalysisScopeType,
  AutoCorridorAnalysisCandidate,
  AutoCorridorAnalysisResponse,
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

export const RASTER_WEIGHT_PRESETS: Record<
  RoutingProfile,
  {
    slope: number;
    hydric: number;
    property: number;
    landcover: number;
  }
> = {
  balanceado: { slope: 0.35, hydric: 0.2, property: 0.25, landcover: 0.2 },
  hidraulico: { slope: 0.25, hydric: 0.45, property: 0.1, landcover: 0.2 },
  evitar_propiedad: { slope: 0.2, hydric: 0.1, property: 0.5, landcover: 0.2 },
};

export const AUTO_ANALYSIS_SCOPE_PRESETS: Record<
  AutoAnalysisScopeType,
  {
    label: string;
    description: string;
  }
> = {
  consorcio: {
    label: 'Consorcio completo',
    description: 'Explora automáticamente las zonas críticas del consorcio completo.',
  },
  cuenca: {
    label: 'Cuenca',
    description: 'Analiza una de las cuencas principales del consorcio.',
  },
  subcuenca: {
    label: 'Subcuenca',
    description: 'Parte desde una subcuenca específica y propone conexiones dentro de su cuenca.',
  },
  punto: {
    label: 'Punto',
    description: 'Parte desde un punto marcado en el mapa y usa la subcuenca contenedora como ancla.',
  },
};

interface BasinFeatureLike {
  properties?: {
    id?: string;
    nombre?: string;
    cuenca?: string;
  } | null;
}

export function buildCuencaOptions(features: BasinFeatureLike[] | undefined) {
  const unique = new Set(
    (features ?? [])
      .map((feature) => feature.properties?.cuenca?.trim())
      .filter((value): value is string => Boolean(value)),
  );
  return [...unique].sort((a, b) => a.localeCompare(b)).map((cuenca) => ({
    value: cuenca,
    label: cuenca,
  }));
}

export function buildSubcuencaOptions(
  features: BasinFeatureLike[] | undefined,
  cuenca: string,
) {
  return (features ?? [])
    .filter((feature) => !cuenca || feature.properties?.cuenca === cuenca)
    .map((feature) => ({
      value: feature.properties?.id ?? '',
      label: feature.properties?.nombre ?? 'Subcuenca',
    }))
    .filter((option) => option.value)
    .sort((a, b) => a.label.localeCompare(b.label));
}

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

export function buildAutoAnalysisSummary(result: AutoCorridorAnalysisResponse | null) {
  if (!result) return null;

  return {
    scopeLabel: AUTO_ANALYSIS_SCOPE_PRESETS[result.scope.type].label,
    profileLabel: ROUTING_PROFILE_PRESETS[result.summary.profile].label,
    modeLabel: ROUTING_MODE_PRESETS[result.summary.mode].label,
    generatedCandidates: result.summary.generated_candidates,
    returnedCandidates: result.summary.returned_candidates,
    routedCandidates: result.summary.routed_candidates,
    unroutableCandidates: result.summary.unroutable_candidates,
    avgScore: result.summary.avg_score.toFixed(1),
    maxScore: result.summary.max_score.toFixed(1),
    zoneCount: result.scope.zone_count,
    criticalZones: result.stats.critical_zones,
  };
}

export function formatAutoCandidateLabel(candidate: AutoCorridorAnalysisCandidate): string {
  return `${candidate.source_zone_name} → ${candidate.target_zone_name}`;
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
}, autoAnalysisPoint?: { lon: number; lat: number } | null): FeatureCollection | null {
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

  if (autoAnalysisPoint) {
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [autoAnalysisPoint.lon, autoAnalysisPoint.lat] },
      properties: { role: 'scope-point', label: 'Punto', color: '#1c7ed6' },
    });
  }

  return features.length > 0 ? { type: 'FeatureCollection', features } : null;
}
