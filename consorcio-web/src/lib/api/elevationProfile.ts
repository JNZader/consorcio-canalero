/**
 * Longitudinal elevation profile (`POST /api/v2/geo/elevation-profile`).
 *
 * Operator-only. Samples Copernicus GLO-30 (`dem_filled`), never a burned DEM.
 * The payload is a distance/elevation series plus a disclaimer — not a canal
 * invert or a hydraulic section.
 */

import type { LineString } from 'geojson';

import { apiFetch } from './core';

export type ElevationProfilePoint = {
  distance_m: number;
  elevation_m: number | null;
  elevation_mde_ar?: number | null;
  lon?: number;
  lat?: number;
};

export type ElevationProfileResponse = {
  puntos: ElevationProfilePoint[];
  length_m: number;
  min_elevation_m: number | null;
  max_elevation_m: number | null;
  source: string;
  cell_m: number;
  disclaimer: string;
  mde_ar_disclaimer?: string;
};

export function fetchElevationProfile(
  geometry: LineString,
  areaId?: string,
): Promise<ElevationProfileResponse> {
  return apiFetch<ElevationProfileResponse>('/geo/elevation-profile', {
    method: 'POST',
    body: JSON.stringify({ geometry, area_id: areaId ?? null }),
  });
}
