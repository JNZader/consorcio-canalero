/**
 * RelevamientoCobertura.test.tsx — flujo-caminos S4, task 4.13.
 *
 * RSS-R4: a DEM candidate is NEVER counted as surveyed. The three counters are
 * rendered separately and NEVER summed, and a candidate-only segment is
 * displayed as NOT YET SURVEYED.
 *
 * The load-bearing assertion is the arithmetic one: no rendered number equals
 * `relevados + solo_candidato`. A single "surveyed" figure that quietly folded
 * in candidate-only segments would report fieldwork nobody did — which is the
 * exact failure this requirement exists to prevent, and it is invisible to any
 * test that only checks the three numbers are present.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { RelevamientoCobertura } from '../../src/components/map2d/RelevamientoCobertura';
import type { CoberturaResponse } from '../../src/lib/api/relevamiento';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const COBERTURA: CoberturaResponse = {
  area_id: 'zona-4',
  relevados: 12,
  solo_candidato: 7,
  sin_datos: 21,
  total_activos: 40,
};

describe('RelevamientoCobertura — three counters, never summed (RSS-R4)', () => {
  it('renders each counter separately, with its own value', () => {
    renderWithMantine(<RelevamientoCobertura cobertura={COBERTURA} />);

    expect(within(screen.getByTestId('cobertura-relevados')).getByText('12')).toBeTruthy();
    expect(within(screen.getByTestId('cobertura-solo-candidato')).getByText('7')).toBeTruthy();
    expect(within(screen.getByTestId('cobertura-sin-datos')).getByText('21')).toBeTruthy();
  });

  it('NEVER renders relevados + solo_candidato as one figure', () => {
    const { container } = renderWithMantine(<RelevamientoCobertura cobertura={COBERTURA} />);
    const text = container.textContent ?? '';

    // 12 + 7 = 19. That number must appear nowhere.
    const sum = String(COBERTURA.relevados + COBERTURA.solo_candidato);
    expect(text).not.toContain(sum);
  });

  it('shows the denominator as the ACTIVE segment total, not a derived sum', () => {
    renderWithMantine(<RelevamientoCobertura cobertura={COBERTURA} />);
    const total = screen.getByTestId('cobertura-total-activos');
    expect(total.textContent).toContain('40');
  });

  it('describes a candidate-only segment as NOT YET SURVEYED', () => {
    renderWithMantine(<RelevamientoCobertura cobertura={COBERTURA} />);
    const node = screen.getByTestId('cobertura-solo-candidato');
    // The label has to say what the number means, in the operator's terms.
    expect(node.textContent).toMatch(/sin relevar|sin relevamiento|falta relevar/i);
    expect(node.textContent).toMatch(/sugerencia|candidat/i);
    // …and it must not be labelled as surveyed under any wording.
    expect(node.textContent).not.toMatch(/\brelevados\b/i);
  });

  it('never labels the candidate counter as a survey result', () => {
    const { container } = renderWithMantine(<RelevamientoCobertura cobertura={COBERTURA} />);
    const text = (container.textContent ?? '').toLowerCase();
    expect(text).not.toContain('relevados (incluye');
    expect(text).not.toContain('total relevado');
  });

  it('renders a zero counter as zero, not as an absence', () => {
    renderWithMantine(
      <RelevamientoCobertura cobertura={{ ...COBERTURA, solo_candidato: 0 }} />
    );
    expect(within(screen.getByTestId('cobertura-solo-candidato')).getByText('0')).toBeTruthy();
  });
});
