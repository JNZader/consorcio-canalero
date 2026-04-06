/**
 * CanalSuggestionsPanel — Panel de sugerencias de la red de canales.
 *
 * Muestra resultados del analisis de red sobre un mapa Leaflet y en tabla,
 * con boton para disparar nuevos analisis.
 *
 * Tipos de sugerencia:
 * - hotspot: puntos criticos de acumulacion de flujo (circulos naranja/rojo)
 * - gap: zonas sin cobertura de canales (poligonos/puntos rojos)
 * - route: rutas sugeridas para nuevos canales (lineas azules punteadas)
 * - bottleneck: segmentos criticos por centralidad (lineas rojas gruesas)
 * - maintenance: prioridad de mantenimiento (segmentos coloreados)
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Center,
  Checkbox,
  Container,
  Group,
  Loader,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../../constants';
import {
  canalSuggestionsApi,
  type CanalSuggestion,
  type SuggestionTipo,
} from '../../lib/api';
import { formatDate } from '../../lib/formatters';
import { logger } from '../../lib/logger';
import {
  IconAlertTriangle,
  IconCheck,
  IconNetwork,
  IconPlayerPlay,
  IconRadar,
  IconRefresh,
  IconRoute,
  IconSortDescending,
  IconTool,
} from '../ui/icons';


// ===========================================
// CONSTANTS
// ===========================================

const TIPO_LABELS: Record<SuggestionTipo, string> = {
  hotspot: 'Punto critico',
  gap: 'Brecha de cobertura',
  route: 'Ruta sugerida',
  bottleneck: 'Cuello de botella',
  maintenance: 'Prioridad de mantenimiento',
};

const TIPO_COLORS: Record<SuggestionTipo, string> = {
  hotspot: '#e8590c',
  gap: '#e03131',
  route: '#1971c2',
  bottleneck: '#c92a2a',
  maintenance: '#2f9e44',
};

const TIPO_OPTIONS = [
  { value: '', label: 'Todos los tipos' },
  { value: 'hotspot', label: 'Puntos criticos' },
  { value: 'gap', label: 'Brechas de cobertura' },
  { value: 'route', label: 'Rutas sugeridas' },
  { value: 'bottleneck', label: 'Cuellos de botella' },
  { value: 'maintenance', label: 'Prioridad de mantenimiento' },
];

// ===========================================
// HELPERS
// ===========================================

/** Extract a displayable description from suggestion metadata */
function getDescription(s: CanalSuggestion): string {
  if (!s.metadata) return '-';
  const meta = s.metadata as Record<string, unknown>;

  // Try common metadata fields
  if (typeof meta.description === 'string') return meta.description;
  if (typeof meta.nombre === 'string') return meta.nombre;
  if (typeof meta.segment_name === 'string') return meta.segment_name;
  if (typeof meta.zone_id === 'string') return `Zona: ${meta.zone_id}`;
  if (typeof meta.severity === 'string') return `Severidad: ${meta.severity}`;
  if (typeof meta.gap_km === 'number') return `Distancia al canal: ${(meta.gap_km as number).toFixed(1)} km`;

  return '-';
}

/** Get the score color based on value (0-100 scale) */
function getScoreColor(score: number): string {
  if (score >= 75) return 'red';
  if (score >= 50) return 'orange';
  if (score >= 25) return 'yellow';
  return 'green';
}

/** Get the maintenance priority color for a 0-1 score */
function getMaintenanceColor(score: number): string {
  if (score >= 0.7) return '#e03131'; // red = high priority
  if (score >= 0.4) return '#f08c00'; // yellow/orange = medium
  return '#2f9e44'; // green = low
}

