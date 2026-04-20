/**
 * InfoPanelBpaBranch.test.tsx
 *
 * Covers the NEW Pilar Verde BPA-aware branch added to `<InfoPanel>` in Phase 3.
 *
 * Three detection paths:
 *   (1) Feature has flat `bpa_total` in properties           → render <BpaCard>
 *   (2) Feature has `nro_cuenta` matching a parcel in
 *       `bpaEnriched.parcels[]` with non-null `bpa_2025`     → render <BpaCard>
 *   (3) Neither                                               → render generic branch
 *
 * The generic (pre-Phase-3) behavior is preserved — falling back renders the
 * existing key/value dump.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { Feature } from 'geojson';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { InfoPanel } from '../../src/components/map2d/InfoPanel';
import type {
  BpaEnrichedFile,
  BpaHistoryFile,
} from '../../src/types/pilarVerde';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/**
 * FLAT feature properties as emitted by the `bpa_2025.geojson` source.
 * bpa_total present → BpaCard path (1).
 */
function buildFlatBpaFeature(): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-62.7, -32.6] },
    properties: {
      n_explotacion: 'La Sentina',
      cuenta: '150115736126',
      superficie: 245.7,
      superficie_bpa: 245.7,
      bpa_total: '8',
      id_explotacion: '1010',
      activa: '1',
      eje_persona: 'Si',
      eje_planeta: 'Si',
      eje_prosperidad: 'No',
      eje_alianza: 'No',
      capacitacion: 'Si',
      tranqueras_abiertas: 'No',
      polinizacion: 'No',
      integ_comunidad: 'No',
      nutricion_suelo: 'Si',
      rotacion_gramineas: 'Si',
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
    },
  };
}

/**
 * A catastro-like feature with `nro_cuenta` but NO bpa_total. The BPA data
 * has to come from the `bpaEnriched` lookup.
 */
function buildCatastroFeatureWithCuenta(cuenta: string): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-62.7, -32.6] },
    properties: {
      nro_cuenta: cuenta,
      Superficie_Tierra_Rural: 2457000, // m² in real IDECor
    },
  };
}

/** A fully populated enriched record — `bpa_2025` non-null. */
function buildBpaEnriched(cuenta: string, name: string): BpaEnrichedFile {
  return {
    schema_version: '1.2',
    generated_at: '2026-04-20T05:37:59Z',
    source: 'IDECor',
    parcels: [
      {
        nro_cuenta: cuenta,
        nomenclatura: '…',
        departamento: 'MARCOS JUAREZ',
        pedania: '…',
        superficie_ha: 245.7,
        valuacion: null,
        ley_forestal: 'aceptada',
        bpa_2025: {
          n_explotacion: name,
          superficie_bpa: 245.7,
          bpa_total: '8',
          id_explotacion: '1010',
          activa: true,
          ejes: { persona: 'Si', planeta: 'Si', prosperidad: 'No', alianza: 'No' },
          practicas: {
            capacitacion: 'Si',
            tranqueras_abiertas: 'No',
            polinizacion: 'No',
            integ_comunidad: 'No',
            nutricion_suelo: 'Si',
            rotacion_gramineas: 'Si',
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
          },
        },
        bpa_historico: {},
        años_bpa: 1,
        años_lista: ['2025'],
      },
    ],
  };
}

function buildBpaHistory(cuenta: string, years: string[]): BpaHistoryFile {
  const entry: Record<string, string> = {};
  for (const y of years) entry[y] = 'La Sentina';
  return {
    schema_version: '1.0',
    generated_at: '2026-04-20T05:37:59Z',
    history: { [cuenta]: entry },
  };
}

