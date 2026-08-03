/**
 * LayerControlsPanelProvenance.test.tsx — Batch 1 "datos honestos".
 *
 * The "Datos al DD/MM/AAAA" line lives at the FOOT of a family's accordion
 * panel, beside the existing attribution lines — zero pixels over the canvas.
 * Only the families the registry actually knows a date for may render one.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';
import { buildLayerProvenance } from '../../src/components/map2d/layerProvenance';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const pilarVerdeItems = [
  {
    id: 'pilar_verde_agro_zonas',
    label: 'Zonas Agroforestales',
    category: 'pilar_verde' as const,
  },
];

const canalesRelevadosItems = [
  { kind: 'leaf' as const, id: 'canal_relevado_1', label: 'Canal Norte' },
];

function baseProps(overrides: Record<string, unknown> = {}) {
  return {
    layerItems: pilarVerdeItems,
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
    canalesRelevadosItems,
    ...overrides,
  };
}

const PROVENANCE = buildLayerProvenance({
  canalesGeneratedAt: '2026-04-20T20:18:51Z',
  pilarVerdeGeneratedAt: '2026-02-01T10:00:00Z',
});

describe('<LayerControlsPanel /> — provenance lines', () => {
  it('renders nothing when the prop is absent (back-compat)', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps()} />);

    expect(screen.queryByTestId('layer-provenance-canales')).toBeNull();
    expect(screen.queryByTestId('layer-provenance-pilar_verde')).toBeNull();
  });

  it('renders the Canales line inside the Canales panel', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps({ layerProvenance: PROVENANCE })} />);

    // Pinned literal — asserting against the same builder that fed the prop
    // would only prove the component echoes it.
    const line = screen.getByTestId('layer-provenance-canales');
    expect(line.textContent).toBe('Datos al 20/04/2026');
  });

  it('renders the Pilar Verde line inside the Pilar Verde panel', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps({ layerProvenance: PROVENANCE })} />);

    expect(screen.getByTestId('layer-provenance-pilar_verde').textContent).toBe(
      'Datos al 1/02/2026'
    );
  });

  it('renders NO line for a family the registry has no date for', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps({
          layerItems: [
            {
              id: 'basins',
              label: 'Subcuencas',
              category: 'hidrografia' as const,
            },
          ],
          layerProvenance: PROVENANCE,
        })}
      />
    );

    expect(screen.queryByTestId('layer-provenance-hidrografia')).toBeNull();
    expect(screen.queryByTestId('layer-provenance-territorio')).toBeNull();
  });

  it('renders only the families present in the provenance map', () => {
    const onlyCanales = buildLayerProvenance({
      canalesGeneratedAt: '2026-04-20T20:18:51Z',
    });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerProvenance: onlyCanales })} />);

    expect(screen.getByTestId('layer-provenance-canales')).toBeInTheDocument();
    expect(screen.queryByTestId('layer-provenance-pilar_verde')).toBeNull();
  });
});
