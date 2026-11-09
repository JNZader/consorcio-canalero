import { describe, expect, it } from 'vitest';

import {
  type FloodAnalysisResultado,
  fusionComparisonReady,
  pickFloodComparisonSides,
  validateFloodAnalysisDates,
} from '../../src/lib/api/geeFloodAnalysis';

describe('validateFloodAnalysisDates', () => {
  it('rejects end before or equal to start', () => {
    expect(validateFloodAnalysisDates('2024-01-10', '2024-01-10', 'sar_only')).toMatch(/posterior/);
    expect(validateFloodAnalysisDates('2024-01-10', '2024-01-09', 'fusion')).toMatch(/posterior/);
  });

  it('requires >5 day span for fusion comparison', () => {
    expect(validateFloodAnalysisDates('2024-01-01', '2024-01-06', 'fusion')).toMatch(
      />5 días|6 días/
    );
    expect(validateFloodAnalysisDates('2024-01-01', '2024-01-07', 'fusion')).toBeNull();
  });

  it('allows short span for sar_only', () => {
    expect(validateFloodAnalysisDates('2024-01-01', '2024-01-03', 'sar_only')).toBeNull();
  });
});

describe('fusionComparisonReady', () => {
  it('matches backend end-start > 5', () => {
    expect(fusionComparisonReady('2024-01-01', '2024-01-06')).toBe(false);
    expect(fusionComparisonReady('2024-01-01', '2024-01-07')).toBe(true);
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
