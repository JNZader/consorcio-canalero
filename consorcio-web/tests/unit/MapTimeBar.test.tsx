import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { MapTimeBar } from '../../src/components/map2d/MapTimeBar';

function wrap(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('MapTimeBar', () => {
  it('renders nothing without a temporal layer', () => {
    wrap(<MapTimeBar />);
    expect(screen.queryByTestId('map-time-bar')).not.toBeInTheDocument();
  });

  it('shows the selected image date', () => {
    wrap(<MapTimeBar imageDate="2024-03-01" imageSensor="S2" />);
    expect(screen.getByTestId('map-time-bar-label')).toHaveTextContent('S2 · 2024-03-01');
  });

  it('prefers the comparison range when both dates exist', () => {
    wrap(
      <MapTimeBar
        imageDate="2024-03-01"
        compareLeftDate="2023-01-01"
        compareRightDate="2024-01-01"
      />,
    );
    expect(screen.getByTestId('map-time-bar-label')).toHaveTextContent(
      '2023-01-01 → 2024-01-01',
    );
  });

  it('collapses the date line', async () => {
    const user = userEvent.setup();
    wrap(<MapTimeBar imageDate="2024-03-01" />);
    await user.click(screen.getByLabelText('Contraer barra de tiempo'));
    expect(screen.queryByTestId('map-time-bar-label')).not.toBeInTheDocument();
  });
});
