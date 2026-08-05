/**
 * MapaMapLibre — 2D interactive map using MapLibre GL JS.
 *
 * Replaces MapaLeaflet.tsx with an imperative MapLibre map following the
 * EXACT same pattern as TerrainViewer3D.tsx: raw new maplibregl.Map({})
 * mounted in a useEffect, all data wired reactively via subsequent useEffects.
 *
 * Drop-in replacement: same external interface (no props — standalone component).
 * MapaInteractivo.tsx only needs a 1-line lazy import change to activate this.
 */

import { Box, Stack } from '@mantine/core';
import type { Feature, FeatureCollection } from 'geojson';

import maplibregl from 'maplibre-gl';
import { ALL_ETAPAS, type Etapa } from '../types/canales';
import { collectCanalChildIds, groupCanalesByFolder } from './shared/canalesGrouping';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Protocol } from 'pmtiles';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

// Register PMTiles protocol once at module level.
// NOTE: migrating the vector layers to PMTiles is a SEPARATE ticket — several
// layers (waterways especially) are consumed as decorated FeatureCollections
// both by the map and by the KMZ export (`exportSources`), so a tile source
// would have to keep a GeoJSON twin alive for the export path.
const _pmtilesProtocol = new Protocol();
maplibregl.addProtocol('pmtiles', _pmtilesProtocol.tile.bind(_pmtilesProtocol));
import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../constants';
import { useApprovedZones } from '../hooks/useApprovedZones';
import { useBasins } from '../hooks/useBasins';
import { useCaminosColoreados } from '../hooks/useCaminosColoreados';
import { useCanales } from '../hooks/useCanales';
import { useCatastroMap } from '../hooks/useCatastroMap';
import { useConflictos } from '../hooks/useConflictos';
import { useEscuelas } from '../hooks/useEscuelas';
import { fichaSelectionKey, useFichaTerritorial } from '../hooks/useFichaTerritorial';
import { useFichaOverlay } from '../hooks/useFichaOverlay';
import { FICHA_MAX_BUFFER_M, FICHA_PARCELAS_MAX } from '../lib/api/ficha';
import { showWarning } from '../lib/notifications';
import { syncFichaOverlayLayers } from './map2d/fichaOverlayLayers';
import { syncParcelaHighlightLayers } from './map2d/parcelaHighlightLayers';
import { useFichaOverlayTabs } from './map2d/useFichaOverlayTabs';
import { useMapDragSignal } from './map2d/useMapDragSignal';
import { useGEELayers } from '../hooks/useGEELayers';
import { useGeoLayers } from '../hooks/useGeoLayers';
import { useImageComparisonListener } from '../hooks/useImageComparison';
import { usePilarVerde } from '../hooks/usePilarVerde';
import { useSelectedImageListener } from '../hooks/useSelectedImage';
import { useSoilMap } from '../hooks/useSoilMap';
import { WATERWAY_DEFS, useWaterways } from '../hooks/useWaterways';
import { useConfigStore } from '../stores/configStore';
import {
  PILAR_VERDE_LAYER_IDS,
  selectEtapaGate,
  useMapLayerSyncStore,
} from '../stores/mapLayerSyncStore';
import styles from '../styles/components/map.module.css';
import DrawControl, { type DrawControlHandle } from './map/DrawControl';
import { RasterLegend } from './RasterLegend';
import { LayerControlsPanel } from './map2d/LayerControlsPanel';
import { buildLayerProvenance } from './map2d/layerProvenance';
import { useLayerHealth } from './map2d/useLayerHealth';
import { useRasterTileHealth } from './map2d/useRasterTileHealth';
import { LeyendaPanel } from './map2d/LeyendaPanel';
import { MapBaseSelectorPanel } from './map2d/MapBaseSelectorPanel';
import { MapUiPanels } from './map2d/MapUiPanels';
import { MapViewportOverlay } from './map2d/MapViewportOverlay';
import { MapWorkspace, useMapWorkspaceDesktop } from './map2d/MapWorkspace';
import { type ViewMode, ViewModePanel } from './map2d/ViewModePanel';
import {
  type ComparisonOverlayController,
  type ComparisonOverlaySyncInputs,
  createComparisonOverlayController,
} from './map2d/comparisonOverlay';
import { DEFAULT_BASE_LAYER, GEE_LAYER_NAMES, SOURCE_IDS } from './map2d/map2dConfig';
import {
  buildFamilyActiveCounts,
  shouldLatchBpaJoin,
  sumFamilyActiveCounts,
} from './map2d/map2dDerived';
import { syncCanalCuencaLayer } from './map2d/canalCuencaLayer';
import { MeasurementLabels } from './map2d/measurement/MeasurementLabels';
import { MeasurementShapes } from './map2d/measurement/MeasurementShapes';
import { MeasurementToolbar } from './map2d/measurement/MeasurementToolbar';
import { useMeasurement } from './map2d/measurement/useMeasurement';
import { useComparisonSlider } from './map2d/useComparisonSlider';
import { useMapExportHandlers } from './map2d/useMapActionHandlers';
import { useMapDerivedState } from './map2d/useMapDerivedState';
import { useMapInitialization } from './map2d/useMapInitialization';
import { useFichaDrawWiring } from './map2d/useFichaDrawWiring';
import { useFichaInteraction } from './map2d/useFichaInteraction';
import { useMapEscapeExit } from './map2d/useMapEscapeExit';
import { useMapInteractionEffects } from './map2d/useMapInteractionEffects';
import { reloadIgnSource } from './map2d/mapRasterOverlayHelpers';
import { useMapLayerEffects } from './map2d/useMapLayerEffects';
import { useReportHighlight } from './map2d/useReportHighlight';
import { YPF_ESTACION_BOMBEO_GEOJSON } from './map2d/ypfEstacionBombeoLayer';

