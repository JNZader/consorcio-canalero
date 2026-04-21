/**
 * MapActionsPanel.test.tsx
 *
 * Batch F — Phase 6 — KMZ export button.
 *
 * Pins the contract for the "Exportar KMZ" entry inside the existing
 * "Exportar" `Menu` dropdown in `MapActionsPanel`:
 *
 *   1. When `onExportKmz` is provided, a menu item with the literal
 *      label "Exportar KMZ" renders inside the same dropdown that owns
 *      "Exportar PNG" / "Exportar PDF zonificación".
 *   2. Clicking that menu item invokes `onExportKmz` exactly once with
 *      no arguments.
 *   3. When `onExportKmz` is NOT provided (undefined), the menu item is
 *      NOT rendered at all — this mirrors how the "Exportar PDF
 *      zonificación" item is gated by `hasApprovedZones`. The overall
 *      "Exportar" dropdown stays clickable because PNG is always on.
 *
 * Rationale for not disabling the KMZ entry based on
 * `visibleVectors`: YPF is modelled as an always-on floor inside
 * `handleExportKmz` (via `ALWAYS_ON_KEYS` in the builder), so the KMZ
 * is never "empty"; the on-empty UX is already handled inside the
 * handler itself (try/catch + red notification). Mirrors PNG's
 * always-enabled behaviour.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MapActionsPanel } from '../../src/components/map2d/MapActionsPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('<MapActionsPanel /> — Exportar KMZ menu item', () => {
  it('renders the "Exportar KMZ" menu item inside the Export dropdown when onExportKmz is provided', async () => {
    const user = userEvent.setup();

    renderWithMantine(
      <MapActionsPanel
        isOperator={false}
        markingMode={false}
        onToggleMarkingMode={() => {}}
        canManageZoning={false}
        showSuggestedZonesPanel={false}
        hasApprovedZones={false}
        onToggleSuggestedZonesPanel={() => {}}
        onOpenExportPng={() => {}}
        onExportApprovedZonesPdf={() => {}}
        onExportKmz={() => {}}
      />
    );

    // Open the "Exportar" Menu trigger.
    await user.click(screen.getByRole('button', { name: /exportar/i }));

    // Literal label match — must be EXACTLY "Exportar KMZ".
    expect(screen.getByText('Exportar KMZ')).toBeInTheDocument();
  });

  it('invokes onExportKmz exactly once with no arguments when the menu item is clicked', async () => {
    const user = userEvent.setup();
    const onExportKmz = vi.fn();

    renderWithMantine(
      <MapActionsPanel
        isOperator={false}
        markingMode={false}
        onToggleMarkingMode={() => {}}
        canManageZoning={false}
        showSuggestedZonesPanel={false}
        hasApprovedZones={false}
        onToggleSuggestedZonesPanel={() => {}}
        onOpenExportPng={() => {}}
        onExportApprovedZonesPdf={() => {}}
        onExportKmz={onExportKmz}
      />
    );

    await user.click(screen.getByRole('button', { name: /exportar/i }));
    await user.click(screen.getByText('Exportar KMZ'));

    expect(onExportKmz).toHaveBeenCalledTimes(1);
    expect(onExportKmz).toHaveBeenCalledWith();
  });

  it('omits the "Exportar KMZ" menu item when onExportKmz is undefined', async () => {
    const user = userEvent.setup();

    renderWithMantine(
      <MapActionsPanel
        isOperator={false}
        markingMode={false}
        onToggleMarkingMode={() => {}}
        canManageZoning={false}
        showSuggestedZonesPanel={false}
        hasApprovedZones={false}
        onToggleSuggestedZonesPanel={() => {}}
        onOpenExportPng={() => {}}
        onExportApprovedZonesPdf={() => {}}
      />
    );

    await user.click(screen.getByRole('button', { name: /exportar/i }));

    // The dropdown is open and PNG is visible — prove it to distinguish
    // "menu is closed" from "KMZ item is absent".
    expect(screen.getByText('Exportar PNG')).toBeInTheDocument();
    expect(screen.queryByText('Exportar KMZ')).not.toBeInTheDocument();
  });

  it('sits as a sibling Menu.Item alongside "Exportar PNG" (both inside the same dropdown)', async () => {
    const user = userEvent.setup();

    renderWithMantine(
      <MapActionsPanel
        isOperator={false}
        markingMode={false}
        onToggleMarkingMode={() => {}}
        canManageZoning={false}
        showSuggestedZonesPanel={false}
        hasApprovedZones={false}
        onToggleSuggestedZonesPanel={() => {}}
        onOpenExportPng={() => {}}
        onExportApprovedZonesPdf={() => {}}
        onExportKmz={() => {}}
      />
    );

    await user.click(screen.getByRole('button', { name: /exportar/i }));

    // Both PNG and KMZ are present in the same open dropdown.
    const png = screen.getByText('Exportar PNG');
    const kmz = screen.getByText('Exportar KMZ');
    expect(png).toBeInTheDocument();
    expect(kmz).toBeInTheDocument();

    // And both are rendered as items of a Mantine Menu — i.e. have a
    // shared ancestor with role="menu".
    const menu = png.closest('[role="menu"]');
    expect(menu).not.toBeNull();
    expect(menu?.contains(kmz)).toBe(true);
  });
});
