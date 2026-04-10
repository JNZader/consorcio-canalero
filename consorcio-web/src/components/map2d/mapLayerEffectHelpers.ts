import type { FeatureCollection } from 'geojson';
import type maplibregl from 'maplibre-gl';

import { getMartinTileUrl } from '../../hooks/useMartinLayers';
import type { WATERWAY_DEFS } from '../../hooks/useWaterways';
import { SOURCE_IDS, buildWaterwayLayerConfigs } from './map2dConfig';
import { asFeatureCollection, ensureGeoJsonSource, setLayerVisibility } from './map2dUtils';

interface LayerLike {
  id: string;
  nombre: string;
  tipo: string;
}

interface PublicLayerLike extends LayerLike {
  data?: FeatureCollection | null;
}

export function syncBaseTileVisibility(
  map: maplibregl.Map,
  baseLayer: 'osm' | 'satellite',
) {
  setLayerVisibility(map, 'osm-tiles', baseLayer === 'osm');
  setLayerVisibility(map, 'satellite-tiles', baseLayer === 'satellite');
}

export function syncWaterwayLayers(
  map: maplibregl.Map,
  waterwaysDefs: readonly (typeof WATERWAY_DEFS)[number][],
  isVisible: boolean,
) {
  const waterwayFiles = buildWaterwayLayerConfigs(waterwaysDefs);

  for (const waterwayFile of waterwayFiles) {
    if (!map.getSource(waterwayFile.id)) {
      map.addSource(waterwayFile.id, { type: 'vector', url: waterwayFile.url });
    }

    const lineLayerId = `${waterwayFile.id}-line`;
    if (!map.getLayer(lineLayerId)) {
      map.addLayer({
        id: lineLayerId,
        type: 'line',
        source: waterwayFile.id,
        'source-layer': waterwayFile.layer,
        paint: {
          'line-color': waterwayFile.color,
          'line-width': waterwayFile.layer === 'canales_existentes' ? 4 : 3,
          'line-opacity': 0.9,
          ...(waterwayFile.layer === 'canales_existentes'
            ? { 'line-dasharray': [3, 2] }
            : {}),
        },
      });
    }

    setLayerVisibility(map, lineLayerId, isVisible);
  }
}

export function syncSoilLayers(
  map: maplibregl.Map,
  soilCollection: FeatureCollection | null,
  isVisible: boolean,
) {
  ensureGeoJsonSource(map, SOURCE_IDS.SOIL, soilCollection ?? asFeatureCollection([]));

  if (!map.getLayer(`${SOURCE_IDS.SOIL}-fill`)) {
    map.addLayer({
      id: `${SOURCE_IDS.SOIL}-fill`,
      type: 'fill',
      source: SOURCE_IDS.SOIL,
      paint: {
        'fill-color': ['coalesce', ['get', '__color'], '#8d6e63'],
        'fill-opacity': 0.22,
      },
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.SOIL}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.SOIL}-line`,
      type: 'line',
      source: SOURCE_IDS.SOIL,
      paint: { 'line-color': '#6d4c41', 'line-width': 0.8, 'line-opacity': 0.55 },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.SOIL}-fill`, isVisible);
  setLayerVisibility(map, `${SOURCE_IDS.SOIL}-line`, isVisible);
}

