// @ts-nocheck
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

  // ============================================
  // INITIAL LOAD & STATE
  // ============================================

  describe('Initial load and state', () => {
    it('loads valid image from localStorage on mount', async () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));

      const { result } = renderHook(() => useSelectedImage());

      await waitFor(() => expect(result.current.isLoading).toBe(false));
      expect(result.current.selectedImage).toEqual(baseImage);
      expect(result.current.hasSelectedImage).toBe(true);
    });

    it('catches mutation: should set isLoading to exactly false after mount', async () => {
      const { result } = renderHook(() => useSelectedImage());

      await waitFor(() => {
        // Must be exactly false, not just falsy
        expect(result.current.isLoading).toBe(false);
        expect(result.current.isLoading).not.toBe(true);
        expect(typeof result.current.isLoading).toBe('boolean');
      });
    });

    it('catches mutation: should start with null selectedImage when empty', async () => {
      const { result } = renderHook(() => useSelectedImage());

      await waitFor(() => expect(result.current.isLoading).toBe(false));
      expect(result.current.selectedImage).toBeNull();
      expect(result.current.hasSelectedImage).toBe(false);
    });
  });

  // ============================================
  // INVALID DATA HANDLING
  // ============================================

  describe('Invalid data handling', () => {
    it('clears invalid stored payload and handles parse errors', async () => {
      store.set(STORAGE_KEY, JSON.stringify({ bad: true }));
      isValidSelectedImageMock.mockReturnValue(false);

      const { result } = renderHook(() => useSelectedImage());

      await waitFor(() => expect(result.current.isLoading).toBe(false));
      expect(result.current.selectedImage).toBeNull();
      expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
    });

    it('catches mutation: should call logger.error on JSON parse failure', async () => {
      store.set(STORAGE_KEY, '{invalid-json');

      renderHook(() => useSelectedImage());

      await waitFor(() => {
        expect(loggerMock.error).toHaveBeenCalled();
      });
    });

    it('catches mutation: should call logger.warn when validation fails', async () => {
      store.set(STORAGE_KEY, JSON.stringify({ bad: true }));
      isValidSelectedImageMock.mockReturnValue(false);

      renderHook(() => useSelectedImage());

      await waitFor(() => {
        expect(loggerMock.warn).toHaveBeenCalled();
      });
    });

    it('catches mutation: should clear localStorage on JSON parse error', async () => {
      store.set(STORAGE_KEY, '{invalid-json');

      renderHook(() => useSelectedImage());

      await waitFor(() => {
        expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
      });
    });
  });

  // ============================================
  // SET SELECTED IMAGE
  // ============================================

  describe('Setting selected image', () => {
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

    it('catches mutation: should call localStorage.setItem with correct key', async () => {
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      act(() => {
        result.current.setSelectedImage(baseImage);
      });

      expect(window.localStorage.setItem).toHaveBeenCalledWith(
        STORAGE_KEY,
        expect.any(String)
      );
    });

    it('catches mutation: should set exact image data to localStorage', async () => {
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      act(() => {
        result.current.setSelectedImage(baseImage);
      });

      const calls = (window.localStorage.setItem as any).mock.calls;
      const storedValue = calls.find((call: any) => call[0] === STORAGE_KEY)?.[1];
      expect(storedValue).toBeDefined();
      
      const parsed = JSON.parse(storedValue);
      expect(parsed.tile_url).toBe(baseImage.tile_url);
      expect(parsed.sensor).toBe(baseImage.sensor);
      expect(parsed.target_date).toBe(baseImage.target_date);
    });

    it('catches mutation: should add timestamp when setting image', async () => {
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      act(() => {
        result.current.setSelectedImage(baseImage);
      });

      expect(result.current.selectedImage?.selected_at).toBeDefined();
      // Verify it's a valid ISO string
      expect(() => new Date(result.current.selectedImage?.selected_at || '')).not.toThrow();
    });

    it('catches mutation: should update internal state when setSelectedImage called', async () => {
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      expect(result.current.selectedImage).toBeNull();

      act(() => {
        result.current.setSelectedImage(baseImage);
      });

      expect(result.current.selectedImage).not.toBeNull();
      expect(result.current.hasSelectedImage).toBe(true);
    });

    it('catches mutation: should dispatch selectedImageChange custom event with detail', async () => {
      const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      act(() => {
        result.current.setSelectedImage(baseImage);
      });

      // Find the custom event
      const customEvents = dispatchSpy.mock.calls.filter(
        (call: any) => call[0].type === 'selectedImageChange'
      );
      expect(customEvents.length).toBeGreaterThan(0);
      
      // Verify event has detail property
      const event = customEvents[0]?.[0] as CustomEvent;
      expect(event.detail).toBeDefined();
      expect(event.detail).toEqual(baseImage);

      dispatchSpy.mockRestore();
    });

    it('catches mutation: should not set image when passed null', async () => {
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      act(() => {
        result.current.setSelectedImage(baseImage);
      });
      expect(result.current.selectedImage).not.toBeNull();

      act(() => {
        result.current.setSelectedImage(null);
      });

      expect(result.current.selectedImage).toBeNull();
      expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
    });
  });

  // ============================================
  // CLEAR SELECTED IMAGE
  // ============================================

  describe('Clearing selected image', () => {
    it('catches mutation: should call localStorage.removeItem on clear', async () => {
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      act(() => {
        result.current.setSelectedImage(baseImage);
      });

      vi.clearAllMocks();

      act(() => {
        result.current.clearSelectedImage();
      });

      expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
    });

    it('catches mutation: should clear state to null', async () => {
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      act(() => {
        result.current.setSelectedImage(baseImage);
      });

      act(() => {
        result.current.clearSelectedImage();
      });

      expect(result.current.selectedImage).toBeNull();
      expect(result.current.hasSelectedImage).toBe(false);
    });

    it('catches mutation: should dispatch selectedImageChange event on clear', async () => {
      const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      act(() => {
        result.current.setSelectedImage(baseImage);
      });

      dispatchSpy.mockClear();

      act(() => {
        result.current.clearSelectedImage();
      });

      const customEvents = dispatchSpy.mock.calls.filter(
        (call: any) => call[0].type === 'selectedImageChange'
      );
      expect(customEvents.length).toBeGreaterThan(0);

      dispatchSpy.mockRestore();
    });
  });

  // ============================================
  // LISTENER HOOK
  // ============================================

  describe('useSelectedImageListener', () => {
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

    it('catches mutation: should listen to selectedImageChange custom events', async () => {
      const { result } = renderHook(() => useSelectedImageListener());

      const updated = { ...baseImage, target_date: '2026-03-20' };
      act(() => {
        window.dispatchEvent(new CustomEvent('selectedImageChange', { detail: updated }));
      });

      expect(result.current?.target_date).toBe('2026-03-20');
    });

    it('catches mutation: should listen to storage events from other tabs', async () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));
      const { result } = renderHook(() => useSelectedImageListener());

      const newImage = { ...baseImage, target_date: '2026-04-01' };
      act(() => {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: STORAGE_KEY,
            newValue: JSON.stringify(newImage),
          })
        );
      });

      expect(result.current?.target_date).toBe('2026-04-01');
    });

    it('catches mutation: should clean up event listeners on unmount', () => {
      const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');

      const { unmount } = renderHook(() => useSelectedImageListener());

      unmount();

      expect(removeEventListenerSpy).toHaveBeenCalledWith('selectedImageChange', expect.any(Function));
      expect(removeEventListenerSpy).toHaveBeenCalledWith('storage', expect.any(Function));

      removeEventListenerSpy.mockRestore();
    });

    it('catches mutation: should handle null in custom event detail', () => {
      const { result } = renderHook(() => useSelectedImageListener());

      act(() => {
        window.dispatchEvent(new CustomEvent('selectedImageChange', { detail: null }));
      });

      expect(result.current).toBeNull();
    });

    it('catches mutation: should validate data from storage events', () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));
      isValidSelectedImageMock.mockReturnValue(true);

      const { result } = renderHook(() => useSelectedImageListener());
      expect(result.current).toEqual(baseImage);

      // Now send invalid data
      isValidSelectedImageMock.mockReturnValue(false);
      const newImage = { ...baseImage, target_date: '2026-04-05' };
      act(() => {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: STORAGE_KEY,
            newValue: JSON.stringify(newImage),
          })
        );
      });

      expect(result.current).toBeNull();
    });
  });

  // ============================================
  // SYNC FUNCTION
  // ============================================

  describe('getSelectedImageSync', () => {
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

    it('catches mutation: should return null when no data in localStorage', () => {
      expect(getSelectedImageSync()).toBeNull();
    });

    it('catches mutation: should validate before returning', () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));
      isValidSelectedImageMock.mockReturnValue(true);

      const result = getSelectedImageSync();
      expect(result).toEqual(baseImage);

      isValidSelectedImageMock.mockReturnValue(false);
      const result2 = getSelectedImageSync();
      expect(result2).toBeNull();
    });

    it('catches mutation: should clean up invalid data', () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));
      isValidSelectedImageMock.mockReturnValue(false);

      getSelectedImageSync();

      expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
    });

    it('catches mutation: should clean up on JSON parse error', () => {
      store.set(STORAGE_KEY, '{broken');

      getSelectedImageSync();

      expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
    });
  });

  // ============================================
  // STORAGE EVENT HANDLING
  // ============================================

  describe('Storage event handling', () => {
    it('catches mutation: should add storage event listener on mount', () => {
      const addEventListenerSpy = vi.spyOn(window, 'addEventListener');
      
      renderHook(() => useSelectedImage());

      expect(addEventListenerSpy).toHaveBeenCalledWith('storage', expect.any(Function));
      addEventListenerSpy.mockRestore();
    });

    it('catches mutation: should remove storage event listener on unmount', () => {
      const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');

      const { unmount } = renderHook(() => useSelectedImage());

      unmount();

      expect(removeEventListenerSpy).toHaveBeenCalledWith('storage', expect.any(Function));
      removeEventListenerSpy.mockRestore();
    });

    it('catches mutation: should only react to STORAGE_KEY changes', async () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));
      const { result } = renderHook(() => useSelectedImage());

      // Wait for initial load
      await waitFor(() => expect(result.current.isLoading).toBe(false));
      expect(result.current.selectedImage).toEqual(baseImage);
      
      // Store the initial state for comparison
      const initialSelectedImage = result.current.selectedImage;

      // Change a different key with completely different data
      const differentImage = { ...baseImage, target_date: '2026-05-01', tile_url: 'https://different.url' };
      act(() => {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: 'different_key',
            newValue: JSON.stringify(differentImage),
          })
        );
      });

      // State should NOT change from the event about a different key
      expect(result.current.selectedImage).toBe(initialSelectedImage);
      expect(result.current.selectedImage).toEqual(baseImage);
      expect(result.current.selectedImage?.target_date).toBe('2026-03-01');
      expect(result.current.selectedImage?.tile_url).toBe('https://tiles.test/layer');
      expect(result.current.selectedImage?.tile_url).not.toBe('https://different.url');
    });

    it('catches mutation: should clear when storage key is set to null', () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));
      const { result } = renderHook(() => useSelectedImage());

      act(() => {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: STORAGE_KEY,
            newValue: null,
          })
        );
      });

      expect(result.current.selectedImage).toBeNull();
    });

    it('catches mutation: should update state when storage event fires with new value', async () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));
      const { result } = renderHook(() => useSelectedImage());

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      const newImage = { ...baseImage, target_date: '2026-04-01' };
      act(() => {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: STORAGE_KEY,
            newValue: JSON.stringify(newImage),
          })
        );
      });

      expect(result.current.selectedImage?.target_date).toBe('2026-04-01');
    });
  });
});
