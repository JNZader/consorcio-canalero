/**
 * useRasterTileHealth.test.ts — Batch 1 "datos honestos".
 *
 * The hook exists because MapLibre emits ONE error per failed TILE: panning over
 * an area a raster source does not cover produces dozens of events per second.
 * The contract under test is therefore as much about what does NOT happen
 * (no state write, no log line, no re-render per event) as about the signal.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { logger } from '../../src/lib/logger';
import type { ClassifiedMapError } from '../../src/components/map2d/mapErrorClassify';
import { useRasterTileHealth } from '../../src/components/map2d/useRasterTileHealth';

function tileError(sourceId: string | null): ClassifiedMapError {
  return {
    kind: 'tile',
    sourceId,
    // A MOSAIC source: one event per failed tile, so the threshold applies.
    sourceType: 'raster',
    status: 404,
    url: 'https://tiles.example/1/2/3.png',
    message: 'AJAXError: Not Found (404)',
  };
}

/** A one-shot `image` source (the IGN overlay shape) — B4c/T4. */
function imageError(sourceId: string, kind: ClassifiedMapError['kind'] = 'tile'): ClassifiedMapError {
  return {
    kind,
    sourceId,
    sourceType: 'image',
    status: 404,
    url: 'https://app.example/assets/altimetria_ign.webp',
    message: 'AJAXError: Not Found (404)',
  };
}

const OTHER_ERROR: ClassifiedMapError = {
  kind: 'other',
  sourceId: null,
  sourceType: null,
  status: null,
  url: null,
  message: 'Style is not done loading',
};

let warnSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.useFakeTimers();
  warnSpy = vi.spyOn(logger, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  warnSpy.mockRestore();
});

/** Feed `count` tile errors for one source, back to back. */
function feed(
  onMapError: (error: ClassifiedMapError) => void,
  sourceId: string | null,
  count: number
) {
  act(() => {
    for (let i = 0; i < count; i += 1) onMapError(tileError(sourceId));
  });
}

describe('useRasterTileHealth · degradation threshold', () => {
  it('does NOT degrade on a single tile error', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 3 }));

    feed(result.current.onMapError, 'dem-tiles', 1);

    expect(result.current.degradedSourceIds).toEqual([]);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it('degrades once the threshold is reached inside the window, logging ONCE', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 3 }));

    feed(result.current.onMapError, 'dem-tiles', 3);

    expect(result.current.degradedSourceIds).toEqual(['dem-tiles']);
    expect(warnSpy).toHaveBeenCalledTimes(1);
  });

  it('does not log again while the source stays degraded', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 3 }));

    feed(result.current.onMapError, 'dem-tiles', 3);
    feed(result.current.onMapError, 'dem-tiles', 20);

    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(result.current.degradedSourceIds).toEqual(['dem-tiles']);
  });

  it('does NOT degrade when the failures fall outside the rolling window', () => {
    const { result } = renderHook(() =>
      useRasterTileHealth({ threshold: 3, windowMs: 1000, recoverMs: 60000 })
    );

    for (let i = 0; i < 5; i += 1) {
      feed(result.current.onMapError, 'dem-tiles', 1);
      act(() => {
        vi.advanceTimersByTime(1500);
      });
    }

    expect(result.current.degradedSourceIds).toEqual([]);
  });

  it('ignores non-tile errors entirely', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 2 }));

    act(() => {
      result.current.onMapError(OTHER_ERROR);
      result.current.onMapError(OTHER_ERROR);
      result.current.onMapError(OTHER_ERROR);
    });

    expect(result.current.degradedSourceIds).toEqual([]);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it('tracks each source independently', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 3 }));

    feed(result.current.onMapError, 'dem-tiles', 3);
    feed(result.current.onMapError, 'gee-tiles', 1);

    expect(result.current.degradedSourceIds).toEqual(['dem-tiles']);
  });
});

describe('useRasterTileHealth · unidentified sources', () => {
  it('never surfaces a source-less failure, but still logs it', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 3 }));

    feed(result.current.onMapError, null, 5);

    expect(result.current.degradedSourceIds).toEqual([]);
    expect(warnSpy).toHaveBeenCalledTimes(1);
  });
});

