export type ProfileSample = {
  readonly distance_m: number;
  readonly elevation_m: number | null;
  readonly lon?: number;
  readonly lat?: number;
};

export type ProfileExtremaPoint = {
  readonly lon: number;
  readonly lat: number;
  readonly elevation_m: number;
  readonly distance_m: number;
};

export type ProfileRangeStats = {
  readonly length_m: number;
  readonly min_elevation_m: number | null;
  readonly max_elevation_m: number | null;
  readonly delta_m: number | null;
  readonly coordinates: ReadonlyArray<readonly [number, number]>;
  readonly min_point: ProfileExtremaPoint | null;
  readonly max_point: ProfileExtremaPoint | null;
};

export function sliceProfile(
  samples: readonly ProfileSample[],
  distanceA: number,
  distanceB: number,
): ProfileSample[] {
  const lo = Math.min(distanceA, distanceB);
  const hi = Math.max(distanceA, distanceB);
  return samples.filter((sample) => sample.distance_m >= lo && sample.distance_m <= hi);
}

export function profileSliceStats(samples: readonly ProfileSample[]): ProfileRangeStats | null {
  if (samples.length < 2) {
    return null;
  }
  const first = samples[0];
  const last = samples[samples.length - 1];
  if (!first || !last) {
    return null;
  }
  const zs = samples
    .map((sample) => sample.elevation_m)
    .filter((value): value is number => value != null);
  const firstZ = samples.find((sample) => sample.elevation_m != null)?.elevation_m ?? null;
  let lastZ: number | null = null;
  for (let index = samples.length - 1; index >= 0; index -= 1) {
    const value = samples[index]?.elevation_m;
    if (value != null) {
      lastZ = value;
      break;
    }
  }
  const coordinates: Array<readonly [number, number]> = [];
  let minPoint: ProfileExtremaPoint | null = null;
  let maxPoint: ProfileExtremaPoint | null = null;
  for (const sample of samples) {
    if (typeof sample.lon === 'number' && typeof sample.lat === 'number') {
      coordinates.push([sample.lon, sample.lat]);
    }
    if (sample.elevation_m == null || typeof sample.lon !== 'number' || typeof sample.lat !== 'number') {
      continue;
    }
    const point: ProfileExtremaPoint = {
      lon: sample.lon,
      lat: sample.lat,
      elevation_m: sample.elevation_m,
      distance_m: sample.distance_m,
    };
    if (!minPoint || sample.elevation_m < minPoint.elevation_m) {
      minPoint = point;
    }
    if (!maxPoint || sample.elevation_m > maxPoint.elevation_m) {
      maxPoint = point;
    }
  }
  return {
    length_m: last.distance_m - first.distance_m,
    min_elevation_m: zs.length > 0 ? Math.min(...zs) : null,
    max_elevation_m: zs.length > 0 ? Math.max(...zs) : null,
    delta_m: firstZ != null && lastZ != null ? lastZ - firstZ : null,
    coordinates,
    min_point: minPoint,
    max_point: maxPoint,
  };
}
