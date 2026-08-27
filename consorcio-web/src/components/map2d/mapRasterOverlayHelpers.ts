import type maplibregl from 'maplibre-gl';

import { buildTileUrl, findPrecipNormalLayer, type GeoLayerInfo } from '../../hooks/useGeoLayers';
import { HAZARD_RISK_CLASSES } from '../../hooks/useHazardUrlState';
import { MARTIN_SOURCES, getMartinTileUrl } from '../../hooks/useMartinLayers';
import { SOURCE_IDS } from './map2dConfig';
import { IGN_IMAGE_URL, IGN_MAPLIBRE_COORDS, setLayerVisibility } from './map2dUtils';
import { PILAR_VERDE_Z_ORDER } from './pilarVerdeLayers';

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
  beforeLayerId = 'vector-layers-start'
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
    beforeLayerId
  );
}

function getRasterTiles(source: maplibregl.Source | undefined): string[] | undefined {
  const serializableSource = source as
    | (maplibregl.Source & { serialize?: () => { tiles?: string[] }; tiles?: string[] })
    | undefined;
  return serializableSource?.serialize?.().tiles ?? serializableSource?.tiles;
}

type RasterTileSourceWithSetter = maplibregl.RasterTileSource & {
  setTiles?: (tiles: string[]) => void;
};

function syncHazardRasterSource(
  map: maplibregl.Map,
  sourceId: string,
  tileUrl: string | null,
  visible: boolean
) {
  const layerId = `${sourceId}-layer`;
  if (!visible || !tileUrl) {
    setLayerVisibility(map, layerId, false);
    return;
  }

  const source = map.getSource(sourceId) as maplibregl.RasterTileSource | undefined;
  if (!source) {
    map.addSource(sourceId, { type: 'raster', tiles: [tileUrl], tileSize: 256 });
  } else if (getRasterTiles(source)?.[0] !== tileUrl) {
    const mutableSource = source as RasterTileSourceWithSetter;
    if (mutableSource.setTiles) {
      mutableSource.setTiles([tileUrl]);
    } else {
      removeRasterOverlay(map, sourceId);
      map.addSource(sourceId, { type: 'raster', tiles: [tileUrl], tileSize: 256 });
    }
  }

  if (!map.getLayer(layerId)) {
    map.addLayer(
      {
        id: layerId,
        type: 'raster',
        source: sourceId,
        paint: { 'raster-opacity': 0.55 },
      },
      'vector-layers-start'
    );
  } else {
    setLayerVisibility(map, layerId, true);
  }
}

export function syncPrecipNormalLayer(
  map: maplibregl.Map,
  params: {
    readonly isHazardActive: boolean;
    readonly precipMonth: string;
    readonly allGeoLayers: readonly GeoLayerInfo[];
  }
) {
  const layer = findPrecipNormalLayer(params.allGeoLayers, params.precipMonth);
  const rescaleMax = params.precipMonth === 'anual' ? 1800 : 200;
  syncHazardRasterSource(
    map,
    SOURCE_IDS.PRECIP_NORMAL,
    layer ? buildTileUrl(layer.id, { rescaleMin: 0, rescaleMax }) : null,
    params.isHazardActive
  );
}

function findRiskLayer(
  allGeoLayers: readonly GeoLayerInfo[],
  type: string
): GeoLayerInfo | undefined {
  return (
    allGeoLayers.find((layer) => layer.tipo === type && layer.variante === 'relevado') ??
    allGeoLayers.find((layer) => layer.tipo === type)
  );
}

function hiddenRiskRanges(activeRiskClasses: readonly string[]): number[] {
  return HAZARD_RISK_CLASSES.flatMap((riskClass, index) =>
    activeRiskClasses.includes(riskClass) ? [] : [index]
  );
}

