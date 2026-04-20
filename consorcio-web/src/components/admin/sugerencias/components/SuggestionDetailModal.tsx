import { Badge, Box, Button, Collapse, Divider, Group, Modal, Paper, Select, Stack, Text, Textarea, Timeline, Title } from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import type { Sugerencia } from '../../../../lib/api';
import { formatDate } from '../../../../lib/formatters';
import { IconHistory, IconTrash } from '../../../ui/icons';
import { CATEGORIA_OPTIONS, ESTADO_OPTIONS } from '../constants';
import type { SeguimientoEntry } from '../sugerenciasPanelTypes';
import { SugerenciaGeometryMap } from './SugerenciaGeometryMap';

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
  onIncorporateChannel,
  incorporating,
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
  canales: Array<{ id: string; data: import('geojson').FeatureCollection; style: { color?: string; weight?: number; opacity?: number } }>;
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
  onIncorporateChannel: () => void;
  incorporating: boolean;
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
            <Text size="sm" fw={500}>Titulo</Text>
            <Text>{selectedSugerencia.titulo}</Text>
          </div>

          <div>
            <Text size="sm" fw={500}>Descripcion</Text>
            <Paper p="sm" style={{ background: 'light-dark(var(--mantine-color-gray-1), var(--mantine-color-dark-6))' }} radius="sm">
              <Text size="sm">{selectedSugerencia.descripcion}</Text>
            </Paper>
          </div>

          <Group>
            <div>
              <Text size="sm" fw={500}>Categoria</Text>
              <Badge variant="outline">
                {CATEGORIA_OPTIONS.find((c) => c.value === selectedSugerencia.categoria)?.label || 'Sin categoria'}
              </Badge>
            </div>
            <div>
              <Text size="sm" fw={500}>Tipo</Text>
              <Badge color={selectedSugerencia.tipo === 'ciudadana' ? 'blue' : 'violet'} variant="light">
                {selectedSugerencia.tipo === 'ciudadana' ? 'Ciudadana' : 'Interna'}
              </Badge>
            </div>
            <div>
              <Text size="sm" fw={500}>Fecha</Text>
              <Text size="sm" c="gray.6">{formatDate(selectedSugerencia.created_at)}</Text>
            </div>
          </Group>

          {selectedSugerencia.contacto_nombre && (
            <div>
              <Text size="sm" fw={500}>Contacto</Text>
              <Text size="sm" c="gray.6">
                {selectedSugerencia.contacto_nombre}
                {selectedSugerencia.contacto_email && ` - ${selectedSugerencia.contacto_email}`}
                {selectedSugerencia.contacto_telefono && ` - ${selectedSugerencia.contacto_telefono}`}
              </Text>
            </div>
          )}

          {selectedSugerencia.geometry?.features?.length ? (
            <div>
              <Group justify="space-between" align="center" mb="xs">
                <Text size="sm" fw={500}>Geometría sugerida</Text>
                <Badge color="blue" variant="light">Propuesta no oficial</Badge>
              </Group>
              <Box style={{ height: 280, borderRadius: 8, overflow: 'hidden' }}>
                <SugerenciaGeometryMap
                  geometry={selectedSugerencia.geometry}
                  canales={canales}
                />
              </Box>
              <Text size="xs" c="dimmed" mt={6}>
                Línea sugerida en violeta. Los canales relevados se muestran como referencia en azul oscuro.
              </Text>
              <Group mt="sm">
                <Button
                  size="xs"
                  color="teal"
                  onClick={onIncorporateChannel}
                  loading={incorporating}
                  disabled={String(selectedSugerencia.estado) === 'implementada'}
                >
                  {String(selectedSugerencia.estado) === 'implementada'
                    ? 'Ya incorporada a Canales existentes'
                    : 'Incorporar a Canales existentes'}
                </Button>
              </Group>
            </div>
          ) : null}

          <Paper p="md" style={{ background: 'light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-6))' }} radius="md">
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <IconHistory size={18} />
                <Text size="sm" fw={600}>Historial de Gestión</Text>
              </Group>
              <Button
                variant="subtle"
                size="xs"
                onClick={() => setShowHistorial(!showHistorial)}
                loading={loadingHistorial}
              >
                {showHistorial ? 'Ocultar' : 'Mostrar'} ({historial.length})
              </Button>
            </Group>

            <Collapse in={showHistorial}>
              {historial.length === 0 ? (
                <Text size="sm" c="dimmed" ta="center" py="md">
                  {loadingHistorial ? 'Cargando historial...' : 'Sin historial disponible'}
                </Text>
              ) : (
                <Timeline active={0} lineWidth={2}>
                  {historial.map((entry) => (
                    <Timeline.Item key={entry.id} title={`Cambio a ${entry.estado_nuevo.replace('_', ' ').toUpperCase()}`}>
                      <Text size="xs" fw={500}>{entry.comentario_publico}</Text>
                      {entry.comentario_interno && (
                        <Text size="xs" c="blue" fs="italic">Interno: {entry.comentario_interno}</Text>
                      )}
                      <Text size="xs" c="dimmed" mt={2}>{formatDate(entry.fecha)}</Text>
                    </Timeline.Item>
                  ))}
                  <Timeline.Item title="Sugerencia Creada">
                    <Text size="xs" mt={2}>Ingresada al sistema</Text>
                  </Timeline.Item>
                </Timeline>
              )}
            </Collapse>
          </Paper>

          {selectedSugerencia.estado === 'pendiente' && (
            <Paper p="md" style={{ background: 'light-dark(var(--mantine-color-violet-0), var(--mantine-color-dark-5))' }} radius="md">
              <Text size="sm" fw={600} mb="md">Agendar para Reunion</Text>
              <Group>
                <DatePickerInput
                  label="Fecha de reunion"
                  placeholder="Seleccionar fecha"
                  value={agendarFecha}
                  onChange={setAgendarFecha}
                  minDate={new Date()}
                  style={{ flex: 1 }}
                />
                <Button color="violet" onClick={onAgendar} loading={agendando} disabled={!agendarFecha} mt={24}>
                  Agendar
                </Button>
              </Group>
            </Paper>
          )}

          <Paper p="md" style={{ background: 'light-dark(var(--mantine-color-blue-0), var(--mantine-color-dark-5))' }} radius="md">
            <Title order={6} size="sm" fw={600} mb="md">Gestión de la sugerencia</Title>
            <Stack gap="sm">
              <Select label="Cambiar Estado" data={ESTADO_OPTIONS} value={newEstado} onChange={(v) => setNewEstado(v || 'pendiente')} />
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
            <Button variant="light" color="red" leftSection={<IconTrash size={16} />} onClick={onDelete} loading={deleting}>
              Eliminar
            </Button>
            <Group>
              <Button variant="light" onClick={onClose}>Cancelar</Button>
              <Button onClick={onUpdate} loading={updating}>Registrar Gestión</Button>
            </Group>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
