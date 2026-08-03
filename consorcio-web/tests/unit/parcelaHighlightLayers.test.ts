/**
 * parcelaHighlightLayers — the on-map cue for a multi-parcel selection (T4).
 *
 * The highlight reuses the catastro VECTOR source and filters it by the
 * whitelisted `nomenclatura` property, so these tests pin the three things that
 * can silently break it: the property name, the add/update/remove lifecycle, and
 * the no-op when the catastro source is not on the map.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  PARCELA_HIGHLIGHT_FILL_LAYER,
  PARCELA_HIGHLIGHT_LINE_LAYER,
  buildParcelaHighlightFilter,
  clearParcelaHighlightLayers,
  syncParcelaHighlightLayers,
} from '../../src/components/map2d/parcelaHighlightLayers';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { LAYER_PROPERTY_WHITELISTS } from '../../src/components/map2d/layerPropertyWhitelists';

/** Minimal MapLibre stand-in that tracks which layers currently exist. */
function createMapMock({ withCatastro = true } = {}) {
  const layers = new Map<string, Record<string, unknown>>();
  return {
    layers,
    addLayer: vi.fn((layer: { id: string }) => layers.set(layer.id, layer)),
    removeLayer: vi.fn((id: string) => layers.delete(id)),
    getLayer: vi.fn((id: string) => layers.get(id)),
    getSource: vi.fn((id: string) =>
      withCatastro && id === SOURCE_IDS.CATASTRO ? { type: 'vector' } : undefined
    ),
    setFilter: vi.fn((id: string, filter: unknown) => {
      const layer = layers.get(id);
      if (layer) layer.filter = filter;
    }),
  };
}

describe('syncParcelaHighlightLayers', () => {
  it('filters on the `nomenclatura` property the catastro tiles actually publish', () => {
    // If this property were renamed, the highlight would silently paint nothing
    // while the analysis kept working — the exact kind of half-broken state the
    // whitelist test exists to prevent.
    expect(LAYER_PROPERTY_WHITELISTS.catastro).toContain('nomenclatura');
    expect(buildParcelaHighlightFilter(['a', 'b'])).toEqual([
      'in',
      ['get', 'nomenclatura'],
      ['literal', ['a', 'b']],
    ]);
  });

  it('adds a fill + line layer on the catastro source for the selection', () => {
    const map = createMapMock();
    syncParcelaHighlightLayers(map as never, ['13-06-01-0201', '13-06-01-0202']);

    const fill = map.layers.get(PARCELA_HIGHLIGHT_FILL_LAYER);
    const line = map.layers.get(PARCELA_HIGHLIGHT_LINE_LAYER);
    expect(fill).toBeDefined();
    expect(line).toBeDefined();
    expect(fill?.source).toBe(SOURCE_IDS.CATASTRO);
    expect(fill?.['source-layer']).toBe('parcelas_catastro');
    expect(fill?.filter).toEqual(
      buildParcelaHighlightFilter(['13-06-01-0201', '13-06-01-0202'])
    );
  });

  it('a SINGLE parcel is highlighted too (the user is about to add a second)', () => {
    const map = createMapMock();
    syncParcelaHighlightLayers(map as never, ['13-06-01-0201']);
    expect(map.layers.has(PARCELA_HIGHLIGHT_FILL_LAYER)).toBe(true);
  });

  it('UPDATES the filter in place instead of re-adding the layers', () => {
    const map = createMapMock();
    syncParcelaHighlightLayers(map as never, ['13-06-01-0201']);
    syncParcelaHighlightLayers(map as never, ['13-06-01-0201', '13-06-01-0202']);

    // Two layers created once each; the second sync only moved the filter.
    expect(map.addLayer).toHaveBeenCalledTimes(2);
    expect(map.setFilter).toHaveBeenCalledTimes(2);
    expect(map.layers.get(PARCELA_HIGHLIGHT_FILL_LAYER)?.filter).toEqual(
      buildParcelaHighlightFilter(['13-06-01-0201', '13-06-01-0202'])
    );
  });

  it('an EMPTY selection removes both layers, so nothing lingers', () => {
    const map = createMapMock();
    syncParcelaHighlightLayers(map as never, ['13-06-01-0201']);
    syncParcelaHighlightLayers(map as never, []);

    expect(map.layers.has(PARCELA_HIGHLIGHT_FILL_LAYER)).toBe(false);
    expect(map.layers.has(PARCELA_HIGHLIGHT_LINE_LAYER)).toBe(false);
  });

  it('clearParcelaHighlightLayers is the teardown shorthand', () => {
    const map = createMapMock();
    syncParcelaHighlightLayers(map as never, ['13-06-01-0201']);
    clearParcelaHighlightLayers(map as never);
    expect(map.layers.size).toBe(0);
  });

  it('paints NOTHING while the catastro layer is turned OFF', () => {
    // This is the real rule, and the reason the flag exists: turning catastro off
    // only flips its LAYERS' visibility — `syncCatastroLayers` leaves the vector
    // SOURCE on the map — so a source check alone never fires, and the amber
    // highlight kept painting parcels the user had just hidden.
    const map = createMapMock();
    syncParcelaHighlightLayers(map as never, ['13-06-01-0201'], false);

    expect(map.getSource).not.toHaveBeenCalled();
    expect(map.addLayer).not.toHaveBeenCalled();
    expect(map.layers.size).toBe(0);
  });

  it('REMOVES an existing highlight when the catastro layer is turned off', () => {
    const map = createMapMock();
    syncParcelaHighlightLayers(map as never, ['13-06-01-0201'], true);
    expect(map.layers.has(PARCELA_HIGHLIGHT_FILL_LAYER)).toBe(true);

    syncParcelaHighlightLayers(map as never, ['13-06-01-0201'], false);

    expect(map.layers.has(PARCELA_HIGHLIGHT_FILL_LAYER)).toBe(false);
    expect(map.layers.has(PARCELA_HIGHLIGHT_LINE_LAYER)).toBe(false);
  });

  it('is a NO-OP (never throws) before the style has added the catastro source', () => {
    // Not the layer switch (that is `catastroVisible`): the map style simply has
    // not loaded the source yet. The caller re-runs on every selection change, so
    // the highlight appears as soon as the source is there.
    const map = createMapMock({ withCatastro: false });
    expect(() => syncParcelaHighlightLayers(map as never, ['13-06-01-0201'])).not.toThrow();
    expect(map.addLayer).not.toHaveBeenCalled();
  });
});
