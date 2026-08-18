/**
 * hazardVisibilitySnapshot.ts
 *
 * Per-tab, non-persistent (sessionStorage) snapshot of the pre-hazard vector
 * visibility stack.
 *
 * WHY sessionStorage (and NOT localStorage):
 * The product forbids remembering hazard UI state across reloads, but it DOES
 * need the pre-hazard visibility that was captured at the moment hazard mode
 * turned on to survive a reload *in the same tab* — otherwise disabling hazard
 * after a reload would restore the canonical hazard stack instead of the
 * user's prior map. sessionStorage is scoped to the tab: it survives
 * reload/reload-in-the-same-tab, evaporates on tab close, and never touches the
 * hazard UI store's localStorage persistence. A shared `?hazard=1` link opened
 * in a NEW tab therefore starts with no snapshot and falls back to documented
 * normal defaults (never inheriting another tab's pre-hazard state).
 *
 * The snapshot is versioned: a schema/version bump invalidates any previously
 * stored blob, which is then cleared and treated as absent.
 */

export const HAZARD_VISIBILITY_SNAPSHOT_VERSION = 1;

const SNAPSHOT_STORAGE_KEY = `cc-hazard-visibility-v${HAZARD_VISIBILITY_SNAPSHOT_VERSION}`;

export interface HazardVisibilitySnapshot {
  readonly version: number;
  readonly values: Record<string, boolean>;
}

type SafeStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null;

/**
 * Returns sessionStorage, or null when it is unavailable (SSR, privacy mode,
 * sandboxed iframe, CSP-blocked storage). A probe write confirms it is actually
 * usable — some environments expose the object but throw on access.
 */
function getSafeSessionStorage(): SafeStorage {
  try {
    if (typeof sessionStorage === 'undefined' || sessionStorage === null) {
      return null;
    }
    const probe = '__cc_hvs_probe__';
    sessionStorage.setItem(probe, '1');
    sessionStorage.removeItem(probe);
    return sessionStorage;
  } catch {
    return null;
  }
}

function isHazardVisibilitySnapshot(value: unknown): value is HazardVisibilitySnapshot {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  // Wrong version (or missing) → treat as stale and clear it.
  if (record.version !== HAZARD_VISIBILITY_SNAPSHOT_VERSION) return false;
  if (typeof record.values !== 'object' || record.values === null) return false;
  const values = record.values as Record<string, unknown>;
  for (const [key, entry] of Object.entries(values)) {
    if (typeof key !== 'string') return false;
    if (typeof entry !== 'boolean') return false;
  }
  return true;
}

/**
 * Read the persisted pre-hazard snapshot.
 *
 * Returns null (and clears any stored blob) when:
 * - sessionStorage is unavailable,
 * - there is no snapshot,
 * - the stored JSON is malformed,
 * - the version is wrong/stale,
 * - the shape is invalid (any non-string key or non-boolean value).
 *
 * Callers must treat a null result as "use documented normal defaults".
 */
export function readHazardVisibilitySnapshot(): HazardVisibilitySnapshot | null {
  const storage = getSafeSessionStorage();
  if (!storage) return null;

  let raw: string | null;
  try {
    raw = storage.getItem(SNAPSHOT_STORAGE_KEY);
  } catch {
    // Access denied mid-session → behave as if absent.
    return null;
  }
  if (!raw) return null;

  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isHazardVisibilitySnapshot(parsed)) {
      clearHazardVisibilitySnapshot();
      return null;
    }
    return parsed;
  } catch {
    // Malformed JSON → fail safe.
    clearHazardVisibilitySnapshot();
    return null;
  }
}

/**
 * Persist the pre-hazard snapshot. No-op (and never throws) when sessionStorage
 * is unavailable or full. The in-memory ref in the hook still protects the
 * active session even when this write is dropped.
 */
export function writeHazardVisibilitySnapshot(values: Record<string, boolean>): void {
  const storage = getSafeSessionStorage();
  if (!storage) return;
  try {
    const snapshot: HazardVisibilitySnapshot = {
      version: HAZARD_VISIBILITY_SNAPSHOT_VERSION,
      values: { ...values },
    };
    storage.setItem(SNAPSHOT_STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // Storage full / disabled → nothing we can do here.
  }
}

/**
 * Remove the persisted snapshot. No-op (and never throws) when sessionStorage is
 * unavailable. Safe to call even when no snapshot exists.
 */
export function clearHazardVisibilitySnapshot(): void {
  const storage = getSafeSessionStorage();
  if (!storage) return;
  try {
    storage.removeItem(SNAPSHOT_STORAGE_KEY);
  } catch {
    // ignore
  }
}

/** Exposed for tests: the exact storage key used. */
export const HAZARD_VISIBILITY_SNAPSHOT_KEY = SNAPSHOT_STORAGE_KEY;