/** Extract geometry coordinates from suggestion metadata for map rendering */
function extractGeometry(
  s: CanalSuggestion
): { type: 'point'; lat: number; lng: number } | { type: 'line'; positions: [number, number][] } | null {
  if (!s.metadata) return null;
  const meta = s.metadata as Record<string, unknown>;

  // Check for GeoJSON geometry in metadata
  const geom = (meta.geometry ?? meta.geometria ?? meta.geom) as Record<string, unknown> | undefined;

  if (geom) {
    const gType = geom.type as string | undefined;
    const coords = geom.coordinates as unknown;

    if (gType === 'Point' && Array.isArray(coords) && coords.length >= 2) {
      return { type: 'point', lat: coords[1] as number, lng: coords[0] as number };
    }

    if (
      (gType === 'LineString' || gType === 'MultiLineString') &&
      Array.isArray(coords) &&
      coords.length > 0
    ) {
      // For LineString: [[lng, lat], ...]
      // For MultiLineString: [[[lng, lat], ...], ...]
      const lineCoords = gType === 'MultiLineString'
        ? (coords as number[][][]).flat()
        : (coords as number[][]);

      return {
        type: 'line',
        positions: lineCoords.map((c) => [c[1], c[0]] as [number, number]),
      };
    }

    if (gType === 'Polygon' && Array.isArray(coords) && coords.length > 0) {
      // Render polygon outline as a line
      const ring = (coords as number[][][])[0];
      return {
        type: 'line',
        positions: ring.map((c) => [c[1], c[0]] as [number, number]),
      };
    }
  }

  // Check for direct lat/lng in metadata
  const lat = meta.lat ?? meta.latitude;
  const lng = meta.lng ?? meta.longitude ?? meta.lon;
  if (typeof lat === 'number' && typeof lng === 'number') {
    return { type: 'point', lat, lng };
  }

  // Check centroid
  const centroid = meta.centroid as Record<string, unknown> | undefined;
  if (centroid) {
    const cCoords = centroid.coordinates as number[] | undefined;
    if (cCoords && cCoords.length >= 2) {
      return { type: 'point', lat: cCoords[1], lng: cCoords[0] };
    }
  }

  return null;
}

// ===========================================
// MAPLIBRE MAP COMPONENT
// ===========================================

interface SuggestionsMapProps {
  readonly suggestions: CanalSuggestion[];
  readonly visibleTypes: Set<SuggestionTipo>;
}

