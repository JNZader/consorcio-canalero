import type { FeatureCollection, LineString, Point } from 'geojson';
import type * as maplibregl from 'maplibre-gl';

import type { WATERWAY_DEFS } from '../../hooks/useWaterways';
import { getSoilPmtilesArchiveKey } from '../../lib/soilPmtiles';
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
import { MAP_GLYPHS_URL } from './roadLabelLayer';
import { setLayerVisibility } from './map2dUtils';
import {
  syncAgroAceptadaLayer,
  syncAgroPresentadaLayer,
  syncAgroZonasLayer,
  syncApprovedZoneLayers,
  syncBasinLayers,
  syncBpaHistoricoLayer,
  syncCaminosHuecosLayers,
  syncCanalesLayers,
  syncCatastroLayers,
  syncEscuelasLayer,
  syncPorcentajeForestacionLayer,
  syncPuntosInteresLayer,
  syncRedVialOficialLayers,
  syncRoadFlowLayers,
  syncRoadLayers,
  syncSoilLayers,
  syncWaterwayLayers,
  syncYpfEstacionBombeoLayer,
  syncZonaLayer,
} from './mapLayerEffectHelpers';
import type { RoadFlowKindVisibility } from './roadFlowLayers';
import { syncMartinSuggestionLayers } from './mapRasterOverlayHelpers';

const COMPARISON_SOURCE_ID = 'comparison-left';
const COMPARISON_LAYER_ID = 'comparison-left-layer';

/**
 * Vector layers rendered in the side-by-side comparison overlay.
 *
 * Deliberately excludes raster-only UI ids (e.g. `precip_normal`): the
 * comparison view shows exactly ONE raster tile layer on the left
 * (`leftTileUrl`), not the normal map's collection of raster overlays.
 *
 * `road_flow` is the one vector layer deliberately absent, by the owner-ratified
 * rule of 2026-08-23: any layer whose data needs an authenticated panel PLUS a
 * disclaimer stays out of the comparator, because the slider renders map paint
 * and nothing else. The operator-only overlays (`red_vial_oficial`,
 * `caminos_huecos`, `puntos_interes`, `sentido_camino`) satisfy only the first
 * half — they are not rankings and carry no disclaimer — so they belong here,
 * behind the SAME role gate the base map uses: a visitor who cannot see them on
 * the right cannot see them on the left.
 */
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
  'red_vial_oficial',
  'caminos_huecos',
  'puntos_interes',
  'sentido_camino',
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
  /**
   * Operator-only overlays. Mounted behind the SAME role gate the base map uses,
   * so a visitor who cannot see them on the right cannot see them on the left.
   */
  redVialOficial: { shouldMount: boolean };
  caminosHuecos: { shouldMount: boolean };
  puntosInteres: FeatureCollection<Point> | null;
  /** The consorcio boundary: always painted, toggled by `vectorVisibility.zona`. */
  zona: FeatureCollection | null;
  /**
   * The road-flow payload. The RANKING is never painted here — `road_flow` needs
   * an authenticated panel plus the RFA-R4 disclaimer, and the owner-ratified
   * rule of 2026-08-23 keeps such layers out of the comparator. The direction
   * chevrons ARE painted, gated by `vectorVisibility.sentido_camino` exactly as
   * on the base map: they are not a ranking and carry no disclaimer.
   */
  roadFlow: {
    crossings: FeatureCollection<Point> | null | undefined;
    totalFlujoNatural: number;
    kinds: RoadFlowKindVisibility;
    flechas?: FeatureCollection<Point> | null;
  };
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
  syncSoilLayers(map, !!visible.soil, getSoilPmtilesArchiveKey());
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
  // Operator-only overlays, behind the SAME role gate as the base map: a visitor
  // who cannot see them on the right cannot see them on the left.
  syncRedVialOficialLayers(map, inputs.redVialOficial.shouldMount, !!visible.red_vial_oficial);
  syncCaminosHuecosLayers(map, inputs.caminosHuecos.shouldMount, !!visible.caminos_huecos);
  syncPuntosInteresLayer(map, inputs.puntosInteres, !!visible.puntos_interes);
  syncZonaLayer(map, inputs.zona, visible.zona !== false);
  syncYpfEstacionBombeoLayer(map, visible.ypf_estacion_bombeo !== false);
  syncRoadFlowLayers(
    map,
    inputs.roadFlow.crossings,
    inputs.roadFlow.totalFlujoNatural,
    // `road_flow` stays OUT of the comparator: the owner-ratified rule of
    // 2026-08-23 keeps out any layer whose data needs an authenticated panel
    // PLUS a disclaimer, and the ranking carries the RFA-R4 statement in a panel
    // this view does not render. The direction chevrons are not a ranking.
    false,
    inputs.roadFlow.kinds,
    inputs.roadFlow.flechas,
    !!visible.sentido_camino
  );

  applyLayerOpacity(map as unknown as Parameters<typeof applyLayerOpacity>[0], inputs.opacityByLayer);
  applyLayerOrder(map as unknown as Parameters<typeof applyLayerOrder>[0], inputs.orderByLayer);
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
      glyphs: MAP_GLYPHS_URL,
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
