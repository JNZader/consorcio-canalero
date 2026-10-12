import type { Feature, LineString } from 'geojson';
import length from '@turf/length';

function displayName(feature: Feature, fallback = 'Elemento'): string {
  const props = (feature.properties as Record<string, unknown> | null) ?? {};
  const raw =
    props.nombre ??
    props.name ??
    props.rtn ??
    props.designacion ??
    props.nro_cuenta ??
    props.cuenta ??
    null;
  const title = raw === null || raw === undefined ? '' : String(raw).trim();
  return title.length > 0 ? title : fallback;
}

export interface IdentifyChip {
  readonly key: string;
  readonly label: string;
  readonly count: number;
  readonly indices: readonly number[];
}

export interface IdentifyTramoRow {
  readonly index: number;
  readonly label: string;
}

export function groupIdentifyChips(features: readonly Feature[]): IdentifyChip[] {
  const groups = new Map<string, number[]>();
  features.forEach((feature, index) => {
    const name = displayName(feature);
    const current = groups.get(name);
    if (current) current.push(index);
    else groups.set(name, [index]);
  });
  return [...groups.entries()].map(([name, indices]) => ({
    key: name,
    label: indices.length > 1 ? `${name} ×${indices.length}` : name,
    count: indices.length,
    indices,
  }));
}

export function shouldHideDuplicateChips(chips: readonly IdentifyChip[], featureCount: number): boolean {
  return chips.length === 1 && chips[0].count === featureCount && featureCount > 1;
}

function lineKm(feature: Feature): number | null {
  if (feature.geometry?.type !== 'LineString') return null;
  const metres = length(feature as Feature<LineString>, { units: 'meters' });
  if (!Number.isFinite(metres) || metres <= 0) return null;
  return metres / 1000;
}

export function identifyTramoRows(features: readonly Feature[]): IdentifyTramoRow[] {
  return features.map((feature, index) => {
    const km = lineKm(feature);
    const kmPart = km == null ? '' : ` · ${km.toFixed(2)} km`;
    return { index, label: `Tramo ${index + 1}${kmPart}` };
  });
}
