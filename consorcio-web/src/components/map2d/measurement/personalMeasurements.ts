import type { LineString, Polygon } from 'geojson';

const KEY = 'cc-personal-measurements';
let memory: PersonalMeasurement[] = [];

export interface PersonalMeasurement {
  readonly id: string;
  readonly kind: 'distance' | 'area';
  readonly geometry: LineString | Polygon;
}

function store(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readPersonalMeasurements(): PersonalMeasurement[] {
  const raw = store()?.getItem(KEY);
  if (!raw) return memory;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    memory = parsed.filter(
      (item): item is PersonalMeasurement =>
        !!item &&
        typeof item === 'object' &&
        typeof (item as PersonalMeasurement).id === 'string' &&
        ((item as PersonalMeasurement).geometry?.type === 'LineString' ||
          (item as PersonalMeasurement).geometry?.type === 'Polygon')
    );
    return memory;
  } catch {
    return memory;
  }
}

export function savePersonalMeasurement(entry: PersonalMeasurement): PersonalMeasurement[] {
  const next = [entry, ...readPersonalMeasurements().filter((item) => item.id !== entry.id)].slice(0, 40);
  memory = next;
  try {
    store()?.setItem(KEY, JSON.stringify(next));
  } catch {
    /* private mode */
  }
  return next;
}
