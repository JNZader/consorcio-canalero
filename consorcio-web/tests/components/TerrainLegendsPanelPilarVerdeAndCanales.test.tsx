/**
 * TerrainLegendsPanelPilarVerdeAndCanales.test.tsx
 *
 * Phase 4 (Batch E) of `pilar-verde-y-canales-3d` — extends the 3D legends
 * panel with 7 conditional blocks mirroring the 2D `LeyendaPanel`:
 *   - BPA histórico 4-chip gradient (años 1 / 3 / 5 / 7)
 *   - Agro aceptada single chip
 *   - Agro presentada single chip
 *   - Agro zonas 3-chip warm block
 *   - Porcentaje forestación 3-tier violet block
 *   - Canales relevados single SOLID chip (medium blue — `readec`)
 *   - Canales propuestos 5-chip DASHED block (one per etapa)
 *
 * Rules:
 *   - ALL colors sourced from `PILAR_VERDE_COLORS` / `CANALES_COLORS` — no
 *     hardcoded hexes in this test file (single source of truth — same map
 *     constants feed the MapLibre paints).
 *   - Each block renders ONLY when its matching `*Visible` prop is true.
 *   - Dashed chips for propuestos carry `data-dashed="true"` for deterministic
 *     DOM assertions.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLegendsPanel } from '../../src/components/terrain/TerrainLegendsPanel';
import { CANALES_COLORS } from '../../src/components/map2d/canalesLayers';
import { PILAR_VERDE_COLORS } from '../../src/components/map2d/pilarVerdeLayers';
import { ALL_ETAPAS } from '../../src/types/canales';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const baseProps = {
  activeRasterType: undefined,
  hiddenClasses: {} as Record<string, number[]>,
  onClassToggle: vi.fn(),
  hiddenRanges: {} as Record<string, number[]>,
  onRangeToggle: vi.fn(),
  // Default: soil ON so the panel doesn't short-circuit to `null` — gives us
  // a parent container that the conditional PV/Canales blocks can mount
  // alongside.
  vectorLayerVisibility: { soil: true } as Record<string, boolean>,
} as const;

describe('<TerrainLegendsPanel /> — BPA histórico gradient strip', () => {
  it('renders the "Años en BPA" title + 4 chips when bpaHistoricoVisible === true', () => {
    renderWithMantine(
      <TerrainLegendsPanel {...baseProps} bpaHistoricoVisible />,
    );

    expect(screen.getByText(/Años en BPA/i)).toBeInTheDocument();

    // 4 chips, aria-labeled by año count (1, 3, 5, 7), color pulled from
    // PILAR_VERDE_COLORS.bpaHistoricoStop{N}.
    const chipStops = [
      { label: '1', color: PILAR_VERDE_COLORS.bpaHistoricoStop1 },
      { label: '3', color: PILAR_VERDE_COLORS.bpaHistoricoStop3 },
      { label: '5', color: PILAR_VERDE_COLORS.bpaHistoricoStop5 },
      { label: '7', color: PILAR_VERDE_COLORS.bpaHistoricoStop7 },
    ] as const;

    for (const { label, color } of chipStops) {
      const chip = screen.getByLabelText(label);
      expect(chip).toBeInTheDocument();
      expect(chip.getAttribute('style') ?? '').toContain(color);
    }
  });

  it('does NOT render the BPA histórico block when bpaHistoricoVisible is false (default)', () => {
    renderWithMantine(<TerrainLegendsPanel {...baseProps} />);

    expect(screen.queryByText(/Años en BPA/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('1')).not.toBeInTheDocument();
  });
});

describe('<TerrainLegendsPanel /> — Agro aceptada / presentada single chips', () => {
  it('renders the Agro aceptada chip with label "Cumplen ley forestal" and PILAR_VERDE_COLORS.agroAceptadaFill', () => {
    renderWithMantine(
      <TerrainLegendsPanel {...baseProps} agroAceptadaVisible />,
    );

    const chip = screen.getByTestId('terrain-3d-agro-aceptada-legend');
    expect(chip).toBeInTheDocument();
    expect(chip.textContent).toContain('Cumplen ley forestal');
    expect(chip.getAttribute('data-color')).toBe(PILAR_VERDE_COLORS.agroAceptadaFill);
  });

  it('renders the Agro presentada chip with label "No cumplen ley forestal" and PILAR_VERDE_COLORS.agroPresentadaFill', () => {
    renderWithMantine(
      <TerrainLegendsPanel {...baseProps} agroPresentadaVisible />,
    );

    const chip = screen.getByTestId('terrain-3d-agro-presentada-legend');
    expect(chip).toBeInTheDocument();
    expect(chip.textContent).toContain('No cumplen ley forestal');
    expect(chip.getAttribute('data-color')).toBe(
      PILAR_VERDE_COLORS.agroPresentadaFill,
    );
  });

  it('hides each chip when its visibility flag is false', () => {
    renderWithMantine(<TerrainLegendsPanel {...baseProps} />);

    expect(screen.queryByTestId('terrain-3d-agro-aceptada-legend')).not.toBeInTheDocument();
    expect(screen.queryByTestId('terrain-3d-agro-presentada-legend')).not.toBeInTheDocument();
  });
});

describe('<TerrainLegendsPanel /> — Agro zonas 3-chip block', () => {
  it('renders the 3-chip block with title "Zonas agroforestales" + 3 labeled chips', () => {
    renderWithMantine(<TerrainLegendsPanel {...baseProps} agroZonasVisible />);

    expect(screen.getByText(/Zonas agroforestales/i)).toBeInTheDocument();

    const rioTercero = screen.getByTestId('terrain-3d-agro-zonas-legend-rio-tercero');
    const carcarana = screen.getByTestId('terrain-3d-agro-zonas-legend-carcarana');
    const tortugas = screen.getByTestId('terrain-3d-agro-zonas-legend-tortugas');

    expect(rioTercero.textContent).toContain('Río Tercero Este');
    expect(rioTercero.getAttribute('data-color')).toBe(
      PILAR_VERDE_COLORS.agroZonaRioTercero,
    );
    expect(carcarana.textContent).toContain('Río Carcarañá');
    expect(carcarana.getAttribute('data-color')).toBe(
      PILAR_VERDE_COLORS.agroZonaCarcarana,
    );
    expect(tortugas.textContent).toContain('Arroyo Tortugas Este');
    expect(tortugas.getAttribute('data-color')).toBe(
      PILAR_VERDE_COLORS.agroZonaTortugas,
    );
  });

  it('does NOT render the Agro zonas block when agroZonasVisible is false', () => {
    renderWithMantine(<TerrainLegendsPanel {...baseProps} />);

    expect(screen.queryByText(/Zonas agroforestales/i)).not.toBeInTheDocument();
  });
});

describe('<TerrainLegendsPanel /> — Porcentaje forestación 3-tier block', () => {
  it('renders the 3-tier block with title "Forestación obligatoria" + 3 labeled tiers', () => {
    renderWithMantine(
      <TerrainLegendsPanel {...baseProps} porcentajeForestacionVisible />,
    );

    expect(screen.getByText(/Forestación obligatoria/i)).toBeInTheDocument();

    const baja = screen.getByTestId('terrain-3d-porcentaje-forestacion-baja');
    const media = screen.getByTestId('terrain-3d-porcentaje-forestacion-media');
    const alta = screen.getByTestId('terrain-3d-porcentaje-forestacion-alta');

    expect(baja.textContent).toContain('Baja (≤ 2,3%)');
    expect(baja.getAttribute('data-color')).toBe(
      PILAR_VERDE_COLORS.porcentajeForestacionBaja,
    );
    expect(media.textContent).toContain('Media (2,4 – 2,6%)');
    expect(media.getAttribute('data-color')).toBe(
      PILAR_VERDE_COLORS.porcentajeForestacionMedia,
    );
    expect(alta.textContent).toContain('Alta (≥ 2,7%)');
    expect(alta.getAttribute('data-color')).toBe(
      PILAR_VERDE_COLORS.porcentajeForestacionAlta,
    );
  });

  it('does NOT render the Porcentaje forestación block when the flag is false', () => {
    renderWithMantine(<TerrainLegendsPanel {...baseProps} />);

    expect(screen.queryByText(/Forestación obligatoria/i)).not.toBeInTheDocument();
  });
});

describe('<TerrainLegendsPanel /> — Canales relevados 3-chip SOLID block', () => {
  it('renders title "Canales relevados" + 3 SOLID chips (Sin obra / Readecuación / Asociada) mirroring 2D', () => {
    renderWithMantine(
      <TerrainLegendsPanel {...baseProps} canalesRelevadosVisible />,
    );

    expect(screen.getByText(/Canales relevados/i)).toBeInTheDocument();

    const expected = [
      {
        testId: 'terrain-3d-canal-relevado-chip-sin-obra',
        label: 'Sin obra',
        color: CANALES_COLORS.relevadoSinObra,
      },
      {
        testId: 'terrain-3d-canal-relevado-chip-readec',
        label: 'Readecuación',
        color: CANALES_COLORS.relevadoReadec,
      },
      {
        testId: 'terrain-3d-canal-relevado-chip-asociada',
        label: 'Asociada',
        color: CANALES_COLORS.relevadoAsociada,
      },
    ] as const;

    for (const { testId, label, color } of expected) {
      const chip = screen.getByTestId(testId);
      expect(chip).toBeInTheDocument();
      expect(chip.textContent).toContain(label);
      expect(chip.getAttribute('data-color')).toBe(color);
      // SOLID chips — explicitly NOT dashed (contrasts with propuestos).
      expect(chip.getAttribute('data-dashed')).not.toBe('true');
    }
  });

  it('does NOT render the relevados chips when the flag is false', () => {
    renderWithMantine(<TerrainLegendsPanel {...baseProps} />);

    expect(
      screen.queryByTestId('terrain-3d-canal-relevado-chip-sin-obra'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('terrain-3d-canal-relevado-chip-readec'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('terrain-3d-canal-relevado-chip-asociada'),
    ).not.toBeInTheDocument();
  });
});

describe('<TerrainLegendsPanel /> — Canales propuestos 5-chip DASHED block', () => {
  it('renders title "Canales propuestos" + 5 dashed chips in etapa order', () => {
    renderWithMantine(
      <TerrainLegendsPanel {...baseProps} canalesPropuestosVisible />,
    );

    expect(screen.getByText(/Canales propuestos/i)).toBeInTheDocument();

    const expected = {
      Alta: CANALES_COLORS.propuestoAlta,
      'Media-Alta': CANALES_COLORS.propuestoMediaAlta,
      Media: CANALES_COLORS.propuestoMedia,
      Opcional: CANALES_COLORS.propuestoOpcional,
      'Largo plazo': CANALES_COLORS.propuestoLargoPlazo,
    } as const;

    for (const etapa of ALL_ETAPAS) {
      const chip = screen.getByTestId(`terrain-3d-canales-propuestos-chip-${etapa}`);
      expect(chip).toBeInTheDocument();
      // Every propuesto chip MUST carry the dashed marker for deterministic
      // DOM assertions — this is the contract with the visual line layer.
      expect(chip.getAttribute('data-dashed')).toBe('true');
      expect(chip.getAttribute('data-color')).toBe(expected[etapa]);
      expect(chip.textContent).toContain(etapa);
    }
  });

  it('does NOT render the propuestos block when the flag is false', () => {
    renderWithMantine(<TerrainLegendsPanel {...baseProps} />);

    expect(screen.queryByText(/Canales propuestos/i)).not.toBeInTheDocument();
  });
});

describe('<TerrainLegendsPanel /> — panel mounts even without soil when a PV flag is ON', () => {
  it('mounts when ONLY bpaHistoricoVisible is true (no soil, no raster)', () => {
    renderWithMantine(
      <TerrainLegendsPanel
        activeRasterType={undefined}
        hiddenClasses={{}}
        onClassToggle={vi.fn()}
        hiddenRanges={{}}
        onRangeToggle={vi.fn()}
        vectorLayerVisibility={{}}
        bpaHistoricoVisible
      />,
    );

    // Panel root MUST render when any PV/Canales flag is ON — otherwise the
    // legend blocks have no container to mount into and the user sees nothing
    // when they toggle PV layers with soil + raster both off.
    expect(screen.getByTestId('terrain-3d-legends-panel')).toBeInTheDocument();
    expect(screen.getByText(/Años en BPA/i)).toBeInTheDocument();
  });
});
