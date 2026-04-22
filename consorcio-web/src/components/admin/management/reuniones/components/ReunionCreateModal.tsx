import { ActionIcon, Button, Group, Modal, Stack, Text, TextInput, Textarea } from '@mantine/core';
import type { UseFormReturnType } from '@mantine/form';
import { IconTrash } from '../../../../ui/icons';

export interface ReunionCreateFormValues {
  titulo: string;
  fecha_reunion: string;
  lugar: string;
  descripcion: string;
  orden_del_dia_items: string[];
  tipo: string;
}

export function ReunionCreateModal({
  opened,
  onClose,
  form,
  newChecklistPoint,
  setNewChecklistPoint,
  onAddChecklistPoint,
  onSubmit,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  form: UseFormReturnType<ReunionCreateFormValues>;
  newChecklistPoint: string;
  setNewChecklistPoint: (value: string) => void;
  onAddChecklistPoint: () => void;
  onSubmit: (values: ReunionCreateFormValues) => void | Promise<void>;
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Nueva Reunion" size="lg">
      <form onSubmit={form.onSubmit(onSubmit)}>
        <Stack gap="sm">
          <TextInput
            label="Titulo"
            placeholder="Ej: Reunion de comision de marzo"
            required
            {...form.getInputProps('titulo')}
          />
          <TextInput
            type="datetime-local"
            label="Fecha y hora"
            required
            {...form.getInputProps('fecha_reunion')}
          />
          <TextInput
            label="Lugar"
            placeholder="Ej: Sede del consorcio"
            {...form.getInputProps('lugar')}
          />
          <Textarea
            label="Descripcion"
            placeholder="Temas generales a tratar"
            autosize
            minRows={2}
            {...form.getInputProps('descripcion')}
          />
          <Stack gap="xs">
            <Text fw={500} size="sm">
              Orden del dia (checklist)
            </Text>

            <Group align="flex-end" gap="xs">
              <TextInput
                value={newChecklistPoint}
                onChange={(event) => setNewChecklistPoint(event.currentTarget.value)}
                placeholder="Escribe un punto y pulsa Anadir"
                style={{ flex: 1 }}
              />
              <Button type="button" variant="light" onClick={onAddChecklistPoint}>
                Anadir punto
              </Button>
            </Group>

            <Stack gap="xs">
              {form.values.orden_del_dia_items.map((point, index) => (
                <Group key={`orden-${index}`} align="flex-start" gap="xs">
                  <Text size="sm" mt={8}>
                    {index + 1}.
                  </Text>
                  <TextInput
                    value={point}
                    onChange={(event) =>
                      form.setFieldValue(`orden_del_dia_items.${index}`, event.currentTarget.value)
                    }
                    placeholder={`Punto ${index + 1}`}
                    style={{ flex: 1 }}
                  />
                  <ActionIcon
                    type="button"
                    color="red"
                    variant="subtle"
                    onClick={() => form.removeListItem('orden_del_dia_items', index)}
                    aria-label={`Eliminar punto ${index + 1}`}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Group>
              ))}
            </Stack>

            {form.errors.orden_del_dia_items ? (
              <Text size="xs" c="red">
                {form.errors.orden_del_dia_items}
              </Text>
            ) : null}
          </Stack>
          <Button type="submit" mt="xs">
            Crear Reunion
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
