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
 *     `map.project(labelPosition)`, then shifted ABOVE the anchor so the
 *     chip does not cover the vertex or the segment it describes.
 *
 * Styling:
 *   - `#fd7e14` border matches the orange measurement draw line color
 *     from Batch B, so the label reads as part of the same feature.
 *   - Inline styles only — deliberately avoids a CSS module to keep the
 *     batch small and consistent with the inline-style approach used
 *     elsewhere in the measurement subdirectory.
 */

import type { LineString, MultiLineString } from 'geojson';
import type * as maplibregl from 'maplibre-gl';
import { useEffect, useState } from 'react';
import { mapColorTokens } from '../../../lib/mapColorTokens';
import { MAP_Z } from '../mapZIndex';
import { formatArea, formatDistance } from './measurementFormat';
import type { MeasurementEntry } from './useMeasurement';

const COLLISION_THRESHOLD_PX = 40;
const MIN_ZOOM_TO_SHOW_ALL = 14;

export interface MeasurementLabelsProps {
  readonly map: maplibregl.Map | null;
  readonly measurements: readonly MeasurementEntry[];
  /** The dock owns the chart. `null` closes it. */
  readonly onProfileLine?: (line: LineString | null) => void;
  /** Active profile geometry, keeps label in sync when dock closes externally */
  readonly activeProfileGeometry?: LineString | MultiLineString | null;
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
  onProfileLine,
  activeProfileGeometry,
}: MeasurementLabelsProps) {
  const [positions, setPositions] = useState<Record<string, PixelPosition>>({});
  const [profileId, setProfileId] = useState<string | null>(null);
  const [dismissedIds, setDismissedIds] = useState<ReadonlySet<string>>(new Set());
  const openEntry = measurements.find((entry) => entry.id === profileId) ?? null;
  const openLine = openEntry ? distanceLine(openEntry) : null;

  useEffect(() => {
    if (profileId != null && openLine == null) {
      setProfileId(null);
      onProfileLine?.(null);
    }
  }, [onProfileLine, openLine, profileId]);

  // If dock was closed externally (dockGeometry became null), reset local profileId
  useEffect(() => {
    if (activeProfileGeometry === null && profileId !== null) {
      setProfileId(null);
    }
  }, [activeProfileGeometry, profileId]);

  function closeProfile() {
    setProfileId(null);
    onProfileLine?.(null);
  }

  function toggleProfile(id: string) {
    if (profileId === id) {
      closeProfile();
      return;
    }
    const entry = measurements.find((item) => item.id === id);
    const line = entry ? distanceLine(entry) : null;
    setProfileId(id);
    onProfileLine?.(line);
  }

  useEffect(() => {
    if (!map) return;

    const update = () => {
      const next: Record<string, PixelPosition> = {};
      for (const m of measurements) {
        // For a distance LineString, anchor at the final endpoint of the tramo
        // so the badge never obstructs the canal path and terrain features.
        const anchor =
          m.kind === 'distance' &&
          m.geometry?.type === 'LineString' &&
          m.geometry.coordinates.length > 0
            ? (m.geometry.coordinates[m.geometry.coordinates.length - 1] as [number, number])
            : m.labelPosition;
        const pt = map.project(anchor);
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
  const visible = getVisibleMeasurements(measurements, positions, zoom).filter(
    (m) => !dismissedIds.has(m.id)
  );

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        zIndex: MAP_Z.measurementLabel,
      }}
    >
      {visible.map((m) => {
        const pos = positions[m.id];
        if (!pos) return null;
        const text = m.kind === 'distance' ? formatDistance(m.value) : formatArea(m.value);
        const line = distanceLine(m);
        const isProfileActive = profileId === m.id || (activeProfileGeometry != null && line != null);

        return (
          <div
            key={m.id}
            data-testid={`measurement-label-${m.id}`}
            style={{
              position: 'absolute',
              left: pos.x,
              top: pos.y,
              transform: 'translate(-50%, calc(-100% - 10px))',
              willChange: 'left, top',
              background: 'rgba(255, 255, 255, 0.96)',
              backdropFilter: 'blur(4px)',
              border: '1.5px solid #fd7e14',
              borderRadius: 6,
              padding: '3px 8px',
              fontSize: 11,
              fontWeight: 600,
              boxShadow: '0 2px 6px rgba(0,0,0,0.18)',
              whiteSpace: 'nowrap',
              color: mapColorTokens.h333,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              pointerEvents: 'auto',
            }}
          >
            <span>{text}</span>
            {line ? (
              <button
                type="button"
                aria-label="Perfil de elevación"
                aria-pressed={isProfileActive}
                onClick={() => toggleProfile(m.id)}
                title={isProfileActive ? 'Cerrar perfil de elevación' : 'Abrir perfil de elevación'}
                style={{
                  pointerEvents: 'auto',
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: '1px 6px',
                  border: isProfileActive
                    ? '1px solid #74c0fc'
                    : '1px solid var(--cc-color-border)',
                  borderRadius: 4,
                  background: isProfileActive ? '#e7f5ff' : 'var(--cc-color-surface-raised)',
                  color: isProfileActive ? '#1971c2' : 'var(--cc-color-text-muted)',
                  fontSize: 10,
                  fontWeight: 600,
                  cursor: 'pointer',
                  lineHeight: '14px',
                }}
              >
                {isProfileActive ? 'Perfil abierto' : 'Perfil'}
              </button>
            ) : null}
            <button
              type="button"
              aria-label={`Ocultar cartelito ${m.id}`}
              title="Ocultar cartelito"
              onClick={(e) => {
                e.stopPropagation();
                setDismissedIds((prev) => new Set([...prev, m.id]));
              }}
              style={{
                pointerEvents: 'auto',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 15,
                height: 15,
                padding: 0,
                border: 0,
                borderRadius: '50%',
                background: 'transparent',
                color: 'var(--cc-color-text-muted)',
                fontSize: 11,
                lineHeight: 1,
                cursor: 'pointer',
              }}
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
