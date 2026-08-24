/**
 * RoadFlowRankedList.test.tsx — flujo-caminos S4, task 4.8.
 *
 * The living acceptance criteria for the ranked list (RFA-R2/R3, Law 7, D6):
 *
 *   - `N.º de M` uses M = the `flujo_natural` COUNT, never the total row count.
 *   - Each ranked point shows flow direction across the road, upslope
 *     contributing area, and its segment identity.
 *   - Canal crossings are a SEPARATE, UNRANKED companion set.
 *   - The generation timestamp is ALWAYS shown; the stale notice appears when
 *     the response says `desactualizado`.
 *   - A `confianza='baja'` row carries "orientación aproximada" WITH its
 *     server-authored reason, and is STILL RANKED and STILL SHOWN.
 *   - No volume, rate, depth, cuneta size or return period appears ANYWHERE.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { RoadFlowRankedList } from '../../src/components/map2d/RoadFlowRankedList';
import type {
  RoadFlowCrossingFeature,
  RoadFlowCrossingProperties,
  RoadFlowCrossingsResponse,
} from '../../src/lib/api/roadFlow';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function feature(props: Partial<RoadFlowCrossingProperties>): RoadFlowCrossingFeature {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-63.5, -32.9] },
    properties: {
      id: props.id ?? 'row-1',
      tipo: props.tipo ?? 'flujo_natural',
      tramo_ref: props.tramo_ref ?? 'RV-1042',
      canal_ref: props.canal_ref ?? null,
      direccion_flujo_deg: props.direccion_flujo_deg ?? 245,
      rumbo_camino_deg: props.rumbo_camino_deg ?? 88,
      lado_cruce: props.lado_cruce ?? 'norte',
      area_aporte_ha: props.area_aporte_ha ?? 128.4,
      orden_ranking: props.orden_ranking ?? 1,
      confianza: props.confianza ?? 'alta',
      nota: props.nota ?? null,
    },
  };
}

/**
 * THREE ranked natural crossings plus TWO canal candidates: five rows in the
 * collection, but M is 3. A denominator taken from `features.length` would read
 * "1.º de 5" and be arithmetically meaningless.
 */
