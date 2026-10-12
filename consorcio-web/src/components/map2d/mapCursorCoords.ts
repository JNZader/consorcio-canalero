export interface MapCursorCoords {
  lng: number;
  lat: number;
}

export function formatMapCursorCoords(coords: MapCursorCoords | null, digits = 5): string {
  if (!coords) return '—';
  const latHem = coords.lat >= 0 ? 'N' : 'S';
  const lngHem = coords.lng >= 0 ? 'E' : 'O';
  return `${Math.abs(coords.lat).toFixed(digits)}° ${latHem}  ${Math.abs(coords.lng).toFixed(digits)}° ${lngHem}`;
}

export function coordsFromLngLat(lngLat: { lng: number; lat: number } | null | undefined): MapCursorCoords | null {
  if (!lngLat) return null;
  if (!Number.isFinite(lngLat.lng) || !Number.isFinite(lngLat.lat)) return null;
  if (lngLat.lat < -90 || lngLat.lat > 90) return null;
  if (lngLat.lng < -180 || lngLat.lng > 180) return null;
  return { lng: lngLat.lng, lat: lngLat.lat };
}
