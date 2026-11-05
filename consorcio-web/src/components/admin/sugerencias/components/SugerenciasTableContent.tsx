import { Badge, Box, Group, Pagination, Text, Tooltip } from '@mantine/core';
import type { Sugerencia } from '../../../../lib/api';
import { formatDate } from '../../../../lib/formatters';
import { IconButton } from '../../../ui/IconButton';
import { IconInfoCircle } from '../../../ui/icons';
import { LoadingState } from '../../../ui/LoadingState';
import { ResponsiveRecordList } from '../../../ui/ResponsiveRecordList';
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
      <ResponsiveRecordList
        label="Tabla de sugerencias"
        columns={['Fecha', 'Título', 'Categoría', 'Tipo', 'Estado', 'Acciones']}
        minWidth={760}
        striped
        highlightOnHover
        records={sugerencias.map((sug) => ({
          id: sug.id,
          cells: [
            <Text key="fecha" size="sm">
              {formatDate(sug.created_at)}
            </Text>,
            <Box key="titulo">
              <Text size="sm" lineClamp={1} style={{ maxWidth: 250 }}>
                {sug.titulo}
              </Text>
              {sug.geometry?.features?.length ? (
                <Badge size="xs" color="blue" variant="light" mt={4}>
                  Con línea
                </Badge>
              ) : null}
            </Box>,
            <Badge key="categoria" variant="outline" size="sm">
              {getCategoriaLabel(sug.categoria)}
            </Badge>,
            <Badge
              key="tipo"
              color={sug.tipo === 'ciudadana' ? 'blue' : 'violet'}
              size="sm"
              variant="light"
            >
              {sug.tipo === 'ciudadana' ? 'Ciudadana' : 'Interna'}
            </Badge>,
            getStatusBadge(sug.estado),
            <Tooltip key="acciones" label="Ver detalle">
              <IconButton
                variant="light"
                onClick={() => onViewDetail(sug)}
                aria-label={`Ver detalle de sugerencia: ${sug.titulo}`}
              >
                <IconInfoCircle size={18} />
              </IconButton>
            </Tooltip>,
          ],
        }))}
      />

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
