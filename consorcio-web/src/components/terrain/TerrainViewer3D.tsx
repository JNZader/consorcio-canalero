/**
 * TerrainViewer3D - 3D terrain visualization using three.js + react-three-fiber.
 *
 * Renders terrain-RGB elevation tiles as a PlaneGeometry mesh with colorized
 * texture overlay. Uses relative vertical exaggeration: subtracts minimum
 * elevation first so the terrain range (not absolute altitude) is exaggerated.
 *
 * Terrain-RGB decoding:
 *   elevation = (R * 256 * 256 + G * 256 + B) * 0.1 - 10000
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
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
import type { Mesh, Texture } from 'three';
import {
  CanvasTexture,
  ClampToEdgeWrapping,
  DoubleSide,
  LinearFilter,
  PlaneGeometry,
  SRGBColorSpace,
} from 'three';
import { IconAlertTriangle } from '../ui/icons';
import { API_URL } from '../../lib/api';

/* -------------------------------------------------------------------------- */
/*  Constants                                                                  */
/* -------------------------------------------------------------------------- */

const DEFAULT_CENTER: [number, number] = [-62.69, -32.63];
const DEFAULT_ZOOM = 12;

const MIN_EXAGGERATION = 1;
const MAX_EXAGGERATION = 50;
const DEFAULT_EXAGGERATION = 15;

/** Tile pixel size (standard web map tile). */
const TILE_SIZE = 256;

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                    */
/* -------------------------------------------------------------------------- */

/** Convert lat/lon to tile coordinates at a given zoom level. */
function latLonToTile(
  lat: number,
  lon: number,
  zoom: number,
): { x: number; y: number } {
  const n = 2 ** zoom;
  const x = Math.floor(((lon + 180) / 360) * n);
  const latRad = (lat * Math.PI) / 180;
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) *
      n,
  );
  return { x, y };
}

/** Build a tile URL for the backend proxy. */
function buildTileUrl(
  layerId: string,
  z: number,
  x: number,
  y: number,
  encoding?: string,
): string {
  const base = `${API_URL}/api/v2/geo/layers/${layerId}/tiles/${z}/${x}/${y}.png`;
  return encoding ? `${base}?encoding=${encodeURIComponent(encoding)}` : base;
}

/**
 * Load an image via canvas and return its RGBA pixel data.
 * Returns null if the fetch returns 204 (no content / out of bounds).
 */
async function loadImagePixels(
  url: string,
): Promise<{ data: Uint8ClampedArray; width: number; height: number } | null> {
  const response = await fetch(url, { mode: 'cors' });
  if (response.status === 204) return null;
  if (!response.ok)
    throw new Error(`Tile fetch failed: ${response.status} ${response.statusText}`);

  const blob = await response.blob();
  const bitmap = await createImageBitmap(blob);

  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext('2d')!;
  ctx.drawImage(bitmap, 0, 0);

  const imageData = ctx.getImageData(0, 0, bitmap.width, bitmap.height);
  return { data: imageData.data, width: bitmap.width, height: bitmap.height };
}

/**
 * Decode terrain-RGB pixels into elevation values.
 * Formula: elevation = (R * 256² + G * 256 + B) * 0.1 - 10000
 */
function decodeElevation(pixels: Uint8ClampedArray, count: number): Float32Array {
  const elevations = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    const idx = i * 4;
    const r = pixels[idx];
    const g = pixels[idx + 1];
    const b = pixels[idx + 2];
    elevations[i] = (r * 65536 + g * 256 + b) * 0.1 - 10000;
  }
  return elevations;
}

/* -------------------------------------------------------------------------- */
/*  Data hook                                                                  */
/* -------------------------------------------------------------------------- */

interface TerrainData {
  elevations: Float32Array;
  minElev: number;
  maxElev: number;
  width: number;
  height: number;
  textureUrl: string;
}

function useTerrainData(
  demLayerId: string | undefined,
  textureLayerId: string | undefined,
  center: [number, number],
  zoom: number,
) {
  const [data, setData] = useState<TerrainData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!demLayerId) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    const tile = latLonToTile(center[1], center[0], zoom);
    const elevUrl = buildTileUrl(demLayerId, zoom, tile.x, tile.y, 'terrain-rgb');
    const texLayerId = textureLayerId ?? demLayerId;
    const texUrl = buildTileUrl(texLayerId, zoom, tile.x, tile.y);

    loadImagePixels(elevUrl)
      .then((result) => {
        if (cancelled) return;
        if (!result) {
          setError('El tile de elevación está fuera de rango (204).');
          setLoading(false);
          return;
        }

        const { data: pixels, width, height } = result;
        const elevations = decodeElevation(pixels, width * height);

        let minElev = Number.POSITIVE_INFINITY;
        let maxElev = Number.NEGATIVE_INFINITY;
        for (let i = 0; i < elevations.length; i++) {
          if (elevations[i] < minElev) minElev = elevations[i];
          if (elevations[i] > maxElev) maxElev = elevations[i];
        }

        setData({ elevations, minElev, maxElev, width, height, textureUrl: texUrl });
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Error cargando elevación');
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [demLayerId, textureLayerId, center, zoom]);

  return { data, loading, error };
}

/* -------------------------------------------------------------------------- */
/*  Three.js terrain mesh                                                      */
/* -------------------------------------------------------------------------- */

interface TerrainMeshProps {
  data: TerrainData;
  exaggeration: number;
}

