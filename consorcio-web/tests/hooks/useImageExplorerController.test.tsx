import { act, renderHook, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock, updateTileLayerMock, fitZonaMock, loggerMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  updateTileLayerMock: vi.fn(),
  fitZonaMock: vi.fn(),
  loggerMock: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

vi.mock('../../src/lib/api', () => ({
  API_URL: 'http://localhost:8000',
  GEE_TIMEOUT: 300000,
  apiFetch: apiFetchMock,
  getAuthToken: vi.fn().mockResolvedValue('token'),
}));

vi.mock('../../src/lib/logger', () => ({ logger: loggerMock }));

vi.mock('../../src/components/admin/images/useImageExplorerMap', async () => {
  const { useRef } = await import('react');
  return {
    useImageExplorerMap: () => {
      const mapRef = useRef<HTMLDivElement>(null);
      return { mapRef, updateTileLayer: updateTileLayerMock, fitZona: fitZonaMock };
    },
  };
});

vi.mock('../../src/hooks/useSelectedImage', async () => {
  const { useCallback, useState } = await import('react');
  return {
    useSelectedImage: () => {
      const [selectedImage, setSelectedImage] = useState<unknown>(null);
      const clearSelectedImage = useCallback(() => setSelectedImage(null), []);
      return { selectedImage, setSelectedImage, clearSelectedImage };
    },
  };
});

vi.mock('../../src/hooks/useImageComparison', async () => {
  const { useCallback, useState } = await import('react');
  return {
    useImageComparison: () => {
      const [comparison, setComparison] = useState<Record<string, unknown> | null>(null);
      const setLeftImage = useCallback(
        (img: unknown) => setComparison((prev) => ({ ...(prev ?? {}), left: img })),
        []
      );
      const setRightImage = useCallback(
        (img: unknown) => setComparison((prev) => ({ ...(prev ?? {}), right: img })),
        []
      );
      const clearComparison = useCallback(() => setComparison(null), []);
      return { comparison, setLeftImage, setRightImage, clearComparison, isReady: false };
    },
  };
});

import { useImageExplorerController } from '../../src/components/admin/images/useImageExplorerController';

const API_BASE = '/geo/gee/images';

type Call = { url: string; signal?: AbortSignal };

interface ApiCalls {
  visualizations: Call[];
  floodList: Call[];
  flood: Call[];
  dates: Call[];
  scenes: Call[];
  dayImage: Call[];
}

let calls: ApiCalls;

/** Classify an apiFetch endpoint into one of the explorer's six request kinds. */
function classify(url: string): keyof ApiCalls | null {
  if (!url.startsWith(`${API_BASE}/`)) return null;
  const rest = url.slice(API_BASE.length);
  if (rest.startsWith('/historic-floods/')) return 'flood';
  if (rest.startsWith('/historic-floods')) return 'floodList';
  if (rest.startsWith('/visualizations')) return 'visualizations';
  if (rest.startsWith('/available-dates')) return 'dates';
  if (rest.startsWith('/scenes/')) return 'scenes';
  return 'dayImage';
}

const imageResult = (overrides: Record<string, unknown> = {}) => ({
  tile_url: 'https://tiles.test/day',
  target_date: '2026-03-10',
  dates_available: ['2026-03-10'],
  images_count: 1,
  visualization: 'rgb',
  visualization_description: 'RGB',
  sensor: 'sentinel2',
  collection: 'COPERNICUS/S2',
  ...overrides,
});

const floodResult = (date: string) =>
  imageResult({
    tile_url: 'https://tiles.test/flood',
    target_date: date,
    flood_info: {
      id: 'f1',
      name: 'Inundacion 2016',
      date,
      description: 'Evento historico',
      severity: 'alta',
    },
  });

/** Route responses per request kind; every handler is persistent (see repo gotcha (a)). */
function stubApi(
  overrides: Partial<Record<keyof ApiCalls, (url: string, signal?: AbortSignal) => unknown>> = {}
) {
  apiFetchMock.mockImplementation(async (url: string, options?: { signal?: AbortSignal }) => {
    const kind = classify(url);
    if (!kind) throw new Error(`Unexpected endpoint: ${url}`);
    calls[kind].push({ url, signal: options?.signal });
    const handler = overrides[kind];
    if (handler) return handler(url, options?.signal);
    switch (kind) {
      case 'visualizations':
        return [{ id: 'rgb', description: 'Color natural' }];
      case 'floodList':
        return {
          floods: [
            {
              id: 'f1',
              name: 'Inundacion 2016',
              date: '2016-04-20',
              description: 'x',
              severity: 'alta',
            },
          ],
        };
      case 'flood':
        return floodResult('2016-04-20');
      case 'dates':
        return { dates: ['2026-03-10', '2026-03-12'] };
      case 'scenes':
        return {
          scenes: [
            { ...imageResult(), id: 's1', label: 'Escena 1', tile_url: 'https://tiles.test/s1' },
          ],
        };
      default:
        return imageResult();
    }
  });
}

async function mountController(wrapper?: typeof StrictMode) {
  const rendered = renderHook(() => useImageExplorerController(), wrapper ? { wrapper } : undefined);
  await waitFor(() => expect(rendered.result.current.loadingDates).toBe(false));
  return rendered;
}

const lastUrl = (kind: keyof ApiCalls) => calls[kind].at(-1)?.url ?? '';

beforeEach(() => {
  vi.clearAllMocks();
  calls = { visualizations: [], floodList: [], flood: [], dates: [], scenes: [], dayImage: [] };
  stubApi();
});

describe('useImageExplorerController — bootstrap', () => {
  it('loads visualizations, historic floods and available dates on mount', async () => {
    const { result } = await mountController();

    await waitFor(() => expect(result.current.historicFloods).toHaveLength(1));
    expect(result.current.visOptions).toEqual([{ value: 'rgb', label: 'Color natural' }]);
    expect([...result.current.availableDatesSet]).toEqual(['2026-03-10', '2026-03-12']);
    expect(result.current.selectedDay).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('drops malformed visualizations/floods and dedupes+sorts available dates', async () => {
    stubApi({
      visualizations: () => [{ id: 'rgb', description: 'ok' }, { id: 42 }, null, 'nope'],
      floodList: () => ({ floods: [{ id: 'f1', name: 'ok', date: '2016-04-20' }, { id: 'x' }] }),
      dates: () => ({ dates: ['2026-03-12', '2026-03-10', '2026-03-12', 7, null] }),
    });

    const { result } = await mountController();

    await waitFor(() => expect(result.current.historicFloods).toHaveLength(1));
    expect(result.current.visOptions).toHaveLength(1);
    expect([...result.current.availableDatesSet]).toEqual(['2026-03-10', '2026-03-12']);
  });

  it('keeps empty lists and logs when the bootstrap endpoints fail', async () => {
    stubApi({
      visualizations: () => Promise.reject(new Error('boom')),
      floodList: () => Promise.reject(new Error('boom')),
      dates: () => Promise.reject(new Error('boom')),
    });

    const { result } = await mountController();

    expect(result.current.historicFloods).toEqual([]);
    expect(result.current.availableDatesSet.size).toBe(0);
    expect(loggerMock.error).toHaveBeenCalled();
  });

  it('falls back to SAR visualizations for sentinel1', async () => {
    const { result } = await mountController();

    act(() => result.current.setSensor('sentinel1'));

    expect(result.current.visOptions.map((option) => option.value)).toEqual(['vv', 'vv_flood']);
  });
});

describe('useImageExplorerController — historic flood suppression', () => {
  it('does not re-fetch the generic day image after loading a historic flood', async () => {
    const { result } = await mountController();

    await act(async () => {
      await result.current.loadHistoricFlood('f1');
    });

    await waitFor(() => expect(result.current.selectedDay).toBe('2016-04-20'));
    expect(result.current.result?.tile_url).toBe('https://tiles.test/flood');
    // The generic day effect must have been suppressed for the flood's day.
    expect(calls.dayImage).toHaveLength(0);
    expect(result.current.calendarYear).toBe(2016);
    expect(result.current.calendarMonth).toBe(3);
  });

  it('still fetches another day after loading the SAME flood twice (ref stores the day, not a flag)', async () => {
    const { result } = await mountController();

    await act(async () => {
      await result.current.loadHistoricFlood('f1');
    });
    await waitFor(() => expect(result.current.selectedDay).toBe('2016-04-20'));

    // Second load: setSelectedDay with the same value is an Object.is no-op, so
    // the day effect never runs and the suppression stays pending.
    await act(async () => {
      await result.current.loadHistoricFlood('f1');
    });
    expect(calls.dayImage).toHaveLength(0);

    // A different day MUST fetch — a boolean guard would have swallowed it.
    await act(async () => {
      result.current.setSelectedDay('2016-04-21');
    });

    await waitFor(() => expect(calls.dayImage).toHaveLength(1));
    expect(lastUrl('dayImage')).toContain('target_date=2016-04-21');
  });

  it('handleSelectDay clears a pending suppression so an explicit click always fetches', async () => {
    const { result } = await mountController();

    await act(async () => {
      await result.current.loadHistoricFlood('f1');
    });
    await waitFor(() => expect(result.current.selectedDay).toBe('2016-04-20'));
    // Leaves suppression pending for 2016-04-20.
    await act(async () => {
      await result.current.loadHistoricFlood('f1');
    });
    // Move away without clearing the ref: the pending day is still 2016-04-20.
    await act(async () => {
      result.current.setSelectedDay('2016-04-21');
    });
    await waitFor(() => expect(calls.dayImage).toHaveLength(1));

    // Explicit calendar click on the suppressed day must fetch anyway.
    await act(async () => {
      result.current.handleSelectDay('2016-04-20');
    });

    await waitFor(() => expect(calls.dayImage).toHaveLength(2));
    expect(lastUrl('dayImage')).toContain('target_date=2016-04-20');
    expect(result.current.selectedSceneId).toBeNull();
  });

  it('reports the error and keeps the previous result when the flood request fails', async () => {
    stubApi({ flood: () => Promise.reject(new Error('GEE caido')) });
    const { result } = await mountController();

    await act(async () => {
      await result.current.loadHistoricFlood('f1');
    });

    expect(result.current.error).toBe('GEE caido');
    expect(result.current.result).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.selectedDay).toBeNull();
  });
});

describe('useImageExplorerController — stale responses (AbortController)', () => {
  it('aborts the in-flight image request and ignores its late response', async () => {
    let resolveSlow: ((value: unknown) => void) | undefined;
    stubApi({
      dayImage: (url) => {
        if (url.includes('2026-03-10')) {
          return new Promise((resolve) => {
            resolveSlow = resolve;
          });
        }
        return imageResult({ tile_url: 'https://tiles.test/fast', target_date: '2026-03-12' });
      },
    });
    const { result } = await mountController();

    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(calls.dayImage).toHaveLength(1));

    await act(async () => {
      result.current.handleSelectDay('2026-03-12');
    });
    await waitFor(() => expect(result.current.result?.tile_url).toBe('https://tiles.test/fast'));

    // The first request was aborted when the second one started...
    expect(calls.dayImage[0].signal?.aborted).toBe(true);

    // ...and its late response must not clobber the newer result.
    await act(async () => {
      resolveSlow?.(imageResult({ tile_url: 'https://tiles.test/slow' }));
      await Promise.resolve();
    });

    expect(result.current.result?.tile_url).toBe('https://tiles.test/fast');
    expect(updateTileLayerMock).not.toHaveBeenCalledWith('https://tiles.test/slow');
    expect(result.current.loading).toBe(false);
  });

  it('a late failure of an aborted request does not surface an error', async () => {
    let rejectSlow: ((reason: Error) => void) | undefined;
    stubApi({
      dayImage: (url) => {
        if (url.includes('2026-03-10')) {
          return new Promise((_resolve, reject) => {
            rejectSlow = reject;
          });
        }
        return imageResult({ tile_url: 'https://tiles.test/fast' });
      },
    });
    const { result } = await mountController();

    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(calls.dayImage).toHaveLength(1));
    await act(async () => {
      result.current.handleSelectDay('2026-03-12');
    });
    await waitFor(() => expect(result.current.result?.tile_url).toBe('https://tiles.test/fast'));

    await act(async () => {
      rejectSlow?.(new Error('stale failure'));
      await Promise.resolve();
    });

    expect(result.current.error).toBeNull();
  });

  it('aborts the available-dates request on unmount', async () => {
    const { unmount } = await mountController();
    const datesSignal = calls.dates.at(-1)?.signal;
    expect(datesSignal?.aborted).toBe(false);

    unmount();

    expect(datesSignal?.aborted).toBe(true);
  });

  it('aborts the scenes request when the sensor changes', async () => {
    const { result } = await mountController();
    await act(async () => {
      result.current.setSensor('landsat8');
    });
    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(calls.scenes).toHaveLength(1));
    const scenesSignal = calls.scenes[0].signal;

    await act(async () => {
      result.current.setSensor('landsat7');
    });

    expect(scenesSignal?.aborted).toBe(true);
  });
});

