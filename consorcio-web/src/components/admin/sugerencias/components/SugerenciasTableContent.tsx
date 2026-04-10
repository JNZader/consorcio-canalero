import { ActionIcon, Badge, Center, Group, Loader, Pagination, Table, Text, Tooltip } from '@mantine/core';
import type { Sugerencia } from '../../../../lib/api';
import { formatDate } from '../../../../lib/formatters';
import { EmptyState } from '../../../ui';
import { IconInfoCircle } from '../../../ui/icons';
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
    return (
      <Center py="xl">
        <Group align="center">
          <Loader />
          <Text size="sm" c="gray.6">
            Cargando sugerencias...
          </Text>
        </Group>
      </Center>
    );
  }

  if (sugerencias.length === 0) {
    return (
      <EmptyState
        title="No hay sugerencias"
        description="No se encontraron sugerencias con los filtros aplicados"
      />
    );
  }

  return (
    <>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Fecha</Table.Th>
            <Table.Th>Titulo</Table.Th>
            <Table.Th>Categoria</Table.Th>
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
                  <ActionIcon variant="light" onClick={() => onViewDetail(sug)}>
                    <IconInfoCircle size={18} />
                  </ActionIcon>
                </Tooltip>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      {totalPages > 1 && (
        <Group justify="center" mt="md">
          <Pagination total={totalPages} value={page} onChange={onPageChange} />
        </Group>
      )}
    </>
  );
}
