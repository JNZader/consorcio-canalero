/**
 * LayerControlsPanelPilarVerdeStatus.test.tsx — T3c final round.
 *
 * Two pieces of feedback for the ONLY family whose render payload is lazy:
 *   - R4-001: when the ~1.0 MB `layers` group FAILED, the panel says so next to
 *     the Pilar Verde family instead of leaving a toggled-on layer invisible
 *     with no explanation (re-toggling retries, since the errored query has no
 *     cached data for `staleTime: Infinity` to shield).
 *   - R4-002: while that group is in flight AND a Pilar Verde layer is on, a
 *     small spinner renders beside the family (mirrors the bpaLoading pattern).
 *
 * Also pins the accent-folded search (R3-003): "forestacion" must find
 * "% Forestación obligatoria" and "inundación" must find "Riesgo de Inundacion".
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const pilarVerdeItems = [
  {
    id: 'pilar_verde_porcentaje_forestacion',
    label: '% Forestación obligatoria',
    category: 'pilar_verde' as const,
  },
  {
    id: 'pilar_verde_agro_zonas',
    label: 'Zonas Agroforestales',
    category: 'pilar_verde' as const,
  },
];

const demOptions = [{ value: 'layer-flood', label: 'Riesgo de Inundacion' }];

function baseProps(overrides: Record<string, unknown> = {}) {
  return {
    layerItems: pilarVerdeItems,
    vectorVisibility: {},
    onLayerVisibilityChange: () => {},
    showIGNOverlay: false,
    onShowIGNOverlayChange: () => {},
    demEnabled: true,
    showDemOverlay: false,
    onShowDemOverlayChange: () => {},
    activeDemLayerId: null,
    onActiveDemLayerIdChange: () => {},
    demOptions,
    ...overrides,
  };
}

function search(term: string) {
  fireEvent.change(screen.getByLabelText('Buscar capa'), {
    target: { value: term },
  });
}

describe('<LayerControlsPanel /> — Pilar Verde payload status', () => {
  it('renders a warning row when the layers group failed (R4-001)', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps({
          vectorVisibility: { pilar_verde_agro_zonas: true },
          pilarVerdeLayersError: 'Pilar Verde: no se pudieron cargar agroZonas',
        })}
      />
    );

    const row = screen.getByTestId('pilar-verde-layers-error');
    expect(row).toBeInTheDocument();
    expect(row.textContent).toMatch(/reintentá/i);
  });

  it('renders no warning row when the group is healthy', () => {
    renderWithMantine(
      <LayerControlsPanel {...baseProps({ vectorVisibility: { pilar_verde_agro_zonas: true } })} />
    );

    expect(screen.queryByTestId('pilar-verde-layers-error')).toBeNull();
  });

  it('shows a spinner while the group loads AND a Pilar Verde layer is on (R4-002)', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps({
          vectorVisibility: { pilar_verde_agro_zonas: true },
          pilarVerdeLayersLoading: true,
        })}
      />
    );

    expect(screen.getByTestId('pilar-verde-layers-loading')).toBeInTheDocument();
  });

  it('hides the spinner when no Pilar Verde layer is on (nothing was requested)', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps({ pilarVerdeLayersLoading: true })} />);

    expect(screen.queryByTestId('pilar-verde-layers-loading')).toBeNull();
  });
});

describe('<LayerControlsPanel /> — accent-folded search (R3-003)', () => {
  it('finds an ACCENTED label from an unaccented query', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps()} />);

    search('forestacion');

    expect(screen.queryByTestId('layer-controls-no-results')).toBeNull();
    expect(screen.getByLabelText('% Forestación obligatoria')).toBeInTheDocument();
  });

  it('finds an UNACCENTED label from an accented query', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps()} />);

    search('inundación');

    expect(screen.queryByTestId('layer-controls-no-results')).toBeNull();
    expect(screen.getByTestId('raster-search-option-layer-flood')).toBeInTheDocument();
  });

  it('still reports no results for a genuine miss', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps()} />);

    search('zzzz');

    expect(screen.getByTestId('layer-controls-no-results')).toBeInTheDocument();
  });
});
