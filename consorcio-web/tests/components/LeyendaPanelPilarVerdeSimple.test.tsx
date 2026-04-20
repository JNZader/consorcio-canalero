/**
 * LeyendaPanelPilarVerdeSimple.test.tsx
 *
 * Companion tests for the simple (single-chip) Pilar Verde legends in
 * `<LeyendaPanel />`. Sibling of `LeyendaPanelBpaHistorico.test.tsx`.
 *
 * 4 layers, 4 conditional legend blocks — each rendered only when its
 * corresponding visibility prop is `true`:
 *   1. pilar_verde_agro_aceptada       → green  "Cumplen ley forestal"
 *   2. pilar_verde_agro_presentada     → red    "No cumplen ley forestal"
 *   3. pilar_verde_agro_zonas          → cyan   "Zonas agroforestales"
 *   4. pilar_verde_porcentaje_forestacion → violet "Forestación obligatoria (2-5%)"
 *
 * Colors MUST come from `PILAR_VERDE_COLORS` (single source of truth) so the
 * legend never drifts from the MapLibre paint.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';
import { PILAR_VERDE_COLORS } from '../../src/components/map2d/pilarVerdeLayers';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const LABEL_ACEPTADA = 'Cumplen ley forestal';
const LABEL_PRESENTADA = 'No cumplen ley forestal';
const LABEL_ZONAS = 'Zonas agroforestales';
const TITLE_PORCENTAJE = 'Forestación obligatoria';
// Spanish comma decimal separator (NOT dot). Tier buckets match the
// categorized `step` paint expression in `buildPorcentajeForestacionFillPaint`.
const LABEL_PORCENTAJE_BAJA = 'Baja (≤ 2,3%)';
const LABEL_PORCENTAJE_MEDIA = 'Media (2,4 – 2,6%)';
const LABEL_PORCENTAJE_ALTA = 'Alta (≥ 2,7%)';

const TESTID_ACEPTADA = 'pilar-verde-agro-aceptada-legend';
const TESTID_PRESENTADA = 'pilar-verde-agro-presentada-legend';
const TESTID_ZONAS = 'pilar-verde-agro-zonas-legend';
const TESTID_PORCENTAJE = 'pilar-verde-porcentaje-forestacion-legend';
const TESTID_PORCENTAJE_BAJA = 'pilar-verde-porcentaje-forestacion-baja';
const TESTID_PORCENTAJE_MEDIA = 'pilar-verde-porcentaje-forestacion-media';
const TESTID_PORCENTAJE_ALTA = 'pilar-verde-porcentaje-forestacion-alta';

describe('<LeyendaPanel /> — simple Pilar Verde legends (agro + porcentaje)', () => {
  describe('defaults', () => {
    it('does NOT render any of the 4 simple legends by default', () => {
      renderWithMantine(<LeyendaPanel />);
      expect(screen.queryByText(LABEL_ACEPTADA)).not.toBeInTheDocument();
      expect(screen.queryByText(LABEL_PRESENTADA)).not.toBeInTheDocument();
      expect(screen.queryByText(LABEL_ZONAS)).not.toBeInTheDocument();
      expect(screen.queryByText(TITLE_PORCENTAJE)).not.toBeInTheDocument();
      expect(screen.queryByText(LABEL_PORCENTAJE_BAJA)).not.toBeInTheDocument();
      expect(screen.queryByText(LABEL_PORCENTAJE_MEDIA)).not.toBeInTheDocument();
      expect(screen.queryByText(LABEL_PORCENTAJE_ALTA)).not.toBeInTheDocument();
    });

    it('does NOT render any of the 4 simple legends when flags are explicitly false', () => {
      renderWithMantine(
        <LeyendaPanel
          pilarVerdeAgroAceptadaVisible={false}
          pilarVerdeAgroPresentadaVisible={false}
          pilarVerdeAgroZonasVisible={false}
          pilarVerdePorcentajeForestacionVisible={false}
        />,
      );
      expect(screen.queryByTestId(TESTID_ACEPTADA)).not.toBeInTheDocument();
      expect(screen.queryByTestId(TESTID_PRESENTADA)).not.toBeInTheDocument();
      expect(screen.queryByTestId(TESTID_ZONAS)).not.toBeInTheDocument();
      expect(screen.queryByTestId(TESTID_PORCENTAJE)).not.toBeInTheDocument();
    });
  });

  describe('agro_aceptada (verde — cumplen ley forestal)', () => {
    it('renders when its flag is true with exact Spanish label', () => {
      renderWithMantine(<LeyendaPanel pilarVerdeAgroAceptadaVisible />);
      expect(screen.getByTestId(TESTID_ACEPTADA)).toBeInTheDocument();
      expect(screen.getByText(LABEL_ACEPTADA)).toBeInTheDocument();
    });

    it('chip color matches PILAR_VERDE_COLORS.agroAceptadaFill (single source of truth)', () => {
      renderWithMantine(<LeyendaPanel pilarVerdeAgroAceptadaVisible />);
      const chip = screen.getByLabelText(LABEL_ACEPTADA);
      expect(chip).toHaveAttribute('data-color', PILAR_VERDE_COLORS.agroAceptadaFill);
    });

    it('is hidden when only other flags are on', () => {
      renderWithMantine(<LeyendaPanel pilarVerdeAgroPresentadaVisible />);
      expect(screen.queryByTestId(TESTID_ACEPTADA)).not.toBeInTheDocument();
    });
  });

  describe('agro_presentada (rojo — no cumplen ley forestal)', () => {
    it('renders when its flag is true with exact Spanish label', () => {
      renderWithMantine(<LeyendaPanel pilarVerdeAgroPresentadaVisible />);
      expect(screen.getByTestId(TESTID_PRESENTADA)).toBeInTheDocument();
      expect(screen.getByText(LABEL_PRESENTADA)).toBeInTheDocument();
    });

    it('chip color matches PILAR_VERDE_COLORS.agroPresentadaFill (single source of truth)', () => {
      renderWithMantine(<LeyendaPanel pilarVerdeAgroPresentadaVisible />);
      const chip = screen.getByLabelText(LABEL_PRESENTADA);
      expect(chip).toHaveAttribute('data-color', PILAR_VERDE_COLORS.agroPresentadaFill);
    });

    it('is hidden when only other flags are on', () => {
      renderWithMantine(<LeyendaPanel pilarVerdeAgroZonasVisible />);
      expect(screen.queryByTestId(TESTID_PRESENTADA)).not.toBeInTheDocument();
    });
  });

  describe('agro_zonas (cian — zonas agroforestales)', () => {
    it('renders when its flag is true with exact Spanish label', () => {
      renderWithMantine(<LeyendaPanel pilarVerdeAgroZonasVisible />);
      expect(screen.getByTestId(TESTID_ZONAS)).toBeInTheDocument();
      expect(screen.getByText(LABEL_ZONAS)).toBeInTheDocument();
    });

    it('chip color matches PILAR_VERDE_COLORS.agroZonasFill (single source of truth)', () => {
      renderWithMantine(<LeyendaPanel pilarVerdeAgroZonasVisible />);
      const chip = screen.getByLabelText(LABEL_ZONAS);
      expect(chip).toHaveAttribute('data-color', PILAR_VERDE_COLORS.agroZonasFill);
    });

    it('is hidden when only other flags are on', () => {
      renderWithMantine(<LeyendaPanel pilarVerdePorcentajeForestacionVisible />);
      expect(screen.queryByTestId(TESTID_ZONAS)).not.toBeInTheDocument();
    });
  });

  describe('porcentaje_forestacion (violeta — 3 tiers baja/media/alta)', () => {
    it('renders the titled container with all three tier chips when the flag is true', () => {
      renderWithMantine(<LeyendaPanel pilarVerdePorcentajeForestacionVisible />);
      expect(screen.getByTestId(TESTID_PORCENTAJE)).toBeInTheDocument();
      // The container title reads "Forestación obligatoria" (no % range —
      // that lives on each tier chip).
      expect(screen.getByText(TITLE_PORCENTAJE)).toBeInTheDocument();
      // Exactly 3 tier rows (not a single chip anymore).
      expect(screen.getByTestId(TESTID_PORCENTAJE_BAJA)).toBeInTheDocument();
      expect(screen.getByTestId(TESTID_PORCENTAJE_MEDIA)).toBeInTheDocument();
      expect(screen.getByTestId(TESTID_PORCENTAJE_ALTA)).toBeInTheDocument();
    });

    it('labels each tier with Spanish comma decimals — Baja ≤ 2,3% / Media 2,4–2,6% / Alta ≥ 2,7%', () => {
      renderWithMantine(<LeyendaPanel pilarVerdePorcentajeForestacionVisible />);
      expect(screen.getByText(LABEL_PORCENTAJE_BAJA)).toBeInTheDocument();
      expect(screen.getByText(LABEL_PORCENTAJE_MEDIA)).toBeInTheDocument();
      expect(screen.getByText(LABEL_PORCENTAJE_ALTA)).toBeInTheDocument();
    });

    it('each chip color comes from PILAR_VERDE_COLORS (single source of truth — no hardcoded hex)', () => {
      renderWithMantine(<LeyendaPanel pilarVerdePorcentajeForestacionVisible />);
      expect(screen.getByLabelText(LABEL_PORCENTAJE_BAJA)).toHaveAttribute(
        'data-color',
        PILAR_VERDE_COLORS.porcentajeForestacionBaja,
      );
      expect(screen.getByLabelText(LABEL_PORCENTAJE_MEDIA)).toHaveAttribute(
        'data-color',
        PILAR_VERDE_COLORS.porcentajeForestacionMedia,
      );
      expect(screen.getByLabelText(LABEL_PORCENTAJE_ALTA)).toHaveAttribute(
        'data-color',
        PILAR_VERDE_COLORS.porcentajeForestacionAlta,
      );
    });

    it('is hidden when only other flags are on', () => {
      renderWithMantine(<LeyendaPanel pilarVerdeAgroAceptadaVisible />);
      expect(screen.queryByTestId(TESTID_PORCENTAJE)).not.toBeInTheDocument();
      expect(screen.queryByTestId(TESTID_PORCENTAJE_BAJA)).not.toBeInTheDocument();
      expect(screen.queryByTestId(TESTID_PORCENTAJE_MEDIA)).not.toBeInTheDocument();
      expect(screen.queryByTestId(TESTID_PORCENTAJE_ALTA)).not.toBeInTheDocument();
    });
  });

  describe('composition', () => {
    it('renders all 4 simple legends together when all flags are on', () => {
      renderWithMantine(
        <LeyendaPanel
          pilarVerdeAgroAceptadaVisible
          pilarVerdeAgroPresentadaVisible
          pilarVerdeAgroZonasVisible
          pilarVerdePorcentajeForestacionVisible
        />,
      );
      expect(screen.getByTestId(TESTID_ACEPTADA)).toBeInTheDocument();
      expect(screen.getByTestId(TESTID_PRESENTADA)).toBeInTheDocument();
      expect(screen.getByTestId(TESTID_ZONAS)).toBeInTheDocument();
      expect(screen.getByTestId(TESTID_PORCENTAJE)).toBeInTheDocument();
    });

    it('coexists with the BPA histórico legend and custom items', () => {
      renderWithMantine(
        <LeyendaPanel
          pilarVerdeBpaHistoricoVisible
          pilarVerdeAgroAceptadaVisible
          pilarVerdeAgroPresentadaVisible
          pilarVerdeAgroZonasVisible
          pilarVerdePorcentajeForestacionVisible
          customItems={[{ color: '#FF0000', label: 'Zona Consorcio', type: 'border' }]}
        />,
      );
      expect(screen.getByText('Zona Consorcio')).toBeInTheDocument();
      expect(screen.getByText('Años en BPA:')).toBeInTheDocument();
      expect(screen.getByTestId(TESTID_ACEPTADA)).toBeInTheDocument();
      expect(screen.getByTestId(TESTID_PRESENTADA)).toBeInTheDocument();
      expect(screen.getByTestId(TESTID_ZONAS)).toBeInTheDocument();
      expect(screen.getByTestId(TESTID_PORCENTAJE)).toBeInTheDocument();
    });
  });
});
