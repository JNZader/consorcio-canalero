/**
 * LayerControlsPanelAccordion.test.tsx
 *
 * Phase 2 of `rediseno-ux-mapa`:
 *   - 2.2 Layers grouped by family in a Mantine `Accordion` (one item per
 *     family, LOCKED order Base → Hidrografía → Territorio → Pilar Verde →
 *     Canales → Análisis).
 *   - 2.3 Search box filters `layerItems` by label (case-insensitive); families
 *     with no matching item are hidden.
 *   - 2.4 Per-family "N active" badge derived from `vectorVisibility`.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const layerItems = [
  { id: 'waterways', label: 'Hidrografía', category: 'hidrografia' as const },
  { id: 'roads', label: 'Red Vial', category: 'territorio' as const },
  { id: 'catastro', label: 'Catastro rural IDECOR', category: 'territorio' as const },
  { id: 'pilar_verde_bpa_historico', label: 'BPA histórico (por años)', category: 'pilar_verde' as const },
  { id: 'puntos_conflicto', label: 'Puntos conflicto', category: 'analisis' as const },
];

const baseProps = {
  baseLayer: 'osm' as const,
  onBaseLayerChange: () => {},
  layerItems,
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

describe('<LayerControlsPanel /> — family accordion (2.2)', () => {
  it('renders one accordion control per non-empty family', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} vectorVisibility={{}} />);

    expect(screen.getByRole('button', { name: /base/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /hidrografía/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /territorio/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /pilar verde/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /análisis/i })).toBeInTheDocument();
    // No canales items supplied → no Canales family.
    expect(screen.queryByRole('button', { name: /canales/i })).not.toBeInTheDocument();
  });

  it('places each layer checkbox under its own family panel', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} vectorVisibility={{}} />);

    // Use the checkbox role: the "Hidrografía" family control label collides
    // with the "Hidrografía" (waterways) layer label under getByLabelText.
    expect(screen.getByRole('checkbox', { name: 'Red Vial' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Catastro rural IDECOR' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Hidrografía' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'BPA histórico (por años)' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Puntos conflicto' })).toBeInTheDocument();
  });
});

describe('<LayerControlsPanel /> — search box (2.3)', () => {
  it('filters layers by label (case-insensitive) and hides non-matching families', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} vectorVisibility={{}} />);

    fireEvent.change(screen.getByLabelText('Buscar capa'), { target: { value: 'catastro' } });

    // Only the matching layer remains.
    expect(screen.getByRole('checkbox', { name: 'Catastro rural IDECOR' })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'Red Vial' })).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'Hidrografía' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('checkbox', { name: 'BPA histórico (por años)' }),
    ).not.toBeInTheDocument();

    // Non-matching families are gone; Territorio survives; Base hidden.
    expect(screen.getByRole('button', { name: /territorio/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /hidrografía/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /base/i })).not.toBeInTheDocument();
  });

  it('restores all families when the search query is cleared', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} vectorVisibility={{}} />);

    const search = screen.getByLabelText('Buscar capa');
    fireEvent.change(search, { target: { value: 'catastro' } });
    expect(screen.queryByRole('checkbox', { name: 'Red Vial' })).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: '' } });
    expect(screen.getByRole('checkbox', { name: 'Red Vial' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Hidrografía' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /base/i })).toBeInTheDocument();
  });
});

describe('<LayerControlsPanel /> — searchable Base + Canales (FF2/FF3)', () => {
  const canalesRelevadosItems = [
    { kind: 'leaf' as const, id: 'canal_relevado_norte', label: 'Canal Norte' },
  ];

  function renderWithCanales() {
    return renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{}}
        canalesRelevadosItems={canalesRelevadosItems}
      />,
    );
  }

  it('shows the Canales section when typing a canal label', () => {
    renderWithCanales();
    fireEvent.change(screen.getByLabelText('Buscar capa'), { target: { value: 'norte' } });

    expect(screen.getByTestId('layer-controls-canales')).toBeInTheDocument();
    expect(screen.getByTestId('canal-toggle-canal_relevado_norte')).toBeInTheDocument();
  });

  it('shows the Canales section when typing the "canal" keyword', () => {
    renderWithCanales();
    fireEvent.change(screen.getByLabelText('Buscar capa'), { target: { value: 'canal' } });

    expect(screen.getByTestId('layer-controls-canales')).toBeInTheDocument();
  });

  it('shows the Base section when typing "ign"', () => {
    renderWithCanales();
    fireEvent.change(screen.getByLabelText('Buscar capa'), { target: { value: 'ign' } });

    expect(screen.getByRole('button', { name: /base/i })).toBeInTheDocument();
    expect(screen.getByLabelText('IGN Altimetría')).toBeInTheDocument();
  });

  it('renders a no-results hint when nothing matches (FF3)', () => {
    renderWithCanales();
    fireEvent.change(screen.getByLabelText('Buscar capa'), { target: { value: 'zzz' } });

    expect(screen.getByTestId('layer-controls-no-results')).toHaveTextContent(
      'Sin resultados para «zzz»',
    );
    expect(screen.queryByTestId('layer-controls-canales')).not.toBeInTheDocument();
  });
});

describe('<LayerControlsPanel /> — active-count badge (2.4)', () => {
  it('shows the count of active layers within a family', () => {
    renderWithMantine(
      <LayerControlsPanel {...baseProps} vectorVisibility={{ roads: true, catastro: false }} />,
    );

    const territorio = screen.getByRole('button', { name: /territorio/i });
    expect(within(territorio).getByText('1')).toBeInTheDocument();
  });

  it('reflects a higher active count when more layers in the family are on', () => {
    renderWithMantine(
      <LayerControlsPanel {...baseProps} vectorVisibility={{ roads: true, catastro: true }} />,
    );

    const territorio = screen.getByRole('button', { name: /territorio/i });
    expect(within(territorio).getByText('2')).toBeInTheDocument();
  });

  it('shows no badge for a family with zero active layers', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} vectorVisibility={{}} />);

    const hidrografia = screen.getByRole('button', { name: /hidrografía/i });
    expect(within(hidrografia).queryByText('1')).not.toBeInTheDocument();
  });
});
