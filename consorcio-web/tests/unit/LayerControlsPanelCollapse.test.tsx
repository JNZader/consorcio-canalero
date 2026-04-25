/**
 * LayerControlsPanelCollapse.test.tsx
 *
 * Collapsible "Capas" section inside `<LayerControlsPanel />`. The user can
 * click the section header (or press Enter/Space) to hide the body of the
 * Capas panel when it takes up too much screen space. State is local to the
 * panel (`useState`) and does NOT persist across unmounts.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const baseProps = {
  baseLayer: 'osm' as const,
  onBaseLayerChange: () => {},
  layerItems: [
    { id: 'catastro', label: 'Catastro' },
    { id: 'pilar_verde_bpa_2025', label: 'BPA 2025' },
  ],
  vectorVisibility: {},
  onLayerVisibilityChange: () => {},
  showIGNOverlay: false,
  onShowIGNOverlayChange: () => {},
  demEnabled: false,
  showDemOverlay: false,
  onShowDemOverlayChange: () => {},
  activeDemLayerId: null,
  onActiveDemLayerIdChange: () => {},
  demOptions: [],
};

describe('<LayerControlsPanel /> — "Capas" collapsible section', () => {
  it('renders the panel landmark and Capas checkboxes visible by default (expanded)', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} />);

    expect(
      screen.getByRole('region', { name: /controles de capas del mapa/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/seleccionar capa base/i)).toBeInTheDocument();
    expect(screen.getByText('Capas')).toBeInTheDocument();
    expect(screen.getByLabelText('Catastro')).toBeInTheDocument();
    expect(screen.getByLabelText('BPA 2025')).toBeInTheDocument();
  });

  it('hides the Capas body when the header is clicked, keeps title visible', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} />);

    const header = screen.getByTestId('layer-controls-capas-header');
    fireEvent.click(header);

    expect(screen.queryByLabelText('Catastro')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('BPA 2025')).not.toBeInTheDocument();
    // Title still visible.
    expect(screen.getByText('Capas')).toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });

  it('re-shows the Capas body after a second click', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} />);

    const header = screen.getByTestId('layer-controls-capas-header');
    fireEvent.click(header);
    fireEvent.click(header);

    expect(screen.getByLabelText('Catastro')).toBeInTheDocument();
    expect(screen.getByLabelText('BPA 2025')).toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'true');
  });

  it('exposes an accessible label for the DEM layer selector', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        demEnabled
        showDemOverlay
        activeDemLayerId="slope"
        demOptions={[{ value: 'slope', label: 'Pendiente' }]}
      />,
    );

    expect(screen.getAllByLabelText(/tipo de capa dem/i)[0]).toBeInTheDocument();
  });

  it('selects the first DEM layer before enabling the overlay when none is active', () => {
    const onShowDemOverlayChange = vi.fn();
    const onActiveDemLayerIdChange = vi.fn();

    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        demEnabled
        onShowDemOverlayChange={onShowDemOverlayChange}
        onActiveDemLayerIdChange={onActiveDemLayerIdChange}
        demOptions={[
          { value: 'dem-1', label: 'Elevación' },
          { value: 'slope-1', label: 'Pendiente' },
        ]}
      />,
    );

    fireEvent.click(screen.getByLabelText('Capa DEM'));

    expect(onActiveDemLayerIdChange).toHaveBeenCalledWith('dem-1');
    expect(onShowDemOverlayChange).toHaveBeenCalledWith(true);
  });

  it('toggles via Enter key on the header', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} />);

    const header = screen.getByTestId('layer-controls-capas-header');
    fireEvent.keyDown(header, { key: 'Enter' });

    expect(screen.queryByLabelText('Catastro')).not.toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });
});
