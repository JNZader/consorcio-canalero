/**
 * TerrainLayerTogglesPanelPilarVerde.test.tsx
 *
 * Phase 3 (Batch D) of `pilar-verde-y-canales-3d` — extends the 3D toggles
 * panel with a "Pilar Verde" CollapsibleSection (5 checkboxes, all default
 * OFF per `PILAR_VERDE_DEFAULT_VISIBILITY`) and a "Canales" CollapsibleSection
 * with 2 master toggles.
 *
 * Tests assert:
 *   1. "Pilar Verde" section renders with 5 checkboxes in canonical order,
 *      ALL unchecked by default (matches `PILAR_VERDE_DEFAULT_VISIBILITY`).
 *   2. Clicking a Pilar Verde checkbox calls
 *      `onVectorLayerToggle(layerId, true)`.
 *   3. "Canales" section renders 2 master checkboxes (relevados default ON,
 *      propuestos default OFF — matches `PILAR_AZUL_DEFAULT_VISIBILITY`).
 *   4. Clicking "Canales propuestos" calls
 *      `onVectorLayerToggle('canales_propuestos', true)`.
 *
 * The propuestos etapas filter (Alta → Largo plazo) used to mount in the
 * Canales section here, but moved to `TerrainLegendsPanel` as interactive
 * checkboxes (single source of truth — same chip both displays the color
 * and toggles its etapa). Its tests live with the standalone component
 * (`PropuestasEtapasFilter.test.tsx`).
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLayerTogglesPanel } from '../../src/components/terrain/TerrainLayerTogglesPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function makeBaseProps(overrides?: {
  vectorLayerVisibility?: Record<string, boolean>;
  onVectorLayerToggle?: ReturnType<typeof vi.fn>;
}) {
  return {
    rasterLayers: [],
    selectedImageOption: null,
    activeRasterLayerId: undefined,
    onActiveRasterLayerChange: vi.fn(),
    overlayOpacity: 0.7,
    onOverlayOpacityChange: vi.fn(),
    vectorLayerVisibility: overrides?.vectorLayerVisibility ?? {
      // Matches PILAR_VERDE_DEFAULT_VISIBILITY + PILAR_AZUL_DEFAULT_VISIBILITY
      pilar_verde_bpa_historico: false,
      pilar_verde_agro_aceptada: false,
      pilar_verde_agro_presentada: false,
      pilar_verde_agro_zonas: false,
      pilar_verde_porcentaje_forestacion: false,
      canales_relevados: true,
      canales_propuestos: false,
      canal_relevado_norte: true,
      canal_propuesto_sur: false,
    },
    onVectorLayerToggle: overrides?.onVectorLayerToggle ?? vi.fn(),
    onClose: vi.fn(),
    hasApprovedZones: false,
    // The shared CanalesLayerSection renders nothing without per-canal
    // entries (masters were replaced by bulk "Encender/Apagar todos" rows).
    canalesRelevadosItems: [
      { kind: 'leaf', id: 'canal_relevado_norte', label: 'Canal Norte' },
    ] as const,
    canalesPropuestosItems: [
      { kind: 'leaf', id: 'canal_propuesto_sur', label: 'Canal Sur' },
    ] as const,
  };
}

describe('<TerrainLayerTogglesPanel /> — Pilar Verde section', () => {
  it('renders a "Pilar Verde" CollapsibleSection', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...makeBaseProps()} />);

    // The section title is rendered by CollapsibleSection as a <Text>.
    expect(screen.getByText('Pilar Verde')).toBeInTheDocument();
  });

  it('renders the 5 Pilar Verde checkboxes with the spec-mandated labels', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...makeBaseProps()} />);

    // Labels from Task 3.1 (Batch D orchestrator spec).
    expect(screen.getByLabelText(/BPA histórico \(por años\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Agroforestal: Cumplen/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Agroforestal: Presentaron/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Zonas Agroforestales/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/% Forestación obligatoria/i)).toBeInTheDocument();
  });

  it('defaults ALL 5 Pilar Verde checkboxes to UNCHECKED', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...makeBaseProps()} />);

    expect(screen.getByLabelText(/BPA histórico \(por años\)/i)).not.toBeChecked();
    expect(screen.getByLabelText(/Agroforestal: Cumplen/i)).not.toBeChecked();
    expect(screen.getByLabelText(/Agroforestal: Presentaron/i)).not.toBeChecked();
    expect(screen.getByLabelText(/Zonas Agroforestales/i)).not.toBeChecked();
    expect(screen.getByLabelText(/% Forestación obligatoria/i)).not.toBeChecked();
  });

  it('calls onVectorLayerToggle with the correct layer id when a Pilar Verde checkbox is clicked', () => {
    const onVectorLayerToggle = vi.fn();
    renderWithMantine(
      <TerrainLayerTogglesPanel {...makeBaseProps({ onVectorLayerToggle })} />,
    );

    fireEvent.click(screen.getByLabelText(/BPA histórico \(por años\)/i));

    expect(onVectorLayerToggle).toHaveBeenCalledWith('pilar_verde_bpa_historico', true);
  });
});

describe('<TerrainLayerTogglesPanel /> — Canales section', () => {
  it('renders a "Canales" CollapsibleSection', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...makeBaseProps()} />);

    expect(screen.getByText('Canales')).toBeInTheDocument();
  });

  it('renders 2 master checkboxes with the correct defaults (relevados ON, propuestos OFF)', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...makeBaseProps()} />);

    // Shared CanalesLayerSection (893ab58): masters are bulk toggles whose
    // label flips between "Encender/Apagar todos los {side}".
    const relevados = screen.getByLabelText('Apagar todos los relevados');
    const propuestos = screen.getByLabelText('Encender todos los propuestos');

    expect(relevados).toBeChecked();
    expect(propuestos).not.toBeChecked();
  });

  it('calls onVectorLayerToggle("canales_propuestos", true) when the propuestos master is clicked', () => {
    const onVectorLayerToggle = vi.fn();
    renderWithMantine(
      <TerrainLayerTogglesPanel {...makeBaseProps({ onVectorLayerToggle })} />,
    );

    fireEvent.click(screen.getByLabelText('Encender todos los propuestos'));

    expect(onVectorLayerToggle).toHaveBeenCalledWith('canales_propuestos', true);
  });
});

