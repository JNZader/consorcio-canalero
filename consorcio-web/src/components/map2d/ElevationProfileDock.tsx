/**
 * Full-width profile docked on the bottom of the map.
 * Desktop: 220–360 px, default 260, drag the top edge. Phone: a bottom sheet
 * with the same handle. Collapse leaves a one-line bar so the map stays usable.
 */

import { Group, Text } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import type { Feature, GeoJsonProperties, Geometry, LineString, MultiLineString } from 'geojson';
import {
  lazy,
  type PointerEvent as ReactPointerEvent,
  Suspense,
  useEffect,
  useRef,
  useState,
} from 'react';
import { mediaMaxWidth } from '../../lib/breakpoints';
import { IconButton } from '../ui/IconButton';
import { MAP_Z } from './mapZIndex';
import type { ProfileChartRow } from './profileChartRows';
import {
  clampDockHeight,
  PROFILE_DOCK_DEFAULT_PX,
  PROFILE_DOCK_MAX_PX,
  PROFILE_DOCK_MIN_PX,
} from './profileCursorSync';
import type { ProfileRangeStats } from './profileRange';
import { useMapSheetDialog } from './useMapSheetDialog';

const ElevationProfileChart = lazy(async () => {
  const mod = await import('./ElevationProfileChart');
  return { default: mod.ElevationProfileChart };
});

