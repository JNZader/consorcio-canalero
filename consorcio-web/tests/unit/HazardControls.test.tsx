import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { HazardControls } from '../../src/components/map2d/HazardControls';
import {
  HAZARD_RISK_CLASS,
  HAZARD_RISK_CLASSES,
  PRECIPITATION_PERIOD,
  type HazardControlsProps,
} from '../../src/components/map2d/hazardControls.types';

function renderControls(overrides: Partial<HazardControlsProps> = {}) {
  const props: HazardControlsProps = {
    basins: [{ id: 'rio-tercero', label: 'Río Tercero' }],
    selectedBasinId: null,
    onBasinChange: vi.fn(),
    visibleRiskClasses: ['Bajo', 'Medio', 'Alto', 'Crítico'],
    onRiskClassChange: vi.fn(),
    precipitationPeriod: PRECIPITATION_PERIOD.ANNUAL,
    onPrecipitationPeriodChange: vi.fn(),
    onReset: vi.fn(),
    collapsed: false,
    onCollapsedChange: vi.fn(),
    ...overrides,
  };

  render(
    <MantineProvider env="test">
      <HazardControls {...props} />
    </MantineProvider>
  );
  return props;
}

describe('HazardControls', () => {
  it('renders the desktop panel with canonical risk and precipitation tokens', () => {
    renderControls();

    expect(HAZARD_RISK_CLASS.CRITICAL).toBe('Crítico');
    expect(PRECIPITATION_PERIOD.ANNUAL).toBe('anual');
    expect(screen.getByTestId('hazard-controls-desktop')).toBeInTheDocument();
    expect(screen.getByLabelText('Seleccionar cuenca')).toBeInTheDocument();
    for (const riskClass of HAZARD_RISK_CLASSES) {
      expect(screen.getByLabelText(riskClass)).toBeInTheDocument();
    }
    expect(screen.getByLabelText('Crítico')).toBeChecked();
    expect(screen.getByLabelText('Periodo de precipitación')).toHaveValue('Anual');
    expect(screen.getByRole('button', { name: 'Restablecer' })).toBeInTheDocument();
  });

  it('emits risk, reset, and collapse callbacks without owning state', async () => {
    const props = renderControls();
    const user = userEvent.setup();

    await user.click(screen.getByLabelText('Alto'));
    await user.click(screen.getByRole('button', { name: 'Restablecer' }));
    await user.click(screen.getByRole('button', { name: 'Contraer controles de riesgos' }));

    expect(props.onRiskClassChange).toHaveBeenCalledWith('Alto', false);
    expect(props.onReset).toHaveBeenCalledTimes(1);
    expect(props.onCollapsedChange).toHaveBeenCalledWith(true);
  });

  it('emits basin and precipitation selections through accessible combobox options', async () => {
    const props = renderControls();
    const user = userEvent.setup();

    const basinSelect = screen.getByLabelText('Seleccionar cuenca');
    await user.click(basinSelect);
    await user.click(screen.getByRole('option', { name: 'Río Tercero' }));

    await user.click(basinSelect);
    await user.click(screen.getByRole('option', { name: 'Mostrar todo' }));

    await user.click(screen.getByLabelText('Periodo de precipitación'));
    await user.click(screen.getByRole('option', { name: 'Enero' }));

    expect(props.onBasinChange).toHaveBeenNthCalledWith(1, 'rio-tercero');
    expect(props.onBasinChange).toHaveBeenNthCalledWith(2, null);
    expect(props.onPrecipitationPeriodChange).toHaveBeenCalledOnce();
    expect(props.onPrecipitationPeriodChange).toHaveBeenCalledWith(PRECIPITATION_PERIOD.JANUARY);
  });

  it('collapses for an open ficha even when the parent does not collapse it', async () => {
    const onFichaMinimize = vi.fn();
    const props = renderControls({ collapsed: false, fichaOpen: true, onFichaMinimize });
    const user = userEvent.setup();

    expect(screen.getByTestId('hazard-controls-desktop-collapsed')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Expandir controles de riesgos' }));

    expect(props.onCollapsedChange).toHaveBeenCalledWith(false);
    expect(onFichaMinimize).toHaveBeenCalledTimes(1);
  });
});