export function syncHazardRiskLayers(
  map: maplibregl.Map,
  params: {
    readonly isHazardActive: boolean;
    readonly activeRiskClasses: readonly string[];
    readonly allGeoLayers: readonly GeoLayerInfo[];
  }
) {
  const hideRanges = hiddenRiskRanges(params.activeRiskClasses);
  const riskLayers = [
    [SOURCE_IDS.FLOOD_RISK, 'flood_risk'],
    [SOURCE_IDS.DRAINAGE_NEED, 'drainage_need'],
  ] as const;

  for (const [sourceId, type] of riskLayers) {
    const layer = findRiskLayer(params.allGeoLayers, type);
    syncHazardRasterSource(
      map,
      sourceId,
      layer ? buildTileUrl(layer.id, { hideRanges }) : null,
      params.isHazardActive
    );
  }
}

export function syncDemRasterLayer(
  map: maplibregl.Map,
  params: {
    showDemOverlay: boolean;
    activeDemLayerId: string | null;
    demTileUrl: string | null;
  }
) {
  if (!params.showDemOverlay || !params.activeDemLayerId || !params.demTileUrl) {
    setLayerVisibility(map, `${SOURCE_IDS.DEM_RASTER}-layer`, false);
    return;
  }

  const existing = map.getSource(SOURCE_IDS.DEM_RASTER) as maplibregl.RasterTileSource | undefined;
  const existingTiles = getRasterTiles(existing);
  const sourceHasCurrentTiles = existingTiles?.[0] === params.demTileUrl;

  if (existing && sourceHasCurrentTiles) {
    (
      existing as maplibregl.RasterTileSource & {
        setTiles?: (tiles: string[]) => void;
      }
    ).setTiles?.([params.demTileUrl]);
  } else if (existing) {
    removeRasterOverlay(map, SOURCE_IDS.DEM_RASTER);
    map.addSource(SOURCE_IDS.DEM_RASTER, {
      type: 'raster',
      tiles: [params.demTileUrl],
      tileSize: 256,
    });
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
        paint: { 'raster-opacity': 0.6 },
      },
      'vector-layers-start'
    );
  } else {
    setLayerVisibility(map, `${SOURCE_IDS.DEM_RASTER}-layer`, true);
  }
}

/**
 * Hoist the DEM raster ABOVE contextual context vectors (soil / catastro /
 * basins / roads / waterways) while keeping it BELOW the user-authored stack
 * (Pilar Verde fills + Canales lines + zonas). Prevents the translucent DEM
 * overlay from dimming cadastral and soil detail, which is the primary reason
 * the user requested the layer-visibility audit.
 *
 * No-op when the DEM layer is absent (DEM toggled off) — next sync pass will
 * call this again once the layer is re-added.
 *
 * The "before" target is resolved in priority order:
 *   1. The lowest-in-stack Pilar Verde layer currently mounted
 *      (zonas < forestación < presentada < aceptada < bpa).
 *   2. Otherwise, the Canales relevados line layer (the lowest canal layer).
 *   3. Otherwise, `moveLayer` without a `beforeId` — places DEM on top, which
 *      is fine in this fallback because no user layer is mounted yet.
 *
 * MapLibre's `moveLayer(id, beforeId)` signature means the moved layer lands
 * JUST BELOW `beforeId` in the style order (= renders UNDER it). That's
 * exactly the relationship we want.
 */
export function moveDemAboveContextualVectors(map: maplibregl.Map) {
  const demLayerId = `${SOURCE_IDS.DEM_RASTER}-layer`;
  if (!map.getLayer(demLayerId)) return;

  let beforeId: string | undefined;

  // 1. Prefer the lowest Pilar Verde fill layer (first mounted in z-order).
  for (const pvId of PILAR_VERDE_Z_ORDER) {
    const candidate = `${pvId}-fill`;
    if (map.getLayer(candidate)) {
      beforeId = candidate;
      break;
    }
  }

  // 2. Fallback to the canales relevados line.
  if (!beforeId) {
    const canalesRelevadosLine = `${SOURCE_IDS.CANALES_RELEVADOS}-line`;
    if (map.getLayer(canalesRelevadosLine)) {
      beforeId = canalesRelevadosLine;
    }
  }

  // 3. Fallback to the canales propuestos line.
  if (!beforeId) {
    const canalesPropuestosLine = `${SOURCE_IDS.CANALES_PROPUESTOS}-line`;
    if (map.getLayer(canalesPropuestosLine)) {
      beforeId = canalesPropuestosLine;
    }
  }

  try {
    // `moveLayer(id)` (no beforeId) hoists to the top; that's fine in the
    // no-user-layers-mounted case. Otherwise place DEM just below the lowest
    // user layer so it still covers the contextual vectors.
    if (beforeId) {
      map.moveLayer(demLayerId, beforeId);
    } else {
      map.moveLayer(demLayerId);
    }
  } catch {
    // moveLayer can race with concurrent style edits — safe to ignore. Next
    // sync pass will retry.
  }
}

