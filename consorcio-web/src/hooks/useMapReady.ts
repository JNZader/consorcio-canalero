/**
 * Hook to fix Leaflet map sizing issues.
 *
 * Leaflet maps often render incorrectly when:
 * - The container size changes after initialization
 * - The map is initialized while hidden or with zero dimensions
 * - React components re-render
 * - SPA navigation occurs (TanStack Router)
 *
 * This hook calls invalidateSize() to recalculate the map size.
 */

import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';

/**
 * Hook that ensures the map renders correctly by calling invalidateSize.
 * Must be used inside a MapContainer component.
 */
export function useMapReady() {
  const map = useMap();
  const hasInitialized = useRef(false);

  useEffect(() => {
    const safeInvalidateSize = () => {
      try {
        const container = map.getContainer?.();
        if (!container || !container.isConnected) return;
        map.invalidateSize();
      } catch {
        // Ignore transient Leaflet errors during unmounts, tab visibility changes,
        // or route transitions where the map container no longer exists.
      }
    };

    // Force immediate invalidation
    safeInvalidateSize();

    // Invalidation schedule for SPA navigation - less aggressive now that we use keys
    const timeouts = [
      setTimeout(() => safeInvalidateSize(), 0),
      setTimeout(() => safeInvalidateSize(), 100),
      setTimeout(() => safeInvalidateSize(), 300),
    ];

    // Use requestAnimationFrame for smoother updates
    let rafId: number;
    const invalidateOnFrame = () => {
      safeInvalidateSize();
      if (!hasInitialized.current) {
        hasInitialized.current = true;
        // One more after initialization
        rafId = requestAnimationFrame(() => safeInvalidateSize());
      }
    };
    rafId = requestAnimationFrame(invalidateOnFrame);

    // Handle window resize
    const handleResize = () => {
      safeInvalidateSize();
    };
    window.addEventListener('resize', handleResize);

    // Handle visibility change (tab switching)
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        safeInvalidateSize();
        setTimeout(() => safeInvalidateSize(), 100);
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Use ResizeObserver for container size changes
    const container = map.getContainer();
    let resizeObserver: ResizeObserver | null = null;
    if (container && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => {
        safeInvalidateSize();
      });
      resizeObserver.observe(container);
    }

    return () => {
      timeouts.forEach(clearTimeout);
      cancelAnimationFrame(rafId);
      window.removeEventListener('resize', handleResize);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      resizeObserver?.disconnect();
    };
  }, [map]);

  return map;
}

/**
 * Component that fixes map sizing issues.
 * Add this as a child of MapContainer.
 */
export function MapReadyHandler() {
  useMapReady();
  return null;
}
