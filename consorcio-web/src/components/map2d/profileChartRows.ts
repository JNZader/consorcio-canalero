/**
 * profileChartRows
 *
 * Recharts rows for the elevation profile.
 *
 * A multi-part trace carries `parte` per point. Between two parts the road
 * jumps, so a null row is inserted at the boundary: with `connectNulls={false}`
 * the line breaks there instead of drawing a straight segment across terrain the
 * road never crosses. The break row keeps the boundary lon/lat, so hovering it
 * still points at the right place on the map.
 */

import type { ElevationProfilePoint } from '../../lib/api/elevationProfile';

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
    if (parte !== undefined && punto.parte !== undefined && punto.parte !== parte) {
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