/* -------------------------------------------------------------------------- */
/*  Constants                                                                  */
/* -------------------------------------------------------------------------- */

const DEFAULT_ZOOM = MAP_DEFAULT_ZOOM;

/**
 * Is the ficha overlay ACTUALLY painting? (Enabled is not enough: the fetch may
 * still be in flight, and an enabled-but-empty overlay paints nothing.)
 *
 * ONE definition, TWO consumers — the overlay effect's `visible`, and the parcel
 * highlight's `overlayActive`. They must never disagree: the highlight
 * suppresses its amber fill precisely while these classes are on screen, so a
 * duplicated literal that drifted would put the wash back over the legend.
 *
 * A module-level helper rather than an inline expression because `MapaMapLibre`
 * sits exactly ON biome's `noExcessiveCognitiveComplexity` ceiling
 * (`maxAllowedComplexity: 30`, `biome.json`) — measured: inlining this one `&&`
 * anywhere inside the component takes it to 31 and trips the rule. The predicate
 * belongs outside the component anyway, since it is pure.
 */
function isFichaOverlayPainting(enabled: boolean, data: unknown): boolean {
  return enabled && data != null;
}

/* -------------------------------------------------------------------------- */
/*  Main component                                                             */
/* -------------------------------------------------------------------------- */

