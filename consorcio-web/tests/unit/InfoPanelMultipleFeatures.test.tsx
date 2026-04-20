/**
 * InfoPanelMultipleFeatures.test.tsx
 *
 * Phase 8 — InfoPanel now supports rendering MULTIPLE stacked features in a
 * single panel. When a user clicks on a map point where N layers overlap,
 * MapLibre's `queryRenderedFeatures` returns all of them. We show every one,
 * stacked in document order (top-most MapLibre feature first), each separated
 * by a divider.
 *
 * The BPA detection branch still wins on a per-feature basis — i.e. each
 * feature independently decides whether it renders as a `<BpaCard>` or as the
 * generic property-dump.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { Feature } from 'geojson';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { InfoPanel } from '../../src/components/map2d/InfoPanel';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

// Helper to attach a layer id so the whitelist logic (Fix 2) kicks in where
// relevant. MapLibre's queryRenderedFeatures adds this at runtime.
type FeatureWithLayer = Feature & { layer?: { id: string } };

function buildFeatureWithLayer(layerId: string, props: Record<string, unknown>): FeatureWithLayer {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-62.7, -32.6] },
    properties: props,
    layer: { id: layerId },
  };
}

describe('<InfoPanel /> multiple features (Phase 8)', () => {
  it('renders nothing when features is an empty array', () => {
    renderWithMantine(<InfoPanel features={[]} onClose={() => {}} />);
    expect(screen.queryByRole('heading', { name: /informacion/i })).not.toBeInTheDocument();
  });

  it('renders a single feature as one section (same as legacy)', () => {
    const feature = buildFeatureWithLayer(`${SOURCE_IDS.CATASTRO}-fill`, {
      nomenclatura: '12-04-0001-123456',
    });
    renderWithMantine(<InfoPanel features={[feature]} onClose={() => {}} />);
    expect(screen.getByRole('heading', { name: /informacion/i })).toBeInTheDocument();
    // One feature → one section
    expect(screen.getAllByTestId('info-panel-feature-section')).toHaveLength(1);
  });

  it('renders N sections when N features overlap at click point', () => {
    const feature1 = buildFeatureWithLayer(`${SOURCE_IDS.CATASTRO}-fill`, {
      nomenclatura: 'catastro-1',
    });
    const feature2 = buildFeatureWithLayer(`${SOURCE_IDS.SOIL}-fill`, {
      capability: 'III',
    });
    const feature3 = buildFeatureWithLayer(`${SOURCE_IDS.ROADS}-line`, {
      ccn: '158',
      fna: 'RN 158',
    });
    renderWithMantine(
      <InfoPanel features={[feature1, feature2, feature3]} onClose={() => {}} />,
    );
    expect(screen.getAllByTestId('info-panel-feature-section')).toHaveLength(3);
  });

  it('preserves MapLibre z-order (first feature renders first)', () => {
    const topFeature = buildFeatureWithLayer(`${SOURCE_IDS.CATASTRO}-fill`, {
      nomenclatura: 'TOP-FEATURE',
    });
    const bottomFeature = buildFeatureWithLayer(`${SOURCE_IDS.SOIL}-fill`, {
      capability: 'BOTTOM-FEATURE',
    });
    renderWithMantine(
      <InfoPanel features={[topFeature, bottomFeature]} onClose={() => {}} />,
    );
    const sections = screen.getAllByTestId('info-panel-feature-section');
    expect(sections[0]?.textContent).toContain('TOP-FEATURE');
    expect(sections[1]?.textContent).toContain('BOTTOM-FEATURE');
  });

  it('still accepts the legacy singular `feature` prop for backwards compatibility', () => {
    const feature = buildFeatureWithLayer(`${SOURCE_IDS.CATASTRO}-fill`, {
      nomenclatura: 'legacy',
    });
    renderWithMantine(<InfoPanel feature={feature} onClose={() => {}} />);
    expect(screen.getByRole('heading', { name: /informacion/i })).toBeInTheDocument();
    expect(screen.getAllByTestId('info-panel-feature-section')).toHaveLength(1);
  });
});