describe('useImageExplorerController — calendar navigation', () => {
  it('goes from January back to December of the PREVIOUS year (one year, not two)', async () => {
    const { result } = await mountController(StrictMode);

    await act(async () => {
      result.current.handleMonthYearChange(2020, 0);
    });
    await act(async () => {
      result.current.handlePrevMonth();
    });

    expect(result.current.calendarMonth).toBe(11);
    expect(result.current.calendarYear).toBe(2019);
    expect(result.current.selectedDay).toBeNull();
  });

  it('goes from December forward to January of the NEXT year', async () => {
    const { result } = await mountController(StrictMode);

    await act(async () => {
      result.current.handleMonthYearChange(2020, 11);
    });
    await act(async () => {
      result.current.handleNextMonth();
    });

    expect(result.current.calendarMonth).toBe(0);
    expect(result.current.calendarYear).toBe(2021);
  });

  it('moves within the same year for non-boundary months', async () => {
    const { result } = await mountController();

    await act(async () => {
      result.current.handleMonthYearChange(2020, 5);
    });
    await act(async () => {
      result.current.handlePrevMonth();
    });
    expect(result.current).toMatchObject({ calendarYear: 2020, calendarMonth: 4 });

    await act(async () => {
      result.current.handleNextMonth();
    });
    expect(result.current).toMatchObject({ calendarYear: 2020, calendarMonth: 5 });
  });

  it('never advances past the current month', async () => {
    const now = new Date();
    const { result } = await mountController();

    await act(async () => {
      result.current.handleMonthYearChange(now.getFullYear(), now.getMonth());
    });
    await act(async () => {
      result.current.handleNextMonth();
    });

    expect(result.current.calendarYear).toBe(now.getFullYear());
    expect(result.current.calendarMonth).toBe(now.getMonth());
  });

  it('handleMonthYearChange resets day, result and scenes', async () => {
    const { result } = await mountController();
    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(result.current.result).not.toBeNull());

    await act(async () => {
      result.current.handleMonthYearChange(2019, 2);
    });

    expect(result.current.result).toBeNull();
    expect(result.current.selectedDay).toBeNull();
    expect(result.current.scenes).toEqual([]);
    expect(result.current.selectedSceneId).toBeNull();
  });
});

