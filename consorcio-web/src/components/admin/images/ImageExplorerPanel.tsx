import {
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Paper,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import '@mantine/dates/styles.css';
import {
  IconAlertTriangle,
  IconCalendar,
  IconCheck,
  IconGitCompare,
  IconPhoto,
  IconRefresh,
  IconSatellite,
  IconX,
} from '../../ui/icons';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useCallback, useEffect, useRef, useState } from 'react';
import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../../../constants';
import { useConfigStore } from '../../../stores/configStore';
import { useSelectedImage, type SelectedImage } from '../../../hooks/useSelectedImage';
import { useImageComparison } from '../../../hooks/useImageComparison';
import { API_URL } from '../../../lib/api';
import { logger } from '../../../lib/logger';

// Types
interface Visualization {
  id: string;
  description: string;
}

interface ImageResult {
  tile_url: string;
  target_date: string;
  dates_available: string[];
  images_count: number;
  visualization: string;
  visualization_description: string;
  sensor: string;
  collection: string;
  flood_info?: {
    id: string;
    name: string;
    date: string;
    description: string;
    severity: string;
  };
}

interface HistoricFlood {
  id: string;
  name: string;
  date: string;
  description: string;
  severity: string;
}

// API base URL
const API_BASE = `${API_URL}/api/v1/images`;

// Estilo para la capa zona (borde rojo sin relleno)
const ZONA_STYLE = {
  color: '#FF0000',
  weight: 3,
  fillOpacity: 0,
};

