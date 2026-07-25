import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Feature } from 'geojson';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { ExportPngModal } from '../../src/components/map2d/ExportPngModal';
import { InfoPanel } from '../../src/components/map2d/InfoPanel';
import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';
import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';
import { MapActionsPanel } from '../../src/components/map2d/MapActionsPanel';
import { MapUiPanels } from '../../src/components/map2d/MapUiPanels';
import { MapViewportOverlay } from '../../src/components/map2d/MapViewportOverlay';
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

  it('renders layer controls and action controls and forwards their callbacks', async () => {
    const user = userEvent.setup();
    const onBaseLayerChange = vi.fn();
    const onLayerVisibilityChange = vi.fn();
    const onShowIGNOverlayChange = vi.fn();
    const onShowDemOverlayChange = vi.fn();
    const onOpenExportPng = vi.fn();

    renderWithMantine(
      <>
        <LayerControlsPanel
          baseLayer="osm"
          onBaseLayerChange={onBaseLayerChange}
          viewModePanel={<div>view-mode-slot</div>}
          layerItems={[{ id: 'roads', label: 'Red vial', category: 'territorio' }]}
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
          hasApprovedZones
          onOpenExportPng={onOpenExportPng}
          onExportApprovedZonesPdf={() => {}}
        />
      </>
    );

    expect(screen.getByText('view-mode-slot')).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: /satélite/i }));
    expect(onBaseLayerChange).toHaveBeenCalledWith('satellite');

    await user.click(screen.getByLabelText(/red vial/i));
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('roads', true);

    await user.click(screen.getByLabelText(/ign altimetría/i));
    expect(onShowIGNOverlayChange).toHaveBeenCalledWith(true);

    await user.click(screen.getByRole('checkbox', { name: /^capa dem$/i }));
    expect(onShowDemOverlayChange).toHaveBeenCalledWith(false);

    await user.click(screen.getByRole('button', { name: /exportar/i }));
    fireEvent.click(screen.getByText(/exportar png/i).closest('button') as HTMLButtonElement);
    expect(onOpenExportPng).toHaveBeenCalledTimes(1);
  });

  it('renders modals and viewport overlay interactions', async () => {
    const user = userEvent.setup();
    const onTitleChange = vi.fn();
    const onIncludeLegendChange = vi.fn();
    const onIncludeMetadataChange = vi.fn();
    const onExport = vi.fn();
    const onSliderMouseDown = vi.fn();

    renderWithMantine(
      <>
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

    fireEvent.mouseDown(screen.getByRole('separator', { name: /divisor de comparación/i }));
    expect(onSliderMouseDown).toHaveBeenCalledTimes(1);
  });

  it('composes the extracted panels through MapUiPanels', async () => {
    const user = userEvent.setup();
    const onBaseLayerChange = vi.fn();
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
        layerItems={[{ id: 'waterways', label: 'Hidrografía', category: 'hidrografia' }]}
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
        hasApprovedZones={false}
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
        selectedFeatures={[feature]}
        onCloseInfoPanel={onCloseInfoPanel}
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
    expect(screen.getByRole('heading', { name: /informacion/i })).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: /satélite/i }));
    expect(onBaseLayerChange).toHaveBeenCalledWith('satellite');

    await user.click(screen.getByRole('button', { name: /cerrar panel de informacion/i }));
    expect(onCloseInfoPanel).toHaveBeenCalledTimes(1);
  });
});
