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
const LABEL_PORCENTAJE = 'Forestación obligatoria (2-5%)';

const TESTID_ACEPTADA = 'pilar-verde-agro-aceptada-legend';
const TESTID_PRESENTADA = 'pilar-verde-agro-presentada-legend';
const TESTID_ZONAS = 'pilar-verde-agro-zonas-legend';
const TESTID_PORCENTAJE = 'pilar-verde-porcentaje-forestacion-legend';

describe('<LeyendaPanel /> — simple Pilar Verde legends (agro + porcentaje)', () => {
  describe('defaults', () => {
    it('does NOT render any of the 4 simple legends by default', () => {
      renderWithMantine(<LeyendaPanel />);
      expect(screen.queryByText(LABEL_ACEPTADA)).not.toBeInTheDocument();
      expect(screen.queryByText(LABEL_PRESENTADA)).not.toBeInTheDocument();
      expect(screen.queryByText(LABEL_ZONAS)).not.toBeInTheDocument();
      expect(screen.queryByText(LABEL_PORCENTAJE)).not.toBeInTheDocument();
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

  describe('porcentaje_forestacion (violeta — forestación obligatoria 2-5%)', () => {
    it('renders when its flag is true with exact Spanish label', () => {
      renderWithMantine(<LeyendaPanel pilarVerdePorcentajeForestacionVisible />);
      expect(screen.getByTestId(TESTID_PORCENTAJE)).toBeInTheDocument();
      expect(screen.getByText(LABEL_PORCENTAJE)).toBeInTheDocument();
    });

    it('chip color matches PILAR_VERDE_COLORS.porcentajeForestacionFill (single source of truth)', () => {
      renderWithMantine(<LeyendaPanel pilarVerdePorcentajeForestacionVisible />);
      const chip = screen.getByLabelText(LABEL_PORCENTAJE);
      expect(chip).toHaveAttribute('data-color', PILAR_VERDE_COLORS.porcentajeForestacionFill);
    });

    it('is hidden when only other flags are on', () => {
      renderWithMantine(<LeyendaPanel pilarVerdeAgroAceptadaVisible />);
      expect(screen.queryByTestId(TESTID_PORCENTAJE)).not.toBeInTheDocument();
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
