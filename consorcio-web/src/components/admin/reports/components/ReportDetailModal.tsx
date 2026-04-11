import { Badge, Button, Card, Group, Image, Modal, Paper, Select, SimpleGrid, Stack, Text, Textarea, Timeline, Title } from '@mantine/core';
import type { Report } from '../../../../lib/api';
import { CATEGORY_OPTIONS, STATUS_OPTIONS } from '../../../../constants';
import { formatDate } from '../../../../lib/formatters';
import type { SeguimientoEntry } from '../reportsPanelTypes';
import { IconHistory } from '../../../ui/icons';

export function ReportDetailModal({
  opened,
  onClose,
  selectedReport,
  history,
  loadingHistory,
  newStatus,
  setNewStatus,
  publicComment,
  setPublicComment,
  adminNotes,
  setAdminNotes,
  onUpdate,
  updating,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  selectedReport: Report | null;
  history: SeguimientoEntry[];
  loadingHistory: boolean;
  newStatus: string;
  setNewStatus: (value: string) => void;
  publicComment: string;
  setPublicComment: (value: string) => void;
  adminNotes: string;
  setAdminNotes: (value: string) => void;
  onUpdate: () => void;
  updating: boolean;
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Detalle de Denuncia" size="lg" aria-labelledby="modal-title-detail">
      {selectedReport && (
        <Stack gap="md">
          <SimpleGrid cols={2}>
            <div>
              <Text size="sm" fw={500}>Fecha</Text>
              <Text size="sm" c="gray.6">{formatDate(selectedReport.created_at, { includeTime: true })}</Text>
            </div>
            <div>
              <Text size="sm" fw={500}>Categoria</Text>
              <Badge variant="outline">
                {CATEGORY_OPTIONS.find((c) => c.value === selectedReport.categoria)?.label || selectedReport.categoria}
              </Badge>
            </div>
          </SimpleGrid>

          <div>
            <Text size="sm" fw={500} id="descripcion-label">Descripcion</Text>
            <Paper p="sm" style={{ background: 'light-dark(var(--mantine-color-gray-1), var(--mantine-color-dark-6))' }} radius="sm" aria-labelledby="descripcion-label">
              <Text size="sm">{selectedReport.descripcion}</Text>
            </Paper>
          </div>

          {selectedReport.ubicacion_texto && (
            <div>
              <Text size="sm" fw={500}>Ubicacion</Text>
              <Text size="sm" c="gray.6">{selectedReport.ubicacion_texto}</Text>
              {selectedReport.latitud != null && selectedReport.longitud != null && (
                <Text size="xs" c="gray.6">Coordenadas: {selectedReport.latitud}, {selectedReport.longitud}</Text>
              )}
            </div>
          )}

          {selectedReport.imagenes && selectedReport.imagenes.length > 0 && (
            <div>
              <Text size="sm" fw={500} mb="xs" id="imagenes-label">Imagenes adjuntas</Text>
              <SimpleGrid cols={3} aria-labelledby="imagenes-label">
                {selectedReport.imagenes.map((url) => (
                  <Card key={url} padding={0} radius="sm">
                    <Image src={url} alt={`Imagen de la denuncia sobre ${selectedReport.categoria || 'problema reportado'} en ${selectedReport.ubicacion_texto || 'ubicacion no especificada'}`} height={100} fit="cover" />
                  </Card>
                ))}
              </SimpleGrid>
            </div>
          )}

          {(selectedReport.contacto_nombre || selectedReport.contacto_telefono) && (
            <div>
              <Text size="sm" fw={500}>Contacto</Text>
              <Text size="sm" c="gray.6">
                {selectedReport.contacto_nombre}
                {selectedReport.contacto_telefono && ` - ${selectedReport.contacto_telefono}`}
              </Text>
            </div>
          )}

          <Paper p="md" style={{ background: 'light-dark(var(--mantine-color-blue-0), var(--mantine-color-dark-5))' }} radius="md">
            <Title order={6} mb="md" id="admin-section-label">Gestion del reporte</Title>
            <Stack gap="sm" aria-labelledby="admin-section-label">
              <Select label="Cambiar Estado" data={STATUS_OPTIONS} value={newStatus} onChange={(v) => setNewStatus(v || 'pendiente')} />
              <Textarea label="Comentario Publico" placeholder="Lo que el ciudadano vera..." value={publicComment} onChange={(e) => setPublicComment(e.target.value)} minRows={2} />
              <Textarea label="Notas Internas (Consorcio)" placeholder="Detalles tecnicos, costos, etc..." value={adminNotes} onChange={(e) => setAdminNotes(e.target.value)} minRows={2} />
            </Stack>
          </Paper>

          <div>
            <Group gap="xs" mb="sm">
              <IconHistory size={18} />
              <Text fw={600} size="sm">Historial de Seguimiento</Text>
            </Group>
            {loadingHistory ? (
              <Text size="sm">Cargando...</Text>
            ) : (
              <Timeline active={0} lineWidth={2}>
                {history.map((entry) => (
                  <Timeline.Item key={entry.id} title={`Cambio a ${entry.estado_nuevo.replace('_', ' ').toUpperCase()}`}>
                    <Text size="xs" fw={500}>{entry.comentario_publico}</Text>
                    {entry.comentario_interno && <Text size="xs" c="blue" fs="italic">Interno: {entry.comentario_interno}</Text>}
                    <Text size="xs" c="dimmed" mt={2}>{formatDate(entry.fecha, { includeTime: true })}</Text>
                  </Timeline.Item>
                ))}
                <Timeline.Item title="Reporte Creado">
                  <Text size="xs" mt={2}>Ingresado al sistema</Text>
                </Timeline.Item>
              </Timeline>
            )}
          </div>

          <Group justify="flex-end">
            <Button variant="light" onClick={onClose}>Cancelar</Button>
            <Button onClick={onUpdate} loading={updating}>Registrar Gestion</Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
