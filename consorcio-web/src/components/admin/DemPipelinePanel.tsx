/**
 * DemPipelinePanel - Admin panel for triggering and viewing DEM pipeline results.
 *
 * Allows admins to:
 * - Trigger a new DEM pipeline (download from GEE + terrain analysis + basin delineation)
 * - Monitor progress while Celery processes
 * - View results: 3D terrain viewer, generated layers list, basin map, download links
 */

import {
  Alert,
  Badge,
  Button,
  Center,
  Container,
  Divider,
  Group,
  Loader,
  NumberInput,
  Paper,
  Progress,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { useDemPipeline } from '../../hooks/useDemPipeline';
import { demPipelineApi } from '../../lib/api/demPipeline';
import type { GeoLayerResponse } from '../../lib/api/demPipeline';
import {
  IconAlertTriangle,
  IconChartBar,
  IconDownload,
  IconGlobe,
  IconPlayerPlay,
  IconRefresh,
} from '../ui/icons';

// Lazy load the 3D viewer since it pulls in deck.gl
const TerrainViewer3D = lazy(() => import('../terrain/TerrainViewer3D'));

/** Human-readable layer type names */
const LAYER_TYPE_LABELS: Record<string, string> = {
  dem_raw: 'DEM Original',
  slope: 'Pendiente',
  aspect: 'Orientacion',
  flow_dir: 'Direccion de Flujo',
  flow_acc: 'Acumulacion de Flujo',
  twi: 'Indice de Humedad (TWI)',
  hand: 'Altura sobre Drenaje (HAND)',
  drainage: 'Red de Drenaje',
  terrain_class: 'Clasificacion de Terreno',
  basins: 'Cuencas',
};

export default function DemPipelinePanel() {
  const { state, progress, layers, basins, error, submit, reset, fetchLayers, fetchBasins } =
    useDemPipeline();

  const [minBasinAreaHa, setMinBasinAreaHa] = useState<number>(5000);

  // On mount, try to fetch existing layers and basins
  useEffect(() => {
    fetchLayers();
    fetchBasins();
  }, [fetchLayers, fetchBasins]);

  const handleSubmit = useCallback(() => {
    submit(undefined, minBasinAreaHa);
  }, [submit, minBasinAreaHa]);

  const demRawLayer = layers.find((l) => l.tipo === 'dem_raw');

  return (
    <Container size="xl" py="md">
      <Group justify="space-between" mb="xl">
        <div>
          <Group gap="xs">
            <IconGlobe size={24} />
            <Title order={2}>DEM Pipeline</Title>
          </Group>
          <Text c="dimmed" size="sm">
            Analisis de elevacion digital: descarga desde GEE, analisis de terreno y delineacion de
            cuencas
          </Text>
        </div>
        {state !== 'idle' && (
          <Button variant="subtle" leftSection={<IconRefresh size={16} />} onClick={reset}>
            Reiniciar
          </Button>
        )}
      </Group>

      {/* Submit form */}
      {(state === 'idle' || state === 'failed') && (
        <Paper p="lg" radius="md" withBorder mb="xl">
          <Title order={4} mb="md">
            Generar DEM
          </Title>
          <Stack gap="md">
            <Text size="sm" c="dimmed">
              Este proceso descarga el modelo de elevacion digital (DEM) desde Google Earth Engine,
              ejecuta un analisis completo de terreno (pendiente, aspecto, flujo, TWI, HAND,
              drenaje, clasificacion) y delinea cuencas hidrograficas automaticamente.
            </Text>

            <Group>
              <NumberInput
                label="Area minima de cuenca (ha)"
                description="Cuencas menores a este valor se descartan"
                value={minBasinAreaHa}
                onChange={(val) => setMinBasinAreaHa(typeof val === 'number' ? val : 5000)}
                min={1000}
                max={50000}
                step={1000}
                w={260}
              />
            </Group>

            {error && (
              <Alert icon={<IconAlertTriangle size={16} />} color="red" title="Error">
                {error}
              </Alert>
            )}

            <Button
              leftSection={<IconPlayerPlay size={18} />}
              onClick={handleSubmit}
              loading={(state as string) === 'submitting'}
              size="md"
            >
              Generar DEM
            </Button>
          </Stack>
        </Paper>
      )}

      {/* Polling / Progress */}
      {(state === 'submitting' || state === 'polling') && (
        <Paper p="xl" radius="md" withBorder mb="xl">
          <Stack align="center" gap="md">
            <Loader size="lg" />
            <Title order={4}>Procesando pipeline DEM...</Title>
            <Text c="dimmed" size="sm">
              Esto puede tardar varios minutos dependiendo del area.
            </Text>
            <Progress value={progress} size="xl" radius="xl" w="100%" animated striped />
            <Text size="sm" fw={600}>
              {progress}% completado
            </Text>
          </Stack>
        </Paper>
      )}

      {/* Results */}
      {(state === 'completed' || layers.length > 0) && (
        <Stack gap="xl">
          {/* 3D Terrain Viewer */}
          <Paper p="lg" radius="md" withBorder>
            <Suspense
              fallback={
                <Center mih={400}>
                  <Stack align="center" gap="md">
                    <Loader size="lg" />
                    <Text c="dimmed">Cargando visualizador 3D...</Text>
                  </Stack>
                </Center>
              }
            >
              <TerrainViewer3D demLayerId={demRawLayer?.id} height={500} />
            </Suspense>
          </Paper>

          <Divider />

          {/* Generated Layers Table */}
          {layers.length > 0 && (
            <Paper p="lg" radius="md" withBorder>
              <Group justify="space-between" mb="md">
                <Group gap="xs">
                  <IconChartBar size={20} />
                  <Title order={4}>Capas Generadas</Title>
                </Group>
                <Badge size="lg" variant="light">
                  {layers.length} capas
                </Badge>
              </Group>

              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Capa</Table.Th>
                    <Table.Th>Tipo</Table.Th>
                    <Table.Th>Formato</Table.Th>
                    <Table.Th>Fecha</Table.Th>
                    <Table.Th>Acciones</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {layers.map((layer) => (
                    <LayerRow key={layer.id} layer={layer} />
                  ))}
                </Table.Tbody>
              </Table>
            </Paper>
          )}

          {/* Basin Summary */}
          {basins && basins.features.length > 0 && (
            <Paper p="lg" radius="md" withBorder>
              <Group gap="xs" mb="md">
                <IconGlobe size={20} />
                <Title order={4}>Cuencas Delineadas</Title>
                <Badge size="lg" variant="light" color="blue">
                  {basins.features.length} cuencas
                </Badge>
              </Group>

              <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="sm">
                {basins.features.map((feature, idx) => (
                  <Paper key={idx} p="sm" radius="sm" withBorder>
                    <Group justify="space-between">
                      <Text size="sm" fw={500}>
                        Cuenca {feature.properties.basin_id}
                      </Text>
                      <Badge size="sm" variant="outline">
                        {feature.properties.area_ha} ha
                      </Badge>
                    </Group>
                  </Paper>
                ))}
              </SimpleGrid>
            </Paper>
          )}
        </Stack>
      )}
    </Container>
  );
}

/** Individual layer row with download button */
function LayerRow({ layer }: { readonly layer: GeoLayerResponse }) {
  const handleDownload = useCallback(() => {
    const url = demPipelineApi.getLayerFileUrl(layer.id);
    window.open(url, '_blank');
  }, [layer.id]);

  const label = LAYER_TYPE_LABELS[layer.tipo] || layer.tipo;
  const formatBadge = layer.formato === 'geojson' ? 'GeoJSON' : 'GeoTIFF';

  return (
    <Table.Tr>
      <Table.Td>
        <Text size="sm" fw={500}>
          {layer.nombre}
        </Text>
      </Table.Td>
      <Table.Td>
        <Badge size="sm" variant="light">
          {label}
        </Badge>
      </Table.Td>
      <Table.Td>
        <Badge size="sm" variant="outline" color={layer.formato === 'geojson' ? 'teal' : 'blue'}>
          {formatBadge}
        </Badge>
      </Table.Td>
      <Table.Td>
        <Text size="xs" c="dimmed">
          {new Date(layer.created_at).toLocaleDateString('es-AR')}
        </Text>
      </Table.Td>
      <Table.Td>
        <Button
          size="xs"
          variant="subtle"
          leftSection={<IconDownload size={14} />}
          onClick={handleDownload}
        >
          Descargar
        </Button>
      </Table.Td>
    </Table.Tr>
  );
}
