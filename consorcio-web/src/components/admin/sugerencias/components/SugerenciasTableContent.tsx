import { Badge, Box, Group, Pagination, Table, Text, Tooltip } from '@mantine/core';
import type { Sugerencia } from '../../../../lib/api';
import { formatDate } from '../../../../lib/formatters';
import { IconButton } from '../../../ui/IconButton';
import { IconInfoCircle } from '../../../ui/icons';
import { LoadingState } from '../../../ui/LoadingState';
import { getCategoriaLabel } from '../sugerenciasPanelUtils';

export function SugerenciasTableContent({
  loading,
  sugerencias,
  totalPages,
  page,
  onPageChange,
  onViewDetail,
  getStatusBadge,
}: Readonly<{
  loading: boolean;
  sugerencias: Sugerencia[];
  totalPages: number;
  page: number;
  onPageChange: (page: number) => void;
  onViewDetail: (sugerencia: Sugerencia) => void;
  getStatusBadge: (status: string) => React.ReactNode;
}>) {
  if (loading) {
    return <LoadingState compact message="Cargando sugerencias..." />;
  }

  if (sugerencias.length === 0) {
    return (
      <LoadingState
        status="empty"
        title="No hay sugerencias"
        description="No se encontraron sugerencias con los filtros aplicados"
      />
    );
  }

  return (
    <Box aria-live="polite">
      <Table.ScrollContainer minWidth={760} type="native">
        <Table striped highlightOnHover aria-label="Tabla de sugerencias">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Fecha</Table.Th>
              <Table.Th>Título</Table.Th>
              <Table.Th>Categoría</Table.Th>
              <Table.Th>Tipo</Table.Th>
              <Table.Th>Estado</Table.Th>
              <Table.Th>Acciones</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {sugerencias.map((sug) => (
              <Table.Tr key={sug.id}>
                <Table.Td>
                  <Text size="sm">{formatDate(sug.created_at)}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" lineClamp={1} style={{ maxWidth: 250 }}>
                    {sug.titulo}
                  </Text>
                  {sug.geometry?.features?.length ? (
                    <Badge size="xs" color="blue" variant="light" mt={4}>
                      Con línea
                    </Badge>
                  ) : null}
                </Table.Td>
                <Table.Td>
                  <Badge variant="outline" size="sm">
                    {getCategoriaLabel(sug.categoria)}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Badge
                    color={sug.tipo === 'ciudadana' ? 'blue' : 'violet'}
                    size="sm"
                    variant="light"
                  >
                    {sug.tipo === 'ciudadana' ? 'Ciudadana' : 'Interna'}
                  </Badge>
                </Table.Td>
                <Table.Td>{getStatusBadge(sug.estado)}</Table.Td>
                <Table.Td>
                  <Tooltip label="Ver detalle">
                    <IconButton
                      variant="light"
                      onClick={() => onViewDetail(sug)}
                      aria-label={`Ver detalle de sugerencia: ${sug.titulo}`}
                    >
                      <IconInfoCircle size={18} />
                    </IconButton>
                  </Tooltip>
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
            aria-label="Paginación de sugerencias"
          />
        </Group>
      )}
    </Box>
  );
}
