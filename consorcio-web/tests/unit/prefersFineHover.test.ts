import { describe, expect, it, vi } from 'vitest';

import {
  prefersFineHover,
  subscribePrefersFineHover,
} from '../../src/components/map2d/prefersFineHover';

function mockMedia(hover: boolean, fine: boolean) {
  const hoverMq = {
    matches: hover,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
  const pointerMq = {
    matches: fine,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
  return {
    media: {
      matchMedia: (query: string) => (query.includes('hover') ? hoverMq : pointerMq),
    },
    hoverMq,
    pointerMq,
  };
}

describe('prefersFineHover MOB-02', () => {
  it('is true only when hover and fine pointer both match', () => {
    expect(prefersFineHover(mockMedia(true, true).media)).toBe(true);
    expect(prefersFineHover(mockMedia(false, true).media)).toBe(false);
    expect(prefersFineHover(mockMedia(true, false).media)).toBe(false);
    expect(prefersFineHover(null)).toBe(false);
    expect(prefersFineHover({} as never)).toBe(true);
  });

  it('listens to matchMedia change instead of sampling once', () => {
    const { media, hoverMq, pointerMq } = mockMedia(true, true);
    const onChange = vi.fn();
    const stop = subscribePrefersFineHover(onChange, media);
    expect(hoverMq.addEventListener).toHaveBeenCalledWith('change', expect.any(Function));
    expect(pointerMq.addEventListener).toHaveBeenCalledWith('change', expect.any(Function));
    stop();
    expect(hoverMq.removeEventListener).toHaveBeenCalled();
    expect(pointerMq.removeEventListener).toHaveBeenCalled();
  });
});
