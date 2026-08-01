import { Box } from '@mantine/core';
import type { Feature } from 'geojson';
import { memo } from 'react';
import type { ConsorcioInfo } from '../../hooks/useCaminosColoreados';
import type { BpaEnrichedFile, BpaHistoryFile } from '../../types/pilarVerde';
import type { FichaResponse, FichaTipo } from '../../lib/api/ficha';
import type { FichaApiError } from '../../lib/api/ficha';
import { RasterLegend } from '../RasterLegend';
import { ExportPngModal } from './ExportPngModal';
import { FichaTerritorialPanel } from './FichaTerritorialPanel';
import { InfoPanel } from './InfoPanel';
import {
  type CanalToggleEntry,
  LayerControlsPanel,
  type LayerFineControl,
} from './LayerControlsPanel';
import { LeyendaPanel } from './LeyendaPanel';
import { MapActionsPanel } from './MapActionsPanel';
import { type ViewMode, ViewModePanel } from './ViewModePanel';
import type { LayerCategory } from './map2dDerived';
import type { ParcelaDisplayProps } from './useMapInteractionEffects';

interface LayerItem {
  id: string;
  label: string;
  category: LayerCategory;
}

interface DemOption {
  value: string;
  label: string;
}

interface LegendItem {
  color: string;
  label: string;
  type: string;
}

export interface MapUiPanelsProps {
  readonly baseLayer: 'osm' | 'satellite';
  readonly onBaseLayerChange: (value: 'osm' | 'satellite') => void;
  readonly viewMode: ViewMode;
  readonly onViewModeChange: (mode: ViewMode) => void;
  readonly hasSingleImage: boolean;
  readonly hasComparison: boolean;
  readonly singleImageInfo?: { sensor: string; date: string } | null;
  readonly comparisonInfo?: { leftDate: string; rightDate: string } | null;
  readonly layerItems: LayerItem[];
  readonly vectorVisibility: Record<string, boolean>;
  readonly onLayerVisibilityChange: (layerId: string, visible: boolean) => void;
  readonly showIGNOverlay: boolean;
  readonly onShowIGNOverlayChange: (visible: boolean) => void;
  readonly demEnabled: boolean;
  readonly showDemOverlay: boolean;
  readonly onShowDemOverlayChange: (visible: boolean) => void;
  readonly activeDemLayerId: string | null;
  readonly onActiveDemLayerIdChange: (value: string | null) => void;
  readonly demOptions: DemOption[];
  readonly canalesRelevadosItems?: readonly CanalToggleEntry[];
  readonly canalesPropuestosItems?: readonly CanalToggleEntry[];
  /** Per-layer opacity + render-order controls (Fase 3 — Tanda B). */
  readonly layerFineControl?: LayerFineControl;
  readonly hasApprovedZones: boolean;
  readonly onOpenExportPng: () => void;
  readonly onExportApprovedZonesPdf: () => void;
  /**
   * Optional — KMZ export handler produced by
   * `useMapExportHandlers.handleExportKmz`. When provided, the
   * `MapActionsPanel` renders the "Exportar KMZ" entry inside the
   * existing Export dropdown.
   */
  readonly onExportKmz?: () => void;
  readonly showLegend: boolean;
  readonly consorcios: ConsorcioInfo[];
  readonly activeLegendItems: LegendItem[];
  readonly visibleRasterLayers: Array<{ tipo: string }>;
  readonly hiddenClasses: Record<string, number[]>;
  readonly hiddenRanges: Record<string, number[]>;
  readonly onClassToggle: (layerType: string, classIndex: number, visible: boolean) => void;
  readonly onRangeToggle: (layerType: string, rangeIndex: number, visible: boolean) => void;
  /**
   * Phase 8 — array of all features returned by MapLibre at the click
   * point. InfoPanel renders one stacked section per feature in order
   * (top-most first).
   */
  readonly selectedFeatures: readonly Feature[];
  readonly onCloseInfoPanel: () => void;
  /**
   * Ficha territorial (A4) — the container owns the fetch (`useFichaTerritorial`)
   * and threads its state down here; `InfoPanel` stays pure. When
   * `fichaActive` is false the sibling panel renders nothing.
   */
  readonly fichaActive: boolean;
  readonly fichaTipo: FichaTipo;
  readonly fichaNroCuenta: string | null;
  readonly fichaParcelaProps?: ParcelaDisplayProps | null;
  readonly fichaLoading: boolean;
  readonly fichaError: FichaApiError | Error | null;
  readonly fichaData: FichaResponse | undefined;
  readonly onCloseFicha: () => void;
  /**
   * Optional Pilar Verde enriched catastro data — when present, InfoPanel
   * will render `<BpaCard>` for any feature whose `nro_cuenta` matches a
   * parcel with a non-null `bpa_2025` record.
   */
  readonly bpaEnriched?: BpaEnrichedFile | null;
  /** Optional Pilar Verde historical BPA lookup — powers the BpaCard histórico footer. */
  readonly bpaHistory?: BpaHistoryFile | null;
  readonly exportPngModalOpen: boolean;
  readonly onCloseExportPngModal: () => void;
  readonly exportTitle: string;
  readonly exportIncludeLegend: boolean;
  readonly exportIncludeMetadata: boolean;
  readonly onExportTitleChange: (value: string) => void;
  readonly onExportIncludeLegendChange: (value: boolean) => void;
  readonly onExportIncludeMetadataChange: (value: boolean) => void;
  readonly onExportPng: () => void;
  /**
   * When false, the layer selector and static legend are rendered by the parent
   * outside the map canvas. Overlay-only mode keeps quick actions, info panels
   * and modals inside the map.
   */
  readonly showEmbeddedMapControls?: boolean;
  /**
   * When false, the raster legend is NOT rendered inside the map canvas. The
   * parent is expected to render `<RasterLegend floating={false} />` somewhere
   * outside the map (typically in a bottom bar next to `LeyendaPanel`).
   * Defaults to `true` to preserve the floating bottom-right behavior.
   */
  readonly showEmbeddedRasterLegend?: boolean;
}

