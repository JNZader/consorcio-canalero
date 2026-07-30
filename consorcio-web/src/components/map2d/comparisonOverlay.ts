import type { FeatureCollection, LineString, Point } from 'geojson';
import type maplibregl from 'maplibre-gl';

import type { WATERWAY_DEFS } from '../../hooks/useWaterways';
import type { CanalFeatureProperties, Etapa } from '../../types/canales';
import type { EscuelaFeatureProperties } from '../../types/escuelas';
import type { PilarVerdeData } from '../../types/pilarVerde';
import {
  LAYER_RENDER_REGISTRY,
  RENDERABLE_UI_LAYER_IDS,
  type RenderableUiLayerId,
  applyLayerOpacity,
  applyLayerOrder,
} from './layerRenderRegistry';
import { buildWaterwayLayerConfigs } from './map2dConfig';
import { setLayerVisibility } from './map2dUtils';
import {
  syncAgroAceptadaLayer,
  syncAgroPresentadaLayer,
  syncAgroZonasLayer,
  syncApprovedZoneLayers,
  syncBasinLayers,
  syncBpaHistoricoLayer,
  syncCanalesLayers,
  syncCatastroLayers,
  syncEscuelasLayer,
  syncPorcentajeForestacionLayer,
  syncRoadLayers,
  syncSoilLayers,
  syncWaterwayLayers,
} from './mapLayerEffectHelpers';
import { syncMartinSuggestionLayers } from './mapRasterOverlayHelpers';

const COMPARISON_SOURCE_ID = 'comparison-left';
const COMPARISON_LAYER_ID = 'comparison-left-layer';

export const COMPARISON_RENDERABLE_UI_LAYER_IDS = [
  'basins',
  'approved_zones',
  'waterways',
  'roads',
  'soil',
  'catastro',
  'puntos_conflicto',
  'pilar_verde_bpa_historico',
  'pilar_verde_agro_aceptada',
  'pilar_verde_agro_presentada',
  'pilar_verde_agro_zonas',
  'pilar_verde_porcentaje_forestacion',
  'canales_relevados',
  'canales_propuestos',
  'escuelas',
] as const satisfies readonly RenderableUiLayerId[];

export interface ComparisonCanalesSyncInputs {
  relevados: FeatureCollection<LineString, CanalFeatureProperties> | null;
  propuestas: FeatureCollection<LineString, CanalFeatureProperties> | null;
  visibleRelevadoIds: readonly string[];
  visiblePropuestaIds: readonly string[];
  activeEtapas: readonly Etapa[];
}

export interface ComparisonOverlaySyncInputs {
  leftTileUrl: string;
  vectorVisibility: Readonly<Record<string, boolean>>;
  waterwaysDefs: readonly (typeof WATERWAY_DEFS)[number][];
  soilCollection: FeatureCollection | null;
  roadsCollection: FeatureCollection | null | undefined;
  basins: FeatureCollection | null | undefined;
  approvedZonesCollection: FeatureCollection | null | undefined;
  pilarVerde?: Partial<PilarVerdeData> | null;
  canales: ComparisonCanalesSyncInputs;
  escuelasCollection: FeatureCollection<Point, EscuelaFeatureProperties> | null;
  opacityByLayer: Record<string, number> | undefined;
  orderByLayer: readonly string[] | undefined;
}

function findFirstRenderableLayer(map: maplibregl.Map): string | undefined {
  for (const id of RENDERABLE_UI_LAYER_IDS) {
    for (const layer of LAYER_RENDER_REGISTRY[id].mlLayers) {
      if (map.getLayer(layer.id)) return layer.id;
    }
  }
  return undefined;
}

export function syncComparisonRasterLayer(map: maplibregl.Map, leftTileUrl: string): void {
  if (map.getLayer(COMPARISON_LAYER_ID)) {
    map.removeLayer(COMPARISON_LAYER_ID);
  }
  if (map.getSource(COMPARISON_SOURCE_ID)) {
    map.removeSource(COMPARISON_SOURCE_ID);
  }

  map.addSource(COMPARISON_SOURCE_ID, {
    type: 'raster',
    tiles: [leftTileUrl],
    tileSize: 256,
  });
  map.addLayer(
    {
      id: COMPARISON_LAYER_ID,
      type: 'raster',
      source: COMPARISON_SOURCE_ID,
      paint: { 'raster-opacity': 1 },
    },
    findFirstRenderableLayer(map)
  );
}

