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
  readonly anchor: 'descarga' | 'cabecera';
  readonly depthAtAnchor_m: number;
  readonly isDraining: boolean;
  readonly maxEmbankment_m: number;
  readonly dMaxEmbankment_m: number;
  readonly requiredDeepening_m: number;
}

export interface SimulateCanalOptions {
  readonly flowDirection?: 'digitizado' | 'inverso' | null;
  readonly anchor?: 'descarga' | 'cabecera';
  /** Target excavation cut at anchor point in meters (default 0 or user-specified e.g. 1.2 m) */
  readonly depthAtAnchor_m?: number;
  /** Design hydraulic slope in per mil (e.g. 0.30 ‰). If null/undefined, connects to opposite endpoint */
  readonly designSlopePerMil?: number | null;
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
 * Option B: Configurable anchor point ('descarga' vs 'cabecera'), depth of cut at anchor,
 * and design hydraulic slope (in ‰).
 * Computes cut/fill at every sample and reports whether gravity drainage is continuous
 * or requires an embankment / deepening at the outlet.
 */
export function simulateCanalSolera(
  samples: readonly { distance_m: number; elevation_m: number | null }[],
  flowDirectionOrOptions?: 'digitizado' | 'inverso' | null | SimulateCanalOptions,
  explicitOptions?: SimulateCanalOptions
): SimulatedCanalRead {
  if (samples.length < 2) return { ok: false, reason: 'missing' };
  const first = samples.find((s) => s.elevation_m != null && Number.isFinite(s.elevation_m));
  const last = [...samples].reverse().find((s) => s.elevation_m != null && Number.isFinite(s.elevation_m));
  if (!first || !last || first.elevation_m == null || last.elevation_m == null) {
    return { ok: false, reason: 'missing' };
  }
  const span = last.distance_m - first.distance_m;
  if (!(span > 0)) return { ok: false, reason: 'missing' };

  const options: SimulateCanalOptions =
    typeof flowDirectionOrOptions === 'object' && flowDirectionOrOptions !== null
      ? flowDirectionOrOptions
      : {
          flowDirection: flowDirectionOrOptions,
          ...explicitOptions,
        };

  const isInverse = options.flowDirection === 'inverso';
  const anchor = options.anchor ?? 'descarga';
  const depthAtAnchor = options.depthAtAnchor_m ?? 0;
  const designSlopePerMil = options.designSlopePerMil ?? null;

  // Determine which end is downstream (descarga) and which is upstream (cabecera)
  const isDownstreamAtFirst =
    options.flowDirection === 'inverso' ||
    (options.flowDirection == null && first.elevation_m < last.elevation_m);

  const zGroundDownstream = isDownstreamAtFirst ? first.elevation_m : last.elevation_m;
  const zGroundUpstream = isDownstreamAtFirst ? last.elevation_m : first.elevation_m;

  let zDownstreamSolera: number;
  let zUpstreamSolera: number;

  if (designSlopePerMil != null && Number.isFinite(designSlopePerMil)) {
    const slopeGradient = Math.abs(designSlopePerMil) / 1000;
    if (anchor === 'cabecera') {
      zUpstreamSolera = zGroundUpstream - depthAtAnchor;
      zDownstreamSolera = zUpstreamSolera - slopeGradient * span;
    } else {
      zDownstreamSolera = zGroundDownstream - depthAtAnchor;
      zUpstreamSolera = zDownstreamSolera + slopeGradient * span;
    }
  } else {
    // Mode without fixed slope: connect both endpoints with depthAtAnchor cut
    if (anchor === 'cabecera') {
      zUpstreamSolera = zGroundUpstream - depthAtAnchor;
      zDownstreamSolera = zGroundDownstream - depthAtAnchor;
    } else {
      zDownstreamSolera = zGroundDownstream - depthAtAnchor;
      zUpstreamSolera = zGroundUpstream - depthAtAnchor;
    }
  }

  // Solera slope along distance_m (from first to last sample)
  const soleraSlopeAlongDistance = isDownstreamAtFirst
    ? (zUpstreamSolera - zDownstreamSolera) / span
    : (zDownstreamSolera - zUpstreamSolera) / span;

  const soleraAtFirst = isDownstreamAtFirst ? zDownstreamSolera : zUpstreamSolera;

  let maxCut = -Infinity;
  let dMaxCut = first.distance_m;
  let minCut = Infinity;
  let dMaxEmbankment = first.distance_m;
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
    const solera = soleraAtFirst + soleraSlopeAlongDistance * (sample.distance_m - first.distance_m);
    const cut = sample.elevation_m - solera;
    if (cut > maxCut) {
      maxCut = cut;
      dMaxCut = sample.distance_m;
    }
    if (cut < minCut) {
      minCut = cut;
      dMaxEmbankment = sample.distance_m;
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

  const hydraulicSlopePct = ((zDownstreamSolera - zUpstreamSolera) / span) * 100;
  const hydraulicSlopePerMil = hydraulicSlopePct * 10;
  const hasEmbankment = minCut < -0.05;

  return {
    ok: true,
    rows,
    stats: {
      zStart: zUpstreamSolera,
      zEnd: zDownstreamSolera,
      deltaZ: zDownstreamSolera - zUpstreamSolera,
      slopePct: hydraulicSlopePct,
      slopePerMil: hydraulicSlopePerMil,
      maxCut_m: maxCut === -Infinity ? 0 : maxCut,
      dMaxCut_m: dMaxCut,
      minCut_m: minCut === Infinity ? 0 : minCut,
      meanCut_m: countCut > 0 ? sumCut / countCut : 0,
      orientation: isInverse ? 'inverso' : 'digitizado',
      anchor,
      depthAtAnchor_m: depthAtAnchor,
      isDraining: !hasEmbankment,
      maxEmbankment_m: hasEmbankment ? Math.abs(minCut) : 0,
      dMaxEmbankment_m: dMaxEmbankment,
      requiredDeepening_m: hasEmbankment ? Math.abs(minCut) : 0,
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
