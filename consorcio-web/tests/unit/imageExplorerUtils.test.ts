import { describe, expect, it, vi } from 'vitest';

import {
  buildVisualizationOptions,
  createSelectedImageFromResult,
  explorerSceneVisualization,
} from '../../src/components/admin/images/imageExplorerUtils';

describe('imageExplorerUtils', () => {
  it('defaults optical explorer scenes to falso_color instead of stored rgb', () => {
    expect(explorerSceneVisualization('sentinel2', 'rgb')).toBe('falso_color');
    expect(explorerSceneVisualization('landsat8', null)).toBe('falso_color');
    expect(explorerSceneVisualization('sentinel2', 'mndwi')).toBe('mndwi');
    expect(explorerSceneVisualization('sentinel1', 'rgb')).toBe('rgb');
    expect(explorerSceneVisualization('sentinel1', null)).toBe('vv_flood');
  });

  it('builds visualization options per sensor', () => {
    expect(buildVisualizationOptions('sentinel2', [{ id: 'rgb', description: 'RGB' }])).toEqual([
      { value: 'rgb', label: 'RGB' },
    ]);
    expect(buildVisualizationOptions('sentinel1', [])).toEqual([
      { value: 'vv', label: 'Radar SAR (VV)' },
      { value: 'vv_flood', label: 'Deteccion de agua (SAR)' },
    ]);
  });

  it('creates selected image payload from result', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-04-09T18:00:00Z'));
    const result = createSelectedImageFromResult({
      tile_url: 'https://tiles.example.com/{z}/{x}/{y}.png',
      target_date: '2026-03-01',
      dates_available: ['2026-03-01'],
      images_count: 2,
      visualization: 'rgb',
      visualization_description: 'RGB',
      sensor: 'Sentinel-2',
      collection: 'COPERNICUS/S2',
    });
    expect(result?.target_date).toBe('2026-03-01');
    expect(result?.selected_at).toBe('2026-04-09T18:00:00.000Z');
    vi.useRealTimers();
  });
});
