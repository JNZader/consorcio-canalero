import { describe, expect, it } from 'vitest';
import {
  clampDockHeight,
  indexFromPlotX,
  nearestIndexByDistance,
  nearestProfileSample,
  PROFILE_DOCK_MAX_PX,
  PROFILE_DOCK_MIN_PX,
} from '../../src/components/map2d/profileCursorSync';

describe('nearestIndexByDistance', () => {
  const samples = [{ distance_m: 0 }, { distance_m: 100 }, { distance_m: 250 }];

  it('picks the closest sample along the trace', () => {
    expect(nearestIndexByDistance(samples, 90)).toBe(1);
    expect(nearestIndexByDistance(samples, 200)).toBe(2);
  });
});

describe('nearestProfileSample', () => {
  it('returns the sample closest to the pointer', () => {
    const hit = nearestProfileSample(
      [
        { distance_m: 0, lon: -62.7, lat: -32.6 },
        { distance_m: 500, lon: -62.71, lat: -32.61 },
      ],
      -62.709,
      -32.609
    );
    expect(hit?.index).toBe(1);
    expect(hit?.distance_m).toBe(500);
  });
});

describe('indexFromPlotX', () => {
  it('maps the right edge of the plot to the last sample', () => {
    const samples = [{ distance_m: 0 }, { distance_m: 1000 }];
    expect(indexFromPlotX(200, 100, 100, samples)).toBe(1);
    expect(indexFromPlotX(100, 100, 100, samples)).toBe(0);
  });
});

describe('clampDockHeight', () => {
  it('keeps the dock inside the allowed band', () => {
    expect(clampDockHeight(10)).toBe(PROFILE_DOCK_MIN_PX);
    expect(clampDockHeight(900)).toBe(PROFILE_DOCK_MAX_PX);
    expect(clampDockHeight(260)).toBe(260);
  });
});