function TerrainMesh({ data, exaggeration }: TerrainMeshProps) {
  const meshRef = useRef<Mesh>(null);
  const { elevations, minElev, width, height, textureUrl } = data;

  const segments = width - 1;
  const segmentsY = height - 1;

  // Build geometry with relative exaggeration
  const geometry = useMemo(() => {
    const geo = new PlaneGeometry(10, 10, segments, segmentsY);
    const posAttr = geo.attributes.position;

    for (let iy = 0; iy < height; iy++) {
      for (let ix = 0; ix < width; ix++) {
        // PlaneGeometry lays out vertices row by row, top to bottom
        const vertexIndex = iy * width + ix;
        const relativeElev = elevations[vertexIndex] - minElev;
        // Z is the "up" axis for PlaneGeometry before rotation
        posAttr.setZ(vertexIndex, relativeElev * exaggeration * 0.001);
      }
    }

    posAttr.needsUpdate = true;
    geo.computeVertexNormals();
    return geo;
  }, [elevations, minElev, width, height, segments, segmentsY, exaggeration]);

  // Load texture
  const [texture, setTexture] = useState<Texture | null>(null);

  useEffect(() => {
    let cancelled = false;

    // Use fetch + createImageBitmap for CORS handling, then convert to CanvasTexture
    fetch(textureUrl, { mode: 'cors' })
      .then((res) => {
        if (!res.ok) throw new Error(`Texture fetch failed: ${res.status}`);
        return res.blob();
      })
      .then((blob) => createImageBitmap(blob))
      .then((bitmap) => {
        if (cancelled) return;
        const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
        const ctx = canvas.getContext('2d')!;
        ctx.drawImage(bitmap, 0, 0);

        // CanvasTexture needs HTMLCanvasElement, so copy to a regular canvas
        const htmlCanvas = document.createElement('canvas');
        htmlCanvas.width = bitmap.width;
        htmlCanvas.height = bitmap.height;
        const htmlCtx = htmlCanvas.getContext('2d')!;
        htmlCtx.drawImage(bitmap, 0, 0);

        const tex = new CanvasTexture(htmlCanvas);
        tex.colorSpace = SRGBColorSpace;
        tex.minFilter = LinearFilter;
        tex.magFilter = LinearFilter;
        tex.wrapS = ClampToEdgeWrapping;
        tex.wrapT = ClampToEdgeWrapping;
        tex.needsUpdate = true;
        setTexture(tex);
      })
      .catch((err) => {
        if (!cancelled) {
          console.warn('Failed to load terrain texture:', err);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [textureUrl]);

  return (
    <mesh ref={meshRef} geometry={geometry} rotation={[-Math.PI / 2, 0, 0]}>
      {texture ? (
        <meshStandardMaterial
          map={texture}
          side={DoubleSide}
          roughness={0.8}
          metalness={0.1}
        />
      ) : (
        <meshStandardMaterial
          color="#4a7c59"
          side={DoubleSide}
          roughness={0.8}
          metalness={0.1}
        />
      )}
    </mesh>
  );
}

/* -------------------------------------------------------------------------- */
/*  Camera auto-fit                                                            */
/* -------------------------------------------------------------------------- */

function AutoFitCamera() {
  const { camera } = useThree();

  useEffect(() => {
    camera.position.set(8, 6, 8);
    camera.lookAt(0, 0, 0);
  }, [camera]);

  return null;
}

/* -------------------------------------------------------------------------- */
/*  Main component                                                             */
/* -------------------------------------------------------------------------- */

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

export default function TerrainViewer3D({
  demLayerId,
  textureLayerId,
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
  height = 500,
}: TerrainViewer3DProps) {
  const [exaggeration, setExaggeration] = useState(DEFAULT_EXAGGERATION);

  const { data, loading, error } = useTerrainData(
    demLayerId,
    textureLayerId,
    center,
    zoom,
  );

  if (error) {
    return (
      <Alert
        icon={<IconAlertTriangle size={16} />}
        title="Error de visualización"
        color="red"
      >
        {error}
      </Alert>
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

  if (loading || !data) {
    return (
      <Paper p="xl" radius="md" withBorder>
        <Stack align="center" gap="md">
          <Loader size="lg" />
          <Text c="dimmed">Cargando terreno 3D...</Text>
        </Stack>
      </Paper>
    );
  }

  const elevRange = data.maxElev - data.minElev;

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="flex-end">
        <Title order={5}>Vista 3D del Terreno</Title>
        <Group gap="xs" align="center">
          <Text size="xs" c="dimmed">
            Exageracion vertical:
          </Text>
          <Box w={160}>
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
                { value: 25, label: '25x' },
                { value: 50, label: '50x' },
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
        <Canvas
          style={{ width: '100%', height: '100%', background: '#1a1a2e' }}
          camera={{ position: [8, 6, 8], fov: 50, near: 0.1, far: 1000 }}
        >
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 5]} intensity={1} />
          <directionalLight position={[-5, 5, -5]} intensity={0.3} />

          <TerrainMesh data={data} exaggeration={exaggeration} />

          <OrbitControls
            enableDamping
            dampingFactor={0.12}
            minDistance={2}
            maxDistance={30}
            maxPolarAngle={Math.PI * 0.85}
          />
          <AutoFitCamera />
        </Canvas>

        {/* Info overlay */}
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
            Rango: {elevRange.toFixed(1)}m ({data.minElev.toFixed(0)}–
            {data.maxElev.toFixed(0)}m)
          </Text>
          <Text size="xs" c="gray.4">
            Arrastre para rotar, scroll para zoom
          </Text>
        </Box>
      </Paper>
    </Stack>
  );
}
