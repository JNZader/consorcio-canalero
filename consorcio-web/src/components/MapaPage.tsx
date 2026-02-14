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
import { useDashboardStats } from '../lib/query';
import { useCanAccess } from '../stores/authStore';
import { useSelectedImageListener } from '../hooks/useSelectedImage';
import { MapaContenido } from './MapaInteractivo';
import { IconAlertTriangle, IconPhoto, IconSatellite } from './ui/icons';

/**
 * MapaContent - Contenido interno de la pagina de mapa.
 * Exportado para uso dentro de contextos que ya tienen MantineProvider.
 */
export function MapaContent() {
  // Verificar permisos - solo miembros de la comision (admin/operador) ven las estadisticas
  const isCommissionMember = useCanAccess(['admin', 'operador']);

  // Obtener estadisticas reales del API (auth-aware hook)
  const { stats, isLoading: statsLoading } = useDashboardStats('30d');

  // Get selected satellite image
  const selectedImage = useSelectedImageListener();

  // Construir estadisticas dinamicas desde la API (solo denuncias)
  const dynamicStats = isCommissionMember && stats ? [
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
  ] : [];

  return (
    <Box
      style={{ background: 'light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))' }}
      mih="100vh"
    >
      {/* Header */}
      <Paper shadow="xs" p="md" mb={0}>
        <Container size="xl">
          <Title order={2}>Mapa Interactivo</Title>
          <Text c="gray.6">Explora las cuencas, caminos e infraestructura del consorcio</Text>
        </Container>
      </Paper>

      <Container size="xl" py="md">
        {/* Controles */}
        <Paper shadow="sm" p="md" mb="md" radius="md">
          <Group justify="space-between" wrap="wrap" gap="md">
            <Group gap="md" wrap="wrap">
              {/* Selected satellite image info */}
              {selectedImage ? (
                <Group gap="xs">
                  <IconSatellite size={20} color="var(--mantine-color-blue-6)" />
                  <Stack gap={2}>
                    <Text size="sm" fw={500}>
                      Imagen satelital activa
                    </Text>
                    <Group gap="xs">
                      <Badge size="sm" color="blue" variant="light">
                        {selectedImage.sensor}
                      </Badge>
                      <Text size="xs" c="dimmed">
                        {selectedImage.target_date} - {selectedImage.visualization_description}
                      </Text>
                    </Group>
                  </Stack>
                </Group>
              ) : (
                <Group gap="xs">
                  <IconPhoto size={20} color="var(--mantine-color-gray-5)" />
                  <Text size="sm" c="dimmed">
                    No hay imagen satelital seleccionada
                  </Text>
                </Group>
              )}

              {/* Image explorer button for admins */}
              {isCommissionMember && (
                <Button
                  component="a"
                  href="/admin/images"
                  variant="light"
                  size="sm"
                  leftSection={<IconPhoto size={16} />}
                >
                  {selectedImage ? 'Cambiar imagen' : 'Explorar imagenes'}
                </Button>
              )}
            </Group>

            <Button
              component="a"
              href="/reportes"
              color="orange"
              leftSection={<IconAlertTriangle size={18} />}
            >
              Reportar Incidente
            </Button>
          </Group>
        </Paper>

        {/* Mapa - usa el contenido directo para evitar provider anidado */}
        <Paper shadow="sm" radius="md" style={{ overflow: 'hidden' }} mb="md">
          <MapaContenido />
        </Paper>

        {/* Estadisticas rapidas - Solo visible para miembros de la comision */}
        {isCommissionMember && (
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            {statsLoading ? (
              // Skeleton mientras cargan los datos
              Array.from({ length: 2 }).map((_, i) => (
                <Card key={`skeleton-${i}`} shadow="sm" padding="md" radius="md">
                  <Skeleton height={24} width={80} mb="xs" />
                  <Skeleton height={16} width={100} />
                </Card>
              ))
            ) : (
              dynamicStats.map((stat) => (
                <Card key={stat.id} shadow="sm" padding="md" radius="md">
                  <Text size="xl" fw={700} c={stat.color}>
                    {stat.value}
                  </Text>
                  <Text size="sm" c="gray.6">
                    {stat.label}
                  </Text>
                </Card>
              ))
            )}
          </SimpleGrid>
        )}
      </Container>
    </Box>
  );
}

/**
 * MapaPage - Page component (MantineProvider is provided by main.tsx).
 */
export default function MapaPage() {
  return <MapaContent />;
}
