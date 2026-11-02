/** Paste a point in the consorcio. Decimal or DMS, either axis order. */

export interface MapCoordinate {
  readonly lat: number;
  readonly lon: number;
}

export type CoordinateRead =
  | { readonly ok: true; readonly point: MapCoordinate }
  | { readonly ok: false; readonly reason: 'out-of-bounds' }
  | null;

/** Generous box around the province of Córdoba, not the consorcio polygon. */
export const CORDOBA_BOUNDS = {
  minLat: -35.1,
  maxLat: -29.4,
  minLon: -65.9,
  maxLon: -61.7,
} as const;

export function inCordoba(lat: number, lon: number): boolean {
  return (
    lat >= CORDOBA_BOUNDS.minLat &&
    lat <= CORDOBA_BOUNDS.maxLat &&
    lon >= CORDOBA_BOUNDS.minLon &&
    lon <= CORDOBA_BOUNDS.maxLon
  );
}

function num(raw: string): number {
  return Number(raw.replace(',', '.'));
}

function validLatLon(lat: number, lon: number): boolean {
  return lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}

function chooseOrder(first: number, second: number): CoordinateRead {
  const options = [
    { lat: first, lon: second },
    { lat: second, lon: first },
  ].filter((point) => validLatLon(point.lat, point.lon));
  if (options.length === 0) return null;
  const inside = options.filter((point) => inCordoba(point.lat, point.lon));
  if (inside.length === 0) return { ok: false, reason: 'out-of-bounds' };
  const preferred = inside.find((point) => point.lat === first && point.lon === second);
  return { ok: true, point: preferred ?? inside[0]! };
}

function dmsValue(match: RegExpMatchArray): number | null {
  const degrees = num(match[1] ?? '');
  const minutes = match[2] ? num(match[2]) : 0;
  const seconds = match[3] ? num(match[3]) : 0;
  if (!Number.isFinite(degrees) || !Number.isFinite(minutes) || !Number.isFinite(seconds)) return null;
  const hemisphere = (match[4] ?? '').toUpperCase();
  const negative = hemisphere === 'S' || hemisphere === 'W' || hemisphere === 'O' || degrees < 0;
  const absolute = Math.abs(degrees) + minutes / 60 + seconds / 3600;
  return negative ? -absolute : absolute;
}

const DMS_PART =
  /([+-]?\d+(?:[.,]\d+)?)(?:\s*[°º]\s*(\d+(?:[.,]\d+)?)?(?:\s*['′]\s*(\d+(?:[.,]\d+)?)?\s*["″]?)?)?\s*([NnSsEeOoWw])/;

function parseDms(text: string): CoordinateRead {
  const matches = [...text.matchAll(new RegExp(DMS_PART, 'g'))].filter((match) => match[4]);
  if (matches.length < 2) return null;
  const a = dmsValue(matches[0]!);
  const b = dmsValue(matches[1]!);
  if (a == null || b == null) return null;
  const hemiA = (matches[0]![4] ?? '').toUpperCase();
  const hemiB = (matches[1]![4] ?? '').toUpperCase();
  const aIsLat = hemiA === 'N' || hemiA === 'S';
  const bIsLat = hemiB === 'N' || hemiB === 'S';
  if (aIsLat && !bIsLat) return chooseOrder(a, b);
  if (bIsLat && !aIsLat) return chooseOrder(b, a);
  return chooseOrder(a, b);
}

const DECIMAL = /^\s*(-?\d+(?:[.,]\d+)?)\s*[,;]\s*(-?\d+(?:[.,]\d+)?)\s*$/;
const DECIMAL_SPACE = /^\s*(-?\d+(?:[.,]\d+)?)\s+(-?\d+(?:[.,]\d+)?)\s*$/;

/** Null when the text is not a coordinate. `out-of-bounds` when it is, but not in Córdoba. */
export function parseCoordinateQuery(raw: string): CoordinateRead {
  const text = raw.trim();
  if (!text) return null;
  if (/[°ºNnSsOoWw]/.test(text)) {
    const dms = parseDms(text);
    if (dms) return dms;
  }
  const match = DECIMAL.exec(text) ?? DECIMAL_SPACE.exec(text);
  if (!match) return null;
  const first = num(match[1] ?? '');
  const second = num(match[2] ?? '');
  if (!Number.isFinite(first) || !Number.isFinite(second)) return null;
  return chooseOrder(first, second);
}
