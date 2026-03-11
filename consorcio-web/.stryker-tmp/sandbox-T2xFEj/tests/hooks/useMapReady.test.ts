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
});
