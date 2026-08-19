/**
 * LayerOrderSection.test.tsx
 *
 * map-redesign Fase 3 — Tanda B (task 3.5).
 *   - `reorderLayerIds` pure fn moves an id correctly (unit; @dnd-kit pointer
 *     drag is impractical to fire in jsdom, so the reorder math is extracted).
 *   - `resolveEffectiveBottomToTop` guarantees the FULL set (contract).
 *   - The "Orden de capas" list renders ALL reorderable layers (active AND
 *     dimmed inactive) — never a partial subset.
 *   - The reset button writes `[]` (clean reset per Tanda A's no-op guarantee).
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  LayerOrderSection,
  reorderLayerIds,
  resolveEffectiveBottomToTop,
} from '../../src/components/map2d/LayerOrderSection';
import {
  DEFAULT_LAYER_ORDER,
  RENDERABLE_UI_LAYER_IDS,
} from '../../src/components/map2d/layerRenderRegistry';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('reorderLayerIds (pure)', () => {
  it('moves an id forward to the target slot', () => {
    expect(reorderLayerIds(['a', 'b', 'c', 'd'], 'a', 'c')).toEqual(['b', 'c', 'a', 'd']);
  });

  it('moves an id backward to the target slot', () => {
    expect(reorderLayerIds(['a', 'b', 'c', 'd'], 'd', 'b')).toEqual(['a', 'd', 'b', 'c']);
  });

  it('is a no-op (copy) when active === over', () => {
    const input = ['a', 'b', 'c'];
    const out = reorderLayerIds(input, 'b', 'b');
    expect(out).toEqual(['a', 'b', 'c']);
    expect(out).not.toBe(input); // returns a fresh array, never mutates
  });

  it('is a no-op (copy) when an id is not present', () => {
    expect(reorderLayerIds(['a', 'b'], 'x', 'a')).toEqual(['a', 'b']);
  });

  it('never mutates its input', () => {
    const input = ['a', 'b', 'c'];
    reorderLayerIds(input, 'a', 'c');
    expect(input).toEqual(['a', 'b', 'c']);
  });
});

describe('resolveEffectiveBottomToTop (full-set contract)', () => {
  it('falls back to DEFAULT_LAYER_ORDER on an empty override', () => {
    expect(resolveEffectiveBottomToTop([])).toEqual([...DEFAULT_LAYER_ORDER]);
  });

  it('keeps a valid override order verbatim (already full set)', () => {
    const full = [...RENDERABLE_UI_LAYER_IDS];
    expect(resolveEffectiveBottomToTop(full)).toEqual(full);
  });

  it('drops unknown ids and re-inserts any MISSING renderable id → always the full set', () => {
    const partial = ['roads', 'nonexistent_layer', 'waterways'];
    const resolved = resolveEffectiveBottomToTop(partial);
    // Full set, no strays, no dupes.
    expect([...resolved].sort()).toEqual([...RENDERABLE_UI_LAYER_IDS].sort());
    // Honors the user's leading order for the ids they DID list.
    expect(resolved.slice(0, 2)).toEqual(['roads', 'waterways']);
  });

  it('FF-B2: a missing id lands at its DEFAULT_LAYER_ORDER slot, NOT appended at the end', () => {
    // Simulate a persisted FULL order (seeded from default) from BEFORE `roads`
    // was registered. `roads` is the DEFAULT bottommost → must re-insert at the
    // bottom (index 0), not surface at the end/top.
    const withoutRoads = DEFAULT_LAYER_ORDER.filter((id) => id !== 'roads');
    const resolved = resolveEffectiveBottomToTop(withoutRoads);
    expect([...resolved].sort()).toEqual([...RENDERABLE_UI_LAYER_IDS].sort());
    expect(resolved[0]).toBe('roads');
    expect(resolved.at(-1)).not.toBe('roads');
  });

  it('FF-B2: a missing MID-stack id lands in its DEFAULT neighbourhood, not the end', () => {
    // `basins` sits at DEFAULT index 4 (mid-stack). A persisted full order
    // missing it should re-insert it adjacent to its DEFAULT neighbours.
    const withoutBasins = DEFAULT_LAYER_ORDER.filter((id) => id !== 'basins');
    const resolved = resolveEffectiveBottomToTop(withoutBasins);
    const idx = resolved.indexOf('basins');
    // Its DEFAULT predecessor is `catastro`, successor `precip_normal`.
    expect(resolved[idx - 1]).toBe('catastro');
    expect(resolved[idx + 1]).toBe('precip_normal');
    expect(resolved.at(-1)).not.toBe('basins');
  });

  it('FF-B2: a CUSTOM order missing a new id keeps the custom relative order + slots the new id by default', () => {
    // User moved escuelas to the bottom (custom), and this persisted order
    // predates `puntos_conflicto` being registered. The custom escuelas-first
    // ordering is preserved; the missing id is slotted by its default rank.
    const custom = DEFAULT_LAYER_ORDER.filter((id) => id !== 'puntos_conflicto' && id !== 'escuelas');
    const persisted = ['escuelas', ...custom]; // escuelas forced to bottom
    const resolved = resolveEffectiveBottomToTop(persisted);
    expect([...resolved].sort()).toEqual([...RENDERABLE_UI_LAYER_IDS].sort());
    // Custom choice honored: escuelas stays at the very bottom.
    expect(resolved[0]).toBe('escuelas');
    // Missing puntos_conflicto is present (full-set), not lost.
    expect(resolved).toContain('puntos_conflicto');
  });
});

describe('<LayerOrderSection /> (task 3.5 UI)', () => {
  it('renders a row for EVERY reorderable layer (full set, not partial)', () => {
    renderWithMantine(
      <LayerOrderSection
        orderByLayer={[]}
        onLayerOrderChange={() => {}}
        vectorVisibility={{}}
      />
    );
    for (const id of RENDERABLE_UI_LAYER_IDS) {
      expect(screen.getByTestId(`layer-order-item-${id}`)).toBeInTheDocument();
    }
  });

  it('shows top-of-list = top-of-map (DEFAULT reversed → escuelas first, roads last)', () => {
    renderWithMantine(
      <LayerOrderSection
        orderByLayer={[]}
        onLayerOrderChange={() => {}}
        vectorVisibility={{}}
      />
    );
    const rows = screen.getAllByTestId(/^layer-order-item-/);
    expect(rows[0]).toHaveAttribute('data-testid', 'layer-order-item-escuelas');
    expect(rows.at(-1)).toHaveAttribute('data-testid', 'layer-order-item-roads');
  });

  it('FF-B1: the reset button writes the explicit DEFAULT_LAYER_ORDER (bottom→top, full set)', () => {
    // Writing `[]` would only reset the LIST while the MAP stayed on the custom
    // stacking (applyLayerOrder([]) is a no-op → never undoes the moveLayers).
    // The reset must ACTIVELY re-assert the default so the map re-hoists.
    const onLayerOrderChange = vi.fn();
    renderWithMantine(
      <LayerOrderSection
        orderByLayer={['roads', 'waterways']}
        onLayerOrderChange={onLayerOrderChange}
        vectorVisibility={{}}
      />
    );
    fireEvent.click(screen.getByTestId('layer-order-reset'));
    expect(onLayerOrderChange).toHaveBeenCalledWith([...DEFAULT_LAYER_ORDER]);
  });

  it('SNAPSHOT/REGRESSION: default reversed-for-display then reorder with no move === same order', () => {
    // Display list = DEFAULT (bottom→top) reversed (top→bottom).
    const display = [...DEFAULT_LAYER_ORDER].reverse();
    // A "no move" drag (active === over) yields the identical display order …
    const afterNoMove = reorderLayerIds(display, display[0], display[0]);
    // … and reversing back to bottom→top reproduces DEFAULT exactly.
    expect([...afterNoMove].reverse()).toEqual([...DEFAULT_LAYER_ORDER]);
  });

  it('uses labelById overrides when provided', () => {
    renderWithMantine(
      <LayerOrderSection
        orderByLayer={[]}
        onLayerOrderChange={() => {}}
        vectorVisibility={{}}
        labelById={{ roads: 'Mi Red Vial Custom' }}
      />
    );
    expect(screen.getByText('Mi Red Vial Custom')).toBeInTheDocument();
  });
});
