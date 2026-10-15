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

import type { Feature } from 'geojson';

import * as maplibregl from 'maplibre-gl';
import { bootMapLibreWorker } from '../lib/maplibreLoader';
import { groupCanalesByFolder } from './shared/canalesGrouping';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import '../lib/pmtilesProtocol';

// Register PMTiles protocol once at module level (see pmtilesProtocol.ts).
// NOTE: migrating the vector layers to PMTiles is a SEPARATE ticket — several
// layers (waterways especially) are consumed as decorated FeatureCollections
// both by the map and by the KMZ export (`exportSources`), so a tile source
// would have to keep a GeoJSON twin alive for the export path.
void bootMapLibreWorker();

import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../constants';
import { useApprovedZones } from '../hooks/useApprovedZones';
import { useAuth } from '../hooks/useAuth';
import { useBasins } from '../hooks/useBasins';
import { useCaminosColoreados } from '../hooks/useCaminosColoreados';
import { useCanales } from '../hooks/useCanales';
import { useCatastroMap } from '../hooks/useCatastroMap';
import { useConflictos } from '../hooks/useConflictos';
import { useDeferredIdleMount } from '../hooks/useDeferredIdleMount';
import { useEscuelas } from '../hooks/useEscuelas';
import { useGEELayers } from '../hooks/useGEELayers';
import {
  buildTileUrl,
  combineHazardGeoLayers,
  useGeoLayers,
  usePrecipNormalLayers,
} from '../hooks/useGeoLayers';
import { useImageComparisonListener } from '../hooks/useImageComparison';
import { usePilarVerde } from '../hooks/usePilarVerde';
import { useSelectedImageListener } from '../hooks/useSelectedImage';
import { useSoilMap } from '../hooks/useSoilMap';
import { useWaterways } from '../hooks/useWaterways';
import { useConfigStore } from '../stores/configStore';
import { useMapCameraStore } from '../stores/mapCameraStore';
import {
  PILAR_VERDE_LAYER_IDS,
  selectEtapaGate,
  useMapLayerSyncStore,
} from '../stores/mapLayerSyncStore';
import type { DrawControlHandle } from './map/DrawControl';
import { canalCollections, fitMapToCanal } from './map2d/canalFocus';
import { buildLayerProvenance } from './map2d/layerProvenance';
import { MapaMapLibreView } from './map2d/MapaMapLibreView';
import { DEFAULT_BASE_LAYER, GEE_LAYER_NAMES, SOURCE_IDS } from './map2d/map2dConfig';
import type { ClassifiedMapError } from './map2d/mapErrorClassify';
import { MAP2D_HILLSHADE_Z_FACTOR, reloadIgnSource } from './map2d/mapRasterOverlayHelpers';
import type { ProfileRangeStats } from './map2d/profileRange';
import { useLayerHealth } from './map2d/useLayerHealth';
import { useMapaMapLibreStage } from './map2d/useMapaMapLibreStage';
import { useMapDerivedState } from './map2d/useMapDerivedState';
import { useMapInitialization } from './map2d/useMapInitialization';
import { useMapPermalink } from './map2d/useMapPermalink';
import type { QuickPlacePin } from './map2d/useQuickPlaceMarker';
import { useRasterTileHealth } from './map2d/useRasterTileHealth';
import { useRasterTileLoading } from './map2d/useRasterTileLoading';
import { useRoadFlowWiring } from './map2d/useRoadFlowWiring';
import type { ViewMode } from './map2d/ViewModePanel';

/* -------------------------------------------------------------------------- */
/*  Constants                                                                  */
/* -------------------------------------------------------------------------- */

const DEFAULT_ZOOM = MAP_DEFAULT_ZOOM;

/* -------------------------------------------------------------------------- */
/*  Main component                                                             */
/* -------------------------------------------------------------------------- */