describe('useRasterTileHealth · recovery', () => {
  it('recovers after `recoverMs` of silence', () => {
    const { result } = renderHook(() =>
      useRasterTileHealth({ threshold: 3, windowMs: 15000, recoverMs: 10000 })
    );

    feed(result.current.onMapError, 'dem-tiles', 3);
    expect(result.current.degradedSourceIds).toEqual(['dem-tiles']);

    act(() => {
      vi.advanceTimersByTime(11000);
    });

    expect(result.current.degradedSourceIds).toEqual([]);
    // One line for the degradation, one for the recovery — never per tile.
    expect(warnSpy).toHaveBeenCalledTimes(2);
  });

  it('stays degraded while errors keep arriving', () => {
    const { result } = renderHook(() =>
      useRasterTileHealth({ threshold: 3, windowMs: 15000, recoverMs: 10000 })
    );

    feed(result.current.onMapError, 'dem-tiles', 3);

    for (let i = 0; i < 4; i += 1) {
      act(() => {
        vi.advanceTimersByTime(6000);
      });
      feed(result.current.onMapError, 'dem-tiles', 1);
    }

    expect(result.current.degradedSourceIds).toEqual(['dem-tiles']);
  });

  it('clears its recovery interval on unmount', () => {
    const clearSpy = vi.spyOn(globalThis, 'clearInterval');
    const { unmount } = renderHook(() => useRasterTileHealth());

    unmount();

    expect(clearSpy).toHaveBeenCalled();
    clearSpy.mockRestore();
  });
});

describe('useRasterTileHealth · render pressure', () => {
  it('does not re-render per tile error — only on the ok→degradado transition', () => {
    let renders = 0;
    const { result } = renderHook(() => {
      renders += 1;
      return useRasterTileHealth({ threshold: 5 });
    });

    const initialRenders = renders;

    // 4 errors: below the threshold, so NOT a single state write.
    feed(result.current.onMapError, 'dem-tiles', 4);
    expect(renders).toBe(initialRenders);

    // The 5th crosses it: exactly one re-render.
    feed(result.current.onMapError, 'dem-tiles', 1);
    expect(renders).toBe(initialRenders + 1);

    // 50 more while already degraded: still no further renders.
    feed(result.current.onMapError, 'dem-tiles', 50);
    expect(renders).toBe(initialRenders + 1);
  });
});

/**
 * Fix round — the `desconocido` bucket must never LEAK into the published list.
 *
 * It lives in the degraded set (so it dedups its log line and recovers like any
 * other key) and is filtered only at publication. Before the fix, both writers
 * spread the raw set: one storm of source-less errors followed by one real
 * degradation published `['dem-tiles', 'desconocido']`, and the recovery sweep
 * could leave a ghost behind.
 */
describe('useRasterTileHealth · desconocido never leaks', () => {
  it('publishes ONLY the real source in the MIXED case', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 8 }));

    feed(result.current.onMapError, null, 8);
    feed(result.current.onMapError, 'dem-tiles', 8);

    expect(result.current.degradedSourceIds).toEqual(['dem-tiles']);
  });

  it('publishes nothing at all when only the unknown bucket degraded', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 8 }));

    feed(result.current.onMapError, null, 40);

    expect(result.current.degradedSourceIds).toEqual([]);
  });

  it('leaves no ghost when the unknown bucket expires while a real source stays degraded', () => {
    const { result } = renderHook(() =>
      useRasterTileHealth({ threshold: 4, windowMs: 60000, recoverMs: 10000 })
    );

    feed(result.current.onMapError, null, 4);
    feed(result.current.onMapError, 'dem-tiles', 4);
    expect(result.current.degradedSourceIds).toEqual(['dem-tiles']);

    // Only the unknown bucket goes silent; `dem-tiles` keeps failing.
    for (let i = 0; i < 3; i += 1) {
      act(() => {
        vi.advanceTimersByTime(6000);
      });
      feed(result.current.onMapError, 'dem-tiles', 1);
    }

    expect(result.current.degradedSourceIds).toEqual(['dem-tiles']);
  });

  it('does not re-render when the expiring key was never published', () => {
    let renders = 0;
    const { result } = renderHook(() => {
      renders += 1;
      return useRasterTileHealth({ threshold: 4, windowMs: 60000, recoverMs: 10000 });
    });

    feed(result.current.onMapError, null, 4);
    const rendersAfterUnknown = renders;

    act(() => {
      vi.advanceTimersByTime(11000);
    });

    expect(renders).toBe(rendersAfterUnknown);
    expect(result.current.degradedSourceIds).toEqual([]);
  });
});

