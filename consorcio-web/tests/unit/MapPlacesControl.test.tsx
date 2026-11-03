import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MapPlacesControl } from '../../src/components/map2d/MapPlacesControl';
import { MapSearchBox } from '../../src/components/map2d/MapSearchBox';

function wrap(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('MapPlacesControl', () => {
  it('recenters the consorcio', async () => {
    const user = userEvent.setup();
    const onRecenter = vi.fn();
    wrap(<MapPlacesControl onRecenter={onRecenter} />);
    await user.click(screen.getByTestId('map-recenter-consorcio'));
    expect(onRecenter).toHaveBeenCalledOnce();
  });

  it('is a single home button, without a lugares menu', () => {
    const { container } = wrap(<MapPlacesControl onRecenter={() => {}} />);
    const group = container.querySelector('.maplibregl-ctrl-group');
    expect(group?.querySelectorAll(':scope > button')).toHaveLength(1);
    expect(screen.queryByTestId('map-quick-places')).not.toBeInTheDocument();
  });
});

describe('MapSearchBox lugares rápidos', () => {
  const places = [
    { id: 'bell-ville', label: 'Bell Ville' },
    { id: 'san-marcos-sud', label: 'San Marcos Sud' },
    { id: 'monte-lena', label: 'Monte Leña' },
  ];

  function renderSearch(overrides: Partial<Parameters<typeof MapSearchBox>[0]> = {}) {
    return wrap(
      <MapSearchBox
        query=""
        onQueryChange={() => {}}
        canalIndex={null}
        parcels={null}
        parcelsLoading={false}
        onPickCanal={() => {}}
        onPickParcel={() => {}}
        places={places}
        onPickPlace={() => {}}
        onGeolocate={() => {}}
        {...overrides}
      />
    );
  }

  it('offers Ubicarme and the three towns while the query is empty', async () => {
    const user = userEvent.setup();
    const onPickPlace = vi.fn();
    const onGeolocate = vi.fn();
    renderSearch({ onPickPlace, onGeolocate });

    expect(screen.getByRole('list', { name: 'Lugares rápidos' })).toBeInTheDocument();
    await user.click(screen.getByTestId('map-geolocate'));
    expect(onGeolocate).toHaveBeenCalledOnce();
    await user.click(screen.getByText('Bell Ville'));
    expect(onPickPlace).toHaveBeenCalledWith('bell-ville');
    expect(screen.getByText('San Marcos Sud')).toBeInTheDocument();
    expect(screen.getByText('Monte Leña')).toBeInTheDocument();
  });

  it('does not render the duplicated copy-link or QR buttons', () => {
    renderSearch();
    expect(screen.queryByTestId('map-copy-link')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'QR' })).not.toBeInTheDocument();
  });
});