export default function MapaMapLibre() {
  // ── Config & auth ─────────────────────────────────────────────────────────
  const config = useConfigStore((state) => state.config);
  const { isStaff } = useAuth();

  const mapCenter = config?.map.center ?? {
    lat: MAP_CENTER[0],
    lng: MAP_CENTER[1],
  };
  const handedCamera = useMapCameraStore.getState().camera;
  const centerLat = handedCamera?.lat ?? mapCenter.lat;
  const centerLng = handedCamera?.lng ?? mapCenter.lng;
  const zoom = handedCamera?.zoom ?? config?.map.zoom ?? DEFAULT_ZOOM;

  // ── Map refs ──────────────────────────────────────────────────────────────
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const comparisonContainerRef = useRef<HTMLDivElement>(null);
  const comparisonMapRef = useRef<maplibregl.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapLoadError, setMapLoadError] = useState<string | null>(null);

  // Comparison slider
  const sliderContainerRef = useRef<HTMLDivElement>(null);
  const [sliderPosition, setSliderPosition] = useState(50);
  const isDraggingSlider = useRef(false);

  // ── UI state ──────────────────────────────────────────────────────────────
  // Phase 8 — array instead of single feature so InfoPanel can stack all
  // overlapping features at the click point (one section per layer).
  const [selectedFeatures, setSelectedFeatures] = useState<Feature[]>([]);
  const [elevationProfileHover, setElevationProfileHover] = useState<{
    lon: number;
    lat: number;
  } | null>(null);
  const [elevationProfileRange, setElevationProfileRange] = useState<ProfileRangeStats | null>(
    null
  );
  const [quickPlace, setQuickPlace] = useState<QuickPlacePin | null>(null);
  useEffect(() => {
    setElevationProfileHover(null);
    setElevationProfileRange(null);
  }, [selectedFeatures]);
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
  const [showHillshade, setShowHillshade] = useState(false);
  const [showDemOverlay, setShowDemOverlay] = useState(false);
  const [activeDemLayerId, setActiveDemLayerId] = useState<string | null>(null);
  const [rasterCompareId, setRasterCompareId] = useState<string | null>(null);
  const rasterCompareActive =
    !!rasterCompareId &&
    !!activeDemLayerId &&
    rasterCompareId !== activeDemLayerId &&
    showDemOverlay;
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
  const labelSizeScale = useMapLayerSyncStore((state) => state.map2d.labelSizeScale);
  const lineWidthScale = useMapLayerSyncStore((state) => state.map2d.lineWidthScale);
  const setLayerOpacity = useMapLayerSyncStore((state) => state.setLayerOpacity);
  const setLayerOrder = useMapLayerSyncStore((state) => state.setLayerOrder);
  const setLabelSizeScale = useMapLayerSyncStore((state) => state.setLabelSizeScale);
  const setLineWidthScale = useMapLayerSyncStore((state) => state.setLineWidthScale);
  const layerFineControl = {
    opacityByLayer,
    onLayerOpacityChange: (layerId: string, multiplier: number) =>
      setLayerOpacity('map2d', layerId, multiplier),
    orderByLayer,
    onLayerOrderChange: (orderedIds: string[]) => setLayerOrder('map2d', orderedIds),
    labelSizeScale,
    onLabelSizeScaleChange: (scale: number) => setLabelSizeScale('map2d', scale),
    lineWidthScale,
    onLineWidthScaleChange: (scale: number) => setLineWidthScale('map2d', scale),
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
  // Roads + waterways are ON at startup but not LCP. Wait for idle so the
  // GeoJSON fetches (and JSON.parse) stay off the first TBT window.
  const mapVectorIdle = useDeferredIdleMount();
  const { layers: capas } = useGEELayers({ layerNames: [...GEE_LAYER_NAMES] });
  const {
    caminos,
    consorcios,
    error: caminosError,
    reload: reloadCaminos,
  } = useCaminosColoreados({ enabled: mapVectorIdle });
  const { conflictos } = useConflictos();
  // 2D paint uses `suelos_cu.pmtiles` (syncSoilLayers). The GeoJSON is only
  // for KMZ export — same latch as catastro (`exportIntent`).
  const {
    soilMap,
    error: soilError,
    reload: reloadSoil,
  } = useSoilMap({
    enabled: exportIntent,
  });
  const { basins, error: basinsError, loading: basinsLoading, reload: reloadBasins } = useBasins();
  const {
    waterways,
    error: waterwaysError,
    reload: reloadWaterways,
  } = useWaterways({
    enabled: mapVectorIdle,
  });
  const {
    layers: allGeoLayers,
    error: geoLayersError,
    reload: reloadGeoLayers,
    enabled: geoLayersEnabled,
  } = useGeoLayers();
  const rasterLoading = useRasterTileLoading(mapReady ? mapRef.current : null, showDemOverlay);
  const demRawLayer = allGeoLayers.find((layer) => layer.tipo === 'dem_raw');
  const hillshadeTileUrl = demRawLayer
    ? buildTileUrl(demRawLayer.id, {
        encoding: 'terrain-rgb',
        zFactor: MAP2D_HILLSHADE_Z_FACTOR,
      })
    : null;
  const { layers: precipNormalLayers } = usePrecipNormalLayers();
  const hazardGeoLayers = combineHazardGeoLayers(allGeoLayers, precipNormalLayers);
  const { approvedZones, hasApprovedZones } = useApprovedZones();

  // Cruces de camino (flujo-caminos, S4). ONE hook owns the whole capability —
  // fetch, panel state, survey selection and the map gestures. See its header
  // for why it is not inline here.
  const deactivateRoadFlow = useCallback(() => toggleLayer('road_flow', false), [toggleLayer]);
  const roadFlow = useRoadFlowWiring({
    mapRef,
    mapReady,
    active: !!vectorVisibility.road_flow || !!vectorVisibility.sentido_camino,
    panelActive: !!vectorVisibility.road_flow,
    geoLayers: allGeoLayers,
    onDeactivate: deactivateRoadFlow,
  });

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
  } = useCanales(isStaff ? 'interno' : 'public');
  const canalesData = {
    relevados: canalesRelevados,
    propuestas: canalesPropuestas,
    index: canalesIndex,
  };
  const canalesRelevadosItems = useMemo(
    () => groupCanalesByFolder(canalesIndex?.relevados ?? [], 'relevado'),
    [canalesIndex]
  );
  const flyToCanal = (toggleId: string) => {
    fitMapToCanal(mapRef.current, canalCollections(canalesRelevados, canalesPropuestas), toggleId);
  };
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
    showRoadFlow: roadFlow.showRoadFlow,
    // Same staff bit as road_flow (isStaff). Not "POIs follow the crossings
    // toggle": useMapDerivedState runs before usePuntosInteresWiring, so the
    // POI hook's showPuntosInteres is not in scope here.
    showPuntosInteres: roadFlow.showRoadFlow,
    showRedVialOficial: isStaff,
    showCaminosHuecos: isStaff,
  });

  const satelliteLayer =
    viewMode === 'single' && singleImageInfo
      ? { label: `Imagen ${singleImageInfo.sensor} · ${singleImageInfo.date}` }
      : null;

  useMapPermalink({
    mapRef,
    mapReady,
    showDemOverlay,
    activeDemLayerId,
    setShowDemOverlay,
    setActiveDemLayerId,
    demLayers,
  });

  // The comparison view is NEVER auto-activated from the comparison state.
  // A saved pair is restored (localStorage, or the public endpoint for
  // incognito / cross-device) but restoring it must not switch the view:
  // entering the map shows the chosen image, or the base map. The pair stays
  // saved and the `Base | Imagen | Comparar` selector is one click away.
  // Regression this pins: an effect here flipped the view to 'comparison' on
  // the ASYNC backend restore, overriding the image the visitor had chosen.

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
  const handleMapError = (error: ClassifiedMapError) => {
    onMapError(error);
    if (error.kind === 'other' && /no pudimos cargar el mapa/i.test(error.message)) {
      setMapLoadError(error.message);
    }
  };

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
      soil: exportIntent,
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
    onMapError: handleMapError,
  });

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (handedCamera?.bearing) {
      map.setBearing(handedCamera.bearing);
    }
    const publish = () => {
      const c = map.getCenter();
      useMapCameraStore.getState().setCamera({
        lng: c.lng,
        lat: c.lat,
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
      });
    };
    map.on('moveend', publish);
    return () => {
      map.off('moveend', publish);
    };
  }, [mapReady]);

  const stage = useMapaMapLibreStage({
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
  });

  return (
    <MapaMapLibreView
      {...stage}
      activeDemLayerId={activeDemLayerId}
      activeLegendItems={activeLegendItems}
      baseLayer={baseLayer}
      bpaJoinError={bpaJoinError}
      bpaJoinLoading={bpaJoinLoading}
      canalesPropuestosItems={canalesPropuestosItems}
      canalesRelevadosItems={canalesRelevadosItems}
      comparisonContainerRef={comparisonContainerRef}
      comparisonInfo={comparisonInfo}
      consorcios={consorcios}
      containerRef={containerRef}
      demLayerOptions={demLayerOptions}
      demLayers={demLayers}
      drawControlRef={drawControlRef}
      etapaGate={etapaGate}
      exportIncludeLegend={exportIncludeLegend}
      exportIncludeMetadata={exportIncludeMetadata}
      exportPngModalOpen={exportPngModalOpen}
      exportTitle={exportTitle}
      flyToCanal={flyToCanal}
      geoLayersError={geoLayersError}
      handleExportIntent={handleExportIntent}
      hasApprovedZones={hasApprovedZones}
      hasComparison={hasComparison}
      hasSingleImage={hasSingleImage}
      hiddenClasses={hiddenClasses}
      hiddenRanges={hiddenRanges}
      hillshadeTileUrl={hillshadeTileUrl}
      layerFineControl={layerFineControl}
      layerHealth={layerHealth}
      layerProvenance={layerProvenance}
      mapLoadError={mapLoadError}
      mapReady={mapReady}
      mapRef={mapRef}
      pilarVerde={pilarVerde}
      pilarVerdeLayersError={pilarVerdeLayersError}
      pilarVerdeLayersLoading={pilarVerdeLayersLoading}
      propuestasEtapasVisibility={propuestasEtapasVisibility}
      rasterCompareActive={rasterCompareActive}
      rasterCompareId={rasterCompareId}
      rasterLoading={rasterLoading}
      reloadGeoLayers={reloadGeoLayers}
      roadFlow={roadFlow}
      roadsCollection={roadsCollection}
      satelliteLayer={satelliteLayer}
      selectedFeatures={selectedFeatures}
      setActiveDemLayerId={setActiveDemLayerId}
      setBaseLayer={setBaseLayer}
      setElevationProfileHover={setElevationProfileHover}
      setElevationProfileRange={setElevationProfileRange}
      setEtapaVisible={setEtapaVisible}
      setExportIncludeLegend={setExportIncludeLegend}
      setExportIncludeMetadata={setExportIncludeMetadata}
      setExportPngModalOpen={setExportPngModalOpen}
      setExportTitle={setExportTitle}
      setHiddenClasses={setHiddenClasses}
      setHiddenRanges={setHiddenRanges}
      setQuickPlace={setQuickPlace}
      setRasterCompareId={setRasterCompareId}
      setSelectedFeatures={setSelectedFeatures}
      setShowDemOverlay={setShowDemOverlay}
      setShowHillshade={setShowHillshade}
      setShowIGNOverlay={setShowIGNOverlay}
      setViewMode={setViewMode}
      showDemOverlay={showDemOverlay}
      showHillshade={showHillshade}
      showIGNOverlay={showIGNOverlay}
      showLegend={showLegend}
      singleImageInfo={singleImageInfo}
      sliderContainerRef={sliderContainerRef}
      sliderPosition={sliderPosition}
      toggleLayer={toggleLayer}
      vectorLayerItems={vectorLayerItems}
      vectorVisibility={vectorVisibility}
      viewMode={viewMode}
      visibleRasterLayers={visibleRasterLayers}
      waterwaysError={waterwaysError}
    />
  );
}
