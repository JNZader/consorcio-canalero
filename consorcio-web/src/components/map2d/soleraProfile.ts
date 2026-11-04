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

export interface SimulatedCanalStats {
  readonly zStart: number;
  readonly zEnd: number;
  readonly deltaZ: number;
  readonly slopePct: number;
  readonly slopePerMil: number;
  readonly maxCut_m: number;
  readonly dMaxCut_m: number;
  readonly minCut_m: number;
  readonly meanCut_m: number;
  readonly orientation: 'digitizado' | 'inverso';
}

export interface SimulatedCanalRow {
  readonly distance_m: number;
  readonly elevation_m: number | null;
  readonly simulatedSolera: number | null;
  readonly simulatedCut_m: number | null;
}

export type SimulatedCanalRead =
  | { readonly ok: true; readonly rows: readonly SimulatedCanalRow[]; readonly stats: SimulatedCanalStats }
  | { readonly ok: false; readonly reason: 'missing' };

/**
 * Simulates a projected canal solera (design invert) across a profile trace.
 * If flowDirection is 'inverso', the upstream start is the last sample and downstream is the first.
 * Connects the endpoints with a continuous gravity slope and computes excavation cuts and fills.
 */
export function simulateCanalSolera(
  samples: readonly { distance_m: number; elevation_m: number | null }[],
  flowDirection?: 'digitizado' | 'inverso' | null
): SimulatedCanalRead {
  if (samples.length < 2) return { ok: false, reason: 'missing' };
  const first = samples.find((s) => s.elevation_m != null && Number.isFinite(s.elevation_m));
  const last = [...samples].reverse().find((s) => s.elevation_m != null && Number.isFinite(s.elevation_m));
  if (!first || !last || first.elevation_m == null || last.elevation_m == null) {
    return { ok: false, reason: 'missing' };
  }
  const span = last.distance_m - first.distance_m;
  if (!(span > 0)) return { ok: false, reason: 'missing' };

  const isInverse = flowDirection === 'inverso';
  const zUpstream = isInverse ? last.elevation_m : first.elevation_m;
  const zDownstream = isInverse ? first.elevation_m : last.elevation_m;
  const slopeAlongDistance = (last.elevation_m - first.elevation_m) / span;

  let maxCut = -Infinity;
  let dMaxCut = first.distance_m;
  let minCut = Infinity;
  let sumCut = 0;
  let countCut = 0;

  const rows: SimulatedCanalRow[] = [];
  for (const sample of samples) {
    if (sample.elevation_m == null || !Number.isFinite(sample.elevation_m)) {
      rows.push({
        distance_m: sample.distance_m,
        elevation_m: null,
        simulatedSolera: null,
        simulatedCut_m: null,
      });
      continue;
    }
    const solera = first.elevation_m + slopeAlongDistance * (sample.distance_m - first.distance_m);
    const cut = sample.elevation_m - solera;
    if (cut > maxCut) {
      maxCut = cut;
      dMaxCut = sample.distance_m;
    }
    if (cut < minCut) {
      minCut = cut;
    }
    sumCut += cut;
    countCut += 1;

    rows.push({
      distance_m: sample.distance_m,
      elevation_m: sample.elevation_m,
      simulatedSolera: solera,
      simulatedCut_m: cut,
    });
  }

  const hydraulicSlopePct = ((zDownstream - zUpstream) / span) * 100;
  const hydraulicSlopePerMil = hydraulicSlopePct * 10;

  return {
    ok: true,
    rows,
    stats: {
      zStart: zUpstream,
      zEnd: zDownstream,
      deltaZ: zDownstream - zUpstream,
      slopePct: hydraulicSlopePct,
      slopePerMil: hydraulicSlopePerMil,
      maxCut_m: maxCut === -Infinity ? 0 : maxCut,
      dMaxCut_m: dMaxCut,
      minCut_m: minCut === Infinity ? 0 : minCut,
      meanCut_m: countCut > 0 ? sumCut / countCut : 0,
      orientation: isInverse ? 'inverso' : 'digitizado',
    },
  };
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
