/**
 * escuelasLayers.test.ts
 *
 * Unit tests for the Pilar Azul (Escuelas rurales) colocated layer registry:
 *   - Public constants: `ESCUELAS_LAYER_ID`, `ESCUELAS_SOURCE_ID`,
 *     `ESCUELA_ICON_NAME`, `ESCUELA_ICON_URL`.
 *   - `registerEscuelaIcon(map)` — promise-based `loadImage` with
 *     `hasImage` guard + `pixelRatio: 2` on `addImage`.
 *   - Layout/paint factories: `buildEscuelasSymbolLayout`,
 *     `buildEscuelasSymbolPaint` — design §6.3 locks the exact shape.
 *
 * Source/layer MOUNT order (loadImage → addImage → addSource → addLayer) is
 * enforced at the helper-composition level here; `syncEscuelasLayer` (Batch D)
 * re-asserts it in `mapLayerEffectHelpers.ts`.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  ESCUELA_ICON_NAME,
  ESCUELA_ICON_URL,
  ESCUELAS_LAYER_ID,
  ESCUELAS_SOURCE_ID,
  buildEscuelasSymbolLayout,
  buildEscuelasSymbolPaint,
  registerEscuelaIcon,
} from '../../src/components/map2d/escuelasLayers';

// ---------------------------------------------------------------------------
// Map mock — minimal MapLibre surface area used by Batch C APIs
// ---------------------------------------------------------------------------

interface MockImage {
  width: number;
  height: number;
}

interface MapMockOptions {
  /** Image names to pretend are already registered. */
  images?: string[];
  /** If set, `loadImage` rejects with this error (v4 Promise API). */
  loadImageError?: Error;
  /** If true, `loadImage` resolves with `{data: null}` (simulates missing asset). */
  loadImageReturnsNullImage?: boolean;
}

