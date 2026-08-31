import { afterEach, describe, expect, it } from 'vitest';

import {
  HAZARD_NORMAL_VISIBILITY,
  HAZARD_VISIBILITY_SNAPSHOT_KEY,
  HAZARD_VISIBILITY_SNAPSHOT_VERSION,
  clearHazardVisibilitySnapshot,
  parseHazardVisibilitySnapshot,
  readHazardVisibilitySnapshot,
  serializeHazardVisibilitySnapshot,
  writeHazardVisibilitySnapshot,
} from '../../src/components/map2d/hazardVisibilitySnapshot';

const PRE_HAZARD = { roads: true, soil: false, canales_relevados: true, flood_risk: false };
const SNAPSHOT = { version: HAZARD_VISIBILITY_SNAPSHOT_VERSION, values: PRE_HAZARD };

function memoryStorage(initial: Record<string, string> = {}) {
  const store = { ...initial };
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    store,
  };
}

describe('hazardVisibilitySnapshot', () => {
  afterEach(() => {
    clearHazardVisibilitySnapshot(null);
    window.sessionStorage.removeItem(HAZARD_VISIBILITY_SNAPSHOT_KEY);
  });

  it('round-trips versioned blobs and rejects missing, malformed, and mismatched versions', () => {
    const raw = serializeHazardVisibilitySnapshot(PRE_HAZARD);
    expect(JSON.parse(raw)).toEqual(SNAPSHOT);
    expect(parseHazardVisibilitySnapshot(raw)).toEqual(SNAPSHOT);
    expect(parseHazardVisibilitySnapshot(null)).toBeNull();
    expect(parseHazardVisibilitySnapshot('{not-json')).toBeNull();
    expect(parseHazardVisibilitySnapshot(JSON.stringify({ version: 1, values: 'nope' }))).toBeNull();
    expect(parseHazardVisibilitySnapshot(JSON.stringify({ version: 99, values: PRE_HAZARD }))).toBeNull();
  });

  it('writes through provided storage, never localStorage, and clears bad blobs', () => {
    const storage = memoryStorage();
    writeHazardVisibilitySnapshot(PRE_HAZARD, storage);
    expect(readHazardVisibilitySnapshot(storage)).toEqual(SNAPSHOT);
    expect(window.localStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeFalsy();
    const malformed = memoryStorage({ [HAZARD_VISIBILITY_SNAPSHOT_KEY]: '{broken' });
    const mismatched = memoryStorage({
      [HAZARD_VISIBILITY_SNAPSHOT_KEY]: JSON.stringify({ version: 2, values: PRE_HAZARD }),
    });
    expect(readHazardVisibilitySnapshot(malformed)).toBeNull();
    expect(malformed.store[HAZARD_VISIBILITY_SNAPSHOT_KEY]).toBeUndefined();
    expect(readHazardVisibilitySnapshot(mismatched)).toBeNull();
  });

  it('degrades to in-memory same-mount restoration when storage throws', () => {
    const deny = () => {
      throw new Error('denied');
    };
    const denied = { getItem: deny, setItem: deny, removeItem: deny };
    expect(() => writeHazardVisibilitySnapshot(PRE_HAZARD, denied)).not.toThrow();
    expect(readHazardVisibilitySnapshot(denied)).toEqual(SNAPSHOT);
    expect(() => clearHazardVisibilitySnapshot(denied)).not.toThrow();
    expect(readHazardVisibilitySnapshot(denied)).toBeNull();
  });

  it('exports normal defaults with canals on and the rest of the canonical stack off', () => {
    expect(HAZARD_NORMAL_VISIBILITY.canales_relevados).toBe(true);
    expect(
      Object.entries(HAZARD_NORMAL_VISIBILITY).filter(([, visible]) => visible).map(([id]) => id)
    ).toEqual(['canales_relevados']);
  });
});
