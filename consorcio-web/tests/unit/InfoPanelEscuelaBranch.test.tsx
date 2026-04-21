/**
 * InfoPanelEscuelaBranch.test.tsx
 *
 * Covers the Pilar Azul (Escuelas rurales) branch added to `<InfoPanel>` in
 * Batch E / Phase 4.
 *
 * Detection path (AFTER the Canal branch, BEFORE the generic whitelist):
 *   feature.layer.id === 'escuelas-symbol'  →  render <EscuelaCard>
 *
 * Priority order among stacked features (top-most first, one section each):
 *   (1) BPA-aware branch — flat `bpa_total` or enriched catastro match
 *   (2) CanalCard branch — `estado` ∈ { 'relevado', 'propuesto' }
 *   (3) EscuelaCard branch — `layer.id === 'escuelas-symbol'`   ← NEW
 *   (4) Generic whitelist dump — fallback for everything else
 *
 * The overlap test ("CanalCard wins when a click hits BOTH a canal line AND a
 * school") is structural: a click on a crossing returns both features from
 * `queryRenderedFeatures` in array order. The feature-section renderer is
 * PER-FEATURE (each feature independently picks its branch), so BOTH cards
 * render side-by-side. The overlap BEHAVIOR we care about is tested in
 * `useMapInteractionEffectsClickableLayers.test.ts` (layer array order) —
 * this file just confirms that a feature missing `layer.id` does NOT fall
 * into the escuela branch.
 *
 * @see spec   `sdd/escuelas-rurales/spec` §REQ-ESC-5, §REQ-ESC-6
 * @see design `sdd/escuelas-rurales/design` §8 InfoPanel Routing
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { Feature } from 'geojson';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { InfoPanel } from '../../src/components/map2d/InfoPanel';
import type { CanalFeatureProperties } from '../../src/types/canales';
import type { EscuelaFeatureProperties } from '../../src/types/escuelas';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

// ---------------------------------------------------------------------------
// Fixture builders
// ---------------------------------------------------------------------------

/** Attach a synthetic `layer.id` mirroring what MapLibre surfaces at runtime. */
type FeatureWithLayer = Feature & { readonly layer?: { readonly id: string } };

function buildEscuelaFeature(
  overrides: Partial<EscuelaFeatureProperties> = {},
  layerId = 'escuelas-symbol',
): FeatureWithLayer {
  const properties: EscuelaFeatureProperties = {
    nombre: 'Esc. Joaquín Víctor González',
    localidad: 'Monte Leña',
    ambito: 'Rural Aglomerado',
    nivel: 'Inicial · Primario',
    ...overrides,
  };
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-62.58, -32.53] },
    properties: properties as unknown as Record<string, unknown>,
    layer: { id: layerId },
  };
}

function buildCanalFeature(
  overrides: Partial<CanalFeatureProperties> = {},
): FeatureWithLayer {
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
    geometry: {
      type: 'LineString',
      coordinates: [
        [-62.7, -32.6],
        [-62.71, -32.61],
      ],
    },
    properties: properties as unknown as Record<string, unknown>,
    layer: { id: 'canales_relevados-line' },
  };
}

function buildGenericFeature(): FeatureWithLayer {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-62.5, -32.5] },
    properties: { foo: 'bar' },
    layer: { id: 'something-else-fill' },
  };
}

// ---------------------------------------------------------------------------
// Tests — discriminator routing
// ---------------------------------------------------------------------------

describe('<InfoPanel /> — Escuela detection branch (layer.id === "escuelas-symbol")', () => {
  it('renders <EscuelaCard> for a feature on the escuelas-symbol layer', () => {
    const feature = buildEscuelaFeature();
    renderWithMantine(<InfoPanel feature={feature} onClose={() => {}} />);
    expect(screen.getByTestId('escuela-card')).toBeInTheDocument();
    // Card is wired through (humanized heading).
    expect(
      screen.getByRole('heading', { name: 'Escuela Joaquín Víctor González' }),
    ).toBeInTheDocument();
  });

  it('does NOT render <CanalCard> or the generic fallback for an escuela feature', () => {
    const feature = buildEscuelaFeature();
    renderWithMantine(<InfoPanel feature={feature} onClose={() => {}} />);
    expect(screen.queryByTestId('canal-card')).not.toBeInTheDocument();
    // Generic fallback renders a single Stack of Badges — its presence would
    // show "Localidad" / "Ámbito" / "Nivel" as badge labels (they're NOT in
    // the whitelist), so the feature section MUST be the escuela card only.
    expect(screen.getAllByTestId('info-panel-feature-section')).toHaveLength(1);
  });

  it('renders <EscuelaCard> for a "Rural Disperso" feature', () => {
    const feature = buildEscuelaFeature({
      nombre: 'Esc. Sarmiento',
      ambito: 'Rural Disperso',
    });
    renderWithMantine(<InfoPanel feature={feature} onClose={() => {}} />);
    expect(screen.getByTestId('escuela-card')).toBeInTheDocument();
    expect(screen.getByText('Rural Disperso')).toBeInTheDocument();
  });

  it('does NOT render <EscuelaCard> for a non-escuela feature (no layer.id match)', () => {
    const feature = buildGenericFeature();
    renderWithMantine(<InfoPanel feature={feature} onClose={() => {}} />);
    expect(screen.queryByTestId('escuela-card')).not.toBeInTheDocument();
  });

  it('does NOT render <EscuelaCard> for a feature on a different symbol layer', () => {
    // Defensive: another future symbol layer MUST not accidentally route.
    const feature = buildEscuelaFeature({}, 'some-other-symbol');
    renderWithMantine(<InfoPanel feature={feature} onClose={() => {}} />);
    expect(screen.queryByTestId('escuela-card')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — branch precedence (escuela branch runs AFTER canal branch)
// ---------------------------------------------------------------------------

describe('<InfoPanel /> — branch precedence (canal before escuela)', () => {
  it('renders <CanalCard> when stacked above <EscuelaCard> (canal feature first)', () => {
    // Simulates the overlap scenario: click on a canal line that crosses a
    // school icon. MapLibre returns canal first (canales_propuestos-line @9
    // is before escuelas-symbol @10 in buildClickableLayers — see Batch E
    // task 4.5/4.6). InfoPanel renders BOTH as separate sections, preserving
    // z-order.
    const canalFeature = buildCanalFeature({ estado: 'propuesto', prioridad: 'Alta' });
    const escuelaFeature = buildEscuelaFeature();
    renderWithMantine(
      <InfoPanel features={[canalFeature, escuelaFeature]} onClose={() => {}} />,
    );
    const sections = screen.getAllByTestId('info-panel-feature-section');
    expect(sections).toHaveLength(2);
    // First section: CanalCard (canal feature wins array position 0).
    expect(sections[0]).toContainElement(screen.getByTestId('canal-card'));
    // Second section: EscuelaCard (second feature).
    expect(sections[1]).toContainElement(screen.getByTestId('escuela-card'));
  });

  it('routes each stacked feature to its own branch independently', () => {
    const features = [
      buildCanalFeature({ estado: 'relevado' }),
      buildEscuelaFeature(),
    ];
    renderWithMantine(<InfoPanel features={features} onClose={() => {}} />);
    // Exactly 1 canal card + 1 escuela card (not two of either).
    expect(screen.getAllByTestId('canal-card')).toHaveLength(1);
    expect(screen.getAllByTestId('escuela-card')).toHaveLength(1);
  });
});
