/**
 * TerrainLayerTogglesPanelPilarVerde.test.tsx
 *
 * Phase 3 (Batch D) of `pilar-verde-y-canales-3d` — extends the 3D toggles
 * panel with a "Pilar Verde" CollapsibleSection (5 checkboxes, all default
 * OFF per `PILAR_VERDE_DEFAULT_VISIBILITY`) and a "Canales" CollapsibleSection
 * with 2 master toggles + a conditional `<PropuestasEtapasFilter>` that
 * UNMOUNTS when the propuestos master is OFF (matches 2D spec).
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
 *   5. `<PropuestasEtapasFilter>` is NOT in the DOM when
 *      `vectorLayerVisibility.canales_propuestos === false`.
 *   6. `<PropuestasEtapasFilter>` IS in the DOM when
 *      `vectorLayerVisibility.canales_propuestos === true`, renders 5 etapa
 *      checkboxes reflecting `etapasVisibility`, and clicking one calls
 *      `onSetEtapaVisible(etapa, bool)`.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLayerTogglesPanel } from '../../src/components/terrain/TerrainLayerTogglesPanel';
import { ALL_ETAPAS, type Etapa } from '../../src/types/canales';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const defaultEtapasVisibility: Record<Etapa, boolean> = {
  Alta: true,
  'Media-Alta': true,
  Media: true,
  Opcional: true,
  'Largo plazo': true,
};

function makeBaseProps(overrides?: {
  vectorLayerVisibility?: Record<string, boolean>;
  etapasVisibility?: Record<Etapa, boolean>;
  onVectorLayerToggle?: ReturnType<typeof vi.fn>;
  onSetEtapaVisible?: ReturnType<typeof vi.fn>;
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
    },
    onVectorLayerToggle: overrides?.onVectorLayerToggle ?? vi.fn(),
    onClose: vi.fn(),
    hasApprovedZones: false,
    etapasVisibility: overrides?.etapasVisibility ?? defaultEtapasVisibility,
    onSetEtapaVisible: overrides?.onSetEtapaVisible ?? vi.fn(),
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

    const relevados = screen.getByLabelText('Canales relevados');
    const propuestos = screen.getByLabelText('Canales propuestos');

    expect(relevados).toBeChecked();
    expect(propuestos).not.toBeChecked();
  });

  it('calls onVectorLayerToggle("canales_propuestos", true) when the propuestos master is clicked', () => {
    const onVectorLayerToggle = vi.fn();
    renderWithMantine(
      <TerrainLayerTogglesPanel {...makeBaseProps({ onVectorLayerToggle })} />,
    );

    fireEvent.click(screen.getByLabelText('Canales propuestos'));

    expect(onVectorLayerToggle).toHaveBeenCalledWith('canales_propuestos', true);
  });
});

describe('<TerrainLayerTogglesPanel /> — PropuestasEtapasFilter conditional mount', () => {
  it('does NOT mount the etapas filter when propuestos master is OFF', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...makeBaseProps()} />);

    // The filter renders a Stack with data-testid="propuestas-etapas-filter".
    expect(screen.queryByTestId('propuestas-etapas-filter')).not.toBeInTheDocument();
    // And its heading "Etapas propuestas" must not be present.
    expect(screen.queryByText(/Etapas propuestas/i)).not.toBeInTheDocument();
  });

  it('mounts the etapas filter with 5 etapa checkboxes when propuestos master is ON', () => {
    const props = makeBaseProps({
      vectorLayerVisibility: {
        pilar_verde_bpa_historico: false,
        pilar_verde_agro_aceptada: false,
        pilar_verde_agro_presentada: false,
        pilar_verde_agro_zonas: false,
        pilar_verde_porcentaje_forestacion: false,
        canales_relevados: true,
        canales_propuestos: true,
      },
    });
    renderWithMantine(<TerrainLayerTogglesPanel {...props} />);

    expect(screen.getByTestId('propuestas-etapas-filter')).toBeInTheDocument();
    // Anchor each regex to avoid "Alta" matching inside "Media-Alta" — the
    // checkboxes render the etapa string as the ONLY text content of the
    // label (after the color dot span), so `^Etapa$` is safe.
    for (const etapa of ALL_ETAPAS) {
      // Escape regex-special chars in the etapa string (e.g. "-").
      const escaped = etapa.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      expect(screen.getByLabelText(new RegExp(`^${escaped}$`, 'i'))).toBeInTheDocument();
    }
  });

  it('reflects etapasVisibility in the etapa checkbox state', () => {
    const props = makeBaseProps({
      vectorLayerVisibility: {
        pilar_verde_bpa_historico: false,
        pilar_verde_agro_aceptada: false,
        pilar_verde_agro_presentada: false,
        pilar_verde_agro_zonas: false,
        pilar_verde_porcentaje_forestacion: false,
        canales_relevados: true,
        canales_propuestos: true,
      },
      etapasVisibility: {
        Alta: false,
        'Media-Alta': true,
        Media: true,
        Opcional: true,
        'Largo plazo': true,
      },
    });
    renderWithMantine(<TerrainLayerTogglesPanel {...props} />);

    expect(screen.getByLabelText(/^Alta$/i)).not.toBeChecked();
    expect(screen.getByLabelText(/^Media-Alta$/i)).toBeChecked();
  });

  it('calls onSetEtapaVisible when an etapa checkbox is clicked', () => {
    const onSetEtapaVisible = vi.fn();
    const props = makeBaseProps({
      vectorLayerVisibility: {
        pilar_verde_bpa_historico: false,
        pilar_verde_agro_aceptada: false,
        pilar_verde_agro_presentada: false,
        pilar_verde_agro_zonas: false,
        pilar_verde_porcentaje_forestacion: false,
        canales_relevados: true,
        canales_propuestos: true,
      },
      onSetEtapaVisible,
    });
    renderWithMantine(<TerrainLayerTogglesPanel {...props} />);

    // Click 'Alta' — it was TRUE in defaults, click should flip to FALSE.
    fireEvent.click(screen.getByLabelText(/^Alta$/i));

    expect(onSetEtapaVisible).toHaveBeenCalledWith('Alta', false);
  });
});
