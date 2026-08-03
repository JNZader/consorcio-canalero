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
    status: 404,
    url: 'https://tiles.example/1/2/3.png',
    message: 'AJAXError: Not Found (404)',
  };
}

const OTHER_ERROR: ClassifiedMapError = {
  kind: 'other',
  sourceId: null,
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
