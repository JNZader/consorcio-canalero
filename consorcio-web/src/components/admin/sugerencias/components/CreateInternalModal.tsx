import { Button, Group, Modal, Select, Stack, TextInput, Textarea } from '@mantine/core';
import { CATEGORIA_OPTIONS, PRIORIDAD_OPTIONS } from '../constants';

const INTERNAL_TOPIC_TITLE_ERROR_ID = 'internal-topic-title-error';
const INTERNAL_TOPIC_DESCRIPTION_ERROR_ID = 'internal-topic-description-error';

export function CreateInternalModal({
  opened,
  onClose,
  newTitulo,
  setNewTitulo,
  newDescripcion,
  setNewDescripcion,
  newCategoria,
  setNewCategoria,
  newPrioridad,
  setNewPrioridad,
  creating,
  onCreate,
  errors,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  newTitulo: string;
  setNewTitulo: (value: string) => void;
  newDescripcion: string;
  setNewDescripcion: (value: string) => void;
  newCategoria: string | null;
  setNewCategoria: (value: string | null) => void;
  newPrioridad: string;
  setNewPrioridad: (value: string) => void;
  creating: boolean;
  onCreate: () => void;
  errors?: {
    titulo?: string;
    descripcion?: string;
  };
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Nuevo Tema Interno" size="md">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onCreate();
        }}
        noValidate
      >
        <Stack gap="md">
          <TextInput
            label="Titulo"
            placeholder="Titulo del tema"
            value={newTitulo}
            onChange={(e) => setNewTitulo(e.target.value)}
            required
            error={errors?.titulo}
            errorProps={{
              id: INTERNAL_TOPIC_TITLE_ERROR_ID,
              role: 'alert',
              'aria-live': 'assertive',
            }}
          />
          <Textarea
            label="Descripcion"
            placeholder="Describe el tema a tratar..."
            value={newDescripcion}
            onChange={(e) => setNewDescripcion(e.target.value)}
            minRows={4}
            required
            error={errors?.descripcion}
            errorProps={{
              id: INTERNAL_TOPIC_DESCRIPTION_ERROR_ID,
              role: 'alert',
              'aria-live': 'assertive',
            }}
          />
          <Group grow>
            <Select
              label="Categoria"
              placeholder="Seleccionar"
              data={CATEGORIA_OPTIONS}
              value={newCategoria}
              onChange={setNewCategoria}
              clearable
            />
            <Select
              label="Prioridad"
              data={PRIORIDAD_OPTIONS}
              value={newPrioridad}
              onChange={(v) => setNewPrioridad(v || 'normal')}
            />
          </Group>
          <Group justify="flex-end" mt="md">
            <Button type="button" variant="light" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="submit" loading={creating}>
              Crear Tema
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
