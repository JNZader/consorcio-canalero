/**
 * Multi-parcel UI surface (T4): the panel header, the minimized pill and the
 * toolbar toggle.
 *
 * The point of the header is what it does NOT say. A union of N parcels has no
 * nomenclatura, no account and no designación of its own, so the per-parcel
 * identity block is replaced by "N parcelas · X ha" — the two facts that are
 * actually true of the analyzed area.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  FichaTerritorialPanel,
  fichaPillLabel,
} from '../../src/components/map2d/FichaTerritorialPanel';
import { MeasurementToolbar } from '../../src/components/map2d/measurement/MeasurementToolbar';
import { FichaApiError, type FichaDataset, type FichaResponse } from '../../src/lib/api/ficha';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function dataset(clases: FichaDataset['clases']): FichaDataset {
  return {
    cobertura: 'total',
    clases,
    pixel_count: 5000,
    low_confidence: false,
    cobertura_ratio: 1,
  };
}

const DATA: FichaResponse = {
  tipo: 'parcelas',
  area_ha: 210.5,
  suelos: dataset([{ clase: 'IV', ha: 210.5, pct: 100 }]),
  flood_risk: dataset([{ clase: 'Alto', ha: 210.5, pct: 100 }]),
  drainage_need: dataset([{ clase: 'Bajo', ha: 210.5, pct: 100 }]),
  precipitacion_mensual: {
    cobertura: 'total',
    low_confidence: false,
    pixel_count: 12,
    cobertura_ratio: 1,
    unidad: 'mm',
    serie: [],
    anual_mm: 900,
  },
};

const PARCELA_PROPS = {
  nomenclatura: '13-06-01-0201',
  nroCuenta: '110123',
  desigOficial: 'Lote 4',
  superficieHa: '25.4',
  departamento: 'General San Martín',
  pedania: 'Arroyo Algodón',
  tipoParcela: 'rural',
};

function panel(props: Record<string, unknown> = {}) {
  return (
    <FichaTerritorialPanel
      active
      tipo="parcelas"
      nroCuenta={null}
      parcelasCount={3}
      bpaEnriched={null}
      isLoading={false}
      isError={false}
      error={null}
      data={DATA}
      onClose={vi.fn()}
      {...props}
    />
  );
}

/** The 404 the backend answers when some nomenclaturas are gone from the catastro. */
function errorFaltantes(nomenclaturas: string[]) {
  return new FichaApiError(
    404,
    'parcela_no_encontrada',
    `No se encontraron las parcelas: ${nomenclaturas.join(', ')}`,
    { nomenclaturas }
  );
}

describe('ficha panel — multi-parcel error recovery (T4 fix round)', () => {
  it('offers "Quitar faltantes" naming HOW MANY parcels the server could not resolve', async () => {
    // A stale parcel cannot be ctrl-clicked away — it is not on the map — so
    // without this the whole selection has to be rebuilt by hand.
    const onRemoveParcelas = vi.fn();
    const faltantes = ['13-06-01-0202', '13-06-01-0203'];
    renderWithMantine(
      panel({
        isError: true,
        error: errorFaltantes(faltantes),
        data: undefined,
        onRemoveParcelas,
      })
    );

    const boton = screen.getByTestId('ficha-error-quitar-faltantes');
    expect(boton.textContent).toContain('Quitar faltantes (2)');

    await userEvent.click(boton);
    expect(onRemoveParcelas).toHaveBeenCalledWith(faltantes);
  });

  it('does not offer the removal for a SINGLE-parcel ficha (nothing to trim)', () => {
    renderWithMantine(
      panel({
        tipo: 'parcela',
        parcelasCount: 1,
        isError: true,
        error: errorFaltantes(['13-06-01-0201']),
        data: undefined,
        onRemoveParcelas: vi.fn(),
      })
    );

    expect(screen.queryByTestId('ficha-error-quitar-faltantes')).toBeNull();
  });

  it('does not offer the removal when the container did not wire it', () => {
    renderWithMantine(
      panel({
        isError: true,
        error: errorFaltantes(['13-06-01-0202']),
        data: undefined,
      })
    );

    expect(screen.queryByTestId('ficha-error-quitar-faltantes')).toBeNull();
    expect(screen.getByTestId('ficha-error')).toBeTruthy();
  });

  it('adds an ACTIONABLE line to the vertex cap, which the server message cannot', () => {
    // `ficha_max_vertices` is the ceiling a real rural selection hits first, and
    // only the client knows the analyzed area is a selection the user can shrink.
    renderWithMantine(
      panel({
        isError: true,
        error: new FichaApiError(
          422,
          'cap_excedido',
          'La zona supera el limite de vertices (1000).',
          { cap: 'vertices', limite: 1000, valor: 1450 }
        ),
        data: undefined,
      })
    );

    expect(screen.getByTestId('ficha-error-vertices-hint').textContent).toContain(
      'Deseleccioná algunas parcelas'
    );
  });

  it('does not add the vertex line to the AREA cap (deselecting is not the fix)', () => {
    renderWithMantine(
      panel({
        isError: true,
        error: new FichaApiError(422, 'cap_excedido', 'La zona supera el limite de area.', {
          cap: 'area_ha',
          limite: 50000,
          valor: 90000,
        }),
        data: undefined,
      })
    );

    expect(screen.queryByTestId('ficha-error-vertices-hint')).toBeNull();
  });

  it('does not add the vertex line to a single-parcel ficha', () => {
    renderWithMantine(
      panel({
        tipo: 'parcela',
        parcelasCount: 1,
        isError: true,
        error: new FichaApiError(422, 'cap_excedido', 'La zona supera el limite.', {
          cap: 'vertices',
        }),
        data: undefined,
      })
    );

    expect(screen.queryByTestId('ficha-error-vertices-hint')).toBeNull();
  });
});

