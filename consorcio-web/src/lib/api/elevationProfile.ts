/**
 * Longitudinal elevation profile (`POST /api/v2/geo/elevation-profile`).
 *
 * Operator-only. Samples Copernicus GLO-30 (`dem_filled`), never a burned DEM.
 * The payload is a distance/elevation series plus a disclaimer — not a canal
 * invert or a hydraulic section.
 */

import type { LineString, MultiLineString } from 'geojson';

import { apiFetch } from './core';

export type ElevationProfilePoint = {
  distance_m: number;
  elevation_m: number | null;
  elevation_mde_ar?: number | null;
  elevation_aw3d30?: number | null;
  elevation_nasadem?: number | null;
  lon?: number;
  lat?: number;
  /** Part index on a multi-part trace. Absent on a single LineString, so the
   * chart draws one unbroken line exactly as before. */
  parte?: number;
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
  aw3d30_disclaimer?: string;
  nasadem_disclaimer?: string;
  /** `hit` when the row came from `elevation_profile_cache`; `miss` when it was
   * computed now. Additive: the series is identical either way. */
  cache?: 'hit' | 'miss';
  /** Part count on a multi-part trace; absent for a single LineString. */
  partes?: number;
};

const PUBLIC_ELEVATION_PATH = '/public/map/elevation-profile';
const OPERATOR_ELEVATION_PATH = '/geo/elevation-profile';

export function fetchElevationProfile(
  geometry: LineString | MultiLineString,
  areaId?: string,
  compareDems = false
): Promise<ElevationProfileResponse> {
  if (!compareDems) {
    // Anonymous route: local DEM only (GLO-30 + MDE-Ar). skipAuth keeps the
    // public profile out of the auth-expiry flow for visitors with a stale
    // token — the endpoint needs no session at all.
    return apiFetch<ElevationProfileResponse>(PUBLIC_ELEVATION_PATH, {
      method: 'POST',
      skipAuth: true,
      body: JSON.stringify({ geometry, area_id: areaId ?? null }),
    });
  }
  // AW3D30/NASADEM cost GEE round-trips; that stays operator-only.
  return apiFetch<ElevationProfileResponse>(OPERATOR_ELEVATION_PATH, {
    method: 'POST',
    body: JSON.stringify({
      geometry,
      area_id: areaId ?? null,
      compare_dems: true,
    }),
  });
}
