import {
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  Paper,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { lazy, Suspense, useEffect, useState } from 'react';
import { useGeoLayers } from '../hooks/useGeoLayers';
import { useMultiHazardGate } from '../hooks/useMultiHazardGate';
import { useSelectedImageListener } from '../hooks/useSelectedImage';
import { withBasePath } from '../lib/basePath';
import { useDashboardStats } from '../lib/query';
import { useCanAccess } from '../stores/authStore';
import mapStyles from '../styles/components/map.module.css';
import { MapaContenido } from './MapaInteractivo';
import { MapViewPanes, notifyMapPaneShown, shouldArmThreeD } from './map2d/MapViewPanes';
import { MapPageViewProvider } from './map2d/mapPageViewContext';
import { resolveTerrainAvailability, terrainAvailabilityHint } from './map2d/terrainAvailability';
import { IconAlertTriangle, IconPhoto, IconSatellite } from './ui/icons';

// Lazy-load TerrainViewer3D (MapLibre terrain, not deck.gl).
const TerrainViewer3D = lazy(() => import('./terrain/TerrainViewer3D'));

type MapViewMode = '2d' | '3d';

/**
 * MapaContent - Contenido interno de la pagina de mapa.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 */
export function MapaContent() {
  // Verificar permisos - solo miembros de la comision (admin/operador) ven las estadisticas
  const isCommissionMember = useCanAccess(['admin', 'operador']);
  const multiHazardEnabled = useMultiHazardGate();

  // Obtener estadisticas reales del API (auth-aware hook)
  const { stats, isLoading: statsLoading } = useDashboardStats('30d');

  // Get selected satellite image
  const selectedImage = useSelectedImageListener();

  // DEM layers — find the dem_raw layer for 3D terrain
  const {
    layers: demLayers,
    loading: demLoading,
    error: demError,
    reload: reloadDem,
  } = useGeoLayers();
  const demRawLayer = demLayers.find((l) => l.tipo === 'dem_raw');
  const terrainStatus = resolveTerrainAvailability({
    loading: demLoading,
    error: demError,
    hasDemRaw: !!demRawLayer,
  });
  const terrainHint = terrainAvailabilityHint(terrainStatus);

  // 2D/3D view toggle — UX-17 keeps 2D mounted after first 3D open.
  const [mapViewMode, setMapViewMode] = useState<MapViewMode>('2d');
  const [threeDArmed, setThreeDArmed] = useState(false);
  useEffect(() => {
    setThreeDArmed((prev) => shouldArmThreeD(prev, mapViewMode));
    if (mapViewMode === '2d') notifyMapPaneShown();
  }, [mapViewMode]);

  // Construir estadisticas dinamicas desde la API (solo denuncias)
  const dynamicStats =
    isCommissionMember && stats
      ? [
          {
            id: 'denuncias',
            value: stats.denuncias?.pendiente?.toString() || '0',
            label: 'Denuncias activas',
            color: 'red',
          },
          {
            id: 'resueltas',
            value: stats.denuncias?.resuelto?.toString() || '0',
            label: 'Resueltas este mes',
            color: 'green',
          },
        ]
      : [];

  return (
    <MapPageViewProvider
      value={{
        mode: mapViewMode,
        setMode: setMapViewMode,
        terrainReady: terrainStatus === 'ready',
        terrainHint: terrainStatus === 'ready' ? null : terrainHint,
        terrainStatus,
        onRetryTerrain: () => void reloadDem(),
      }}
    >
      <Box
        style={{
          background: 'light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))',
        }}
        mih="100vh"
      >
        <Container
          fluid
          px={{ base: 'xs', md: 'md' }}
          py="xs"
          className={mapStyles.mapPageContainer}
        >
          {/* One compact row. 2D/3D, capa base and the satellite view live in the
            layers panel so this bar no longer spends a second row on them. */}
          <Paper shadow="sm" p="xs" mb="xs" radius="md" className={mapStyles.mapPageHeader}>
            <Group justify="space-between" wrap="wrap" gap="xs">
              <Group gap="xs" wrap="wrap">
                <Title order={2} fz="h5">
                  Mapa Interactivo
                </Title>
                <Text size="xs" c="gray.6">
                  Explorá las cuencas, caminos e infraestructura del consorcio
                </Text>
                {multiHazardEnabled && (
                  <Badge size="sm" color="blue" variant="light">
                    Visor de riesgos disponible
                  </Badge>
                )}
                {selectedImage ? (
                  <Group gap={6} wrap="nowrap">
                    <IconSatellite size={16} color="var(--mantine-color-blue-6)" />
                    <Text size="xs" fw={500}>
                      Imagen satelital activa
                    </Text>
                    <Badge size="sm" color="blue" variant="light">
                      {selectedImage.sensor}
                    </Badge>
                    <Text size="xs" c="dimmed">
                      {selectedImage.target_date} - {selectedImage.visualization_description}
                    </Text>
                  </Group>
                ) : (
                  <Group gap={6} wrap="nowrap">
                    <IconPhoto size={16} color="var(--mantine-color-gray-5)" />
                    <Text size="xs" c="dimmed">
                      No hay imagen satelital seleccionada
                    </Text>
                  </Group>
                )}
                {isCommissionMember && (
                  <Button
                    component="a"
                    href={withBasePath('/admin/images')}
                    variant="light"
                    size="xs"
                    leftSection={<IconPhoto size={14} />}
                  >
                    {selectedImage ? 'Cambiar imagen' : 'Explorar imágenes'}
                  </Button>
                )}
              </Group>
              <Button
                component="a"
                href={withBasePath('/participacion')}
                color="orange"
                size="xs"
                leftSection={<IconAlertTriangle size={16} />}
              >
                Reportar Incidente
              </Button>
            </Group>
          </Paper>

          {/* Mapa 2D o Terreno 3D */}
          <Paper
            shadow="sm"
            radius="md"
            className={mapStyles.mapPageCanvas}
            style={{ overflow: 'hidden' }}
            mb="sm"
          >
            {/*
            `.canvasHeightBudget` publishes the SAME `--map-canvas-height`
            as `.mapCanvasWrapper`. UX-17 hides rather than unmounts 2D.
          */}
            <MapViewPanes
              className={mapStyles.canvasHeightBudget}
              mode={mapViewMode}
              threeDArmed={threeDArmed}
              twoD={<MapaContenido />}
              threeD={
                <Suspense
                  fallback={
                    <Box
                      p="xl"
                      style={{
                        minHeight: 500,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <Stack align="center" gap="md">
                        <Skeleton circle height={48} width={48} />
                        <Text size="sm" c="dimmed">
                          Cargando visualizador 3D...
                        </Text>
                      </Stack>
                    </Box>
                  }
                >
                  <TerrainViewer3D demLayerId={demRawLayer?.id} height="var(--map-canvas-height)" />
                </Suspense>
              }
            />
          </Paper>

          {/* Estadisticas rapidas - Solo visible para miembros de la comision */}
          {isCommissionMember && (
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
              {statsLoading
                ? // Skeleton mientras cargan los datos
                  Array.from({ length: 2 }).map((_, i) => (
                    <Card key={`skeleton-${i}`} shadow="sm" padding="md" radius="md">
                      <Skeleton height={24} width={80} mb="xs" />
                      <Skeleton height={16} width={100} />
                    </Card>
                  ))
                : dynamicStats.map((stat) => (
                    <Card key={stat.id} shadow="sm" padding="md" radius="md">
                      <Text size="xl" fw={700} c={stat.color}>
                        {stat.value}
                      </Text>
                      <Text size="sm" c="gray.6">
                        {stat.label}
                      </Text>
                    </Card>
                  ))}
            </SimpleGrid>
          )}
        </Container>
      </Box>
    </MapPageViewProvider>
  );
}

/**
 * MapaPage - Page component (MantineProvider is provided by main.tsx).
 */
export default function MapaPage() {
  return <MapaContent />;
}
