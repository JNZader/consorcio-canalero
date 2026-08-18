/**
 * hazardVisibilitySnapshot.test.ts
 *
 * Locks the versioned, per-tab (sessionStorage) pre-hazard visibility snapshot:
 * round-trip persistence, malformed / wrong-version / stale rejection, safe
 * clearing, and graceful degradation when sessionStorage is unavailable.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  HAZARD_VISIBILITY_SNAPSHOT_KEY,
  HAZARD_VISIBILITY_SNAPSHOT_VERSION,
  readHazardVisibilitySnapshot,
  writeHazardVisibilitySnapshot,
  clearHazardVisibilitySnapshot,
} from '../../src/components/map2d/hazardVisibilitySnapshot';

const SAMPLE: Record<string, boolean> = {
  roads: true,
  waterways: false,
  catastro: true,
};

describe('hazardVisibilitySnapshot', () => {
  beforeEach(() => {
    try {
      sessionStorage.clear();
    } catch {
      // ignore
    }
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns null when no snapshot exists', () => {
    expect(readHazardVisibilitySnapshot()).toBeNull();
  });

  it('round-trips a written snapshot with the correct version', () => {
    writeHazardVisibilitySnapshot(SAMPLE);

    const loaded = readHazardVisibilitySnapshot();
    expect(loaded).not.toBeNull();
    expect(loaded?.version).toBe(HAZARD_VISIBILITY_SNAPSHOT_VERSION);
    expect(loaded?.values).toEqual(SAMPLE);

    // The raw blob is versioned + namespaced.
    const raw = sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY);
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw as string);
    expect(parsed.version).toBe(HAZARD_VISIBILITY_SNAPSHOT_VERSION);
  });

  it('clears and ignores malformed JSON', () => {
    sessionStorage.setItem(HAZARD_VISIBILITY_SNAPSHOT_KEY, '{not valid');
    expect(readHazardVisibilitySnapshot()).toBeNull();
    // Malformed blob removed.
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
  });

  it('clears and ignores a wrong-version snapshot (stale)', () => {
    sessionStorage.setItem(
      HAZARD_VISIBILITY_SNAPSHOT_KEY,
      JSON.stringify({ version: HAZARD_VISIBILITY_SNAPSHOT_VERSION + 1, values: SAMPLE })
    );
    expect(readHazardVisibilitySnapshot()).toBeNull();
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
  });

  it('clears and ignores a structurally invalid snapshot (non-boolean values)', () => {
    sessionStorage.setItem(
      HAZARD_VISIBILITY_SNAPSHOT_KEY,
      JSON.stringify({ version: HAZARD_VISIBILITY_SNAPSHOT_VERSION, values: { roads: 'yes' } })
    );
    expect(readHazardVisibilitySnapshot()).toBeNull();
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
  });

  it('clears and ignores a snapshot whose values is not an object', () => {
    sessionStorage.setItem(
      HAZARD_VISIBILITY_SNAPSHOT_KEY,
      JSON.stringify({ version: HAZARD_VISIBILITY_SNAPSHOT_VERSION, values: 42 })
    );
    expect(readHazardVisibilitySnapshot()).toBeNull();
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
  });

  it('clear is safe when no snapshot exists', () => {
    expect(() => clearHazardVisibilitySnapshot()).not.toThrow();
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
  });

  it('does not throw and falls back when sessionStorage is undefined (SSR/no storage)', () => {
    const original = globalThis.sessionStorage;
    Object.defineProperty(globalThis, 'sessionStorage', {
      value: undefined,
      configurable: true,
    });
    try {
      expect(() => writeHazardVisibilitySnapshot(SAMPLE)).not.toThrow();
      expect(readHazardVisibilitySnapshot()).toBeNull();
      expect(() => clearHazardVisibilitySnapshot()).not.toThrow();
    } finally {
      Object.defineProperty(globalThis, 'sessionStorage', {
        value: original,
        configurable: true,
      });
    }
  });

  it('does not throw when sessionStorage access throws', () => {
    const throwing = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
      removeItem: () => {
        throw new Error('blocked');
      },
    };
    const original = globalThis.sessionStorage;
    Object.defineProperty(globalThis, 'sessionStorage', {
      value: throwing,
      configurable: true,
    });
    try {
      expect(() => writeHazardVisibilitySnapshot(SAMPLE)).not.toThrow();
      expect(readHazardVisibilitySnapshot()).toBeNull();
      expect(() => clearHazardVisibilitySnapshot()).not.toThrow();
    } finally {
      Object.defineProperty(globalThis, 'sessionStorage', {
        value: original,
        configurable: true,
      });
    }
  });
});
