import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useDeferredIdleMount } from '../../src/hooks/useDeferredIdleMount';

/**
 * PERF — this hook is the gate that keeps the service-worker registration
 * (inside ``UpdateBanner``) out of the LCP window. The behaviour that matters
 * is the ORDER: nothing may flip before ``load`` has fired, and nothing may
 * flip on ``load`` alone either — the main thread has to go idle first.
 *
 * ``document.readyState`` is stubbed rather than driven for real: happy-dom
 * reports ``complete`` as soon as the document exists, which would make the
 * "still loading" branch untestable.
 */
describe('useDeferredIdleMount', () => {
  let readyState: DocumentReadyState;

  beforeEach(() => {
    readyState = 'loading';
    vi.spyOn(document, 'readyState', 'get').mockImplementation(() => readyState);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  /** Removes ``requestIdleCallback`` so the ``setTimeout`` branch is taken. */
  function withoutRequestIdleCallback() {
    const original = window.requestIdleCallback;
    // biome-ignore lint/performance/noDelete: restoring the exact absence is the point
    delete (window as { requestIdleCallback?: unknown }).requestIdleCallback;
    return () => {
      window.requestIdleCallback = original;
    };
  }

  it('stays false while the page is still loading', () => {
    const restore = withoutRequestIdleCallback();
    try {
      const { result } = renderHook(() => useDeferredIdleMount());

      expect(result.current).toBe(false);

      // Time passing is NOT enough — the timer is only armed on ``load``.
      act(() => {
        vi.advanceTimersByTime(10_000);
      });
      expect(result.current).toBe(false);
    } finally {
      restore();
    }
  });

  it('stays false on load alone and flips once the idle fallback fires', () => {
    const restore = withoutRequestIdleCallback();
    try {
      const { result } = renderHook(() => useDeferredIdleMount());

      act(() => {
        window.dispatchEvent(new Event('load'));
      });
      expect(result.current).toBe(false);

      act(() => {
        vi.advanceTimersByTime(3000);
      });
      expect(result.current).toBe(true);
    } finally {
      restore();
    }
  });

  it('uses requestIdleCallback when the browser provides one', () => {
    const idleSpy = vi.fn((cb: IdleRequestCallback) => {
      cb({ didTimeout: false, timeRemaining: () => 50 } as IdleDeadline);
      return 1;
    });
    window.requestIdleCallback = idleSpy as unknown as typeof window.requestIdleCallback;

    const { result } = renderHook(() => useDeferredIdleMount());
    expect(idleSpy).not.toHaveBeenCalled();

    act(() => {
      window.dispatchEvent(new Event('load'));
    });

    expect(idleSpy).toHaveBeenCalledTimes(1);
    expect(result.current).toBe(true);
  });

  it('arms immediately when load already fired before mount', () => {
    readyState = 'complete';
    const restore = withoutRequestIdleCallback();
    try {
      const { result } = renderHook(() => useDeferredIdleMount());
      expect(result.current).toBe(false);

      act(() => {
        vi.advanceTimersByTime(3000);
      });
      expect(result.current).toBe(true);
    } finally {
      restore();
    }
  });

  it('does not flip after unmount', () => {
    const restore = withoutRequestIdleCallback();
    try {
      const { result, unmount } = renderHook(() => useDeferredIdleMount());

      act(() => {
        window.dispatchEvent(new Event('load'));
      });
      unmount();

      act(() => {
        vi.advanceTimersByTime(10_000);
      });
      expect(result.current).toBe(false);
    } finally {
      restore();
    }
  });
});
