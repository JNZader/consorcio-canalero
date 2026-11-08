import { Badge, Box, Button, Group, Pagination, Text, Tooltip } from '@mantine/core';
import type { Sugerencia } from '../../../../lib/api';
import { formatDate } from '../../../../lib/formatters';
import { IconButton } from '../../../ui/IconButton';
import { IconInfoCircle } from '../../../ui/icons';
import { LoadingState } from '../../../ui/LoadingState';
import { ResponsiveRecordList } from '../../../ui/ResponsiveRecordList';
import { getCategoriaLabel } from '../sugerenciasPanelUtils';

/**
 * Columnas ordenables de la bandeja. Los `sortKey` son los que acepta
 * el backend para sugerencias: created_at | estado | categoria.
 */
const COLUMNS = [
  { label: 'Fecha', sortKey: 'created_at' },
  'Título',
  { label: 'Categoría', sortKey: 'categoria' },
  'Tipo',
  { label: 'Estado', sortKey: 'estado' },
  'Acciones',
] as const;

export function SugerenciasTableContent({
  loading,
  loadError,
  onRetry,
  sugerencias,
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
  sugerencias: Sugerencia[];
  totalPages: number;
  page: number;
  onPageChange: (page: number) => void;
  onViewDetail: (sugerencia: Sugerencia) => void;
  getStatusBadge: (status: string) => React.ReactNode;
  sorting?: React.ComponentProps<typeof ResponsiveRecordList>['sorting'];
}>) {
  if (loading) {
    return <LoadingState compact message="Cargando sugerencias..." />;
  }

  if (loadError) {
    return (
      <LoadingState
        status="error"
        title="No pudimos cargar las sugerencias"
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
        columns={COLUMNS}
        minWidth={760}
        striped
        highlightOnHover
        sorting={sorting}
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
