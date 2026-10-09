import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { LineString } from 'geojson';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) => (
      <div style={{ width: 320, height: 160 }}>{children}</div>
    ),
    LineChart: ({
      children,
      onMouseMove,
      onMouseLeave,
    }: {
      children?: ReactNode;
      onMouseMove?: (event: { activeLabel?: number | string }) => void;
      onMouseLeave?: () => void;
    }) => (
      <div
        data-testid="elevation-line-chart"
        onMouseMove={() => onMouseMove?.({ activeLabel: 15 })}
        onMouseLeave={() => onMouseLeave?.()}
      >
        {children}
      </div>
    ),
  };
});

vi.mock('../../src/lib/api/elevationProfile', () => ({
  fetchElevationProfile: vi.fn(),
}));

import { fetchElevationProfile } from '../../src/lib/api/elevationProfile';
import { ElevationProfileChart } from '../../src/components/map2d/ElevationProfileChart';

const line: LineString = {
  type: 'LineString',
  coordinates: [
    [-62.7, -32.6],
    [-62.71, -32.61],
  ],
};

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('<ElevationProfileChart />', () => {
  it('does not fetch until the operator asks', () => {
    renderWithMantine(<ElevationProfileChart geometry={line} />);
    expect(screen.getByRole('button', { name: 'Perfil de elevación' })).toBeInTheDocument();
    expect(fetchElevationProfile).not.toHaveBeenCalled();
  });

  it('renders disclaimer and extrema after a successful sample', async () => {
    vi.mocked(fetchElevationProfile).mockResolvedValueOnce({
      puntos: [
        { distance_m: 0, elevation_m: 120 },
        { distance_m: 15, elevation_m: 118 },
      ],
      length_m: 15,
      min_elevation_m: 118,
      max_elevation_m: 120,
      source: 'dem_filled.tif',
      cell_m: 15,
      disclaimer: 'Perfil sobre Copernicus GLO-30 (~30 m). No es cota de proyecto ni sección de canal.',
    });
    const user = userEvent.setup();
    renderWithMantine(<ElevationProfileChart geometry={line} />);
    await user.click(screen.getByRole('button', { name: 'Perfil de elevación' }));
    expect(await screen.findByTestId('elevation-profile-disclaimer')).toHaveTextContent('GLO-30');
    expect(screen.getByTestId('elevation-profile-extrema')).toHaveTextContent('118.0 m');
    expect(screen.getByTestId('elevation-profile-chart')).toBeInTheDocument();
  });

  it('reports chart hover distance for the map cursor', async () => {
    vi.mocked(fetchElevationProfile).mockResolvedValueOnce({
      puntos: [
        { distance_m: 0, elevation_m: 120 },
        { distance_m: 15, elevation_m: 118 },
      ],
      length_m: 15,
      min_elevation_m: 118,
      max_elevation_m: 120,
      source: 'dem_filled.tif',
      cell_m: 15,
      disclaimer: 'Perfil sobre Copernicus GLO-30 (~30 m). No es cota de proyecto ni sección de canal.',
    });
    const onHoverDistanceM = vi.fn();
    const user = userEvent.setup();
    renderWithMantine(
      <ElevationProfileChart geometry={line} onHoverDistanceM={onHoverDistanceM} />,
    );
    await user.click(screen.getByRole('button', { name: 'Perfil de elevación' }));
    fireEvent.mouseMove(await screen.findByTestId('elevation-line-chart'));
    expect(onHoverDistanceM).toHaveBeenCalledWith(15);
    fireEvent.mouseLeave(screen.getByTestId('elevation-line-chart'));
    expect(onHoverDistanceM).toHaveBeenCalledWith(null);
  });

  it('renders nothing for a Point', () => {
    renderWithMantine(
      <ElevationProfileChart geometry={{ type: 'Point', coordinates: [-62.7, -32.6] }} />,
    );
    expect(screen.queryByTestId('elevation-profile')).not.toBeInTheDocument();
  });
});
