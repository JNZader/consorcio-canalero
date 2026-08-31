import { describe, expect, it } from 'vitest';

import {
  BASIN_CATALOG_STATUS,
  HAZARD_RISK_CLASSES,
  parseHazardUrlState,
  resolveBasinCatalogStatus,
  toHazardSearch,
} from '../../src/hooks/useHazardUrlState';

const OPEN_GATE = { gateOpen: true, basinIds: ['basin-a', 'basin-b'] };
const SHARED = { hazard: '1' as const, basin: 'shared-basin' };

describe('hazard URL state', () => {
  it('parses shareable hazard, basin, risk-class, and precipitation-month state', () => {
    expect(
      parseHazardUrlState(
        { hazard: '1', basin: 'basin-a', riskClasses: ['Bajo,Alto', 'Crítico'], precipMonth: '03' },
        OPEN_GATE
      )
    ).toEqual({ hazard: true, basin: 'basin-a', riskClasses: ['Bajo', 'Alto', 'Crítico'], precipMonth: '03' });
  });

  it('normalizes invalid state to defaults and removes it from canonical search', () => {
    const state = parseHazardUrlState(
      { hazard: '1', basin: 'unknown', riskClasses: 'invalid,also-invalid', precipMonth: '99' },
      OPEN_GATE
    );
    expect(state).toEqual({ hazard: true, basin: null, riskClasses: [...HAZARD_RISK_CLASSES], precipMonth: 'anual' });
    expect(toHazardSearch(state, true)).toEqual({ hazard: '1' });
  });

  it('writes only state that differs from the active defaults', () => {
    const state = parseHazardUrlState(
      { hazard: '1', basin: 'basin-b', riskClasses: 'Medio,Alto', precipMonth: '11' },
      OPEN_GATE
    );
    expect(toHazardSearch(state, true)).toEqual({
      hazard: '1', basin: 'basin-b', riskClasses: 'Medio,Alto', precipMonth: '11',
    });
  });

  it('resets to defaults while retaining active hazard mode', () => {
    expect(toHazardSearch(parseHazardUrlState({ hazard: '1' }, OPEN_GATE), true)).toEqual({ hazard: '1' });
  });

  it('strips all hazard state when the role/feature gate is closed', () => {
    const state = parseHazardUrlState(
      { hazard: '1', basin: 'basin-a', riskClasses: 'Bajo', precipMonth: '05' },
      { ...OPEN_GATE, gateOpen: false }
    );
    expect(state.hazard).toBe(false);
    expect(toHazardSearch(state, false)).toEqual({});
  });
});

describe('C5 — basin catalog race (B3B-NEW-003)', () => {
  it('keeps a valid basin when basinIds are omitted during load', () => {
    expect(parseHazardUrlState(SHARED, { gateOpen: true }).basin).toBe('shared-basin');
    expect(
      parseHazardUrlState(SHARED, {
        gateOpen: true,
        basinCatalogStatus: BASIN_CATALOG_STATUS.LOADING,
      }).basin
    ).toBe('shared-basin');
  });

  it('does not drop a valid basin when basinIds is empty while the catalog is loading', () => {
    const state = parseHazardUrlState(SHARED, {
      gateOpen: true,
      basinIds: [],
      basinCatalogStatus: BASIN_CATALOG_STATUS.LOADING,
    });
    expect(state.basin).toBe('shared-basin');
    expect(toHazardSearch(state, true)).toEqual({ hazard: '1', basin: 'shared-basin' });
  });

  it('keeps a known basin after the catalog resolves', () => {
    expect(
      parseHazardUrlState(SHARED, {
        gateOpen: true,
        basinIds: ['shared-basin', 'other'],
        basinCatalogStatus: BASIN_CATALOG_STATUS.READY,
      }).basin
    ).toBe('shared-basin');
  });

  it('drops an unknown basin only after the catalog resolves, including a resolved empty catalog', () => {
    expect(
      parseHazardUrlState(SHARED, {
        gateOpen: true,
        basinIds: ['other'],
        basinCatalogStatus: BASIN_CATALOG_STATUS.READY,
      }).basin
    ).toBeNull();
    expect(
      parseHazardUrlState(SHARED, {
        gateOpen: true,
        basinIds: [],
        basinCatalogStatus: BASIN_CATALOG_STATUS.READY,
      }).basin
    ).toBeNull();
  });

  it('preserves the basin parameter when the catalog errors (fail-open)', () => {
    const state = parseHazardUrlState(SHARED, {
      gateOpen: true,
      basinIds: [],
      basinCatalogStatus: BASIN_CATALOG_STATUS.ERROR,
    });
    expect(state.basin).toBe('shared-basin');
    expect(toHazardSearch(state, true)).toEqual({ hazard: '1', basin: 'shared-basin' });
  });

  it('does not canonicalize a shared basin away across the loading window, then drops only if unknown', () => {
    const loading = parseHazardUrlState(SHARED, {
      gateOpen: true,
      basinIds: [],
      basinCatalogStatus: BASIN_CATALOG_STATUS.LOADING,
    });
    expect(toHazardSearch(loading, true)).toEqual({ hazard: '1', basin: 'shared-basin' });

    const readyKnown = parseHazardUrlState(SHARED, {
      gateOpen: true,
      basinIds: ['shared-basin'],
      basinCatalogStatus: BASIN_CATALOG_STATUS.READY,
    });
    expect(toHazardSearch(readyKnown, true)).toEqual({ hazard: '1', basin: 'shared-basin' });

    const readyUnknown = parseHazardUrlState(SHARED, {
      gateOpen: true,
      basinIds: ['other'],
      basinCatalogStatus: BASIN_CATALOG_STATUS.READY,
    });
    expect(readyUnknown.basin).toBeNull();
    expect(toHazardSearch(readyUnknown, true)).toEqual({ hazard: '1' });
  });

  it('maps useBasins loading/error flags to catalog status without treating empty as ready', () => {
    expect(resolveBasinCatalogStatus({ loading: true, error: null })).toBe(
      BASIN_CATALOG_STATUS.LOADING
    );
    expect(
      resolveBasinCatalogStatus({
        loading: false,
        error: 'No se pudieron cargar las cuencas operativas',
      })
    ).toBe(BASIN_CATALOG_STATUS.ERROR);
    expect(resolveBasinCatalogStatus({ loading: false, error: null })).toBe(
      BASIN_CATALOG_STATUS.READY
    );
    expect(resolveBasinCatalogStatus({ loading: true, error: 'stale' })).toBe(
      BASIN_CATALOG_STATUS.LOADING
    );
  });
});
