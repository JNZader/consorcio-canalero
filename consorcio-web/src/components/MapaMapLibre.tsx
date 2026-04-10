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

import { Box } from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import type { Feature, FeatureCollection } from 'geojson';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Protocol } from 'pmtiles';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

// Register PMTiles protocol once at module level
const _pmtilesProtocol = new Protocol();
maplibregl.addProtocol('pmtiles', _pmtilesProtocol.tile.bind(_pmtilesProtocol));
import { useApprovedZones } from '../hooks/useApprovedZones';
import { useBasins } from '../hooks/useBasins';
import { useCaminosColoreados } from '../hooks/useCaminosColoreados';
import { useCatastroMap } from '../hooks/useCatastroMap';
import { GEE_LAYER_COLORS, useGEELayers } from '../hooks/useGEELayers';
import { useGeoLayers } from '../hooks/useGeoLayers';
import { useImageComparisonListener } from '../hooks/useImageComparison';
import { useInfrastructure } from '../hooks/useInfrastructure';
import { getMartinTileUrl, MARTIN_SOURCES, useZonaRiskColors } from '../hooks/useMartinLayers';
import { usePublicLayers } from '../hooks/usePublicLayers';
import { useSelectedImageListener } from '../hooks/useSelectedImage';
import { useSoilMap } from '../hooks/useSoilMap';
import { useSuggestedZones } from '../hooks/useSuggestedZones';
import { WATERWAY_DEFS, useWaterways } from '../hooks/useWaterways';
import { formatDate } from '../lib/formatters';
import { useCanAccess } from '../stores/authStore';
import { useConfigStore } from '../stores/configStore';
import { useMapLayerSyncStore } from '../stores/mapLayerSyncStore';
import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../constants';
import styles from '../styles/components/map.module.css';
import DrawControl, { type DrawControlHandle, type DrawnPolygon } from './map/DrawControl';
import LineDrawControl, { type DrawnLineFeatureCollection } from './map/LineDrawControl';
import { LAYER_LEGEND_CONFIG } from '../config/rasterLegend';
import { MapUiPanels } from './map2d/MapUiPanels';
import { MapViewportOverlay } from './map2d/MapViewportOverlay';
import { GEE_LAYER_NAMES, SOURCE_IDS, buildWaterwayLayerConfigs } from './map2d/map2dConfig';
import {
  IGN_IMAGE_URL,
  IGN_MAPLIBRE_COORDS,
  leafletCenterToMapLibre,
} from './map2d/map2dUtils';
import {
  useAssetCreationHandler,
  useMapExportHandlers,
  useZoningHandlers,
} from './map2d/useMapActionHandlers';
import { useComparisonSlider } from './map2d/useComparisonSlider';
import { useMapInteractionEffects } from './map2d/useMapInteractionEffects';
import { useMapInitialization } from './map2d/useMapInitialization';
import { useMapLayerEffects } from './map2d/useMapLayerEffects';
import { useMapDerivedState } from './map2d/useMapDerivedState';
import { type ViewMode } from './map2d/ViewModePanel';

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
  const isOperator = useCanAccess(['admin', 'operador']);
  const canManageZoning = useCanAccess(['admin', 'operador']);
  const _mapInstanceId = useId();

  const center = useMemo<[number, number]>(
    () =>
      config?.map.center
        ? leafletCenterToMapLibre([config.map.center.lat, config.map.center.lng])
        : leafletCenterToMapLibre(MAP_CENTER),
    [config?.map.center?.lat, config?.map.center?.lng],
  );
  const zoom = useMemo(() => config?.map.zoom ?? DEFAULT_ZOOM, [config?.map.zoom]);

  // ── Map refs ──────────────────────────────────────────────────────────────
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);

  // Comparison slider
  const sliderContainerRef = useRef<HTMLDivElement>(null);
  const [sliderPosition, setSliderPosition] = useState(50);
  const isDraggingSlider = useRef(false);

  // Draw control refs
  const drawControlRef = useRef<DrawControlHandle | null>(null);

  // ── UI state ──────────────────────────────────────────────────────────────
  const [selectedFeature, setSelectedFeature] = useState<Feature | null>(null);
  const [baseLayer, setBaseLayer] = useState<'osm' | 'satellite'>('osm');
  const [viewMode, setViewMode] = useState<ViewMode>('base');
  const [showLegend, setShowLegend] = useState(true);
  const [showSuggestedZonesPanel, setShowSuggestedZonesPanel] = useState(false);
  const [showIGNOverlay, setShowIGNOverlay] = useState(false);
  const [showDemOverlay, setShowDemOverlay] = useState(false);
  const [activeDemLayerId, setActiveDemLayerId] = useState<string | null>(null);
  const [markingMode, setMarkingMode] = useState(false);
  const [newPoint, setNewPoint] = useState<{ lat: number; lng: number } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [captureMode, setCaptureMode] = useState(false);
  const [exportPngModalOpen, setExportPngModalOpen] = useState(false);
  const [exportIncludeLegend, setExportIncludeLegend] = useState(true);
  const [exportIncludeMetadata, setExportIncludeMetadata] = useState(true);
  const [exportTitle, setExportTitle] = useState('Mapa del Consorcio');
  const [approvalName, setApprovalName] = useState('Zonificación Consorcio aprobada');
  const [approvalNotes, setApprovalNotes] = useState('');
  const [suggestedZoneNames, setSuggestedZoneNames] = useState<Record<string, string>>({});
  const [draftBasinAssignments, setDraftBasinAssignments] = useState<Record<string, string>>({});
  const [selectedDraftBasinId, setSelectedDraftBasinId] = useState<string | null>(null);
  const [draftDestinationZoneId, setDraftDestinationZoneId] = useState<string | null>(null);
  const [drawnPolygon, setDrawnPolygon] = useState<DrawnPolygon | null>(null);
  const [drawnLine, setDrawnLine] = useState<DrawnLineFeatureCollection | null>(null);
  const [hiddenClasses, setHiddenClasses] = useState<Record<string, number[]>>({});
  const [hiddenRanges, setHiddenRanges] = useState<Record<string, number[]>>({});
  const [visibleRasterLayers, setVisibleRasterLayers] = useState<Array<{ tipo: string }>>([]);

  const form = useForm({
    initialValues: { nombre: '', tipo: 'alcantarilla', descripcion: '', cuenca: '' },
    validate: { nombre: (value) => (value.length < 3 ? 'Nombre demasiado corto' : null) },
  });

  // ── Layer sync store ──────────────────────────────────────────────────────
  const sharedVisibleVectors = useMapLayerSyncStore((state) => state.map2d.visibleVectors);
  const setSharedVectorVisibility = useMapLayerSyncStore((state) => state.setVectorVisibility);
  const setSharedActiveRasterType = useMapLayerSyncStore((state) => state.setActiveRasterType);
  const is2DViewInitialized = useMapLayerSyncStore((state) => state.initializedViews.map2d);
  const hydrateSharedViewState = useMapLayerSyncStore((state) => state.hydrateViewState);

  // Local visibility state (mirrors sharedVisibleVectors, drives setLayoutProperty)
  const [vectorVisibility, setVectorVisibility] = useState<Record<string, boolean>>(
    () => sharedVisibleVectors,
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
    [setSharedVectorVisibility],
  );

  // ── Data hooks ────────────────────────────────────────────────────────────
  const { layers: capas } = useGEELayers({ layerNames: [...GEE_LAYER_NAMES] });
  const { caminos, consorcios } = useCaminosColoreados();
  const { assets, intersections, createAsset } = useInfrastructure();
  const { layers: publicLayers } = usePublicLayers();
  const { soilMap } = useSoilMap();
  const { catastroMap } = useCatastroMap();
  const { basins } = useBasins();
  const { suggestedZones } = useSuggestedZones();
  const { waterways } = useWaterways();
  const { layers: allGeoLayers } = useGeoLayers();
  const { data: zonaRiskColors = {} } = useZonaRiskColors();
  const {
    approvedZones,
    approvedAt,
    approvedVersion,
    hasApprovedZones,
    approvedZonesHistory,
    saveApprovedZones,
    clearApprovedZones,
    restoreApprovedZonesVersion,
  } = useApprovedZones();

  const selectedImage = useSelectedImageListener();
  const comparison = useImageComparisonListener();

  const {
    zonaCollection,
    roadsCollection,
    waterwaysCollection,
    soilCollection,
    infrastructureCollection,
    approvedZonesCollection,
    suggestedZonesDisplay,
    demTileUrl,
    demLayers,
    effectiveBasinAssignments,
    suggestedZoneSummaries,
    selectedDraftBasinName,
    selectedDraftBasinZoneId,
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
    assets,
    publicLayers,
    soilMap,
    basins,
    suggestedZones,
    waterways,
    allGeoLayers,
    approvedZones,
    draftBasinAssignments,
    suggestedZoneNames,
    hiddenClasses,
    hiddenRanges,
    activeDemLayerId,
    selectedDraftBasinId,
    selectedImage,
    comparison,
    vectorVisibility,
    hasApprovedZones,
    intersectionsLength: intersections?.features?.length ?? 0,
  });

  // Auto-activate comparison when comparison state changes
  useEffect(() => {
    if (comparison?.enabled && comparison.left && comparison.right) {
      setViewMode('comparison');
    }
  }, [comparison]);

  // Auto-activate single image view when image loads
  useEffect(() => {
    if (selectedImage && viewMode === 'base') {
      setViewMode('single');
    }
  }, [selectedImage]);

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
    suggestedZonesDisplay,
    showSuggestedZonesPanel,
    hasApprovedZones,
    infrastructureCollection,
    publicLayers,
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
  });

  useMapInitialization({
    maplibre: maplibregl,
    containerRef,
    center,
    zoom,
    mapRef,
    setMapReady,
  });

  useMapInteractionEffects({
    mapRef,
    mapReady,
    markingMode,
    setNewPoint,
    setSelectedFeature,
    showSuggestedZonesPanel,
    setSelectedDraftBasinId,
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

  const {
    handleExportPng,
    handleExportApprovedZonesPdf,
    handleExportApprovedZonesGeoJSON,
  } = useMapExportHandlers({
    mapRef,
    exportTitle,
    setExportPngModalOpen,
    approvedZones,
  });

  /* ---------------------------------------------------------------------- */
  /*  Infrastructure asset creation                                          */
  /* ---------------------------------------------------------------------- */
  const handleSaveAsset = useAssetCreationHandler<typeof form.values>({
    newPoint,
    createAsset,
    setIsSubmitting,
    setNewPoint,
    setMarkingMode,
    resetForm: form.reset,
  });

  const { handleApproveZones, handleClearApprovedZones, handleApplyBasinMove } = useZoningHandlers({
    suggestedZonesDisplay,
    effectiveBasinAssignments,
    suggestedZoneNames,
    approvalName,
    approvalNotes,
    saveApprovedZones,
    clearApprovedZones,
    selectedDraftBasinId,
    draftDestinationZoneId,
    setDraftBasinAssignments,
    setSelectedDraftBasinId,
    setDraftDestinationZoneId,
  });

  /* ---------------------------------------------------------------------- */
  /*  Render                                                                 */
  /* ---------------------------------------------------------------------- */

  return (
    <Box className={styles.mapWrapper} style={{ position: 'relative', height: '100%' }}>
      {/* Map container */}
      <div ref={sliderContainerRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
        <MapViewportOverlay
          viewMode={viewMode}
          sliderPosition={sliderPosition}
          mapReady={mapReady}
          onSliderMouseDown={handleSliderMouseDown}
        />
      </div>

      {/* Draw controls (attached to map after load) */}
      {mapReady && mapRef.current && isOperator && (
        <>
          <DrawControl
            ref={drawControlRef}
            map={mapRef.current}
            onPolygonCreated={setDrawnPolygon}
            onPolygonDeleted={() => setDrawnPolygon(null)}
            showControls={isOperator}
          />
          <LineDrawControl
            map={mapRef.current}
            value={drawnLine}
            onChange={setDrawnLine}
          />
        </>
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
        isOperator={isOperator}
        markingMode={markingMode}
        onToggleMarkingMode={() => {
          setMarkingMode(!markingMode);
          setNewPoint(null);
        }}
        canManageZoning={canManageZoning}
        showSuggestedZonesPanel={showSuggestedZonesPanel}
        hasApprovedZones={hasApprovedZones}
        onToggleSuggestedZonesPanel={() => setShowSuggestedZonesPanel((prev) => !prev)}
        onOpenExportPng={() => setExportPngModalOpen(true)}
        onExportApprovedZonesPdf={handleExportApprovedZonesPdf}
        showLegend={showLegend}
        consorcios={vectorVisibility.roads && !!roadsCollection ? consorcios : []}
        activeLegendItems={activeLegendItems}
        visibleRasterLayers={visibleRasterLayers}
        hiddenClasses={hiddenClasses}
        hiddenRanges={hiddenRanges}
        onClassToggle={(layerType, classIndex, visible) =>
          setHiddenClasses((prev) => {
            const curr = prev[layerType] ?? [];
            const next = visible ? curr.filter((i) => i !== classIndex) : [...curr, classIndex];
            return { ...prev, [layerType]: next };
          })
        }
        onRangeToggle={(layerType, rangeIndex, visible) =>
          setHiddenRanges((prev) => {
            const curr = prev[layerType] ?? [];
            const next = visible ? curr.filter((i) => i !== rangeIndex) : [...curr, rangeIndex];
            return { ...prev, [layerType]: next };
          })
        }
        suggestedZoneSummaries={suggestedZoneSummaries}
        suggestedZoneNames={suggestedZoneNames}
        onZoneNameChange={(id, value) => setSuggestedZoneNames((prev) => ({ ...prev, [id]: value }))}
        selectedDraftBasinName={selectedDraftBasinName}
        selectedDraftBasinZoneId={selectedDraftBasinZoneId}
        draftDestinationZoneId={draftDestinationZoneId}
        onDestinationZoneChange={setDraftDestinationZoneId}
        onApplyBasinMove={handleApplyBasinMove}
        approvedAt={approvedAt}
        approvedVersion={approvedVersion}
        approvedZonesHistory={approvedZonesHistory}
        approvalName={approvalName}
        approvalNotes={approvalNotes}
        onApprovalNameChange={setApprovalName}
        onApprovalNotesChange={setApprovalNotes}
        onCloseSuggestedZonesPanel={() => setShowSuggestedZonesPanel(false)}
        onApproveZones={handleApproveZones}
        onClearApprovedZones={handleClearApprovedZones}
        onRestoreVersion={async (id) => {
          try {
            await restoreApprovedZonesVersion(id);
            notifications.show({ title: 'Versión restaurada', message: 'Zonificación restaurada', color: 'green' });
          } catch (_err) {
            notifications.show({ title: 'Error', message: 'No se pudo restaurar', color: 'red' });
          }
        }}
        onExportApprovedZonesGeoJSON={handleExportApprovedZonesGeoJSON}
        selectedFeature={selectedFeature}
        onCloseInfoPanel={() => setSelectedFeature(null)}
        newPoint={newPoint}
        onCloseAssetPointModal={() => {
          setNewPoint(null);
          form.reset();
          setMarkingMode(false);
        }}
        onSubmitAssetPointModal={form.onSubmit(handleSaveAsset)}
        isSubmitting={isSubmitting}
        nameInputProps={form.getInputProps('nombre')}
        typeInputProps={form.getInputProps('tipo')}
        descriptionInputProps={form.getInputProps('descripcion')}
        exportPngModalOpen={exportPngModalOpen}
        onCloseExportPngModal={() => setExportPngModalOpen(false)}
        exportTitle={exportTitle}
        exportIncludeLegend={exportIncludeLegend}
        exportIncludeMetadata={exportIncludeMetadata}
        onExportTitleChange={setExportTitle}
        onExportIncludeLegendChange={setExportIncludeLegend}
        onExportIncludeMetadataChange={setExportIncludeMetadata}
        onExportPng={handleExportPng}
      />
    </Box>
  );
}