function buildResponse(
  overrides: Partial<RoadFlowCrossingsResponse> = {}
): RoadFlowCrossingsResponse {
  const features = [
    feature({ id: 'f1', orden_ranking: 1, tramo_ref: 'RV-1042', area_aporte_ha: 512.3 }),
    feature({ id: 'f2', orden_ranking: 2, tramo_ref: 'RV-1043', area_aporte_ha: 210.7 }),
    feature({
      id: 'f3',
      orden_ranking: 3,
      tramo_ref: 'RV-1044',
      area_aporte_ha: 98.1,
      confianza: 'baja',
      nota: 'incidencia oblicua (31.2 grados): dentro de la banda de cuantizacion del puntero D8',
    }),
    feature({
      id: 'c1',
      tipo: 'canal',
      tramo_ref: 'RV-2001',
      canal_ref: 'CN-9',
      orden_ranking: null,
      area_aporte_ha: null,
    }),
    feature({
      id: 'c2',
      tipo: 'canal',
      tramo_ref: 'RV-2002',
      canal_ref: 'CN-11',
      orden_ranking: null,
      area_aporte_ha: null,
      confianza: 'baja',
      nota: 'alineacion compartida de 140 m: el punto es el punto medio del tramo comun',
    }),
  ];

  return {
    area_id: 'zona-4',
    calculada_en: '2026-08-22T14:03:00Z',
    desactualizado: false,
    total_flujo_natural: 3,
    total_canal: 2,
    features: { type: 'FeatureCollection', features },
    excluidos: [],
    parametros: {},
    variante: 'natural',
    segmentos_parcialmente_cubiertos: 0,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Law 7 — the denominator
// ---------------------------------------------------------------------------

describe('RoadFlowRankedList — the rank denominator (Law 7)', () => {
  it('reads `N.º de M` with M = the flujo_natural count, NOT the row count', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);

    // 3 ranked rows, 5 features in the collection. M must be 3.
    expect(screen.getByText('1.º de 3')).toBeTruthy();
    expect(screen.getByText('2.º de 3')).toBeTruthy();
    expect(screen.getByText('3.º de 3')).toBeTruthy();

    expect(screen.queryByText(/de 5/)).toBeNull();
  });

  it('uses the SERVER counter, not a recount of the rendered rows', () => {
    // A response whose counter disagrees with the collection: the counter wins,
    // because it is the run's own count of ranked crossings.
    const data = buildResponse({ total_flujo_natural: 7 });
    renderWithMantine(<RoadFlowRankedList data={data} />);
    expect(screen.getByText('1.º de 7')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// What each ranked row must say
// ---------------------------------------------------------------------------

describe('RoadFlowRankedList — each ranked point', () => {
  it('shows flow direction across the road, contributing area and segment identity', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    const row = screen.getByTestId('road-flow-rank-f1');

    expect(within(row).getByText(/245°/)).toBeTruthy(); // flow direction
    expect(within(row).getByText(/88°/)).toBeTruthy(); // road bearing
    expect(within(row).getByText(/512,3 ha/)).toBeTruthy(); // upslope area
    expect(within(row).getByText(/RV-1042/)).toBeTruthy(); // segment identity
  });

  it('orders the ranked rows by rank', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    const ranked = screen.getAllByTestId(/^road-flow-rank-/);
    expect(ranked.map((el) => el.getAttribute('data-testid'))).toEqual([
      'road-flow-rank-f1',
      'road-flow-rank-f2',
      'road-flow-rank-f3',
    ]);
  });
});

// ---------------------------------------------------------------------------
// Canal candidates — a separate, unranked companion set
// ---------------------------------------------------------------------------

describe('RoadFlowRankedList — canal crossings', () => {
  it('renders them as a SEPARATE set, never mixed into the ranking', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);

    const canalSection = screen.getByTestId('road-flow-canal-section');
    expect(within(canalSection).getByTestId('road-flow-canal-c1')).toBeTruthy();
    expect(within(canalSection).getByTestId('road-flow-canal-c2')).toBeTruthy();

    // No canal row is inside the ranked set.
    const ranked = screen.getAllByTestId(/^road-flow-rank-/);
    expect(ranked).toHaveLength(3);
  });

  it('gives them NO rank label at all', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    const canalRow = screen.getByTestId('road-flow-canal-c1');
    expect(within(canalRow).queryByText(/\d+\.º de/)).toBeNull();
  });

  it('names each candidate its road segment and its canal', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    const canalRow = screen.getByTestId('road-flow-canal-c1');
    expect(within(canalRow).getByText(/RV-2001/)).toBeTruthy();
    expect(within(canalRow).getByText(/CN-9/)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Age of the result
// ---------------------------------------------------------------------------

describe('RoadFlowRankedList — the generation timestamp', () => {
  it('ALWAYS shows when the ranking was calculated', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    const stamp = screen.getByTestId('road-flow-calculada-en');
    expect(stamp.textContent).toMatch(/Calculado el/);
    expect(stamp.textContent).toMatch(/22\/08\/2026/);
  });

  it('shows the stale notice when the run is desactualizado', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse({ desactualizado: true })} />);
    expect(screen.getByTestId('road-flow-desactualizado')).toBeTruthy();
    // …and the timestamp is still there: stale is not a reason to hide the age.
    expect(screen.getByTestId('road-flow-calculada-en')).toBeTruthy();
  });

  it('does NOT show the stale notice on a fresh run', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    expect(screen.queryByTestId('road-flow-desactualizado')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Low confidence — marked, not demoted
// ---------------------------------------------------------------------------

describe('RoadFlowRankedList — low confidence', () => {
  it('marks a baja row "orientación aproximada" and carries the SERVER reason', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    const row = screen.getByTestId('road-flow-rank-f3');

    const marker = within(row).getByTestId('road-flow-confianza-f3');
    expect(marker.textContent).toContain('orientación aproximada');
    // The reason is the backend's `nota`, verbatim — not a sentence re-derived
    // client-side from a band the frontend does not own.
    expect(marker.getAttribute('title')).toContain('banda de cuantizacion');
  });

  it('gives a canal row its own `nota` as the reason', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    const marker = screen.getByTestId('road-flow-confianza-c2');
    expect(marker.textContent).toContain('orientación aproximada');
    expect(marker.getAttribute('title')).toContain('alineacion compartida');
  });

  it('keeps the baja row RANKED and SHOWN — marking is not demotion', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    const row = screen.getByTestId('road-flow-rank-f3');
    expect(within(row).getByText('3.º de 3')).toBeTruthy();
    // It sits in its rank position, not at the bottom of the list.
    const ranked = screen.getAllByTestId(/^road-flow-rank-/);
    expect(ranked[2].getAttribute('data-testid')).toBe('road-flow-rank-f3');
  });

  it('does not mark a confident row', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    expect(screen.queryByTestId('road-flow-confianza-f1')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// The disclaimer travels with the list
// ---------------------------------------------------------------------------

describe('RoadFlowRankedList — the disclaimer', () => {
  it('renders it directly, always mounted, above the ranking', () => {
    renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    expect(screen.getByTestId('road-flow-disclaimer-lista')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// The negative contract
// ---------------------------------------------------------------------------

describe('RoadFlowRankedList — no hydraulic magnitude ANYWHERE', () => {
  it('renders no volume, rate, depth, cuneta size or return period', () => {
    const { container } = renderWithMantine(<RoadFlowRankedList data={buildResponse()} />);
    const text = (container.textContent ?? '').toLowerCase();

    for (const forbidden of [
      'volumen',
      'caudal',
      'm³',
      'm3/s',
      'l/s',
      'profundidad',
      'cuneta',
      'capacidad',
      'período de retorno',
      'periodo de retorno',
      'tr ',
    ]) {
      expect(text, `"${forbidden}" reached the ranked list`).not.toContain(forbidden);
    }
  });
});

// ---------------------------------------------------------------------------
// Empty / coverage states
// ---------------------------------------------------------------------------

describe('RoadFlowRankedList — empty run', () => {
  it('says so, and still shows the timestamp and the disclaimer', () => {
    const empty = buildResponse({
      total_flujo_natural: 0,
      total_canal: 0,
      features: { type: 'FeatureCollection', features: [] },
    });
    renderWithMantine(<RoadFlowRankedList data={empty} />);
    expect(screen.getByTestId('road-flow-empty')).toBeTruthy();
    expect(screen.getByTestId('road-flow-calculada-en')).toBeTruthy();
    expect(screen.getByTestId('road-flow-disclaimer-lista')).toBeTruthy();
  });
});
