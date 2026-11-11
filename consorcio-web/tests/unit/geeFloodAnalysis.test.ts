import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

// geeFloodAnalysis importa apiFetch de ./core — mockear ese módulo para
// controlar los GET de estado del poll sin tocar la red.
vi.mock('../../src/lib/api/core', () => ({
  apiFetch: apiFetchMock,
  GEE_TIMEOUT: 1000,
}));

import {
  type FloodAnalysisMethod,
  type FloodAnalysisResultado,
  floodAnalysisErrorCopy,
  fusionComparisonReady,
  getFloodAnalysis,
  isAuthError,
  pickFloodComparisonSides,
  pollFloodAnalysisUntilDone,
  validateFloodAnalysisDates,
} from '../../src/lib/api/geeFloodAnalysis';
import { QueryError } from '../../src/lib/queryError';

describe('validateFloodAnalysisDates', () => {
  // Backend (gee_tasks_support.build_flood_analysis_result): the >=1-day span
  // gate only guards the fusion comparison branch; sar_only / optical_only
  // accept same-day dates. Method × span matrix.
  const matrix: Array<[FloodAnalysisMethod, string, string, RegExp | null]> = [
    ['fusion', '2024-01-10', '2024-01-10', /1 día/],
    ['sar_only', '2024-01-10', '2024-01-10', null],
    ['optical_only', '2024-01-10', '2024-01-10', null],
    ['fusion', '2024-01-10', '2024-01-11', null],
  ];

  it.each(matrix)('method matrix %s %s → %s', (method, start, end, expected) => {
    const result = validateFloodAnalysisDates(start, end, method);
    if (expected === null) {
      expect(result).toBeNull();
    } else {
      expect(result).toMatch(expected);
    }
  });

  it('discriminates by method: span-0 sar_only passes AND span-0 fusion fails', () => {
    expect(validateFloodAnalysisDates('2024-01-01', '2024-01-01', 'sar_only')).toBeNull();
    expect(validateFloodAnalysisDates('2024-01-01', '2024-01-01', 'fusion')).toMatch(/1 día/);
  });

  it('allows longer spans for any method (day-to-day deltas)', () => {
    expect(validateFloodAnalysisDates('2024-01-01', '2024-01-07', 'fusion')).toBeNull();
    expect(validateFloodAnalysisDates('2024-01-01', '2024-01-03', 'sar_only')).toBeNull();
    expect(validateFloodAnalysisDates('2024-01-01', '2024-01-02', 'optical_only')).toBeNull();
  });

  it('rejects a reference before the flood date for every method', () => {
    expect(validateFloodAnalysisDates('2024-01-10', '2024-01-09', 'fusion')).toMatch(/1 día/);
    expect(validateFloodAnalysisDates('2024-01-10', '2024-01-09', 'sar_only')).toMatch(/anterior/);
    expect(validateFloodAnalysisDates('2024-01-10', '2024-01-09', 'optical_only')).toMatch(
      /anterior/
    );
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
    expect(sides.source).toBe('comparison');
    expect(sides.right?.visualization).toBe('rgb');
  });

  it('reports flood_only when comparison has flood tile but no normal_rgb (#710)', () => {
    const resultado: FloodAnalysisResultado = {
      comparison: {
        flood_detection: tile('2024-01-10', 'inundacion'),
      },
    };
    const sides = pickFloodComparisonSides(resultado);
    expect(sides.source).toBe('flood_only');
    expect(sides.left).toBeNull();
    expect(sides.right?.target_date).toBe('2024-01-10');
  });

  it('reports normal_only when comparison has normal_rgb but no flood tile (#710)', () => {
    const resultado: FloodAnalysisResultado = {
      comparison: {
        normal_rgb: tile('2024-01-20', 'rgb'),
      },
    };
    const sides = pickFloodComparisonSides(resultado);
    expect(sides.source).toBe('normal_only');
    expect(sides.left?.target_date).toBe('2024-01-20');
    expect(sides.right).toBeNull();
  });

  it('comparison blob without usable tiles is not a comparison (#710)', () => {
    expect(pickFloodComparisonSides({ comparison: {} }).source).toBe('empty');
    expect(pickFloodComparisonSides({ comparison: { normal_rgb: { target_date: '2024-01-20' } } }).source).toBe(
      'empty'
    );
  });

  it('comparison blob without tiles falls through to sar (#710)', () => {
    const resultado: FloodAnalysisResultado = {
      comparison: {},
      sar: {
        ...tile('2024-01-10', 'vv_flood'),
        sensor: 'Sentinel-1',
        collection: 'COPERNICUS/S1_GRD',
      },
    };
    expect(pickFloodComparisonSides(resultado).source).toBe('sar');
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

describe('getFloodAnalysis', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it('encodes analisisId so "/" or "?" cannot forge the path or query (#712)', async () => {
    apiFetchMock.mockResolvedValue({ id: 'x', tipo: 'flood', estado: 'completed' });

    await getFloodAnalysis('../admin/secret?x=1');

    expect(apiFetchMock.mock.calls[0][0]).toBe('/geo/gee/analysis/..%2Fadmin%2Fsecret%3Fx%3D1');
  });

  it('keeps a plain UUID untouched in the path', async () => {
    apiFetchMock.mockResolvedValue({ id: 'x', tipo: 'flood', estado: 'completed' });
    const uuid = '11111111-1111-1111-1111-111111111111';

    await getFloodAnalysis(uuid);

    expect(apiFetchMock.mock.calls[0][0]).toBe(`/geo/gee/analysis/${uuid}`);
  });
});

describe('floodAnalysisErrorCopy', () => {
  it('maps a GEE/celery timeout to short copy without the traceback', () => {
    const copy = floodAnalysisErrorCopy(
      'SoftTimeLimitExceeded: maximum time limit\nTraceback (most recent call last):\n  File "/app/domains/geo/gee_tasks.py", line 182'
    );
    expect(copy.mensaje.titulo).toMatch(/tardó demasiado/i);
    expect(copy.detalleTecnico).toBeNull();
  });

  it('maps missing scenes to the "no images" copy', () => {
    const copy = floodAnalysisErrorCopy(
      'ValueError: No SR scenes available for the requested dates'
    );
    expect(copy.mensaje.titulo).toMatch(/No encontramos imágenes/i);
    expect(copy.detalleTecnico).toBeNull();
  });

  it('maps quota/rate-limit rejections', () => {
    expect(
      floodAnalysisErrorCopy('EEException: Quota exceeded for project canalero-prod').mensaje.titulo
    ).toMatch(/límite de consultas/i);
    expect(floodAnalysisErrorCopy('EEException: Too many requests (429)').mensaje.titulo).toMatch(
      /límite de consultas/i
    );
  });

  it('unknown error → generic copy + technical detail collapsed to one truncated line', () => {
    const raw = [
      'SQLAlchemyError: could not connect to server',
      'Traceback (most recent call last):',
      '  File "/app/shared/storage.py", line 10, in connect',
      'https://earthengine.googleapis.com/v1/projects/canalero-x/maps/abc123/tiles/{z}/{x}/{y}',
    ].join('\n');

    const copy = floodAnalysisErrorCopy(raw);

    expect(copy.mensaje.titulo).toMatch(/No pudimos completar/i);
    expect(`${copy.mensaje.titulo} ${copy.mensaje.detalle}`).not.toContain('https://');
    expect(copy.detalleTecnico).not.toBeNull();
    expect(copy.detalleTecnico).not.toContain('\n');
    expect(copy.detalleTecnico?.length).toBeLessThanOrEqual(140);
    // Truncado: la cola de la URL (paths/ids de proyecto) queda afuera.
    expect(copy.detalleTecnico).not.toContain('canalero-x');
  });

  it('scrubs URLs from the HEAD of the detail — positional truncation alone would keep them', () => {
    // La URL vive en la primera línea: ningún recorte posicional la saca.
    const copy = floodAnalysisErrorCopy(
      'HttpError: 403 when requesting https://earthengine.googleapis.com/v1/projects/canalero-prod/maps/abc/tiles — permission denied'
    );
    expect(copy.detalleTecnico).not.toBeNull();
    expect(copy.detalleTecnico).not.toContain('https://');
    expect(copy.detalleTecnico).not.toContain('earthengine');
    expect(copy.detalleTecnico).toContain('[url]');
  });

  it('classifies on the exception head only — a "timeout" inside a traceback frame is not a timeout', () => {
    const copy = floodAnalysisErrorCopy(
      'SQLAlchemyError: connection refused\nTraceback (most recent call last):\n  File "/app/db.py", line 3, in connect\n    timeout = 300'
    );
    // El head es un error de conexión: NO copia de timeout, y el detalle
    // técnico sobrevive (un falso positivo escondería la causa real).
    expect(copy.mensaje.titulo).not.toMatch(/tardó demasiado/i);
    expect(copy.mensaje.titulo).toMatch(/No pudimos completar/i);
    expect(copy.detalleTecnico).not.toBeNull();
  });

  it('empty or missing error → fallback copy, no technical detail', () => {
    expect(floodAnalysisErrorCopy(null).detalleTecnico).toBeNull();
    expect(floodAnalysisErrorCopy('   ').detalleTecnico).toBeNull();
    expect(floodAnalysisErrorCopy(undefined).mensaje.titulo).toMatch(/No pudimos completar/i);
  });

  it('honors a custom fallback (comparison_error branch)', () => {
    const copy = floodAnalysisErrorCopy(null, {
      titulo: 'Sin tiles',
      detalle: 'Probá otra combinación.',
    });
    expect(copy.mensaje.titulo).toBe('Sin tiles');
  });
});

describe('isAuthError', () => {
  it('detects QueryError 401/403 from the apiFetch retry path', () => {
    expect(isAuthError(new QueryError('detail', 401))).toBe(true);
    expect(isAuthError(new QueryError('detail', 403))).toBe(true);
  });

  it('rejects other statuses and plain errors', () => {
    expect(isAuthError(new QueryError('boom', 500))).toBe(false);
    expect(isAuthError(new QueryError('boom', 404))).toBe(false);
    expect(isAuthError(new Error('La solicitud excedió el tiempo límite (300s)'))).toBe(false);
    expect(isAuthError('cadena')).toBe(false);
  });

  it('detects the session-dead plain Error thrown by apiFetch (RES2-001)', () => {
    expect(
      isAuthError(new Error('Tu sesión ha expirado. Por favor iniciá sesión nuevamente.'))
    ).toBe(true);
  });
});
