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
import userEvent from '@testing-library/user-event';
import type { Feature } from 'geojson';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { InfoPanel } from '../../src/components/map2d/InfoPanel';
import { useCanAccess } from '../../src/stores/authStore';

vi.mock('../../src/stores/authStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/stores/authStore')>();
  return {
    ...actual,
    useCanAccess: vi.fn(() => false),
  };
});
import type { CanalFeatureProperties } from '../../src/types/canales';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
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
  afterEach(() => {
    vi.mocked(useCanAccess).mockReturnValue(false);
  });

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

  it('keeps canal details behind the chip list when several are stacked', async () => {
    const features: Feature[] = [
      buildCanalFeature({ id: 'a', nombre: 'Canal A', estado: 'relevado' }),
      buildCanalFeature({
        id: 'b',
        nombre: 'Canal B',
        estado: 'propuesto',
        prioridad: 'Media',
      }),
    ];
    const user = userEvent.setup();
    renderWithMantine(
      <InfoPanel features={features} onClose={() => {}} />,
    );
    expect(screen.queryByTestId('canal-card')).not.toBeInTheDocument();
    expect(screen.getByTestId('info-feature-chips')).toBeInTheDocument();
    expect(screen.getByTestId('info-panel-group-summary')).toBeInTheDocument();
    expect(screen.queryByTestId('elevation-profile')).not.toBeInTheDocument();
    await user.click(screen.getByText('Canal A'));
    expect(screen.getAllByTestId('canal-card')).toHaveLength(1);
    expect(screen.getByRole('heading', { name: 'Canal A' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Canal B' })).not.toBeInTheDocument();
  });

  it('shows the canal card after picking it from a mixed stack', async () => {
    const features: Feature[] = [
      buildCanalFeature({ nombre: 'Canal Primero', estado: 'relevado' }),
      buildGenericFeature(),
    ];
    const user = userEvent.setup();
    renderWithMantine(
      <InfoPanel features={features} onClose={() => {}} />,
    );
    expect(screen.queryByTestId('canal-card')).not.toBeInTheDocument();
    await user.click(screen.getByText('Canal Primero'));
    expect(screen.getAllByTestId('canal-card')).toHaveLength(1);
    expect(screen.getAllByTestId('info-panel-feature-section')).toHaveLength(1);
  });

  it('loads the elevation profile only for operators', async () => {
    vi.mocked(useCanAccess).mockReturnValue(true);
    renderWithMantine(
      <InfoPanel feature={buildCanalFeature()} onClose={() => {}} />,
    );
    expect(await screen.findByTestId('elevation-profile')).toBeInTheDocument();
  });
});
