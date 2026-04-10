import type { Feature, FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';
import type maplibregl from 'maplibre-gl';

// MapLibre note: center is [lng, lat] — opposite from Leaflet [lat, lng]
export function leafletCenterToMapLibre(center: [number, number]): [number, number] {
  return [center[1], center[0]];
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
    properties: { ...(feature.properties ?? {}), ...properties },
  };
}

/**
 * Upsert a GeoJSON source: setData if source exists, else addSource + addLayer.
 */
export function ensureGeoJsonSource(
  map: maplibregl.Map,
  sourceId: string,
  data: FeatureCollection,
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
export const IGN_MAPLIBRE_COORDS: [[number, number], [number, number], [number, number], [number, number]] = [
  [-62.750969, -32.44785],
  [-62.345994, -32.44785],
  [-62.345994, -32.665914],
  [-62.750969, -32.665914],
];

export const IGN_IMAGE_URL = '/overlays/ign/altimetria_ign_consorcio.webp';
