/**
 * TerrainLayerTogglesPanelIDECorAttribution.test.tsx
 *
 * Phase 4 (Batch E) of `pilar-verde-y-canales-3d` — divergence fix:
 *
 *   The 2D `LayerControlsPanel` shows a small dimmed footer
 *   "Datos: IDECor — Gobierno de Córdoba" whenever any layer backed by
 *   IDECor data (currently the Pilar Verde family — see `layerAttributions.ts`)
 *   is visible. The 3D toggles panel was initially shipped WITHOUT the
 *   attribution footer, creating a visual + legal divergence between 2D and 3D.
 *
 *   Fix: mirror the 2D pattern by reading `getActiveAttributions(visibleVectors)`
 *   from `../map2d/layerAttributions` (map-agnostic helper — reuse as-is) and
 *   render one `<Text size="xs" c="dimmed">` per active attribution at the
 *   bottom of the toggles panel.
 *
 *   Contract:
 *     - When ANY Pilar Verde layer is visible, the footer text
 *       "Datos: IDECor — Gobierno de Córdoba" MUST render.
 *     - When NO IDECor-backed layer is visible, the footer MUST NOT render.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLayerTogglesPanel } from '../../src/components/terrain/TerrainLayerTogglesPanel';
import type { Etapa } from '../../src/types/canales';

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

function makeBaseProps(vectorLayerVisibility: Record<string, boolean>) {
  return {
    rasterLayers: [],
    selectedImageOption: null,
    activeRasterLayerId: undefined,
    onActiveRasterLayerChange: vi.fn(),
    overlayOpacity: 0.7,
    onOverlayOpacityChange: vi.fn(),
    vectorLayerVisibility,
    onVectorLayerToggle: vi.fn(),
    onClose: vi.fn(),
    hasApprovedZones: false,
    etapasVisibility: defaultEtapasVisibility,
    onSetEtapaVisible: vi.fn(),
  };
}

const IDECOR_ATTRIBUTION = 'Datos: IDECor — Gobierno de Córdoba';

describe('<TerrainLayerTogglesPanel /> — IDECor attribution footer', () => {
  it('renders the IDECor attribution when a Pilar Verde layer (bpa_historico) is visible', () => {
    renderWithMantine(
      <TerrainLayerTogglesPanel
        {...makeBaseProps({
          pilar_verde_bpa_historico: true,
          pilar_verde_agro_aceptada: false,
          pilar_verde_agro_presentada: false,
          pilar_verde_agro_zonas: false,
          pilar_verde_porcentaje_forestacion: false,
          canales_relevados: false,
          canales_propuestos: false,
        })}
      />,
    );

    expect(screen.getByText(IDECOR_ATTRIBUTION)).toBeInTheDocument();
  });

  it('renders the IDECor attribution when ANY Pilar Verde layer is visible (agro_zonas)', () => {
    renderWithMantine(
      <TerrainLayerTogglesPanel
        {...makeBaseProps({
          pilar_verde_bpa_historico: false,
          pilar_verde_agro_aceptada: false,
          pilar_verde_agro_presentada: false,
          pilar_verde_agro_zonas: true,
          pilar_verde_porcentaje_forestacion: false,
          canales_relevados: false,
          canales_propuestos: false,
        })}
      />,
    );

    expect(screen.getByText(IDECOR_ATTRIBUTION)).toBeInTheDocument();
  });

  it('does NOT render the IDECor attribution when no IDECor-backed layer is visible', () => {
    renderWithMantine(
      <TerrainLayerTogglesPanel
        {...makeBaseProps({
          pilar_verde_bpa_historico: false,
          pilar_verde_agro_aceptada: false,
          pilar_verde_agro_presentada: false,
          pilar_verde_agro_zonas: false,
          pilar_verde_porcentaje_forestacion: false,
          // Canales layers are NOT IDECor-backed — they must not trigger the
          // attribution.
          canales_relevados: true,
          canales_propuestos: true,
        })}
      />,
    );

    expect(screen.queryByText(IDECOR_ATTRIBUTION)).not.toBeInTheDocument();
  });

  it('does NOT render the IDECor attribution when ALL layers are hidden', () => {
    renderWithMantine(
      <TerrainLayerTogglesPanel
        {...makeBaseProps({
          pilar_verde_bpa_historico: false,
          pilar_verde_agro_aceptada: false,
          pilar_verde_agro_presentada: false,
          pilar_verde_agro_zonas: false,
          pilar_verde_porcentaje_forestacion: false,
          canales_relevados: false,
          canales_propuestos: false,
        })}
      />,
    );

    expect(screen.queryByText(IDECOR_ATTRIBUTION)).not.toBeInTheDocument();
  });
});
