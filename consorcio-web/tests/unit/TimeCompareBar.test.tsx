import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TimeCompareBar } from '../../src/components/map2d/TimeCompareBar';
import type { SelectedImage } from '../../src/hooks/useSelectedImage';

vi.mock('../../src/lib/api/mapImage', () => ({
  mapImageApi: {
    getImageParams: vi.fn(async () => ({ imagen_principal: null, imagen_comparacion: null })),
    saveImagenPrincipal: vi.fn(async () => ({})),
    saveImagenComparacion: vi.fn(async () => ({})),
    getPublicCurrentImage: vi.fn(async () => ({ status: 'unavailable' })),
    getPublicCurrentComparison: vi.fn(async () => ({ status: 'unavailable' })),
  },
}));

vi.mock('../../src/lib/api/timeLayers', async () => {
  const actual = await vi.importActual<typeof import('../../src/lib/api/timeLayers')>(
    '../../src/lib/api/timeLayers'
  );
  return {
    ...actual,
    fetchAnnualSentinel: vi.fn(),
    fetchJrcYear: vi.fn(),
    fetchJrcOccurrence: vi.fn(),
  };
});

import { fetchAnnualSentinel, fetchJrcOccurrence } from '../../src/lib/api/timeLayers';

function image(year: number, sensor: SelectedImage['sensor'] = 'Sentinel-2'): SelectedImage {
  return {
    tile_url: 'https://earthengine.googleapis.com/v1/projects/p/maps/m/tiles/{z}/{x}/{y}',
    target_date: `${year}-07-02`,
    sensor,
    visualization: sensor === 'JRC' ? 'occurrence' : 'rgb',
    visualization_description: `imagen ${year}`,
    collection: 'test',
    images_count: 4,
    days_buffer: sensor === 'JRC' ? 1 : 182,
    max_cloud: sensor === 'JRC' ? null : 60,
    mode: 'composite',
    selected_at: '2026-11-02T00:00:00Z',
  };
}

function renderBar(onViewModeChange = vi.fn()) {
  render(
    <MantineProvider env="test">
      <TimeCompareBar onViewModeChange={onViewModeChange} />
    </MantineProvider>
  );
  return onViewModeChange;
}

describe('TimeCompareBar', () => {
  beforeEach(() => {
    vi.mocked(window.localStorage.setItem).mockClear();
    vi.mocked(fetchAnnualSentinel).mockReset();
    vi.mocked(fetchJrcOccurrence).mockReset();
  });

  function writes(key: string): string[] {
    return vi
      .mocked(window.localStorage.setItem)
      .mock.calls.filter((call) => call[0] === key)
      .map((call) => String(call[1]));
  }

  it('loads both annual composites and opens the comparison', async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAnnualSentinel).mockImplementation(async (year) => image(year));
    const onViewModeChange = renderBar();

    await user.click(screen.getByRole('button', { name: 'Ver comparación' }));

    expect(fetchAnnualSentinel).toHaveBeenCalledTimes(2);
    expect(onViewModeChange).toHaveBeenCalledWith('comparison');
    await waitFor(() => {
      expect(writes('consorcio_image_comparison').length).toBeGreaterThan(0);
    });
    const stored = JSON.parse(writes('consorcio_image_comparison').at(-1) ?? '{}');
    expect(stored.left.days_buffer).toBe(182);
    expect(stored.left.mode).toBe('composite');
    expect(stored.right.mode).toBe('composite');
    expect(stored.enabled).toBe(true);
  });

  it('shows the long-term JRC recurrence as a single image', async () => {
    const user = userEvent.setup();
    vi.mocked(fetchJrcOccurrence).mockResolvedValue(image(2021, 'JRC'));
    const onViewModeChange = renderBar();

    await user.click(screen.getByRole('radio', { name: 'Agua JRC' }));
    await user.click(screen.getByRole('button', { name: 'Recurrencia histórica' }));

    expect(fetchJrcOccurrence).toHaveBeenCalledOnce();
    expect(onViewModeChange).toHaveBeenCalledWith('single');
    await waitFor(() => {
      expect(writes('consorcio_selected_image').length).toBeGreaterThan(0);
    });
    const stored = JSON.parse(writes('consorcio_selected_image').at(-1) ?? '{}');
    expect(stored.sensor).toBe('JRC');
    expect(stored.visualization).toBe('occurrence');
  });

  it('keeps every month, including Dic, in a wrapping row', () => {
    renderBar();
    for (let month = 1; month <= 12; month += 1) {
      expect(screen.getByTestId(`s2-month-${month}`)).toBeInTheDocument();
    }
    const dic = screen.getByTestId('s2-month-12');
    const year = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1;
    if (currentMonth < 12) {
      expect(dic).toBeDisabled();
    } else {
      expect(dic).toBeEnabled();
    }
    expect(year).toBeGreaterThan(2000);
  });

  it('tells an anonymous visitor that the comparison needs an operator', async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAnnualSentinel).mockRejectedValue(
      Object.assign(new Error('no'), { status: 401 })
    );
    renderBar();

    await user.click(screen.getByRole('button', { name: 'Ver comparación' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('entrar como operador');
  });
});
