import type { FeatureCollection } from 'geojson';
import type maplibregl from 'maplibre-gl';

import {
  asFeatureCollection,
  type TerrainVectorLayerVisibility,
} from './terrainViewer3DUtils';

export const TERRAIN_SOURCE_IDS = {
  zona: 'terrain-vector-zona',
  approved_zones: 'terrain-vector-approved-zones',
  cuencas: 'terrain-vector-cuencas',
  basins: 'terrain-vector-basins',
  roads: 'terrain-vector-roads',
  waterways: 'terrain-vector-waterways',
  soil: 'terrain-vector-soil',
  catastro: 'terrain-vector-catastro',
  infrastructure: 'terrain-vector-infrastructure',
} as const;

interface TerrainVectorCollections {
  zonaCollection: FeatureCollection | null;
  approvedZonesCollection: FeatureCollection | null | undefined;
  cuencasCollection: FeatureCollection | null;
  basins: FeatureCollection | null | undefined;
  roadsCollection: FeatureCollection | null | undefined;
  waterwaysCollection: FeatureCollection | null;
  soilCollection: FeatureCollection | null;
  catastroCollection: FeatureCollection | null | undefined;
  infrastructureCollection: FeatureCollection | null;
}

function ensureGeoJsonSource(
  map: maplibregl.Map,
  sourceId: string,
  data: FeatureCollection | null | undefined,
) {
  const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  const nextData = data ?? asFeatureCollection([]);

  if (source) {
    source.setData(nextData);
    return;
  }

  map.addSource(sourceId, {
    type: 'geojson',
    data: nextData,
  });
}

function ensureLayerVisibility(
  map: maplibregl.Map,
  layerId: string,
  visible: boolean,
) {
  if (map.getLayer(layerId)) {
    map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
  }
}

function ensureTerrainVectorLayers(
  map: maplibregl.Map,
  collections: TerrainVectorCollections,
) {
  ensureGeoJsonSource(map, TERRAIN_SOURCE_IDS.zona, collections.zonaCollection);
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.zona}-line`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.zona}-line`,
      type: 'line',
      source: TERRAIN_SOURCE_IDS.zona,
      paint: { 'line-color': '#FF0000', 'line-width': 3, 'line-opacity': 0.95 },
    });
  }

  ensureGeoJsonSource(
    map,
    TERRAIN_SOURCE_IDS.approved_zones,
    collections.approvedZonesCollection,
  );
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.approved_zones}-fill`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.approved_zones}-fill`,
      type: 'fill',
      source: TERRAIN_SOURCE_IDS.approved_zones,
      paint: {
        'fill-color': ['coalesce', ['get', '__color'], '#1971c2'],
        'fill-opacity': 0.18,
      },
    });
  }
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.approved_zones}-line`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.approved_zones}-line`,
      type: 'line',
      source: TERRAIN_SOURCE_IDS.approved_zones,
      paint: {
        'line-color': ['coalesce', ['get', '__color'], '#1971c2'],
        'line-width': 3,
        'line-opacity': 0.95,
      },
    });
  }

  ensureGeoJsonSource(map, TERRAIN_SOURCE_IDS.cuencas, collections.cuencasCollection);
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.cuencas}-fill`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.cuencas}-fill`,
      type: 'fill',
      source: TERRAIN_SOURCE_IDS.cuencas,
      paint: {
        'fill-color': ['coalesce', ['get', '__color'], '#3388ff'],
        'fill-opacity': 0.12,
      },
    });
  }
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.cuencas}-line`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.cuencas}-line`,
      type: 'line',
      source: TERRAIN_SOURCE_IDS.cuencas,
      paint: {
        'line-color': ['coalesce', ['get', '__color'], '#3388ff'],
        'line-width': 2,
        'line-opacity': 0.9,
      },
    });
  }

  ensureGeoJsonSource(map, TERRAIN_SOURCE_IDS.basins, collections.basins);
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.basins}-fill`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.basins}-fill`,
      type: 'fill',
      source: TERRAIN_SOURCE_IDS.basins,
      paint: { 'fill-color': '#00897B', 'fill-opacity': 0.08 },
    });
  }
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.basins}-line`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.basins}-line`,
      type: 'line',
      source: TERRAIN_SOURCE_IDS.basins,
      paint: { 'line-color': '#00897B', 'line-width': 1.5, 'line-opacity': 0.95 },
    });
  }

  ensureGeoJsonSource(map, TERRAIN_SOURCE_IDS.roads, collections.roadsCollection);
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.roads}-line`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.roads}-line`,
      type: 'line',
      source: TERRAIN_SOURCE_IDS.roads,
      paint: {
        'line-color': ['coalesce', ['get', 'color'], '#FFEB3B'],
        'line-width': 2,
        'line-opacity': 0.9,
      },
    });
  }

  ensureGeoJsonSource(map, TERRAIN_SOURCE_IDS.waterways, collections.waterwaysCollection);
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.waterways}-line`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.waterways}-line`,
      type: 'line',
      source: TERRAIN_SOURCE_IDS.waterways,
      paint: {
        'line-color': ['coalesce', ['get', '__color'], '#1565C0'],
        'line-width': 3,
        'line-opacity': 0.9,
      },
    });
  }

  ensureGeoJsonSource(map, TERRAIN_SOURCE_IDS.soil, collections.soilCollection);
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.soil}-fill`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.soil}-fill`,
      type: 'fill',
      source: TERRAIN_SOURCE_IDS.soil,
      paint: {
        'fill-color': ['coalesce', ['get', '__color'], '#8d6e63'],
        'fill-opacity': 0.22,
      },
    });
  }
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.soil}-line`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.soil}-line`,
      type: 'line',
      source: TERRAIN_SOURCE_IDS.soil,
      paint: { 'line-color': '#6d4c41', 'line-width': 0.8, 'line-opacity': 0.55 },
    });
  }

  ensureGeoJsonSource(map, TERRAIN_SOURCE_IDS.catastro, collections.catastroCollection);
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.catastro}-line`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.catastro}-line`,
      type: 'line',
      source: TERRAIN_SOURCE_IDS.catastro,
      paint: { 'line-color': '#f8f9fa', 'line-width': 0.7, 'line-opacity': 0.7 },
    });
  }

  ensureGeoJsonSource(
    map,
    TERRAIN_SOURCE_IDS.infrastructure,
    collections.infrastructureCollection,
  );
  if (!map.getLayer(`${TERRAIN_SOURCE_IDS.infrastructure}-circle`)) {
    map.addLayer({
      id: `${TERRAIN_SOURCE_IDS.infrastructure}-circle`,
      type: 'circle',
      source: TERRAIN_SOURCE_IDS.infrastructure,
      paint: {
        'circle-color': ['coalesce', ['get', '__color'], '#fd7e14'],
        'circle-radius': 6,
        'circle-opacity': 0.95,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 1.5,
      },
    });
  }
}

