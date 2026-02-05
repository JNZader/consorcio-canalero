/**
 * Hook for managing selected satellite image across all map views.
 * Uses localStorage to persist the selection between page navigations.
 */

import { useCallback, useEffect, useState } from 'react';
import { logger } from '../lib/logger';
import { isValidSelectedImage } from '../lib/typeGuards';

const STORAGE_KEY = 'consorcio_selected_image';

export interface SelectedImage {
  tile_url: string;
  target_date: string;
  sensor: 'Sentinel-1' | 'Sentinel-2';
  visualization: string;
  visualization_description: string;
  collection: string;
  images_count: number;
  flood_info?: {
    id: string;
    name: string;
    description: string;
    severity: string;
  };
  selected_at: string; // ISO timestamp when selected
}

/**
 * Hook to get and set the currently selected satellite image.
 * The image is stored in localStorage so it persists across page navigations.
 */
export function useSelectedImage() {
  const [selectedImage, setSelectedImageState] = useState<SelectedImage | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Validate data structure before using
        if (isValidSelectedImage(parsed)) {
          setSelectedImageState(parsed as SelectedImage);
        } else {
          logger.warn('Invalid selected image data in localStorage, clearing');
          localStorage.removeItem(STORAGE_KEY);
        }
      }
    } catch (error) {
      logger.error('Error loading selected image from localStorage:', error);
      localStorage.removeItem(STORAGE_KEY);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Listen for changes from other tabs/windows
  useEffect(() => {
    const handleStorageChange = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) {
        if (event.newValue) {
          try {
            const parsed = JSON.parse(event.newValue);
            // Validate data structure before using
            if (isValidSelectedImage(parsed)) {
              setSelectedImageState(parsed as SelectedImage);
            } else {
              setSelectedImageState(null);
            }
          } catch {
            setSelectedImageState(null);
          }
        } else {
          setSelectedImageState(null);
        }
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  // Set the selected image
  const setSelectedImage = useCallback((image: SelectedImage | null) => {
    if (image) {
      const imageWithTimestamp = {
        ...image,
        selected_at: new Date().toISOString(),
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(imageWithTimestamp));
      setSelectedImageState(imageWithTimestamp);
    } else {
      localStorage.removeItem(STORAGE_KEY);
      setSelectedImageState(null);
    }

    // Dispatch custom event for same-tab updates
    window.dispatchEvent(new CustomEvent('selectedImageChange', { detail: image }));
  }, []);

  // Clear the selected image
  const clearSelectedImage = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setSelectedImageState(null);
    window.dispatchEvent(new CustomEvent('selectedImageChange', { detail: null }));
  }, []);

  // Check if an image is currently selected
  const hasSelectedImage = selectedImage !== null;

  return {
    selectedImage,
    setSelectedImage,
    clearSelectedImage,
    hasSelectedImage,
    isLoading,
  };
}

/**
 * Hook to listen for selected image changes without ability to modify.
 * Useful for map components that just need to display the layer.
 */
export function useSelectedImageListener() {
  const [selectedImage, setSelectedImage] = useState<SelectedImage | null>(null);

  useEffect(() => {
    // Load initial value with validation
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (isValidSelectedImage(parsed)) {
          setSelectedImage(parsed as SelectedImage);
        } else {
          localStorage.removeItem(STORAGE_KEY);
        }
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }

    // Listen for custom events (same tab)
    const handleCustomEvent = (event: CustomEvent<SelectedImage | null>) => {
      // Custom events come from our own code, but validate anyway
      if (event.detail === null || isValidSelectedImage(event.detail)) {
        setSelectedImage(event.detail as SelectedImage | null);
      }
    };

    // Listen for storage events (other tabs)
    const handleStorageChange = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) {
        if (event.newValue) {
          try {
            const parsed = JSON.parse(event.newValue);
            if (isValidSelectedImage(parsed)) {
              setSelectedImage(parsed as SelectedImage);
            } else {
              setSelectedImage(null);
            }
          } catch {
            setSelectedImage(null);
          }
        } else {
          setSelectedImage(null);
        }
      }
    };

    window.addEventListener('selectedImageChange', handleCustomEvent as EventListener);
    window.addEventListener('storage', handleStorageChange);

    return () => {
      window.removeEventListener('selectedImageChange', handleCustomEvent as EventListener);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  return selectedImage;
}

/**
 * Get selected image synchronously (for non-React contexts).
 * Validates the data before returning to prevent XSS attacks.
 */
export function getSelectedImageSync(): SelectedImage | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return null;

    const parsed = JSON.parse(stored);
    if (isValidSelectedImage(parsed)) {
      return parsed as SelectedImage;
    }

    // Invalid data, clean up
    localStorage.removeItem(STORAGE_KEY);
    return null;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}