export function syncCatastroLayers(map: maplibregl.Map, isVisible: boolean) {
  if (!map.getSource(SOURCE_IDS.CATASTRO)) {
    map.addSource(SOURCE_IDS.CATASTRO, {
      type: 'vector',
      tiles: [getMartinTileUrl('parcelas_catastro')],
      minzoom: 8,
      maxzoom: 19,
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.CATASTRO}-fill`)) {
    map.addLayer({
      id: `${SOURCE_IDS.CATASTRO}-fill`,
      type: 'fill',
      source: SOURCE_IDS.CATASTRO,
      'source-layer': 'parcelas_catastro',
      paint: { 'fill-color': '#8d6e63', 'fill-opacity': 0.08 },
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.CATASTRO}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.CATASTRO}-line`,
      type: 'line',
      source: SOURCE_IDS.CATASTRO,
      'source-layer': 'parcelas_catastro',
      paint: { 'line-color': '#6d4c41', 'line-width': 0.8, 'line-opacity': 0.5 },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.CATASTRO}-fill`, isVisible);
  setLayerVisibility(map, `${SOURCE_IDS.CATASTRO}-line`, isVisible);
}

export function syncRoadLayers(
  map: maplibregl.Map,
  roadsCollection: FeatureCollection | null | undefined,
  isVisible: boolean,
) {
  ensureGeoJsonSource(map, SOURCE_IDS.ROADS, roadsCollection ?? asFeatureCollection([]));

  if (!map.getLayer(`${SOURCE_IDS.ROADS}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.ROADS}-line`,
      type: 'line',
      source: SOURCE_IDS.ROADS,
      paint: {
        'line-color': ['coalesce', ['get', 'color'], '#FFEB3B'],
        'line-width': 2,
        'line-opacity': 0.9,
      },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.ROADS}-line`, isVisible && !!roadsCollection);
}

export function syncBasinLayers(
  map: maplibregl.Map,
  basins: FeatureCollection | null | undefined,
  isVisible: boolean,
) {
  ensureGeoJsonSource(map, SOURCE_IDS.BASINS, basins ?? asFeatureCollection([]));

  if (!map.getLayer(`${SOURCE_IDS.BASINS}-fill`)) {
    map.addLayer({
      id: `${SOURCE_IDS.BASINS}-fill`,
      type: 'fill',
      source: SOURCE_IDS.BASINS,
      paint: { 'fill-color': '#00897B', 'fill-opacity': 0.08 },
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.BASINS}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.BASINS}-line`,
      type: 'line',
      source: SOURCE_IDS.BASINS,
      paint: { 'line-color': '#00897B', 'line-width': 1.5, 'line-opacity': 0.95 },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.BASINS}-fill`, isVisible && !!basins);
  setLayerVisibility(map, `${SOURCE_IDS.BASINS}-line`, isVisible && !!basins);
}

