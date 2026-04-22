import type { Feature, FeatureCollection, GeoJsonProperties, Geometry, Position } from 'geojson';
import type { LngLatBoundsLike } from 'maplibre-gl';
import type maplibregl from 'maplibre-gl';
import { MAP_BOUNDS } from '../../constants';

// MapLibre note: center is [lng, lat] — opposite from Leaflet [lat, lng]
export function leafletCenterToMapLibre(center: [number, number]): [number, number] {
  return [center[1], center[0]];
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
    properties: { ...(feature.properties ?? {}), ...properties },
  };
}

/**
 * Upsert a GeoJSON source: setData if source exists, else addSource + addLayer.
 */
export function ensureGeoJsonSource(
  map: maplibregl.Map,
  sourceId: string,
  data: FeatureCollection
): void {
  const existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(data);
  } else {
    map.addSource(sourceId, { type: 'geojson', data });
  }
}

export function setLayerVisibility(map: maplibregl.Map, layerId: string, visible: boolean): void {
  if (map.getLayer(layerId)) {
    map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
  }
}

export function formatExportFilename(title: string, extension: 'png' | 'pdf') {
  const safeTitle =
    (title.trim() || 'mapa_consorcio')
      .toLowerCase()
      .normalize('NFD')
      .replace(/\p{M}/gu, '')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '') || 'mapa_consorcio';
  return `${safeTitle}_${new Date().toISOString().slice(0, 10)}.${extension}`;
}

// Leaflet: [[-32.665914, -62.750969], [-32.44785, -62.345994]] = [[lat,lng],[lat,lng]]
// MapLibre image source needs 4 corners: NW, NE, SE, SW as [[lng,lat], ...]
export const IGN_MAPLIBRE_COORDS: [
  [number, number],
  [number, number],
  [number, number],
  [number, number],
] = [
  [-62.750969, -32.44785],
  [-62.345994, -32.44785],
  [-62.345994, -32.665914],
  [-62.750969, -32.665914],
];

export const IGN_IMAGE_URL = '/overlays/ign/altimetria_ign_consorcio.webp';

/**
 * Fallback bounds for the consorcio area, derived from `MAP_BOUNDS`.
 * Used when the dynamic `zonaCollection` from GEE is not yet available
 * (pending fetch, failed fetch, or offline).
 *
 * Shape: `[[west, south], [east, north]]` — the MapLibre `LngLatBoundsLike`
 * tuple form.
 */
export const MAP_FALLBACK_BOUNDS: LngLatBoundsLike = [
  [MAP_BOUNDS.west, MAP_BOUNDS.south],
  [MAP_BOUNDS.east, MAP_BOUNDS.north],
];

/**
 * Walk every coordinate of every feature in the FeatureCollection and return
 * the min/max lng/lat as a MapLibre `LngLatBoundsLike` tuple:
 * `[[minLng, minLat], [maxLng, maxLat]]`.
 *
 * Supports Point, MultiPoint, LineString, MultiLineString, Polygon, and
 * MultiPolygon geometries. Features with `null` geometry or unrecognized
 * types are skipped.
 *
 * Returns `null` when the input is `null`, has no features, or no feature
 * has readable coordinates.
 */
export function getFeatureCollectionBounds(fc: FeatureCollection | null): LngLatBoundsLike | null {
  if (!fc || !Array.isArray(fc.features) || fc.features.length === 0) {
    return null;
  }

  let minLng = Number.POSITIVE_INFINITY;
  let minLat = Number.POSITIVE_INFINITY;
  let maxLng = Number.NEGATIVE_INFINITY;
  let maxLat = Number.NEGATIVE_INFINITY;
  let hasCoords = false;

  const visit = (coord: Position): void => {
    const lng = coord[0];
    const lat = coord[1];
    if (typeof lng !== 'number' || typeof lat !== 'number') return;
    if (lng < minLng) minLng = lng;
    if (lat < minLat) minLat = lat;
    if (lng > maxLng) maxLng = lng;
    if (lat > maxLat) maxLat = lat;
    hasCoords = true;
  };

  for (const feature of fc.features) {
    const geom = feature.geometry as Geometry | null;
    if (!geom) continue;
    switch (geom.type) {
      case 'Point':
        visit(geom.coordinates as Position);
        break;
      case 'MultiPoint':
      case 'LineString':
        for (const c of geom.coordinates as Position[]) visit(c);
        break;
      case 'MultiLineString':
      case 'Polygon':
        for (const ring of geom.coordinates as Position[][]) {
          for (const c of ring) visit(c);
        }
        break;
      case 'MultiPolygon':
        for (const poly of geom.coordinates as Position[][][]) {
          for (const ring of poly) {
            for (const c of ring) visit(c);
          }
        }
        break;
      default:
        // GeometryCollection and unknown types intentionally skipped —
        // the consorcio zone never ships those, and ignoring keeps the
        // helper safe and allocation-free.
        break;
    }
  }

  if (!hasCoords) return null;
  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ];
}

/**
 * Resolve the bbox the export path should fit to:
 *  - If `zonaCollection` has valid features, return its bbox.
 *  - Otherwise, fall back to `MAP_FALLBACK_BOUNDS` (derived from `MAP_BOUNDS`).
 *
 * Never returns `null` — callers can unconditionally pass the result to
 * `map.fitBounds`.
 */
export function resolveConsorcioBounds(zonaCollection: FeatureCollection | null): LngLatBoundsLike {
  return getFeatureCollectionBounds(zonaCollection) ?? MAP_FALLBACK_BOUNDS;
}
