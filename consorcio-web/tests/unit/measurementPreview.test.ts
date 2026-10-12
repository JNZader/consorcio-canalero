import type { Feature, LineString, Polygon } from 'geojson';
import { describe, expect, it } from 'vitest';

import { liveMeasurementLabel } from '../../src/components/map2d/measurement/measurementPreview';

const line: Feature<LineString> = {
  type: 'Feature',
  properties: {},
  geometry: {
    type: 'LineString',
    coordinates: [
      [-62.7, -32.6],
      [-62.6, -32.6],
    ],
  },
};

const polygon: Feature<Polygon> = {
  type: 'Feature',
  properties: {},
  geometry: {
    type: 'Polygon',
    coordinates: [
      [
        [-62.7, -32.6],
        [-62.6, -32.6],
        [-62.6, -32.5],
        [-62.7, -32.6],
      ],
    ],
  },
};

describe('liveMeasurementLabel', () => {
  it('returns null until a distance line has two vertices', () => {
    expect(liveMeasurementLabel('measuring-distance', [])).toBeNull();
    expect(
      liveMeasurementLabel('measuring-distance', [
        {
          type: 'Feature',
          properties: {},
          geometry: { type: 'LineString', coordinates: [[-62.7, -32.6]] },
        },
      ]),
    ).toBeNull();
  });

  it('formats a live distance', () => {
    const label = liveMeasurementLabel('measuring-distance', [line]);
    expect(label).toMatch(/m|km/);
    expect(label).not.toBe('— m');
  });

  it('formats a live area', () => {
    const label = liveMeasurementLabel('measuring-area', [polygon]);
    expect(label).toMatch(/m²|ha/);
  });

  it('returns null when idle', () => {
    expect(liveMeasurementLabel('idle', [line])).toBeNull();
  });
});
