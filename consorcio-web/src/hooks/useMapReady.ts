/**
 * Legacy hook stubs — kept for API compatibility during MapLibre migration.
 * The Leaflet-based implementation has been removed.
 * These are no-ops since MapLibre GL handles map sizing automatically.
 */

/** No-op. MapLibre GL handles map sizing automatically. */
export function useMapReady() {
  return null;
}

/** No-op component. MapLibre GL handles map sizing automatically. */
export function MapReadyHandler() {
  return null;
}
