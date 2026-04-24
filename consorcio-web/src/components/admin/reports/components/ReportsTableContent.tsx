import {
  ActionIcon,
  Badge,
  Box,
  Center,
  Group,
  Loader,
  Pagination,
  Table,
  Text,
  Tooltip,
} from '@mantine/core';
import type { Report } from '../../../../lib/api';
import { formatDate } from '../../../../lib/formatters';
import { EmptyState } from '../../../ui/EmptyState';
import { IconInfoCircle, IconMap } from '../../../ui/icons';
import { getCategoryLabel } from '../reportsPanelUtils';

export function ReportsTableContent({
  loading,
  filteredReports,
  totalPages,
  page,
  onPageChange,
  onViewDetail,
  getStatusBadge,
}: Readonly<{
  loading: boolean;
  filteredReports: Report[];
  totalPages: number;
  page: number;
  onPageChange: (page: number) => void;
  onViewDetail: (report: Report) => void;
  getStatusBadge: (status: string) => React.ReactNode;
}>) {
  if (loading) {
    return (
      <Center py="xl" aria-busy="true" aria-live="polite">
        <Group align="center">
          <Loader aria-hidden="true" />
          <Text size="sm" c="gray.6">
            Cargando denuncias...
          </Text>
        </Group>
      </Center>
    );
  }

  if (filteredReports.length === 0) {
    return (
      <EmptyState
        title="No hay denuncias"
        description="No se encontraron denuncias con los filtros aplicados"
      />
    );
  }

  return (
    <Box aria-live="polite">
      <Table.ScrollContainer minWidth={820} type="native">
        <Table striped highlightOnHover aria-label="Tabla de denuncias">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Fecha</Table.Th>
              <Table.Th>Categoria</Table.Th>
              <Table.Th>Descripcion</Table.Th>
              <Table.Th>Ubicacion</Table.Th>
              <Table.Th>Estado</Table.Th>
              <Table.Th>Acciones</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {filteredReports.map((report) => (
              <Table.Tr key={report.id}>
                <Table.Td>
                  <Text size="sm">{formatDate(report.created_at, { includeTime: true })}</Text>
                </Table.Td>
                <Table.Td>
                  <Badge variant="outline">{getCategoryLabel(report.categoria)}</Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" lineClamp={2} style={{ maxWidth: 300 }}>
                    {report.descripcion}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c="gray.6" lineClamp={1} style={{ maxWidth: 200 }}>
                    {report.ubicacion_texto || 'Sin direccion'}
                  </Text>
                </Table.Td>
                <Table.Td>{getStatusBadge(report.estado)}</Table.Td>
                <Table.Td>
                  <Group gap="xs" wrap="nowrap">
                    <Tooltip label="Ver detalle">
                      <ActionIcon
                        variant="light"
                        onClick={() => onViewDetail(report)}
                        aria-label={`Ver detalle de denuncia del ${formatDate(report.created_at)}`}
                      >
                        <IconInfoCircle size={18} />
                      </ActionIcon>
                    </Tooltip>
                    {report.latitud != null && report.longitud != null && (
                      <Tooltip label="Ver en mapa">
                        <ActionIcon
                          variant="light"
                          color="blue"
                          component="a"
                          href={`/mapa?lat=${report.latitud}&lng=${report.longitud}&zoom=15`}
                          aria-label={`Ver ubicacion de denuncia en el mapa, coordenadas ${report.latitud}, ${report.longitud}`}
                        >
                          <IconMap size={18} />
                        </ActionIcon>
                      </Tooltip>
                    )}
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>

      {totalPages > 1 && (
        <Group justify="center" mt="md">
          <Pagination
            total={totalPages}
            value={page}
            onChange={onPageChange}
            aria-label="Paginacion de denuncias"
          />
        </Group>
      )}
    </Box>
  );
}
