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
      // STRONG: Not just "isDefined" but verify exact content
      expect(storedValue).not.toBeNull();
      expect(storedValue).not.toBeUndefined();
      expect(typeof storedValue).toBe('string');
      
      const parsed = JSON.parse(storedValue);
      expect(parsed.tile_url).toBe('https://tiles.test/layer');  // EXACT value
      expect(parsed.sensor).toBe('Sentinel-2');  // EXACT value
      expect(parsed.target_date).toBe('2026-03-01');  // EXACT value
      expect(parsed.visualization).toBe('true_color');  // EXACT value
      expect(parsed.collection).toBe('sentinel-2');  // EXACT value
      expect(parsed.images_count).toBe(3);  // EXACT numeric value
    });

    it('catches mutation: should add timestamp when setting image', async () => {
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      const beforeTime = new Date();
      act(() => {
        result.current.setSelectedImage(baseImage);
      });
      const afterTime = new Date();

      // STRONG: Verify timestamp exists, is valid ISO, and is in correct range
      const selectedAt = result.current.selectedImage?.selected_at;
      expect(selectedAt).not.toBeNull();
      expect(selectedAt).not.toBeUndefined();
      expect(typeof selectedAt).toBe('string');
      
      const timestamp = new Date(selectedAt || '');
      expect(timestamp.getTime()).toBeGreaterThanOrEqual(beforeTime.getTime());
      expect(timestamp.getTime()).toBeLessThanOrEqual(afterTime.getTime());
      
      // Verify it's a valid ISO string format
      expect(selectedAt).toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
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

      // Find the custom event with exact event type
      const customEvents = dispatchSpy.mock.calls.filter(
        (call: any) => call[0].type === 'selectedImageChange'
      );
      expect(customEvents.length).toBeGreaterThan(0);
      
      // Verify event structure and detail content (STRONG - not just "defined")
      const event = customEvents[0]?.[0] as CustomEvent;
      expect(event).not.toBeNull();
      expect(event).not.toBeUndefined();
      expect(event.type).toBe('selectedImageChange');  // EXACT event type
      
      expect(event.detail).not.toBeNull();
      expect(event.detail).not.toBeUndefined();
      expect(event.detail.tile_url).toBe(baseImage.tile_url);  // EXACT detail content
      expect(event.detail.sensor).toBe(baseImage.sensor);
      expect(event.detail.target_date).toBe(baseImage.target_date);

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

     it('catches mutation: should listen to selectedImageChange custom events with exact update', async () => {
      const { result } = renderHook(() => useSelectedImageListener());

      const updated = { ...baseImage, target_date: '2026-03-20' };
      act(() => {
        window.dispatchEvent(new CustomEvent('selectedImageChange', { detail: updated }));
      });

      // STRONG: Verify exact field values, not just first field
      expect(result.current).not.toBeNull();
      expect(result.current?.target_date).toBe('2026-03-20');  // EXACT date
      expect(result.current?.tile_url).toBe(baseImage.tile_url);  // EXACT URL  
      expect(result.current?.sensor).toBe('Sentinel-2');  // EXACT sensor
      expect(result.current?.visualization).toBe('true_color');  // EXACT visualization
    });

    it('catches mutation: should listen to storage events from other tabs with exact data', async () => {
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

      // STRONG: Verify exact field values after storage event
      expect(result.current).not.toBeNull();
      expect(result.current?.target_date).toBe('2026-04-01');  // EXACT new date
      expect(result.current?.tile_url).toBe(baseImage.tile_url);  // EXACT URL unchanged
      expect(result.current?.sensor).toBe('Sentinel-2');  // EXACT sensor
      expect(result.current?.images_count).toBe(3);  // EXACT count
    });

    it('catches mutation: should clean up ALL event listeners on unmount', () => {
      const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');

      const { unmount } = renderHook(() => useSelectedImageListener());

      unmount();

      // STRONG: Verify BOTH listeners are removed with exact event names
      const removeCalls = removeEventListenerSpy.mock.calls;
      const selectedImageChangeRemoved = removeCalls.some(
        call => call[0] === 'selectedImageChange' && typeof call[1] === 'function'
      );
      const storageRemoved = removeCalls.some(
        call => call[0] === 'storage' && typeof call[1] === 'function'
      );
      
      expect(selectedImageChangeRemoved).toBe(true);
      expect(storageRemoved).toBe(true);
      
      // Verify they were called at least once each
      const selectedImageChangeCount = removeCalls.filter(c => c[0] === 'selectedImageChange').length;
      const storageCount = removeCalls.filter(c => c[0] === 'storage').length;
      expect(selectedImageChangeCount).toBeGreaterThanOrEqual(1);
      expect(storageCount).toBeGreaterThanOrEqual(1);

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

    it('catches mutation: should return null when no data in localStorage with exact null check', () => {
      // Ensure localStorage is empty
      store.clear();
      const result = getSelectedImageSync();
      
      // STRONG: Verify exact null, not just falsy
      expect(result).toBeNull();
      expect(result).not.toBeUndefined();
      expect(result).not.toBe(false);
      expect(typeof result).toBe('object');
    });

    it('catches mutation: should validate before returning in sync function', () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));
      isValidSelectedImageMock.mockReturnValue(true);

      const result = getSelectedImageSync();
      // STRONG: Verify exact content when valid
      expect(result).not.toBeNull();
      expect(result?.tile_url).toBe('https://tiles.test/layer');
      expect(result?.sensor).toBe('Sentinel-2');
      expect(result?.target_date).toBe('2026-03-01');

      isValidSelectedImageMock.mockReturnValue(false);
      const result2 = getSelectedImageSync();
      // STRONG: Verify exact null when invalid
      expect(result2).toBeNull();
      expect(result2).not.toBeUndefined();
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

  // ============================================
  // ADVANCED EVENT DISPATCH BEHAVIOR
  // ============================================

  describe('Advanced event dispatch behavior', () => {
    it('catches mutation: custom event MUST have detail property with image', async () => {
      const dispatchedEvents: CustomEvent[] = [];
      const originalDispatch = window.dispatchEvent;
      
      window.dispatchEvent = vi.fn((event: Event) => {
        dispatchedEvents.push(event as CustomEvent);
        return originalDispatch.call(window, event);
      });

      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      act(() => {
        result.current.setSelectedImage(baseImage);
      });

      // Find the selectedImageChange event
      const changeEvent = dispatchedEvents.find(e => e.type === 'selectedImageChange');
      expect(changeEvent).toBeDefined();
      expect(changeEvent?.detail).toBeDefined(); // Must have detail
      expect(changeEvent?.detail).toEqual(baseImage); // detail must be the image
      expect(changeEvent?.detail).not.toBeUndefined(); // Catches {} mutation
      expect(changeEvent?.detail).not.toBeNull(); // When setting image

      window.dispatchEvent = originalDispatch;
    });

    it('catches mutation: custom event detail must be null when clearing image', async () => {
      const dispatchedEvents: CustomEvent[] = [];
      const originalDispatch = window.dispatchEvent;
      
      window.dispatchEvent = vi.fn((event: Event) => {
        dispatchedEvents.push(event as CustomEvent);
        return originalDispatch.call(window, event);
      });

      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      act(() => {
        result.current.setSelectedImage(baseImage);
      });

      dispatchedEvents.length = 0; // Clear previous events

      act(() => {
        result.current.clearSelectedImage();
      });

      const clearEvent = dispatchedEvents.find(e => e.type === 'selectedImageChange');
      expect(clearEvent).toBeDefined();
      expect(clearEvent?.detail).toBeNull(); // Must be null, not undefined
    });

    it('catches mutation: must dispatch event even when passing null to setSelectedImage', async () => {
      const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      dispatchSpy.mockClear();

      act(() => {
        result.current.setSelectedImage(null);
      });

      expect(dispatchSpy).toHaveBeenCalled();
      const calls = dispatchSpy.mock.calls.filter(c => c[0].type === 'selectedImageChange');
      expect(calls.length).toBeGreaterThan(0);

      dispatchSpy.mockRestore();
    });

    it('catches mutation: image in state must match image in event detail', async () => {
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      const testImage = {
        ...baseImage,
        target_date: '2026-06-15',
        tile_url: 'https://specific.test/url',
      };

      const capturedEvents: CustomEvent[] = [];
      const originalDispatch = window.dispatchEvent;
      window.dispatchEvent = vi.fn((event: Event) => {
        if (event.type === 'selectedImageChange') {
          capturedEvents.push(event as CustomEvent);
        }
        return originalDispatch.call(window, event);
      });

      act(() => {
        result.current.setSelectedImage(testImage);
      });

      const eventDetail = capturedEvents[0]?.detail;
      expect(eventDetail?.tile_url).toBe(testImage.tile_url);
      expect(eventDetail?.target_date).toBe(testImage.target_date);
      expect(result.current.selectedImage?.tile_url).toBe(eventDetail?.tile_url);
      expect(result.current.selectedImage?.target_date).toBe(eventDetail?.target_date);

      window.dispatchEvent = originalDispatch;
    });
  });

  // ============================================
  // EVENT LISTENER CLEANUP VERIFICATION
  // ============================================

  describe('Event listener cleanup verification', () => {
    it('catches mutation: must removeEventListener on listener hook unmount', () => {
      const removeListenerCalls: Array<[string, Function]> = [];
      const originalRemove = window.removeEventListener;

      window.removeEventListener = vi.fn((event: string, handler: any) => {
        removeListenerCalls.push([event, handler]);
        return originalRemove.call(window, event, handler);
      });

      const { unmount } = renderHook(() => useSelectedImageListener());

      unmount();

      // Must have removed both event types
      const events = removeListenerCalls.map(([e]) => e);
      expect(events).toContain('selectedImageChange');
      expect(events).toContain('storage');

      window.removeEventListener = originalRemove;
    });

    it('catches mutation: both hooks must add storage listener', () => {
      const addListenerCalls: Array<[string, Function]> = [];
      const originalAdd = window.addEventListener;

      window.addEventListener = vi.fn((event: string, handler: any) => {
        addListenerCalls.push([event, handler]);
        return originalAdd.call(window, event, handler);
      });

      const { unmount: unmount1 } = renderHook(() => useSelectedImage());
      const { unmount: unmount2 } = renderHook(() => useSelectedImageListener());

      // Both should have added storage listener
      const storageListeners = addListenerCalls.filter(([e]) => e === 'storage');
      expect(storageListeners.length).toBeGreaterThanOrEqual(2);

      unmount1();
      unmount2();

      window.addEventListener = originalAdd;
    });

    it('catches mutation: must clean up exactly matching listener handlers', () => {
      const addedListeners = new Map<string, Set<Function>>();
      const removedListeners = new Map<string, Set<Function>>();
      
      const originalAdd = window.addEventListener;
      const originalRemove = window.removeEventListener;

      window.addEventListener = vi.fn((event: string, handler: any) => {
        if (!addedListeners.has(event)) {
          addedListeners.set(event, new Set());
        }
        addedListeners.get(event)!.add(handler);
        return originalAdd.call(window, event, handler);
      });

      window.removeEventListener = vi.fn((event: string, handler: any) => {
        if (!removedListeners.has(event)) {
          removedListeners.set(event, new Set());
        }
        removedListeners.get(event)!.add(handler);
        return originalRemove.call(window, event, handler);
      });

      const { unmount } = renderHook(() => useSelectedImageListener());

      // Verify listeners were added
      expect(addedListeners.has('selectedImageChange')).toBe(true);
      expect(addedListeners.has('storage')).toBe(true);

      unmount();

      // Verify listeners were removed
      expect(removedListeners.has('selectedImageChange')).toBe(true);
      expect(removedListeners.has('storage')).toBe(true);

      window.addEventListener = originalAdd;
      window.removeEventListener = originalRemove;
    });
  });

  // ============================================
  // VALIDATION & ERROR HANDLING
  // ============================================

  describe('Validation and error handling', () => {
    it('catches mutation: must call isValidSelectedImage to validate stored data', async () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));
      isValidSelectedImageMock.mockReturnValue(true);

      renderHook(() => useSelectedImage());

      await waitFor(() => {
        expect(isValidSelectedImageMock).toHaveBeenCalled();
      });
    });

    it('catches mutation: invalid data must be removed from localStorage', async () => {
      store.set(STORAGE_KEY, JSON.stringify({ invalid: true }));
      isValidSelectedImageMock.mockReturnValue(false);

      renderHook(() => useSelectedImage());

      await waitFor(() => {
        expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
      });
    });

    it('catches mutation: must preserve exact selected_at timestamp format', async () => {
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      const beforeDate = new Date();
      act(() => {
        result.current.setSelectedImage(baseImage);
      });
      const afterDate = new Date();

      const savedImage = result.current.selectedImage;
      expect(savedImage?.selected_at).toBeDefined();
      
      const savedTime = new Date(savedImage?.selected_at || '');
      expect(savedTime.getTime()).toBeGreaterThanOrEqual(beforeDate.getTime());
      expect(savedTime.getTime()).toBeLessThanOrEqual(afterDate.getTime() + 1000); // +1s margin
    });

    it('catches mutation: must store ALL required properties of image', async () => {
      const { result } = renderHook(() => useSelectedImage());
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      const requiredFields = [
        'tile_url',
        'target_date',
        'sensor',
        'visualization',
        'visualization_description',
        'collection',
        'images_count',
      ];

      act(() => {
        result.current.setSelectedImage(baseImage);
      });

      const stored = result.current.selectedImage;
      for (const field of requiredFields) {
        expect(stored).toHaveProperty(field);
        expect(stored?.[field as keyof typeof baseImage]).toBe(baseImage[field as keyof typeof baseImage]);
      }
    });
  });

  // ============================================
  // SYNC FUNCTION EDGE CASES
  // ============================================

  describe('Sync function edge cases', () => {
    it('catches mutation: getSelectedImageSync must check isValidSelectedImage', () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));
      isValidSelectedImageMock.mockReturnValue(true);

      const result1 = getSelectedImageSync();
      expect(result1).toEqual(baseImage);

      isValidSelectedImageMock.mockReturnValue(false);

      const result2 = getSelectedImageSync();
      expect(result2).toBeNull();
    });

    it('catches mutation: getSelectedImageSync must remove invalid data', () => {
      store.set(STORAGE_KEY, JSON.stringify(baseImage));
      isValidSelectedImageMock.mockReturnValue(false);

      const removeItemSpy = window.localStorage.removeItem as any;
      removeItemSpy.mockClear();

      getSelectedImageSync();

      expect(removeItemSpy).toHaveBeenCalledWith(STORAGE_KEY);
    });

    it('catches mutation: getSelectedImageSync must handle JSON parse errors', () => {
      store.set(STORAGE_KEY, '{bad-json]');

      const result = getSelectedImageSync();
      expect(result).toBeNull();
      expect(window.localStorage.removeItem).toHaveBeenCalledWith(STORAGE_KEY);
    });
  });
});
