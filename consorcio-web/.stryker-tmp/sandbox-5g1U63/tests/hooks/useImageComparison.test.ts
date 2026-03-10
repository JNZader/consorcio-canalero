// @ts-nocheck
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { isValidImageComparisonMock, loggerMock } = vi.hoisted(() => ({
  isValidImageComparisonMock: vi.fn(),
  loggerMock: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}));

vi.mock('../../src/lib/typeGuards', () => ({
  isValidImageComparison: isValidImageComparisonMock,
}));

vi.mock('../../src/lib/logger', () => ({
  logger: loggerMock,
}));

import { useImageComparison, useImageComparisonListener } from '../../src/hooks/useImageComparison';
import type { SelectedImage } from '../../src/hooks/useSelectedImage';

const STORAGE_KEY = 'consorcio_image_comparison';

const baseImage: SelectedImage = {
  tile_url: 'https://tiles.test/layer',
  target_date: '2026-03-01',
  sensor: 'Sentinel-2' as const,
  visualization: 'true_color',
  visualization_description: 'Natural color',
  collection: 'sentinel-2',
  images_count: 3,
  selected_at: '2026-03-01T10:00:00.000Z',
};

const baseImage2: SelectedImage = {
  ...baseImage,
  target_date: '2026-03-15',
  selected_at: '2026-03-15T10:00:00.000Z',
};

