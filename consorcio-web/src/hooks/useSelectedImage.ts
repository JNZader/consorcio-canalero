/**
 * Hook for managing selected satellite image across all map views.
 *
 * Persistence strategy (dual):
 * 1. localStorage — fast, per-browser, used as primary cache
 * 2. Backend (system_settings) — stores PARAMETERS only (not tile URLs)
 *    so any browser can regenerate the tile from GEE on page load
 *
 * GEE tile URLs are TEMPORARY and expire. The backend stores the params
 * (sensor, date, visualization, etc.) and we regenerate the tile on load.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { mapImageApi, type ImagenMapaParams } from '../lib/api/mapImage';
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
 * Extract the backend-persistable params from a SelectedImage.
 * We only store what's needed to regenerate the tile — NOT the tile URL itself.
 */
function toBackendParams(image: SelectedImage): ImagenMapaParams {
  return {
    sensor: image.sensor,
    target_date: image.target_date,
    visualization: image.visualization,
    max_cloud: null, // Not stored in SelectedImage; backend uses default
    days_buffer: 10, // Default; the exact buffer used during search
  };
}

/**
 * Persist image params to backend (fire-and-forget).
 * Failures are logged but do NOT block the UI.
 */
function persistToBackend(image: SelectedImage | null): void {
  if (image) {
    mapImageApi.saveImagenPrincipal(toBackendParams(image)).catch((err) => {
      logger.warn('Failed to persist image params to backend:', err);
    });
  } else {
    // Save null to clear the backend setting
    mapImageApi
      .saveImagenPrincipal({
        sensor: '',
        target_date: '',
        visualization: '',
        max_cloud: null,
        days_buffer: 10,
      })
      .catch(() => {
        // Silently ignore — clearing is best-effort
      });
  }
}

/**
 * Hook to get and set the currently selected satellite image.
 * The image is stored in localStorage so it persists across page navigations.
 * Additionally persists params to the backend for cross-browser/device sync.
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
      persistToBackend(imageWithTimestamp);
    } else {
      localStorage.removeItem(STORAGE_KEY);
      setSelectedImageState(null);
      persistToBackend(null);
    }

    // Dispatch custom event for same-tab updates
    window.dispatchEvent(new CustomEvent('selectedImageChange', { detail: image }));
  }, []);

  // Clear the selected image
  const clearSelectedImage = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setSelectedImageState(null);
    persistToBackend(null);
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

// GEE map IDs expire after ~24–72 h. Regenerate if cached tile is older than this.
const GEE_TILE_MAX_AGE_MS = 6 * 60 * 60 * 1000; // 6 hours

function isTileStale(image: SelectedImage): boolean {
  if (!image.selected_at) return true;
  const age = Date.now() - new Date(image.selected_at).getTime();
  return age > GEE_TILE_MAX_AGE_MS;
}

/**
 * Hook to listen for selected image changes without ability to modify.
 * Useful for map components that just need to display the layer.
 *
 * If localStorage is empty on mount, attempts to fetch saved params from
 * the backend and regenerate the tile URL from GEE.
 * If the cached tile URL is older than GEE_TILE_MAX_AGE_MS, it regenerates
 * from the backend even when localStorage has data (GEE map IDs expire).
 */
export function useSelectedImageListener() {
  const [selectedImage, setSelectedImage] = useState<SelectedImage | null>(null);
  const fetchedFromBackend = useRef(false);

  useEffect(() => {
    // Load initial value with validation
    let hasLocal = false;
    let needsRefresh = false;
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (isValidSelectedImage(parsed)) {
          const image = parsed as SelectedImage;
          if (isTileStale(image)) {
            // Tile URL may be expired — use params for display label but trigger refresh
            needsRefresh = true;
          } else {
            setSelectedImage(image);
            hasLocal = true;
          }
        } else {
          localStorage.removeItem(STORAGE_KEY);
        }
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }

    // If no local image OR tile is stale, regenerate from backend
    if ((!hasLocal || needsRefresh) && !fetchedFromBackend.current) {
      fetchedFromBackend.current = true;
      restoreFromBackend()
        .then((restored) => {
          if (restored) {
            setSelectedImage(restored);
            // Also cache in localStorage for fast future loads
            localStorage.setItem(STORAGE_KEY, JSON.stringify(restored));
            window.dispatchEvent(
              new CustomEvent('selectedImageChange', { detail: restored })
            );
          } else if (needsRefresh) {
            // Backend couldn't regenerate — remove stale entry
            localStorage.removeItem(STORAGE_KEY);
          }
        })
        .catch((err) => {
          logger.warn('Failed to restore image from backend:', err);
          if (needsRefresh) localStorage.removeItem(STORAGE_KEY);
        });
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
 * Fetch saved params from backend and regenerate a fresh tile URL from GEE.
 * Returns a full SelectedImage or null if nothing is saved / regeneration fails.
 */
async function restoreFromBackend(): Promise<SelectedImage | null> {
  try {
    const response = await mapImageApi.getImageParams();
    const params = response.imagen_principal;

    if (!params || !params.sensor || !params.target_date) {
      return null;
    }

    // Regenerate the tile URL by calling the GEE imagery endpoint
    const result = await mapImageApi.regenerateTile(params);

    return {
      tile_url: result.tile_url,
      target_date: result.target_date,
      sensor: result.sensor as 'Sentinel-1' | 'Sentinel-2',
      visualization: result.visualization,
      visualization_description: result.visualization_description,
      collection: result.collection,
      images_count: result.images_count,
      selected_at: new Date().toISOString(),
    };
  } catch (err) {
    logger.warn('Could not restore image from backend:', err);
    return null;
  }
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
