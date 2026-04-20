/**
 * Pilar Verde-specific slice of `useMapDerivedState`.
 *
 * Scope: verify the hook accepts a `pilarVerde?: PilarVerdeData | null` param
 * and re-exposes the 5 presentation collections in a stable shape (`pilarVerde`
 * pass-through). The existing behavior of the hook is not touched by this
 * test file — see `useMapDerivedState.test.ts` for the broader coverage.
 */

import type { FeatureCollection } from 'geojson';
import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useMapDerivedState } from '../../src/components/map2d/useMapDerivedState';
import type { PilarVerdeData } from '../../src/types/pilarVerde';

function fc(): FeatureCollection {
  return { type: 'FeatureCollection', features: [] };
}

function baseParams(overrides?: Partial<Parameters<typeof useMapDerivedState>[0]>) {
  return {
    capas: {},
    caminos: null,
    soilMap: null,
    basins: null,
    suggestedZones: null,
    waterways: [],
    allGeoLayers: [],
    approvedZones: null,
    draftBasinAssignments: {},
    suggestedZoneNames: {},
    hiddenClasses: {},
    hiddenRanges: {},
    activeDemLayerId: null,
    selectedDraftBasinId: null,
    selectedImage: null,
    comparison: null,
    vectorVisibility: {},
    hasApprovedZones: false,
    intersectionsLength: 0,
    isAdmin: false,
    ...overrides,
  } satisfies Parameters<typeof useMapDerivedState>[0];
}

describe('useMapDerivedState · Pilar Verde', () => {
  it('re-exposes the pilar verde slots on the returned object', () => {
    const pilarVerde: PilarVerdeData = {
      zonaAmpliada: null,
      bpa2025: fc() as never,
      agroAceptada: fc() as never,
      agroPresentada: fc() as never,
      agroZonas: fc() as never,
      porcentajeForestacion: fc() as never,
      bpaEnriched: null,
      bpaHistory: null,
      aggregates: null,
    };

    const { result } = renderHook(() => useMapDerivedState(baseParams({ pilarVerde })));

    expect(result.current.pilarVerde).toBe(pilarVerde);
  });

  it('returns null pilarVerde slot when the param is omitted', () => {
    const { result } = renderHook(() => useMapDerivedState(baseParams()));
    expect(result.current.pilarVerde).toBeNull();
  });

  it('accepts null explicitly and propagates it without throwing', () => {
    const { result } = renderHook(() =>
      useMapDerivedState(baseParams({ pilarVerde: null })),
    );
    expect(result.current.pilarVerde).toBeNull();
  });
});
