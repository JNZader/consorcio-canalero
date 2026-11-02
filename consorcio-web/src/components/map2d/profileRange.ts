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
  readonly mean_elevation_m: number | null;
  readonly median_elevation_m: number | null;
  readonly delta_m: number | null;
  readonly ascent_m: number;
  readonly descent_m: number;
  /** Steepest uphill segment, in percent. Null when no segment has a run. */
  readonly max_up_slope_pct: number | null;
  /** Steepest downhill segment (most negative), in percent. */
  readonly max_down_slope_pct: number | null;
  /** Net slope, (cota final − cota inicial) / longitud, in percent. */
  readonly mean_slope_pct: number | null;
  readonly coordinates: ReadonlyArray<readonly [number, number]>;
  readonly min_point: ProfileExtremaPoint | null;
  readonly max_point: ProfileExtremaPoint | null;
};

export function medianElevation(values: readonly number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[mid] ?? null;
  }
  const lo = sorted[mid - 1];
  const hi = sorted[mid];
  if (lo == null || hi == null) {
    return null;
  }
  return (lo + hi) / 2;
}

function elevationsOf(samples: readonly ProfileSample[]): number[] {
  return samples
    .map((sample) => sample.elevation_m)
    .filter((value): value is number => value != null && Number.isFinite(value));
}

/**
 * Grade of a trace: mean and median elevation, cumulative climb and drop, and
 * slopes. A null sample breaks the segment so a gap is not treated as terrain
 * the path never crosses.
 */
export function profileGrade(samples: readonly ProfileSample[]): {
  readonly mean_elevation_m: number | null;
  readonly median_elevation_m: number | null;
  readonly ascent_m: number;
  readonly descent_m: number;
  readonly max_up_slope_pct: number | null;
  readonly max_down_slope_pct: number | null;
  readonly mean_slope_pct: number | null;
} {
  const zs = elevationsOf(samples);
  const mean = zs.length > 0 ? zs.reduce((sum, value) => sum + value, 0) / zs.length : null;
  let ascent = 0;
  let descent = 0;
  let maxUp: number | null = null;
  let maxDown: number | null = null;
  for (let index = 1; index < samples.length; index += 1) {
    const prev = samples[index - 1];
    const next = samples[index];
    if (!prev || !next || prev.elevation_m == null || next.elevation_m == null) {
      continue;
    }
    const run = next.distance_m - prev.distance_m;
    if (!(run > 0)) {
      continue;
    }
    const rise = next.elevation_m - prev.elevation_m;
    if (rise > 0) {
      ascent += rise;
    } else if (rise < 0) {
      descent += -rise;
    }
    const slope = (rise / run) * 100;
    if (maxUp == null || slope > maxUp) {
      maxUp = slope;
    }
    if (maxDown == null || slope < maxDown) {
      maxDown = slope;
    }
  }
  const firstZ = samples.find((sample) => sample.elevation_m != null)?.elevation_m ?? null;
  let lastZ: number | null = null;
  for (let index = samples.length - 1; index >= 0; index -= 1) {
    const value = samples[index]?.elevation_m;
    if (value != null) {
      lastZ = value;
      break;
    }
  }
  const first = samples[0];
  const last = samples[samples.length - 1];
  const length = first && last ? last.distance_m - first.distance_m : 0;
  const delta = firstZ != null && lastZ != null ? lastZ - firstZ : null;
  return {
    mean_elevation_m: mean,
    median_elevation_m: medianElevation(zs),
    ascent_m: ascent,
    descent_m: descent,
    max_up_slope_pct: maxUp,
    max_down_slope_pct: maxDown,
    mean_slope_pct: delta != null && length > 0 ? (delta / length) * 100 : null,
  };
}

/** Local slope at a sample, percent. Central difference when both neighbours exist. */
export function localSlopePct(samples: readonly ProfileSample[], index: number): number | null {
  const current = samples[index];
  if (!current || current.elevation_m == null) {
    return null;
  }
  const prev = samples[index - 1];
  const next = samples[index + 1];
  const prevOk = prev != null && prev.elevation_m != null && prev.distance_m < current.distance_m;
  const nextOk = next != null && next.elevation_m != null && next.distance_m > current.distance_m;
  if (prevOk && nextOk && prev?.elevation_m != null && next?.elevation_m != null) {
    const run = next.distance_m - prev.distance_m;
    if (!(run > 0)) {
      return null;
    }
    return ((next.elevation_m - prev.elevation_m) / run) * 100;
  }
  if (nextOk && next?.elevation_m != null) {
    const run = next.distance_m - current.distance_m;
    if (!(run > 0)) {
      return null;
    }
    return ((next.elevation_m - current.elevation_m) / run) * 100;
  }
  if (prevOk && prev?.elevation_m != null) {
    const run = current.distance_m - prev.distance_m;
    if (!(run > 0)) {
      return null;
    }
    return ((current.elevation_m - prev.elevation_m) / run) * 100;
  }
  return null;
}

export function sliceProfile(
  samples: readonly ProfileSample[],
  distanceA: number,
  distanceB: number
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
    if (
      sample.elevation_m == null ||
      typeof sample.lon !== 'number' ||
      typeof sample.lat !== 'number'
    ) {
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
  const grade = profileGrade(samples);
  return {
    length_m: last.distance_m - first.distance_m,
    min_elevation_m: zs.length > 0 ? Math.min(...zs) : null,
    max_elevation_m: zs.length > 0 ? Math.max(...zs) : null,
    mean_elevation_m: grade.mean_elevation_m,
    median_elevation_m: grade.median_elevation_m,
    delta_m: firstZ != null && lastZ != null ? lastZ - firstZ : null,
    ascent_m: grade.ascent_m,
    descent_m: grade.descent_m,
    max_up_slope_pct: grade.max_up_slope_pct,
    max_down_slope_pct: grade.max_down_slope_pct,
    mean_slope_pct: grade.mean_slope_pct,
    coordinates,
    min_point: minPoint,
    max_point: maxPoint,
  };
}
