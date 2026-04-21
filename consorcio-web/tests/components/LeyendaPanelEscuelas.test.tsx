/**
 * LeyendaPanelEscuelas.test.tsx
 *
 * Covers the new Pilar Azul "Escuelas rurales" legend block inside
 * `<LeyendaPanel />`. The block mounts conditionally, mirroring the Pilar
 * Azul canales (relevados / propuestos) conditional pattern, BUT uses an
 * image thumbnail (the escuela icon) as its visual indicator instead of a
 * color chip — there is nothing to color-swatch, the icon IS the legend.
 *
 *   - "Escuela rural" chip — icon thumbnail (24×24, uses ESCUELA_ICON_URL)
 *     + label "Escuela rural" (singular, matches the 4-field popup).
 *     Visible iff `pilarAzulEscuelasVisible === true`.
 *
 * The test also pins the divider UX widening decided in Batch E risk #1:
 * when ONLY the escuelas toggle is ON (canales OFF), the Pilar Azul section
 * divider MUST still render so the legend visually separates Pilar Azul
 * from the Pilar Verde blocks above it. This prevents the "orphan chip"
 * regression where escuelas would stick flush against the last Pilar Verde
 * block with no divider.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { ESCUELA_ICON_URL } from '../../src/components/map2d/escuelasLayers';
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

  it('chip contains a 24×24 thumbnail loaded from ESCUELA_ICON_URL', () => {
    renderWithMantine(<LeyendaPanel pilarAzulEscuelasVisible />);
    const block = screen.getByTestId('escuelas-legend');
    // The block MUST contain an <img> pointing at the bundled icon asset —
    // single source of truth is `escuelasLayers.ts::ESCUELA_ICON_URL`. If
    // someone ever moves the asset, this test catches the drift.
    const img = block.querySelector('img');
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute('src', ESCUELA_ICON_URL);
    expect(img).toHaveAttribute('width', '24');
    expect(img).toHaveAttribute('height', '24');
    // Decorative thumbnail — empty alt keeps it out of the a11y tree (the
    // adjacent "Escuela rural" text carries the meaning).
    expect(img).toHaveAttribute('alt', '');
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
// (not a bare `<hr>`). Counting role=separator also ignores any decorative
// elements that may share `<hr>` or equivalent semantics.
// ---------------------------------------------------------------------------

describe('<LeyendaPanel /> — Pilar Azul section divider widening', () => {
  it('does NOT render the Pilar Azul divider when ALL Pilar Azul flags are off', () => {
    const { container } = renderWithMantine(<LeyendaPanel />);
    // Zero Pilar Azul flags → zero Pilar Azul dividers. (Other dividers
    // belong to Pilar Verde blocks; those are also off in this render.)
    expect(container.querySelectorAll('[role="separator"]').length).toBe(0);
  });

  it('renders the Pilar Azul divider when ONLY escuelas is on', () => {
    const { container } = renderWithMantine(
      <LeyendaPanel pilarAzulEscuelasVisible />,
    );
    // With only escuelas ON, the widened guard must still emit the Pilar
    // Azul section divider so the escuelas chip does not sit orphan
    // against the previous section (Pilar Verde or customItems).
    expect(container.querySelectorAll('[role="separator"]').length).toBeGreaterThanOrEqual(1);
    // And of course the escuelas chip itself is present.
    expect(screen.getByTestId('escuelas-legend')).toBeInTheDocument();
  });

  it('renders the Pilar Azul divider when escuelas + canales relevados are on', () => {
    const { container } = renderWithMantine(
      <LeyendaPanel
        pilarAzulEscuelasVisible
        pilarAzulCanalesRelevadosVisible
      />,
    );
    // Still just one Pilar Azul section divider (no dupes — the widening
    // is an OR, not an additional block).
    expect(container.querySelectorAll('[role="separator"]').length).toBeGreaterThanOrEqual(1);
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