export function syncTerrainVectorLayers(
  map: maplibregl.Map,
  collections: TerrainVectorCollections,
  visibility: TerrainVectorLayerVisibility,
) {
  ensureTerrainVectorLayers(map, collections);

  ensureLayerVisibility(
    map,
    `${TERRAIN_SOURCE_IDS.approved_zones}-fill`,
    visibility.approved_zones && !!collections.approvedZonesCollection,
  );
  ensureLayerVisibility(
    map,
    `${TERRAIN_SOURCE_IDS.approved_zones}-line`,
    visibility.approved_zones && !!collections.approvedZonesCollection,
  );
  ensureLayerVisibility(
    map,
    `${TERRAIN_SOURCE_IDS.zona}-line`,
    visibility.zona && !!collections.zonaCollection,
  );
  ensureLayerVisibility(map, `${TERRAIN_SOURCE_IDS.cuencas}-fill`, false);
  ensureLayerVisibility(map, `${TERRAIN_SOURCE_IDS.cuencas}-line`, false);
  ensureLayerVisibility(
    map,
    `${TERRAIN_SOURCE_IDS.basins}-fill`,
    visibility.basins && !!collections.basins,
  );
  ensureLayerVisibility(
    map,
    `${TERRAIN_SOURCE_IDS.basins}-line`,
    visibility.basins && !!collections.basins,
  );
  ensureLayerVisibility(
    map,
    `${TERRAIN_SOURCE_IDS.roads}-line`,
    visibility.roads && !!collections.roadsCollection,
  );
  ensureLayerVisibility(
    map,
    `${TERRAIN_SOURCE_IDS.waterways}-line`,
    visibility.waterways && !!collections.waterwaysCollection,
  );
  ensureLayerVisibility(
    map,
    `${TERRAIN_SOURCE_IDS.soil}-fill`,
    visibility.soil && !!collections.soilCollection,
  );
  ensureLayerVisibility(
    map,
    `${TERRAIN_SOURCE_IDS.soil}-line`,
    visibility.soil && !!collections.soilCollection,
  );
  ensureLayerVisibility(
    map,
    `${TERRAIN_SOURCE_IDS.catastro}-line`,
    visibility.catastro && !!collections.catastroCollection,
  );
  ensureLayerVisibility(
    map,
    `${TERRAIN_SOURCE_IDS.infrastructure}-circle`,
    visibility.infrastructure && !!collections.infrastructureCollection,
  );
}
