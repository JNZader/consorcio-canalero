import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { isValidImageComparisonMock, loggerMock, mapImageApiMock } = vi.hoisted(() => ({
  isValidImageComparisonMock: vi.fn(),
  loggerMock: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
  mapImageApiMock: {
    getImageParams: vi.fn().mockResolvedValue({ imagen_principal: null, imagen_comparacion: null }),
    saveImagenPrincipal: vi.fn().mockResolvedValue({}),
    saveImagenComparacion: vi.fn().mockResolvedValue({}),
    regenerateTile: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('../../src/lib/typeGuards', () => ({
  isValidImageComparison: isValidImageComparisonMock,
}));

vi.mock('../../src/lib/logger', () => ({
  logger: loggerMock,
}));

vi.mock('../../src/lib/api/mapImage', () => ({
  mapImageApi: mapImageApiMock,
}));

import { useImageComparison, useImageComparisonListener } from '../../src/hooks/useImageComparison';
import type { SelectedImage } from '../../src/hooks/useSelectedImage';

const STORAGE_KEY = 'consorcio_image_comparison';

const leftImage: SelectedImage = {
  tile_url: 'https://tiles.test/layer',
  target_date: '2026-03-01',
  sensor: 'Sentinel-2',
  visualization: 'true_color',
  visualization_description: 'Natural color',
  collection: 'sentinel-2',
  images_count: 3,
  selected_at: '2026-03-01T10:00:00.000Z',
};

const rightImage: SelectedImage = {
  ...leftImage,
  target_date: '2026-03-15',
  selected_at: '2026-03-15T10:00:00.000Z',
};

const initialComparison = { left: leftImage, right: rightImage, enabled: true };

describe('useImageComparison', () => {
  const store = new Map<string, string>();

  beforeEach(() => {
    vi.clearAllMocks();
    store.clear();
    isValidImageComparisonMock.mockReturnValue(true);

    window.localStorage.getItem = vi.fn((key: string) => store.get(key) ?? null);
    window.localStorage.setItem = vi.fn((key: string, value: string) => {
      store.set(key, value);
    });
    window.localStorage.removeItem = vi.fn((key: string) => {
      store.delete(key);
    });
  });

  it('loads a valid stored comparison on mount', async () => {
    store.set(STORAGE_KEY, JSON.stringify(initialComparison));

    const { result } = renderHook(() => useImageComparison());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.comparison).toEqual(initialComparison);
    expect(result.current.isReady).toEqual(rightImage);
  });

  it('removes invalid or malformed stored payloads', async () => {
    store.set(STORAGE_KEY, '{bad-json');

    const first = renderHook(() => useImageComparison());
    await waitFor(() => expect(first.result.current.isLoading).toBe(false));
    expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);

    vi.clearAllMocks();
    store.set(STORAGE_KEY, JSON.stringify({ bad: true }));
    isValidImageComparisonMock.mockReturnValue(false);

    const second = renderHook(() => useImageComparison());
    await waitFor(() => expect(second.result.current.isLoading).toBe(false));
    expect(second.result.current.comparison).toBeNull();
    expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
  });

  it('setLeftImage creates a comparison, persists it, emits an event and saves backend params', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const { result } = renderHook(() => useImageComparison());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.setLeftImage(leftImage);
    });

    expect(result.current.comparison).toEqual({
      left: leftImage,
      right: leftImage,
      enabled: true,
    });
    expect(window.localStorage.setItem).toHaveBeenCalledWith(
      STORAGE_KEY,
      JSON.stringify({ left: leftImage, right: leftImage, enabled: true })
    );
    expect(mapImageApiMock.saveImagenComparacion).toHaveBeenCalledWith({
      enabled: true,
      left: {
        sensor: leftImage.sensor,
        target_date: leftImage.target_date,
        visualization: leftImage.visualization,
        max_cloud: null,
        days_buffer: 10,
      },
      right: {
        sensor: leftImage.sensor,
        target_date: leftImage.target_date,
        visualization: leftImage.visualization,
        max_cloud: null,
        days_buffer: 10,
      },
    });
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'imageComparisonChange' })
    );

    dispatchSpy.mockRestore();
  });

  it('setRightImage preserves the left image, and setEnabled only works when a comparison exists', async () => {
    store.set(STORAGE_KEY, JSON.stringify(initialComparison));
    const { result } = renderHook(() => useImageComparison());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const updatedRight: SelectedImage = {
      ...rightImage,
      target_date: '2026-04-01',
      selected_at: '2026-04-01T10:00:00.000Z',
    };

    act(() => {
      result.current.setRightImage(updatedRight);
    });

    expect(result.current.comparison).toEqual({
      left: leftImage,
      right: updatedRight,
      enabled: true,
    });

    act(() => {
      result.current.setEnabled(false);
    });

    expect(result.current.comparison?.enabled).toBe(false);

    store.clear();
    const empty = renderHook(() => useImageComparison());
    await waitFor(() => expect(empty.result.current.isLoading).toBe(false));
    act(() => {
      empty.result.current.setEnabled(true);
    });
    expect(empty.result.current.comparison).toBeNull();
  });

  it('clearComparison removes state, local storage, backend params and emits a null event', async () => {
    store.set(STORAGE_KEY, JSON.stringify(initialComparison));
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const { result } = renderHook(() => useImageComparison());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.clearComparison();
    });

    expect(result.current.comparison).toBeNull();
    expect(result.current.isReady).toBeFalsy();
    expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
    expect(mapImageApiMock.saveImagenComparacion).toHaveBeenCalledWith({
      enabled: false,
      left: null,
      right: null,
    });
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ detail: null })
    );

    dispatchSpy.mockRestore();
  });

  it('logs a warning when backend persistence fails', async () => {
    mapImageApiMock.saveImagenComparacion.mockRejectedValueOnce(new Error('save failed'));
    const { result } = renderHook(() => useImageComparison());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.setLeftImage(leftImage);
    });

    await waitFor(() => {
      expect(loggerMock.warn).toHaveBeenCalledWith(
        'Failed to persist comparison params to backend:',
        expect.any(Error)
      );
    });
  });
});

