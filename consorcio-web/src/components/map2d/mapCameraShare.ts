/** UX-03: MapLibre `hash: 'v'` owns the camera. Query lat/lng/zoom is leftover. */

export const CAMERA_QUERY_KEYS = ['lat', 'lng', 'zoom'] as const;

export function hasMapLibreCameraHash(hash: string): boolean {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  if (!raw) return false;
  const params = new URLSearchParams(raw.includes('=') ? raw : `v=${raw}`);
  const packed = params.get('v');
  if (!packed) return false;
  const parts = packed.split('/');
  return parts.length >= 3 && parts.every((part) => part.length > 0);
}

export function stripCameraQuery(search: string): string {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  const params = new URLSearchParams(raw);
  for (const key of CAMERA_QUERY_KEYS) params.delete(key);
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

export function shouldApplyQueryCamera(search: string, hash: string): boolean {
  if (hasMapLibreCameraHash(hash)) return false;
  const raw = search.startsWith('?') ? search.slice(1) : search;
  const params = new URLSearchParams(raw);
  const lat = Number.parseFloat(params.get('lat') ?? '');
  const lng = Number.parseFloat(params.get('lng') ?? '');
  return Number.isFinite(lat) && Number.isFinite(lng);
}