export function ElevationProfileDock({
  geometry,
  title,
  estimate = false,
  onClose,
  onHoverLngLat,
  onRangeCoordinates,
  externalDistanceM = null,
  onSamples,
  onActivated,
  flowDirection = null,
  crossings = [],
  parcelFeatures = null,
  culverts = null,
  coarseSamples = null,
}: {
  readonly geometry: LineString | MultiLineString;
  readonly title: string;
  readonly estimate?: boolean;
  readonly onClose: () => void;
  readonly onHoverLngLat?: (point: { lon: number; lat: number } | null) => void;
  readonly onRangeCoordinates?: (range: ProfileRangeStats | null) => void;
  readonly externalDistanceM?: number | null;
  readonly onSamples?: (rows: readonly ProfileChartRow[]) => void;
  readonly onActivated?: () => void;
  readonly flowDirection?: 'digitizado' | 'inverso' | null;
  readonly crossings?: readonly { lon: number; lat: number; label: string }[];
  readonly parcelFeatures?: readonly Feature<Geometry, GeoJsonProperties>[] | null;
  readonly culverts?: readonly { lon: number; lat: number; label: string }[] | null;
  readonly coarseSamples?: readonly ProfileChartRow[] | null;
}) {
  const narrow = useMediaQuery(mediaMaxWidth('md'), false, { getInitialValueInEffect: false });
  const [height, setHeight] = useState(PROFILE_DOCK_DEFAULT_PX);
  const [collapsed, setCollapsed] = useState(false);
  const narrowSheet = narrow && !collapsed;
  const sectionRef = useRef<HTMLElement | null>(null);
  const sheetDialog = useMapSheetDialog<HTMLElement>(
    narrowSheet,
    onClose,
    MAP_Z.profile,
    undefined,
    sectionRef
  );
  const dragOrigin = useRef<{ y: number; height: number } | null>(null);
  const effectiveHeight = collapsed ? 44 : height;

  useEffect(() => {
    const parent = sectionRef.current?.parentElement;
    if (!parent) return;
    parent.style.setProperty('--map-bottom-dock-offset', `${effectiveHeight}px`);
    return () => {
      parent.style.removeProperty('--map-bottom-dock-offset');
    };
  }, [effectiveHeight]);

  function onHandlePointerDown(event: ReactPointerEvent<HTMLButtonElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    dragOrigin.current = { y: event.clientY, height };
  }

  function onHandlePointerMove(event: ReactPointerEvent<HTMLButtonElement>) {
    const origin = dragOrigin.current;
    if (!origin) {
      return;
    }
    setHeight(clampDockHeight(origin.height + (origin.y - event.clientY)));
  }

  function onHandlePointerUp() {
    dragOrigin.current = null;
  }

  function nudgeHeight(delta: number) {
    setHeight((current) => clampDockHeight(current + delta));
  }

  return (
    <section
      ref={sectionRef}
      data-testid="elevation-profile-dock"
      data-collapsed={collapsed ? 'true' : 'false'}
      data-sheet={narrow ? 'true' : 'false'}
      aria-label={title}
      {...(sheetDialog.modal
        ? { role: 'dialog' as const, 'aria-modal': true as const, tabIndex: -1 as const }
        : undefined)}
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: MAP_Z.profile,
        height: effectiveHeight,
        maxHeight: narrow ? '70vh' : PROFILE_DOCK_MAX_PX,
        display: 'flex',
        flexDirection: 'column',
        background: 'light-dark(rgba(255,255,255,0.97), rgba(28,28,28,0.97))',
        borderTop: '1px solid var(--mantine-color-gray-4)',
        borderRadius: narrow ? '12px 12px 0 0' : 0,
        boxShadow: '0 -2px 10px rgba(0,0,0,0.12)',
      }}
    >
      {/* Colapsado en el teléfono el asa competía con los 44px de cerrar/expandir. */}
      {narrow && collapsed ? null : (
        <button
          type="button"
          data-testid="elevation-profile-resize"
          role="slider"
          aria-label="Cambiar alto del perfil"
          aria-valuemin={PROFILE_DOCK_MIN_PX}
          aria-valuemax={PROFILE_DOCK_MAX_PX}
          aria-valuenow={height}
          onPointerDown={onHandlePointerDown}
          onPointerMove={onHandlePointerMove}
          onPointerUp={onHandlePointerUp}
          onKeyDown={(event) => {
            if (event.key === 'ArrowUp') {
              nudgeHeight(20);
            }
            if (event.key === 'ArrowDown') {
              nudgeHeight(-20);
            }
          }}
          style={{
            flex: '0 0 auto',
            height: narrow ? 'var(--cc-touch-min, 44px)' : 14,
            border: 0,
            background: 'transparent',
            cursor: 'ns-resize',
            touchAction: 'none',
          }}
        >
          <span
            style={{
              display: 'block',
              width: 36,
              height: 4,
              margin: '4px auto 0',
              borderRadius: 4,
              background: 'var(--mantine-color-gray-5)',
            }}
          />
        </button>
      )}
      <Group justify="space-between" wrap="nowrap" px="sm" gap="xs">
        <Text size="xs" fw={700}>
          {title}
          {estimate ? ' · estimación mientras dibujás' : ''}
        </Text>
        <Group gap={4} wrap="nowrap">
          <IconButton
            size="sm"
            variant="subtle"
            aria-expanded={!collapsed}
            aria-label={collapsed ? 'Expandir perfil' : 'Contraer perfil'}
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? '▴' : '▾'}
          </IconButton>
          <IconButton size="sm" variant="subtle" aria-label="Cerrar perfil" onClick={onClose}>
            ×
          </IconButton>
        </Group>
      </Group>
      {collapsed ? null : (
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflow: 'auto',
            overscrollBehavior: 'contain',
            touchAction: 'pan-y',
            padding: '0 8px calc(8px + env(safe-area-inset-bottom, 0px))',
          }}
        >
          <Suspense fallback={null}>
            <ElevationProfileChart
              geometry={geometry}
              autoLoad
              onHoverLngLat={onHoverLngLat}
              onRangeCoordinates={onRangeCoordinates}
              externalDistanceM={externalDistanceM}
              onSamples={onSamples}
              onActivated={onActivated}
              flowDirection={flowDirection}
              crossings={crossings}
              parcelFeatures={parcelFeatures}
              culverts={culverts}
              coarseSamples={coarseSamples}
            />
          </Suspense>
        </div>
      )}
    </section>
  );
}
