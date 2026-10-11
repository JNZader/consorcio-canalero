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
      onClick,
    }: {
      children?: ReactNode;
      onMouseMove?: (event: { activeIndex?: number }) => void;
      onMouseLeave?: () => void;
      onClick?: (event: { activeIndex?: number }) => void;
    }) => (
      <div
        data-testid="elevation-line-chart"
        onMouseMove={() => onMouseMove?.({ activeIndex: 1 })}
        onClick={() => onClick?.({ activeIndex: 1 })}
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

  it('reports sample lon/lat for the map cursor', async () => {
    vi.mocked(fetchElevationProfile).mockResolvedValueOnce({
      puntos: [
        { distance_m: 0, elevation_m: 120, lon: -62.7, lat: -32.6 },
        { distance_m: 15, elevation_m: 118, lon: -62.71, lat: -32.61 },
      ],
      length_m: 15,
      min_elevation_m: 118,
      max_elevation_m: 120,
      source: 'dem_filled.tif',
      cell_m: 15,
      disclaimer: 'Perfil sobre Copernicus GLO-30 (~30 m). No es cota de proyecto ni sección de canal.',
    });
    const onHoverLngLat = vi.fn();
    const user = userEvent.setup();
    renderWithMantine(
      <ElevationProfileChart geometry={line} onHoverLngLat={onHoverLngLat} />,
    );
    await user.click(screen.getByRole('button', { name: 'Perfil de elevación' }));
    fireEvent.mouseMove(await screen.findByTestId('elevation-line-chart'));
    expect(onHoverLngLat).toHaveBeenCalledWith({ lon: -62.71, lat: -32.61 });
    fireEvent.mouseLeave(screen.getByTestId('elevation-line-chart'));
    expect(onHoverLngLat).toHaveBeenCalledWith(null);
  });

  it('reports a pick at the hovered sample', async () => {
    vi.mocked(fetchElevationProfile).mockResolvedValueOnce({
      puntos: [
        { distance_m: 0, elevation_m: 120, lon: -62.7, lat: -32.6 },
        { distance_m: 15, elevation_m: 118, lon: -62.71, lat: -32.61 },
      ],
      length_m: 15,
      min_elevation_m: 118,
      max_elevation_m: 120,
      source: 'dem_filled.tif',
      cell_m: 15,
      disclaimer: 'Perfil sobre Copernicus GLO-30 (~30 m). No es cota de proyecto ni sección de canal.',
    });
    const onPickLngLat = vi.fn();
    const user = userEvent.setup();
    renderWithMantine(
      <ElevationProfileChart geometry={line} onPickLngLat={onPickLngLat} />,
    );
    await user.click(screen.getByRole('button', { name: 'Perfil de elevación' }));
    fireEvent.click(await screen.findByTestId('elevation-line-chart'));
    expect(onPickLngLat).toHaveBeenCalledWith({ lon: -62.71, lat: -32.61 });
  });

  it('renders MDE-Ar disclaimer and a second series when sampled', async () => {
    vi.mocked(fetchElevationProfile).mockResolvedValueOnce({
      puntos: [
        { distance_m: 0, elevation_m: 120, elevation_mde_ar: 122 },
        { distance_m: 15, elevation_m: 118, elevation_mde_ar: 119 },
      ],
      length_m: 15,
      min_elevation_m: 118,
      max_elevation_m: 120,
      source: 'dem_filled.tif',
      cell_m: 15,
      disclaimer:
        'Perfil sobre Copernicus GLO-30 (~30 m). No es cota de proyecto ni sección de canal.',
      mde_ar_disclaimer:
        'MDE-Ar (IGN, SRVN16). No comparar el delta con GLO-30 como cota verdadera.',
    });
    const user = userEvent.setup();
    renderWithMantine(<ElevationProfileChart geometry={line} />);
    await user.click(screen.getByRole('button', { name: 'Perfil de elevación' }));
    expect(await screen.findByTestId('elevation-profile-mde-ar')).toHaveTextContent('SRVN16');
    expect(screen.getByTestId('elevation-profile-disclaimer')).toHaveTextContent('GLO-30');
  });

  it('renders nothing for a Point', () => {
    renderWithMantine(
      <ElevationProfileChart geometry={{ type: 'Point', coordinates: [-62.7, -32.6] }} />,
    );
    expect(screen.queryByTestId('elevation-profile')).not.toBeInTheDocument();
  });
});
