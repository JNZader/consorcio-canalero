/**
 * useHazardUrlState.test.ts
 *
 * Locks the Multi-Hazard URL-state hook: parsing, validation, setters, reset,
 * and the feature-flag + role gate.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  useHazardUrlState,
  HAZARD_DEFAULT_RISK_CLASSES,
  HAZARD_DEFAULT_PRECIP_MONTH,
  type PrecipMonth,
  type RiskClass,
} from '../../src/hooks/useHazardUrlState';

const mocks = vi.hoisted(() => ({
  search: {} as Record<string, unknown>,
  navigate: vi.fn(),
  canAccess: vi.fn(() => true),
  router: { state: { status: 'idle' } } as unknown,
}));

vi.mock('@tanstack/react-router', () => ({
  getRouteApi: () => ({
    useSearch: () => mocks.search,
  }),
  useNavigate: () => mocks.navigate,
  useRouter: () => mocks.router,
}));

vi.mock('../../src/stores/authStore', () => ({
  useCanAccess: mocks.canAccess,
}));

describe('useHazardUrlState', () => {
  beforeEach(() => {
    mocks.search = {};
    mocks.navigate.mockClear();
    mocks.canAccess.mockReturnValue(true);
    import.meta.env.VITE_FEATURE_MULTI_HAZARD_VIEWER = 'true';
  });

  afterEach(() => {
    vi.clearAllMocks();
    delete import.meta.env.VITE_FEATURE_MULTI_HAZARD_VIEWER;
  });

  it('returns safe defaults when hazard mode is not requested', () => {
    const { result } = renderHook(() => useHazardUrlState());

    expect(result.current.hazard).toBe(false);
    expect(result.current.isHazardActive).toBe(false);
    expect(result.current.basin).toBeNull();
    expect(result.current.riskClasses).toEqual([]);
    expect(result.current.precipMonth).toBe(HAZARD_DEFAULT_PRECIP_MONTH);
  });

  it('activates hazard mode when hazard=1, flag is on, and user has role', () => {
    mocks.search = { hazard: true };

    const { result } = renderHook(() => useHazardUrlState());

    expect(result.current.hazard).toBe(true);
    expect(result.current.isHazardActive).toBe(true);
    expect(result.current.riskClasses).toEqual(HAZARD_DEFAULT_RISK_CLASSES);
    expect(result.current.precipMonth).toBe(HAZARD_DEFAULT_PRECIP_MONTH);
  });

  it('ignores hazard=1 when the feature flag is off', () => {
    import.meta.env.VITE_FEATURE_MULTI_HAZARD_VIEWER = 'false';
    mocks.search = { hazard: true };

    const { result } = renderHook(() => useHazardUrlState());

    expect(result.current.hazard).toBe(true);
    expect(result.current.isHazardActive).toBe(false);
    expect(result.current.riskClasses).toEqual([]);
  });

  it('ignores hazard=1 when the user lacks the admin/operador role', () => {
    mocks.canAccess.mockReturnValue(false);
    mocks.search = { hazard: true };

    const { result } = renderHook(() => useHazardUrlState());

    expect(result.current.hazard).toBe(true);
    expect(result.current.isHazardActive).toBe(false);
    expect(result.current.riskClasses).toEqual([]);
  });

  it('parses basin id and drops empty/invalid values', () => {
    const { rerender, result } = renderHook(() => useHazardUrlState());

    mocks.search = { basin: 'cuenca-rio-tercero' };
    rerender({});
    expect(result.current.basin).toBe('cuenca-rio-tercero');

    mocks.search = { basin: '' };
    rerender({});
    expect(result.current.basin).toBeNull();

    mocks.search = { basin: '   ' };
    rerender({});
    expect(result.current.basin).toBeNull();

    mocks.search = {};
    rerender({});
    expect(result.current.basin).toBeNull();
  });

  it('parses riskClasses from comma-separated string and filters unknown values', () => {
    mocks.search = { hazard: true, riskClasses: ['Bajo', 'Medio', 'Imposible'] };

    const { result } = renderHook(() => useHazardUrlState());

    expect(result.current.riskClasses).toEqual(['Bajo', 'Medio']);
  });

  it('parses riskClasses from a single comma-separated string', () => {
    mocks.search = { hazard: true, riskClasses: 'Bajo,Alto,Crítico,Falso' };

    const { result } = renderHook(() => useHazardUrlState());

    expect(result.current.riskClasses).toEqual(['Bajo', 'Alto', 'Crítico']);
  });

  it('selects a precipitation month other than annual', () => {
    mocks.search = { hazard: true, precipMonth: '03' as PrecipMonth };

    const { result } = renderHook(() => useHazardUrlState());

    expect(result.current.precipMonth).toBe('03');
  });

  it('falls back to annual when precipMonth is unknown', () => {
    mocks.search = { hazard: true, precipMonth: '13' };

    const { result } = renderHook(() => useHazardUrlState());

    expect(result.current.precipMonth).toBe('anual');
  });

  it('setHazard writes the hazard param when gate is open', () => {
    const { result } = renderHook(() => useHazardUrlState());

    act(() => result.current.setHazard(true));

    expect(mocks.navigate).toHaveBeenCalledWith({
      search: expect.any(Function),
      replace: true,
    });
    const searchFn = mocks.navigate.mock.calls[0][0].search;
    expect(searchFn({})).toEqual({ hazard: true });
  });

  it('setHazard drops the hazard param when gate is closed', () => {
    mocks.canAccess.mockReturnValue(false);
    const { result } = renderHook(() => useHazardUrlState());

    act(() => result.current.setHazard(true));

    const searchFn = mocks.navigate.mock.calls[0][0].search;
    expect(searchFn({})).toEqual({ hazard: false });
  });

  it('setBasin writes a basin id and null clears it', () => {
    const { result } = renderHook(() => useHazardUrlState());

    act(() => result.current.setBasin('cuenca-x'));
    let searchFn = mocks.navigate.mock.calls[0][0].search;
    expect(searchFn({})).toEqual({ basin: 'cuenca-x' });

    act(() => result.current.setBasin(null));
    searchFn = mocks.navigate.mock.calls[1][0].search;
    expect(searchFn({})).toEqual({ basin: undefined });
  });

  it('setRiskClasses writes the array and omits it when empty', () => {
    const { result } = renderHook(() => useHazardUrlState());

    act(() => result.current.setRiskClasses(['Bajo', 'Crítico'] as RiskClass[]));
    let searchFn = mocks.navigate.mock.calls[0][0].search;
    expect(searchFn({})).toEqual({ riskClasses: ['Bajo', 'Crítico'] });

    act(() => result.current.setRiskClasses([] as RiskClass[]));
    searchFn = mocks.navigate.mock.calls[1][0].search;
    expect(searchFn({})).toEqual({ riskClasses: undefined });
  });

  it('setPrecipMonth writes the month', () => {
    const { result } = renderHook(() => useHazardUrlState());

    act(() => result.current.setPrecipMonth('07'));

    const searchFn = mocks.navigate.mock.calls[0][0].search;
    expect(searchFn({})).toEqual({ precipMonth: '07' });
  });

  it('resetToDefaults writes the canonical hazard stack', () => {
    const { result } = renderHook(() => useHazardUrlState());

    act(() => result.current.resetToDefaults());

    const searchFn = mocks.navigate.mock.calls[0][0].search;
    expect(searchFn({})).toEqual({
      hazard: true,
      basin: undefined,
      riskClasses: HAZARD_DEFAULT_RISK_CLASSES,
      precipMonth: HAZARD_DEFAULT_PRECIP_MONTH,
      layers: undefined,
    });
  });

  it('resetToDefaults writes hazard:false when gate is closed', () => {
    mocks.canAccess.mockReturnValue(false);
    const { result } = renderHook(() => useHazardUrlState());

    act(() => result.current.resetToDefaults());

    const searchFn = mocks.navigate.mock.calls[0][0].search;
    expect(searchFn({})).toEqual({
      hazard: false,
      basin: undefined,
      riskClasses: HAZARD_DEFAULT_RISK_CLASSES,
      precipMonth: HAZARD_DEFAULT_PRECIP_MONTH,
      layers: undefined,
    });
  });

  it('merges new search params with previous ones', () => {
    const { result } = renderHook(() => useHazardUrlState());

    act(() => result.current.setBasin('cuenca-rio-tercero'));

    const searchFn = mocks.navigate.mock.calls[0][0].search;
    expect(searchFn({ existing: 'value' })).toEqual({
      existing: 'value',
      basin: 'cuenca-rio-tercero',
    });
  });

  it('returns safe defaults and no-op setters when there is no router context', () => {
    mocks.router = undefined;

    const { result } = renderHook(() => useHazardUrlState());

    expect(result.current.hazard).toBe(false);
    expect(result.current.isHazardActive).toBe(false);
    expect(result.current.basin).toBeNull();
    expect(result.current.riskClasses).toEqual([]);
    expect(result.current.precipMonth).toBe(HAZARD_DEFAULT_PRECIP_MONTH);

    expect(() => act(() => result.current.setHazard(true))).not.toThrow();
    expect(() => act(() => result.current.setBasin('x'))).not.toThrow();
    expect(() => act(() => result.current.setRiskClasses([] as RiskClass[]))).not.toThrow();
    expect(() => act(() => result.current.setPrecipMonth('01'))).not.toThrow();
    expect(() => act(() => result.current.resetToDefaults())).not.toThrow();
    expect(mocks.navigate).not.toHaveBeenCalled();

    mocks.router = { state: { status: 'idle' } };
  });
});
