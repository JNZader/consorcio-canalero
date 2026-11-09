import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

// geeFloodAnalysis imports apiFetch from ./core — mock that module.
vi.mock('../../src/lib/api/core', () => ({
  apiFetch: apiFetchMock,
  GEE_TIMEOUT: 1000,
  API_URL: 'http://test',
  API_PREFIX: '/api/v2',
  DEFAULT_TIMEOUT: 1000,
}));

vi.mock('../../src/lib/notifications', () => ({
  showError: vi.fn(),
  showInfo: vi.fn(),
  showSuccess: vi.fn(),
}));

import { ImageExplorerFloodAnalysis } from '../../src/components/admin/images/ImageExplorerFloodAnalysis';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

const floodTile = {
  tile_url: 'https://earthengine.googleapis.com/v1/projects/x/maps/flood/tiles/{z}/{x}/{y}',
  target_date: '2024-01-10',
  sensor: 'Sentinel-2',
  visualization: 'inundacion',
  visualization_description: 'Inundación',
  collection: 'COPERNICUS/S2_SR_HARMONIZED',
  images_count: 1,
  dates_available: ['2024-01-10'],
};

const normalTile = {
  ...floodTile,
  tile_url: 'https://earthengine.googleapis.com/v1/projects/x/maps/normal/tiles/{z}/{x}/{y}',
  target_date: '2024-01-20',
  visualization: 'rgb',
  visualization_description: 'RGB',
};

describe('ImageExplorerFloodAnalysis', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it('submits flood analysis, polls, and pushes comparison sides', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();

    apiFetchMock
      .mockResolvedValueOnce({
        id: '11111111-1111-1111-1111-111111111111',
        tipo: 'flood',
        estado: 'pending',
      })
      .mockResolvedValueOnce({
        id: '11111111-1111-1111-1111-111111111111',
        tipo: 'flood',
        estado: 'completed',
        resultado: {
          method: 'fusion',
          comparison: {
            normal_rgb: normalTile,
            flood_detection: floodTile,
          },
        },
      });

    render(
      <ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />,
      { wrapper }
    );

    await user.type(screen.getByLabelText(/Fecha de crecida/i), '2024-01-10');
    await user.type(screen.getByLabelText(/Fecha de referencia/i), '2024-01-20');

    await user.click(screen.getByRole('button', { name: /Correr detección/i }));

    await waitFor(() => {
      expect(onSetLeft).toHaveBeenCalled();
      expect(onSetRight).toHaveBeenCalled();
    });

    expect(apiFetchMock.mock.calls[0][0]).toBe('/geo/gee/analysis');
    expect(apiFetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST' });
    const body = JSON.parse(apiFetchMock.mock.calls[0][1].body as string);
    expect(body).toEqual({
      tipo: 'flood',
      parametros: {
        start_date: '2024-01-10',
        end_date: '2024-01-20',
        method: 'fusion',
      },
    });

    expect(onSetLeft.mock.calls[0][0].target_date).toBe('2024-01-20');
    expect(onSetRight.mock.calls[0][0].visualization).toBe('inundacion');
  });

  it('blocks fusion when span is too short', async () => {
    const user = userEvent.setup();
    render(
      <ImageExplorerFloodAnalysis onSetLeftImage={vi.fn()} onSetRightImage={vi.fn()} />,
      { wrapper }
    );

    await user.type(screen.getByLabelText(/Fecha de crecida/i), '2024-01-10');
    await user.type(screen.getByLabelText(/Fecha de referencia/i), '2024-01-12');

    expect(screen.getByRole('alert')).toHaveTextContent(/5 días|6 días/i);
    expect(screen.getByRole('button', { name: /Correr detección/i })).toBeDisabled();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });
});
