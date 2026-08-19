import { describe, expect, it } from 'vitest';

import { HAZARD_RISK_CLASSES, parseHazardUrlState, toHazardSearch } from '../../src/hooks/useHazardUrlState';

const OPEN_GATE = { gateOpen: true, basinIds: ['basin-a', 'basin-b'] };

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
