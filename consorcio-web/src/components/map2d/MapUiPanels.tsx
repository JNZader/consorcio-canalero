import { Box } from '@mantine/core';
import type { Feature } from 'geojson';
import { type FormEvent, memo } from 'react';
import { AssetPointModal } from './AssetPointModal';
import { ExportPngModal } from './ExportPngModal';
import { InfoPanel } from './InfoPanel';
import { LayerControlsPanel } from './LayerControlsPanel';
import { MapActionsPanel } from './MapActionsPanel';
import { SuggestedZonesPanel } from './SuggestedZonesPanel';
import { ViewModePanel, type ViewMode } from './ViewModePanel';
import { LeyendaPanel } from './LeyendaPanel';
import { RasterLegend } from '../RasterLegend';
import type { ConsorcioInfo } from '../../hooks/useCaminosColoreados';
import type { BpaEnrichedFile, BpaHistoryFile } from '../../types/pilarVerde';

interface LayerItem {
  id: string;
  label: string;
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

interface SuggestedZoneSummary {
  id: string;
  defaultName: string;
  family?: string | null;
  basinCount: number;
  superficieHa: number;
}

interface ApprovedZoneHistoryItem {
  id: string;
  nombre: string;
  version: number;
  approvedAt: string;
  notes?: string | null;
  approvedByName?: string | null;
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
  readonly isOperator: boolean;
  readonly markingMode: boolean;
  readonly onToggleMarkingMode: () => void;
  readonly canManageZoning: boolean;
  readonly showSuggestedZonesPanel: boolean;
  readonly hasApprovedZones: boolean;
  readonly onToggleSuggestedZonesPanel: () => void;
  readonly onOpenExportPng: () => void;
  readonly onExportApprovedZonesPdf: () => void;
  readonly showLegend: boolean;
  readonly consorcios: ConsorcioInfo[];
  readonly activeLegendItems: LegendItem[];
  readonly visibleRasterLayers: Array<{ tipo: string }>;
  readonly hiddenClasses: Record<string, number[]>;
  readonly hiddenRanges: Record<string, number[]>;
  readonly onClassToggle: (layerType: string, classIndex: number, visible: boolean) => void;
  readonly onRangeToggle: (layerType: string, rangeIndex: number, visible: boolean) => void;
  readonly suggestedZoneSummaries: SuggestedZoneSummary[];
  readonly suggestedZoneNames: Record<string, string>;
  readonly onZoneNameChange: (id: string, value: string) => void;
  readonly selectedDraftBasinName: string | null;
  readonly selectedDraftBasinZoneId: string | null;
  readonly draftDestinationZoneId: string | null;
  readonly onDestinationZoneChange: (value: string | null) => void;
  readonly onApplyBasinMove: () => void;
  readonly approvedAt: string | null;
  readonly approvedVersion: number | null;
  readonly approvedZonesHistory: ApprovedZoneHistoryItem[];
  readonly approvalName: string;
  readonly approvalNotes: string;
  readonly onApprovalNameChange: (value: string) => void;
  readonly onApprovalNotesChange: (value: string) => void;
  readonly onCloseSuggestedZonesPanel: () => void;
  readonly onApproveZones: () => void;
  readonly onClearApprovedZones: () => void;
  readonly onRestoreVersion: (id: string) => void;
  readonly onExportApprovedZonesGeoJSON: () => void;
  /**
   * Phase 8 — array of all features returned by MapLibre at the click
   * point. InfoPanel renders one stacked section per feature in order
   * (top-most first).
   */
  readonly selectedFeatures: readonly Feature[];
  readonly onCloseInfoPanel: () => void;
  /**
   * Optional Pilar Verde enriched catastro data — when present, InfoPanel
   * will render `<BpaCard>` for any feature whose `nro_cuenta` matches a
   * parcel with a non-null `bpa_2025` record.
   */
  readonly bpaEnriched?: BpaEnrichedFile | null;
  /** Optional Pilar Verde historical BPA lookup — powers the BpaCard histórico footer. */
  readonly bpaHistory?: BpaHistoryFile | null;
  readonly newPoint: { lat: number; lng: number } | null;
  readonly onCloseAssetPointModal: () => void;
  readonly onSubmitAssetPointModal: (event?: FormEvent<HTMLFormElement>) => void;
  readonly isSubmitting: boolean;
  readonly nameInputProps: object;
  readonly typeInputProps: object;
  readonly descriptionInputProps: object;
  readonly exportPngModalOpen: boolean;
  readonly onCloseExportPngModal: () => void;
  readonly exportTitle: string;
  readonly exportIncludeLegend: boolean;
  readonly exportIncludeMetadata: boolean;
  readonly onExportTitleChange: (value: string) => void;
  readonly onExportIncludeLegendChange: (value: boolean) => void;
  readonly onExportIncludeMetadataChange: (value: boolean) => void;
  readonly onExportPng: () => void;
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
  isOperator,
  markingMode,
  onToggleMarkingMode,
  canManageZoning,
  showSuggestedZonesPanel,
  hasApprovedZones,
  onToggleSuggestedZonesPanel,
  onOpenExportPng,
  onExportApprovedZonesPdf,
  showLegend,
  consorcios,
  activeLegendItems,
  visibleRasterLayers,
  hiddenClasses,
  hiddenRanges,
  onClassToggle,
  onRangeToggle,
  suggestedZoneSummaries,
  suggestedZoneNames,
  onZoneNameChange,
  selectedDraftBasinName,
  selectedDraftBasinZoneId,
  draftDestinationZoneId,
  onDestinationZoneChange,
  onApplyBasinMove,
  approvedAt,
  approvedVersion,
  approvedZonesHistory,
  approvalName,
  approvalNotes,
  onApprovalNameChange,
  onApprovalNotesChange,
  onCloseSuggestedZonesPanel,
  onApproveZones,
  onClearApprovedZones,
  onRestoreVersion,
  onExportApprovedZonesGeoJSON,
  selectedFeatures,
  onCloseInfoPanel,
  bpaEnriched,
  bpaHistory,
  newPoint,
  onCloseAssetPointModal,
  onSubmitAssetPointModal,
  isSubmitting,
  nameInputProps,
  typeInputProps,
  descriptionInputProps,
  exportPngModalOpen,
  onCloseExportPngModal,
  exportTitle,
  exportIncludeLegend,
  exportIncludeMetadata,
  onExportTitleChange,
  onExportIncludeLegendChange,
  onExportIncludeMetadataChange,
  onExportPng,
}: MapUiPanelsProps) {
  return (
    <>
      <Box
        style={{
          position: 'absolute',
          top: 12,
          left: 12,
          zIndex: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
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
        />
      </Box>

      <MapActionsPanel
        isOperator={isOperator}
        markingMode={markingMode}
        onToggleMarkingMode={onToggleMarkingMode}
        canManageZoning={canManageZoning}
        showSuggestedZonesPanel={showSuggestedZonesPanel}
        hasApprovedZones={hasApprovedZones}
        onToggleSuggestedZonesPanel={onToggleSuggestedZonesPanel}
        onOpenExportPng={onOpenExportPng}
        onExportApprovedZonesPdf={onExportApprovedZonesPdf}
      />

      {/*
        Phase 8 Fix 3/4 — decouple legends from the top-right action bar so
        they stop colliding with the InfoPanel (also top-right).
          · LeyendaPanel   → bottom-LEFT  (via `floating={true}`)
          · RasterLegend   → bottom-RIGHT (via its own `.rasterLegendPanel`)
          · InfoPanel      → top-RIGHT    (via `.infoPanel`)
        Each legend has its own bounded max-height + internal scroll so tall
        DEM / BPA gradients don't push the layout.
      */}
      {showLegend && (
        <LeyendaPanel
          consorcios={consorcios}
          customItems={activeLegendItems}
          floating
          pilarVerdeBpaHistoricoVisible={!!vectorVisibility.pilar_verde_bpa_historico}
          pilarVerdeAgroAceptadaVisible={!!vectorVisibility.pilar_verde_agro_aceptada}
          pilarVerdeAgroPresentadaVisible={!!vectorVisibility.pilar_verde_agro_presentada}
          pilarVerdeAgroZonasVisible={!!vectorVisibility.pilar_verde_agro_zonas}
          pilarVerdePorcentajeForestacionVisible={
            !!vectorVisibility.pilar_verde_porcentaje_forestacion
          }
        />
      )}

      {visibleRasterLayers.length > 0 && (
        <RasterLegend
          layers={visibleRasterLayers}
          hiddenClasses={hiddenClasses}
          hiddenRanges={hiddenRanges}
          onClassToggle={onClassToggle}
          onRangeToggle={onRangeToggle}
        />
      )}

      {showSuggestedZonesPanel && suggestedZoneSummaries.length > 0 && canManageZoning && (
        <SuggestedZonesPanel
          zones={suggestedZoneSummaries}
          zoneNames={suggestedZoneNames}
          onZoneNameChange={onZoneNameChange}
          selectedBasinName={selectedDraftBasinName}
          selectedBasinZoneId={selectedDraftBasinZoneId}
          destinationZoneId={draftDestinationZoneId}
          onDestinationZoneChange={onDestinationZoneChange}
          onApplyBasinMove={onApplyBasinMove}
          hasApprovedZones={hasApprovedZones}
          approvedAt={approvedAt}
          approvedVersion={approvedVersion}
          approvedZonesHistory={approvedZonesHistory}
          approvalName={approvalName}
          approvalNotes={approvalNotes}
          onApprovalNameChange={onApprovalNameChange}
          onApprovalNotesChange={onApprovalNotesChange}
          onClose={onCloseSuggestedZonesPanel}
          onApproveZones={onApproveZones}
          onClearApprovedZones={onClearApprovedZones}
          onRestoreVersion={onRestoreVersion}
          onExportApprovedZonesGeoJSON={onExportApprovedZonesGeoJSON}
          onExportApprovedZonesPdf={onExportApprovedZonesPdf}
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

      <AssetPointModal
        opened={!!newPoint}
        coordinates={newPoint}
        onClose={onCloseAssetPointModal}
        onSubmit={onSubmitAssetPointModal}
        isSubmitting={isSubmitting}
        nameInputProps={nameInputProps}
        typeInputProps={typeInputProps}
        descriptionInputProps={descriptionInputProps}
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
