/**
 * LayerControlsPanelAttribution.test.tsx
 *
 * Attribution-footer behavior of `<LayerControlsPanel />`.
 *
 *   - When at least one PILAR_VERDE_LAYER_IDS entry is visible in
 *     `vectorVisibility`, the legend footer MUST render the literal text
 *     "Datos: IDECor — Gobierno de Córdoba".
 *   - When NO Pilar Verde layer is visible, that text MUST NOT render.
 *
 * The source of truth for which IDs are "Pilar Verde" is the
 * `PILAR_VERDE_LAYER_IDS` constant exported from `mapLayerSyncStore.ts`.
 * The test imports it directly — NO duplicated string literals.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';
import { PILAR_VERDE_LAYER_IDS } from '../../src/stores/mapLayerSyncStore';

const IDECOR_TEXT = 'Datos: IDECor — Gobierno de Córdoba';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const baseProps = {
  baseLayer: 'osm' as const,
  onBaseLayerChange: () => {},
  layerItems: [
    { id: 'catastro', label: 'Catastro' },
    { id: PILAR_VERDE_LAYER_IDS[0], label: 'BPA 2025' },
  ],
  onLayerVisibilityChange: () => {},
  showIGNOverlay: false,
  onShowIGNOverlayChange: () => {},
  demEnabled: false,
  showDemOverlay: false,
  onShowDemOverlayChange: () => {},
  activeDemLayerId: null,
  onActiveDemLayerIdChange: () => {},
  demOptions: [],
};

describe('<LayerControlsPanel /> — IDECor attribution footer', () => {
  it('does NOT render the IDECor attribution when no Pilar Verde layer is visible', () => {
    const vectorVisibility: Record<string, boolean> = {
      catastro: true,
    };
    renderWithMantine(
      <LayerControlsPanel {...baseProps} vectorVisibility={vectorVisibility} />,
    );
    expect(screen.queryByText(IDECOR_TEXT)).not.toBeInTheDocument();
  });

  it('does NOT render IDECor when a Pilar Verde key exists but is false', () => {
    const vectorVisibility: Record<string, boolean> = {
      [PILAR_VERDE_LAYER_IDS[0]]: false,
      [PILAR_VERDE_LAYER_IDS[1]]: false,
    };
    renderWithMantine(
      <LayerControlsPanel {...baseProps} vectorVisibility={vectorVisibility} />,
    );
    expect(screen.queryByText(IDECOR_TEXT)).not.toBeInTheDocument();
  });

  it('renders the IDECor attribution when ONE Pilar Verde layer is visible', () => {
    const vectorVisibility: Record<string, boolean> = {
      [PILAR_VERDE_LAYER_IDS[0]]: true,
    };
    renderWithMantine(
      <LayerControlsPanel {...baseProps} vectorVisibility={vectorVisibility} />,
    );
    expect(screen.getByText(IDECOR_TEXT)).toBeInTheDocument();
  });

  it('renders the IDECor attribution when ALL Pilar Verde layers are visible (no duplication)', () => {
    const vectorVisibility: Record<string, boolean> = Object.fromEntries(
      PILAR_VERDE_LAYER_IDS.map((id) => [id, true]),
    );
    renderWithMantine(
      <LayerControlsPanel {...baseProps} vectorVisibility={vectorVisibility} />,
    );
    const matches = screen.getAllByText(IDECOR_TEXT);
    expect(matches).toHaveLength(1);
  });

  it('uses the store-exported constant — does not hardcode layer IDs', () => {
    // Belt-and-braces: if PILAR_VERDE_LAYER_IDS is empty for some reason this
    // test battery would give false-greens. Assert the constant is non-empty.
    expect(PILAR_VERDE_LAYER_IDS.length).toBeGreaterThan(0);
  });
});
