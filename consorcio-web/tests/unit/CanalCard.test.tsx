/**
 * CanalCard.test.tsx
 *
 * Specifies `<CanalCard>` — the Pilar Azul info-panel card that replaces the
 * generic property dump when the user clicks a canal feature.
 *
 * The test is the LIVING ACCEPTANCE CRITERIA for Task 3.1/3.2 in
 * `sdd/canales-relevados-y-propuestas/tasks`. Scenarios map 1:1 to the spec
 * (see `sdd/canales-relevados-y-propuestas/spec` — "InfoPanel Canal Branch +
 * CanalCard").
 *
 * Cases covered:
 *   - Full relevado: nombre, codigo, estado label, longitud, tramo, NO prioridad badge.
 *   - Full propuesto Alta: nombre, codigo, estado, prioridad badge with Etapa 1 color,
 *       longitud with declared annotation, descripcion, tramo, ★ Destacado.
 *   - Minimal canal (nulls everywhere except nombre + longitud + estado).
 *   - Longitud formatting: matches the Rioplatense 'es-AR' locale (1.355 m),
 *     and the declared-longitud parenthetical is only shown when it differs.
 *   - Etapa colors: all 5 map to `CANALES_COLORS.propuesto*`.
 *   - Featured indicator renders `★ Destacado`, hidden otherwise.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { CanalCard } from '../../src/components/map2d/CanalCard';
import { CANALES_COLORS } from '../../src/components/map2d/canalesLayers';
import { formatLongitud } from '../../src/components/map2d/canalesFormat';
import type { CanalFeatureProperties } from '../../src/types/canales';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

// ---------------------------------------------------------------------------
// Fixture builders
// ---------------------------------------------------------------------------

function buildRelevado(
  overrides: Partial<CanalFeatureProperties> = {},
): CanalFeatureProperties {
  return {
    id: 'canal-norte-readec',
    codigo: 'N4',
    nombre: 'Readecuación tramo inicial colector norte',
    descripcion: null,
    estado: 'relevado',
    longitud_m: 1355,
    longitud_declarada_m: 1355,
    prioridad: null,
    featured: false,
    tramo_folder: 'Canal Norte',
    source_style: 'readec',
    ...overrides,
  };
}

function buildPropuesto(
  overrides: Partial<CanalFeatureProperties> = {},
): CanalFeatureProperties {
  return {
    id: 'propuesto-alta',
    codigo: 'E12',
    nombre: 'Nuevo colector sur',
    descripcion: 'Obra principal',
    estado: 'propuesto',
    longitud_m: 2400,
    longitud_declarada_m: 2500,
    prioridad: 'Alta',
    featured: true,
    tramo_folder: 'Canal Sur',
    source_style: 'prio_Alta',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('<CanalCard /> — header + estado label', () => {
  it('renders nombre as the heading', () => {
    renderWithMantine(<CanalCard properties={buildRelevado()} />);
    expect(
      screen.getByRole('heading', { name: 'Readecuación tramo inicial colector norte' }),
    ).toBeInTheDocument();
  });

  it('shows "relevado" estado label + codigo when present', () => {
    renderWithMantine(<CanalCard properties={buildRelevado({ codigo: 'N4' })} />);
    const subtitle = screen.getByTestId('canal-card-subtitle');
    expect(subtitle.textContent).toContain('N4');
    expect(subtitle.textContent?.toLowerCase()).toContain('relevado');
  });

  it('shows "propuesto" estado label + codigo when present', () => {
    renderWithMantine(<CanalCard properties={buildPropuesto()} />);
    const subtitle = screen.getByTestId('canal-card-subtitle');
    expect(subtitle.textContent).toContain('E12');
    expect(subtitle.textContent?.toLowerCase()).toContain('propuesto');
  });

  it('omits codigo from the subtitle when null', () => {
    renderWithMantine(
      <CanalCard properties={buildRelevado({ codigo: null })} />,
    );
    const subtitle = screen.getByTestId('canal-card-subtitle');
    // Should NOT show a leading "null · relevado" glitch.
    expect(subtitle.textContent).not.toContain('null');
    expect(subtitle.textContent?.toLowerCase()).toContain('relevado');
  });
});

describe('<CanalCard /> — prioridad Badge', () => {
  it('does NOT render a prioridad Badge for relevados (null prioridad)', () => {
    renderWithMantine(<CanalCard properties={buildRelevado()} />);
    expect(screen.queryByTestId('canal-card-prioridad')).not.toBeInTheDocument();
  });

  it('renders a prioridad Badge for propuesto Alta with the Alta color', () => {
    renderWithMantine(<CanalCard properties={buildPropuesto({ prioridad: 'Alta' })} />);
    const badge = screen.getByTestId('canal-card-prioridad');
    expect(badge.textContent).toContain('Alta');
    expect(badge).toHaveAttribute('data-color', CANALES_COLORS.propuestoAlta);
  });

  it('maps all 5 etapas to their matching color token', () => {
    const table = [
      { prioridad: 'Alta' as const, color: CANALES_COLORS.propuestoAlta },
      { prioridad: 'Media-Alta' as const, color: CANALES_COLORS.propuestoMediaAlta },
      { prioridad: 'Media' as const, color: CANALES_COLORS.propuestoMedia },
      { prioridad: 'Opcional' as const, color: CANALES_COLORS.propuestoOpcional },
      { prioridad: 'Largo plazo' as const, color: CANALES_COLORS.propuestoLargoPlazo },
    ];
    for (const { prioridad, color } of table) {
      const { unmount } = renderWithMantine(
        <CanalCard properties={buildPropuesto({ prioridad })} />,
      );
      const badge = screen.getByTestId('canal-card-prioridad');
      expect(badge).toHaveAttribute('data-color', color);
      expect(badge.textContent).toContain(prioridad);
      unmount();
    }
  });

  it('does NOT render a prioridad Badge for propuestos with null prioridad', () => {
    renderWithMantine(
      <CanalCard properties={buildPropuesto({ prioridad: null })} />,
    );
    expect(screen.queryByTestId('canal-card-prioridad')).not.toBeInTheDocument();
  });
});

describe('<CanalCard /> — longitud formatting', () => {
  it('shows "2.456 m" when computed === declared', () => {
    renderWithMantine(
      <CanalCard
        properties={buildRelevado({ longitud_m: 2456, longitud_declarada_m: 2456 })}
      />,
    );
    const cell = screen.getByTestId('canal-card-longitud');
    expect(cell.textContent).toBe('2.456 m');
  });

  it('shows "2.456 m · (2.500 m declarada)" when computed differs from declared', () => {
    renderWithMantine(
      <CanalCard
        properties={buildRelevado({ longitud_m: 2456, longitud_declarada_m: 2500 })}
      />,
    );
    const cell = screen.getByTestId('canal-card-longitud');
    expect(cell.textContent).toBe('2.456 m · (2.500 m declarada)');
  });

  it('shows only computed when declared is null', () => {
    renderWithMantine(
      <CanalCard
        properties={buildRelevado({ longitud_m: 1355, longitud_declarada_m: null })}
      />,
    );
    const cell = screen.getByTestId('canal-card-longitud');
    expect(cell.textContent).toBe('1.355 m');
  });

  it('uses the shared formatLongitud helper verbatim', () => {
    // Guards against accidental drift between the card and the pure helper.
    expect(formatLongitud(1355)).toBe('1.355 m');
    expect(formatLongitud(2456, 2500)).toBe('2.456 m · (2.500 m declarada)');
    expect(formatLongitud(1355, 1355)).toBe('1.355 m');
    expect(formatLongitud(1355, null)).toBe('1.355 m');
  });
});

describe('<CanalCard /> — descripción', () => {
  it('renders descripción text when present', () => {
    renderWithMantine(
      <CanalCard
        properties={buildPropuesto({ descripcion: 'Obra principal' })}
      />,
    );
    expect(screen.getByText('Obra principal')).toBeInTheDocument();
  });

  it('does NOT render a description block when null', () => {
    renderWithMantine(
      <CanalCard properties={buildRelevado({ descripcion: null })} />,
    );
    expect(screen.queryByTestId('canal-card-descripcion')).not.toBeInTheDocument();
  });
});

describe('<CanalCard /> — featured indicator', () => {
  it('renders "★ Destacado" when featured is true', () => {
    renderWithMantine(
      <CanalCard properties={buildPropuesto({ featured: true })} />,
    );
    const marker = screen.getByTestId('canal-card-featured');
    expect(marker.textContent).toContain('★');
    expect(marker.textContent?.toLowerCase()).toContain('destacado');
  });

  it('omits the ★ marker when featured is false', () => {
    renderWithMantine(
      <CanalCard properties={buildRelevado({ featured: false })} />,
    );
    expect(screen.queryByTestId('canal-card-featured')).not.toBeInTheDocument();
  });
});

describe('<CanalCard /> — tramo folder', () => {
  it('renders "Tramo: {folder}" when tramo_folder is present', () => {
    renderWithMantine(
      <CanalCard properties={buildRelevado({ tramo_folder: 'Canal Norte' })} />,
    );
    const tramo = screen.getByTestId('canal-card-tramo');
    expect(tramo.textContent).toContain('Canal Norte');
  });

  it('omits the tramo line when tramo_folder is null', () => {
    renderWithMantine(
      <CanalCard properties={buildRelevado({ tramo_folder: null })} />,
    );
    expect(screen.queryByTestId('canal-card-tramo')).not.toBeInTheDocument();
  });
});

describe('<CanalCard /> — minimal metadata canal', () => {
  it('renders without errors when everything nullable is null', () => {
    const minimal: CanalFeatureProperties = {
      id: 'canal-ne-sin-intervencion',
      codigo: null,
      nombre: 'Canal NE',
      descripcion: null,
      estado: 'relevado',
      longitud_m: 1200,
      longitud_declarada_m: null,
      prioridad: null,
      featured: false,
      tramo_folder: null,
      source_style: null,
    };
    renderWithMantine(<CanalCard properties={minimal} />);
    // Nombre + longitud always render.
    expect(screen.getByRole('heading', { name: 'Canal NE' })).toBeInTheDocument();
    expect(screen.getByTestId('canal-card-longitud').textContent).toBe('1.200 m');
    // Optional sections NOT rendered.
    expect(screen.queryByTestId('canal-card-prioridad')).not.toBeInTheDocument();
    expect(screen.queryByTestId('canal-card-descripcion')).not.toBeInTheDocument();
    expect(screen.queryByTestId('canal-card-featured')).not.toBeInTheDocument();
    expect(screen.queryByTestId('canal-card-tramo')).not.toBeInTheDocument();
  });
});
