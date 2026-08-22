import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { HazardControlsMobile } from '../../src/components/map2d/HazardControlsMobile';
import {
  HAZARD_RISK_CLASSES,
  PRECIPITATION_PERIOD,
  type HazardControlsProps,
} from '../../src/components/map2d/hazardControls.types';

function renderControls(overrides: Partial<HazardControlsProps> = {}) {
  const props: HazardControlsProps = {
    basins: [{ id: 'carcarana', label: 'Carcarañá' }],
    selectedBasinId: null,
    onBasinChange: vi.fn(),
    visibleRiskClasses: HAZARD_RISK_CLASSES,
    onRiskClassChange: vi.fn(),
    precipitationPeriod: PRECIPITATION_PERIOD.ANNUAL,
    onPrecipitationPeriodChange: vi.fn(),
    onReset: vi.fn(),
    collapsed: true,
    onCollapsedChange: vi.fn(),
    ...overrides,
  };

  const view = render(
    <MantineProvider env="test">
      <HazardControlsMobile {...props} />
    </MantineProvider>
  );
  return { props, ...view };
}

describe('HazardControlsMobile', () => {
  it('renders a compact chip while collapsed and asks the parent to expand it', () => {
    const { props } = renderControls();

    fireEvent.click(screen.getByTestId('hazard-controls-mobile-chip'));

    expect(props.onCollapsedChange).toHaveBeenCalledWith(false);
  });

  it('renders the bottom sheet controls when expanded', async () => {
    const { props } = renderControls({ collapsed: false });
    const user = userEvent.setup();

    expect(screen.getByTestId('hazard-controls-mobile-sheet')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Contraer controles de riesgos'));
    await user.click(screen.getByLabelText('Seleccionar cuenca'));
    await user.click(screen.getByRole('option', { name: 'Carcarañá' }));
    fireEvent.click(screen.getByLabelText('Medio'));
    await user.click(screen.getByLabelText('Periodo de precipitación'));
    await user.click(screen.getByRole('option', { name: 'Mes 01' }));
    fireEvent.click(screen.getByRole('button', { name: 'Restablecer' }));

    expect(props.onCollapsedChange).toHaveBeenCalledWith(true);
    expect(props.onBasinChange).toHaveBeenCalledWith('carcarana');
    expect(props.onRiskClassChange).toHaveBeenCalledWith('Medio', false);
    expect(props.onPrecipitationPeriodChange).toHaveBeenCalledWith('01');
    expect(props.onReset).toHaveBeenCalledTimes(1);
  });

  it('uses ficha precedence to reduce the sheet to a chip and signal minimization', () => {
    const onFichaMinimize = vi.fn();
    renderControls({ collapsed: false, fichaOpen: true, onFichaMinimize });

    expect(screen.getByTestId('hazard-controls-mobile-chip')).toBeInTheDocument();
    expect(onFichaMinimize).toHaveBeenCalledTimes(1);
  });
});
