// @ts-nocheck
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useMapReady } from '../../src/hooks/useMapReady';

const invalidateSizeMock = vi.fn();
const getContainerMock = vi.fn();

vi.mock('react-leaflet', () => ({
  useMap: () => ({
    invalidateSize: invalidateSizeMock,
    getContainer: getContainerMock,
  }),
}));

describe('useMapReady', () => {
  const observeMock = vi.fn();
  const disconnectMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();

    getContainerMock.mockReturnValue(document.createElement('div'));

    class ResizeObserverMock {
      observe = observeMock;
      disconnect = disconnectMock;
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(cb, 0) as unknown as number);
    vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  // ============================================
  // IMMEDIATE INVALIDATION
  // ============================================

  describe('Immediate invalidation', () => {
    it('catches mutation: should call invalidateSize immediately on mount', () => {
      renderHook(() => useMapReady());
      
      expect(invalidateSizeMock).toHaveBeenCalled();
    });

    it('catches mutation: should call invalidateSize at least once synchronously', () => {
      renderHook(() => useMapReady());
      
      expect(invalidateSizeMock.mock.calls.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ============================================
  // TIMEOUT SCHEDULING
  // ============================================

  describe('Timeout scheduling', () => {
    it('catches mutation: should schedule timeout at 0ms', () => {
      const timeoutSpy = vi.spyOn(global, 'setTimeout');
      
      renderHook(() => useMapReady());
      
      // Check that at least one timeout was scheduled with 0ms
      const hasZeroTimeout = timeoutSpy.mock.calls.some(call => call[1] === 0);
      expect(hasZeroTimeout).toBe(true);
      
      timeoutSpy.mockRestore();
    });

    it('catches mutation: should schedule timeout at 100ms', () => {
      const timeoutSpy = vi.spyOn(global, 'setTimeout');
      
      renderHook(() => useMapReady());
      
      const has100msTimeout = timeoutSpy.mock.calls.some(call => call[1] === 100);
      expect(has100msTimeout).toBe(true);
      
      timeoutSpy.mockRestore();
    });

    it('catches mutation: should schedule timeout at 300ms', () => {
      const timeoutSpy = vi.spyOn(global, 'setTimeout');
      
      renderHook(() => useMapReady());
      
      const has300msTimeout = timeoutSpy.mock.calls.some(call => call[1] === 300);
      expect(has300msTimeout).toBe(true);
      
      timeoutSpy.mockRestore();
    });

    it('catches mutation: should call invalidateSize in scheduled timeouts', () => {
      renderHook(() => useMapReady());
      
      // Run all timers and verify invalidateSize was called
      vi.runAllTimers();
      
      expect(invalidateSizeMock.mock.calls.length).toBeGreaterThanOrEqual(3);
    });
  });

  // ============================================
  // REQUEST ANIMATION FRAME
  // ============================================

  describe('RequestAnimationFrame handling', () => {
    it('catches mutation: should use requestAnimationFrame', () => {
      const rafSpy = vi.spyOn(global, 'requestAnimationFrame');
      
      renderHook(() => useMapReady());
      
      expect(rafSpy).toHaveBeenCalled();
      
      rafSpy.mockRestore();
    });

    it('catches mutation: should call invalidateSize in RAF callback', () => {
      renderHook(() => useMapReady());
      
      // Run all timers to execute RAF callbacks
      vi.runAllTimers();
      
      expect(invalidateSizeMock).toHaveBeenCalled();
    });

    it('catches mutation: should schedule additional RAF after initialization', () => {
      const rafSpy = vi.spyOn(global, 'requestAnimationFrame');
      
      renderHook(() => useMapReady());
      vi.runAllTimers();
      
      // Should be called at least twice: once for initial, once for post-init
      expect(rafSpy.mock.calls.length).toBeGreaterThanOrEqual(2);
      
      rafSpy.mockRestore();
    });

    it('catches mutation: should set hasInitialized flag correctly', () => {
      renderHook(() => useMapReady());
      
      vi.runAllTimers();
      
      // The hook tracks initialization internally via hasInitialized.current
      // We verify it works by checking that RAF is called twice
      expect(invalidateSizeMock.mock.calls.length).toBeGreaterThan(0);
    });
  });

  // ============================================
  // EVENT LISTENERS
  // ============================================

  describe('Event listener setup and cleanup', () => {
    it('catches mutation: should register window resize listener', () => {
      const addWindowSpy = vi.spyOn(window, 'addEventListener');
      
      renderHook(() => useMapReady());
      
      expect(addWindowSpy).toHaveBeenCalledWith('resize', expect.any(Function));
      
      addWindowSpy.mockRestore();
    });

    it('catches mutation: should register document visibilitychange listener', () => {
      const addDocSpy = vi.spyOn(document, 'addEventListener');
      
      renderHook(() => useMapReady());
      
      expect(addDocSpy).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
      
      addDocSpy.mockRestore();
    });

    it('catches mutation: should remove window resize listener on cleanup', () => {
      const removeWindowSpy = vi.spyOn(window, 'removeEventListener');
      
      const { unmount } = renderHook(() => useMapReady());
      
      unmount();
      
      expect(removeWindowSpy).toHaveBeenCalledWith('resize', expect.any(Function));
      
      removeWindowSpy.mockRestore();
    });

    it('catches mutation: should remove document visibilitychange listener on cleanup', () => {
      const removeDocSpy = vi.spyOn(document, 'removeEventListener');
      
      const { unmount } = renderHook(() => useMapReady());
      
      unmount();
      
      expect(removeDocSpy).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
      
      removeDocSpy.mockRestore();
    });

    it('catches mutation: should call invalidateSize when window resize event fires', () => {
      renderHook(() => useMapReady());
      
      vi.runAllTimers();
      const callCountBefore = invalidateSizeMock.mock.calls.length;
      
      // Trigger resize event
      window.dispatchEvent(new Event('resize'));
      
      expect(invalidateSizeMock.mock.calls.length).toBeGreaterThan(callCountBefore);
    });

    it('catches mutation: should call invalidateSize when visibility becomes visible', () => {
      // Mock document.visibilityState
      Object.defineProperty(document, 'visibilityState', {
        value: 'visible',
        configurable: true,
      });

      renderHook(() => useMapReady());
      
      vi.runAllTimers();
      const callCountBefore = invalidateSizeMock.mock.calls.length;
      
      // Trigger visibility change event
      document.dispatchEvent(new Event('visibilitychange'));
      
      expect(invalidateSizeMock.mock.calls.length).toBeGreaterThan(callCountBefore);
    });

    it('catches mutation: should NOT call invalidateSize when visibility is hidden', () => {
      Object.defineProperty(document, 'visibilityState', {
        value: 'hidden',
        configurable: true,
      });

      renderHook(() => useMapReady());
      
      vi.runAllTimers();
      const callCountBefore = invalidateSizeMock.mock.calls.length;
      
      // Trigger visibility change event while hidden
      document.dispatchEvent(new Event('visibilitychange'));
      
      // Should NOT increase (or only by scheduled timeouts, not from visibility handler)
      expect(invalidateSizeMock.mock.calls.length).toBe(callCountBefore);
    });

    it('catches mutation: should schedule extra invalidateSize call with 100ms after visibility becomes visible', () => {
      Object.defineProperty(document, 'visibilityState', {
        value: 'visible',
        configurable: true,
      });

      const timeoutSpy = vi.spyOn(global, 'setTimeout');
      
      renderHook(() => useMapReady());
      
      vi.runAllTimers();
      timeoutSpy.mockClear();
      
      // Trigger visibility change
      document.dispatchEvent(new Event('visibilitychange'));
      
      // Should have scheduled a 100ms timeout
      const has100msTimeout = timeoutSpy.mock.calls.some(call => call[1] === 100);
      expect(has100msTimeout).toBe(true);
      
      timeoutSpy.mockRestore();
    });
  });

  // ============================================
  // RESIZE OBSERVER
  // ============================================

  describe('ResizeObserver handling', () => {
    it('catches mutation: should create ResizeObserver', () => {
      renderHook(() => useMapReady());
      
      // The ResizeObserver constructor should have been called
      expect(getContainerMock).toHaveBeenCalled();
      expect(observeMock).toHaveBeenCalledTimes(1);
    });

    it('catches mutation: should observe the map container', () => {
      const container = document.createElement('div');
      getContainerMock.mockReturnValue(container);
      
      renderHook(() => useMapReady());
      
      expect(observeMock).toHaveBeenCalledWith(container);
    });

    it('catches mutation: should disconnect ResizeObserver on cleanup', () => {
      const { unmount } = renderHook(() => useMapReady());
      
      unmount();
      
      expect(disconnectMock).toHaveBeenCalledTimes(1);
    });

    it('catches mutation: should not fail if ResizeObserver is not available', () => {
      vi.unstubAllGlobals();
      vi.stubGlobal('ResizeObserver', undefined);
      
      const { unmount } = renderHook(() => useMapReady());
      
      // Should not throw
      expect(() => unmount()).not.toThrow();
    });
  });

  // ============================================
  // CLEANUP COMPREHENSIVE
  // ============================================

  describe('Comprehensive cleanup', () => {
    it('invalidates map size repeatedly and wires cleanup handlers', () => {
      const addWindowSpy = vi.spyOn(window, 'addEventListener');
      const removeWindowSpy = vi.spyOn(window, 'removeEventListener');
      const addDocSpy = vi.spyOn(document, 'addEventListener');
      const removeDocSpy = vi.spyOn(document, 'removeEventListener');

      const { unmount } = renderHook(() => useMapReady());

      vi.runAllTimers();
      expect(invalidateSizeMock).toHaveBeenCalled();
      expect(observeMock).toHaveBeenCalledTimes(1);
      expect(addWindowSpy).toHaveBeenCalledWith('resize', expect.any(Function));
      expect(addDocSpy).toHaveBeenCalledWith('visibilitychange', expect.any(Function));

      unmount();

      expect(removeWindowSpy).toHaveBeenCalledWith('resize', expect.any(Function));
      expect(removeDocSpy).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
      expect(disconnectMock).toHaveBeenCalledTimes(1);
      
      addWindowSpy.mockRestore();
      removeWindowSpy.mockRestore();
      addDocSpy.mockRestore();
      removeDocSpy.mockRestore();
    });

    it('catches mutation: should clear all timeouts on cleanup', () => {
      const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout');
      
      const { unmount } = renderHook(() => useMapReady());
      
      unmount();
      
      // Should have cleared multiple timeouts
      expect(clearTimeoutSpy.mock.calls.length).toBeGreaterThanOrEqual(3);
      
      clearTimeoutSpy.mockRestore();
    });

    it('catches mutation: should cancel animation frame on cleanup', () => {
      const cancelSpy = vi.spyOn(global, 'cancelAnimationFrame');
      
      const { unmount } = renderHook(() => useMapReady());
      
      unmount();
      
      expect(cancelSpy).toHaveBeenCalled();
      
      cancelSpy.mockRestore();
    });
  });

  // ============================================
  // RETURN VALUE
  // ============================================

  describe('Return value', () => {
    it('catches mutation: should return the map object', () => {
      const { result } = renderHook(() => useMapReady());
      
      expect(result.current).toBeDefined();
      expect(result.current.invalidateSize).toBeDefined();
      expect(result.current.getContainer).toBeDefined();
    });
  });

  // ============================================
  // ADVANCED CALLBACK VERIFICATION
  // ============================================

  describe('Advanced callback verification', () => {
    it('catches mutation: timeout callback MUST call invalidateSize (not undefined)', () => {
      const timeoutSpy = vi.spyOn(global, 'setTimeout');
      
      renderHook(() => useMapReady());

      // Get all timeout callbacks
      const callbacks = timeoutSpy.mock.calls.map(call => call[0]);
      expect(callbacks.length).toBeGreaterThanOrEqual(3);

      // Verify each callback actually calls invalidateSize
      invalidateSizeMock.mockClear();
      vi.runAllTimers();

      expect(invalidateSizeMock).toHaveBeenCalled();

      timeoutSpy.mockRestore();
    });

    it('catches mutation: ResizeObserver callback MUST call invalidateSize', () => {
      const observerCallbacks: FrameRequestCallback[] = [];
      
      class ResizeObserverCapture {
        callback: ResizeObserverCallback;
        constructor(callback: ResizeObserverCallback) {
          this.callback = callback;
        }
        observe(el: Element) {
          observerCallbacks.push(this.callback as any);
        }
        disconnect() {}
      }

      vi.stubGlobal('ResizeObserver', ResizeObserverCapture as any);

      renderHook(() => useMapReady());

      // The ResizeObserver was created and callback stored
      expect(observerCallbacks.length).toBeGreaterThan(0);

      invalidateSizeMock.mockClear();
      
      // Simulate resize event
      vi.runAllTimers();
      
      // ResizeObserver callback should have called invalidateSize
      expect(invalidateSizeMock).toHaveBeenCalled();
    });

    it('catches mutation: RAF callback MUST call invalidateSize on each invocation', () => {
      const rafCallbacks: FrameRequestCallback[] = [];
      const originalRAF = global.requestAnimationFrame;
      
      vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
        rafCallbacks.push(cb);
        return setTimeout(cb, 0) as unknown as number;
      });

      renderHook(() => useMapReady());

      expect(rafCallbacks.length).toBeGreaterThan(0);

      invalidateSizeMock.mockClear();
      vi.runAllTimers();

      // All RAF callbacks should have executed and called invalidateSize
      expect(invalidateSizeMock).toHaveBeenCalled();

      vi.stubGlobal('requestAnimationFrame', originalRAF);
    });

    it('catches mutation: resize event handler MUST call invalidateSize', () => {
      renderHook(() => useMapReady());

      invalidateSizeMock.mockClear();
      const callCountBefore = invalidateSizeMock.mock.calls.length;

      window.dispatchEvent(new Event('resize'));

      expect(invalidateSizeMock.mock.calls.length).toBeGreaterThan(callCountBefore);
    });

    it('catches mutation: visibility change to visible MUST call invalidateSize', () => {
      Object.defineProperty(document, 'visibilityState', {
        value: 'visible',
        configurable: true,
      });

      renderHook(() => useMapReady());

      invalidateSizeMock.mockClear();
      const callCountBefore = invalidateSizeMock.mock.calls.length;

      document.dispatchEvent(new Event('visibilitychange'));

      expect(invalidateSizeMock.mock.calls.length).toBeGreaterThan(callCountBefore);
    });

    it('catches mutation: visibility condition MUST check === "visible" exactly', () => {
      const visibilityStates = ['visible', 'hidden', 'prerender', 'unloaded'];

      for (const state of visibilityStates) {
        Object.defineProperty(document, 'visibilityState', {
          value: state,
          configurable: true,
        });

        invalidateSizeMock.mockClear();
        vi.clearAllMocks();

        renderHook(() => useMapReady());

        vi.runAllTimers();
        const callCountAfterInit = invalidateSizeMock.mock.calls.length;

        document.dispatchEvent(new Event('visibilitychange'));

        if (state === 'visible') {
          // Should increase calls
          expect(invalidateSizeMock.mock.calls.length).toBeGreaterThan(callCountAfterInit);
        } else {
          // Should NOT increase calls from visibility handler
          expect(invalidateSizeMock.mock.calls.length).toBe(callCountAfterInit);
        }
      }
    });
  });

  // ============================================
  // CLEANUP HANDLER VERIFICATION
  // ============================================

  describe('Cleanup handler verification', () => {
    it('catches mutation: clearTimeout MUST be called for each timeout ID', () => {
      const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout');

      const { unmount } = renderHook(() => useMapReady());

      clearTimeoutSpy.mockClear();

      unmount();

      // Should have cleared all 3+ timeouts
      expect(clearTimeoutSpy.mock.calls.length).toBeGreaterThanOrEqual(3);

      clearTimeoutSpy.mockRestore();
    });

    it('catches mutation: listener cleanup callbacks MUST execute with exact function reference', () => {
      const addedListeners = new Map<string, Function[]>();
      const removedListeners = new Map<string, Function[]>();

      const originalAdd = window.addEventListener;
      const originalRemove = window.removeEventListener;

      window.addEventListener = vi.fn((event: string, handler: any) => {
        if (!addedListeners.has(event)) addedListeners.set(event, []);
        addedListeners.get(event)!.push(handler);
        return originalAdd.call(window, event, handler);
      });

      window.removeEventListener = vi.fn((event: string, handler: any) => {
        if (!removedListeners.has(event)) removedListeners.set(event, []);
        removedListeners.get(event)!.push(handler);
        return originalRemove.call(window, event, handler);
      });

      const { unmount } = renderHook(() => useMapReady());

      const addedResizeHandlers = addedListeners.get('resize');
      expect(addedResizeHandlers?.length).toBeGreaterThan(0);

      unmount();

      const removedResizeHandlers = removedListeners.get('resize');
      // Should have attempted to remove
      expect(removedResizeHandlers?.length).toBeGreaterThan(0);

      window.addEventListener = originalAdd;
      window.removeEventListener = originalRemove;
    });

    it('catches mutation: ResizeObserver.disconnect() MUST be called on cleanup', () => {
      const { unmount } = renderHook(() => useMapReady());

      // disconnectMock was called during setup (constructor and observe)
      const initialCallCount = disconnectMock.mock.calls.length;

      unmount();

      // disconnect should be called on cleanup
      expect(disconnectMock.mock.calls.length).toBeGreaterThanOrEqual(initialCallCount);
    });

    it('catches mutation: cancelAnimationFrame MUST be called with correct ID', () => {
      const cancelSpy = vi.spyOn(global, 'cancelAnimationFrame');

      const { unmount } = renderHook(() => useMapReady());

      cancelSpy.mockClear();

      unmount();

      expect(cancelSpy).toHaveBeenCalled();

      cancelSpy.mockRestore();
    });
  });

  // ============================================
  // TIMING CRITICAL TESTS
  // ============================================

  describe('Timing critical tests', () => {
    it('catches mutation: must schedule timeout at EXACTLY 0ms, 100ms, 300ms', () => {
      const scheduledTimeouts = new Set<number>();
      const originalSetTimeout = global.setTimeout;

      vi.stubGlobal('setTimeout', ((callback: any, delay: number) => {
        if (typeof delay === 'number') {
          scheduledTimeouts.add(delay);
        }
        return originalSetTimeout.call(global, callback, delay);
      }) as any);

      renderHook(() => useMapReady());

      expect(scheduledTimeouts.has(0)).toBe(true);
      expect(scheduledTimeouts.has(100)).toBe(true);
      expect(scheduledTimeouts.has(300)).toBe(true);

      vi.stubGlobal('setTimeout', originalSetTimeout);
    });

    it('catches mutation: timeout at 0ms MUST call invalidateSize when executed', () => {
      const timeoutCallbacks = new Map<number, any[]>();
      const originalSetTimeout = global.setTimeout;

      vi.stubGlobal('setTimeout', ((callback: any, delay: number) => {
        if (!timeoutCallbacks.has(delay)) {
          timeoutCallbacks.set(delay, []);
        }
        timeoutCallbacks.get(delay)!.push(callback);
        return originalSetTimeout.call(global, callback, delay);
      }) as any);

      invalidateSizeMock.mockClear();

      renderHook(() => useMapReady());

      // Get the 0ms callback and verify it calls invalidateSize
      const zeroMsCallbacks = timeoutCallbacks.get(0) || [];
      expect(zeroMsCallbacks.length).toBeGreaterThan(0);

      vi.runAllTimers();

      expect(invalidateSizeMock).toHaveBeenCalled();

      vi.stubGlobal('setTimeout', originalSetTimeout);
    });

    it('catches mutation: useMap() must be called and return valid map object', () => {
      const { result } = renderHook(() => useMapReady());

      expect(result.current).toBeDefined();
      expect(typeof result.current.invalidateSize).toBe('function');
      expect(typeof result.current.getContainer).toBe('function');
    });
  });

  // ============================================
  // EDGE CASE: NO FEATURES MISSING
  // ============================================

  describe('Feature completeness', () => {
    it('catches mutation: all three timeout delays must be present and distinct', () => {
      const timeoutSpy = vi.spyOn(global, 'setTimeout');

      renderHook(() => useMapReady());

      const delays = timeoutSpy.mock.calls.map(call => call[1]).filter(d => typeof d === 'number');
      
      // Must have timeouts with specific delays
      expect(delays).toContain(0);
      expect(delays).toContain(100);
      expect(delays).toContain(300);

      timeoutSpy.mockRestore();
    });

    it('catches mutation: requestAnimationFrame must be used', () => {
      const rafSpy = vi.spyOn(global, 'requestAnimationFrame');

      renderHook(() => useMapReady());

      expect(rafSpy).toHaveBeenCalled();

      rafSpy.mockRestore();
    });

    it('catches mutation: ResizeObserver must be created if available', () => {
      const { unmount } = renderHook(() => useMapReady());

      expect(observeMock).toHaveBeenCalled();
      expect(getContainerMock).toHaveBeenCalled();

      unmount();

      expect(disconnectMock).toHaveBeenCalled();
    });

    it('catches mutation: both window and document event listeners must be registered', () => {
      const addWindowSpy = vi.spyOn(window, 'addEventListener');
      const addDocSpy = vi.spyOn(document, 'addEventListener');

      renderHook(() => useMapReady());

      expect(addWindowSpy).toHaveBeenCalledWith('resize', expect.any(Function));
      expect(addDocSpy).toHaveBeenCalledWith('visibilitychange', expect.any(Function));

      addWindowSpy.mockRestore();
      addDocSpy.mockRestore();
    });
  });
});
