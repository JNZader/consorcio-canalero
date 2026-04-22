/**
 * MeasurementLabels — HTML overlay that floats a label per measurement
 * at its `labelPosition`, re-projecting on every map `move` event.
 *
 * Why HTML (not a MapLibre `symbol` layer with `text-field`):
 *   The 2D base style has NO `glyphs` URL (same constraint that bit us
 *   during escuelas-rurales — see `SpriteGlyphs.md` in docs/). A symbol
 *   layer with `text-field` on a glyph-less style crashes the renderer.
 *   `map.project(lngLat) → pixel` + absolute-positioned `<div>` is the
 *   stable fallback, and it matches the lightweight ephemeral nature of
 *   the measurement feature.
 *
 * Positioning:
 *   - The outer wrapper is `position: absolute; inset: 0` so it fills the
 *     map container exactly.
 *   - `pointerEvents: 'none'` lets map drag/click pass through untouched
 *     (critical — otherwise the label would eat clicks near polygon
 *     centroids and break the draw UX).
 *   - Each label is absolutely-positioned using the pixel coords from
 *     `map.project(labelPosition)`, then `translate(-50%, -50%)` centres
 *     the label on the anchor point.
 *
 * Styling:
 *   - `#fd7e14` border matches the orange measurement draw line color
 *     from Batch B, so the label reads as part of the same feature.
 *   - Inline styles only — deliberately avoids a CSS module to keep the
 *     batch small and consistent with the inline-style approach used
 *     elsewhere in the measurement subdirectory.
 */

import { useEffect, useState } from 'react';
import type maplibregl from 'maplibre-gl';

import { formatArea, formatDistance } from './measurementFormat';
import type { MeasurementEntry } from './useMeasurement';

export interface MeasurementLabelsProps {
  readonly map: maplibregl.Map | null;
  readonly measurements: readonly MeasurementEntry[];
}

interface PixelPosition {
  readonly x: number;
  readonly y: number;
}

export function MeasurementLabels({
  map,
  measurements,
}: MeasurementLabelsProps) {
  const [positions, setPositions] = useState<Record<string, PixelPosition>>({});

  useEffect(() => {
    if (!map) return;

    const update = () => {
      const next: Record<string, PixelPosition> = {};
      for (const m of measurements) {
        const pt = map.project(m.labelPosition);
        next[m.id] = { x: pt.x, y: pt.y };
      }
      setPositions(next);
    };

    // Seed positions immediately so the first paint doesn't flash at (0,0).
    update();
    map.on('move', update);

    return () => {
      map.off('move', update);
    };
  }, [map, measurements]);

  if (!map) return null;

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 15,
      }}
    >
      {measurements.map((m) => {
        const pos = positions[m.id];
        if (!pos) return null;
        const text = m.kind === 'distance' ? formatDistance(m.value) : formatArea(m.value);
        return (
          <div
            key={m.id}
            data-testid={`measurement-label-${m.id}`}
            style={{
              position: 'absolute',
              left: pos.x,
              top: pos.y,
              transform: 'translate(-50%, -50%)',
              background: 'white',
              border: '1px solid #fd7e14',
              borderRadius: 4,
              padding: '2px 6px',
              fontSize: 12,
              fontWeight: 600,
              boxShadow: '0 1px 2px rgba(0,0,0,0.15)',
              whiteSpace: 'nowrap',
              color: '#333',
            }}
          >
            {text}
          </div>
        );
      })}
    </div>
  );
}
