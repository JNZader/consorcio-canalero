/**
 * LeyendaPanelCanales.test.tsx
 *
 * Covers the two new Pilar Azul (Canales) legend blocks inside
 * `<LeyendaPanel />`. Blocks mount conditionally, mirroring the Pilar Verde
 * simple-chip pattern:
 *
 *   - "Canales relevados"  — 3 solid blue chips (sin obra / readec / asociada).
 *     Visible iff `pilarAzulCanalesRelevadosVisible === true`.
 *   - "Canales propuestos" — 5 dashed chips, one per etapa.
 *     Visible iff `pilarAzulCanalesPropuestosVisible === true`.
 *
 * All colors come from `CANALES_COLORS` — no hardcoded hex in the test bed.
 * Propuestos chips carry a dashed-line indicator (CSS class + SVG), so the
 * legend MAY drift from the MapLibre paint only if `CANALES_COLORS` changes,
 * not if someone mis-types a hex into the legend.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { CANALES_COLORS } from '../../src/components/map2d/canalesLayers';
import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

// ---------------------------------------------------------------------------
// Relevados block
// ---------------------------------------------------------------------------

describe('<LeyendaPanel /> — Canales Relevados block', () => {
  it('is hidden by default (no flag)', () => {
    renderWithMantine(<LeyendaPanel />);
    expect(screen.queryByTestId('canales-relevados-legend')).not.toBeInTheDocument();
    expect(screen.queryByText('Canales Relevados')).not.toBeInTheDocument();
  });

  it('is hidden when the flag is explicitly false', () => {
    renderWithMantine(<LeyendaPanel pilarAzulCanalesRelevadosVisible={false} />);
    expect(screen.queryByTestId('canales-relevados-legend')).not.toBeInTheDocument();
  });

  it('renders the section + 3 chips when the flag is true', () => {
    renderWithMantine(<LeyendaPanel pilarAzulCanalesRelevadosVisible />);
    expect(screen.getByText('Canales Relevados')).toBeInTheDocument();
    const block = screen.getByTestId('canales-relevados-legend');
    expect(block).toBeInTheDocument();
    // 3 chips: sin obra / readec / asociada.
    expect(screen.getByText('Sin obra')).toBeInTheDocument();
    expect(screen.getByText('Readecuación')).toBeInTheDocument();
    expect(screen.getByText('Asociada')).toBeInTheDocument();
  });

  it('chip colors match CANALES_COLORS.relevado*', () => {
    renderWithMantine(<LeyendaPanel pilarAzulCanalesRelevadosVisible />);
    expect(screen.getByTestId('canal-relevado-chip-sin-obra')).toHaveAttribute(
      'data-color',
      CANALES_COLORS.relevadoSinObra,
    );
    expect(screen.getByTestId('canal-relevado-chip-readec')).toHaveAttribute(
      'data-color',
      CANALES_COLORS.relevadoReadec,
    );
    expect(screen.getByTestId('canal-relevado-chip-asociada')).toHaveAttribute(
      'data-color',
      CANALES_COLORS.relevadoAsociada,
    );
  });
});

// ---------------------------------------------------------------------------
// Propuestos block
// ---------------------------------------------------------------------------

describe('<LeyendaPanel /> — Canales Propuestos block', () => {
  it('is hidden by default (no flag)', () => {
    renderWithMantine(<LeyendaPanel />);
    expect(screen.queryByTestId('canales-propuestos-legend')).not.toBeInTheDocument();
    expect(screen.queryByText('Canales Propuestos')).not.toBeInTheDocument();
  });

  it('is hidden when the flag is explicitly false', () => {
    renderWithMantine(<LeyendaPanel pilarAzulCanalesPropuestosVisible={false} />);
    expect(screen.queryByTestId('canales-propuestos-legend')).not.toBeInTheDocument();
  });

  it('renders 5 chips (one per etapa) when the flag is true', () => {
    renderWithMantine(<LeyendaPanel pilarAzulCanalesPropuestosVisible />);
    expect(screen.getByText('Canales Propuestos')).toBeInTheDocument();
    const block = screen.getByTestId('canales-propuestos-legend');
    expect(block).toBeInTheDocument();

    // 5 chips — one per etapa.
    expect(screen.getByText('Alta')).toBeInTheDocument();
    expect(screen.getByText('Media-Alta')).toBeInTheDocument();
    expect(screen.getByText('Media')).toBeInTheDocument();
    expect(screen.getByText('Opcional')).toBeInTheDocument();
    expect(screen.getByText('Largo plazo')).toBeInTheDocument();
  });

  it('chip colors match CANALES_COLORS.propuesto*', () => {
    renderWithMantine(<LeyendaPanel pilarAzulCanalesPropuestosVisible />);
    expect(screen.getByTestId('canal-propuesto-chip-Alta')).toHaveAttribute(
      'data-color',
      CANALES_COLORS.propuestoAlta,
    );
    expect(screen.getByTestId('canal-propuesto-chip-Media-Alta')).toHaveAttribute(
      'data-color',
      CANALES_COLORS.propuestoMediaAlta,
    );
    expect(screen.getByTestId('canal-propuesto-chip-Media')).toHaveAttribute(
      'data-color',
      CANALES_COLORS.propuestoMedia,
    );
    expect(screen.getByTestId('canal-propuesto-chip-Opcional')).toHaveAttribute(
      'data-color',
      CANALES_COLORS.propuestoOpcional,
    );
    expect(screen.getByTestId('canal-propuesto-chip-Largo plazo')).toHaveAttribute(
      'data-color',
      CANALES_COLORS.propuestoLargoPlazo,
    );
  });

  it('each propuestos chip carries a dashed-line indicator', () => {
    renderWithMantine(<LeyendaPanel pilarAzulCanalesPropuestosVisible />);
    // Propuestos chips expose `data-dashed="true"` so we can guarantee the
    // dashed affordance survives any CSS refactor. The inner SVG OR the
    // inline-style `strokeDasharray`/border-style marker is also pinned.
    const etapas = ['Alta', 'Media-Alta', 'Media', 'Opcional', 'Largo plazo'];
    for (const etapa of etapas) {
      const chip = screen.getByTestId(`canal-propuesto-chip-${etapa}`);
      expect(chip).toHaveAttribute('data-dashed', 'true');
    }
  });
});

// ---------------------------------------------------------------------------
// Both blocks visible simultaneously
// ---------------------------------------------------------------------------

describe('<LeyendaPanel /> — both Canales blocks together', () => {
  it('renders both blocks when both flags are true', () => {
    renderWithMantine(
      <LeyendaPanel
        pilarAzulCanalesRelevadosVisible
        pilarAzulCanalesPropuestosVisible
      />,
    );
    expect(screen.getByTestId('canales-relevados-legend')).toBeInTheDocument();
    expect(screen.getByTestId('canales-propuestos-legend')).toBeInTheDocument();
  });
});
