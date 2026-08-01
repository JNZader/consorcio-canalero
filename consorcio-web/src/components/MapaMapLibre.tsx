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
import type { Feature } from 'geojson';

import maplibregl from 'maplibre-gl';
import { ALL_ETAPAS, type Etapa } from '../types/canales';
import { groupCanalesByFolder } from './shared/canalesGrouping';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Protocol } from 'pmtiles';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

// Register PMTiles protocol once at module level
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
import { useFichaTerritorial } from '../hooks/useFichaTerritorial';
import { useGEELayers } from '../hooks/useGEELayers';
import { useGeoLayers } from '../hooks/useGeoLayers';
import { useImageComparisonListener } from '../hooks/useImageComparison';
import { usePilarVerde } from '../hooks/usePilarVerde';
import { useSelectedImageListener } from '../hooks/useSelectedImage';
import { useSoilMap } from '../hooks/useSoilMap';
import { WATERWAY_DEFS, useWaterways } from '../hooks/useWaterways';
import { useConfigStore } from '../stores/configStore';
import { useMapLayerSyncStore } from '../stores/mapLayerSyncStore';
import styles from '../styles/components/map.module.css';
import { RasterLegend } from './RasterLegend';
import { LayerControlsPanel } from './map2d/LayerControlsPanel';
import { LeyendaPanel } from './map2d/LeyendaPanel';
import { MapBaseSelectorPanel } from './map2d/MapBaseSelectorPanel';
import { MapUiPanels } from './map2d/MapUiPanels';
import { MapViewportOverlay } from './map2d/MapViewportOverlay';
import { MapWorkspace } from './map2d/MapWorkspace';
import { type ViewMode, ViewModePanel } from './map2d/ViewModePanel';
import {
  type ComparisonOverlayController,
  type ComparisonOverlaySyncInputs,
  createComparisonOverlayController,
} from './map2d/comparisonOverlay';
import { DEFAULT_BASE_LAYER, GEE_LAYER_NAMES } from './map2d/map2dConfig';
import { MeasurementLabels } from './map2d/measurement/MeasurementLabels';
import { MeasurementShapes } from './map2d/measurement/MeasurementShapes';
import { MeasurementToolbar } from './map2d/measurement/MeasurementToolbar';
import { useMeasurement } from './map2d/measurement/useMeasurement';
import { useComparisonSlider } from './map2d/useComparisonSlider';
import { useMapExportHandlers } from './map2d/useMapActionHandlers';
import { useMapDerivedState } from './map2d/useMapDerivedState';
import { useMapInitialization } from './map2d/useMapInitialization';
import { type ParcelaResuelta, useMapInteractionEffects } from './map2d/useMapInteractionEffects';
import { useMapLayerEffects } from './map2d/useMapLayerEffects';
import { useReportHighlight } from './map2d/useReportHighlight';
import { YPF_ESTACION_BOMBEO_GEOJSON } from './map2d/ypfEstacionBombeoLayer';

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

  const mapCenter = config?.map.center ?? { lat: MAP_CENTER[0], lng: MAP_CENTER[1] };
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
  // Ficha territorial (A4) — the catastro parcel resolved by the last click, or
  // null. Drives `useFichaTerritorial` and the sibling `<FichaTerritorialPanel>`.
  const [fichaParcela, setFichaParcela] = useState<ParcelaResuelta | null>(null);
  // Startup default: 'satellite' so the first-load map shows Satélite + Imagen
  // (single view when an image is selected) plus Hidrografía + Red Vial.
  const [baseLayer, setBaseLayer] = useState<'osm' | 'satellite'>(DEFAULT_BASE_LAYER);
  const [viewMode, setViewMode] = useState<ViewMode>('base');
  const showLegend = true;
  const [showIGNOverlay, setShowIGNOverlay] = useState(false);
  const [showDemOverlay, setShowDemOverlay] = useState(false);
  const [activeDemLayerId, setActiveDemLayerId] = useState<string | null>(null);
  const [exportPngModalOpen, setExportPngModalOpen] = useState(false);
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
  const { caminos, consorcios } = useCaminosColoreados();
  const { conflictos } = useConflictos();
  // Lazy fetch (~2.2MB geojson): the soil layer starts OFF
  // (mapLayerSyncStore soil: false), so defer the download until the user
  // actually toggles it on — same pattern as TerrainViewer3D.tsx.
  // Correctness: soilCollection is only consumed by syncSoilLayers (hidden
  // while OFF) and the KMZ export, which skips soil unless
  // visibleLayers.soil === true (kmzBuilder.ts::shouldIncludeLayer).
  const { soilMap } = useSoilMap({ enabled: !!vectorVisibility.soil });
  const { basins } = useBasins();
  const { waterways } = useWaterways();
  const { layers: allGeoLayers } = useGeoLayers();
  const { approvedZones, hasApprovedZones } = useApprovedZones();

  const selectedImage = useSelectedImageListener();
  const comparison = useImageComparisonListener();
  const { data: pilarVerde } = usePilarVerde();
  const {
    relevados: canalesRelevados,
    propuestas: canalesPropuestas,
    index: canalesIndex,
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
  const { collection: escuelasCollection } = useEscuelas();
  const escuelasData = { collection: escuelasCollection };
  // Lazy fetch (~1.8MB geojson): the 2D catastro RENDER uses Martin vector
  // tiles (mapLayerEffectHelpers.ts::syncCatastroLayers) — this geojson's
  // only 2D consumer is `exportSources.catastro` for the KMZ export. The
  // KMZ builder only includes catastro when the layer is visible
  // (kmzBuilder.ts::shouldIncludeLayer → visibleLayers.catastro === true),
  // so gating the fetch on visibility is lossless for the export.
  // Known race (documented trade-off): toggling catastro ON and exporting
  // KMZ before the fetch resolves silently omits the layer — same graceful
  // degradation buildKmz already applies to any missing slot.
  const { catastroMap } = useCatastroMap({ enabled: !!vectorVisibility.catastro });

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
  });

  useMapInitialization({
    maplibre: maplibregl,
    containerRef,
    centerLat,
    centerLng,
    zoom,
    mapRef,
    setMapReady,
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
  } = useMeasurement(measurementMap);

  useMapInteractionEffects({
    mapRef,
    mapReady,
    measurementMode: measurementState.mode,
    setSelectedFeatures,
    onParcelaResolved: setFichaParcela,
  });

  // Ficha territorial fetch — owned by the container, threaded to MapUiPanels as
  // props so `InfoPanel` never fetches (design §6). Idle when no parcel selected.
  const ficha = useFichaTerritorial(
    fichaParcela ? { tipo: 'parcela', nomenclatura: fichaParcela.nomenclatura } : null
  );

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
  const handleSliderMouseDown = useComparisonSlider({
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

  // "N capas activas" indicator (Phase 1). Phase 2.4 refines this to only
  // count top-level families; for now it reflects all visible vector flags.
  const activeLayerCount = Object.values(vectorVisibility).filter(Boolean).length;

  return (
    <Box className={styles.mapWorkspace} data-testid="map-workspace">
      <Box
        className={styles.mapTopBar}
        aria-label="Selector de capa base y vista satelital"
        data-testid="map-top-bar"
      >
        <MapBaseSelectorPanel
          baseLayer={baseLayer}
          onBaseLayerChange={setBaseLayer}
          viewModePanel={
            baseLayer === 'satellite' ? (
              <ViewModePanel
                viewMode={viewMode}
                onViewModeChange={setViewMode}
                hasSingleImage={hasSingleImage}
                hasComparison={hasComparison}
                singleImageInfo={singleImageInfo}
                comparisonInfo={comparisonInfo}
              />
            ) : null
          }
        />
      </Box>

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
                onSliderMouseDown={handleSliderMouseDown}
              />
            </div>

            {/* Measurement tools: floating toolbar + HTML label overlay. */}
            <MeasurementToolbar
              mode={measurementState.mode}
              hasMeasurements={measurementState.measurements.length > 0}
              onStartDistance={startMeasureDistance}
              onStartArea={startMeasureArea}
              onClear={clearMeasurements}
            />
            <MeasurementLabels map={measurementMap} measurements={measurementState.measurements} />
            <MeasurementShapes map={measurementMap} measurements={measurementState.measurements} />

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
              layerFineControl={layerFineControl}
              hasApprovedZones={hasApprovedZones}
              onOpenExportPng={() => setExportPngModalOpen(true)}
              onExportApprovedZonesPdf={handleExportApprovedZonesPdf}
              onExportKmz={handleExportKmz}
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
              fichaActive={fichaParcela !== null}
              fichaTipo="parcela"
              fichaNroCuenta={fichaParcela?.nroCuenta ?? null}
              fichaLoading={ficha.isLoading}
              fichaError={ficha.error}
              fichaData={ficha.data}
              onCloseFicha={() => setFichaParcela(null)}
              bpaEnriched={pilarVerde?.bpaEnriched}
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
              showEmbeddedMapControls={false}
              showEmbeddedRasterLegend={false}
            />
          </Box>
        }
        controls={
          <Stack gap="sm" data-testid="map-controls-tree">
            <LayerControlsPanel
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
              layerFineControl={layerFineControl}
            />
            {showLegend && (
              <>
                <LeyendaPanel
                  consorcios={vectorVisibility.roads && !!roadsCollection ? consorcios : []}
                  customItems={activeLegendItems}
                  embedded
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