export function syncComparisonVectorLayers(
  map: maplibregl.Map,
  inputs: ComparisonOverlaySyncInputs
): void {
  const visible = inputs.vectorVisibility;

  syncWaterwayLayers(map, inputs.waterwaysDefs, !!visible.waterways);
  for (const waterway of buildWaterwayLayerConfigs(inputs.waterwaysDefs)) {
    setLayerVisibility(
      map,
      `${waterway.id}-line`,
      !!visible.waterways && visible[`waterways_${waterway.layer}`] !== false
    );
  }

  syncRoadLayers(map, inputs.roadsCollection, !!visible.roads);
  syncSoilLayers(map, inputs.soilCollection, !!visible.soil);
  syncCatastroLayers(map, !!visible.catastro);
  syncBasinLayers(map, inputs.basins, !!visible.basins);
  syncApprovedZoneLayers(map, inputs.approvedZonesCollection, !!visible.approved_zones);
  syncMartinSuggestionLayers(map, {
    showConflictPoints: !!visible.puntos_conflicto,
  });

  syncBpaHistoricoLayer(
    map,
    (inputs.pilarVerde?.bpaHistorico ?? null) as FeatureCollection | null,
    !!visible.pilar_verde_bpa_historico
  );
  syncAgroAceptadaLayer(
    map,
    (inputs.pilarVerde?.agroAceptada ?? null) as FeatureCollection | null,
    !!visible.pilar_verde_agro_aceptada
  );
  syncAgroPresentadaLayer(
    map,
    (inputs.pilarVerde?.agroPresentada ?? null) as FeatureCollection | null,
    !!visible.pilar_verde_agro_presentada
  );
  syncAgroZonasLayer(
    map,
    (inputs.pilarVerde?.agroZonas ?? null) as FeatureCollection | null,
    !!visible.pilar_verde_agro_zonas
  );
  syncPorcentajeForestacionLayer(
    map,
    (inputs.pilarVerde?.porcentajeForestacion ?? null) as FeatureCollection | null,
    !!visible.pilar_verde_porcentaje_forestacion
  );

  syncCanalesLayers(map, {
    relevados: inputs.canales.relevados,
    propuestas: inputs.canales.propuestas,
    relevadosVisible: !!visible.canales_relevados,
    propuestasVisible: !!visible.canales_propuestos,
    visibleRelevadoIds: inputs.canales.visibleRelevadoIds,
    visiblePropuestaIds: inputs.canales.visiblePropuestaIds,
    activeEtapas: inputs.canales.activeEtapas,
  });
  syncEscuelasLayer(map, inputs.escuelasCollection, !!visible.escuelas);

  applyLayerOpacity(map, inputs.opacityByLayer);
  applyLayerOrder(map, inputs.orderByLayer);
}

export interface ComparisonMapConstructor {
  new (options: maplibregl.MapOptions): maplibregl.Map;
}

export interface ComparisonOverlayController {
  readonly map: maplibregl.Map;
  update: (inputs: ComparisonOverlaySyncInputs) => void;
  dispose: () => void;
}

export interface CreateComparisonOverlayParams {
  mapConstructor: ComparisonMapConstructor;
  container: HTMLElement;
  baseMap: maplibregl.Map;
  initialInputs: ComparisonOverlaySyncInputs;
}

export function createComparisonOverlayController({
  mapConstructor: MapConstructor,
  container,
  baseMap,
  initialInputs,
}: CreateComparisonOverlayParams): ComparisonOverlayController {
  const center = baseMap.getCenter().toArray();
  const overlayMap = new MapConstructor({
    container,
    interactive: false,
    attributionControl: false,
    style: {
      version: 8,
      sources: {},
      layers: [
        {
          id: 'comparison-transparent-background',
          type: 'background',
          paint: {
            'background-color': 'rgba(0,0,0,0)',
            'background-opacity': 0,
          },
        },
      ],
    },
    center: [center[0], center[1]],
    zoom: baseMap.getZoom(),
    bearing: baseMap.getBearing(),
    pitch: baseMap.getPitch(),
  });

  let latestInputs = initialInputs;
  let styleReady = false;
  let disposed = false;

  const syncView = () => {
    if (disposed) return;
    overlayMap.jumpTo({
      center: baseMap.getCenter(),
      zoom: baseMap.getZoom(),
      bearing: baseMap.getBearing(),
      pitch: baseMap.getPitch(),
    });
  };

  const syncLatest = (includeRaster: boolean) => {
    if (disposed) return;
    if (includeRaster) {
      syncComparisonRasterLayer(overlayMap, latestInputs.leftTileUrl);
    }
    syncComparisonVectorLayers(overlayMap, latestInputs);
    syncView();
  };

  const handleLoad = () => {
    styleReady = true;
    syncLatest(true);
  };

  const handleResize = () => {
    overlayMap.resize();
    syncView();
  };

  overlayMap.once('load', handleLoad);
  baseMap.on('move', syncView);
  baseMap.on('resize', handleResize);

  return {
    map: overlayMap,
    update(nextInputs) {
      const tileChanged = nextInputs.leftTileUrl !== latestInputs.leftTileUrl;
      latestInputs = nextInputs;
      if (!styleReady && overlayMap.isStyleLoaded()) {
        styleReady = true;
      }
      if (!styleReady) return;
      syncLatest(tileChanged);
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      baseMap.off('move', syncView);
      baseMap.off('resize', handleResize);
      overlayMap.off('load', handleLoad);
      overlayMap.remove();
    },
  };
}
