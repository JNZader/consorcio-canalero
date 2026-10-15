/**
 * profileChartRows
 *
 * Recharts rows for the elevation profile.
 *
 * A multi-part trace carries `parte` per point. The parts are chained along the
 * trace, so MOST boundaries are continuous and must NOT break the line: a break
 * at every boundary chopped the profile into as many segments as tramos. A null
 * row is inserted only where the boundary is a real GAP — a branch returning to
 * its junction. With `connectNulls={false}` the line breaks there instead of
 * drawing a straight segment across terrain the road never crosses. The break
 * row keeps the boundary lon/lat, so hovering it still points at the right
 * place on the map.
 */

import distance from '@turf/distance';
import type { ElevationProfilePoint } from '../../lib/api/elevationProfile';

/** Boundary gap, in metres, that still reads as "the trace continues". */
const PART_GAP_M = 25;

/**
 * Whether the boundary between two parts is a real gap. Without coordinates
 * continuity cannot be proven, so the break stays: a spurious break is a
 * cosmetic gap, while a missing one draws a line over terrain the road never
 * crosses.
 */
function isPartGap(
  anterior: ElevationProfilePoint | undefined,
  punto: ElevationProfilePoint
): boolean {
  if (
    anterior?.lon === undefined ||
    anterior.lat === undefined ||
    punto.lon === undefined ||
    punto.lat === undefined
  ) {
    return true;
  }
  return (
    distance([anterior.lon, anterior.lat], [punto.lon, punto.lat], { units: 'meters' }) > PART_GAP_M
  );
}

export type ProfileChartRow = {
  distance_m: number;
  elevation_m: number | null;
  elevation_mde_ar: number | null;
  elevation_aw3d30: number | null;
  elevation_nasadem: number | null;
  lon?: number;
  lat?: number;
};

function rowOf(punto: ElevationProfilePoint): ProfileChartRow {
  return {
    distance_m: punto.distance_m,
    elevation_m: punto.elevation_m,
    elevation_mde_ar: punto.elevation_mde_ar ?? null,
    elevation_aw3d30: punto.elevation_aw3d30 ?? null,
    elevation_nasadem: punto.elevation_nasadem ?? null,
    lon: punto.lon,
    lat: punto.lat,
  };
}

export function buildProfileChartRows(puntos: readonly ElevationProfilePoint[]): ProfileChartRow[] {
  const rows: ProfileChartRow[] = [];
  let parte: number | undefined;
  let anterior: ElevationProfilePoint | undefined;
  for (const punto of puntos) {
    if (
      parte !== undefined &&
      punto.parte !== undefined &&
      punto.parte !== parte &&
      isPartGap(anterior, punto)
    ) {
      rows.push({
        distance_m: punto.distance_m,
        elevation_m: null,
        elevation_mde_ar: null,
        elevation_aw3d30: null,
        elevation_nasadem: null,
        lon: anterior?.lon,
        lat: anterior?.lat,
      });
    }
    rows.push(rowOf(punto));
    parte = punto.parte ?? parte;
    anterior = punto;
  }
  return rows;
}
