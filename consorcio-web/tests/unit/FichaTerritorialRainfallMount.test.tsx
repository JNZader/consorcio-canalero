/**
 * FichaTerritorialRainfallMount.test.tsx  (Lluvia v2 — Task 3.3 RED)
 *
 * The conditional mount of the authenticated Rainfall v2 detail inside the
 * ficha's Lluvia tab (spec "Authenticated Technical Rainfall Detail": no
 * dedicated page; the detail lives IN the ficha):
 *   - it mounts ONLY on the Lluvia tab of a parcel ficha that carries a
 *     nomenclatura (the only ficha context with a resolvable regional scope
 *     in this release);
 *   - the public compact PrecipChart stays rendered alongside it, untouched;
 *   - other tabs, other tipos and parcels without nomenclatura mount nothing.
 *
 * The staff/role gate lives INSIDE `RainfallDetailPanel` (covered by its own
 * suite); here the component is a sentinel so the mount condition itself is
 * what is under test.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../src/components/map2d/rainfall/RainfallDetailPanel', () => ({
  RainfallDetailPanel: ({ nomenclatura }: { nomenclatura: string }) => (
    <div data-testid="rainfall-detail-sentinel">{nomenclatura}</div>
  ),
}));

import { FichaTerritorialPanel } from '../../src/components/map2d/FichaTerritorialPanel';
import type { FichaResponse } from '../../src/lib/api/ficha';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function ficha(overrides: Partial<FichaResponse> = {}): FichaResponse {
  const dataset = {
    cobertura: 'total' as const,
    clases: [{ clase: 'IV', ha: 12.5, pct: 62.5 }],
    pixel_count: 40,
    low_confidence: false,
    cobertura_ratio: 1,
  };
  return {
    tipo: 'parcela',
    area_ha: 20,
    suelos: dataset,
    flood_risk: dataset,
    drainage_need: dataset,
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

const PARCELA_PROPS = {
  nomenclatura: '13-06-01-0203',
  nroCuenta: '110123',
  desigOficial: 'Lote 4',
  superficieHa: '25.4',
  departamento: 'General San Martín',
  pedania: 'Arroyo Algodón',
  tipoParcela: 'rural',
};

const baseProps = {
  active: true,
  tipo: 'parcela' as const,
  nroCuenta: null,
  parcelaProps: PARCELA_PROPS,
  bpaEnriched: null,
  isLoading: false,
  isError: false,
  error: null,
  data: ficha(),
  onClose: () => {},
  tab: 'precipitacion' as const,
};

describe('FichaTerritorialPanel — Rainfall v2 detail mount (Lluvia tab)', () => {
  it('mounts the technical detail on the parcel ficha Lluvia tab, keeping the public chart', () => {
    renderWithMantine(<FichaTerritorialPanel {...baseProps} />);

    expect(screen.getByTestId('rainfall-detail-sentinel')).toHaveTextContent('13-06-01-0203');
    // The public compact normal is untouched and still rendered (spec: the
    // compact public 1991–2020 normal MUST remain available).
    expect(screen.getByTestId('ficha-precipitacion')).toBeInTheDocument();
  });

  it('mounts nothing on the other dataset tabs', () => {
    renderWithMantine(<FichaTerritorialPanel {...baseProps} tab="suelos" />);
    expect(screen.queryByTestId('rainfall-detail-sentinel')).toBeNull();
  });

  it('mounts nothing for a parcel ficha without nomenclatura', () => {
    renderWithMantine(<FichaTerritorialPanel {...baseProps} parcelaProps={null} />);
    expect(screen.queryByTestId('rainfall-detail-sentinel')).toBeNull();
  });

  it('mounts nothing for non-parcel tipos (no resolvable regional scope)', () => {
    renderWithMantine(
      <FichaTerritorialPanel
        {...baseProps}
        tipo="poligono"
        parcelaProps={null}
        data={ficha({ tipo: 'poligono' })}
      />
    );
    expect(screen.queryByTestId('rainfall-detail-sentinel')).toBeNull();
  });
});
