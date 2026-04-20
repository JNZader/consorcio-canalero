/**
 * LayerControlsPanelCanales.test.tsx
 *
 * Covers the Pilar Azul "Canales" CollapsibleSection inside
 * `<LayerControlsPanel />`. The section renders AFTER the existing "Capas"
 * section and contains:
 *
 *   - 2 master checkboxes: "Canales relevados" + "Canales propuestos"
 *     (defaults: relevados ON, propuestos OFF — driven by store state via
 *     `vectorVisibility`).
 *   - Per-canal sub-checkboxes for each master, disabled + tooltipped when
 *     the master is OFF.
 *   - The `<PropuestasEtapasFilter>` subsection, which UNMOUNTS when the
 *     propuestos master is OFF.
 *
 * See spec `sdd/canales-relevados-y-propuestas/spec` §LayerControlsPanel.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';
import { ALL_ETAPAS } from '../../src/types/canales';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const baseProps = {
  baseLayer: 'osm' as const,
  onBaseLayerChange: () => {},
  layerItems: [{ id: 'catastro', label: 'Catastro' }],
  showIGNOverlay: false,
  onShowIGNOverlayChange: () => {},
  demEnabled: false,
  showDemOverlay: false,
  onShowDemOverlayChange: () => {},
  activeDemLayerId: null,
  onActiveDemLayerIdChange: () => {},
  demOptions: [],
};

const canalesRelevadosItems = [
  { id: 'canal_relevado_norte', label: 'Canal Norte' },
  { id: 'canal_relevado_sur', label: 'Canal Sur' },
];

const canalesPropuestosItems = [
  { id: 'canal_propuesto_nuevo_colector', label: 'Nuevo colector' },
  { id: 'canal_propuesto_ampliacion', label: 'Ampliación' },
];

const defaultEtapasVisibility = {
  Alta: true,
  'Media-Alta': true,
  Media: true,
  Opcional: true,
  'Largo plazo': true,
} as const;

describe('<LayerControlsPanel /> — Canales section', () => {
  it('renders a "Canales" collapsible section with both master checkboxes', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ canales_relevados: true, canales_propuestos: false }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
        propuestasEtapasVisibility={defaultEtapasVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );

    expect(screen.getByTestId('layer-controls-canales')).toBeInTheDocument();
    expect(screen.getByLabelText('Canales relevados')).toBeChecked();
    expect(screen.getByLabelText('Canales propuestos')).not.toBeChecked();
  });

  it('reflects master state from vectorVisibility', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ canales_relevados: false, canales_propuestos: true }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
        propuestasEtapasVisibility={defaultEtapasVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );

    expect(screen.getByLabelText('Canales relevados')).not.toBeChecked();
    expect(screen.getByLabelText('Canales propuestos')).toBeChecked();
  });

  it('calls onLayerVisibilityChange when a master checkbox is toggled', () => {
    const onLayerVisibilityChange = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ canales_relevados: true, canales_propuestos: false }}
        onLayerVisibilityChange={onLayerVisibilityChange}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
        propuestasEtapasVisibility={defaultEtapasVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );

    fireEvent.click(screen.getByLabelText('Canales propuestos'));
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('canales_propuestos', true);
  });

  it('does NOT render the Canales section when no items are supplied', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{}}
        onLayerVisibilityChange={() => {}}
      />,
    );
    expect(screen.queryByTestId('layer-controls-canales')).not.toBeInTheDocument();
  });
});

describe('<LayerControlsPanel /> — per-canal sub-checkboxes', () => {
  it('renders one checkbox per canal in each group', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: true,
          canales_propuestos: true,
          canal_relevado_norte: true,
          canal_relevado_sur: true,
          canal_propuesto_nuevo_colector: true,
          canal_propuesto_ampliacion: true,
        }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
        propuestasEtapasVisibility={defaultEtapasVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );

    for (const item of canalesRelevadosItems) {
      expect(screen.getByTestId(`canal-toggle-${item.id}`)).toBeInTheDocument();
      expect(screen.getByLabelText(item.label)).toBeChecked();
    }
    for (const item of canalesPropuestosItems) {
      expect(screen.getByTestId(`canal-toggle-${item.id}`)).toBeInTheDocument();
      expect(screen.getByLabelText(item.label)).toBeChecked();
    }
  });

  it('disables relevado per-canal checkboxes when the relevados master is OFF', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: false,
          canales_propuestos: true,
          canal_relevado_norte: true,
          canal_relevado_sur: true,
        }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
        propuestasEtapasVisibility={defaultEtapasVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );

    for (const item of canalesRelevadosItems) {
      const checkbox = screen.getByLabelText(item.label) as HTMLInputElement;
      expect(checkbox).toBeDisabled();
    }
  });

  it('disables propuesto per-canal checkboxes when the propuestos master is OFF', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: true,
          canales_propuestos: false,
          canal_propuesto_nuevo_colector: true,
        }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
        propuestasEtapasVisibility={defaultEtapasVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );

    for (const item of canalesPropuestosItems) {
      const checkbox = screen.getByLabelText(item.label) as HTMLInputElement;
      expect(checkbox).toBeDisabled();
    }
  });

  it('renders a tooltip on disabled per-canal rows', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: false,
          canales_propuestos: true,
          canal_relevado_norte: true,
        }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
        propuestasEtapasVisibility={defaultEtapasVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );

    // Tooltip markup carries its label via `data-tooltip-label` (set by our
    // wrapper) — independent of the Mantine/react-floating-ui portal that
    // may not be in the DOM until the user hovers.
    const row = screen.getByTestId('canal-toggle-canal_relevado_norte');
    expect(row).toHaveAttribute(
      'data-tooltip-label',
      "Activá 'Canales relevados' para usar esta opción",
    );
  });

  it('calls onLayerVisibilityChange when a per-canal checkbox is toggled (master ON)', () => {
    const onLayerVisibilityChange = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: true,
          canales_propuestos: false,
          canal_relevado_norte: true,
          canal_relevado_sur: false,
        }}
        onLayerVisibilityChange={onLayerVisibilityChange}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
        propuestasEtapasVisibility={defaultEtapasVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );

    fireEvent.click(screen.getByLabelText('Canal Sur'));
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('canal_relevado_sur', true);
  });
});

describe('<LayerControlsPanel /> — PropuestasEtapasFilter subsection', () => {
  it('renders PropuestasEtapasFilter when the propuestos master is ON', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ canales_relevados: true, canales_propuestos: true }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
        propuestasEtapasVisibility={defaultEtapasVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );

    expect(screen.getByTestId('propuestas-etapas-filter')).toBeInTheDocument();
    for (const etapa of ALL_ETAPAS) {
      const row = within(screen.getByTestId('propuestas-etapas-filter'));
      expect(row.getByLabelText(etapa)).toBeInTheDocument();
    }
  });

  it('UNMOUNTS PropuestasEtapasFilter when the propuestos master is OFF', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ canales_relevados: true, canales_propuestos: false }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
        propuestasEtapasVisibility={defaultEtapasVisibility}
        onSetEtapaVisible={() => {}}
      />,
    );

    expect(screen.queryByTestId('propuestas-etapas-filter')).not.toBeInTheDocument();
  });
});
