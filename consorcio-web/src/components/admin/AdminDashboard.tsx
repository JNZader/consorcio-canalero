import {
  Button,
  Container,
  Divider,
  FileInput,
  Group,
  Paper,
  Progress,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { lazy, Suspense, useState } from 'react';
import { CUENCA_COLORS as DEFAULT_CUENCA_COLORS } from '../../constants';
import { API_URL, getAuthToken } from '../../lib/api';
import { withBasePath } from '../../lib/basePath';
import { formatDate } from '../../lib/formatters';
import { logger } from '../../lib/logger';
import { showError, showNotification, showSuccess } from '../../lib/notifications';
import { useMonitoringDashboard, useReports } from '../../lib/query';
import { erroresUi, textoError } from '../../lib/userFacingError';
import { useConfigStore } from '../../stores/configStore';
import { IconDownload } from '../ui/icons';
import { LoadingState } from '../ui/LoadingState';
import { PageHeader } from '../ui/PageHeader';
import { StatusBadge } from '../ui/StatusBadge';
import { createDashboardJsonExport } from './adminDashboardExport';
import { PilarVerdeWidgetConnected } from './pilarVerdeWidget/PilarVerdeWidget';

const DashboardEstadisticas = lazy(() =>
  import('./management/DashboardEstadisticas').then((m) => ({ default: m.DashboardEstadisticas }))
);

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
  const [basinsFile, setBasinsFile] = useState<File | null>(null);
  const [approvedZonesFile, setApprovedZonesFile] = useState<File | null>(null);
  const [bundleFile, setBundleFile] = useState<File | null>(null);
  const [importingBasins, setImportingBasins] = useState(false);
  const [importingApprovedZones, setImportingApprovedZones] = useState(false);
  const [exportingBundle, setExportingBundle] = useState(false);
  const [importingBundle, setImportingBundle] = useState(false);

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

  const handleRetry = () => {
    refetchReports();
    refetchMonitoring();
  };

  const handleExportDashboardData = async () => {
    setExporting(true);
    try {
      const token = await getAuthToken();
      const response = await fetch(`${API_URL}/api/v2/monitoring/dashboard`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) throw new Error(textoError(erroresUi.exportarDashboard));

      const payload: unknown = await response.json();
      const { blob, filename } = createDashboardJsonExport(payload);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch (error) {
      logger.error('Export error:', error);
      showError(erroresUi.exportarDashboard.titulo, erroresUi.exportarDashboard.detalle);
    } finally {
      setExporting(false);
    }
  };

  const handleImportGeoJson = async (
    file: File | null,
    endpoint: string,
    successTitle: string,
    onSuccess?: () => void
  ) => {
    if (!file) {
      showNotification(
        'Archivo requerido',
        'Seleccioná un archivo GeoJSON antes de importar.',
        'yellow'
      );
      return;
    }

    const token = await getAuthToken();
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_URL}${endpoint}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });

    const payload = (await response.json().catch(() => null)) as {
      importedCount?: number;
      metadata?: Record<string, unknown>;
      detail?: string;
    } | null;

    if (!response.ok) {
      throw new Error(
        payload?.detail || textoError(erroresUi.importarArchivo, `Respuesta ${response.status}.`)
      );
    }

    showSuccess(
      successTitle,
      `Se importaron ${payload?.importedCount ?? 0} features correctamente.`
    );
    onSuccess?.();
  };

  const handleImportBasins = async () => {
    setImportingBasins(true);
    try {
      await handleImportGeoJson(
        basinsFile,
        '/api/v2/geo/basins/import',
        'Subcuencas importadas',
        () => setBasinsFile(null)
      );
    } catch (error) {
      logger.error('Basins import error:', error);
      showError(
        erroresUi.importarSubcuencas.titulo,
        error instanceof Error ? error.message : 'No se pudo importar el archivo.'
      );
    } finally {
      setImportingBasins(false);
    }
  };

  const handleImportApprovedZones = async () => {
    setImportingApprovedZones(true);
    try {
      await handleImportGeoJson(
        approvedZonesFile,
        '/api/v2/geo/basins/approved-zones/import',
        'Zonificación aprobada importada',
        () => setApprovedZonesFile(null)
      );
    } catch (error) {
      logger.error('Approved zones import error:', error);
      showError(
        erroresUi.importarZonificacion.titulo,
        error instanceof Error ? error.message : 'No se pudo importar el archivo.'
      );
    } finally {
      setImportingApprovedZones(false);
    }
  };

  const handleExportBundle = async () => {
    setExportingBundle(true);
    try {
      const token = await getAuthToken();
      const response = await fetch(`${API_URL}/api/v2/geo/bundle/export`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (!response.ok) {
        throw new Error(textoError(erroresUi.exportarBundle, `Respuesta ${response.status}.`));
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `geo_bundle_${new Date().toISOString().slice(0, 10)}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);

      showSuccess('Bundle exportado', 'Se descargó el bundle geoespacial correctamente.');
    } catch (error) {
      logger.error('Bundle export error:', error);
      showError(
        erroresUi.exportarBundle.titulo,
        error instanceof Error ? error.message : 'No se pudo exportar el bundle.'
      );
    } finally {
      setExportingBundle(false);
    }
  };

  const handleImportBundle = async () => {
    if (!bundleFile) {
      showNotification(
        'Archivo requerido',
        'Seleccioná un archivo ZIP antes de importar.',
        'yellow'
      );
      return;
    }

    setImportingBundle(true);
    try {
      const token = await getAuthToken();
      const formData = new FormData();
      formData.append('file', bundleFile);

      const response = await fetch(`${API_URL}/api/v2/geo/bundle/import`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });

      const payload = (await response.json().catch(() => null)) as {
        layersImported?: number;
        vectorsImported?: Record<string, number>;
        detail?: string;
      } | null;

      if (!response.ok) {
        throw new Error(
          payload?.detail || textoError(erroresUi.importarBundle, `Respuesta ${response.status}.`)
        );
      }

      showSuccess(
        'Bundle importado',
        `Vectores restaurados y ${payload?.layersImported ?? 0} capas importadas.`
      );
      setBundleFile(null);
    } catch (error) {
      logger.error('Bundle import error:', error);
      showError(
        erroresUi.importarBundle.titulo,
        error instanceof Error ? error.message : 'No se pudo importar el bundle.'
      );
    } finally {
      setImportingBundle(false);
    }
  };

  if (reportsLoading) {
    return <LoadingState message="Cargando dashboard..." />;
  }

  if (reportsError) {
    return (
      <Container size="xl" py="xl">
        <LoadingState
          status="error"
          title={erroresUi.cargarDashboard.titulo}
          message={erroresUi.cargarDashboard.detalle}
          action={
            <Button mt="sm" size="xs" onClick={handleRetry}>
              Reintentar
            </Button>
          }
        />
      </Container>
    );
  }

  return (
    <Container size="xl" py="md">
      <PageHeader
        title="Panel de Gestión Integral"
        subtitle="Inteligencia de datos y monitoreo satelital"
        actions={
          <Button
            variant="filled"
            color="violet"
            leftSection={<IconDownload size={18} />}
            onClick={handleExportDashboardData}
            loading={exporting}
          >
            Descargar datos (JSON)
          </Button>
        }
      />

      {/* Componente de Visualizacion Avanzada */}
      <Suspense fallback={<Skeleton height={200} radius="md" />}>
        <DashboardEstadisticas />
      </Suspense>

      <Divider my="xl" label="Detalle de Operaciones" labelPosition="center" />

      <Paper shadow="sm" p="md" radius="md" withBorder mb="xl">
        <Group justify="space-between" align="flex-start" mb="md">
          <div>
            <Title order={4}>Importación geoespacial</Title>
            <Text c="gray.6" size="sm">
              Reemplaza subcuencas operativas y carga una nueva zonificación aprobada desde archivos
              GeoJSON exportados.
            </Text>
          </div>
        </Group>

        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <Paper withBorder p="md" radius="md">
            <Stack gap="sm">
              <div>
                <Text fw={600}>Subcuencas operativas</Text>
                <Text size="sm" c="gray.6">
                  Importa <code>zonas_operativas.geojson</code> y reemplaza las subcuencas actuales.
                </Text>
              </div>
              <FileInput
                value={basinsFile}
                onChange={setBasinsFile}
                accept=".geojson,.json,application/geo+json,application/json"
                placeholder="Seleccionar GeoJSON"
                aria-label="Seleccionar GeoJSON de subcuencas a importar"
                styles={{ placeholder: { color: '#495057' } }}
                clearable
              />
              <Button onClick={handleImportBasins} loading={importingBasins} disabled={!basinsFile}>
                Importar subcuencas
              </Button>
            </Stack>
          </Paper>

          <Paper withBorder p="md" radius="md">
            <Stack gap="sm">
              <div>
                <Text fw={600}>Zonificación aprobada</Text>
                <Text size="sm" c="gray.6">
                  Importa <code>zonificacion_aprobada.geojson</code> como nueva versión aprobada.
                </Text>
              </div>
              <FileInput
                value={approvedZonesFile}
                onChange={setApprovedZonesFile}
                accept=".geojson,.json,application/geo+json,application/json"
                placeholder="Seleccionar GeoJSON"
                aria-label="Seleccionar GeoJSON de zonificación a importar"
                styles={{ placeholder: { color: '#495057' } }}
                clearable
              />
              <Button
                onClick={handleImportApprovedZones}
                loading={importingApprovedZones}
                disabled={!approvedZonesFile}
                color="teal"
              >
                Importar zonificación
              </Button>
            </Stack>
          </Paper>
        </SimpleGrid>
      </Paper>

      <Paper shadow="sm" p="md" radius="md" withBorder mb="xl">
        <Stack gap="md">
          <div>
            <Title order={4}>Bundle geo</Title>
            <Text c="gray.6" size="sm">
              Exporta o importa un paquete completo con subcuencas, zonificación aprobada y capas
              geo respaldadas por archivos.
            </Text>
          </div>

          <Group align="flex-end">
            <Button
              variant="filled"
              color="indigo.9"
              leftSection={<IconDownload size={18} />}
              onClick={handleExportBundle}
              loading={exportingBundle}
            >
              Exportar bundle geo
            </Button>

            <FileInput
              value={bundleFile}
              onChange={setBundleFile}
              accept=".zip,application/zip"
              placeholder="Seleccionar bundle ZIP"
              aria-label="Seleccionar bundle ZIP a importar"
              clearable
              styles={{ placeholder: { color: '#495057' } }}
              style={{ flex: 1, minWidth: 260 }}
            />

            <Button onClick={handleImportBundle} loading={importingBundle} disabled={!bundleFile}>
              Importar bundle geo
            </Button>
          </Group>
        </Stack>
      </Paper>

      <SimpleGrid cols={{ base: 1, lg: 2 }} mb="xl">
        {/* Pilar Verde — BPA + Plan Provincial Agroforestal */}
        <PilarVerdeWidgetConnected />
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, lg: 2 }} mb="xl">
        {/* Inundacion por Cuenca - Datos reales del API */}
        <Paper shadow="sm" p="md" radius="md" withBorder>
          <Title order={4} mb="md">
            Monitoreo Satelital por Cuenca
          </Title>
          {monitoringLoading ? (
            <Text c="gray.6" ta="center" py="md">
              Cargando datos...
            </Text>
          ) : rankingCuencas.length > 0 ? (
            <Stack gap="md">
              {rankingCuencas.map((cuenca) => {
                const cuencaConfig = config?.cuencas.find((c) => c.id === cuenca.cuenca);
                const color = cuencaConfig?.color || DEFAULT_CUENCA_COLORS[cuenca.cuenca] || 'blue';
                const nombre =
                  cuencaConfig?.nombre || DEFAULT_CUENCA_NAMES[cuenca.cuenca] || cuenca.cuenca;
                const progressValue = Math.min(cuenca.porcentaje_problematico * 10, 100);
                return (
                  <div key={cuenca.cuenca}>
                    <Group justify="space-between" mb="xs">
                      <Text size="sm" fw={500}>
                        {nombre}
                      </Text>
                      <Text size="sm" c="gray.6">
                        {cuenca.area_anegada_ha.toFixed(1)} ha (
                        {cuenca.porcentaje_problematico.toFixed(2)}%)
                      </Text>
                    </Group>
                    <Progress value={progressValue} color={color} size="lg" radius="xl" />
                  </div>
                );
              })}
            </Stack>
          ) : (
            <Text c="gray.6" ta="center" py="md">
              Sin datos de inundación disponibles
            </Text>
          )}
        </Paper>

        {/* Ultimos Reportes */}
        <Paper shadow="sm" p="md" radius="md" withBorder>
          <Group justify="space-between" mb="md">
            <Title order={4}>Ultimos Reportes Vecinales</Title>
            <Button
              component="a"
              href={withBasePath('/admin/participacion')}
              variant="subtle"
              size="xs"
            >
              Ver todos
            </Button>
          </Group>

          {recentReports.length > 0 ? (
            <Table.ScrollContainer minWidth={400}>
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
            </Table.ScrollContainer>
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