function SuggestionsMap({ suggestions, visibleTypes }: SuggestionsMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const [mapReady, setMapReady] = useState(false);

  // Initialize map
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap',
          },
        },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
      },
      center: [MAP_CENTER[1], MAP_CENTER[0]],
      zoom: MAP_DEFAULT_ZOOM ?? 11,
    });

    map.on('load', () => {
      mapInstanceRef.current = map;
      setMapReady(true);
    });

    return () => {
      map.remove();
      mapInstanceRef.current = null;
      setMapReady(false);
    };
  }, []);

  // Render suggestions as GeoJSON layers
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;

    const SOURCE_ID = 'suggestions-data';
    const POINTS_LAYER = 'suggestions-circles';
    const LINES_LAYER = 'suggestions-lines';

    // Build GeoJSON features
    const filtered = suggestions.filter((s) => visibleTypes.has(s.tipo as SuggestionTipo));

    const pointFeatures: GeoJSON.Feature[] = [];
    const lineFeatures: GeoJSON.Feature[] = [];

    for (const s of filtered) {
      const geo = extractGeometry(s);
      if (!geo) continue;
      const tipo = s.tipo as SuggestionTipo;
      const color = TIPO_COLORS[tipo];

      if (geo.type === 'point') {
        const radius = tipo === 'hotspot'
          ? Math.max(6, Math.min(18, s.score / 5))
          : tipo === 'gap' ? 10 : 8;
        pointFeatures.push({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [geo.lng, geo.lat] },
          properties: {
            id: s.id,
            tipo,
            color,
            radius,
            score: s.score,
            label: TIPO_LABELS[tipo],
            description: getDescription(s),
          },
        });
      } else if (geo.type === 'line') {
        const weight = tipo === 'bottleneck'
          ? Math.max(4, Math.min(10, s.score / 10))
          : tipo === 'maintenance' ? 5 : 3;
        const lineColor = tipo === 'maintenance' ? getMaintenanceColor(s.score / 100) : color;
        const dasharray = tipo === 'route' ? [10, 6] : [1];
        lineFeatures.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: geo.positions.map(([lat, lng]) => [lng, lat]) },
          properties: {
            id: s.id,
            tipo,
            color: lineColor,
            weight,
            dasharray: JSON.stringify(dasharray),
            score: s.score,
            label: TIPO_LABELS[tipo],
            description: getDescription(s),
          },
        });
      }
    }

    const pointsGeoJSON: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: pointFeatures };
    const linesGeoJSON: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: lineFeatures };

    // Update or create sources/layers
    const ptSource = map.getSource(`${SOURCE_ID}-points`) as maplibregl.GeoJSONSource | undefined;
    const lnSource = map.getSource(`${SOURCE_ID}-lines`) as maplibregl.GeoJSONSource | undefined;

    if (ptSource) {
      ptSource.setData(pointsGeoJSON);
    } else {
      map.addSource(`${SOURCE_ID}-points`, { type: 'geojson', data: pointsGeoJSON });
      map.addLayer({
        id: POINTS_LAYER,
        type: 'circle',
        source: `${SOURCE_ID}-points`,
        paint: {
          'circle-color': ['get', 'color'],
          'circle-radius': ['get', 'radius'],
          'circle-opacity': 0.5,
          'circle-stroke-color': ['get', 'color'],
          'circle-stroke-width': 2,
          'circle-stroke-opacity': 1,
        },
      });

      map.on('click', POINTS_LAYER, (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const { label, score, description } = f.properties as Record<string, string | number>;
        const coords = (f.geometry as GeoJSON.Point).coordinates as [number, number];
        if (popupRef.current) popupRef.current.remove();
        popupRef.current = new maplibregl.Popup()
          .setLngLat(coords)
          .setHTML(`<strong>${label}</strong><br/>Score: ${Number(score).toFixed(1)}${description !== '-' ? `<br/>${description}` : ''}`)
          .addTo(map);
      });

      map.on('mouseenter', POINTS_LAYER, () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', POINTS_LAYER, () => { map.getCanvas().style.cursor = ''; });
    }

    if (lnSource) {
      lnSource.setData(linesGeoJSON);
    } else {
      map.addSource(`${SOURCE_ID}-lines`, { type: 'geojson', data: linesGeoJSON });
      map.addLayer({
        id: LINES_LAYER,
        type: 'line',
        source: `${SOURCE_ID}-lines`,
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['get', 'weight'],
          'line-opacity': 0.8,
        },
      });

      map.on('click', LINES_LAYER, (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const { label, score, description } = f.properties as Record<string, string | number>;
        const coords = e.lngLat;
        if (popupRef.current) popupRef.current.remove();
        popupRef.current = new maplibregl.Popup()
          .setLngLat(coords)
          .setHTML(`<strong>${label}</strong><br/>Score: ${Number(score).toFixed(1)}${description !== '-' ? `<br/>${description}` : ''}`)
          .addTo(map);
      });

      map.on('mouseenter', LINES_LAYER, () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', LINES_LAYER, () => { map.getCanvas().style.cursor = ''; });
    }

    // Auto-fit bounds when we have data
    if (filtered.length > 0) {
      const allCoords: [number, number][] = [];
      for (const f of pointFeatures) {
        const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates;
        allCoords.push([lng, lat]);
      }
      for (const f of lineFeatures) {
        for (const coord of (f.geometry as GeoJSON.LineString).coordinates) {
          allCoords.push([coord[0], coord[1]]);
        }
      }
      if (allCoords.length > 0) {
        const lngs = allCoords.map(([lng]) => lng);
        const lats = allCoords.map(([, lat]) => lat);
        try {
          map.fitBounds(
            [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
            { padding: 30, maxZoom: 14 }
          );
        } catch {
          // ignore invalid bounds
        }
      }
    }
  }, [suggestions, visibleTypes, mapReady]);

  return <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />;
}

// ===========================================
// MAIN PANEL
// ===========================================

