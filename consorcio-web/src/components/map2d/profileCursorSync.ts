/**
 * Shared cursor between the elevation chart and the line on the map.
 * Distances are metres along the trace. Pixel tests belong to the caller.
 */

export type ProfileCursorSample = {
  readonly distance_m: number;
  readonly lon?: number;
  readonly lat?: number;
};

const EARTH_RADIUS_M = 6_371_000;

export function nearestIndexByDistance(
  samples: readonly { distance_m: number }[],
  distanceM: number
): number | null {
  if (samples.length === 0) {
    return null;
  }
  let best = 0;
  let bestDelta = Infinity;
  for (let index = 0; index < samples.length; index += 1) {
    const delta = Math.abs(samples[index]!.distance_m - distanceM);
    if (delta < bestDelta) {
      best = index;
      bestDelta = delta;
    }
  }
  return best;
}

/** Metres between two WGS84 points. Enough to pick a sample, not a survey. */
export function metersBetween(aLon: number, aLat: number, bLon: number, bLat: number): number {
  const latRad = ((aLat + bLat) / 2) * (Math.PI / 180);
  const dLat = (bLat - aLat) * (Math.PI / 180);
  const dLon = (bLon - aLon) * (Math.PI / 180) * Math.cos(latRad);
  return EARTH_RADIUS_M * Math.hypot(dLat, dLon);
}

export function nearestProfileSample(
  samples: readonly ProfileCursorSample[],
  lon: number,
  lat: number
): { index: number; distance_m: number; metersAway: number } | null {
  let best: { index: number; distance_m: number; metersAway: number } | null = null;
  for (let index = 0; index < samples.length; index += 1) {
    const sample = samples[index];
    if (!sample || sample.lon == null || sample.lat == null) {
      continue;
    }
    const metersAway = metersBetween(lon, lat, sample.lon, sample.lat);
    if (!best || metersAway < best.metersAway) {
      best = { index, distance_m: sample.distance_m, metersAway };
    }
  }
  return best;
}

/**
 * Map a pointer X inside the plot (axis already excluded) to a sample index.
 * `plotLeft` and `plotWidth` are in the same coordinate space as `clientX`.
 */
export function indexFromPlotX(
  clientX: number,
  plotLeft: number,
  plotWidth: number,
  samples: readonly { distance_m: number }[]
): number | null {
  if (samples.length === 0 || !(plotWidth > 0)) {
    return null;
  }
  const start = samples[0]!.distance_m;
  const end = samples[samples.length - 1]!.distance_m;
  const span = end - start;
  const frac = Math.min(1, Math.max(0, (clientX - plotLeft) / plotWidth));
  const distance = span === 0 ? start : start + frac * span;
  return nearestIndexByDistance(samples, distance);
}

export const PROFILE_DOCK_DEFAULT_PX = 280;
export const PROFILE_DOCK_MIN_PX = 220;
export const PROFILE_DOCK_MAX_PX = 420;

export function clampDockHeight(height: number): number {
  return Math.min(PROFILE_DOCK_MAX_PX, Math.max(PROFILE_DOCK_MIN_PX, Math.round(height)));
}
