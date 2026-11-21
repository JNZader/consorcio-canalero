export const GEOLOCATE_MIN_ZOOM = 14;

export function geolocateFlyToOptions(coords: { longitude: number; latitude: number }, currentZoom: number) {
  return {
    center: [coords.longitude, coords.latitude] as [number, number],
    zoom: Math.max(currentZoom, GEOLOCATE_MIN_ZOOM),
    essential: false as const,
  };
}

const HASH_DEBOUNCE_GUARD_MS = 450;

export function requestMapGeolocate(
  map: {
    getZoom: () => number;
    flyTo: (opts: { center: [number, number]; zoom: number; essential: boolean }) => void;
    once?: (event: 'moveend' | 'dragstart', handler: () => void) => void;
    off?: (event: 'moveend' | 'dragstart', handler: () => void) => void;
  } | null,
  geolocation: Pick<Geolocation, 'getCurrentPosition'> | null = typeof navigator === 'undefined'
    ? null
    : navigator.geolocation,
  onGeolocated?: (coords: { longitude: number; latitude: number }) => void,
  onError?: (error: GeolocationPositionError) => void,
): boolean {
  if (!map || !geolocation) return false;
  geolocation.getCurrentPosition(
    (position) => {
      const previousUrl = typeof window === 'undefined' ? '' : window.location.href;
      let userMoved = false;
      let guardTimer: ReturnType<typeof setTimeout> | null = null;
      const restoreUrl = () => {
        if (!userMoved && typeof window !== 'undefined' && previousUrl) {
          window.history.replaceState(window.history.state, '', previousUrl);
        }
      };
      const cancelGuard = () => {
        userMoved = true;
        if (guardTimer !== null) {
          clearTimeout(guardTimer);
          guardTimer = null;
        }
      };
      const onMoveEnd = () => {
        restoreUrl();
        if (guardTimer !== null) clearTimeout(guardTimer);
        // MapLibre `hash: 'v'` writes `#v=` ~300ms after `moveend`; guard past its debounce.
        guardTimer = setTimeout(() => {
          restoreUrl();
          map.off?.('dragstart', cancelGuard);
          guardTimer = null;
        }, HASH_DEBOUNCE_GUARD_MS);
      };
      if ('once' in map && typeof map.once === 'function') {
        map.once('dragstart', cancelGuard);
        map.once('moveend', onMoveEnd);
      }
      map.flyTo(geolocateFlyToOptions(position.coords, map.getZoom()));
      onGeolocated?.({
        longitude: position.coords.longitude,
        latitude: position.coords.latitude,
      });
    },
    (error) => {
      onError?.(error);
    },
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 30_000 },
  );
  return true;
}
