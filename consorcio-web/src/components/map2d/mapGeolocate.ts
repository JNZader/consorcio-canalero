export const GEOLOCATE_MIN_ZOOM = 14;

export function geolocateFlyToOptions(coords: { longitude: number; latitude: number }, currentZoom: number) {
  return {
    center: [coords.longitude, coords.latitude] as [number, number],
    zoom: Math.max(currentZoom, GEOLOCATE_MIN_ZOOM),
    essential: false as const,
  };
}

export function requestMapGeolocate(
  map: {
    getZoom: () => number;
    flyTo: (opts: { center: [number, number]; zoom: number; essential: boolean }) => void;
    once?: (event: 'moveend', handler: () => void) => void;
  } | null,
  geolocation: Pick<Geolocation, 'getCurrentPosition'> | null = typeof navigator === 'undefined'
    ? null
    : navigator.geolocation,
  onGeolocated?: (coords: { longitude: number; latitude: number }) => void,
): boolean {
  if (!map || !geolocation) return false;
  geolocation.getCurrentPosition(
    (position) => {
      const previousUrl = typeof window === 'undefined' ? '' : window.location.href;
      const onMoveEnd = () => {
        if (typeof window !== 'undefined' && previousUrl) {
          window.history.replaceState(window.history.state, '', previousUrl);
        }
      };
      if ('once' in map && typeof map.once === 'function') {
        map.once('moveend', onMoveEnd);
      }
      map.flyTo(geolocateFlyToOptions(position.coords, map.getZoom()));
      onGeolocated?.({
        longitude: position.coords.longitude,
        latitude: position.coords.latitude,
      });
    },
    () => undefined,
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 30_000 },
  );
  return true;
}