describe('useImageComparisonListener', () => {
  const store = new Map<string, string>();

  beforeEach(() => {
    vi.clearAllMocks();
    store.clear();
    isValidImageComparisonMock.mockReturnValue(true);

    window.localStorage.getItem = vi.fn((key: string) => store.get(key) ?? null);
    window.localStorage.setItem = vi.fn((key: string, value: string) => {
      store.set(key, value);
    });
    window.localStorage.removeItem = vi.fn((key: string) => {
      store.delete(key);
    });
  });

  it('loads the initial stored comparison when valid', () => {
    store.set(STORAGE_KEY, JSON.stringify(initialComparison));

    const { result } = renderHook(() => useImageComparisonListener());

    expect(result.current).toEqual(initialComparison);
  });

  it('ignores invalid initial data and clears bad local storage', () => {
    store.set(STORAGE_KEY, JSON.stringify({ bad: true }));
    isValidImageComparisonMock.mockReturnValue(false);

    const { result } = renderHook(() => useImageComparisonListener());

    expect(result.current).toBeNull();
    expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
  });

  it('reacts to same-tab custom events and cross-tab storage events', () => {
    const { result } = renderHook(() => useImageComparisonListener());

    act(() => {
      window.dispatchEvent(new CustomEvent('imageComparisonChange', { detail: initialComparison }));
    });
    expect(result.current).toEqual(initialComparison);

    act(() => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: STORAGE_KEY,
        newValue: JSON.stringify({ ...initialComparison, enabled: false }),
      }));
    });
    expect(result.current).toEqual({ ...initialComparison, enabled: false });

    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: STORAGE_KEY, newValue: null }));
    });
    expect(result.current).toBeNull();
  });

  it('ignores invalid custom payloads and unrelated storage keys, and cleans up listeners', () => {
    const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');
    const { result, unmount } = renderHook(() => useImageComparisonListener());

    isValidImageComparisonMock.mockReturnValue(false);
    act(() => {
      window.dispatchEvent(new CustomEvent('imageComparisonChange', { detail: { bad: true } }));
      window.dispatchEvent(new StorageEvent('storage', { key: 'other-key', newValue: JSON.stringify(initialComparison) }));
    });

    expect(result.current).toBeNull();

    unmount();

    expect(removeEventListenerSpy).toHaveBeenCalledWith('imageComparisonChange', expect.any(Function));
    expect(removeEventListenerSpy).toHaveBeenCalledWith('storage', expect.any(Function));

    removeEventListenerSpy.mockRestore();
  });
});
