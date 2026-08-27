import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';
import { getPrecipitationRange } from '../../src/components/map2d/precipRanges';

describe('precipitation ranges', () => {
  it('uses the annual range for the annual normal', () => {
    expect(getPrecipitationRange('anual')).toMatchObject({ min: 0, max: 1800, unit: 'mm' });
  });

  it('uses the monthly range for every monthly normal', () => {
    expect(getPrecipitationRange('03')).toMatchObject({ min: 0, max: 200, unit: 'mm' });
  });

  it('renders the active shared range in the hazard legend', () => {
    render(
      <MantineProvider env="test">
        <LeyendaPanel hazardPrecipitationRange={getPrecipitationRange('03')} />
      </MantineProvider>
    );

    expect(screen.getByTestId('hazard-precipitation-legend')).toHaveTextContent(
      'CHIRPS 1991-2020 normal mensual'
    );
    expect(screen.getByTestId('hazard-precipitation-legend')).toHaveTextContent('200 mm');
  });
});
