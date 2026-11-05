import { Paper, Text } from '@mantine/core';
import { IconButton } from '../../../../ui/IconButton';
import { IconEdit } from '../../../../ui/icons';
import { ResponsiveRecordList } from '../../../../ui/ResponsiveRecordList';
import type { Gasto } from '../finanzasTypes';
import { renderCategoriaBadge } from '../finanzasUtils';

export function GastosTable({
  gastos,
  onEdit,
}: Readonly<{ gastos: Gasto[]; onEdit: (gasto: Gasto) => void }>) {
  return (
    <Paper withBorder radius="md">
      <ResponsiveRecordList
        label="Libro de gastos"
        columns={['Fecha', 'Descripción', 'Categoría', 'Monto', 'Proveedor', 'Acciones']}
        minWidth={680}
        verticalSpacing="sm"
        records={gastos.map((gasto) => ({
          id: gasto.id,
          cells: [
            new Date(gasto.fecha).toLocaleDateString(),
            <Text key="descripcion" size="sm" fw={500}>
              {gasto.descripcion}
            </Text>,
            renderCategoriaBadge(gasto.categoria),
            <Text key="monto" fw={700} c="red.7">
              -${gasto.monto.toLocaleString()}
            </Text>,
            gasto.proveedor || '-',
            <IconButton
              key="acciones"
              variant="subtle"
              onClick={() => onEdit(gasto)}
              aria-label={`Editar gasto: ${gasto.descripcion}`}
            >
              <IconEdit size={16} />
            </IconButton>,
          ],
        }))}
      />
    </Paper>
  );
}
