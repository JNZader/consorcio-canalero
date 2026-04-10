import { Button, FileInput, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core';
import type { UseFormReturnType } from '@mantine/form';
import { IconUpload } from '../../../../ui/icons';

export interface IngresoFormValues {
  descripcion: string;
  monto: number;
  fuente: string;
  pagador: string;
  comprobante_url: string;
  fecha: string;
}

export function IngresoFormModal({
  opened,
  onClose,
  form,
  sourceData,
  comprobanteFile,
  setComprobanteFile,
  onOpenSource,
  onSubmit,
  loading,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  form: UseFormReturnType<IngresoFormValues>;
  sourceData: Array<{ value: string; label: string }>;
  comprobanteFile: File | null;
  setComprobanteFile: (file: File | null) => void;
  onOpenSource: () => void;
  onSubmit: (values: IngresoFormValues) => void | Promise<void>;
  loading: boolean;
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Registrar Ingreso">
      <form onSubmit={form.onSubmit(onSubmit)}>
        <Stack gap="sm">
          <TextInput
            label="Descripcion"
            placeholder="Ej: Subsidio provincial"
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
              label="Fuente"
              placeholder="Selecciona una fuente"
              data={sourceData}
              searchable
              required
              {...form.getInputProps('fuente')}
            />
          </SimpleGrid>
          <Group justify="space-between" gap="xs">
            <Text size="xs" c="dimmed">
              No aparece la fuente?
            </Text>
            <Button type="button" variant="subtle" size="xs" onClick={onOpenSource}>
              Agregar fuente
            </Button>
          </Group>
          <SimpleGrid cols={2}>
            <TextInput
              label="Pagador"
              placeholder="Ej: Ministerio de Produccion"
              {...form.getInputProps('pagador')}
            />
            <TextInput type="date" label="Fecha" {...form.getInputProps('fecha')} />
          </SimpleGrid>
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
          <Button type="submit" fullWidth mt="md" color="green" loading={loading}>
            Guardar Ingreso
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
