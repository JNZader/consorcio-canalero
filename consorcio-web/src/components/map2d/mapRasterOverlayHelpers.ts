import type maplibregl from 'maplibre-gl';

import { MARTIN_SOURCES, getMartinTileUrl } from '../../hooks/useMartinLayers';
import { SOURCE_IDS } from './map2dConfig';
import { IGN_IMAGE_URL, IGN_MAPLIBRE_COORDS, setLayerVisibility } from './map2dUtils';

interface LayerLike {
  id: string;
  nombre: string;
  tipo: string;
}

function removeRasterOverlay(map: maplibregl.Map, sourceId: string) {
  if (map.getLayer(`${sourceId}-layer`)) {
    map.removeLayer(`${sourceId}-layer`);
  }
  if (map.getSource(sourceId)) {
    map.removeSource(sourceId);
  }
}

function addRasterOverlay(
  map: maplibregl.Map,
  sourceId: string,
  tileUrl: string,
  beforeLayerId = 'vector-layers-start',
) {
  removeRasterOverlay(map, sourceId);
  map.addSource(sourceId, {
    type: 'raster',
    tiles: [tileUrl],
    tileSize: 256,
  });
  map.addLayer(
    {
      id: `${sourceId}-layer`,
      type: 'raster',
      source: sourceId,
      paint: { 'raster-opacity': 0.85 },
    },
    beforeLayerId,
  );
}

export function syncDemRasterLayer(
  map: maplibregl.Map,
  params: {
    showDemOverlay: boolean;
    activeDemLayerId: string | null;
    demTileUrl: string | null;
  },
) {
  if (!params.showDemOverlay || !params.activeDemLayerId || !params.demTileUrl) {
    setLayerVisibility(map, `${SOURCE_IDS.DEM_RASTER}-layer`, false);
    return;
  }

  const existing = map.getSource(SOURCE_IDS.DEM_RASTER) as
    | maplibregl.RasterTileSource
    | undefined;

  if (existing) {
    (
      existing as maplibregl.RasterTileSource & {
        setTiles?: (tiles: string[]) => void;
      }
    ).setTiles?.([params.demTileUrl]);
  } else {
    map.addSource(SOURCE_IDS.DEM_RASTER, {
      type: 'raster',
      tiles: [params.demTileUrl],
      tileSize: 256,
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.DEM_RASTER}-layer`)) {
    map.addLayer(
      {
        id: `${SOURCE_IDS.DEM_RASTER}-layer`,
        type: 'raster',
        source: SOURCE_IDS.DEM_RASTER,
        paint: { 'raster-opacity': 0.8 },
      },
      'vector-layers-start',
    );
  } else {
    setLayerVisibility(map, `${SOURCE_IDS.DEM_RASTER}-layer`, true);
  }
}

export function getVisibleRasterLayersForDem(
  allGeoLayers: LayerLike[],
  showDemOverlay: boolean,
  activeDemLayerId: string | null,
) {
  if (!showDemOverlay || !activeDemLayerId) {
    return [] as Array<{ tipo: string }>;
  }

  const layer = allGeoLayers.find((item) => item.id === activeDemLayerId);
  return layer ? [{ tipo: layer.tipo }] : [];
}

export function syncIgnLayer(map: maplibregl.Map, showIGNOverlay: boolean) {
  if (!map.getSource(SOURCE_IDS.IGN)) {
    map.addSource(SOURCE_IDS.IGN, {
      type: 'image',
      url: IGN_IMAGE_URL,
      coordinates: IGN_MAPLIBRE_COORDS,
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.IGN}-layer`)) {
    map.addLayer(
      {
        id: `${SOURCE_IDS.IGN}-layer`,
        type: 'raster',
        source: SOURCE_IDS.IGN,
        paint: { 'raster-opacity': 0.65 },
      },
      'vector-layers-start',
    );
  }

  setLayerVisibility(map, `${SOURCE_IDS.IGN}-layer`, showIGNOverlay);
}

export function syncImageOverlays(
  map: maplibregl.Map,
  params: {
    baseLayer: 'osm' | 'satellite';
    viewMode: 'base' | 'single' | 'comparison';
    selectedImage: { tile_url: string } | null;
    comparison: {
      left?: { tile_url: string } | null;
      right?: { tile_url: string } | null;
    } | null;
  },
) {
  // Image overlays only apply when the user is actively showing satellite
  // imagery as the base layer; in OSM mode they are always hidden so the
  // user gets the plain street map even if a previously selected image is
  // still persisted in the imagery store.
  const showImagery = params.baseLayer === 'satellite';
  const showSingle =
    showImagery && params.viewMode === 'single' && !!params.selectedImage;
  const showComparison =
    showImagery &&
    params.viewMode === 'comparison' &&
    !!params.comparison?.left &&
    !!params.comparison?.right;

  if (showSingle && params.selectedImage) {
    addRasterOverlay(map, SOURCE_IDS.SATELLITE_IMAGE, params.selectedImage.tile_url);
  } else {
    removeRasterOverlay(map, SOURCE_IDS.SATELLITE_IMAGE);
  }

  if (showComparison && params.comparison?.right) {
    removeRasterOverlay(map, SOURCE_IDS.COMPARISON_LEFT);
    addRasterOverlay(map, SOURCE_IDS.COMPARISON_RIGHT, params.comparison.right.tile_url);
  } else {
    removeRasterOverlay(map, SOURCE_IDS.COMPARISON_LEFT);
    removeRasterOverlay(map, SOURCE_IDS.COMPARISON_RIGHT);
  }
}

export function syncMartinSuggestionLayers(
  map: maplibregl.Map,
  params: {
    showConflictPoints: boolean;
  },
) {
  const puntosStyle = MARTIN_SOURCES.puntos_conflicto.style;

  if (!map.getSource(SOURCE_IDS.MARTIN_PUNTOS)) {
    map.addSource(SOURCE_IDS.MARTIN_PUNTOS, {
      type: 'vector',
      tiles: [getMartinTileUrl('puntos_conflicto')],
      minzoom: 0,
      maxzoom: 22,
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.MARTIN_PUNTOS}-circle`)) {
    map.addLayer({
      id: `${SOURCE_IDS.MARTIN_PUNTOS}-circle`,
      type: 'circle',
      source: SOURCE_IDS.MARTIN_PUNTOS,
      'source-layer': 'puntos_conflicto',
      paint: {
        'circle-color': puntosStyle.fillColor,
        'circle-opacity': puntosStyle.fillOpacity,
        'circle-radius': puntosStyle.radius ?? 5,
        'circle-stroke-color': puntosStyle.color,
        'circle-stroke-width': puntosStyle.weight,
      },
    });
  }
  setLayerVisibility(
    map,
    `${SOURCE_IDS.MARTIN_PUNTOS}-circle`,
    params.showConflictPoints,
  );
}
