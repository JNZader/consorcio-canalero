import type { FeatureCollection, LineString } from 'geojson';
import { describe, expect, it, vi } from 'vitest';

import {
  CANAL_FOCUS_PADDING,
  canalCollections,
  canalFocusBbox,
  canalSlugFromToggleId,
  featureMatchesCanalToggle,
  findCanalFeature,
  fitMapToCanal,
} from '../../src/components/map2d/canalFocus';

const line: LineString = {
  type: 'LineString',
  coordinates: [
    [-62.6, -32.6],
    [-62.5, -32.5],
  ],
};

const relevados: FeatureCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      id: 't269-03',
      properties: { id: 't269-03', slug: 't269-03' },
      geometry: line,
    },
  ],
};

describe('canalFocus UX-05', () => {
  it('strips explorer toggle prefixes', () => {
    expect(canalSlugFromToggleId('canal_relevado_t269_03')).toBe('t269-03');
    expect(canalSlugFromToggleId('canal_propuesto_la_sara')).toBe('la-sara');
  });

  it('matches by feature id or properties', () => {
    const feature = relevados.features[0];
    expect(featureMatchesCanalToggle(feature, 'canal_relevado_t269_03')).toBe(true);
    expect(featureMatchesCanalToggle(feature, 't269-03')).toBe(true);
    expect(featureMatchesCanalToggle(feature, 'canal_relevado_other')).toBe(false);
  });

  it('finds a canal and returns a bbox', () => {
    expect(findCanalFeature([relevados], 'canal_relevado_t269_03')?.id).toBe('t269-03');
    const box = canalFocusBbox([relevados], 'canal_relevado_t269_03');
    expect(box).toEqual([-62.6, -32.6, -62.5, -32.5]);
  });

  it('returns null when the canal is missing', () => {
    expect(canalFocusBbox([relevados], 'canal_relevado_nope')).toBeNull();
    expect(canalCollections(null, undefined)).toEqual([]);
    expect(canalCollections(relevados, null)).toEqual([relevados]);
  });

  it('fitMapToCanal calls fitBounds with padding', () => {
    const map = { fitBounds: vi.fn() };
    expect(fitMapToCanal(map, [relevados], 'canal_relevado_t269_03')).toBe(true);
    expect(map.fitBounds).toHaveBeenCalledWith(
      [
        [-62.6, -32.6],
        [-62.5, -32.5],
      ],
      { padding: CANAL_FOCUS_PADDING, duration: 600 },
    );
    expect(fitMapToCanal(null, [relevados], 'canal_relevado_t269_03')).toBe(false);
    expect(fitMapToCanal(map, [relevados], 'missing')).toBe(false);
  });

  it('bboxes polygons without turf', () => {
    const polygon: FeatureCollection = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { id: 'poly' },
          geometry: {
            type: 'Polygon',
            coordinates: [
              [
                [-62.7, -32.7],
                [-62.4, -32.7],
                [-62.4, -32.4],
                [-62.7, -32.4],
                [-62.7, -32.7],
              ],
            ],
          },
        },
      ],
    };
    expect(canalFocusBbox([polygon], 'poly')).toEqual([-62.7, -32.7, -62.4, -32.4]);
  });
});
