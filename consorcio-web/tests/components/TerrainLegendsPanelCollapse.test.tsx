/**
 * TerrainLegendsPanelCollapse.test.tsx
 *
 * Collapsible body for the 3D legends panel. Click the "Leyendas" header
 * (or press Enter/Space) to hide the raster + soil legends, keeping only the
 * title row. Default is expanded. Local-state only (useState).
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLegendsPanel } from '../../src/components/terrain/TerrainLegendsPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const baseProps = {
  activeRasterType: undefined,
  hiddenClasses: {} as Record<string, number[]>,
  onClassToggle: vi.fn(),
  hiddenRanges: {} as Record<string, number[]>,
  onRangeToggle: vi.fn(),
  vectorLayerVisibility: { soil: true },
};

describe('<TerrainLegendsPanel /> — collapsible body', () => {
  it('renders the soil legend visible by default (expanded)', () => {
    renderWithMantine(<TerrainLegendsPanel {...baseProps} />);

    expect(screen.getByText('Leyendas')).toBeInTheDocument();
    expect(screen.getByTestId('terrain-3d-soil-legend')).toBeInTheDocument();
  });

  it('hides the soil legend when the header is clicked, keeps title visible', () => {
    renderWithMantine(<TerrainLegendsPanel {...baseProps} />);

    const header = screen.getByTestId('terrain-3d-legends-header');
    fireEvent.click(header);

    expect(screen.queryByTestId('terrain-3d-soil-legend')).not.toBeInTheDocument();
    // Title still visible.
    expect(screen.getByText('Leyendas')).toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });

  it('re-shows the soil legend after a second click', () => {
    renderWithMantine(<TerrainLegendsPanel {...baseProps} />);

    const header = screen.getByTestId('terrain-3d-legends-header');
    fireEvent.click(header);
    fireEvent.click(header);

    expect(screen.getByTestId('terrain-3d-soil-legend')).toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'true');
  });

  it('toggles via Enter key on the header', () => {
    renderWithMantine(<TerrainLegendsPanel {...baseProps} />);

    const header = screen.getByTestId('terrain-3d-legends-header');
    fireEvent.keyDown(header, { key: 'Enter' });

    expect(screen.queryByTestId('terrain-3d-soil-legend')).not.toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });
});