/**
 * B4c/T4 (RES-003) — the IGN altimetry overlay is a MapLibre `image` source:
 * ONE request for the whole extent. It could never reach 8 failures in 15 s, so
 * a 404 right after the user turned the layer on degraded nothing and the banner
 * stayed silent while the layer simply never appeared.
 */
describe('useRasterTileHealth · one-shot sources bypass the threshold', () => {
  const IGN = 'map2d-ign-overlay';

  it('degrades an `image` source on the FIRST failure', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 8 }));

    act(() => result.current.onMapError(imageError(IGN)));

    expect(result.current.degradedSourceIds).toEqual([IGN]);
  });

  it('degrades it even when the error is not AJAXError-shaped (`kind: other`)', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 8 }));

    act(() => result.current.onMapError(imageError(IGN, 'other')));

    expect(result.current.degradedSourceIds).toEqual([IGN]);
  });

  it('degrades a source listed in `immediateSourceIds` even without a source type', () => {
    const { result } = renderHook(() =>
      useRasterTileHealth({ threshold: 8, immediateSourceIds: [IGN] })
    );

    act(() =>
      result.current.onMapError({
        kind: 'tile',
        sourceId: IGN,
        sourceType: null,
        status: 404,
        url: null,
        message: 'AJAXError',
      })
    );

    expect(result.current.degradedSourceIds).toEqual([IGN]);
  });

  it('does NOT weaken the anti-noise threshold for mosaic sources', () => {
    const { result } = renderHook(() =>
      useRasterTileHealth({ threshold: 3, immediateSourceIds: [IGN] })
    );

    // Two raster-tile failures: still healthy, exactly as before.
    feed(result.current.onMapError, 'map2d-dem-raster', 2);
    expect(result.current.degradedSourceIds).toEqual([]);

    // …and the image source degrading alongside does not drag it in early.
    act(() => result.current.onMapError(imageError(IGN)));
    expect(result.current.degradedSourceIds).toEqual([IGN]);

    feed(result.current.onMapError, 'map2d-dem-raster', 1);
    expect([...result.current.degradedSourceIds].sort()).toEqual([IGN, 'map2d-dem-raster'].sort());
  });

  it('never publishes an unnamed one-shot failure as `desconocido`', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 8 }));

    act(() =>
      result.current.onMapError({
        kind: 'tile',
        sourceId: null,
        sourceType: 'image',
        status: 404,
        url: null,
        message: 'AJAXError',
      })
    );

    expect(result.current.degradedSourceIds).toEqual([]);
  });

  it('logs exactly ONE line for a one-shot degradation, not one per event', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 8 }));

    act(() => {
      result.current.onMapError(imageError(IGN));
      result.current.onMapError(imageError(IGN));
      result.current.onMapError(imageError(IGN));
    });

    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(String(warnSpy.mock.calls[0]?.[0])).toContain('única request');
  });

  /**
   * B4c fix round (REL-001/RES-001) — the silence sweep is a LIE for one-shot
   * sources. `recoverMs` means "no new failures ⇒ healed", which holds for tiles
   * only because they retry themselves on the next pan/zoom. An `ImageSource`
   * requests once from `onAdd` and never again (verified against the installed
   * maplibre-gl), so silence means "still broken". The previous version of this
   * suite asserted the opposite and blessed a blank layer being declared healthy
   * 60 s later.
   */
  it('does NOT recover by silence — it never retries, so silence is not health', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 8, recoverMs: 10_000 }));

    act(() => result.current.onMapError(imageError(IGN)));
    expect(result.current.degradedSourceIds).toEqual([IGN]);

    // Five minutes of perfect silence: still degraded, because nothing retried.
    act(() => vi.advanceTimersByTime(300_000));
    expect(result.current.degradedSourceIds).toEqual([IGN]);
  });

  it('still recovers MOSAIC sources by silence (the rule is untouched for tiles)', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 3, recoverMs: 10_000 }));

    feed(result.current.onMapError, 'map2d-dem-raster', 3);
    expect(result.current.degradedSourceIds).toEqual(['map2d-dem-raster']);

    act(() => vi.advanceTimersByTime(15_000));
    expect(result.current.degradedSourceIds).toEqual([]);
  });

  it('a degraded one-shot source does not block its neighbours from recovering', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 3, recoverMs: 10_000 }));

    act(() => result.current.onMapError(imageError(IGN)));
    feed(result.current.onMapError, 'map2d-dem-raster', 3);
    expect([...result.current.degradedSourceIds].sort()).toEqual([IGN, 'map2d-dem-raster'].sort());

    act(() => vi.advanceTimersByTime(15_000));
    expect(result.current.degradedSourceIds).toEqual([IGN]);
  });
});