export default function CanalSuggestionsPanel() {
  // Data state
  const [suggestions, setSuggestions] = useState<CanalSuggestion[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [filterTipo, setFilterTipo] = useState<string>('');

  // Analysis trigger state
  const [analyzing, setAnalyzing] = useState(false);
  const [lastAnalysis, setLastAnalysis] = useState<string | null>(null);

  // Map layer visibility
  const [visibleTypes, setVisibleTypes] = useState<Set<SuggestionTipo>>(
    new Set(['hotspot', 'gap', 'route', 'bottleneck', 'maintenance'])
  );

  // Sort state
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Fetch results
  const fetchResults = useCallback(async (tipo?: string) => {
    setLoading(true);
    setError(null);
    try {
      const params: { tipo?: SuggestionTipo; limit?: number } = { limit: 100 };
      if (tipo) params.tipo = tipo as SuggestionTipo;
      const data = await canalSuggestionsApi.getResults(params);
      setSuggestions(data.items);
      setTotalCount(data.total);
      setBatchId(data.batch_id);

      // Set last analysis timestamp from data
      if (data.items.length > 0) {
        setLastAnalysis(data.items[0].created_at);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al cargar resultados';
      setError(message);
      logger.error('[CanalSuggestions] Error fetching results:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchResults();
  }, [fetchResults]);

  // Filter change
  const handleFilterChange = useCallback(
    (value: string | null) => {
      const tipo = value ?? '';
      setFilterTipo(tipo);
      fetchResults(tipo || undefined);
    },
    [fetchResults]
  );

  // Toggle layer visibility
  const toggleLayerType = useCallback((tipo: SuggestionTipo) => {
    setVisibleTypes((prev) => {
      const next = new Set(prev);
      if (next.has(tipo)) {
        next.delete(tipo);
      } else {
        next.add(tipo);
      }
      return next;
    });
  }, []);

  // Trigger analysis
  const handleAnalyze = useCallback(async () => {
    setAnalyzing(true);
    try {
      const res = await canalSuggestionsApi.postAnalyze();
      notifications.show({
        title: 'Analisis iniciado',
        message: `Tarea enviada (ID: ${res.task_id}). Los resultados se actualizaran cuando finalice.`,
        color: 'blue',
        autoClose: 8000,
      });

      // Poll for completion (simple approach: retry after delays)
      const pollIntervals = [5000, 10000, 15000, 20000, 30000];
      for (const delay of pollIntervals) {
        await new Promise((r) => setTimeout(r, delay));
        try {
          const data = await canalSuggestionsApi.getResults({ limit: 1 });
          if (data.batch_id && data.batch_id !== batchId) {
            // New batch detected
            notifications.show({
              title: 'Analisis completado',
              message: 'Los resultados se han actualizado.',
              color: 'green',
              icon: <IconCheck size={16} />,
            });
            fetchResults(filterTipo || undefined);
            setAnalyzing(false);
            return;
          }
        } catch {
          // Keep polling
        }
      }

      // After polling, try one final fetch
      notifications.show({
        title: 'Analisis en progreso',
        message: 'El analisis continua en segundo plano. Recarga manualmente para ver resultados.',
        color: 'yellow',
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al iniciar analisis';
      notifications.show({
        title: 'Error',
        message,
        color: 'red',
      });
      logger.error('[CanalSuggestions] Error triggering analysis:', err);
    } finally {
      setAnalyzing(false);
    }
  }, [batchId, fetchResults, filterTipo]);

  // Sorted suggestions for table
  const sortedSuggestions = useMemo(() => {
    const sorted = [...suggestions];
    sorted.sort((a, b) =>
      sortDir === 'desc' ? b.score - a.score : a.score - b.score
    );
    return sorted;
  }, [suggestions, sortDir]);

  // Summary stats
  const stats = useMemo(() => {
    const byTipo: Partial<Record<SuggestionTipo, number>> = {};
    for (const s of suggestions) {
      const t = s.tipo as SuggestionTipo;
      byTipo[t] = (byTipo[t] ?? 0) + 1;
    }
    return byTipo;
  }, [suggestions]);

  return (
    <Container size="xl" py="md">
      <Stack gap="lg">
        {/* Header */}
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={2}>Sugerencias de Red de Canales</Title>
            <Text c="dimmed" size="sm">
              Analisis inteligente de la red: puntos criticos, brechas, rutas sugeridas,
              cuellos de botella y prioridades de mantenimiento.
            </Text>
          </div>

          <Group gap="sm">
            <Tooltip label="Recargar resultados">
              <ActionIcon
                variant="light"
                size="lg"
                onClick={() => fetchResults(filterTipo || undefined)}
                loading={loading}
              >
                <IconRefresh size={18} />
              </ActionIcon>
            </Tooltip>

            <Button
              leftSection={analyzing ? <Loader size={14} /> : <IconRadar size={18} />}
              onClick={handleAnalyze}
              loading={analyzing}
              disabled={analyzing}
              color="blue"
            >
              {analyzing ? 'Analizando...' : 'Analizar Red'}
            </Button>
          </Group>
        </Group>

        {/* Last analysis timestamp */}
        {lastAnalysis && (
          <Text size="xs" c="dimmed">
            Ultimo analisis: {formatDate(lastAnalysis)}
          </Text>
        )}

        {/* Error alert */}
        {error && (
          <Alert
            color="red"
            icon={<IconAlertTriangle size={18} />}
            title="Error"
            withCloseButton
            onClose={() => setError(null)}
          >
            {error}
          </Alert>
        )}

        {/* Summary cards */}
        {suggestions.length > 0 && (
          <SimpleGrid cols={{ base: 2, sm: 3, md: 5 }} spacing="sm">
            {(Object.keys(TIPO_LABELS) as SuggestionTipo[]).map((tipo) => (
              <Paper key={tipo} p="sm" withBorder radius="md">
                <Group gap="xs" justify="space-between">
                  <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
                    {TIPO_LABELS[tipo]}
                  </Text>
                  <Badge size="lg" color={TIPO_COLORS[tipo]} variant="light">
                    {stats[tipo] ?? 0}
                  </Badge>
                </Group>
              </Paper>
            ))}
          </SimpleGrid>
        )}

        {/* Map with overlays */}
        <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
          <div style={{ height: 450 }}>
            <SuggestionsMap
              suggestions={suggestions}
              visibleTypes={visibleTypes}
            />
          </div>

          {/* Layer toggles */}
          <Group p="sm" gap="md" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>
            <Text size="xs" fw={600} c="dimmed">
              Capas:
            </Text>
            {(Object.keys(TIPO_LABELS) as SuggestionTipo[]).map((tipo) => (
              <Checkbox
                key={tipo}
                label={
                  <Text size="xs" c={TIPO_COLORS[tipo]} fw={500}>
                    {TIPO_LABELS[tipo]}
                  </Text>
                }
                checked={visibleTypes.has(tipo)}
                onChange={() => toggleLayerType(tipo)}
                size="xs"
              />
            ))}
          </Group>
        </Paper>

        {/* Results table */}
        <Paper withBorder radius="md" p="md">
          <Stack gap="sm">
            <Group justify="space-between">
              <Title order={4}>Resultados ({totalCount})</Title>
              <Group gap="sm">
                <Select
                  data={TIPO_OPTIONS}
                  value={filterTipo}
                  onChange={handleFilterChange}
                  placeholder="Filtrar por tipo"
                  size="xs"
                  w={220}
                  clearable={false}
                />
                <Tooltip label={sortDir === 'desc' ? 'Mayor score primero' : 'Menor score primero'}>
                  <ActionIcon
                    variant="light"
                    size="sm"
                    onClick={() => setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))}
                  >
                    <IconSortDescending
                      size={14}
                      style={{ transform: sortDir === 'asc' ? 'rotate(180deg)' : undefined }}
                    />
                  </ActionIcon>
                </Tooltip>
              </Group>
            </Group>

            {loading ? (
              <Center py="xl">
                <Loader />
              </Center>
            ) : suggestions.length === 0 ? (
              <Center py="xl">
                <Stack align="center" gap="xs">
                  <IconNetwork size={48} color="var(--mantine-color-dimmed)" />
                  <Text c="dimmed">
                    No hay resultados de analisis. Presiona &quot;Analizar Red&quot; para comenzar.
                  </Text>
                </Stack>
              </Center>
            ) : (
              <Table striped highlightOnHover withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Tipo</Table.Th>
                    <Table.Th>Score</Table.Th>
                    <Table.Th>Descripcion</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {sortedSuggestions.map((s) => (
                    <Table.Tr key={s.id}>
                      <Table.Td>
                        <Badge
                          color={TIPO_COLORS[s.tipo as SuggestionTipo]}
                          variant="light"
                          size="sm"
                        >
                          {TIPO_LABELS[s.tipo as SuggestionTipo] ?? s.tipo}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Badge color={getScoreColor(s.score)} variant="filled" size="sm">
                          {s.score.toFixed(1)}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{getDescription(s)}</Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Stack>
        </Paper>
      </Stack>
    </Container>
  );
}
