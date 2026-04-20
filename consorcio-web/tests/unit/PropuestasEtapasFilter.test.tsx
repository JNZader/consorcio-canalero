/**
 * PropuestasEtapasFilter.test.tsx
 *
 * The 5-etapa checkbox group rendered inside `<LayerControlsPanel />` when
 * the propuestos master is ON. Per spec §Etapas Filter:
 *
 *   - MOUNTS conditionally — not CSS-hidden, UNMOUNTED when master is OFF.
 *   - 5 checkboxes in canonical order: Alta, Media-Alta, Media, Opcional,
 *     Largo plazo.
 *   - Each checkbox reflects `propuestasEtapasVisibility[etapa]` and calls
 *     `setEtapaVisible(etapa, next)` on toggle.
 *   - Default: all 5 checked.
 *   - Colored dot before each label (tests check for `data-color-dot`).
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { CANALES_COLORS } from '../../src/components/map2d/canalesLayers';
import { PropuestasEtapasFilter } from '../../src/components/map2d/PropuestasEtapasFilter';
import { ALL_ETAPAS } from '../../src/types/canales';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const defaultVisibility = {
  Alta: true,
  'Media-Alta': true,
  Media: true,
  Opcional: true,
  'Largo plazo': true,
} as const;

describe('<PropuestasEtapasFilter /> — conditional mount', () => {
  it('UNMOUNTS (returns null) when masterOn is false', () => {
    renderWithMantine(
      <PropuestasEtapasFilter
        masterOn={false}
        propuestasEtapasVisibility={defaultVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );
    // The component rendered nothing of its own — neither the root testid
    // nor any of its 5 checkboxes should appear in the tree. (MantineProvider
    // itself injects a `<style>` tag, so we cannot assert the container is
    // literally empty — we assert the component's own output is absent.)
    expect(screen.queryByTestId('propuestas-etapas-filter')).not.toBeInTheDocument();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('renders 5 checkboxes when masterOn is true', () => {
    renderWithMantine(
      <PropuestasEtapasFilter
        masterOn
        propuestasEtapasVisibility={defaultVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );
    const root = screen.getByTestId('propuestas-etapas-filter');
    expect(root).toBeInTheDocument();
    for (const etapa of ALL_ETAPAS) {
      expect(screen.getByLabelText(etapa)).toBeInTheDocument();
    }
    expect(screen.getAllByRole('checkbox')).toHaveLength(5);
  });
});

describe('<PropuestasEtapasFilter /> — checkbox state', () => {
  it('reflects propuestasEtapasVisibility for each etapa', () => {
    renderWithMantine(
      <PropuestasEtapasFilter
        masterOn
        propuestasEtapasVisibility={{
          Alta: false,
          'Media-Alta': true,
          Media: false,
          Opcional: true,
          'Largo plazo': true,
        }}
        onSetEtapaVisible={() => {}}
      />,
    );
    expect(screen.getByLabelText('Alta')).not.toBeChecked();
    expect(screen.getByLabelText('Media-Alta')).toBeChecked();
    expect(screen.getByLabelText('Media')).not.toBeChecked();
    expect(screen.getByLabelText('Opcional')).toBeChecked();
    expect(screen.getByLabelText('Largo plazo')).toBeChecked();
  });

  it('calls onSetEtapaVisible with the etapa + new value when toggled', () => {
    const onSetEtapaVisible = vi.fn();
    renderWithMantine(
      <PropuestasEtapasFilter
        masterOn
        propuestasEtapasVisibility={defaultVisibility}
        onSetEtapaVisible={onSetEtapaVisible}
      />,
    );
    fireEvent.click(screen.getByLabelText('Alta'));
    expect(onSetEtapaVisible).toHaveBeenCalledWith('Alta', false);

    fireEvent.click(screen.getByLabelText('Opcional'));
    expect(onSetEtapaVisible).toHaveBeenCalledWith('Opcional', false);
  });

  it('calls onSetEtapaVisible with true when turning an unchecked etapa on', () => {
    const onSetEtapaVisible = vi.fn();
    renderWithMantine(
      <PropuestasEtapasFilter
        masterOn
        propuestasEtapasVisibility={{ ...defaultVisibility, Alta: false }}
        onSetEtapaVisible={onSetEtapaVisible}
      />,
    );
    fireEvent.click(screen.getByLabelText('Alta'));
    expect(onSetEtapaVisible).toHaveBeenCalledWith('Alta', true);
  });
});

describe('<PropuestasEtapasFilter /> — color dots', () => {
  it('renders a color dot matching CANALES_COLORS for each etapa', () => {
    renderWithMantine(
      <PropuestasEtapasFilter
        masterOn
        propuestasEtapasVisibility={defaultVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );
    const expected: Array<[typeof ALL_ETAPAS[number], string]> = [
      ['Alta', CANALES_COLORS.propuestoAlta],
      ['Media-Alta', CANALES_COLORS.propuestoMediaAlta],
      ['Media', CANALES_COLORS.propuestoMedia],
      ['Opcional', CANALES_COLORS.propuestoOpcional],
      ['Largo plazo', CANALES_COLORS.propuestoLargoPlazo],
    ];
    for (const [etapa, color] of expected) {
      const dot = screen.getByTestId(`propuestas-etapa-dot-${etapa}`);
      expect(dot).toHaveAttribute('data-color-dot', color);
    }
  });
});
