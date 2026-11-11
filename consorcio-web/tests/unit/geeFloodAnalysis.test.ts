import { describe, expect, it } from 'vitest';

import {
  type FloodAnalysisMethod,
  type FloodAnalysisResultado,
  fusionComparisonReady,
  pickFloodComparisonSides,
  validateFloodAnalysisDates,
} from '../../src/lib/api/geeFloodAnalysis';

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
