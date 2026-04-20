/**
 * InfoPanelCanalBranch.test.tsx
 *
 * Covers the Pilar Azul (Canales) branch added to `<InfoPanel>` in Phase 3.
 *
 * Detection path:
 *   feature.properties.estado === 'relevado' || 'propuesto' → render <CanalCard>
 *
 * Priority order among stacked features (top-most first, one section each):
 *   (1) BPA-aware branch — if the feature matches Pilar Verde BPA heuristics
 *   (2) CanalCard branch — if `estado` matches 'relevado' / 'propuesto'
 *   (3) Generic whitelist dump — fallback for everything else
 *
 * The Phase 8 stacking contract (one section per feature) is preserved: a
 * multi-feature array of canals renders each canal inside its own CanalCard
 * section, separated by dividers.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { Feature } from 'geojson';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { InfoPanel } from '../../src/components/map2d/InfoPanel';
import type { CanalFeatureProperties } from '../../src/types/canales';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function buildCanalFeature(
  overrides: Partial<CanalFeatureProperties> = {},
): Feature {
  const properties: CanalFeatureProperties = {
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
  return {
    type: 'Feature',
    geometry: { type: 'LineString', coordinates: [[-62.7, -32.6], [-62.71, -32.61]] },
    properties: properties as unknown as Record<string, unknown>,
  };
}

function buildGenericFeature(): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-62.5, -32.5] },
    properties: { foo: 'bar' },
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('<InfoPanel /> — Canal detection branch', () => {
  it('renders <CanalCard> for a relevado feature', () => {
    const feature = buildCanalFeature({ estado: 'relevado' });
    renderWithMantine(
      <InfoPanel feature={feature} onClose={() => {}} />,
    );
    expect(screen.getByTestId('canal-card')).toBeInTheDocument();
    // Card MUST carry the canal nombre (sanity check that props are threaded).
    expect(screen.getByRole('heading', { name: 'Readecuación tramo inicial colector norte' })).toBeInTheDocument();
  });

  it('renders <CanalCard> for a propuesto feature', () => {
    const feature = buildCanalFeature({
      estado: 'propuesto',
      prioridad: 'Alta',
      nombre: 'Nuevo colector sur',
    });
    renderWithMantine(
      <InfoPanel feature={feature} onClose={() => {}} />,
    );
    expect(screen.getByTestId('canal-card')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Nuevo colector sur' })).toBeInTheDocument();
    // Prioridad Badge MUST render for propuestos (confirms the full props chain).
    expect(screen.getByTestId('canal-card-prioridad')).toBeInTheDocument();
  });

  it('does NOT render <CanalCard> for a generic (non-canal) feature', () => {
    renderWithMantine(
      <InfoPanel feature={buildGenericFeature()} onClose={() => {}} />,
    );
    expect(screen.queryByTestId('canal-card')).not.toBeInTheDocument();
  });

  it('renders one <CanalCard> per feature when multiple canals are stacked', () => {
    const features: Feature[] = [
      buildCanalFeature({ id: 'a', nombre: 'Canal A', estado: 'relevado' }),
      buildCanalFeature({
        id: 'b',
        nombre: 'Canal B',
        estado: 'propuesto',
        prioridad: 'Media',
      }),
    ];
    renderWithMantine(
      <InfoPanel features={features} onClose={() => {}} />,
    );
    const cards = screen.getAllByTestId('canal-card');
    expect(cards).toHaveLength(2);
    expect(screen.getByRole('heading', { name: 'Canal A' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Canal B' })).toBeInTheDocument();
  });

  it('mixes canal + generic sections when stacked', () => {
    const features: Feature[] = [
      buildCanalFeature({ nombre: 'Canal Primero', estado: 'relevado' }),
      buildGenericFeature(),
    ];
    renderWithMantine(
      <InfoPanel features={features} onClose={() => {}} />,
    );
    // Exactly ONE canal card (not two).
    expect(screen.getAllByTestId('canal-card')).toHaveLength(1);
    // Generic section renders alongside.
    expect(screen.getAllByTestId('info-panel-feature-section')).toHaveLength(2);
  });
});
