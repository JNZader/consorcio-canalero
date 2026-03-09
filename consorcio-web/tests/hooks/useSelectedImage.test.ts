import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { isValidSelectedImageMock, loggerMock } = vi.hoisted(() => ({
  isValidSelectedImageMock: vi.fn(),
  loggerMock: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}));

vi.mock('../../src/lib/typeGuards', () => ({
  isValidSelectedImage: isValidSelectedImageMock,
}));

vi.mock('../../src/lib/logger', () => ({
  logger: loggerMock,
}));

import {
  getSelectedImageSync,
  useSelectedImage,
  useSelectedImageListener,
} from '../../src/hooks/useSelectedImage';

const STORAGE_KEY = 'consorcio_selected_image';

const baseImage = {
  tile_url: 'https://tiles.test/layer',
  target_date: '2026-03-01',
  sensor: 'Sentinel-2' as const,
  visualization: 'true_color',
  visualization_description: 'Natural color',
  collection: 'sentinel-2',
  images_count: 3,
  selected_at: '2026-03-01T10:00:00.000Z',
};

describe('useSelectedImage', () => {
  const store = new Map<string, string>();

  beforeEach(() => {
    vi.clearAllMocks();
    store.clear();

    window.localStorage.getItem = vi.fn((key: string) => store.get(key) ?? null);
    window.localStorage.setItem = vi.fn((key: string, value: string) => {
      store.set(key, value);
    });
    window.localStorage.removeItem = vi.fn((key: string) => {
      store.delete(key);
    });

    isValidSelectedImageMock.mockReturnValue(true);
  });

  it('loads valid image from localStorage on mount', async () => {
    store.set(STORAGE_KEY, JSON.stringify(baseImage));

    const { result } = renderHook(() => useSelectedImage());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.selectedImage).toEqual(baseImage);
    expect(result.current.hasSelectedImage).toBe(true);
  });

  it('clears invalid stored payload and handles parse errors', async () => {
    store.set(STORAGE_KEY, JSON.stringify({ bad: true }));
    isValidSelectedImageMock.mockReturnValue(false);

    const { result } = renderHook(() => useSelectedImage());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.selectedImage).toBeNull();
    expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);

    store.set(STORAGE_KEY, '{invalid-json');
    renderHook(() => useSelectedImage());
    expect(loggerMock.error).toHaveBeenCalled();
  });

  it('sets and clears selected image while dispatching change events', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const { result } = renderHook(() => useSelectedImage());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.setSelectedImage({ ...baseImage, selected_at: 'old' });
    });

    expect(window.localStorage.setItem).toHaveBeenCalledWith(
      STORAGE_KEY,
      expect.stringContaining('"tile_url":"https://tiles.test/layer"')
    );
    expect(result.current.hasSelectedImage).toBe(true);
    expect(dispatchSpy).toHaveBeenCalled();

    act(() => {
      result.current.clearSelectedImage();
    });

    expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
    expect(result.current.selectedImage).toBeNull();
    dispatchSpy.mockRestore();
  });

  it('listens to custom and storage updates in listener hook', () => {
    store.set(STORAGE_KEY, JSON.stringify(baseImage));

    const { result } = renderHook(() => useSelectedImageListener());
    expect(result.current).toEqual(baseImage);

    const updated = { ...baseImage, target_date: '2026-03-15' };
    act(() => {
      window.dispatchEvent(new CustomEvent('selectedImageChange', { detail: updated }));
    });
    expect(result.current?.target_date).toBe('2026-03-15');

    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: STORAGE_KEY,
          newValue: null,
        })
      );
    });
    expect(result.current).toBeNull();
  });

  it('returns sync selected image only when payload is valid', () => {
    store.set(STORAGE_KEY, JSON.stringify(baseImage));
    isValidSelectedImageMock.mockReturnValue(true);
    expect(getSelectedImageSync()).toEqual(baseImage);

    isValidSelectedImageMock.mockReturnValue(false);
    expect(getSelectedImageSync()).toBeNull();
    expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);

    store.set(STORAGE_KEY, '{broken');
    expect(getSelectedImageSync()).toBeNull();
  });
});
