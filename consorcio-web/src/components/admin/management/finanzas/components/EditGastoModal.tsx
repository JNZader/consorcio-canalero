import { Button, FileInput, Modal, Select, Stack, TextInput } from '@mantine/core';
import type { UseFormReturnType } from '@mantine/form';
import { IconUpload } from '../../../../ui/icons';
import type { Gasto } from '../finanzasTypes';

const EDIT_GASTO_CATEGORY_ERROR_ID = 'edit-gasto-category-error';

interface EditGastoFormValues {
  categoria: string;
}

export function EditGastoModal({
  opened,
  onClose,
  form,
  categoryData,
  editingGasto,
  onEditingGastoChange,
  comprobanteFile,
  setComprobanteFile,
  onOpenCategory,
  onSubmit,
  loading,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  form: UseFormReturnType<EditGastoFormValues>;
  categoryData: Array<{ value: string; label: string }>;
  editingGasto: Gasto | null;
  onEditingGastoChange: (value: string) => void;
  comprobanteFile: File | null;
  setComprobanteFile: (file: File | null) => void;
  onOpenCategory: () => void;
  onSubmit: (values: EditGastoFormValues) => void | Promise<void>;
  loading: boolean;
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Editar categoria de gasto">
      <form onSubmit={form.onSubmit(onSubmit)} noValidate>
        <Stack gap="sm">
          <Select
            label="Categoria"
            placeholder="Selecciona categoria"
            data={categoryData}
            searchable
            required
            {...form.getInputProps('categoria')}
            errorProps={{
              id: EDIT_GASTO_CATEGORY_ERROR_ID,
              role: 'alert',
              'aria-live': 'assertive',
            }}
          />
          <Button type="button" variant="subtle" size="xs" onClick={onOpenCategory}>
            Agregar categoria
          </Button>
          <TextInput
            label="Comprobante URL"
            placeholder="https://..."
            value={editingGasto?.comprobante_url || ''}
            onChange={(event) => onEditingGastoChange(event.currentTarget.value)}
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
            Actualizar categoria
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
