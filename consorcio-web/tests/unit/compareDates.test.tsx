import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MapViewportOverlay } from '../../src/components/map2d/MapViewportOverlay';
import { monthOptions, tileThumbnailUrl } from '../../src/lib/api/timeLayers';

describe('Sentinel-2 month selector helpers', () => {
  it('stops the month list at the current month', () => {
    expect(monthOptions(2026, new Date(2026, 10, 2))).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
    expect(monthOptions(2024, new Date(2026, 10, 2))).toHaveLength(12);
  });

  it('builds a thumbnail from an XYZ template', () => {
    const url = tileThumbnailUrl('https://tiles.example/{z}/{x}/{y}', -64.18, -32.41, 2);
    expect(url).toMatch(/^https:\/\/tiles\.example\/2\/\d+\/\d+$/);
    expect(tileThumbnailUrl('https://tiles.example/fixed.png')).toBeNull();
  });
});

describe('comparison curtain dates', () => {
  it('pins the dates to the map edges, not to the divider', () => {
    render(
      <MantineProvider env="test">
        <MapViewportOverlay
          viewMode="comparison"
          sliderPosition={20}
          mapReady
          onSliderPointerDown={() => {}}
          leftDate="2018-07-02"
          rightDate="2024-07-02"
        />
      </MantineProvider>
    );
    const left = screen.getByTestId('comparison-date-left');
    const right = screen.getByTestId('comparison-date-right');
    expect(left).toHaveTextContent('2018-07-02');
    expect(right).toHaveTextContent('2024-07-02');
    expect(left.getAttribute('style')).toContain('left: 12px');
    expect(right.getAttribute('style')).toContain('right: 56px');
    expect(screen.getByTestId('map-comparison-divider').getAttribute('style')).toContain('left: 20%');
  });
});
