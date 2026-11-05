import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { CanalesLayerSection } from '../../src/components/shared/CanalesLayerSection';
import { ElevationProfileDock } from '../../src/components/map2d/ElevationProfileDock';
import {
  LayerControlsPanel,
  type LayerFineControl,
} from '../../src/components/map2d/LayerControlsPanel';
import { LayerOpacityControl } from '../../src/components/map2d/layerControlWidgets';
import { ICON_BUTTON_CLASS } from '../../src/components/ui/IconButton';

vi.mock('../../src/components/map2d/ElevationProfileChart', () => ({
  ElevationProfileChart: () => <div data-testid="elevation-profile-chart-stub" />,
}));

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function makeFineControl(): LayerFineControl {
  return {
    opacityByLayer: { soil: 0.4 },
    onLayerOpacityChange: vi.fn(),
    orderByLayer: [],
    onLayerOrderChange: vi.fn(),
    labelSizeScale: 1.2,
    onLabelSizeScaleChange: vi.fn(),
    lineWidthScale: 1.4,
    onLineWidthScaleChange: vi.fn(),
  };
}

describe('controles que faltaban en el piso táctil', () => {
  it('los restablecer de opacidad, etiquetas y grosor usan IconButton', () => {
    const fineControl = makeFineControl();
    renderWithMantine(
      <>
        <LayerOpacityControl
          layerId="soil"
          label="Suelos"
          multiplier={0.4}
          onChange={fineControl.onLayerOpacityChange}
        />
        <LayerControlsPanel
          baseLayer="osm"
          onBaseLayerChange={() => {}}
          layerItems={[{ id: 'soil', label: 'Suelos', category: 'territorio' }]}
          vectorVisibility={{ soil: true }}
          onLayerVisibilityChange={() => {}}
          showIGNOverlay={false}
          onShowIGNOverlayChange={() => {}}
          demEnabled={false}
          showDemOverlay={false}
          onShowDemOverlayChange={() => {}}
          activeDemLayerId={null}
          onActiveDemLayerIdChange={() => {}}
          demOptions={[]}
          layerFineControl={fineControl}
        />
      </>
    );

    expect(screen.getAllByTestId('layer-opacity-reset-soil')[0]).toHaveClass(ICON_BUTTON_CLASS);
    const ajustes = screen.getByRole('button', { name: /ajustes/i });
    if (ajustes.getAttribute('aria-expanded') === 'false') fireEvent.click(ajustes);
    expect(screen.getByTestId('map-label-size-reset')).toHaveClass(ICON_BUTTON_CLASS);
    expect(screen.getByTestId('map-line-width-reset')).toHaveClass(ICON_BUTTON_CLASS);
    fireEvent.click(screen.getByTestId('map-label-size-reset'));
    fireEvent.click(screen.getByTestId('map-line-width-reset'));
    expect(fineControl.onLabelSizeScaleChange).toHaveBeenCalledWith(1);
    expect(fineControl.onLineWidthScaleChange).toHaveBeenCalledWith(1);
  });

  it('el ojo del explorador de canales y las acciones del perfil usan IconButton', async () => {
    renderWithMantine(
      <>
        <CanalesLayerSection
          side="relevados"
          variant="explorer"
          entries={[{ kind: 'leaf', id: 'norte', label: 'Norte' }]}
          masterFlag="canales_relevados"
          masterOn
          vectorVisibility={{ norte: true }}
          onLayerVisibilityChange={vi.fn()}
        />
        <ElevationProfileDock
          geometry={{ type: 'LineString', coordinates: [[0, 0], [1, 1]] }}
          title="Perfil de elevación"
          onClose={vi.fn()}
        />
      </>
    );

    expect(await screen.findByTestId('elevation-profile-chart-stub')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ocultar Norte' })).toHaveClass(ICON_BUTTON_CLASS);
    expect(screen.getByRole('button', { name: 'Contraer perfil' })).toHaveClass(ICON_BUTTON_CLASS);
    expect(screen.getByRole('button', { name: 'Cerrar perfil' })).toHaveClass(ICON_BUTTON_CLASS);
  });
});
