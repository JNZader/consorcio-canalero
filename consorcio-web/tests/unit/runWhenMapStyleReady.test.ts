import { describe, expect, it, vi } from 'vitest';

import {
  isMapStyleNotReadyError,
  runWhenMapStyleReady,
} from '../../src/components/map2d/map2dUtils';

describe('runWhenMapStyleReady', () => {
  it('swallows Style is not done loading so ErrorBoundary does not unmount the map', () => {
    const map = {} as never;
    const fn = vi.fn(() => {
      throw new Error('Style is not done loading.');
    });
    expect(() => runWhenMapStyleReady(map, true, fn)).not.toThrow();
    expect(fn).toHaveBeenCalledOnce();
  });

  it('rethrows other errors', () => {
    const map = {} as never;
    expect(() =>
      runWhenMapStyleReady(map, true, () => {
        throw new Error('boom');
      }),
    ).toThrow('boom');
  });

  it('no-ops when the map is not ready', () => {
    const fn = vi.fn();
    runWhenMapStyleReady({} as never, false, fn);
    expect(fn).not.toHaveBeenCalled();
  });
});

describe('isMapStyleNotReadyError', () => {
  it('matches MapLibre _checkLoaded', () => {
    expect(isMapStyleNotReadyError(new Error('Style is not done loading'))).toBe(true);
    expect(isMapStyleNotReadyError(new Error('tile fail'))).toBe(false);
  });
});
