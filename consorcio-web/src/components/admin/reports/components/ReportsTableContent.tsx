import { Badge, Box, Button, Checkbox, Group, Pagination, Text, Tooltip } from '@mantine/core';
import type { Report } from '../../../../lib/api';
import { formatDate } from '../../../../lib/formatters';
import { IconButton } from '../../../ui/IconButton';
import { IconInfoCircle, IconMap } from '../../../ui/icons';
import { LoadingState } from '../../../ui/LoadingState';
import { ResponsiveRecordList } from '../../../ui/ResponsiveRecordList';
import { getCategoryLabel } from '../reportsPanelUtils';

/**
 * Columnas ordenables de la bandeja. Los `sortKey` son los que acepta
 * el backend para denuncias: created_at | estado | tipo (la columna
 * "Categoría" ordena por `tipo`, el nombre real del campo en la API).
 */
const COLUMNS = [
  { label: 'Fecha', sortKey: 'created_at' },
  { label: 'Categoría', sortKey: 'tipo' },
  'Descripción',
  'Ubicación',
  { label: 'Estado', sortKey: 'estado' },
  'Acciones',
] as const;

export function ReportsTableContent({
  loading,
  loadError,
  onRetry,
  selectedIds,
  onToggleSelected,
  filteredReports,
  totalPages,
  page,
  onPageChange,
  onViewDetail,
  getStatusBadge,
  sorting,
}: Readonly<{
  loading: boolean;
  loadError?: string | null;
  onRetry?: () => void;
  selectedIds?: readonly string[];
  onToggleSelected?: (id: string) => void;
  filteredReports: Report[];
  totalPages: number;
  page: number;
  onPageChange: (page: number) => void;
  onViewDetail: (report: Report) => void;
  getStatusBadge: (status: string) => React.ReactNode;
  sorting?: React.ComponentProps<typeof ResponsiveRecordList>['sorting'];
}>) {
  if (loading) {
    return <LoadingState compact message="Cargando denuncias..." />;
  }

  if (loadError) {
    return (
      <LoadingState
        status="error"
        title="No pudimos cargar las denuncias"
        message={loadError}
        action={
          onRetry ? (
            <Button mt="sm" onClick={onRetry}>
              Reintentar
            </Button>
          ) : undefined
        }
      />
    );
  }

  if (filteredReports.length === 0) {
    return (
      <LoadingState
        status="empty"
        title="No hay denuncias"
        description="No se encontraron denuncias con los filtros aplicados"
      />
    );
  }

  return (
    <Box aria-live="polite">
      <ResponsiveRecordList
        label="Tabla de denuncias"
        columns={COLUMNS}
        minWidth={820}
        striped
        highlightOnHover
        sorting={sorting}
        records={filteredReports.map((report) => ({
          id: report.id,
          cells: [
            <Text key="fecha" size="sm">
              {formatDate(report.created_at, { includeTime: true })}
            </Text>,
            <Badge key="categoria" variant="outline">
              {getCategoryLabel(report.categoria)}
            </Badge>,
            <Text key="descripcion" size="sm" lineClamp={2} style={{ maxWidth: 300 }}>
              {report.descripcion}
            </Text>,
            <Text key="ubicacion" size="sm" c="dimmed" lineClamp={1} style={{ maxWidth: 200 }}>
              {report.ubicacion_texto || 'Sin dirección'}
            </Text>,
            getStatusBadge(report.estado),
            <Group key="acciones" gap="xs" wrap="wrap">
              {onToggleSelected ? (
                <Checkbox
                  aria-label={`Seleccionar denuncia ${report.id}`}
                  checked={selectedIds?.includes(report.id) ?? false}
                  onChange={() => onToggleSelected(report.id)}
                />
              ) : null}
              <Tooltip label="Ver detalle">
                <IconButton
                  variant="light"
                  onClick={() => onViewDetail(report)}
                  aria-label={`Ver detalle de denuncia del ${formatDate(report.created_at)}`}
                >
                  <IconInfoCircle size={18} />
                </IconButton>
              </Tooltip>
              {report.latitud != null && report.longitud != null && (
                <Tooltip label="Ver en mapa">
                  <IconButton
                    variant="light"
                    component="a"
                    href={`/mapa?${new URLSearchParams({
                      report: '1',
                      lat: String(report.latitud),
                      lng: String(report.longitud),
                      zoom: '15',
                    })}`}
                    aria-label={`Ver ubicación de denuncia en el mapa, coordenadas ${report.latitud}, ${report.longitud}`}
                  >
                    <IconMap size={18} />
                  </IconButton>
                </Tooltip>
              )}
            </Group>,
          ],
        }))}
      />

      {totalPages > 1 && (
        <Group justify="center" mt="md">
          <Pagination
            total={totalPages}
            value={page}
            onChange={onPageChange}
            aria-label="Paginación de denuncias"
          />
        </Group>
      )}
    </Box>
  );
}
