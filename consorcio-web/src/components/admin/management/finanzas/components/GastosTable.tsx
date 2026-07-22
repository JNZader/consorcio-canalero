import { ActionIcon, Paper, Table, Text } from '@mantine/core';
import { IconEdit } from '../../../../ui/icons';
import type { Gasto } from '../finanzasTypes';
import { renderCategoriaBadge } from '../finanzasUtils';

export function GastosTable({
  gastos,
  onEdit,
}: Readonly<{ gastos: Gasto[]; onEdit: (gasto: Gasto) => void }>) {
  return (
    <Paper withBorder radius="md">
      <Table.ScrollContainer minWidth={680} type="native">
        <Table verticalSpacing="sm" aria-label="Libro de gastos">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Fecha</Table.Th>
              <Table.Th>Descripcion</Table.Th>
              <Table.Th>Categoria</Table.Th>
              <Table.Th>Monto</Table.Th>
              <Table.Th>Proveedor</Table.Th>
              <Table.Th>Acciones</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {gastos.map((gasto) => (
              <Table.Tr key={gasto.id}>
                <Table.Td>{new Date(gasto.fecha).toLocaleDateString()}</Table.Td>
                <Table.Td>
                  <Text size="sm" fw={500}>
                    {gasto.descripcion}
                  </Text>
                </Table.Td>
                <Table.Td>{renderCategoriaBadge(gasto.categoria)}</Table.Td>
                <Table.Td>
                  <Text fw={700} c="red.7">
                    -${gasto.monto.toLocaleString()}
                  </Text>
                </Table.Td>
                <Table.Td>{gasto.proveedor || '-'}</Table.Td>
                <Table.Td>
                  <ActionIcon
                    variant="subtle"
                    onClick={() => onEdit(gasto)}
                    aria-label={`Editar gasto: ${gasto.descripcion}`}
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
