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
  });
});