export const MapUiPanels = memo(function MapUiPanels({
  baseLayer,
  onBaseLayerChange,
  viewMode,
  onViewModeChange,
  hasSingleImage,
  hasComparison,
  singleImageInfo,
  comparisonInfo,
  layerItems,
  vectorVisibility,
  onLayerVisibilityChange,
  showIGNOverlay,
  onShowIGNOverlayChange,
  demEnabled,
  showDemOverlay,
  onShowDemOverlayChange,
  activeDemLayerId,
  onActiveDemLayerIdChange,
  demOptions,
  canalesRelevadosItems,
  canalesPropuestosItems,
  layerFineControl,
  hasApprovedZones,
  onOpenExportPng,
  onExportApprovedZonesPdf,
  onExportKmz,
  showLegend,
  consorcios,
  activeLegendItems,
  visibleRasterLayers,
  hiddenClasses,
  hiddenRanges,
  onClassToggle,
  onRangeToggle,
  selectedFeatures,
  onCloseInfoPanel,
  fichaActive,
  fichaTipo,
  fichaNroCuenta,
  fichaParcelaProps,
  fichaLoading,
  fichaError,
  fichaData,
  onCloseFicha,
  bpaEnriched,
  bpaHistory,
  exportPngModalOpen,
  onCloseExportPngModal,
  exportTitle,
  exportIncludeLegend,
  exportIncludeMetadata,
  onExportTitleChange,
  onExportIncludeLegendChange,
  onExportIncludeMetadataChange,
  onExportPng,
  showEmbeddedMapControls = true,
  showEmbeddedRasterLegend = true,
}: MapUiPanelsProps) {
  return (
    <>
      {/*
        Side-by-side top-left stack (mirrors the 3D `TerrainLayerTogglesPanel`
        + `TerrainLegendsPanel` split):

          [LayerControlsPanel] [LeyendaPanel]

        Previously `LayerControlsPanel` lived at top-left and `LeyendaPanel`
        floated at bottom-left via the `.legendPanel` CSS class. When the
        layer list grew tall (many BPA toggles + DEM + attributions) the two
        panels visually collided. Bounding `LayerControlsPanel` with
        `maxHeight + overflow-y: auto` was not enough — the two panels still
        shared the same vertical column.

        The new layout owns positioning from this outer flex-row container
        (LeyendaPanel is rendered in `embedded` mode so its
        `.legendPanel` absolute-positioning class is NOT applied). Each
        panel keeps its own bounded `maxHeight` so neither overflows the
        viewport.

        RasterLegend (bottom-right) and InfoPanel (top-right) remain
        unchanged.
      */}
      {showEmbeddedMapControls && (
        <Box
          data-testid="map-2d-top-left-panels"
          style={{
            position: 'absolute',
            top: 12,
            left: 12,
            zIndex: 16,
            display: 'flex',
            flexDirection: 'row',
            alignItems: 'flex-start',
            gap: 8,
            maxHeight: 'calc(100vh - 180px)',
            overflowY: 'auto',
            overflowX: 'hidden',
          }}
        >
          <LayerControlsPanel
            baseLayer={baseLayer}
            onBaseLayerChange={onBaseLayerChange}
            viewModePanel={
              baseLayer === 'satellite' ? (
                <ViewModePanel
                  viewMode={viewMode}
                  onViewModeChange={onViewModeChange}
                  hasSingleImage={hasSingleImage}
                  hasComparison={hasComparison}
                  singleImageInfo={singleImageInfo}
                  comparisonInfo={comparisonInfo}
                />
              ) : null
            }
            layerItems={layerItems}
            vectorVisibility={vectorVisibility}
            onLayerVisibilityChange={onLayerVisibilityChange}
            showIGNOverlay={showIGNOverlay}
            onShowIGNOverlayChange={onShowIGNOverlayChange}
            demEnabled={demEnabled}
            showDemOverlay={showDemOverlay}
            onShowDemOverlayChange={onShowDemOverlayChange}
            activeDemLayerId={activeDemLayerId}
            onActiveDemLayerIdChange={onActiveDemLayerIdChange}
            demOptions={demOptions}
            canalesRelevadosItems={canalesRelevadosItems}
            canalesPropuestosItems={canalesPropuestosItems}
            layerFineControl={layerFineControl}
          />
          {showLegend && (
            <LeyendaPanel
              consorcios={consorcios}
              customItems={activeLegendItems}
              embedded
              width={260}
              data-testid="map-2d-leyenda-panel"
              style={{ maxHeight: 'calc(100vh - 180px)', overflowY: 'auto' }}
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
            />
          )}
        </Box>
      )}

      <MapActionsPanel
        hasApprovedZones={hasApprovedZones}
        onOpenExportPng={onOpenExportPng}
        onExportApprovedZonesPdf={onExportApprovedZonesPdf}
        onExportKmz={onExportKmz}
      />

      {showEmbeddedRasterLegend && visibleRasterLayers.length > 0 && (
        <RasterLegend
          layers={visibleRasterLayers}
          hiddenClasses={hiddenClasses}
          hiddenRanges={hiddenRanges}
          onClassToggle={onClassToggle}
          onRangeToggle={onRangeToggle}
        />
      )}

      {selectedFeatures.length > 0 && (
        <InfoPanel
          features={selectedFeatures}
          onClose={onCloseInfoPanel}
          bpaEnriched={bpaEnriched}
          bpaHistory={bpaHistory}
        />
      )}

      <FichaTerritorialPanel
        active={fichaActive}
        tipo={fichaTipo}
        nroCuenta={fichaNroCuenta}
        parcelaProps={fichaParcelaProps}
        bpaEnriched={bpaEnriched}
        isLoading={fichaLoading}
        isError={fichaError !== null}
        error={fichaError}
        data={fichaData}
        onClose={onCloseFicha}
      />

      <ExportPngModal
        opened={exportPngModalOpen}
        onClose={onCloseExportPngModal}
        title={exportTitle}
        includeLegend={exportIncludeLegend}
        includeMetadata={exportIncludeMetadata}
        onTitleChange={onExportTitleChange}
        onIncludeLegendChange={onExportIncludeLegendChange}
        onIncludeMetadataChange={onExportIncludeMetadataChange}
        onExport={onExportPng}
      />
    </>
  );
});
