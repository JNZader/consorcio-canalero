import { Button, FileInput, Modal, NumberInput, Select, SimpleGrid, Stack, TextInput } from '@mantine/core';
import type { UseFormReturnType } from '@mantine/form';
import { IconUpload } from '../../../../ui/icons';
import type { IngresoFormValues } from './IngresoFormModal';

export function EditIngresoModal({
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
    <Modal opened={opened} onClose={onClose} title="Editar ingreso">
      <form onSubmit={form.onSubmit(onSubmit)}>
        <Stack gap="sm">
          <TextInput label="Descripcion" required {...form.getInputProps('descripcion')} />
          <SimpleGrid cols={2}>
            <NumberInput label="Monto ($)" required hideControls {...form.getInputProps('monto')} />
            <Select
              label="Fuente"
              placeholder="Selecciona fuente"
              data={sourceData}
              searchable
              required
              {...form.getInputProps('fuente')}
            />
          </SimpleGrid>
          <Button type="button" variant="subtle" size="xs" onClick={onOpenSource}>
            Agregar fuente
          </Button>
          <SimpleGrid cols={2}>
            <TextInput label="Pagador" {...form.getInputProps('pagador')} />
            <TextInput type="date" label="Fecha" {...form.getInputProps('fecha')} />
          </SimpleGrid>
          <TextInput
            label="Comprobante (URL foto/PDF)"
            placeholder="https://..."
            {...form.getInputProps('comprobante_url')}
          />
          <FileInput
            label="Reemplazar comprobante"
            placeholder="Imagen o PDF"
            value={comprobanteFile}
            onChange={setComprobanteFile}
            accept="image/jpeg,image/png,image/webp,application/pdf"
            leftSection={<IconUpload size={16} />}
            clearable
          />
          <Button type="submit" fullWidth mt="md" loading={loading}>
            Actualizar ingreso
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
