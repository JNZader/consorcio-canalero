import {
  Button,
  Modal,
  NativeSelect,
  NumberInput,
  SimpleGrid,
  Stack,
  TextInput,
} from '@mantine/core';
import type { UseFormReturnType } from '@mantine/form';

const EDIT_GASTO_DESCRIPTION_ERROR_ID = 'edit-gasto-description-error';
const EDIT_GASTO_AMOUNT_ERROR_ID = 'edit-gasto-amount-error';
const EDIT_GASTO_CATEGORY_ERROR_ID = 'edit-gasto-category-error';

export interface EditGastoFormValues {
  categoria: string;
  descripcion?: string;
  monto?: number;
  fecha?: string;
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
    <Modal opened={opened} onClose={onClose} title="Editar gasto">
      <form onSubmit={form.onSubmit(onSubmit)} noValidate>
        <Stack gap="sm">
          <TextInput
            label="Descripción"
            required
            {...form.getInputProps('descripcion')}
            errorProps={{
              id: EDIT_GASTO_DESCRIPTION_ERROR_ID,
              role: 'alert',
              'aria-live': 'assertive',
            }}
          />
          <SimpleGrid cols={2}>
            <NumberInput
              label="Monto ($)"
              required
              hideControls
              {...form.getInputProps('monto')}
              errorProps={{
                id: EDIT_GASTO_AMOUNT_ERROR_ID,
                role: 'alert',
                'aria-live': 'assertive',
              }}
            />
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
          </SimpleGrid>
          <TextInput type="date" label="Fecha" required {...form.getInputProps('fecha')} />
          <Button type="submit" fullWidth mt="md" loading={submitting}>
            Actualizar gasto
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
