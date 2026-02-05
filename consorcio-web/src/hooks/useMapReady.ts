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
    // Force immediate invalidation
    map.invalidateSize();

    // Invalidation schedule for SPA navigation - less aggressive now that we use keys
    const timeouts = [
      setTimeout(() => map.invalidateSize(), 0),
      setTimeout(() => map.invalidateSize(), 100),
      setTimeout(() => map.invalidateSize(), 300),
    ];

    // Use requestAnimationFrame for smoother updates
    let rafId: number;
    const invalidateOnFrame = () => {
      map.invalidateSize();
      if (!hasInitialized.current) {
        hasInitialized.current = true;
        // One more after initialization
        rafId = requestAnimationFrame(() => map.invalidateSize());
      }
    };
    rafId = requestAnimationFrame(invalidateOnFrame);

    // Handle window resize
    const handleResize = () => {
      map.invalidateSize();
    };
    window.addEventListener('resize', handleResize);

    // Handle visibility change (tab switching)
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        map.invalidateSize();
        setTimeout(() => map.invalidateSize(), 100);
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Use ResizeObserver for container size changes
    const container = map.getContainer();
    let resizeObserver: ResizeObserver | null = null;
    if (container && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => {
        map.invalidateSize();
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
