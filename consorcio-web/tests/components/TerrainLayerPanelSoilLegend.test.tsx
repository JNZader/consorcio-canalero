/**
 * TerrainLayerPanelSoilLegend.test.tsx
 *
 * Phase 8 — the 3D chrome was split into `<TerrainLayerTogglesPanel />` and
 * `<TerrainLegendsPanel />`. This file now exercises the legend panel
 * directly.
 *
 * Validates that `<TerrainLegendsPanel />` renders a legend for the
 * "Suelos IDECOR 1:50.000" vector layer when it is toggled ON, and hides
 * it when the layer is OFF.
 *
 * Colors MUST come from `SOIL_CAPABILITY_COLORS` in `useSoilMap.ts`
 * (single source of truth — same map feeds the MapLibre paint in
 * `terrainVectorLayerEffects.ts`).
 *
 * Labels: IDECOR soil-capability classes I–VIII in Spanish.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLegendsPanel } from '../../src/components/terrain/TerrainLegendsPanel';
import {
  SOIL_CAPABILITY_COLORS,
  SOIL_CAPABILITY_LABELS,
  SOIL_CAPABILITY_ORDER,
} from '../../src/hooks/useSoilMap';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const SOIL_LEGEND_TESTID = 'terrain-3d-soil-legend';
const SOIL_CHIP_TESTID_PREFIX = 'terrain-3d-soil-legend-chip';

const baseProps = {
  activeRasterType: undefined,
  hiddenClasses: {},
  onClassToggle: vi.fn(),
  hiddenRanges: {},
  onRangeToggle: vi.fn(),
} as const;

describe('TerrainLegendsPanel — Suelos (soil) vector layer legend', () => {
  it('renders all 8 IDECOR capability classes (I–VIII) with Spanish labels and SOIL_CAPABILITY_COLORS when soil layer is ON', () => {
    renderWithMantine(
      <TerrainLegendsPanel
        {...baseProps}
        vectorLayerVisibility={{ soil: true }}
      />
    );

    const legend = screen.getByTestId(SOIL_LEGEND_TESTID);
    expect(legend).toBeInTheDocument();

    // All 8 chips present in I → VIII order
    expect(SOIL_CAPABILITY_ORDER).toHaveLength(8);

    for (const cap of SOIL_CAPABILITY_ORDER) {
      const chip = screen.getByTestId(`${SOIL_CHIP_TESTID_PREFIX}-${cap}`);
      expect(chip).toBeInTheDocument();

      // Color must come from SOIL_CAPABILITY_COLORS (single source of truth)
      const expectedColor = SOIL_CAPABILITY_COLORS[cap];
      expect(expectedColor).toBeTruthy();

      const swatch = chip.querySelector('[data-soil-swatch="true"]') as HTMLElement | null;
      expect(swatch).not.toBeNull();
      // Mantine/CSS may normalize hex to rgb(); assert on the inline style attribute instead.
      expect(swatch?.getAttribute('style') ?? '').toContain(expectedColor);

      // Label should contain both the roman numeral and the Spanish descriptor
      const spanishLabel = SOIL_CAPABILITY_LABELS[cap];
      expect(chip.textContent).toContain(cap);
      expect(chip.textContent).toContain(spanishLabel);
    }

    // Spot-check the exact Spanish wording required by the audit.
    // Each chip renders text of the form "{roman} — {label}", so match the full
    // "{roman} — {label}" strings to avoid partial-match collisions
    // (e.g. "Buena" as a substring of "Muy Buena").
    expect(screen.getByText('I — Excelente')).toBeInTheDocument();
    expect(screen.getByText('II — Muy Buena')).toBeInTheDocument();
    expect(screen.getByText('III — Buena')).toBeInTheDocument();
    expect(screen.getByText('IV — Moderada')).toBeInTheDocument();
    expect(screen.getByText('V — Baja')).toBeInTheDocument();
    expect(screen.getByText('VI — Muy Baja')).toBeInTheDocument();
    expect(screen.getByText('VII — Sumamente Baja')).toBeInTheDocument();
    expect(screen.getByText('VIII — No Arable')).toBeInTheDocument();
  });

  it('does NOT render the soil legend when the soil layer toggle is OFF', () => {
    renderWithMantine(
      <TerrainLegendsPanel
        {...baseProps}
        vectorLayerVisibility={{ soil: false }}
      />
    );

    expect(screen.queryByTestId(SOIL_LEGEND_TESTID)).not.toBeInTheDocument();
  });

  it('does NOT render the soil legend when vectorLayerVisibility has no soil key', () => {
    renderWithMantine(
      <TerrainLegendsPanel
        {...baseProps}
        vectorLayerVisibility={{}}
      />
    );

    expect(screen.queryByTestId(SOIL_LEGEND_TESTID)).not.toBeInTheDocument();
  });
});
