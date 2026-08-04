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
import { reloadIgnSource, syncIgnLayer } from '../../src/components/map2d/mapRasterOverlayHelpers';

interface FakeMap {
  readonly sources: Set<string>;
  readonly layers: Set<string>;
  readonly addSource: ReturnType<typeof vi.fn>;
  readonly addLayer: ReturnType<typeof vi.fn>;
  readonly removeSource: ReturnType<typeof vi.fn>;
  readonly removeLayer: ReturnType<typeof vi.fn>;
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
    removeSource: vi.fn((id: string) => {
      sources.delete(id);
    }),
    removeLayer: vi.fn((id: string) => {
      layers.delete(id);
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

/**
 * B4c fix round (REL-001/RES-001) — the retry behind the health entry.
 *
 * A MapLibre `ImageSource` issues its ONE request from `onAdd` (→ `load()`);
 * nothing in the tile lifecycle repeats it, so a 404 leaves the layer blank
 * forever and `syncIgnLayer` (a visibility flip once mounted) cannot fix it.
 * Removing source + layer and adding them back runs `onAdd` again, which is the
 * only thing that re-downloads the WebP.
 */
describe('reloadIgnSource — the only real retry', () => {
  it('removes the layer AND the source, then re-adds both (re-running onAdd → load)', () => {
    const map = makeMap();
    syncIgnLayer(asMap(map), true);

    reloadIgnSource(asMap(map), true);

    expect(map.removeLayer).toHaveBeenCalledWith(`${SOURCE_IDS.IGN}-layer`);
    expect(map.removeSource).toHaveBeenCalledWith(SOURCE_IDS.IGN);
    // A SECOND addSource is the whole point — that is the new download.
    expect(map.addSource).toHaveBeenCalledTimes(2);
    expect(map.addLayer).toHaveBeenCalledTimes(2);
    expect(map.sources.has(SOURCE_IDS.IGN)).toBe(true);
    expect(map.layers.has(`${SOURCE_IDS.IGN}-layer`)).toBe(true);
  });

  it('removes the LAYER before the SOURCE (MapLibre refuses a source still in use)', () => {
    const map = makeMap();
    syncIgnLayer(asMap(map), true);

    reloadIgnSource(asMap(map), true);

    const layerOrder = map.removeLayer.mock.invocationCallOrder[0];
    const sourceOrder = map.removeSource.mock.invocationCallOrder[0];
    expect(layerOrder).toBeLessThan(sourceOrder);
  });

  it('rebuilds the SAME source spec — the image url is not lost on retry', () => {
    const map = makeMap();
    syncIgnLayer(asMap(map), true);
    const [, first] = map.addSource.mock.calls[0] as [string, Record<string, unknown>];

    reloadIgnSource(asMap(map), true);
    const [, second] = map.addSource.mock.calls[1] as [string, Record<string, unknown>];

    expect(second).toEqual(first);
  });

  it('recovers a half-mounted state (source present, layer gone)', () => {
    const map = makeMap();
    syncIgnLayer(asMap(map), true);
    map.layers.delete(`${SOURCE_IDS.IGN}-layer`);

    reloadIgnSource(asMap(map), true);

    expect(map.layers.has(`${SOURCE_IDS.IGN}-layer`)).toBe(true);
    expect(map.sources.has(SOURCE_IDS.IGN)).toBe(true);
  });

  it('does not re-download while the overlay is OFF (stays lazy)', () => {
    const map = makeMap();
    syncIgnLayer(asMap(map), true);

    reloadIgnSource(asMap(map), false);

    // The old source is gone and nothing was fetched again: with the layer off
    // there is nothing to show and no reason to pay for the WebP.
    expect(map.addSource).toHaveBeenCalledTimes(1);
    expect(map.sources.has(SOURCE_IDS.IGN)).toBe(false);
  });

  it('is safe when nothing was ever mounted', () => {
    const map = makeMap();

    expect(() => reloadIgnSource(asMap(map), false)).not.toThrow();
    expect(map.removeLayer).not.toHaveBeenCalled();
    expect(map.removeSource).not.toHaveBeenCalled();
    expect(map.addSource).not.toHaveBeenCalled();
  });
});