export default function ImageExplorerPanel() {
  const config = useConfigStore((state) => state.config);
  
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const zonaLayerRef = useRef<L.GeoJSON | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImageResult | null>(null);

  // Filters
  const [selectedDate, setSelectedDate] = useState<Date | null>(new Date());
  const [daysBuffer, setDaysBuffer] = useState<string>(
    config?.analysis.default_days_back?.toString() || '10'
  );
  const [maxCloud, setMaxCloud] = useState<string>(
    config?.analysis.default_max_cloud?.toString() || '40'
  );
  const [visualization, setVisualization] = useState<string>('rgb');
  const [sensor, setSensor] = useState<'sentinel2' | 'sentinel1'>('sentinel2');

  // Data
  const [visualizations, setVisualizations] = useState<Visualization[]>([]);
  const [historicFloods, setHistoricFloods] = useState<HistoricFlood[]>([]);

  // Shared image selection
  const { selectedImage, setSelectedImage, clearSelectedImage } = useSelectedImage();

  // Image comparison
  const { comparison, setLeftImage, setRightImage, clearComparison, isReady: comparisonReady } = useImageComparison();

  // Initialize map
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const center = config?.map.center 
      ? ([config.map.center.lat, config.map.center.lng] as [number, number]) 
      : MAP_CENTER;
    const zoom = config?.map.zoom ?? MAP_DEFAULT_ZOOM;

    const map = L.map(mapRef.current, {
      center,
      zoom,
      zoomControl: true,
    });

    // Base layer - satellite
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      {
        attribution: 'Tiles &copy; Esri',
        maxZoom: 18,
      }
    ).addTo(map);

    // Labels layer
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      {
        maxZoom: 18,
      }
    ).addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Cargar capa zona del consorcio
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // Cargar GeoJSON de la zona
    fetch(`${API_URL}/api/v1/gee/layers/zona`)
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error('No se pudo cargar la capa zona');
      })
      .then((geojson) => {
        if (zonaLayerRef.current) {
          map.removeLayer(zonaLayerRef.current);
        }
        const layer = L.geoJSON(geojson, { style: ZONA_STYLE }).addTo(map);
        zonaLayerRef.current = layer;
      })
      .catch((err) => logger.warn('Error cargando capa zona:', err));

    return () => {
      if (zonaLayerRef.current && map) {
        map.removeLayer(zonaLayerRef.current);
        zonaLayerRef.current = null;
      }
    };
  }, []);

  // Fetch visualizations on mount
  useEffect(() => {
    fetch(`${API_BASE}/visualizations`)
      .then((res) => res.json())
      .then((data: Visualization[]) => setVisualizations(data))
      .catch((err) => logger.error('Error fetching visualizations:', err));

    fetch(`${API_BASE}/historic-floods`)
      .then((res) => res.json())
      .then((data: { floods: HistoricFlood[] }) => setHistoricFloods(data.floods))
      .catch((err) => logger.error('Error fetching historic floods:', err));
  }, []);

  // Update tile layer on map
  const updateTileLayer = useCallback((tileUrl: string) => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // Remove previous tile layer
    if (tileLayerRef.current) {
      map.removeLayer(tileLayerRef.current);
    }

    // Add new tile layer
    const layer = L.tileLayer(tileUrl, {
      attribution: 'Imagery &copy; Google Earth Engine',
      maxZoom: 18,
      opacity: 0.9,
    }).addTo(map);

    tileLayerRef.current = layer;
  }, []);

  // Fetch image
  const fetchImage = useCallback(async () => {
    if (!selectedDate) {
      setError('Selecciona una fecha');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Handle both Date objects and date strings
      const dateObj = selectedDate instanceof Date ? selectedDate : new Date(selectedDate);
      const dateStr = dateObj.toISOString().split('T')[0];
      const endpoint = sensor === 'sentinel2' ? 'sentinel2' : 'sentinel1';

      const params = new URLSearchParams({
        target_date: dateStr,
        days_buffer: daysBuffer,
        visualization: visualization,
      });

      if (sensor === 'sentinel2') {
        params.append('max_cloud', maxCloud);
      }

      const response = await fetch(`${API_BASE}/${endpoint}?${params}`);

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error fetching image');
      }

      const data: ImageResult = await response.json();
      setResult(data);
      updateTileLayer(data.tile_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
    } finally {
      setLoading(false);
    }
  }, [selectedDate, daysBuffer, maxCloud, visualization, sensor, updateTileLayer]);

  // Load historic flood
  const loadHistoricFlood = useCallback(
    async (floodId: string) => {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(
          `${API_BASE}/historic-floods/${floodId}?visualization=${visualization}`
        );

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Error fetching historic flood');
        }

        const data: ImageResult = await response.json();
        setResult(data);
        updateTileLayer(data.tile_url);

        // Update selected date to match flood date
        if (data.flood_info) {
          setSelectedDate(new Date(data.flood_info.date));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido');
      } finally {
        setLoading(false);
      }
    },
    [visualization, updateTileLayer]
  );

  // Create SelectedImage from current result
  const createImageData = useCallback((): SelectedImage | null => {
    if (!result) return null;

    return {
      tile_url: result.tile_url,
      target_date: result.target_date,
      sensor: result.sensor as 'Sentinel-1' | 'Sentinel-2',
      visualization: result.visualization,
      visualization_description: result.visualization_description,
      collection: result.collection,
      images_count: result.images_count,
      flood_info: result.flood_info ? {
        id: result.flood_info.id,
        name: result.flood_info.name,
        description: result.flood_info.description,
        severity: result.flood_info.severity,
      } : undefined,
      selected_at: new Date().toISOString(),
    };
  }, [result]);

  // Handle selecting image for use in other views
  const handleSelectImage = useCallback(() => {
    const imageData = createImageData();
    if (imageData) {
      setSelectedImage(imageData);
    }
  }, [createImageData, setSelectedImage]);

  // Handle setting as left comparison image
  const handleSetLeftImage = useCallback(() => {
    const imageData = createImageData();
    if (imageData) {
      setLeftImage(imageData);
    }
  }, [createImageData, setLeftImage]);

  // Handle setting as right comparison image
  const handleSetRightImage = useCallback(() => {
    const imageData = createImageData();
    if (imageData) {
      setRightImage(imageData);
    }
  }, [createImageData, setRightImage]);

  // Check if current result matches selected image
  const isCurrentImageSelected = selectedImage?.tile_url === result?.tile_url;

  // Visualization options based on sensor
  const visOptions =
    sensor === 'sentinel2'
      ? visualizations.map((v) => ({ value: v.id, label: v.description }))
      : [
          { value: 'vv', label: 'Radar SAR (VV)' },
          { value: 'vv_flood', label: 'Deteccion de agua (SAR)' },
        ];

  return (
    <Stack gap="md">
      {/* Controls */}
      <Paper p="md" withBorder radius="md">
        <Stack gap="md">
          {/* Sensor selection */}
          <Group justify="space-between" wrap="wrap" gap="md">
            <SegmentedControl
              value={sensor}
              onChange={(v) => {
                setSensor(v as 'sentinel2' | 'sentinel1');
                setVisualization(v === 'sentinel2' ? 'rgb' : 'vv');
              }}
              data={[
                { value: 'sentinel2', label: 'Sentinel-2 (Optico)' },
                { value: 'sentinel1', label: 'Sentinel-1 (SAR)' },
              ]}
            />

            <Group gap="xs">
              <IconCalendar size={18} />
              <Text size="sm" c="dimmed">
                SAR funciona con nubes
              </Text>
            </Group>
          </Group>

          {/* Filters */}
          <Group gap="md" wrap="wrap">
            <DatePickerInput
              type="default"
              label="Fecha objetivo"
              placeholder="Seleccionar"
              value={selectedDate}
              onChange={setSelectedDate}
              maxDate={new Date()}
              w={180}
              popoverProps={{
                withinPortal: true,
                zIndex: 10000,
                styles: { dropdown: { zIndex: 10000 } },
              }}
            />

            <Select
              label="Dias de busqueda"
              value={daysBuffer}
              onChange={(v) => v && setDaysBuffer(v)}
              data={[
                { value: '5', label: '+/- 5 dias' },
                { value: '10', label: '+/- 10 dias' },
                { value: '15', label: '+/- 15 dias' },
                { value: '30', label: '+/- 30 dias' },
              ]}
              w={140}
            />

            {sensor === 'sentinel2' && (
              <Select
                label="Nubes max."
                value={maxCloud}
                onChange={(v) => v && setMaxCloud(v)}
                data={[
                  { value: '20', label: '20%' },
                  { value: '40', label: '40%' },
                  { value: '60', label: '60%' },
                  { value: '80', label: '80%' },
                ]}
                w={100}
              />
            )}

            <Select
              label="Visualizacion"
              value={visualization}
              onChange={(v) => v && setVisualization(v)}
              data={visOptions}
              w={220}
            />

            <Button
              leftSection={<IconRefresh size={18} />}
              onClick={fetchImage}
              loading={loading}
              mt="auto"
            >
              Cargar Imagen
            </Button>
          </Group>
        </Stack>
      </Paper>

      {/* Historic floods */}
      {historicFloods.length > 0 && (
        <Paper p="md" withBorder radius="md">
          <Title order={5} mb="sm">
            <Group gap="xs">
              <IconPhoto size={20} />
              Escenas Historicas
            </Group>
          </Title>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
            {historicFloods.map((flood) => (
              <Card
                key={flood.id}
                padding="sm"
                radius="md"
                withBorder
                style={{ cursor: 'pointer' }}
                onClick={() => loadHistoricFlood(flood.id)}
              >
                <Group justify="space-between" mb="xs">
                  <Text fw={500}>{flood.name}</Text>
                  <Badge
                    color={
                      flood.severity === 'alta'
                        ? 'red'
                        : flood.severity === 'media'
                          ? 'orange'
                          : 'yellow'
                    }
                    size="sm"
                  >
                    {flood.severity}
                  </Badge>
                </Group>
                <Text size="sm" c="dimmed">
                  {flood.description}
                </Text>
                <Text size="xs" c="dimmed" mt="xs">
                  {flood.date}
                </Text>
              </Card>
            ))}
          </SimpleGrid>
        </Paper>
      )}

      {/* Error */}
      {error && (
        <Alert color="red" icon={<IconAlertTriangle />} title="Error">
          {error}
        </Alert>
      )}

      {/* Map and info */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {/* Map */}
        <Card
          padding={0}
          radius="md"
          withBorder
          style={{ flex: '1 1 600px', minHeight: 500, position: 'relative' }}
        >
          <div
            ref={mapRef}
            style={{ width: '100%', height: 500, borderRadius: 'var(--mantine-radius-md)' }}
          />

          {loading && (
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: 'rgba(255,255,255,0.8)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 'var(--mantine-radius-md)',
              }}
            >
              <Stack align="center">
                <Loader size="lg" />
                <Text>Cargando imagen satelital...</Text>
              </Stack>
            </div>
          )}
        </Card>

        {/* Info panel */}
        {result && (
          <Card padding="md" radius="md" withBorder style={{ flex: '0 0 280px' }}>
            <Title order={5} mb="md">
              <Group gap="xs">
                <IconSatellite size={20} />
                Informacion
              </Group>
            </Title>

            <Stack gap="sm">
              {result.flood_info && (
                <Paper p="sm" withBorder radius="sm" bg="blue.0">
                  <Text size="sm" fw={500} c="blue.7">
                    {result.flood_info.name}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {result.flood_info.description}
                  </Text>
                </Paper>
              )}

              <Paper p="sm" withBorder radius="sm">
                <Text size="sm" c="dimmed">
                  Sensor
                </Text>
                <Text size="lg" fw={600}>
                  {result.sensor}
                </Text>
              </Paper>

              <Paper p="sm" withBorder radius="sm">
                <Text size="sm" c="dimmed">
                  Fecha de imagen
                </Text>
                <Text size="lg" fw={600}>
                  {result.target_date}
                </Text>
              </Paper>

              <Paper p="sm" withBorder radius="sm">
                <Text size="sm" c="dimmed">
                  Visualizacion
                </Text>
                <Text size="md" fw={500}>
                  {result.visualization_description}
                </Text>
              </Paper>

              <Paper p="sm" withBorder radius="sm">
                <Text size="sm" c="dimmed">
                  Imagenes encontradas
                </Text>
                <Text size="lg" fw={600}>
                  {result.images_count}
                </Text>
              </Paper>

              {result.dates_available && result.dates_available.length > 0 && (
                <Paper p="sm" withBorder radius="sm">
                  <Text size="sm" c="dimmed" mb="xs">
                    Fechas disponibles
                  </Text>
                  <Group gap="xs" wrap="wrap">
                    {result.dates_available.slice(0, 8).map((date) => (
                      <Badge
                        key={date}
                        size="sm"
                        variant="light"
                        style={{ cursor: 'pointer' }}
                        onClick={() => {
                          setSelectedDate(new Date(date));
                        }}
                      >
                        {date}
                      </Badge>
                    ))}
                  </Group>
                </Paper>
              )}

              <Text size="xs" c="dimmed">
                Coleccion: {result.collection}
              </Text>

              {/* Use this image button */}
              <Button
                fullWidth
                mt="md"
                variant={isCurrentImageSelected ? 'light' : 'filled'}
                color={isCurrentImageSelected ? 'green' : 'blue'}
                leftSection={isCurrentImageSelected ? <IconCheck size={18} /> : <IconPhoto size={18} />}
                onClick={handleSelectImage}
                disabled={isCurrentImageSelected}
              >
                {isCurrentImageSelected ? 'Imagen seleccionada' : 'Usar esta imagen'}
              </Button>

              {/* Comparison buttons */}
              <Divider my="sm" label="Comparar imagenes" labelPosition="center" />
              <Group grow>
                <Tooltip label="Imagen izquierda (antes)">
                  <Button
                    variant={comparison?.left?.tile_url === result?.tile_url ? 'light' : 'outline'}
                    color="blue"
                    size="sm"
                    onClick={handleSetLeftImage}
                  >
                    Izquierda
                  </Button>
                </Tooltip>
                <Tooltip label="Imagen derecha (despues)">
                  <Button
                    variant={comparison?.right?.tile_url === result?.tile_url ? 'light' : 'outline'}
                    color="green"
                    size="sm"
                    onClick={handleSetRightImage}
                  >
                    Derecha
                  </Button>
                </Tooltip>
              </Group>
            </Stack>
          </Card>
        )}
      </div>

      {/* Currently selected image indicator */}
      {selectedImage && (
        <Paper p="sm" withBorder radius="md" bg="green.0">
          <Group justify="space-between">
            <Group gap="xs">
              <IconCheck size={18} color="var(--mantine-color-green-7)" />
              <Text size="sm" fw={500} c="green.7">
                Imagen activa en otras vistas:
              </Text>
              <Badge variant="light" color="green">
                {selectedImage.sensor} - {selectedImage.target_date}
              </Badge>
              <Text size="sm" c="dimmed">
                ({selectedImage.visualization_description})
              </Text>
            </Group>
            <Button
              variant="subtle"
              color="red"
              size="xs"
              leftSection={<IconX size={14} />}
              onClick={clearSelectedImage}
            >
              Quitar
            </Button>
          </Group>
        </Paper>
      )}

      {/* Comparison mode indicator */}
      {comparison && (
        <Paper p="sm" withBorder radius="md" bg="blue.0">
          <Group justify="space-between">
            <Group gap="md">
              <IconGitCompare size={18} color="var(--mantine-color-blue-7)" />
              <Text size="sm" fw={500} c="blue.7">
                Comparacion activa:
              </Text>
              <Group gap="xs">
                <Badge variant="light" color="blue">
                  {comparison.left?.target_date || 'Sin seleccionar'}
                </Badge>
                <Text size="sm" c="dimmed">vs</Text>
                <Badge variant="light" color="green">
                  {comparison.right?.target_date || 'Sin seleccionar'}
                </Badge>
              </Group>
              {comparisonReady && (
                <Text size="xs" c="dimmed">
                  (Ve al Mapa para ver la comparacion)
                </Text>
              )}
            </Group>
            <Button
              variant="subtle"
              color="red"
              size="xs"
              leftSection={<IconX size={14} />}
              onClick={clearComparison}
            >
              Quitar
            </Button>
          </Group>
        </Paper>
      )}

      {/* Visualization legend */}
      <Paper p="sm" withBorder radius="md">
        <Group gap="lg" wrap="wrap">
          <Text size="sm" fw={500}>
            Visualizaciones:
          </Text>
          {sensor === 'sentinel2' ? (
            <>
              <Text size="sm" c="dimmed">
                RGB = Color natural | NDWI/MNDWI = Agua en azul | NDVI = Vegetacion en verde |
                Inundacion = Agua detectada
              </Text>
            </>
          ) : (
            <Text size="sm" c="dimmed">
              VV = Radar (oscuro=agua) | VV Flood = Deteccion de inundacion en cyan
            </Text>
          )}
        </Group>
      </Paper>
    </Stack>
  );
}
