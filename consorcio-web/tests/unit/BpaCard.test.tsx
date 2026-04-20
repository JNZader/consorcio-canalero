/**
 * BpaCard.test.tsx
 *
 * Component tests for the Pilar Verde BPA card rendered inside InfoPanel.
 *
 * Phase 7 refinement — the card no longer renders 21 chips. Instead it shows:
 *   - A header line with nombre + cuenta + "Activa 2025" / "Sin actividad 2025"
 *   - A "Hizo BPA" line with the year list + total años count
 *   - When a 2025 BPA record is present: 4 axis badges + a compact "Prácticas
 *     que cumple" line listing only the adopted practicas (Si)
 *   - IDECor attribution footer
 *
 * The card is prop-driven — all data enters through props, no context or hooks.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { BpaCard } from '../../src/components/map2d/BpaCard';
import { PILAR_VERDE_COLORS } from '../../src/components/map2d/pilarVerdeLayers';
import type {
  Bpa2025EnrichedRecord,
  BpaPracticesRecord,
} from '../../src/types/pilarVerde';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

function buildPractices(overrides: Partial<BpaPracticesRecord> = {}): BpaPracticesRecord {
  const base: BpaPracticesRecord = {
    capacitacion: 'No',
    tranqueras_abiertas: 'No',
    polinizacion: 'No',
    integ_comunidad: 'No',
    nutricion_suelo: 'No',
    rotacion_gramineas: 'No',
    pasturas_implantadas: 'No',
    sistema_terraza: 'No',
    bioinsumos: 'No',
    manejo_de_cultivo_int: 'No',
    trazabilidad: 'No',
    tecn_pecuaria: 'No',
    agricultura_de_precision: 'No',
    economia_circular: 'No',
    participacion_grup_asociativo: 'No',
    indiacagro: 'No',
    caminos_rurales: 'No',
    ag_tech: 'No',
    bpa_tutor: 'No',
    corredores_bio: 'No',
    riego_precision: 'No',
  };
  return { ...base, ...overrides };
}

function buildBpa(
  overrides: Partial<Bpa2025EnrichedRecord> = {},
): Bpa2025EnrichedRecord {
  return {
    n_explotacion: 'La Sentina',
    superficie_bpa: 245.7,
    bpa_total: '8',
    id_explotacion: '1010',
    activa: true,
    ejes: { persona: 'Si', planeta: 'Si', prosperidad: 'No', alianza: 'No' },
    practicas: buildPractices({
      capacitacion: 'Si',
      rotacion_gramineas: 'Si',
      nutricion_suelo: 'Si',
    }),
    ...overrides,
  };
}

describe('<BpaCard />', () => {
  it('renders the explotación name, cuenta and superficie in the header', () => {
    renderWithMantine(
      <BpaCard
        nombre="La Sentina"
        cuenta="150115736126"
        superficie_ha={245.7}
        años_bpa={3}
        años_lista={['2019', '2020', '2025']}
        bpa_activa_2025
        bpa={buildBpa()}
      />,
    );

    expect(screen.getByText('La Sentina')).toBeInTheDocument();
    expect(screen.getByText(/150115736126/)).toBeInTheDocument();
    expect(screen.getByText(/245\.7/)).toBeInTheDocument();
  });

  it('renders "Activa 2025" marker in the header when bpa_activa_2025 is true', () => {
    renderWithMantine(
      <BpaCard
        nombre="La Sentina"
        cuenta="150115736126"
        superficie_ha={245.7}
        años_bpa={1}
        años_lista={['2025']}
        bpa_activa_2025
        bpa={buildBpa()}
      />,
    );
    expect(screen.getByText(/Activa 2025/i)).toBeInTheDocument();
  });

  it('renders "Sin actividad 2025" marker when bpa_activa_2025 is false', () => {
    renderWithMantine(
      <BpaCard
        nombre="Los Olivos"
        cuenta="900000000000"
        años_bpa={2}
        años_lista={['2019', '2020']}
        bpa_activa_2025={false}
      />,
    );
    expect(screen.getByText(/Sin actividad 2025/i)).toBeInTheDocument();
  });

  it('renders the "Hizo BPA" line with sorted years and total count', () => {
    renderWithMantine(
      <BpaCard
        nombre="La Sentina"
        cuenta="150115736126"
        años_bpa={3}
        años_lista={['2019', '2020', '2025']}
        bpa_activa_2025
        bpa={buildBpa()}
      />,
    );
    const line = screen.getByTestId('bpa-card-anios');
    expect(line.textContent).toContain('2019, 2020, 2025');
    expect(line.textContent).toContain('(3 años)');
  });

  it('renders 4 axis badges with Persona / Planeta / Prosperidad / Alianza labels when bpa is provided', () => {
    renderWithMantine(
      <BpaCard
        nombre="La Sentina"
        cuenta="150115736126"
        años_bpa={1}
        años_lista={['2025']}
        bpa_activa_2025
        bpa={buildBpa()}
      />,
    );

    expect(screen.getByText(/Persona:\s*Si/i)).toBeInTheDocument();
    expect(screen.getByText(/Planeta:\s*Si/i)).toBeInTheDocument();
    expect(screen.getByText(/Prosperidad:\s*No/i)).toBeInTheDocument();
    expect(screen.getByText(/Alianza:\s*No/i)).toBeInTheDocument();
  });

  it('tags each axis badge with the spec color palette', () => {
    const { container } = renderWithMantine(
      <BpaCard
        nombre="La Sentina"
        cuenta="150115736126"
        bpa={buildBpa()}
      />,
    );

    const persona = container.querySelector('[data-eje="persona"]');
    const planeta = container.querySelector('[data-eje="planeta"]');
    const prosperidad = container.querySelector('[data-eje="prosperidad"]');
    const alianza = container.querySelector('[data-eje="alianza"]');

    expect(persona).not.toBeNull();
    expect(planeta).not.toBeNull();
    expect(prosperidad).not.toBeNull();
    expect(alianza).not.toBeNull();
    expect(persona?.getAttribute('data-eje-color')).toBe(PILAR_VERDE_COLORS.ejePersona);
    expect(planeta?.getAttribute('data-eje-color')).toBe(PILAR_VERDE_COLORS.ejePlaneta);
    expect(prosperidad?.getAttribute('data-eje-color')).toBe(PILAR_VERDE_COLORS.ejeProsperidad);
    expect(alianza?.getAttribute('data-eje-color')).toBe(PILAR_VERDE_COLORS.ejeAlianza);
  });

  it('renders only ADOPTED practicas in the compact list', () => {
    renderWithMantine(
      <BpaCard
        nombre="La Sentina"
        cuenta="150115736126"
        bpa={buildBpa()}
      />,
    );
    const line = screen.getByTestId('bpa-card-practicas-adoptadas');
    // 3 adopted: capacitacion, rotacion_gramineas, nutricion_suelo.
    expect(line.textContent).toContain('Capacitación');
    expect(line.textContent).toContain('Rotación de gramíneas');
    expect(line.textContent).toContain('Nutrición del suelo');
    expect(line.textContent).toContain('(3/21)');
    // NOT adopted practices must not appear in the compact list.
    expect(line.textContent).not.toContain('Trazabilidad');
    expect(line.textContent).not.toContain('AgTech');
  });

  it('shows "No adoptó prácticas" when all practicas are "No"', () => {
    renderWithMantine(
      <BpaCard
        nombre="La Sentina"
        cuenta="150115736126"
        bpa={buildBpa({ practicas: buildPractices() })}
      />,
    );
    expect(screen.getByTestId('bpa-card-sin-practicas')).toBeInTheDocument();
  });

  it('HIDES ejes badges + practicas list when bpa prop is null (historical-only parcel)', () => {
    renderWithMantine(
      <BpaCard
        nombre="Los Olivos"
        cuenta="900000000000"
        años_bpa={2}
        años_lista={['2019', '2020']}
        bpa_activa_2025={false}
        bpa={null}
      />,
    );
    expect(screen.queryByText(/Persona:/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId('bpa-card-practicas-adoptadas')).not.toBeInTheDocument();
  });

  it('renders IDECor attribution footer', () => {
    renderWithMantine(
      <BpaCard
        nombre="La Sentina"
        cuenta="150115736126"
        bpa={buildBpa()}
      />,
    );
    expect(
      screen.getByText(/Datos:\s*IDECor.*Gobierno de Córdoba/i),
    ).toBeInTheDocument();
  });
});
