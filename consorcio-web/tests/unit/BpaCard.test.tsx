/**
 * BpaCard.test.tsx
 *
 * Component tests for the Pilar Verde BPA card rendered inside InfoPanel
 * when the selected feature represents a 2025 BPA record.
 *
 * Spec reference: `sdd/pilar-verde-bpa-agroforestal/spec` § "InfoPanel BPA Branch"
 * (flat layout, no eje grouping, 4 axis badges + 21 chip single flat list).
 *
 * The card is rendered WITHOUT any context (no usePilarVerde, no route). All
 * data enters via props — this keeps testing straightforward and makes the
 * component reusable in stories / Playwright snapshots later.
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
        bpa={buildBpa()}
        cuenta="150115736126"
        superficie_ha={245.7}
      />,
    );

    expect(screen.getByText('La Sentina')).toBeInTheDocument();
    expect(screen.getByText(/150115736126/)).toBeInTheDocument();
    expect(screen.getByText(/245\.7/)).toBeInTheDocument();
  });

  it('renders 4 axis badges with Persona / Planeta / Prosperidad / Alianza labels', () => {
    renderWithMantine(<BpaCard bpa={buildBpa()} cuenta="150115736126" />);

    // Each badge has "Persona: Si" / "Planeta: Si" / "Prosperidad: No" / "Alianza: No"
    expect(screen.getByText(/Persona:\s*Si/i)).toBeInTheDocument();
    expect(screen.getByText(/Planeta:\s*Si/i)).toBeInTheDocument();
    expect(screen.getByText(/Prosperidad:\s*No/i)).toBeInTheDocument();
    expect(screen.getByText(/Alianza:\s*No/i)).toBeInTheDocument();
  });

  it('tags each axis badge with the spec color palette', () => {
    const { container } = renderWithMantine(
      <BpaCard bpa={buildBpa()} cuenta="150115736126" />,
    );

    // We render axis badges with a deterministic `data-eje-color` attribute so
    // CSS-in-JS inline styles remain testable without brittle style strings.
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

  it('renders all 21 practice chips in a single flat list (no eje grouping)', () => {
    const { container } = renderWithMantine(
      <BpaCard bpa={buildBpa()} cuenta="150115736126" />,
    );

    const chips = container.querySelectorAll('[data-practica-chip]');
    expect(chips).toHaveLength(21);
  });

  it('renders practice chips sorted alphabetically — ag_tech first, trazabilidad last', () => {
    const { container } = renderWithMantine(
      <BpaCard bpa={buildBpa()} cuenta="150115736126" />,
    );

    const chips = container.querySelectorAll('[data-practica-chip]');
    const firstKey = chips[0]?.getAttribute('data-practica-key');
    const lastKey = chips[chips.length - 1]?.getAttribute('data-practica-key');
    expect(firstKey).toBe('ag_tech');
    expect(lastKey).toBe('trazabilidad');
  });

  it('marks adopted chips with data-adopted="true" and non-adopted with "false"', () => {
    const { container } = renderWithMantine(
      <BpaCard bpa={buildBpa()} cuenta="150115736126" />,
    );

    const adopted = container.querySelectorAll('[data-practica-chip][data-adopted="true"]');
    const notAdopted = container.querySelectorAll(
      '[data-practica-chip][data-adopted="false"]',
    );
    // fixture has 3 Si: capacitacion, rotacion_gramineas, nutricion_suelo
    expect(adopted).toHaveLength(3);
    expect(notAdopted).toHaveLength(18);
  });

  it('renders chip labels in Rioplatense Spanish (humanized)', () => {
    renderWithMantine(<BpaCard bpa={buildBpa()} cuenta="150115736126" />);
    expect(screen.getByText('Capacitación')).toBeInTheDocument();
    expect(screen.getByText('Rotación de gramíneas')).toBeInTheDocument();
    expect(screen.getByText('AgTech')).toBeInTheDocument();
    expect(screen.getByText('Trazabilidad')).toBeInTheDocument();
  });

  it('renders the histórico footer with years sorted ascending when present', () => {
    renderWithMantine(
      <BpaCard
        bpa={buildBpa()}
        cuenta="150115736126"
        historico={{ '2024': 'La Sentina', '2019': 'La Sentina', '2020': 'La Sentina' }}
      />,
    );
    const footer = screen.getByText(/En BPA:/i);
    expect(footer).toBeInTheDocument();
    expect(footer.textContent).toMatch(/2019.*2020.*2024/);
  });

  it('HIDES the histórico footer when no historico prop is given', () => {
    renderWithMantine(<BpaCard bpa={buildBpa()} cuenta="150115736126" />);
    expect(screen.queryByText(/En BPA:/i)).not.toBeInTheDocument();
  });

  it('HIDES the histórico footer when historico is an empty object', () => {
    renderWithMantine(
      <BpaCard bpa={buildBpa()} cuenta="150115736126" historico={{}} />,
    );
    expect(screen.queryByText(/En BPA:/i)).not.toBeInTheDocument();
  });

  it('renders IDECor attribution footer', () => {
    renderWithMantine(<BpaCard bpa={buildBpa()} cuenta="150115736126" />);
    expect(
      screen.getByText(/Datos:\s*IDECor.*Gobierno de Córdoba/i),
    ).toBeInTheDocument();
  });
});
