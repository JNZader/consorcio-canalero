/**
 * B3c legend completion: visible flood/drainage class chips, selected-basin
 * outline/label, and a visible aggregate when risk classes are hidden.
 * Visibility comes from URL `riskClasses`, not DEM `hiddenRanges`.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { HazardLegendInput } from '../../src/components/map2d/hazardLegend';
import {
  buildHazardLegendView,
  colorForHazardRiskClass,
} from '../../src/components/map2d/hazardLegend';
import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';
import { getPrecipitationRange } from '../../src/components/map2d/precipRanges';
import { LAYER_LEGEND_CONFIG } from '../../src/config/rasterLegend';
import { HAZARD_RISK_CLASSES } from '../../src/hooks/useHazardUrlState';

const BASIN_OPTIONS = [
  { id: 'candil', label: 'Candil' },
  { id: 'aliviador', label: 'Aliviador' },
] as const;
const ALL_VISIBLE = [...HAZARD_RISK_CLASSES];
const WITHOUT_CRITICO = ['Bajo', 'Medio', 'Alto'] as const;
const LOW_AND_MEDIUM = ['Bajo', 'Medio'] as const;

function floodRiskColor(label: string): string {
  return LAYER_LEGEND_CONFIG.flood_risk.ranges?.find((range) => range.label === label)?.color ?? '';
}

function legendView(overrides: Partial<HazardLegendInput> = {}) {
  return buildHazardLegendView({
    active: true,
    riskClasses: ALL_VISIBLE,
    selectedBasinId: null,
    basinOptions: BASIN_OPTIONS,
    ...overrides,
  });
}

function renderLegend(overrides: Partial<HazardLegendInput> = {}) {
  return render(
    <MantineProvider env="test">
      <LeyendaPanel hazardLegend={legendView(overrides)} />
    </MantineProvider>
  );
}

describe('buildHazardLegendView', () => {
  it('returns null when hazard mode is inactive', () => {
    expect(legendView({ active: false, selectedBasinId: 'candil' })).toBeNull();
  });

  it('lists every URL-visible class and reports no hidden aggregate', () => {
    expect(legendView()).toEqual({
      visibleClasses: ALL_VISIBLE,
      hasHiddenClasses: false,
      basinLabel: null,
    });
  });

  it('drops hidden classes and flags the aggregate when Crítico is off', () => {
    expect(legendView({ riskClasses: [...WITHOUT_CRITICO] })).toEqual({
      visibleClasses: [...WITHOUT_CRITICO],
      hasHiddenClasses: true,
      basinLabel: null,
    });
  });

  it('uses a different visible subset when only Bajo and Medio remain', () => {
    expect(legendView({ riskClasses: [...LOW_AND_MEDIUM], basinOptions: [] })).toEqual({
      visibleClasses: [...LOW_AND_MEDIUM],
      hasHiddenClasses: true,
      basinLabel: null,
    });
  });

  it('resolves the selected basin label from existing basin options', () => {
    expect(legendView({ selectedBasinId: 'candil' })?.basinLabel).toBe('Candil');
  });

  it('falls back to a Cuenca prefix when the selected basin is missing', () => {
    expect(legendView({ selectedBasinId: 'unknown-basin' })?.basinLabel).toBe(
      'Cuenca unknown-basin'
    );
  });

  it('accepts coordinator basin options that also carry geometry', () => {
    expect(
      legendView({
        riskClasses: ['Medio', 'Alto'],
        selectedBasinId: 'candil',
        basinOptions: [{ id: 'candil', label: 'Candil', geometry: null }],
      })
    ).toEqual({
      visibleClasses: ['Medio', 'Alto'],
      hasHiddenClasses: true,
      basinLabel: 'Candil',
    });
  });
});

describe('colorForHazardRiskClass', () => {
  it('uses the flood_risk colormap for each discrete class', () => {
    for (const riskClass of HAZARD_RISK_CLASSES) {
      expect(colorForHazardRiskClass(riskClass)).toBe(floodRiskColor(riskClass));
    }
  });
});

describe('<LeyendaPanel /> — hazard risk classes, basin, and hidden aggregate', () => {
  it('does not render hazard chips, basin, or hidden-class copy by default', () => {
    render(
      <MantineProvider env="test">
        <LeyendaPanel />
      </MantineProvider>
    );
    expect(screen.queryByTestId('hazard-risk-class-legend')).not.toBeInTheDocument();
    expect(screen.queryByTestId('hazard-basin-legend')).not.toBeInTheDocument();
    expect(screen.queryByText('algunas clases ocultas')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Bajo')).not.toBeInTheDocument();
  });

  it('renders chips for every currently visible flood/drainage class', () => {
    renderLegend();
    expect(screen.getByTestId('hazard-risk-class-legend')).toBeInTheDocument();
    expect(screen.getByText('Clases de riesgo')).toBeInTheDocument();
    for (const riskClass of HAZARD_RISK_CLASSES) {
      expect(screen.getByLabelText(riskClass)).toHaveAttribute(
        'data-color',
        floodRiskColor(riskClass)
      );
    }
    expect(screen.queryByText('algunas clases ocultas')).not.toBeInTheDocument();
  });

  it('omits hidden classes and shows a visible aggregate when Crítico is hidden', () => {
    renderLegend({ riskClasses: [...WITHOUT_CRITICO] });
    expect(screen.getByLabelText('Bajo')).toBeInTheDocument();
    expect(screen.getByLabelText('Medio')).toBeInTheDocument();
    expect(screen.getByLabelText('Alto')).toBeInTheDocument();
    expect(screen.queryByLabelText('Crítico')).not.toBeInTheDocument();
    const indicator = screen.getByTestId('hazard-hidden-classes-indicator');
    expect(indicator).toHaveTextContent('algunas clases ocultas');
    expect(indicator).toBeVisible();
  });

  it('shows the aggregate for a different hidden subset (Bajo and Medio only)', () => {
    renderLegend({ riskClasses: [...LOW_AND_MEDIUM], basinOptions: [] });
    expect(screen.getByLabelText('Bajo')).toBeInTheDocument();
    expect(screen.getByLabelText('Medio')).toBeInTheDocument();
    expect(screen.queryByLabelText('Alto')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Crítico')).not.toBeInTheDocument();
    expect(screen.getByTestId('hazard-hidden-classes-indicator')).toHaveTextContent(
      'algunas clases ocultas'
    );
  });

  it('renders the selected-basin outline and label', () => {
    renderLegend({ selectedBasinId: 'candil' });
    const basin = screen.getByTestId('hazard-basin-legend');
    expect(basin).toHaveTextContent('Candil');
    expect(screen.getByText('Cuenca seleccionada')).toBeInTheDocument();
    expect(screen.getByLabelText('Contorno de cuenca Candil')).toBeInTheDocument();
  });

  it('does not render a basin row when no basin is selected', () => {
    renderLegend();
    expect(screen.queryByTestId('hazard-basin-legend')).not.toBeInTheDocument();
    expect(screen.queryByText('Cuenca seleccionada')).not.toBeInTheDocument();
  });

  it('keeps the B3b precipitation ramp working next to the new hazard legend', () => {
    render(
      <MantineProvider env="test">
        <LeyendaPanel
          hazardPrecipitationRange={getPrecipitationRange('03')}
          hazardLegend={legendView({
            riskClasses: [...WITHOUT_CRITICO],
            selectedBasinId: 'aliviador',
          })}
        />
      </MantineProvider>
    );
    expect(screen.getByTestId('hazard-precipitation-legend')).toHaveTextContent(
      'CHIRPS 1991-2020 normal mensual'
    );
    expect(screen.getByTestId('hazard-precipitation-legend')).toHaveTextContent('200 mm');
    expect(screen.getByLabelText('Bajo')).toBeInTheDocument();
    expect(screen.queryByLabelText('Crítico')).not.toBeInTheDocument();
    expect(screen.getByText('algunas clases ocultas')).toBeInTheDocument();
    expect(screen.getByTestId('hazard-basin-legend')).toHaveTextContent('Aliviador');
  });
});
