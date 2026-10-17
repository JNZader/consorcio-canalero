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
 *     centroids and break the draw UX). The distance-profile button and
 *     the docked chart are the only children that opt back in.
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

import type { LineString } from 'geojson';
import type * as maplibregl from 'maplibre-gl';
import { lazy, Suspense, useEffect, useState } from 'react';
import { mapColorTokens } from '../../../lib/mapColorTokens';
import type { ProfileRangeStats } from '../profileRange';
import { formatArea, formatDistance } from './measurementFormat';
import type { MeasurementEntry } from './useMeasurement';

const ElevationProfileChart = lazy(async () => {
  const mod = await import('../ElevationProfileChart');
  return { default: mod.ElevationProfileChart };
});

const COLLISION_THRESHOLD_PX = 40;
const MIN_ZOOM_TO_SHOW_ALL = 14;

export interface MeasurementLabelsProps {
  readonly map: maplibregl.Map | null;
  readonly measurements: readonly MeasurementEntry[];
  readonly onElevationProfileHover?: (point: { lon: number; lat: number } | null) => void;
  readonly onElevationProfileRange?: (range: ProfileRangeStats | null) => void;
}

/** The line the operator drew. An area, or a line with one vertex, has no profile. */
function distanceLine(entry: MeasurementEntry): LineString | null {
  const geometry = entry.geometry;
  if (entry.kind !== 'distance' || geometry == null || geometry.type !== 'LineString') {
    return null;
  }
  if (geometry.coordinates.length < 2) {
    return null;
  }
  return geometry;
}

interface PixelPosition {
  readonly x: number;
  readonly y: number;
}

function getVisibleMeasurements(
  measurements: readonly MeasurementEntry[],
  positions: Record<string, PixelPosition>,
  zoom: number
): readonly MeasurementEntry[] {
  if (zoom >= MIN_ZOOM_TO_SHOW_ALL) return measurements;

  const sorted = [...measurements].sort((a, b) => {
    if (a.kind === 'area' && b.kind !== 'area') return -1;
    if (a.kind !== 'area' && b.kind === 'area') return 1;
    return b.value - a.value;
  });

  const visible: MeasurementEntry[] = [];
  const keptPositions: PixelPosition[] = [];

  for (const m of sorted) {
    const pos = positions[m.id];
    if (!pos) continue;

    let collides = false;
    for (const kept of keptPositions) {
      const dx = pos.x - kept.x;
      const dy = pos.y - kept.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < COLLISION_THRESHOLD_PX) {
        collides = true;
        break;
      }
    }

    if (!collides) {
      visible.push(m);
      keptPositions.push(pos);
    }
  }

  return visible;
}

export function MeasurementLabels({
  map,
  measurements,
  onElevationProfileHover,
  onElevationProfileRange,
}: MeasurementLabelsProps) {
  const [positions, setPositions] = useState<Record<string, PixelPosition>>({});
  const [profileId, setProfileId] = useState<string | null>(null);
  const openEntry = measurements.find((entry) => entry.id === profileId) ?? null;
  const openLine = openEntry ? distanceLine(openEntry) : null;

  useEffect(() => {
    if (profileId != null && openLine == null) {
      setProfileId(null);
      onElevationProfileHover?.(null);
      onElevationProfileRange?.(null);
    }
  }, [onElevationProfileHover, onElevationProfileRange, openLine, profileId]);

  function closeProfile() {
    setProfileId(null);
    onElevationProfileHover?.(null);
    onElevationProfileRange?.(null);
  }

  function toggleProfile(id: string) {
    if (profileId === id) {
      closeProfile();
      return;
    }
    if (profileId != null) {
      onElevationProfileHover?.(null);
      onElevationProfileRange?.(null);
    }
    setProfileId(id);
  }

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
    map.on('zoom', update);

    return () => {
      map.off('move', update);
      map.off('zoom', update);
    };
  }, [map, measurements]);

  if (!map) return null;

  const zoom = map.getZoom();
  const visible = getVisibleMeasurements(measurements, positions, zoom);

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 17,
      }}
    >
      {visible.map((m) => {
        const pos = positions[m.id];
        if (!pos) return null;
        const text = m.kind === 'distance' ? formatDistance(m.value) : formatArea(m.value);
        const line = distanceLine(m);
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
              color: mapColorTokens.h333,
            }}
          >
            {text}
            {line ? (
              <button
                type="button"
                aria-pressed={profileId === m.id}
                onClick={() => toggleProfile(m.id)}
                style={{
                  pointerEvents: 'auto',
                  display: 'block',
                  marginTop: 2,
                  padding: 0,
                  border: 0,
                  background: 'transparent',
                  color: '#1c7ed6',
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: 'pointer',
                  textDecoration: 'underline',
                }}
              >
                Perfil de elevación
              </button>
            ) : null}
          </div>
        );
      })}
      {openLine ? (
        <div
          data-testid="measurement-profile-panel"
          style={{
            position: 'absolute',
            right: 12,
            bottom: 12,
            width: 340,
            maxWidth: 'calc(100% - 24px)',
            pointerEvents: 'auto',
            background: 'white',
            border: '1px solid #fd7e14',
            borderRadius: 6,
            padding: 8,
            boxShadow: '0 2px 8px rgba(0,0,0,0.18)',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 4,
            }}
          >
            <span style={{ fontSize: 12, fontWeight: 700, color: mapColorTokens.h333 }}>
              Perfil de la medición
            </span>
            <button
              type="button"
              onClick={closeProfile}
              style={{
                pointerEvents: 'auto',
                border: 0,
                background: 'transparent',
                color: mapColorTokens.h333,
                fontSize: 11,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Cerrar
            </button>
          </div>
          <Suspense fallback={null}>
            <ElevationProfileChart
              geometry={openLine}
              autoLoad
              onHoverLngLat={onElevationProfileHover}
              onRangeCoordinates={onElevationProfileRange}
            />
          </Suspense>
        </div>
      ) : null}
    </div>
  );
}