describe('useImageExplorerController — request parameters', () => {
  it('uses days_buffer=1, mode=scene and max_cloud for optical sensors', async () => {
    const { result } = await mountController();

    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(calls.dayImage).toHaveLength(1));

    const url = lastUrl('dayImage');
    expect(url.startsWith(`${API_BASE}/sentinel2?`)).toBe(true);
    expect(url).toContain('target_date=2026-03-10');
    expect(url).toContain('days_buffer=1');
    expect(url).toContain('mode=scene');
    expect(url).toContain('max_cloud=80');
  });

  it('sends mode=composite and days_buffer=20 only for landsat7 in composite mode', async () => {
    const { result } = await mountController();

    await act(async () => {
      result.current.setSensor('landsat7');
      result.current.setCompositionMode('composite');
    });
    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(calls.dayImage).toHaveLength(1));
    expect(lastUrl('dayImage')).toContain('mode=composite');
    expect(lastUrl('dayImage')).toContain('days_buffer=20');
    expect(lastUrl('dayImage').startsWith(`${API_BASE}/landsat7?`)).toBe(true);

    // Same composite mode on another landsat must NOT get the 20-day buffer.
    await act(async () => {
      result.current.setSensor('landsat8');
    });
    await waitFor(() => expect(calls.dayImage.length).toBeGreaterThan(1));
    expect(lastUrl('dayImage')).toContain('mode=scene');
    expect(lastUrl('dayImage')).toContain('days_buffer=1');
  });

  it('omits max_cloud for sentinel1 (radar) in both the image and the dates request', async () => {
    const { result } = await mountController();

    await act(async () => {
      result.current.setSensor('sentinel1');
    });
    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(calls.dayImage).toHaveLength(1));

    expect(lastUrl('dayImage')).not.toContain('max_cloud');
    expect(lastUrl('dates')).not.toContain('max_cloud');
    expect(lastUrl('dates')).toContain('sensor=sentinel1');
  });

  it('re-requests available dates with the new max_cloud (month is 1-based)', async () => {
    const { result } = await mountController();

    await act(async () => {
      result.current.handleMonthYearChange(2026, 2);
    });
    await waitFor(() => expect(lastUrl('dates')).toContain('year=2026'));

    expect(lastUrl('dates')).toContain('month=3');

    await act(async () => {
      result.current.setMaxCloud('10');
    });
    await waitFor(() => expect(lastUrl('dates')).toContain('max_cloud=10'));
  });

  it('surfaces the image error message and clears loading', async () => {
    stubApi({ dayImage: () => Promise.reject(new Error('Sin imagenes')) });
    const { result } = await mountController();

    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });

    await waitFor(() => expect(result.current.error).toBe('Sin imagenes'));
    expect(result.current.loading).toBe(false);
    expect(result.current.result).toBeNull();
  });

  it('falls back to a generic message for non-Error rejections', async () => {
    stubApi({ dayImage: () => Promise.reject('kaboom') });
    const { result } = await mountController();

    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });

    await waitFor(() => expect(result.current.error).toBe('Error desconocido'));
  });
});

