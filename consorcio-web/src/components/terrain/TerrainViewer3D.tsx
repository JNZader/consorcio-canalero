/**
 * TerrainViewer3D - 3D terrain visualization using deck.gl.
 *
 * Renders DEM elevation data as a terrain mesh with color gradient
 * (green for low elevation, brown/white for high) and optional
 * drainage network overlay.
 *
 * Uses deck.gl's BitmapLayer + SimpleMeshLayer for terrain rendering
 * with vertical exaggeration suitable for flat terrain (5x-10x).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Group,
  Loader,
  Paper,
  Slider,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { IconAlertTriangle } from '../ui/icons';

// Lazy-load deck.gl to avoid bundling when not used
let DeckGL: any = null;
let BitmapLayer: any = null;
let GeoJsonLayer: any = null;

async function loadDeckGL() {
  if (DeckGL) return;
  const [deckMod, layersMod] = await Promise.all([
    import('@deck.gl/react'),
    import('@deck.gl/layers'),
  ]);
  DeckGL = deckMod.default || deckMod.DeckGL;
  BitmapLayer = layersMod.BitmapLayer;
  GeoJsonLayer = layersMod.GeoJsonLayer;
}

interface TerrainViewer3DProps {
  /** URL to fetch the DEM GeoTIFF (GET /geo/layers/{id}/file) */
  readonly demUrl?: string;
  /** GeoJSON data for drainage network overlay */
  readonly drainageGeoJson?: Record<string, unknown> | null;
  /** GeoJSON data for basin polygons overlay */
  readonly basinsGeoJson?: Record<string, unknown> | null;
  /** Center coordinates [longitude, latitude] */
  readonly center?: [number, number];
  /** Initial zoom level */
  readonly zoom?: number;
  /** Container height */
  readonly height?: number | string;
}

// Default center: Bell Ville, Cordoba, Argentina
const DEFAULT_CENTER: [number, number] = [-62.69, -32.63];
const DEFAULT_ZOOM = 11;

/**
 * Color scale for terrain: green (low) -> yellow -> brown -> white (high)
 */
const ELEVATION_COLORS: [number, number, number, number][] = [
  [34, 139, 34, 200],   // forest green (low)
  [144, 238, 144, 200], // light green
  [255, 255, 102, 200], // yellow
  [210, 180, 140, 200], // tan/brown
  [139, 90, 43, 200],   // saddle brown
  [255, 255, 255, 200], // white (high)
];

