/**
 * Interacciones del mapa 2D: medición, ficha, hazard, comparación y export.
 * El contenedor sigue siendo el dueño del mapa y de los datos. Este hook se llama
 * en el mismo punto del render para conservar el orden de los efectos.
 */
import type { Feature, FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';
import * as maplibregl from 'maplibre-gl';
import type { RefObject, SetStateAction } from 'react';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import type { ConsorcioInfo } from '../../hooks/useCaminosColoreados';
import { useFichaOverlay } from '../../hooks/useFichaOverlay';
import { fichaSelectionKey, useFichaTerritorial } from '../../hooks/useFichaTerritorial';
import { buildTileUrl, type GeoLayerInfo } from '../../hooks/useGeoLayers';
import { useHazardBasinMembership } from '../../hooks/useHazardBasinMembership';
import { resolveBasinCatalogStatus } from '../../hooks/useHazardUrlState';
import type { ImageComparison } from '../../hooks/useImageComparison';
import type { SelectedImage } from '../../hooks/useSelectedImage';
import { WATERWAY_DEFS } from '../../hooks/useWaterways';
import { FICHA_PARCELAS_MAX } from '../../lib/api/ficha';
import { showWarning } from '../../lib/notifications';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import {
  ALL_ETAPAS,
  type CanalesFeatureCollection,
  type Etapa,
  type IndexFile,
} from '../../types/canales';
import type { EscuelaFeatureCollection } from '../../types/escuelas';
import type { PilarVerdeData } from '../../types/pilarVerde';
import type { DrawControlHandle } from '../map/DrawControl';
import { syncCanalCuencaLayer } from './canalCuencaLayer';
import {
  type ComparisonOverlayController,
  type ComparisonOverlaySyncInputs,
  createComparisonOverlayController,
} from './comparisonOverlay';
import { syncFichaOverlayLayers } from './fichaOverlayLayers';
import { buildHazardBasinOptions } from './hazardBasinOptions';
import { buildHazardLegendView } from './hazardLegend';
import { type ActiveLegendItem, shouldLatchBpaJoin } from './map2dDerived';
import { useMeasurement } from './measurement/useMeasurement';
import { syncParcelaHighlightLayers } from './parcelaHighlightLayers';
import type { ProfileRangeStats } from './profileRange';
import { useAnalysisToolsGate } from './useAnalysisToolsGate';
import { useComparisonSlider } from './useComparisonSlider';
import { useElevationProfileCursor } from './useElevationProfileCursor';
import { useFichaDrawWiring } from './useFichaDrawWiring';
import { useFichaInteraction } from './useFichaInteraction';
import { useFichaOverlayTabs } from './useFichaOverlayTabs';
import { useHazardMapState } from './useHazardMapState';
import { useMapExportHandlers } from './useMapActionHandlers';
import { useMapDragSignal } from './useMapDragSignal';
import { useMapEscapeExit } from './useMapEscapeExit';
import { useMapHoverTooltip } from './useMapHoverTooltip';
import { useMapInteractionEffects } from './useMapInteractionEffects';
import { useMapLayerEffects } from './useMapLayerEffects';
import { usePuntosInteresWiring } from './usePuntosInteresWiring';
import { type QuickPlacePin, useQuickPlaceMarker } from './useQuickPlaceMarker';
import { useReportHighlight } from './useReportHighlight';
import type { RoadFlowWiring } from './useRoadFlowWiring';
import { useSelectedLineHighlight } from './useSelectedLineHighlight';
import type { ViewMode } from './ViewModePanel';
import { YPF_ESTACION_BOMBEO_GEOJSON } from './ypfEstacionBombeoLayer';

function isFichaOverlayPainting(enabled: boolean, data: unknown): boolean {
  return enabled && data != null;
}

export interface MapaMapLibreStageInput {
  readonly activeDemLayerId: string | null;
  readonly activeLegendItems: ActiveLegendItem[];
  readonly allGeoLayers: GeoLayerInfo[];
  readonly approvedZones: FeatureCollection<Geometry, GeoJsonProperties> | null;
  readonly approvedZonesCollection:
    | FeatureCollection<Geometry, GeoJsonProperties>
    | null
    | undefined;
  readonly baseLayer: 'osm' | 'satellite';
  readonly basins: FeatureCollection<Geometry, GeoJsonProperties> | null;
  readonly basinsError: string | null;
  readonly basinsLoading: boolean;
  readonly caminos: FeatureCollection<Geometry, GeoJsonProperties> | null;
  readonly canalesData: {
    relevados: CanalesFeatureCollection | null;
    propuestas: CanalesFeatureCollection | null;
    index: IndexFile | null;
  };
  readonly canalesIndex: IndexFile | null;
  readonly canalesPropuestas: CanalesFeatureCollection | null;
  readonly canalesRelevados: CanalesFeatureCollection | null;
  readonly catastroMap: FeatureCollection<Geometry, GeoJsonProperties> | null;
  readonly comparison: ImageComparison | null;
  readonly comparisonContainerRef: RefObject<HTMLDivElement | null>;
  readonly comparisonMapRef: RefObject<maplibregl.Map | null>;
  readonly consorcios: ConsorcioInfo[];
  readonly demTileUrl: string | null;
  readonly drawControlRef: RefObject<DrawControlHandle | null>;
  readonly elevationProfileHover: { lon: number; lat: number } | null;
  readonly elevationProfileRange: ProfileRangeStats | null;
  readonly escuelasCollection: EscuelaFeatureCollection | null;
  readonly escuelasData: { collection: EscuelaFeatureCollection | null };
  readonly exportTitle: string;
  readonly hazardGeoLayers: GeoLayerInfo[];
  readonly hiddenClasses: { [x: string]: number[] };
  readonly hiddenRanges: { [x: string]: number[] };
  readonly hillshadeTileUrl: string | null;
  readonly isDraggingSlider: RefObject<boolean>;
  readonly isStaff: boolean;
  readonly mapReady: boolean;
  readonly mapRef: RefObject<maplibregl.Map | null>;
  readonly opacityByLayer: { [x: string]: number };
  readonly orderByLayer: string[];
  readonly pilarVerde: PilarVerdeData | null;
  readonly propuestasEtapasVisibility: {
    Alta: boolean;
    'Media-Alta': boolean;
    Media: boolean;
    Opcional: boolean;
    'Largo plazo': boolean;
  };
  readonly quickPlace: QuickPlacePin | null;
  readonly rasterCompareActive: boolean;
  readonly rasterCompareId: string | null;
  readonly roadFlow: RoadFlowWiring;
  readonly roadsCollection: FeatureCollection<Geometry, GeoJsonProperties> | null | undefined;
  readonly selectedFeatures: Feature<Geometry, GeoJsonProperties>[];
  readonly selectedImage: SelectedImage | null;
  readonly setBpaJoinIntent: (value: SetStateAction<boolean>) => void;
  readonly setElevationProfileHover: (
    value: SetStateAction<{ lon: number; lat: number } | null>
  ) => void;
  readonly setElevationProfileRange: (value: SetStateAction<ProfileRangeStats | null>) => void;
  readonly setExportPngModalOpen: (value: SetStateAction<boolean>) => void;
  readonly setSelectedFeatures: (
    value: SetStateAction<Feature<Geometry, GeoJsonProperties>[]>
  ) => void;
  readonly setSliderPosition: (value: SetStateAction<number>) => void;
  readonly setViewMode: (value: SetStateAction<ViewMode>) => void;
  readonly setVisibleRasterLayers: (value: SetStateAction<{ tipo: string }[]>) => void;
  readonly showDemOverlay: boolean;
  readonly showHillshade: boolean;
  readonly showIGNOverlay: boolean;
  readonly sliderContainerRef: RefObject<HTMLDivElement | null>;
  readonly soilCollection: FeatureCollection<Geometry, GeoJsonProperties> | null;
  readonly vectorVisibility: { [x: string]: boolean };
  readonly viewMode: 'comparison' | 'base' | 'single';
  readonly visibleRasterLayers: { tipo: string }[];
  readonly waterwaysCollection: FeatureCollection<Geometry, GeoJsonProperties> | null;
  readonly zonaCollection: FeatureCollection<Geometry, GeoJsonProperties> | null;
}

export function useMapaMapLibreStage(input: MapaMapLibreStageInput) {
  const {
    activeDemLayerId,
    activeLegendItems,
    allGeoLayers,
    approvedZones,
    approvedZonesCollection,
    baseLayer,
    basins,
    basinsError,
    basinsLoading,
    caminos,
    canalesData,
    canalesIndex,
    canalesPropuestas,
    canalesRelevados,
    catastroMap,
    comparison,
    comparisonContainerRef,
    comparisonMapRef,
    consorcios,
    demTileUrl,
    drawControlRef,
    elevationProfileHover,
    elevationProfileRange,
    escuelasCollection,
    escuelasData,
    exportTitle,
    hazardGeoLayers,
    hiddenClasses,
    hiddenRanges,
    hillshadeTileUrl,
    isDraggingSlider,
    isStaff,
    mapReady,
    mapRef,
    opacityByLayer,
    orderByLayer,
    pilarVerde,
    propuestasEtapasVisibility,
    quickPlace,
    rasterCompareActive,
    rasterCompareId,
    roadFlow,
    roadsCollection,
    selectedFeatures,
    selectedImage,
    setBpaJoinIntent,
    setElevationProfileHover,
    setElevationProfileRange,
    setExportPngModalOpen,
    setSelectedFeatures,
    setSliderPosition,
    setViewMode,
    setVisibleRasterLayers,
    showDemOverlay,
    showHillshade,
    showIGNOverlay,
    sliderContainerRef,
    soilCollection,
    vectorVisibility,
    viewMode,
    visibleRasterLayers,
    waterwaysCollection,
    zonaCollection,
  } = input;

  /* ---------------------------------------------------------------------- */
  /*  Measurement tools (SDD map-measurement-tools)                          */
  /* ---------------------------------------------------------------------- */
  // `useMeasurement` owns a DEDICATED MapboxDraw instance so its `clear()`
  // never touches LineDrawControl features. We pass `mapReady ? map : null`
  // so the hook's `useEffect` re-runs once the map finishes loading (the
  // bare ref would never re-trigger React on its own).
  const measurementMap = mapReady ? mapRef.current : null;
  const {
    state: measurementState,
    liveLabel: measurementLiveLabel,
    startDistance: startMeasureDistance,
    startArea: startMeasureArea,
    clear: clearMeasurements,
    cancel: cancelMeasurement,
  } = useMeasurement(measurementMap);

  // The ONE interaction-mode coordinator (design §6.1, JDB-012): it derives the
  // single mode from measurement + ficha-draw, enforces their mutual exclusion,
  // and owns parcel/polygon selection. Entering draw mode cancels measurement via
  // `clearMeasurements` so only one MapboxDraw instance ever mounts.
  // T4 fix round — at `FICHA_PARCELAS_MAX` an additive click is dropped, and a
  // click that changes nothing and says nothing reads as a broken map. The
  // coordinator reports the drop; the toast lives here so the hook keeps no UI
  // dependency.
  const handleParcelasCapReached = useCallback(() => {
    showWarning(
      'Selección al máximo',
      `No se pueden analizar más de ${FICHA_PARCELAS_MAX} parcelas a la vez. Quitá alguna para agregar otra.`
    );
  }, []);

  const fichaInteraction = useFichaInteraction(
    measurementState.mode,
    clearMeasurements,
    handleParcelasCapReached
  );
  const fichaDraw = useFichaDrawWiring({
    interactionMode: fichaInteraction.interactionMode,
    drawSession: fichaInteraction.state.drawing,
    redrawPolygon: fichaInteraction.redrawPolygon,
    drawControlRef,
  });
  const isFichaDrawSession = fichaDraw.isDrawSession;
  const puntosInteres = usePuntosInteresWiring({
    layerOn: !!vectorVisibility.puntos_interes,
    fichaInteractionMode: fichaInteraction.interactionMode,
    fichaDrawEscapeMode: fichaDraw.escapeMode,
    onCancelMeasurement: cancelMeasurement,
    onClearFicha: fichaInteraction.clearFicha,
  });
  // Memoized: `useHazardMapState` feeds these options to the basin-zoom
  // effect's deps — a fresh identity per render would re-fire fitBounds.
  const hazardBasins = useMemo(() => buildHazardBasinOptions(basins), [basins]);
  const hazard = useHazardMapState({
    mapRef,
    mapReady,
    allGeoLayers: hazardGeoLayers,
    basinIds: hazardBasins.map((basin) => basin.id),
    basinCatalogStatus: resolveBasinCatalogStatus({
      loading: basinsLoading,
      error: basinsError,
      hasData: basins != null,
    }),
    basinOptions: hazardBasins,
    fichaActive: fichaInteraction.request !== null,
  });
  const hazardLegend = buildHazardLegendView({
    active: hazard.isHazardActive,
    riskClasses: hazard.url.riskClasses,
    selectedBasinId: hazard.url.basin,
    basinOptions: hazardBasins,
  });
  const basinMembership = useHazardBasinMembership(hazard.isHazardActive ? hazard.url.basin : null);

  // Canal-selection mode gate (A6). Declared here so it can feed BOTH the
  // vt_canal_network cyan-line effect below AND `useMapLayerEffects`, which is
  // the SINGLE owner of the static `canales_relevados-line` visibility: passing
  // `isFichaCanal` lets it suppress the redundant relevados twin race-free (no
  // second effect fighting over the same layer).
  const isFichaCanal = fichaInteraction.interactionMode === 'ficha-canal';

  // Latch the BPA-join fetch the first time a PARCELA ficha opens — that is the
  // ONLY consumer of `bpa_enriched.json` in the ficha (`PilarVerdeBadges`
  // renders nothing for `poligono`/`canal_*`). Never reset: `staleTime:
  // Infinity` means one fetch per session.
  useEffect(() => {
    if (shouldLatchBpaJoin(fichaInteraction.request, fichaInteraction.tipo)) {
      setBpaJoinIntent(true);
    }
  }, [fichaInteraction.request, fichaInteraction.tipo]);

  useMapLayerEffects({
    mapRef,
    mapReady,
    baseLayer,
    vectorVisibility,
    soilCollection,
    roadsCollection,
    basins,
    zonaCollection,
    approvedZonesCollection,
    activeDemLayerId: rasterCompareActive ? rasterCompareId : activeDemLayerId,
    showDemOverlay: showDemOverlay || rasterCompareActive,
    demTileUrl: rasterCompareActive && rasterCompareId ? buildTileUrl(rasterCompareId) : demTileUrl,
    allGeoLayers,
    setVisibleRasterLayers,
    showIGNOverlay,
    showHillshade,
    hillshadeTileUrl,
    viewMode,
    selectedImage,
    comparison,
    waterwaysDefs: WATERWAY_DEFS,
    pilarVerde,
    canales: canalesData,
    escuelas: escuelasData,
    isFichaCanal,
    roadFlowCrossings: roadFlow.mapCollection,
    roadFlowFlechas: roadFlow.mapFlechas,
    roadFlowTotalFlujoNatural: roadFlow.totalFlujoNatural,
    roadFlowKinds: roadFlow.kinds,
    puntosInteresCollection: puntosInteres.collection,
    catastroMembership: basinMembership.membership,
    // Catálogo IDECOR: public since 2026-10-15 (owner decision).
    showRedVialOficial: true,
    showCaminosHuecos: isStaff,
  });

  useMapInteractionEffects({
    mapRef,
    mapReady,
    measurementMode: puntosInteres.interactionMode,
    setSelectedFeatures,
    selectedFeatures,
    roadsFeatures: caminos?.features ?? [],
    canalRelevados: canalesRelevados?.features ?? [],
    canalPropuestas: canalesPropuestas?.features ?? [],
    onParcelaResolved: fichaInteraction.resolveParcela,
    // Mode transitions ALWAYS discard the selection, including with the sticky
    // touch mode on (where a null resolve means "you missed", not "clear").
    onClearParcelas: fichaInteraction.clearParcelas,
    onCanalResolved: fichaInteraction.resolveCanal,
    onPoiPlace: puntosInteres.onPoiPlace,
  });
  useMapHoverTooltip({
    mapRef,
    mapReady,
    mode: puntosInteres.interactionMode,
  });

  // Ficha territorial fetch — owned by the container, threaded to MapUiPanels as
  // props so `InfoPanel` never fetches (design §6). Idle when nothing selected.
  // A `tipo=parcela` (click) or `tipo=poligono` (free draw) request, or null.
  const ficha = useFichaTerritorial(fichaInteraction.request);

  // Identity of the selection, derived from the REQUEST (same derivation as the
  // query key). The panels use it as their reset trigger, so it must never be
  // rebuilt from display fields: `nro_cuenta` is optional and a drawn polygon or
  // a duplicated canal name has none, which made two different selections look
  // identical and left the new analysis stuck behind the old pill.
  const fichaKey = fichaSelectionKey(fichaInteraction.request);

  // On-map overlay (A(b) slice 1, soils): opt-in "ver recortado en el mapa"
  // toggle. The overlay query is ENABLED only while the toggle is on AND a zone
  // is selected, so it never fetches unless the user opts in. The geometry lives
  // in the ficha state, so a null request (clearFicha / every mode switch resets
  // the coordinator to IDLE) drops the fetch and the paint effect below removes
  // any lingering layer.
  //
  // ONE selector (T3b): the ficha panel's dataset TAB picks both the table the
  // user reads and the dataset the map paints, and the class rows of that table
  // filter the paint. All of it lives in `useFichaOverlayTabs` because the
  // pieces are only correct together (see that file's header).
  const fichaTabs = useFichaOverlayTabs({
    selectionKey: fichaKey,
    ficha: ficha.data,
  });

  // A selected zone is the container's business, not the panel's: with no
  // request there is no geometry to clip and the query must stay idle.
  const fichaOverlayEnabled = fichaTabs.overlayEnabled && fichaInteraction.request !== null;
  const fichaOverlay = useFichaOverlay(
    fichaInteraction.request,
    fichaTabs.overlayDataset,
    fichaOverlayEnabled
  );

  const fichaOverlayPainting = isFichaOverlayPainting(fichaOverlayEnabled, fichaOverlay.data);

  // Auto-minimize signal (T3a, fix 2): one bump per map DRAG gesture, so open
  // panels collapse to their pills the moment the user starts panning. Zoom and
  // click are deliberately NOT subscribed — see `useMapDragSignal`.
  const mapDragSignal = useMapDragSignal(mapRef, mapReady);

  // Paint / clear the clipped overlay. `visible` is false whenever the toggle is
  // off, no zone is selected, or the fetch has no data yet — so a stale overlay
  // never lingers over a new selection (the query key changes with the selection,
  // dropping the previous data, and this effect then removes the layer).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncFichaOverlayLayers(map, {
      featureCollection: (fichaOverlay.data as unknown as FeatureCollection | undefined) ?? null,
      dataset: fichaTabs.overlayDataset,
      visible: fichaOverlayPainting,
      // Same call, same effect: the sync re-creates the layers whenever they
      // were removed, and a fresh layer carries no filter — reapplying it in a
      // second effect would leave one frame painting the hidden classes.
      visibleClases: fichaTabs.visibleClases,
    });
  }, [
    mapReady,
    fichaOverlayPainting,
    fichaOverlay.data,
    fichaTabs.overlayDataset,
    fichaTabs.visibleClases,
  ]);

  // Paint / clear the multi-parcel selection highlight (T4). Driven by the
  // coordinator's `parcelas` set — NOT by the settled/analyzed one — so it
  // answers every ctrl-click immediately while the request is still debouncing,
  // and clears itself on every reset, mode switch and deselect without a second
  // piece of state to keep in sync.
  //
  // The catastro VISIBILITY is a real input: the source stays on the map when
  // the layer is turned off (only the layers' visibility flips), so without this
  // the highlight painted parcels the user had just hidden.
  //
  // So is whether the ficha OVERLAY is painting. This effect runs AFTER the
  // overlay effect above, so the highlight's amber fill lands on top of it: over
  // a no-coverage area it reads as the legend's "Alto" class, and over a covered
  // one it tints every real class orange. `overlayActive` drops the fill (the
  // outline still identifies the selection) exactly while the overlay is up —
  // see the long note in `parcelaHighlightLayers.ts`. It mirrors the SAME
  // expression fed to the overlay's `visible`, so the two can never disagree.
  const parcelasSeleccionadas = fichaInteraction.state.parcelas;
  const catastroVisible = vectorVisibility.catastro !== false;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncParcelaHighlightLayers(map, parcelasSeleccionadas, catastroVisible, fichaOverlayPainting);
  }, [mapReady, parcelasSeleccionadas, catastroVisible, fichaOverlayPainting]);

  // Canal mode (A6 + A7): the CURATED relevados/propuestos layers are the ficha
  // canal source now (their visibility in canal mode is owned by
  // `useMapLayerEffects` via `isFichaCanal`), so there is no separate clickable
  // layer to mount here. Instead this effect paints the CATCHMENT outline the
  // backend echoed for a resolved `tipo=canal_cuenca` ficha, and clears it for
  // any other tipo or when the selection changes (the query key drops stale data
  // and `geometria_cuenca` goes undefined). The A(b) "ver recortado" overlay
  // clips to this same basin.
  const cuencaOutline =
    ficha.data?.tipo === 'canal_cuenca'
      ? ((ficha.data.geometria_cuenca as unknown as import('geojson').Geometry | undefined) ?? null)
      : null;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncCanalCuencaLayer(map, cuencaOutline);
  }, [mapReady, cuencaOutline]);

  // Measurement and ficha-draw are mutually exclusive: starting a measurement
  // ends drawing first (the reverse — draw cancelling measurement — is handled by
  // `useFichaInteraction.startDraw` → `clearMeasurements`).
  const handleStartMeasureDistance = useCallback(() => {
    puntosInteres.cancelPlace();
    fichaInteraction.stopDraw();
    startMeasureDistance();
  }, [fichaInteraction, puntosInteres.cancelPlace, startMeasureDistance]);
  const handleStartMeasureArea = useCallback(() => {
    puntosInteres.cancelPlace();
    fichaInteraction.stopDraw();
    startMeasureArea();
  }, [fichaInteraction, puntosInteres.cancelPlace, startMeasureArea]);
  const handleToggleFichaDraw = useCallback(() => {
    puntosInteres.cancelPlace();
    if (fichaInteraction.state.drawing) fichaInteraction.stopDraw();
    else fichaInteraction.startDraw();
  }, [fichaInteraction, puntosInteres.cancelPlace]);
  // Draw-mode sub-controls (T3c, fix 4). MapboxDraw returns to `simple_select`
  // after `draw.create`, so these re-enter draw mode / wipe the polygon without
  // toggling the whole ficha-draw mode off and on.
  const handleRedrawPolygon = fichaDraw.handleRedrawPolygon;
  const handleDeleteDrawnPolygon = fichaDraw.handleDeletePolygon;
  const handleToggleFichaCanal = useCallback(() => {
    puntosInteres.cancelPlace();
    if (fichaInteraction.state.canalMode) fichaInteraction.stopCanal();
    else fichaInteraction.startCanal();
  }, [fichaInteraction, puntosInteres.cancelPlace]);
  // T4 — the touch equivalent of holding ctrl. Unlike draw/canal this is NOT a
  // map interaction mode: clicks keep resolving parcels exactly as in idle, they
  // just accumulate, so nothing here touches `interactionMode`.
  const handleToggleFichaMultiSelect = useCallback(() => {
    fichaInteraction.setMultiSelect(!fichaInteraction.state.multiSelect);
  }, [fichaInteraction]);

  // Login gate for the ANALYSIS tools (draw / canal / sticky multi-select). The
  // hook returns the toolbar callbacks only for a CONFIRMED session, and the
  // toolbar renders each button only when its callback is present — so anonymous
  // visitors get no button in the DOM at all, while MEDIR, DESCARGAR, CAPAS and
  // the ficha-on-click (including the ctrl+clic gesture) stay public. It is a
  // render gate, NOT an authz boundary: the ficha endpoints remain public behind
  // their own caps. See `useAnalysisToolsGate` for the full rationale.
  const analysisToolProps = useAnalysisToolsGate({
    drawing: fichaInteraction.state.drawing,
    canalMode: fichaInteraction.state.canalMode,
    multiSelect: fichaInteraction.state.multiSelect,
    stopDraw: fichaInteraction.stopDraw,
    stopCanal: fichaInteraction.stopCanal,
    setMultiSelect: fichaInteraction.setMultiSelect,
    onToggleFichaDraw: handleToggleFichaDraw,
    onRedrawPolygon: handleRedrawPolygon,
    onDeletePolygon: handleDeleteDrawnPolygon,
    onToggleFichaCanal: handleToggleFichaCanal,
    onToggleFichaMultiSelect: handleToggleFichaMultiSelect,
  });

  // Escape is the universal exit from ANY active interaction mode. Until this
  // was wired, `useMeasurement.cancel()` had no caller at all and a user who
  // started measuring had no way back to idle (map-fluidity T1).
  const handleExitDraw = useCallback(() => fichaInteraction.stopDraw(), [fichaInteraction]);
  const handleExitCanal = useCallback(() => fichaInteraction.stopCanal(), [fichaInteraction]);
  const handleCloseInfoPanel = useCallback(() => {
    setSelectedFeatures([]);
    setElevationProfileHover(null);
    setElevationProfileRange(null);
  }, []);
  const handleClosePanels = useCallback(() => {
    handleCloseInfoPanel();
    fichaInteraction.clearFicha();
  }, [fichaInteraction, handleCloseInfoPanel]);
  useMapEscapeExit({
    // Escape must still leave the draw SESSION after the polygon is finished,
    // when `interactionMode` has already gone back to idle (T4).
    mode: puntosInteres.escapeMode,
    onCancelMeasurement: cancelMeasurement,
    onExitDraw: handleExitDraw,
    onExitCanal: handleExitCanal,
    onExitPoiPlace: puntosInteres.cancelPlace,
    onClosePanels: handleClosePanels,
  });

  // Drop a temporary marker when the page is opened with `?lat=&lng=&zoom=`
  // (admin reports → "Ver en mapa"). Reads the URL once on mount; the
  // marker is auto-popped and the user can close it.
  useReportHighlight({ mapRef, mapReady });
  useQuickPlaceMarker({ mapRef, mapReady, place: quickPlace });
  useElevationProfileCursor({
    mapRef,
    mapReady,
    hover: elevationProfileHover,
    range: elevationProfileRange,
  });
  useSelectedLineHighlight({
    mapRef,
    mapReady,
    features: selectedFeatures,
  });

  const comparisonVisibleRelevadoIds = (canalesIndex?.relevados ?? [])
    .map((canal) => canal.id)
    .filter((slug) => {
      const key = `canal_relevado_${slug.replace(/-/g, '_')}`;
      return vectorVisibility[key] !== false;
    });
  const comparisonVisiblePropuestaIds = useMapLayerSyncStore
    .getState()
    .getVisiblePropuestaIds('map2d');
  const comparisonActiveEtapas = (Object.entries(propuestasEtapasVisibility) as [Etapa, boolean][])
    .filter(([, visible]) => visible)
    .map(([etapa]) => etapa);

  useEffect(() => {
    if (rasterCompareActive) setViewMode('comparison');
  }, [rasterCompareActive]);

  const comparisonSyncInputs: ComparisonOverlaySyncInputs = {
    leftTileUrl: rasterCompareActive
      ? buildTileUrl(activeDemLayerId as string)
      : (comparison?.left?.tile_url ?? ''),
    vectorVisibility,
    waterwaysDefs: WATERWAY_DEFS,
    soilCollection,
    roadsCollection,
    basins,
    approvedZonesCollection,
    pilarVerde,
    canales: {
      relevados: canalesRelevados,
      propuestas: canalesPropuestas,
      visibleRelevadoIds: comparisonVisibleRelevadoIds,
      visiblePropuestaIds: comparisonVisiblePropuestaIds,
      activeEtapas: comparisonActiveEtapas.length > 0 ? comparisonActiveEtapas : ALL_ETAPAS,
    },
    escuelasCollection,
    opacityByLayer,
    orderByLayer,
    // Same expressions the base map uses, so the panes cannot drift apart.
    redVialOficial: { shouldMount: isStaff },
    caminosHuecos: { shouldMount: isStaff },
    puntosInteres: puntosInteres.collection,
    zona: zonaCollection,
    roadFlow: {
      crossings: roadFlow.mapCollection,
      totalFlujoNatural: roadFlow.totalFlujoNatural,
      kinds: roadFlow.kinds,
      flechas: roadFlow.mapFlechas,
    },
  };
  const comparisonSyncInputsRef = useRef(comparisonSyncInputs);
  comparisonSyncInputsRef.current = comparisonSyncInputs;
  const comparisonControllerRef = useRef<ComparisonOverlayController | null>(null);
  const comparisonActive =
    mapReady &&
    viewMode === 'comparison' &&
    (rasterCompareActive || (!!comparison?.left?.tile_url && !!comparison?.right?.tile_url));

  // The overlay map has a narrow lifecycle: it is created once for an active
  // comparison and removed when the comparison closes. Vector/data/fine-control
  // changes are synchronized by the separate effect below.
  useEffect(() => {
    if (!comparisonActive) return;

    const baseMap = mapRef.current;
    const comparisonContainer = comparisonContainerRef.current;
    if (!baseMap || !comparisonContainer) return;

    const controller = createComparisonOverlayController({
      mapConstructor: maplibregl.Map,
      container: comparisonContainer,
      baseMap,
      initialInputs: comparisonSyncInputsRef.current,
    });
    comparisonControllerRef.current = controller;
    comparisonMapRef.current = controller.map;

    return () => {
      controller.dispose();
      if (comparisonControllerRef.current === controller) {
        comparisonControllerRef.current = null;
      }
      if (comparisonMapRef.current === controller.map) {
        comparisonMapRef.current = null;
      }
    };
  }, [comparisonActive]);

  // Idempotent synchronization intentionally runs after every render. This
  // keeps the existing overlay instance current for data, visibility,
  // sub-filter, opacity and order changes, while the controller retains the
  // latest inputs until the style load event wins any startup race.
  useEffect(() => {
    comparisonControllerRef.current?.update(comparisonSyncInputs);
  });

  /* ---------------------------------------------------------------------- */
  /*  Comparison slider — Task 2.11 (CSS clip-path on right image layer)    */
  /* ---------------------------------------------------------------------- */
  const handleSliderPointerDown = useComparisonSlider({
    sliderContainerRef,
    isDraggingSlider,
    setSliderPosition,
  });

  /* ---------------------------------------------------------------------- */
  /*  Draw controls — Task 2.10                                              */
  /* ---------------------------------------------------------------------- */
  // Draw controls are mounted as React components that receive the map instance
  // after it's ready. The actual integration happens via the DrawControl component
  // which uses map.addControl() imperatively (see DrawControl.tsx).

  // ── KMZ export data sources ────────────────────────────────────────────
  // Keys MUST match `kmzLayerRegistry` entries. Missing/null slots are
  // silently skipped by `buildKmz` — the hook does not refuse when a slot
  // is empty. Memoised explicitly: a fresh object identity every render
  // would invalidate `useMapExportHandlers`'s `handleExportKmz` useCallback
  // (dep: `exportSources`) and everything downstream of it.
  const exportSources = useMemo(
    () => ({
      canales_relevados: canalesRelevados,
      canales_propuestos: canalesPropuestas,
      escuelas: escuelasCollection,
      pilar_verde_bpa_historico: pilarVerde?.bpaHistorico ?? null,
      pilar_verde_agro_aceptada: pilarVerde?.agroAceptada ?? null,
      pilar_verde_agro_presentada: pilarVerde?.agroPresentada ?? null,
      pilar_verde_agro_zonas: pilarVerde?.agroZonas ?? null,
      pilar_verde_porcentaje_forestacion: pilarVerde?.porcentajeForestacion ?? null,
      waterways: waterwaysCollection,
      roads: roadsCollection ?? null,
      catastro: catastroMap,
      soil: soilCollection,
      'ypf-estacion-bombeo': YPF_ESTACION_BOMBEO_GEOJSON,
    }),
    [
      canalesRelevados,
      canalesPropuestas,
      escuelasCollection,
      pilarVerde?.bpaHistorico,
      pilarVerde?.agroAceptada,
      pilarVerde?.agroPresentada,
      pilarVerde?.agroZonas,
      pilarVerde?.porcentajeForestacion,
      waterwaysCollection,
      roadsCollection,
      catastroMap,
      soilCollection,
    ]
  );

  const { handleExportPng, handleExportApprovedZonesPdf, handleExportKmz } = useMapExportHandlers({
    mapRef,
    exportTitle,
    setExportPngModalOpen,
    approvedZones,
    activeLegendItems,
    consorcios: vectorVisibility.roads && roadsCollection ? consorcios : [],
    visibleRasterLayers,
    hiddenClasses,
    hiddenRanges,
    exportSources,
    zonaCollection,
    canalesRelevados:
      vectorVisibility.canales_relevados && canalesRelevados ? canalesRelevados : null,
  });

  return {
    analysisToolProps,
    cancelMeasurement,
    clearMeasurements,
    comparisonActive,
    ficha,
    fichaInteraction,
    fichaKey,
    fichaOverlay,
    fichaTabs,
    handleCloseInfoPanel,
    handleExportApprovedZonesPdf,
    handleExportKmz,
    handleExportPng,
    handleSliderPointerDown,
    handleStartMeasureArea,
    handleStartMeasureDistance,
    hazard,
    hazardBasins,
    hazardLegend,
    isFichaCanal,
    isFichaDrawSession,
    mapDragSignal,
    measurementLiveLabel,
    measurementMap,
    measurementState,
    puntosInteres,
  };
}
