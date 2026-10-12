import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MapPlacesControl } from '../../src/components/map2d/MapPlacesControl';

function wrap(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('MapPlacesControl', () => {
  it('recenters the consorcio', async () => {
    const user = userEvent.setup();
    const onRecenter = vi.fn();
    wrap(<MapPlacesControl onRecenter={onRecenter} onFlyToPlace={() => {}} />);
    await user.click(screen.getByTestId('map-recenter-consorcio'));
    expect(onRecenter).toHaveBeenCalledOnce();
  });

  it('flies to Bell Ville from lugares rápidos', async () => {
    const user = userEvent.setup();
    const onFlyToPlace = vi.fn();
    wrap(<MapPlacesControl onRecenter={() => {}} onFlyToPlace={onFlyToPlace} />);
    await user.click(screen.getByTestId('map-quick-places'));
    await user.click(screen.getByText('Bell Ville'));
    expect(onFlyToPlace).toHaveBeenCalledWith('bell-ville');
  });

  it('lists San Marcos Sud and Monte Leña', async () => {
    const user = userEvent.setup();
    wrap(<MapPlacesControl onRecenter={() => {}} onFlyToPlace={() => {}} />);
    await user.click(screen.getByTestId('map-quick-places'));
    expect(screen.getByText('San Marcos Sud')).toBeInTheDocument();
    expect(screen.getByText('Monte Leña')).toBeInTheDocument();
  });

  it('offers Ubicarme when geolocate is wired', async () => {
    const user = userEvent.setup();
    const onGeolocate = vi.fn();
    wrap(
      <MapPlacesControl onRecenter={() => {}} onFlyToPlace={() => {}} onGeolocate={onGeolocate} />,
    );
    expect(screen.queryByTestId('map-geolocate')).toBeInTheDocument();
    await user.click(screen.getByTestId('map-geolocate'));
    expect(onGeolocate).toHaveBeenCalledOnce();
  });
});
