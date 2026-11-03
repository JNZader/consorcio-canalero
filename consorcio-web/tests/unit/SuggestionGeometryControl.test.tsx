import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { DrawnLineFeatureCollection } from '../../src/components/map/LineDrawControl';
import SuggestionGeometryControl, {
  removeSuggestionVertexAt,
  toSourceFeatures,
  undoLastSuggestionVertex,
} from '../../src/components/map/SuggestionGeometryControl';

type EventHandler = (event: unknown) => void;

function createMockMap() {
  const sources = new Map<string, { data: unknown; setData: ReturnType<typeof vi.fn> }>();
  const layers = new Map<string, unknown>();
  const mapHandlers = new Map<string, EventHandler[]>();
  const layerHandlers = new Map<string, EventHandler[]>();
  const queryRenderedFeatures = vi.fn(() => [] as unknown[]);

  const map = {
    getSource: vi.fn((id: string) => sources.get(id)),
    addSource: vi.fn((id: string, spec: { data: unknown }) => {
      const setData = vi.fn((next: unknown) => {
        const entry = sources.get(id);
        if (entry) entry.data = next;
      });
      sources.set(id, { data: spec.data, setData });
    }),
    removeSource: vi.fn((id: string) => {
      sources.delete(id);
    }),
    getLayer: vi.fn((id: string) => layers.get(id)),
    addLayer: vi.fn((spec: { id: string }) => {
      layers.set(spec.id, spec);
    }),
    removeLayer: vi.fn((id: string) => {
      layers.delete(id);
    }),
    getStyle: vi.fn(() => ({ version: 8 })),
    getCanvas: vi.fn(() => ({ style: { cursor: '' } })),
    queryRenderedFeatures,
    on: vi.fn((event: string, layerOrHandler: string | EventHandler, maybeHandler?: EventHandler) => {
      if (typeof layerOrHandler === 'string' && maybeHandler) {
        const key = `${event}:${layerOrHandler}`;
        layerHandlers.set(key, [...(layerHandlers.get(key) ?? []), maybeHandler]);
      } else if (typeof layerOrHandler === 'function') {
        mapHandlers.set(event, [...(mapHandlers.get(event) ?? []), layerOrHandler]);
      }
    }),
    off: vi.fn(),
    fireClick(lng: number, lat: number, point = { x: 100, y: 100 }, hitVertexFeatures: unknown[] = []) {
      queryRenderedFeatures.mockReturnValueOnce(hitVertexFeatures);
      let defaultPrevented = false;
      const originalEvent = {
        defaultPrevented: false,
        preventDefault() {
          this.defaultPrevented = true;
        },
        stopPropagation: vi.fn(),
      };
      const baseEvent = {
        lngLat: { lng, lat },
        point,
        originalEvent,
        get defaultPrevented() {
          return defaultPrevented;
        },
        preventDefault() {
          defaultPrevented = true;
        },
      };

      if (hitVertexFeatures.length > 0) {
        for (const handler of layerHandlers.get('click:suggestion-geometry-source-point') ?? []) {
          handler({ ...baseEvent, features: hitVertexFeatures });
        }
      }

      for (const handler of mapHandlers.get('click') ?? []) {
        handler(baseEvent);
      }
    },
    getSourceData(id = 'suggestion-geometry-source') {
      return sources.get(id)?.data as { features: Array<{ geometry: { type: string; coordinates: unknown } }> } | undefined;
    },
  };

  return map;
}

describe('SuggestionGeometryControl (CIT-01)', () => {
  it('deletes a single Point when clicking the vertex without re-adding it in handleClick', () => {
    const mockMap = createMockMap();
    let currentGeometry: DrawnLineFeatureCollection | null = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
        },
      ],
    };

    const onChange = vi.fn((next: DrawnLineFeatureCollection | null) => {
      currentGeometry = next;
    });

    render(
      <SuggestionGeometryControl
        map={mockMap as never}
        value={currentGeometry}
        onChange={onChange}
      />
    );

    // Simulate clicking directly on the existing vertex
    mockMap.fireClick(-62.68, -32.62, { x: 50, y: 50 }, [
      {
        type: 'Feature',
        properties: { feature_role: 'vertex', featureIndex: 0, vertexIndex: 0 },
        geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
      },
    ]);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(currentGeometry).toBeNull();
  });

  it('emits Point vertex features alongside LineString so all vertices render as circular handles', () => {
    const lineGeometry: DrawnLineFeatureCollection = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry: {
            type: 'LineString',
            coordinates: [
              [-62.68, -32.62],
              [-62.69, -32.63],
              [-62.7, -32.64],
            ],
          },
        },
      ],
    };

    const sourceFeatures = toSourceFeatures(lineGeometry);
    const lines = sourceFeatures.filter((f) => f.geometry.type === 'LineString');
    const points = sourceFeatures.filter((f) => f.geometry.type === 'Point');

    expect(lines).toHaveLength(1);
    expect(points).toHaveLength(3);
    expect(points.map((p) => p.properties?.vertexIndex)).toEqual([0, 1, 2]);
  });

  it('undoes vertices step by step from 3-point LineString -> 2-point LineString -> Point -> null', () => {
    const threePoints: DrawnLineFeatureCollection = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry: {
            type: 'LineString',
            coordinates: [
              [-62.68, -32.62],
              [-62.69, -32.63],
              [-62.7, -32.64],
            ],
          },
        },
      ],
    };

    const twoPoints = undoLastSuggestionVertex(threePoints);
    expect(twoPoints?.features[0]?.geometry).toEqual({
      type: 'LineString',
      coordinates: [
        [-62.68, -32.62],
        [-62.69, -32.63],
      ],
    });

    const onePoint = undoLastSuggestionVertex(twoPoints);
    expect(onePoint?.features[0]?.geometry).toEqual({
      type: 'Point',
      coordinates: [-62.68, -32.62],
    });

    const empty = undoLastSuggestionVertex(onePoint);
    expect(empty).toBeNull();
  });

  it('removes a specific vertex from a LineString when tapped', () => {
    const threePoints: DrawnLineFeatureCollection = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry: {
            type: 'LineString',
            coordinates: [
              [-62.68, -32.62],
              [-62.69, -32.63],
              [-62.7, -32.64],
            ],
          },
        },
      ],
    };

    const afterRemovingMiddle = removeSuggestionVertexAt(threePoints, 0, 1);
    expect(afterRemovingMiddle?.features[0]?.geometry).toEqual({
      type: 'LineString',
      coordinates: [
        [-62.68, -32.62],
        [-62.7, -32.64],
      ],
    });
  });
});
