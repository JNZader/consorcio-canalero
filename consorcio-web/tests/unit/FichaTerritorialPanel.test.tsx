/**
 * FichaTerritorialPanel.test.tsx
 *
 * Covers the presentational states of the ficha card (A4.8):
 *   - loading indicator, no stale result;
 *   - error states 404 / 422 / 429 / 503 surface the server's actionable message;
 *   - `sin_cobertura` renders text, NOT a `0 %` row;
 *   - low-confidence badge appears only when a dataset flags it;
 *   - tables render the server ha / % numbers verbatim;
 *   - Pilar Verde "sin vinculación" when the parcel has no BPA record.
 *
 * @see spec `ficha-frontend` §"Loading, error and no-coverage states",
 *           §"Low-confidence badge", §"Card rendering"
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { FichaTerritorialPanel } from '../../src/components/map2d/FichaTerritorialPanel';
import { FichaApiError, type FichaDataset, type FichaResponse } from '../../src/lib/api/ficha';
import type {
  Bpa2025EnrichedRecord,
  BpaEnrichedFile,
  ParcelEnriched,
} from '../../src/types/pilarVerde';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function dataset(overrides: Partial<FichaDataset> = {}): FichaDataset {
  return {
    cobertura: 'total',
    clases: [{ clase: 'IV', ha: 12.5, pct: 62.5 }],
    pixel_count: 40,
    low_confidence: false,
    cobertura_ratio: 1,
    ...overrides,
  };
}

function ficha(overrides: Partial<FichaResponse> = {}): FichaResponse {
  return {
    tipo: 'parcela',
    area_ha: 20,
    suelos: dataset(),
    flood_risk: dataset({ clases: [{ clase: 'Alto', ha: 20, pct: 100 }] }),
    drainage_need: dataset({ clases: [{ clase: 'Bajo', ha: 20, pct: 100 }] }),
    precipitacion_mensual: {
      cobertura: 'sin_cobertura',
      low_confidence: false,
      pixel_count: 0,
      cobertura_ratio: 0,
      unidad: 'mm',
      serie: [],
      anual_mm: null,
    },
    ...overrides,
  };
}

function bpa2025(activa: boolean): Bpa2025EnrichedRecord {
  return {
    superficie_bpa: 10,
    bpa_total: '2',
    activa,
    ejes: { persona: 'Si', planeta: 'Si', prosperidad: 'No', alianza: 'No' },
    // The 21 practica flags are irrelevant to the badge under test.
    practicas: {} as Bpa2025EnrichedRecord['practicas'],
  };
}

function bpaEnrichedFor(parcel: Partial<ParcelEnriched> & { nro_cuenta: string }): BpaEnrichedFile {
  return {
    schema_version: '1.2',
    generated_at: '2026-01-01',
    source: 'test',
    parcels: [
      {
        nomenclatura: null,
        departamento: null,
        pedania: null,
        superficie_ha: null,
        ley_forestal: 'no_inscripta',
        bpa_2025: null,
        bpa_historico: {},
        años_bpa: 0,
        años_lista: [],
        ...parcel,
      },
    ],
  };
}

const baseProps = {
  active: true,
  tipo: 'parcela' as const,
  nroCuenta: null,
  bpaEnriched: null,
  isLoading: false,
  isError: false,
  error: null,
  data: undefined,
  onClose: () => {},
};

describe('FichaTerritorialPanel', () => {
  it('renders nothing when inactive', () => {
    renderWithMantine(<FichaTerritorialPanel {...baseProps} active={false} />);
    expect(screen.queryByTestId('ficha-territorial-panel')).toBeNull();
  });

  it('shows a loading indicator and no result', () => {
    renderWithMantine(<FichaTerritorialPanel {...baseProps} isLoading />);
    expect(screen.getByTestId('ficha-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('ficha-result')).toBeNull();
  });

  it.each([
    [404, 'parcela_no_encontrada', 'No existe una parcela con nomenclatura 99-99'],
    [422, 'cap_excedido', 'Se supero el limite de area_ha: 30000 > 20000'],
    [429, 'limite_de_tasa', 'Demasiados pedidos. Reintente en unos segundos.'],
    [503, 'dataset_no_cargado', 'El dataset suelos no esta cargado en esta instalacion'],
  ])('surfaces the server message for a %i error', (status, codigo, detail) => {
    renderWithMantine(
      <FichaTerritorialPanel
        {...baseProps}
        isError
        error={new FichaApiError(status, codigo, detail)}
      />
    );
    const alert = screen.getByTestId('ficha-error');
    expect(alert).toHaveTextContent(detail);
  });

  it('renders one table per dataset with the server numbers', () => {
    renderWithMantine(<FichaTerritorialPanel {...baseProps} data={ficha()} />);
    expect(screen.getByTestId('ficha-result')).toBeInTheDocument();
    expect(screen.getByText('Superficie analizada:')).toBeInTheDocument();
    // Soils row from the fixture — ha and the SERVER pct, not a recomputed one.
    expect(screen.getByText('12.5 ha')).toBeInTheDocument();
    expect(screen.getByText('62.5%')).toBeInTheDocument();
    expect(screen.getByTestId('ficha-suelos')).toBeInTheDocument();
    expect(screen.getByTestId('ficha-flood-risk')).toBeInTheDocument();
    expect(screen.getByTestId('ficha-drainage-need')).toBeInTheDocument();
  });

  it('renders "sin cobertura" text and no 0% row for an uncovered dataset', () => {
    const data = ficha({ suelos: dataset({ cobertura: 'sin_cobertura', clases: [] }) });
    renderWithMantine(<FichaTerritorialPanel {...baseProps} data={data} />);
    expect(screen.getByTestId('ficha-suelos-sin-cobertura')).toBeInTheDocument();
    // No fabricated 0 % row anywhere.
    expect(screen.queryByText('0.0%')).toBeNull();
    expect(screen.queryByText('0%')).toBeNull();
  });

  it('shows the low-confidence badge only when a dataset flags it', () => {
    const clean = ficha();
    const { rerender } = renderWithMantine(<FichaTerritorialPanel {...baseProps} data={clean} />);
    expect(screen.queryByTestId('ficha-low-confidence')).toBeNull();

    const flagged = ficha({ flood_risk: dataset({ low_confidence: true, pixel_count: 3 }) });
    rerender(
      <MantineProvider env="test">
        <FichaTerritorialPanel {...baseProps} data={flagged} />
      </MantineProvider>
    );
    // Badge appears (resumen + dataset header both render it).
    expect(screen.getAllByTestId('ficha-low-confidence').length).toBeGreaterThan(0);
  });

  it('renders Pilar Verde "sin vinculación" for a parcel with no BPA record', () => {
    renderWithMantine(<FichaTerritorialPanel {...baseProps} data={ficha()} nroCuenta="12345" />);
    expect(screen.getByTestId('pilar-verde-sin-vinculacion')).toBeInTheDocument();
  });

  it('renders the plural BPA-years badge and "Activa 2025" for a matched active parcel', () => {
    const bpaEnriched = bpaEnrichedFor({
      nro_cuenta: '12345',
      años_bpa: 3,
      años_lista: ['2023', '2024', '2025'],
      bpa_2025: bpa2025(true),
    });
    renderWithMantine(
      <FichaTerritorialPanel
        {...baseProps}
        data={ficha()}
        nroCuenta="12345"
        bpaEnriched={bpaEnriched}
      />
    );
    expect(screen.getByTestId('ficha-pilar-verde')).toBeInTheDocument();
    expect(screen.queryByTestId('pilar-verde-sin-vinculacion')).toBeNull();
    expect(screen.getByText(/3 años de BPA/)).toBeInTheDocument();
    expect(screen.getByText('Activa 2025')).toBeInTheDocument();
  });

  it('renders the singular BPA-years badge for a one-year parcel', () => {
    const bpaEnriched = bpaEnrichedFor({
      nro_cuenta: '12345',
      años_bpa: 1,
      años_lista: ['2025'],
      bpa_2025: bpa2025(true),
    });
    renderWithMantine(
      <FichaTerritorialPanel
        {...baseProps}
        data={ficha()}
        nroCuenta="12345"
        bpaEnriched={bpaEnriched}
      />
    );
    expect(screen.getByText(/1 año de BPA/)).toBeInTheDocument();
  });

  it('does NOT render "Activa 2025" when the enriched record is present but inactive', () => {
    const bpaEnriched = bpaEnrichedFor({
      nro_cuenta: '12345',
      años_bpa: 2,
      años_lista: ['2024', '2025'],
      bpa_2025: bpa2025(false),
    });
    renderWithMantine(
      <FichaTerritorialPanel
        {...baseProps}
        data={ficha()}
        nroCuenta="12345"
        bpaEnriched={bpaEnriched}
      />
    );
    expect(screen.getByText(/2 años de BPA/)).toBeInTheDocument();
    expect(screen.queryByText('Activa 2025')).toBeNull();
    expect(screen.getByText('2025: inactiva')).toBeInTheDocument();
  });
});
