import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MapViewportOverlay } from '../../src/components/map2d/MapViewportOverlay';

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
    expect(left.className).toMatch(/comparisonDateLeft/);
    expect(right.className).toMatch(/comparisonDateRight/);
    expect(screen.getByTestId('map-comparison-divider').getAttribute('style')).toContain('left: 20%');
  });
});
