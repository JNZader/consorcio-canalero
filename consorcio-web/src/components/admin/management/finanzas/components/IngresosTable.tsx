import { ActionIcon, Anchor, Paper, Table, Text } from '@mantine/core';
import { IconEdit } from '../../../../ui/icons';
import type { Ingreso } from '../finanzasTypes';
import { renderFuenteBadge } from '../finanzasUtils';

export function IngresosTable({
  ingresos,
  onEdit,
}: Readonly<{
  ingresos: Ingreso[];
  onEdit: (ingreso: Ingreso) => void;
}>) {
  return (
    <Paper withBorder radius="md">
      <Table.ScrollContainer minWidth={760} type="native">
        <Table verticalSpacing="sm" aria-label="Libro de ingresos">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Fecha</Table.Th>
              <Table.Th>Descripcion</Table.Th>
              <Table.Th>Fuente</Table.Th>
              <Table.Th>Monto</Table.Th>
              <Table.Th>Pagador</Table.Th>
              <Table.Th>Comprobante</Table.Th>
              <Table.Th>Acciones</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {ingresos.map((ingreso) => (
              <Table.Tr key={ingreso.id}>
                <Table.Td>{new Date(ingreso.fecha).toLocaleDateString()}</Table.Td>
                <Table.Td>
                  <Text size="sm" fw={500}>
                    {ingreso.descripcion}
                  </Text>
                </Table.Td>
                <Table.Td>{renderFuenteBadge(ingreso.fuente)}</Table.Td>
                <Table.Td>
                  <Text fw={700} c="green.7">
                    +${ingreso.monto.toLocaleString()}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="xs" c="dimmed">
                    {ingreso.pagador || '-'}
                  </Text>
                </Table.Td>
                <Table.Td>
                  {ingreso.comprobante_url ? (
                    <Anchor
                      href={ingreso.comprobante_url}
                      target="_blank"
                      rel="noreferrer"
                      size="sm"
                    >
                      Ver archivo
                    </Anchor>
                  ) : (
                    <Text size="xs" c="dimmed">
                      -
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <ActionIcon
                    variant="subtle"
                    onClick={() => onEdit(ingreso)}
                    aria-label={`Editar ingreso: ${ingreso.descripcion}`}
                  >
                    <IconEdit size={16} />
                  </ActionIcon>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Paper>
  );
}