export function syncZonaLayer(
  map: maplibregl.Map,
  zonaCollection: FeatureCollection | null,
) {
  ensureGeoJsonSource(map, SOURCE_IDS.ZONA, zonaCollection ?? asFeatureCollection([]));

  if (!map.getLayer(`${SOURCE_IDS.ZONA}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.ZONA}-line`,
      type: 'line',
      source: SOURCE_IDS.ZONA,
      paint: { 'line-color': '#FF0000', 'line-width': 3, 'line-opacity': 0.95 },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.ZONA}-line`, !!zonaCollection);
}

export function syncApprovedZoneLayers(
  map: maplibregl.Map,
  approvedZonesCollection: FeatureCollection | null | undefined,
  isVisible: boolean,
) {
  ensureGeoJsonSource(
    map,
    SOURCE_IDS.APPROVED_ZONES,
    approvedZonesCollection ?? asFeatureCollection([]),
  );

  if (!map.getLayer(`${SOURCE_IDS.APPROVED_ZONES}-fill`)) {
    map.addLayer({
      id: `${SOURCE_IDS.APPROVED_ZONES}-fill`,
      type: 'fill',
      source: SOURCE_IDS.APPROVED_ZONES,
      paint: {
        'fill-color': ['coalesce', ['get', '__color'], '#1971c2'],
        'fill-opacity': 0.18,
      },
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.APPROVED_ZONES}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.APPROVED_ZONES}-line`,
      type: 'line',
      source: SOURCE_IDS.APPROVED_ZONES,
      paint: {
        'line-color': ['coalesce', ['get', '__color'], '#1971c2'],
        'line-width': 3,
        'line-opacity': 0.95,
      },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.APPROVED_ZONES}-fill`, isVisible && !!approvedZonesCollection);
  setLayerVisibility(map, `${SOURCE_IDS.APPROVED_ZONES}-line`, isVisible && !!approvedZonesCollection);
}

export function shouldShowSuggestedZones(params: {
  showSuggestedZonesPanel: boolean;
  hasApprovedZones: boolean;
  suggestedZonesDisplay: FeatureCollection | null;
}) {
  return (
    params.showSuggestedZonesPanel &&
    !params.hasApprovedZones &&
    !!params.suggestedZonesDisplay
  );
}

export function syncSuggestedZoneLayers(
  map: maplibregl.Map,
  suggestedZonesDisplay: FeatureCollection | null,
  isVisible: boolean,
) {
  ensureGeoJsonSource(
    map,
    SOURCE_IDS.SUGGESTED_ZONES,
    suggestedZonesDisplay ?? asFeatureCollection([]),
  );

  if (!map.getLayer(`${SOURCE_IDS.SUGGESTED_ZONES}-fill`)) {
    map.addLayer({
      id: `${SOURCE_IDS.SUGGESTED_ZONES}-fill`,
      type: 'fill',
      source: SOURCE_IDS.SUGGESTED_ZONES,
      paint: {
        'fill-color': ['coalesce', ['get', '__color'], '#1971c2'],
        'fill-opacity': 0.15,
      },
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.SUGGESTED_ZONES}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.SUGGESTED_ZONES}-line`,
      type: 'line',
      source: SOURCE_IDS.SUGGESTED_ZONES,
      paint: {
        'line-color': ['coalesce', ['get', '__color'], '#1971c2'],
        'line-width': 2,
        'line-opacity': 0.9,
        'line-dasharray': [4, 4],
      },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.SUGGESTED_ZONES}-fill`, isVisible);
  setLayerVisibility(map, `${SOURCE_IDS.SUGGESTED_ZONES}-line`, isVisible);
}

export function syncInfrastructureLayer(
  map: maplibregl.Map,
  infrastructureCollection: FeatureCollection | null,
  isVisible: boolean,
) {
  ensureGeoJsonSource(
    map,
    SOURCE_IDS.INFRASTRUCTURE,
    infrastructureCollection ?? asFeatureCollection([]),
  );

  if (!map.getLayer(`${SOURCE_IDS.INFRASTRUCTURE}-circle`)) {
    map.addLayer({
      id: `${SOURCE_IDS.INFRASTRUCTURE}-circle`,
      type: 'circle',
      source: SOURCE_IDS.INFRASTRUCTURE,
      paint: {
        'circle-color': ['coalesce', ['get', '__color'], '#fd7e14'],
        'circle-radius': 6,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 1.5,
      },
    });
  }

  setLayerVisibility(
    map,
    `${SOURCE_IDS.INFRASTRUCTURE}-circle`,
    isVisible && !!infrastructureCollection,
  );
}

export function syncPublicLayers(
  map: maplibregl.Map,
  publicLayers: PublicLayerLike[],
  isVisible: boolean,
) {
  for (const layer of publicLayers) {
    const sourceId = `${SOURCE_IDS.PUBLIC_LAYERS_PREFIX}${layer.id}`;
    const fillLayerId = `${sourceId}-fill`;
    const lineLayerId = `${sourceId}-line`;

    ensureGeoJsonSource(map, sourceId, layer.data ?? asFeatureCollection([]));

    if (!map.getLayer(fillLayerId)) {
      map.addLayer({
        id: fillLayerId,
        type: 'fill',
        source: sourceId,
        paint: { 'fill-color': '#4dabf7', 'fill-opacity': 0.18 },
      });
    }

    if (!map.getLayer(lineLayerId)) {
      map.addLayer({
        id: lineLayerId,
        type: 'line',
        source: sourceId,
        paint: { 'line-color': '#228be6', 'line-width': 1.5, 'line-opacity': 0.95 },
      });
    }

    setLayerVisibility(map, fillLayerId, isVisible);
    setLayerVisibility(map, lineLayerId, isVisible);
  }
}
