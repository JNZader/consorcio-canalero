import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Feature } from 'geojson';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { AssetPointModal } from '../../src/components/map2d/AssetPointModal';
import { ExportPngModal } from '../../src/components/map2d/ExportPngModal';
import { InfoPanel } from '../../src/components/map2d/InfoPanel';
import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';
import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';
import { MapActionsPanel } from '../../src/components/map2d/MapActionsPanel';
import { MapUiPanels } from '../../src/components/map2d/MapUiPanels';
import { MapViewportOverlay } from '../../src/components/map2d/MapViewportOverlay';
import { SuggestedZonesPanel } from '../../src/components/map2d/SuggestedZonesPanel';
import { MAP_VIEW_MODE, ViewModePanel } from '../../src/components/map2d/ViewModePanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('map2d extracted panels', () => {
  it('renders legend, info and view-mode panels with their main interactions', async () => {
    const user = userEvent.setup();
    const onCloseInfo = vi.fn();
    const onViewModeChange = vi.fn();

    const feature: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
      properties: {
        nombre: 'Canal Este',
        estado: 'activo',
        __internal: 'hidden',
      },
    };

    renderWithMantine(
      <>
        <LeyendaPanel
          floating={false}
          customItems={[{ color: '#ff0000', label: 'Zona de prueba', type: 'border' }]}
          consorcios={[
            { codigo: 'C1', nombre: 'Consorcio Norte', color: '#123456', longitud_km: 12.4 },
          ]}
        />
        <InfoPanel feature={feature} onClose={onCloseInfo} />
        <ViewModePanel
          viewMode={MAP_VIEW_MODE.BASE}
          onViewModeChange={onViewModeChange}
          hasSingleImage
          hasComparison
          singleImageInfo={{ sensor: 'Sentinel-2', date: '2026-04-01' }}
          comparisonInfo={{ leftDate: '2026-03-01', rightDate: '2026-04-01' }}
        />
      </>
    );

    expect(screen.getByText('Leyenda')).toBeInTheDocument();
    expect(screen.getByText('Zona de prueba')).toBeInTheDocument();
    expect(screen.queryByText('__internal')).not.toBeInTheDocument();
    expect(screen.getByText('Canal Este')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /base/i })).toBeChecked();

    await user.click(screen.getByText(/Red Vial \(1 consorcios\)/i));
    expect(screen.getByText(/C1 \(12 km\)/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cerrar panel de informacion/i }));
    expect(onCloseInfo).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('radio', { name: /comparar/i }));
    expect(onViewModeChange).toHaveBeenCalledWith(MAP_VIEW_MODE.COMPARISON);
  });

  it('renders zoning, layer controls and action controls and forwards their callbacks', async () => {
    const user = userEvent.setup();
    const onApproveZones = vi.fn();
    const onRestoreVersion = vi.fn();
    const onBaseLayerChange = vi.fn();
    const onLayerVisibilityChange = vi.fn();
    const onShowIGNOverlayChange = vi.fn();
    const onShowDemOverlayChange = vi.fn();
    const onToggleMarkingMode = vi.fn();
    const onToggleSuggestedZonesPanel = vi.fn();
    const onOpenExportPng = vi.fn();

    renderWithMantine(
      <>
        <SuggestedZonesPanel
          zones={[{ id: 'zona-1', defaultName: 'Zona Norte', family: 'A', basinCount: 3, superficieHa: 120.4 }]}
          zoneNames={{ 'zona-1': 'Zona Operativa Norte' }}
          onZoneNameChange={() => {}}
          selectedBasinName="Subcuenca 7"
          selectedBasinZoneId="zona-1"
          destinationZoneId={null}
          onDestinationZoneChange={() => {}}
          onApplyBasinMove={() => {}}
          hasApprovedZones
          approvedAt="2026-04-09T14:00:00.000Z"
          approvedVersion={3}
          approvedZonesHistory={[
            { id: 'v3', nombre: 'Actual', version: 3, approvedAt: '2026-04-09T14:00:00.000Z' },
            { id: 'v2', nombre: 'Anterior', version: 2, approvedAt: '2026-04-01T14:00:00.000Z' },
          ]}
          approvalName="Actual"
          approvalNotes=""
          onApprovalNameChange={() => {}}
          onApprovalNotesChange={() => {}}
          onClose={() => {}}
          onApproveZones={onApproveZones}
          onClearApprovedZones={() => {}}
          onRestoreVersion={onRestoreVersion}
          onExportApprovedZonesGeoJSON={() => {}}
          onExportApprovedZonesPdf={() => {}}
        />
        <LayerControlsPanel
          baseLayer="osm"
          onBaseLayerChange={onBaseLayerChange}
          viewModePanel={<div>view-mode-slot</div>}
          layerItems={[{ id: 'roads', label: 'Red vial' }]}
          vectorVisibility={{ roads: false }}
          onLayerVisibilityChange={onLayerVisibilityChange}
          showIGNOverlay={false}
          onShowIGNOverlayChange={onShowIGNOverlayChange}
          demEnabled
          showDemOverlay
          onShowDemOverlayChange={onShowDemOverlayChange}
          activeDemLayerId="dem-1"
          onActiveDemLayerIdChange={() => {}}
          demOptions={[{ value: 'dem-1', label: 'Pendiente' }]}
        />
        <MapActionsPanel
          isOperator
          markingMode={false}
          onToggleMarkingMode={onToggleMarkingMode}
          canManageZoning
          showSuggestedZonesPanel={false}
          hasApprovedZones
          onToggleSuggestedZonesPanel={onToggleSuggestedZonesPanel}
          onOpenExportPng={onOpenExportPng}
          onExportApprovedZonesPdf={() => {}}
        />
      </>
    );

    expect(screen.getByText(/zonificación aprobada/i)).toBeInTheDocument();
    expect(screen.getByText('view-mode-slot')).toBeInTheDocument();
    expect(document.getElementById('map-suggested-zones-panel')).toHaveAttribute(
      'aria-label',
      'Panel de zonificación'
    );
    expect(screen.getByRole('button', { name: /marcar punto/i })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    expect(screen.getByRole('button', { name: /ver zonificación/i })).toHaveAttribute(
      'aria-controls',
      'map-suggested-zones-panel'
    );
    expect(screen.getByRole('button', { name: /ver zonificación/i })).toHaveAttribute(
      'aria-expanded',
      'false'
    );

    await user.click(screen.getByRole('button', { name: /aprobar esta zonificación/i }));
    expect(onApproveZones).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /restaurar/i }));
    expect(onRestoreVersion).toHaveBeenCalledWith('v2');

    await user.click(screen.getByRole('radio', { name: /satélite/i }));
    expect(onBaseLayerChange).toHaveBeenCalledWith('satellite');

    await user.click(screen.getByLabelText(/red vial/i));
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('roads', true);

    await user.click(screen.getByLabelText(/ign altimetría/i));
    expect(onShowIGNOverlayChange).toHaveBeenCalledWith(true);

    await user.click(screen.getByRole('checkbox', { name: /^capa dem$/i }));
    expect(onShowDemOverlayChange).toHaveBeenCalledWith(false);

    await user.click(screen.getByRole('button', { name: /marcar punto/i }));
    expect(onToggleMarkingMode).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /ver zonificación/i }));
    expect(onToggleSuggestedZonesPanel).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /exportar/i }));
    fireEvent.click(screen.getByText(/exportar png/i).closest('button') as HTMLButtonElement);
    expect(onOpenExportPng).toHaveBeenCalledTimes(1);
  });

  it('renders modals and viewport overlay interactions', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn((event?: Event) => event?.preventDefault());
    const onTitleChange = vi.fn();
    const onIncludeLegendChange = vi.fn();
    const onIncludeMetadataChange = vi.fn();
    const onExport = vi.fn();
    const onSliderMouseDown = vi.fn();

    renderWithMantine(
      <>
        <AssetPointModal
          opened
          coordinates={{ lat: -32.62543, lng: -62.68421 }}
          onClose={() => {}}
          onSubmit={onSubmit}
          isSubmitting={false}
          nameInputProps={{ value: 'Puente norte', onChange: () => {} }}
          typeInputProps={{ value: 'puente', onChange: () => {} }}
          descriptionInputProps={{ value: 'Descripción inicial', onChange: () => {} }}
        />
        <ExportPngModal
          opened
          title="Mapa operativo"
          includeLegend
          includeMetadata={false}
          onClose={() => {}}
          onTitleChange={onTitleChange}
          onIncludeLegendChange={onIncludeLegendChange}
          onIncludeMetadataChange={onIncludeMetadataChange}
          onExport={onExport}
        />
        <MapViewportOverlay
          viewMode="comparison"
          sliderPosition={37}
          mapReady={false}
          onSliderMouseDown={onSliderMouseDown}
        />
      </>
    );

    expect(screen.getByText(/coordenadas: -32.62543, -62.68421/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue('Mapa operativo')).toBeInTheDocument();
    expect(screen.getByText(/cargando mapa/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/título del mapa/i), ' 2026');
    expect(onTitleChange).toHaveBeenCalled();

    await user.click(screen.getByLabelText(/incluir leyenda/i));
    expect(onIncludeLegendChange).toHaveBeenCalledWith(false);

    await user.click(screen.getByLabelText(/incluir metadatos/i));
    expect(onIncludeMetadataChange).toHaveBeenCalledWith(true);

    await user.click(screen.getByRole('button', { name: /descargar png/i }));
    expect(onExport).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /guardar punto/i }));
    expect(onSubmit).toHaveBeenCalled();

    fireEvent.mouseDown(screen.getByRole('separator', { name: /divisor de comparación/i }));
    expect(onSliderMouseDown).toHaveBeenCalledTimes(1);
  });

  it('connects asset point name validation error to the field', () => {
    renderWithMantine(
      <AssetPointModal
        opened
        coordinates={{ lat: -32.62543, lng: -62.68421 }}
        onClose={() => {}}
        onSubmit={(event) => event?.preventDefault()}
        isSubmitting={false}
        nameInputProps={{ value: '', onChange: () => {}, error: 'Nombre demasiado corto' }}
        typeInputProps={{ value: 'puente', onChange: () => {} }}
        descriptionInputProps={{ value: '', onChange: () => {} }}
      />
    );

    const nameInput = screen.getByRole('textbox', { name: /nombre/i });

    expect(nameInput.closest('form')).toHaveAttribute('novalidate');
    expect(nameInput).toHaveAttribute('aria-invalid', 'true');
    expect(nameInput.getAttribute('aria-describedby')).toContain('asset-point-name-error');
    expect(screen.getByText(/nombre demasiado corto/i)).toHaveAttribute('role', 'alert');
  });

  it('composes the extracted panels through MapUiPanels', async () => {
    const user = userEvent.setup();
    const onBaseLayerChange = vi.fn();
    const onToggleMarkingMode = vi.fn();
    const onCloseSuggestedZonesPanel = vi.fn();
    const onCloseInfoPanel = vi.fn();

    const feature: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
      properties: { nombre: 'Activo 1' },
    };

    renderWithMantine(
      <MapUiPanels
        baseLayer="osm"
        onBaseLayerChange={onBaseLayerChange}
        viewMode={MAP_VIEW_MODE.BASE}
        onViewModeChange={() => {}}
        hasSingleImage={false}
        hasComparison={false}
        singleImageInfo={null}
        comparisonInfo={null}
        layerItems={[{ id: 'waterways', label: 'Hidrografía' }]}
        vectorVisibility={{ waterways: true, roads: true }}
        onLayerVisibilityChange={() => {}}
        showIGNOverlay={false}
        onShowIGNOverlayChange={() => {}}
        demEnabled={false}
        showDemOverlay={false}
        onShowDemOverlayChange={() => {}}
        activeDemLayerId={null}
        onActiveDemLayerIdChange={() => {}}
        demOptions={[]}
        isOperator
        markingMode={false}
        onToggleMarkingMode={onToggleMarkingMode}
        canManageZoning
        showSuggestedZonesPanel
        hasApprovedZones={false}
        onToggleSuggestedZonesPanel={() => {}}
        onOpenExportPng={() => {}}
        onExportApprovedZonesPdf={() => {}}
        showLegend
        consorcios={[{ codigo: 'C1', nombre: 'Consorcio Norte', color: '#123456', longitud_km: 10 }]}
        activeLegendItems={[{ color: '#ff0000', label: 'Zona', type: 'border' }]}
        visibleRasterLayers={[]}
        hiddenClasses={{}}
        hiddenRanges={{}}
        onClassToggle={() => {}}
        onRangeToggle={() => {}}
        suggestedZoneSummaries={[{ id: 'z1', defaultName: 'Zona 1', basinCount: 2, superficieHa: 80 }]}
        suggestedZoneNames={{ z1: 'Zona Operativa 1' }}
        onZoneNameChange={() => {}}
        selectedDraftBasinName="Subcuenca A"
        selectedDraftBasinZoneId="z1"
        draftDestinationZoneId={null}
        onDestinationZoneChange={() => {}}
        onApplyBasinMove={() => {}}
        approvedAt={null}
        approvedVersion={null}
        approvedZonesHistory={[]}
        approvalName="Versión 1"
        approvalNotes=""
        onApprovalNameChange={() => {}}
        onApprovalNotesChange={() => {}}
        onCloseSuggestedZonesPanel={onCloseSuggestedZonesPanel}
        onApproveZones={() => {}}
        onClearApprovedZones={() => {}}
        onRestoreVersion={() => {}}
        onExportApprovedZonesGeoJSON={() => {}}
        selectedFeatures={[feature]}
        onCloseInfoPanel={onCloseInfoPanel}
        newPoint={null}
        onCloseAssetPointModal={() => {}}
        onSubmitAssetPointModal={() => {}}
        isSubmitting={false}
        nameInputProps={{}}
        typeInputProps={{}}
        descriptionInputProps={{}}
        exportPngModalOpen={false}
        onCloseExportPngModal={() => {}}
        exportTitle="Mapa"
        exportIncludeLegend
        exportIncludeMetadata
        onExportTitleChange={() => {}}
        onExportIncludeLegendChange={() => {}}
        onExportIncludeMetadataChange={() => {}}
        onExportPng={() => {}}
      />
    );

    expect(screen.getByText(/capa base/i)).toBeInTheDocument();
    expect(screen.getByText('Leyenda')).toBeInTheDocument();
    expect(screen.getByText(/zonas sugeridas/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /informacion/i })).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: /satélite/i }));
    expect(onBaseLayerChange).toHaveBeenCalledWith('satellite');

    await user.click(screen.getByRole('button', { name: /marcar punto/i }));
    expect(onToggleMarkingMode).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /cerrar panel de zonificación/i }));
    expect(onCloseSuggestedZonesPanel).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /cerrar panel de informacion/i }));
    expect(onCloseInfoPanel).toHaveBeenCalledTimes(1);
  });
});
