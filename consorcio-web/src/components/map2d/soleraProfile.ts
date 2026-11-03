export interface SoleraSample {
  readonly distance_m: number;
  readonly elevation_m: number | null;
  readonly solera_m?: number | null;
}

export interface SoleraRow {
  readonly distance_m: number;
  readonly terreno: number;
  readonly solera: number;
  readonly cover_m: number;
}

export type SoleraRead =
  | { readonly ok: true; readonly rows: readonly SoleraRow[] }
  | { readonly ok: false; readonly reason: 'missing' };

/** Terrain versus a surveyed or design invert. Missing invert is not invented. */
export function soleraCover(samples: readonly SoleraSample[]): SoleraRead {
  const rows: SoleraRow[] = [];
  for (const sample of samples) {
    if (sample.elevation_m == null || sample.solera_m == null || !Number.isFinite(sample.solera_m)) {
      continue;
    }
    rows.push({
      distance_m: sample.distance_m,
      terreno: sample.elevation_m,
      solera: sample.solera_m,
      cover_m: sample.elevation_m - sample.solera_m,
    });
  }
  if (rows.length < 2) return { ok: false, reason: 'missing' };
  return { ok: true, rows };
}

export interface SurveyProfile {
  readonly id: string;
  readonly label: string;
  readonly samples: readonly { distance_m: number; elevation_m: number | null }[];
}

/** Two stored relevamientos. There is no second survey until one is supplied. */
export function pairedSurveys(
  current: SurveyProfile | null,
  other: SurveyProfile | null
): { ok: true; left: SurveyProfile; right: SurveyProfile } | { ok: false; reason: 'missing' } {
  if (!current || !other || current.samples.length < 2 || other.samples.length < 2) {
    return { ok: false, reason: 'missing' };
  }
  return { ok: true, left: current, right: other };
}
