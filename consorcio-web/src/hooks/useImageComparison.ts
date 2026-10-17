/**
 * Hook for managing side-by-side image comparison.
 * Allows selecting two satellite images to compare on the map.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  type ImagenMapaParams,
  type MapImageResult,
  type PublicCurrentMapImage,
  mapImageApi,
} from '../lib/api/mapImage';
import { logger } from '../lib/logger';
import { isValidImageComparison } from '../lib/typeGuards';
import { isTileStale, type SatelliteSensorLabel, type SelectedImage } from './useSelectedImage';

const STORAGE_KEY = 'consorcio_image_comparison';

export interface ImageComparison {
  left: SelectedImage;
  right: SelectedImage;
  enabled: boolean;
}

function isComparisonStale(comparison: ImageComparison): boolean {
  return isTileStale(comparison.left) || isTileStale(comparison.right);
}

/**
 * Persist comparison params to backend (fire-and-forget).
 */
function persistComparisonToBackend(comparison: ImageComparison | null): void {
  const payload = comparison
    ? {
        enabled: comparison.enabled,
        left: {
          sensor: comparison.left.sensor,
          target_date: comparison.left.target_date,
          visualization: comparison.left.visualization,
          max_cloud: comparison.left.max_cloud ?? null,
          days_buffer: clampDaysBuffer(comparison.left.days_buffer),
          mode: comparison.left.mode ?? null,
        },
        right: {
          sensor: comparison.right.sensor,
          target_date: comparison.right.target_date,
          visualization: comparison.right.visualization,
          max_cloud: comparison.right.max_cloud ?? null,
          days_buffer: clampDaysBuffer(comparison.right.days_buffer),
          mode: comparison.right.mode ?? null,
        },
      }
    : { enabled: false, left: null, right: null };

  mapImageApi.saveImagenComparacion(payload).catch((err) => {
    logger.warn('Failed to persist comparison params to backend:', err);
  });
}

function clampDaysBuffer(value: number | undefined): number {
  if (typeof value !== 'number' || value < 1) return 10;
  return Math.min(30, value);
}

function selectedFromRegeneratedTile(
  params: ImagenMapaParams,
  tile: MapImageResult,
): SelectedImage {
  return {
    tile_url: tile.tile_url,
    target_date: tile.target_date,
    sensor: tile.sensor as SatelliteSensorLabel,
    visualization: tile.visualization,
    visualization_description: tile.visualization_description,
    collection: tile.collection,
    images_count: tile.images_count,
    days_buffer: params.days_buffer,
    max_cloud: params.max_cloud ?? null,
    mode: params.mode ?? undefined,
    selected_at: new Date().toISOString(),
  };
}

function selectedFromPublicImage(image: PublicCurrentMapImage): SelectedImage {
  return {
    tile_url: image.tile_url,
    target_date: image.target_date,
    sensor: image.sensor as SatelliteSensorLabel,
    visualization: image.visualization,
    visualization_description: image.visualization_description,
    collection: 'server-approved',
    images_count: image.images_count,
    days_buffer: image.days_buffer,
    max_cloud: image.max_cloud,
    mode: image.mode,
    selected_at: new Date().toISOString(),
  };
}

async function restorePublicComparison(): Promise<ImageComparison | null> {
  const response = await mapImageApi.getPublicCurrentComparison();
  if (response.status !== 'available' || !response.left || !response.right) {
    return null;
  }
  return {
    left: selectedFromPublicImage(response.left),
    right: selectedFromPublicImage(response.right),
    enabled: true,
  };
}

async function restoreComparisonFromBackend(): Promise<ImageComparison | null> {
  const saved = await mapImageApi.getImageParams();
  const comparison = saved.imagen_comparacion;
  if (!comparison?.enabled || !comparison.left || !comparison.right) return null;
  const [leftTile, rightTile] = await Promise.all([
    mapImageApi.regenerateTile(comparison.left),
    mapImageApi.regenerateTile(comparison.right),
  ]);
  if (!leftTile.tile_url || !rightTile.tile_url) return null;
  return {
    left: selectedFromRegeneratedTile(comparison.left, leftTile),
    right: selectedFromRegeneratedTile(comparison.right, rightTile),
    enabled: true,
  };
}

/**
 * Hook to manage image comparison state.
 * Stores left and right images for side-by-side comparison.
 */
export function useImageComparison() {
  const [comparison, setComparisonState] = useState<ImageComparison | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load from localStorage on mount; if empty/invalid, rebuild both tiles
  // from the operator-saved backend params (same strategy as the principal image).
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        let hasLocal = false;
        let needsRefresh = false;
        try {
          const stored = localStorage.getItem(STORAGE_KEY);
          if (stored) {
            const parsed = JSON.parse(stored);
            if (isValidImageComparison(parsed)) {
              const comp = parsed as ImageComparison;
              if (!cancelled) setComparisonState(comp);
              hasLocal = true;
              if (isComparisonStale(comp)) {
                needsRefresh = true;
              } else {
                return;
              }
            } else {
              localStorage.removeItem(STORAGE_KEY);
            }
          }
        } catch {
          localStorage.removeItem(STORAGE_KEY);
        }
        if (!hasLocal || needsRefresh) {
          try {
            const restored = await restoreComparisonFromBackend();
            if (cancelled || !restored) return;
            localStorage.setItem(STORAGE_KEY, JSON.stringify(restored));
            setComparisonState(restored);
            window.dispatchEvent(new CustomEvent('imageComparisonChange', { detail: restored }));
          } catch (err) {
            logger.warn('Failed to restore comparison from backend:', err);
            if (!hasLocal) {
              try {
                localStorage.removeItem(STORAGE_KEY);
              } catch {
                /* ignore */
              }
            }
          }
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
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
      persistComparisonToBackend(newComparison);
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
      persistComparisonToBackend(newComparison);
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
      persistComparisonToBackend(newComparison);
      window.dispatchEvent(new CustomEvent('imageComparisonChange', { detail: newComparison }));
      return newComparison;
    });
  }, []);

  // Clear comparison
  const clearComparison = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setComparisonState(null);
    persistComparisonToBackend(null);
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
    let cancelled = false;
    const load = async () => {
      let hasLocal = false;
      let needsRefresh = false;
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored);
          if (isValidImageComparison(parsed)) {
            const comp = parsed as ImageComparison;
            if (!cancelled) setComparison(comp);
            hasLocal = true;
            if (isComparisonStale(comp)) {
              needsRefresh = true;
            } else {
              return;
            }
          } else {
            localStorage.removeItem(STORAGE_KEY);
          }
        }
      } catch {
        localStorage.removeItem(STORAGE_KEY);
      }
      if (!hasLocal || needsRefresh) {
        try {
          const restored = await restorePublicComparison();
          if (!cancelled && restored) setComparison(restored);
        } catch (err) {
          logger.warn('Failed to restore public comparison:', err);
        }
      }
    };
    void load();

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
      cancelled = true;
      window.removeEventListener('imageComparisonChange', handleCustomEvent as EventListener);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  return comparison;
}
