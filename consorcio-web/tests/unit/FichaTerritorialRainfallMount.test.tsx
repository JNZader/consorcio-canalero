/**
 * FichaTerritorialRainfallMount.test.tsx  (Lluvia v2 — Task 3.3 RED;
 * Lluvia UX — the PrecipChart accordion, design D7)
 *
 * The conditional mount of the authenticated Rainfall v2 detail inside the
 * ficha's Lluvia tab (spec "Authenticated Technical Rainfall Detail": no
 * dedicated page; the detail lives IN the ficha):
 *   - it mounts ONLY on the Lluvia tab of a parcel ficha that carries a
 *     nomenclatura (the only ficha context with a resolvable regional scope
 *     in this release);
 *   - the public compact PrecipChart stays rendered alongside it, now inside a
 *     `CollapsibleSection`;
 *   - other tabs, other tipos and parcels without nomenclatura mount nothing.
 *
 * AND the accordion default, which is the part with teeth (D7). The fold is a
 * statement about WHAT ELSE IS ON THE SCREEN, so it is keyed on the v2 detail's
 * exact mount predicate — `staff && tipo === 'parcela' && !!nomenclatura` — and
 * never on the role alone. `defaultOpen={!staff}` was the first draft and it
 * collapsed the public normal for a staff reader on a NON-parcela ficha: a
 * reader who gets no v2 detail at all, so the fold would have hidden that
 * reader's ONLY rainfall content, which the modified requirement forbids in as
 * many words. Authorization is not a layout fact.
 *
 * The staff/role gate itself lives INSIDE `RainfallDetailPanel` (covered by its
 * own suite); here the component is a sentinel, so the mount condition and the
 * fold default are what is under test.
 */

import { MantineProvider } from '@mantine/core';
import { act, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../src/components/map2d/rainfall/RainfallDetailPanel', () => ({
  RainfallDetailPanel: ({
    nomenclatura,
    prioritizeAnswer,
  }: {
    nomenclatura: string;
    prioritizeAnswer?: boolean;
  }) => (
    <div
      data-testid="rainfall-detail-sentinel"
      data-prioritize-answer={prioritizeAnswer ? 'true' : 'false'}
    >
      {nomenclatura}
    </div>
  ),
}));

import { FichaTerritorialPanel } from '../../src/components/map2d/FichaTerritorialPanel';
import type { FichaResponse } from '../../src/lib/api/ficha';
import { useAuthStore } from '../../src/stores/authStore';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

