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
import userEvent from '@testing-library/user-event';
import type { Feature } from 'geojson';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { InfoPanel } from '../../src/components/map2d/InfoPanel';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
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

  it('shows a group summary and no detail until a chip is selected', () => {
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
    expect(screen.getByTestId('info-panel-group-summary')).toHaveTextContent('3');
    expect(screen.queryByTestId('info-panel-feature-section')).not.toBeInTheDocument();
  });

  it('reveals only the selected chip detail', async () => {
    const topFeature = buildFeatureWithLayer(`${SOURCE_IDS.CATASTRO}-fill`, {
      nombre: 'TOP-FEATURE',
      nomenclatura: 'TOP-FEATURE',
    });
    const bottomFeature = buildFeatureWithLayer(`${SOURCE_IDS.SOIL}-fill`, {
      nombre: 'BOTTOM-FEATURE',
      capability: 'BOTTOM-FEATURE',
    });
    const user = userEvent.setup();
    renderWithMantine(
      <InfoPanel features={[topFeature, bottomFeature]} onClose={() => {}} />,
    );
    expect(screen.queryByTestId('info-panel-feature-section')).not.toBeInTheDocument();
    await user.click(screen.getByText('TOP-FEATURE'));
    expect(screen.getAllByTestId('info-panel-feature-section')).toHaveLength(1);
    expect(screen.getByTestId('info-panel-feature-section').textContent).toContain(
      'TOP-FEATURE',
    );
    expect(screen.getAllByTestId('info-panel-feature-section')).toHaveLength(1);
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
