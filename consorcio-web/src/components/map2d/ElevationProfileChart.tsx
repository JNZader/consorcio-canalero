/**
 * Google Earth-style elevation profile: distance (m) vs elevation (m).
 *
 * Loads only after the operator asks. GLO-30 disclaimer is always shown with
 * the curve. Nodata holes are omitted from the line (recharts skips null y).
 */

import { Alert, Button, Stack, Text } from '@mantine/core';
import { useState } from 'react';
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

export function ElevationProfileChart({ geometry }: { geometry: Geometry | null | undefined }) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [profile, setProfile] = useState<ElevationProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isLineString(geometry)) {
    return null;
  }
  const line = geometry;

  async function load() {
    setStatus('loading');
    setError(null);
    try {
      const data = await fetchElevationProfile(line);
      setProfile(data);
      setStatus('ready');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo muestrear el DEM');
      setStatus('error');
    }
  }

  const chartRows =
    profile?.puntos.map((p) => ({
      distance_m: p.distance_m,
      elevation_m: p.elevation_m,
    })) ?? [];

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
                <LineChart data={chartRows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <XAxis dataKey="distance_m" tickFormatter={(v) => `${Math.round(Number(v))}`} />
                  <YAxis domain={['auto', 'auto']} tickFormatter={(v) => `${Number(v).toFixed(0)}`} width={40} />
                  <Tooltip
                    formatter={(value) =>
                      value == null ? 'sin dato' : formatM(Number(value))
                    }
                    labelFormatter={(label) => `${Math.round(Number(label))} m`}
                  />
                  <Line
                    type="monotone"
                    dataKey="elevation_m"
                    stroke="var(--mantine-color-blue-6)"
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : null}
        </>
      ) : null}
    </Stack>
  );
}
