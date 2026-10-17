import length from '@turf/length';
import type { Feature, LineString, Polygon } from 'geojson';
import { describe, expect, it } from 'vitest';

import {
  drawnLineMeters,
  liveMeasurementLabel,
} from '../../src/components/map2d/measurement/measurementPreview';

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
      ])
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

describe('drawnLineMeters', () => {
  it('returns the geodesic length of the drawn line', () => {
    const drawn: LineString = {
      type: 'LineString',
      coordinates: [
        [0, 0.00005],
        [0.01, -0.00004],
        [0.02, 0.00005],
      ],
    };
    const axisMeters = length(
      {
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'LineString',
          coordinates: [
            [0, 0],
            [0.02, 0],
          ],
        },
      },
      { units: 'meters' }
    );
    const drawnMeters = length(
      { type: 'Feature', properties: {}, geometry: drawn },
      { units: 'meters' }
    );
    expect(drawnLineMeters(drawn)).toBeCloseTo(drawnMeters, 5);
    expect(drawnLineMeters(drawn)).toBeGreaterThan(axisMeters);
  });
});
