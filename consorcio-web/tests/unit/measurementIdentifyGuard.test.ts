import { describe, expect, it } from 'vitest';

import {
  armMeasurementIdentifyGuard,
  isMeasurementIdentifyBlocked,
  resetMeasurementIdentifyGuard,
} from '../../src/components/map2d/measurement/measurementIdentifyGuard';

describe('measurementIdentifyGuard', () => {
  it('blocks identify for 300 ms after a measurement finishes', () => {
    resetMeasurementIdentifyGuard();
    expect(isMeasurementIdentifyBlocked(1000)).toBe(false);
    armMeasurementIdentifyGuard(1000);
    expect(isMeasurementIdentifyBlocked(1100)).toBe(true);
    expect(isMeasurementIdentifyBlocked(1300)).toBe(false);
  });
});
