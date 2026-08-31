export const HAZARD_VISIBILITY_SNAPSHOT_VERSION = 1 as const;
export const HAZARD_VISIBILITY_SNAPSHOT_KEY = 'consorcio_hazard_visibility_snapshot';

export const HAZARD_NORMAL_VISIBILITY = {
  flood_risk: false,
  drainage_need: false,
  soil: false,
  canales_relevados: true,
  basins: false,
  precip_normal: false,
} as const;

export interface HazardVisibilitySnapshot {
  readonly version: typeof HAZARD_VISIBILITY_SNAPSHOT_VERSION;
  readonly values: Record<string, boolean>;
}

export type HazardSnapshotStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

let memorySnapshot: HazardVisibilitySnapshot | null = null;

function makeSnapshot(values: Record<string, boolean>): HazardVisibilitySnapshot {
  return { version: HAZARD_VISIBILITY_SNAPSHOT_VERSION, values: { ...values } };
}

export function serializeHazardVisibilitySnapshot(values: Record<string, boolean>): string {
  return JSON.stringify(makeSnapshot(values));
}

export function parseHazardVisibilitySnapshot(raw: string | null): HazardVisibilitySnapshot | null {
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return isHazardVisibilitySnapshot(parsed) ? makeSnapshot(parsed.values) : null;
  } catch {
    return null;
  }
}

function getSessionStorage(): HazardSnapshotStorage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function writeHazardVisibilitySnapshot(
  values: Record<string, boolean>,
  storage: HazardSnapshotStorage | null = getSessionStorage()
): void {
  memorySnapshot = makeSnapshot(values);
  try {
    storage?.setItem(HAZARD_VISIBILITY_SNAPSHOT_KEY, JSON.stringify(memorySnapshot));
  } catch {
    /* same-mount memory fallback */
  }
}

export function readHazardVisibilitySnapshot(
  storage: HazardSnapshotStorage | null = getSessionStorage()
): HazardVisibilitySnapshot | null {
  try {
    if (!storage) return memorySnapshot;
    const raw = storage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY);
    const parsed = parseHazardVisibilitySnapshot(raw);
    if (raw !== null && parsed === null) {
      try {
        storage.removeItem(HAZARD_VISIBILITY_SNAPSHOT_KEY);
      } catch {
        /* ignore denied clear */
      }
      memorySnapshot = null;
      return null;
    }
    if (parsed) memorySnapshot = parsed;
    return parsed ?? memorySnapshot;
  } catch {
    return memorySnapshot;
  }
}

export function clearHazardVisibilitySnapshot(
  storage: HazardSnapshotStorage | null = getSessionStorage()
): void {
  memorySnapshot = null;
  try {
    storage?.removeItem(HAZARD_VISIBILITY_SNAPSHOT_KEY);
  } catch {
    /* ignore denied clear */
  }
}

function isHazardVisibilitySnapshot(value: unknown): value is HazardVisibilitySnapshot {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  if (record.version !== HAZARD_VISIBILITY_SNAPSHOT_VERSION) return false;
  if (typeof record.values !== 'object' || record.values === null || Array.isArray(record.values)) {
    return false;
  }
  return Object.values(record.values as Record<string, unknown>).every(
    (entry) => typeof entry === 'boolean'
  );
}
