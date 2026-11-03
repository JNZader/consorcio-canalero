import type { LineString } from 'geojson';
import type { ProfileSample } from './profileRange';

/** MapLibre / Mapbox terrain-RGB height, metres. */
export function terrainRgbMeters(red: number, green: number, blue: number): number {
  return -10000 + (red * 256 * 256 + green * 256 + blue) * 0.1;
}

export function tilePixel(
  lon: number,
  lat: number,
  zoom: number
): { x: number; y: number; px: number; py: number } {
  const n = 2 ** zoom;
  const gx = ((lon + 180) / 360) * n;
  const latRad = (lat * Math.PI) / 180;
  const gy = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
  const x = Math.floor(gx);
  const y = Math.floor(gy);
  return { x, y, px: Math.floor((gx - x) * 256), py: Math.floor((gy - y) * 256) };
}

export interface CoarseReader {
  read(x: number, y: number, px: number, py: number): Promise<{ r: number; g: number; b: number } | null>;
}

export function terrainTileReader(template: string, zoom = 12): CoarseReader {
  const cache = new Map<string, Uint8ClampedArray | null>();
  return {
    async read(x, y, px, py) {
      const key = `${zoom}:${x}:${y}`;
      if (!cache.has(key)) {
        cache.set(key, await loadTerrainTile(template, zoom, x, y));
      }
      const data = cache.get(key);
      if (!data) return null;
      const offset = (py * 256 + px) * 4;
      return { r: data[offset] ?? 0, g: data[offset + 1] ?? 0, b: data[offset + 2] ?? 0 };
    },
  };
}

async function loadTerrainTile(
  template: string,
  zoom: number,
  x: number,
  y: number
): Promise<Uint8ClampedArray | null> {
  if (typeof document === 'undefined') return null;
  const url = template.replace('{z}', String(zoom)).replace('{x}', String(x)).replace('{y}', String(y));
  try {
    const response = await fetch(url);
    if (!response.ok) return null;
    const blob = await response.blob();
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 256;
    const context = canvas.getContext('2d');
    if (!context) return null;
    context.drawImage(bitmap, 0, 0);
    return context.getImageData(0, 0, 256, 256).data;
  } catch {
    return null;
  }
}

/** A few vertices, decoded from the client DEM. The finished line still asks the server. */
export async function coarseProfile(
  line: LineString,
  reader: CoarseReader,
  zoom = 12
): Promise<ProfileSample[]> {
  const coords = line.coordinates.filter((pair) => pair.length >= 2);
  if (coords.length < 2) return [];
  const rows: ProfileSample[] = [];
  let distance = 0;
  for (let index = 0; index < coords.length; index += 1) {
    const lon = coords[index]![0]!;
    const lat = coords[index]![1]!;
    if (index > 0) {
      const prev = coords[index - 1]!;
      const dx = (lon - prev[0]!) * 111_320 * Math.cos((lat * Math.PI) / 180);
      const dy = (lat - prev[1]!) * 110_540;
      distance += Math.hypot(dx, dy);
    }
    const tile = tilePixel(lon, lat, zoom);
    const pixel = await reader.read(tile.x, tile.y, tile.px, tile.py);
    rows.push({
      distance_m: distance,
      elevation_m: pixel ? terrainRgbMeters(pixel.r, pixel.g, pixel.b) : null,
      lon,
      lat,
    });
  }
  return rows;
}
