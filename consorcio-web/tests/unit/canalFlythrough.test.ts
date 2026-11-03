import { describe, expect, it } from 'vitest';

import { flythroughFrames } from '../../src/components/terrain/canalFlythrough';

describe('canal flythrough', () => {
  it('steps along the line and reports distance for the profile cursor', () => {
    const frames = flythroughFrames(
      [
        [-64.2, -32.4],
        [-64.19, -32.4],
        [-64.18, -32.4],
      ],
      50
    );
    expect(frames.length).toBeGreaterThan(1);
    expect(frames[0]!.distance_m).toBeGreaterThan(0);
    expect(frames.at(-1)!.distance_m).toBeGreaterThan(frames[0]!.distance_m);
    expect(frames[0]!.bearing).toBeGreaterThanOrEqual(0);
    expect(frames[0]!.bearing).toBeLessThan(360);
  });

  it('returns nothing for a single point', () => {
    expect(flythroughFrames([[-64.2, -32.4]])).toEqual([]);
  });
});
