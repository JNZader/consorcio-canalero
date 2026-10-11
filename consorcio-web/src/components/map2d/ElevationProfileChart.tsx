/**
 * Google Earth-style elevation profile: distance (m) vs elevation (m).
 *
 * Loads only after the operator asks. GLO-30 disclaimer is always shown with
 * the curve. Nodata holes are omitted from the line (recharts skips null y).
 */

import { Alert, Button, Stack, Text } from '@mantine/core';
import { useRef, useState } from 'react';
import type { Geometry, LineString } from 'geojson';
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import {
  fetchElevationProfile,
  type ElevationProfileResponse,
} from '../../lib/api/elevationProfile';

function isLineString(geometry: Geometry | null | undefined): geometry is LineString {
  return geometry?.type === 'LineString' && geometry.coordinates.length >= 2;
}

function formatM(value: number): string {
  return `${value.toFixed(1)} m`;
}

function lngLatAtIndex(
  rows: readonly { lon?: number; lat?: number }[],
  rawIndex: unknown,
): { lon: number; lat: number } | null {
  const index = typeof rawIndex === 'number' ? rawIndex : Number(rawIndex);
  const row = Number.isInteger(index) ? rows[index] : undefined;
  if (row && typeof row.lon === 'number' && typeof row.lat === 'number') {
    return { lon: row.lon, lat: row.lat };
  }
  return null;
}

export function ElevationProfileChart({
  geometry,
  onHoverLngLat,
  onPickLngLat,
}: {
  geometry: Geometry | null | undefined;
  onHoverLngLat?: (point: { lon: number; lat: number } | null) => void;
  onPickLngLat?: (point: { lon: number; lat: number }) => void;
}) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [profile, setProfile] = useState<ElevationProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  if (!isLineString(geometry)) {
    return null;
  }
  const line = geometry;

  async function load() {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setStatus('loading');
    setError(null);
    try {
      const data = await fetchElevationProfile(line);
      setProfile(data);
      setStatus('ready');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo muestrear el DEM');
      setStatus('error');
    } finally {
      inFlight.current = false;
    }
  }

  const chartRows =
    profile?.puntos.map((p) => ({
      distance_m: p.distance_m,
      elevation_m: p.elevation_m,
      elevation_mde_ar: p.elevation_mde_ar,
      lon: p.lon,
      lat: p.lat,
    })) ?? [];
  const hasMdeAr = chartRows.some((row) => row.elevation_mde_ar != null);

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
          <Text size="xs" c="dimmed" data-testid="elevation-profile-disclaimer">
            {profile.disclaimer}
          </Text>
          {profile.mde_ar_disclaimer ? (
            <Text size="xs" c="dimmed" data-testid="elevation-profile-mde-ar">
              {profile.mde_ar_disclaimer}
            </Text>
          ) : null}
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
          {chartRows.some((row) => row.elevation_m != null) ? (
            <div data-testid="elevation-profile-chart" style={{ width: '100%', height: 160 }}>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart
                  data={chartRows}
                  margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                  onMouseMove={(event) => {
                    onHoverLngLat?.(lngLatAtIndex(chartRows, event.activeIndex));
                  }}
                  onClick={(event) => {
                    const point = lngLatAtIndex(chartRows, event.activeIndex);
                    if (point) {
                      onPickLngLat?.(point);
                    }
                  }}
                  onMouseLeave={() => onHoverLngLat?.(null)}
                >
                  <XAxis dataKey="distance_m" tickFormatter={(v) => `${Math.round(Number(v))}`} />
                  <YAxis domain={['auto', 'auto']} tickFormatter={(v) => `${Number(v).toFixed(0)}`} width={40} />
                  <Tooltip
                    formatter={(value) =>
                      value == null ? 'sin dato' : formatM(Number(value))
                    }
                    labelFormatter={(label) => `${Math.round(Number(label))} m`}
                  />
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
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : null}
        </>
      ) : null}
    </Stack>
  );
}
