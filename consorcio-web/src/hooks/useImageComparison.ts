/**
 * Hook for managing side-by-side image comparison.
 * Allows selecting two satellite images to compare on the map.
 */

import { useCallback, useEffect, useState } from 'react';
import { isValidImageComparison } from '../lib/typeGuards';
import type { SelectedImage } from './useSelectedImage';

const STORAGE_KEY = 'consorcio_image_comparison';

export interface ImageComparison {
  left: SelectedImage;
  right: SelectedImage;
  enabled: boolean;
}

/**
 * Hook to manage image comparison state.
 * Stores left and right images for side-by-side comparison.
 */
export function useImageComparison() {
  const [comparison, setComparisonState] = useState<ImageComparison | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load from localStorage on mount with validation
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Validate data structure before using
        if (isValidImageComparison(parsed)) {
          setComparisonState(parsed as ImageComparison);
        } else {
          // Invalid data, clean up
          localStorage.removeItem(STORAGE_KEY);
        }
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Set left image
  const setLeftImage = useCallback((image: SelectedImage) => {
    setComparisonState((prev) => {
      const newComparison: ImageComparison = {
        left: image,
        right: prev?.right || image,
        enabled: prev?.enabled ?? true,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newComparison));
      window.dispatchEvent(new CustomEvent('imageComparisonChange', { detail: newComparison }));
      return newComparison;
    });
  }, []);

  // Set right image
  const setRightImage = useCallback((image: SelectedImage) => {
    setComparisonState((prev) => {
      const newComparison: ImageComparison = {
        left: prev?.left || image,
        right: image,
        enabled: prev?.enabled ?? true,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newComparison));
      window.dispatchEvent(new CustomEvent('imageComparisonChange', { detail: newComparison }));
      return newComparison;
    });
  }, []);

  // Enable/disable comparison
  const setEnabled = useCallback((enabled: boolean) => {
    setComparisonState((prev) => {
      if (!prev) return null;
      const newComparison = { ...prev, enabled };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newComparison));
      window.dispatchEvent(new CustomEvent('imageComparisonChange', { detail: newComparison }));
      return newComparison;
    });
  }, []);

  // Clear comparison
  const clearComparison = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setComparisonState(null);
    window.dispatchEvent(new CustomEvent('imageComparisonChange', { detail: null }));
  }, []);

  // Check if both images are set
  const isReady = comparison?.left && comparison?.right;

  return {
    comparison,
    setLeftImage,
    setRightImage,
    setEnabled,
    clearComparison,
    isReady,
    isLoading,
  };
}

/**
 * Hook to listen for comparison changes without ability to modify.
 * Useful for map components that just need to display the comparison.
 */
export function useImageComparisonListener() {
  const [comparison, setComparison] = useState<ImageComparison | null>(null);

  useEffect(() => {
    // Load initial value with validation
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (isValidImageComparison(parsed)) {
          setComparison(parsed as ImageComparison);
        } else {
          localStorage.removeItem(STORAGE_KEY);
        }
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }

    // Listen for custom events (same tab)
    const handleCustomEvent = (event: CustomEvent<ImageComparison | null>) => {
      // Validate even from custom events for extra safety
      if (event.detail === null || isValidImageComparison(event.detail)) {
        setComparison(event.detail as ImageComparison | null);
      }
    };

    // Listen for storage events (other tabs)
    const handleStorageChange = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) {
        if (event.newValue) {
          try {
            const parsed = JSON.parse(event.newValue);
            if (isValidImageComparison(parsed)) {
              setComparison(parsed as ImageComparison);
            } else {
              setComparison(null);
            }
          } catch {
            setComparison(null);
          }
        } else {
          setComparison(null);
        }
      }
    };

    window.addEventListener('imageComparisonChange', handleCustomEvent as EventListener);
    window.addEventListener('storage', handleStorageChange);

    return () => {
      window.removeEventListener('imageComparisonChange', handleCustomEvent as EventListener);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  return comparison;
}
