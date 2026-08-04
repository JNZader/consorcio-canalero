/**
 * syncIgnLayerLazy.test.ts
 *
 * PERF — the historic IGN altimetry raster is OFF by default, but `syncIgnLayer`
 * used to add its image source unconditionally and only then hide the layer. The
 * result: every visitor of /mapa downloaded the WebP (and paid the GPU upload)
 * for a layer they never turned on.
 *
 * The contract pinned here: nothing touches the map until the user asks for the
 * layer; after that, toggling is a visibility flip and the source is NEVER
 * re-added (which would re-download the image).
 */

import { describe, expect, it, vi } from 'vitest';

import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { syncIgnLayer } from '../../src/components/map2d/mapRasterOverlayHelpers';

interface FakeMap {
  readonly sources: Set<string>;
  readonly layers: Set<string>;
  readonly addSource: ReturnType<typeof vi.fn>;
  readonly addLayer: ReturnType<typeof vi.fn>;
  readonly setLayoutProperty: ReturnType<typeof vi.fn>;
  getSource(id: string): unknown;
  getLayer(id: string): unknown;
}

function makeMap(): FakeMap {
  const sources = new Set<string>();
  const layers = new Set<string>();
  const map: FakeMap = {
    sources,
    layers,
    addSource: vi.fn((id: string) => {
      sources.add(id);
    }),
    addLayer: vi.fn((layer: { id: string }) => {
      layers.add(layer.id);
    }),
    setLayoutProperty: vi.fn(),
    getSource: (id: string) => (sources.has(id) ? {} : undefined),
    getLayer: (id: string) => (layers.has(id) ? {} : undefined),
  };
  return map;
}

// The helper only uses the handful of methods above.
// biome-ignore lint/suspicious/noExplicitAny: narrow structural fake of maplibregl.Map
const asMap = (m: FakeMap) => m as any;

describe('syncIgnLayer — lazy mount', () => {
  it('does NOT add the source or the layer while the overlay is off', () => {
    const map = makeMap();

    syncIgnLayer(asMap(map), false);

    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.addLayer).not.toHaveBeenCalled();
    // Not even a visibility write: there is no layer to write to.
    expect(map.setLayoutProperty).not.toHaveBeenCalled();
  });

  it('stays inert across repeated off-syncs (re-renders must not mount it)', () => {
    const map = makeMap();

    syncIgnLayer(asMap(map), false);
    syncIgnLayer(asMap(map), false);
    syncIgnLayer(asMap(map), false);

    expect(map.addSource).not.toHaveBeenCalled();
  });

  it('mounts source + layer the first time the user turns it on', () => {
    const map = makeMap();

    syncIgnLayer(asMap(map), true);

    expect(map.addSource).toHaveBeenCalledTimes(1);
    expect(map.addLayer).toHaveBeenCalledTimes(1);
    const [sourceId, source] = map.addSource.mock.calls[0] as [string, { type: string; url: string }];
    expect(sourceId).toBe(SOURCE_IDS.IGN);
    expect(source.type).toBe('image');
    expect(source.url).toContain('altimetria_ign_consorcio');
  });

  it('toggling off AFTER mounting only flips visibility — never re-adds the source', () => {
    const map = makeMap();

    syncIgnLayer(asMap(map), true);
    syncIgnLayer(asMap(map), false);
    syncIgnLayer(asMap(map), true);

    expect(map.addSource).toHaveBeenCalledTimes(1);
    expect(map.addLayer).toHaveBeenCalledTimes(1);
    expect(map.setLayoutProperty).toHaveBeenCalledTimes(3);
  });
});