/**
 * `clearSource` is the ONLY exit for a one-shot source, and it belongs to the
 * action that genuinely re-downloads (`reloadIgnSource`). Optimistic on purpose:
 * a retry that fails again re-degrades on its FIRST error.
 */
describe('useRasterTileHealth · clearSource (the real retry)', () => {
  const IGN = 'map2d-ign-overlay';

  it('runs the full cycle: error → stuck degraded → clear → clean → error → degraded again', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 8, recoverMs: 10_000 }));

    act(() => result.current.onMapError(imageError(IGN)));
    expect(result.current.degradedSourceIds).toEqual([IGN]);

    // Silence does nothing…
    act(() => vi.advanceTimersByTime(60_000));
    expect(result.current.degradedSourceIds).toEqual([IGN]);

    // …the retry does.
    act(() => result.current.clearSource(IGN));
    expect(result.current.degradedSourceIds).toEqual([]);

    // The re-download failed too → degraded again on the FIRST error, no
    // threshold, no leftover state from the previous round.
    act(() => result.current.onMapError(imageError(IGN)));
    expect(result.current.degradedSourceIds).toEqual([IGN]);

    // And it is STILL not recoverable by silence after the retry cycle.
    act(() => vi.advanceTimersByTime(60_000));
    expect(result.current.degradedSourceIds).toEqual([IGN]);
  });

  it('leaves other degraded sources alone', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 3 }));

    act(() => result.current.onMapError(imageError(IGN)));
    feed(result.current.onMapError, 'map2d-dem-raster', 3);

    act(() => result.current.clearSource(IGN));

    expect(result.current.degradedSourceIds).toEqual(['map2d-dem-raster']);
  });

  it('is a no-op for a source that was never degraded (no spurious re-render)', () => {
    let renders = 0;
    const { result } = renderHook(() => {
      renders += 1;
      return useRasterTileHealth({ threshold: 3 });
    });
    const before = renders;

    act(() => result.current.clearSource('map2d-never-failed'));

    expect(result.current.degradedSourceIds).toEqual([]);
    expect(renders).toBe(before);
  });

  it('clears the failure WINDOW too, so a cleared mosaic source starts from zero', () => {
    const { result } = renderHook(() => useRasterTileHealth({ threshold: 3 }));

    feed(result.current.onMapError, 'map2d-dem-raster', 3);
    expect(result.current.degradedSourceIds).toEqual(['map2d-dem-raster']);

    act(() => result.current.clearSource('map2d-dem-raster'));
    expect(result.current.degradedSourceIds).toEqual([]);

    // Two more failures must NOT be enough (they would be if the old window
    // survived the clear).
    feed(result.current.onMapError, 'map2d-dem-raster', 2);
    expect(result.current.degradedSourceIds).toEqual([]);
    feed(result.current.onMapError, 'map2d-dem-raster', 1);
    expect(result.current.degradedSourceIds).toEqual(['map2d-dem-raster']);
  });
});

/**
 * READ-002: the option is documented as EXTRA ids, so it must be additive —
 * a caller adding one id cannot silently drop the built-in IGN default.
 */
describe('useRasterTileHealth · immediateSourceIds is additive', () => {
  it('keeps the IGN default when a caller adds its own id', () => {
    const { result } = renderHook(() =>
      useRasterTileHealth({ threshold: 8, immediateSourceIds: ['otra-fuente'] })
    );

    act(() =>
      result.current.onMapError({
        kind: 'tile',
        sourceId: 'map2d-ign-overlay',
        sourceType: null,
        status: 404,
        url: null,
        message: 'AJAXError',
      })
    );
    act(() =>
      result.current.onMapError({
        kind: 'tile',
        sourceId: 'otra-fuente',
        sourceType: null,
        status: 404,
        url: null,
        message: 'AJAXError',
      })
    );

    expect([...result.current.degradedSourceIds].sort()).toEqual(
      ['map2d-ign-overlay', 'otra-fuente'].sort()
    );
  });
});
