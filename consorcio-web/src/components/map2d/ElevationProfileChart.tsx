/**
 * Google Earth-style elevation profile: distance vs elevation.
 *
 * Readouts stay outside the plot. The header carries the trace stats, a drag
 * updates that header (with Limpiar), and the cursor is a label pinned to the
 * top of a vertical line — never a floating card over the curves. DEM values
 * sit in a legend beside the plot. Disclaimers fold into "Sobre los datos".
 */

import { Alert, Button, Checkbox, Group, Skeleton, Stack, Text } from '@mantine/core';
import type { Geometry, LineString, MultiLineString } from 'geojson';
import { useEffect, useRef, useState } from 'react';
import {
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts';
import {
  type ElevationProfileResponse,
  fetchElevationProfile,
} from '../../lib/api/elevationProfile';
import { mapColorTokens } from '../../lib/mapColorTokens';
import { buildProfileChartRows, type ProfileChartRow } from './profileChartRows';
import {
  formatAxisDistance,
  formatCursorReadout,
  formatElevationM,
  formatEs,
  formatProfileDistance,
  formatRelief,
  formatSignedDeltaM,
  formatSlopePct,
  usesKilometreAxis,
} from './profileFormat';
import {
  localSlopePct,
  type ProfileRangeStats,
  profileGrade,
  profileSliceStats,
  sliceProfile,
} from './profileRange';

function hasProfileParts(
  geometry: Geometry | null | undefined
): geometry is LineString | MultiLineString {
  if (geometry?.type === 'LineString') {
    return geometry.coordinates.length >= 2;
  }
  if (geometry?.type === 'MultiLineString') {
    return geometry.coordinates.some((parte) => parte.length >= 2);
  }
  return false;
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

const SERIES = [
  {
    key: 'elevation_m' as const,
    name: 'GLO-30',
    color: 'var(--mantine-color-blue-6)',
  },
  {
    key: 'elevation_mde_ar' as const,
    name: 'MDE-Ar',
    color: 'var(--mantine-color-orange-6)',
  },
  {
    key: 'elevation_aw3d30' as const,
    name: 'AW3D30',
    color: 'var(--mantine-color-teal-6)',
  },
  {
    key: 'elevation_nasadem' as const,
    name: 'NASADEM',
    color: 'var(--mantine-color-violet-6)',
  },
];

type SeriesKey = (typeof SERIES)[number]['key'];

function seriesValue(row: ProfileChartRow | undefined, key: SeriesKey): number | null {
  if (!row) {
    return null;
  }
  const value = row[key];
  return typeof value === 'number' ? value : null;
}

export function ElevationProfileChart({
  geometry,
  onHoverLngLat,
  onPickLngLat,
  onRangeCoordinates,
  autoLoad = false,
}: {
  geometry: Geometry | null | undefined;
  onHoverLngLat?: (point: { lon: number; lat: number } | null) => void;
  onPickLngLat?: (point: { lon: number; lat: number }) => void;
  onRangeCoordinates?: (range: ProfileRangeStats | null) => void;
  /** Sample on mount. The ficha leaves this false and keeps its own button. */
  autoLoad?: boolean;
}) {
  const startLoaded = autoLoad && hasProfileParts(geometry);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>(
    startLoaded ? 'loading' : 'idle'
  );
  const [compareDems, setCompareDems] = useState(false);
  const [profile, setProfile] = useState<ElevationProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<{ a: number; b: number } | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [aboutOpen, setAboutOpen] = useState(false);
  const requestGen = useRef(0);
  const loadedOnce = useRef(startLoaded);
  const dragStart = useRef<number | null>(null);
  const dragged = useRef(false);
  const rangeCb = useRef(onRangeCoordinates);
  rangeCb.current = onRangeCoordinates;
  const hoverCb = useRef(onHoverLngLat);
  hoverCb.current = onHoverLngLat;

  useEffect(() => {
    setRange(null);
    setHoverIndex(null);
    rangeCb.current?.(null);
    hoverCb.current?.(null);
    if (autoLoad && hasProfileParts(geometry)) {
      loadedOnce.current = true;
    }
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
  }, [autoLoad, compareDems, geometry]);

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

  function clearRange() {
    setRange(null);
    onRangeCoordinates?.(null);
  }

  const chartRows = buildProfileChartRows(profile?.puntos ?? []);
  const visibleSeries = SERIES.filter((series) => chartRows.some((row) => row[series.key] != null));
  const grade = profileGrade(chartRows);
  const elevations = chartRows
    .map((row) => row.elevation_m)
    .filter((value): value is number => value != null);
  const minZ = elevations.length > 0 ? Math.min(...elevations) : null;
  const maxZ = elevations.length > 0 ? Math.max(...elevations) : null;
  const selection =
    range != null ? profileSliceStats(sliceProfile(chartRows, range.a, range.b)) : null;
  const spanM =
    chartRows.length >= 2
      ? chartRows[chartRows.length - 1]!.distance_m - chartRows[0]!.distance_m
      : (profile?.length_m ?? 0);
  const hoverRow = hoverIndex != null ? chartRows[hoverIndex] : undefined;
  const cursorLabel = hoverRow
    ? formatCursorReadout(
        hoverRow.distance_m,
        hoverRow.elevation_m,
        localSlopePct(chartRows, hoverIndex ?? -1)
      )
    : null;
  const cursorFrac =
    hoverRow && spanM > 0
      ? Math.min(1, Math.max(0, (hoverRow.distance_m - (chartRows[0]?.distance_m ?? 0)) / spanM))
      : null;

  const graphHeader =
    minZ != null &&
    maxZ != null &&
    grade.mean_elevation_m != null &&
    grade.median_elevation_m != null
      ? `Gráfico mín ${formatEs(minZ, 1)} · prom ${formatEs(grade.mean_elevation_m, 1)} · med ${formatEs(grade.median_elevation_m, 1)} · máx ${formatEs(maxZ, 1)} m`
      : null;

  const tramoHeader =
    grade.mean_slope_pct != null
      ? `Tramo ${formatProfileDistance(spanM)} · ${formatRelief(grade.ascent_m, grade.descent_m)} · pend. máx ${
          grade.max_up_slope_pct != null ? formatSlopePct(grade.max_up_slope_pct) : '—'
        } / ${grade.max_down_slope_pct != null ? formatSlopePct(grade.max_down_slope_pct) : '—'} · prom ${formatSlopePct(grade.mean_slope_pct)}`
      : `Tramo ${formatProfileDistance(spanM)}`;

  return (
    <Stack gap={6} data-testid="elevation-profile">
      {status === 'idle' && !autoLoad ? (
        <Button size="xs" variant="light" onClick={() => void load()}>
          Perfil de elevación
        </Button>
      ) : null}
      {status === 'loading' ? (
        <Stack gap={6} data-testid="elevation-profile-loading" aria-busy="true" aria-live="polite">
          <Text size="xs" c="dimmed">
            Muestreando el modelo de elevación…
          </Text>
          <Skeleton height={12} width="80%" radius="sm" />
          <Skeleton height={12} width="55%" radius="sm" />
          <Skeleton height={148} radius="sm" />
        </Stack>
      ) : null}
      {status === 'error' ? (
        <Alert
          color="yellow"
          data-testid="elevation-profile-error"
          title="No se pudo armar el perfil"
        >
          <Stack gap={6}>
            <Text size="xs">{error}</Text>
            <Button size="xs" variant="light" onClick={() => void load()}>
              Reintentar
            </Button>
          </Stack>
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
          {graphHeader ? (
            <Text size="xs" data-testid="elevation-profile-extrema">
              {graphHeader}
            </Text>
          ) : (
            <Text size="xs" c="dimmed">
              Sin muestras válidas sobre el DEM.
            </Text>
          )}
          <Text size="xs" data-testid="elevation-profile-tramo-stats">
            {tramoHeader}
          </Text>
          {selection && range ? (
            <Group gap={6} wrap="nowrap" align="flex-start">
              <Text size="xs" data-testid="elevation-profile-selection" style={{ flex: 1 }}>
                {`Selección (${formatProfileDistance(Math.min(range.a, range.b))}–${formatProfileDistance(Math.max(range.a, range.b))}) ${formatProfileDistance(selection.length_m)}`}
                {selection.delta_m != null ? ` · Δ ${formatSignedDeltaM(selection.delta_m)}` : ''}
                {selection.mean_slope_pct != null
                  ? ` · pend. prom ${formatSlopePct(selection.mean_slope_pct)}`
                  : ''}
              </Text>
              <Button
                size="compact-xs"
                variant="subtle"
                onClick={clearRange}
                data-testid="elevation-profile-clear"
              >
                Limpiar
              </Button>
            </Group>
          ) : null}
          {chartRows.some((row) => row.elevation_m != null) ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'stretch', flexWrap: 'wrap' }}>
              <div
                data-testid="elevation-profile-chart"
                data-axis={usesKilometreAxis(spanM) ? 'km' : 'm'}
                style={{ position: 'relative', flex: '1 1 180px', minWidth: 0, height: 168 }}
              >
                {cursorLabel && cursorFrac != null ? (
                  <div
                    data-testid="elevation-profile-cursor"
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: `calc(40px + (100% - 48px) * ${cursorFrac})`,
                      transform:
                        cursorFrac < 0.12
                          ? 'translateX(0)'
                          : cursorFrac > 0.88
                            ? 'translateX(-100%)'
                            : 'translateX(-50%)',
                      fontSize: 11,
                      lineHeight: '14px',
                      whiteSpace: 'nowrap',
                      pointerEvents: 'none',
                      zIndex: 1,
                      color: 'var(--mantine-color-text)',
                    }}
                  >
                    {cursorLabel}
                  </div>
                ) : null}
                <ResponsiveContainer width="100%" height={168}>
                  <LineChart
                    data={chartRows}
                    margin={{ top: 16, right: 8, left: 0, bottom: 0 }}
                    onMouseDown={(event) => {
                      const distance = distanceAtIndex(chartRows, event.activeIndex);
                      dragStart.current = distance;
                      dragged.current = false;
                    }}
                    onMouseMove={(event) => {
                      const index = sampleIndex(event.activeIndex);
                      setHoverIndex(index);
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
                      setHoverIndex(null);
                      onHoverLngLat?.(null);
                      dragStart.current = null;
                      dragged.current = false;
                    }}
                  >
                    <XAxis
                      dataKey="distance_m"
                      tickFormatter={(value) => formatAxisDistance(Number(value), spanM)}
                      fontSize={10}
                      minTickGap={28}
                    />
                    <YAxis
                      domain={['auto', 'auto']}
                      tickFormatter={(value) => formatEs(Number(value), 0)}
                      width={40}
                      fontSize={10}
                    />
                    {hoverRow ? (
                      <ReferenceLine
                        x={hoverRow.distance_m}
                        stroke={mapColorTokens.h868e96}
                        strokeDasharray="3 3"
                        ifOverflow="hidden"
                      />
                    ) : null}
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
                    {visibleSeries.some((series) => series.key === 'elevation_mde_ar') ? (
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
                    {visibleSeries.some((series) => series.key === 'elevation_aw3d30') ? (
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
                    {visibleSeries.some((series) => series.key === 'elevation_nasadem') ? (
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
              {visibleSeries.length > 0 ? (
                <Stack gap={2} data-testid="elevation-profile-legend" style={{ flex: '0 0 auto' }}>
                  <Text size="xs" fw={600}>
                    DEMs
                  </Text>
                  {visibleSeries.map((series) => {
                    const value = seriesValue(hoverRow, series.key);
                    return (
                      <Text key={series.key} size="xs" style={{ color: series.color }}>
                        {series.name}
                        {value != null
                          ? ` ${formatElevationM(value)}`
                          : hoverRow
                            ? ' sin dato'
                            : ''}
                      </Text>
                    );
                  })}
                </Stack>
              ) : null}
            </div>
          ) : null}
          <div>
            <Button
              size="compact-xs"
              variant="subtle"
              aria-expanded={aboutOpen}
              onClick={() => setAboutOpen((open) => !open)}
              data-testid="elevation-profile-about-toggle"
            >
              Sobre los datos
            </Button>
            <Stack gap={2} hidden={!aboutOpen} style={aboutOpen ? undefined : { display: 'none' }}>
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
            </Stack>
          </div>
        </>
      ) : null}
    </Stack>
  );
}
