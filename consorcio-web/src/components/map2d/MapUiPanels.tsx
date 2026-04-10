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
  readonly selectedFeature: Feature | null;
  readonly onCloseInfoPanel: () => void;
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
  selectedFeature,
  onCloseInfoPanel,
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
            <ViewModePanel
              viewMode={viewMode}
              onViewModeChange={onViewModeChange}
              hasSingleImage={hasSingleImage}
              hasComparison={hasComparison}
              singleImageInfo={singleImageInfo}
              comparisonInfo={comparisonInfo}
            />
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
      >
        {showLegend && (
          <LeyendaPanel consorcios={consorcios} customItems={activeLegendItems} floating={false} />
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
      </MapActionsPanel>

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

      {selectedFeature && <InfoPanel feature={selectedFeature} onClose={onCloseInfoPanel} />}

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