describe('ficha panel — multi-parcel header (T4)', () => {
  it('shows "N parcelas" plus the analyzed hectares', () => {
    renderWithMantine(panel());
    const header = screen.getByTestId('ficha-parcelas-header');
    expect(header.textContent).toContain('3 parcelas');
    expect(header.textContent).toContain('210');
  });

  it('does NOT show any per-parcel identity field for a union', () => {
    // Even if the container mistakenly threads the last-clicked parcel's props,
    // the panel must not attribute the union's hectares to that one parcel.
    renderWithMantine(panel({ parcelaProps: PARCELA_PROPS }));

    expect(screen.queryByTestId('ficha-parcela-header')).toBeNull();
    expect(screen.queryByText('13-06-01-0201')).toBeNull();
    expect(screen.queryByText('110123')).toBeNull();
  });

  it('a single-parcel ficha still shows the identity header (no regression)', () => {
    renderWithMantine(
      panel({ tipo: 'parcela', parcelasCount: 1, parcelaProps: PARCELA_PROPS })
    );

    expect(screen.getByTestId('ficha-parcela-header')).toBeTruthy();
    expect(screen.queryByTestId('ficha-parcelas-header')).toBeNull();
  });

  it('renders the count header even before the analysis lands', () => {
    // The count is known from the selection alone, so the loading panel can
    // already say what is being analyzed.
    renderWithMantine(panel({ isLoading: true, data: undefined }));
    expect(screen.getByTestId('ficha-parcelas-header').textContent).toContain('3 parcelas');
  });
});

describe('fichaPillLabel — multi-parcel (T4)', () => {
  it('leads with the parcel COUNT, which is what identifies a union', () => {
    expect(fichaPillLabel({ tipo: 'parcelas', parcelasCount: 3, areaHa: 210.5 })).toContain(
      '3 parcelas'
    );
  });

  it('falls back to a generic label when the count is unknown', () => {
    expect(fichaPillLabel({ tipo: 'parcelas' })).toBe('Ficha · Parcelas');
  });

  it('leaves the other tipos untouched', () => {
    expect(fichaPillLabel({ tipo: 'parcela', areaHa: null })).toBe('Ficha · Parcela');
    expect(fichaPillLabel({ tipo: 'canal_cuenca', canalNombre: 'Canal Este' })).toBe(
      'Ficha · Canal Este'
    );
  });
});

describe('MeasurementToolbar — multi-select toggle (T4)', () => {
  it('is NOT rendered when the caller does not wire it (3D viewer)', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={false}
        onStartDistance={vi.fn()}
        onStartArea={vi.fn()}
        onClear={vi.fn()}
      />
    );
    expect(screen.queryByTestId('ficha-multi-select-toggle')).toBeNull();
  });

  it('renders a pressed-state toggle and fires the handler on click', async () => {
    const onToggle = vi.fn();
    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={false}
        onStartDistance={vi.fn()}
        onStartArea={vi.fn()}
        onClear={vi.fn()}
        fichaMultiSelectActive={false}
        onToggleFichaMultiSelect={onToggle}
      />
    );

    const boton = screen.getByTestId('ficha-multi-select-toggle');
    expect(boton.getAttribute('aria-pressed')).toBe('false');
    await userEvent.click(boton);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('reports its active state to screen readers', () => {
    renderWithMantine(
      <MeasurementToolbar
        mode="idle"
        hasMeasurements={false}
        onStartDistance={vi.fn()}
        onStartArea={vi.fn()}
        onClear={vi.fn()}
        fichaMultiSelectActive
        onToggleFichaMultiSelect={vi.fn()}
      />
    );
    expect(
      screen.getByTestId('ficha-multi-select-toggle').getAttribute('aria-pressed')
    ).toBe('true');
  });
});
