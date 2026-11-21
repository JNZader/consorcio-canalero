import { afterEach, describe, expect, it, vi } from 'vitest';

import { flythroughFrames, playFlythrough } from '../../src/components/terrain/canalFlythrough';

describe('canal flythrough', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

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

  it('stops advancing when the AbortSignal aborts', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const easeTo = vi.fn();
    const onFrame = vi.fn(() => {
      controller.abort();
    });
    const frames = [
      { lon: -64.2, lat: -32.4, bearing: 90, distance_m: 100 },
      { lon: -64.19, lat: -32.4, bearing: 90, distance_m: 200 },
    ];

    const promise = playFlythrough({ easeTo }, frames, onFrame, controller.signal);
    await vi.runAllTimersAsync();
    await promise;

    expect(onFrame).toHaveBeenCalledTimes(1);
    expect(easeTo).toHaveBeenCalledTimes(1);
  });

  it('does not run any frame when started with an already-aborted signal', async () => {
    const controller = new AbortController();
    controller.abort();
    const easeTo = vi.fn();
    const onFrame = vi.fn();

    await playFlythrough(
      { easeTo },
      [{ lon: -64.2, lat: -32.4, bearing: 90, distance_m: 100 }],
      onFrame,
      controller.signal
    );

    expect(onFrame).not.toHaveBeenCalled();
    expect(easeTo).not.toHaveBeenCalled();
  });
});