function createMapMock(options: MapMockOptions = {}) {
  const images = new Set<string>(options.images ?? []);
  const callOrder: string[] = [];

  const map = {
    callOrder,
    images,
    hasImage: vi.fn((name: string) => {
      callOrder.push(`hasImage:${name}`);
      return images.has(name);
    }),
    addImage: vi.fn((name: string, _img: MockImage, _opts?: { pixelRatio?: number }) => {
      callOrder.push(`addImage:${name}`);
      images.add(name);
    }),
    // MapLibre GL JS 4.x: loadImage(url) returns Promise<{data: Image}>.
    // The pre-v4 callback overload was removed — see escuelasLayers.ts.
    loadImage: vi.fn((url: string) => {
      callOrder.push(`loadImage:${url}`);
      if (options.loadImageError) {
        return Promise.reject(options.loadImageError);
      }
      if (options.loadImageReturnsNullImage) {
        return Promise.resolve({ data: null });
      }
      return Promise.resolve({ data: { width: 64, height: 64 } as MockImage });
    }),
  };
  return map;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

describe('escuelasLayers · constants', () => {
  it('exposes the canonical layer id `escuelas-symbol` (design §6.1)', () => {
    expect(ESCUELAS_LAYER_ID).toBe('escuelas-symbol');
  });

  it('exposes the source id `escuelas` (matches SOURCE_IDS.ESCUELAS once wired in Batch D)', () => {
    expect(ESCUELAS_SOURCE_ID).toBe('escuelas');
  });

  it('exposes the image name `escuela` (keyed by icon-image layout expression)', () => {
    expect(ESCUELA_ICON_NAME).toBe('escuela');
  });

  it('exposes the public asset URL for the rasterized icon', () => {
    expect(ESCUELA_ICON_URL).toBe('/capas/escuelas/escuela-icon.png');
  });
});

// ---------------------------------------------------------------------------
// registerEscuelaIcon — promise + hasImage guard + pixelRatio
// ---------------------------------------------------------------------------

describe('registerEscuelaIcon · first mount', () => {
  it('resolves after loadImage → hasImage-guard → addImage sequence', async () => {
    const map = createMapMock();
    await expect(
      registerEscuelaIcon(map as unknown as maplibregl.Map),
    ).resolves.toBeUndefined();

    // loadImage was called with the canonical URL (v4 API: no callback arg).
    expect(map.loadImage).toHaveBeenCalledTimes(1);
    expect(map.loadImage).toHaveBeenCalledWith(ESCUELA_ICON_URL);

    // addImage was called exactly once, with pixelRatio=2 (design §6.2)
    expect(map.addImage).toHaveBeenCalledTimes(1);
    expect(map.addImage).toHaveBeenCalledWith(
      ESCUELA_ICON_NAME,
      expect.objectContaining({ width: 64, height: 64 }),
      { pixelRatio: 2 },
    );
  });

  it('calls loadImage BEFORE addImage (order-of-ops enforced by the promise)', async () => {
    const map = createMapMock();
    await registerEscuelaIcon(map as unknown as maplibregl.Map);

    const loadImageIdx = map.callOrder.findIndex((c) => c.startsWith('loadImage:'));
    const addImageIdx = map.callOrder.findIndex((c) => c.startsWith('addImage:'));
    expect(loadImageIdx).toBeGreaterThanOrEqual(0);
    expect(addImageIdx).toBeGreaterThan(loadImageIdx);
  });
});

describe('registerEscuelaIcon · hasImage guard', () => {
  it('short-circuits and does NOT re-loadImage when the image is already registered', async () => {
    const map = createMapMock({ images: [ESCUELA_ICON_NAME] });
    await expect(
      registerEscuelaIcon(map as unknown as maplibregl.Map),
    ).resolves.toBeUndefined();

    // Fast path: hasImage returns true → we skip loadImage + addImage entirely.
    expect(map.hasImage).toHaveBeenCalledWith(ESCUELA_ICON_NAME);
    expect(map.loadImage).not.toHaveBeenCalled();
    expect(map.addImage).not.toHaveBeenCalled();
  });

  it('does not call addImage twice when two concurrent registrations race (double hasImage guard)', async () => {
    // Simulate the race: first registration populates the cache before the
    // second Promise resolves. We stub loadImage to populate `hasImage`
    // BEFORE the Promise resolves, so the post-load double-check in
    // `registerEscuelaIcon` must skip `addImage`.
    const images = new Set<string>();
    const map = {
      hasImage: vi.fn((name: string) => images.has(name)),
      addImage: vi.fn((name: string) => {
        images.add(name);
      }),
      loadImage: vi.fn((_url: string) => {
        // Race: another registration completed between the initial guard and
        // the Promise resolve, so the image is already present when we resume.
        images.add(ESCUELA_ICON_NAME);
        return Promise.resolve({ data: { width: 64, height: 64 } as MockImage });
      }),
    };

    await registerEscuelaIcon(map as unknown as maplibregl.Map);
    expect(map.addImage).not.toHaveBeenCalled();
  });
});

describe('registerEscuelaIcon · error handling', () => {
  it('rejects when loadImage returns an error', async () => {
    const map = createMapMock({ loadImageError: new Error('404 not found') });
    await expect(
      registerEscuelaIcon(map as unknown as maplibregl.Map),
    ).rejects.toThrow('404 not found');
    expect(map.addImage).not.toHaveBeenCalled();
  });

  it('rejects when loadImage resolves without an image (no silent success)', async () => {
    const map = createMapMock({ loadImageReturnsNullImage: true });
    await expect(
      registerEscuelaIcon(map as unknown as maplibregl.Map),
    ).rejects.toThrow();
    expect(map.addImage).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// MapLibre v4 Promise API — regression guard for the callback→Promise shift
// ---------------------------------------------------------------------------
//
// MapLibre GL JS 4.x removed the callback overload of `map.loadImage`. The
// function now takes ONLY a URL and returns a `Promise<{data: HTMLImageElement
// | ImageBitmap}>`. A pre-v4 call like `map.loadImage(url, (err, img) => ...)`
// silently discards the callback and leaves the wrapping Promise pending
// forever — symbol layers whose `icon-image` references the icon then render
// invisibly because `addImage` is never called.
//
// This test pins the v4-correct behavior with a Promise-returning mock so any
// regression back to the callback style is caught by CI.
// -- see fix(escuelas): maplibre v4 loadImage Promise API
// ---------------------------------------------------------------------------

describe('registerEscuelaIcon · MapLibre v4 Promise loadImage API', () => {
  it('registers the icon when loadImage is a Promise (v4 API, no callback)', async () => {
    // v4 map surface: loadImage takes (url) only, returns Promise<{data}>.
    const images = new Set<string>();
    const imageInstance = { width: 64, height: 64 };
    const map = {
      hasImage: vi.fn((name: string) => images.has(name)),
      addImage: vi.fn((name: string) => {
        images.add(name);
      }),
      loadImage: vi.fn(
        (url: string): Promise<{ data: MockImage }> => {
          expect(url).toBe(ESCUELA_ICON_URL);
          return Promise.resolve({ data: imageInstance });
        },
      ),
    };

    await expect(
      registerEscuelaIcon(map as unknown as maplibregl.Map),
    ).resolves.toBeUndefined();

    // Critical assertion: addImage MUST have been called with the unwrapped
    // `.data` image object (not the outer `{data: ...}` envelope), otherwise
    // MapLibre silently hides the symbol layer that references the icon.
    expect(map.addImage).toHaveBeenCalledTimes(1);
    expect(map.addImage).toHaveBeenCalledWith(
      ESCUELA_ICON_NAME,
      imageInstance,
      { pixelRatio: 2 },
    );
  });

  it('rejects when the v4 loadImage Promise rejects', async () => {
    const map = {
      hasImage: vi.fn(() => false),
      addImage: vi.fn(),
      loadImage: vi.fn(() => Promise.reject(new Error('network failure'))),
    };

    await expect(
      registerEscuelaIcon(map as unknown as maplibregl.Map),
    ).rejects.toThrow('network failure');
    expect(map.addImage).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Layout factory — design §6.3 locks the exact shape
// ---------------------------------------------------------------------------

describe('buildEscuelasSymbolLayout', () => {
  it('sets icon-image to the canonical image name', () => {
    const layout = buildEscuelasSymbolLayout();
    expect(layout['icon-image']).toBe(ESCUELA_ICON_NAME);
  });

  it('uses a zoom-interpolated icon-size from 0.4 @ z10 to 0.8 @ z16', () => {
    const layout = buildEscuelasSymbolLayout();
    expect(layout['icon-size']).toEqual([
      'interpolate',
      ['linear'],
      ['zoom'],
      10,
      0.4,
      16,
      0.8,
    ]);
  });

  it('enables icon-allow-overlap (clusters of nearby schools still render every icon)', () => {
    const layout = buildEscuelasSymbolLayout();
    expect(layout['icon-allow-overlap']).toBe(true);
  });

  it('reads text-field from the `nombre` property', () => {
    const layout = buildEscuelasSymbolLayout();
    expect(layout['text-field']).toEqual(['get', 'nombre']);
  });

  it('sets text-size 11, text-offset [0, 1.2], text-optional true', () => {
    const layout = buildEscuelasSymbolLayout();
    expect(layout['text-size']).toBe(11);
    expect(layout['text-offset']).toEqual([0, 1.2]);
    expect(layout['text-optional']).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Paint factory — design §6.3
// ---------------------------------------------------------------------------

describe('buildEscuelasSymbolPaint', () => {
  it('renders the label in `#1a237e` with a white halo of width 1.5', () => {
    const paint = buildEscuelasSymbolPaint();
    expect(paint['text-color']).toBe('#1a237e');
    expect(paint['text-halo-color']).toBe('#ffffff');
    expect(paint['text-halo-width']).toBe(1.5);
  });
});

// ---------------------------------------------------------------------------
// Typescript-only ambient import shim (keeps `maplibregl.Map` typed in tests)
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-namespace
declare namespace maplibregl {
  // biome-ignore lint/suspicious/noExplicitAny: ambient shim narrowed by tests
  type Map = any;
}
