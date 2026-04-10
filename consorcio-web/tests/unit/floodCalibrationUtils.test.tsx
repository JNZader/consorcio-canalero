import { describe, expect, it } from 'vitest';

import { formatZScore, getRainfallColor, getRainfallLabel, getZScoreColor, getZonePaint } from '../../src/components/admin/floodCalibration/floodCalibrationUtils';

describe('floodCalibrationUtils', () => {
  it('returns zone colors by label state', () => {
    expect(getZonePaint('z', { z: true }).fillColor).toBe('#ef4444');
    expect(getZonePaint('z', { z: false }).fillColor).toBe('#22c55e');
    expect(getZonePaint('z', {}).fillColor).toBe('#9ca3af');
  });

  it('categorizes rainfall ranges', () => {
    expect(getRainfallColor(undefined)).toBeUndefined();
    expect(getRainfallLabel(5)).toBe('Lluvia leve');
    expect(getRainfallLabel(20)).toBe('Lluvia moderada');
    expect(getRainfallLabel(40)).toBe('Lluvia intensa');
    expect(getRainfallLabel(70)).toBe('Lluvia muy intensa');
  });

  it('formats zscores and color categories', () => {
    expect(formatZScore(1.24)).toBe('+1.2σ');
    expect(formatZScore(-2.04)).toBe('-2.0σ');
    expect(getZScoreColor(0.2)).toBe('green');
    expect(getZScoreColor(1.2)).toBe('orange');
    expect(getZScoreColor(2.2)).toBe('red');
  });
});