export default function MapaMapLibre() {
  // ── Config & auth ─────────────────────────────────────────────────────────
  const config = useConfigStore((state) => state.config);

  const mapCenter = config?.map.center ?? {
    lat: MAP_CENTER[0],
    lng: MAP_CENTER[1],
  };
  const centerLat = mapCenter.lat;
  const centerLng = mapCenter.lng;
  const zoom = config?.map.zoom ?? DEFAULT_ZOOM;

  // ── Map refs ──────────────────────────────────────────────────────────────
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const comparisonContainerRef = useRef<HTMLDivElement>(null);
  const comparisonMapRef = useRef<maplibregl.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);

  // Comparison slider
  const sliderContainerRef = useRef<HTMLDivElement>(null);
  const [sliderPosition, setSliderPosition] = useState(50);
  const isDraggingSlider = useRef(false);

  // ── UI state ──────────────────────────────────────────────────────────────
  // Phase 8 — array instead of single feature so InfoPanel can stack all
  // overlapping features at the click point (one section per layer).
  const [selectedFeatures, setSelectedFeatures] = useState<Feature[]>([]);
  // Ficha territorial free-draw handle (A5). `useFichaInteraction` (below) owns
  // all ficha interaction state; this ref lets the container kick off polygon
  // drawing imperatively once `DrawControl` mounts.
  const drawControlRef = useRef<DrawControlHandle>(null);
  // Startup default: 'satellite' so the first-load map shows Satélite + Imagen
  // (single view when an image is selected) plus Hidrografía + Red Vial.
  const [baseLayer, setBaseLayer] = useState<'osm' | 'satellite'>(DEFAULT_BASE_LAYER);
  const [viewMode, setViewMode] = useState<ViewMode>('base');
  const showLegend = true;
  const [showIGNOverlay, setShowIGNOverlay] = useState(false);
  const [showDemOverlay, setShowDemOverlay] = useState(false);
  const [activeDemLayerId, setActiveDemLayerId] = useState<string | null>(null);
  const [exportPngModalOpen, setExportPngModalOpen] = useState(false);
  // Latched export INTENT: flipped on the first time the user opens the Export
  // dropdown and never reset, so the heavy catastro GeoJSON (KMZ-only) is
  // fetched once, on demand. See the `useCatastroMap` call below.
  const [exportIntent, setExportIntent] = useState(false);
  // Latched BPA-join INTENT (same shape as `exportIntent`): flipped the first
  // time a PARCELA ficha opens, so the ~512KB `bpa_enriched.json` + history
  // pair is fetched on demand instead of on every /mapa mount. `staleTime:
  // Infinity` keeps the single fetch for the rest of the session.
  const [bpaJoinIntent, setBpaJoinIntent] = useState(false);
  const [exportIncludeLegend, setExportIncludeLegend] = useState(true);
  const [exportIncludeMetadata, setExportIncludeMetadata] = useState(true);
  const [exportTitle, setExportTitle] = useState('Mapa del Consorcio');
  const [hiddenClasses, setHiddenClasses] = useState<Record<string, number[]>>({});
  const [hiddenRanges, setHiddenRanges] = useState<Record<string, number[]>>({});
  const [visibleRasterLayers, setVisibleRasterLayers] = useState<Array<{ tipo: string }>>([]);

  // ── Layer sync store ──────────────────────────────────────────────────────
  const sharedVisibleVectors = useMapLayerSyncStore((state) => state.map2d.visibleVectors);
  const setSharedVectorVisibility = useMapLayerSyncStore((state) => state.setVectorVisibility);
  const propuestasEtapasVisibility = useMapLayerSyncStore(
    (state) => state.propuestasEtapasVisibility
  );
  const setEtapaVisible = useMapLayerSyncStore((state) => state.setEtapaVisible);
  // B4c/T3: the etapas filter also decides what the map DRAWS, so it has to
  // reach every active-layer count. Threaded to `LayerControlsPanel` (family
  // badge) and used below for the workspace badge.
  const etapaGate = useMapLayerSyncStore(selectEtapaGate);

  // ── Per-layer fine controls (Fase 3 — Tanda B) ────────────────────────────
  // Opacity/order slots + setters for the map2d view. Assembled into a single
  // `layerFineControl` object threaded to MapUiPanels + LayerControlsPanel.
  const opacityByLayer = useMapLayerSyncStore((state) => state.map2d.opacityByLayer);
  const orderByLayer = useMapLayerSyncStore((state) => state.map2d.orderByLayer);
  const setLayerOpacity = useMapLayerSyncStore((state) => state.setLayerOpacity);
  const setLayerOrder = useMapLayerSyncStore((state) => state.setLayerOrder);
  const layerFineControl = {
    opacityByLayer,
    onLayerOpacityChange: (layerId: string, multiplier: number) =>
      setLayerOpacity('map2d', layerId, multiplier),
    orderByLayer,
    onLayerOrderChange: (orderedIds: string[]) => setLayerOrder('map2d', orderedIds),
  };

  // Local visibility state (mirrors sharedVisibleVectors, drives setLayoutProperty)
  const [vectorVisibility, setVectorVisibility] = useState<Record<string, boolean>>(
    () => sharedVisibleVectors
  );

  // Sync from shared store → local
  useEffect(() => {
    setVectorVisibility(sharedVisibleVectors);
  }, [sharedVisibleVectors]);

  const toggleLayer = useCallback(
    (layerId: string, visible: boolean) => {
      setVectorVisibility((prev) => ({ ...prev, [layerId]: visible }));
      setSharedVectorVisibility('map2d', layerId, visible);
    },
    [setSharedVectorVisibility]
  );

  // ── Data hooks ────────────────────────────────────────────────────────────
  const { layers: capas } = useGEELayers({ layerNames: [...GEE_LAYER_NAMES] });
  const {
    caminos,
    consorcios,
    error: caminosError,
    reload: reloadCaminos,
  } = useCaminosColoreados();
  const { conflictos } = useConflictos();
  // Lazy fetch (~2.2MB geojson): the soil layer starts OFF
  // (mapLayerSyncStore soil: false), so defer the download until the user
  // actually toggles it on — same pattern as TerrainViewer3D.tsx.
  // Correctness: soilCollection is only consumed by syncSoilLayers (hidden
  // while OFF) and the KMZ export, which skips soil unless
  // visibleLayers.soil === true (kmzBuilder.ts::shouldIncludeLayer).
  const soilEnabled = !!vectorVisibility.soil;
  const { soilMap, error: soilError, reload: reloadSoil } = useSoilMap({ enabled: soilEnabled });
  const { basins, error: basinsError, reload: reloadBasins } = useBasins();
  const { waterways, error: waterwaysError, reload: reloadWaterways } = useWaterways();
  const {
    layers: allGeoLayers,
    error: geoLayersError,
    reload: reloadGeoLayers,
    enabled: geoLayersEnabled,
  } = useGeoLayers();
  const { approvedZones, hasApprovedZones } = useApprovedZones();

  const selectedImage = useSelectedImageListener();
  const comparison = useImageComparisonListener();
  // Lazy fetch (~1.6MB across 10 static assets). Split by consumer:
  //  - `meta` (aggregates.json, 4KB) stays EAGER because `showPilarVerde`
  //    (useMapDerivedState) gates the Pilar Verde toggles on it — deferring it
  //    would hide the checkboxes that are the only way to request the rest.
  //  - `layers` (~1.1MB of render GeoJSON) waits until a `pilar_verde_*` flag
  //    is on; all five default OFF.
  //  - `bpa` (~512KB) waits for a Pilar Verde layer (InfoPanel/BpaCard reads it
  //    for clicked BPA features) OR the latched parcela-ficha intent, which is
  //    what `PilarVerdeBadges` joins against.
  const pilarVerdeLayersNeeded = PILAR_VERDE_LAYER_IDS.some((id) => !!vectorVisibility[id]);
  const {
    data: pilarVerde,
    bpaLoading: bpaJoinLoading,
    bpaError: bpaJoinError,
    layersLoading: pilarVerdeLayersLoading,
    layersError: pilarVerdeLayersError,
    reloadLayers: reloadPilarVerdeLayers,
  } = usePilarVerde({
    layers: pilarVerdeLayersNeeded,
    bpa: pilarVerdeLayersNeeded || bpaJoinIntent,
  });
  const {
    relevados: canalesRelevados,
    propuestas: canalesPropuestas,
    index: canalesIndex,
    error: canalesError,
    reload: reloadCanales,
  } = useCanales();
  const canalesData = {
    relevados: canalesRelevados,
    propuestas: canalesPropuestas,
    index: canalesIndex,
  };
  const canalesRelevadosItems = useMemo(
    () => groupCanalesByFolder(canalesIndex?.relevados ?? [], 'relevado'),
    [canalesIndex]
  );
  const canalesPropuestosItems = useMemo(
    () => groupCanalesByFolder(canalesIndex?.propuestas ?? [], 'propuesto'),
    [canalesIndex]
  );
  const {
    collection: escuelasCollection,
    error: escuelasError,
    reload: reloadEscuelas,
  } = useEscuelas();
  const escuelasData = { collection: escuelasCollection };
  // Lazy fetch (~1.8MB geojson) gated on export INTENT, not on layer
  // visibility: the 2D catastro RENDER uses Martin vector tiles
  // (mapLayerEffectHelpers.ts::syncCatastroLayers), so this geojson's only 2D
  // consumer is `exportSources.catastro` for the KMZ export. Catastro now
  // defaults to ON, so gating on visibility meant every visitor paid a
  // multi-MB download + main-thread parse for a file the map never renders.
  // `exportIntent` latches when the Export dropdown opens — one paint frame
  // before the user can even click "Exportar KMZ" — and `staleTime: Infinity`
  // keeps the single fetch cached for the rest of the session.
  // Known race (unchanged trade-off): exporting KMZ while the fetch is still
  // in flight omits the catastro slot, the same graceful degradation buildKmz
  // already applies to any missing slot.
  const {
    catastroMap,
    error: catastroError,
    reload: reloadCatastro,
  } = useCatastroMap({ enabled: exportIntent });
  // Stable identity: `MapActionsPanel` is memoized, so an inline arrow here
  // would re-render it on every parent render.
  const handleExportIntent = useCallback(() => setExportIntent(true), []);

  const {
    zonaCollection,
    roadsCollection,
    soilCollection,
    waterwaysCollection,
    approvedZonesCollection,
    demTileUrl,
    demLayers,
    activeLegendItems,
    hasSingleImage,
    hasComparison,
    singleImageInfo,
    comparisonInfo,
    vectorLayerItems,
    demLayerOptions,
  } = useMapDerivedState({
    capas,
    caminos,
    soilMap,
    basins,
    waterways,
    allGeoLayers,
    approvedZones,
    hiddenClasses,
    hiddenRanges,
    activeDemLayerId,
    selectedImage,
    comparison,
    vectorVisibility,
    hasApprovedZones,
    intersectionsLength: conflictos?.features?.length ?? 0,
    pilarVerde,
    canales: canalesData,
    escuelas: escuelasData,
  });

  // Auto-activate comparison when comparison state changes
  useEffect(() => {
    if (comparison?.enabled && comparison.left && comparison.right) {
      setViewMode('comparison');
    }
  }, [comparison]);

  // Auto-activate single image view ONLY when an image transitions from
  // null → truthy (i.e. the user just selected one). Without the ref the
  // effect would re-fire whenever viewMode flips back to 'base', creating
  // an infinite loop where the user can never escape 'single' as long as
  // there is a selectedImage in the store.
  const prevSelectedImageRef = useRef(selectedImage);
  useEffect(() => {
    if (selectedImage && !prevSelectedImageRef.current) {
      setViewMode('single');
    }
    prevSelectedImageRef.current = selectedImage;
  }, [selectedImage]);

  useEffect(() => {
    const mapContainer = sliderContainerRef.current;
    const map = mapRef.current;
    if (!mapReady || !mapContainer || !map || !globalThis.ResizeObserver) return;

    const resizeObserver = new ResizeObserver(() => {
      map.resize();
      comparisonMapRef.current?.resize();
    });
    resizeObserver.observe(mapContainer);

    return () => resizeObserver.disconnect();
  }, [mapReady]);

  // Raster mosaics fail per TILE, not per layer: `useRasterTileHealth` folds
  // that firehose into a per-source "degradado" flag and only re-renders on a
  // transition. `onMapError` enters `useMapInitialization` through a REF — it
  // must never join that hook's dependency array (it would remount the map).
  const { degradedSourceIds, onMapError, clearSource } = useRasterTileHealth();

  // The IGN overlay is the ONE degraded source with a real retry: an
  // `ImageSource` fetches once from `onAdd` and never again, so the only way
  // back is rebuilding it. Clearing the health flag FIRST is deliberate — the
  // re-download is optimistic, and a second failure re-degrades it on its first
  // error (one-shot sources bypass the threshold).
  const reloadIgnOverlay = () => {
    const map = mapRef.current;
    if (!map) return;
    clearSource(SOURCE_IDS.IGN);
    reloadIgnSource(map, showIGNOverlay);
  };
  const ignOverlayDegraded = degradedSourceIds.includes(SOURCE_IDS.IGN);

  const layerHealth = useLayerHealth({
    caminos: { error: caminosError, reload: reloadCaminos },
    basins: { error: basinsError, reload: reloadBasins },
    waterways: { error: waterwaysError, reload: reloadWaterways },
    geo_layers: { error: geoLayersError, reload: reloadGeoLayers },
    soil: { error: soilError, reload: reloadSoil },
    catastro: { error: catastroError, reload: reloadCatastro },
    canales: { error: canalesError, reload: reloadCanales },
    escuelas: { error: escuelasError, reload: reloadEscuelas },
    pilar_verde: {
      error: pilarVerdeLayersError,
      loading: pilarVerdeLayersLoading,
      reload: reloadPilarVerdeLayers,
    },
    ign_overlay: {
      // Curated copy comes from the registry; this only says "it failed".
      error: ignOverlayDegraded ? 'ign image source failed' : null,
      reload: reloadIgnOverlay,
    },
    raster_tiles: { degradedSourceIds },
    // Lazy families: a CLOSED gate produces no entry, so an anonymous visitor
    // never reads a failure for a fetch that never ran, and "Reintentar" can
    // never pull a multi-MB asset the gate exists to defer.
    gates: {
      geoLayers: geoLayersEnabled,
      soil: soilEnabled,
      catastro: exportIntent,
      pilarVerde: pilarVerdeLayersNeeded,
      ignOverlay: showIGNOverlay,
    },
  });

  const layerProvenance = buildLayerProvenance({
    canalesGeneratedAt: canalesIndex?.generated_at,
    pilarVerdeGeneratedAt: pilarVerde?.aggregates?.generated_at,
  });

  useMapInitialization({
    maplibre: maplibregl,
    containerRef,
    centerLat,
    centerLng,
    zoom,
    mapRef,
    setMapReady,
    onMapError,
  });

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
    activeDemLayerId,
    showDemOverlay,
    demTileUrl,
    allGeoLayers,
    setVisibleRasterLayers,
    showIGNOverlay,
    viewMode,
    selectedImage,
    comparison,
    waterwaysDefs: WATERWAY_DEFS,
    pilarVerde,
    canales: canalesData,
    escuelas: escuelasData,
    isFichaCanal,
  });

  useMapInteractionEffects({
    mapRef,
    mapReady,
    measurementMode: fichaInteraction.interactionMode,
    setSelectedFeatures,
    onParcelaResolved: fichaInteraction.resolveParcela,
    // Mode transitions ALWAYS discard the selection, including with the sticky
    // touch mode on (where a null resolve means "you missed", not "clear").
    onClearParcelas: fichaInteraction.clearParcelas,
    onCanalResolved: fichaInteraction.resolveCanal,
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

  // Free-draw session wiring (T4). Lives in its own hook so the escape-mode
  // synthesis and the "Otro" path are unit-testable — see `useFichaDrawWiring`.
  const fichaDraw = useFichaDrawWiring({
    interactionMode: fichaInteraction.interactionMode,
    drawSession: fichaInteraction.state.drawing,
    redrawPolygon: fichaInteraction.redrawPolygon,
    drawControlRef,
  });
  const isFichaDrawSession = fichaDraw.isDrawSession;

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
    fichaInteraction.stopDraw();
    startMeasureDistance();
  }, [fichaInteraction, startMeasureDistance]);
  const handleStartMeasureArea = useCallback(() => {
    fichaInteraction.stopDraw();
    startMeasureArea();
  }, [fichaInteraction, startMeasureArea]);
  const handleToggleFichaDraw = useCallback(() => {
    if (fichaInteraction.state.drawing) fichaInteraction.stopDraw();
    else fichaInteraction.startDraw();
  }, [fichaInteraction]);
  // Draw-mode sub-controls (T3c, fix 4). MapboxDraw returns to `simple_select`
  // after `draw.create`, so these re-enter draw mode / wipe the polygon without
  // toggling the whole ficha-draw mode off and on.
  const handleRedrawPolygon = fichaDraw.handleRedrawPolygon;
  const handleDeleteDrawnPolygon = fichaDraw.handleDeletePolygon;
  const handleToggleFichaCanal = useCallback(() => {
    if (fichaInteraction.state.canalMode) fichaInteraction.stopCanal();
    else fichaInteraction.startCanal();
  }, [fichaInteraction]);
  // T4 — the touch equivalent of holding ctrl. Unlike draw/canal this is NOT a
  // map interaction mode: clicks keep resolving parcels exactly as in idle, they
  // just accumulate, so nothing here touches `interactionMode`.
  const handleToggleFichaMultiSelect = useCallback(() => {
    fichaInteraction.setMultiSelect(!fichaInteraction.state.multiSelect);
  }, [fichaInteraction]);

  // Escape is the universal exit from ANY active interaction mode. Until this
  // was wired, `useMeasurement.cancel()` had no caller at all and a user who
  // started measuring had no way back to idle (map-fluidity T1).
  const handleExitDraw = useCallback(() => fichaInteraction.stopDraw(), [fichaInteraction]);
  const handleExitCanal = useCallback(() => fichaInteraction.stopCanal(), [fichaInteraction]);
  useMapEscapeExit({
    // Escape must still leave the draw SESSION after the polygon is finished,
    // when `interactionMode` has already gone back to idle (T4).
    mode: fichaDraw.escapeMode,
    onCancelMeasurement: cancelMeasurement,
    onExitDraw: handleExitDraw,
    onExitCanal: handleExitCanal,
  });

  // Drop a temporary marker when the page is opened with `?lat=&lng=&zoom=`
  // (admin reports → "Ver en mapa"). Reads the URL once on mount; the
  // marker is auto-popped and the user can close it.
  useReportHighlight({ mapRef, mapReady });

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

  const comparisonSyncInputs: ComparisonOverlaySyncInputs = {
    leftTileUrl: comparison?.left?.tile_url ?? '',
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
  };
  const comparisonSyncInputsRef = useRef(comparisonSyncInputs);
  comparisonSyncInputsRef.current = comparisonSyncInputs;
  const comparisonControllerRef = useRef<ComparisonOverlayController | null>(null);
  const comparisonActive =
    mapReady &&
    viewMode === 'comparison' &&
    !!comparison?.left?.tile_url &&
    !!comparison?.right?.tile_url;

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
    consorcios: vectorVisibility.roads && !!roadsCollection ? consorcios : [],
    visibleRasterLayers,
    hiddenClasses,
    hiddenRanges,
    exportSources,
    zonaCollection,
    canalesRelevados:
      vectorVisibility.canales_relevados && !!canalesRelevados ? canalesRelevados : null,
  });

  /* ---------------------------------------------------------------------- */
  /*  Render                                                                 */
  /* ---------------------------------------------------------------------- */

  // Same hook `MapWorkspace` uses for the sidebar-vs-Drawer decision, so the
  // floating top bar and the Drawer can never both own the base-layer control.
  const isDesktop = useMapWorkspaceDesktop();

  // "N capas activas" indicator. It counts EXACTLY what the control panel shows
  // as rows — same derivation as the per-family badges (`buildFamilyActiveCounts`,
  // also called by `LayerControlsPanel`), so the two numbers agree by
  // construction. Counting raw `vectorVisibility` keys instead reported ~68
  // "active" layers (per-canal + per-waterway sub-keys) over a map with ~6
  // visible ones, flatly contradicting the badges beside it.
  const canalChildIds = collectCanalChildIds(
    canalesRelevadosItems,
    canalesPropuestosItems,
    vectorVisibility,
    etapaGate
  );
  const activeLayerCount = sumFamilyActiveCounts(
    buildFamilyActiveCounts({
      layerItems: vectorLayerItems,
      vectorVisibility,
      canalChildIds,
      showIGNOverlay,
      showDemOverlay,
    })
  );

  // ONE definition of the base-layer controls (capa base + the satellite view
  // mode slot), consumed by BOTH placements below so they cannot drift: the
  // desktop `.mapTopBar`, and — on mobile — `LayerControlsPanel`'s own "Base"
  // section inside the Drawer. `MapBaseSelectorPanel` and `LayerControlsPanel`
  // take the exact same three props, so the object is spread into either one.
  const baseControls = {
    baseLayer,
    onBaseLayerChange: setBaseLayer,
    viewModePanel:
      baseLayer === 'satellite' ? (
        <ViewModePanel
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          hasSingleImage={hasSingleImage}
          hasComparison={hasComparison}
          singleImageInfo={singleImageInfo}
          comparisonInfo={comparisonInfo}
        />
      ) : null,
  };

  return (
    <Box
      className={styles.mapWorkspace}
      data-testid="map-workspace"
      /* Published so the stylesheet can collapse the grid's first (top bar)
         row when the bar is not rendered — otherwise the `auto` row plus the
         `gap` leave 12px of dead space above the canvas on mobile. */
      data-topbar={isDesktop ? 'true' : 'false'}
    >
      {/* Desktop ONLY. On mobile the very same controls live in the layers
          Drawer (see the `controls` tree below): a floating bar over a 360px
          canvas cost ~149px of map and duplicated a control the Drawer already
          owns. Both branches read `baseControls`, so there is exactly one
          definition of what "base layer controls" means. */}
      {isDesktop && (
        <Box
          className={styles.mapTopBar}
          aria-label="Selector de capa base y vista satelital"
          data-testid="map-top-bar"
        >
          <MapBaseSelectorPanel {...baseControls} />
        </Box>
      )}

      <MapWorkspace
        activeLayerCount={activeLayerCount}
        canvas={
          <Box
            className={styles.mapCanvasWrapper}
            role="application"
            aria-label="mapa interactivo del consorcio para explorar cuencas, canales e infraestructura"
          >
            {/* Map container */}
            <div
              ref={sliderContainerRef}
              style={{ width: '100%', height: '100%', position: 'relative' }}
            >
              <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
              {viewMode === 'comparison' && comparison?.left && comparison.right && (
                <div
                  ref={comparisonContainerRef}
                  style={{
                    position: 'absolute',
                    inset: 0,
                    pointerEvents: 'none',
                    zIndex: 10,
                    clipPath: `inset(0 ${100 - sliderPosition}% 0 0)`,
                  }}
                />
              )}
              <MapViewportOverlay
                viewMode={viewMode}
                sliderPosition={sliderPosition}
                mapReady={mapReady}
                onSliderPointerDown={handleSliderPointerDown}
              />
            </div>

            {/* Measurement tools + ficha free-draw: one floating toolbar (JDB-012). */}
            <MeasurementToolbar
              mode={fichaInteraction.interactionMode}
              hasMeasurements={measurementState.measurements.length > 0}
              onStartDistance={handleStartMeasureDistance}
              onStartArea={handleStartMeasureArea}
              onClear={clearMeasurements}
              onCancel={cancelMeasurement}
              fichaDrawActive={isFichaDrawSession}
              onToggleFichaDraw={handleToggleFichaDraw}
              onRedrawPolygon={handleRedrawPolygon}
              onDeletePolygon={handleDeleteDrawnPolygon}
              fichaCanalActive={isFichaCanal}
              onToggleFichaCanal={handleToggleFichaCanal}
              fichaMultiSelectActive={fichaInteraction.state.multiSelect}
              onToggleFichaMultiSelect={handleToggleFichaMultiSelect}
            />

            {/* Canal analysis (A6 + A7): the influence-strip vs catchment control
                is NO LONGER a standalone floating card — it now renders as a
                header section INSIDE `FichaTerritorialPanel` (threaded below via
                the `fichaCanal*` props) so it can never be covered by the ficha
                card and stays reachable in loading/error states. */}
            <MeasurementLabels map={measurementMap} measurements={measurementState.measurements} />
            <MeasurementShapes map={measurementMap} measurements={measurementState.measurements} />

            {/* Ficha free-draw (A5): DrawControl is mounted ONLY while drawing so it
                never coexists with the measurement MapboxDraw (shared-slot bug). A
                completed polygon fires a `tipo=poligono` ficha via the container. */}
            {measurementMap && isFichaDrawSession && (
              <DrawControl
                ref={drawControlRef}
                map={measurementMap}
                onPolygonCreated={fichaInteraction.completePolygon}
                onPolygonDeleted={fichaInteraction.deletePolygon}
              />
            )}

            <MapUiPanels
              baseLayer={baseLayer}
              onBaseLayerChange={setBaseLayer}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
              hasSingleImage={hasSingleImage}
              hasComparison={hasComparison}
              singleImageInfo={singleImageInfo}
              comparisonInfo={comparisonInfo}
              layerItems={vectorLayerItems}
              vectorVisibility={vectorVisibility}
              onLayerVisibilityChange={toggleLayer}
              showIGNOverlay={showIGNOverlay}
              onShowIGNOverlayChange={setShowIGNOverlay}
              demEnabled={demLayers.length > 0}
              showDemOverlay={showDemOverlay}
              onShowDemOverlayChange={setShowDemOverlay}
              activeDemLayerId={activeDemLayerId}
              onActiveDemLayerIdChange={setActiveDemLayerId}
              demOptions={demLayerOptions}
              canalesRelevadosItems={canalesRelevadosItems}
              canalesPropuestosItems={canalesPropuestosItems}
              etapaGate={etapaGate}
              layerFineControl={layerFineControl}
              hasApprovedZones={hasApprovedZones}
              onOpenExportPng={() => setExportPngModalOpen(true)}
              onExportApprovedZonesPdf={handleExportApprovedZonesPdf}
              onExportKmz={handleExportKmz}
              onExportMenuOpen={handleExportIntent}
              showLegend={showLegend}
              consorcios={vectorVisibility.roads && !!roadsCollection ? consorcios : []}
              activeLegendItems={activeLegendItems}
              visibleRasterLayers={visibleRasterLayers}
              hiddenClasses={hiddenClasses}
              hiddenRanges={hiddenRanges}
              onClassToggle={(layerType, classIndex, visible) =>
                setHiddenClasses((prev) => {
                  const curr = prev[layerType] ?? [];
                  const next = visible
                    ? curr.filter((i) => i !== classIndex)
                    : [...curr, classIndex];
                  return { ...prev, [layerType]: next };
                })
              }
              onRangeToggle={(layerType, rangeIndex, visible) =>
                setHiddenRanges((prev) => {
                  const curr = prev[layerType] ?? [];
                  const next = visible
                    ? curr.filter((i) => i !== rangeIndex)
                    : [...curr, rangeIndex];
                  return { ...prev, [layerType]: next };
                })
              }
              selectedFeatures={selectedFeatures}
              onCloseInfoPanel={() => setSelectedFeatures([])}
              fichaActive={fichaInteraction.request !== null}
              fichaTipo={fichaInteraction.tipo}
              fichaNroCuenta={fichaInteraction.nroCuenta}
              fichaSelectionKey={fichaKey}
              fichaParcelaProps={fichaInteraction.parcelaProps}
              fichaParcelasCount={fichaInteraction.parcelasAnalizadas.length}
              onFichaRemoveParcelas={fichaInteraction.removeParcelas}
              fichaLoading={ficha.isLoading}
              fichaFetching={ficha.isFetching}
              fichaError={ficha.error}
              fichaData={ficha.data}
              onCloseFicha={fichaInteraction.clearFicha}
              onRetryFicha={ficha.refetch}
              fichaOverlayVisible={fichaTabs.overlayVisible}
              onToggleFichaOverlay={fichaTabs.setOverlayVisible}
              fichaTab={fichaTabs.tab}
              onChangeFichaTab={fichaTabs.changeTab}
              fichaHiddenClases={fichaTabs.hiddenClases}
              onToggleFichaClase={fichaTabs.toggleClase}
              fichaOverlayLoading={fichaOverlay.isLoading}
              fichaOverlayError={fichaOverlay.isError}
              mapDragSignal={mapDragSignal}
              fichaCanalNombre={fichaInteraction.state.canal?.canalNombre ?? null}
              fichaCanalAnalysisMode={fichaInteraction.state.canal?.analysisMode}
              onFichaCanalAnalysisModeChange={fichaInteraction.setCanalAnalysisMode}
              fichaCanalBufferM={fichaInteraction.state.canal?.bufferM}
              fichaCanalMaxBufferM={FICHA_MAX_BUFFER_M}
              onFichaCanalBufferChange={fichaInteraction.setBuffer}
              bpaEnriched={pilarVerde?.bpaEnriched}
              bpaLoading={bpaJoinLoading}
              bpaError={bpaJoinError}
              bpaHistory={pilarVerde?.bpaHistory}
              exportPngModalOpen={exportPngModalOpen}
              onCloseExportPngModal={() => setExportPngModalOpen(false)}
              exportTitle={exportTitle}
              exportIncludeLegend={exportIncludeLegend}
              exportIncludeMetadata={exportIncludeMetadata}
              onExportTitleChange={setExportTitle}
              onExportIncludeLegendChange={setExportIncludeLegend}
              onExportIncludeMetadataChange={setExportIncludeMetadata}
              onExportPng={handleExportPng}
              layerHealth={layerHealth}
              layerProvenance={layerProvenance}
              showEmbeddedMapControls={false}
              showEmbeddedRasterLegend={false}
            />
          </Box>
        }
        controls={
          /* ONE scroll only (T5): `.workspaceSidebarBody` (desktop) / the Drawer
             body (mobile) is the scroller, so every panel in this tree renders
             unbounded. Three nested scroll areas used to push the legend out of
             reach and trap the wheel gesture. */
          <Stack gap="sm" data-testid="map-controls-tree">
            <LayerControlsPanel
              insideScrollContainer
              /* Mobile ONLY. `LayerControlsPanel` renders the "Capa base"
                 selector and the `viewModePanel` slot only when these props are
                 defined, so spreading them exclusively on !isDesktop is what
                 keeps EXACTLY ONE base-layer control on screen: the floating
                 `.mapTopBar` owns it on desktop, the Drawer owns it here. Same
                 `baseControls` either way. */
              {...(isDesktop ? {} : baseControls)}
              layerItems={vectorLayerItems}
              vectorVisibility={vectorVisibility}
              onLayerVisibilityChange={toggleLayer}
              showIGNOverlay={showIGNOverlay}
              onShowIGNOverlayChange={setShowIGNOverlay}
              demEnabled={demLayers.length > 0}
              showDemOverlay={showDemOverlay}
              onShowDemOverlayChange={setShowDemOverlay}
              activeDemLayerId={activeDemLayerId}
              onActiveDemLayerIdChange={setActiveDemLayerId}
              demOptions={demLayerOptions}
              canalesRelevadosItems={canalesRelevadosItems}
              canalesPropuestosItems={canalesPropuestosItems}
              etapaGate={etapaGate}
              layerFineControl={layerFineControl}
              pilarVerdeLayersLoading={pilarVerdeLayersLoading}
              pilarVerdeLayersError={pilarVerdeLayersError}
              layerHealth={layerHealth}
              layerProvenance={layerProvenance}
            />
            {showLegend && (
              <>
                <LeyendaPanel
                  consorcios={vectorVisibility.roads && !!roadsCollection ? consorcios : []}
                  customItems={activeLegendItems}
                  embedded
                  insideScrollContainer
                  data-testid="map-2d-external-leyenda-panel"
                  pilarVerdeBpaHistoricoVisible={!!vectorVisibility.pilar_verde_bpa_historico}
                  pilarVerdeAgroAceptadaVisible={!!vectorVisibility.pilar_verde_agro_aceptada}
                  pilarVerdeAgroPresentadaVisible={!!vectorVisibility.pilar_verde_agro_presentada}
                  pilarVerdeAgroZonasVisible={!!vectorVisibility.pilar_verde_agro_zonas}
                  pilarVerdePorcentajeForestacionVisible={
                    !!vectorVisibility.pilar_verde_porcentaje_forestacion
                  }
                  pilarAzulCanalesRelevadosVisible={!!vectorVisibility.canales_relevados}
                  pilarAzulCanalesPropuestosVisible={!!vectorVisibility.canales_propuestos}
                  pilarAzulEscuelasVisible={!!vectorVisibility.escuelas}
                  propuestasEtapasVisibility={propuestasEtapasVisibility}
                  onSetEtapaVisible={setEtapaVisible}
                />
                {visibleRasterLayers.length > 0 && (
                  <RasterLegend
                    layers={visibleRasterLayers}
                    hiddenClasses={hiddenClasses}
                    hiddenRanges={hiddenRanges}
                    floating={false}
                    onClassToggle={(layerType, classIndex, visible) =>
                      setHiddenClasses((prev) => {
                        const curr = prev[layerType] ?? [];
                        const next = visible
                          ? curr.filter((i) => i !== classIndex)
                          : [...curr, classIndex];
                        return { ...prev, [layerType]: next };
                      })
                    }
                    onRangeToggle={(layerType, rangeIndex, visible) =>
                      setHiddenRanges((prev) => {
                        const curr = prev[layerType] ?? [];
                        const next = visible
                          ? curr.filter((i) => i !== rangeIndex)
                          : [...curr, rangeIndex];
                        return { ...prev, [layerType]: next };
                      })
                    }
                  />
                )}
              </>
            )}
          </Stack>
        }
      />
    </Box>
  );
}
