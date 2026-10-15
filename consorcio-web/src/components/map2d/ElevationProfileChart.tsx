/**
 * Google Earth-style elevation profile: distance (m) vs elevation (m).
 *
 * Loads only after the operator asks. GLO-30 disclaimer is always shown with
 * the curve. Nodata holes are omitted from the line (recharts skips null y).
 */

import { Alert, Button, Checkbox, Stack, Text } from '@mantine/core';
import type { Geometry, LineString, MultiLineString } from 'geojson';
import { useEffect, useRef, useState } from 'react';
import {
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  type ElevationProfileResponse,
  fetchElevationProfile,
} from '../../lib/api/elevationProfile';
import { mapColorTokens } from '../../lib/mapColorTokens';
import { buildProfileChartRows } from './profileChartRows';
import { type ProfileRangeStats, profileSliceStats, sliceProfile } from './profileRange';

function hasProfileParts(
  geometry: Geometry | null | undefined
): geometry is LineString | MultiLineString {
  if (geometry?.type === 'LineString') {
    return geometry.coordinates.length >= 2;
  }
  if (geometry?.type === 'MultiLineString') {
    // Cada tramo del camino es una parte: el perfil las muestrea todas.
    return geometry.coordinates.some((parte) => parte.length >= 2);
  }
  return false;
}

function formatM(value: number): string {
  return `${value.toFixed(1)} m`;
}

function sampleIndex(rawIndex: unknown): number | null {
  const index = typeof rawIndex === 'number' ? rawIndex : Number(rawIndex);
  return Number.isInteger(index) ? index : null;
}

function lngLatAtIndex(
  rows: readonly { lon?: number; lat?: number }[],
  rawIndex: unknown
): { lon: number; lat: number } | null {
  const index = sampleIndex(rawIndex);
  const row = index != null ? rows[index] : undefined;
  if (row && typeof row.lon === 'number' && typeof row.lat === 'number') {
    return { lon: row.lon, lat: row.lat };
  }
  return null;
}

function distanceAtIndex(
  rows: readonly { distance_m: number }[],
  rawIndex: unknown
): number | null {
  const index = sampleIndex(rawIndex);
  const row = index != null ? rows[index] : undefined;
  return row ? row.distance_m : null;
}

