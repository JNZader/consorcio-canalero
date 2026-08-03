import { Alert, Box, Center, Skeleton, Stack, Text } from '@mantine/core';
import { Suspense, lazy } from 'react';
import styles from '../styles/components/map.module.css';
import { ErrorBoundary } from './ErrorBoundary';

// Lazy load del componente de mapa con MapLibre GL
// Esto separa MapLibre del bundle inicial
const MapaMapLibre = lazy(() => import('./MapaMapLibre'));

// Componente de carga mientras se descarga MapLibre
function MapaLoadingSkeleton() {
  return (
    <Box
      className={styles.mapSkeletonWrapper}
      aria-live="polite"
      aria-busy="true"
      aria-label="Cargando mapa"
    >
      <Skeleton height="100%" radius="md" />
      <Center className={styles.skeletonOverlay}>
        <Stack align="center" gap="md">
          <Skeleton circle height={48} width={48} />
          <Skeleton height={16} width={120} radius="md" />
        </Stack>
      </Center>
    </Box>
  );
}

// Fallback component for map loading errors
function MapaErrorFallback() {
  return (
    <Box
      className={styles.mapWrapper}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'light-dark(var(--mantine-color-gray-1), var(--mantine-color-dark-6))',
      }}
    >
      <Stack gap="sm" maw={560} p="md">
        <Alert color="red" title="Error al cargar el mapa" variant="light" radius="md">
          <Text size="sm">
            No se pudo cargar el componente del mapa. Por favor, recarga la pagina o intenta mas
            tarde.
          </Text>
        </Alert>
        <Box component="section" role="region" aria-label="descripcion textual del mapa">
          <Text size="sm" fw={600}>
            Descripcion textual del mapa
          </Text>
          <Text size="sm">
            El mapa interactivo permite explorar cuencas, canales e infraestructura del Consorcio.
            En un dispositivo compatible, usa sus controles de capas para consultar cada elemento
            territorial.
          </Text>
        </Box>
      </Stack>
    </Box>
  );
}

// Componente interno con lazy loading y ErrorBoundary
function MapaContenido() {
  return (
    <ErrorBoundary fallback={<MapaErrorFallback />}>
      <Suspense fallback={<MapaLoadingSkeleton />}>
        <MapaMapLibre />
      </Suspense>
    </ErrorBoundary>
  );
}

// Export internal component for use within other MantineProvider contexts
export { MapaContenido };

/**
 * MapaInteractivo - Page component (MantineProvider is provided by main.tsx).
 */
export default function MapaInteractivo() {
  return <MapaContenido />;
}
