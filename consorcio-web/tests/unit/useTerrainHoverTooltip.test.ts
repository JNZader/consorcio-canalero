import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useTerrainHoverTooltip } from '../../src/components/terrain/useTerrainHoverTooltip';

describe('useTerrainHoverTooltip', () => {
  it('registers mousemove when the map is ready and Popup exists', () => {
    const on = vi.fn();
    const off = vi.fn();
    const map = {
      on,
      off,
      getLayer: () => ({}),
      queryRenderedFeatures: () => [],
      getCanvas: () => ({ style: { cursor: '' } }),
    };
    const mapRef = { current: map };

    const { unmount } = renderHook(() =>
      useTerrainHoverTooltip({ mapRef: mapRef as never, ready: true }),
    );

    expect(on).toHaveBeenCalledWith('mousemove', expect.any(Function));
    expect(on).toHaveBeenCalledWith('mouseout', expect.any(Function));
    unmount();
    expect(off).toHaveBeenCalledWith('mousemove', expect.any(Function));
  });

  it('does nothing before ready', () => {
    const on = vi.fn();
    renderHook(() =>
      useTerrainHoverTooltip({
        mapRef: { current: { on } } as never,
        ready: false,
      }),
    );
    expect(on).not.toHaveBeenCalled();
  });
});
