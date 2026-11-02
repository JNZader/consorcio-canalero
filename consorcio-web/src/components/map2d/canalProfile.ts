/**
 * Canal reading of an elevation profile.
 *
 * The KMZ canals do not carry a surveyed drainage bearing. The digitized
 * order is the flow, unless the feature says `sentido_flujo: 'inverso'`.
 * A positive slope along that flow is water climbing. A slope flatter than
 * the sediment threshold can drop silt.
 */

import type { RoadFlowCrossingsResponse } from '../../lib/api/roadFlow';
import { nearestProfileSample } from './profileCursorSync';

export type FlowSense = 'digitizado' | 'inverso';

export type SlopeThresholds = {
  /** Absolute slope below this (percent) is a sediment risk. */
  readonly sedimentPct: number;
  /** Uphill along the flow, steeper than this (percent), is against drainage. */
  readonly adversePct: number;
};

export const DEFAULT_SLOPE_THRESHOLDS: SlopeThresholds = {
  sedimentPct: 0.1,
  adversePct: 0.05,
};

export type CanalSlopeNote = {
  readonly kind: 'adverse' | 'sediment';
  readonly from_m: number;
  readonly to_m: number;
  /** Signed slope along the flow, percent. Positive climbs. */
  readonly slope_pct: number;
};

type Sample = {
  readonly distance_m: number;
  readonly elevation_m: number | null;
};

export function canalSlopeNotes(
  samples: readonly Sample[],
  flow: FlowSense,
  thresholds: SlopeThresholds = DEFAULT_SLOPE_THRESHOLDS
): CanalSlopeNote[] {
  const raw: CanalSlopeNote[] = [];
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
    const along = ((next.elevation_m - prev.elevation_m) / run) * 100;
    const flowSlope = flow === 'inverso' ? -along : along;
    if (flowSlope > thresholds.adversePct) {
      raw.push({
        kind: 'adverse',
        from_m: prev.distance_m,
        to_m: next.distance_m,
        slope_pct: flowSlope,
      });
    } else if (Math.abs(flowSlope) < thresholds.sedimentPct) {
      raw.push({
        kind: 'sediment',
        from_m: prev.distance_m,
        to_m: next.distance_m,
        slope_pct: flowSlope,
      });
    }
  }
  return mergeAdjacent(raw);
}

function mergeAdjacent(notes: readonly CanalSlopeNote[]): CanalSlopeNote[] {
  const merged: CanalSlopeNote[] = [];
  for (const note of notes) {
    const last = merged[merged.length - 1];
    if (last && last.kind === note.kind && last.to_m === note.from_m) {
      merged[merged.length - 1] = {
        kind: last.kind,
        from_m: last.from_m,
        to_m: note.to_m,
        slope_pct:
          note.kind === 'adverse' ? Math.max(last.slope_pct, note.slope_pct) : note.slope_pct,
      };
      continue;
    }
    merged.push(note);
  }
  return merged;
}

export type ProfileCrossing = {
  readonly lon: number;
  readonly lat: number;
  readonly label: string;
};

export function crossingKindLabel(tipo: string | null | undefined): string {
  if (tipo === 'flujo_natural') return 'Cruce de camino';
  if (tipo === 'canal') return 'Cruce de canal';
  if (tipo === 'conduccion') return 'Conducción';
  return 'Cruce';
}

/** Road, canal and conveyance crossings already computed for the map. */
export function marksFromRoadFlow(data: RoadFlowCrossingsResponse | undefined): ProfileCrossing[] {
  const marks: ProfileCrossing[] = [];
  for (const feature of data?.features.features ?? []) {
    const coords = feature.geometry?.coordinates;
    if (!coords || coords.length < 2) {
      continue;
    }
    const lon = Number(coords[0]);
    const lat = Number(coords[1]);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
      continue;
    }
    marks.push({ lon, lat, label: crossingKindLabel(feature.properties?.tipo) });
  }
  return marks;
}

export function crossingsOnProfile(
  samples: readonly { distance_m: number; lon?: number; lat?: number }[],
  crossings: readonly ProfileCrossing[],
  maxMeters = 35
): { distance_m: number; label: string }[] {
  const hits: { distance_m: number; label: string }[] = [];
  for (const crossing of crossings) {
    const nearest = nearestProfileSample(samples, crossing.lon, crossing.lat);
    if (nearest && nearest.metersAway <= maxMeters) {
      hits.push({ distance_m: nearest.distance_m, label: crossing.label });
    }
  }
  hits.sort((a, b) => a.distance_m - b.distance_m);
  return hits;
}