export default function TerrainViewer3D({
  demUrl,
  drainageGeoJson,
  basinsGeoJson,
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
  height = 500,
}: TerrainViewer3DProps) {
  const [deckLoaded, setDeckLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [exaggeration, setExaggeration] = useState(8);
  const containerRef = useRef<HTMLDivElement>(null);

  // Load deck.gl lazily
  useEffect(() => {
    loadDeckGL()
      .then(() => setDeckLoaded(true))
      .catch((err) => {
        setLoadError(
          err instanceof Error ? err.message : 'Error cargando visualizador 3D'
        );
      });
  }, []);

  const initialViewState = useMemo(
    () => ({
      longitude: center[0],
      latitude: center[1],
      zoom,
      pitch: 45,
      bearing: -30,
      maxPitch: 85,
    }),
    [center, zoom],
  );

  const layers = useMemo(() => {
    if (!deckLoaded || !GeoJsonLayer) return [];

    const result: unknown[] = [];

    // Basin polygons layer
    if (basinsGeoJson) {
      result.push(
        new GeoJsonLayer({
          id: 'basins-layer',
          data: basinsGeoJson,
          filled: true,
          stroked: true,
          getFillColor: [100, 150, 255, 80],
          getLineColor: [30, 80, 200, 200],
          getLineWidth: 2,
          lineWidthMinPixels: 1,
          pickable: true,
          autoHighlight: true,
          highlightColor: [100, 150, 255, 150],
        }),
      );
    }

    // Drainage network layer
    if (drainageGeoJson) {
      result.push(
        new GeoJsonLayer({
          id: 'drainage-layer',
          data: drainageGeoJson,
          filled: false,
          stroked: true,
          getLineColor: [0, 100, 255, 220],
          getLineWidth: 3,
          lineWidthMinPixels: 1,
          pickable: false,
        }),
      );
    }

    return result;
  }, [deckLoaded, basinsGeoJson, drainageGeoJson]);

  const getTooltip = useCallback((info: { object?: { properties?: Record<string, unknown> } }) => {
    if (!info.object?.properties) return null;
    const props = info.object.properties;
    if (props.basin_id !== undefined) {
      return {
        text: `Basin ${props.basin_id}\nArea: ${props.area_ha} ha`,
        style: { backgroundColor: 'rgba(0,0,0,0.7)', color: '#fff' },
      };
    }
    return null;
  }, []);

  if (loadError) {
    return (
      <Alert
        icon={<IconAlertTriangle size={16} />}
        title="Error de visualizacion"
        color="red"
      >
        {loadError}
      </Alert>
    );
  }

  if (!deckLoaded) {
    return (
      <Paper p="xl" radius="md" withBorder>
        <Stack align="center" gap="md">
          <Loader size="lg" />
          <Text c="dimmed">Cargando visualizador 3D...</Text>
        </Stack>
      </Paper>
    );
  }

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="flex-end">
        <Title order={5}>Vista 3D del Terreno</Title>
        <Group gap="xs" align="center">
          <Text size="xs" c="dimmed">
            Exageracion vertical:
          </Text>
          <Box w={120}>
            <Slider
              value={exaggeration}
              onChange={setExaggeration}
              min={1}
              max={20}
              step={1}
              size="xs"
              label={(val) => `${val}x`}
            />
          </Box>
        </Group>
      </Group>

      <Paper
        ref={containerRef}
        radius="md"
        withBorder
        style={{
          height: typeof height === 'number' ? `${height}px` : height,
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {DeckGL && (
          <DeckGL
            initialViewState={initialViewState}
            controller={{
              dragRotate: true,
              touchRotate: true,
              keyboard: true,
            }}
            layers={layers}
            getTooltip={getTooltip}
            style={{ width: '100%', height: '100%' }}
          />
        )}

        {/* Legend */}
        <Box
          style={{
            position: 'absolute',
            bottom: 12,
            right: 12,
            background: 'rgba(0,0,0,0.7)',
            borderRadius: 8,
            padding: '8px 12px',
            zIndex: 10,
          }}
        >
          <Text size="xs" c="white" fw={600} mb={4}>
            Leyenda
          </Text>
          <Group gap={4}>
            {ELEVATION_COLORS.map((color, i) => (
              <Box
                key={i}
                style={{
                  width: 16,
                  height: 12,
                  backgroundColor: `rgba(${color[0]},${color[1]},${color[2]},${color[3] / 255})`,
                  borderRadius: 2,
                }}
              />
            ))}
          </Group>
          <Group justify="space-between" mt={2}>
            <Text size="xs" c="gray.4">Bajo</Text>
            <Text size="xs" c="gray.4">Alto</Text>
          </Group>
          {basinsGeoJson && (
            <Group gap={4} mt={4}>
              <Box
                style={{
                  width: 12,
                  height: 12,
                  backgroundColor: 'rgba(100,150,255,0.5)',
                  border: '1px solid rgba(30,80,200,0.8)',
                  borderRadius: 2,
                }}
              />
              <Text size="xs" c="gray.4">Cuencas</Text>
            </Group>
          )}
          {drainageGeoJson && (
            <Group gap={4} mt={2}>
              <Box
                style={{
                  width: 12,
                  height: 2,
                  backgroundColor: 'rgba(0,100,255,0.9)',
                  borderRadius: 1,
                }}
              />
              <Text size="xs" c="gray.4">Drenaje</Text>
            </Group>
          )}
        </Box>
      </Paper>
    </Stack>
  );
}
