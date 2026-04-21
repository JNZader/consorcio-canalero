/**
 * LeyendaPanelEscuelas.test.tsx
 *
 * Covers the Pilar Azul "Escuelas rurales" legend block inside
 * `<LeyendaPanel />`. This file was updated when the symbol+icon rendering
 * approach was abandoned in favor of a native MapLibre `circle` layer —
 * the legend chip now mirrors that circle rather than thumbnailing the old
 * PNG icon (see `escuelasLayers.ts` header for history).
 *
 *   - "Escuela rural" chip — 12×12 blue circle swatch matching the map's
 *     `buildEscuelasCirclePaint()` (fill `#1976d2`, 2px white stroke) +
 *     label "Escuela rural" (singular, matches the 4-field popup).
 *     Visible iff `pilarAzulEscuelasVisible === true`.
 *
 * The test also pins the divider UX widening decided in Batch E risk #1:
 * when ONLY the escuelas toggle is ON (canales OFF), the Pilar Azul section
 * divider MUST still render so the legend visually separates Pilar Azul
 * from the Pilar Verde blocks above it.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

// ---------------------------------------------------------------------------
// Escuelas rurales block — conditional render + content
// ---------------------------------------------------------------------------

describe('<LeyendaPanel /> — Escuelas rurales block', () => {
  it('is hidden by default (no flag)', () => {
    renderWithMantine(<LeyendaPanel />);
    expect(screen.queryByTestId('escuelas-legend')).not.toBeInTheDocument();
    expect(screen.queryByText('Escuela rural')).not.toBeInTheDocument();
  });

  it('is hidden when the flag is explicitly false', () => {
    renderWithMantine(<LeyendaPanel pilarAzulEscuelasVisible={false} />);
    expect(screen.queryByTestId('escuelas-legend')).not.toBeInTheDocument();
    expect(screen.queryByText('Escuela rural')).not.toBeInTheDocument();
  });

  it('renders the chip when the flag is true', () => {
    renderWithMantine(<LeyendaPanel pilarAzulEscuelasVisible />);
    const block = screen.getByTestId('escuelas-legend');
    expect(block).toBeInTheDocument();
    // Label is the singular "Escuela rural" (matches the popup field
    // vocabulary — keep lowercase "rural" per canales conventions).
    expect(screen.getByText('Escuela rural')).toBeInTheDocument();
  });

  it('chip contains a blue circle swatch mirroring the MapLibre circle paint', () => {
    renderWithMantine(<LeyendaPanel pilarAzulEscuelasVisible />);
    const block = screen.getByTestId('escuelas-legend');

    // No <img> — the chip is purely CSS now (no external asset dependency).
    expect(block.querySelector('img')).toBeNull();

    const swatch = screen.getByTestId('escuelas-legend-swatch');
    expect(swatch).toBeInTheDocument();
    // The swatch is a rendered DOM element whose inline style must match the
    // MapLibre `circle` paint on the `escuelas-symbol` layer: blue fill +
    // 2px white stroke + round shape. We pin the actual inline style props.
    const style = (swatch as HTMLElement).style;
    // Accept either the hex literal we write OR the normalized rgb() form,
    // since different DOM implementations serialize inline colors
    // differently (jsdom keeps the hex verbatim; browsers emit rgb()).
    expect(style.backgroundColor.toLowerCase()).toMatch(
      /^(#1976d2|rgb\(25,\s*118,\s*210\))$/,
    );
    expect(style.width).toBe('12px');
    expect(style.height).toBe('12px');
    expect(style.borderRadius).toBe('50%');
    expect(style.border).toContain('2px');
    expect(style.border.toLowerCase()).toContain('solid');
    // Accessible label on the visual element — decorative-but-named so the
    // adjacent "Escuela rural" text is the primary a11y carrier.
    expect(swatch).toHaveAttribute('aria-label', 'Escuela rural');
  });

  it('unmounts the chip when the flag flips from true to false', () => {
    const { rerender } = renderWithMantine(
      <LeyendaPanel pilarAzulEscuelasVisible />,
    );
    expect(screen.getByTestId('escuelas-legend')).toBeInTheDocument();

    rerender(
      <MantineProvider>
        <LeyendaPanel pilarAzulEscuelasVisible={false} />
      </MantineProvider>,
    );
    expect(screen.queryByTestId('escuelas-legend')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Pilar Azul section divider — widening rule (Batch E risk #1)
// ---------------------------------------------------------------------------
//
// The existing divider guard in LeyendaPanel was:
//   (pilarAzulCanalesRelevadosVisible || pilarAzulCanalesPropuestosVisible)
// Batch F widens it to include escuelas so the divider still renders when
// ONLY the escuelas toggle is ON. We detect the divider via the a11y
// `role="separator"` contract — that is what Mantine `<Divider />` emits
// (not a bare `<hr>`).
// ---------------------------------------------------------------------------

describe('<LeyendaPanel /> — Pilar Azul section divider widening', () => {
  it('does NOT render the Pilar Azul divider when ALL Pilar Azul flags are off', () => {
    const { container } = renderWithMantine(<LeyendaPanel />);
    expect(container.querySelectorAll('[role="separator"]').length).toBe(0);
  });

  it('renders the Pilar Azul divider when ONLY escuelas is on', () => {
    const { container } = renderWithMantine(
      <LeyendaPanel pilarAzulEscuelasVisible />,
    );
    expect(
      container.querySelectorAll('[role="separator"]').length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId('escuelas-legend')).toBeInTheDocument();
  });

  it('renders the Pilar Azul divider when escuelas + canales relevados are on', () => {
    const { container } = renderWithMantine(
      <LeyendaPanel
        pilarAzulEscuelasVisible
        pilarAzulCanalesRelevadosVisible
      />,
    );
    expect(
      container.querySelectorAll('[role="separator"]').length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId('escuelas-legend')).toBeInTheDocument();
    expect(screen.getByTestId('canales-relevados-legend')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Coexistence with existing Pilar Azul blocks
// ---------------------------------------------------------------------------

describe('<LeyendaPanel /> — Escuelas coexists with canales blocks', () => {
  it('renders escuelas + relevados + propuestos together', () => {
    renderWithMantine(
      <LeyendaPanel
        pilarAzulEscuelasVisible
        pilarAzulCanalesRelevadosVisible
        pilarAzulCanalesPropuestosVisible
      />,
    );
    expect(screen.getByTestId('escuelas-legend')).toBeInTheDocument();
    expect(screen.getByTestId('canales-relevados-legend')).toBeInTheDocument();
    expect(screen.getByTestId('canales-propuestos-legend')).toBeInTheDocument();
  });
});
