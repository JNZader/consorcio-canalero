import { Button, Modal, NativeSelect, Stack } from '@mantine/core';
import type { UseFormReturnType } from '@mantine/form';

const EDIT_GASTO_CATEGORY_ERROR_ID = 'edit-gasto-category-error';
interface EditGastoFormValues {
  categoria: string;
}

export function EditGastoModal({
  opened,
  onClose,
  form,
  categoryData,
  onSubmit,
  submitting,
}: Readonly<{
  opened: boolean;
  onClose: () => void;
  form: UseFormReturnType<EditGastoFormValues>;
  categoryData: Array<{ value: string; label: string }>;
  onSubmit: (values: EditGastoFormValues) => void | Promise<void>;
  submitting: boolean;
}>) {
  return (
    <Modal opened={opened} onClose={onClose} title="Editar categoría de gasto">
      <form onSubmit={form.onSubmit(onSubmit)} noValidate>
        <Stack gap="sm">
          <NativeSelect
            label="Categoría"
            data={categoryData}
            required
            {...form.getInputProps('categoria')}
            errorProps={{
              id: EDIT_GASTO_CATEGORY_ERROR_ID,
              role: 'alert',
              'aria-live': 'assertive',
            }}
          />
          <Button type="submit" fullWidth mt="md" loading={submitting}>
            Actualizar categoría
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
