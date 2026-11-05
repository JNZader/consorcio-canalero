import { Paper, Text } from '@mantine/core';
import { IconButton } from '../../../../ui/IconButton';
import { IconEdit } from '../../../../ui/icons';
import { ResponsiveRecordList } from '../../../../ui/ResponsiveRecordList';
import type { Ingreso } from '../finanzasTypes';
import { renderCategoriaBadge } from '../finanzasUtils';

export function IngresosTable({
  ingresos,
  onEdit,
}: Readonly<{ ingresos: Ingreso[]; onEdit: (ingreso: Ingreso) => void }>) {
  return (
    <Paper withBorder radius="md">
      <ResponsiveRecordList
        label="Libro de ingresos"
        columns={['Fecha', 'Descripción', 'Categoría', 'Monto', 'Consorcista', 'Acciones']}
        minWidth={680}
        verticalSpacing="sm"
        records={ingresos.map((ingreso) => ({
          id: ingreso.id,
          cells: [
            new Date(ingreso.fecha).toLocaleDateString(),
            <Text key="descripcion" size="sm" fw={500}>
              {ingreso.descripcion}
            </Text>,
            renderCategoriaBadge(ingreso.categoria),
            <Text key="monto" fw={700} c="green.7">
              +${ingreso.monto.toLocaleString()}
            </Text>,
            <Text key="consorcista" size="xs" c="dimmed">
              {ingreso.consorcista_id || '-'}
            </Text>,
            <IconButton
              key="acciones"
              variant="subtle"
              onClick={() => onEdit(ingreso)}
              aria-label={`Editar ingreso: ${ingreso.descripcion}`}
            >
              <IconEdit size={16} />
            </IconButton>,
          ],
        }))}
      />
    </Paper>
  );
}