export function ElevationProfileChart({
  geometry,
  onHoverLngLat,
  onPickLngLat,
  onRangeCoordinates,
}: {
  geometry: Geometry | null | undefined;
  onHoverLngLat?: (point: { lon: number; lat: number } | null) => void;
  onPickLngLat?: (point: { lon: number; lat: number }) => void;
  onRangeCoordinates?: (range: ProfileRangeStats | null) => void;
}) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [compareDems, setCompareDems] = useState(false);
  const [profile, setProfile] = useState<ElevationProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<{ a: number; b: number } | null>(null);
  const requestGen = useRef(0);
  const loadedOnce = useRef(false);
  const dragStart = useRef<number | null>(null);
  const dragged = useRef(false);
  const rangeCb = useRef(onRangeCoordinates);
  rangeCb.current = onRangeCoordinates;
  const hoverCb = useRef(onHoverLngLat);
  hoverCb.current = onHoverLngLat;

  useEffect(() => {
    setRange(null);
    rangeCb.current?.(null);
    hoverCb.current?.(null);
    if (!hasProfileParts(geometry) || !loadedOnce.current) {
      if (!hasProfileParts(geometry)) {
        loadedOnce.current = false;
      }
      setProfile(null);
      setError(null);
      setStatus('idle');
      return;
    }
    const gen = ++requestGen.current;
    const line = geometry;
    setStatus('loading');
    setError(null);
    void fetchElevationProfile(line, undefined, compareDems).then(
      (data) => {
        if (gen !== requestGen.current) {
          return;
        }
        setProfile(data);
        setStatus('ready');
      },
      (cause: unknown) => {
        if (gen !== requestGen.current) {
          return;
        }
        setError(cause instanceof Error ? cause.message : 'No se pudo muestrear el DEM');
        setStatus('error');
      }
    );
  }, [compareDems, geometry]);

  if (!hasProfileParts(geometry)) {
    return null;
  }
  const line = geometry;

  async function load() {
    loadedOnce.current = true;
    const gen = ++requestGen.current;
    setStatus('loading');
    setError(null);
    try {
      const data = await fetchElevationProfile(line, undefined, compareDems);
      if (gen !== requestGen.current) {
        return;
      }
      setProfile(data);
      setStatus('ready');
    } catch (cause) {
      if (gen !== requestGen.current) {
        return;
      }
      setError(cause instanceof Error ? cause.message : 'No se pudo muestrear el DEM');
      setStatus('error');
    }
  }

  const chartRows = buildProfileChartRows(profile?.puntos ?? []);
  const hasMdeAr = chartRows.some((row) => row.elevation_mde_ar != null);
  const hasAw3d30 = chartRows.some((row) => row.elevation_aw3d30 != null);
  const hasNasadem = chartRows.some((row) => row.elevation_nasadem != null);
  const selection =
    range != null ? profileSliceStats(sliceProfile(chartRows, range.a, range.b)) : null;

  return (
    <Stack gap={6} data-testid="elevation-profile">
      {status === 'idle' ? (
        <Button size="xs" variant="light" onClick={() => void load()}>
          Perfil de elevación
        </Button>
      ) : null}
      {status === 'loading' ? (
        <Text size="xs" c="dimmed">
          Muestreando DEM…
        </Text>
      ) : null}
      {status === 'error' ? (
        <Alert color="yellow" data-testid="elevation-profile-error">
          {error}
        </Alert>
      ) : null}
      {status === 'ready' && profile ? (
        <>
          <Checkbox
            size="xs"
            label="Comparar DEMs (GEE)"
            checked={compareDems}
            onChange={(event) => setCompareDems(event.currentTarget.checked)}
            data-testid="elevation-profile-compare-dems"
          />
          {profile.min_elevation_m != null && profile.max_elevation_m != null ? (
            <Text size="xs" data-testid="elevation-profile-extrema">
              {formatM(profile.min_elevation_m)} – {formatM(profile.max_elevation_m)} ·{' '}
              {Math.round(profile.length_m)} m
            </Text>
          ) : (
            <Text size="xs" c="dimmed">
              Sin muestras válidas sobre el DEM.
            </Text>
          )}
          {selection ? (
            <Text size="xs" data-testid="elevation-profile-selection">
              Selección: {Math.round(selection.length_m)} m
              {selection.min_elevation_m != null && selection.max_elevation_m != null
                ? ` · ${formatM(selection.min_elevation_m)} – ${formatM(selection.max_elevation_m)}`
                : ''}
              {selection.delta_m != null ? ` · Δ ${selection.delta_m.toFixed(1)} m` : ''}
            </Text>
          ) : (
            <Text size="xs" c="dimmed">
              Arrastrá en el perfil para marcar un tramo.
            </Text>
          )}
          {chartRows.some((row) => row.elevation_m != null) ? (
            <div data-testid="elevation-profile-chart" style={{ width: '100%', height: 160 }}>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart
                  data={chartRows}
                  margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                  onMouseDown={(event) => {
                    const distance = distanceAtIndex(chartRows, event.activeIndex);
                    dragStart.current = distance;
                    dragged.current = false;
                  }}
                  onMouseMove={(event) => {
                    onHoverLngLat?.(lngLatAtIndex(chartRows, event.activeIndex));
                    const distance = distanceAtIndex(chartRows, event.activeIndex);
                    if (dragStart.current == null || distance == null) {
                      return;
                    }
                    if (distance !== dragStart.current) {
                      dragged.current = true;
                      setRange({ a: dragStart.current, b: distance });
                    }
                  }}
                  onMouseUp={(event) => {
                    const distance = distanceAtIndex(chartRows, event.activeIndex);
                    if (dragged.current && dragStart.current != null && distance != null) {
                      const next = { a: dragStart.current, b: distance };
                      setRange(next);
                      const stats = profileSliceStats(sliceProfile(chartRows, next.a, next.b));
                      onRangeCoordinates?.(stats);
                    } else {
                      const point = lngLatAtIndex(chartRows, event.activeIndex);
                      if (point) {
                        onPickLngLat?.(point);
                      }
                    }
                    dragStart.current = null;
                    dragged.current = false;
                  }}
                  onMouseLeave={() => {
                    onHoverLngLat?.(null);
                    dragStart.current = null;
                    dragged.current = false;
                  }}
                >
                  <XAxis dataKey="distance_m" tickFormatter={(v) => `${Math.round(Number(v))}`} />
                  <YAxis
                    domain={['auto', 'auto']}
                    tickFormatter={(v) => `${Number(v).toFixed(0)}`}
                    width={40}
                  />
                  <Tooltip
                    formatter={(value) => (value == null ? 'sin dato' : formatM(Number(value)))}
                    labelFormatter={(label) => `${Math.round(Number(label))} m`}
                  />
                  {range ? (
                    <ReferenceArea
                      x1={Math.min(range.a, range.b)}
                      x2={Math.max(range.a, range.b)}
                      fill={mapColorTokens.hf97316}
                      fillOpacity={0.18}
                      ifOverflow="visible"
                    />
                  ) : null}
                  {selection?.min_point ? (
                    <ReferenceDot
                      x={selection.min_point.distance_m}
                      y={selection.min_point.elevation_m}
                      r={5}
                      fill={mapColorTokens.h2563eb}
                      stroke={mapColorTokens.hffffff}
                    />
                  ) : null}
                  {selection?.max_point ? (
                    <ReferenceDot
                      x={selection.max_point.distance_m}
                      y={selection.max_point.elevation_m}
                      r={5}
                      fill={mapColorTokens.hdc2626}
                      stroke={mapColorTokens.hffffff}
                    />
                  ) : null}
                  <Line
                    type="linear"
                    dataKey="elevation_m"
                    name="GLO-30"
                    stroke="var(--mantine-color-blue-6)"
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                  {hasMdeAr ? (
                    <Line
                      type="linear"
                      dataKey="elevation_mde_ar"
                      name="MDE-Ar"
                      stroke="var(--mantine-color-orange-6)"
                      dot={false}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  ) : null}
                  {hasAw3d30 ? (
                    <Line
                      type="linear"
                      dataKey="elevation_aw3d30"
                      name="AW3D30"
                      stroke="var(--mantine-color-teal-6)"
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ) : null}
                  {hasNasadem ? (
                    <Line
                      type="linear"
                      dataKey="elevation_nasadem"
                      name="NASADEM"
                      stroke="var(--mantine-color-violet-6)"
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ) : null}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : null}
          <Text size="xs" c="dimmed" data-testid="elevation-profile-disclaimer">
            {profile.disclaimer}
          </Text>
          {profile.mde_ar_disclaimer ? (
            <Text size="xs" c="dimmed" data-testid="elevation-profile-mde-ar">
              {profile.mde_ar_disclaimer}
            </Text>
          ) : null}
          {profile.aw3d30_disclaimer ? (
            <Text size="xs" c="dimmed" data-testid="elevation-profile-aw3d30">
              {profile.aw3d30_disclaimer}
            </Text>
          ) : null}
          {profile.nasadem_disclaimer ? (
            <Text size="xs" c="dimmed" data-testid="elevation-profile-nasadem">
              {profile.nasadem_disclaimer}
            </Text>
          ) : null}
        </>
      ) : null}
    </Stack>
  );
}
