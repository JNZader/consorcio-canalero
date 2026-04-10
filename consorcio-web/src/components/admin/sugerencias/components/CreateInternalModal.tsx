import { Button, Group, Modal, Select, Stack, Textarea, TextInput } from '@mantine/core';
import { CATEGORIA_OPTIONS, PRIORIDAD_OPTIONS } from '../constants';

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
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Nuevo Tema Interno" size="md">
      <Stack gap="md">
        <TextInput
          label="Titulo"
          placeholder="Titulo del tema"
          value={newTitulo}
          onChange={(e) => setNewTitulo(e.target.value)}
          required
        />
        <Textarea
          label="Descripcion"
          placeholder="Describe el tema a tratar..."
          value={newDescripcion}
          onChange={(e) => setNewDescripcion(e.target.value)}
          minRows={4}
          required
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
          <Button variant="light" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={onCreate} loading={creating}>
            Crear Tema
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
