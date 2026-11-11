import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

// geeFloodAnalysis importa apiFetch de ./core — mockear ese módulo para
// controlar los GET de estado del poll sin tocar la red.
vi.mock('../../src/lib/api/core', () => ({
  apiFetch: apiFetchMock,
  GEE_TIMEOUT: 1000,
}));

import {
  type FloodAnalysisResultado,
  fusionComparisonReady,
  pickFloodComparisonSides,
  pollFloodAnalysisUntilDone,
  validateFloodAnalysisDates,
} from '../../src/lib/api/geeFloodAnalysis';

describe('validateFloodAnalysisDates', () => {
  it('rejects end before or equal to start', () => {
    expect(validateFloodAnalysisDates('2024-01-10', '2024-01-10', 'sar_only')).toMatch(/1 día/);
    expect(validateFloodAnalysisDates('2024-01-10', '2024-01-09', 'fusion')).toMatch(/1 día/);
  });

  it('allows next-day span for fusion (day-to-day deltas)', () => {
    expect(validateFloodAnalysisDates('2024-01-01', '2024-01-02', 'fusion')).toBeNull();
    expect(validateFloodAnalysisDates('2024-01-01', '2024-01-07', 'fusion')).toBeNull();
  });

  it('allows short span for sar_only', () => {
    expect(validateFloodAnalysisDates('2024-01-01', '2024-01-03', 'sar_only')).toBeNull();
  });
});

describe('fusionComparisonReady', () => {
  it('matches backend end-start >= 1', () => {
    expect(fusionComparisonReady('2024-01-01', '2024-01-01')).toBe(false);
    expect(fusionComparisonReady('2024-01-01', '2024-01-02')).toBe(true);
  });
});

describe('pickFloodComparisonSides', () => {
  const tile = (date: string, vis: string) => ({
    tile_url: `https://earthengine.googleapis.com/v1/projects/x/maps/${date}/tiles/{z}/{x}/{y}`,
    target_date: date,
    sensor: 'Sentinel-2',
    visualization: vis,
    visualization_description: vis,
    collection: 'COPERNICUS/S2_SR_HARMONIZED',
    images_count: 1,
    dates_available: [date],
  });

  it('prefers comparison normal_rgb / flood_detection', () => {
    const resultado: FloodAnalysisResultado = {
      method: 'fusion',
      comparison: {
        normal_rgb: tile('2024-01-20', 'rgb'),
        flood_detection: tile('2024-01-10', 'inundacion'),
        flood_rgb: tile('2024-01-10', 'rgb'),
      },
    };
    const sides = pickFloodComparisonSides(resultado);
    expect(sides.source).toBe('comparison');
    expect(sides.left?.target_date).toBe('2024-01-20');
    expect(sides.right?.visualization).toBe('inundacion');
  });

  it('falls back to flood_rgb when flood_detection missing', () => {
    const resultado: FloodAnalysisResultado = {
      comparison: {
        normal_rgb: tile('2024-01-20', 'rgb'),
        flood_rgb: tile('2024-01-10', 'rgb'),
      },
    };
    const sides = pickFloodComparisonSides(resultado);
    expect(sides.right?.visualization).toBe('rgb');
  });

  it('uses sar as right when no comparison', () => {
    const resultado: FloodAnalysisResultado = {
      method: 'sar_only',
      sar: {
        ...tile('2024-01-10', 'vv_flood'),
        sensor: 'Sentinel-1',
        collection: 'COPERNICUS/S1_GRD',
      },
    };
    const sides = pickFloodComparisonSides(resultado);
    expect(sides.source).toBe('sar');
    expect(sides.left).toBeNull();
    expect(sides.right?.sensor).toBe('Sentinel-1');
  });

  it('returns empty when resultado has no tiles', () => {
    expect(pickFloodComparisonSides({ method: 'fusion' }).source).toBe('empty');
    expect(pickFloodComparisonSides(null).source).toBe('empty');
  });
});

describe('pollFloodAnalysisUntilDone', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it('resuelve tras 2 rechazos transitorios seguidos de éxito', async () => {
    vi.useFakeTimers();
    try {
      apiFetchMock
        .mockRejectedValueOnce(new Error('503 Service Unavailable'))
        .mockRejectedValueOnce(new Error('La solicitud excedió el tiempo límite (300s)'))
        .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'completed' });

      const promise = pollFloodAnalysisUntilDone('job-1');
      // Drena los backoffs incrementales (1s tras el primer rechazo, 2s tras el segundo).
      await vi.runAllTimersAsync();

      await expect(promise).resolves.toMatchObject({ id: 'job-1', estado: 'completed' });
      expect(apiFetchMock).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it('rechaza al tercer rechazo transitorio consecutivo', async () => {
    vi.useFakeTimers();
    try {
      apiFetchMock.mockRejectedValue(new Error('502 Bad Gateway'));

      const promise = pollFloodAnalysisUntilDone('job-1');
      // Registrar la expectativa antes de avanzar evita la unhandled rejection.
      const expectation = expect(promise).rejects.toThrow('502 Bad Gateway');
      await vi.runAllTimersAsync();
      await expectation;

      expect(apiFetchMock).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it('AbortError corta inmediato, sin reintento', async () => {
    apiFetchMock.mockRejectedValue(new DOMException('Aborted', 'AbortError'));

    await expect(pollFloodAnalysisUntilDone('job-1')).rejects.toMatchObject({
      name: 'AbortError',
    });
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
  });

  it('un GET exitoso resetea el contador de transitorios', async () => {
    vi.useFakeTimers();
    try {
      apiFetchMock
        .mockRejectedValueOnce(new Error('503'))
        .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'running' })
        .mockRejectedValueOnce(new Error('503'))
        .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'completed' });

      // Sin reset, el segundo 503 sería el tercer transitorio acumulado y mataría el poll.
      const promise = pollFloodAnalysisUntilDone('job-1', { intervalMs: 1000 });
      await vi.runAllTimersAsync();

      await expect(promise).resolves.toMatchObject({ estado: 'completed' });
      expect(apiFetchMock).toHaveBeenCalledTimes(4);
    } finally {
      vi.useRealTimers();
    }
  });
});
