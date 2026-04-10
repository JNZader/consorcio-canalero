import type { CanalSuggestion, SuggestionTipo } from '../../../lib/api';
import { ALL_SUGGESTION_TYPES, TIPO_COLORS, TIPO_LABELS } from './canalSuggestionsConstants';

export function getDescription(suggestion: CanalSuggestion): string {
  if (!suggestion.metadata) return '-';
  const meta = suggestion.metadata as Record<string, unknown>;

  if (typeof meta.description === 'string') return meta.description;
  if (typeof meta.nombre === 'string') return meta.nombre;
  if (typeof meta.segment_name === 'string') return meta.segment_name;
  if (typeof meta.zone_id === 'string') return `Zona: ${meta.zone_id}`;
  if (typeof meta.severity === 'string') return `Severidad: ${meta.severity}`;
  if (typeof meta.gap_km === 'number') return `Distancia al canal: ${meta.gap_km.toFixed(1)} km`;

  return '-';
}

export function getScoreColor(score: number): string {
  if (score >= 75) return 'red';
  if (score >= 50) return 'orange';
  if (score >= 25) return 'yellow';
  return 'green';
}

export function getMaintenanceColor(score: number): string {
  if (score >= 0.7) return '#e03131';
  if (score >= 0.4) return '#f08c00';
  return '#2f9e44';
}

export function extractGeometry(
  suggestion: CanalSuggestion,
): { type: 'point'; lat: number; lng: number } | { type: 'line'; positions: [number, number][] } | null {
  if (!suggestion.metadata) return null;
  const meta = suggestion.metadata as Record<string, unknown>;
  const geom = (meta.geometry ?? meta.geometria ?? meta.geom) as Record<string, unknown> | undefined;

  if (geom) {
    const gType = geom.type as string | undefined;
    const coords = geom.coordinates as unknown;

    if (gType === 'Point' && Array.isArray(coords) && coords.length >= 2) {
      return { type: 'point', lat: coords[1] as number, lng: coords[0] as number };
    }

    if ((gType === 'LineString' || gType === 'MultiLineString') && Array.isArray(coords) && coords.length > 0) {
      const lineCoords = gType === 'MultiLineString' ? (coords as number[][][]).flat() : (coords as number[][]);
      return {
        type: 'line',
        positions: lineCoords.map((coord) => [coord[1], coord[0]] as [number, number]),
      };
    }

    if (gType === 'Polygon' && Array.isArray(coords) && coords.length > 0) {
      const ring = (coords as number[][][])[0];
      return {
        type: 'line',
        positions: ring.map((coord) => [coord[1], coord[0]] as [number, number]),
      };
    }
  }

  const lat = meta.lat ?? meta.latitude;
  const lng = meta.lng ?? meta.longitude ?? meta.lon;
  if (typeof lat === 'number' && typeof lng === 'number') {
    return { type: 'point', lat, lng };
  }

  const centroid = meta.centroid as Record<string, unknown> | undefined;
  if (centroid) {
    const cCoords = centroid.coordinates as number[] | undefined;
    if (cCoords && cCoords.length >= 2) {
      return { type: 'point', lat: cCoords[1], lng: cCoords[0] };
    }
  }

  return null;
}

export function sortSuggestions(suggestions: CanalSuggestion[], sortDir: 'asc' | 'desc') {
  return [...suggestions].sort((a, b) => (sortDir === 'desc' ? b.score - a.score : a.score - b.score));
}

export function buildSuggestionStats(suggestions: CanalSuggestion[]) {
  const byTipo: Partial<Record<SuggestionTipo, number>> = {};
  for (const suggestion of suggestions) {
    const tipo = suggestion.tipo as SuggestionTipo;
    byTipo[tipo] = (byTipo[tipo] ?? 0) + 1;
  }
  return byTipo;
}

export function createVisibleTypesSet() {
  return new Set<SuggestionTipo>(ALL_SUGGESTION_TYPES);
}

export function buildMapCollections(suggestions: CanalSuggestion[], visibleTypes: Set<SuggestionTipo>) {
  const filtered = suggestions.filter((suggestion) => visibleTypes.has(suggestion.tipo as SuggestionTipo));
  const pointFeatures: GeoJSON.Feature[] = [];
  const lineFeatures: GeoJSON.Feature[] = [];

  for (const suggestion of filtered) {
    const geometry = extractGeometry(suggestion);
    if (!geometry) continue;

    const tipo = suggestion.tipo as SuggestionTipo;
    const color = TIPO_COLORS[tipo];

    if (geometry.type === 'point') {
      const radius = tipo === 'hotspot' ? Math.max(6, Math.min(18, suggestion.score / 5)) : tipo === 'gap' ? 10 : 8;
      pointFeatures.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [geometry.lng, geometry.lat] },
        properties: {
          id: suggestion.id,
          tipo,
          color,
          radius,
          score: suggestion.score,
          label: TIPO_LABELS[tipo],
          description: getDescription(suggestion),
        },
      });
    } else {
      const weight = tipo === 'bottleneck' ? Math.max(4, Math.min(10, suggestion.score / 10)) : tipo === 'maintenance' ? 5 : 3;
      const lineColor = tipo === 'maintenance' ? getMaintenanceColor(suggestion.score / 100) : color;
      const dasharray = tipo === 'route' ? [10, 6] : [1];
      lineFeatures.push({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: geometry.positions.map(([lat, lng]) => [lng, lat]) },
        properties: {
          id: suggestion.id,
          tipo,
          color: lineColor,
          weight,
          dasharray: JSON.stringify(dasharray),
          score: suggestion.score,
          label: TIPO_LABELS[tipo],
          description: getDescription(suggestion),
        },
      });
    }
  }

  return {
    filtered,
    pointFeatures,
    lineFeatures,
    pointsGeoJSON: { type: 'FeatureCollection', features: pointFeatures } as GeoJSON.FeatureCollection,
    linesGeoJSON: { type: 'FeatureCollection', features: lineFeatures } as GeoJSON.FeatureCollection,
  };
}

export function collectBoundsCoordinates(
  pointFeatures: GeoJSON.Feature[],
  lineFeatures: GeoJSON.Feature[],
): [number, number][] {
  const coords: [number, number][] = [];
  for (const feature of pointFeatures) {
    const [lng, lat] = (feature.geometry as GeoJSON.Point).coordinates;
    coords.push([lng, lat]);
  }
  for (const feature of lineFeatures) {
    for (const coord of (feature.geometry as GeoJSON.LineString).coordinates) {
      coords.push([coord[0], coord[1]]);
    }
  }
  return coords;
}
