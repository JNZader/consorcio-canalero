import {
  Alert,
  Button,
  Container,
  Group,
  Paper,
  Progress,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
  Divider,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import type { ReactNode } from 'react';
import { CONSORCIO_AREA_HA, CONSORCIO_AREA_DISPLAY, CUENCA_COLORS as DEFAULT_CUENCA_COLORS } from '../../constants';
import { useConfigStore } from '../../stores/configStore';
import { useMonitoringDashboard, useReports } from '../../lib/query';
import { formatDate } from '../../lib/formatters';
import { logger } from '../../lib/logger';
import { LoadingState } from '../ui';
import { StatusBadge } from '../ui/StatusBadge';
import {
  IconClipboardList,
  IconDownload,
  IconMap,
  IconPhoto,
} from '../ui/icons';
import { DashboardEstadisticas } from './management/DashboardEstadisticas';
import { API_URL, getAuthToken } from '../../lib/api';
import { useState } from 'react';

interface QuickStat {
  readonly label: string;
  readonly value: string | number;
  readonly icon: ReactNode;
  readonly color: string;
  readonly description?: string;
}

// Nombres legibles de cuencas (fallback)
const DEFAULT_CUENCA_NAMES: Record<string, string> = {
  candil: 'Candil',
  ml: 'ML',
  noroeste: 'Noroeste',
  norte: 'Norte',
};

export default function AdminDashboard() {
  const config = useConfigStore((state) => state.config);
  const [exporting, setExporting] = useState(false);

  const {
    reports: recentReports,
    isLoading: reportsLoading,
    error: reportsError,
    refetch: refetchReports,
  } = useReports({ limit: 5 });
  const {
    rankingCuencas,
    isLoading: monitoringLoading,
    refetch: refetchMonitoring,
  } = useMonitoringDashboard();

  // Contar reportes pendientes
  const reportesPendientes = recentReports.filter(r => r.estado === 'pendiente').length;

  const handleRetry = () => {
    refetchReports();
    refetchMonitoring();
  };

  const handleExportPDF = async () => {
    setExporting(true);
    try {
      const token = await getAuthToken();
      const response = await fetch(`${API_URL}/api/v1/management/export-integral`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) throw new Error('Error al generar PDF');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `informe_gestion_integral_${new Date().toISOString().split('T')[0]}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch (error) {
      logger.error('Export error:', error);
      notifications.show({
        title: 'Error de exportacion',
        message: 'No se pudo generar el PDF. Intenta nuevamente.',
        color: 'red',
      });
    } finally {
      setExporting(false);
    }
  };

  if (reportsLoading) {
    return <LoadingState message="Cargando dashboard..." />;
  }

  if (reportsError) {
    return (
      <Container size="xl" py="xl">
        <Alert color="red" title="Error de conexion">
          Error al cargar datos. Verifica que el backend este activo.
          <Button mt="sm" size="xs" onClick={handleRetry}>
            Reintentar
          </Button>
        </Alert>
      </Container>
    );
  }

  return (
    <Container size="xl" py="md">
      <Group justify="space-between" mb="xl">
        <div>
          <Title order={2}>Panel de Gestion Integral</Title>
          <Text c="gray.6">Inteligencia de datos y monitoreo satelital</Text>
        </div>
        <Group>
          <Button
            variant="filled"
            color="violet"
            leftSection={<IconDownload size={18} />}
            onClick={handleExportPDF}
            loading={exporting}
          >
            Exportar Reporte Mensual
          </Button>
        </Group>
      </Group>

      {/* Componente de Visualizacion Avanzada */}
      <DashboardEstadisticas />

      <Divider my="xl" label="Detalle de Operaciones" labelPosition="center" />

      <SimpleGrid cols={{ base: 1, lg: 2 }} mb="xl">
        {/* Inundacion por Cuenca - Datos reales del API */}
        <Paper shadow="sm" p="md" radius="md" withBorder>
          <Title order={4} mb="md">
            Monitoreo Satelital por Cuenca
          </Title>
          {monitoringLoading ? (
            <Text c="gray.6" ta="center" py="md">Cargando datos...</Text>
          ) : rankingCuencas.length > 0 ? (
            <Stack gap="md">
              {rankingCuencas.map((cuenca) => {
                const cuencaConfig = config?.cuencas.find(c => c.id === cuenca.cuenca);
                const color = cuencaConfig?.color || DEFAULT_CUENCA_COLORS[cuenca.cuenca] || 'blue';
                const nombre = cuencaConfig?.nombre || DEFAULT_CUENCA_NAMES[cuenca.cuenca] || cuenca.cuenca;
                const progressValue = Math.min(cuenca.porcentaje_problematico * 10, 100);
                return (
                  <div key={cuenca.cuenca}>
                    <Group justify="space-between" mb="xs">
                      <Text size="sm" fw={500}>
                        {nombre}
                      </Text>
                      <Text size="sm" c="gray.6">
                        {cuenca.area_anegada_ha.toFixed(1)} ha ({cuenca.porcentaje_problematico.toFixed(2)}%)
                      </Text>
                    </Group>
                    <Progress value={progressValue} color={color} size="lg" radius="xl" />
                  </div>
                );
              })}
            </Stack>
          ) : (
            <Text c="gray.6" ta="center" py="md">
              Sin datos de inundacion disponibles
            </Text>
          )}
        </Paper>

        {/* Ultimos Reportes */}
        <Paper shadow="sm" p="md" radius="md" withBorder>
          <Group justify="space-between" mb="md">
            <Title order={4}>Ultimos Reportes Vecinales</Title>
            <Button component="a" href="/admin/reports" variant="subtle" size="xs">
              Ver todos
            </Button>
          </Group>

          {recentReports.length > 0 ? (
            <Table verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Tipo</Table.Th>
                  <Table.Th>Estado</Table.Th>
                  <Table.Th>Fecha</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {recentReports.map((report) => (
                  <Table.Tr key={report.id}>
                    <Table.Td>
                      <Text size="sm" lineClamp={1}>
                        {report.tipo.replace('_', ' ')}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <StatusBadge status={report.estado} size="sm" />
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" c="gray.6">
                        {formatDate(report.created_at)}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          ) : (
            <Text c="gray.6" ta="center" py="xl">
              No hay reportes recientes
            </Text>
          )}
        </Paper>
      </SimpleGrid>
    </Container>
  );
}
