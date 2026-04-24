import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { RasterLegend } from '../../src/components/RasterLegend';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('<RasterLegend />', () => {
  it('toggles a categorical class once when the checkbox itself is clicked', () => {
    const onClassToggle = vi.fn();

    renderWithMantine(
      <RasterLegend
        layers={[{ tipo: 'terrain_class' }]}
        onClassToggle={onClassToggle}
        floating={false}
      />,
    );

    fireEvent.click(screen.getByLabelText('Ocultar Sin Riesgo en Clasificación de Terreno'));

    expect(onClassToggle).toHaveBeenCalledTimes(1);
    expect(onClassToggle).toHaveBeenCalledWith('terrain_class', 0, false);
  });

  it('toggles a categorical class from the row label without requiring precise checkbox click', () => {
    const onClassToggle = vi.fn();

    renderWithMantine(
      <RasterLegend
        layers={[{ tipo: 'terrain_class' }]}
        onClassToggle={onClassToggle}
        floating={false}
      />,
    );

    fireEvent.click(screen.getByText('Drenaje Natural'));

    expect(onClassToggle).toHaveBeenCalledTimes(1);
    expect(onClassToggle).toHaveBeenCalledWith('terrain_class', 1, false);
  });

  it('toggles a continuous range once and announces the current action in Spanish', () => {
    const onRangeToggle = vi.fn();

    renderWithMantine(
      <RasterLegend
        layers={[{ tipo: 'flood_risk' }]}
        hiddenRanges={{ flood_risk: [0] }}
        onRangeToggle={onRangeToggle}
        floating={false}
      />,
    );

    fireEvent.click(screen.getByLabelText('Mostrar Bajo en Riesgo de Inundación'));

    expect(onRangeToggle).toHaveBeenCalledTimes(1);
    expect(onRangeToggle).toHaveBeenCalledWith('flood_risk', 0, true);
  });
});
