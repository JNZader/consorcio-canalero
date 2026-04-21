/**
 * EscuelaCard.test.tsx
 *
 * Specifies `<EscuelaCard>` — the Pilar Azul escuela info-panel card shown
 * when the user clicks a point feature on the `escuelas-symbol` layer.
 *
 * Scope is frozen by design `sdd/escuelas-rurales/design` §9 and spec
 * `sdd/escuelas-rurales/spec` REQ-ESC-2 + REQ-ESC-5:
 *   - 4 fields rendered in this order: Nombre (title) · Localidad · Ámbito · Nivel.
 *   - No conditional rows, no empty-state branches (ETL guarantees the 4 values).
 *   - `nombre` humanization: ETL ships raw `"Esc. …"`; card replaces the leading
 *     `"Esc. "` with `"Escuela "` for display. The map label keeps the raw
 *     prefix (that path lives in `escuelasLayers.ts::buildEscuelasLabelLayout`
 *     via `['get', 'nombre']` — NOT tested here). Carry-over from Batch D risks
 *     note (apply-progress #2061 — risk #1).
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { EscuelaCard } from '../../src/components/map2d/EscuelaCard';
import type { EscuelaFeatureProperties } from '../../src/types/escuelas';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

// ---------------------------------------------------------------------------
// Fixture builder — mirrors the real ETL output shape. The raw `Esc. ` prefix
// is preserved (that is the on-disk shape per `types/escuelas.ts` jsdoc).
// ---------------------------------------------------------------------------

function buildEscuelaProperties(
  overrides: Partial<EscuelaFeatureProperties> = {},
): EscuelaFeatureProperties {
  return {
    nombre: 'Esc. Joaquín Víctor González',
    localidad: 'Monte Leña',
    ambito: 'Rural Aglomerado',
    nivel: 'Inicial · Primario',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('<EscuelaCard /> — nombre title + humanization', () => {
  it('renders the nombre as the card heading', () => {
    renderWithMantine(<EscuelaCard properties={buildEscuelaProperties()} />);
    // Heading text is HUMANIZED ("Escuela …"), NOT the raw ETL prefix.
    expect(
      screen.getByRole('heading', { name: 'Escuela Joaquín Víctor González' }),
    ).toBeInTheDocument();
  });

  it('humanizes the "Esc. " prefix to "Escuela " (InfoPanel-only)', () => {
    renderWithMantine(
      <EscuelaCard
        properties={buildEscuelaProperties({ nombre: 'Esc. Sarmiento' })}
      />,
    );
    const heading = screen.getByTestId('escuela-card').querySelector('h5');
    expect(heading?.textContent).toBe('Escuela Sarmiento');
    // The raw "Esc. " prefix MUST NOT appear in the rendered card.
    expect(screen.queryByText(/^Esc\.\s/)).not.toBeInTheDocument();
  });

  it('leaves a nombre without the "Esc. " prefix untouched', () => {
    // Defensive: if a future ETL ships a name without the prefix, the card
    // must not mangle it.
    renderWithMantine(
      <EscuelaCard
        properties={buildEscuelaProperties({ nombre: 'Escuela Rural Sin Prefijo' })}
      />,
    );
    expect(
      screen.getByRole('heading', { name: 'Escuela Rural Sin Prefijo' }),
    ).toBeInTheDocument();
  });
});

describe('<EscuelaCard /> — 3 labeled rows (Localidad · Ámbito · Nivel)', () => {
  it('renders the Localidad label + value', () => {
    renderWithMantine(
      <EscuelaCard
        properties={buildEscuelaProperties({ localidad: 'Monte Leña' })}
      />,
    );
    const card = screen.getByTestId('escuela-card');
    expect(within(card).getByText('Localidad')).toBeInTheDocument();
    expect(within(card).getByText('Monte Leña')).toBeInTheDocument();
  });

  it('renders the Ámbito label + value for "Rural Aglomerado"', () => {
    renderWithMantine(
      <EscuelaCard
        properties={buildEscuelaProperties({ ambito: 'Rural Aglomerado' })}
      />,
    );
    const card = screen.getByTestId('escuela-card');
    expect(within(card).getByText('Ámbito')).toBeInTheDocument();
    expect(within(card).getByText('Rural Aglomerado')).toBeInTheDocument();
  });

  it('renders the Ámbito label + value for "Rural Disperso"', () => {
    renderWithMantine(
      <EscuelaCard
        properties={buildEscuelaProperties({ ambito: 'Rural Disperso' })}
      />,
    );
    const card = screen.getByTestId('escuela-card');
    expect(within(card).getByText('Rural Disperso')).toBeInTheDocument();
  });

  it('renders the Nivel label + value and preserves the `·` middot', () => {
    renderWithMantine(
      <EscuelaCard
        properties={buildEscuelaProperties({ nivel: 'Inicial · Primario' })}
      />,
    );
    const card = screen.getByTestId('escuela-card');
    expect(within(card).getByText('Nivel')).toBeInTheDocument();
    // Middot is VALUE content (NOT a separator) — spec scenario
    // "Parser preserves `·` inside `Nivel`" ripples into the card.
    expect(within(card).getByText('Inicial · Primario')).toBeInTheDocument();
  });
});

describe('<EscuelaCard /> — rigid 4-field layout (no conditional rows)', () => {
  it('renders exactly 3 labels (Localidad, Ámbito, Nivel) always', () => {
    renderWithMantine(<EscuelaCard properties={buildEscuelaProperties()} />);
    const card = screen.getByTestId('escuela-card');
    // Exactly 3 labels — no optional rows (design §9).
    expect(within(card).getByText('Localidad')).toBeInTheDocument();
    expect(within(card).getByText('Ámbito')).toBeInTheDocument();
    expect(within(card).getByText('Nivel')).toBeInTheDocument();
  });

  it('never renders an empty-state placeholder for the 4 required fields', () => {
    // All 4 fields are REQUIRED non-empty strings per REQ-ESC-2.
    renderWithMantine(<EscuelaCard properties={buildEscuelaProperties()} />);
    const card = screen.getByTestId('escuela-card');
    // No "—", "N/A", or conditional empty-state fallback.
    expect(within(card).queryByText('—')).not.toBeInTheDocument();
    expect(within(card).queryByText(/N\/A/i)).not.toBeInTheDocument();
    // Card body is non-empty and has all 4 values.
    expect(card.textContent).toContain('Escuela Joaquín Víctor González');
    expect(card.textContent).toContain('Monte Leña');
    expect(card.textContent).toContain('Rural Aglomerado');
    expect(card.textContent).toContain('Inicial · Primario');
  });
});