describe('useImageExplorerController — scenes', () => {
  it('requests scenes only for landsat sensors', async () => {
    const { result } = await mountController();

    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(calls.dayImage).toHaveLength(1));
    expect(calls.scenes).toHaveLength(0);

    await act(async () => {
      result.current.setSensor('landsat8');
    });
    await waitFor(() => expect(calls.scenes).toHaveLength(1));
    expect(lastUrl('scenes').startsWith(`${API_BASE}/scenes/landsat8?`)).toBe(true);
    await waitFor(() => expect(result.current.scenes).toHaveLength(1));
  });

  it('clears scenes when the sensor stops being landsat or the day is cleared', async () => {
    const { result } = await mountController();
    await act(async () => {
      result.current.setSensor('landsat8');
    });
    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(result.current.scenes).toHaveLength(1));

    await act(async () => {
      result.current.setSensor('sentinel2');
    });
    expect(result.current.scenes).toEqual([]);

    await act(async () => {
      result.current.setSensor('landsat8');
    });
    await waitFor(() => expect(result.current.scenes).toHaveLength(1));

    await act(async () => {
      result.current.setSelectedDay(null);
    });
    await waitFor(() => expect(result.current.scenes).toEqual([]));
    expect(result.current.selectedSceneId).toBeNull();
  });

  it('drops malformed scenes and keeps an empty list when the request fails', async () => {
    stubApi({
      scenes: () => ({ scenes: [{ id: 's1' }, null, 'x'] }),
    });
    const { result } = await mountController();
    await act(async () => {
      result.current.setSensor('landsat8');
    });
    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(calls.scenes).toHaveLength(1));
    expect(result.current.scenes).toEqual([]);

    stubApi({ scenes: () => Promise.reject(new Error('scenes down')) });
    await act(async () => {
      result.current.handleSelectDay('2026-03-12');
    });
    await waitFor(() => expect(loggerMock.error).toHaveBeenCalled());
    expect(result.current.scenes).toEqual([]);
  });

  it('handleSelectScene swaps the result, marks the scene active and repaints the tile', async () => {
    const { result } = await mountController();
    await act(async () => {
      result.current.setSensor('landsat8');
    });
    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(result.current.scenes).toHaveLength(1));

    const scene = result.current.scenes[0];
    act(() => {
      result.current.handleSelectScene(scene);
    });

    expect(result.current.result).toEqual(scene);
    expect(result.current.selectedSceneId).toBe('s1');
    expect(updateTileLayerMock).toHaveBeenCalledWith('https://tiles.test/s1');
  });
});

