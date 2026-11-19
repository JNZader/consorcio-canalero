/**
 * MisInformes.tsx — the user's background informes (PR 2, S2: "«Mis informes»
 * en el front").
 *
 * One Mantine Table row per informe: nombre (with the failure reason under it
 * when the job died — S8's readable `error`), union hectares (a dash until
 * the task stores `resultado`, never a fabricated 0), a colored estado Badge,
 * the polled progreso (Progress is `aria-hidden`; the visible "%"-text and
 * the Badge carry the state to assistive tech, the house pattern from
 * VistaPrevia), the creation date in es-AR, and the download button — enabled
 * only on `completed`, because the PDF endpoint answers 409 until the bytes
 * exist.
 *
 * The data and the polling live in `useInformeArea` (this component is the
 * rendering half only), so the Generar step's inline progress and this table
 * share ONE query and one poll loop.
 */

import {
  Alert,
  Badge,
  Box,
  Button,
  Group,
  Loader,
  Progress,
  ScrollArea,
  Stack,
  Table,
  Text,
} from '@mantine/core';

import {
  INFORME_AREA_ESTADOS,
  type InformeAreaEstado,
  type InformeAreaItem,
} from '../../../lib/api/informesArea';
import { fmtHa } from '../fichaShared';
import { esRechazoTerminal, useDescargarInformeArea, useMisInformes } from './useInformeArea';

/** Badge label + theme color per estado. Colors are the semantic palette. */
const ETIQUETAS_ESTADO: Record<InformeAreaEstado, { etiqueta: string; color: string }> = {
  [INFORME_AREA_ESTADOS.PENDIENTE]: { etiqueta: 'Pendiente', color: 'gray' },
  [INFORME_AREA_ESTADOS.GENERANDO]: { etiqueta: 'Generando', color: 'institucional' },
  [INFORME_AREA_ESTADOS.COMPLETO]: { etiqueta: 'Listo', color: 'exito' },
  [INFORME_AREA_ESTADOS.FALLIDO]: { etiqueta: 'Falló', color: 'alerta' },
};

const FORMATO_FECHA = new Intl.DateTimeFormat('es-AR', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

function fechaEsAr(iso: string): string {
  return FORMATO_FECHA.format(new Date(iso));
}

export interface MisInformesProps {
  /** Test seam: skip the data hooks and render given rows directly. */
  readonly informes?: readonly InformeAreaItem[];
}

export function MisInformes({ informes }: MisInformesProps) {
  const listado = useMisInformes();
  const descarga = useDescargarInformeArea();

  const filas = informes ?? listado.informes;

  if (listado.isLoading) {
    return (
      <Group gap="xs" py="lg" data-testid="informe-area-mis-informes-cargando">
        <Loader size="sm" />
        <Text size="sm" c="dimmed">
          Cargando tus informes…
        </Text>
      </Group>
    );
  }

  if (listado.isError) {
    return (
      <Alert color="alerta" variant="light" title="No se pudo cargar tus informes">
        <Stack gap="xs">
          <Text size="sm">
            {listado.error instanceof Error && listado.error.message
              ? listado.error.message
              : 'Revisá la conexión e intentá de nuevo.'}
          </Text>
          {!esRechazoTerminal(listado.error) && (
            <Button size="xs" variant="light" color="red" onClick={listado.refetch}>
              Reintentar
            </Button>
          )}
        </Stack>
      </Alert>
    );
  }

  if (filas.length === 0) {
    return (
      <Stack align="center" gap={4} py="lg" data-testid="informe-area-mis-informes-vacio">
        <Text size="sm" c="dimmed">
          Todavía no generaste informes.
        </Text>
        <Text size="xs" c="dimmed">
          Elegí subcuencas en el mapa y generá el primero; va a aparecer acá para descargarlo.
        </Text>
      </Stack>
    );
  }

  return (
    // Mantine 9 dropped `Table.ScrollArea`; the plain ScrollArea carries the
    // horizontal story for the 6 columns inside the ~520px drawer.
    <ScrollArea type="auto" offsetScrollbars>
      <Table
        withRowBorders={false}
        verticalSpacing={6}
        fz="xs"
        data-testid="informe-area-mis-informes"
      >
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Informe</Table.Th>
            <Table.Th ta="right">Superficie</Table.Th>
            <Table.Th>Estado</Table.Th>
            <Table.Th w={90}>Progreso</Table.Th>
            <Table.Th>Creada</Table.Th>
            <Table.Th ta="right">PDF</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {filas.map((informe) => {
            const estado = ETIQUETAS_ESTADO[informe.estado] ?? ETIQUETAS_ESTADO.pending;
            const descargable = informe.estado === INFORME_AREA_ESTADOS.COMPLETO;
            return (
              <Table.Tr key={informe.id} data-testid="informe-area-mis-informes-fila">
                <Table.Td>
                  <Text size="xs" truncate="end" maw={150}>
                    {informe.nombre}
                  </Text>
                  {informe.estado === INFORME_AREA_ESTADOS.FALLIDO && informe.error && (
                    <Text size="xs" c="alerta" maw={170}>
                      {informe.error}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td ta="right">
                  {informe.area_ha === null ? '—' : fmtHa(informe.area_ha)}
                </Table.Td>
                <Table.Td>
                  <Badge size="xs" color={estado.color} variant="light">
                    {estado.etiqueta}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  {informe.estado === INFORME_AREA_ESTADOS.FALLIDO ? (
                    <Box component="span" c="dimmed">
                      —
                    </Box>
                  ) : (
                    <Group gap={6} wrap="nowrap">
                      <Progress
                        value={informe.progreso}
                        size="sm"
                        aria-hidden
                        style={{ flex: 1 }}
                      />
                      <Text size="xs" c="dimmed" style={{ flex: '0 0 auto' }} ta="right">
                        {informe.progreso}%
                      </Text>
                    </Group>
                  )}
                </Table.Td>
                <Table.Td>{fechaEsAr(informe.created_at)}</Table.Td>
                <Table.Td ta="right">
                  <Button
                    size="compact-xs"
                    variant="light"
                    disabled={!descargable}
                    loading={descarga.isPending && descarga.variables?.id === informe.id}
                    onClick={() => descarga.mutate(informe)}
                    aria-label={`Descargar el PDF de ${informe.nombre}`}
                    data-testid="informe-area-mis-informes-descarga"
                  >
                    Descargar
                  </Button>
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  );
}
