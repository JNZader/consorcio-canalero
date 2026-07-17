/**
 * LayerControlsPanelCanales.test.tsx
 *
 * Covers the Pilar Azul "Canales" accordion item inside
 * `<LayerControlsPanel />` (change `rediseno-ux-mapa`, Phase 2).
 *
 * The Canales content is rendered by the shipped `CanalesLayerSection`
 * (`components/shared/CanalesLayerSection.tsx`), shared with the 3D viewer:
 *
 *   - Master toggle with a DYNAMIC label ("Encender/Apagar todos los
 *     relevados|propuestos") + indeterminate state.
 *   - Per-canal leaf rows (`data-testid="canal-toggle-<id>"`). Children are
 *     NEVER disabled; toggling any child auto-enables its master.
 *
 * Entries are the `CanalToggleEntry` discriminated union
 * (`{ kind: 'leaf', id, label }` or `{ kind: 'group', ... }`).
 *
 * The Canales accordion item is OPEN by default (the panel passes every family
 * value in `defaultValue`), so its content is reachable without expanding.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';
import type { CanalToggleEntry } from '../../src/components/shared/canalesGrouping';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const baseProps = {
  baseLayer: 'osm' as const,
  onBaseLayerChange: () => {},
  layerItems: [{ id: 'catastro', label: 'Catastro', category: 'territorio' as const }],
  showIGNOverlay: false,
  onShowIGNOverlayChange: () => {},
  demEnabled: false,
  showDemOverlay: false,
  onShowDemOverlayChange: () => {},
  activeDemLayerId: null,
  onActiveDemLayerIdChange: () => {},
  demOptions: [],
};

const canalesRelevadosItems: CanalToggleEntry[] = [
  { kind: 'leaf', id: 'canal_relevado_norte', label: 'Canal Norte' },
  { kind: 'leaf', id: 'canal_relevado_sur', label: 'Canal Sur' },
];

const canalesPropuestosItems: CanalToggleEntry[] = [
  { kind: 'leaf', id: 'canal_propuesto_nuevo_colector', label: 'Nuevo colector' },
  { kind: 'leaf', id: 'canal_propuesto_ampliacion', label: 'Ampliación' },
];

describe('<LayerControlsPanel /> — Canales section', () => {
  it('renders a "Canales" accordion item with both dynamic master toggles', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ canales_relevados: true, canales_propuestos: false }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
      />,
    );

    expect(screen.getByTestId('layer-controls-canales')).toBeInTheDocument();
    // Master labels are dynamic. With one child on / one off (or all off), the
    // master reads "Encender todos los …".
    expect(screen.getByLabelText('Encender todos los relevados')).toBeInTheDocument();
    expect(screen.getByLabelText('Encender todos los propuestos')).toBeInTheDocument();
  });

  it('shows the "Apagar todos" master label when every child is on', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: true,
          canal_relevado_norte: true,
          canal_relevado_sur: true,
        }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
      />,
    );

    expect(screen.getByLabelText('Apagar todos los relevados')).toBeInTheDocument();
  });

  it('toggling a master calls onLayerVisibilityChange for the master flag', () => {
    const onLayerVisibilityChange = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ canales_relevados: false, canales_propuestos: false }}
        onLayerVisibilityChange={onLayerVisibilityChange}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
      />,
    );

    fireEvent.click(screen.getByLabelText('Encender todos los propuestos'));
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

describe('<LayerControlsPanel /> — per-canal rows', () => {
  it('renders one leaf row per canal in each side', () => {
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
      />,
    );

    for (const item of [...canalesRelevadosItems, ...canalesPropuestosItems]) {
      if (item.kind !== 'leaf') continue;
      expect(screen.getByTestId(`canal-toggle-${item.id}`)).toBeInTheDocument();
      expect(screen.getByLabelText(item.label)).toBeChecked();
    }
  });

  it('never disables per-canal rows, even when the master is OFF', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: false,
          canal_relevado_norte: false,
          canal_relevado_sur: false,
        }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
      />,
    );

    for (const item of canalesRelevadosItems) {
      if (item.kind !== 'leaf') continue;
      const checkbox = screen.getByLabelText(item.label) as HTMLInputElement;
      expect(checkbox).not.toBeDisabled();
    }
  });

  it('toggling a child calls onLayerVisibilityChange for that child id', () => {
    const onLayerVisibilityChange = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: true,
          canal_relevado_norte: true,
          canal_relevado_sur: false,
        }}
        onLayerVisibilityChange={onLayerVisibilityChange}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
      />,
    );

    fireEvent.click(screen.getByLabelText('Canal Sur'));
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('canal_relevado_sur', true);
  });

  it('auto-enables the master when a child is turned on while the master is OFF', () => {
    const onLayerVisibilityChange = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: false,
          canal_relevado_norte: false,
          canal_relevado_sur: false,
        }}
        onLayerVisibilityChange={onLayerVisibilityChange}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
      />,
    );

    fireEvent.click(screen.getByLabelText('Canal Norte'));
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('canal_relevado_norte', true);
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('canales_relevados', true);
  });

  it('master bulk-toggle propagates true to every child id (FF6)', () => {
    const onLayerVisibilityChange = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: false,
          canal_relevado_norte: false,
          canal_relevado_sur: false,
        }}
        onLayerVisibilityChange={onLayerVisibilityChange}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
      />,
    );

    fireEvent.click(screen.getByLabelText('Encender todos los relevados'));
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('canales_relevados', true);
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('canal_relevado_norte', true);
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('canal_relevado_sur', true);
  });
});

describe('<LayerControlsPanel /> — Canales active-count badge (FF1)', () => {
  function canalesControl() {
    return screen.getByRole('button', { name: /canales/i });
  }

  it('counts the number of visible canal children (not the master flags)', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: true,
          canal_relevado_norte: true,
          canal_relevado_sur: true,
        }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
      />,
    );

    expect(within(canalesControl()).getByText('2')).toBeInTheDocument();
  });

  it('drops the count when a child is toggled off', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{
          canales_relevados: true,
          canal_relevado_norte: true,
          canal_relevado_sur: false,
        }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
      />,
    );

    expect(within(canalesControl()).getByText('1')).toBeInTheDocument();
  });

  it('shows NO badge when the master flag is on but no child is visible (staleness guard)', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        // Master ON, every child OFF — the old master-flag count reported "1".
        vectorVisibility={{ canales_relevados: true, canales_propuestos: false }}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={canalesRelevadosItems}
        canalesPropuestosItems={canalesPropuestosItems}
      />,
    );

    expect(within(canalesControl()).queryByText('1')).not.toBeInTheDocument();
  });
});

describe('<LayerControlsPanel /> — canal groups (FF5)', () => {
  const groupEntry: CanalToggleEntry = {
    kind: 'group',
    folder: 'monte_lena',
    label: 'Monte Leña',
    children: [
      { id: 'canal_relevado_a', label: 'Tramo 1' },
      { id: 'canal_relevado_b', label: 'Tramo 2' },
    ],
  };

  it('renders a group control (CanalGroupRow) for a tramo_folder entry', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{}}
        onLayerVisibilityChange={() => {}}
        canalesRelevadosItems={[groupEntry]}
      />,
    );

    expect(screen.getByTestId('canal-group-monte_lena')).toBeInTheDocument();
  });

  it('the group bulk checkbox writes every child id at once', () => {
    const onLayerVisibilityChange = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{}}
        onLayerVisibilityChange={onLayerVisibilityChange}
        canalesRelevadosItems={[groupEntry]}
      />,
    );

    fireEvent.click(screen.getByLabelText('Toggle Monte Leña'));
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('canal_relevado_a', true);
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('canal_relevado_b', true);
  });
});