export function getVisibleRasterLayersForDem(
  allGeoLayers: LayerLike[],
  showDemOverlay: boolean,
  activeDemLayerId: string | null
) {
  if (!showDemOverlay || !activeDemLayerId) {
    return [] as Array<{ tipo: string }>;
  }

  const layer = allGeoLayers.find((item) => item.id === activeDemLayerId);
  return layer ? [{ tipo: layer.tipo }] : [];
}

/**
 * Mount (or just toggle) the historic IGN altimetry raster.
 *
 * LAZY BY CONTRACT (PERF): the layer is OFF by default, yet this used to add the
 * image source unconditionally and only then set `visibility: none` — so every
 * single visitor of `/mapa` downloaded ~1.5 MB of WebP (2.7 MB before the
 * resize) and paid the GPU upload for a layer they never asked for. Now nothing
 * is added until the user actually turns it on; once mounted the layer stays
 * mounted and toggling is a cheap visibility flip (no re-download).
 *
 * The effect in `useMapLayerEffects` already re-runs on `showIGNOverlay`, so the
 * first "on" reaches this function and does the real work.
 *
 * TOGGLING DOES NOT RETRY A FAILED DOWNLOAD (B4c fix round): once the source
 * exists this is a pure `visibility` flip, and `ImageSource` fetches exactly ONCE
 * (`onAdd` → `load`; `loadTile` only marks the tile errored — maplibre-gl
 * `ImageSource`). So a 404 leaves the layer permanently blank and turning it off
 * and on again changes nothing. {@link reloadIgnSource} is the ONLY recovery.
 */
export function syncIgnLayer(map: maplibregl.Map, showIGNOverlay: boolean) {
  // Never mounted and not wanted → do not touch the map at all.
  if (!showIGNOverlay && !map.getSource(SOURCE_IDS.IGN)) return;

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
      'vector-layers-start'
    );
  }

  setLayerVisibility(map, `${SOURCE_IDS.IGN}-layer`, showIGNOverlay);
}

/**
 * Re-download the IGN altimetry image — the REAL retry behind the health entry.
 *
 * Why a rebuild and not a flag: a MapLibre `ImageSource` issues its single
 * request from `onAdd` (`ImageSource.onAdd` → `load()`), and nothing in the tile
 * lifecycle ever repeats it — `loadTile` just marks the tile errored. Removing
 * the layer + source and adding them back therefore runs `onAdd` again, which is
 * what actually re-fetches the WebP.
 *
 * `updateImage({url})` would also re-`load()` with one less removal, but it only
 * works when the source is already mounted; the rebuild ALSO recovers a
 * half-mounted state (source present, layer gone) and reuses `syncIgnLayer` as
 * the single place that knows how the layer is built (paint, insertion point,
 * visibility). One construction site, not two that can drift.
 *
 * Safe to call when nothing is mounted: `removeRasterOverlay` is guarded and
 * `syncIgnLayer(map, false)` is a no-op.
 */
export function reloadIgnSource(map: maplibregl.Map, showIGNOverlay: boolean) {
  removeRasterOverlay(map, SOURCE_IDS.IGN);
  syncIgnLayer(map, showIGNOverlay);
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
  }
) {
  // Image overlays only apply when the user is actively showing satellite
  // imagery as the base layer; in OSM mode they are always hidden so the
  // user gets the plain street map even if a previously selected image is
  // still persisted in the imagery store.
  const showImagery = params.baseLayer === 'satellite';
  const showSingle = showImagery && params.viewMode === 'single' && !!params.selectedImage;
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
  }
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
  setLayerVisibility(map, `${SOURCE_IDS.MARTIN_PUNTOS}-circle`, params.showConflictPoints);
}
