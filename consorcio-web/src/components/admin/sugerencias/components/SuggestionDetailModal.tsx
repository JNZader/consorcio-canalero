import {
  Badge,
  Box,
  Button,
  Collapse,
  Divider,
  Group,
  Modal,
  Paper,
  Select,
  Stack,
  Text,
  Textarea,
  Timeline,
  Title,
} from '@mantine/core';
import { DatePicker } from '@mantine/dates';
import type { Sugerencia } from '../../../../lib/api';
import { formatDate } from '../../../../lib/formatters';
import { IconHistory, IconTrash } from '../../../ui/icons';
import { CATEGORIA_OPTIONS, getAllowedNextEstadosSugerencia } from '../constants';
import type { SeguimientoEntry } from '../sugerenciasPanelTypes';
import { SugerenciaGeometryMap } from './SugerenciaGeometryMap';

const SUGGESTION_HISTORY_REGION_ID = 'suggestion-history-region';

export function SuggestionDetailModal({
  opened,
  onClose,
  selectedSugerencia,
  canales,
  historial,
  loadingHistorial,
  showHistorial,
  setShowHistorial,
  newEstado,
  setNewEstado,
  publicComment,
  setPublicComment,
  adminNotes,
  setAdminNotes,
  agendarFecha,
  setAgendarFecha,
  onAgendar,
  agendando,
  onDelete,
  deleting,
  onUpdate,
  updating,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  selectedSugerencia: Sugerencia | null;
  /**
   * Batch 5 (2026-04-20): migrated from `waterways` (legacy Hidrografía mix)
   * to `canales` — the authoritative Pilar Azul reference-map backdrop.
   * Parents should wire this from `useCanales().relevados` wrapped in the
   * `{id, data, style}` shape expected by `SugerenciaGeometryMap`. Pass an
   * empty array when Pilar Azul data is not yet available; the modal still
   * mounts and the reference backdrop simply stays empty.
   */
  canales: Array<{
    id: string;
    data: import('geojson').FeatureCollection;
    style: { color?: string; weight?: number; opacity?: number };
  }>;
  historial: SeguimientoEntry[];
  loadingHistorial: boolean;
  showHistorial: boolean;
  setShowHistorial: (value: boolean) => void;
  newEstado: string;
  setNewEstado: (value: string) => void;
  publicComment: string;
  setPublicComment: (value: string) => void;
  adminNotes: string;
  setAdminNotes: (value: string) => void;
  agendarFecha: Date | null;
  setAgendarFecha: (value: Date | null) => void;
  onAgendar: () => void;
  agendando: boolean;
  onDelete: () => void;
  deleting: boolean;
  onUpdate: () => void;
  updating: boolean;
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Detalle de Sugerencia" size="lg">
      {selectedSugerencia && (
        <Stack gap="md">
          <div>
            <Text size="sm" fw={500}>
              Titulo
            </Text>
            <Text>{selectedSugerencia.titulo}</Text>
          </div>

          <div>
            <Text size="sm" fw={500}>
              Descripcion
            </Text>
            <Paper
              p="sm"
              style={{
                background: 'light-dark(var(--mantine-color-gray-1), var(--mantine-color-dark-6))',
              }}
              radius="sm"
            >
              <Text size="sm">{selectedSugerencia.descripcion}</Text>
            </Paper>
          </div>

          <Group>
            <div>
              <Text size="sm" fw={500}>
                Categoria
              </Text>
              <Badge variant="outline">
                {CATEGORIA_OPTIONS.find((c) => c.value === selectedSugerencia.categoria)?.label ||
                  'Sin categoria'}
              </Badge>
            </div>
            <div>
              <Text size="sm" fw={500}>
                Tipo
              </Text>
              <Badge
                color={selectedSugerencia.tipo === 'ciudadana' ? 'blue' : 'violet'}
                variant="light"
              >
                {selectedSugerencia.tipo === 'ciudadana' ? 'Ciudadana' : 'Interna'}
              </Badge>
            </div>
            <div>
              <Text size="sm" fw={500}>
                Fecha
              </Text>
              <Text size="sm" c="gray.6">
                {formatDate(selectedSugerencia.created_at)}
              </Text>
            </div>
          </Group>

          {selectedSugerencia.contacto_nombre && (
            <div>
              <Text size="sm" fw={500}>
                Contacto
              </Text>
              <Text size="sm" c="gray.6">
                {selectedSugerencia.contacto_nombre}
                {selectedSugerencia.contacto_email && ` - ${selectedSugerencia.contacto_email}`}
                {selectedSugerencia.contacto_telefono &&
                  ` - ${selectedSugerencia.contacto_telefono}`}
              </Text>
            </div>
          )}

          {selectedSugerencia.geometry?.features?.length ? (
            <div>
              <Group justify="space-between" align="center" mb="xs">
                <Text size="sm" fw={500}>
                  Geometría sugerida
                </Text>
                <Badge color="blue" variant="light">
                  Propuesta no oficial
                </Badge>
              </Group>
              <Box style={{ height: 280, borderRadius: 8, overflow: 'hidden' }}>
                <SugerenciaGeometryMap geometry={selectedSugerencia.geometry} canales={canales} />
              </Box>
              <Text size="xs" c="dimmed" mt={6}>
                Línea sugerida en violeta. Los canales relevados se muestran como referencia en azul
                oscuro.
              </Text>
            </div>
          ) : null}

          <Paper
            p="md"
            style={{
              background: 'light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-6))',
            }}
            radius="md"
          >
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <IconHistory size={18} />
                <Text size="sm" fw={600}>
                  Historial de Gestión
                </Text>
              </Group>
              <Button
                variant="subtle"
                size="xs"
                onClick={() => setShowHistorial(!showHistorial)}
                loading={loadingHistorial}
                aria-expanded={showHistorial}
                aria-controls={SUGGESTION_HISTORY_REGION_ID}
              >
                {showHistorial ? 'Ocultar' : 'Mostrar'} ({historial.length})
              </Button>
            </Group>

            <Collapse
              id={SUGGESTION_HISTORY_REGION_ID}
              in={showHistorial}
              role="region"
              aria-label="Historial de gestión de la sugerencia"
            >
              {historial.length === 0 ? (
                <Text size="sm" c="dimmed" ta="center" py="md">
                  {loadingHistorial ? 'Cargando historial...' : 'Sin historial disponible'}
                </Text>
              ) : (
                <Timeline active={0} lineWidth={2}>
                  {historial.map((entry) => (
                    <Timeline.Item
                      key={entry.id}
                      title={`Cambio a ${entry.estado_nuevo.replace('_', ' ').toUpperCase()}`}
                    >
                      <Text size="xs" fw={500}>
                        {entry.comentario_publico}
                      </Text>
                      {entry.comentario_interno && (
                        <Text size="xs" c="blue" fs="italic">
                          Interno: {entry.comentario_interno}
                        </Text>
                      )}
                      <Text size="xs" c="dimmed" mt={2}>
                        {formatDate(entry.fecha)}
                      </Text>
                    </Timeline.Item>
                  ))}
                  <Timeline.Item title="Sugerencia Creada">
                    <Text size="xs" mt={2}>
                      Ingresada al sistema
                    </Text>
                  </Timeline.Item>
                </Timeline>
              )}
            </Collapse>
          </Paper>

          {selectedSugerencia.estado === 'pendiente' && (
            <Paper
              p="md"
              style={{
                background:
                  'light-dark(var(--mantine-color-violet-0), var(--mantine-color-dark-5))',
              }}
              radius="md"
            >
              <Group justify="space-between" mb="sm">
                <Text size="sm" fw={600}>
                  Agendar para Reunión
                </Text>
                {agendarFecha && (
                  <Text size="xs" c="violet.7" fw={600}>
                    {formatDate(agendarFecha.toISOString().split('T')[0])}
                  </Text>
                )}
              </Group>
              <Text size="xs" c="dimmed" mb="xs">
                Tocá un día del calendario y luego "Agendar". Sólo fechas futuras.
              </Text>
              {/*
                Stack vertical: el DatePicker centrado arriba (con su
                tamaño natural — el modal lg le da espacio cómodo) y los
                botones en una fila al pie. Antes el layout era
                horizontal con un Stack `flex: 1` al costado, lo que
                dejaba un huecazo vertical y hacía ver los botones
                "deformes". Inline > popover acá: mostrar el mes
                completo es la única operación útil del panel y no hay
                otro contenido que compita por el espacio.
              */}
              <Stack gap="md">
                <Group justify="center">
                  <DatePicker
                    value={agendarFecha}
                    onChange={(value) =>
                      setAgendarFecha(value ? new Date(value as unknown as string) : null)
                    }
                    minDate={new Date()}
                    size="sm"
                    styles={{
                      calendarHeader: { marginBottom: 8 },
                      day: { borderRadius: 'var(--mantine-radius-sm)' },
                    }}
                  />
                </Group>
                <Group grow gap="xs">
                  {agendarFecha && (
                    <Button variant="subtle" color="gray" onClick={() => setAgendarFecha(null)}>
                      Limpiar
                    </Button>
                  )}
                  <Button
                    color="violet"
                    onClick={onAgendar}
                    loading={agendando}
                    disabled={!agendarFecha}
                  >
                    Agendar
                  </Button>
                </Group>
              </Stack>
            </Paper>
          )}

          <Paper
            p="md"
            style={{
              background: 'light-dark(var(--mantine-color-blue-0), var(--mantine-color-dark-5))',
            }}
            radius="md"
          >
            <Title order={6} size="sm" fw={600} mb="md">
              Gestión de la sugerencia
            </Title>
            <Stack gap="sm">
              <Select
                label="Cambiar Estado"
                description={
                  String(selectedSugerencia.estado) === 'implementada' ||
                  String(selectedSugerencia.estado) === 'descartada'
                    ? 'La sugerencia está cerrada — no admite más cambios de estado.'
                    : undefined
                }
                data={[...getAllowedNextEstadosSugerencia(String(selectedSugerencia.estado))]}
                value={newEstado}
                onChange={(v) => setNewEstado(v || String(selectedSugerencia.estado))}
                disabled={
                  String(selectedSugerencia.estado) === 'implementada' ||
                  String(selectedSugerencia.estado) === 'descartada'
                }
              />
              <Textarea
                label="Comentario Público"
                placeholder="Lo que el vecino verá en su seguimiento..."
                value={publicComment}
                onChange={(e) => setPublicComment(e.target.value)}
                minRows={2}
              />
              <Textarea
                label="Notas Internas (Consorcio)"
                placeholder="Detalles de la discusión en comisión, presupuesto, etc..."
                value={adminNotes}
                onChange={(e) => setAdminNotes(e.target.value)}
                minRows={2}
              />
            </Stack>
          </Paper>

          <Divider />

          <Group justify="space-between">
            <Button
              variant="light"
              color="red"
              leftSection={<IconTrash size={16} />}
              onClick={onDelete}
              loading={deleting}
            >
              Eliminar
            </Button>
            <Group>
              <Button variant="light" onClick={onClose}>
                Cancelar
              </Button>
              <Button onClick={onUpdate} loading={updating}>
                Registrar Gestión
              </Button>
            </Group>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