/** Same seam `RainfallDetailPanel.test.tsx` drives `useCanAccess` through. */
function setAuth(rol: 'admin' | 'operador' | 'ciudadano' | null) {
  useAuthStore.setState({
    user: rol ? { id: 'u1', email: 'staff@consorcio.test' } : null,
    loading: false,
    initialized: true,
    profile: rol ? ({ rol } as never) : null,
  });
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

function precedes(first: HTMLElement, second: HTMLElement): boolean {
  return (
    (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) ===
    Node.DOCUMENT_POSITION_FOLLOWING
  );
}

afterEach(() => setAuth(null));

describe('FichaTerritorialPanel — Rainfall v2 detail mount (Lluvia tab)', () => {
  it('mounts the technical detail on the parcel ficha Lluvia tab, keeping the public chart', () => {
    // Non-staff here (no session seeded), so the fold is OPEN and the public
    // chart is readable with no control operated — the case the spec clause is
    // actually about.
    renderWithMantine(<FichaTerritorialPanel {...baseProps} />);

    expect(screen.getByTestId('rainfall-detail-sentinel')).toHaveTextContent('13-06-01-0203');
    // The public compact normal is untouched and still rendered (spec: the
    // compact public 1991–2020 normal MUST remain available), now inside the
    // fold's body.
    const body = screen.getByTestId('ficha-precip-fold-body');
    expect(screen.getByTestId('ficha-precipitacion')).toBeInTheDocument();
    expect(body).toContainElement(screen.getByTestId('ficha-precipitacion'));
  });

  it('renders the v2 detail ABOVE the public fold', () => {
    setAuth('operador');
    renderWithMantine(<FichaTerritorialPanel {...baseProps} />);

    const detail = screen.getByTestId('rainfall-detail-sentinel');
    const fold = screen.getByTestId('ficha-precip-fold');
    expect(precedes(detail, fold)).toBe(true);
  });

  it('prioritizes the answer ahead of verbose ficha context in the mobile sheet', () => {
    setAuth('operador');
    renderWithMantine(<FichaTerritorialPanel {...baseProps} sheet />);

    const tabs = screen.getByTestId('ficha-dataset-tabs');
    const detail = screen.getByTestId('rainfall-detail-sentinel');
    const summary = screen.getByTestId('ficha-resumen');
    const identity = screen.getByTestId('ficha-parcela-header');

    // The selector stays first so changing tabs never requires a scroll. Once
    // Lluvia is selected, its answer becomes the first substantive content;
    // the parcel identity and cross-dataset summary remain rendered below.
    expect(precedes(tabs, detail)).toBe(true);
    expect(detail).toHaveAttribute('data-prioritize-answer', 'true');
    expect(precedes(detail, summary)).toBe(true);
    expect(precedes(detail, identity)).toBe(true);
  });

  it('mounts nothing on the other dataset tabs', () => {
    renderWithMantine(<FichaTerritorialPanel {...baseProps} tab="suelos" />);
    expect(screen.queryByTestId('rainfall-detail-sentinel')).toBeNull();
    expect(screen.queryByTestId('ficha-precip-fold')).toBeNull();
  });

  it('mounts nothing for a parcel ficha without nomenclatura', () => {
    renderWithMantine(<FichaTerritorialPanel {...baseProps} parcelaProps={null} />);
    expect(screen.queryByTestId('rainfall-detail-sentinel')).toBeNull();
    // …and the public chart is still there, open, because it is now this
    // reader's only rainfall content.
    expect(screen.getByTestId('ficha-precipitacion')).toBeInTheDocument();
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
    expect(screen.getByTestId('ficha-precipitacion')).toBeInTheDocument();
  });
});

describe('FichaTerritorialPanel — mobile rainfall transitions', () => {
  it('resets the sheet scroll when the selected ficha changes on the same Lluvia tab', () => {
    setAuth('operador');
    const { rerender } = renderWithMantine(
      <FichaTerritorialPanel {...baseProps} sheet resetKey="parcel-a" />
    );
    const body = screen.getByTestId('ficha-territorial-panel-sheet-body');
    body.scrollTop = 240;

    rerender(
      <MantineProvider env="test">
        <FichaTerritorialPanel
          {...baseProps}
          sheet
          resetKey="parcel-b"
          parcelaProps={{ ...PARCELA_PROPS, nomenclatura: '13-06-01-0204' }}
        />
      </MantineProvider>
    );

    expect(body.scrollTop).toBe(0);
  });

  it('resets once when auth enables prioritization, but not for an unrelated poll update', () => {
    setAuth('ciudadano');
    const { rerender } = renderWithMantine(
      <FichaTerritorialPanel {...baseProps} sheet resetKey="parcel-a" />
    );
    const body = screen.getByTestId('ficha-territorial-panel-sheet-body');
    let scrollTop = 240;
    const setScrollTop = vi.fn((value: number) => {
      scrollTop = value;
    });
    Object.defineProperty(body, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: setScrollTop,
    });

    act(() => setAuth('operador'));

    expect(setScrollTop).toHaveBeenCalledTimes(1);
    expect(setScrollTop).toHaveBeenCalledWith(0);

    scrollTop = 180;
    setScrollTop.mockClear();
    rerender(
      <MantineProvider env="test">
        <FichaTerritorialPanel
          {...baseProps}
          sheet
          resetKey="parcel-a"
          data={ficha({ area_ha: 21 })}
        />
      </MantineProvider>
    );

    expect(body.scrollTop).toBe(180);
    expect(setScrollTop).not.toHaveBeenCalled();
  });

  it('preserves the focused dataset control across entering and leaving rainfall prioritization', () => {
    setAuth('ciudadano');
    renderWithMantine(<FichaTerritorialPanel {...baseProps} sheet resetKey="parcel-a" />);
    const lluviaOption = screen.getByRole('radio', { name: 'Lluvia' });
    lluviaOption.focus();
    expect(lluviaOption).toHaveFocus();

    act(() => setAuth('operador'));

    expect(screen.getByRole('radio', { name: 'Lluvia' })).toBe(lluviaOption);
    expect(lluviaOption).toHaveFocus();

    act(() => setAuth('ciudadano'));

    expect(screen.getByRole('radio', { name: 'Lluvia' })).toBe(lluviaOption);
    expect(lluviaOption).toHaveFocus();
  });
});

