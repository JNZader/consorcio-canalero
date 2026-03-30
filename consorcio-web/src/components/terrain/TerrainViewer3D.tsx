/**
 * TerrainViewer3D - 3D terrain visualization using deck.gl TerrainLayer.
 *
 * Renders terrain-RGB elevation tiles as a 3D mesh with optional colorized
 * texture overlay. Uses high vertical exaggeration (default 15x) because
 * Bell Ville terrain is very flat (elevation ~80-120m).
 *
 * deck.gl TerrainLayer decodes Mapbox Terrain-RGB tiles natively:
 *   elevation = (R * 65536 + G * 256 + B) * 0.1 - 10000
 */

import { useEffect, useMemo, useState } from 'react';
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
import { API_URL } from '../../lib/api';

// Lazy-loaded deck.gl modules
let DeckGL: any = null;
let TerrainLayer: any = null;
let webgl2Adapter: any = null;

async function loadDeckGL() {
  if (DeckGL) return;
  const [deckMod, geoLayersMod, webglMod] = await Promise.all([
    import('@deck.gl/react'),
    import('@deck.gl/geo-layers'),
    import('@luma.gl/webgl'),
  ]);
  DeckGL = deckMod.default || deckMod.DeckGL;
  TerrainLayer = geoLayersMod.TerrainLayer;
  webgl2Adapter = webglMod.webgl2Adapter;
}

/**
 * Mapbox Terrain-RGB elevation decoder values.
 * elevation = R * 6553.6 + G * 25.6 + B * 0.1 - 10000
 */
const TERRAIN_RGB_DECODER = {
  rScaler: 6553.6,
  gScaler: 25.6,
  bScaler: 0.1,
  offset: -10000,
} as const;

interface TerrainViewer3DProps {
  /** UUID of the DEM layer for terrain-RGB tiles */
  readonly demLayerId?: string;
  /** UUID of a layer to use as texture (colorized tiles draped on terrain) */
  readonly textureLayerId?: string;
  /** Center coordinates [longitude, latitude] */
  readonly center?: [number, number];
  /** Initial zoom level */
  readonly zoom?: number;
  /** Container height */
  readonly height?: number | string;
}

// Default center: Bell Ville, Cordoba, Argentina
const DEFAULT_CENTER: [number, number] = [-62.69, -32.63];
const DEFAULT_ZOOM = 12;

// Vertical exaggeration range for flat terrain
const MIN_EXAGGERATION = 1;
const MAX_EXAGGERATION = 30;
const DEFAULT_EXAGGERATION = 15;

/**
 * Build a tile URL template for the backend tile proxy.
 * Uses {x}, {y}, {z} placeholders that deck.gl replaces per tile.
 */
function buildTerrainTileUrl(layerId: string, encoding?: string): string {
  const base = `${API_URL}/api/v2/geo/layers/${layerId}/tiles/{z}/{x}/{y}.png`;
  if (encoding) {
    return `${base}?encoding=${encodeURIComponent(encoding)}`;
  }
  return base;
}

export default function TerrainViewer3D({
  demLayerId,
  textureLayerId,
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
  height = 500,
}: TerrainViewer3DProps) {
  const [deckLoaded, setDeckLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [exaggeration, setExaggeration] = useState(DEFAULT_EXAGGERATION);

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

  /**
   * Apply vertical exaggeration by scaling the elevation decoder.
   * Multiplying rScaler/gScaler/bScaler by N effectively scales
   * all decoded elevation values by N.
   */
  const elevationDecoder = useMemo(
    () => ({
      rScaler: TERRAIN_RGB_DECODER.rScaler * exaggeration,
      gScaler: TERRAIN_RGB_DECODER.gScaler * exaggeration,
      bScaler: TERRAIN_RGB_DECODER.bScaler * exaggeration,
      offset: TERRAIN_RGB_DECODER.offset * exaggeration,
    }),
    [exaggeration],
  );

  const layers = useMemo(() => {
    if (!deckLoaded || !TerrainLayer || !demLayerId) return [];

    return [
      new TerrainLayer({
        id: 'terrain-layer',
        minZoom: 0,
        maxZoom: 15,
        elevationData: buildTerrainTileUrl(demLayerId, 'terrain-rgb'),
        texture: textureLayerId
          ? buildTerrainTileUrl(textureLayerId)
          : buildTerrainTileUrl(demLayerId),
        elevationDecoder,
        // meshMaxError controls mesh detail AND skirt height (skirt = meshMaxError * 2).
        // Low value = detailed mesh + minimal side walls.
        meshMaxError: 0.5,
        wireframe: false,
        material: {
          ambient: 0.35,
          diffuse: 0.6,
          shininess: 32,
          specularColor: [30, 30, 30],
        },
        color: [255, 255, 255],
        operation: 'terrain+draw',
      }),
    ];
  }, [deckLoaded, demLayerId, textureLayerId, elevationDecoder]);

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

  if (!demLayerId) {
    return (
      <Alert
        icon={<IconAlertTriangle size={16} />}
        title="Sin capa DEM"
        color="yellow"
      >
        No hay capa DEM disponible para visualizar en 3D. Ejecuta el pipeline
        DEM primero.
      </Alert>
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
          <Box w={140}>
            <Slider
              value={exaggeration}
              onChange={setExaggeration}
              min={MIN_EXAGGERATION}
              max={MAX_EXAGGERATION}
              step={1}
              size="xs"
              label={(val) => `${val}x`}
              marks={[
                { value: 1, label: '1x' },
                { value: 15, label: '15x' },
                { value: 30, label: '30x' },
              ]}
            />
          </Box>
        </Group>
      </Group>

      <Paper
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
            deviceProps={{
              type: 'webgl' as const,
              adapters: webgl2Adapter ? [webgl2Adapter] : undefined,
            }}
            layers={layers}
            style={{ width: '100%', height: '100%', background: '#1a1a2e' }}
            getTooltip={null}
          />
        )}

        {/* Elevation info overlay */}
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
            Terreno 3D
          </Text>
          <Text size="xs" c="gray.4">
            Exageracion: {exaggeration}x
          </Text>
          <Text size="xs" c="gray.4">
            Arrastre para rotar, scroll para zoom
          </Text>
        </Box>
      </Paper>
    </Stack>
  );
}
