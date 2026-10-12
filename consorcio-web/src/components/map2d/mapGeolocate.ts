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
  } | null,
  geolocation: Pick<Geolocation, 'getCurrentPosition'> | null = typeof navigator === 'undefined'
    ? null
    : navigator.geolocation,
): boolean {
  if (!map || !geolocation) return false;
  geolocation.getCurrentPosition(
    (position) => {
      map.flyTo(geolocateFlyToOptions(position.coords, map.getZoom()));
    },
    () => undefined,
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 30_000 },
  );
  return true;
}