describe('useImageComparison', () => {
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

    isValidImageComparisonMock.mockReturnValue(true);
  });

  describe('useImageComparison', () => {
    describe('Initial load', () => {
      it('should load valid comparison from localStorage on mount', async () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        expect(result.current.comparison).toEqual(comparison);
        expect(result.current.isReady).toBeTruthy(); // isReady returns the SelectedImage objects, not boolean
      });

      it('should initialize with loading state then finish loading', async () => {
        const { result } = renderHook(() => useImageComparison());

        // After render completes, isLoading will be false since effect runs synchronously
        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(result.current.comparison).toBeNull();
      });

      it('should clear invalid stored payload', async () => {
        store.set(STORAGE_KEY, JSON.stringify({ bad: true }));
        isValidImageComparisonMock.mockReturnValue(false);

        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        expect(result.current.comparison).toBeNull();
        expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
      });

      it('should handle JSON parse errors', async () => {
        store.set(STORAGE_KEY, '{invalid-json');

        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        expect(result.current.comparison).toBeNull();
        expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
      });
    });

    describe('setLeftImage', () => {
      it('should set left image and maintain right image', async () => {
        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        act(() => {
          result.current.setLeftImage(baseImage);
        });

        expect(result.current.comparison?.left).toEqual(baseImage);
        expect(result.current.comparison?.right).toEqual(baseImage); // defaults to left
        expect(result.current.comparison?.enabled).toBe(true);
      });

      it('should preserve right image when setting left', async () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        const newLeftImage: SelectedImage = {
          ...baseImage,
          target_date: '2026-02-15',
          selected_at: '2026-02-15T10:00:00.000Z',
        };

        act(() => {
          result.current.setLeftImage(newLeftImage);
        });

        expect(result.current.comparison?.left).toEqual(newLeftImage);
        expect(result.current.comparison?.right).toEqual(baseImage2);
      });

      it('should save to localStorage', async () => {
        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        act(() => {
          result.current.setLeftImage(baseImage);
        });

        expect(window.localStorage.setItem).toHaveBeenCalledWith(
          STORAGE_KEY,
          expect.stringContaining('"left"')
        );
      });

      it('should dispatch custom event', async () => {
        const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        act(() => {
          result.current.setLeftImage(baseImage);
        });

        expect(dispatchSpy).toHaveBeenCalledWith(
          expect.objectContaining({ type: 'imageComparisonChange' })
        );
        dispatchSpy.mockRestore();
      });
    });

    describe('setRightImage', () => {
      it('should set right image and maintain left image', async () => {
        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        act(() => {
          result.current.setRightImage(baseImage2);
        });

        expect(result.current.comparison?.right).toEqual(baseImage2);
        expect(result.current.comparison?.left).toEqual(baseImage2); // defaults to right
      });

      it('should preserve left image when setting right', async () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        const newRightImage: SelectedImage = {
          ...baseImage2,
          target_date: '2026-04-01',
          selected_at: '2026-04-01T10:00:00.000Z',
        };

        act(() => {
          result.current.setRightImage(newRightImage);
        });

        expect(result.current.comparison?.left).toEqual(baseImage);
        expect(result.current.comparison?.right).toEqual(newRightImage);
      });

      it('should save to localStorage', async () => {
        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        act(() => {
          result.current.setRightImage(baseImage2);
        });

        expect(window.localStorage.setItem).toHaveBeenCalledWith(
          STORAGE_KEY,
          expect.stringContaining('"right"')
        );
      });
    });

    describe('setEnabled', () => {
      it('should toggle enabled state', async () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        expect(result.current.comparison?.enabled).toBe(true);

        act(() => {
          result.current.setEnabled(false);
        });

        expect(result.current.comparison?.enabled).toBe(false);
        expect(window.localStorage.setItem).toHaveBeenCalled();
      });

      it('should do nothing if no comparison exists', async () => {
        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        act(() => {
          result.current.setEnabled(true);
        });

        expect(result.current.comparison).toBeNull();
      });
    });

    describe('clearComparison', () => {
      it('should clear comparison data', async () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        expect(result.current.comparison).not.toBeNull();

        act(() => {
          result.current.clearComparison();
        });

        expect(result.current.comparison).toBeNull();
      });

      it('should remove from localStorage', async () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        act(() => {
          result.current.clearComparison();
        });

        expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
      });

      it('should dispatch clear event', async () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        act(() => {
          result.current.clearComparison();
        });

        expect(dispatchSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            detail: null,
          })
        );
        dispatchSpy.mockRestore();
      });
    });

    describe('isReady', () => {
      it('should be truthy when both images are set', async () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        expect(result.current.isReady).toBeTruthy();
      });

      it('should be truthy when only left is set (right defaults to left)', async () => {
        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        act(() => {
          result.current.setLeftImage(baseImage);
        });

        expect(result.current.isReady).toBeTruthy();
      });

      it('should be falsy when no images are set', async () => {
        const { result } = renderHook(() => useImageComparison());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        expect(result.current.isReady).toBeFalsy();
      });
    });
  });

  describe('useImageComparisonListener', () => {
    beforeEach(() => {
      isValidImageComparisonMock.mockReturnValue(true);
    });

    describe('Initial load', () => {
      it('should load valid comparison from localStorage', () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const { result } = renderHook(() => useImageComparisonListener());

        expect(result.current).toEqual(comparison);
      });

      it('should start as null when no stored comparison', () => {
        const { result } = renderHook(() => useImageComparisonListener());

        expect(result.current).toBeNull();
      });

      it('should handle invalid stored data', () => {
        store.set(STORAGE_KEY, JSON.stringify({ bad: true }));
        isValidImageComparisonMock.mockReturnValue(false);

        const { result } = renderHook(() => useImageComparisonListener());

        expect(result.current).toBeNull();
      });

      it('should handle JSON parse errors', () => {
        store.set(STORAGE_KEY, '{invalid-json');

        const { result } = renderHook(() => useImageComparisonListener());

        expect(result.current).toBeNull();
      });
    });

    describe('Event listening', () => {
      it('should listen to custom imageComparisonChange events', () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        const { result } = renderHook(() => useImageComparisonListener());

        expect(result.current).toBeNull();

        act(() => {
          window.dispatchEvent(
            new CustomEvent('imageComparisonChange', { detail: comparison })
          );
        });

        expect(result.current).toEqual(comparison);
      });

      it('should listen to storage events from other tabs', () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        const { result } = renderHook(() => useImageComparisonListener());

        act(() => {
          window.dispatchEvent(
            new StorageEvent('storage', {
              key: STORAGE_KEY,
              newValue: JSON.stringify(comparison),
            })
          );
        });

        expect(result.current).toEqual(comparison);
      });

      it('should handle null in storage events (clear from other tab)', () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const { result } = renderHook(() => useImageComparisonListener());

        expect(result.current).not.toBeNull();

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

      it('should validate custom event detail', () => {
        const { result } = renderHook(() => useImageComparisonListener());

        isValidImageComparisonMock.mockReturnValue(false);

        const invalidComparison = { invalid: true };

        act(() => {
          window.dispatchEvent(
            new CustomEvent('imageComparisonChange', { detail: invalidComparison })
          );
        });

        expect(result.current).toBeNull();
      });

      it('should allow null detail in custom events', () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const { result } = renderHook(() => useImageComparisonListener());

        expect(result.current).not.toBeNull();

        act(() => {
          window.dispatchEvent(
            new CustomEvent('imageComparisonChange', { detail: null })
          );
        });

        expect(result.current).toBeNull();
      });

      it('should ignore storage events for other keys', () => {
        const comparison = { left: baseImage, right: baseImage2, enabled: true };
        store.set(STORAGE_KEY, JSON.stringify(comparison));

        const { result } = renderHook(() => useImageComparisonListener());

        expect(result.current).toEqual(comparison);

        act(() => {
          window.dispatchEvent(
            new StorageEvent('storage', {
              key: 'other_key',
              newValue: null,
            })
          );
        });

        expect(result.current).toEqual(comparison);
      });
    });

    describe('Cleanup', () => {
      it('should clean up event listeners on unmount', () => {
        const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');

        const { unmount } = renderHook(() => useImageComparisonListener());

        unmount();

        expect(removeEventListenerSpy).toHaveBeenCalledWith(
          'imageComparisonChange',
          expect.any(Function)
        );
        expect(removeEventListenerSpy).toHaveBeenCalledWith('storage', expect.any(Function));

        removeEventListenerSpy.mockRestore();
      });
    });
  });

  describe('Integration between hooks', () => {
    it('useImageComparisonListener should receive updates from useImageComparison', async () => {
      const { result: writerResult } = renderHook(() => useImageComparison());
      const { result: listenerResult } = renderHook(() => useImageComparisonListener());

      await waitFor(() => expect(writerResult.current.isLoading).toBe(false));

      act(() => {
        writerResult.current.setLeftImage(baseImage);
        writerResult.current.setRightImage(baseImage2);
      });

      expect(listenerResult.current?.left).toEqual(baseImage);
      expect(listenerResult.current?.right).toEqual(baseImage2);
    });
  });
});
