import type { Feature, GeoJsonProperties, Geometry, Position } from 'geojson';
import type { ProfileCrossing } from './canalProfile';

export interface CulvertPoint {
  readonly lon: number;
  readonly lat: number;
  readonly label: string;
}

function cuentaOf(props: GeoJsonProperties): string {
  if (!props) return '';
  const record = props as Record<string, unknown>;
  const value = record.Nro_Cuenta ?? record.nro_cuenta ?? record.cuenta;
  return value == null ? '' : String(value).trim();
}

function ringsOf(geometry: Geometry | null | undefined): Position[][] {
  if (!geometry) return [];
  if (geometry.type === 'Polygon') return geometry.coordinates;
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat();
  return [];
}

function cross(
  a: readonly [number, number],
  b: readonly [number, number],
  c: readonly [number, number],
  d: readonly [number, number]
): { lon: number; lat: number } | null {
  const abx = b[0] - a[0];
  const aby = b[1] - a[1];
  const cdx = d[0] - c[0];
  const cdy = d[1] - c[1];
  const denom = abx * cdy - aby * cdx;
  if (Math.abs(denom) < 1e-15) return null;
  const acx = c[0] - a[0];
  const acy = c[1] - a[1];
  const t = (acx * cdy - acy * cdx) / denom;
  const u = (acx * aby - acy * abx) / denom;
  if (t < 0 || t > 1 || u < 0 || u > 1) return null;
  return { lon: a[0] + t * abx, lat: a[1] + t * aby };
}

/** Parcel edges that the profile line actually crosses. Empty when there is no geometry. */
export function parcelBoundaryMarks(
  samples: readonly { lon?: number; lat?: number }[],
  parcels: readonly Feature<Geometry, GeoJsonProperties>[] | null | undefined
): ProfileCrossing[] {
  const line = samples.filter(
    (sample): sample is { lon: number; lat: number } =>
      typeof sample.lon === 'number' && typeof sample.lat === 'number'
  );
  if (line.length < 2 || !parcels || parcels.length === 0) return [];

  let minLon = Infinity;
  let maxLon = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;
  for (const pt of line) {
    if (pt.lon < minLon) minLon = pt.lon;
    if (pt.lon > maxLon) maxLon = pt.lon;
    if (pt.lat < minLat) minLat = pt.lat;
    if (pt.lat > maxLat) maxLat = pt.lat;
  }

  const marks: ProfileCrossing[] = [];
  for (const parcel of parcels) {
    const rings = ringsOf(parcel.geometry);
    if (rings.length === 0) continue;

    let pMinLon = Infinity;
    let pMaxLon = -Infinity;
    let pMinLat = Infinity;
    let pMaxLat = -Infinity;
    for (const ring of rings) {
      for (const pt of ring) {
        if (!pt) continue;
        if (pt[0]! < pMinLon) pMinLon = pt[0]!;
        if (pt[0]! > pMaxLon) pMaxLon = pt[0]!;
        if (pt[1]! < pMinLat) pMinLat = pt[1]!;
        if (pt[1]! > pMaxLat) pMaxLat = pt[1]!;
      }
    }
    if (pMaxLon < minLon || pMinLon > maxLon || pMaxLat < minLat || pMinLat > maxLat) {
      continue;
    }

    const label = cuentaOf(parcel.properties)
      ? `Parcela ${cuentaOf(parcel.properties)}`
      : 'Límite de parcela';
    for (const ring of rings) {
      for (let edge = 1; edge < ring.length; edge += 1) {
        const c = ring[edge - 1];
        const d = ring[edge];
        if (!c || !d || c.length < 2 || d.length < 2) continue;
        for (let step = 1; step < line.length; step += 1) {
          const hit = cross(
            [line[step - 1]!.lon, line[step - 1]!.lat],
            [line[step]!.lon, line[step]!.lat],
            [c[0]!, c[1]!],
            [d[0]!, d[1]!]
          );
          if (hit) marks.push({ ...hit, label });
        }
      }
    }
  }
  return marks;
}

export function culvertPoints(
  collection: { features?: readonly { geometry?: { type?: string; coordinates?: number[] }; properties?: { tipo?: string; titulo?: string } | null }[] } | null | undefined
): { lon: number; lat: number; label: string }[] {
  const points: { lon: number; lat: number; label: string }[] = [];
  for (const feature of collection?.features ?? []) {
    if (feature.properties?.tipo !== 'alcantarilla') continue;
    const coords = feature.geometry?.coordinates;
    if (!coords || coords.length < 2) continue;
    const lon = Number(coords[0]);
    const lat = Number(coords[1]);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    const title = feature.properties.titulo?.trim();
    points.push({ lon, lat, label: title ? `Alcantarilla ${title}` : 'Alcantarilla' });
  }
  return points;
}

export function culvertMarks(
  points: readonly CulvertPoint[] | null | undefined
): ProfileCrossing[] {
  if (!points || points.length === 0) return [];
  return points.map((point) => ({ lon: point.lon, lat: point.lat, label: point.label }));
}
