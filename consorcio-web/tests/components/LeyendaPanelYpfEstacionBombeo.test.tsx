/**
 * LeyendaPanelYpfEstacionBombeo.test.tsx
 *
 * Covers the "Estación de bombeo YPF" legend entry inside `<LeyendaPanel />`.
 *
 * Unlike every other Pilar Azul / Pilar Verde block, this entry is:
 *   - ALWAYS rendered (no visibility prop, no conditional).
 *   - Renders a 12×12 orange (`#d84315`) circle swatch + label
 *     "Estación de bombeo YPF".
 *   - Mirrors the MapLibre circle paint on the `ypf-estacion-bombeo-circle`
 *     layer (orange fill, 2px white stroke).
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('<LeyendaPanel /> — YPF estación de bombeo block', () => {
  it('is ALWAYS rendered (no visibility prop gates it)', () => {
    renderWithMantine(<LeyendaPanel />);
    expect(screen.getByTestId('ypf-estacion-bombeo-legend')).toBeInTheDocument();
    expect(screen.getByText('Estación de bombeo YPF')).toBeInTheDocument();
  });

  it('is still rendered when every other Pilar Azul flag is off', () => {
    renderWithMantine(
      <LeyendaPanel
        pilarAzulCanalesRelevadosVisible={false}
        pilarAzulCanalesPropuestosVisible={false}
        pilarAzulEscuelasVisible={false}
      />,
    );
    expect(screen.getByTestId('ypf-estacion-bombeo-legend')).toBeInTheDocument();
  });

  it('is still rendered when every Pilar Azul flag is ON (coexistence)', () => {
    renderWithMantine(
      <LeyendaPanel
        pilarAzulCanalesRelevadosVisible
        pilarAzulCanalesPropuestosVisible
        pilarAzulEscuelasVisible
      />,
    );
    expect(screen.getByTestId('ypf-estacion-bombeo-legend')).toBeInTheDocument();
    expect(screen.getByTestId('canales-relevados-legend')).toBeInTheDocument();
    expect(screen.getByTestId('canales-propuestos-legend')).toBeInTheDocument();
    expect(screen.getByTestId('escuelas-legend')).toBeInTheDocument();
  });

  it('renders an orange circle swatch with 2px white stroke', () => {
    renderWithMantine(<LeyendaPanel />);

    const swatch = screen.getByTestId('ypf-estacion-bombeo-legend-swatch');
    expect(swatch).toBeInTheDocument();

    const style = (swatch as HTMLElement).style;
    // jsdom keeps the hex verbatim; browsers normalize to rgb().
    expect(style.backgroundColor.toLowerCase()).toMatch(
      /^(#d84315|rgb\(216,\s*67,\s*21\))$/,
    );
    expect(style.width).toBe('12px');
    expect(style.height).toBe('12px');
    expect(style.borderRadius).toBe('50%');
    expect(style.border).toContain('2px');
    expect(style.border.toLowerCase()).toContain('solid');
    expect(swatch).toHaveAttribute('aria-hidden', 'true');
  });

  it('contains NO <img> — swatch is pure CSS (no asset dependency)', () => {
    renderWithMantine(<LeyendaPanel />);
    const block = screen.getByTestId('ypf-estacion-bombeo-legend');
    expect(block.querySelector('img')).toBeNull();
  });
});