describe('FichaTerritorialPanel — the PrecipChart fold default (D7)', () => {
  it('staff on a parcel WITH nomenclatura: the public chart is demoted, closed', () => {
    // The v2 detail renders above it, so the public monthly normal is context,
    // not the answer — and the reader still reaches it in one click.
    setAuth('operador');
    renderWithMantine(<FichaTerritorialPanel {...baseProps} />);

    expect(screen.getByTestId('rainfall-detail-sentinel')).toBeInTheDocument();
    expect(screen.getByTestId('ficha-precip-fold-header')).toHaveAttribute(
      'aria-expanded',
      'false'
    );
    expect(screen.queryByTestId('ficha-precipitacion')).toBeNull();
    // The title still names its own scope, so the two "normal" numbers on this
    // screen cannot be read as one pipeline (R1).
    expect(screen.getByTestId('ficha-precip-fold').textContent).toContain(
      'recorte de la parcela'
    );
  });

  it('staff on a NON-parcela ficha: no v2 detail renders, so the fold stays OPEN', () => {
    // The defect `defaultOpen={!staff}` would have shipped: this reader gets no
    // v2 detail at all, so collapsing the public normal hides the only rainfall
    // content they have — behind a word about authorization.
    setAuth('admin');
    renderWithMantine(
      <FichaTerritorialPanel
        {...baseProps}
        tipo="poligono"
        parcelaProps={null}
        data={ficha({ tipo: 'poligono' })}
      />
    );

    expect(screen.queryByTestId('rainfall-detail-sentinel')).toBeNull();
    expect(screen.getByTestId('ficha-precip-fold-header')).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTestId('ficha-precipitacion')).toBeInTheDocument();
  });

  it('non-staff on a parcel: no v2 detail is authorized, so the fold stays OPEN', () => {
    setAuth('ciudadano');
    renderWithMantine(<FichaTerritorialPanel {...baseProps} />);

    expect(screen.getByTestId('ficha-precip-fold-header')).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTestId('ficha-precipitacion')).toBeInTheDocument();
  });

  it('recomputes the default when the predicate flips after mount', () => {
    // `CollapsibleSection` reads `defaultOpen` exactly ONCE, into `useState`
    // (`CollapsibleSection.tsx:69`), and later prop changes are ignored by
    // design. `useCanAccess` reads the auth store, which HYDRATES and can move
    // on login/logout while the ficha is open — so without the `key` remount
    // this fold would keep a default computed from the pre-hydration value: a
    // staff reader left with the public chart open above a v2 detail, or a
    // reader who lost access left with their only content collapsed.
    setAuth('ciudadano');
    renderWithMantine(<FichaTerritorialPanel {...baseProps} />);
    expect(screen.getByTestId('ficha-precip-fold-header')).toHaveAttribute('aria-expanded', 'true');

    act(() => setAuth('operador'));

    expect(screen.getByTestId('ficha-precip-fold-header')).toHaveAttribute(
      'aria-expanded',
      'false'
    );
    expect(screen.getByTestId('rainfall-detail-sentinel')).toBeInTheDocument();
  });
});
