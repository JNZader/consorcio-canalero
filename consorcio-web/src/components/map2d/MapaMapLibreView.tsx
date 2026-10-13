/**
 * Vista del mapa 2D. Recibe el estado ya armado por `MapaMapLibre` y no cambia
 * el comportamiento: los controles, el lienzo y los paneles se renderizan igual.
 */
import { Alert, Box, Stack, Text } from '@mantine/core';
import type { QueryObserverResult, RefetchOptions } from '@tanstack/react-query';
import type { Feature, FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';
import type * as maplibregl from 'maplibre-gl';
import type { PointerEvent as ReactPointerEvent, RefObject, SetStateAction } from 'react';
import { lazy, Suspense } from 'react';
import { MAP_BOUNDS, MAP_HOME_FIT_PADDING, MAP_QUICK_PLACES } from '../../constants';
import type { ConsorcioInfo } from '../../hooks/useCaminosColoreados';
import type { UseFichaOverlayResult } from '../../hooks/useFichaOverlay';
import type { UseFichaTerritorialResult } from '../../hooks/useFichaTerritorial';
import type { GeoLayerInfo } from '../../hooks/useGeoLayers';
import type { HazardPrecipMonth, HazardRiskClass } from '../../hooks/useHazardUrlState';
import { FICHA_MAX_BUFFER_M } from '../../lib/api/ficha';
import { erroresUi } from '../../lib/userFacingError';
import styles from '../../styles/components/map.module.css';
import type { Etapa } from '../../types/canales';
import type { PilarVerdeData } from '../../types/pilarVerde';
import type { DrawControlHandle } from '../map/DrawControl';
import { RasterLegend } from '../RasterLegend';
import {
  type CanalToggleEntry,
  collectCanalChildIds,
  type EtapaGate,
} from '../shared/canalesGrouping';
import { VisuallyHidden } from '../ui/accessibility/primitives';
import { HazardMapControls } from './HazardMapControls';
import type { HazardBasinOption } from './hazardControls.types';
import type { HazardLegendView } from './hazardLegend';
import { LayerControlsPanel } from './LayerControlsPanel';
import type { LayerHealth } from './layerHealth';
import { MapBaseSelectorPanel } from './MapBaseSelectorPanel';
import { MapCursorReadout } from './MapCursorReadout';
import { MapPlacesControl } from './MapPlacesControl';
import { MapUiPanels } from './MapUiPanels';
import { MapViewportOverlay } from './MapViewportOverlay';
import { MapWorkspace, useMapWorkspaceDesktop } from './MapWorkspace';
import type { ActiveLegendItem } from './map2dDerived';
import { buildFamilyActiveCounts, sumFamilyActiveCounts } from './map2dDerived';
import { requestMapGeolocate } from './mapGeolocate';
import { MeasurementLabels } from './measurement/MeasurementLabels';
import { MeasurementShapes } from './measurement/MeasurementShapes';
import { MeasurementToolbar } from './measurement/MeasurementToolbar';
import type { MeasurementState } from './measurement/useMeasurement';
import { PuntoInteresPlaceModal } from './PuntoInteresPlaceModal';
import type { PrecipitationRange } from './precipRanges';
import type { ProfileRangeStats } from './profileRange';
import type { AnalysisToolProps } from './useAnalysisToolsGate';
import type { UseFichaInteractionResult } from './useFichaInteraction';
import type { FichaOverlayTabsState } from './useFichaOverlayTabs';
import type { PuntosInteresWiring } from './usePuntosInteresWiring';
import type { QuickPlacePin } from './useQuickPlaceMarker';
import type { RoadFlowWiring } from './useRoadFlowWiring';
import type { ViewMode } from './ViewModePanel';
import { ViewModePanel } from './ViewModePanel';

const DrawControl = lazy(() => import('../map/DrawControl'));

function toggleHazardRiskClass(
  riskClasses: readonly HazardRiskClass[],
  riskClass: HazardRiskClass,
  visible: boolean
): HazardRiskClass[] {
  return visible
    ? [...new Set([...riskClasses, riskClass])]
    : riskClasses.filter((currentRiskClass) => currentRiskClass !== riskClass);
}

export interface MapaMapLibreViewProps {
  readonly activeDemLayerId: string | null;
  readonly activeLegendItems: ActiveLegendItem[];
  readonly analysisToolProps: AnalysisToolProps;
  readonly baseLayer: 'osm' | 'satellite';
  readonly bpaJoinError: string | null;
  readonly bpaJoinLoading: boolean;
  readonly canalesPropuestosItems: CanalToggleEntry[];
  readonly canalesRelevadosItems: CanalToggleEntry[];
  readonly cancelMeasurement: () => void;
  readonly clearMeasurements: () => void;
  readonly comparisonActive: boolean;
  readonly comparisonContainerRef: RefObject<HTMLDivElement | null>;
  readonly comparisonInfo: { leftDate: string; rightDate: string } | null;
  readonly consorcios: ConsorcioInfo[];
  readonly containerRef: RefObject<HTMLDivElement | null>;
  readonly demLayerOptions: { value: string; tipo: string; label: string }[];
  readonly demLayers: { id: string; tipo: string; nombre: string }[];
  readonly drawControlRef: RefObject<DrawControlHandle | null>;
  readonly etapaGate: EtapaGate;
  readonly exportIncludeLegend: boolean;
  readonly exportIncludeMetadata: boolean;
  readonly exportPngModalOpen: boolean;
  readonly exportTitle: string;
  readonly ficha: UseFichaTerritorialResult;
  readonly fichaInteraction: UseFichaInteractionResult;
  readonly fichaKey: string;
  readonly fichaOverlay: UseFichaOverlayResult;
  readonly fichaTabs: FichaOverlayTabsState;
  readonly flyToCanal: (toggleId: string) => void;
  readonly geoLayersError: string | null;
  readonly handleCloseInfoPanel: () => void;
  readonly handleExportApprovedZonesPdf: () => Promise<void>;
  readonly handleExportIntent: () => void;
  readonly handleExportKmz: () => Promise<void>;
  readonly handleExportPng: () => Promise<void>;
  readonly handleSliderPointerDown: (event: ReactPointerEvent) => void;
  readonly handleStartMeasureArea: () => void;
  readonly handleStartMeasureDistance: () => void;
  readonly hasApprovedZones: boolean;
  readonly hasComparison: boolean;
  readonly hasSingleImage: boolean;
  readonly hazard: {
    gateOpen: boolean;
    isHazardActive: boolean;
    url: {
      setHazard: (hazard: boolean) => void;
      setBasin: (basin: string | null) => void;
      setRiskClasses: (riskClasses: readonly HazardRiskClass[]) => void;
      setPrecipMonth: (precipMonth: HazardPrecipMonth) => void;
      resetToDefaults: () => void;
      hazard: boolean;
      basin: string | null;
      riskClasses: HazardRiskClass[];
      precipMonth: HazardPrecipMonth;
    };
    panelOpen: boolean;
    setPanelOpen: (open: boolean) => void;
    mobileExpanded: boolean;
    setMobileExpanded: (expanded: boolean) => void;
    pendingBasinZoom: boolean;
    precipitationRange: PrecipitationRange | null;
    showPrecipitation: boolean;
    visibleRasterLayers: { tipo: string }[];
  };
  readonly hazardBasins: HazardBasinOption[];
  readonly hazardLegend: HazardLegendView | null;
  readonly hiddenClasses: { [x: string]: number[] };
  readonly hiddenRanges: { [x: string]: number[] };
  readonly hillshadeTileUrl: string | null;
  readonly isFichaCanal: boolean;
  readonly isFichaDrawSession: boolean;
  readonly layerFineControl: {
    opacityByLayer: Record<string, number>;
    onLayerOpacityChange: (layerId: string, multiplier: number) => void;
    orderByLayer: string[];
    onLayerOrderChange: (orderedIds: string[]) => void;
    labelSizeScale: number;
    onLabelSizeScaleChange: (scale: number) => void;
    lineWidthScale: number;
    onLineWidthScaleChange: (scale: number) => void;
  };
  readonly layerHealth: LayerHealth;
  readonly layerProvenance: {
    canales?: string | undefined;
    base?: string | undefined;
    hidrografia?: string | undefined;
    territorio?: string | undefined;
    pilar_verde?: string | undefined;
    analisis?: string | undefined;
  };
  readonly mapDragSignal: number;
  readonly mapLoadError: string | null;
  readonly mapReady: boolean;
  readonly mapRef: RefObject<maplibregl.Map | null>;
  readonly measurementLiveLabel: string | null;
  readonly measurementMap: maplibregl.Map | null;
  readonly measurementState: MeasurementState;
  readonly pilarVerde: PilarVerdeData | null;
  readonly pilarVerdeLayersError: string | null;
  readonly pilarVerdeLayersLoading: boolean;
  readonly propuestasEtapasVisibility: {
    Alta: boolean;
    'Media-Alta': boolean;
    Media: boolean;
    Opcional: boolean;
    'Largo plazo': boolean;
  };
  readonly puntosInteres: PuntosInteresWiring;
  readonly rasterCompareActive: boolean;
  readonly rasterCompareId: string | null;
  readonly rasterLoading: boolean;
  readonly reloadGeoLayers: (
    options?: RefetchOptions
  ) => Promise<QueryObserverResult<GeoLayerInfo[], Error>>;
  readonly roadFlow: RoadFlowWiring;
  readonly roadsCollection: FeatureCollection<Geometry, GeoJsonProperties> | null | undefined;
  readonly satelliteLayer: { label: string } | null;
  readonly selectedFeatures: Feature<Geometry, GeoJsonProperties>[];
  readonly setActiveDemLayerId: (value: SetStateAction<string | null>) => void;
  readonly setBaseLayer: (value: SetStateAction<'osm' | 'satellite'>) => void;
  readonly setElevationProfileHover: (
    value: SetStateAction<{ lon: number; lat: number } | null>
  ) => void;
  readonly setElevationProfileRange: (value: SetStateAction<ProfileRangeStats | null>) => void;
  readonly setEtapaVisible: (etapa: Etapa, visible: boolean) => void;
  readonly setExportIncludeLegend: (value: SetStateAction<boolean>) => void;
  readonly setExportIncludeMetadata: (value: SetStateAction<boolean>) => void;
  readonly setExportPngModalOpen: (value: SetStateAction<boolean>) => void;
  readonly setExportTitle: (value: SetStateAction<string>) => void;
  readonly setHiddenClasses: (value: SetStateAction<Record<string, number[]>>) => void;
  readonly setHiddenRanges: (value: SetStateAction<Record<string, number[]>>) => void;
  readonly setQuickPlace: (value: SetStateAction<QuickPlacePin | null>) => void;
  readonly setRasterCompareId: (value: SetStateAction<string | null>) => void;
  readonly setSelectedFeatures: (
    value: SetStateAction<Feature<Geometry, GeoJsonProperties>[]>
  ) => void;
  readonly setShowDemOverlay: (value: SetStateAction<boolean>) => void;
  readonly setShowHillshade: (value: SetStateAction<boolean>) => void;
  readonly setShowIGNOverlay: (value: SetStateAction<boolean>) => void;
  readonly setViewMode: (value: SetStateAction<ViewMode>) => void;
  readonly showDemOverlay: boolean;
  readonly showHillshade: boolean;
  readonly showIGNOverlay: boolean;
  readonly showLegend: true;
  readonly singleImageInfo: { sensor: string; date: string } | null;
  readonly sliderContainerRef: RefObject<HTMLDivElement | null>;
  readonly sliderPosition: number;
  readonly toggleLayer: (layerId: string, visible: boolean) => void;
  readonly vectorLayerItems: {
    id: string;
    label: string;
    category: 'canales' | 'hidrografia' | 'territorio' | 'pilar_verde' | 'analisis';
  }[];
  readonly vectorVisibility: { [x: string]: boolean };
  readonly viewMode: 'comparison' | 'base' | 'single';
  readonly visibleRasterLayers: { tipo: string }[];
  readonly waterwaysError: string | null;
}

export function MapaMapLibreView(props: MapaMapLibreViewProps) {
  const {
    activeDemLayerId,
    activeLegendItems,
    analysisToolProps,
    baseLayer,
    bpaJoinError,
    bpaJoinLoading,
    canalesPropuestosItems,
    canalesRelevadosItems,
    cancelMeasurement,
    clearMeasurements,
    comparisonActive,
    comparisonContainerRef,
    comparisonInfo,
    consorcios,
    containerRef,
    demLayerOptions,
    demLayers,
    drawControlRef,
    etapaGate,
    exportIncludeLegend,
    exportIncludeMetadata,
    exportPngModalOpen,
    exportTitle,
    ficha,
    fichaInteraction,
    fichaKey,
    fichaOverlay,
    fichaTabs,
    flyToCanal,
    geoLayersError,
    handleCloseInfoPanel,
    handleExportApprovedZonesPdf,
    handleExportIntent,
    handleExportKmz,
    handleExportPng,
    handleSliderPointerDown,
    handleStartMeasureArea,
    handleStartMeasureDistance,
    hasApprovedZones,
    hasComparison,
    hasSingleImage,
    hazard,
    hazardBasins,
    hazardLegend,
    hiddenClasses,
    hiddenRanges,
    hillshadeTileUrl,
    isFichaCanal,
    isFichaDrawSession,
    layerFineControl,
    layerHealth,
    layerProvenance,
    mapDragSignal,
    mapLoadError,
    mapReady,
    mapRef,
    measurementLiveLabel,
    measurementMap,
    measurementState,
    pilarVerde,
    pilarVerdeLayersError,
    pilarVerdeLayersLoading,
    propuestasEtapasVisibility,
    puntosInteres,
    rasterCompareActive,
    rasterCompareId,
    rasterLoading,
    reloadGeoLayers,
    roadFlow,
    roadsCollection,
    satelliteLayer,
    selectedFeatures,
    setActiveDemLayerId,
    setBaseLayer,
    setElevationProfileHover,
    setElevationProfileRange,
    setEtapaVisible,
    setExportIncludeLegend,
    setExportIncludeMetadata,
    setExportPngModalOpen,
    setExportTitle,
    setHiddenClasses,
    setHiddenRanges,
    setQuickPlace,
    setRasterCompareId,
    setSelectedFeatures,
    setShowDemOverlay,
    setShowHillshade,
    setShowIGNOverlay,
    setViewMode,
    showDemOverlay,
    showHillshade,
    showIGNOverlay,
    showLegend,
    singleImageInfo,
    sliderContainerRef,
    sliderPosition,
    toggleLayer,
    vectorLayerItems,
    vectorVisibility,
    viewMode,
    visibleRasterLayers,
    waterwaysError,
  } = props;

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
  const activeLayerCount =
    sumFamilyActiveCounts(
      buildFamilyActiveCounts({
        layerItems: vectorLayerItems,
        vectorVisibility,
        canalChildIds,
        showIGNOverlay,
        showHillshade,
        showDemOverlay,
        showSatellite: Boolean(satelliteLayer),
      })
    ) + hazard.visibleRasterLayers.length;

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
          hasComparison={hasComparison || rasterCompareActive}
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
        liveMessage={waterwaysError ?? geoLayersError ?? undefined}
        canvas={
          <Box
            className={styles.mapCanvasWrapper}
            role="application"
            aria-label="mapa interactivo del consorcio para explorar cuencas, canales e infraestructura"
            aria-describedby="mapa-instrucciones-lector"
          >
            <VisuallyHidden id="mapa-instrucciones-lector">
              Mapa del consorcio. Con el tabulador llegás a los controles de zoom y de capas. Cuando
              el lienzo tiene el foco, las flechas mueven el mapa. Escape cierra el panel abierto.
            </VisuallyHidden>
            {/* Map container */}
            <div
              ref={sliderContainerRef}
              style={{ width: '100%', height: '100%', position: 'relative' }}
            >
              <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
              {mapLoadError ? (
                <Box
                  style={{
                    position: 'absolute',
                    inset: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: 16,
                    zIndex: 20,
                  }}
                >
                  <Stack gap="sm" maw={560}>
                    <Alert color="red" title={erroresUi.cargarMapa.titulo} variant="light">
                      <Text size="sm">{mapLoadError}</Text>
                    </Alert>
                    <Box
                      component="section"
                      role="region"
                      aria-label="descripción textual del mapa"
                    >
                      <Text size="sm">
                        El mapa interactivo permite explorar cuencas, canales e infraestructura del
                        Consorcio.
                      </Text>
                    </Box>
                  </Stack>
                </Box>
              ) : null}
              {comparisonActive && (
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
              mode={puntosInteres.interactionMode}
              hasMeasurements={measurementState.measurements.length > 0}
              liveLabel={measurementLiveLabel}
              onStartDistance={handleStartMeasureDistance}
              onStartArea={handleStartMeasureArea}
              onClear={clearMeasurements}
              onCancel={cancelMeasurement}
              fichaDrawActive={isFichaDrawSession}
              fichaCanalActive={isFichaCanal}
              fichaMultiSelectActive={fichaInteraction.state.multiSelect}
              poiPlaceActive={puntosInteres.placing}
              onTogglePoiPlace={puntosInteres.onTogglePoiPlace}
              /* Draw / canal / multi-select callbacks are login-gated: absent for
               anonymous visitors, so those buttons are not rendered at all. */
              {...analysisToolProps}
            />
            <PuntoInteresPlaceModal
              opened={puntosInteres.modalOpen}
              saving={puntosInteres.saving}
              error={puntosInteres.saveError}
              onClose={puntosInteres.closeModal}
              onSave={puntosInteres.saveDraft}
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
              <Suspense fallback={null}>
                <DrawControl
                  ref={drawControlRef}
                  map={measurementMap}
                  onPolygonCreated={fichaInteraction.completePolygon}
                  onPolygonDeleted={fichaInteraction.deletePolygon}
                />
              </Suspense>
            )}

            <MapUiPanels
              baseLayer={baseLayer}
              onBaseLayerChange={setBaseLayer}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
              hasSingleImage={hasSingleImage}
              hasComparison={hasComparison || rasterCompareActive}
              singleImageInfo={singleImageInfo}
              comparisonInfo={comparisonInfo}
              layerItems={vectorLayerItems}
              vectorVisibility={vectorVisibility}
              onLayerVisibilityChange={toggleLayer}
              showIGNOverlay={showIGNOverlay}
              onShowIGNOverlayChange={setShowIGNOverlay}
              showHillshade={showHillshade}
              onShowHillshadeChange={setShowHillshade}
              hillshadeAvailable={!!hillshadeTileUrl}
              demEnabled={demLayers.length > 0}
              showDemOverlay={showDemOverlay}
              onShowDemOverlayChange={setShowDemOverlay}
              activeDemLayerId={activeDemLayerId}
              onActiveDemLayerIdChange={setActiveDemLayerId}
              demOptions={demLayerOptions}
              satelliteLayer={satelliteLayer}
              onHideSatellite={() => setViewMode('base')}
              rasterLoading={rasterLoading}
              demLoadError={geoLayersError}
              onRetryDem={() => {
                void reloadGeoLayers();
              }}
              onFocusCanal={flyToCanal}
              rasterCompareId={rasterCompareId}
              onRasterCompare={setRasterCompareId}
              canalesRelevadosItems={canalesRelevadosItems}
              canalesPropuestosItems={canalesPropuestosItems}
              etapaGate={etapaGate}
              layerFineControl={layerFineControl}
              hasApprovedZones={hasApprovedZones}
              onOpenExportPng={() => setExportPngModalOpen(true)}
              onExportApprovedZonesPdf={handleExportApprovedZonesPdf}
              onExportKmz={handleExportKmz}
              onExportMenuOpen={handleExportIntent}
              cursorReadout={<MapCursorReadout map={mapRef.current} mapReady={mapReady} />}
              placesControl={
                <MapPlacesControl
                  onRecenter={() => {
                    setQuickPlace(null);
                    mapRef.current?.fitBounds(
                      [
                        [MAP_BOUNDS.west, MAP_BOUNDS.south],
                        [MAP_BOUNDS.east, MAP_BOUNDS.north],
                      ],
                      { padding: MAP_HOME_FIT_PADDING, duration: 800 }
                    );
                  }}
                  onFlyToPlace={(placeId) => {
                    const place = MAP_QUICK_PLACES.find((item) => item.id === placeId);
                    if (!place) return;
                    setQuickPlace({
                      label: place.label,
                      lng: place.center[0],
                      lat: place.center[1],
                    });
                    mapRef.current?.flyTo({
                      center: place.center,
                      zoom: place.zoom,
                      duration: 800,
                    });
                  }}
                  onGeolocate={() => {
                    requestMapGeolocate(mapRef.current);
                  }}
                />
              }
              showLegend={showLegend}
              consorcios={vectorVisibility.roads && roadsCollection ? consorcios : []}
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
              onCloseInfoPanel={handleCloseInfoPanel}
              onElevationProfileHover={setElevationProfileHover}
              onElevationProfileRange={setElevationProfileRange}
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
              onDeletePuntoInteres={async (id) => {
                try {
                  await puntosInteres.deletePunto(id);
                } finally {
                  setSelectedFeatures((current) =>
                    current.filter((feature) => {
                      const featureId = feature.id == null ? '' : String(feature.id);
                      const propertyId =
                        feature.properties && 'id' in feature.properties
                          ? String(feature.properties.id)
                          : '';
                      return featureId !== id && propertyId !== id;
                    })
                  );
                }
              }}
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
              roadFlowActive={roadFlow.roadFlowActive}
              roadFlowCrossings={roadFlow.crossings}
              roadFlowCobertura={roadFlow.cobertura}
              roadFlowKinds={roadFlow.kinds}
              onRoadFlowKindsChange={roadFlow.setKinds}
              onSelectRoadFlowCrossing={roadFlow.onSelectCrossing}
              onSurveyTramo={roadFlow.onSurveyTramo}
              onCloseRoadFlow={roadFlow.onClose}
              tramoSurveyRef={roadFlow.tramoRef}
              tramoSurveyDetalle={roadFlow.tramoDetalle}
              tramoSurveyLoading={roadFlow.tramoLoading}
              tramoSurveyError={roadFlow.tramoError}
              onRetryTramoSurvey={roadFlow.onRetryTramoSurvey}
              onSubmitTramoSurvey={roadFlow.onSubmitTramoSurvey}
              onCloseTramoSurvey={roadFlow.onCloseTramoSurvey}
            />
            <HazardMapControls
              active={hazard.isHazardActive}
              desktop={isDesktop}
              desktopCollapsed={!hazard.panelOpen}
              mobileCollapsed={!hazard.mobileExpanded}
              onDesktopCollapsedChange={(collapsed) => hazard.setPanelOpen(!collapsed)}
              onMobileCollapsedChange={(collapsed) => hazard.setMobileExpanded(!collapsed)}
              controls={{
                basins: hazardBasins,
                selectedBasinId: hazard.url.basin,
                onBasinChange: hazard.url.setBasin,
                visibleRiskClasses: hazard.url.riskClasses,
                onRiskClassChange: (riskClass, visible) =>
                  hazard.url.setRiskClasses(
                    toggleHazardRiskClass(hazard.url.riskClasses, riskClass, visible)
                  ),
                precipitationPeriod: hazard.url.precipMonth,
                onPrecipitationPeriodChange: hazard.url.setPrecipMonth,
                onReset: hazard.url.resetToDefaults,
                fichaOpen: fichaInteraction.request !== null,
              }}
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
              showHillshade={showHillshade}
              onShowHillshadeChange={setShowHillshade}
              hillshadeAvailable={!!hillshadeTileUrl}
              demEnabled={demLayers.length > 0}
              showDemOverlay={showDemOverlay}
              onShowDemOverlayChange={setShowDemOverlay}
              activeDemLayerId={activeDemLayerId}
              onActiveDemLayerIdChange={setActiveDemLayerId}
              demOptions={demLayerOptions}
              satelliteLayer={satelliteLayer}
              onHideSatellite={() => setViewMode('base')}
              rasterLoading={rasterLoading}
              demLoadError={geoLayersError}
              onRetryDem={() => {
                void reloadGeoLayers();
              }}
              onFocusCanal={flyToCanal}
              rasterCompareId={rasterCompareId}
              onRasterCompare={setRasterCompareId}
              canalesRelevadosItems={canalesRelevadosItems}
              canalesPropuestosItems={canalesPropuestosItems}
              etapaGate={etapaGate}
              layerFineControl={layerFineControl}
              hazardLayerControl={{
                active: hazard.isHazardActive,
                activeLayerCount: hazard.visibleRasterLayers.length,
                onActiveChange: hazard.url.setHazard,
                visible: hazard.gateOpen,
              }}
              pilarVerdeLayersLoading={pilarVerdeLayersLoading}
              pilarVerdeLayersError={pilarVerdeLayersError}
              layerHealth={layerHealth}
              layerProvenance={layerProvenance}
              legendPanelProps={
                showLegend
                  ? {
                      consorcios: vectorVisibility.roads && roadsCollection ? consorcios : [],
                      customItems: activeLegendItems,
                      pilarVerdeBpaHistoricoVisible: !!vectorVisibility.pilar_verde_bpa_historico,
                      pilarVerdeAgroAceptadaVisible: !!vectorVisibility.pilar_verde_agro_aceptada,
                      pilarVerdeAgroPresentadaVisible:
                        !!vectorVisibility.pilar_verde_agro_presentada,
                      pilarVerdeAgroZonasVisible: !!vectorVisibility.pilar_verde_agro_zonas,
                      pilarVerdePorcentajeForestacionVisible:
                        !!vectorVisibility.pilar_verde_porcentaje_forestacion,
                      pilarAzulCanalesRelevadosVisible: !!vectorVisibility.canales_relevados,
                      pilarAzulCanalesPropuestosVisible: !!vectorVisibility.canales_propuestos,
                      pilarAzulEscuelasVisible: !!vectorVisibility.escuelas,
                      hazardPrecipitationRange: hazard.precipitationRange,
                      hazardLegend,
                      propuestasEtapasVisibility,
                      onSetEtapaVisible: setEtapaVisible,
                    }
                  : undefined
              }
            />
            {showLegend && (
              <>
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
