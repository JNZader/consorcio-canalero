import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { isValidSelectedImageMock, loggerMock, mapImageApiMock } = vi.hoisted(() => ({
  isValidSelectedImageMock: vi.fn(),
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
  isValidSelectedImage: isValidSelectedImageMock,
}));

vi.mock('../../src/lib/logger', () => ({
  logger: loggerMock,
}));

vi.mock('../../src/lib/api/mapImage', () => ({
  mapImageApi: mapImageApiMock,
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
    mapImageApiMock.getImageParams.mockResolvedValue({ imagen_principal: null, imagen_comparacion: null });
    mapImageApiMock.regenerateTile.mockResolvedValue({
      tile_url: 'https://tiles.test/restored',
      target_date: '2026-03-05',
      sensor: 'Sentinel-2',
      visualization: 'true_color',
      visualization_description: 'Natural color',
      collection: 'sentinel-2',
      images_count: 2,
    });
  });

  it('loads a valid image from localStorage on mount', async () => {
    store.set(STORAGE_KEY, JSON.stringify(baseImage));

    const { result } = renderHook(() => useSelectedImage());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.selectedImage).toEqual(baseImage);
    expect(result.current.hasSelectedImage).toBe(true);
  });

  it('clears invalid or broken localStorage payloads', async () => {
    store.set(STORAGE_KEY, '{broken');
    const { result, rerender } = renderHook(() => useSelectedImage());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.selectedImage).toBeNull();
    expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
    expect(loggerMock.error).toHaveBeenCalled();

    vi.clearAllMocks();
    store.set(STORAGE_KEY, JSON.stringify({ bad: true }));
    isValidSelectedImageMock.mockReturnValue(false);
    rerender();
  });

  it('sets and clears the selected image while syncing localStorage and backend params', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const { result } = renderHook(() => useSelectedImage());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.setSelectedImage(baseImage);
    });

    expect(result.current.selectedImage?.tile_url).toBe(baseImage.tile_url);
    expect(result.current.selectedImage?.selected_at).toBeTypeOf('string');
    expect(window.localStorage.setItem).toHaveBeenCalledWith(STORAGE_KEY, expect.any(String));
    expect(mapImageApiMock.saveImagenPrincipal).toHaveBeenCalledWith({
      sensor: 'Sentinel-2',
      target_date: '2026-03-01',
      visualization: 'true_color',
      max_cloud: null,
      days_buffer: 10,
    });
    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'selectedImageChange' }));

    act(() => {
      result.current.clearSelectedImage();
    });

    expect(result.current.selectedImage).toBeNull();
    expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
    expect(mapImageApiMock.saveImagenPrincipal).toHaveBeenCalledWith({
      sensor: '',
      target_date: '',
      visualization: '',
      max_cloud: null,
      days_buffer: 10,
    });
    dispatchSpy.mockRestore();
  });

  it('reacts only to matching storage events', async () => {
    store.set(STORAGE_KEY, JSON.stringify(baseImage));
    const { result } = renderHook(() => useSelectedImage());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'other_key',
          newValue: JSON.stringify({ ...baseImage, target_date: '2026-04-01' }),
        }),
      );
    });
    expect(result.current.selectedImage?.target_date).toBe('2026-03-01');

    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: STORAGE_KEY,
          newValue: JSON.stringify({ ...baseImage, target_date: '2026-04-01' }),
        }),
      );
    });
    expect(result.current.selectedImage?.target_date).toBe('2026-04-01');
  });
});

describe('useSelectedImageListener', () => {
  const store = new Map<string, string>();
  const freshImage = {
    ...baseImage,
    selected_at: new Date().toISOString(),
  };

  beforeEach(() => {
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

  it('listens to same-tab custom events and cross-tab storage events', () => {
    store.set(STORAGE_KEY, JSON.stringify(freshImage));
    const { result } = renderHook(() => useSelectedImageListener());

    expect(result.current).toEqual(freshImage);

    act(() => {
      window.dispatchEvent(
        new CustomEvent('selectedImageChange', { detail: { ...baseImage, target_date: '2026-03-20' } }),
      );
    });
    expect(result.current?.target_date).toBe('2026-03-20');

    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: STORAGE_KEY, newValue: null }));
    });
    expect(result.current).toBeNull();
  });

  it('restores from backend when there is no local image or the tile is stale', async () => {
    mapImageApiMock.getImageParams.mockResolvedValue({
      imagen_principal: {
        sensor: 'Sentinel-2',
        target_date: '2026-03-05',
        visualization: 'true_color',
      },
      imagen_comparacion: null,
    });
    mapImageApiMock.regenerateTile.mockResolvedValue({
      tile_url: 'https://tiles.test/restored',
      target_date: '2026-03-05',
      sensor: 'Sentinel-2',
      visualization: 'true_color',
      visualization_description: 'Natural color',
      collection: 'sentinel-2',
      images_count: 2,
    });

    const { result } = renderHook(() => useSelectedImageListener());

    await waitFor(() => expect(result.current?.tile_url).toBe('https://tiles.test/restored'));
    expect(mapImageApiMock.getImageParams).toHaveBeenCalled();
    expect(mapImageApiMock.regenerateTile).toHaveBeenCalled();
  });
});

describe('getSelectedImageSync', () => {
  const store = new Map<string, string>();

  beforeEach(() => {
    store.clear();
    window.localStorage.getItem = vi.fn((key: string) => store.get(key) ?? null);
    window.localStorage.removeItem = vi.fn((key: string) => {
      store.delete(key);
    });
    isValidSelectedImageMock.mockReturnValue(true);
  });

  it('returns only valid stored images and cleans invalid payloads', () => {
    store.set(STORAGE_KEY, JSON.stringify(baseImage));
    expect(getSelectedImageSync()).toEqual(baseImage);

    isValidSelectedImageMock.mockReturnValue(false);
    expect(getSelectedImageSync()).toBeNull();
    expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);

    store.set(STORAGE_KEY, '{broken');
    expect(getSelectedImageSync()).toBeNull();
  });
});
