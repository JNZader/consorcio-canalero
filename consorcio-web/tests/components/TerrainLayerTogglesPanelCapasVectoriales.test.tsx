/**
 * TerrainLayerTogglesPanelCapasVectoriales.test.tsx
 *
 * UX uniformity fix — wrap the base vector checkboxes in a CollapsibleSection
 * so the three "category" blocks (Capas vectoriales 3D, Pilar Verde, Canales)
 * all behave the same way: each is independently collapsible, each defaults to
 * expanded, each is togglable by clicking its own header.
 *
 * Tests assert:
 *   1. A `CollapsibleSection` with title "Capas vectoriales 3D" is rendered
 *      inside the outer `terrain-3d-toggles` body, and exposes the deterministic
 *      testId `terrain-3d-capas-vectoriales` (+ `-header`, + `-body`).
 *   2. ALL base vector checkboxes (the PRIORITY_3D_VECTOR_LAYERS set —
 *      approved_zones, basins, roads, waterways, soil, catastro) are rendered
 *      INSIDE the section body, not siblings of it.
 *   3. Default state is expanded (checkboxes visible on mount).
 *   4. Clicking the section header collapses the body — the checkboxes are
 *      removed from the DOM, but the section title row stays visible.
 *   5. A second click re-expands the body, checkboxes return.
 *
 * Why this matters: the outer "Capas 3D" collapsible + the inner "Pilar Verde"
 * / "Canales" collapsibles were already CollapsibleSections. The flat base-
 * layer block was the odd one out — inconsistent UX. Wrapping it closes that
 * gap and gives users a symmetric chrome.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLayerTogglesPanel } from '../../src/components/terrain/TerrainLayerTogglesPanel';
import { PRIORITY_3D_VECTOR_LAYERS } from '../../src/components/terrain/terrainLayerConfig';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const baseProps = {
  rasterLayers: [],
  selectedImageOption: null,
  activeRasterLayerId: undefined,
  onActiveRasterLayerChange: vi.fn(),
  overlayOpacity: 0.7,
  onOverlayOpacityChange: vi.fn(),
  vectorLayerVisibility: {} as Record<string, boolean>,
  onVectorLayerToggle: vi.fn(),
  onClose: vi.fn(),
  hasApprovedZones: false,
};

describe('<TerrainLayerTogglesPanel /> — "Capas vectoriales 3D" CollapsibleSection', () => {
  it('renders the section with the deterministic testId root', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...baseProps} />);

    expect(screen.getByTestId('terrain-3d-capas-vectoriales')).toBeInTheDocument();
    expect(screen.getByTestId('terrain-3d-capas-vectoriales-header')).toBeInTheDocument();
    expect(screen.getByTestId('terrain-3d-capas-vectoriales-body')).toBeInTheDocument();
  });

  it('renders ALL base vector checkboxes INSIDE the section body (not as siblings)', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...baseProps} />);

    const body = screen.getByTestId('terrain-3d-capas-vectoriales-body');

    // Every PRIORITY_3D_VECTOR_LAYERS entry must have its Checkbox rendered
    // inside the section body.
    for (const layer of PRIORITY_3D_VECTOR_LAYERS) {
      // The label in the DOM is either `layer.label` (supported) or
      // `${label} (pendiente|not_supported_yet)` — match a prefix regex so
      // both forms work.
      const escaped = layer.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const checkbox = within(body).getByLabelText(new RegExp(`^${escaped}`, 'i'));
      expect(checkbox).toBeInTheDocument();
    }
  });

  it('defaults the section to EXPANDED (checkboxes visible on mount)', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...baseProps} />);

    const header = screen.getByTestId('terrain-3d-capas-vectoriales-header');
    expect(header).toHaveAttribute('aria-expanded', 'true');

    // A concrete checkbox from the base set — "Cuencas" (approved_zones) —
    // must be in the document on mount.
    expect(screen.getByLabelText(/^Cuencas/i)).toBeInTheDocument();
  });

  it('collapses the body when the section header is clicked (checkboxes hidden)', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...baseProps} />);

    const header = screen.getByTestId('terrain-3d-capas-vectoriales-header');
    fireEvent.click(header);

    expect(header).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('terrain-3d-capas-vectoriales-body')).not.toBeInTheDocument();

    // The individual base-layer checkboxes must be gone too.
    expect(screen.queryByLabelText(/^Cuencas/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Subcuencas/i)).not.toBeInTheDocument();

    // The section title row stays visible — this is the collapsed state.
    expect(screen.getByText(/Capas vectoriales 3D/i)).toBeInTheDocument();
  });

  it('re-expands the body after a second click on the header', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...baseProps} />);

    const header = screen.getByTestId('terrain-3d-capas-vectoriales-header');
    fireEvent.click(header);
    fireEvent.click(header);

    expect(header).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTestId('terrain-3d-capas-vectoriales-body')).toBeInTheDocument();
    expect(screen.getByLabelText(/^Cuencas/i)).toBeInTheDocument();
  });
});