function buildBpaEnrichedWithHistory(
  cuenta: string,
  name: string,
  historyYears: string[],
): BpaEnrichedFile {
  const enriched = buildBpaEnriched(cuenta, name);
  const historico: Record<string, string> = {};
  for (const y of historyYears) historico[y] = name;
  enriched.parcels[0] = {
    ...enriched.parcels[0],
    bpa_historico: historico,
    años_bpa: historyYears.length + 1, // +1 for the 2025 record
    años_lista: [...historyYears, '2025'].sort(),
  };
  return enriched;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('<InfoPanel /> BPA branch', () => {
  it('renders BpaCard when the feature has a flat bpa_total', () => {
    renderWithMantine(
      <InfoPanel feature={buildFlatBpaFeature()} onClose={() => {}} />,
    );

    // BpaCard-specific markers
    expect(screen.getByTestId('bpa-card')).toBeInTheDocument();
    expect(screen.getByText('La Sentina')).toBeInTheDocument();
    expect(
      screen.getByText(/Datos:\s*IDECor.*Gobierno de Córdoba/i),
    ).toBeInTheDocument();
  });

  it('renders BpaCard when nro_cuenta matches an enriched parcel with non-null bpa_2025', () => {
    const feature = buildCatastroFeatureWithCuenta('150115736126');
    const bpaEnriched = buildBpaEnriched('150115736126', 'La Sentina');

    renderWithMantine(
      <InfoPanel
        feature={feature}
        onClose={() => {}}
        bpaEnriched={bpaEnriched}
      />,
    );

    expect(screen.getByTestId('bpa-card')).toBeInTheDocument();
    expect(screen.getByText('La Sentina')).toBeInTheDocument();
  });

  it('wires histórico years into BpaCard when enriched parcel has años_lista (Phase 7)', () => {
    const feature = buildCatastroFeatureWithCuenta('150115736126');
    // Enriched parcel with historical years + 2025 active.
    const bpaEnriched = buildBpaEnrichedWithHistory('150115736126', 'La Sentina', [
      '2019',
      '2020',
      '2024',
    ]);

    renderWithMantine(
      <InfoPanel
        feature={feature}
        onClose={() => {}}
        bpaEnriched={bpaEnriched}
      />,
    );
    const line = screen.getByTestId('bpa-card-anios');
    // Phase 7 label: "Hizo BPA: 2019, 2020, 2024, 2025 (4 años)"
    expect(line.textContent).toContain('2019, 2020, 2024, 2025');
    expect(line.textContent).toContain('(4 años)');
  });

  it('falls back to the generic property-dump branch when no BPA match exists', () => {
    const feature: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [-62.7, -32.6] },
      properties: { nombre: 'Canal Este', estado: 'activo' },
    };

    renderWithMantine(<InfoPanel feature={feature} onClose={() => {}} />);

    expect(screen.queryByTestId('bpa-card')).not.toBeInTheDocument();
    // Generic branch renders "Informacion" heading + property badges
    expect(screen.getByRole('heading', { name: /informacion/i })).toBeInTheDocument();
    expect(screen.getByText('nombre')).toBeInTheDocument();
    expect(screen.getByText('Canal Este')).toBeInTheDocument();
  });

  it('falls back to the generic branch when cuenta exists but años_bpa === 0', () => {
    const feature = buildCatastroFeatureWithCuenta('999999999999');
    const bpaEnriched: BpaEnrichedFile = {
      schema_version: '1.2',
      generated_at: '2026-04-20T05:37:59Z',
      source: 'IDECor',
      parcels: [
        {
          nro_cuenta: '999999999999',
          nomenclatura: null,
          departamento: null,
          pedania: null,
          superficie_ha: null,
          valuacion: null,
          ley_forestal: 'no_inscripta',
          bpa_2025: null,
          bpa_historico: {},
          años_bpa: 0,
          años_lista: [],
        },
      ],
    };

    renderWithMantine(
      <InfoPanel
        feature={feature}
        onClose={() => {}}
        bpaEnriched={bpaEnriched}
      />,
    );

    expect(screen.queryByTestId('bpa-card')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /informacion/i })).toBeInTheDocument();
  });

  it('returns null when feature is null (unchanged pre-existing behavior)', () => {
    renderWithMantine(<InfoPanel feature={null} onClose={() => {}} />);
    // Neither the BPA card nor the generic "Informacion" heading is rendered.
    expect(screen.queryByTestId('bpa-card')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /informacion/i })).not.toBeInTheDocument();
  });
});
