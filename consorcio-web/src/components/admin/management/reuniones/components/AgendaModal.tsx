import {
  ActionIcon,
  Badge,
  Button,
  Divider,
  Group,
  Modal,
  MultiSelect,
  Paper,
  Stack,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core';
import type { UseFormReturnType } from '@mantine/form';
import { IconLink, IconPlus, IconTrash } from '../../../../ui/icons';
import { getAgendaReferenceColor, hasAgendaItems } from '../reunionesUtils';
import type { AgendaItem, EntityOption, Reunion } from '../reunionesTypes';

export interface AgendaFormValues {
  titulo: string;
  descripcion: string;
  referencias: string[];
}

export function AgendaModal({
  opened,
  onClose,
  selectedReunion,
  agenda,
  exporting,
  onExport,
  form,
  onAddTopic,
  availableEntities,
  loadingEntities,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  selectedReunion: Reunion | null;
  agenda: AgendaItem[];
  exporting: boolean;
  onExport: () => void | Promise<void>;
  form: UseFormReturnType<AgendaFormValues>;
  onAddTopic: (values: AgendaFormValues) => void | Promise<void>;
  availableEntities: EntityOption[];
  loadingEntities: boolean;
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Orden del Dia" size="xl">
      {selectedReunion && (
        <Stack gap="md">
          <Group justify="space-between">
            <div>
              <Text fw={700} size="lg">
                {selectedReunion.titulo}
              </Text>
              <Text size="sm" c="dimmed">
                {new Date(selectedReunion.fecha_reunion).toLocaleString()}
              </Text>
              {selectedReunion.descripcion ? (
                <Text size="sm" c="dimmed">
                  {selectedReunion.descripcion}
                </Text>
              ) : null}
              {hasAgendaItems(selectedReunion.orden_del_dia_items) ? (
                <ol style={{ margin: 0, paddingLeft: 18 }}>
                  {selectedReunion.orden_del_dia_items?.map((item, index) => (
                    <li key={`${selectedReunion.id}-detalle-orden-${index}`}>
                      <Text size="sm">{item}</Text>
                    </li>
                  ))}
                </ol>
              ) : null}
            </div>
            <Button size="xs" variant="outline" onClick={onExport} loading={exporting}>
              Exportar PDF
            </Button>
          </Group>

          <Divider label="Temas a Tratar" labelPosition="center" />

          {agenda.length === 0 ? (
            <Paper p="xl" withBorder style={{ borderStyle: 'dashed' }}>
              <Text ta="center" c="dimmed">
                No hay temas en la agenda todavia.
              </Text>
            </Paper>
          ) : (
            <Stack gap="sm">
              {agenda.map((item, index) => (
                <Paper key={item.id} p="md" withBorder radius="md">
                  <Group justify="space-between" align="flex-start">
                    <div style={{ flex: 1 }}>
                      <Text fw={600}>
                        {index + 1}. {item.titulo}
                      </Text>
                      <Text size="sm" c="dimmed" mb="xs">
                        {item.descripcion}
                      </Text>

                      {item.referencias && item.referencias.length > 0 && (
                        <Group gap="xs" mt="xs">
                          {item.referencias.map((ref, refIndex) => (
                            <Badge
                              key={`${item.id}-${refIndex}`}
                              size="xs"
                              variant="outline"
                              color={getAgendaReferenceColor(ref.entidad_tipo)}
                              leftSection={<IconLink size={10} />}
                            >
                              {ref.metadata?.label ||
                                `${ref.entidad_tipo.toUpperCase()} #${ref.entidad_id.slice(0, 5)}`}
                            </Badge>
                          ))}
                        </Group>
                      )}
                    </div>
                    <ActionIcon color="red" variant="subtle">
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Group>
                </Paper>
              ))}
            </Stack>
          )}

          <Paper p="md" bg="gray.0" radius="md">
            <Text fw={600} size="sm" mb="sm">
              Agregar Tema a la Agenda
            </Text>
            <form onSubmit={form.onSubmit(onAddTopic)}>
              <Stack gap="xs">
                <TextInput
                  placeholder="Titulo del tema (Ej: Reparacion Puente FFCC)"
                  size="sm"
                  required
                  {...form.getInputProps('titulo')}
                />
                <Textarea
                  placeholder="Descripcion o puntos a discutir..."
                  size="sm"
                  {...form.getInputProps('descripcion')}
                />
                <MultiSelect
                  label="Vincular con (@)"
                  placeholder="Escribe para buscar reportes, tramites o activos..."
                  data={availableEntities}
                  searchable
                  nothingFoundMessage="No se encontro nada..."
                  clearable
                  size="sm"
                  {...form.getInputProps('referencias')}
                />
                <Group justify="flex-end" mt="xs">
                  <Button
                    type="submit"
                    size="xs"
                    leftSection={<IconPlus size={14} />}
                    loading={loadingEntities}
                  >
                    Anadir Tema
                  </Button>
                </Group>
              </Stack>
            </form>
          </Paper>
        </Stack>
      )}
    </Modal>
  );
}
