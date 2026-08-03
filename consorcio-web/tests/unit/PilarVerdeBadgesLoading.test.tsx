/**
 * PilarVerdeBadgesLoading.test.tsx — T3c fix 1 (ficha BPA-join honesty).
 *
 * `bpa_enriched.json` is now lazy-loaded (the first parcela ficha triggers it),
 * so the badges MUST distinguish "still downloading" from "this parcel has no
 * BPA record". Claiming "Sin vinculación" mid-fetch states a false fact.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { PilarVerdeBadges } from '../../src/components/map2d/PilarVerdeBadges';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const bpaEnriched = {
  schema_version: '1.2',
  generated_at: '2026-04-20T05:37:59Z',
  source: 'test',
  parcels: [{ nro_cuenta: '123', años_bpa: 3, bpa_2025: { activa: true } }],
  // biome-ignore lint/suspicious/noExplicitAny: narrow fixture for the join only
} as any;

describe('<PilarVerdeBadges /> — lazy BPA loading state', () => {
  it('shows a pending state instead of "Sin vinculación" while loading', () => {
    renderWithMantine(
      <PilarVerdeBadges tipo="parcela" nroCuenta="999" bpaEnriched={null} loading />
    );

    expect(screen.getByTestId('pilar-verde-cargando')).toBeInTheDocument();
    expect(screen.queryByTestId('pilar-verde-sin-vinculacion')).toBeNull();
  });

  it('falls back to "Sin vinculación" once loaded with no match', () => {
    renderWithMantine(
      <PilarVerdeBadges tipo="parcela" nroCuenta="999" bpaEnriched={bpaEnriched} />
    );

    expect(screen.getByTestId('pilar-verde-sin-vinculacion')).toBeInTheDocument();
    expect(screen.queryByTestId('pilar-verde-cargando')).toBeNull();
  });

  it('renders the badges once the lazy payload lands', () => {
    renderWithMantine(
      <PilarVerdeBadges tipo="parcela" nroCuenta="123" bpaEnriched={bpaEnriched} loading={false} />
    );

    expect(screen.getByText(/3 años de BPA/)).toBeInTheDocument();
    expect(screen.queryByTestId('pilar-verde-cargando')).toBeNull();
  });

  it('says the join FAILED instead of hanging on "Cargando…" (R4-001)', () => {
    renderWithMantine(
      <PilarVerdeBadges
        tipo="parcela"
        nroCuenta="123"
        bpaEnriched={null}
        error="Pilar Verde: no se pudieron cargar bpaEnriched"
      />
    );

    expect(screen.getByTestId('pilar-verde-error')).toBeInTheDocument();
    expect(screen.queryByTestId('pilar-verde-cargando')).toBeNull();
    expect(screen.queryByTestId('pilar-verde-sin-vinculacion')).toBeNull();
  });

  it('prefers the error over a stale loading flag', () => {
    renderWithMantine(
      <PilarVerdeBadges tipo="parcela" nroCuenta="123" bpaEnriched={null} loading error="boom" />
    );

    expect(screen.getByTestId('pilar-verde-error')).toBeInTheDocument();
    expect(screen.queryByTestId('pilar-verde-cargando')).toBeNull();
  });

  it('still renders nothing for non-parcela fichas, loading or not', () => {
    renderWithMantine(
      <PilarVerdeBadges tipo="poligono" nroCuenta={null} bpaEnriched={null} loading />
    );
    expect(screen.queryByTestId('ficha-pilar-verde')).toBeNull();
    expect(screen.queryByTestId('pilar-verde-cargando')).toBeNull();
  });
});