describe('useImageExplorerController — image selection and comparison', () => {
  it('selects the current result as principal image and reflects it in isCurrentImageSelected', async () => {
    const { result } = await mountController();

    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(result.current.result).not.toBeNull());
    expect(result.current.isCurrentImageSelected).toBe(false);

    act(() => {
      result.current.handleSelectImage();
    });

    await waitFor(() => expect(result.current.isCurrentImageSelected).toBe(true));

    act(() => {
      result.current.clearSelectedImage();
    });
    expect(result.current.isCurrentImageSelected).toBe(false);
  });

  // Regression guard: the flag used to be a bare `?.tile_url === ?.tile_url`,
  // so with no result AND no selected image both sides were `undefined` and it
  // read `true` ("already selected") on an empty explorer. Harmless while the
  // panel renders that button under `{result && …}`, a trap the moment anyone
  // consumes the flag outside that guard.
  it('reads false when there is neither a result nor a selected image', async () => {
    const { result } = await mountController();

    expect(result.current.result).toBeNull();
    expect(result.current.selectedImage).toBeNull();
    expect(result.current.isCurrentImageSelected).toBe(false);
  });

  it('ignores selection handlers when there is no result', async () => {
    const { result } = await mountController();

    act(() => {
      result.current.handleSelectImage();
      result.current.handleSetLeftImage();
      result.current.handleSetRightImage();
    });

    expect(result.current.selectedImage).toBeNull();
    expect(result.current.comparison).toBeNull();
  });

  it('fills left and right comparison slots from the current result', async () => {
    const { result } = await mountController();
    await act(async () => {
      result.current.handleSelectDay('2026-03-10');
    });
    await waitFor(() => expect(result.current.result).not.toBeNull());

    act(() => {
      result.current.handleSetLeftImage();
    });
    act(() => {
      result.current.handleSetRightImage();
    });

    expect(result.current.comparison).toMatchObject({
      left: { tile_url: 'https://tiles.test/day' },
      right: { tile_url: 'https://tiles.test/day' },
    });

    act(() => {
      result.current.clearComparison();
    });
    expect(result.current.comparison).toBeNull();
  });
});
