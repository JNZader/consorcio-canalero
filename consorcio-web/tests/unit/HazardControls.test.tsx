import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
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

  it('emits risk, reset, and collapse callbacks without owning state', () => {
    const props = renderControls();

    fireEvent.click(screen.getByLabelText('Alto'));
    fireEvent.click(screen.getByRole('button', { name: 'Restablecer' }));
    fireEvent.click(screen.getByRole('button', { name: 'Contraer controles de riesgos' }));

    expect(props.onRiskClassChange).toHaveBeenCalledWith('Alto', false);
    expect(props.onReset).toHaveBeenCalledTimes(1);
    expect(props.onCollapsedChange).toHaveBeenCalledWith(true);
  });

  it('renders an expand chip when the parent collapses it and minimizes for a ficha', () => {
    const onFichaMinimize = vi.fn();
    const props = renderControls({ collapsed: true, fichaOpen: true, onFichaMinimize });

    expect(screen.getByTestId('hazard-controls-desktop-collapsed')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Expandir controles de riesgos' }));

    expect(props.onCollapsedChange).toHaveBeenCalledWith(false);
    expect(onFichaMinimize).toHaveBeenCalledTimes(1);
  });
});
