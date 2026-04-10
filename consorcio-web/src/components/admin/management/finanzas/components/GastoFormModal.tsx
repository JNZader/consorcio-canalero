import { Button, FileInput, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core';
import type { FormEvent } from 'react';
import { IconUpload } from '../../../../ui/icons';

type FormValues = Record<string, unknown>;

interface InputPropsLike extends Record<string, unknown> {
  value?: unknown;
  onChange?: (...args: unknown[]) => void;
  error?: unknown;
}

interface SimpleFormLike {
  values: FormValues;
  getInputProps: (field: string) => InputPropsLike;
  onSubmit: (
    handler: (values: FormValues) => void | Promise<void>,
  ) => (event?: FormEvent<HTMLFormElement>) => void;
}

export function GastoFormModal({
  opened,
  onClose,
  form,
  categoryData,
  comprobanteFile,
  setComprobanteFile,
  onOpenCategory,
  onSubmit,
  loading,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  form: SimpleFormLike;
  categoryData: Array<{ value: string; label: string }>;
  comprobanteFile: File | null;
  setComprobanteFile: (file: File | null) => void;
  onOpenCategory: () => void;
  onSubmit: (values: FormValues) => void | Promise<void>;
  loading: boolean;
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Registrar Gasto de Caja">
      <form onSubmit={form.onSubmit(onSubmit)}>
        <Stack gap="sm">
          <TextInput
            label="Descripcion del Gasto"
            placeholder="Ej: Compra de 500L gasoil"
            required
            {...form.getInputProps('descripcion')}
          />
          <SimpleGrid cols={2}>
            <NumberInput
              label="Monto ($)"
              placeholder="0.00"
              required
              hideControls
              {...form.getInputProps('monto')}
            />
            <Select
              label="Categoria"
              placeholder="Selecciona una categoria"
              data={categoryData}
              searchable
              required
              {...form.getInputProps('categoria')}
            />
          </SimpleGrid>
          <Group justify="space-between" gap="xs">
            <Text size="xs" c="dimmed">
              No aparece la categoria?
            </Text>
            <Button type="button" variant="subtle" size="xs" onClick={onOpenCategory}>
              Agregar categoria
            </Button>
          </Group>
          <TextInput type="date" label="Fecha" {...form.getInputProps('fecha')} />
          <TextInput
            label="Comprobante (URL foto/PDF)"
            placeholder="https://..."
            {...form.getInputProps('comprobante_url')}
          />
          <FileInput
            label="O subir comprobante"
            placeholder="Imagen o PDF"
            value={comprobanteFile}
            onChange={setComprobanteFile}
            accept="image/jpeg,image/png,image/webp,application/pdf"
            leftSection={<IconUpload size={16} />}
            clearable
          />
          <Button type="submit" fullWidth mt="md" color="red" loading={loading}>
            Guardar Gasto
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
